"""プラン生成の各エージェントに渡すプロンプト（AIへの指示文）。

ここにあるのは「AIに何を頼むか」の文面だけ。どのモデルで呼ぶか、検索・
予算の計算・結果の検証・差し戻しの分岐といった処理は agents.py にある。
文面を調整したいときはこのファイルだけを見ればよい。

各 *_prompt() は state（TravelPlanState）と、agents.py が計算した値を受け取り、
文字列を返すだけの純粋な関数。AIも検索も呼ばない。
"""

import re
from datetime import date

from services.weather import parse_duration


# ----------------------------------------------------------------------
# 共通の部品（複数のプロンプトに足すもの）
# ----------------------------------------------------------------------
def refresh_hint(state, rejected: list, what: str) -> str:
    """候補を集め直すときにだけ添える、審査の指摘と「前回の顔ぶれ」。

    候補エージェントは temperature=0 なので、同じプロンプトなら同じ候補が返る。
    差し戻しで呼び直しても指摘を渡さなければ、検索とLLMを使ってまったく同じ
    顔ぶれを作り直すだけで、1円も1秒も無駄になる（実際そうなっていた）。
    指摘と、前回選ばれて弾かれた顔ぶれを渡して、別の候補が出るようにする。

    差し戻し以外（初回生成・部分編集）では空文字を返し、プロンプトを変えない。
    """
    if not state.get("feedback") or not str(state.get("status", "")).startswith("fix"):
        return ""
    hint = ("\n【前回の審査での指摘（必ず反映すること）】\n" + str(state["feedback"])
            + f"\n上の指摘を踏まえて、{what}の顔ぶれを見直すこと。")
    if rejected:
        hint += ("\n【前回選ばれて指摘を受けた顔ぶれ】: " + "、".join(rejected)
                 + "\n指摘に当てはまるものは候補から必ず外し、その分を新しい候補で補うこと。"
                 "指摘に関係のないものは残してよい。")
    return hint


def preference(state) -> str:
    """過去の★評価から得たユーザーの好みを、参考としてプロンプトに添える。"""
    p = state.get("user_preferences")
    if not p:
        return ""
    return (
        "\n【ユーザーの好み（過去の★評価より・参考）】\n" + p
        + "\n※あくまで参考。今回の明示の要望・条件を最優先しつつ、可能な範囲で好みに寄せ、低評価の傾向は避けること。\n"
    )


def weather(state) -> str:
    """旅行日の天気予報ヒントをプロンプトに添える（屋内/屋外の調整用・取得時のみ）。"""
    w = state.get("weather")
    return f"\n{w}\n" if w else ""


def directive(state=None) -> str:
    """全エージェント共通の指示（出力言語・本日の日付・実在性）。各プロンプト末尾に付与する。

    海外の行き先では、金額の円換算と「日本語名（現地語名）」の書き方も加える。
    現地語名は地図で探すときの手がかりになる（geocoding._variants が括弧の中を先に試す）。
    """
    text = (
        "\n【共通の指示】\n"
        f"・本日の日付は {date.today().isoformat()}。営業状況・季節・開催時期の判断に使うこと。\n"
        "・すべて日本語で出力すること。\n"
        "・実在し、現在も営業している施設・スポット・店舗のみを扱うこと。"
        "閉業・移転・長期休業・期間限定の終了が疑われる場合は避け、確証が持てなければ別の確実な候補にすること。\n"
    )
    if state and state.get("is_overseas"):
        cc = (state.get("dest_country") or "").upper()
        text += (
            f"・行き先は海外（国コード {cc}）。金額はすべて日本円に換算して書き、"
            "換算に使った概算レート（例: 1ユーロ≒165円）を1か所に明記すること。\n"
            "・施設・スポット・店・宿の名前は「日本語名（現地語または英語の正式名称）」の形で書くこと"
            "（例: エッフェル塔（Tour Eiffel））。地図で探すのに使うので現地語名を省かないこと。\n"
        )
    return text


def weekday_hint(travel_date: str) -> str:
    """旅行日が具体的な日付なら『（火曜日）』のような曜日ヒントを返す（定休日判断用）。"""
    m = re.search(r'(\d{4})\D+(\d{1,2})\D+(\d{1,2})', str(travel_date or ''))
    if not m:
        return ""
    try:
        d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return ""
    return f"（{['月', '火', '水', '木', '金', '土', '日'][d.weekday()]}曜日）"


