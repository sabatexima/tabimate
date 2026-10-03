#!/usr/bin/env python3
"""しおりスライドの下見を作り、本物のフォントで文字があふれる箱が無いかを数える。

Google スライドの実物は、ログインした人のドライブにしか作れない。そこで、
services/slides_export.py が作る要求（Slides API の batchUpdate）をそのまま
HTML に描き、Chromium で開いて確かめる。デザインを変えたら、まずこれを回す。

  ・見本のプラン（tests/data/slides_samples.json と、テストで使う旅の形）を描く
  ・Zen Maru Gothic（実物と同じフォント）を読み込んでから、文字の箱ごとに
    「行が1つ増えて下に重なる」「横にあふれる」を数える
  ・見本ごとに、全ページを並べた画像（PNG）を出す

  使い方: python3 scripts/preview_slides.py [出力先フォルダ]
  必要なもの: Chrome か Chromium（Playwright の同梱版も探す）、Pillow、
             ネットワーク（初回だけフォントを GitHub の google/fonts から取る）

下見は「近い見た目」で、実物と同じではない。図形の内側の余白（左右7.2pt・
上下3.6pt）と行の高さ（行間100%で字の1.2倍）は Slides に合わせてある。
"""
import glob
import html
import json
import os
import subprocess
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
os.environ.setdefault("SECRET_KEY", "preview")

FONTS = {
    "ZenMaruGothic-Regular.ttf": 400,
    "ZenMaruGothic-Bold.ttf": 700,
}
FONT_URL = "https://raw.githubusercontent.com/google/fonts/main/ofl/zenmarugothic/{}"


def _rgb(c):
    return "#%02x%02x%02x" % tuple(round(c.get(k, 0) * 255) for k in ("red", "green", "blue"))


def _py_index(text, u16):
    """UTF-16 の位置を、Python の文字の位置に直す。"""
    n = 0
    for i, ch in enumerate(text):
        if n >= u16:
            return i
        n += 2 if ord(ch) > 0xFFFF else 1
    return len(text)


