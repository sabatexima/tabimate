"""プラン生成ワークフローを構成する各エージェント（ノード）の実装。

各関数は TravelPlanState を受け取り、担当領域の成果物を計算して
更新分の辞書を返す（LangGraph のノード規約）。役割:
  - transport_agent          : 往復交通費を試算し残予算を算出
  - sightseeing_candidates / sightseeing_expert : 観光スポットの候補抽出→選定
  - accommodation_candidates / accommodation_agent : 宿泊施設の候補抽出→選定
  - gourmet_candidates / gourmet_hunter         : 飲食店の候補抽出→選定
  - timekeeper               : 時系列スケジュールの組み立て
  - cost_manager             : 費用見積もりの作成
  - balancer                 : プラン全体を審査し承認/差し戻しを判定
  - route_after_balancer     : 審査結果に応じて次ノードへの分岐を決める

LLM 呼び出しは llm.with_structured_output で型付き出力を得て、
invoke_with_retry でリトライしながら実行する。

AIへの指示文（プロンプト）の文面は chat/prompts.py にある。ここに置くのは、
検索・予算の計算・結果の検証・差し戻しの分岐といった「処理」だけ。
"""

import re
from concurrent.futures import ThreadPoolExecutor
from services.weather import parse_duration
from chat.models import TravelPlanState
from chat.llm import llm, llm_strong, invoke_with_retry, build_search_context
from chat import prompts as P
from logger import get_logger
from chat.models import (
    DestinationChoice, TransportOutput, SightseeingOutput, GourmetOutput,
    TimekeeperOutput, AccommodationOutput, CostOutput, BalancerOutput,
    SightseeingCandidatesOutput, GourmetCandidatesOutput, AccommodationCandidatesOutput,
)

log = get_logger("agents")

ACCOMMODATION_BUDGET_RATIO = 0.40  # 残予算に占める宿泊費の上限割合
FOOD_BUDGET_RATIO          = 0.25  # 残予算に占める食費の上限割合
MAX_BALANCER_RETRIES       = 5     # バランサー差し戻し上限回数


def is_day_trip(duration: str) -> bool:
    """宿泊なし（日帰り・0泊）かどうかを判定する。

    注意: 「0泊2日」（夜行）も True（宿は取らない）。ただし行程は2日分あるため、
    スケジュール・食事・費用の日数は parse_duration() の日数側で判断すること。
    """
    return parse_duration(duration)[0] == 0


def _pp(data, label):
    """抽出した項目リストをラベル付きでログに整形出力する。"""
    if not data:
        return
    log.info(label)
    for item in data:  # type: ignore[arg-type]
        log.info("  - %s", item)


def _run_set(state) -> set | None:
    """部分編集時に再生成すべき領域の集合を返す。

    edit_targets が空（＝フル生成）の場合は None を返し、全ノードを実行する。
    観光/グルメ/宿泊/交通を変えるとスケジュールが、何かを変えると費用が
    影響を受けるため、依存関係を加味して再計算対象を広げる。
    """
    targets = set(state.get("edit_targets") or [])
    if not targets or "all" in targets:
        return None
    run = set(targets)
    if run & {"sightseeing", "gourmet", "accommodation", "transport"}:
        run.add("schedule")   # 構成要素が変わればスケジュールも組み直す
    run.add("budget")         # 費用は常に再計算して整合を保つ
    return run


def _skip(state, area: str) -> bool:
    """部分編集で、この領域を再生成せず前回の成果物を引き継ぐ場合 True。"""
    run = _run_set(state)
    return run is not None and area not in run


