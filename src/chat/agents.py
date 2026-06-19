import re
from chat.models import TravelPlanState
from chat.llm import llm, invoke_with_retry, build_search_context
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
    return "日帰り" in duration or bool(re.match(r'0泊', duration.strip()))


def _pp(data, label):
    """Plain small bubble logger for extracted entities."""
    if not data:
        return
    log.info(label)
    for item in data:  # type: ignore[arg-type]
        log.info("  - %s", item)


def transport_agent(state: TravelPlanState):
    log.info("[🚄 交通エージェント]: 往復交通費を試算中... destination=%s", state["destination"])
    prompt = f"""あなたは交通費の専門家です。以下の条件で往復交通費（1人あたり）を概算してください。

出発地: {state['departure_location']}
目的地: {state['destination']}
参加人数: {state['num_people']}人
旅行日程: {state['travel_date']}

【選定の基準】
・新幹線・特急・飛行機など、所要時間と費用のバランスが最も良い交通手段を選ぶこと
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
    structured_llm = llm.with_structured_output(SightseeingCandidatesOutput)
    response = invoke_with_retry(structured_llm, prompt)
    _pp(response.candidates, "✨ 候補スポット:")
    return {"spot_candidates": response.candidates}


def sightseeing_expert(state: TravelPlanState):
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
    structured_llm = llm.with_structured_output(SightseeingOutput)
    response = invoke_with_retry(structured_llm, prompt)
    _pp(response.spots, "✨ 選定スポット:")
    return {"spots": response.spots}


def accommodation_candidates(state: TravelPlanState):
    if is_day_trip(state["duration"]):
        log.info("[🏨 宿泊エージェント]: 日帰りのため宿泊施設なし")
        return {"accommodation_candidates": []}
    log.info("[🏨 宿泊エキスパート]: 宿泊候補を抽出中... destination=%s", state["destination"])
    num_nights = int(m.group(1)) if (m := re.search(r'(\d+)泊', state["duration"])) else 1
    queries = [
        f"{state['destination']} ホテル 旅館 おすすめ {state['themes'][0]} 公式",
        f"{state['destination']} 宿泊 観光協会 おすすめ",
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
特別条件: {', '.join(state['special_requirements']) if state['special_requirements'] else 'なし'}
観光スポット: {', '.join(spots)}
飲食店: {', '.join(restaurants)}
{search_context}

【出力】
厳密に3個以上5個以下の施設名のみを返してください。
"""
    structured_llm = llm.with_structured_output(AccommodationCandidatesOutput)
    response = invoke_with_retry(structured_llm, prompt)
    _pp(response.accommodation, "🏨 候補宿泊施設:")
    return {"accommodation_candidates": response.accommodation}


def accommodation_agent(state: TravelPlanState):
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
・1泊1人あたりの料金が目安上限（{per_night_budget:,}円）以内に収まる施設を選ぶこと
・チェックイン時刻（最早）とチェックアウト時刻（最遅）を明記すること
・朝食プランの有無と料金を明記すること（テーマに合う朝食が提供される場合は積極的に推奨すること）
・特別条件がある場合（バリアフリー等）は、具体的な対応設備（スロープ・エレベーター・手すり等）を確認済みの施設のみ選ぶこと
"""
    if state.get("feedback") and state.get("status") in ("fix_accommodation", "fix_budget", "fix_gourmet", "fix_sightseeing"):
        prompt += f"\n【バランサーからの修正要求】:\n{state['feedback']}\nこの指摘を反映して、施設を選び直してください。"
    if state.get("user_feedback"):
        prompt += f"\n【ユーザーからのご要望（最優先）】:\n{state['user_feedback']}\n上記の要望を必ず最優先で反映して宿泊施設を選んでください。"

    structured_llm = llm.with_structured_output(AccommodationOutput)
    response = invoke_with_retry(structured_llm, prompt)
    _pp(response.accommodation, "🏨 選定宿泊施設:")
    return {"accommodation": response.accommodation}


def gourmet_candidates(state: TravelPlanState):
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
    structured_llm = llm.with_structured_output(GourmetCandidatesOutput)
    response = invoke_with_retry(structured_llm, prompt)
    _pp(response.restaurants, "🍱 候補飲食店:")
    return {"restaurant_candidates": response.restaurants}


def gourmet_hunter(state: TravelPlanState):
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
・アレルギー・食事制限がある場合は、その食材を使わないメニューが実際にあるか確認した店のみ選ぶこと
・{state['num_people']}人が同一テーブルで着席できる席数・個室・貸切の可否を確認すること
"""
    if state.get("feedback") and state.get("status") in ("fix_gourmet", "fix_budget", "fix_accommodation", "fix_sightseeing", "fix_time"):
        prompt += f"\n【バランサーからの修正要求】:\n{state['feedback']}\nこの指摘を反映して、飲食店を選び直してください。"
    if state.get("user_feedback"):
        prompt += f"\n【ユーザーからのご要望（最優先）】:\n{state['user_feedback']}\n上記の要望を必ず最優先で反映して飲食店を選んでください。"

    structured_llm = llm.with_structured_output(GourmetOutput)
    response = invoke_with_retry(structured_llm, prompt)
    _pp(response.restaurants, "🍱 選定飲食店:")
    return {"restaurants": response.restaurants}


