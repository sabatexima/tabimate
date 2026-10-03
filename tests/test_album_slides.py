"""思い出のアルバム（Google スライド）の検査。ネットワーク・API キー・DB は使わない。

  ・並べ方: 写真が1枚も漏れず・重ならず・小さすぎず・撮った順に並ぶ／ページからはみ出さない
  ・要求: Google が公開している Slides API のスキーマを守る（test_slides_schema の検査を使う）
  ・変な思い出（絵文字・制御文字・None・崩れた日付・極端な縦横比）を大量に流しても落ちない
  ・写真の下ごしらえ: 向きを直す・縮める・枠の形に切り抜く（顔のある上の方を残す）
  ・作る流れ: 取りに来られない写真だけを落として残りは貼る／一時ファイルは必ず消す
  ・画面: 持ち主と共有された人だけが作れる／進み具合のページを返して、できたら移る

実行: pytest tests/test_album_slides.py
"""
import io
import json
import os
import random
import sys
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("SECRET_KEY", "test-secret")

from services import album_slides as A  # noqa: E402
from test_slides_schema import check_requests  # noqa: E402

START = datetime(2026, 8, 14, 9, 0)


def photos_of(aspects, start=START, per_day=None, undated=0):
    """縦横比の並びから Photo を作る（per_day 枚ごとに次の日へ）。"""
    out = []
    for i, a in enumerate(aspects):
        day = i // per_day if per_day else 0
        taken = start + timedelta(days=day, minutes=17 * i)
        out.append(A.Photo(i + 1, a, None if i >= len(aspects) - undated else taken))
    return out


def album_of(photos, **kw):
    album = {"id": 1, "title": "熱海でのんびり", "start_date": "2026-08-14", "end_date": "2026-08-15",
             "cover_photo_id": None, "best": [], "stickers": [],
             "photos": [{"id": p.id, "taken_at": p.taken.isoformat(" ") if p.taken else None,
                         "storage_path": f"trips/1/u/{p.id}.jpg"} for p in photos]}
    album.update(kw)
    return album


MIXED = [1.333, 0.75, 1.333, 1.333, 0.75, 1.0, 1.78, 1.333, 0.75, 0.75, 1.333, 3.0, 1.333, 0.5]


def _overlap(a, b):
    return not (a.x + a.w <= b.x + 0.01 or b.x + b.w <= a.x + 0.01 or
                a.y + a.h <= b.y + 0.01 or b.y + b.h <= a.y + 0.01)


# ----------------------------------------------------------------------
# 並べ方
# ----------------------------------------------------------------------
@pytest.mark.parametrize("aspects,per_day", [
    (MIXED, 7), (MIXED * 3, 14), ([1.333] * 9, None), ([0.75] * 9, None), ([1.0], None),
    ([0.2, 5.0, 0.3, 4.0], None),          # 極端に細長い写真
])
def test_every_photo_appears_once_in_the_day_pages(aspects, per_day):
    photos = photos_of(aspects, per_day=per_day)
    pages = A.layout(album_of(photos), photos)
    day_slots = [s for p in pages if p.kind in ("opener", "grid", "hero") for s in p.slots]
    assert sorted(s.photo_id for s in day_slots) == [p.id for p in photos]


@pytest.mark.parametrize("aspects,per_day", [(MIXED, 7), (MIXED * 4, 9), ([0.75] * 13, None)])
def test_photos_follow_the_order_they_were_taken(aspects, per_day):
    """読む順（ページ順 → 左上から）が撮った順になる。"""
    photos = photos_of(aspects, per_day=per_day)
    pages = A.layout(album_of(photos), photos)
    seen = []
    for page in pages:
        if page.kind not in ("opener", "grid", "hero"):
            continue
        # ページの中でも、次の写真は「右」か「下」にある（横一列・2段・大きな1枚＋縦の列のどれでも）
        for a, b in zip(page.slots, page.slots[1:]):
            assert b.x >= a.x + a.w - 0.01 or b.y >= a.y + a.h - 0.01, (page.kind, a, b)
        seen += [s.photo_id for s in page.slots]
    assert seen == sorted(seen)


@pytest.mark.parametrize("aspects", [MIXED, MIXED * 3, [1.333] * 20, [0.75] * 20, [0.2, 5.0, 1.0]])
def test_slots_stay_on_the_page_do_not_overlap_and_are_not_tiny(aspects):
    photos = photos_of(aspects, per_day=6)
    pages = A.layout(album_of(photos, stickers=["a"] * 8), photos)
    for page in pages:
        flat = [s for s in page.slots if not s.rot]
        for s in page.slots:
            assert s.x >= -0.01 and s.y >= -0.01
            assert s.x + s.w <= A.BASE_W + 0.01 and s.y + s.h <= A.BASE_H + 0.01
            assert min(s.w, s.h) >= A.MIN_SIDE - 0.01 or page.kind == "closing"
        if page.kind in ("opener", "grid"):
            for i, a in enumerate(flat):
                for b in flat[i + 1:]:
                    assert not _overlap(a, b), (page.kind, a, b)
                # 白いふちのぶん外へ出ても、ページの端には付かない
                assert a.x - A.MAT >= 30 and a.x + a.w + A.MAT <= A.BASE_W - 30


