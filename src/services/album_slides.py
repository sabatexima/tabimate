"""思い出（旅の写真・付箋・ベストショット）を、写真が主役の Google スライドのアルバムにする。

しおりのスライド（slides_export.py）と同じ流れで、同じ部品（_Deck）を使う:
  1) layout(): 写真をどのページのどこに置くかを決める（純粋な関数）
  2) 写真を、置く枠の形に切り抜いて一時置き場に上げる（Google が URL から取りに来る）
  3) build_requests(): 枠と文字の要求を組み立てる（純粋な関数）
  4) create_album(): 2) と 3) をつないで、本人のドライブにスライドを作る

デザインの考え方（写真集・フォトブックから）:
  ・主役は写真に写っている人たち。キャラクター（ちゃむ）は出さない。飾りは控えめに
    （白いふち・マスキングテープを少し・紙の色）
  ・写真は撮った日ごとに、撮った順に並べる。日の最初のページに「1日目」と日付
  ・写真の縦横に合わせて並べ方を選ぶ（横長を縦の枠に押し込んで顔を切らない）。
    並べ方は「横一列」「上下2段」「大きな1枚＋縦に重ねた小さな写真」から、
    ページをいちばん広く使えるものを選ぶ。切り抜くときは上寄りに残す（顔が上にあることが多い）
  ・ページの枚数は「ページを広く使う」と「1枚を大きく見せる」の釣り合いで決める
  ・表紙は表紙に選んだ写真を大きく。横長なら全面に、縦長なら右半分に
  ・文字は画面と同じ Zen Maru Gothic、色もしおりと同じ（クリームの紙・金茶）

写真は撮ったままの大きさで保存されているので、そのままでは Google スライドの
上限（2500万画素）を超えることがある。置く枠の大きさに合わせて切り抜き・縮小した
JPEG を作ってから渡す（長辺1600pxまで）。向き（EXIF）もここで直す。
"""

import io
import math
import threading
import time
import zlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime

from logger import get_logger
from services.slides_export import (
    API, BASE_H, BASE_W, BLUSH, BORDER, EMU_PER_PT, GOLD, INK, LEAF, MUTED,
    SURFACE, WAVY, SlidesError, _clean, _Deck, _items, _line_height, _spaced, _width, _wrap_lines,
)

logger = get_logger("services.album_slides")

MAX_PHOTOS = 80          # アルバムに載せる写真の上限（多いときは旅全体からまんべんなく選ぶ）
MAX_PX = 1600            # 渡す写真の長辺（px）
PX_PER_PT = 2.4          # 枠1ptあたりの画素（全画面で見てもぼやけない程度）
WORK_QUALITY = 90        # 作業用（縮めただけ）の JPEG の画質
SLIDE_QUALITY = 85       # スライドに渡す JPEG の画質

PRINT = "#ffffff"        # 写真の白いふち
KRAFT = "#efe2bf"        # 生成りのマスキングテープ
QUOTE = "#e6d3a6"        # ベストショットの引用符（金茶を淡く）
_TAPES = (BLUSH, KRAFT, LEAF)
_WEEKDAYS = "月火水木金土日"

MAT = 4                  # 写真の白いふち（pt）
GUTTER = 14              # 写真と写真のあいだ（ふちの外どうし 6pt）
MIN_SIDE = 78            # これより小さな写真は作らない（pt）

# 写真を置く枠の縦横比の範囲（横/縦）。これを超える写真（パノラマなど）は切り抜く
_MIN_ASPECT, _MAX_ASPECT = 0.66, 1.78
# 並べ方に合わせて写真を少し切り抜いてよい範囲（縦横比を何倍まで変えてよいか）
_STRETCH = (0.87, 0.93, 1.0, 1.08, 1.16)

# ページの中で写真を置く場所（基準の 720×405pt で）
OPEN_BOX = (214, 40, 462, 325)     # 日の最初のページ（左に日付の欄）
GRID_BOX = (44, 42, 632, 328)      # 続きのページ

# ページの枚数を決める重み（下の _paginate_day を参照）
PAGE_COST = 0.22         # 1ページ増えるごとの重み（大きいほど1ページに詰める）
HERO_COST = 0.30         # 横長1枚を全面に出すページの重み（多用しない）
SMALL_COST = 0.10        # 小さな写真（短い辺が110pt未満）1枚ごとの重み


# ----------------------------------------------------------------------
# データの形
# ----------------------------------------------------------------------
@dataclass
class Photo:
    id: int
    aspect: float                 # 横/縦（向きを直したあと）
    taken: datetime | None = None


@dataclass
class Slot:
    """写真1枚を置く枠（基準の pt）。rot は中心まわりの角度。"""
    key: str
    photo_id: int
    x: float
    y: float
    w: float
    h: float
    rot: float = 0.0

    @property
    def aspect(self) -> float:
        return self.w / self.h

    @property
    def px(self) -> tuple:
        """渡す画像の大きさ（px）。長辺は MAX_PX まで。"""
        long_px = min(MAX_PX, math.ceil(max(self.w, self.h) * PX_PER_PT))
        if self.w >= self.h:
            return long_px, max(1, round(long_px / self.aspect))
        return max(1, round(long_px * self.aspect)), long_px


@dataclass
class Page:
    kind: str                     # cover / cover_split / best / opener / grid / hero / words / closing
    slots: list = field(default_factory=list)
    day: dict | None = None
    info: dict = field(default_factory=dict)


# ----------------------------------------------------------------------
# 日付まわり
# ----------------------------------------------------------------------
def _parse_dt(value) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).strip().replace("/", "-")[:19])
    except ValueError:
        return None


def _parse_date(value) -> date | None:
    dt = _parse_dt(value)
    return dt.date() if dt else None


def _md(d: date) -> str:
    return f"{d.month}月{d.day}日"


def _md_w(d: date) -> str:
    return f"{d.month}月{d.day}日（{_WEEKDAYS[d.weekday()]}）"


def _hm(dt: datetime | None) -> str:
    return f"{dt.hour}:{dt.minute:02d}" if dt else ""


