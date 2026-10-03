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
            # 回した図形（マスキングテープ）も含め、4つの角がページに収まること
            sw, sh = size["width"]["magnitude"], size["height"]["magnitude"]
            a, b = tr.get("scaleX", 1), tr.get("shearY", 0)
            c, d = tr.get("shearX", 0), tr.get("scaleY", 1)
            for px, py in ((0, 0), (sw, 0), (0, sh), (sw, sh)):
                cx = a * px + c * py + tr["translateX"]
                cy = b * px + d * py + tr["translateY"]
                assert -0.5 <= cx <= w + 0.5, (oid, "横にはみ出す", cx)
                assert -0.5 <= cy <= h + 0.5, (oid, "縦にはみ出す", cy)
            if kind == "createShape":
                assert body["shapeType"] in ("RECTANGLE", "ROUND_RECTANGLE", "ELLIPSE", "TEXT_BOX",
                                             "FLOWCHART_TERMINATOR", "WEDGE_ROUND_RECTANGLE_CALLOUT")
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
    "時刻の幅": _plan(schedule=["1日目"] + [f"{9 + i:02d}:00〜{10 + i:02d}:30 予定{i}（説明が少し長めの行）"
                                          for i in range(12)]),
    "2週間": _plan(duration="13泊14日", travel_date="2026年12月28日", themes=["温泉", "雪景色"],
                 schedule=sum(([f"{d}日目"] + [f"{9 + i:02d}:00 予定{d}-{i}" for i in range(6)]
                               for d in range(1, 15)), [])),
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


def test_bold_ranges_count_emoji_as_two():
    """Slides の文字位置は UTF-16。絵文字の後ろの行で、太字の範囲がずれないこと。"""
    lines = ["🍀🍀 はじめの行", "■ 2日目の費用", "・昼食: 1,500円", "■ 合計"]
    text, styles = SX._join_with_styles(
        lines, lambda line: (len(line), "#000000") if line.startswith("■") else None)
    units = text.encode("utf-16-le")
    picked = [units[a * 2:b * 2].decode("utf-16-le") for a, b, _, _ in styles]
    assert picked == ["■ 2日目の費用", "■ 合計"]


def _timeline(texts_in_order):
    """タイムラインの (時刻, 予定) の組を、ページの順に拾う。"""
    out, pending = [], None
    for t in texts_in_order:
        if re.fullmatch(r"\d{1,2}:\d{2}", t):
            pending = t
        elif pending:
            out.append((pending, t))
            pending = None
    return out


def _texts_in_order(body):
    return [r["insertText"]["text"] for r in body if "insertText" in r]


def test_schedule_gets_one_page_per_day_and_splits_long_days():
    body, _ = SX.build_requests(SHAPES["長い旅"])
    _validate(body)
    texts = _texts_in_order(body)
    # 「旅のあらまし」のカードに1回、その日のページに1回
    assert all(texts.count(f"{d}日目") == 2 for d in range(1, 7))
    assert "日ごとの みどころ" in texts
    # 日付が具体的なので、各日の左の帯に曜日つきの日付が出る
    assert "11月3日（火）" in texts and "11月8日（日）" in texts

    body, _ = SX.build_requests(SHAPES["1日がとても長い"])
    _validate(body)
    texts = _texts_in_order(body)
    assert texts.count("1日目") >= 2 and "（つづき）" in texts
    # 40行がどれも1回ずつ、どこかのページに載っていること（取りこぼし・重複が無い）
    assert sorted(_timeline(texts)) == sorted((f"{i:02d}:00", f"予定{i}") for i in range(40))


def test_time_ranges_take_two_lines_and_do_not_overlap():
    """「09:00〜11:00」は時刻の欄に入りきらない。開始と終了を2行にし、高さも確保する。"""
    plan = _plan(schedule=["1日目", "09:00〜11:00 兼六園", "11:30-12:30 近江町市場で昼食", "13:00 美術館"])
    body, _ = SX.build_requests(plan)
    _validate(body)
    texts = _texts_in_order(body)
    assert "09:00" in texts and "〜11:00" in texts and "〜12:30" in texts
    assert "兼六園" in texts, "時刻を外した中身が予定の欄に出ていない"
    # 次の行の時刻が、前の行の2行目（終了時刻）に重ならない
    boxes = {r["createShape"]["objectId"]: r["createShape"]["elementProperties"]
             for r in body if "createShape" in r}
    y_of = {r["insertText"]["text"]: boxes[r["insertText"]["objectId"]]["transform"]["translateY"]
            for r in body if "insertText" in r}
    assert y_of["11:30"] >= y_of["〜11:00"] + 16