def test_slots_keep_close_to_the_photos_shape():
    """枠の形は写真の形に近い（切り抜きは2割まで。全面のページと細長い写真は別）。"""
    photos = photos_of(MIXED * 2, per_day=10)
    by_id = {p.id: p for p in photos}
    for page in A.layout(album_of(photos), photos):
        if page.kind not in ("opener", "grid"):
            continue
        for s in page.slots:
            natural = A._clamp(by_id[s.photo_id].aspect)
            assert 1 / 1.2 <= s.aspect / natural <= 1.2, (s.aspect, natural)


def test_portrait_photos_get_portrait_slots():
    photos = photos_of([0.75] * 8)
    for page in A.layout(album_of(photos), photos):
        if page.kind in ("opener", "grid"):
            assert all(s.h > s.w for s in page.slots)


def test_cover_uses_the_chosen_photo_full_page_or_split():
    photos = photos_of([1.333, 0.75, 1.5])
    pages = A.layout(album_of(photos, cover_photo_id=1), photos)
    assert pages[0].kind == "cover" and pages[0].slots[0].photo_id == 1
    assert (pages[0].slots[0].w, pages[0].slots[0].h) == (A.BASE_W, A.BASE_H)
    pages = A.layout(album_of(photos, cover_photo_id=2), photos)
    assert pages[0].kind == "cover_split" and pages[0].slots[0].photo_id == 2
    assert pages[0].slots[0].x + pages[0].slots[0].w == A.BASE_W


def test_cover_falls_back_to_the_best_shot_then_a_landscape_photo():
    photos = photos_of([0.75, 0.75, 1.5, 1.333])
    pages = A.layout(album_of(photos, best=[{"photo_id": 4, "reason": "笑顔"}]), photos)
    assert pages[0].slots[0].photo_id == 4
    pages = A.layout(album_of(photos, cover_photo_id=999), photos)   # 消えた写真
    assert pages[0].slots[0].photo_id == 3, "横長の最初の1枚"


def test_best_shot_page_and_missing_best_shot():
    photos = photos_of([1.333] * 4)
    pages = A.layout(album_of(photos, best=[{"photo_id": 2, "reason": "光がきれい"},
                                            {"photo_id": 999, "reason": "消えた写真"}]), photos)
    best = [p for p in pages if p.kind == "best"]
    assert len(best) == 1 and best[0].slots[0].photo_id == 2 and best[0].info["reason"] == "光がきれい"


def test_days_are_labelled_and_undated_photos_come_last():
    photos = photos_of([1.333] * 6, per_day=2, undated=1)
    days = A._days(photos, None)
    assert [d["label"] for d, _ in days] == ["1日目", "2日目", "3日目", ""]
    assert days[-1][0]["date"] is None and [p.id for p in days[-1][1]] == [6]
    # 旅の初日より前の日付（カメラの時計ずれ）は、写真の最初の日から数える
    days = A._days(photos_of([1.0, 1.0]), datetime(2026, 8, 20).date())
    assert days[0][0]["label"] == ""
    # 出発日から数える（初日に写真が無くても「2日目」から）
    days = A._days(photos_of([1.0, 1.0], start=START + timedelta(days=1)), START.date())
    assert days[0][0]["label"] == "2日目"


def test_single_day_trip_has_no_day_number():
    photos = photos_of([1.333] * 3)
    days = A._days(photos, START.date())
    assert days[0][0]["label"] == "" and days[0][0]["span"] == "9:00 – 9:34"


def test_long_days_get_one_full_page_photo():
    photos = photos_of([1.333] * 12)
    pages = A.layout(album_of(photos), photos)
    heroes = [p for p in pages if p.kind == "hero"]
    assert len(heroes) == 1
    assert heroes[0].slots[0].photo_id not in (1, 12), "まん中あたりから選ぶ"
    assert pages[1].kind == "opener", "日の頭は日付のページ"
    # 表紙に使った写真は全面にしない
    pages = A.layout(album_of(photos, cover_photo_id=heroes[0].slots[0].photo_id), photos)
    assert all(p.slots[0].photo_id != heroes[0].slots[0].photo_id for p in pages if p.kind == "hero")