def _filter_real_places(names: list, destination: str, min_keep: int,
                        country: str | None = "jp") -> list:
    """候補名を Google Places で実在確認し、見つからない名前を候補から落とす。

    プロンプトで「実在する店のみ」と指示してもLLMは店名を創作することがある
    （例:「海鮮処 磯丸」）。GOOGLE_MAPS_API_KEY 設定時のみ動き、未設定なら素通し。
    検証できない名前（None＝APIエラー等）は落とさない。実在確認できた候補が
    min_keep 未満になる場合は、選択肢を保つため絞り込みを諦めて全件返す。
    """
    from services.geocoding import verify_place_exists
    names = list(names or [])
    if not names:
        return []
    # 1件ずつ順に問い合わせると候補数ぶんの往復が直列に積み上がる（8件で8往復）。
    # 互いに独立な問い合わせなので並列にして待ち時間を候補数ぶんの1に縮める（順序は維持）。
    with ThreadPoolExecutor(max_workers=min(8, len(names))) as ex:
        verdicts = list(ex.map(lambda n: verify_place_exists(n, destination, country=country), names))
    checked = list(zip(names, verdicts))
    dropped = [n for n, ok in checked if ok is False]
    if not dropped:
        return names
    kept = [n for n, ok in checked if ok is not False]
    if len(kept) < min_keep:
        log.info("[実在確認] 未確認候補が多いため絞り込みを中止: dropped=%s", dropped)
        return names
    log.info("[実在確認] Google Placesで見つからず候補から除外: %s", dropped)
    return kept


# 車での移動を指す言い回し。表記ゆれが多いので、完全一致ではなく「含むか」で見る。
_CAR_WORDS = ("車", "カー", "ドライブ", "自家用", "マイカー", "car")


def _is_car(mode: str) -> bool:
    """交通手段の文字列が車での移動を指しているか（運転しない人の除外判定用）。

    「電車」「自転車」「乗車」は車ではないので、先に取り除いてから見る。
    """
    m = (mode or "").lower()
    for not_a_car in ("電車", "汽車", "自転車", "乗車", "下車", "駐車", "列車", "停車"):
        m = m.replace(not_a_car, "")
    return any(w in m for w in _CAR_WORDS)


def _clearly_specific(destination: str) -> bool:
    """地図の行政界から、市町村くらいの広さだと分かる行き先か。

    分からない（見つからない・通信できない・行政界が無く既定の半径になった）ときは
    False（＝AI に判断させる）。「関東」「どこでも」はここで弾かれず、AI に回る。
    """
    try:
        from services.geocoding import _MAX_DIST_KM
        from services.weather import dest_center
        center = dest_center(destination)
    except Exception:
        return False
    return bool(center) and float(center.get("radius_km") or _MAX_DIST_KM) < _MAX_DIST_KM


def settle_destination(state: TravelPlanState):
    """行き先が広すぎる（「日本」「関東」「どこでも」など）とき、具体的なエリアを1つ決める。

    交通費・天気・地図・検索はすべて行き先で決まるので、生成のいちばん最初に呼ぶ。
    広すぎる行き先のまま進むと、交通費を「東京→日本」で見積もってから観光地を
    京都に決める、といった食い違いが起きる。

    決めたときは destination を決めたエリアに置き換え、元の言い方と理由を
    destination_request / destination_note に残す（プランのカードでお客さまに伝える）。
    判断できない・失敗したときは何も変えない（元の行き先で生成を続ける）。
    """
    dest = str(state.get("destination") or "").strip()
    if not dest:
        return {}
    # 地図で市町村くらいの広さだと分かる行き先は、AI に聞くまでもない（呼び出しと
    # 1〜2秒の待ちを省く。照会は後で国を調べるのと同じもので、結果は使い回される）
    if not state.get("avoid_area") and _clearly_specific(dest):
        return {}
    prompt = P.destination_prompt(state)
    try:
        structured_llm = llm.with_structured_output(DestinationChoice)
        response = invoke_with_retry(structured_llm, prompt)
    except Exception:
        log.warning("行き先の判断に失敗。元の行き先のまま進めます: destination=%s", dest, exc_info=True)
        return {}
    area = str(response.area or "").strip()
    if not response.is_broad or not area or area == dest:
        return {}
    log.info("🧭 行き先が広いため具体化: %s → %s（%s）", dest, area, response.reason)
    return {"destination": area, "destination_request": dest,
            "destination_note": str(response.reason or "").strip()}


