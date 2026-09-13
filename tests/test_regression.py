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
    from services import weather
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
    from services import weather
    assert weather.parse_date("2026年7月3日") == date(2026, 7, 3)
    d = weather.parse_date("7/2")
    assert d is not None and (d.month, d.day) == (7, 2)
    assert weather.parse_date("未定") is None
    assert weather.parse_date("2泊3日") is None  # 期間表記を日付と誤認しない


def test_forecast_clamps_end_within_16_days(monkeypatch):
    from services import weather
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
    from services import weather
    from services import geocoding
    calls = []
    monkeypatch.setattr(geocoding, "geocode_center",
                        lambda d: (calls.append(d),
                                   {"lat": 35.0, "lng": 138.4, "radius_km": 80.0, "country_code": "jp"})[1])
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


def test_plan_card_has_no_blank_lines():
    """プランカードのHTMLに空行が無いこと。

    このHTMLは画面側で marked.parse() を通る。Markdown は空行を見つけると
    「HTMLはここまで」と判断してMarkdownの解釈に戻り、その次に来る
    4字下げの行をコードブロックにしてしまう。

    実際にそれで壊れていた。日帰り（宿泊が空）だと空のセクションが
    空白だけの行を残し、次の `    <details>` がコードブロックになって、
    画面に `<details>` という文字がそのまま出たうえ、スケジュールは
    折りたためず開きっぱなしになっていた。
    """
    from chat.formatter import _format_plan

    for name, state in [
        ("日帰り（宿泊が空）", _sample_plan_state()),
        ("観光が空", _sample_plan_state(spots=[])),
        ("総評なし", _sample_plan_state(status="")),
        ("予算不足", _sample_plan_state(status="budget_infeasible")),
    ]:
        html = _format_plan(state)
        blanks = [i for i, line in enumerate(html.splitlines(), 1) if not line.strip()]
        assert not blanks, f"{name}: {blanks}行目が空。marked がここでHTMLを打ち切る"


def _markdown_breaks_out(html: str):
    """marked が「HTMLはここまで」と判断して表示を壊す箇所を返す（無ければ None）。

    CommonMark のうち、ここで効くのは2つだけ:
      ・ブロック要素で始まる行からHTMLブロックが始まり、**空行で終わる**
      ・**4字下げの行はコードブロック**
    つまり「空行のすぐあとに4字下げの行」が来たら、そこがそのまま文字として出る。
    """
    ended = False
    for i, line in enumerate(html.splitlines(), 1):
        if not line.strip():
            ended = True
            continue
        if ended and line.startswith("    "):
            return f"{i}行目 {line.strip()[:40]!r} がコードブロックとして表示される"
        ended = False        # 字下げの浅い行からは、またHTMLとして読まれる
    return None


def test_plan_card_survives_markdown():
    """プランカードが marked を通っても崩れないこと。

    test_plan_card_has_no_blank_lines より一段ゆるいが、こちらは
    「画面でどう見えるか」に直結する。報告された症状はこれだった:
    `<details>` という文字が四角い枠で出て、スケジュールが折りたためない。
    """
    from chat.formatter import _format_plan

    for name, state in [
        ("日帰り（宿泊が空）", _sample_plan_state()),
        ("観光が空", _sample_plan_state(spots=[])),
        ("グルメが空", _sample_plan_state(restaurants=[])),
        ("スケジュールが空", _sample_plan_state(schedule=[])),
    ]:
        broken = _markdown_breaks_out(_format_plan(state))
        assert broken is None, f"{name}: {broken}"


def test_old_plans_in_history_are_repaired(monkeypatch):
    """直す前に保存されたプランも、開き直したときは崩れないこと。

    保存されているのは古いHTMLのままなので、formatter を直しただけでは
    履歴を開いた人には壊れて見える。返すときにも手当てする。
    """
    import json as _json

    import app as app_mod
    import db
    import views.planner as P

    broken = ('<div class="plan-card">\n  <div class="plan-accordion">\n'
              '    <details><summary>✨ 主要観光地</summary></details>\n'
              '    \n'                      # 宿泊が空 → 空白だけの行
              '    <details><summary>📅 スケジュール</summary></details>\n'
              '  </div>\n</div>')
    # ふつうの返事。段落を分ける空行は絶対に消してはいけない
    plain = 'どこに行きましょう？\n\n- 熱海\n- 箱根'

    monkeypatch.setattr(db, "get_chat_messages", lambda uid: [
        {"role": "user", "content": "千葉に日帰りで"},
        {"role": "ai", "content": broken},
        {"role": "ai", "content": plain},
    ])
    app_mod.app.config["TESTING"] = True
    with app_mod.app.test_client() as c:
        with c.session_transaction() as sess:
            sess["user_id"] = "u-1"
            sess["user_email"] = "u@example.com"
        got = _json.loads(c.get("/get_messages").data)

    assert _markdown_breaks_out(got[1]["content"]) is None, "古いプランが直っていない"
    assert got[2]["content"] == plain, "ふつうの返事の空行まで消している（段落が潰れる）"
    assert P._repair_plan_html(plain) == plain


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
# テンプレートの url_for（存在しない endpoint はその画面を丸ごと 500 にする）
# ----------------------------------------------------------------------
def test_every_url_for_in_templates_points_to_a_real_endpoint():
    """テンプレートが url_for で指す endpoint が、すべて登録済みであること。

    Jinja のコンパイル検査では見つからない（url_for は描画時に解決される）。
    shared/plan.html が Blueprint 名を 'share.' と書いていて、公開リンクで
    プランを開くと BuildError で 500 になっていた。ブループリントの登録名は
    'sharing' なので、この一か所だけが食い違っていた。
    """
    import re
    from pathlib import Path

    import app as app_mod

    endpoints = {r.endpoint for r in app_mod.app.url_map.iter_rules()}
    # template_folder は相対パス。カレントディレクトリ基準で探すと1件も見つからず、
    # 何も検査しないまま通ってしまう（実際それで壊れた状態を素通りした）
    templates = list((Path(app_mod.app.root_path) / app_mod.app.template_folder).rglob("*.html"))
    assert len(templates) >= 10, "テンプレートが見つかっていない（探し方が壊れている）"

    found, bad = 0, []
    for f in templates:
        for m in re.finditer(r"url_for\(\s*['\"]([\w.]+)['\"]", f.read_text()):
            found += 1
            if m.group(1) not in endpoints:
                bad.append(f"{f.name}: {m.group(1)}")
    assert found >= 20, "url_for を1つも拾えていない（正規表現が壊れている）"
    assert not bad, f"存在しない endpoint を参照している: {bad}"