def day_sections(duration: str) -> str:
    """費用見積もりプロンプト用に、日別の費用項目テンプレートを生成する。"""
    num_nights, num_days = parse_duration(duration)
    if num_days <= 1:
        return (
            "■ 当日の費用\n"
            "・現地交通費（バス・電車・タクシー等）\n"
            "・各観光スポットの入場料（無料の場合も「無料」と明記）\n"
            "・昼食の食費（各飲食店ごとに1人あたりの金額を記載）"
        )
    # 宿泊なしの複数日（0泊2日=夜行など）は宿泊費の行を出さない
    lodging_line = "\n・宿泊費（1泊1人あたり、朝食込/素泊まりを区別）" if num_nights > 0 else ""
    breakfast_line = "・朝食費（宿泊プランに含まれない場合）\n" if num_nights > 0 else "・朝食費\n"

    sections = []
    for day in range(1, num_days + 1):
        if day == 1:
            sections.append(
                f"■ 1日目の費用\n"
                f"・現地到着後の交通費（バス・電車・タクシー等）\n"
                f"・各観光スポットの入場料（無料の場合も「無料」と明記）\n"
                f"・昼食・夕食の食費（各飲食店ごとに1人あたりの金額を記載）"
                f"{lodging_line}"
            )
        elif day == num_days:
            sections.append(
                f"■ {day}日目（最終日）の費用\n"
                f"{breakfast_line}"
                f"・観光スポットの入場料\n"
                f"・昼食の食費\n"
                f"・帰路の現地交通費"
            )
        else:
            sections.append(
                f"■ {day}日目の費用\n"
                f"{breakfast_line}"
                f"・観光スポットの入場料\n"
                f"・昼食・夕食の食費"
                f"{lodging_line}"
            )
    return "\n\n".join(sections)


# ----------------------------------------------------------------------
# エージェントごとのプロンプト（グラフの順）
# ----------------------------------------------------------------------
def destination_prompt(state) -> str:
    """行き先が広すぎる（「日本」「関東」「どこでも」）かを判断させ、広ければ具体的なエリアを1つ決めさせる。"""
    themes = "、".join(state.get("themes") or []) or "指定なし"
    special = "、".join(state.get("special_requirements") or []) or "なし"
    prompt = f"""あなたは旅行プランナーです。お客さまの希望する行き先が、旅程を組むには広すぎるかを判断し、
広すぎる場合は、その範囲の中から具体的な行き先を1つ決めてください。

希望の行き先: {state.get('destination')}
出発地: {state.get('departure_location') or '不明'}
旅行日程: {state.get('travel_date') or '不明'}
期間: {state.get('duration') or '不明'}
参加人数: {state.get('num_people') or '不明'}人
1人あたりの予算上限: {state.get('budget_limit') or '不明'}円
旅行テーマ: {themes}
特別条件: {special}
交通手段の希望: {state.get('transport_mode') or 'おまかせ'}

【広すぎるかの基準】
・国全体（「日本」「海外」「アメリカ」など）、複数の都道府県にまたがる地方（「関東」「東北」「九州」「北陸」「四国」など）、
  「どこでも」「おまかせ」「近場」「温泉地」のように場所を特定しない言い方は、広すぎる
・都道府県は、期間に対して広すぎるときだけ広すぎるとする（例: 北海道に1泊2日は広すぎる。北海道を6泊7日で周遊するならそのまま）
・市区町村や、観光地としてまとまったエリア（箱根・軽井沢・京都・金沢・湯布院・ハワイのオアフ島など）は、そのまま

【広すぎるときの決め方】
・希望の範囲の中から、テーマ・季節（旅行日程）・期間・予算・出発地からの移動時間に合う、観光地としてまとまったエリアを1つ選ぶ
・移動で旅が潰れないよう、期間が短いほど出発地から近い所を選ぶ（日帰り・1泊なら片道2〜3時間以内が目安）
・予算の中で、往復の交通費を払っても宿・食事・観光に十分なお金が残る所を選ぶ
・国も決まっていない海外なら、予算と期間で無理のない都市を選ぶ
・地図で検索できる一般的な地名で答える（例: 箱根、日光、湯布院、台北）。「関東の温泉地」のような言い方はしない
・reason は、選んだ行き先と理由を、お客さまにやさしく伝える1文にする（例:「温泉が楽しめて東京から近い箱根で組みました」）
"""
    if state.get("no_car"):
        prompt += "\n【重要】運転免許がない/運転しない前提です。公共交通機関だけで無理なく行けて、現地も電車・バス・徒歩で回れる所を選ぶこと。"
    if state.get("avoid_area"):
        prompt += (f"\n【重要】お客さまは、前回選んだ「{state['avoid_area']}」とは別の場所を希望しています。"
                   f"「{state['avoid_area']}」以外から選ぶこと。")
    if state.get("user_feedback"):
        prompt += f"\n【お客さまのご要望】:\n{state['user_feedback']}"
    prompt += directive(state)
    return prompt