def date_range(start: date | None, end: date | None) -> str:
    """「2026年8月14日 – 16日」の形。片方しか無ければその日だけ。"""
    if start and end and end < start:
        start, end = end, start
    start = start or end
    if not start:
        return ""
    if not end or end == start:
        return f"{start.year}年{_md_w(start)}"
    if (start.year, start.month) == (end.year, end.month):
        return f"{start.year}年{_md(start)} – {end.day}日"
    if start.year == end.year:
        return f"{start.year}年{_md(start)} – {_md(end)}"
    return f"{start.year}年{_md(start)} – {end.year}年{_md(end)}"


# ----------------------------------------------------------------------
# 写真の並べ方
# ----------------------------------------------------------------------
def _clamp(a: float, lo: float = _MIN_ASPECT, hi: float = _MAX_ASPECT) -> float:
    return max(lo, min(hi, a))


def _row(aspects, W, H, g):
    """横一列。高さをそろえて、幅いっぱい（入らなければ高さいっぱい）に。"""
    h = min(H, (W - g * (len(aspects) - 1)) / sum(aspects))
    total = sum(a * h for a in aspects) + g * (len(aspects) - 1)
    x, y, rects = (W - total) / 2, (H - h) / 2, []
    for a in aspects:
        rects.append((x, y, a * h, h))
        x += a * h + g
    return rects


def _rows2(aspects, k, W, H, g):
    """上下2段（上に k 枚）。各段を幅いっぱいにそろえ、入らなければ全体を縮める。"""
    top, bottom = aspects[:k], aspects[k:]
    h1 = (W - g * (len(top) - 1)) / sum(top)
    h2 = (W - g * (len(bottom) - 1)) / sum(bottom)
    s = min(1.0, (H - g) / (h1 + h2))
    h1, h2 = h1 * s, h2 * s
    y = (H - (h1 + h2 + g)) / 2
    rects = []
    for row, h in ((top, h1), (bottom, h2)):
        total = sum(a * h for a in row) + g * (len(row) - 1)
        x = (W - total) / 2
        for a in row:
            rects.append((x, y, a * h, h))
            x += a * h + g
        y += h + g
    return rects


def _big_and_column(aspects, W, H, g, big_first=True):
    """大きな1枚と、縦に重ねた小さな写真。読む順（左→右・上→下）が撮った順になるよう、
    大きな写真が左なら最初の1枚、右なら最後の1枚を大きくする。"""
    big = aspects[0] if big_first else aspects[-1]
    col = aspects[1:] if big_first else aspects[:-1]
    m = len(col)
    S = sum(1 / a for a in col)
    h = min(H, (W - g + g * (m - 1) / S) / (big + 1 / S))
    wc = (h - g * (m - 1)) / S
    total = big * h + g + wc
    x0, y0 = (W - total) / 2, (H - h) / 2
    big_rect_x = x0 if big_first else x0 + wc + g
    col_x = x0 + big * h + g if big_first else x0
    col_rects, y = [], y0
    for a in col:
        col_rects.append((col_x, y, wc, wc / a))
        y += wc / a + g
    big_rect = (big_rect_x, y0, big * h, h)
    return [big_rect] + col_rects if big_first else col_rects + [big_rect]


def _candidates(n: int, prefer_left: bool):
    """n 枚の並べ方の候補（関数, ひいきの点）。"""
    yield (lambda a, W, H, g: _row(a, W, H, g)), 0.0
    for k in range(1, n):
        yield (lambda a, W, H, g, k=k: _rows2(a, k, W, H, g)), 0.0
    if n >= 3:
        yield (lambda a, W, H, g: _big_and_column(a, W, H, g, True)), 0.01 if prefer_left else 0.0
        yield (lambda a, W, H, g: _big_and_column(a, W, H, g, False)), 0.0 if prefer_left else 0.01


def arrange(aspects: list, box: tuple, prefer_left: bool = True):
    """写真の縦横比の並びを、箱 (x, y, w, h) にいちばん広く収める並べ方を選ぶ。

    返り値: (点数, [(x, y, w, h), …]) 。点数は「箱のうち写真が占める割合」から、
    切り抜きの大きさのぶんを引いたもの。小さすぎる写真ができる並べ方は選ばない
    （どれも駄目なら None）。
    """
    bx, by, W, H = box
    base = [_clamp(a) for a in aspects]
    best = None
    for make, bonus in _candidates(len(base), prefer_left):
        for m in _STRETCH:
            a = [_clamp(v * m, 0.6, 2.0) for v in base]
            rects = make(a, W, H, GUTTER)
            if min(min(w, h) for _, _, w, h in rects) < MIN_SIDE:
                continue
            cover = sum(w * h for _, _, w, h in rects) / (W * H)
            crop = max(abs(math.log((w / h) / b)) for (_, _, w, h), b in zip(rects, base))
            score = cover - 0.35 * crop + bonus
            if best is None or score > best[0]:
                best = (score, [(bx + x, by + y, w, h) for x, y, w, h in rects])
    return best


def _page_cost(chunk: list, box: tuple, prefer_left: bool):
    """1ページぶんの重み（小さいほど良い）と並べ方。"""
    got = arrange([p.aspect for p in chunk], box, prefer_left)
    if not got:
        return None
    score, rects = got
    small = sum(1 for _, _, w, h in rects if min(w, h) < 110)
    return PAGE_COST + (1 - score) + SMALL_COST * small, rects