def test_public_trip_link_wraps_every_photo(monkeypatch):
    """公開リンクで開いた旅（閲覧のみ）でも、写真が1枚ずつポラロイド枠に入っていること。

    閲覧のみのときだけ素の <img> を並べていたため、写真用のCSSが当たらず
    原寸のまま横に並び、カードからはみ出していた（スマホでは横スクロール）。
    共有リンクで人に見せる一番ふつうの場面で崩れていたので、ここで押さえる。
    """
    import re

    import app as app_mod
    import db_reflection as repo
    import views.sharing as S
    from services import storage

    trip = {"id": 1, "user_id": "owner", "title": "沼津", "start_date": "2025-06-12",
            "end_date": "2025-06-13", "is_favorite": 0, "best_shots": "[]"}
    photos = [{"id": i, "trip_id": 1, "storage_path": f"p/{i}.jpg", "taken_at": None,
               "lat": None, "lng": None} for i in range(1, 4)]
    monkeypatch.setattr(S.sharing, "get_link_by_token",
                        lambda t: {"resource_type": "trip", "resource_id": 1, "permission": "view"})
    monkeypatch.setattr(repo, "get_trip_by_id", lambda tid, viewer_id=None: dict(trip))
    monkeypatch.setattr(repo, "get_trip", lambda tid, uid: None)
    monkeypatch.setattr(repo, "get_photos", lambda tid: [dict(p) for p in photos])
    monkeypatch.setattr(repo, "get_stickers", lambda tid: [])
    monkeypatch.setattr(storage, "get_urls", lambda paths: {p: f"/u/{p}" for p in paths})
    monkeypatch.setattr(storage, "get_thumb_urls", lambda paths: {p: f"/t/{p}" for p in paths})
    app_mod.app.config["TESTING"] = True

    with app_mod.app.test_client() as c:
        res = c.get("/s/abc")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    grid = re.search(r'<div class="photo-grid"[^>]*>(.*?)</div>\s*<div class="photo-count"', html, re.S).group(1)
    imgs = len(re.findall(r"<img\b", grid))
    figs = len(re.findall(r'<figure class="photo"', grid))
    assert imgs == 3, "写真が3枚出ていない"
    assert figs == imgs, f"枠に入っていない写真がある（img {imgs} / figure {figs}）"
    assert "photo-del" not in grid, "閲覧のみなのに削除ボタンが出ている"


def test_public_plan_link_renders(monkeypatch):
    """公開リンク（/s/<token>）でプランを開けること。ここが元の不具合。"""
    import app as app_mod
    import db
    from services import geocoding
    from services import weather
    import views.sharing as S

    plan = _sample_plan_state() | {"id": 7, "spot_coords": []}
    monkeypatch.setattr(S.sharing, "get_link_by_token",
                        lambda t: {"resource_type": "plan", "resource_id": 7, "permission": "view"})
    monkeypatch.setattr(db, "get_travel_plan_by_id", lambda i: dict(plan))
    monkeypatch.setattr(geocoding, "ensure_plan_coords", lambda p: None)
    monkeypatch.setattr(weather, "plan_forecast", lambda p: [])
    app_mod.app.config["TESTING"] = True

    with app_mod.app.test_client() as c:
        res = c.get("/s/abc")
    assert res.status_code == 200, res.status_code
    html = res.get_data(as_text=True)
    assert "/shared/plan/7/ics?token=abc" in html, "カレンダーのリンクが公開トークン付きで出ること"


# ----------------------------------------------------------------------
# ICS カレンダー書き出し（年なし日付 / 日別イベント / TZ / 折りたたみ）
# ----------------------------------------------------------------------
def test_ics_advanced(monkeypatch):
    """年なし日付「7/10」が、その年の7/10になること。

    parse_date は「60日以上前なら翌年」と推定するので、実行日が9月以降だと
    翌年の7/10になり、TODAY.year を前提にしたこのテストは9月〜12月に落ちる
    （実際に落ちた）。判断に使う「今日」を7/1に固定して、年をまたがない
    条件で確かめる。
    """
    from services import weather
    from views.planner import _build_plan_ics

    class _July1(date):
        @classmethod
        def today(cls):
            return cls(2026, 7, 1)

    monkeypatch.setattr(weather, "date", _July1)
    plan = {
        "id": 7, "destination": "静岡", "travel_date": "7/10", "duration": "1泊2日",
        "spots": ["三保松原"], "restaurants": [], "accommodation": ["ホテルA"],
        "schedule": ["1日目", "08:00 川崎を出発（新幹線）", "12:00 昼食",
                     "2日目", "10:00 観光", "17:00 帰路へ"],
        "budget_estimate": ["合計 3万円"],
    }
    ics = _build_plan_ics(plan)
    # 年なし日付でも「今日」に化けず7/10になる
    assert "DTSTART;VALUE=DATE:20260710" in ics
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


