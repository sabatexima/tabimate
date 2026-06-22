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
"""

import re
from datetime import date
from chat.models import TravelPlanState
from chat.llm import llm, llm_strong, invoke_with_retry, build_search_context
from chat.logger import get_logger
from chat.models import (
    TransportOutput, SightseeingOutput, GourmetOutput,
    TimekeeperOutput, AccommodationOutput, CostOutput, BalancerOutput,
    SightseeingCandidatesOutput, GourmetCandidatesOutput, AccommodationCandidatesOutput,
)

log = get_logger("agents")

ACCOMMODATION_BUDGET_RATIO = 0.40  # 残予算に占める宿泊費の上限割合
FOOD_BUDGET_RATIO          = 0.25  # 残予算に占める食費の上限割合
MAX_BALANCER_RETRIES       = 5     # バランサー差し戻し上限回数


def is_day_trip(duration: str) -> bool:
    """期間文字列が日帰り（宿泊なし）かどうかを判定する。"""
    return "日帰り" in duration or bool(re.match(r'0泊', duration.strip()))


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


def _directive(state=None) -> str:
    """全エージェント共通の指示（出力言語・本日の日付・実在性）。各プロンプト末尾に付与する。"""
    return (
        "\n【共通の指示】\n"
        f"・本日の日付は {date.today().isoformat()}。営業状況・季節・開催時期の判断に使うこと。\n"
        "・すべて日本語で出力すること。\n"
        "・実在し、現在も営業している施設・スポット・店舗のみを扱うこと。"
        "閉業・移転・長期休業・期間限定の終了が疑われる場合は避け、確証が持てなければ別の確実な候補にすること。\n"
    )


def transport_agent(state: TravelPlanState):
    """往復交通費を概算し、予算上限から差し引いた残予算を返す。

    交通費が予算上限を超える場合は ValueError を送出して以降の処理を止める。
    """
    if _skip(state, "transport"):
        return {}  # 部分編集: 交通は対象外。前回の交通費・残予算を引き継ぐ
    transport_mode = state.get("transport_mode", "おまかせ")
    no_car = state.get("no_car", False)
    # 運転免許なしの場合は車・レンタカーを使わない（誤って車指定でも公共交通に切替）
    if no_car and transport_mode in ("車", "レンタカー", "自家用車", "マイカー"):
        transport_mode = "おまかせ"
    log.info(
        "[🚄 交通エージェント]: 往復交通費を試算中... destination=%s, mode=%s, no_car=%s",
        state["destination"], transport_mode, no_car,
    )

    if transport_mode and transport_mode != "おまかせ":
        mode_instruction = f"""・利用する交通手段は「{transport_mode}」で固定すること（他の手段に置き換えないこと）
・「{transport_mode}」での出発地→目的地→出発地の往復に必要な費用を見積もること
・車・レンタカーの場合: 往復のガソリン代＋高速道路料金（＋必要なら駐車場代）を「1台あたり」で算出し、1台あたり最大5人乗車として {state['num_people']}人を割り当て、最終的に1人あたりの金額に割り戻すこと
・高速バス・夜行バスの場合: 往復の運賃を1人あたりで見積もること
・飛行機の場合: 往復の航空券代＋必要なら空港アクセス費を1人あたりで見積もること
・新幹線・特急など鉄道の場合: 往復の運賃＋特急/指定席料金を1人あたりで見積もること"""
    elif no_car:
        mode_instruction = """・運転免許がない/運転しない前提。車・レンタカーは選ばないこと。
・新幹線・特急・飛行機・高速バス・在来線など公共交通機関のみで、所要時間と費用のバランスが最も良い手段を選ぶこと"""
    else:
        mode_instruction = """・新幹線・特急・飛行機・高速バス・車など、所要時間と費用のバランスが最も良い交通手段を選ぶこと
・宿泊・食事・観光に十分な残予算を確保できるよう、過度に高額でない費用対効果の高い手段を優先すること（交通費で予算の大半を使い切らない）"""

    prompt = f"""あなたは交通費の専門家です。以下の条件で往復交通費（1人あたり）を概算してください。

出発地: {state['departure_location']}
目的地: {state['destination']}
参加人数: {state['num_people']}人
旅行日程: {state['travel_date']}
交通手段の希望: {transport_mode}

