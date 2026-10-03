"""Google スライドへの「旅のしおり」書き出しの検査（APIキー・ネットワーク不要）。

本物の Slides API は呼べないので、2つに分けて確かめる:
  ・build_requests() が作る要求が、API の約束（ID の形・参照先・文字位置・
    フィールド名）を守っているか。旅の形を変えて総当たりで見る
  ・ルートと OAuth の流れ（許可画面へ送る → /auth/callback に戻る → 作る）

実行: pytest tests/test_slides_export.py
"""
import json
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("GOOGLE_API_KEY", "dummy")
os.environ.setdefault("TAVILY_API_KEY", "dummy")

from services import slides_export as SX  # noqa: E402

OWNER = "u-owner"


def _plan(**over):
    p = {
        "id": 7, "google_user_id": OWNER,
        "destination": "金沢", "travel_date": "2026年11月3日", "duration": "2泊3日",
        "num_people": 2, "departure_location": "東京", "total_per_person": 68000,
        "budget_limit": 80000,
        "spots": ["兼六園", "金沢21世紀美術館", "ひがし茶屋街"],
        "restaurants": ["近江町市場 いきいき亭", "金沢おでん 赤玉本店"],
        "accommodation": ["ホテル日航金沢"],
        "schedule": ["1日目：金沢市内", "08:00 東京駅発（北陸新幹線・約2時間30分）",
                     "11:00 🍣 近江町市場で昼食", "13:00 兼六園",
                     "【2日目】", "09:00 金沢21世紀美術館", "12:00 昼食",
                     "3日目", "10:00 チェックアウト", "12:30 金沢駅発"],
        "budget_estimate": ["■ 往復交通費: 28,000円/人", "■ 1日目の費用", "・兼六園: 320円",
                            "■ 合計", "・1人あたり合計: 68,000円"],
        "packing_list": ["折りたたみ傘", "歩きやすい靴", "モバイルバッテリー"],
        "feedback": "移動が少なく、ゆったり楽しめるプランです🍀",
    }
    p.update(over)
    return p


# ----------------------------------------------------------------------
# Slides API の約束を守っているか
# ----------------------------------------------------------------------
_ID = re.compile(r"^[a-zA-Z0-9_][a-zA-Z0-9_\-:]{4,49}$")
_KNOWN = {"createSlide", "updatePageProperties", "createShape", "updateShapeProperties",
          "insertText", "updateTextStyle", "updateParagraphStyle", "createLine",
          "updateLineProperties", "createImage", "deleteObject"}


def _validate(requests, images=(), page=(720, 405), delete=None):
    """要求の並びを頭から読み、API に断られる形が無いかを調べる。文字の中身を返す。"""
    slides, objects, texts = set(), {}, {}
    w, h = page
    for req in list(requests) + list(images):
        assert len(req) == 1, req
        (kind, body), = req.items()
        assert kind in _KNOWN, kind
        if kind == "createSlide":
            sid = body["objectId"]
            assert _ID.match(sid) and sid not in slides and sid not in objects, sid
            assert body["slideLayoutReference"] == {"predefinedLayout": "BLANK"}
            slides.add(sid)
        elif kind in ("createShape", "createLine", "createImage"):
            oid = body["objectId"]
            assert _ID.match(oid) and oid not in objects and oid not in slides, oid
            ep = body["elementProperties"]
            assert ep["pageObjectId"] in slides, "まだ無いページに置いている"
            size, tr = ep["size"], ep["transform"]
            assert size["width"]["unit"] == size["height"]["unit"] == tr["unit"] == "PT"
            x, y = tr["translateX"], tr["translateY"]
            assert x >= 0 and y >= 0
            assert x + size["width"]["magnitude"] <= w + 0.5, (oid, "右にはみ出す")
            assert y + size["height"]["magnitude"] <= h + 0.5, (oid, "下にはみ出す")
            if kind == "createShape":
                assert body["shapeType"] in ("RECTANGLE", "ROUND_RECTANGLE", "ELLIPSE", "TEXT_BOX")
            if kind == "createImage":
                assert body["url"].startswith("https://")
            objects[oid] = kind
        elif kind == "updatePageProperties":
            assert body["objectId"] in slides
        elif kind == "deleteObject":
            assert body["objectId"] == delete
        else:
            oid = body["objectId"]
            assert oid in objects, (kind, "まだ無い図形を触っている")
            if kind == "insertText":
                assert body["text"], "空の文字は入れられない（API がエラーにする）"
                assert oid not in texts, "同じ図形に2回入れている"
                assert body["insertionIndex"] == 0
                texts[oid] = body["text"]
            if kind in ("updateTextStyle", "updateParagraphStyle"):
                assert oid in texts, "文字の無い図形に書式を当てている"
                rng = body["textRange"]
                if rng["type"] == "FIXED_RANGE":
                    assert 0 <= rng["startIndex"] < rng["endIndex"] <= SX._u16(texts[oid])
                else:
                    assert rng == {"type": "ALL"}
            if "fields" in body:
                style = body.get("style") or body.get("shapeProperties") or body.get("lineProperties")
                for field in body["fields"].split(","):
                    assert field.split(".")[0] in style, (kind, field, "fields に無い項目を書いている")
    if delete:
        assert requests[-1] == {"deleteObject": {"objectId": delete}}, "最初の空ページは最後に消す"
    return slides, texts


