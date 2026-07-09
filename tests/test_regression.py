"""この開発セッションで修正したバグの回帰テスト。

APIキー・DB不要で一瞬で回る（LLM/検索/DB/ネットワークはモック、または純粋関数のみ）。
一度直したバグが将来ぶり返していないかを検知するのが目的。
実行: pytest tests/test_regression.py

依存（langgraph 等）が入っていない環境では自動でスキップする。本番・CI・
requirements.txt を入れたローカルでは実行される。
"""
import os
import sys
from datetime import date, timedelta

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
os.environ.setdefault("SECRET_KEY", "test")
os.environ.setdefault("GOOGLE_API_KEY", "test")
os.environ.setdefault("TAVILY_API_KEY", "test")
os.environ.pop("GCS_BUCKET", None)

# これらが無い環境ではモジュールごとスキップ（本番・CIでは入っている）
pytest.importorskip("langgraph")
pytest.importorskip("langchain_google_genai")

TODAY = date.today()


def _fmt(d):
    return f"{d.year}年{d.month}月{d.day}日"


# ----------------------------------------------------------------------
# 進捗表示「あと◯つで完成！」の二重表示
# ----------------------------------------------------------------------
def test_progress_prefix_stripped_single_double_none():
    from chat.chat import _strip_progress
    # 単一プレフィックス
    assert _strip_progress("あと2つで完成！ 🍀🍀🍀🍀🍀・・\n\n本文") == "本文"
    # LLMが模倣して二重化（改行1つで続くパターンも剥がす）
    assert _strip_progress(
        "あと2つで完成！ 🍀・\nあと2つで完成！ 🍀🍀・・\n\n本文") == "本文"
    # プレフィックス無しはそのまま
    assert _strip_progress("どちらへのご旅行をお考えですか？") == "どちらへのご旅行をお考えですか？"


# ----------------------------------------------------------------------
# 相対日付（明日・今週末）の絶対日付への正規化
# ----------------------------------------------------------------------
def test_normalize_relative_dates():
    from chat.chat import _normalize_travel_date as norm
    import weather
    assert norm("明日") == _fmt(TODAY + timedelta(days=1))
    assert norm("明日から2泊") == _fmt(TODAY + timedelta(days=1))
    assert norm("あさって") == _fmt(TODAY + timedelta(days=2))
    assert norm("3日後") == _fmt(TODAY + timedelta(days=3))
    # 週末系は曜日依存なので、変換後が解析可能な未来日付であることを確認
    for word in ("今週末", "来週末", "来週"):
        d = weather.parse_date(norm(word))
        assert d is not None and d >= TODAY


def test_normalize_leaves_absolute_and_vague_dates():
    from chat.chat import _normalize_travel_date as norm
    assert norm("2026年7月10日〜12日") == "2026年7月10日〜12日"  # 絶対日付は非破壊
    assert norm("7/10") == "7/10"                              # 年なしも weather 側で解釈可
    assert norm("お盆あたり") == "お盆あたり"                    # 曖昧語は誤変換しない
    assert norm("") == "" and norm(None) is None


# ----------------------------------------------------------------------
# 天気: 年なし日付の解析 / 16日クランプ / 目的地フォールバック
# ----------------------------------------------------------------------
def test_weather_parse_date():
    import weather
    assert weather.parse_date("2026年7月3日") == date(2026, 7, 3)
    d = weather.parse_date("7/2")
    assert d is not None and (d.month, d.day) == (7, 2)
    assert weather.parse_date("未定") is None
    assert weather.parse_date("2泊3日") is None  # 期間表記を日付と誤認しない


def test_forecast_clamps_end_within_16_days(monkeypatch):
    import weather

    sent = {}

    class _Resp:
        def json(self):
            return {"daily": {"time": [], "weathercode": []}}

    monkeypatch.setattr(weather.requests, "get",
                        lambda url, params=None, timeout=None: (sent.update(params), _Resp())[1])

    # 後半が16日を超える長期旅行でも end はクランプされ、リクエスト自体は飛ぶ
    weather.forecast(35.0, 138.4, TODAY + timedelta(days=10), TODAY + timedelta(days=19))
    assert sent["end_date"] == (TODAY + timedelta(days=16)).strftime("%Y-%m-%d")

    # 完全に範囲外ならAPIを呼ばず空
    sent.clear()
    assert weather.forecast(35.0, 138.4, TODAY + timedelta(days=17), TODAY + timedelta(days=18)) == []
    assert sent == {}