# ----------------------------------------------------------------------
# 期間パース（0泊2日=夜行 / 変則表記）と、日数ベースの行程・食事・費用
# ----------------------------------------------------------------------
def test_parse_duration_variants():
    """「N泊M日」以外の表記でも泊数・日数を正しく推定する。"""
    from services import weather as wx
    assert wx.parse_duration("2泊3日") == (2, 3)
    assert wx.parse_duration("1泊") == (1, 2)
    assert wx.parse_duration("0泊2日") == (0, 2)      # 夜行: 宿なし・2日行程
    assert wx.parse_duration("日帰り") == (0, 1)
    assert wx.parse_duration("3日間") == (2, 3)        # 「N日間」→ N-1泊N日相当
    assert wx.parse_duration("2日") == (1, 2)
    assert wx.parse_duration("週末") == (1, 2)
    assert wx.parse_duration("ゆっくりめで") == (1, 2)  # 不明時は1泊2日に既定
    # 日付表記を日数と誤読しない（「12日」を12日間としない）
    assert wx.parse_duration("7月12日〜13日の1泊2日") == (1, 2)


def test_overnight_trip_is_no_lodging_but_two_days(monkeypatch):
    """0泊2日: 宿はスキップしつつ、スケジュールは2日分・チェックイン指示なし。"""
    import chat.agents as ag
    from chat.models import TimekeeperOutput

    assert ag.is_day_trip("0泊2日") is True   # 宿泊なし → 宿の選定はスキップ対象
    assert ag.accommodation_candidates(_agent_state(duration="0泊2日")) == {"accommodation_candidates": []}

    captured = []
    def fake(sllm, prompt):
        captured.append(prompt)
        return TimekeeperOutput(schedule=["1日目", "23:00 夜行バス乗車", "2日目", "06:00 到着", "18:00 帰路"])
    monkeypatch.setattr(ag, "invoke_with_retry", fake)
    ag.timekeeper(_agent_state(duration="0泊2日", accommodation=[]))
    p = captured[0]
    assert "0泊2日" in p and "「2日目」" in p          # 2日分のブロックを要求
    assert "チェックイン（目安15:00" not in p           # 宿泊用の指示は入れない
    assert "宿泊なし" in p and "夜行バス" in p           # 宿泊なし行程の指示に切り替わる


def test_overnight_trip_meals_and_costs():
    """0泊2日: 食事は昼2+夕1、費用テンプレに宿泊費の行が無い。"""
    import chat.agents as ag
    sections = ag._build_day_sections("0泊2日")
    assert "2日目" in sections and "宿泊費" not in sections
    sections_stay = ag._build_day_sections("2泊3日")
    assert "宿泊費" in sections_stay                    # 従来挙動は不変


# ----------------------------------------------------------------------
# ご希望（交通手段・運転の可否・時間）が、保存と修正の往復で消えないこと
# ----------------------------------------------------------------------
def test_saved_plan_edit_keeps_transport_preferences(monkeypatch):
    """しおりからのチャット修正で「運転しない」等の前提が失われないこと。

    以前は edit_saved_plan が transport_mode="おまかせ" / no_car=False を
    決め打ちしており、修正のたびに車前提の行程へ戻る可能性があった。
    """
    import chat.chat as C
    from chat.chat import _PlanEditIntent
    captured = {}
    monkeypatch.setattr(C, "generate_travel_plan",
                        lambda inputs: (captured.update(inputs), dict(inputs, status="approved"))[1])
    monkeypatch.setattr(C, "invoke_with_retry",
                        lambda llm, msgs: _PlanEditIntent(edit_targets=["gourmet"]))
    plan = dict(_saved_plan(), transport_mode="新幹線", no_car=1,
                schedule_pref="夕方までに帰りたい")
    C.edit_saved_plan(plan, "ご飯を変えて")
    assert captured["transport_mode"] == "新幹線"
    assert captured["no_car"] is True
    assert captured["schedule_pref"] == "夕方までに帰りたい"


def test_plan_payload_carries_transport_preferences():
    """チャット内の部分編集も plan_json 経由なので、控えに希望が載っていること。"""
    from chat.formatter import plan_payload
    payload = plan_payload({"destination": "静岡", "transport_mode": "新幹線",
                            "no_car": True, "schedule_pref": "朝はゆっくり"})
    assert payload["transport_mode"] == "新幹線"
    assert payload["no_car"] is True
    assert payload["schedule_pref"] == "朝はゆっくり"


def test_apply_saved_plan_roundtrip_keeps_preferences():
    """修正案プレビューの辞書にも希望が入っていること。

    /apply_saved_plan はクライアントが返してきたこの辞書をそのまま UPDATE に流す。
    ここから漏れると、確定を押した瞬間に保存済みの希望が既定値へ戻る。
    """
    from views.planner import _plan_to_view_dict
    view = _plan_to_view_dict({"destination": "静岡", "transport_mode": "高速バス",
                               "no_car": True, "schedule_pref": "早めに帰りたい"}, 1, None)
    assert view["transport_mode"] == "高速バス"
    assert view["no_car"] is True
    assert view["schedule_pref"] == "早めに帰りたい"