def render(requests, out_html):
    """要求を HTML に描く。返り値はページ数。"""
    slides, objs = [], {}
    for req in requests:
        (kind, v), = req.items()
        if kind == "createSlide":
            slides.append({"id": v["objectId"], "bg": "#fff", "items": []})
        elif kind == "updatePageProperties":
            s = next(s for s in slides if s["id"] == v["objectId"])
            s["bg"] = _rgb(v["pageProperties"]["pageBackgroundFill"]["solidFill"]["color"]["rgbColor"])
        elif kind in ("createShape", "createLine", "createImage"):
            ep = v["elementProperties"]
            tr = ep["transform"]
            o = {"kind": v.get("shapeType") or ("LINE" if kind == "createLine" else "IMAGE"),
                 "m": (tr.get("scaleX", 1), tr.get("shearY", 0), tr.get("shearX", 0), tr.get("scaleY", 1),
                       tr["translateX"], tr["translateY"]),
                 "w": ep["size"]["width"]["magnitude"], "h": ep["size"]["height"]["magnitude"],
                 "fill": None, "alpha": 1, "outline": None, "text": "", "style": {}, "para": {},
                 "ranges": [], "url": v.get("url"), "valign": "TOP"}
            objs[v["objectId"]] = o
            next(s for s in slides if s["id"] == ep["pageObjectId"])["items"].append(o)
        elif kind == "updateShapeProperties":
            o, p = objs[v["objectId"]], v["shapeProperties"]
            if "shapeBackgroundFill" in p:
                sf = p["shapeBackgroundFill"]["solidFill"]
                o["fill"], o["alpha"] = _rgb(sf["color"]["rgbColor"]), sf.get("alpha", 1)
            if "outlineFill" in p.get("outline", {}):
                o["outline"] = _rgb(p["outline"]["outlineFill"]["solidFill"]["color"]["rgbColor"])
            o["valign"] = p.get("contentAlignment", "TOP")
        elif kind == "updateLineProperties":
            o, p = objs[v["objectId"]], v["lineProperties"]
            o["fill"], o["weight"] = _rgb(p["lineFill"]["solidFill"]["color"]["rgbColor"]), p["weight"]["magnitude"]
        elif kind == "insertText":
            objs[v["objectId"]]["text"] = v["text"]
        elif kind == "updateTextStyle":
            o = objs[v["objectId"]]
            if v["textRange"]["type"] == "ALL":
                o["style"] = v["style"]
            else:
                o["ranges"].append((v["textRange"]["startIndex"], v["textRange"]["endIndex"], v["style"]))
        elif kind == "updateParagraphStyle":
            objs[v["objectId"]]["para"] = v["style"]

    faces = "".join(f'@font-face{{font-family:"Zen Maru Gothic";font-weight:{w};src:url({f})}}'
                    for f, w in FONTS.items())
    out = [f'<html><head><meta charset="utf-8"><style>{faces}'
           'body{margin:0;background:#888}.s{position:relative;width:720pt;height:405pt;overflow:hidden;margin:0 0 12pt}'
           '.o{position:absolute;box-sizing:border-box;left:0;top:0;transform-origin:0 0}'
           '.t{white-space:pre-wrap;padding:3.6pt 7.2pt;font-family:"Zen Maru Gothic"}</style></head><body>']
    for s in slides:
        out.append(f'<div class="s" style="background:{s["bg"]}">')
        for o in s["items"]:
            a, b, c, d, x, y = o["m"]
            pos = (f'width:{o["w"]}pt;height:{o["h"]}pt;'
                   f'transform:matrix({a},{b},{c},{d},{x * 4 / 3},{y * 4 / 3});')
            if o["kind"] == "IMAGE":
                src = os.path.join(ROOT, "src", "static", "img", o["url"].rsplit("/", 1)[1])
                out.append(f'<img class="o" src="file://{src}" style="{pos}object-fit:contain">')
                continue
            if o["kind"] == "LINE":
                side = "border-left" if o["h"] > o["w"] else "border-top"
                out.append(f'<div class="o" style="{pos}{side}:{o["weight"]}pt dotted {o["fill"]}"></div>')
                continue
            radius = {"ELLIPSE": "50%", "FLOW_CHART_TERMINATOR": "999pt"}.get(
                o["kind"], f'{min(o["w"], o["h"]) * 0.1667}pt'
                if o["kind"] in ("ROUND_RECTANGLE", "WEDGE_ROUND_RECTANGLE_CALLOUT") else "0")
            css = pos + f"border-radius:{radius};"
            if o["fill"]:
                css += f'background:{o["fill"]};opacity:{o["alpha"]};'
            if o["outline"]:
                css += f'border:1pt solid {o["outline"]};'
            if o["valign"] == "MIDDLE":
                css += "display:flex;align-items:center;justify-content:center;"
            st, para = o["style"], o["para"]
            if st:
                css += (f'font-size:{st["fontSize"]["magnitude"]}pt;'
                        f'color:{_rgb(st["foregroundColor"]["opaqueColor"]["rgbColor"])};'
                        f'font-weight:{700 if st.get("bold") else 400};')
            if para:
                align = {"CENTER": "center", "END": "right"}.get(para.get("alignment"), "left")
                css += f'line-height:{para.get("lineSpacing", 100) / 100 * 1.2};text-align:{align};'
            text, body, i = o["text"], "", 0
            for start, end, sty in sorted((_py_index(o["text"], s0), _py_index(o["text"], e0), st0)
                                          for s0, e0, st0 in o["ranges"]):
                color = _rgb(sty["foregroundColor"]["opaqueColor"]["rgbColor"]) if "foregroundColor" in sty else "inherit"
                body += html.escape(text[i:start]) + f'<b style="color:{color}">{html.escape(text[start:end])}</b>'
                i = end
            body += html.escape(text[i:])
            if o["kind"] == "WEDGE_ROUND_RECTANGLE_CALLOUT":
                # 吹き出しの尾（Slides の既定は、中心から左に20.8%・下に62.5%の位置）
                tx, ty = x + o["w"] * (0.5 - 0.2083), y + o["h"] * (0.5 + 0.625)
                out.append(f'<svg class="o" style="width:720pt;height:405pt;overflow:visible" viewBox="0 0 720 405">'
                           f'<polygon points="{x + o["w"] * .2},{y + o["h"] - 1} {x + o["w"] * .36},{y + o["h"] - 1} {tx},{ty}"'
                           f' fill="{o["fill"]}" stroke="{o["outline"]}"/></svg>')
            out.append(f'<div class="o{" t" if text else ""}" style="{css}">{body}</div>')
        out.append("</div>")
    out.append("""<pre id="result">pending</pre><script>
document.fonts.ready.then(() => {
  const bad = [];
  document.querySelectorAll('.s').forEach((slide, si) => {
    slide.querySelectorAll('.t').forEach((el) => {
      el.style.overflow = 'hidden';
      const over = el.scrollHeight - el.clientHeight, wide = el.scrollWidth - el.clientWidth;
      el.style.overflow = '';
      const lh = parseFloat(getComputedStyle(el).lineHeight) || 16;
      // 困るのは、行が1つ増えて下の物に重なるとき（行の高さの6割以上）と、横にあふれるとき
      if (over > lh * 0.6 || wide > 3)
        bad.push((si + 1) + 'ページ: ' + (over > 2 ? '縦+' + over : '') + (wide > 2 ? ' 横+' + wide : '')
                 + ' 「' + el.textContent.slice(0, 24).replace(/\\n/g, '/') + '」');
    });
  });
  const loaded = [...document.fonts].filter(f => f.status === 'loaded').length;
  document.getElementById('result').textContent =
    (loaded < 2 ? 'NO FONT\\n' : '') + (bad.length ? bad.join('\\n') : 'NO OVERFLOW');
});
</script></body></html>""")
    with open(out_html, "w", encoding="utf-8") as f:
        f.write("".join(out))
    return len(slides)