def test_plan_forecast_geocodes_destination_and_caches(monkeypatch):
    import weather
    import geocoding

    calls = []
    monkeypatch.setattr(geocoding, "geocode_one",
                        lambda d, **k: (calls.append(d), {"lat": 35.0, "lng": 138.4})[1])
    monkeypatch.setattr(weather, "forecast", lambda *a, **k: [{"date": "x"}])
    weather._DEST_CACHE.clear()

    future = _fmt(TODAY + timedelta(days=3))
    plan = {"destination": "静岡", "travel_date": future, "duration": "日帰り", "spot_coords": []}
    assert weather.plan_forecast(plan)          # 座標未保存でも天気が出る
    assert weather.plan_forecast(plan)
    assert calls == ["静岡"]                     # キャッシュされ2回目はジオコーディングしない


# ----------------------------------------------------------------------
# formatter: data-plan 埋め込みの一貫性 / 空セクション / 金額の分割禁止 / 宿検索URL
# ----------------------------------------------------------------------
def _sample_plan_state(**over):
    s = {
        "destination": "静岡", "travel_date": "2026年7月10日", "duration": "日帰り",
        "num_people": 1, "budget_limit": 10000, "departure_location": "川崎",
        "transport_cost": 2000, "remaining_budget": 8000, "total_per_person": 8500,
        "status": "approved", "feedback": "良い", "themes": ["温泉"],
        "special_requirements": [], "spots": ["三保松原"], "restaurants": ["さわやか"],
        "schedule": ["09:00 出発"], "accommodation": [], "budget_estimate": ["合計 8500円"],
    }
    s.update(over)
    return s


def test_formatter_embed_matches_payload():
    import json
    import re
    from chat.formatter import _format_plan, plan_payload
    state = _sample_plan_state()
    html = _format_plan(state)
    m = re.search(r'data-plan="([^"]*)"', html)
    raw = m.group(1).replace("&quot;", '"').replace("&#39;", "'")
    assert json.loads(raw) == plan_payload(state)  # フロント保存ボタンの契約


def test_formatter_skips_empty_accommodation_and_nowraps_cost():
    from chat.formatter import _format_plan
    html = _format_plan(_sample_plan_state())          # 日帰り＝宿泊空
    assert "宿泊施設" not in html                        # 空セクションは出さない
    assert 'white-space:nowrap">8,500円/人' in html      # 金額＋単位は泣き別れさせない


def test_booking_url_is_google_maps_not_rakuten():
    from chat.formatter import booking_url
    u = booking_url("静岡")
    assert u.startswith("https://www.google.com/maps/search/?api=1&query=")
    assert "rakuten" not in u


# ----------------------------------------------------------------------
# チャット履歴の送信上限
# ----------------------------------------------------------------------
def test_history_capped():
    from chat.chat import _build_lc_messages, _MAX_HISTORY_MESSAGES
    hist = [{"role": "user" if i % 2 == 0 else "ai", "content": f"m{i}"} for i in range(100)]
    out = _build_lc_messages(hist)
    assert len(out) == _MAX_HISTORY_MESSAGES + 1   # +システムプロンプト
    assert out[-1].content == "m99"                # 直近が残る


# ----------------------------------------------------------------------
# ICS カレンダー書き出し（年なし日付 / 日別イベント / TZ / 折りたたみ）
# ----------------------------------------------------------------------
def test_ics_advanced():
    from views.planner import _build_plan_ics
    plan = {
        "id": 7, "destination": "静岡", "travel_date": "7/10", "duration": "1泊2日",
        "spots": ["三保松原"], "restaurants": [], "accommodation": ["ホテルA"],
        "schedule": ["1日目", "08:00 川崎を出発（新幹線）", "12:00 昼食",
                     "2日目", "10:00 観光", "17:00 帰路へ"],
        "budget_estimate": ["合計 3万円"],
    }
    ics = _build_plan_ics(plan)
    # 年なし日付でも「今日」に化けず7/10になる
    yr = TODAY.year
    assert f"DTSTART;VALUE=DATE:{yr}0710" in ics
    # RFC 5545: 全行75オクテット以内
    for line in ics.split("\r\n"):
        assert len(line.encode("utf-8")) <= 75
    # タイムゾーン・時刻付きイベント・前日リマインダー
    assert "TZID:Asia/Tokyo" in ics
    assert "DTSTART;TZID=Asia/Tokyo:" in ics
    assert "BEGIN:VALARM" in ics