def transport_agent(state: TravelPlanState):
    """往復交通費を概算し、予算上限から差し引いた残予算を返す。

    交通費が予算上限を超える場合は ValueError を送出して以降の処理を止める。
    """
    if _skip(state, "transport"):
        return {}  # 部分編集: 交通は対象外。前回の交通費・残予算を引き継ぐ
    transport_mode = state.get("transport_mode", "おまかせ")
    no_car = state.get("no_car", False)
    # 運転免許なしの場合は車・レンタカーを使わない（誤って車指定でも公共交通に切替）。
    # 完全一致で見ると「自動車」「レンタカー（現地で借りる）」のような書き方をすり抜け、
    # 運転しない人に「この手段で固定」と指示してしまうので、語を含むかで判定する。
    if no_car and _is_car(transport_mode):
        transport_mode = "おまかせ"
    log.info(
        "[🚄 交通エージェント]: 往復交通費を試算中... destination=%s, mode=%s, no_car=%s",
        state["destination"], transport_mode, no_car,
    )

    prompt = P.transport_prompt(state, transport_mode, no_car)
    structured_llm = llm.with_structured_output(TransportOutput)
    response = invoke_with_retry(structured_llm, prompt)
    remaining = state["budget_limit"] - response.transport_cost
    if remaining <= 0:
        if state.get("destination_request"):
            # 行き先は AI が選んだもの。お客さまの行き先が悪いような言い方をしない
            raise ValueError(
                f"「{state['destination_request']}」の中から選んだ「{state['destination']}」でも、"
                f"往復交通費（{response.transport_cost:,}円/人）が予算上限（{state['budget_limit']:,}円/人）を"
                "超えてしまいました。予算を増やすか、出発地から近い行き先を教えてください。"
            )
        raise ValueError(
            f"往復交通費（{response.transport_cost:,}円/人）が予算上限（{state['budget_limit']:,}円/人）を超えています。予算を増やすか目的地を変更してください。"
        )
    log.info("🚄 往復交通費: %s円/人 -> 残り予算: %s円/人", f"{response.transport_cost:,}", f"{remaining:,}")
    return {"transport_cost": response.transport_cost, "remaining_budget": remaining}


def sightseeing_candidates(state: TravelPlanState):
    """Web検索を踏まえ、観光スポットの候補（5〜8件）を抽出する。"""
    if _skip(state, "sightseeing"):
        return {}  # 部分編集: 観光は対象外
    log.info("[🗺️ 観光エキスパート]: 候補スポットを抽出中... destination=%s", state["destination"])
    queries = [
        f"{state['destination']} {' '.join(state['themes'])} 観光 公式ガイド",
        f"{state['destination']} 観光協会 おすすめスポット",
    ]
    if any("車椅子" in r for r in state["special_requirements"]):
        queries.append(f"{state['destination']} バリアフリー 観光スポット 車椅子対応")
    search_context = build_search_context(queries)

    prompt = P.sightseeing_candidates_prompt(state, search_context)
    structured_llm = llm.with_structured_output(SightseeingCandidatesOutput)
    response = invoke_with_retry(structured_llm, prompt)
    # LLMが創作したスポット名を候補段階で落とす（Google Placesキー設定時のみ）
    candidates = _filter_real_places(response.candidates, state["destination"], min_keep=4,
                                     country=state.get("dest_country") or "jp")
    _pp(candidates, "✨ 候補スポット:")
    return {"spot_candidates": candidates}


def sightseeing_expert(state: TravelPlanState):
    """候補スポットから動線・条件を考慮して最終的なスポット（2〜3件）を選定する。"""
    if _skip(state, "sightseeing"):
        return {}  # 部分編集: 観光は対象外。前回のスポットを引き継ぐ
    log.info("[🗺️ 観光エキスパート]: スポットを選定中... destination=%s", state["destination"])
    # 1日を充実させられる件数を期間から見積もる（1日行程は3〜4、1日増えるごとに+2目安）
    _days = parse_duration(state["duration"])[1]
    target_spots = 4 if _days <= 1 else min(3 + 2 * (_days - 1), 6)
    prompt = P.sightseeing_prompt(state, target_spots)
    structured_llm = llm.with_structured_output(SightseeingOutput)
    response = invoke_with_retry(structured_llm, prompt)
    _pp(response.spots, "✨ 選定スポット:")
    return {"spots": response.spots}


