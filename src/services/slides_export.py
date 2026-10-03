"""保存プランを、絵本の世界観のまま Google スライドの「旅のしおり」にする。

流れは2段:
  1) build_requests(): プランから Slides API の batchUpdate 要求を組み立てる。
     ネットワークに出ない純粋な関数なので、テストで中身を丸ごと確かめられる。
  2) create_presentation(): 本人のアクセストークンで空のスライドを作り、
     1) の要求を流し込んで、開くためのURLを返す。

ファイルは本人の Google ドライブに作られる（drive.file 権限＝このアプリが
作ったファイルにしか触れない、いちばん狭い権限）。

世界観をそろえるために:
  ・文字は画面と同じ Zen Maru Gothic（Google Fonts なのでスライドでも使える）
  ・色は layout.css のトークンと同じ（クリームの紙・若葉色・金茶のキッカー）
  ・ちゃむの絵は、このサイトが公開している static の画像をそのまま貼る
    （Google がURLから取りに来るので、手元の localhost では貼れない。
      その場合は絵だけ省いて、しおり本体は作る）

文字があふれないよう、1枚に入る行数を見積もってページを分ける。
Slides API は文字の大きさを自動で縮めてくれない（API からは設定できない）ため。
"""

import math
import re

from logger import get_logger

logger = get_logger("services.slides_export")

API = "https://slides.googleapis.com/v1/presentations"
FONT = "Zen Maru Gothic"

# layout.css のトークンと同じ色
INK = "#4a4540"          # --text-main
MUTED = "#8a817a"        # --text-muted
GREEN = "#4fa83a"        # --primary-color
GREEN_DARK = "#3b8a2c"   # --primary-dark
GOLD = "#c2a05e"         # しおりのキッカー（金茶）
CREAM = "#fdfaf2"        # 背景グラデの上端
MEADOW = "#edf3de"       # 背景グラデの下端（淡い若葉色）
SURFACE = "#fffdf8"      # --surface（カードの面）
BORDER = "#e7ddca"       # --border
GLOW = "#f6f6a5"         # --glow-cream（四つ葉まわりの淡い光）
WAVY = "#b9d9a5"         # 見出しの波線（rgba(122,190,96,.5) をクリームに重ねた色）
COST = "#a9772f"         # しおりの費用の色

# レイアウトは 720×405pt（16:9）を基準に書き、実際のページの大きさに合わせて伸縮する
BASE_W, BASE_H = 720.0, 405.0
EMU_PER_PT = 12700

# 「1日目」「【2日目】金沢」「3日目：市内」などの見出し行（agents.py の _days_in と同じ規則）
_DAY_RE = re.compile(r'^[【\[]?\s*(\d+)\s*日目[】\]]?\s*[:：]?\s*(.*)$')
_TIME_RE = re.compile(r'^\s*\d{1,2}[:：]\d{2}(\s*[〜~\-–]\s*\d{1,2}[:：]\d{2})?')


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


def _visual_lines(lines: list, chars_per_line: int) -> int:
    """折り返しを含めて、何行ぶんの高さになるかを見積もる（全角1字=1、半角は0.55字）。"""
    total = 0
    for line in lines:
        width = sum(1 if ord(c) > 0x2000 else 0.55 for c in line)
        total += max(1, math.ceil(width / chars_per_line))
    return total


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
    """スケジュールの行を日ごとに分ける。[(見出し, [行…]), …] を返す。

    「N日目」の行が無い（日帰り）ときは、見出し None の1日だけにする。
    見出し行に「：金沢市内」のような副題があれば、見出しに残す。
    """
    days, title, body = [], None, []
    for raw in schedule or []:
        line = str(raw).strip()
        if not line:
            continue
        m = _DAY_RE.match(line)
        if m:
            if title is not None or body:
                days.append((title, body))
            sub = m.group(2).strip()
            title = f"{int(m.group(1))}日目" + (f"　{sub}" if sub else "")
            body = []
        else:
            body.append(line)
    if title is not None or body:
        days.append((title, body))
    return days