【選定の基準】
{mode_instruction}
・旅行日程に応じた繁忙期・閑散期の料金水準を反映すること（GW・お盆・年末年始は正規料金の1.2〜1.5倍を目安に割増）
・{state['num_people']}人グループの場合、団体割引・グループ割引が適用されるか確認し、適用される場合は割引後の金額を使うこと
・早割（EX早特・スーパー早特など）が使える可能性がある場合でも、繁忙期は満席リスクが高いため正規料金ベースで見積もること
・1人あたりの往復合計金額（円）のみを返すこと
"""
    structured_llm = llm.with_structured_output(TransportOutput)
    response = invoke_with_retry(structured_llm, prompt)
    remaining = state["budget_limit"] - response.transport_cost
    if remaining <= 0:
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

    prompt = f"""あなたは旅行のプロです。以下の条件に合う観光スポットの候補を抽出してください。

行き先: {state['destination']}
旅行日程: {state['travel_date']}
期間: {state['duration']}
参加人数: {state['num_people']}人
テーマ: {', '.join(state['themes'])}
特別条件: {', '.join(state['special_requirements']) if state['special_requirements'] else 'なし'}

【選定の基準】
・旅行テーマを最もよく体現できるスポットを優先すること
・各スポットの通常営業時間・定休日を考慮すること
・特別条件がある場合（車椅子利用・アレルギー等）は、施設のバリアフリー対応状況を確認すること
・{state['num_people']}人の大人数でも対応できる収容人数・予約の可否を確認すること
{search_context}

【出力】
厳密に5個以上8個以下の候補を名称のみで返してください。
"""
    if state.get("user_feedback"):
        prompt += f"\n【ユーザーからのご要望（最優先）】:\n{state['user_feedback']}\n上記の要望を必ず最優先で反映して候補を選ぶこと。"
    if state.get("no_car"):
        prompt += "\n【重要】運転免許がない/運転しない前提です。公共交通機関（電車・バス）＋徒歩で無理なく行けるスポットだけを選び、車でしか行けない場所は除外すること。"
    prompt += _directive(state)
    structured_llm = llm.with_structured_output(SightseeingCandidatesOutput)
    response = invoke_with_retry(structured_llm, prompt)
    _pp(response.candidates, "✨ 候補スポット:")
    return {"spot_candidates": response.candidates}


def sightseeing_expert(state: TravelPlanState):
    """候補スポットから動線・条件を考慮して最終的なスポット（2〜3件）を選定する。"""
    if _skip(state, "sightseeing"):
        return {}  # 部分編集: 観光は対象外。前回のスポットを引き継ぐ
    log.info("[🗺️ 観光エキスパート]: スポットを選定中... destination=%s", state["destination"])
    candidates = state.get("spot_candidates", [])
    prompt = f"""あなたは旅行のプロです。以下の候補から最適な観光スポットを選定してください。

行き先: {state['destination']}
旅行日程: {state['travel_date']}
期間: {state['duration']}
参加人数: {state['num_people']}人
テーマ: {', '.join(state['themes'])}
特別条件: {', '.join(state['special_requirements']) if state['special_requirements'] else 'なし'}

【候補一覧】
{chr(10).join(f'- {c}' for c in candidates)}

【選定の基準】
・旅行テーマを最もよく体現できるスポットを優先すること
・各スポットの通常営業時間・定休日・{state['travel_date']}時点の季節限定イベントや混雑状況を考慮すること
・スポット間の移動距離・移動手段（徒歩/バス/電車）と所要時間を意識し、無理のない動線になるよう選ぶこと
・特別条件がある場合（車椅子利用・アレルギー等）は、施設のバリアフリー対応状況を具体的に確認したうえで条件を満たすスポットのみ選ぶこと
・{state['num_people']}人の大人数でも対応できる収容人数・予約の可否・広さを確認すること
"""
    if state.get("user_feedback"):
        prompt += f"\n【ユーザーからのご要望（最優先）】:\n{state['user_feedback']}\n上記の要望を必ず最優先で反映してスポットを選ぶこと。"
    if state.get("no_car"):
        prompt += "\n【重要】運転免許がない/運転しない前提です。公共交通機関（電車・バス）＋徒歩で無理なく行けるスポットだけを選び、車でしか行けない場所は除外すること。"
    prompt += _directive(state)
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
    num_nights = int(m.group(1)) if (m := re.search(r'(\d+)泊', state["duration"])) else 1
    # 1泊あたりの予算目安（残予算の40%を泊数で割る）。この価格帯で泊まれる候補を集める。
    per_night_budget = int(state.get("remaining_budget", 0) * ACCOMMODATION_BUDGET_RATIO) // max(num_nights, 1)
    queries = [
        f"{state['destination']} ホテル 旅館 おすすめ {state['themes'][0]} 公式",
        f"{state['destination']} 宿泊 1泊 {per_night_budget}円以内 おすすめ",
        f"{state['destination']} 格安 ビジネスホテル ゲストハウス",
    ]
    if any("車椅子" in r for r in state["special_requirements"]):
        queries.append(f"{state['destination']} バリアフリー ホテル 車椅子対応 ユニバーサルルーム")
    search_context = build_search_context(queries)
    spots = state.get("spots", [])
    restaurants = state.get("restaurants", [])

    prompt = f"""あなたは宿泊施設の専門家です。以下の条件に合う宿泊施設の候補を抽出してください。

