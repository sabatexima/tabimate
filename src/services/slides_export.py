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
import unicodedata
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
# \d は全角の数字にも当たる（「０９：００」も時刻として拾う）
_TIME_RE = re.compile(r'^\s*(\d{1,2}[:：]\d{2}(?:\s*[〜~\-–－]\s*\d{1,2}[:：]\d{2})?)\s*(.*)$')
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


# Zen Maru Gothic で実際に測った半角の幅（全角=1）。幅の広い字だけ別に見る
_WIDE_LATIN = set("MWmw@%&")
_NARROW_LATIN = set("iljtfr.,:;'!|() ")


def _width(text: str) -> float:
    """文字列の幅（全角1字=1）を見積もる。半角は字の形でおおまかに分ける。

    絵文字をつなぐ文字（ZWJ）と、その次の字・異体字セレクタは数えない
    （👨‍👩‍👧‍👦 は1字ぶん）。
    """
    total = 0.0
    joined = False
    for c in text:
        if joined:
            joined = False
            continue
        if c == "\u200d":
            joined = True
            continue
        if c in "\u200b\ufe0f":
            continue
        if ord(c) > 0x2000:
            total += 1
        elif c in _WIDE_LATIN or c.isupper():
            total += 0.8
        elif c in _NARROW_LATIN:
            total += 0.35
        else:
            total += 0.55
    return total


# 1行に入る字数は、見積もりより少し少なく見ておく。日本語は「。」「、」を行頭に
# 置かない決まり（禁則）で、計算より手前で折り返すことがあるため（実際に1行増えた）
_WRAP_SAFETY = 0.9


# 折り返せる単位: 日本語は1字ずつ、英数字は空白・見えない印までのひと続き
_TOKENS = re.compile(r"[\u3000-\u9fff\uff00-\uffef]|[^\s\u200b\u3000-\u9fff\uff00-\uffef]+|[\s\u200b]+")


def _wrap_lines(line: str, per_line: float) -> int:
    """1行の文字列が、幅 per_line で何行に折り返されるか（実際の折り返し方をまねる）。

    英単語やURLは途中で切れず、入らなければ丸ごと次の行へ送られる。単純に
    「全体の幅 ÷ 1行の幅」で数えると、この送られたぶんの空きを数え損なう。
    """
    lines, cur = 1, 0.0
    for tok in _TOKENS.findall(line):
        w = _width(tok)
        if tok.isspace() or not tok.strip("\u200b"):
            cur += w
            continue
        if cur > 0 and cur + w > per_line:
            lines += 1
            cur = 0.0
        if w > per_line:
            # 1語が1行より長い: 字の途中で切られる
            extra = math.ceil(w / per_line) - 1
            lines += extra
            cur = w - extra * per_line
        else:
            cur += w
    return lines


def _visual_lines(lines: list, chars_per_line: int) -> int:
    """折り返しを含めて、何行ぶんの高さになるかを見積もる（禁則のぶん少し多めに）。"""
    per_line = max(1.0, chars_per_line * _WRAP_SAFETY)
    return sum(_wrap_lines(line, per_line) for line in lines)


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
    for line in _items(schedule):
        if not line:
            continue
        m = _DAY_RE.match(line)
        if m:
            if num is not None or body:
                days.append((num, sub, body))
            num, sub, body = int(m.group(1)), m.group(2).strip(), []
            # 「【2日目】09:00 美術館」のように見出しと予定が1行のときは、
            # 後ろは副題ではなく1つ目の予定（副題にすると、その日が空に見えて消える）
            if _TIME_RE.match(sub):
                body, sub = [sub], ""
        else:
            body.append(line)
    if num is not None or body:
        days.append((num, sub, body))
    return days


def _num(value):
    """金額や人数を整数にする。「80,000」「80000円」も読む。読めない・0以下は None。

    保存済みのプランは数値で入っているはずだが、手で直したデータや古いデータで
    文字列が混ざっても、しおり作りそのものは止めない。
    """
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        n = int(value)
    else:
        text = re.sub(r"[,，\s円人名]", "", _half(str(value)))
        if not re.fullmatch(r"\d+", text):
            return None
        n = int(text)
    return n if n > 0 else None


# 空白も日本語も含まない長い連なり（URL や長い英単語）。折り返せる所が無く横にあふれる
_LONG_RUN = re.compile(r"[^\s\u200b\u3000-\u9fff\uff00-\uffef]{21,}")
_ZWSP = "\u200b"   # 見えない「ここで折り返してよい」印