def accommodation_candidates(state: TravelPlanState):
    """宿泊施設の候補（3〜5件）を抽出する。日帰りなら空リストを返す。"""
    if _skip(state, "accommodation"):
        return {}  # 部分編集: 宿泊は対象外
    if is_day_trip(state["duration"]):
        log.info("[🏨 宿泊エージェント]: 日帰りのため宿泊施設なし")
        return {"accommodation_candidates": []}
    log.info("[🏨 宿泊エキスパート]: 宿泊候補を抽出中... destination=%s", state["destination"])
    num_nights = max(parse_duration(state["duration"])[0], 1)
    # 1泊あたりの予算目安（残予算の40%を泊数で割る）。この価格帯で泊まれる候補を集める。
    per_night_budget = int(state.get("remaining_budget", 0) * ACCOMMODATION_BUDGET_RATIO) // max(num_nights, 1)
    queries = [
        f"{state['destination']} ホテル 旅館 おすすめ {(state['themes'] or [''])[0]} 公式",
        f"{state['destination']} 宿泊 1泊 {per_night_budget}円以内 おすすめ",
        f"{state['destination']} 格安 ビジネスホテル ゲストハウス",
    ]
    if any("車椅子" in r for r in state["special_requirements"]):
        queries.append(f"{state['destination']} バリアフリー ホテル 車椅子対応 ユニバーサルルーム")
    search_context = build_search_context(queries)
    prompt = P.accommodation_candidates_prompt(state, num_nights, per_night_budget, search_context)
    structured_llm = llm.with_structured_output(AccommodationCandidatesOutput)
    response = invoke_with_retry(structured_llm, prompt)
    # LLMが創作した宿名を候補段階で落とす（Google Placesキー設定時のみ）
    accommodation = _filter_real_places(response.accommodation, state["destination"], min_keep=2,
                                        country=state.get("dest_country") or "jp")
    _pp(accommodation, "🏨 候補宿泊施設:")
    return {"accommodation_candidates": accommodation}


def accommodation_agent(state: TravelPlanState):
    """予算配分（残予算の40%）内で最適な宿泊施設(1〜2件)を選定する。

    日帰りなら空リストを返す。バランサーの差し戻しやユーザー要望があれば
    プロンプトに反映して選び直す。
    """
    if _skip(state, "accommodation"):
        return {}  # 部分編集: 宿泊は対象外。前回の宿泊を引き継ぐ
    if is_day_trip(state["duration"]):
        log.info("[🏨 宿泊エージェント]: 日帰りのため宿泊施設なし")
        return {"accommodation": []}
    log.info("[🏨 宿泊エージェント]: 宿泊施設を選定中... destination=%s", state["destination"])
    num_nights = max(parse_duration(state["duration"])[0], 1)
    total_accommodation_budget = int(state["remaining_budget"] * ACCOMMODATION_BUDGET_RATIO)
    per_night_budget = total_accommodation_budget // num_nights
    prompt = P.accommodation_prompt(state, num_nights, total_accommodation_budget, per_night_budget)
    structured_llm = llm.with_structured_output(AccommodationOutput)
    response = invoke_with_retry(structured_llm, prompt)
    _pp(response.accommodation, "🏨 選定宿泊施設:")
    return {"accommodation": response.accommodation}


def gourmet_candidates(state: TravelPlanState):
    """選定済みスポット周辺の飲食店候補（4〜6件）を抽出する。"""
    if _skip(state, "gourmet"):
        return {}  # 部分編集: グルメは対象外
    log.info("[🍣 グルメハンター]: 飲食店候補を抽出中... destination=%s", state["destination"])
    spots = state.get("spots", [])
    # 宿はこの時点で決まっている（グラフ順が 宿 → グルメ）。
    # タイムキーパーには「夕食は宿の徒歩圏で」と指示しているのに、候補を集める段階で
    # 宿を知らないと徒歩圏の店が1軒も入らず、その指示を満たしようがなかった。
    stay = state.get("accommodation", [])
    queries = [
        f"{state['destination']} {' '.join(spots)} 周辺 レストラン おすすめ",
        f"{state['destination']} 郷土料理 地元名物 人気店",
    ]
    if stay:
        queries.append(f"{state['destination']} {stay[0]} 周辺 徒歩圏 夕食")
    if any("アレルギー" in r for r in state["special_requirements"]):
        queries.append(f"{state['destination']} 魚介類アレルギー対応 レストラン")
    if any("車椅子" in r for r in state["special_requirements"]):
        queries.append(f"{state['destination']} バリアフリー レストラン 車椅子対応")
    search_context = build_search_context(queries)

    prompt = P.gourmet_candidates_prompt(state, spots, stay, search_context)
    structured_llm = llm.with_structured_output(GourmetCandidatesOutput)
    response = invoke_with_retry(structured_llm, prompt)
    # LLMが創作した店名を候補段階で落とす（Google Placesキー設定時のみ）
    restaurants = _filter_real_places(response.restaurants, state["destination"], min_keep=3,
                                      country=state.get("dest_country") or "jp")
    _pp(restaurants, "🍱 候補飲食店:")
    return {"restaurant_candidates": restaurants}