行き先: {state['destination']}
旅行日程: {state['travel_date']}
期間: {state['duration']}（{num_nights}泊）
テーマ: {', '.join(state['themes'])}
参加人数: {state['num_people']}人
1泊1人あたりの予算目安: {per_night_budget:,}円（この価格帯で泊まれる施設を中心に）
特別条件: {', '.join(state['special_requirements']) if state['special_requirements'] else 'なし'}
観光スポット: {', '.join(spots)}
飲食店: {', '.join(restaurants)}
{search_context}

【選定の基準】
・1泊1人あたり目安（{per_night_budget:,}円）前後で泊まれる施設を中心に選ぶこと。高級旅館だけに偏らず、ビジネスホテル・ゲストハウス・素泊まり可など手頃な選択肢も必ず含めること。
・最低でも候補の半数は目安価格以内に収まる施設にすること。

【出力】
厳密に3個以上5個以下の施設名のみを返してください。
"""
    prompt += _directive(state)
    structured_llm = llm.with_structured_output(AccommodationCandidatesOutput)
    response = invoke_with_retry(structured_llm, prompt)
    _pp(response.accommodation, "🏨 候補宿泊施設:")
    return {"accommodation_candidates": response.accommodation}


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
    num_nights = int(m.group(1)) if (m := re.search(r'(\d+)泊', state["duration"])) else 1
    total_accommodation_budget = int(state["remaining_budget"] * ACCOMMODATION_BUDGET_RATIO)
    per_night_budget = total_accommodation_budget // num_nights
    candidates = state.get("accommodation_candidates", [])
    prompt = f"""あなたは宿泊施設の選定専門家です。以下の条件に合う最適な宿泊施設を1〜2箇所選んでください。

行き先: {state['destination']}
旅行日程: {state['travel_date']}
期間: {state['duration']}（{num_nights}泊）
テーマ: {', '.join(state['themes'])}
参加人数: {state['num_people']}人
宿泊・食事・観光の予算: {state['remaining_budget']:,}円/人（宿泊費・食費・観光費・現地交通費の合計）
宿泊費の目安上限（合計）: {total_accommodation_budget:,}円/人（{num_nights}泊分の合計）
宿泊費の目安上限（1泊あたり）: {per_night_budget:,}円/人
特別条件: {', '.join(state['special_requirements']) if state['special_requirements'] else 'なし'}
観光スポット: {', '.join(state.get('spots', []))}
飲食店: {', '.join(state.get('restaurants', []))}

【候補一覧】
{chr(10).join(f'- {c}' for c in candidates)}

