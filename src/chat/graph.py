"""プラン生成のワークフロー（LangGraph）定義と実行エントリ。

各エージェント（chat.agents）をノードとして登録し、
  transport → 観光候補/選定 → 宿泊候補/選定 → グルメ候補/選定
  → timekeeper → cost_manager → balancer
の順に連結する。balancer の後は route_after_balancer により
承認なら終了、差し戻しなら該当ノードへ戻る条件分岐を行う。

generate_travel_plan() が外部からの呼び出し口。
末尾の __main__ ブロックは単体動作確認用のCLIテストハーネス。
"""

from concurrent.futures import ThreadPoolExecutor

from langgraph.graph import StateGraph, START, END
from chat.models import TravelPlanState
from chat.agents import (
    transport_agent, sightseeing_candidates, sightseeing_expert,
    gourmet_candidates, gourmet_hunter,
    accommodation_candidates, accommodation_agent,
    timekeeper, cost_manager, balancer,
    route_after_balancer,
)


# プラン生成の状態グラフを構築する。
# transport（交通費）と sightseeing_candidates（観光候補抽出）は互いに独立なので、
# グラフには含めず generate_travel_plan で並列に先行実行してから本体を回す
# （これらは差し戻しの戻り先ではないため、グラフから外しても再生成ループに影響しない）。
workflow = StateGraph(TravelPlanState)

workflow.add_node("sightseeing", sightseeing_expert)
workflow.add_node("accommodation_candidates", accommodation_candidates)
workflow.add_node("accommodation", accommodation_agent)
workflow.add_node("gourmet_candidates", gourmet_candidates)
workflow.add_node("gourmet", gourmet_hunter)
workflow.add_node("timekeeper", timekeeper)
workflow.add_node("cost_manager", cost_manager)
workflow.add_node("balancer", balancer)

workflow.add_edge(START, "sightseeing")
workflow.add_edge("sightseeing", "accommodation_candidates")
workflow.add_edge("accommodation_candidates", "accommodation")
workflow.add_edge("accommodation", "gourmet_candidates")
workflow.add_edge("gourmet_candidates", "gourmet")
workflow.add_edge("gourmet", "timekeeper")
workflow.add_edge("timekeeper", "cost_manager")
workflow.add_edge("cost_manager", "balancer")

workflow.add_conditional_edges(
    "balancer",
    route_after_balancer,
    {
        "end": END,
        "sightseeing": "sightseeing",
        "accommodation": "accommodation",
        "timekeeper": "timekeeper",
        "accommodation_candidates_ready": "accommodation_candidates",
        "gourmet_candidates_ready": "gourmet_candidates",
        "candidates_ready": "sightseeing",
    },
)

graph = workflow.compile()


def generate_travel_plan(inputs: dict):
    """旅行条件 inputs からプラン生成ワークフローを実行し、最終状態を返す。

    制御用フィールド（retry_count・各候補リスト等）を既定値で補ってから
    グラフを実行する。recursion_limit は差し戻しループの暴走を防ぐ上限。
    """
    inputs.setdefault("transport_mode", "おまかせ")
    inputs.setdefault("no_car", False)
    inputs.setdefault("edit_targets", [])
    inputs.setdefault("retry_count", 0)
    inputs.setdefault("prev_status", "")
    inputs.setdefault("user_feedback", "")
    inputs.setdefault("search_context", "")
    inputs.setdefault("spot_candidates", [])
    inputs.setdefault("accommodation_candidates", [])
    inputs.setdefault("restaurant_candidates", [])

    # 互いに独立な「交通費の試算」と「観光候補の抽出」を並列に先行実行して数秒短縮する。
    # どちらも inputs を読むだけで書き換えないためスレッド共有して安全。
    # transport_agent は予算超過時に ValueError を投げるので result() で伝播させる。
    with ThreadPoolExecutor(max_workers=2) as ex:
        f_transport = ex.submit(transport_agent, inputs)
        f_sightseeing = ex.submit(sightseeing_candidates, inputs)
        transport_out = f_transport.result()
        sightseeing_out = f_sightseeing.result()
    inputs.update(transport_out)
    inputs.update(sightseeing_out)

    return graph.invoke(inputs, {"recursion_limit": 60})


