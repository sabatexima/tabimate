"""保存プランを、絵本の世界観のまま Google スライドの「旅のしおり」にする。

流れは2段:
  1) build_requests(): プランから Slides API の batchUpdate 要求を組み立てる。
     ネットワークに出ない純粋な関数なので、テストで中身を丸ごと確かめられる。
  2) create_presentation(): 本人のアクセストークンで空のスライドを作り、
     1) の要求を流し込んで、開くためのURLを返す。

ファイルは本人の Google ドライブに作られる（drive.file 権限＝このアプリが
作ったファイルにしか触れない、いちばん狭い権限）。AI は呼ばない。保存済みの
プランを、決まったレイアウトに当てはめるだけ。

デザインの考え方（旅行のしおり・絵本・スクラップブックのテンプレートから）:
  ・1日1枚。左に日付の帯、右に時刻のタイムライン（しおりの定番の形）
  ・いちばん大事な数字（ひとりあたりの費用）だけを大きく、差し色で見せる
  ・マスキングテープ・やわらかい丸い形・紙ふぶきの点で、手づくりの温かさを足す
  ・日付や人数は小さな札（両端の丸いピル）に。分類は丸いバッジの絵文字で
  ・余白を多めにとり、左右の余白と行の頭をそろえる
  ・ちゃむの最後のひとことは吹き出しで

世界観をそろえるために:
  ・文字は画面と同じ Zen Maru Gothic（Google Fonts なのでスライドでも使える）
  ・色は layout.css のトークンと同じ（クリームの紙・若葉色・金茶・ちゃむの耳のピンク）
  ・ちゃむの絵は、このサイトが公開している static の画像をそのまま貼る
    （Google がURLから取りに来るので、手元の localhost では貼れない。
      その場合は絵だけ省いて、しおり本体は作る）

文字があふれないよう、入る量を見積もってページを分ける。
Slides API は文字の大きさを自動で縮めてくれない（API からは設定できない）ため。
"""

import math
import re
from datetime import date, timedelta

from logger import get_logger

logger = get_logger("services.slides_export")

API = "https://slides.googleapis.com/v1/presentations"
FONT = "Zen Maru Gothic"

# layout.css のトークンと同じ色
INK = "#4a4540"          # --text-main
MUTED = "#8a817a"        # --text-muted
GREEN = "#4fa83a"        # --primary-color
GREEN_DARK = "#3b8a2c"   # --primary-dark
PINK = "#f08ba0"         # --accent-pink（ちゃむの耳）
GOLD = "#c2a05e"         # しおりのキッカー（金茶）
CREAM = "#fdfaf2"        # 背景グラデの上端
MEADOW = "#edf3de"       # 背景グラデの下端（淡い若葉色）
LEAF = "#dcebcf"         # やわらかい丸い形（若葉色を一段濃く）
BLUSH = "#fbe4e9"        # ピンクのテープ・丸い形
SURFACE = "#fffdf8"      # --surface（カードの面）
BORDER = "#e7ddca"       # --border
GLOW = "#f6f6a5"         # --glow-cream（四つ葉まわりの淡い光）
WAVY = "#b9d9a5"         # 見出しの点線（rgba(122,190,96,.5) をクリームに重ねた色）
COST = "#a9772f"         # しおりの費用の色

# レイアウトは 720×405pt（16:9）を基準に書き、実際のページの大きさに合わせて伸縮する
BASE_W, BASE_H = 720.0, 405.0
EMU_PER_PT = 12700
MARGIN = 44              # 左右の余白（行の頭をここにそろえる）

# 「1日目」「【2日目】金沢」「3日目：市内」などの見出し行（agents.py の _days_in と同じ規則）
_DAY_RE = re.compile(r'^[【\[]?\s*(\d+)\s*日目[】\]]?\s*[:：]?\s*(.*)$')
_TIME_RE = re.compile(r'^\s*(\d{1,2}[:：]\d{2}(?:\s*[〜~\-–]\s*\d{1,2}[:：]\d{2})?)\s*(.*)$')
_DATE_RE = re.compile(r'(\d{4})\D+(\d{1,2})\D+(\d{1,2})')
_WEEKDAYS = "月火水木金土日"


def _u16(text: str) -> int:
    """Slides API の文字位置は UTF-16 の単位で数える（絵文字は2つ分）。"""
    return len(text.encode("utf-16-le")) // 2


def _rgb(hex_color: str) -> dict:
    h = hex_color.lstrip("#")
    return {"red": int(h[0:2], 16) / 255, "green": int(h[2:4], 16) / 255,
            "blue": int(h[4:6], 16) / 255}


def _spaced(text: str) -> str:
    """キッカーの字間（CSS の letter-spacing: .38em）を、文字の間の空白でまねる。"""
    return " ".join(text)