class _Deck:
    """batchUpdate の要求を積み上げる。図形の ID 振りと座標の伸縮をここに集める。"""

    def __init__(self, page_w_pt: float, page_h_pt: float, image_url=None):
        self.sx = page_w_pt / BASE_W
        self.sy = page_h_pt / BASE_H
        self.requests: list = []
        self.image_requests: list = []
        self.image_url = image_url  # ファイル名 → 公開URL。None なら絵は貼らない
        self._n = 0
        self.slides = 0

    def _id(self, kind: str) -> str:
        self._n += 1
        return f"tm_{kind}_{self._n:03d}"

    def _box(self, page, x, y, w, h) -> dict:
        return {
            "pageObjectId": page,
            "size": {"width": {"magnitude": round(w * self.sx, 2), "unit": "PT"},
                     "height": {"magnitude": round(h * self.sy, 2), "unit": "PT"}},
            "transform": {"scaleX": 1, "scaleY": 1, "unit": "PT",
                          "translateX": round(x * self.sx, 2),
                          "translateY": round(y * self.sy, 2)},
        }

    # ---- ページと図形 ----
    def slide(self, meadow_top: float = 372) -> str:
        """新しいページ。クリームの紙に、下だけ淡い若葉色の帯を敷く（画面の背景グラデ）。"""
        sid = self._id("slide")
        self.requests.append({"createSlide": {
            "objectId": sid, "insertionIndex": self.slides,
            "slideLayoutReference": {"predefinedLayout": "BLANK"}}})
        self.slides += 1
        self.requests.append({"updatePageProperties": {
            "objectId": sid,
            "pageProperties": {"pageBackgroundFill": {"solidFill": {"color": {"rgbColor": _rgb(CREAM)}}}},
            "fields": "pageBackgroundFill.solidFill.color"}})
        self.shape(sid, "RECTANGLE", 0, meadow_top, BASE_W, BASE_H - meadow_top, fill=MEADOW)
        return sid

    def shape(self, page, kind, x, y, w, h, fill=None, outline=None) -> str:
        oid = self._id("shape")
        self.requests.append({"createShape": {
            "objectId": oid, "shapeType": kind,
            "elementProperties": self._box(page, x, y, w, h)}})
        props, fields = {}, []
        if fill:
            props["shapeBackgroundFill"] = {"solidFill": {"color": {"rgbColor": _rgb(fill)}}}
            fields.append("shapeBackgroundFill.solidFill.color")
        if outline:
            props["outline"] = {"outlineFill": {"solidFill": {"color": {"rgbColor": _rgb(outline)}}},
                                "weight": {"magnitude": 1, "unit": "PT"}}
            fields += ["outline.outlineFill.solidFill.color", "outline.weight"]
        else:
            props["outline"] = {"propertyState": "NOT_RENDERED"}
            fields.append("outline.propertyState")
        props["contentAlignment"] = "TOP"
        fields.append("contentAlignment")
        self.requests.append({"updateShapeProperties": {
            "objectId": oid, "shapeProperties": props, "fields": ",".join(fields)}})
        return oid

    def text(self, oid, text, size=12, color=INK, bold=False, align="START",
             line_spacing=125, styles=()):
        """図形に文字を入れる。styles は [(開始, 終了, {style}, fields)]（UTF-16 の位置）。"""
        if not text:
            return
        self.requests.append({"insertText": {"objectId": oid, "insertionIndex": 0, "text": text}})
        self.requests.append({"updateTextStyle": {
            "objectId": oid, "textRange": {"type": "ALL"},
            "style": {"fontFamily": FONT, "fontSize": {"magnitude": size, "unit": "PT"},
                      "bold": bold, "foregroundColor": {"opaqueColor": {"rgbColor": _rgb(color)}}},
            "fields": "fontFamily,fontSize,bold,foregroundColor"}})
        self.requests.append({"updateParagraphStyle": {
            "objectId": oid, "textRange": {"type": "ALL"},
            "style": {"alignment": align, "lineSpacing": line_spacing},
            "fields": "alignment,lineSpacing"}})
        for start, end, style, fields in styles:
            if end > start:
                self.requests.append({"updateTextStyle": {
                    "objectId": oid,
                    "textRange": {"type": "FIXED_RANGE", "startIndex": start, "endIndex": end},
                    "style": style, "fields": fields}})

    def label(self, page, x, y, w, h, text, **kw) -> str:
        """枠も塗りもない文字だけの箱。"""
        oid = self.shape(page, "TEXT_BOX", x, y, w, h)
        self.text(oid, text, **kw)
        return oid

    def wavy(self, page, x, y, w):
        """見出しの下の点線（画面の wavy underline の代わり）。"""
        oid = self._id("line")
        self.requests.append({"createLine": {
            "objectId": oid, "lineCategory": "STRAIGHT",
            "elementProperties": self._box(page, x, y, w, 0.01)}})
        self.requests.append({"updateLineProperties": {
            "objectId": oid,
            "lineProperties": {"lineFill": {"solidFill": {"color": {"rgbColor": _rgb(WAVY)}}},
                               "weight": {"magnitude": 2.5, "unit": "PT"}, "dashStyle": "DOT"},
            "fields": "lineFill.solidFill.color,weight,dashStyle"}})

    def image(self, page, name, x, y, w, h):
        """ちゃむの絵。貼れなくても本体は作れるよう、別の要求として分けておく。"""
        if not self.image_url:
            return
        self.image_requests.append({"createImage": {
            "objectId": self._id("img"), "url": self.image_url(name),
            "elementProperties": self._box(page, x, y, w, h)}})

    # ---- よく使う組み合わせ ----
    def page_head(self, kicker: str, heading: str) -> str:
        """中身のページ: 金茶のキッカー・見出し・点線・右上のちゃむ。"""
        sid = self.slide()
        self.label(sid, 40, 18, 560, 20, _spaced(kicker), size=9, color=GOLD, bold=True)
        self.label(sid, 40, 34, 600, 36, heading, size=22, bold=True)
        self.wavy(sid, 44, 74, min(320, 40 + 22 * len(heading)))
        self.image(sid, "mate-head.png", 652, 16, 46, 46)
        return sid

    def card(self, page, x, y, w, h, text="", **kw) -> str:
        """角の丸いカードに文字を載せる。

        文字はカードそのものではなく、内側に一回り小さい箱を重ねて入れる。
        スライドの角丸は API から丸みを変えられず、大きなカードほど角が深く
        えぐれるので、カードに直接入れると1行目の頭が角にかかってしまう。
        """
        self.shape(page, "ROUND_RECTANGLE", x, y, w, h, fill=SURFACE, outline=BORDER)
        return self.label(page, x + 16, y + 12, w - 32, h - 24, text, **kw)