【選定の条件】
・旅行テーマ（{', '.join(state['themes'])}）に合った雰囲気・コンセプトの施設を選ぶこと（旅館・ホテル・町家など）
・メインの観光スポットまでのアクセス（徒歩/交通機関・所要時間）を明記すること
・繁忙期（{state['travel_date']}）のため、大人数グループでも予約が取りやすい施設を優先すること
・{state['num_people']}人全員が同一施設に宿泊できる部屋数・プランがあることを確認すること
・1泊1人あたりの料金が目安上限（{per_night_budget:,}円）以内に収まる施設を【必ず】選ぶこと。目安を超える高級宿は予算に余裕がある場合のみ。予算内の候補が無ければ、候補の中で最も安い施設を選ぶこと。
・宿泊費の合計（{num_nights}泊）が宿泊予算の上限（{total_accommodation_budget:,}円/人）を絶対に超えないこと。食事・観光の費用も残ることを念頭に、宿で残予算を使い切らないこと。
・チェックイン時刻（最早）とチェックアウト時刻（最遅）を明記すること
・朝食プランの有無と料金を明記すること（テーマに合う朝食が提供される場合は積極的に推奨すること）
・特別条件がある場合（バリアフリー等）は、具体的な対応設備（スロープ・エレベーター・手すり等）を確認済みの施設のみ選ぶこと
"""
    if state.get("feedback") and state.get("status") in ("fix_accommodation", "fix_budget", "fix_gourmet", "fix_sightseeing"):
        prompt += f"\n【バランサーからの修正要求】:\n{state['feedback']}\nこの指摘を反映して、施設を選び直してください。"
    if state.get("user_feedback"):
        prompt += f"\n【ユーザーからのご要望（最優先）】:\n{state['user_feedback']}\n上記の要望を必ず最優先で反映して宿泊施設を選んでください。"
    prompt += _directive(state)

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
    queries = [
        f"{state['destination']} {' '.join(spots)} 周辺 レストラン おすすめ",
        f"{state['destination']} 郷土料理 地元名物 人気店",
    ]
    if any("アレルギー" in r for r in state["special_requirements"]):
        queries.append(f"{state['destination']} 魚介類アレルギー対応 レストラン")
    if any("車椅子" in r for r in state["special_requirements"]):
        queries.append(f"{state['destination']} バリアフリー レストラン 車椅子対応")
    search_context = build_search_context(queries)

    prompt = f"""あなたはグルメガイドです。以下の条件に合う飲食店の候補を抽出してください。

行き先: {state['destination']}
旅行日程: {state['travel_date']}
期間: {state['duration']}
選定されたスポット: {', '.join(spots)}
旅行のテーマ: {', '.join(state['themes'])}
参加人数: {state['num_people']}人
特別条件: {', '.join(state['special_requirements']) if state['special_requirements'] else 'なし'}
{search_context}

【出力】
厳密に4個以上6個以下の飲食店名のみを返してください。
"""
    prompt += _directive(state)
    structured_llm = llm.with_structured_output(GourmetCandidatesOutput)
    response = invoke_with_retry(structured_llm, prompt)
    _pp(response.restaurants, "🍱 候補飲食店:")
    return {"restaurant_candidates": response.restaurants}


def gourmet_hunter(state: TravelPlanState):
    """候補から食事回数分の飲食店を選定する（食費目安は残予算の25%）。"""
    if _skip(state, "gourmet"):
        return {}  # 部分編集: グルメは対象外。前回の飲食店を引き継ぐ
    log.info("[🍣 グルメハンター]: 飲食店を選定中... destination=%s", state["destination"])
    spots = state.get("spots", [])
    accommodation = state.get("accommodation", [])
    candidates = state.get("restaurant_candidates", [])
    num_nights = int(m.group(1)) if (m := re.search(r'(\d+)泊', state["duration"])) else 1

    prompt = f"""あなたはグルメガイドです。以下の候補から必要な飲食店を選定してください。

行き先: {state['destination']}
旅行日程: {state['travel_date']}
期間: {state['duration']}
選定されたスポット: {', '.join(spots)}
旅行のテーマ: {', '.join(state['themes'])}
参加人数: {state['num_people']}人
宿泊・食事・観光の予算: {state['remaining_budget']:,}円/人
食費の目安上限: {int(state['remaining_budget'] * FOOD_BUDGET_RATIO):,}円/人
選定済みの宿泊施設: {', '.join(accommodation)}
特別条件: {', '.join(state['special_requirements']) if state['special_requirements'] else 'なし'}

【候補一覧】
{chr(10).join(f'- {c}' for c in candidates)}