def _width(text: str) -> float:
    """全角1字=1、半角は0.55字として、文字列の幅（字数）を見積もる。"""
    return sum(1 if ord(c) > 0x2000 else 0.55 for c in text)


# 1行に入る字数は、見積もりより少し少なく見ておく。日本語は「。」「、」を行頭に
# 置かない決まり（禁則）で、計算より手前で折り返すことがあるため（実際に1行増えた）
_WRAP_SAFETY = 0.9


def _visual_lines(lines: list, chars_per_line: int) -> int:
    """折り返しを含めて、何行ぶんの高さになるかを見積もる（禁則のぶん少し多めに）。"""
    per_line = max(1.0, chars_per_line * _WRAP_SAFETY)
    return sum(max(1, math.ceil(_width(line) / per_line)) for line in lines)


def _paginate(lines: list, chars_per_line: int, max_lines: int, is_heading=None) -> list:
    """行のリストを、1枚に入る高さごとに分ける。1行が長すぎても必ず1枚に1行は置く。

    is_heading(行) が真の行（費用の「■ 2日目の費用」など）は、ページの最後に
    取り残さず、次のページの頭へ送る（見出しだけがぽつんと残らないように）。
    """
    pages, current, used = [], [], 0
    for line in lines:
        need = _visual_lines([line], chars_per_line)
        if current and used + need > max_lines:
            carry = []
            if is_heading and len(current) > 1 and is_heading(current[-1]):
                carry = [current.pop()]
            pages.append(current)
            current = carry
            used = _visual_lines(carry, chars_per_line) if carry else 0
        current.append(line)
        used += need
    if current:
        pages.append(current)
    return pages


def split_days(schedule: list) -> list:
    """スケジュールの行を日ごとに分ける。[(日の番号 or None, 副題, [行…]), …] を返す。

    「N日目」の行が無い（日帰り）ときは、番号 None の1日だけにする。
    見出し行に「：金沢市内」のような副題があれば、副題として残す。
    """
    days, num, sub, body = [], None, "", []
    for raw in schedule or []:
        line = str(raw).strip()
        if not line:
            continue
        m = _DAY_RE.match(line)
        if m:
            if num is not None or body:
                days.append((num, sub, body))
            num, sub, body = int(m.group(1)), m.group(2).strip(), []
        else:
            body.append(line)
    if num is not None or body:
        days.append((num, sub, body))
    return days


def _day_date(travel_date, day_num) -> str:
    """旅行日が具体的な日付なら、N日目の日付を「11月4日（水）」の形で返す。"""
    m = _DATE_RE.search(str(travel_date or ""))
    if not m or not day_num:
        return ""
    try:
        d = date(int(m.group(1)), int(m.group(2)), int(m.group(3))) + timedelta(days=day_num - 1)
    except ValueError:
        return ""
    return f"{d.month}月{d.day}日（{_WEEKDAYS[d.weekday()]}）"