def gourmet_hunter(state: TravelPlanState):
    """候補から食事回数分の飲食店を選定する（食費目安は残予算の25%）。"""
    if _skip(state, "gourmet"):
        return {}  # 部分編集: グルメは対象外。前回の飲食店を引き継ぐ
    log.info("[🍣 グルメハンター]: 飲食店を選定中... destination=%s", state["destination"])
    # 食費の目安上限（残予算の FOOD_BUDGET_RATIO）
    food_budget = int(state['remaining_budget'] * FOOD_BUDGET_RATIO)
    # 食事回数は「日数」で決める（0泊2日の夜行でも2日分の食事が必要）
    _days = parse_duration(state["duration"])[1]
    meals = f"昼食×{_days}" + (f" + 夕食×{_days - 1}" if _days >= 2 else "")

    prompt = P.gourmet_prompt(state, meals, food_budget)
    structured_llm = llm.with_structured_output(GourmetOutput)
    response = invoke_with_retry(structured_llm, prompt)
    _pp(response.restaurants, "🍱 選定飲食店:")
    return {"restaurants": response.restaurants}


def timekeeper(state: TravelPlanState):
    """スポット・飲食店・宿泊施設を時系列スケジュールに組み立てる。

    営業時間や移動時間の整合を取り、日帰り/宿泊で出力形式を切り替える。
    バランサーが指摘した未反映項目は強制的に組み込む。
    """
    if _skip(state, "schedule"):
        return {}  # 部分編集: スケジュールは対象外。前回の行程を引き継ぐ
    log.info("[⏱️ タイムキーパー]: スケジュールを組み立て中... destination=%s", state["destination"])
    # 泊数と日数を分けて扱う（0泊2日の夜行は「宿なし・2日行程」）。
    num_nights, num_days = parse_duration(state["duration"])
    day_trip = num_days <= 1
    prompt = P.schedule_prompt(state)
    # スケジュール作成は全エージェント中で最難関（地理・移動時間・営業時間・日数構成を
    # 同時に満たす）ため、上位モデルを使う。lite だと別エリアの施設を近所扱いする等の
    # 誤りが出て審査ループの主因になっていた。
    structured_llm = llm_strong.with_structured_output(TimekeeperOutput)
    response = invoke_with_retry(structured_llm, prompt)

    # 日数の検証（宿泊プランのみ）: 「1日目」〜「N+1日目」のブロックが全て揃っているか。
    # LLMは長期プランで最終日を省略したり途中で帰路に入れることがあるため、
    # 欠けていたら欠落日を明示して1回だけ作り直す（それでも駄目ならバランサーが差し戻す）。
    if not day_trip:
        total_days = num_days
        def _days_in(schedule):
            """スケジュールの行から「N日目」を拾って、揃っている日の集合を返す。"""
            found = set()
            for line in schedule or []:
                dm = re.match(r'[【\[]?\s*(\d+)\s*日目', str(line).strip())
                if dm:
                    found.add(int(dm.group(1)))
            return found
        missing = set(range(1, total_days + 1)) - _days_in(response.schedule)
        if missing:
            log.warning("⏱️ スケジュールの日数不足を検出（%s日目が欠落）。作り直します",
                        "・".join(str(d) for d in sorted(missing)))
            retry_prompt = prompt + P.missing_days_note(missing, num_nights, total_days)
            response = invoke_with_retry(structured_llm, retry_prompt)

    _pp(response.schedule, "📅 作成したスケジュール:")
    return {"schedule": response.schedule}