def _paginate_day(photos: list, opener: bool = True) -> list:
    """1日ぶんの写真をページに分ける。[("opener"|"grid"|"hero", [写真], [枠]) …] を返す。

    日の最初のページ（左に日付）は1〜3枚、続きのページは1〜4枚。「ページの重み」の
    合計がいちばん小さくなる分け方を、後ろから順に求める（動的計画法）。
    続きのページの横長1枚は、全面に出す（HERO_COST の重みで、多用はしない）。
    opener=False なら、日の頭のページを作らずに続きのページだけで並べる。
    """
    n = len(photos)
    if not n:
        return []
    memo: dict = {}

    def rest(i: int):
        """photos[i:] を続きのページに並べたときの (重み, ページ) 。"""
        if i == n:
            return 0.0, []
        if i in memo:
            return memo[i]
        best = None
        for k in range(1, min(4, n - i) + 1):
            chunk = photos[i:i + k]
            if k == 1 and chunk[0].aspect >= 1.2:
                cost, page = PAGE_COST + HERO_COST, ("hero", chunk, None)
            else:
                got = _page_cost(chunk, GRID_BOX, prefer_left=(i % 2 == 0))
                if not got:
                    continue
                cost, page = got[0], ("grid", chunk, got[1])
            tail_cost, tail = rest(i + k)
            if best is None or cost + tail_cost < best[0]:
                best = (cost + tail_cost, [page] + tail)
        memo[i] = best or (99.0, [("grid", photos[i:i + 1],
                                   _row([_clamp(photos[i].aspect)], GRID_BOX[2], GRID_BOX[3], GUTTER))])
        return memo[i]

    if not opener:
        return rest(0)[1]
    best = None
    for k in range(1, min(3, n) + 1):
        got = _page_cost(photos[:k], OPEN_BOX, prefer_left=True)
        if not got:
            continue
        tail_cost, tail = rest(k)
        if best is None or got[0] + tail_cost < best[0]:
            best = (got[0] + tail_cost, [("opener", photos[:k], got[1])] + tail)
    if best is None:   # どう並べても小さすぎる（とても細長い写真など）。1枚ずつ置く
        x, y, W, H = OPEN_BOX
        rects = [(x + rx, y + ry, rw, rh) for rx, ry, rw, rh in _row([_clamp(photos[0].aspect)], W, H, GUTTER)]
        best = (0, [("opener", photos[:1], rects)] + rest(1)[1])
    return best[1]


HERO_MIN_DAY = 9         # この枚数以上の日は、まん中あたりの横長1枚を全面に出す