# ----------------------------------------------------------------------
# timekeeper: 宿泊プランの日数欠落を検出して作り直す
# ----------------------------------------------------------------------
def _agent_state(**over):
    s = {
        "destination": "静岡", "travel_date": "2026年7月10日", "duration": "2泊3日",
        "themes": ["温泉"], "num_people": 1, "budget_limit": 50000,
        "departure_location": "川崎", "transport_mode": "おまかせ", "no_car": False,
        "schedule_pref": "", "weather": "", "user_preferences": "", "user_feedback": "",
        "special_requirements": [], "spots": ["三保松原"], "restaurants": ["さわやか"],
        "accommodation": ["湯回廊 菊屋"], "edit_targets": [], "transport_cost": 12000,
        "remaining_budget": 38000, "feedback": "", "status": "", "retry_count": 0,
        "prev_status": "",
    }
    s.update(over)
    return s


def test_timekeeper_refills_missing_final_day(monkeypatch):
    import chat.agents as ag
    from chat.models import TimekeeperOutput
    calls = []

    def fake(sllm, prompt):
        calls.append(prompt)
        if len(calls) == 1:  # 3日目を欠落させる（今回のバグ）
            return TimekeeperOutput(schedule=["1日目", "08:00 出発", "2日目", "17:00 帰路へ"])
        return TimekeeperOutput(schedule=["1日目", "08:00 出発", "2日目", "10:00 観光",
                                          "3日目", "15:00 帰路へ"])

    monkeypatch.setattr(ag, "invoke_with_retry", fake)
    out = ag.timekeeper(_agent_state())
    assert len(calls) == 2                                  # 欠落を検出して1回作り直す
    assert any("3日目" in s for s in out["schedule"])       # 3日目が入った
    assert "重大な不備" in calls[1]                          # 名指しで再指示


def test_timekeeper_no_retry_when_complete(monkeypatch):
    import chat.agents as ag
    from chat.models import TimekeeperOutput
    calls = []

    def fake(sllm, prompt):
        calls.append(prompt)
        return TimekeeperOutput(schedule=["1日目", "08:00 出発", "2日目", "10:00 観光",
                                          "3日目", "15:00 帰路へ"])

    monkeypatch.setattr(ag, "invoke_with_retry", fake)
    ag.timekeeper(_agent_state())
    assert len(calls) == 1                                  # 正常時は作り直さない


def test_timekeeper_feedback_reaches_on_non_fixtime(monkeypatch):
    """fix_gourmet 等での再スケジュール時も審査の指摘が届き、問題施設の再挿入を禁止する。"""
    import chat.agents as ag
    from chat.models import TimekeeperOutput
    captured = []

    def fake(sllm, prompt):
        captured.append(prompt)
        return TimekeeperOutput(schedule=["1日目", "08:00 出発", "2日目", "10:00 観光",
                                          "3日目", "15:00 帰路へ"])

    monkeypatch.setattr(ag, "invoke_with_retry", fake)
    state = _agent_state(status="fix_gourmet", retry_count=1,
                         feedback="「カフェ・弘法の湯」は伊豆長岡にあり修善寺から徒歩15分は不可能です。")
    ag.timekeeper(state)
    assert "前回審査での指摘" in captured[0]
    assert "カフェ・弘法の湯" in captured[0]
    assert "とされた施設・場所はスケジュールに使わない" in captured[0]