def cost_manager(state: TravelPlanState):
    """確定したプラン内容から、日別＋合計の費用見積もりを作成する。"""
    log.info("[💰 料金マネージャー]: 旅行の費用を試算中... destination=%s", state["destination"])
    prompt = P.cost_prompt(state)
    structured_llm = llm_strong.with_structured_output(CostOutput)  # 数値計算は上位モデル
    response = invoke_with_retry(structured_llm, prompt)
    _pp(response.budget_estimate, "💰 費用見積もり:")
    log.info("💰 1人あたり合計: %s円（予算上限 %s円）", f"{response.total_per_person:,}", f"{state['budget_limit']:,}")
    return {"budget_estimate": response.budget_estimate, "total_per_person": response.total_per_person}


def balancer(state: TravelPlanState):
    """プラン全体を複数観点で審査し、承認(approved)か差し戻し(fix_*)を判定する。

    判定結果(status)・理由(feedback)を返し、retry_count を加算する。
    """
    _edit_targets = state.get("edit_targets") or []
    _is_edit = bool(_edit_targets) and "all" not in _edit_targets
    # 予算に影響しない部分編集（観光地の入れ替え等）は審査不要でご要望を採用する。
    # 予算に影響する編集（宿・グルメ・交通・費用）は、差し戻しはせず予算/実現性だけ確認し、
    # 懸念があれば警告として伝える（指定外の部分まで作り直されるのを防ぐ）。
    _budget_areas = {"accommodation", "gourmet", "budget", "transport"}
    if _is_edit and not (set(_edit_targets) & _budget_areas):
        log.info("[⚖️ バランサー]: 予算に影響しない部分編集のため審査をスキップ")
        return {"status": "approved", "feedback": "ご要望を反映して調整しました🍀"}
    if _is_edit:
        log.info("[⚖️ バランサー]: 部分編集の予算・実現性を確認中...")
    else:
        log.info("[⚖️ バランサー]: プランを審査中... destination=%s", state["destination"])
    prompt = P.review_prompt(state, is_day_trip(state["duration"]))
    structured_llm = llm_strong.with_structured_output(BalancerOutput)  # 多観点審査は上位モデル
    response = invoke_with_retry(structured_llm, prompt)
    status = response.status
    feedback = response.feedback

    # 数値による予算ガード：費用合計(total_per_person)が予算上限の110%を超えるなら、
    # LLMの判定に関わらず承認させない。差し戻しても収まらない（リトライ上限）なら
    # 「予算不足」として明示し、超過プランを黙って提示しないようにする。
    _total = state.get("total_per_person") or 0
    _budget = state.get("budget_limit") or 0
    if not _is_edit and _total and _budget and _total > _budget * 1.10:
        _new_retry = state.get("retry_count", 0) + 1
        if _new_retry >= MAX_BALANCER_RETRIES:
            status = "budget_infeasible"
            feedback = (
                f"費用の1人あたり合計が約{_total:,}円で、予算上限（{_budget:,}円）を超えています。"
                "予算を上げるか、日程を短くする・宿のグレードを下げるなどをご検討ください。"
            )
        elif status not in ("budget_infeasible",):
            status = "fix_budget"
            feedback = (
                f"1人あたり合計が約{_total:,}円で予算（{_budget:,}円）を超過しています。"
                "宿泊・食事をより手頃な選択に見直して予算内に収めてください。"
            ) + (f"\n（審査メモ: {response.feedback}）" if response.feedback else "")
        log.info("⚖️ 予算ガード適用: total=%s budget=%s -> %s", _total, _budget, status)

    log.info("👉 審査結果: [%s]", status.upper())
    log.info("💬 フィードバック: %s", feedback)

    # 部分編集（予算影響あり）は、問題があれば【1回だけ】差し戻して直す機会を与える。
    # それでも収まらなければ、ご要望を反映したうえで懸念を警告として伝えて確定する。
    if _is_edit:
        _new_retry = state.get("retry_count", 0) + 1
        _over_budget = bool(_total and _budget and _total > _budget * 1.10)
        _has_problem = (response.status != "approved") or _over_budget
        _fix_set = {"fix_sightseeing", "fix_gourmet", "fix_accommodation", "fix_budget", "fix_time"}
        if _has_problem and _new_retry < 2:  # 差し戻しは最大1回
            fix_status = response.status if response.status in _fix_set else "fix_budget"
            if _over_budget:
                fix_status = "fix_budget"
            log.info("⚖️ 部分編集を1回だけ差し戻し: %s", fix_status)
            return {
                "status": fix_status,
                "prev_status": state.get("status", ""),
                "feedback": response.feedback,
                "retry_count": _new_retry,
            }
        if response.status == "approved" and not _over_budget:
            feedback = response.feedback
        else:
            feedback = (
                "⚠️ ご要望は反映しましたが、" + response.feedback
                + "（必要なら『もっと安い宿に』『予算をもう少し上げる』などで再調整できます）"
            )
        return {
            "status": "approved",
            "prev_status": state.get("status", ""),
            "feedback": feedback,
            "retry_count": _new_retry,
        }

    return {
        "status": status,
        "prev_status": state.get("status", ""),
        "feedback": feedback,
        "retry_count": state.get("retry_count", 0) + 1,
    }