def _day_pages(photos: list, featured: set) -> list:
    """1日ぶんのページ。写真の多い日は、まん中あたりの横長の1枚を全面のページにして
    流れに緩急をつける（表紙・ベストショットに使った写真は選ばない）。"""
    n = len(photos)
    if n >= HERO_MIN_DAY:
        mid = (n - 1) / 2
        picks = [i for i in range(n // 4, n - n // 4)
                 if photos[i].aspect >= 1.25 and photos[i].id not in featured]
        if picks:
            i = min(picks, key=lambda j: (abs(j - mid), j))
            return (_paginate_day(photos[:i]) + [("hero", [photos[i]], None)]
                    + _paginate_day(photos[i + 1:], opener=False))
    return _paginate_day(photos)


def select_photos(photos: list, cap: int = MAX_PHOTOS, keep=()) -> list:
    """多すぎるときは、撮った順の旅全体からまんべんなく cap 枚を選ぶ。keep の写真は残す。"""
    if len(photos) <= cap:
        return list(photos)
    idx = {round(i * (len(photos) - 1) / (cap - 1)) for i in range(cap)}
    for pid in keep:
        pos = next((i for i, p in enumerate(photos) if p.id == pid), None)
        if pos is not None and pos not in idx:
            # いちばん近い選ばれた1枚と入れ替える
            idx.remove(min(idx, key=lambda i: abs(i - pos)))
            idx.add(pos)
    return [photos[i] for i in sorted(idx)]


def _days(photos: list, start: date | None) -> list:
    """撮った日ごとに分ける。[(日の情報, [写真]) …]。日付の無い写真は最後にまとめる。"""
    dated = sorted((p for p in photos if p.taken), key=lambda p: (p.taken, p.id))
    undated = [p for p in photos if not p.taken]
    groups: dict = {}
    for p in dated:
        groups.setdefault(p.taken.date(), []).append(p)
    first = min(groups) if groups else None
    # 出発日から数える（初日に写真が無くても「2日目」から）。写真が出発日より前なら
    # （カメラの時計ずれなど）出発日は使わず、写真の最初の日から数える
    base = start if (start and first and start <= first) else first
    multi = len(groups) > 1 or (base is not None and base != first)
    out = []
    for d, ps in sorted(groups.items()):
        times = [p.taken for p in ps if p.taken.time() != datetime.min.time()]
        span = ""
        if times:
            lo, hi = _hm(min(times)), _hm(max(times))
            span = lo if lo == hi else f"{lo} – {hi}"
        out.append(({"label": f"{(d - base).days + 1}日目" if multi else "",
                     "date": d, "span": span, "count": len(ps)}, ps))
    if undated:
        out.append(({"label": "", "date": None, "span": "", "count": len(undated)}, undated))
    return out


def _fit_box(aspect: float, max_w: float, max_h: float) -> tuple:
    """縦横比 aspect の箱を、max_w × max_h に収まるいちばん大きな大きさで。"""
    if aspect >= max_w / max_h:
        return max_w, max_w / aspect
    return max_h * aspect, max_h


def layout(album: dict, photos: list) -> list:
    """ページの並びと、写真を置く枠を決める。photos は撮った順の Photo。"""
    by_id = {p.id: p for p in photos}
    best = [b for b in (album.get("best") or []) if isinstance(b, dict) and b.get("photo_id") in by_id][:3]
    cover_id = album.get("cover_photo_id")
    if cover_id not in by_id:
        cover_id = (best[0]["photo_id"] if best else None) or next(
            (p.id for p in photos if p.aspect >= 1.2), photos[0].id)
    selected = select_photos(photos, keep=[cover_id] + [b["photo_id"] for b in best])
    pages: list = []
    n = 0

    def key():
        nonlocal n
        n += 1
        return f"p{n:03d}"

    # 表紙: 横長なら全面、縦長なら右半分
    cover = by_id[cover_id]
    if cover.aspect >= 1.15:
        pages.append(Page("cover", [Slot(key(), cover.id, 0, 0, BASE_W, BASE_H)]))
    else:
        pages.append(Page("cover_split", [Slot(key(), cover.id, 396, 0, BASE_W - 396, BASE_H)]))

    # ベストショット: 白いふちの写真を少し傾けて
    for b in best:
        p = by_id[b["photo_id"]]
        w, h = _fit_box(_clamp(p.aspect, 0.75, 1.5), 330, 268)
        cx, cy = 232, 196
        pages.append(Page("best", [Slot(key(), p.id, cx - w / 2, cy - h / 2 - 14, w, h, rot=-2.0)],
                          info={"reason": b.get("reason") or "", "taken": p.taken,
                                "frame": (cx, cy, w + 24, h + 24 + 36)}))

    # 日ごとのページ
    featured = {cover_id} | {b["photo_id"] for b in best}
    for day, ps in _days(selected, _parse_date(album.get("start_date"))):
        for kind, chunk, rects in _day_pages(ps, featured):
            if kind == "hero":
                slots = [Slot(key(), chunk[0].id, 0, 0, BASE_W, BASE_H)]
                info = {"taken": chunk[0].taken}
            else:
                slots = [Slot(key(), p.id, *r) for p, r in zip(chunk, rects)]
                info = {}
            pages.append(Page(kind, slots, day=day, info=info))

    # 旅のことば（付箋）
    words = _items(album.get("stickers"))[:12]   # None や空は落とす（「None」と出さない）
    if words:
        per = math.ceil(len(words) / math.ceil(len(words) / 6))
        for i in range(0, len(words), per):
            pages.append(Page("words", info={"words": words[i:i + per], "first": i == 0}))

    # おわり: 旅全体から数枚を、白いふちの写真で並べる
    pages.append(Page("closing", _closing_slots(selected, cover_id, featured, key),
                      info={"total": len(photos), "shown": len(selected)}))
    return pages


CLOSING_PH = 118         # おわりのページの写真の高さ（pt）


def _closing_slots(photos: list, cover_id, featured: set, key) -> list:
    """おわりのページの写真（最大4枚・旅全体からまんべんなく）。表紙の写真は使わず、
    ベストショットもなるべく避ける（写真が表紙の1枚だけなら、写真なしで文字だけにする）。"""
    pool = ([p for p in photos if p.id not in featured]
            or [p for p in photos if p.id != cover_id])
    if not pool:
        return []
    pad, gap = 8, 22
    fits = None
    for count in range(min(4, len(pool)), 0, -1):
        picks = ([pool[round(i * (len(pool) - 1) / (count - 1))] for i in range(count)]
                 if count > 1 else [pool[len(pool) // 2]])
        for ph in (CLOSING_PH, CLOSING_PH * 0.88):
            sizes = [(_clamp(p.aspect, 0.75, 1.34) * ph, ph) for p in picks]
            total = sum(w + pad * 2 for w, _ in sizes) + gap * (len(sizes) - 1)
            if total <= BASE_W - 2 * 56:
                fits = picks, sizes, total
                break
        if fits:
            break
    picks, sizes, total = fits
    x = (BASE_W - total) / 2
    tilts = (-4.0, 3.0, -2.5, 4.5)
    slots = []
    for i, (p, (w, h)) in enumerate(zip(picks, sizes)):
        cx = x + pad + w / 2
        slots.append(Slot(key(), p.id, cx - w / 2, 66 + (CLOSING_PH - h) / 2, w, h, rot=tilts[i % len(tilts)]))
        x += w + pad * 2 + gap
    return slots


def all_slots(pages: list) -> list:
    return [s for page in pages for s in page.slots]


# ----------------------------------------------------------------------
# 写真の下ごしらえ（Pillow）
# ----------------------------------------------------------------------
def working_copy(data: bytes):
    """撮ったままの写真から、向きを直して長辺 MAX_PX に縮めた作業用 JPEG と縦横比を返す。

    JPEG は読み込みの段階で縮めて読む（draft）ので、原寸を丸ごと展開しない。
    開けない写真は None。
    """
    from PIL import Image, ImageOps
    try:
        img = Image.open(io.BytesIO(data))
        raw_w, raw_h = img.size
        s = MAX_PX / max(raw_w, raw_h)
        if s < 1:
            img.draft("RGB", (max(1, int(raw_w * s)), max(1, int(raw_h * s))))
        img = ImageOps.exif_transpose(img)
        if img.mode != "RGB":
            img = img.convert("RGB")
        img.thumbnail((MAX_PX, MAX_PX))
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=WORK_QUALITY)
        return out.getvalue(), img.width / img.height
    except Exception:
        logger.warning("アルバム用に写真を開けませんでした", exc_info=True)
        return None


def render_crop(work: bytes, slot: Slot) -> bytes:
    """作業用の写真を、枠の縦横比に切り抜いて枠の大きさに縮める。

    縦を切るときは上寄りに残す（人の顔は上の方にあることが多い）。拡大はしない。
    """
    from PIL import Image
    img = Image.open(io.BytesIO(work))
    w, h = img.size
    a = slot.aspect
    if w / h > a:
        nw = h * a
        left = (w - nw) / 2
        box = (round(left), 0, round(left + nw), h)
    else:
        nh = w / a
        top = (h - nh) * 0.4
        box = (0, round(top), w, round(top + nh))
    img = img.crop(box)
    tw, th = slot.px
    if tw < img.width:
        img = img.resize((tw, max(1, round(tw * img.height / img.width))), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=SLIDE_QUALITY, optimize=True, progressive=True)
    return out.getvalue()


# ----------------------------------------------------------------------
# スライドの要求
# ----------------------------------------------------------------------
class _AlbumDeck(_Deck):
    """しおりの部品に、写真と「最後に手前へ出す物」の記録を足したもの。"""

    def __init__(self, page_w_pt, page_h_pt, urls):
        super().__init__(page_w_pt, page_h_pt)
        self.urls = urls or {}
        self.front: list = []      # [(ページ, [手前に出す物の ID])]（写真より上に重ねる物）

    def photo(self, page, slot: Slot, mat=True):
        """写真を置く。白いふちは先に（写真の下に）描く。URL が無ければふちだけ残る。"""
        if mat:
            if slot.rot:
                self.shape(page, "RECTANGLE", 0, 0, 0, 0, fill=PRINT, outline=BORDER, weight=0.5,
                           element=self._rotated(page, slot.x + slot.w / 2, slot.y + slot.h / 2,
                                                 slot.w + MAT * 2, slot.h + MAT * 2, slot.rot))
            else:
                self.shape(page, "RECTANGLE", slot.x - MAT, slot.y - MAT, slot.w + MAT * 2,
                           slot.h + MAT * 2, fill=PRINT, outline=BORDER, weight=0.5)
        url = self.urls.get(slot.key)
        if not url:
            return
        element = (self._rotated(page, slot.x + slot.w / 2, slot.y + slot.h / 2, slot.w, slot.h, slot.rot)
                   if slot.rot else self._box(page, slot.x, slot.y, slot.w, slot.h))
        self.image_requests.append({"createImage": {
            "objectId": self._id("photo"), "url": url, "elementProperties": element}})

    def on_top(self, page, *ids):
        ids = [i for i in ids if i]
        if ids:
            self.front.append((page, ids))

    def tape_on(self, page, cx, cy, w=70, h=18, color=BLUSH, degrees=-6) -> str:
        return self.shape(page, "RECTANGLE", 0, 0, w, h, fill=color, alpha=0.88,
                          element=self._rotated(page, cx, cy, w, h, degrees))

    def rotated_text(self, page, cx, cy, w, h, deg, text, **kw) -> str:
        oid = self.shape(page, "TEXT_BOX", 0, 0, w, h, element=self._rotated(page, cx, cy, w, h, deg))
        self.text(oid, text, **kw)
        return oid

    def zorder_requests(self) -> list:
        """写真を貼ったあとで、テープや文字の札を写真より手前に出す（ページごとに1つ）。"""
        merged: dict = {}
        for page, ids in self.front:
            merged.setdefault(page, []).extend(ids)
        return [{"updatePageElementsZOrder": {"pageElementObjectIds": ids, "operation": "BRING_TO_FRONT"}}
                for ids in merged.values()]


def _lines(text: str, width: float, size: float) -> int:
    """幅 width の箱で何行になるか。1行にゆったり入る行は1行と数える
    （折り返しの見積もりは禁則のぶん控えめなので、短い題名まで2行と数えてしまうため）。"""
    room = width - 14.4
    total = 0
    for line in text.split("\n"):
        if _width(line) * size <= room * 0.95:
            total += 1
        else:
            total += _wrap_lines(line, max(1.0, room / size * 0.9))
    return total


def _fit(text: str, width: float, max_h: float, sizes, spacing=135) -> tuple:
    """幅 width・高さ max_h に収まる文字の大きさを選ぶ。最小でも入らなければ「…」で切る。"""
    def h_of(t, size):
        return _lines(t, width, size) * _line_height(size, spacing)
    for size in sizes:
        if h_of(text, size) <= max_h:
            return text, size, h_of(text, size)
    size = sizes[-1]
    while len(text) > 1 and h_of(text + "…", size) > max_h:
        text = text[:-1]
    text = text.rstrip("、。 　") + "…"
    return text, size, h_of(text, size)


# 行の頭に来てはいけない字（禁則）と、行の終わりに来てはいけない字
_NO_HEAD = set("、。，．・：；！？!?」』）)]】〉》ー〜…ぁぃぅぇぉっゃゅょゎんァィゥェォッャュョヮン々")
_NO_TAIL = set("「『（([【〈《")


def _kind(c: str) -> str:
    if "\u3040" <= c <= "\u309f":
        return "hira"
    if "\u30a0" <= c <= "\u30ff":
        return "kata"
    if "\u4e00" <= c <= "\u9fff" or c == "々":
        return "kanji"
    return "other"


def _break_cost(prev: str, nxt: str) -> float:
    """prev と nxt のあいだで行を分けたときの読みにくさ（0 がいちばん自然）。

    辞書は使わない。句読点のあと・ひらがなから漢字/カタカナに変わる所（「ずっと|聞こえて」
    「池は|本当に」）は言葉の切れ目であることが多い。助詞らしいひらがなのあとは次に良い。
    """
    if prev in "、。！？!?」』）)":
        return 0.0
    if _kind(prev) == "hira" and _kind(nxt) in ("kanji", "kata"):
        return 0.1
    if prev in "がをにではのともへや" and _kind(nxt) == "hira":
        return 0.45
    return 1.0


def _balance(text: str, width: float, size: float) -> str:
    """2行になる文を、ちょうどよい所で2行に分ける（最後の行に1〜2字だけ残さない）。

    句読点や助詞のあとを選び、無ければまん中で。1行に入るもの・3行以上になるものは
    そのまま（Slides の折り返しに任せる）。
    """
    per_line = (width - 14.4) / size * 0.9
    total = _width(text)
    if "\n" in text or _lines(text, width, size) != 2:
        return text
    best, best_cost = None, None
    for i in range(1, len(text)):
        head, tail = text[:i], text[i:]
        if tail[0] in _NO_HEAD or head[-1] in _NO_TAIL or head[-1] == " " or tail[0] == " ":
            continue
        # 英数字の途中では切らない
        if head[-1].isascii() and head[-1].isalnum() and tail[0].isascii() and tail[0].isalnum():
            continue
        if _width(head) > per_line or _width(tail) > per_line:
            continue
        cost = abs(_width(head) - total / 2) / max(1.0, total / 2) + _break_cost(head[-1], tail[0])
        if best_cost is None or cost < best_cost:
            best, best_cost = i, cost
    return text if best is None else text[:best] + "\n" + text[best:]


def _meta_line(album: dict, photos_total: int, photos: list) -> str:
    start, end = _parse_date(album.get("start_date")), _parse_date(album.get("end_date"))
    if not start and not end:
        taken = sorted(p.taken.date() for p in photos if p.taken)
        if taken:
            start, end = taken[0], taken[-1]
    parts = [date_range(start, end), f"写真 {photos_total}枚"]
    return "　·　".join(p for p in parts if p)


def _title(album: dict) -> str:
    return _clean(album.get("title") or "", one_line=True).strip() or "旅の思い出"


def _cover(deck: _AlbumDeck, page: Page, album: dict, meta: str):
    sid = deck.slide()
    slot = page.slots[0]
    deck.photo(sid, slot, mat=False)
    title = _title(album)
    if page.kind == "cover":
        # 全面の写真に、紙の札を貼る（札・テープ・文字は写真より手前に出す）
        # 札の幅は題名と日付の長さに合わせる（写真をなるべく隠さない）
        # （折り返しの見積もりと同じく1割の余裕を見て、1行に入るなら1行にする）
        cw = min(360, max(250, _width(title) * 26 / 0.95 + 64, _width(meta) * 10 / 0.95 + 64))
        inner = cw - 48
        title_t, size, th = _fit(title, inner, 3 * _line_height(26, 120) + 2, (26, 22, 19), spacing=120)
        title_t = _balance(title_t, inner, size)
        ch = 24 + 18 + 6 + th + 10 + 18 + 22
        cx, cy = 40, BASE_H - 34 - ch
        card = deck.shape(sid, "RECTANGLE", cx, cy, cw, ch, fill=SURFACE, alpha=0.95)
        tape = deck.tape_on(sid, cx + 64, cy + 2, color=BLUSH, degrees=deck.tilt(4, 8))
        k = deck.label(sid, cx + 24, cy + 22, inner, 18, _spaced("思い出のアルバム"), size=9.5, color=GOLD, bold=True)
        t = deck.label(sid, cx + 24, cy + 22 + 22, inner, th, title_t, size=size, bold=True, line_spacing=120)
        m = deck.label(sid, cx + 24, cy + 22 + 22 + th + 8, inner, 18, meta, size=10, color=MUTED)
        deck.on_top(sid, card, tape, k, t, m)
        return
    # 縦長の写真は右半分に。左のクリームの紙に題名
    inner = 300
    title_t, size, th = _fit(title, inner, 4 * _line_height(30, 120) + 2, (30, 26, 22), spacing=120)
    title_t = _balance(title_t, inner, size)
    group = 18 + 14 + th + 18 + 18
    top = (BASE_H - group) / 2
    deck.blob(sid, -40, 300, 200, 130, color=LEAF, alpha=0.45)
    deck.label(sid, 48, top, inner, 18, _spaced("思い出のアルバム"), size=9.5, color=GOLD, bold=True)
    deck.label(sid, 48, top + 32, inner, th, title_t, size=size, bold=True, line_spacing=120)
    deck.line(sid, 56, top + 32 + th + 8, 44, 0, color=WAVY)
    deck.label(sid, 48, top + 32 + th + 18, inner + 20, 18, meta, size=10, color=MUTED)


def _rot(dx, dy, deg):
    t = math.radians(deg)
    return dx * math.cos(t) - dy * math.sin(t), dx * math.sin(t) + dy * math.cos(t)


def _best(deck: _AlbumDeck, page: Page):
    sid = deck.slide()
    slot = page.slots[0]
    cx, cy, fw, fh = page.info["frame"]
    deck.shape(sid, "RECTANGLE", 0, 0, 0, 0, fill=PRINT, outline=BORDER, weight=0.5,
               element=deck._rotated(sid, cx, cy, fw, fh, slot.rot))
    deck.photo(sid, slot, mat=False)
    taken = page.info.get("taken")
    when = (f"{_md_w(taken.date())}　{_hm(taken)}" if taken and taken.time() != datetime.min.time()
            else _md_w(taken.date()) if taken else "")
    if when:
        # ふちの下の余白に、撮った日時を（写真と同じ角度で）
        dx, dy = _rot(0, fh / 2 - 19, slot.rot)
        deck.rotated_text(sid, cx + dx, cy + dy, fw - 24, 22, slot.rot, when, size=9.5, color=MUTED,
                          align="CENTER", line_spacing=100)
    tx, ty = _rot(0, -fh / 2 + 2, slot.rot)
    deck.on_top(sid, deck.tape_on(sid, cx + tx, cy + ty, w=84, h=20, color=KRAFT,
                                  degrees=slot.rot + deck.tilt(3, 6)))

    x, w = 440, 236
    reason = _clean(page.info.get("reason") or "").strip()
    reason, size, rh = _fit(reason, w, 190, (15, 13.5, 12), spacing=165) if reason else ("", 15, 0)
    reason = _balance(reason, w, size)
    group = 40 + 26 + (rh + 14 if reason else 0)
    top = (BASE_H - group) / 2
    deck.label(sid, x - 4, top - 18, 60, 56, "“", size=54, color=QUOTE, bold=True, line_spacing=100)
    deck.label(sid, x, top + 40, w, 18, _spaced("ベストショット"), size=10, color=GOLD, bold=True)
    if reason:
        deck.label(sid, x, top + 66, w, rh, reason, size=size, line_spacing=165)


def _day_head(day: dict) -> str:
    parts = [day["label"], _md_w(day["date"]) if day["date"] else "日付のない写真"]
    return "　·　".join(p for p in parts if p)


def _opener(deck: _AlbumDeck, page: Page, tape_color: str):
    sid = deck.slide()
    day = page.day
    x, w = 44, 156
    if day["date"]:
        heading, sub = _md(day["date"]), f"{_WEEKDAYS[day['date'].weekday()]}曜日"
        h_size = 30
    else:
        heading, sub, h_size = "日付のない写真", "", 17
    notes = [f"写真 {day['count']}枚"] + ([day["span"]] if day["span"] else [])
    group = (24 if day["label"] else 0) + 40 + (22 if sub else 0) + 18 + 18 * len(notes)
    top = (BASE_H - group) / 2
    y = top
    if day["label"]:
        deck.label(sid, x, y, w, 18, _spaced(day["label"]), size=10, color=GOLD, bold=True)
        y += 24
    deck.label(sid, x, y, w, 40, heading, size=h_size, bold=True, line_spacing=100)
    y += 40
    if sub:
        deck.label(sid, x, y, w, 20, sub, size=11.5, color=MUTED)
        y += 22
    deck.line(sid, x + 8, y + 8, 40, 0, color=WAVY)
    y += 18
    for note in notes:
        deck.label(sid, x, y, w, 18, note, size=10, color=MUTED)
        y += 18
    for slot in page.slots:
        deck.photo(sid, slot)
    first = page.slots[0]
    deck.on_top(sid, deck.tape_on(sid, first.x + first.w / 2, first.y - 2, color=tape_color,
                                  degrees=deck.tilt(3, 7)))


def _grid(deck: _AlbumDeck, page: Page):
    sid = deck.slide()
    deck.label(sid, 44, 12, 520, 20, _day_head(page.day), size=9, color=MUTED)
    for slot in page.slots:
        deck.photo(sid, slot)


def _hero(deck: _AlbumDeck, page: Page):
    sid = deck.slide()
    deck.photo(sid, page.slots[0], mat=False)
    text = "　·　".join(p for p in (_day_head(page.day), _hm(page.info.get("taken"))) if p)
    w = _width(text) * 9 + 30
    tag = deck.shape(sid, "RECTANGLE", 36, BASE_H - 30 - 24, w, 24, fill=SURFACE, alpha=0.92)
    label = deck.label(sid, 36 + 8, BASE_H - 30 - 24 + 1, w - 10, 22, text, size=9, color=INK)
    deck.on_top(sid, tag, label)


def _words(deck: _AlbumDeck, page: Page):
    sid = deck.slide()
    deck.label(sid, 44, 26, 400, 20, _spaced("旅のことば"), size=10, color=GOLD, bold=True)
    if page.info.get("first"):
        deck.label(sid, 44, 44, 600, 20, "写真から、旅の空気をことばにしました", size=10, color=MUTED)
    words = page.info["words"]
    nw, nh, gap = 190, 100, 24
    # 4枚なら 2+2、5枚なら 3+2（1枚だけの段を作らない）
    half = math.ceil(len(words) / 2)
    rows = [words[:half], words[half:]] if len(words) > 3 else [words]
    total_h = len(rows) * nh + (len(rows) - 1) * (gap + 6)
    y = 82 + (BASE_H - 30 - 82 - total_h) / 2
    i = 0
    for row in rows:
        total_w = len(row) * nw + (len(row) - 1) * gap
        x = (BASE_W - total_w) / 2
        for text in row:
            cx, cy = x + nw / 2, y + nh / 2
            deg = deck.tilt(1, 3)
            deck.shape(sid, "RECTANGLE", 0, 0, 0, 0, fill=SURFACE, outline=BORDER, weight=0.75,
                       element=deck._rotated(sid, cx, cy, nw, nh, deg))
            t, size, th = _fit(text, nw - 28, nh - 30, (13, 12, 11), spacing=140)
            t = _balance(t, nw - 28, size)
            deck.rotated_text(sid, cx, cy + 3, nw - 28, th + 8, deg, t, size=size, align="CENTER",
                              line_spacing=140)
            tx, ty = _rot(0, -nh / 2, deg)
            deck.tape_on(sid, cx + tx, cy + ty, w=58, h=16, color=_TAPES[i % len(_TAPES)],
                         degrees=deg + deck.tilt(3, 8))
            i += 1
            x += nw + gap
        y += nh + gap + 6


def _closing(deck: _AlbumDeck, page: Page, album: dict, meta: str):
    sid = deck.slide()
    pad, bottom = 8, 26
    for i, slot in enumerate(page.slots):
        cx, cy = slot.x + slot.w / 2, slot.y + slot.h / 2
        dx, dy = _rot(0, (bottom - pad) / 2, slot.rot)
        deck.shape(sid, "RECTANGLE", 0, 0, 0, 0, fill=PRINT, outline=BORDER, weight=0.5,
                   element=deck._rotated(sid, cx + dx, cy + dy, slot.w + pad * 2, slot.h + pad + bottom, slot.rot))
        deck.photo(sid, slot, mat=False)
        if i % 2 == 0:
            tx, ty = _rot(0, -slot.h / 2 - pad, slot.rot)
            deck.on_top(sid, deck.tape_on(sid, cx + tx, cy + ty, w=54, h=15, color=_TAPES[(i // 2) % 3],
                                          degrees=slot.rot + deck.tilt(4, 9)))
    y = 66 + CLOSING_PH + 26 + 40 if page.slots else 140
    deck.label(sid, 60, y, BASE_W - 120, 46, "おかえりなさい", size=30, bold=True, align="CENTER",
               line_spacing=100)
    title, size, th = _fit(_title(album), BASE_W - 200, 20, (12, 11), spacing=120)
    deck.label(sid, 100, y + 52, BASE_W - 200, 20, title, size=size, color=INK, align="CENTER")
    deck.label(sid, 100, y + 74, BASE_W - 200, 18, meta, size=9.5, color=MUTED, align="CENTER")
    if page.info.get("shown", 0) < page.info.get("total", 0):
        deck.label(sid, 100, y + 94, BASE_W - 200, 18,
                   f"全{page.info['total']}枚から {page.info['shown']}枚を選んで載せています",
                   size=8.5, color=MUTED, align="CENTER")
    deck.label(sid, 100, 372, BASE_W - 200, 18, "たびメイトでつくったアルバム", size=8, color=MUTED, align="CENTER")


def build_requests(album: dict, photos: list, pages: list, urls=None, page_size=None,
                   delete_slide=None) -> tuple:
    """(本体の要求, 写真の要求, 重ね順の要求) を作る。urls は 枠の key → 写真の公開URL。"""
    w_pt, h_pt = BASE_W, BASE_H
    if page_size:
        try:
            w_pt = page_size["width"]["magnitude"] / EMU_PER_PT
            h_pt = page_size["height"]["magnitude"] / EMU_PER_PT
        except (KeyError, TypeError, ZeroDivisionError):
            pass
    deck = _AlbumDeck(w_pt, h_pt, urls)
    deck.rng.seed(zlib.crc32(f"{album.get('id')}:{album.get('title')}".encode("utf-8")))
    meta = _meta_line(album, len(photos), photos)
    openers = 0
    for page in pages:
        if page.kind in ("cover", "cover_split"):
            _cover(deck, page, album, meta)
        elif page.kind == "best":
            _best(deck, page)
        elif page.kind == "opener":
            _opener(deck, page, _TAPES[openers % len(_TAPES)])
            openers += 1
        elif page.kind == "grid":
            _grid(deck, page)
        elif page.kind == "hero":
            _hero(deck, page)
        elif page.kind == "words":
            _words(deck, page)
        elif page.kind == "closing":
            _closing(deck, page, album, meta)
    if delete_slide:
        deck.requests.append({"deleteObject": {"objectId": delete_slide}})
    return deck.requests, deck.image_requests, deck.zorder_requests()


# ----------------------------------------------------------------------
# Google スライドに作る
# ----------------------------------------------------------------------
class _Counter:
    """並列の作業から数える（済んだ数を1つずつ増やして返す）。"""

    def __init__(self):
        self._n = 0
        self._lock = threading.Lock()

    def next(self) -> int:
        with self._lock:
            self._n += 1
            return self._n


def _parallel(fn, items, workers):
    if not items:
        return []
    with ThreadPoolExecutor(max_workers=min(workers, len(items))) as ex:
        return list(ex.map(fn, items))


_IMAGE_CALLS = 30         # 写真を貼る要求の回数の上限（Slides API は1分60回まで）


def _insert_images(http, url, headers, images: list, budget: list) -> int:
    """写真を貼る。1枚でも取りに来られないと要求ごと失敗するので、失敗したら半分に分けて
    貼り直す（取りに来られない写真だけを落とす）。貼れた枚数を返す。

    混み合い（429）や Google 側の不調（5xx）は写真のせいではないので、分けずに一度だけ
    少し待って送り直す。budget（残りの回数）を使い切ったら、それ以上は送らない。
    """
    if not images or budget[0] <= 0:
        return 0
    status = None
    for attempt in range(2):
        budget[0] -= 1
        try:
            r = http.post(url, json={"requests": images}, headers=headers, timeout=180)
            status = r.status_code
            if status == 200:
                return len(images)
            logger.warning("写真を貼れませんでした（%d枚）: %s %s", len(images), status, r.text[:300])
        except Exception:
            logger.warning("写真を貼れませんでした（%d枚）", len(images), exc_info=True)
            status = None
        if status not in (429, 500, 502, 503) or attempt or budget[0] <= 0:
            break
        time.sleep(2)
    if len(images) == 1 or status in (429, 500, 502, 503):
        return 0
    half = len(images) // 2
    return (_insert_images(http, url, headers, images[:half], budget)
            + _insert_images(http, url, headers, images[half:], budget))


def create_album(access_token: str, album: dict, read_photo, host, http=None, progress=None) -> str:
    """本人のドライブにアルバムのスライドを作り、開くためのURLを返す。

    album: {"id", "title", "start_date", "end_date", "cover_photo_id",
            "best": [{"photo_id", "reason"}], "stickers": [文字列],
            "photos": [{"id", "taken_at", …}]}（photos は撮った順）
    read_photo(写真の dict) → 撮ったままのバイト列（読めなければ None）
    host: put(名前, バイト列) → 公開URL（置けなければ None）と cleanup() を持つ一時置き場
    progress(ことば, 済んだ数, 全部の数): 進み具合を知らせる（任意）
    """
    if http is None:
        import requests as http
    tell = progress or (lambda *a: None)
    raw = [p for p in (album.get("photos") or []) if p.get("id") is not None]
    if not raw:
        raise SlidesError("この旅にはまだ写真がありません。")

    # 1) 写真を読み、向きを直して縮める（多すぎるときは先に選んでおく）
    rough = select_photos([Photo(p["id"], 1.0, _parse_dt(p.get("taken_at"))) for p in raw],
                          keep=[album.get("cover_photo_id")] + [b.get("photo_id") for b in album.get("best") or []])
    wanted = {p.id for p in rough}
    todo = [p for p in raw if p["id"] in wanted]
    counter = _Counter()
    tell("写真を読み込んでいます", 0, len(todo))

    def prepare(p):
        data = read_photo(p)
        got = working_copy(data) if data else None
        tell("写真を読み込んでいます", counter.next(), len(todo))
        return p, got

    works, photos = {}, []
    for p, got in _parallel(prepare, todo, workers=3):
        if got:
            works[p["id"]] = got[0]
            photos.append(Photo(p["id"], got[1], _parse_dt(p.get("taken_at"))))
    if not photos:
        raise SlidesError("写真を読み込めませんでした。")
    photos.sort(key=lambda p: (p.taken is None, p.taken or datetime.min, p.id))

    # 2) ページを決めて、枠の形に切り抜いた写真を一時置き場へ
    pages = layout(album, photos)
    slots = all_slots(pages)
    counter = _Counter()
    tell("写真をアルバムの形に整えています", 0, len(slots))

    def upload(slot):
        try:
            url = host.put(f"{slot.key}.jpg", render_crop(works[slot.photo_id], slot))
        except Exception:
            logger.warning("アルバムの写真を用意できませんでした: %s", slot.key, exc_info=True)
            url = None
        tell("写真をアルバムの形に整えています", counter.next(), len(slots))
        return slot.key, url

    try:
        urls = {k: u for k, u in _parallel(upload, slots, workers=4) if u}
        if not urls:
            logger.warning("アルバムの写真を置ける場所がありません（Cloud Storage が無い環境）")

        # 3) スライドを作って、枠と文字 → 写真 → 重ね順の順に流し込む
        tell("スライドを作っています", 0, 1)
        headers = {"Authorization": f"Bearer {access_token}"}
        r = http.post(API, json={"title": f"思い出のアルバム — {_title(album)}"}, headers=headers, timeout=20)
        if r.status_code != 200:
            logger.error("アルバムのスライドの作成に失敗: %s %s", r.status_code, r.text[:500])
            if r.status_code == 403:
                raise SlidesError("Google スライドを使う許可が得られませんでした。")
            raise SlidesError("Google スライドを作れませんでした。")
        pres = r.json()
        pid = pres["presentationId"]
        first = (pres.get("slides") or [{}])[0].get("objectId")
        body, images, zorder = build_requests(album, photos, pages, urls, pres.get("pageSize"),
                                              delete_slide=first)
        batch = f"{API}/{pid}:batchUpdate"
        r = http.post(batch, json={"requests": body}, headers=headers, timeout=60)
        if r.status_code != 200:
            logger.error("アルバムの流し込みに失敗: %s %s", r.status_code, r.text[:1000])
            raise SlidesError("スライドに、アルバムの中身を入れられませんでした。")

        placed, budget = 0, [_IMAGE_CALLS]
        for i in range(0, len(images), 20):
            tell("写真を貼っています", i, len(images))
            placed += _insert_images(http, batch, headers, images[i:i + 20], budget)
        tell("写真を貼っています", len(images), len(images))
        if zorder:
            r = http.post(batch, json={"requests": zorder}, headers=headers, timeout=60)
            if r.status_code != 200:
                logger.warning("重ね順を直せませんでした: %s %s", r.status_code, r.text[:300])
    finally:
        try:
            host.cleanup()
        except Exception:
            logger.warning("アルバムの一時ファイルを消せませんでした", exc_info=True)

    logger.info("アルバムのスライドを作成: presentation=%s slides=%d photos=%d/%d",
                pid, sum(1 for q in body if "createSlide" in q), placed, len(images))
    return f"https://docs.google.com/presentation/d/{pid}/edit"