SHAPES = {
    "宿泊あり": _plan(),
    "日帰り": _plan(duration="日帰り", accommodation=[], packing_list=[],
                    schedule=["09:00 東京駅発", "11:00 鎌倉駅着", "12:00 昼食", "17:00 帰路"]),
    "長い旅": _plan(duration="5泊6日", schedule=sum(
        ([f"{d}日目"] + [f"{9 + i:02d}:00 予定{d}-{i}（移動・所要時間などの説明が長めに入る行）" for i in range(9)]
         for d in range(1, 7)), [])),
    "海外": _plan(destination="パリ", spots=["エッフェル塔（Tour Eiffel）", "ルーヴル美術館（Musée du Louvre）"],
                feedback="現地時刻で書いています。1ユーロ≒165円で換算しました。"),
    "中身が少ない": {"id": 1, "google_user_id": OWNER, "destination": "熱海"},
    "長い行き先": _plan(destination="ニューヨーク・マンハッタン島とブルックリン"),
    "持ちもの多め": _plan(packing_list=[f"持ちもの{i}" for i in range(30)]),
    "長い総評": _plan(feedback="とても" * 150),
    "1日がとても長い": _plan(schedule=["1日目"] + [f"{i:02d}:00 予定{i}" for i in range(40)]),
}


@pytest.mark.parametrize("name", list(SHAPES))
def test_requests_follow_the_slides_api_contract(name):
    body, images = SX.build_requests(
        SHAPES[name], image_url=lambda n: f"https://example.run.app/static/img/{n}",
        delete_slide="p_first")
    slides, texts = _validate(body, images, delete="p_first")
    assert len(slides) >= 2, "表紙と最後のページは必ずある"
    assert images, "ちゃむの絵がどこにも無い"
    assert all("createImage" not in r for r in body), "絵が本体に混ざると、貼れないときに全部失敗する"


def test_page_size_from_the_api_is_respected():
    """作ったスライドの大きさ（EMU）に合わせて伸縮すること。4:3 でもはみ出さない。"""
    size = {"width": {"magnitude": 9144000, "unit": "EMU"},
            "height": {"magnitude": 6858000, "unit": "EMU"}}   # 720×540pt
    body, images = SX.build_requests(_plan(), page_size=size,
                                     image_url=lambda n: f"https://x.app/{n}")
    _validate(body, images, page=(720, 540))