def _clean(text: str, one_line: bool = False) -> str:
    """スライドに入れる前に、制御文字を落とす（改行は残す）。one_line なら改行も空白に。

    絵文字の結合に使う文字（ZWJ など）は落とさない（家族の絵文字などが崩れるため）。
    空白の無い長い英数字の連なりには、12字ごとに見えない折り返しの印を入れる。
    何度通しても同じ結果になる（印は連なりの区切りとして数える）。
    """
    text = "".join(ch for ch in str(text)
                   if ch == "\n" or unicodedata.category(ch) != "Cc")
    if one_line:
        text = " ".join(text.split("\n"))
    return _LONG_RUN.sub(lambda m: _ZWSP.join(m.group(0)[i:i + 12]
                                               for i in range(0, len(m.group(0)), 12)), text)


def _items(value, one_line: bool = True) -> list:
    """リストの項目を、画面に出せる文字列だけにして返す（None や空は落とす）。

    「None」という文字がそのまま出ないように、リストを読むところは必ずここを通す。
    """
    if not isinstance(value, (list, tuple)):
        return []
    out = []
    for item in value:
        if item is None or isinstance(item, (dict, list, tuple)):
            continue
        text = _clean(item, one_line=one_line).strip()
        if text:
            out.append(text)
    return out


def _half(text: str) -> str:
    """全角の数字・コロンを半角にする（「０９：００」→「09:00」）。"""
    return unicodedata.normalize("NFKC", text)


def _date_of(travel_date, day_num):
    """旅行日が具体的な日付なら、N日目の日付（date）。分からなければ None。"""
    m = _DATE_RE.search(_half(str(travel_date or "")))
    if not m or not day_num:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3))) + timedelta(days=day_num - 1)
    except ValueError:
        return None


def _day_date(travel_date, day_num) -> str:
    """N日目の日付を「11月4日（水）」の形で。分からなければ空。"""
    d = _date_of(travel_date, day_num)
    return f"{d.month}月{d.day}日（{_WEEKDAYS[d.weekday()]}）" if d else ""


def _weather_for(weather_days, d) -> str:
    """その日の天気を「☀️ 12° / 5°」の形で。予報が無ければ空。"""
    if not d or not weather_days:
        return ""
    for w in weather_days:
        if w.get("date") == d.isoformat():
            temps = ""
            if w.get("tmax") is not None and w.get("tmin") is not None:
                temps = f"  {round(w['tmax'])}° / {round(w['tmin'])}°"
            return f"{w.get('emoji', '')}{temps}".strip()
    return ""


# ----------------------------------------------------------------------
# タイムラインの1行を読む: 時刻・中身・分類・太字にする地名
# ----------------------------------------------------------------------
_MEAL_RE = re.compile(r"昼食|夕食|朝食|ランチ|ディナー|ごはん|食事|食べ歩き|BBQ|バーベキュー")
_CAFE_RE = re.compile(r"カフェ|ひと休み|一休み|おやつ|スイーツ|ティー")
_STAY_RE = re.compile(r"チェックイン|チェックアウト|就寝|宿に戻|ホテルに戻|旅館に戻|ホテルで休")
_FLY_RE = re.compile(r"空港|フライト|航空|搭乗|[A-Z]{2}\s?\d{2,4}便|\(AF|（AF|便）")
_MOVE_RE = re.compile(r"(発|着)([（(、\s]|$)|移動|で[^、。]{1,14}へ|へ向かう|帰路|帰宅")

# 分類ごとの目印（バッジの絵文字と色）
_KINDS = {
    "stay":   ("🏨", "#fbf3d5"),
    "meal":   ("🍱", BLUSH),
    "cafe":   ("☕", BLUSH),
    "fly":    ("✈️", MEADOW),
    "move":   ("🚄", MEADOW),
    "spot":   ("✨", LEAF),
}


def _place_names(plan: dict) -> list:
    """プランの観光地・お店・宿の名前（「（現地語名）」は外す）。長い順に並べる。"""
    names = set()
    for key in ("spots", "restaurants", "accommodation"):
        for raw in _items(plan.get(key)):
            base = re.split(r"[（(]", raw)[0].strip()
            if len(base) >= 2:
                names.add(base)
    return sorted(names, key=len, reverse=True)


