import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def test_smoke_single_input():
    import importlib
    import chat.graph as g

    importlib.reload(g)
    inputs = {
        "destination": "京都",
        "travel_date": "2025年8月13日〜14日（お盆期間）",
        "duration": "1泊2日（1日目13:00現地着〜2日目17:00現地発）",
        "themes": [
            "歴史・伝統文化を深く体感する",
            "本格的な懐石料理を楽しむ",
            "ゆったりのんびり疲れない旅",
        ],
        "num_people": 4,
        "budget_limit": 70000,
        "departure_location": "東京（東京駅）",
        "special_requirements": [
            "同行者に車椅子利用者が1名いるためバリアフリー対応必須",
            "魚介類アレルギーの同行者が1名いるため食事の際は要確認",
        ],
        "retry_count": 0,
        "prev_status": "",
        "user_feedback": "",
        "search_context": "",
        "spot_candidates": [],
        "accommodation_candidates": [],
        "restaurant_candidates": [],
    }

    state = g.generate_travel_plan(inputs)
    assert state["destination"] == "京都"
    assert isinstance(state.get("spots", []), list)
    print("SMOKE TEST PASSED:", state.get("status"))


if __name__ == "__main__":
    test_smoke_single_input()