def transport_prompt(state, transport_mode: str, no_car: bool) -> str:
    """往復交通費を見積もらせる。交通手段の希望・運転の可否・海外で指示を切り替える。"""
    if transport_mode and transport_mode != "おまかせ":
        mode_instruction = f"""・利用する交通手段は「{transport_mode}」で固定すること（他の手段に置き換えないこと）
・「{transport_mode}」での出発地→目的地→出発地の往復に必要な費用を見積もること
・車・レンタカーの場合: 往復のガソリン代＋高速道路料金（＋必要なら駐車場代）を「1台あたり」で算出し、1台あたり最大5人乗車として {state['num_people']}人を割り当て、最終的に1人あたりの金額に割り戻すこと
・高速バス・夜行バスの場合: 往復の運賃を1人あたりで見積もること
・飛行機の場合: 往復の航空券代＋必要なら空港アクセス費を1人あたりで見積もること
・新幹線・特急など鉄道の場合: 往復の運賃＋特急/指定席料金を1人あたりで見積もること"""
        if no_car:
            mode_instruction += "\n・ただし運転免許がない/運転しない前提のため、車・レンタカーの運転を伴う手段は選ばないこと"
    elif no_car:
        mode_instruction = """・運転免許がない/運転しない前提。車・レンタカーは選ばないこと。
・新幹線・特急・飛行機・高速バス・在来線など公共交通機関のみで、所要時間と費用のバランスが最も良い手段を選ぶこと"""
    else:
        mode_instruction = """・新幹線・特急・飛行機・高速バス・車など、所要時間と費用のバランスが最も良い交通手段を選ぶこと
・宿泊・食事・観光に十分な残予算を確保できるよう、過度に高額でない費用対効果の高い手段を優先すること（交通費で予算の大半を使い切らない）"""
    if state.get("is_overseas"):
        # 海外は航空便。国内向けの列挙（新幹線・高速バス）に引きずられて陸路を選ばないよう明示する
        mode_instruction += (
            "\n・行き先は海外のため、往復は航空便を前提にすること（陸路・船を指定された場合を除く）"
            "\n・航空券は燃油サーチャージ・空港税等の諸費用込みの往復額に、自宅→出発空港と現地空港→市内の"
            "アクセス費を加え、1人あたり日本円で見積もること（現地通貨の分は概算レートで換算）"
        )

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
    return prompt


def sightseeing_candidates_prompt(state, search_context: str) -> str:
    """観光スポットの候補を多めに集めさせる。"""
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
    prompt += refresh_hint(state, state.get("spots") or [], "観光スポット")
    prompt += directive(state)
    return prompt


def sightseeing_prompt(state, target_spots: int) -> str:
    """候補の中から、動線と条件に合う観光スポットを target_spots 件ほど選ばせる。"""
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
・スポットは{target_spots}件程度を選ぶこと（移動を含めても1日の滞在時間をしっかり満たせる数。日帰りでも昼過ぎに予定が尽きないようにする）
・**移動で1日が潰れないよう、スポットは1〜2エリアにまとめて選ぶこと**（新宿・銀座・表参道・渋谷のように離れた複数エリアへ散らさない）。スポット間はドアtoドアの公共交通＋徒歩で概ね30分以内を目安にし、無理のない動線にすること
・旅行テーマを最もよく体現できるスポットを優先すること
・各スポットの通常営業時間・定休日・{state['travel_date']}時点の季節限定イベントや混雑状況を考慮すること
・特別条件がある場合（車椅子利用・アレルギー等）は、施設のバリアフリー対応状況を具体的に確認したうえで条件を満たすスポットのみ選ぶこと
・{state['num_people']}人の大人数でも対応できる収容人数・予約の可否・広さを確認すること
"""
    if state.get("feedback") and state.get("status") in ("fix_sightseeing", "fix_time"):
        prompt += (
            f"\n【前回の審査での指摘（必ず反映して選び直す）】:\n{state['feedback']}\n"
            "特に「エリアを絞る」「数を減らす」「過密／移動に無理」という指摘がある場合は、"
            "スポット数を1〜2件減らし、近接した1〜2エリアにまとめて選び直すこと。"
        )
    if state.get("user_feedback"):
        prompt += f"\n【ユーザーからのご要望（最優先）】:\n{state['user_feedback']}\n上記の要望を必ず最優先で反映してスポットを選ぶこと。"
    if state.get("no_car"):
        prompt += "\n【重要】運転免許がない/運転しない前提です。公共交通機関（電車・バス）＋徒歩で無理なく行けるスポットだけを選び、車でしか行けない場所は除外すること。"
    prompt += weather(state)
    prompt += preference(state)
    prompt += directive(state)
    return prompt


def accommodation_candidates_prompt(state, num_nights: int, per_night_budget: int, search_context: str) -> str:
    """1泊あたりの予算目安で泊まれる宿の候補を集めさせる。"""
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
{f"飲食店: {', '.join(restaurants)}" if restaurants else ""}
{search_context}

【選定の基準】
・1泊1人あたり目安（{per_night_budget:,}円）前後で泊まれる施設を中心に選ぶこと。高級旅館だけに偏らず、ビジネスホテル・ゲストハウス・素泊まり可など手頃な選択肢も必ず含めること。
・最低でも候補の半数は目安価格以内に収まる施設にすること。

【出力】
厳密に3個以上5個以下の施設名のみを返してください。
"""
    if state.get("no_car"):
        prompt += "\n【重要】運転免許がない/運転しない前提です。駅・バス停から公共交通機関＋徒歩で無理なく行ける宿だけを選び、車が前提の立地（送迎が無い山中・郊外など）は除外すること。"
    prompt += refresh_hint(state, state.get("accommodation") or [], "宿泊施設")
    prompt += directive(state)
    return prompt