def test_day_header_with_the_first_item_on_the_same_line_keeps_the_item():
    """「【2日目】09:00 美術館」で、その日の予定が消えないこと（実際に消えていた）。"""
    plan = _plan(schedule=["【1日目】09:00 東京駅発", "10:00 金沢着", "【2日目】 09:00 美術館"])
    body, _ = SX.build_requests(plan)
    _validate(body)
    texts = _texts_in_order(body)
    assert "東京駅発" in texts and "美術館" in texts
    assert texts.count("2日目") == 2, "2日目のページが無い"


def test_full_width_times_are_normalised():
    plan = _plan(schedule=["１日目", "０９：００ 出発", "２日目", "１０：００ 帰る"])
    body, _ = SX.build_requests(plan)
    texts = _texts_in_order(body)
    assert "09:00" in texts and "10:00" in texts


def test_timeline_marks_meals_stays_moves_and_bolds_place_names():
    body, _ = SX.build_requests(_plan())
    _, texts = _validate(body)
    emojis = [t for t in _texts_in_order(body) if t in ("🍱", "🏨", "🚄", "✈️", "✨", "☕")]
    assert "🍱" in emojis and "🚄" in emojis and "✨" in emojis
    # 「11:00 🍣 近江町市場で昼食」は食事、「13:00 兼六園」は観光地
    assert SX._kind("🍣 近江町市場で昼食", SX._place_names(_plan())) == "meal"
    assert SX._kind("兼六園（約1時間・バス10分）", ["兼六園"]) == "spot", "観光地をバスの語で移動と取り違えている"
    assert SX._kind("江ノ電で長谷へ（約5分）", []) == "move"
    assert SX._kind("羽田空港発（AF293）", []) == "fly"
    assert SX._kind("ホテル日航金沢にチェックイン", ["ホテル日航金沢"]) == "stay"
    # 地名は予定の中で太字になる（UTF-16 の位置で）
    text = "🍣 近江町市場 いきいき亭で昼食"
    styles = SX._name_styles(text, ["近江町市場 いきいき亭", "近江町市場"])
    units = text.encode("utf-16-le")
    assert [units[a * 2:b * 2].decode("utf-16-le") for a, b, _, _ in styles] == ["近江町市場 いきいき亭"]


def test_day_panel_shows_that_days_weather():
    weather = [{"date": "2026-11-04", "emoji": "☔", "tmax": 14.4, "tmin": 8.6}]
    body, _ = SX.build_requests(_plan(), weather_days=weather)
    texts = _texts_in_order(body)
    assert "☔  14° / 9°" in texts
    assert texts.index("2日目", texts.index("日ごとの みどころ") + 10) < texts.index("☔  14° / 9°")


def test_cover_shows_themes_as_tags():
    body, _ = SX.build_requests(_plan(themes=["食", "街歩き", "とても長いテーマの名前です"]))
    texts = _texts_in_order(body)
    assert "# 食" in texts and "# 街歩き" in texts and "# とても長いテー…" in texts


def test_budget_bar_says_how_much_is_left_or_over():
    body, _ = SX.build_requests(_plan())
    assert "予算の 85%（あと 12,000円）" in _texts_in_order(body)
    body, _ = SX.build_requests(_plan(total_per_person=86000))
    assert "予算より 6,000円 多め" in _texts_in_order(body)
    _validate(body)


def test_full_width_brackets_stay_as_written():
    """時刻を半角にするのは時刻だけ。「（約1時間）」のかっこまで半角に変えない。"""
    body, _ = SX.build_requests(_plan(schedule=["1日目", "０９：００ 兼六園（約1時間・バス10分＋徒歩5分）"]))
    texts = _texts_in_order(body)
    assert "09:00" in texts and "兼六園（約1時間・バス10分＋徒歩5分）" in texts