if __name__ == "__main__":
    travel_inputs = {
        "destination": "京都",
        "travel_date": "2025年8月13日〜14日（お盆期間）",
        "duration": "1泊2日（1日目13:00現地着〜2日目17:00現地発）",
        "themes": ["歴史・伝統文化を深く体感する", "本格的な懐石料理を楽しむ", "ゆったりのんびり疲れない旅"],
        "num_people": 4,
        "budget_limit": 70000,
        "departure_location": "東京（東京駅）",
        "transport_mode": "おまかせ",
        "no_car": False,
        "special_requirements": ["同行者に車椅子利用者が1名いるためバリアフリー対応必須", "魚介類アレルギーの同行者が1名いるため食事の際は要確認"],
        "retry_count": 0,
        "prev_status": "",
        "user_feedback": "",
        "search_context": "",
        "spot_candidates": [],
        "accommodation_candidates": [],
        "restaurant_candidates": [],
    }

    def display_plan(state: dict) -> None:
        print("\n" + "=" * 60)
        print(f"📍 目的地: {state['destination']}（出発地: {state['departure_location']}）")
        print(f"⏱️ 期間: {state['duration']}")
        print(f"👥 参加人数: {state['num_people']}人")
        print(f"💴 予算上限: 1人あたり {state['budget_limit']:,}円")
        print(f"🚍 交通手段: {state.get('transport_mode', 'おまかせ')}")
        print(f"🚄 交通費: {state.get('transport_cost', 0):,}円/人")
        print(f"💰 残り予算: {state.get('remaining_budget', 0):,}円/人")
        print(f"⚠️ 特別条件: {', '.join(state['special_requirements'])}")

        status = state.get("status")
        if status == "budget_infeasible":
            print("\n❌ 予算不足により旅行プランの作成を断念しました ❌")
            print("=" * 60)
            print(f"\n💬 バランサーの判断: {state['feedback']}")
            print("\n💰 試算した費用内訳:")
            for item in state.get("budget_estimate", []):
                print(f"  - {item}")
            return

        if status == "approved":
            print("\n🎉 最終確定した旅行プラン 🎉")
        else:
            print(f"\n⚠️ 未承認のまま終了したプラン（最終ステータス: {status}）⚠️")
            print(f"💬 バランサーの最終指摘: {state['feedback']}")
        print("=" * 60)
        print(f"✨ 主要観光地: {', '.join(state['spots'])}")
        print(f"🍱 グルメ: {', '.join(state['restaurants'])}")
        print(f"🏨 宿泊施設: {', '.join(state['accommodation'])}")
        print("\n📅 スケジュール詳細:")
        for step in state["schedule"]:
            print(f"  - {step}")
        print("\n💰 費用見積もり:")
        for item in state["budget_estimate"]:
            print(f"  - {item}")
        if status == "approved":
            print(f"\n💬 バランサー総評: {state['feedback']}")

    round_num = 1
    while True:
        print(f"\n🚀 エージェントたちによる旅行計画会議を開始します...（第{round_num}回）")
        final_state = generate_travel_plan(travel_inputs)
        display_plan(final_state)

        if final_state.get("status") == "budget_infeasible":
            break

        print("\n" + "=" * 50)
        print("💬 プランへのご意見・修正希望があればお聞かせください。")
        print("   （このままでよければ Enter を押してください）")
        user_comment = input(">> ").strip()

        if not user_comment:
            print("\n✅ プランを確定しました！よい旅を！")
            break

        travel_inputs["user_feedback"] = user_comment
        travel_inputs["retry_count"] = 0
        travel_inputs["prev_status"] = ""
        round_num += 1
        print(f"\n📝 ご要望「{user_comment}」を反映して再プランします...")