def accommodation_prompt(state, num_nights: int, total_accommodation_budget: int, per_night_budget: int) -> str:
    """候補の中から、宿泊予算に収まる宿を原則1軒だけ選ばせる。"""
    candidates = state.get("accommodation_candidates", [])
    prompt = f"""あなたは宿泊施設の選定専門家です。全員が同一施設に宿泊する前提で、最適な宿泊施設を【1箇所だけ】選んでください（連泊で宿泊エリアが大きく変わる場合のみ、その泊数分）。代替案を複数併記しないこと。

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
{f"飲食店: {', '.join(state.get('restaurants', []))}" if state.get('restaurants') else ""}

【候補一覧】
{chr(10).join(f'- {c}' for c in candidates)}

【選定の条件】
・実際に宿泊する施設のみを選ぶこと（全員同一施設・原則1軒）。代替候補や「どちらか」の複数列挙は禁止。宿泊エリアが変わる連泊でない限り1軒に絞ること。
・地図で検索できる正式名称（固有の施設名）で答えること。「駅前のホテル」「地元の旅館」のような曖昧な総称は使わない。
・{state['travel_date']}時点で確実に営業している（閉業・長期休業でない）施設を選ぶこと
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
    # 再ループ時のみ、前回の費用内訳（食事・観光・現地交通を含む）を参考として渡し、
    # 宿の価格帯を「食費などを圧迫しない範囲」で調整できるようにする（初回は前回データ無し）。
    if state.get("retry_count", 0) > 0:
        _prev_estimate = state.get("budget_estimate") or []
        _prev_total = state.get("total_per_person") or 0
        if _prev_estimate or _prev_total:
            prompt += "\n【前回の費用内訳（参考）】\n"
            if _prev_total:
                prompt += f"前回の1人あたり合計: 約{_prev_total:,}円（予算上限 {state['budget_limit']:,}円）\n"
            if _prev_estimate:
                prompt += chr(10).join(_prev_estimate) + "\n"
            prompt += "上記の食事・観光・現地交通の費用も踏まえ、合計が予算内に収まるよう宿の価格帯を調整すること（安くしすぎて質を落とす必要はないが、食費等を圧迫しないこと）。"
    if state.get("user_feedback"):
        prompt += f"\n【ユーザーからのご要望（最優先）】:\n{state['user_feedback']}\n上記の要望を必ず最優先で反映して宿泊施設を選んでください。"
    if state.get("no_car"):
        prompt += "\n【重要】運転免許がない/運転しない前提です。駅・バス停から公共交通機関＋徒歩で無理なく行ける宿だけを選び、車が前提の立地（送迎が無い山中・郊外など）は除外すること。"
    prompt += preference(state)
    prompt += directive(state)
    return prompt


def gourmet_candidates_prompt(state, spots: list, stay: list, search_context: str) -> str:
    """観光スポットと宿の周辺で、飲食店の候補を集めさせる。"""
    prompt = f"""あなたはグルメガイドです。以下の条件に合う飲食店の候補を抽出してください。

行き先: {state['destination']}
旅行日程: {state['travel_date']}
期間: {state['duration']}
選定されたスポット: {', '.join(spots)}
{f"選定済みの宿泊施設: {', '.join(stay)}" if stay else "宿泊施設: なし（宿泊しない行程）"}
旅行のテーマ: {', '.join(state['themes'])}
参加人数: {state['num_people']}人
特別条件: {', '.join(state['special_requirements']) if state['special_requirements'] else 'なし'}
{search_context}

【方針】
・{state['travel_date']}{weekday_hint(state['travel_date'])} に営業している店を優先し、その曜日が定休日に当たりそうな店は候補から外すこと
・地図で検索できる正式な店名で答えること。「駅前のカフェ」「地元の食堂」のような曖昧な総称は使わない。
・宿泊施設がある場合は、その徒歩圏（または宿の館内）で夕食にできる店も1〜2件は候補に含めること（夜にタクシーで往復するだけの外出を避けるため）