def _kind(text: str, places: list) -> str | None:
    """予定の分類。宿 > 食事 > カフェ > 観光地（名前が先頭にある） > 飛行機 > 移動。"""
    if _STAY_RE.search(text):
        return "stay"
    if _MEAL_RE.search(text):
        return "meal"
    if _CAFE_RE.search(text):
        return "cafe"
    if any(text.startswith(n) for n in places):
        return "spot"
    if _FLY_RE.search(text):
        return "fly"
    if _MOVE_RE.search(text):
        return "move"
    if any(n in text for n in places):
        return "spot"
    return None


def _name_styles(text: str, places: list) -> list:
    """予定の中に出てくる地名を太字にする範囲（UTF-16 の位置）。重ならないように。"""
    taken, styles = [], []
    for name in places:
        i = text.find(name)
        if i < 0 or any(i < b and a < i + len(name) for a, b in taken):
            continue
        taken.append((i, i + len(name)))
        start = _u16(text[:i])
        style, fields = _bold()
        styles.append((start, start + _u16(name), style, fields))
    return styles


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
        props["contentAlignment"] = "MIDDLE" if kind in ("FLOW_CHART_TERMINATOR", "ELLIPSE") else "TOP"
        fields.append("contentAlignment")
        self.requests.append({"updateShapeProperties": {
            "objectId": oid, "shapeProperties": props, "fields": ",".join(fields)}})
        return oid

    def text(self, oid, text, size=12, color=INK, bold=False, align="START",
             line_spacing=125, styles=(), space_below=0):
        """図形に文字を入れる。styles は [(開始, 終了, {style}, fields)]（UTF-16 の位置）。"""
        clean = _clean(text)
        if clean != text:
            # 位置がずれるので、落とした文字があれば範囲の太字は付けない
            text, styles = clean, ()
        if not text.strip():
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
        """枠も塗りもない文字だけの箱。

        高さは最低でも「1行＋上下の余白」にする。スライドの文字の箱は内側に
        上下 0.05 インチ（約3.6pt）ずつ余白があり、文字の高さぴったりの箱だと
        数ポイントはみ出す（見えないが、箱が文字に足りていないのは気持ち悪い）。
        """
        size, spacing = kw.get("size", 12), kw.get("line_spacing", 125)
        h = max(h, _line_height(size, spacing) + 8)
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
        text = _clean(text, one_line=True)
        w = _width(text) * size + pad * 2
        oid = self.shape(page, "FLOW_CHART_TERMINATOR", x, y, w, h, fill=fill, outline=outline)
        self.text(oid, text, size=size, color=color, bold=bold, align="CENTER", line_spacing=100)
        return x + w

    def badge(self, page, x, y, emoji, d=34, fill=MEADOW):
        """丸いバッジに絵文字（分類の目印）。

        絵文字は丸の中ではなく、丸より広い透明な箱を重ねて真ん中に置く。図形の
        文字には左右 0.1 インチ（約7.2pt）ずつ余白があり、API からは変えられない
        ので、小さな丸だと絵文字の幅が足りず、真ん中からずれてしまう。
        """
        self.shape(page, "ELLIPSE", x, y, d, d, fill=fill)
        size = round(d * 0.42, 1)
        box_h = _line_height(size, 100) + 8
        oid = self.shape(page, "TEXT_BOX", x - 10, y + (d - box_h) / 2, d + 20, box_h)
        self.text(oid, emoji, size=size, align="CENTER", line_spacing=100)

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

    # 行き先は2行まで（それ以上は「…」）。長いほど字を小さく
    dest = _clean(plan.get("destination") or "旅のしおり", one_line=True).strip() or "旅のしおり"
    size = 44 if _width(dest) <= 7 else 32 if _width(dest) <= 11 else 24
    per_line = 380 / size * _WRAP_SAFETY
    dest = _clip(dest, per_line * 2)
    lines_needed = max(1, math.ceil(_width(dest) / per_line))
    title_h = lines_needed * _line_height(size, 105) + 8
    deck.label(sid, MARGIN + 8, 108, 390, title_h, dest, size=size, bold=True, line_spacing=105)
    y = 108 + title_h + 2
    deck.line(sid, MARGIN + 14, y, min(320, 24 + size * min(_width(dest), 8)), 0, weight=3)
    y += 12

    # その下の情報は、入るものだけ置く。足りなければ天気→テーマ→出発地の順に省く
    blocks = []
    sub = []
    if plan.get("departure_location"):
        sub.append(f"{_clip(_clean(plan['departure_location'], True), 14)} から")
    if plan.get("duration"):
        sub.append(f"{_clip(_clean(plan['duration'], True), 10)}の旅")
    if sub:
        blocks.append(("sub", 30, "、".join(sub)))
    chips = [t for t in [
        f"📅 {_clip(_clean(plan['travel_date'], True), 16)}" if plan.get("travel_date") else "",
        f"👥 {_num(plan.get('num_people'))}人" if _num(plan.get("num_people")) else ""] if t]
    if chips:
        blocks.append(("chips", 34, chips))
    themes = _items(plan.get("themes"))[:3]
    if themes:
        blocks.append(("themes", 28, themes))
    total, budget = _num(plan.get("total_per_person")), _num(plan.get("budget_limit"))
    if total or budget:
        blocks.append(("cost", 50, total or budget))
    days = [d for d in (weather_days or [])[:5]
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(d.get("date") or ""))]
    if days:
        blocks.append(("weather", 22, "🌤 " + "　".join(
            f"{int(d['date'][5:7])}/{int(d['date'][8:10])} {d.get('emoji', '')}" for d in days)))
    bottom = 364
    for drop in ("weather", "themes", "sub", "chips"):
        if y + sum(h for _, h, _ in blocks) <= bottom:
            break
        blocks = [b for b in blocks if b[0] != drop]

    for kind, h, value in blocks:
        if kind == "sub":
            deck.label(sid, MARGIN + 8, y, 390, 22, value, size=13, color=MUTED)
        elif kind == "chips":
            x = MARGIN + 12
            for text in value:
                if x + _width(text) * 10.5 + 28 > 440:
                    break
                x = deck.pill(sid, x, y, text, size=10.5) + 8
        elif kind == "themes":
            # 旅のテーマは、ハッシュタグ風の小さな札に（3つまで）
            x = MARGIN + 12
            for t in value:
                label = f"# {t}" if _width(t) <= 8 else f"# {t[:7]}…"
                if x + _width(label) * 9.5 + 20 > 430:
                    break
                x = deck.pill(sid, x, y, label, size=9.5, fill=MEADOW, color=GREEN_DARK,
                              outline=None, h=20, pad=10) + 6
        elif kind == "cost":
            label = "ひとりあたりの目安" if total else "ひとりあたりの予算"
            deck.label(sid, MARGIN + 12, y, 140, 18, label, size=9.5, color=MUTED)
            deck.label(sid, MARGIN + 10, y + 14, 260, 30, f"{value:,}円", size=20,
                       color=COST, bold=True)
        elif kind == "weather":
            deck.label(sid, MARGIN + 12, y, 360, 20, value, size=10, color=MUTED)
        y += h

    deck.label(sid, MARGIN + 8, 379, 400, 18, "🍀 たびメイト で作った旅のしおり", size=9, color=MUTED)