class _Deck:
    """batchUpdate の要求を積み上げる。図形の ID 振りと座標の伸縮をここに集める。"""

    def __init__(self, page_w_pt: float, page_h_pt: float, image_url=None):
        self.sx = page_w_pt / BASE_W
        self.sy = page_h_pt / BASE_H
        self.requests: list = []
        self.image_requests: list = []
        self.image_url = image_url  # ファイル名 → 公開URL。None なら絵は貼らない
        self._n = 0
        self.slide_ids: list = []

    def _id(self, kind: str) -> str:
        self._n += 1
        return f"tm_{kind}_{self._n:03d}"

    def _size(self, w, h) -> dict:
        return {"width": {"magnitude": round(w * self.sx, 2), "unit": "PT"},
                "height": {"magnitude": round(h * self.sy, 2), "unit": "PT"}}

    def _box(self, page, x, y, w, h) -> dict:
        return {"pageObjectId": page, "size": self._size(w, h),
                "transform": {"scaleX": 1, "scaleY": 1, "unit": "PT",
                              "translateX": round(x * self.sx, 2),
                              "translateY": round(y * self.sy, 2)}}

    def _rotated(self, page, cx, cy, w, h, degrees) -> dict:
        """中心 (cx, cy) のまわりに回した箱。マスキングテープを斜めに貼るのに使う。"""
        t = math.radians(degrees)
        a, b = math.cos(t), math.sin(t)
        sw, sh = w * self.sx, h * self.sy
        ex = cx * self.sx - (a * sw / 2 - b * sh / 2)
        ey = cy * self.sy - (b * sw / 2 + a * sh / 2)
        return {"pageObjectId": page, "size": {"width": {"magnitude": round(sw, 2), "unit": "PT"},
                                                "height": {"magnitude": round(sh, 2), "unit": "PT"}},
                "transform": {"scaleX": round(a, 5), "scaleY": round(a, 5),
                              "shearX": round(-b, 5), "shearY": round(b, 5), "unit": "PT",
                              "translateX": round(ex, 2), "translateY": round(ey, 2)}}

    # ---- ページと図形 ----
    def slide(self) -> str:
        """新しいページ（クリームの紙）。"""
        sid = self._id("slide")
        self.requests.append({"createSlide": {
            "objectId": sid, "insertionIndex": len(self.slide_ids),
            "slideLayoutReference": {"predefinedLayout": "BLANK"}}})
        self.slide_ids.append(sid)
        self.requests.append({"updatePageProperties": {
            "objectId": sid,
            "pageProperties": {"pageBackgroundFill": {"solidFill": {"color": {"rgbColor": _rgb(CREAM)}}}},
            "fields": "pageBackgroundFill.solidFill.color"}})
        return sid

    def shape(self, page, kind, x, y, w, h, fill=None, outline=None, alpha=1.0,
              element=None, weight=1.0) -> str:
        oid = self._id("shape")
        self.requests.append({"createShape": {
            "objectId": oid, "shapeType": kind,
            "elementProperties": element or self._box(page, x, y, w, h)}})
        props, fields = {}, []
        if fill:
            solid = {"color": {"rgbColor": _rgb(fill)}}
            if alpha < 1:
                solid["alpha"] = alpha
            props["shapeBackgroundFill"] = {"solidFill": solid}
            fields.append("shapeBackgroundFill.solidFill")
        if outline:
            props["outline"] = {"outlineFill": {"solidFill": {"color": {"rgbColor": _rgb(outline)}}},
                                "weight": {"magnitude": weight, "unit": "PT"}}
            fields += ["outline.outlineFill.solidFill.color", "outline.weight"]
        else:
            props["outline"] = {"propertyState": "NOT_RENDERED"}
            fields.append("outline.propertyState")
        props["contentAlignment"] = "MIDDLE" if kind in ("FLOWCHART_TERMINATOR", "ELLIPSE") else "TOP"
        fields.append("contentAlignment")
        self.requests.append({"updateShapeProperties": {
            "objectId": oid, "shapeProperties": props, "fields": ",".join(fields)}})
        return oid

    def text(self, oid, text, size=12, color=INK, bold=False, align="START",
             line_spacing=125, styles=(), space_below=0):
        """図形に文字を入れる。styles は [(開始, 終了, {style}, fields)]（UTF-16 の位置）。"""
        if not text:
            return
        self.requests.append({"insertText": {"objectId": oid, "insertionIndex": 0, "text": text}})
        self.requests.append({"updateTextStyle": {
            "objectId": oid, "textRange": {"type": "ALL"},
            "style": {"fontFamily": FONT, "fontSize": {"magnitude": size, "unit": "PT"},
                      "bold": bold, "foregroundColor": {"opaqueColor": {"rgbColor": _rgb(color)}}},
            "fields": "fontFamily,fontSize,bold,foregroundColor"}})
        para = {"alignment": align, "lineSpacing": line_spacing}
        fields = "alignment,lineSpacing"
        if space_below:
            para["spaceBelow"] = {"magnitude": space_below, "unit": "PT"}
            fields += ",spaceBelow"
        self.requests.append({"updateParagraphStyle": {
            "objectId": oid, "textRange": {"type": "ALL"}, "style": para, "fields": fields}})
        for start, end, style, sfields in styles:
            if end > start:
                self.requests.append({"updateTextStyle": {
                    "objectId": oid,
                    "textRange": {"type": "FIXED_RANGE", "startIndex": start, "endIndex": end},
                    "style": style, "fields": sfields}})

    def label(self, page, x, y, w, h, text, **kw) -> str:
        """枠も塗りもない文字だけの箱。"""
        oid = self.shape(page, "TEXT_BOX", x, y, w, h)
        self.text(oid, text, **kw)
        return oid

    def line(self, page, x, y, w, h, color=WAVY, weight=2.5, dash="DOT"):
        oid = self._id("line")
        self.requests.append({"createLine": {
            "objectId": oid, "lineCategory": "STRAIGHT",
            "elementProperties": self._box(page, x, y, max(w, 0.01), max(h, 0.01))}})
        self.requests.append({"updateLineProperties": {
            "objectId": oid,
            "lineProperties": {"lineFill": {"solidFill": {"color": {"rgbColor": _rgb(color)}}},
                               "weight": {"magnitude": weight, "unit": "PT"}, "dashStyle": dash},
            "fields": "lineFill.solidFill.color,weight,dashStyle"}})

    def image(self, page, name, x, y, w, h):
        """ちゃむの絵。貼れなくても本体は作れるよう、別の要求として分けておく。"""
        if not self.image_url:
            return
        self.image_requests.append({"createImage": {
            "objectId": self._id("img"), "url": self.image_url(name),
            "elementProperties": self._box(page, x, y, w, h)}})

    # ---- 飾り ----
    def blob(self, page, x, y, w, h, color=LEAF, alpha=0.55):
        """やわらかい丸い形。大小2つの楕円を重ねて、機械的な円に見せない。"""
        self.shape(page, "ELLIPSE", x, y, w, h, fill=color, alpha=alpha)
        # 2つ目は箱の右下に寄せる（箱 x〜x+w, y〜y+h の中に収める）
        self.shape(page, "ELLIPSE", x + w * 0.38, y + h * 0.4, w * 0.62, h * 0.6,
                   fill=color, alpha=alpha * 0.8)

    def tape(self, page, cx, cy, w=78, h=20, color=BLUSH, degrees=-8, alpha=0.85):
        """マスキングテープ。少し透ける色を斜めに貼る。"""
        self.shape(page, "RECTANGLE", 0, 0, w, h, fill=color, alpha=alpha,
                   element=self._rotated(page, cx, cy, w, h, degrees))

    def confetti(self, page, points):
        """紙ふぶきの小さな点。points は [(x, y, 色), …]。"""
        for x, y, color in points:
            self.shape(page, "ELLIPSE", x, y, 6, 6, fill=color, alpha=0.8)

    def pill(self, page, x, y, text, size=10.5, fill=SURFACE, color=INK, outline=BORDER,
             bold=False, h=24, pad=14) -> float:
        """両端の丸い札。幅は文字数から決め、右端の x を返す（横に並べるため）。"""
        w = _width(text) * size + pad * 2
        oid = self.shape(page, "FLOWCHART_TERMINATOR", x, y, w, h, fill=fill, outline=outline)
        self.text(oid, text, size=size, color=color, bold=bold, align="CENTER", line_spacing=100)
        return x + w

    def badge(self, page, x, y, emoji, d=34, fill=MEADOW):
        """丸いバッジに絵文字（分類の目印）。"""
        oid = self.shape(page, "ELLIPSE", x, y, d, d, fill=fill)
        self.text(oid, emoji, size=d * 0.42, align="CENTER", line_spacing=100)

    def card(self, page, x, y, w, h, text="", inset=(16, 12), **kw) -> str:
        """角の丸いカードに文字を載せる。

        文字はカードそのものではなく、内側に一回り小さい箱を重ねて入れる。
        スライドの角丸は API から丸みを変えられず、大きなカードほど角が深く
        えぐれるので、カードに直接入れると1行目の頭が角にかかってしまう。
        """
        self.shape(page, "ROUND_RECTANGLE", x, y, w, h, fill=SURFACE, outline=BORDER)
        if not text:
            return ""
        ix, iy = inset
        return self.label(page, x + ix, y + iy, w - ix * 2, h - iy * 2, text, **kw)

    def page_head(self, kicker: str, heading: str) -> str:
        """中身のページの頭: 金茶のキッカー・見出し・点線・右上のちゃむ。"""
        sid = self.slide()
        self.blob(sid, 610, 0, 110, 84, color=MEADOW, alpha=0.9)
        self.label(sid, MARGIN, 22, 520, 18, _spaced(kicker), size=9, color=GOLD, bold=True)
        self.label(sid, MARGIN, 36, 560, 34, heading, size=22, bold=True)
        self.line(sid, MARGIN + 4, 74, min(300, 30 + 22 * _width(heading)), 0)
        self.image(sid, "mate-head.png", 650, 14, 48, 48)
        return sid

    def page_numbers(self):
        """全ページが揃ってから、右下に「2 / 9」を入れる（表紙には入れない）。"""
        total = len(self.slide_ids)
        for n, sid in enumerate(self.slide_ids[1:], start=2):
            self.label(sid, 600, 378, 76, 18, f"{n} / {total}", size=8, color=MUTED, align="END")