def test_every_text_uses_the_sites_font():
    body, _ = SX.build_requests(_plan())
    alls = [r["updateTextStyle"] for r in body
            if "updateTextStyle" in r and r["updateTextStyle"]["textRange"]["type"] == "ALL"]
    inserted = sum(1 for r in body if "insertText" in r)
    assert len(alls) == inserted
    assert {s["style"]["fontFamily"] for s in alls} == {"Zen Maru Gothic"}


def test_time_highlight_counts_emoji_as_two():
    """Slides の文字位置は UTF-16。絵文字の後ろの行で、時刻の太字がずれないこと。"""
    body, _ = SX.build_requests(_plan())
    _, texts = _validate(body)
    checked = 0
    for r in body:
        st = r.get("updateTextStyle")
        if not st or st["textRange"]["type"] != "FIXED_RANGE":
            continue
        text = texts[st["objectId"]]
        if "08:00" not in text:
            continue
        units = text.encode("utf-16-le")
        a, b = st["textRange"]["startIndex"], st["textRange"]["endIndex"]
        picked = units[a * 2:b * 2].decode("utf-16-le")
        assert re.fullmatch(r"\d{2}:\d{2}", picked), picked
        checked += 1
    assert checked == 3, "1日目の3行ぶんの時刻が太字になっていない"


def test_schedule_gets_one_page_per_day_and_splits_long_days():
    body, _ = SX.build_requests(SHAPES["長い旅"])
    _, texts = _validate(body)
    headings = [t for t in texts.values() if re.fullmatch(r"\d日目(（つづき）)?", t)]
    assert [h for h in headings if "つづき" not in h] == [f"{d}日目" for d in range(1, 7)]

    body, _ = SX.build_requests(SHAPES["1日がとても長い"])
    _, texts = _validate(body)
    pages = [t for t in texts.values() if t.startswith("1日目")]
    assert len(pages) >= 3 and pages[1] == "1日目（つづき）"
    # 40行がどれも1回ずつ、どこかのページに載っていること（取りこぼし・重複が無い）
    lines = [ln for t in texts.values() for ln in t.split("\n") if re.match(r"\d{2}:00 予定", ln)]
    assert sorted(lines) == sorted(f"{i:02d}:00 予定{i}" for i in range(40))


def test_day_trip_has_a_plain_schedule_and_skips_empty_sections():
    body, _ = SX.build_requests(SHAPES["日帰り"])
    _, texts = _validate(body)
    joined = "\n".join(texts.values())
    assert "当日のスケジュール" in joined
    assert "🏨 宿泊" not in joined, "宿の無い旅に宿の欄を出している"
    assert "わすれずに" not in joined, "持ちものが無いのにページを作っている"


def test_bare_plan_still_makes_a_cover_and_a_goodbye():
    body, _ = SX.build_requests(SHAPES["中身が少ない"])
    slides, texts = _validate(body)
    assert len(slides) == 2
    assert "熱海" in texts.values() and "いってらっしゃい！🍀" in texts.values()
    assert "None" not in "".join(texts.values())


def test_cards_do_not_overflow():
    """カードに入れた文字が、見積もりで箱の高さを超えないこと（API は自動で縮めない）。"""
    for name, plan in SHAPES.items():
        body, _ = SX.build_requests(plan)
        boxes = {r["createShape"]["objectId"]: r["createShape"]["elementProperties"]["size"]
                 for r in body if "createShape" in r}
        sizes = {r["updateTextStyle"]["objectId"]: r["updateTextStyle"]["style"]["fontSize"]["magnitude"]
                 for r in body if "updateTextStyle" in r
                 and r["updateTextStyle"]["textRange"]["type"] == "ALL"}
        spacing = {r["updateParagraphStyle"]["objectId"]: r["updateParagraphStyle"]["style"]["lineSpacing"]
                   for r in body if "updateParagraphStyle" in r}
        for r in body:
            if "insertText" not in r:
                continue
            oid, text = r["insertText"]["objectId"], r["insertText"]["text"]
            box = boxes[oid]
            width, height = box["width"]["magnitude"], box["height"]["magnitude"]
            size = sizes[oid]
            chars = max(1, int((width - 14) / size))
            need = SX._visual_lines(text.split("\n"), chars) * size * spacing[oid] / 100 * 1.2
            assert need <= height + size * 1.5, f"{name}: 「{text[:20]}…」が箱からあふれる"