# 同じ指摘が2回続いたときに戻る先。選び直しでは直らないので、候補集めからやり直す。
# fix_budget は宿が予算の主因なので宿の候補から、fix_time は行程が入りきらない
# ＝観光の顔ぶれが重いということなので観光の候補から集め直す。
# 指摘が毎回違っていても、この回数目の差し戻しからは候補集めまで戻す。
# 上限（MAX_BALANCER_RETRIES=5）に達する前に必ず2回は入れ替えが走る。
_REFRESH_FROM_RETRY = 3

_REFRESH_POOL = {
    "fix_sightseeing":   "sightseeing_candidates",
    "fix_gourmet":       "gourmet_candidates",
    "fix_accommodation": "accommodation_candidates",
    "fix_budget":        "accommodation_candidates",
    "fix_time":          "sightseeing_candidates",
}


def route_after_balancer(state: TravelPlanState):
    """バランサーの審査結果に応じて、次に実行するノード名を返す分岐関数。

    承認・予算不可・リトライ上限なら終了('end')。差し戻し種別ごとに
    やり直すノードへ振り分け、同じ問題の繰り返し時はスポット選定まで戻す。
    """
    status = state["status"]
    prev_status = state.get("prev_status", "")

    terminal_statuses = {"approved", "budget_infeasible"}
    fix_statuses = {
        "fix_sightseeing",
        "fix_gourmet",
        "fix_accommodation",
        "fix_budget",
        "fix_time",
    }

    if status in terminal_statuses:
        return "end"
    if state["retry_count"] >= MAX_BALANCER_RETRIES:
        log.warning("⚠️ 差し戻し上限（5回）に達したため強制終了します。最終ステータス: %s", status)
        return "end"
    # 候補プールの中に正解が無いときは、選び直し（安い）では永久に抜けられない。
    # 候補集め（検索＋LLM。高い）まで戻して顔ぶれを入れ替える。使うのは2通り:
    #   ・同じ指摘が2回続いた   … その領域のプールが原因だとはっきりしている
    #   ・差し戻しが3回目に入った … 指摘が毎回違っても、安い手では収束していない
    # 後者が要るのは、観光→グルメ→観光…と交互に指摘が来ると前者が一度も成立せず、
    # 上限5回を使い切るまで同じ観光候補から選び直し続けてしまうため（実際そうなる）。
    _repeated = status == prev_status
    if status in fix_statuses and (_repeated or state["retry_count"] >= _REFRESH_FROM_RETRY):
        pool = _REFRESH_POOL[status]
        log.warning("⚠️ %s（%s）のため、%s から候補を集め直します。",
                    "同じ問題の繰り返し" if _repeated else "差し戻しが続いている", status, pool)
        return pool

    return {
        "fix_sightseeing": "sightseeing",
        # グルメだけの問題は宿を選び直さず、飲食店の再抽出からやり直す（宿の再発防止）
        "fix_gourmet": "gourmet_candidates",
        "fix_accommodation": "accommodation",
        "fix_budget": "accommodation",
        "fix_time": "timekeeper",
    }.get(status, "end")