def _bold(color=None) -> tuple:
    style = {"bold": True}
    fields = "bold"
    if color:
        style["foregroundColor"] = {"opaqueColor": {"rgbColor": _rgb(color)}}
        fields += ",foregroundColor"
    return style, fields


def _join_with_styles(lines: list, pick) -> tuple:
    """行を改行でつなぎ、pick(行) が返す (先頭からの長さ, 色) ぶんを太字にする範囲を作る。"""
    text, styles, pos = "", [], 0
    for i, line in enumerate(lines):
        if i:
            text += "\n"
            pos += 1
        hit = pick(line)
        if hit:
            length, color = hit
            style, fields = _bold(color)
            styles.append((pos, pos + _u16(line[:length]), style, fields))
        text += line
        pos += _u16(line)
    return text, styles


def _line_height(size: float, spacing: float) -> float:
    """1行の高さ（pt）。Slides は行間100%でおよそ文字の1.2倍になる。"""
    return size * spacing / 100 * 1.2


def _text_height(lines: list, chars_per_line: int, size: float, spacing: float) -> float:
    return _visual_lines(lines, chars_per_line) * _line_height(size, spacing)


# ----------------------------------------------------------------------
# ページ
# ----------------------------------------------------------------------
def _cover(deck: _Deck, plan: dict, weather_days):
    sid = deck.slide()
    # 右上に大きなやわらかい形、その上にちゃむ。左下に小さなピンクの形
    deck.blob(sid, 400, 18, 300, 290, color=LEAF, alpha=0.6)
    deck.shape(sid, "ELLIPSE", 470, 70, 210, 210, fill=GLOW, alpha=0.75)
    deck.blob(sid, 0, 330, 150, 75, color=BLUSH, alpha=0.7)
    deck.shape(sid, "RECTANGLE", 0, 372, BASE_W, 33, fill=MEADOW)
    deck.image(sid, "mate.png", 488, 62, 196, 262)
    deck.tape(sid, 92, 40, w=96, h=22, color=BLUSH, degrees=-9)
    deck.tape(sid, 640, 330, w=84, h=20, color=LEAF, degrees=7, alpha=0.95)
    deck.confetti(sid, [(392, 60, PINK), (430, 326, GOLD), (24, 150, GREEN), (372, 250, GOLD)])

    deck.pill(sid, MARGIN + 12, 78, _spaced("旅のしおり"), size=10, fill=GREEN,
              color="#ffffff", outline=None, bold=True, h=24, pad=16)

    dest = str(plan.get("destination") or "旅のしおり")
    size = 44 if _width(dest) <= 7 else 32 if _width(dest) <= 11 else 24
    lines_needed = max(1, math.ceil(_width(dest) * size / 380))
    title_h = lines_needed * _line_height(size, 105) + 8
    deck.label(sid, MARGIN + 8, 108, 390, title_h, dest, size=size, bold=True, line_spacing=105)
    y = 108 + title_h + 2
    deck.line(sid, MARGIN + 14, y, min(320, 24 + size * min(_width(dest), 8)), 0, weight=3)
    y += 12

    sub = []
    if plan.get("departure_location"):
        sub.append(f"{plan['departure_location']} から")
    if plan.get("duration"):
        sub.append(f"{plan['duration']}の旅")
    if sub:
        deck.label(sid, MARGIN + 8, y, 390, 22, "、".join(sub), size=13, color=MUTED)
        y += 30

    x = MARGIN + 12
    for text in [f"📅 {plan['travel_date']}" if plan.get("travel_date") else "",
                 f"👥 {plan['num_people']}人" if plan.get("num_people") else ""]:
        if text and x < 420:
            x = deck.pill(sid, x, y, text, size=10.5) + 8
    if x > MARGIN + 12:
        y += 34

    cost = plan.get("total_per_person") or plan.get("budget_limit")
    if cost:
        label = "ひとりあたりの目安" if plan.get("total_per_person") else "ひとりあたりの予算"
        deck.label(sid, MARGIN + 12, y, 140, 18, label, size=9.5, color=MUTED)
        deck.label(sid, MARGIN + 10, y + 14, 260, 30, f"{int(cost):,}円", size=20,
                   color=COST, bold=True)
        y += 50

    if weather_days and y < 340:
        days = [d for d in weather_days[:5] if d.get("date")]
        text = "　".join(f"{int(d['date'][5:7])}/{int(d['date'][8:10])} {d.get('emoji', '')}" for d in days)
        if text:
            deck.label(sid, MARGIN + 12, y, 360, 20, "🌤 " + text, size=10, color=MUTED)

    deck.label(sid, MARGIN + 8, 379, 400, 18, "🍀 たびメイト で作った旅のしおり", size=9, color=MUTED)