def test_too_many_photos_are_thinned_evenly_keeping_cover_and_best():
    photos = photos_of([1.333] * 200, per_day=50)
    pages = A.layout(album_of(photos, cover_photo_id=7, best=[{"photo_id": 133, "reason": ""}]), photos)
    in_days = {s.photo_id for p in pages if p.kind in ("opener", "grid", "hero") for s in p.slots}
    assert len(in_days) == A.MAX_PHOTOS and {7, 133} <= in_days
    assert min(in_days) <= 3 and max(in_days) >= 198, "旅の最初から最後まで"
    closing = pages[-1]
    assert closing.kind == "closing" and closing.info == {"total": 200, "shown": A.MAX_PHOTOS}


@pytest.mark.parametrize("n,expected", [(1, [1]), (3, [3]), (6, [6]), (7, [4, 3]), (12, [6, 6]), (20, [6, 6])])
def test_words_pages_are_balanced(n, expected):
    photos = photos_of([1.0])
    pages = A.layout(album_of(photos, stickers=[f"ことば{i}" for i in range(n)] + [None, "", "  "]), photos)
    assert [len(p.info["words"]) for p in pages if p.kind == "words"] == expected


def test_closing_avoids_the_cover_and_fits_the_page():
    photos = photos_of([1.333] * 10)
    closing = A.layout(album_of(photos, cover_photo_id=1), photos)[-1]
    assert 1 <= len(closing.slots) <= 4 and all(s.photo_id != 1 for s in closing.slots)
    assert min(s.x for s in closing.slots) > 40 and max(s.x + s.w for s in closing.slots) < A.BASE_W - 40
    only = photos_of([1.333])
    assert A.layout(album_of(only), only)[-1].slots == [], "表紙の1枚しか無ければ写真なし"


def test_slot_pixel_size_is_capped_and_keeps_the_shape():
    s = A.Slot("k", 1, 0, 0, A.BASE_W, A.BASE_H)
    assert s.px == (A.MAX_PX, 900)
    s = A.Slot("k", 1, 0, 0, 100, 150)
    assert s.px == (240, 360)


def test_date_range_formats():
    d = datetime(2026, 8, 14).date
    assert A.date_range(d(), None) == "2026年8月14日（金）"
    assert A.date_range(d(), datetime(2026, 8, 16).date()) == "2026年8月14日 – 16日"
    assert A.date_range(d(), datetime(2026, 9, 2).date()) == "2026年8月14日 – 9月2日"
    assert A.date_range(datetime(2025, 12, 30).date(), datetime(2026, 1, 2).date()) == "2025年12月30日 – 2026年1月2日"
    assert A.date_range(datetime(2026, 8, 16).date(), d()) == "2026年8月14日 – 16日", "逆でも直す"
    assert A.date_range(None, None) == ""


@pytest.mark.parametrize("text,width,size,expected", [
    ("波の音がずっと聞こえてた", 162, 13, "波の音がずっと\n聞こえてた"),
    ("熱海でのんびり夏休み", 276, 26, "熱海でのんびり\n夏休み"),      # 「熱海での|んびり」にしない
    ("光の入り方がやわらかくて、その場の静けさが伝わる一枚", 236, 15,
     "光の入り方がやわらかくて、\nその場の静けさが伝わる一枚"),
    ("雨のち虹", 162, 13, "雨のち虹"),                                # 1行に入るものはそのまま
    ("改行\nあり", 162, 13, "改行\nあり"),
])
def test_two_line_text_is_broken_at_a_natural_place(text, width, size, expected):
    assert A._balance(text, width, size) == expected


# ----------------------------------------------------------------------
# 要求（Slides API）
# ----------------------------------------------------------------------
def _build(album, photos, urls="all"):
    pages = A.layout(album, photos)
    slots = A.all_slots(pages)
    if urls == "all":
        urls = {s.key: f"https://storage.googleapis.com/b/slides-tmp/x/{s.key}.jpg?sig=1" for s in slots}
    body, images, zorder = A.build_requests(album, photos, pages, urls, delete_slide="p_first")
    return pages, body, images, zorder


def _ids_on_pages(body, images):
    on = {}
    for q in body + images:
        (kind, v), = q.items()
        if kind in ("createShape", "createLine", "createImage"):
            on[v["objectId"]] = v["elementProperties"]["pageObjectId"]
    return on