def _chrome():
    for c in [os.environ.get("CHROME_PATH", "")] + glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome") + [
            "/usr/bin/chromium", "/usr/bin/google-chrome",
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]:
        if c and os.path.exists(c):
            return c
    sys.exit("Chrome / Chromium が見つかりません（CHROME_PATH で指定できます）")


def _plans():
    import test_slides_export as T
    samples = json.load(open(os.path.join(ROOT, "tests", "data", "slides_samples.json"), encoding="utf-8"))
    for name, s in samples.items():
        yield name, s["plan"], s["weather"]
    for name, plan in T.SHAPES.items():
        yield "形:" + name, plan, None


def main():
    out_dir = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "slides-preview")
    os.makedirs(out_dir, exist_ok=True)
    for name in FONTS:
        path = os.path.join(out_dir, name)
        if not os.path.exists(path):
            print(f"▸ フォントを取得: {name}")
            urllib.request.urlretrieve(FONT_URL.format(name), path)

    from services.slides_export import build_requests
    chrome = _chrome()
    failed = 0
    for n, (name, plan, weather) in enumerate(_plans()):
        body, images = build_requests(plan, image_url=lambda f: f"https://example/{f}", weather_days=weather)
        page = os.path.join(out_dir, f"{n:02d}.html")
        pages = render(body + images, page)
        dom = subprocess.run([chrome, "--headless", "--no-sandbox", "--disable-gpu", "--allow-file-access-from-files",
                              "--virtual-time-budget=15000", "--dump-dom", "file://" + page],
                             capture_output=True, text=True, timeout=180).stdout
        result = dom.split('<pre id="result">')[-1].split("</pre>")[0] if '<pre id="result">' in dom else "NO RESULT"
        ok = result == "NO OVERFLOW"
        failed += not ok
        print(f"  {'✓' if ok else '✗'} {name}（{pages}枚）" + ("" if ok else "\n      " + result.replace("\n", "\n      ")))
        png = os.path.join(out_dir, f"{n:02d}.png")
        subprocess.run([chrome, "--headless", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
                        "--allow-file-access-from-files", "--virtual-time-budget=15000",
                        f"--window-size=960,{pages * 556}", f"--screenshot={png}", "file://" + page],
                       capture_output=True, timeout=180)
        _contact_sheet(png, pages)
    print(f"▸ 下見: {out_dir}")
    print("▸ すべて収まりました" if not failed else f"▸ あふれあり: {failed} 件")
    return 1 if failed else 0


def _contact_sheet(png, pages):
    """全ページを2列に並べた画像にする（Pillow が無ければそのまま）。"""
    try:
        from PIL import Image
    except ImportError:
        return
    im = Image.open(png)
    tiles = [im.crop((0, i * 556, 960, i * 556 + 540)).resize((480, 270)) for i in range(pages)]
    sheet = Image.new("RGB", (970, ((pages + 1) // 2) * 275), "#777")
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % 2) * 490, (i // 2) * 275))
    sheet.save(png)


if __name__ == "__main__":
    sys.exit(main())