【選定の基準】
・期間中に必要な食事の回数分をカバーすること（{state['duration']} = {"昼食×1" if is_day_trip(state["duration"]) else f"昼食×{num_nights + 1} + 夕食×{num_nights}"}）
・各日程のスポット周辺にある店を選び、日別に「〇日目 昼食」「〇日目 夕食」と明記すること
・{state['destination']}ならではの地元名物・郷土料理が味わえる店を優先すること
・食事の合計が食費の目安上限（{int(state['remaining_budget'] * FOOD_BUDGET_RATIO):,}円/人）以内に収まる価格帯の店を選び、最初から予算内に収めること（後の差し戻しを避ける）
・アレルギー・食事制限がある場合は、その食材を使わないメニューが実際にあるか確認した店のみ選ぶこと
・{state['num_people']}人が同一テーブルで着席できる席数・個室・貸切の可否を確認すること
"""
    if state.get("feedback") and state.get("status") in ("fix_gourmet", "fix_budget", "fix_accommodation", "fix_sightseeing", "fix_time"):
        prompt += f"\n【バランサーからの修正要求】:\n{state['feedback']}\nこの指摘を反映して、飲食店を選び直してください。"
    if state.get("user_feedback"):
        prompt += f"\n【ユーザーからのご要望（最優先）】:\n{state['user_feedback']}\n上記の要望を必ず最優先で反映して飲食店を選んでください。"
    prompt += _directive(state)

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
    spots = state.get("spots", [])
    restaurants = state.get("restaurants", [])
    accommodation = state.get("accommodation", [])

    must_include_block = ""
    if state.get("feedback") and state.get("status") == "fix_time":
        # バランサーが明示した「missing」候補を強制投入
        missing_spots = [s for s in spots if s in state.get("feedback", "")]
        missing_restaurants = [s for s in restaurants if s in state.get("feedback", "")]
        if missing_spots or missing_restaurants:
            must_include_block = "【絶対に含めるべき項目（前回の指摘により）】\n"
            if missing_spots:
                must_include_block += "・観光スポット（すべて必須）: " + "、".join(missing_spots) + "\n"
            if missing_restaurants:
                must_include_block += "・飲食店（すべて必須）: " + "、".join(missing_restaurants) + "\n"

    day_trip = is_day_trip(state["duration"])

    if day_trip:
        prompt = f"""あなたは綿密なツアーコンダクターです。
以下の【絶対に守るべき条件】と【絶対に含めるべき項目】を満たした日帰りタイムスケジュールを作成してください。

【絶対に守るべき条件】
・旅行の時間枠: {state['duration']}  ← 必ずこの時間枠の中に全ての予定を収めること
・出発地: {state['departure_location']}（往路・復路の移動時間を具体的にスケジュールに組み込むこと）
・往復の交通手段: {state.get('transport_mode', 'おまかせ')}（この手段に合わせて往復の移動時間・経路を組むこと。車なら運転・休憩・駐車、高速バスなら乗車時間、鉄道/飛行機なら駅・空港での移動を考慮）
・参加人数: {state['num_people']}人（大人数は移動・入場・食事に時間がかかるため各行動に余裕を持たせること）
・各スポットの営業時間（開館・閉館）を確認し、「到着時刻 + 滞在時間 <= 閉館時刻」を必ず守ること
・スポット間の移動は交通手段と所要時間を明記し、{state['destination']}の混雑を考慮して余裕を持たせること
・食事（昼食）の時間帯を明確に確保し、飲食店の営業時間内に訪問できるようにすること
・特別条件（車椅子等）がある場合、移動に追加時間がかかることを考慮すること
・帰路の出発時間に余裕を持たせること

【絶対に含めるべき項目】（以下のリストのすべてをスケジュールに組み込むこと）
・観光スポット（すべて必須）: {', '.join(spots) if spots else '（なし）'}
・飲食店（すべて必須）: {', '.join(restaurants) if restaurants else '（なし）'}
・旅行テーマ: {', '.join(state['themes'])}
{must_include_block}
【出力形式】
・各行動を「HH:MM 行動内容（所要時間・移動手段・距離）」の形式で時系列に記載すること
・総移動時間と観光時間のバランスが適切かを自己チェックし、詰め込みすぎの場合は削減すること
"""
    else:
        prompt = f"""あなたは綿密なツアーコンダクターです。
以下の【絶対に守るべき条件】と【絶対に含めるべき項目】を満たした日別タイムスケジュールを作成してください。