【出力】
厳密に4個以上6個以下の飲食店名のみを返してください。
"""
    if state.get("no_car"):
        prompt += "\n【重要】運転免許がない/運転しない前提です。公共交通機関（電車・バス）＋徒歩で無理なく行ける店だけを選び、車でしか行けない店は除外すること。"
    prompt += refresh_hint(state, state.get("restaurants") or [], "飲食店")
    prompt += directive(state)
    return prompt


def gourmet_prompt(state, meals: str, food_budget: int) -> str:
    """候補の中から、食事の回数ぶんの飲食店を食費の目安内で選ばせる。"""
    spots = state.get("spots", [])
    accommodation = state.get("accommodation", [])
    candidates = state.get("restaurant_candidates", [])
    prompt = f"""あなたはグルメガイドです。以下の候補から必要な飲食店を選定してください。

行き先: {state['destination']}
旅行日程: {state['travel_date']}
期間: {state['duration']}
選定されたスポット: {', '.join(spots)}
旅行のテーマ: {', '.join(state['themes'])}
参加人数: {state['num_people']}人
宿泊・食事・観光の予算: {state['remaining_budget']:,}円/人
食費の目安上限: {food_budget:,}円/人
{f"選定済みの宿泊施設: {', '.join(accommodation)}" if accommodation else "宿泊施設: なし（宿泊しない行程）"}
特別条件: {', '.join(state['special_requirements']) if state['special_requirements'] else 'なし'}

【候補一覧】
{chr(10).join(f'- {c}' for c in candidates)}

【選定の基準】
・期間中に必要な食事の回数分をカバーすること（{state['duration']} = {meals}）
・{state['travel_date']}{weekday_hint(state['travel_date'])} の営業日・定休日を考慮し、当日に営業している店のみを選ぶこと（その曜日が定休日に当たる店は選ばない。定休日が不明なら定休日の少ない業態を優先）
・地図で検索できる正式な店名で答えること。「駅前のカフェ」「地元の食堂」のような曖昧な総称は使わない。
・各日程のスポット周辺にある店を選び、日別に「〇日目 昼食」「〇日目 夕食」と明記すること
・{state['destination']}ならではの地元名物・郷土料理が味わえる店を優先すること
・食事の合計が食費の目安上限（{food_budget:,}円/人）以内に収まる価格帯の店を選び、最初から予算内に収めること（後の差し戻しを避ける）
・アレルギー・食事制限がある場合は、その食材を使わないメニューが実際にあるか確認した店のみ選ぶこと
・{state['num_people']}人が同一テーブルで着席できる席数・個室・貸切の可否を確認すること
"""
    if state.get("feedback") and state.get("status") in ("fix_gourmet", "fix_budget", "fix_accommodation", "fix_sightseeing", "fix_time"):
        prompt += f"\n【バランサーからの修正要求】:\n{state['feedback']}\nこの指摘を反映して、飲食店を選び直してください。"
    if state.get("user_feedback"):
        prompt += f"\n【ユーザーからのご要望（最優先）】:\n{state['user_feedback']}\n上記の要望を必ず最優先で反映して飲食店を選んでください。"
    if state.get("no_car"):
        # 観光・宿には入れていた条件が飲食店にだけ抜けており、車でしか行けない店が選ばれ得た
        prompt += "\n【重要】運転免許がない/運転しない前提です。公共交通機関（電車・バス）＋徒歩で無理なく行ける店だけを選び、車でしか行けない店は除外すること。"
    prompt += preference(state)
    prompt += directive(state)
    return prompt


def schedule_prompt(state) -> str:
    """スポット・飲食店・宿を、時系列のスケジュールに組ませる。日帰りと複数日で形式を切り替える。"""
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

    # 泊数と日数を分けて扱う（0泊2日の夜行は「宿なし・2日行程」）。
    # スケジュールの形式は日数で、宿の扱いは泊数で決める。
    num_nights, num_days = parse_duration(state["duration"])
    day_trip = num_days <= 1

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
・日帰りでも【1日をしっかり使う】こと。昼過ぎ（〜14時台）に予定が尽きて早く帰る行程にはしない。
・【帰宅時刻から逆算して組む】こと：まず無理のない帰宅時刻（目安は夕方〜夜の18〜21時頃、ユーザー指定の時間があればそれを最優先）を決め、「帰宅時刻 − 復路の所要時間 = 現地を出発する時刻」を算出する。その現地出発時刻まで現地で充実して過ごすように、午前から行程を組み立てること（最終入場・閉館時刻は厳守）。
・提示スポットだけで早く終わってしまう場合は、近隣の【具体的な】スポット・カフェ・体験（例: 展望台、庭園、名店のおやつ、川沿いの遊歩道など実在の場所）を補って充実させること。曖昧な「散策」「自由時間」で埋めないこと。

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
        # 宿の有無で行程指示を切り替える（0泊2日=夜行は宿の指示を入れない）
        if num_nights > 0:
            lodging_rules = """・宿泊施設のチェックイン（目安15:00〜）・チェックアウト（目安11:00〜）を必ずスケジュールに組み込むこと