def test_db_write_and_read_cover_the_same_plan_columns():
    """travel_plans の INSERT・UPDATE・SELECT が同じ列集合を扱っていること。

    列を1か所にだけ足すと、書けるのに読めない（またはその逆）が起きる。
    実際そうやって transport_mode 等が抜け落ちていた。
    """
    import re
    from pathlib import Path
    src = Path(__file__).resolve().parent.parent / "src" / "db.py"
    text = src.read_text(encoding="utf-8")

    insert = re.search(r"INSERT INTO travel_plans \((.*?)\) VALUES", text, re.S).group(1)
    insert_cols = {c.strip() for c in insert.replace("\n", " ").split(",") if c.strip()}
    # UPDATE は rating 用など複数あるので、プラン本体を書き換えるものを選ぶ
    updates = [m.group(1) for m in
               re.finditer(r"UPDATE travel_plans SET(.*?)WHERE id = :id", text, re.S)]
    update = next(u for u in updates if "destination =" in u)
    update_cols = {m.group(1) for m in re.finditer(r"(\w+)\s*=\s*:", update)}
    select = re.search(r"_PLAN_SELECT_COLS = \((.*?)\n\)", text, re.S).group(1)
    select_cols = {c.strip() for c in select.replace('"', " ").replace("\n", " ").split(",") if c.strip()}

    assert len(insert_cols) >= 20 and len(update_cols) >= 20 and len(select_cols) >= 20
    for col in ("transport_mode", "no_car", "schedule_pref"):
        assert col in insert_cols, f"INSERT に {col} が無い"
        assert col in update_cols, f"UPDATE に {col} が無い"
        assert col in select_cols, f"SELECT に {col} が無い"
    # 書き込める列はすべて読み戻せること（geo_done は書き込み時に固定値なので除く）
    assert (insert_cols | update_cols) - {"geo_done"} <= select_cols | {"google_user_id", "user_email"}


# ----------------------------------------------------------------------
# 審査 → ルーティングの取りこぼし
# ----------------------------------------------------------------------
def test_every_balancer_status_has_a_route():
    """バランサーが返しうる status が、すべて実在するノードへ振り分けられること。

    逆に、どこからも生成されない status の分岐を残さないこと（読む人を惑わせる）。
    """
    from chat.models import BalancerOutput
    from chat.agents import route_after_balancer
    from chat.graph import workflow
    import typing

    statuses = typing.get_args(BalancerOutput.model_fields["status"].annotation)
    assert len(statuses) == 7
    destinations = set(workflow.nodes) | {"end"}
    for status in statuses:
        route = route_after_balancer({"status": status, "prev_status": "", "retry_count": 0})
        assert route in destinations, f"{status} の行き先 {route} がノードに無い"


def test_route_after_balancer_has_no_unreachable_branch():
    """ルーティングが参照する status 名が、実際に代入されうるものだけであること。"""
    import inspect
    from chat.agents import route_after_balancer, balancer
    from chat.models import BalancerOutput, TravelPlanState
    import typing

    known = set(typing.get_args(BalancerOutput.model_fields["status"].annotation))
    known |= set(typing.get_args(TravelPlanState.__annotations__["status"]))
    source = inspect.getsource(route_after_balancer) + inspect.getsource(balancer)
    for name in ("fallback_sightseeing", "fallback_accommodation", "fallback_gourmet",
                 "candidates_ready", "accommodation_candidates_ready"):
        assert name not in known, f"{name} はどこからも代入されない"
        assert f'"{name}"' not in source, f"{name} の分岐が残っている"


# ----------------------------------------------------------------------
# 「運転しない」がどこかのエージェントで抜け落ちないこと
# ----------------------------------------------------------------------
def test_is_car_covers_spelling_variants():
    """車を指す言い回しの揺れを拾い、電車・自転車を巻き込まないこと。

    以前は ("車","レンタカー","自家用車","マイカー") の完全一致だけで見ており、
    「自動車」「レンタカー（現地で借りる）」がすり抜けて、運転しない人に
    「この手段で固定」と指示していた。
    """
    from chat.agents import _is_car
    for mode in ("車", "レンタカー", "自家用車", "マイカー", "自動車",
                 "レンタカー（現地で借りる）", "car", "Car", "ドライブ", "車（レンタカー）"):
        assert _is_car(mode), mode
    for mode in ("新幹線", "電車", "飛行機", "高速バス", "おまかせ", "特急",
                 "在来線", "自転車", "船", "電車＋バス", "夜行バス", "列車", ""):
        assert not _is_car(mode), mode


def test_no_car_reaches_every_prompt_building_agent():
    """プロンプトを組み立てるエージェントは全員 no_car を見ていること。

    宿・飲食店・観光のどこか1つでも見落とすと、運転しない人に
    車でしか行けない場所が混ざる。実際に宿とグルメ候補で抜けていた。
    """
    import inspect
    import chat.agents as A

    # 費用マネージャーは決まったプランに値段を付けるだけで、行き先も経路も選ばない
    prices_only = {"cost_manager"}
    builders = [name for name, fn in vars(A).items()
                if inspect.isfunction(fn) and fn.__module__ == A.__name__
                and not name.startswith("_") and "prompt" in inspect.getsource(fn)
                and name not in prices_only]
    assert len(builders) >= 8, builders
    missing = [n for n in builders if "no_car" not in inspect.getsource(getattr(A, n))]
    assert not missing, f"no_car を見ていないエージェント: {missing}"