【絶対に守るべき条件】
・旅行の時間枠: {state['duration']}  ← 必ずこの時間枠の中に全ての予定を収めること
・出発地: {state['departure_location']}（往路・復路の移動時間を具体的にスケジュールに組み込むこと）
・往復の交通手段: {state.get('transport_mode', 'おまかせ')}（この手段に合わせて往復の移動時間・経路を組むこと。車なら運転・休憩・駐車、高速バスなら乗車時間、鉄道/飛行機なら駅・空港での移動を考慮）
・参加人数: {state['num_people']}人（大人数は移動・入場・食事に時間がかかるため各行動に余裕を持たせること）
・各スポットの営業時間（開館・閉館）を確認し、開館前の到着や閉館時刻を超えた滞在にならないよう、「到着時刻 + 滞在時間 <= 閉館時刻」を必ず守ること
・スポット間の移動は交通手段と所要時間を明記し、{state['destination']}の混雑を考慮して余裕を持たせること
・宿泊施設のチェックイン（目安15:00〜）・チェックアウト（目安11:00〜）を必ずスケジュールに組み込むこと
・食事（昼食・夕食）の時間帯を明確に確保し、飲食店の営業時間内に訪問できるようにすること
・特別条件（車椅子等）がある場合、移動に追加時間がかかることを考慮すること
・チェックアウト後は宿泊施設に戻る行程を入れないこと。最終日は最後の観光地から直接、または帰路の駅周辺で昼食をとってから出発すること
・夕食はできるだけ宿泊施設内または徒歩圏内の飲食店を選び、タクシーで往復するだけの外出は避けること

【絶対に含めるべき項目】（以下のリストのすべてをスケジュールに組み込むこと）
・観光スポット（すべて必須）: {', '.join(spots) if spots else '（なし）'}
・飲食店（すべて必須）: {', '.join(restaurants) if restaurants else '（なし）'}
・宿泊施設: {', '.join(accommodation) if accommodation else '（なし）'}
・旅行テーマ: {', '.join(state['themes'])}
{must_include_block}
【出力形式】
・「1日目」「2日目」などの日別ブロックに分けて記載すること
・各行動を「HH:MM 行動内容（所要時間・移動手段・距離）」の形式で時系列に記載すること
・1日の総移動時間と観光時間のバランスが適切かを自己チェックし、詰め込みすぎの場合は削減すること
"""
    if state.get("feedback") and state.get("status") == "fix_time":
        prompt += f"\n【重要：バランサーからの前回の修正要求】:\n{state['feedback']}\n上記の指摘（特に開始時刻や移動時間）を完全にクリアし、【絶対に含めるべき項目】をすべて反映したスケジュールに修正してください。"
    if state.get("user_feedback"):
        prompt += f"\n\n【ユーザーからのご要望（最優先）】:\n{state['user_feedback']}\n上記の要望を必ず最優先で反映してスケジュールを組んでください。"

    # 「散策」「自由時間」などの曖昧な予定で埋めない（具体的な行動で構成する）
    prompt += (
        "\n\n【予定の質（重要）】\n"
        "・「散策」「自由時間」「周辺をぶらぶら」などの曖昧な時間で埋めないこと。各時間帯は具体的な"
        "スポット名・体験・食事で構成すること。\n"
        "・どうしても空き時間ができる場合のみ30分以内に留め、その時間も近くの具体的な店・スポットを示すこと。\n"
        "・1日に詰め込みすぎず、移動と滞在のバランスを優先すること（無理に予定を増やして散策で埋めない）。"
    )
    if state.get("no_car"):
        prompt += (
            "\n\n【移動手段（重要）】運転免許がない/運転しない前提です。すべての移動を公共交通機関（電車・バス）"
            "＋徒歩で組み、各移動に路線・所要時間を明記すること。レンタカー・自家用車の運転を前提にしないこと。"
        )

    prompt += _directive(state)
    structured_llm = llm.with_structured_output(TimekeeperOutput)
    response = invoke_with_retry(structured_llm, prompt)
    _pp(response.schedule, "📅 作成したスケジュール:")
    return {"schedule": response.schedule}


def _build_day_sections(duration: str) -> str:
    """費用見積もりプロンプト用に、日別の費用項目テンプレートを生成する。"""
    if is_day_trip(duration):
        return (
            "■ 当日の費用\n"
            "・現地交通費（バス・電車・タクシー等）\n"
            "・各観光スポットの入場料（無料の場合も「無料」と明記）\n"
            "・昼食の食費（各飲食店ごとに1人あたりの金額を記載）"
        )
    m = re.search(r'(\d+)泊(\d+)日', duration)
    num_nights = int(m.group(1)) if m else 1
    num_days   = int(m.group(2)) if m else 2

    sections = []
    for day in range(1, num_days + 1):
        if day == 1:
            sections.append(
                f"■ 1日目の費用\n"
                f"・現地到着後の交通費（バス・電車・タクシー等）\n"
                f"・各観光スポットの入場料（無料の場合も「無料」と明記）\n"
                f"・昼食・夕食の食費（各飲食店ごとに1人あたりの金額を記載）\n"
                f"・宿泊費（1泊1人あたり、朝食込/素泊まりを区別）"
            )
        elif day == num_days:
            sections.append(
                f"■ {day}日目（最終日）の費用\n"
                f"・朝食費（宿泊プランに含まれない場合）\n"
                f"・観光スポットの入場料\n"
                f"・昼食の食費\n"
                f"・帰路の現地交通費"
            )
        else:
            sections.append(
                f"■ {day}日目の費用\n"
                f"・朝食費（宿泊プランに含まれない場合）\n"
                f"・観光スポットの入場料\n"
                f"・昼食・夕食の食費\n"
                f"・宿泊費（1泊1人あたり、朝食込/素泊まりを区別）"
            )
    return "\n\n".join(sections)


def cost_manager(state: TravelPlanState):
    """確定したプラン内容から、日別＋合計の費用見積もりを作成する。"""
    log.info("[💰 料金マネージャー]: 旅行の費用を試算中... destination=%s", state["destination"])
    spots = state.get("spots", [])
    restaurants = state.get("restaurants", [])
    accommodation = state.get("accommodation", [])
    schedule_lines = chr(10).join(state['schedule']) if state.get('schedule') else '（なし）'

    prompt = f"""あなたは旅行費用の専門家です。以下のプランに基づき、旅行にかかる費用を項目ごとに詳細に見積もってください。