def _fit_height(lines: list, chars_per_line: int, size: float, spacing: float,
                low: float = 110, high: float = 268) -> float:
    """中身に合わせたカードの高さ。少ないときに大きな空白のカードにならないように。"""
    need = _visual_lines(lines, chars_per_line) * size * spacing / 100 * 1.25 + 30
    return max(low, min(high, need))


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


def _cover(deck: _Deck, plan: dict, weather_days):
    sid = deck.slide(meadow_top=332)
    deck.shape(sid, "ELLIPSE", 452, 54, 250, 250, fill=GLOW)
    deck.image(sid, "mate.png", 478, 62, 200, 268)

    dest = str(plan.get("destination") or "旅のしおり")
    size = 40 if len(dest) <= 8 else 30 if len(dest) <= 14 else 22
    deck.label(sid, 56, 70, 380, 24, _spaced("旅のしおり"), size=11, color=GOLD, bold=True)
    deck.label(sid, 56, 92, 400, 92, dest, size=size, bold=True, line_spacing=110)
    deck.wavy(sid, 60, 186, min(330, 30 + size * len(dest)))

    meta = []
    if plan.get("travel_date"):
        meta.append(f"📅 {plan['travel_date']}")
    sub = " ・ ".join(x for x in [
        f"⏱️ {plan['duration']}" if plan.get("duration") else "",
        f"👥 {plan['num_people']}人" if plan.get("num_people") else "",
    ] if x)
    if sub:
        meta.append(sub)
    if plan.get("departure_location"):
        meta.append(f"📍 {plan['departure_location']} から")
    cost = None
    if plan.get("total_per_person"):
        cost = f"💴 費用の目安 {int(plan['total_per_person']):,}円/人"
    elif plan.get("budget_limit"):
        cost = f"💴 予算 {int(plan['budget_limit']):,}円/人"
    if cost:
        meta.append(cost)
    if weather_days:
        meta.append("🌤 " + "　".join(
            f"{int(d['date'][5:7])}/{int(d['date'][8:10])} {d.get('emoji', '')}"
            for d in weather_days[:5] if d.get("date")))
    text, styles = _join_with_styles(
        meta, lambda line: (len(line), COST) if line == cost else None)
    deck.label(sid, 58, 200, 390, 120, text, size=13, line_spacing=140, styles=styles)
    deck.label(sid, 56, 350, 600, 22, "🍀 たびメイト で作った旅のしおり", size=10, color=MUTED)