# ----------------------------------------------------------------------
# 会話は毎ターン作り直される。任意項目が黙って消えないこと
# ----------------------------------------------------------------------
def _complete_state(**over):
    from chat.chat import ConversationState
    base = dict(destination="静岡", travel_date="2099年8月1日", duration="1泊2日",
                themes=["温泉"], num_people=2, budget_limit=30000,
                departure_location="川崎", is_complete=True,
                plan_change_request="宿を変えて", edit_targets=["accommodation"])
    base.update(over)
    return ConversationState(**base)


def test_optional_preferences_survive_a_turn_that_forgets_them(monkeypatch):
    """抽出が任意項目を落としても、前回プランに控えた値で補うこと。

    「免許がない」と伝えた数ターン後に「宿を変えて」と言っただけで、
    軽量モデルが no_car を返さなくなると配慮ごと消えていた。
    """
    import chat.chat as C
    captured = {}
    monkeypatch.setattr(C, "invoke_with_retry", lambda llm, msgs: _complete_state())
    monkeypatch.setattr(C, "_build_user_preferences", lambda uid: "")
    monkeypatch.setattr(C, "generate_travel_plan",
                        lambda inputs: (captured.update(inputs), dict(inputs, status="approved"))[1])
    import db
    monkeypatch.setattr(db, "get_last_plan", lambda uid: {
        "destination": "静岡", "duration": "1泊2日", "travel_date": "2099年8月1日",
        "num_people": 2, "budget_limit": 30000, "departure_location": "川崎",
        "transport_mode": "新幹線", "no_car": True, "schedule_pref": "夕方までに帰りたい",
        "special_requirements": ["魚介類アレルギー"],
        "spots": ["a"], "restaurants": ["b"], "accommodation": ["c"],
        "schedule": ["1日目"], "budget_estimate": ["x"],
        "transport_cost": 5000, "remaining_budget": 25000,
    })
    C.chat("宿を変えて", messages_history=[], user_id="u1")
    assert captured["no_car"] is True
    assert captured["transport_mode"] == "新幹線"
    assert captured["schedule_pref"] == "夕方までに帰りたい"
    assert captured["special_requirements"] == ["魚介類アレルギー"]


def test_explicit_change_beats_the_carried_over_value(monkeypatch):
    """今回はっきり答えた値は、前回の控えより優先されること（引き継ぎで上書きしない）。"""
    import chat.chat as C
    captured = {}
    monkeypatch.setattr(C, "invoke_with_retry",
                        lambda llm, msgs: _complete_state(no_car=False, transport_mode="車",
                                                          special_requirements=[]))
    monkeypatch.setattr(C, "_build_user_preferences", lambda uid: "")
    monkeypatch.setattr(C, "generate_travel_plan",
                        lambda inputs: (captured.update(inputs), dict(inputs, status="approved"))[1])
    import db
    monkeypatch.setattr(db, "get_last_plan", lambda uid: {
        "destination": "静岡", "duration": "1泊2日", "travel_date": "2099年8月1日",
        "num_people": 2, "budget_limit": 30000, "departure_location": "川崎",
        "transport_mode": "新幹線", "no_car": True, "special_requirements": ["魚介類アレルギー"],
    })
    C.chat("やっぱり車で行く", messages_history=[], user_id="u1")
    assert captured["no_car"] is False              # 明示的に「運転する」に変えた
    assert captured["transport_mode"] == "車"
    assert captured["special_requirements"] == []   # 「無い」と答えたなら空のまま


def test_transport_agent_neutralises_a_car_mode_for_non_drivers(monkeypatch):
    """運転しない人に「自動車で固定」と指示しないこと。

    交通手段の文字列は軽量モデルが自由に書くので、表記が少しずれただけで
    除外をすり抜けてはいけない。
    """
    import chat.agents as A
    seen = {}
    monkeypatch.setattr(A, "invoke_with_retry",
                        lambda llm, prompt: (seen.update(p=prompt),
                                             type("R", (), {"transport_cost": 5000})())[1])
    monkeypatch.setattr(A, "llm", type("L", (), {"with_structured_output": lambda s, m: None})())

    base = dict(destination="静岡", departure_location="川崎", num_people=2,
                travel_date="2099年8月1日", budget_limit=30000, no_car=True)
    for mode in ("車", "自動車", "レンタカー（現地で借りる）", "マイカー"):
        A.transport_agent(dict(base, transport_mode=mode))
        assert "で固定すること" not in seen["p"], mode
        assert "運転免許がない" in seen["p"], mode

    # 運転できる人の指定は、これまでどおりその手段で固定する
    A.transport_agent(dict(base, no_car=False, transport_mode="レンタカー"))
    assert "「レンタカー」で固定すること" in seen["p"]