def _overview(deck: _Deck, plan: dict):
    cols = [(icon, label, fill, [str(i) for i in plan.get(key) or [] if str(i).strip()])
            for icon, label, fill, key in (("✨", "めぐるところ", MEADOW, "spots"),
                                           ("🍱", "ごはん", BLUSH, "restaurants"),
                                           ("🏨", "とまるところ", "#fbf3d5", "accommodation"))]
    cols = [c for c in cols if c[3]]
    if not cols:
        return
    sid = deck.page_head("旅のなかみ", "この旅で 楽しむこと")
    gap = 18
    width = BASE_W - MARGIN * 2
    w = (width - gap * (len(cols) - 1)) / len(cols)
    inner = w - 32
    # 長い名前（海外の「日本語名（現地語名）」など）が多いときは、字を一段ずつ小さく
    for size in (12, 10.5, 9.5):
        chars = max(6, int(inner / size))
        h = max(_text_height([f"・{i}" for i in c[3]], chars, size, 145) for c in cols)
        if h <= 188:
            break
    h = max(150, min(262, h + 74))
    for n, (icon, label, fill, items) in enumerate(cols):
        x = MARGIN + n * (w + gap)
        deck.card(sid, x, 100, w, h)
        deck.tape(sid, x + w / 2, 100, w=64, h=16,
                  color=(BLUSH, LEAF, "#f6edc8")[n % 3], degrees=(-6, 5, -4)[n % 3])
        deck.badge(sid, x + 16, 118, icon, d=34, fill=fill)
        deck.label(sid, x + 56, 124, w - 64, 22, label, size=13, bold=True, color=GREEN_DARK)
        deck.label(sid, x + 16, 160, inner, h - 68, "\n".join(f"・{i}" for i in items),
                   size=size, line_spacing=145)