# ----------------------------------------------------------------------
# 入力ガード（0人 / 0円 / 過去日付）と、今旅行中を弾かないこと
# ----------------------------------------------------------------------
def _conv_state(**over):
    from chat.chat import ConversationState
    base = dict(destination="静岡", travel_date=_fmt(TODAY + timedelta(days=10)),
                duration="1泊2日", themes=["温泉"], num_people=1, budget_limit=10000,
                departure_location="川崎", transport_mode="おまかせ", no_car=False,
                schedule_pref=None, special_requirements=[], is_complete=True,
                plan_change_request=None, edit_targets=None, next_question="")
    base.update(over)
    return ConversationState(**base)


def test_guard_rejects_zero_people(monkeypatch):
    import chat.chat as C
    monkeypatch.setattr(C, "invoke_with_retry", lambda llm, msgs: _conv_state(num_people=0))
    resp, plan = C.chat("x", messages_history=[], user_id=None)
    assert plan is None and "1名様" in resp


def test_guard_rejects_zero_budget(monkeypatch):
    import chat.chat as C
    monkeypatch.setattr(C, "invoke_with_retry", lambda llm, msgs: _conv_state(budget_limit=0))
    resp, plan = C.chat("x", messages_history=[], user_id=None)
    assert plan is None and "1円以上" in resp


def test_guard_rejects_fully_past_trip(monkeypatch):
    import chat.chat as C
    monkeypatch.setattr(C, "invoke_with_retry",
                        lambda llm, msgs: _conv_state(travel_date="2020年3月15日", duration="1泊2日"))
    resp, plan = C.chat("x", messages_history=[], user_id=None)
    assert plan is None and "過去の日付" in resp


def test_guard_allows_ongoing_trip(monkeypatch):
    """昨日始まって続いている旅（終了日が今日以降）は弾かない。"""
    import chat.chat as C
    started = _fmt(TODAY - timedelta(days=1))
    monkeypatch.setattr(C, "invoke_with_retry",
                        lambda llm, msgs: _conv_state(travel_date=started, duration="2泊3日"))
    monkeypatch.setattr(C, "generate_travel_plan",
                        lambda inputs: dict(inputs, status="approved", spots=["三保松原"],
                                            restaurants=[], accommodation=[], schedule=["1日目"],
                                            budget_estimate=["合計"], transport_cost=0,
                                            remaining_budget=10000, total_per_person=10000,
                                            feedback="ok"))
    resp, plan = C.chat("x", messages_history=[], user_id=None)
    assert plan is not None                                  # 生成に進む


# ----------------------------------------------------------------------
# 保存プラン修正: 基本条件の変更は全体作り直し / 不正値は無視
# ----------------------------------------------------------------------
def _saved_plan():
    return dict(destination="静岡", travel_date="2026年8月1日", duration="1泊2日",
                num_people=2, budget_limit=20000, departure_location="川崎", themes=["温泉"],
                spots=["a"], restaurants=["b"], accommodation=["c"], schedule=["1日目"],
                budget_estimate=["x"])


def test_edit_fundamental_change_forces_full_regen(monkeypatch):
    import chat.chat as C
    from chat.chat import _PlanEditIntent
    captured = {}
    monkeypatch.setattr(C, "generate_travel_plan",
                        lambda inputs: (captured.update(inputs), dict(inputs, status="approved"))[1])
    monkeypatch.setattr(C, "invoke_with_retry",
                        lambda llm, msgs: _PlanEditIntent(edit_targets=["accommodation"],
                                                          new_duration="10泊11日"))
    C.edit_saved_plan(_saved_plan(), "10泊にして")
    assert captured["duration"] == "10泊11日"     # 新しい期間が反映
    assert "edit_targets" not in captured          # 部分編集ではなく全体作り直し


def test_edit_ignores_invalid_people_and_budget(monkeypatch):
    import chat.chat as C
    from chat.chat import _PlanEditIntent
    captured = {}
    monkeypatch.setattr(C, "generate_travel_plan",
                        lambda inputs: (captured.update(inputs), dict(inputs, status="approved"))[1])
    monkeypatch.setattr(C, "invoke_with_retry",
                        lambda llm, msgs: _PlanEditIntent(edit_targets=["all"], new_num_people=0,
                                                          new_budget_limit=0))
    C.edit_saved_plan(_saved_plan(), "0人で予算0円にして")
    assert captured["num_people"] == 2             # 不正な人数は無視して元の値
    assert captured["budget_limit"] == 20000       # 不正な予算も無視