# ----------------------------------------------------------------------
# グルメの候補集めに宿を渡す（「夕食は宿の徒歩圏で」を満たせるようにする）
# ----------------------------------------------------------------------
def _capture_agent(monkeypatch):
    """エージェントに渡るプロンプトと検索クエリを覗くための差し替え。"""
    import chat.agents as A
    seen = {}
    monkeypatch.setattr(A, "invoke_with_retry", lambda llm, prompt: (
        seen.update(prompt=prompt),
        type("R", (), {"restaurants": ["x", "y", "z", "w"],
                       "accommodation": ["h1", "h2", "h3"],
                       "candidates": ["s1", "s2", "s3", "s4", "s5"]})())[1])
    monkeypatch.setattr(A, "llm", type("L", (), {"with_structured_output": lambda s, m: None})())
    monkeypatch.setattr(A, "build_search_context",
                        lambda qs: (seen.update(queries=qs), "")[1])
    monkeypatch.setattr(A, "_filter_real_places", lambda names, dest, min_keep, **kw: names)
    return A, seen


_AGENT_BASE = dict(destination="熱海", travel_date="2099年8月1日", duration="1泊2日",
                   themes=["温泉"], num_people=2, special_requirements=[],
                   remaining_budget=25000, budget_limit=30000,
                   spots=["起雲閣", "来宮神社"])


def test_gourmet_candidates_know_the_chosen_hotel(monkeypatch):
    """宿はグルメより先に決まるので、候補集めの段階で渡すこと。

    渡さないと、宿の徒歩圏の店が候補に1軒も入らないまま
    「夕食は宿の徒歩圏で」とタイムキーパーに要求することになる。
    """
    A, seen = _capture_agent(monkeypatch)
    A.gourmet_candidates(dict(_AGENT_BASE, accommodation=["ホテル熱海"]))
    assert "選定済みの宿泊施設: ホテル熱海" in seen["prompt"]
    assert any("ホテル熱海" in q for q in seen["queries"]), seen["queries"]
    assert "徒歩圏" in seen["prompt"]


def test_gourmet_candidates_skip_the_hotel_for_a_day_trip(monkeypatch):
    """日帰りでは宿の検索も指示も足さないこと（存在しない宿を探しに行かない）。"""
    A, seen = _capture_agent(monkeypatch)
    A.gourmet_candidates(dict(_AGENT_BASE, duration="日帰り", accommodation=[]))
    assert "宿泊施設: なし（宿泊しない行程）" in seen["prompt"]
    assert not any("徒歩圏 夕食" in q for q in seen["queries"]), seen["queries"]


def test_accommodation_prompts_omit_the_always_empty_restaurant_line(monkeypatch):
    """飲食店が決まる前の宿のプロンプトに、空の「飲食店:」行を出さないこと。

    グラフ順が 宿 → グルメ なので、初回は必ず空になる行だった。
    差し戻しや部分編集で埋まっているときは、これまでどおり渡す。
    """
    A, seen = _capture_agent(monkeypatch)
    for agent, extra in ((A.accommodation_candidates, {}),
                         (A.accommodation_agent, {"accommodation_candidates": ["h1"],
                                                  "retry_count": 0})):
        agent(dict(_AGENT_BASE, restaurants=[], **extra))
        assert "\n飲食店: " not in seen["prompt"], agent.__name__
        agent(dict(_AGENT_BASE, restaurants=["磯丸"], **extra))
        assert "飲食店: 磯丸" in seen["prompt"], agent.__name__


# ----------------------------------------------------------------------
# 海外の行き先: 生成側の指示が切り替わること
# ----------------------------------------------------------------------
def test_directive_adds_yen_conversion_and_local_names_overseas():
    from chat.agents import _directive
    home = _directive({"is_overseas": False})
    abroad = _directive({"is_overseas": True, "dest_country": "fr"})
    assert "日本円に換算" not in home and "現地語" not in home
    assert "国コード FR" in abroad and "日本円に換算" in abroad and "Tour Eiffel" in abroad
    assert "すべて日本語で出力" in abroad     # 出力言語は変えない


def test_overseas_flags_reach_transport_timekeeper_and_cost(monkeypatch):
    import chat.agents as A
    seen = {}
    fake = type("R", (), {"transport_cost": 80000, "schedule": ["1日目 …"],
                          "budget_estimate": ["x"], "total_per_person": 1})()
    monkeypatch.setattr(A, "invoke_with_retry", lambda llm, prompt: (seen.update(p=prompt), fake)[1])
    stub = type("L", (), {"with_structured_output": lambda s, m: None})()
    monkeypatch.setattr(A, "llm", stub)
    monkeypatch.setattr(A, "llm_strong", stub)
    base = dict(destination="パリ", departure_location="東京", num_people=2, travel_date="2099年8月1日",
                duration="3泊4日", budget_limit=300000, themes=["美術館"], special_requirements=[],
                spots=["ルーヴル美術館（Musée du Louvre）"], restaurants=["a"], accommodation=["h"],
                transport_cost=120000, remaining_budget=180000, schedule=["1日目"],
                is_overseas=True, dest_country="fr", no_car=False, transport_mode="おまかせ")

    A.transport_agent(dict(base))
    assert "航空便を前提" in seen["p"] and "燃油サーチャージ" in seen["p"]
    A.timekeeper(dict(base))
    assert "現地時刻" in seen["p"] and "入国審査" in seen["p"] and "Tour Eiffel" in seen["p"]
    A.cost_manager(dict(base))
    assert "海外旅行保険" in seen["p"] and "換算レート" in seen["p"]

    # 国内では出ない
    for agent in (A.transport_agent, A.timekeeper, A.cost_manager):
        agent(dict(base, is_overseas=False, dest_country="jp", destination="金沢"))
        assert "航空便を前提" not in seen["p"] and "現地時刻" not in seen["p"] \
            and "海外旅行保険" not in seen["p"], agent.__name__