・チェックアウト後は宿泊施設に戻る行程を入れないこと。最終日は最後の観光地から直接、または帰路の駅周辺で昼食をとってから出発すること
・夕食はできるだけ宿泊施設内または徒歩圏内の飲食店を選び、タクシーで往復するだけの外出は避けること"""
        else:
            lodging_rules = """・これは【宿泊なし】の行程（夜行バス・車中泊・深夜移動など）。ホテルのチェックイン/チェックアウトは存在しないため組み込まないこと
・夜間をどう過ごすか（夜行バスの乗車時刻・車中泊の場所・深夜営業施設など）を具体的に明記すること
・深夜移動の疲労を考慮し、翌日の午前は無理のないペースにすること"""
        prompt = f"""あなたは綿密なツアーコンダクターです。
以下の【絶対に守るべき条件】と【絶対に含めるべき項目】を満たした日別タイムスケジュールを作成してください。

【絶対に守るべき条件】
・旅行の時間枠: {state['duration']}  ← 必ずこの時間枠の中に全ての予定を収めること
・この旅行は{num_nights}泊{num_days}日。「1日目」〜「{num_days}日目」の日別ブロックを必ず【すべて】作成すること
・帰路・帰宅は必ず{num_days}日目（最終日）に置くこと。途中の日に帰路を入れて旅行を切り上げないこと
・「予備日」「自由行動のみの日」を作らないこと。最終日まで具体的なスポット・食事で構成すること
・出発地: {state['departure_location']}（往路・復路の移動時間を具体的にスケジュールに組み込むこと）
・往復の交通手段: {state.get('transport_mode', 'おまかせ')}（この手段に合わせて往復の移動時間・経路を組むこと。車なら運転・休憩・駐車、高速バスなら乗車時間、鉄道/飛行機なら駅・空港での移動を考慮）
・参加人数: {state['num_people']}人（大人数は移動・入場・食事に時間がかかるため各行動に余裕を持たせること）
・各スポットの営業時間（開館・閉館）を確認し、開館前の到着や閉館時刻を超えた滞在にならないよう、「到着時刻 + 滞在時間 <= 閉館時刻」を必ず守ること
・スポット間の移動は交通手段と所要時間を明記し、{state['destination']}の混雑を考慮して余裕を持たせること
{lodging_rules}
・食事（昼食・夕食）の時間帯を明確に確保し、飲食店の営業時間内に訪問できるようにすること
・特別条件（車椅子等）がある場合、移動に追加時間がかかることを考慮すること