行き先: {state['destination']}
旅行日程: {state['travel_date']}
期間: {state['duration']}
出発地: {state['departure_location']}
参加人数: {state['num_people']}人
1人あたり予算上限: {state['budget_limit']:,}円
往復交通費（確定）: {state['transport_cost']:,}円/人
宿泊・食事・観光の予算: {state['remaining_budget']:,}円/人
観光スポット（すべて必須）: {', '.join(spots) if spots else '（なし）'}
飲食店（すべて必須）: {', '.join(restaurants) if restaurants else '（なし）'}
宿泊施設（すべて必須）: {', '.join(accommodation) if accommodation else '（なし）'}
スケジュール:
{schedule_lines}

【見積もりの指示】
以下の項目を日別に分けて、具体的な金額（円）で箇条書きにしてください。上記の観光スポット・飲食店・宿泊施設は【すべて】費用見積もりに含めてください。

■ 往復交通費: {state['transport_cost']:,}円/人（確定済み）

{_build_day_sections(state['duration'])}

■ 合計
・1人あたり小計（交通費除く）: X,XXX円
・往復交通費: {state['transport_cost']:,}円/人
・1人あたり合計: X,XXX円
・{state['num_people']}人グループの総費用: X,XXX円
・予算上限（{state['budget_limit']:,}円）との差額: +X,XXX円の余裕 or -X,XXX円の超過
・予備費の推奨額（総費用の10%）: X,XXX円/人
"""
    if state.get("user_feedback"):
        prompt += f"\n【ユーザーからのご要望（最優先）】:\n{state['user_feedback']}\n上記の要望（予算配分など）を必ず最優先で反映して見積もること。"
    prompt += (
        "\n【整合の必須事項】1人あたり合計は往復交通費を含み、各費用項目の和と必ず一致させること。"
        "予算上限を超える場合は超過額を明記すること。total_per_person は同じ合計額（整数・円）にすること。"
    )
    prompt += _directive(state)
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
    prompt = f"""あなたは旅行代理店のシニアマネージャーです。以下のプランを審査してください。