def test_cost_headings_are_not_left_alone_at_the_bottom():
    lines = ["■ 往復交通費"] + [f"・項目{i}: 1,000円" for i in range(11)] + ["■ 3日目の費用", "・昼食: 1,500円"]
    pages = SX._paginate(lines, 48, 13, is_heading=lambda line: line.startswith("■"))
    assert all(not p[-1].startswith("■") for p in pages[:-1])
    assert sum(len(p) for p in pages) == len(lines)


# ----------------------------------------------------------------------
# 作成の流れ（API の代わりに記録係を使う）
# ----------------------------------------------------------------------
class _Resp:
    def __init__(self, status, body=None):
        self.status_code = status
        self._body = body or {}
        self.text = json.dumps(self._body)

    def json(self):
        return self._body


class _Http:
    def __init__(self, image_status=200, create_status=200):
        self.calls = []
        self.image_status = image_status
        self.create_status = create_status

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append((url, json, headers))
        if url == SX.API:
            return _Resp(self.create_status, {
                "presentationId": "pres123",
                "slides": [{"objectId": "p_first"}],
                "pageSize": {"width": {"magnitude": 9144000, "unit": "EMU"},
                             "height": {"magnitude": 5143500, "unit": "EMU"}}})
        if any("createImage" in r for r in json["requests"]):
            return _Resp(self.image_status, {"error": "image"})
        return _Resp(200, {})


def test_create_presentation_builds_then_adds_pictures():
    http = _Http()
    url = SX.create_presentation("tok", _plan(), image_url=lambda n: f"https://x.app/{n}", http=http)
    assert url == "https://docs.google.com/presentation/d/pres123/edit"
    assert [c[0] for c in http.calls] == [
        SX.API, f"{SX.API}/pres123:batchUpdate", f"{SX.API}/pres123:batchUpdate"]
    assert all(c[2] == {"Authorization": "Bearer tok"} for c in http.calls)
    assert http.calls[0][1] == {"title": "旅のしおり — 金沢"}
    assert http.calls[1][1]["requests"][-1] == {"deleteObject": {"objectId": "p_first"}}


def test_pictures_failing_does_not_fail_the_shiori():
    """localhost など、Google が絵を取りに来られなくても、しおりはできたことにする。"""
    url = SX.create_presentation("tok", _plan(), image_url=lambda n: f"https://x.app/{n}",
                                 http=_Http(image_status=400))
    assert url.endswith("/pres123/edit")


def test_permission_errors_are_explained():
    with pytest.raises(SX.SlidesError, match="許可"):
        SX.create_presentation("tok", _plan(), http=_Http(create_status=403))


# ----------------------------------------------------------------------
# ルートと OAuth の流れ
# ----------------------------------------------------------------------
_METADATA = {
    "issuer": "https://accounts.google.com",
    "authorization_endpoint": "https://accounts.google.com/o/oauth2/v2/auth",
    "token_endpoint": "https://oauth2.googleapis.com/token",
    "jwks_uri": "https://www.googleapis.com/oauth2/v3/certs",
}


@pytest.fixture
def web(monkeypatch):
    import app as app_mod
    import db
    from views.auth import oauth

    flask_app = app_mod.app
    flask_app.config["TESTING"] = True
    flask_app.config["SERVER_NAME"] = None
    monkeypatch.setattr(db, "get_travel_plan_by_id",
                        lambda pid: _plan(id=pid) if pid == 7 else None)
    for name in ("google", "google_slides"):
        monkeypatch.setattr(getattr(oauth, name), "load_server_metadata", lambda: dict(_METADATA))
    from services import weather
    monkeypatch.setattr(weather, "plan_forecast", lambda plan: [])
    client = flask_app.test_client()

    def login(uid=OWNER):
        with client.session_transaction() as s:
            s["user_id"] = uid
            s["user_email"] = "owner@example.com"
    return client, login


