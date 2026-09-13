#!/usr/bin/env python3
"""README に載せる図版を作り直す。

    python3 docs/img/build_readme_figures.py

画面のスクリーンショット（docs/img/screen-*.png）は縦の長さがまちまちで、
そのまま横に並べると下端がガタつく。ここで同じ高さに切りそろえ、角丸と
ラベルをつけて1枚にまとめる。発表資料の図版（docs/presentation）と同じ
仕組み（HTML をヘッドレス Chromium で撮る）なので、色と書体も揃う。

出力:
  readme-screens.png / readme-screens-en.png   3画面を横並び
  readme-chat.png    / readme-chat-en.png      相談 → しおりができる（2画面）
"""
import base64
import re
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "presentation"))
import build_images as bi  # noqa: E402  発表資料の図版と同じ土台を使う

bi.OUT = HERE  # 出力先を docs/img に向ける


def _shot(name: str) -> str:
    return "data:image/png;base64," + base64.b64encode((HERE / name).read_bytes()).decode()


PANEL_CSS = """
  .stage { padding: 44px 40px 36px; }
  .row { display: flex; gap: 40px; justify-content: center; align-items: flex-start; }
  .panel { flex: 0 0 auto; display: flex; flex-direction: column; align-items: center; }
  .shot { width: 460px; height: 820px; overflow: hidden; border-radius: 26px;
          border: 1.5px solid var(--border); background: #fff;
          box-shadow: 0 10px 28px rgba(120,110,90,.16); }
  .shot img { width: 100%; display: block; }
  .cap { margin-top: 18px; font-size: 24px; font-weight: 700; text-align: center; }
  .sub { margin-top: 4px; font-size: 16px; color: var(--muted); text-align: center; }
  .arrow { align-self: center; font-size: 44px; color: #b9cfa8; font-weight: 700; margin-top: -60px; }
"""


def screens(suffix: str, labels):
    """3画面を横並びに。ラベルは (見出し, 添え書き) の3組。"""
    panels = ""
    for name, (cap, sub) in zip(["screen-journal", "screen-bookshelf", "screen-plan-detail"], labels):
        panels += f"""<div class="panel"><div class="shot"><img src="{_shot(name + suffix + '.png')}"></div>
                       <div class="cap">{cap}</div><div class="sub">{sub}</div></div>"""
    return bi.figure("readme-screens" + suffix, 1600, 960, PANEL_CSS, f'<div class="row">{panels}</div>', pad=0)


def chat(suffix: str, labels):
    """相談しているところ → しおりができたところ。1枚の長いスクショから2か所を切り出す。"""
    src = _shot("screen-chat.png")
    (cap1, sub1), (cap2, sub2) = labels
    body = f"""<div class="row">
      <div class="panel"><div class="shot"><img src="{src}" style="margin-top:0"></div>
        <div class="cap">{cap1}</div><div class="sub">{sub1}</div></div>
      <div class="arrow">›</div>
      <div class="panel"><div class="shot"><img src="{src}" style="margin-top:-540px"></div>
        <div class="cap">{cap2}</div><div class="sub">{sub2}</div></div>
    </div>"""
    return bi.figure("readme-chat" + suffix, 1600, 960, PANEL_CSS, body, pad=0)


FIGURES = [
    screens("", [("旅の振り返り", "写真を入れると付箋になる"),
                 ("保存プラン", "作ったしおりが本棚に並ぶ"),
                 ("プラン詳細", "天気・地図・持ち物・おこづかい帳")]),
    screens("-en", [("Trip journal", "Photos become sticky notes"),
                    ("Saved plans", "Your itineraries on a shelf"),
                    ("Plan detail", "Weather, map, packing list, ledger")]),
    chat("", [("話しかける", "足りないことだけ、ちゃむが聞き返す"),
              ("しおりができる", "観光・食・宿・時間割・費用まで")]),
    chat("-en", [("Just talk", "Chamu asks only for what's missing"),
                 ("The itinerary appears", "Sights, food, stay, timetable, cost")]),
]


def main():
    chars = "".join(sorted({c for f in FIGURES for c in re.sub(r"<[^>]+>", "", f["html"])}))
    font_css = bi._font_css(chars)
    tmp = Path(tempfile.mkdtemp(prefix="readme-figs-"))
    try:
        for fig in FIGURES:
            out = bi.render(fig, font_css, tmp)
            print(f"  ✓ {out.name}  {fig['w']}×{fig['h']} → {out.stat().st_size // 1024}KB")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