@pytest.mark.parametrize("aspects,kw", [
    (MIXED, {"cover_photo_id": 2, "best": [{"photo_id": 3, "reason": "みんなの笑顔がそろった一枚"}],
             "stickers": ["波の音がずっと聞こえてた", "坂の途中のパン屋さん", "夕焼け"]}),
    (MIXED * 3, {"title": "北海道ぐるっと一周！富良野のラベンダー畑と美瑛の青い池をめぐる家族旅行" * 2}),
    ([1.0], {"title": "", "start_date": None, "end_date": None}),
])
def test_requests_match_googles_published_schema(aspects, kw):
    photos = photos_of(aspects, per_day=7)
    pages, body, images, zorder = _build(album_of(photos, **kw), photos)
    check_requests(body)
    check_requests(images)
    check_requests(zorder)
    assert len(images) == len(A.all_slots(pages))
    ids = [next(iter(q.values()))["objectId"] for q in body + images
           if next(iter(q)) in ("createShape", "createLine", "createImage", "createSlide")]
    assert len(ids) == len(set(ids)), "ID の重複"
    # 手前に出す物は、どれも同じページの、本体で作った図形
    on = _ids_on_pages(body, [])
    for z in zorder:
        objs = z["updatePageElementsZOrder"]["pageElementObjectIds"]
        assert all(o in on for o in objs) and len({on[o] for o in objs}) == 1
    assert body[-1] == {"deleteObject": {"objectId": "p_first"}}


def test_no_character_images_and_no_none_text():
    """アルバムにはキャラクター（ちゃむ）の絵を入れない。「None」も出さない。"""
    photos = photos_of(MIXED, per_day=7)
    album = album_of(photos, title=None, best=[{"photo_id": 1, "reason": None}], stickers=[None, "雨"])
    pages, body, images, zorder = _build(album, photos)
    for q in images:
        assert "slides-tmp" in q["createImage"]["url"], "写真だけを貼る"
    texts = [q["insertText"]["text"] for q in body if "insertText" in q]
    assert texts and not any("None" in t for t in texts)
    assert not any("ちゃむ" in t for t in texts)
    assert any(t == "旅の思い出" for t in texts), "題名が無ければ「旅の思い出」"


def test_photos_without_a_url_leave_only_the_white_frame():
    photos = photos_of([1.333] * 5)
    pages, body, images, zorder = _build(album_of(photos), photos, urls={})
    assert images == []
    check_requests(body)


def test_text_boxes_are_tall_enough_for_their_lines():
    """文字の箱が、入れた文字の行数ぶんの高さを持っている（下見の HTML であふれを数えるのと同じ考え）。"""
    photos = photos_of(MIXED, per_day=7)
    album = album_of(photos, best=[{"photo_id": 2, "reason": "光の入り方がやわらかくて、その場の静けさが伝わる一枚"}],
                     stickers=["波の音がずっと聞こえてた", "ラベンダーのソフトクリームがとてもおいしかったね"])
    _, body, _, _ = _build(album, photos)
    shapes = {q["createShape"]["objectId"]: q["createShape"] for q in body if "createShape" in q}
    styles = {}
    for q in body:
        if "updateTextStyle" in q and q["updateTextStyle"]["textRange"]["type"] == "ALL":
            styles[q["updateTextStyle"]["objectId"]] = q["updateTextStyle"]["style"]["fontSize"]["magnitude"]
    paras = {q["updateParagraphStyle"]["objectId"]: q["updateParagraphStyle"]["style"]["lineSpacing"]
             for q in body if "updateParagraphStyle" in q}
    for q in body:
        if "insertText" not in q:
            continue
        oid, text = q["insertText"]["objectId"], q["insertText"]["text"]
        size = shapes[oid]["elementProperties"]["size"]
        w, h = size["width"]["magnitude"], size["height"]["magnitude"]
        need = A._lines(text, w, styles[oid]) * A._line_height(styles[oid], paras[oid])
        assert need <= h + 8.5, (text, need, h)


def test_page_size_scales_everything():
    photos = photos_of([1.333] * 3)
    pages = A.layout(album_of(photos), photos)
    urls = {s.key: "https://x/y.jpg" for s in A.all_slots(pages)}
    _, images, _ = A.build_requests(album_of(photos), photos, pages, urls,
                                       page_size={"width": {"magnitude": 9144000 * 2}, "height": {"magnitude": 5143500 * 2}})
    cover = images[0]["createImage"]["elementProperties"]["size"]
    assert cover["width"]["magnitude"] == 1440 and cover["height"]["magnitude"] == 810


def _junk(rng):
    return rng.choice([None, "", " ", "\x00\x07制御", "😀👨‍👩‍👧‍👦" * 9, "A" * 300, "改\n行\n\n多い",
                       "</script><b>", "長い" * 80, 12345, "旅"])