def test_glance_cards_skip_duplicate_names_and_cover_travel_days():
    places = SX._place_names(_plan(spots=["近江町市場"], restaurants=["近江町市場 いきいき亭"]))
    assert SX._highlights(["11:00 近江町市場 いきいき亭で昼食", "13:00 近江町市場を散策"], places) \
        == ["近江町市場 いきいき亭"], "同じ場所を2回挙げている"
    # 地名の出てこない移動だけの日も、空のカードにしない
    assert SX._highlights(["09:00 チェックアウト", "10:00 RER B線で空港へ（約50分）"], places) \
        == ["チェックアウト", "RER B線で空港へ"]
    assert SX._clip("オテル・デュ・ルーヴル・パリ", 8) == "オテル・デュ…"


def test_glance_page_is_only_for_multi_day_trips():
    body, _ = SX.build_requests(SHAPES["日帰り"])
    assert "日ごとの みどころ" not in _texts_in_order(body)
    body, _ = SX.build_requests(_plan(duration="13泊14日", schedule=sum(
        ([f"{d}日目", f"09:00 予定{d}"] for d in range(1, 15)), [])))
    texts = _texts_in_order(body)
    assert texts.count("日ごとの みどころ") == 1 and texts.count("日ごとの みどころ（つづき）") == 1


def test_note_before_day_one_rides_on_day_one():
    """「※時刻は現地時刻」のような1日目より前の行で、1枚を使い切らないこと。"""
    plan = _plan(schedule=["※時刻はすべて現地時刻", "1日目", "10:00 出発", "2日目", "09:00 帰る"])
    body, _ = SX.build_requests(plan)
    slides, texts = _validate(body)
    assert "スケジュール" not in texts.values(), "1日目の前の行だけでページを作っている"
    order = _texts_in_order(body)
    assert order.index("1日目") < order.index("※時刻はすべて現地時刻") < order.index("10:00")


def test_day_trip_has_a_plain_schedule_and_skips_empty_sections():
    body, _ = SX.build_requests(SHAPES["日帰り"])
    _, texts = _validate(body)
    joined = "\n".join(texts.values())
    assert "日帰り" in texts.values()
    assert "とまるところ" not in joined, "宿の無い旅に宿の欄を出している"
    assert "わすれずに" not in joined, "持ちものが無いのにページを作っている"


def test_bare_plan_still_makes_a_cover_and_a_goodbye():
    body, _ = SX.build_requests(SHAPES["中身が少ない"])
    slides, texts = _validate(body)
    assert len(slides) == 2
    assert "熱海" in texts.values() and "いってらっしゃい！🍀" in texts.values()
    assert "None" not in "".join(texts.values())
    assert "ち ゃ む か ら   ひ と こ と" not in texts.values(), "ひとことが無いのに見出しだけ出ている"


def test_every_page_but_the_cover_is_numbered():
    body, _ = SX.build_requests(_plan())
    slides, texts = _validate(body)
    numbers = sorted(t for t in texts.values() if re.fullmatch(r"\d+ / \d+", t))
    total = len(slides)
    assert numbers == sorted(f"{n} / {total}" for n in range(2, total + 1))


def test_cost_page_puts_the_per_person_total_up_front():
    body, _ = SX.build_requests(_plan())
    _, texts = _validate(body)
    assert "68,000円" in texts.values()
    assert "2人で 136,000円" in texts.values()


def test_packing_list_keeps_names_short_and_fits_one_page():
    body, _ = SX.build_requests(_plan(packing_list=["とても長い名前の持ちものの例ですよ"] + [f"品{i}" for i in range(30)]))
    _, texts = _validate(body)
    pills = [t for t in texts.values() if t.startswith("○  ")]
    assert len(pills) == 21
    assert "○  とても長い名前の持ちもの…" in pills


def test_cards_do_not_overflow():
    """入れた文字が、見積もりで箱の高さを超えないこと（API は自動で縮めない）。"""
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
            need = SX._text_height(text.split("\n"), chars, size, spacing[oid])
            assert need <= height + size * 1.6, f"{name}: 「{text[:20]}…」が箱からあふれる"


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