def test_generate_travel_plan_detects_an_overseas_destination(monkeypatch):
    """生成の前に行き先の国を引き、状態に is_overseas / dest_country を入れること。"""
    import chat.graph as G
    captured = {}
    monkeypatch.setattr(G, "_lookup_destination",
                        lambda d: {"lat": 48.86, "lng": 2.35, "radius_km": 80.0, "country_code": "fr"})
    monkeypatch.setattr(G, "transport_agent", lambda i: {"transport_cost": 1, "remaining_budget": 9})
    monkeypatch.setattr(G, "sightseeing_candidates", lambda i: {"spot_candidates": []})
    monkeypatch.setattr(G.graph, "invoke", lambda inputs, config: (captured.update(inputs), inputs)[1])
    G.generate_travel_plan({"destination": "パリ", "travel_date": "2099年8月1日", "duration": "3泊4日",
                            "themes": ["美術館"], "num_people": 2, "budget_limit": 300000,
                            "departure_location": "東京", "special_requirements": []})
    assert captured["is_overseas"] is True and captured["dest_country"] == "fr"

    # 引けなければ国内扱い（従来どおり）
    monkeypatch.setattr(G, "_lookup_destination", lambda d: None)
    G.generate_travel_plan({"destination": "どこか", "travel_date": "2099年8月1日", "duration": "日帰り",
                            "themes": ["x"], "num_people": 1, "budget_limit": 1, "departure_location": "y",
                            "special_requirements": []})
    assert captured["is_overseas"] is False and captured["dest_country"] == ""


def test_generation_hint_reuses_a_given_center(monkeypatch):
    """生成側が先に引いた座標を渡せば、天気のために二度引かないこと。"""
    from services import weather
    from datetime import date, timedelta
    calls = []
    monkeypatch.setattr(weather, "dest_center", lambda d: (calls.append(d), None)[1])
    monkeypatch.setattr(weather, "forecast", lambda lat, lng, s, e: [
        {"date": "x", "label": "晴れ", "tmin": 20, "tmax": 30, "code": 0}])
    soon = date.today() + timedelta(days=2)
    hint = weather.generation_hint("パリ", f"{soon.year}年{soon.month}月{soon.day}日", "日帰り",
                                   center={"lat": 48.86, "lng": 2.35})
    assert "天気予報" in hint and calls == []


def test_packing_list_adds_overseas_essentials(monkeypatch):
    from services import packing, weather
    seen = {}
    monkeypatch.setattr(packing, "invoke_with_retry",
                        lambda llm, prompt: (seen.update(p=prompt), type("R", (), {"items": ["a"]})())[1])
    monkeypatch.setattr(packing, "llm", type("L", (), {"with_structured_output": lambda s, m: None})())
    monkeypatch.setattr(weather, "generation_hint", lambda *a, **k: "")
    monkeypatch.setattr(weather, "dest_center", lambda d: {"lat": 0, "lng": 0, "country_code": "fr"})
    packing.generate_packing_list({"destination": "パリ", "duration": "3泊4日"})
    assert "パスポート" in seen["p"] and "変換プラグ" in seen["p"]
    monkeypatch.setattr(weather, "dest_center", lambda d: {"lat": 0, "lng": 0, "country_code": "jp"})
    packing.generate_packing_list({"destination": "金沢", "duration": "1泊2日"})
    assert "パスポート" not in seen["p"]


def test_plan_geo_returns_the_center_only_when_there_are_no_pins(monkeypatch, client=None):
    from app import app
    import views.planner as P
    import db
    from services import weather, geocoding
    monkeypatch.setattr(geocoding, "ensure_plan_coords", lambda plan: plan)
    monkeypatch.setattr(weather, "dest_center", lambda d: {"lat": 48.86, "lng": 2.35})
    monkeypatch.setattr(P, "_geo_rate_limited", lambda uid: False)
    plans = {1: {"id": 1, "google_user_id": "u1", "destination": "パリ", "geo_done": 1,
                 "spot_coords": [], "restaurant_coords": [], "accommodation_coords": []},
             2: {"id": 2, "google_user_id": "u1", "destination": "パリ", "geo_done": 1,
                 "spot_coords": [{"name": "x", "lat": 1, "lng": 2}],
                 "restaurant_coords": [], "accommodation_coords": []}}
    monkeypatch.setattr(db, "get_travel_plan_by_id", lambda pid: plans.get(pid))
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess["user_id"] = "u1"; sess["user_email"] = "u@example.com"
        empty = c.get("/api/plan_geo/1").get_json()
        pinned = c.get("/api/plan_geo/2").get_json()
    assert empty["center"] == {"lat": 48.86, "lng": 2.35}   # ピンが無い → 行き先の街を出す
    assert "center" not in pinned                            # ピンがあれば fitBounds に任せる