def test_fuzz_strange_albums_never_crash_and_stay_valid():
    rng = random.Random(20261003)
    for _ in range(120):
        n = rng.randint(1, 40)
        aspects = [rng.choice([0.1, 0.5, 0.75, 1.0, 1.333, 1.78, 3.0, 9.0]) for _ in range(n)]
        photos = photos_of(aspects, per_day=rng.choice([None, 1, 3, 8]), undated=rng.randint(0, n))
        rng.shuffle(photos)
        photos.sort(key=lambda p: (p.taken is None, p.taken or datetime.min, p.id))
        album = album_of(photos, title=_junk(rng),
                         start_date=rng.choice([None, "2026-08-14", "壊れた日付", "2026-13-40", "2026/08/10"]),
                         end_date=rng.choice([None, "2026-08-13", "x"]),
                         cover_photo_id=rng.choice([None, 1, n, 999, "1"]),
                         best=rng.choice([[], [{"photo_id": rng.randint(1, n), "reason": _junk(rng)}],
                                          [{"photo_id": None}], [{"reason": "x"}]]),
                         stickers=[_junk(rng) for _ in range(rng.randint(0, 15))])
        pages, body, images, zorder = _build(album, photos)
        check_requests(body)
        check_requests(images)
        check_requests(zorder)
        for page in pages:
            for s in page.slots:
                assert -0.01 <= s.x and s.x + s.w <= A.BASE_W + 0.01
                assert -0.01 <= s.y and s.y + s.h <= A.BASE_H + 0.01
        texts = [q["insertText"]["text"] for q in body if "insertText" in q]
        assert not any("None" in t or "\x00" in t for t in texts)


# ----------------------------------------------------------------------
# 写真の下ごしらえ
# ----------------------------------------------------------------------
def _jpeg(size, orientation=1, color=(200, 120, 40), fmt="JPEG"):
    from PIL import Image
    img = Image.new("RGB", size, color)
    out = io.BytesIO()
    if fmt == "JPEG":
        exif = Image.Exif()
        exif[0x0112] = orientation
        img.save(out, format="JPEG", exif=exif.tobytes())
    else:
        img.save(out, format=fmt)
    return out.getvalue()


def test_working_copy_fixes_the_orientation_and_shrinks():
    from PIL import Image
    work, aspect = A.working_copy(_jpeg((4000, 3000), orientation=6))
    assert Image.open(io.BytesIO(work)).size == (1200, 1600)
    assert aspect == pytest.approx(0.75)
    work, aspect = A.working_copy(_jpeg((640, 480), fmt="PNG"))
    assert Image.open(io.BytesIO(work)).size == (640, 480), "小さい写真は引き伸ばさない"
    assert A.working_copy(b"not an image") is None


def test_render_crop_matches_the_slot_and_keeps_the_top():
    """縦長の写真を横長の枠に入れるときは、上寄りに切り抜く（顔は上の方にあることが多い）。"""
    from PIL import Image
    src = Image.new("RGB", (1000, 2000))
    for y in range(2000):
        src.paste((0, 0, round(y / 2000 * 255)), (0, y, 1000, y + 1))
    buf = io.BytesIO()
    src.save(buf, format="JPEG", quality=95)
    slot = A.Slot("k", 1, 0, 0, 300, 200)
    out = Image.open(io.BytesIO(A.render_crop(buf.getvalue(), slot)))
    assert out.size == slot.px
    # 切り抜く高さ 667px のうち、上の端は (2000-667)*0.4 ≒ 533px の所
    assert out.getpixel((10, 1))[2] == pytest.approx(533 / 2000 * 255, abs=6)
    # 小さな作業用写真は引き伸ばさない
    small = io.BytesIO()
    Image.new("RGB", (200, 150)).save(small, format="JPEG")
    out = Image.open(io.BytesIO(A.render_crop(small.getvalue(), A.Slot("k", 1, 0, 0, 600, 450))))
    assert out.size == (200, 150)


# ----------------------------------------------------------------------
# 作る流れ（Slides API と一時置き場は偽物）
# ----------------------------------------------------------------------
class FakeResponse:
    def __init__(self, status, data=None):
        self.status_code = status
        self._data = data or {}
        self.text = json.dumps(self._data)

    def json(self):
        return self._data


class FakeSlides:
    """取りに来られない写真（URL に bad を含む）があると、その要求ごと 400 を返す。"""

    def __init__(self, create_status=200):
        self.calls = []
        self.create_status = create_status
        self.placed = []

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append((url, json))
        if url.endswith("/presentations"):
            return FakeResponse(self.create_status, {"presentationId": "pres1", "slides": [{"objectId": "first"}],
                                                     "pageSize": {"width": {"magnitude": 9144000},
                                                                  "height": {"magnitude": 5143500}}})
        reqs = json["requests"]
        if any("bad" in q.get("createImage", {}).get("url", "") for q in reqs):
            return FakeResponse(400, {"error": "cannot fetch"})
        self.placed += [q["createImage"]["objectId"] for q in reqs if "createImage" in q]
        return FakeResponse(200, {})