def _overview(deck: _Deck, plan: dict):
    cols = [(icon, label, [str(i) for i in plan.get(key) or [] if str(i).strip()])
            for icon, label, key in (("✨", "主要観光地", "spots"),
                                     ("🍱", "グルメ", "restaurants"),
                                     ("🏨", "宿泊", "accommodation"))]
    cols = [c for c in cols if c[2]]
    if not cols:
        return
    sid = deck.page_head("旅のなかみ", "この旅で めぐるところ")
    gap, left, width = 16, 40, 640
    w = (width - gap * (len(cols) - 1)) / len(cols)
    chars = max(8, int((w - 40) / 12))
    blocks = [[f"{icon} {label}"] + [f"・{i}" for i in items] for icon, label, items in cols]
    size = 12 if max(_visual_lines(b, chars) for b in blocks) <= 12 else 10
    # 列の高さはそろえる（いちばん長い列に合わせる）
    h = max(_fit_height(b, chars, size, 140) for b in blocks)
    for n, lines in enumerate(blocks):
        text, styles = _join_with_styles(
            lines, lambda line, head=lines[0]: (len(line), GREEN_DARK) if line == head else None)
        deck.card(sid, left + n * (w + gap), 92, w, h, text,
                  size=size, line_spacing=140, styles=styles)


def _schedule(deck: _Deck, plan: dict):
    days = split_days(plan.get("schedule"))
    single = len(days) == 1 and days[0][0] is None
    for title, body in days:
        if not body:
            continue
        heading = title or ("当日のスケジュール" if single else "スケジュール")
        pages = _paginate(body, chars_per_line=46, max_lines=12)
        for n, page in enumerate(pages):
            suffix = "（つづき）" if n else ""
            sid = deck.page_head("スケジュール", heading + suffix)
            text, styles = _join_with_styles(
                page, lambda line: ((m.end(), GREEN_DARK) if (m := _TIME_RE.match(line)) else None))
            deck.card(sid, 40, 92, 640, _fit_height(page, 46, 12, 135), text,
                      size=12, line_spacing=135, styles=styles)


def _costs(deck: _Deck, plan: dict):
    lines = [str(x).strip() for x in plan.get("budget_estimate") or [] if str(x).strip()]
    if not lines:
        return

    def pick(line):
        if line.startswith("■") or "合計" in line:
            return len(line), (COST if "合計" in line else GREEN_DARK)
        return None

    pages = _paginate(lines, chars_per_line=48, max_lines=13,
                      is_heading=lambda line: line.startswith("■"))
    for n, page in enumerate(pages):
        sid = deck.page_head("旅の費用", "費用の見積もり" + ("（つづき）" if n else ""))
        text, styles = _join_with_styles(page, pick)
        deck.card(sid, 40, 92, 640, _fit_height(page, 48, 11.5, 130), text,
                  size=11.5, line_spacing=130, styles=styles)


def _packing(deck: _Deck, plan: dict):
    items = [str(i).strip() for i in plan.get("packing_list") or [] if str(i).strip()]
    if not items:
        return
    sid = deck.page_head("持ちもの", "わすれずに 持っていこう")
    items = items[:20]  # 持ちものは最大20個（packing.py の上限）。それ以上は1枚に入らない
    half = math.ceil(len(items) / 2)
    chunks = [[f"☐ {i}" for i in c] for c in (items[:half], items[half:]) if c]
    h = max(_fit_height(c, 22, 12, 150) for c in chunks)
    for n, chunk in enumerate(chunks):
        deck.card(sid, 40 + n * 328, 92, 312, h, "\n".join(chunk), size=12, line_spacing=150)


def _fit_note(note: str, inner_width: float, max_height: float) -> tuple:
    """総評がカードに収まる文字の大きさを選ぶ。最小でも入らなければ「…」で切る。

    全文はアプリのプランに残っているので、しおりでは読める大きさを優先する。
    """
    def fits(text, size):
        chars = max(1, int((inner_width - 14) / size))
        return _visual_lines([text], chars) * size * 145 / 100 * 1.25 <= max_height

    for size in (12, 10.5, 9):
        if fits(note, size):
            return note, size
    while len(note) > 1 and not fits(note + "…", 9):
        note = note[:-1]
    return note.rstrip("、。 　") + "…", 9


def _closing(deck: _Deck, plan: dict):
    sid = deck.slide(meadow_top=332)
    deck.shape(sid, "ELLIPSE", 470, 64, 230, 230, fill=GLOW)
    deck.image(sid, "mate.png", 492, 70, 186, 250)
    deck.label(sid, 48, 40, 400, 22, _spaced("ちゃむから ひとこと"), size=10, color=GOLD, bold=True)
    note = str(plan.get("feedback") or "").strip()
    bottom = 70
    if note:
        note, size = _fit_note(note, inner_width=410 - 32, max_height=190 - 24)
        chars = int((410 - 32 - 14) / size)
        h = _fit_height([note], chars, size, 145, low=80, high=190)
        deck.card(sid, 44, 70, 410, h, note, size=size, line_spacing=145)
        bottom = 70 + h
    deck.label(sid, 44, max(bottom + 18, 200), 420, 50, "いってらっしゃい！🍀",
               size=28, color=GREEN_DARK, bold=True)


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