def test_dest_center_falls_back_when_nominatim_misses(monkeypatch):
    """OSMに載っていない地名でも、天気の座標を諦めないこと。

    geocode_center は Nominatim しか見ない。以前ここは geocode_one を使っており、
    Google Places・表記ゆらぎ・国土地理院まで試していた。切り替えたときに
    その到達範囲を落としてしまうと、一部の行き先で天気が出なくなる。
    """
    from services import weather, geocoding
    weather._DEST_CACHE.clear()
    monkeypatch.setattr(geocoding, "geocode_center", lambda q: None)
    monkeypatch.setattr(geocoding, "geocode_one", lambda q, **kw: {"lat": 36.0, "lng": 137.0})
    loc = weather.dest_center("OSMに無い温泉郷")
    assert loc["lat"] == 36.0 and loc["country_code"] == "jp"
    assert loc["radius_km"] == geocoding._MAX_DIST_KM

    # 中心が取れるときは、そちらを使って国コードも返す（フォールバックは呼ばない）
    weather._DEST_CACHE.clear()
    monkeypatch.setattr(geocoding, "geocode_center",
                        lambda q: {"lat": 48.86, "lng": 2.35, "radius_km": 80.0, "country_code": "fr"})
    monkeypatch.setattr(geocoding, "geocode_one",
                        lambda q, **kw: pytest.fail("中心が取れているのにフォールバックした"))
    assert weather.dest_center("パリ")["country_code"] == "fr"


# ----------------------------------------------------------------------
# 同じ指摘が続いたとき、候補プールごと入れ替えられること
# ----------------------------------------------------------------------
def test_repeated_rejection_falls_back_to_refetching_candidates():
    """2回続けて同じ指摘なら、選び直しではなく候補集めまで戻ること。

    以前は fix_sightseeing がいつも選定ノードに戻っており、観光の候補プールは
    グラフの外で一度作られたきりだった。プールの中に正解が無い場合、
    同じ候補から選び直すだけで差し戻し上限まで回りきっていた。
    """
    from chat.agents import route_after_balancer, _REFRESH_POOL

    def route(status, prev=""):
        return route_after_balancer({"status": status, "prev_status": prev, "retry_count": 1})

    # 1回目は安い選び直し（検索もLLMの候補集めも走らせない）
    assert route("fix_sightseeing") == "sightseeing"
    assert route("fix_accommodation") == "accommodation"
    assert route("fix_time") == "timekeeper"
    # 2回目は候補集めまで戻る
    assert route("fix_sightseeing", "fix_sightseeing") == "sightseeing_candidates"
    assert route("fix_accommodation", "fix_accommodation") == "accommodation_candidates"
    assert route("fix_budget", "fix_budget") == "accommodation_candidates"
    assert route("fix_time", "fix_time") == "sightseeing_candidates"
    assert route("fix_gourmet", "fix_gourmet") == "gourmet_candidates"
    # 差し戻し種別を増やしたら戻り先も決めること（取りこぼしを防ぐ）
    assert set(_REFRESH_POOL) == {"fix_sightseeing", "fix_gourmet", "fix_accommodation",
                                  "fix_budget", "fix_time"}


def test_every_refresh_target_is_wired_back_into_the_graph():
    """候補集めに戻ったあと、選定を通って審査まで戻ってこられること。

    ノードとして登録され、分岐の行き先にも入っていて、かつ出口の辺があること。
    どれか1つでも欠けると、戻った先で行き止まりになる。
    """
    from chat.agents import _REFRESH_POOL
    from chat.graph import workflow

    branch = next(iter(workflow.branches["balancer"].values()))
    for target in set(_REFRESH_POOL.values()):
        assert target in workflow.nodes, f"{target} がノードに無い"
        assert target in (branch.ends or {}), f"{target} が分岐の行き先に無い"
        assert any(src == target for src, _ in workflow.edges), f"{target} から先へ進む辺が無い"
    # 観光の候補集めは選定へ戻る（初回は並列先行実行なので START からは繋がない）
    assert ("sightseeing_candidates", "sightseeing") in workflow.edges
    assert ("__start__", "sightseeing_candidates") not in workflow.edges


def test_candidate_agents_get_the_review_feedback(monkeypatch):
    """候補を集め直すとき、審査の指摘と前回の顔ぶれを渡すこと。

    候補エージェントは temperature=0。指摘を渡さなければ、検索とLLMを使って
    まったく同じ候補を作り直すだけになる（実際そうなっていた）。
    """
    A, seen = _capture_agent(monkeypatch)
    base = dict(_AGENT_BASE, destination="金沢", spots=["兼六園"],
                restaurants=["いきいき亭"], accommodation=["町家宿"])
    for agent, rejected in ((A.sightseeing_candidates, "兼六園"),
                            (A.accommodation_candidates, "町家宿"),
                            (A.gourmet_candidates, "いきいき亭")):
        agent(dict(base, status="fix_time", feedback="移動が長すぎます"))
        assert "移動が長すぎます" in seen["prompt"], agent.__name__
        assert rejected in seen["prompt"], agent.__name__
        # 初回生成では付けない（プロンプトを無駄に長くしない）
        agent(dict(base, status="approved", feedback=""))
        assert "前回の審査での指摘" not in seen["prompt"], agent.__name__


def test_refresh_hint_is_quiet_outside_a_rejection():
    """差し戻し以外では、ヒントを一切足さないこと。"""
    from chat.agents import _refresh_hint
    assert _refresh_hint({"feedback": "", "status": "fix_time"}, ["a"], "観光") == ""
    assert _refresh_hint({"feedback": "だめ", "status": "approved"}, ["a"], "観光") == ""
    assert _refresh_hint({}, ["a"], "観光") == ""
    hint = _refresh_hint({"feedback": "だめ", "status": "fix_sightseeing"}, [], "観光")
    assert "だめ" in hint and "前回選ばれて" not in hint   # 顔ぶれが無ければその節は出さない