# タイムラインの寸法
_TL_X = 246          # 縦線の x
_TL_TIME_X = 262     # 時刻の左端
_TL_TEXT_X = 318     # 予定の左端
_TL_TEXT_W = BASE_W - MARGIN - _TL_TEXT_X
_TL_TOP, _TL_BOTTOM = 52, 372
_TL_SIZE, _TL_SPACING, _TL_GAP = 12, 120, 9


def _entry_height(text: str, width: float) -> float:
    chars = max(6, int((width - 14) / _TL_SIZE))
    return _text_height([text], chars, _TL_SIZE, _TL_SPACING)


def _timeline_pages(body: list) -> list:
    """1日の予定を、タイムラインの高さに収まるページに分ける。"""
    entries = []
    for line in body:
        m = _TIME_RE.match(line)
        if m and m.group(2):
            entries.append((m.group(1).replace("：", ":"), m.group(2)))
        else:
            entries.append(("", line))
    pages, current, used = [], [], 0
    room = _TL_BOTTOM - _TL_TOP
    for time, text in entries:
        width = _TL_TEXT_W if time else BASE_W - MARGIN - _TL_TIME_X
        need = _entry_height(text, width) + _TL_GAP
        if current and used + need > room:
            pages.append(current)
            current, used = [], 0
        current.append((time, text, need))
        used += need
    if current:
        pages.append(current)
    return pages


def _schedule(deck: _Deck, plan: dict):
    days = split_days(plan.get("schedule"))
    # 「1日目」より前の行（海外の「※時刻はすべて現地時刻」など）は、それだけで
    # 1枚にせず、1日目の頭に載せる
    if len(days) > 1 and days[0][0] is None:
        _, _, preface = days.pop(0)
        num, sub, body = days[0]
        days[0] = (num, sub, preface + body)
    single = len(days) == 1 and days[0][0] is None
    for num, sub, body in days:
        if not body:
            continue
        pages = _timeline_pages(body)
        for n, page in enumerate(pages):
            sid = deck.slide()
            # 左の帯: 日付と副題。ページごとに色を変えず、帯の中のテープだけ交互に
            deck.shape(sid, "RECTANGLE", 0, 0, 212, BASE_H, fill=MEADOW)
            deck.blob(sid, 108, 296, 96, 84, color=LEAF, alpha=0.7)
            deck.tape(sid, 106, 26, w=86, h=20,
                      color=BLUSH if (num or 1) % 2 else "#f6edc8", degrees=-7)
            deck.label(sid, 30, 58, 170, 18, _spaced("スケジュール"), size=9, color=GOLD, bold=True)
            big = f"{num}日目" if num else ("日帰り" if single else "スケジュール")
            deck.label(sid, 26, 76, 180, 50, big, size=30 if num else 24, bold=True, color=GREEN_DARK)
            y = 128
            when = _day_date(plan.get("travel_date"), num or 1)
            if when:
                deck.label(sid, 30, y, 170, 20, when, size=11, color=INK)
                y += 22
            if sub:
                deck.label(sid, 30, y, 166, 56, sub, size=11, color=MUTED, line_spacing=130)
            if n:
                deck.label(sid, 30, 250, 170, 18, "（つづき）", size=10, color=MUTED)
            deck.image(sid, "mate-head.png", 30, 300, 66, 66)

            # 右: 時刻のタイムライン
            total = sum(h for _, _, h in page) - _TL_GAP
            deck.line(sid, _TL_X, _TL_TOP + 6, 0, max(8, total - 6), color=WAVY, weight=2, dash="DOT")
            y = _TL_TOP
            for time, text, need in page:
                if time:
                    deck.shape(sid, "ELLIPSE", _TL_X - 5, y + 4, 10, 10, fill=GREEN)
                    deck.label(sid, _TL_TIME_X - 7, y - 3, 62, 20, time, size=_TL_SIZE,
                               bold=True, color=GREEN_DARK, line_spacing=_TL_SPACING)
                    deck.label(sid, _TL_TEXT_X - 7, y - 3, _TL_TEXT_W + 7, need, text,
                               size=_TL_SIZE, line_spacing=_TL_SPACING)
                else:
                    deck.shape(sid, "ELLIPSE", _TL_X - 3, y + 6, 6, 6, fill=SURFACE,
                               outline=GREEN, weight=1)
                    deck.label(sid, _TL_TIME_X - 7, y - 3, BASE_W - MARGIN - _TL_TIME_X + 7, need,
                               text, size=_TL_SIZE, line_spacing=_TL_SPACING, color=MUTED)
                y += need