def test_export_sends_the_owner_to_google_with_the_narrow_scope(web):
    client, login = web
    login()
    r = client.get("/plan/7/slides", headers={"Accept": "text/html"})
    assert r.status_code == 302
    loc = r.headers["Location"]
    assert loc.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert "drive.file" in loc and "auth%2Fdrive&" not in loc and not loc.endswith("auth%2Fdrive")
    assert "redirect_uri=http%3A%2F%2Flocalhost%2Fauth%2Fcallback" in loc, "戻り先はログインと同じ"
    assert "login_hint=owner%40example.com" in loc
    assert "include_granted_scopes=true" in loc
    with client.session_transaction() as s:
        assert s["slides_plan_id"] == 7
        assert any(k.startswith("_state_google_slides_") for k in s)


def test_someone_elses_plan_is_not_found(web):
    client, login = web
    login("u-stranger")
    r = client.get("/plan/7/slides", headers={"Accept": "text/html"})
    assert r.status_code == 404


def test_callback_with_the_slides_state_creates_and_opens_the_presentation(web, monkeypatch):
    client, login = web
    from views.auth import oauth
    from services import slides_export
    login()
    with client.session_transaction() as s:
        s["slides_plan_id"] = 7
        s["_state_google_slides_abc"] = {"data": {}, "exp": 9999999999}
    seen = {}
    monkeypatch.setattr(oauth.google_slides, "authorize_access_token", lambda: {"access_token": "tok"})

    def fake_create(token, plan, image_url=None, weather_days=None):
        seen.update(token=token, plan=plan["id"], image=image_url("mate.png"))
        return "https://docs.google.com/presentation/d/pres123/edit"
    monkeypatch.setattr(slides_export, "create_presentation", fake_create)

    r = client.get("/auth/callback?state=abc&code=xyz")
    assert r.status_code == 302
    assert r.headers["Location"] == "https://docs.google.com/presentation/d/pres123/edit"
    assert seen == {"token": "tok", "plan": 7,
                    "image": "http://localhost/static/img/mate.png"}
    with client.session_transaction() as s:
        assert "slides_plan_id" not in s
        assert s["user_id"] == OWNER, "書き出しでログイン状態を変えてはいけない"


def test_cancelling_the_permission_goes_back_to_the_plan(web):
    client, login = web
    login()
    with client.session_transaction() as s:
        s["slides_plan_id"] = 7
        s["_state_google_slides_abc"] = {"data": {}, "exp": 9999999999}
    r = client.get("/auth/callback?state=abc&error=access_denied")
    assert r.status_code == 302 and r.headers["Location"].endswith("/plan/7")


def test_normal_login_callback_is_not_mistaken_for_an_export(web, monkeypatch):
    """書き出しを途中でやめたあとでも、ふつうのログインの戻りはログインとして扱う。"""
    client, login = web
    from views import slides as V
    from views.auth import oauth
    login()
    with client.session_transaction() as s:
        s["slides_plan_id"] = 7                        # 書き出しの途中でやめた跡
        s["_state_google_slides_old"] = {"data": {}, "exp": 9999999999}
    called = {"slides": False}
    monkeypatch.setattr(V, "finish_slides_export", lambda: called.update(slides=True) or "x")
    monkeypatch.setattr(oauth.google, "authorize_access_token", lambda: {"userinfo": {
        "sub": OWNER, "email": "owner@example.com", "email_verified": True}})
    r = client.get("/auth/callback?state=new-login-state&code=xyz")
    assert r.status_code == 302 and not called["slides"]


def test_plan_page_has_the_slides_button():
    path = os.path.join(os.path.dirname(__file__), "..", "src", "static", "js", "plan-detail.js")
    src = open(path, encoding="utf-8").read()
    assert 'href="/plan/${esc(plan.id)}/slides"' in src
    assert "📑 スライド" in src