【絶対に含めるべき項目】（以下のリストのすべてをスケジュールに組み込むこと）
・観光スポット（すべて必須）: {', '.join(spots) if spots else '（なし）'}
・飲食店（すべて必須）: {', '.join(restaurants) if restaurants else '（なし）'}
・宿泊施設: {', '.join(accommodation) if accommodation else ('（なし・宿泊しない行程）' if num_nights == 0 else '（なし）')}
・旅行テーマ: {', '.join(state['themes'])}
{must_include_block}
【出力形式】
・「1日目」〜「{num_days}日目」の日別ブロック（必ず{num_days}個すべて）に分けて記載すること。各日の先頭行はその日を表す「N日目」の行にすること
・各行動を「HH:MM 行動内容（所要時間・移動手段・距離）」の形式で時系列に記載すること
・1日の総移動時間と観光時間のバランスが適切かを自己チェックし、詰め込みすぎの場合は削減すること
"""
    # 審査の指摘は fix_time に限らず伝える。fix_gourmet 等で作り直したあとの再スケジュールで、
    # 指摘済みの問題施設（位置が違う穴埋めカフェ等）を再び挿入してしまうループを防ぐ。
    if state.get("feedback") and str(state.get("status", "")).startswith("fix"):
        prompt += (
            f"\n【重要：前回審査での指摘】:\n{state['feedback']}\n"
            "指摘で「問題がある」とされた施設・場所はスケジュールに使わないこと（補完スポットとしても不可）。"
            "ただし【絶対に含めるべき項目】に挙げた観光スポット・飲食店・宿泊施設はこの限りではなく、必ず組み込むこと"
            "（「含まれていない」という指摘は、除外ではなく組み込みの指示である）。"
            "時間・移動に関する指摘があれば完全にクリアすること。"
        )
    if state.get("user_feedback"):
        prompt += f"\n\n【ユーザーからのご要望（最優先）】:\n{state['user_feedback']}\n上記の要望を必ず最優先で反映してスケジュールを組んでください。"
    if state.get("schedule_pref"):
        prompt += (
            f"\n\n【時間に関する希望（最優先）】: {state['schedule_pref']}\n"
            "この希望に沿って帰宅時刻・出発時刻・各所の滞在時間を決めること。"
            "例『夕方までに帰りたい』なら帰宅が夕方になるよう復路から逆算し、遅くまで滞在しないこと。"
            "希望と前述の逆算ルールが矛盾する場合は、必ずこの希望を優先する。"
        )

    # 「散策」「自由時間」などの曖昧な予定で埋めない（具体的な行動で構成する）
    prompt += (
        "\n\n【予定の質（重要）】\n"
        "・「散策」「自由時間」「周辺をぶらぶら」などの曖昧な時間で埋めないこと。各時間帯は具体的な"
        "スポット名・体験・食事で構成すること。\n"
        "・どうしても空き時間ができる場合のみ30分以内に留め、その時間も近くの具体的な店・スポットを示すこと。\n"
        "・空き時間を埋めるために追加するカフェ・店・スポットは、直前・直後の予定と【同じエリア内】に実在する"
        "ものだけにすること。別エリア（別の温泉街・別の市区町村）の施設を近所のように扱わないこと。"
        "所在地や実在に確信が持てない場合は追加せず、既存スポットの滞在時間を延ばすこと。\n"
        "・1日に詰め込みすぎず、移動と滞在のバランスを優先すること（無理に予定を増やして散策で埋めない）。"
    )
    prompt += (
        "\n\n【過密にしない（最重要）】\n"
        "・移動時間はドアtoドアで見積もること（出発地点での徒歩＋駅での待ち＋乗車＋到着駅からの徒歩＋乗換）。"
        "乗車時間だけで『約15分』のように短く書かないこと。離れたエリア間の移動は現実的な所要時間を見込む。\n"
        "・食事やカフェ休憩を短時間に連続させないこと（昼食の直後にアフタヌーンティー、休憩→食事→休憩のような並びは避ける）。"
        "食事の間隔は最低でも2〜3時間あけること。\n"
        "・与えられたスポットを全て無理に詰め込まないこと。1日で現実的に回りきれない場合は訪問先を1〜2件減らし、"
        "余裕のあるスケジュールにすること（回りきれないスポットはスケジュールから省いてよい）。\n"
        "・1日に立ち寄る『エリア（街）』は2つ程度までを目安にし、エリアを行き来して移動で消耗しないこと。"
    )
    if state.get("no_car"):
        prompt += (
            "\n\n【移動手段（重要）】運転免許がない/運転しない前提です。すべての移動を公共交通機関（電車・バス）"
            "＋徒歩で組み、各移動に路線・所要時間を明記すること。レンタカー・自家用車の運転を前提にしないこと。"
        )
    if state.get("is_overseas"):
        prompt += (
            "\n\n【海外行程の条件（重要）】\n"
            "・時刻はすべて現地時刻で書き、冒頭に日本との時差を1行で示すこと。\n"
            "・往路・復路のフライトは出発・到着の時刻と所要時間を明記すること。出国は出発の2〜3時間前に空港へ着き、"
            "到着後は入国審査・荷物受取に1時間程度を見込むこと。\n"
            "・初日は到着後の行程を軽めにし、最終日は復路の出発時刻から逆算して現地を出ること。"
            "乗継がある場合はその待ち時間も含めること。"
        )

    if state.get("weather"):
        prompt += (
            weather(state)
            + "・天気が崩れる日は屋外スポットの滞在を短めにし、雨でも楽しめる屋内の時間帯を挟むこと。\n"
        )
    prompt += preference(state)
    prompt += directive(state)
    return prompt


def missing_days_note(missing, num_nights: int, total_days: int) -> str:
    """スケジュールに欠けた日があったとき、作り直しのプロンプトに足す一文。"""
    return (
        "\n\n【重大な不備（必ず修正すること）】前回の出力には "
        + "、".join(f"「{d}日目」" for d in sorted(missing))
        + f" のブロックがありませんでした。この旅行は{num_nights}泊{total_days}日です。"
        f"「1日目」〜「{total_days}日目」の全ブロックを必ず作成し、各日の先頭行に「N日目」の行を置き、"
        f"帰路は{total_days}日目に置いてください。"
    )


def cost_prompt(state) -> str:
    """決まったプランに、日別と合計の費用を付けさせる。"""
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
※宿泊費は実際に宿泊する施設のみを「1泊につき1軒」で計上すること。複数施設を併記して二重に計上しないこと。

■ 往復交通費: {state['transport_cost']:,}円/人（確定済み）

{day_sections(state['duration'])}

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
    if state.get("is_overseas"):
        prompt += (
            "\n【海外の費用】現地通貨の金額はすべて日本円に換算し、換算レートを冒頭に明記すること。"
            "「海外旅行保険」「通信費（SIM/Wi-Fi）」「両替・カード手数料の目安」を項目として必ず加え、"
            "それらも1人あたり合計に含めること。"
        )
    prompt += (
        "\n【整合の必須事項】1人あたり合計は往復交通費を含み、各費用項目の和と必ず一致させること。"
        "予算上限を超える場合は超過額を明記すること。total_per_person は同じ合計額（整数・円）にすること。"
    )
    prompt += directive(state)
    return prompt


def review_prompt(state, day_trip: bool) -> str:
    """プラン全体を6つの観点で審査させる（承認か、どこを直すかの差し戻し）。"""
    _b_nights, _b_days = parse_duration(state["duration"])
    prompt = f"""あなたは旅行代理店のシニアマネージャーです。以下のプランを審査してください。