def _costs(deck: _Deck, plan: dict):
    lines = [str(x).strip() for x in plan.get("budget_estimate") or [] if str(x).strip()]
    total = plan.get("total_per_person")
    if not lines and not total:
        return

    def pick(line):
        if line.startswith("■") or "合計" in line:
            return len(line), (COST if "合計" in line else GREEN_DARK)
        return None

    # 1枚目は左に大きな数字、右に内訳。2枚目以降は内訳だけを広く
    first_w, wide_w = 392, BASE_W - MARGIN * 2
    first_chars, wide_chars = int((first_w - 46) / 11.5), int((wide_w - 46) / 11.5)
    first = _paginate(lines, first_chars, 14, is_heading=lambda s: s.startswith("■"))[:1] if lines else [[]]
    rest = lines[len(first[0]):]
    pages = first + (_paginate(rest, wide_chars, 14, is_heading=lambda s: s.startswith("■")) if rest else [])

    for n, page in enumerate(pages):
        sid = deck.page_head("旅の費用", "費用の見積もり" + ("（つづき）" if n else ""))
        if n == 0:
            # いちばん大事な数字だけを大きく。差し色はここだけに使う
            deck.blob(sid, MARGIN - 6, 108, 230, 220, color=GLOW, alpha=0.55)
            deck.shape(sid, "ELLIPSE", MARGIN + 20, 120, 196, 196, fill=SURFACE, outline=BORDER)
            deck.tape(sid, MARGIN + 118, 124, w=70, h=18, color=BLUSH, degrees=-6)
            if total:
                deck.label(sid, MARGIN + 30, 168, 176, 20, "ひとりあたり", size=11,
                           color=MUTED, align="CENTER")
                deck.label(sid, MARGIN + 26, 190, 184, 40, f"{int(total):,}円", size=26,
                           bold=True, color=COST, align="CENTER")
            if plan.get("budget_limit"):
                deck.label(sid, MARGIN + 30, 238, 176, 20, f"予算 {int(plan['budget_limit']):,}円",
                           size=10.5, color=MUTED, align="CENTER")
            if plan.get("num_people") and total:
                deck.label(sid, MARGIN + 30, 256, 176, 20,
                           f"{plan['num_people']}人で {int(total) * int(plan['num_people']):,}円",
                           size=10.5, color=MUTED, align="CENTER")
            x, w, chars = 288, first_w, first_chars
        else:
            x, w, chars = MARGIN, wide_w, wide_chars
        if page:
            text, styles = _join_with_styles(page, pick)
            h = max(120, min(268, _text_height(page, chars, 11.5, 130) + 30))
            deck.card(sid, x, 98, w, h, text, size=11.5, line_spacing=130, styles=styles)


def _packing(deck: _Deck, plan: dict):
    items = [str(i).strip() for i in plan.get("packing_list") or [] if str(i).strip()][:21]
    if not items:
        return
    sid = deck.page_head("持ちもの", "わすれずに 持っていこう")
    cols, gap_x, gap_y, h = 3, 14, 12, 30
    w = (BASE_W - MARGIN * 2 - gap_x * (cols - 1)) / cols
    rows = math.ceil(len(items) / cols)
    gap_y = min(gap_y, (372 - 100 - rows * h) / max(1, rows - 1)) if rows > 1 else gap_y
    for n, item in enumerate(items):
        col, row = n % cols, n // cols
        x, y = MARGIN + col * (w + gap_x), 100 + row * (h + gap_y)
        oid = deck.shape(sid, "FLOWCHART_TERMINATOR", x, y, w, h, fill=SURFACE, outline=BORDER)
        name = item if _width(item) <= 13 else item[:12] + "…"
        deck.text(oid, f"○  {name}", size=11.5, line_spacing=100)
    deck.confetti(sid, [(660, 360, PINK), (676, 350, GREEN), (52, 364, GOLD)])


def _fit_note(note: str, inner_width: float, max_height: float) -> tuple:
    """総評が吹き出しに収まる文字の大きさを選ぶ。最小でも入らなければ「…」で切る。

    全文はアプリのプランに残っているので、しおりでは読める大きさを優先する。
    """
    def fits(text, size):
        chars = max(1, int((inner_width - 14) / size))
        return _text_height([text], chars, size, 145) <= max_height

    for size in (12.5, 11, 9.5):
        if fits(note, size):
            return note, size
    while len(note) > 1 and not fits(note + "…", 9.5):
        note = note[:-1]
    return note.rstrip("、。 　") + "…", 9.5