def _overview(deck: _Deck, plan: dict):
    cols = [(icon, label, fill, _items(plan.get(key)))
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
    room = 188
    for size in (12, 10.5, 9.5):
        chars = max(6, int(inner / size))
        h = max(_text_height([f"・{i}" for i in c[3]], chars, size, 145) for c in cols)
        if h <= room:
            break

    def fit(items):
        """いちばん小さい字でも入らないときは、入るところまでにして「…ほか N件」で結ぶ。"""
        lines = [f"・{i}" for i in items]
        if _text_height(lines, chars, size, 145) <= room:
            return lines
        kept = list(lines)
        while len(kept) > 1:
            kept.pop()
            rest = len(lines) - len(kept)
            if _text_height(kept + [f"…ほか {rest}件"], chars, size, 145) <= room:
                return kept + [f"…ほか {rest}件"]
        return [_clip(lines[0], chars * _WRAP_SAFETY * 2)] + (
            [f"…ほか {len(lines) - 1}件"] if len(lines) > 1 else [])

    blocks = [fit(c[3]) for c in cols]
    h = max(_text_height(b, chars, size, 145) for b in blocks)
    h = max(150, min(262, h + 74))
    for n, ((icon, label, fill, _), lines) in enumerate(zip(cols, blocks)):
        x = MARGIN + n * (w + gap)
        deck.card(sid, x, 100, w, h)
        deck.tape(sid, x + w / 2, 100, w=64, h=16,
                  color=(BLUSH, LEAF, "#f6edc8")[n % 3], degrees=(-6, 5, -4)[n % 3])
        deck.badge(sid, x + 16, 118, icon, d=34, fill=fill)
        deck.label(sid, x + 56, 124, w - 64, 22, label, size=13, bold=True, color=GREEN_DARK)
        deck.label(sid, x + 16, 160, inner, h - 68, "\n".join(lines),
                   size=size, line_spacing=145)


def _clip(text: str, max_width: float) -> str:
    """1行に収まるよう、幅を超えるぶんを「…」にする。"""
    if _width(text) <= max_width:
        return text
    out = ""
    for ch in text:
        if _width(out + ch) > max_width - 1:
            break
        out += ch
    return out.rstrip("、。・ 　(（") + "…"


def _highlights(body: list, places: list) -> list:
    """その日のみどころ。プランの地名が出てくる順に（ある名前を含む短い名前は省く）。

    地名が1つも無い日（移動だけの日など）は、その日の予定の頭から拾う。
    """
    found = []
    for line in body:
        text = _split_time(line)[2]
        # 出てくる順。同じ位置なら長い名前（「近江町市場 いきいき亭」）を先に
        hits = sorted((text.find(n), -len(n), n) for n in places if n in text)
        for _, _, name in hits:
            if any(name in f or f in name for f in found):
                continue
            found.append(name)
    if not found:
        for line in body:
            text = re.split(r"[（(]", _split_time(line)[2])[0].strip()
            if text and not text.startswith("※"):
                found.append(text)
    return found


def _glance(deck: _Deck, plan: dict, weather_days=None):
    """旅のあらまし: 1日1枚の小さなカードで、日程を一目で見渡す（2日以上の旅だけ）。"""
    days = [(num, body) for num, _, body in split_days(plan.get("schedule")) if num]
    if len(days) < 2:
        return
    places = _place_names(plan)
    # 3日以下なら、その日数で横幅を分ける（カードが広くなり、名前を切らずに済む）
    per_page, cols = 8, min(4, len(days))
    gap = 14
    w = (BASE_W - MARGIN * 2 - gap * (cols - 1)) / cols
    size, spacing = 10.5, 130
    # 1行に入る字数（「・」の1字ぶんを引く）。見積もりの余裕も同じだけ見る
    one_line = int((w - 24 - 14) / size) * _WRAP_SAFETY - 1
    for start in range(0, len(days), per_page):
        chunk = days[start:start + per_page]
        sid = deck.page_head("旅のあらまし", "日ごとの みどころ" + ("（つづき）" if start else ""))
        rows = math.ceil(len(chunk) / cols)
        h = 122 if rows > 1 else 168
        top = 96 if rows > 1 else 112
        fits = max(1, int((h - 66) // _line_height(size, spacing)))
        for n, (num, body) in enumerate(chunk):
            x = MARGIN + (n % cols) * (w + gap)
            y = top + (n // cols) * (h + 14)
            deck.card(sid, x, y, w, h)
            deck.pill(sid, x + 12, y + 12, f"{num}日目", size=10, fill=GREEN, color="#ffffff",
                      outline=None, bold=True, h=22, pad=10)
            day = _date_of(plan.get("travel_date"), num)
            meta = " ".join(t for t in [_day_date(plan.get("travel_date"), num),
                                         _weather_for(weather_days, day).split(" ")[0]] if t)
            if meta:
                deck.label(sid, x + 12, y + 38, w - 20, 18, meta, size=9, color=MUTED)
            spots = [_clip(n, one_line) for n in _highlights(body, places)[:fits]]
            if spots:
                deck.label(sid, x + 12, y + 56, w - 24, h - 62, "\n".join(f"・{n}" for n in spots),
                           size=size, line_spacing=spacing)


# タイムラインの寸法
_TL_X = 246          # 縦線の x
_TL_TIME_X = 260     # 時刻の欄の左端
_TL_TEXT_X = 324     # 予定の左端
_TL_TEXT_W = BASE_W - MARGIN - _TL_TEXT_X
_TL_TOP, _TL_BOTTOM = 52, 372
_TL_SIZE, _TL_SPACING, _TL_GAP = 12, 120, 9


def _entry_height(text: str, width: float) -> float:
    chars = max(6, int((width - 14) / _TL_SIZE))
    return _text_height([text], chars, _TL_SIZE, _TL_SPACING)


def _split_time(line: str) -> tuple:
    """「09:00〜11:00 兼六園」→ ("09:00", "〜11:00", "兼六園")。時刻が無ければ ("", "", 行)。"""
    # 合わせるのは元の行のまま（全角のかっこ等を半角に変えて見せないため）。
    # 半角にするのは時刻の部分だけ
    m = _TIME_RE.match(line)
    if not m or not m.group(2):
        return "", "", line
    times = re.split(r"\s*[〜~\-–]\s*", _half(m.group(1)))
    start = times[0]
    until = f"〜{times[1]}" if len(times) > 1 else ""
    return start, until, m.group(2)


def _timeline_pages(body: list) -> list:
    """1日の予定を、タイムラインの高さに収まるページに分ける。

    1件は (開始時刻, 終了時刻, 中身, 高さ)。終了時刻があるときは時刻の欄が
    2行になるので、中身が1行でもその高さを確保する。
    """
    pages, current, used = [], [], 0
    room = _TL_BOTTOM - _TL_TOP
    for line in body:
        start, until, text = _split_time(line)
        width = _TL_TEXT_W if start else BASE_W - MARGIN - _TL_TIME_X
        need = _entry_height(text, width)
        if until:
            need = max(need, _line_height(_TL_SIZE, _TL_SPACING) + _line_height(9.5, 110))
        need += _TL_GAP
        if current and used + need > room:
            pages.append(current)
            current, used = [], 0
        current.append((start, until, text, need))
        used += need
    if current:
        pages.append(current)
    return pages


def _schedule(deck: _Deck, plan: dict, weather_days=None):
    places = _place_names(plan)
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
            day = _date_of(plan.get("travel_date"), num or 1)
            when = _day_date(plan.get("travel_date"), num or 1)
            if when:
                deck.label(sid, 30, y, 170, 20, when, size=11, color=INK)
                y += 22
            sky = _weather_for(weather_days, day)
            if sky:
                deck.pill(sid, 30, y + 2, sky, size=10, fill=SURFACE, h=22, pad=10)
                y += 32
            if sub:
                deck.label(sid, 30, y, 166, 56, sub, size=11, color=MUTED, line_spacing=130)
            if n:
                deck.label(sid, 30, 250, 170, 18, "（つづき）", size=10, color=MUTED)
            deck.image(sid, "mate-head.png", 30, 300, 66, 66)

            # 右: 時刻のタイムライン
            total = sum(e[3] for e in page) - _TL_GAP
            deck.line(sid, _TL_X, _TL_TOP + 6, 0, max(8, total - 6), color=WAVY, weight=2, dash="DOT")
            y = _TL_TOP
            for start, until, text, need in page:
                if start:
                    kind = _kind(text, places)
                    if kind:
                        # 分類の目印: 線の上に小さな丸いバッジ
                        emoji, fill = _KINDS[kind]
                        deck.badge(sid, _TL_X - 11, y - 2, emoji, d=22, fill=fill)
                    else:
                        deck.shape(sid, "ELLIPSE", _TL_X - 5, y + 4, 10, 10, fill=GREEN)
                    deck.label(sid, _TL_TIME_X, y - 3, 60, 20, start, size=_TL_SIZE,
                               bold=True, color=GREEN_DARK, line_spacing=_TL_SPACING)
                    if until:
                        deck.label(sid, _TL_TIME_X, y + 14, 60, 16, until, size=9.5,
                                   color=MUTED, line_spacing=110)
                    deck.label(sid, _TL_TEXT_X - 7, y - 3, _TL_TEXT_W + 7, need, text,
                               size=_TL_SIZE, line_spacing=_TL_SPACING,
                               styles=_name_styles(text, places))
                else:
                    deck.shape(sid, "ELLIPSE", _TL_X - 3, y + 6, 6, 6, fill=SURFACE,
                               outline=GREEN, weight=1)
                    deck.label(sid, _TL_TIME_X - 7, y - 3, BASE_W - MARGIN - _TL_TIME_X + 7, need,
                               text, size=_TL_SIZE, line_spacing=_TL_SPACING, color=MUTED)
                y += need


def _costs(deck: _Deck, plan: dict):
    lines = _items(plan.get("budget_estimate"))
    total = _num(plan.get("total_per_person"))
    budget, people = _num(plan.get("budget_limit")), _num(plan.get("num_people"))
    if not lines and not total:
        return

    def pick(line):
        if line.startswith("■") or "合計" in line:
            return len(line), (COST if "合計" in line else GREEN_DARK)
        return None

    # 1枚目は左に大きな数字、右に内訳。2枚目以降は内訳だけを広く
    first_w, wide_w = 392, BASE_W - MARGIN * 2
    first_chars, wide_chars = int((first_w - 46) / 11.5), int((wide_w - 46) / 11.5)
    # 1枚に入る行数は、カードの高さ（最大268pt）から内側の余白を引いて決める
    max_lines = int((268 - 24 - 8) // _line_height(11.5, 130))
    first = _paginate(lines, first_chars, max_lines, is_heading=lambda s: s.startswith("■"))[:1] if lines else [[]]
    rest = lines[len(first[0]):]
    pages = first + (_paginate(rest, wide_chars, max_lines,
                               is_heading=lambda s: s.startswith("■")) if rest else [])

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
                size = 26 if total < 10 ** 7 else 20
                deck.label(sid, MARGIN + 26, 190, 184, 40, f"{total:,}円", size=size,
                           bold=True, color=COST, align="CENTER")
            if budget:
                deck.label(sid, MARGIN + 30, 238, 176, 20, f"予算 {budget:,}円",
                           size=10.5, color=MUTED, align="CENTER")
            if people and total:
                deck.label(sid, MARGIN + 30, 256, 176, 20, f"{people}人で {total * people:,}円",
                           size=10.5, color=MUTED, align="CENTER")
            _budget_bar(deck, sid, total, budget)
            x, w, chars = 288, first_w, first_chars
        else:
            x, w, chars = MARGIN, wide_w, wide_chars
        if page:
            text, styles = _join_with_styles(page, pick)
            h = max(120, min(268, _text_height(page, chars, 11.5, 130) + 30))
            deck.card(sid, x, 98, w, h, text, size=11.5, line_spacing=130, styles=styles)


def _budget_bar(deck: _Deck, sid, total, budget):
    """予算のうち、どれだけ使う見込みかを細い棒で。こえるときはピンクで知らせる。"""
    total, budget = _num(total), _num(budget)
    if not total or not budget:
        return
    x, y, w, h = MARGIN + 22, 330, 192, 10
    ratio = total / budget
    deck.shape(sid, "FLOW_CHART_TERMINATOR", x, y, w, h, fill=MEADOW)
    over = ratio > 1
    deck.shape(sid, "FLOW_CHART_TERMINATOR", x, y, max(h * 1.6, w * min(ratio, 1)), h,
               fill=PINK if over else GREEN)
    note = (f"予算より {total - budget:,}円 多め" if over
            else f"予算の {round(ratio * 100)}%（あと {budget - total:,}円）")
    deck.label(sid, x - 6, y + 12, w + 12, 18, note, size=9.5,
               color=PINK if over else GREEN_DARK, align="CENTER")


def _packing(deck: _Deck, plan: dict):
    items = _items(plan.get("packing_list"))[:21]
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
        oid = deck.shape(sid, "FLOW_CHART_TERMINATOR", x, y, w, h, fill=SURFACE, outline=BORDER)
        name = item if _width(item) <= 13 else item[:12] + "…"
        deck.text(oid, f"○  {name}", size=11.5, line_spacing=100)
    deck.confetti(sid, [(660, 360, PINK), (676, 350, GREEN), (52, 364, GOLD)])


def _fit_note(note: str, inner_width: float, max_height: float) -> tuple:
    """総評が吹き出しに収まる文字の大きさを選ぶ。最小でも入らなければ「…」で切る。

    全文はアプリのプランに残っているので、しおりでは読める大きさを優先する。
    """
    def fits(text, size):
        chars = max(1, int((inner_width - 14) / size))
        return _text_height(text.split("\n"), chars, size, 145) <= max_height

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

    # 空行が続くだけの改行は1つにまとめる（吹き出しの高さを無駄にしない）
    note = re.sub(r"\n{2,}", "\n", _clean(plan.get("feedback") or "")).strip()
    bottom = 160
    if note:
        deck.label(sid, 300, 34, 380, 18, _spaced("ちゃむから ひとこと"), size=9, color=GOLD, bold=True)
        inner_w = 380 - 40
        note, size = _fit_note(note, inner_w, 170)
        chars = max(1, int((inner_w - 14) / size))
        h = max(90, min(200, _text_height(note.split("\n"), chars, size, 145) + 34))
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
    _glance(deck, plan, weather_days)
    _schedule(deck, plan, weather_days)
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