■ 基本条件: {state['destination']}（{state['duration']}）
■ 旅行日程: {state['travel_date']}
■ 出発地: {state['departure_location']}
■ 参加人数: {state['num_people']}人
■ 予算上限: 1人あたり {state['budget_limit']:,}円（往復交通費 {state['transport_cost']:,}円確定、残り予算: {state['remaining_budget']:,}円）
■ テーマ: {', '.join(state['themes'])}
■ 特別条件: {', '.join(state['special_requirements']) if state['special_requirements'] else 'なし'}
■ 観光地: {', '.join(state['spots'])}
■ 飲食店: {', '.join(state['restaurants'])}
{f"■ 宿泊施設: {', '.join(state.get('accommodation', []))}" if not is_day_trip(state['duration']) else "■ 宿泊施設: なし（日帰り）"}
■ スケジュール:
{chr(10).join(state['schedule'])}
■ 費用見積もり:
{chr(10).join(state.get('budget_estimate', []))}

【審査の{"4" if is_day_trip(state["duration"]) else "5"}観点】
1. 予算: 費用見積もりの1人あたり合計が予算上限（{state['budget_limit']:,}円）の【110%以内】に収まっているか。予備費の範囲内とみなせる軽微な超過（110%以内）は合格とし、fix_budget にしないこと。明確に110%を超える場合のみ問題とし、超過金額を具体的に明記すること。
2. スケジュール: 移動時間が現実的か、開館前到着・閉館後出発などの矛盾がないか、1日の総移動時間が観光時間を上回っていないか。
3. 疲労度: {state['num_people']}人の大人数で、特別条件（{', '.join(state['special_requirements']) if state['special_requirements'] else 'なし'}）を持つ参加者が無理なく楽しめる強度か。
4. テーマ一貫性: 観光スポット・飲食店{"" if is_day_trip(state["duration"]) else "・宿泊施設"}がすべて旅行テーマ（{', '.join(state['themes'])}）に沿っているか。
{"" if is_day_trip(state["duration"]) else f"5. 特別条件の充足: 車椅子対応・アレルギー対応などの特別条件が、全スポット・飲食店・宿泊施設で実際に満たされているか。"}
{"【重要】これは日帰りプランです。fix_accommodation は絶対に使わないこと。" if is_day_trip(state["duration"]) else ""}

【判定ルール】
・上記の各観点すべてをパスした場合のみ 'approved' を返すこと
・差し戻し（fix_*）は「実際に支障がある明確な問題」がある時だけにすること。予算が110%以内、スケジュールに大きな破綻がない、テーマから大きく外れていない、なら細部にこだわらず approved にすること（軽微な好みの問題で差し戻さない）
・問題がある場合は最も優先度の高い1つのstatusを選び、feedbackに「どの観点で・何が・どの程度問題か」を数値を交えて具体的に記載すること
・差し戻しは最大5回まで

【budget_infeasible の判断基準】
費用見積もりの合計が予算上限を20%以上超過しており、かつどのスポット・飲食店・宿泊施設を選んでも構造的に予算内に収まらないと判断される場合のみ選択すること。
"""
    if state.get("retry_count", 0) == 0:
        prompt += "\n【重要】これは初回審査です。予算超過の場合でも budget_infeasible は選ばず、fix_* で差し戻してください。"
    prompt += _directive(state)
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


def route_after_balancer(state: TravelPlanState):
    """バランサーの審査結果に応じて、次に実行するノード名を返す分岐関数。

    承認・予算不可・リトライ上限なら終了('end')。差し戻し種別ごとに
    やり直すノードへ振り分け、同じ問題の繰り返し時はスポット選定まで戻す。
    """
    status = state["status"]
    prev_status = state.get("prev_status", "")

    terminal_statuses = {"approved", "budget_infeasible"}
    intermediate_statuses = {
        "candidates_ready",
        "accommodation_candidates_ready",
        "gourmet_candidates_ready",
    }
    fallback_statuses = {
        "fallback_sightseeing",
        "fallback_accommodation",
        "fallback_gourmet",
    }
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
    if status in intermediate_statuses:
        return status
    if status in fallback_statuses:
        return "timekeeper"
    if status == prev_status and status in fix_statuses:
        log.warning("⚠️ 同じ問題（%s）が繰り返されたため、観光スポット選定からやり直します。", status)
        return "sightseeing"

    return {
        "fix_sightseeing": "sightseeing",
        "fix_gourmet": "accommodation",
        "fix_accommodation": "accommodation",
        "fix_budget": "accommodation",
        "fix_time": "timekeeper",
    }.get(status, "end")