def _closing(deck: _Deck, plan: dict):
    sid = deck.slide()
    deck.blob(sid, 20, 120, 260, 250, color=LEAF, alpha=0.6)
    deck.shape(sid, "ELLIPSE", 50, 150, 190, 190, fill=GLOW, alpha=0.7)
    deck.shape(sid, "RECTANGLE", 0, 372, BASE_W, 33, fill=MEADOW)
    deck.image(sid, "mate.png", 62, 120, 176, 236)
    deck.confetti(sid, [(282, 24, PINK), (690, 40, GREEN), (640, 300, GOLD), (40, 90, PINK)])

    note = str(plan.get("feedback") or "").strip()
    bottom = 160
    if note:
        deck.label(sid, 300, 34, 380, 18, _spaced("ちゃむから ひとこと"), size=9, color=GOLD, bold=True)
        inner_w = 380 - 40
        note, size = _fit_note(note, inner_w, 170)
        chars = max(1, int((inner_w - 14) / size))
        h = max(90, min(200, _text_height([note], chars, size, 145) + 34))
        # 吹き出しの尾は左下（ちゃむの方）に向く
        deck.shape(sid, "WEDGE_ROUND_RECTANGLE_CALLOUT", 300, 60, 380, h, fill=SURFACE, outline=BORDER)
        deck.label(sid, 320, 60 + 16, inner_w, h - 28, note, size=size, line_spacing=145)
        deck.tape(sid, 640, 62, w=70, h=18, color=BLUSH, degrees=8)
        bottom = 60 + h + 40
    deck.label(sid, 300, max(bottom, 170), 400, 50, "いってらっしゃい！🍀",
               size=30, color=GREEN_DARK, bold=True)


def build_requests(plan: dict, page_size=None, image_url=None, weather_days=None,
                   delete_slide=None) -> tuple:
    """プランから (本体の要求, ちゃむの絵の要求) を作る。

    page_size は presentations.create が返す pageSize（EMU）。無ければ 16:9 とみなす。
    image_url は「ファイル名 → 公開URL」の関数。None なら絵の要求は空になる。
    delete_slide は、作成時に最初から入っている空のページの ID（最後に消す）。
    """
    w_pt, h_pt = BASE_W, BASE_H
    if page_size:
        try:
            w_pt = page_size["width"]["magnitude"] / EMU_PER_PT
            h_pt = page_size["height"]["magnitude"] / EMU_PER_PT
        except (KeyError, TypeError, ZeroDivisionError):
            pass
    deck = _Deck(w_pt, h_pt, image_url)
    _cover(deck, plan, weather_days)
    _overview(deck, plan)
    _schedule(deck, plan)
    _costs(deck, plan)
    _packing(deck, plan)
    _closing(deck, plan)
    deck.page_numbers()
    if delete_slide:
        deck.requests.append({"deleteObject": {"objectId": delete_slide}})
    return deck.requests, deck.image_requests


class SlidesError(Exception):
    """スライドを作れなかった。message はそのまま画面に出せる文にする。"""


def create_presentation(access_token: str, plan: dict, image_url=None, weather_days=None,
                        http=None) -> str:
    """本人のドライブにしおりのスライドを作り、開くためのURLを返す。"""
    if http is None:
        import requests as http
    headers = {"Authorization": f"Bearer {access_token}"}
    title = f"旅のしおり — {plan.get('destination') or 'たびメイト'}"

    r = http.post(API, json={"title": title}, headers=headers, timeout=20)
    if r.status_code != 200:
        logger.error("スライドの作成に失敗: %s %s", r.status_code, r.text[:500])
        if r.status_code == 403:
            raise SlidesError("Google スライドを使う許可が得られませんでした。")
        raise SlidesError("Google スライドを作れませんでした。")
    pres = r.json()
    pid = pres["presentationId"]
    first = (pres.get("slides") or [{}])[0].get("objectId")

    body, images = build_requests(plan, pres.get("pageSize"), image_url, weather_days,
                                  delete_slide=first)
    r = http.post(f"{API}/{pid}:batchUpdate", json={"requests": body},
                  headers=headers, timeout=60)
    if r.status_code != 200:
        logger.error("しおりの流し込みに失敗: %s %s", r.status_code, r.text[:1000])
        raise SlidesError("スライドに、しおりの中身を入れられませんでした。")

    # ちゃむの絵は、Google が公開URLから取りに来る。手元の localhost などで
    # 取りに来られなくても、しおり本体はもうできているので失敗にしない
    if images:
        try:
            r = http.post(f"{API}/{pid}:batchUpdate", json={"requests": images},
                          headers=headers, timeout=60)
            if r.status_code != 200:
                logger.warning("ちゃむの絵を貼れませんでした: %s %s", r.status_code, r.text[:300])
        except Exception:
            logger.warning("ちゃむの絵を貼れませんでした", exc_info=True)

    logger.info("旅のしおりのスライドを作成: presentation=%s slides=%s",
                pid, sum(1 for q in body if "createSlide" in q))
    return f"https://docs.google.com/presentation/d/{pid}/edit"