class FakeHost:
    def __init__(self, bad=()):
        self.bad = set(bad)
        self.files = {}
        self.cleaned = False

    def put(self, name, data):
        self.files[name] = data
        return f"https://host/{'bad-' if name[:-4] in self.bad else ''}{name}"

    def cleanup(self):
        self.cleaned = True


def _real_album(n=9):
    photos = photos_of([1.333, 0.75] * (n // 2) + [1.0] * (n % 2), per_day=5)
    album = album_of(photos, stickers=["雨のち虹"])
    files = {p["id"]: _jpeg((1200, 900) if p["id"] % 2 else (900, 1200)) for p in album["photos"]}
    return album, files


def test_create_album_puts_everything_in_order_and_cleans_up():
    album, files = _real_album()
    http, host, steps = FakeSlides(), FakeHost(), []
    url = A.create_album("tok", album, lambda p: files[p["id"]], host, http=http,
                         progress=lambda t, d, n: steps.append(t))
    assert url == "https://docs.google.com/presentation/d/pres1/edit"
    assert host.cleaned
    kinds = [("create" if u.endswith("/presentations") else
              "images" if any("createImage" in q for q in j["requests"]) else
              "zorder" if all("updatePageElementsZOrder" in q for q in j["requests"]) else "body")
             for u, j in http.calls]
    assert kinds[0] == "create" and kinds[1] == "body" and kinds[-1] == "zorder"
    assert set(kinds[2:-1]) == {"images"}
    assert http.calls[0][1]["title"] == "思い出のアルバム — 熱海でのんびり"
    assert len(http.placed) == len(host.files)
    for step in ("写真を読み込んでいます", "写真をアルバムの形に整えています", "スライドを作っています", "写真を貼っています"):
        assert step in steps
    # 渡した写真は枠の大きさ（長辺1600pxまで）に縮めてある
    from PIL import Image
    assert all(max(Image.open(io.BytesIO(b)).size) <= A.MAX_PX for b in host.files.values())


def test_one_unfetchable_photo_does_not_drop_the_others():
    album, files = _real_album(12)
    http, host = FakeSlides(), FakeHost(bad={"p004"})
    A.create_album("tok", album, lambda p: files[p["id"]], host, http=http)
    assert len(http.placed) == len(host.files) - 1
    assert host.cleaned


def test_unreadable_photos_are_skipped_and_no_photos_is_an_error(monkeypatch):
    album, files = _real_album(6)
    http, host = FakeSlides(), FakeHost()
    laid = {}
    real_layout = A.layout
    monkeypatch.setattr(A, "layout", lambda al, ph: laid.setdefault("ids", [p.id for p in ph]) and real_layout(al, ph))
    A.create_album("tok", album, lambda p: None if p["id"] == 2 else files[p["id"]], host, http=http)
    assert laid["ids"] == [1, 3, 4, 5, 6], "読めない写真だけを落とす"
    assert len(http.placed) == len(host.files)
    monkeypatch.setattr(A, "layout", real_layout)
    with pytest.raises(A.SlidesError, match="読み込めませんでした"):
        A.create_album("tok", album, lambda p: None, FakeHost(), http=FakeSlides())
    with pytest.raises(A.SlidesError, match="まだ写真がありません"):
        A.create_album("tok", dict(album, photos=[]), lambda p: None, FakeHost(), http=FakeSlides())


def test_permission_error_still_cleans_up():
    album, files = _real_album(3)
    host = FakeHost()
    with pytest.raises(A.SlidesError, match="許可"):
        A.create_album("tok", album, lambda p: files[p["id"]], host, http=FakeSlides(create_status=403))
    assert host.cleaned and host.files, "置いた一時ファイルは消す"


# ----------------------------------------------------------------------
# 画面（Flask）
# ----------------------------------------------------------------------
OWNER, FRIEND = "u-owner", "u-friend"
TRIP = {"id": 5, "user_id": OWNER, "title": "鎌倉さんぽ", "start_date": "2026-08-14", "end_date": "2026-08-14",
        "cover_photo_id": 11, "best_shots": json.dumps([{"photo_id": 12, "reason": "光がきれい"}])}


@pytest.fixture
def web(monkeypatch):
    import app as app_mod
    import db_reflection as repo
    import db_sharing
    from views.auth import oauth
    from test_slides_export import _METADATA

    flask_app = app_mod.app
    flask_app.config["TESTING"] = True
    flask_app.config["SERVER_NAME"] = None
    monkeypatch.setattr(repo, "get_trip", lambda tid, uid: dict(TRIP) if tid == 5 and uid == OWNER else None)
    monkeypatch.setattr(repo, "get_trip_by_id", lambda tid, viewer_id=None: dict(TRIP) if tid == 5 else None)
    monkeypatch.setattr(repo, "get_photos", lambda tid: [
        {"id": 11, "taken_at": "2026-08-14 10:00:00", "storage_path": "trips/5/u/a.jpg"},
        {"id": 12, "taken_at": "2026-08-14 11:00:00", "storage_path": "trips/5/u/b.jpg"}])
    monkeypatch.setattr(repo, "get_stickers", lambda tid: [{"id": 1, "text": "雨のち虹"}])
    monkeypatch.setattr(db_sharing, "get_grant_for_email",
                        lambda rt, rid, email: {"permission": "view"} if email == "friend@example.com" else None)
    monkeypatch.setattr(db_sharing, "get_link_by_token", lambda token: None)
    for name in ("google", "google_slides"):
        monkeypatch.setattr(getattr(oauth, name), "load_server_metadata", lambda: dict(_METADATA))
    client = flask_app.test_client()

    def login(uid=OWNER, email="owner@example.com"):
        with client.session_transaction() as s:
            s["user_id"] = uid
            s["user_email"] = email
    return client, login


def test_owner_and_shared_friend_are_sent_to_google(web):
    client, login = web
    for uid, email in ((OWNER, "owner@example.com"), (FRIEND, "friend@example.com")):
        login(uid, email)
        r = client.get("/trip/5/slides", headers={"Accept": "text/html"})
        assert r.status_code == 302 and "drive.file" in r.headers["Location"]
        with client.session_transaction() as s:
            assert s["slides_target"] == ["trip", 5]


def test_strangers_cannot_make_an_album(web):
    client, login = web
    login("u-stranger", "stranger@example.com")
    assert client.get("/trip/5/slides", headers={"Accept": "text/html"}).status_code == 404
    assert client.get("/trip/6/slides", headers={"Accept": "text/html"}).status_code == 404


def test_callback_streams_progress_then_opens_the_album(web, monkeypatch):
    client, login = web
    from views.auth import oauth
    from services import album_slides, storage
    login()
    with client.session_transaction() as s:
        s["slides_target"] = ["trip", 5]
        s["_state_google_slides_abc"] = {"data": {}, "exp": 9999999999}
    monkeypatch.setattr(oauth.google_slides, "authorize_access_token", lambda: {"access_token": "tok"})
    monkeypatch.setattr(storage.TempImages, "sweep", classmethod(lambda cls: 0))
    seen = {}

    def fake_create(token, album, read_photo, host, progress=None):
        seen.update(token=token, album=album)
        progress("写真を読み込んでいます", 1, 2)
        progress("写真を貼っています", 2, 2)
        return "https://docs.google.com/presentation/d/album1/edit"
    monkeypatch.setattr(album_slides, "create_album", fake_create)
    r = client.get("/auth/callback?state=abc&code=xyz")
    assert r.status_code == 200 and r.mimetype == "text/html"
    html = r.get_data(as_text=True)
    assert "アルバムを作っています" in html
    assert 'step("写真を読み込んでいます",1,2)' in html
    assert 'finish("https://docs.google.com/presentation/d/album1/edit")' in html
    assert html.rstrip().endswith("</html>")
    assert seen["token"] == "tok"
    a = seen["album"]
    assert a["title"] == "鎌倉さんぽ" and a["cover_photo_id"] == 11
    assert a["best"] == [{"photo_id": 12, "reason": "光がきれい"}] and a["stickers"] == ["雨のち虹"]
    assert [p["id"] for p in a["photos"]] == [11, 12]
    with client.session_transaction() as s:
        assert "slides_target" not in s and s["user_id"] == OWNER


def test_callback_failure_is_shown_on_the_progress_page(web, monkeypatch):
    client, login = web
    from views.auth import oauth
    from services import album_slides, storage
    login()
    with client.session_transaction() as s:
        s["slides_target"] = ["trip", 5]
        s["_state_google_slides_abc"] = {"data": {}, "exp": 9999999999}
    monkeypatch.setattr(oauth.google_slides, "authorize_access_token", lambda: {"access_token": "tok"})
    monkeypatch.setattr(storage.TempImages, "sweep", classmethod(lambda cls: 0))

    def boom(*a, **kw):
        raise album_slides.SlidesError("Google スライドを作れませんでした。</script>")
    monkeypatch.setattr(album_slides, "create_album", boom)
    html = client.get("/auth/callback?state=abc&code=xyz").get_data(as_text=True)
    assert "fail(" in html and "Google スライドを作れませんでした" in html
    assert "</script>\")" not in html, "メッセージで script を閉じさせない"
    assert 'href="/reflection/trips/5"' in html, "旅のページへ戻れる"


def test_cancelling_goes_back_to_the_trip(web):
    client, login = web
    login(FRIEND, "friend@example.com")
    with client.session_transaction() as s:
        s["slides_target"] = ["trip", 5]
        s["_state_google_slides_abc"] = {"data": {}, "exp": 9999999999}
    r = client.get("/auth/callback?state=abc&error=access_denied")
    assert r.status_code == 302 and r.headers["Location"].endswith("/shared/trip/5")


def test_trip_pages_have_the_album_button():
    root = os.path.join(os.path.dirname(__file__), "..", "src")
    own = open(os.path.join(root, "templates", "reflection", "trip.html"), encoding="utf-8").read()
    shared = open(os.path.join(root, "templates", "shared", "trip.html"), encoding="utf-8").read()
    for src in (own, shared):
        assert "url_for('slides.export_album', trip_id=trip.id)" in src and 'id="album-slides-btn"' in src
    assert "not share_token" in shared, "公開リンクでは出さない"
    for js in ("reflection-trip.js", "shared-trip.js"):
        text = open(os.path.join(root, "static", "js", js), encoding="utf-8").read()
        assert "album-slides-btn" in text, "写真が入ったらボタンを出す"


def test_closing_also_avoids_the_best_shot_when_it_can():
    photos = photos_of([1.333] * 3)
    closing = A.layout(album_of(photos, cover_photo_id=1, best=[{"photo_id": 2, "reason": ""}]), photos)[-1]
    assert [s.photo_id for s in closing.slots] == [3]
    two = photos_of([1.333] * 2)
    closing = A.layout(album_of(two, cover_photo_id=1, best=[{"photo_id": 2, "reason": ""}]), two)[-1]
    assert [s.photo_id for s in closing.slots] == [2], "ほかに無ければベストショットでも出す"


def test_busy_api_is_retried_once_instead_of_splitting(monkeypatch):
    """混み合い（429）は写真のせいではないので、分けずに少し待って一度だけ送り直す。"""
    monkeypatch.setattr(A.time, "sleep", lambda s: None)
    calls = []

    class Busy:
        def post(self, url, json=None, headers=None, timeout=None):
            calls.append(len(json["requests"]))
            return FakeResponse(429 if len(calls) == 1 else 200)
    images = [{"createImage": {"objectId": f"i{i}", "url": "https://x"}} for i in range(8)]
    assert A._insert_images(Busy(), "u", {}, images, [30]) == 8
    assert calls == [8, 8]


def test_image_calls_stop_at_the_budget():
    """どれも貼れない（要求が壊れている）ときに、1枚ずつ何十回も送らない。"""
    calls = []

    class Broken:
        def post(self, url, json=None, headers=None, timeout=None):
            calls.append(1)
            return FakeResponse(400)
    images = [{"createImage": {"objectId": f"i{i}", "url": "https://x"}} for i in range(64)]
    assert A._insert_images(Broken(), "u", {}, images, [10]) == 0
    assert len(calls) == 10


def test_temp_images_are_put_signed_and_cleaned_up(monkeypatch):
    from datetime import timezone
    from services import storage
    saved, deleted = {}, []
    monkeypatch.setattr(storage, "using_gcs", lambda: True)
    monkeypatch.setattr(storage, "_get_signing_info", lambda: ("sa@x", "tok"))
    monkeypatch.setattr(storage, "save_at", lambda key, data, ct: saved.setdefault(key, (data, ct)))
    monkeypatch.setattr(storage, "_sign_url", lambda key: f"https://storage.googleapis.com/b/{key}?X-Goog-Signature=1")
    monkeypatch.setattr(storage, "_delete_key", lambda key: deleted.append(key) or True)
    host = storage.TempImages()
    url = host.put("p001.jpg", b"jpeg")
    key = next(iter(saved))
    assert key.startswith("slides-tmp/") and key.endswith("/p001.jpg") and saved[key] == (b"jpeg", "image/jpeg")
    assert url.endswith("p001.jpg?X-Goog-Signature=1")
    host.cleanup()
    assert deleted == [key] and host.keys == []

    class Blob:
        def __init__(self, name, hours):
            self.name = name
            self.time_created = datetime.now(timezone.utc) - timedelta(hours=hours)

    class Client:
        def list_blobs(self, bucket, prefix):
            assert prefix == "slides-tmp/"
            return [Blob("slides-tmp/a/p1.jpg", 30), Blob("slides-tmp/b/p1.jpg", 1)]
    monkeypatch.setattr(storage, "_get_gcs_client", lambda: Client())
    deleted.clear()
    assert storage.TempImages.sweep() == 1 and deleted == ["slides-tmp/a/p1.jpg"], "作りかけの古い物だけ消す"


def test_temp_images_are_not_available_without_cloud_storage(monkeypatch):
    from services import storage
    monkeypatch.setattr(storage, "using_gcs", lambda: False)
    host = storage.TempImages()
    assert host.put("p001.jpg", b"x") is None
    host.cleanup()
    assert storage.TempImages.sweep() == 0