■ 基本条件: {state['destination']}（{state['duration']}）
■ 旅行日程: {state['travel_date']}
■ 出発地: {state['departure_location']}
■ 参加人数: {state['num_people']}人
■ 予算上限: 1人あたり {state['budget_limit']:,}円（往復交通費 {state['transport_cost']:,}円確定、残り予算: {state['remaining_budget']:,}円）
■ テーマ: {', '.join(state['themes'])}
■ 特別条件: {', '.join(state['special_requirements']) if state['special_requirements'] else 'なし'}
■ 往復の交通手段: {state.get('transport_mode') or 'おまかせ'}
■ 運転の可否: {'運転しない（車・レンタカーは不可。公共交通＋徒歩のみ）' if state.get('no_car') else '制約なし'}
■ 時間に関するご希望: {state.get('schedule_pref') or 'なし'}
■ 今回のご要望: {state.get('user_feedback') or 'なし'}
■ 観光地: {', '.join(state['spots'])}
■ 飲食店: {', '.join(state['restaurants'])}
{f"■ 宿泊施設: {', '.join(state.get('accommodation', []))}" if not day_trip else "■ 宿泊施設: なし（宿泊しない行程）"}
■ スケジュール:
{chr(10).join(state['schedule'])}
■ 費用見積もり:
{chr(10).join(state.get('budget_estimate', []))}

【審査の6観点】
1. 予算: 費用見積もりの1人あたり合計が予算上限（{state['budget_limit']:,}円）の【110%以内】に収まっているか。予備費の範囲内とみなせる軽微な超過（110%以内）は合格とし、fix_budget にしないこと。明確に110%を超える場合のみ問題とし、超過金額を具体的に明記すること。
2. スケジュール: 期間（{state['duration']}＝{_b_days}日間）どおりの日数で組まれているか（{"「1日目」〜「" + str(_b_days) + "日目」まで全てあり、帰路は最終日のみ" if _b_days >= 2 else "1日で完結している"}）。「予備日」や中身のない日で埋めていないか。移動時間が現実的か、開館前到着・閉館後出発などの矛盾がないか、1日の総移動時間が観光時間を上回っていないか。
   ※日数不足・途中の日の帰路・予備日は【スケジュールの問題】なので必ず fix_time を選ぶこと（fix_accommodation にしない）。宿泊施設リストは施設名のみで泊数を表さない（同一施設での連泊が原則）ため、宿の泊数不足をここから推定しないこと。
   ※上記の「観光地」「飲食店」リストに無いのにスケジュールへ登場する店・カフェ・スポット（空き時間の補完）は、位置・実在・移動時間の問題があっても fix_gourmet / fix_sightseeing ではなく必ず fix_time を選ぶこと（それらはスケジュール作成者が挿入したものであり、リストの選び直しでは直らない）。feedbackには問題の施設名を明記すること。
3. 疲労度: {state['num_people']}人の大人数で、特別条件（{', '.join(state['special_requirements']) if state['special_requirements'] else 'なし'}）を持つ参加者が無理なく楽しめる強度か。
4. テーマ一貫性: 観光スポット・飲食店{"" if day_trip else "・宿泊施設"}がすべて旅行テーマ（{', '.join(state['themes'])}）に沿っているか。
5. 特別条件の充足: 車椅子対応・アレルギー対応などの特別条件が、全スポット・飲食店{"" if day_trip else "・宿泊施設"}で実際に満たされているか。
6. ご希望の反映: 上記の「運転の可否」「時間に関するご希望」「今回のご要望」がスケジュールに反映されているか。
   ※「運転しない」なのに車・レンタカーでの移動が含まれる、「夕方までに帰りたい」のに夜遅くの帰宅になっている、
     といった食い違いは fix_time を選び、feedback に食い違いの箇所を具体的に書くこと（「なし」の項目は審査対象外）。
{"【重要】これは宿泊のないプランです（日帰りまたは夜行）。fix_accommodation は絶対に使わないこと。" if day_trip else ""}

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
    prompt += directive(state)
    return prompt