def timekeeper(state: TravelPlanState):
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

    structured_llm = llm.with_structured_output(TimekeeperOutput)
    response = invoke_with_retry(structured_llm, prompt)
    _pp(response.schedule, "📅 作成したスケジュール:")
    return {"schedule": response.schedule}


def _build_day_sections(duration: str) -> str:
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
    structured_llm = llm.with_structured_output(CostOutput)
    response = invoke_with_retry(structured_llm, prompt)
    _pp(response.budget_estimate, "💰 費用見積もり:")
    return {"budget_estimate": response.budget_estimate}


def balancer(state: TravelPlanState):
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
1. 予算: 費用見積もりの1人あたり合計が予算上限（{state['budget_limit']:,}円）を超えていないか。超過している場合は具体的な超過金額を明記すること。
2. スケジュール: 移動時間が現実的か、開館前到着・閉館後出発などの矛盾がないか、1日の総移動時間が観光時間を上回っていないか。
3. 疲労度: {state['num_people']}人の大人数で、特別条件（{', '.join(state['special_requirements']) if state['special_requirements'] else 'なし'}）を持つ参加者が無理なく楽しめる強度か。
4. テーマ一貫性: 観光スポット・飲食店{"" if is_day_trip(state["duration"]) else "・宿泊施設"}がすべて旅行テーマ（{', '.join(state['themes'])}）に沿っているか。
{"" if is_day_trip(state["duration"]) else f"5. 特別条件の充足: 車椅子対応・アレルギー対応などの特別条件が、全スポット・飲食店・宿泊施設で実際に満たされているか。"}
{"【重要】これは日帰りプランです。fix_accommodation は絶対に使わないこと。" if is_day_trip(state["duration"]) else ""}

【判定ルール】
・上記5観点すべてをパスした場合のみ 'approved' を返すこと
・問題がある場合は最も優先度の高い1つのstatusを選び、feedbackに「どの観点で・何が・どの程度問題か」を数値を交えて具体的に記載すること
・差し戻しは最大5回まで。問題が軽微な場合は approved にすること

【budget_infeasible の判断基準】
費用見積もりの合計が予算上限を20%以上超過しており、かつどのスポット・飲食店・宿泊施設を選んでも構造的に予算内に収まらないと判断される場合のみ選択すること。
"""
    if state.get("retry_count", 0) == 0:
        prompt += "\n【重要】これは初回審査です。予算超過の場合でも budget_infeasible は選ばず、fix_* で差し戻してください。"
    structured_llm = llm.with_structured_output(BalancerOutput)
    response = invoke_with_retry(structured_llm, prompt)
    log.info("👉 審査結果: [%s]", response.status.upper())
    log.info("💬 フィードバック: %s", response.feedback)
    return {
        "status": response.status,
        "prev_status": state.get("status", ""),
        "feedback": response.feedback,
        "retry_count": state.get("retry_count", 0) + 1,
    }


def route_after_balancer(state: TravelPlanState):
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
