#!/usr/bin/env python3
"""発表スライド用の図版（PNG）を作り直す。

    python3 docs/presentation/build_images.py

図はHTMLとして書き、ヘッドレスChromiumで撮る。手で描いた画像と違って、
数字や構成を直したいときはこのファイルを直せば作り直せる。色は
src/static/css/layout.css の値をそのまま持ってきているので、アプリと
同じ見た目になる。

Chromium の場所は CHROME_PATH で上書きできる（既定はこの環境の Playwright 版）。
"""
import base64
import os
import re
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = Path(__file__).resolve().parent / "img"

# アプリと同じ色（src/static/css/layout.css）
C = {
    "green": "#4fa83a", "green_dark": "#3b8a2c", "pink": "#f08ba0",
    "text": "#4a4540", "muted": "#8a817a", "paper": "#faf6ee",
    "surface": "#fffdf8", "border": "#e7ddca", "glow": "#f6f6a5",
    "note": "#fdf6c9", "sky": "#dbeaf7",
}

CHROME = os.environ.get("CHROME_PATH", "/opt/pw-browsers/chromium")


def _b64_png(rel: str) -> str:
    data = (ROOT / rel).read_bytes()
    return "data:image/png;base64," + base64.b64encode(data).decode()


def _font_css(chars: str) -> str:
    """使う文字だけの Zen Maru Gothic を取ってきて、埋め込み用のCSSにする。

    丸ゴシックはこのアプリの声そのものなので、代替フォントでは絵本っぽさが
    出ない。取れなかったときは IPAPGothic に落ちる（形は変わるが読める）。
    """
    try:
        url = ("https://fonts.googleapis.com/css2?family=Zen+Maru+Gothic:wght@400;500;700"
               "&text=" + urllib.request.quote(chars))
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"})
        css = urllib.request.urlopen(req, timeout=40).read().decode()
        for m in re.finditer(r"https://fonts\.gstatic\.com/[^)]+", css):
            blob = urllib.request.urlopen(m.group(0), timeout=40).read()
            css = css.replace(m.group(0),
                              "data:font/woff2;base64," + base64.b64encode(blob).decode())
        return css
    except Exception as e:      # ネットが無くても図は作れるようにする
        print(f"  ! Zen Maru Gothic を取得できなかったので代替フォントで作る（{e}）")
        return ""


def shell(**kw) -> str:
    """図の共通ガワ。角丸・余白・影のとり方をここで一本化する。"""
    return f"""
    :root {{ --green:{C['green']}; --dark:{C['green_dark']}; --pink:{C['pink']};
             --text:{C['text']}; --muted:{C['muted']}; --paper:{C['paper']};
             --surface:{C['surface']}; --border:{C['border']}; --note:{C['note']}; }}
    * {{ box-sizing: border-box; margin: 0; }}
    body {{ font-family: 'Zen Maru Gothic', 'IPAPGothic', sans-serif;
            color: var(--text); background: var(--paper);
            -webkit-font-smoothing: antialiased; }}
    .stage {{ width: {kw['w']}px; height: {kw['h']}px; padding: {kw.get('pad', 64)}px;
              display: flex; flex-direction: column; position: relative; overflow: hidden;
              background:
                radial-gradient(900px 520px at 12% -8%, #fffdf5 0%, transparent 62%),
                linear-gradient(180deg, #fdfaf2 0%, #f6f4e7 60%, #eff3e2 100%); }}
    .card {{ background: var(--surface); border: 1.5px solid var(--border);
             border-radius: 20px; box-shadow: 0 6px 20px rgba(120,110,90,.09); }}
    h1 {{ font-weight: 700; letter-spacing: .01em; }}
    .eyebrow {{ color: var(--green-dark, #3b8a2c); font-weight: 700; font-size: 22px;
                letter-spacing: .18em; }}
    .title {{ font-size: 46px; font-weight: 700; }}
    .lead {{ color: var(--muted); font-size: 22px; line-height: 1.7; }}
    .em {{ color: {C['green_dark']}; font-weight: 700; }}
    """


def figure(name: str, w: int, h: int, css: str, body: str, pad: int = 64):
    return {"name": name, "w": w, "h": h,
            "html": f"<style>{shell(w=w, h=h, pad=pad)}{css}</style>"
                    f'<div class="stage">{body}</div>'}


# ----------------------------------------------------------------------
# 01 表紙
# ----------------------------------------------------------------------
def fig_cover():
    css = """
    .stage { align-items: center; justify-content: center; text-align: center; }
    .chamu { width: 210px; filter: drop-shadow(0 10px 24px rgba(120,110,90,.18)); }
    .name { font-size: 96px; font-weight: 700; margin-top: 18px; letter-spacing: .04em; }
    .name .leaf { font-size: 66px; vertical-align: 18px; margin-left: 12px; }
    .rule { width: 132px; height: 4px; border-radius: 4px; margin: 34px 0 30px;
            background: linear-gradient(90deg, transparent, #4fa83a, transparent); }
    .catch { font-size: 34px; font-weight: 700; line-height: 1.75; }
    .sub { font-size: 22px; color: var(--muted); margin-top: 26px; }
    .corner { position: absolute; font-size: 150px; opacity: .07; }
    """
    return figure("01-cover", 1600, 900, css, f"""
      <div class="corner" style="top:-24px;left:44px;transform:rotate(-14deg)">🍀</div>
      <div class="corner" style="bottom:-30px;right:56px;transform:rotate(12deg)">🍀</div>
      <img class="chamu" src="{_b64_png('src/static/img/mate-head.png')}">
      <div class="name">たびメイト<span class="leaf">🍀</span></div>
      <div class="rule"></div>
      <div class="catch">旅のしおり、AIが作ります。<br>
        帰ってきたら、写真がひとりでに「付箋」になる。</div>
      <div class="sub">絵本みたいにやさしい、旅の相棒アプリ</div>
    """)


# ----------------------------------------------------------------------
# 02 体験の流れ
# ----------------------------------------------------------------------
def fig_journey():
    steps = [
        ("💬", "そうだん", "「熱海に1泊で」と話すだけ。<br>足りないことだけ聞き返す"),
        ("📖", "しおり", "AIエージェントが手分けして<br>日程・お店・宿を組み立てる"),
        ("🗾", "たび", "水彩の地図をまわる順に。<br>持ち物リストとカウントダウン"),
        ("📸", "ふりかえり", "写真を入れるだけで<br>思い出が付箋になる"),
    ]
    cells = ""
    for i, (icon, title, body) in enumerate(steps):
        if i:
            cells += '<div class="arrow">→</div>'
        cells += f"""<div class="card step">
            <div class="ico">{icon}</div>
            <div class="st">{title}</div>
            <div class="sb">{body}</div></div>"""
    css = """
    .head { margin-bottom: 40px; }
    .row { display: flex; align-items: stretch; gap: 14px; }
    .step { flex: 1; padding: 32px 24px; text-align: center;
            display: flex; flex-direction: column; align-items: center; }
    .ico { font-size: 58px; line-height: 1; }
    .st { font-size: 30px; font-weight: 700; margin: 18px 0 12px; }
    .sb { font-size: 19px; color: var(--muted); line-height: 1.75; }
    .arrow { align-self: center; font-size: 40px; color: #b9cfa8; font-weight: 700; }
    .band { margin-top: 34px; padding: 24px 34px; display: flex; align-items: center;
            gap: 20px; border-radius: 20px; background: rgba(79,168,58,.09);
            border: 1.5px dashed rgba(79,168,58,.35); }
    .band .bi { font-size: 40px; }
    .band .bt { font-size: 22px; line-height: 1.6; }
    """
    return figure("02-journey", 1600, 650, css, f"""
      <div class="head">
        <div class="eyebrow">たびメイトの一日</div>
        <div class="title" style="margin-top:12px">「どこ行こう？」から「楽しかったね」まで</div>
      </div>
      <div class="row">{cells}</div>
      <div class="band">
        <div class="bi">🤝</div>
        <div class="bt"><span class="em">おすそわけ</span>— しおりも思い出も、公開リンクかメール指定で。
          ログイン不要の閲覧から、いっしょに編集まで。</div>
      </div>
    """)


# ----------------------------------------------------------------------
# 03 プランを組み立てるAIエージェントたち（LangGraph）
# ----------------------------------------------------------------------
def fig_agents():
    """src/chat/graph.py の構成そのまま。並列先行の2つと、balancer の差し戻しが要点。"""
    chain = [
        ("観光", "sightseeing", "動線を見て2〜3件"),
        ("宿 候補", "accommodation_candidates", "3〜5件を挙げる"),
        ("宿", "accommodation", "残予算の40%以内"),
        ("食 候補", "gourmet_candidates", "周辺から4〜6件"),
        ("食", "gourmet", "食事回数ぶんを選ぶ"),
        ("時間割", "timekeeper", "時系列に組み立てる"),
        ("お金", "cost_manager", "費目ごとに積む"),
    ]
    nodes = ""
    for i, (jp, en, note) in enumerate(chain):
        if i:
            nodes += '<div class="ar">›</div>'
        wide = " wide" if len(en) > 16 else ""
        nodes += f'<div class="nd{wide}"><div class="jp">{jp}</div>' \
                 f'<div class="en">{en}</div><div class="nt">{note}</div></div>'
    nodes += '<div class="ar">›</div>'
    nodes += ('<div class="nd bal"><div class="jp">まとめ役</div>'
              '<div class="en">balancer</div><div class="nt">全体を見て判定</div></div>')

    css = """
    .head { margin-bottom: 26px; }
    .pre { display: flex; gap: 18px; align-items: center; margin-bottom: 22px; }
    .plabel { font-size: 17px; color: var(--muted); line-height: 1.6; }
    .pbox { display: flex; gap: 14px; padding: 14px 16px; border-radius: 18px;
            background: rgba(79,168,58,.07); border: 1.5px dashed rgba(79,168,58,.4); }
    .wrap { position: relative; }
    .flow { display: flex; align-items: stretch; gap: 4px; }
    .nd { flex: 1; padding: 16px 8px 14px; text-align: center; background: var(--surface);
          border: 1.5px solid var(--border); border-radius: 18px;
          box-shadow: 0 6px 18px rgba(120,110,90,.08); }
    .bal { background: linear-gradient(135deg,#4a9d3a,#6fb152); border: none; color: #fff;
           box-shadow: 0 8px 20px rgba(79,168,58,.3); }
    .bal .en { color: rgba(255,255,255,.75); }
    .bal .nt { color: rgba(255,255,255,.9); }
    .jp { font-size: 23px; font-weight: 700; }
    .en { font-size: 11px; color: #a99f93; margin-top: 4px; white-space: nowrap;
          font-family: ui-monospace, monospace; letter-spacing: -.02em; }
    .nd.wide { flex: 1.32; }
    .nt { font-size: 15px; color: var(--muted); margin-top: 9px; line-height: 1.5; }
    .ar { align-self: center; color: #b9cfa8; font-size: 30px; font-weight: 700; }
    svg.loop { position: absolute; left: 0; top: 100%; width: 100%; height: 110px; }
    .loop text { font-family: 'Zen Maru Gothic','IPAPGothic',sans-serif;
                 font-size: 19px; font-weight: 700; fill: #3b8a2c; }
    .tail { display: flex; gap: 18px; margin-top: 132px; }
    .v { flex: 1; padding: 18px 24px; font-size: 20px; line-height: 1.6; }
    .note { flex: 1.5; font-size: 18px; color: var(--muted); line-height: 1.8;
            border-left: 4px solid #e7ddca; padding-left: 22px; align-self: center; }
    """
    return figure("03-agents", 1600, 720, css, f"""
      <div class="head">
        <div class="eyebrow">LangGraph</div>
        <div class="title" style="margin-top:10px">10人のエージェントが、手分けして組み立てる</div>
      </div>
      <div class="pre">
        <div class="plabel">まず並列で<br>先に走る</div>
        <div class="pbox">
          <div class="nd" style="width:270px"><div class="jp">交通費</div>
            <div class="en">transport</div><div class="nt">往復を概算して残予算を出す</div></div>
          <div class="nd" style="width:270px"><div class="jp">観光 候補</div>
            <div class="en">sightseeing_candidates</div><div class="nt">Web検索から5〜8件</div></div>
        </div>
        <div class="plabel">互いに独立なので、グラフの外で同時に。<br>
          差し戻しの戻り先にもならないので、外しても困らない</div>
      </div>

      <div class="wrap">
        <div class="flow">{nodes}</div>
        <svg class="loop" viewBox="0 0 1472 110" preserveAspectRatio="none">
          <path d="M1382 6 C1382 74, 1330 86, 1180 86 L960 86"
                fill="none" stroke="#e07f96" stroke-width="3" stroke-dasharray="9 7"/>
          <path d="M520 86 L200 86 C92 86, 92 74, 92 6"
                fill="none" stroke="#e07f96" stroke-width="3" stroke-dasharray="9 7"/>
          <path d="M92 24 L83 6 L101 6 Z" fill="#e07f96"/>
        </svg>
        <div style="position:absolute;left:0;top:100%;width:100%;height:110px;
                    display:flex;align-items:flex-end;justify-content:center">
          <div style="font-size:19px;font-weight:700;
                      color:#c9526f;transform:translateY(-14px)">
            気になったら、その担当へ差し戻し</div>
        </div>
      </div>

      <div class="tail">
        <div class="card v">✅ 納得したら <span class="em">できあがり</span></div>
        <div class="note">戻り先は観光・宿・時間割など<span class="em">原因のノードだけ</span>。
          全部やり直さないので速い。暴走しないよう recursion_limit で上限を切ってある。</div>
      </div>
    """)


# ----------------------------------------------------------------------
# 04 システム構成
# ----------------------------------------------------------------------
def fig_architecture():
    def box(icon, title, sub, extra=""):
        return f'<div class="card bx" style="{extra}"><div class="bi">{icon}</div>' \
               f'<div class="bt">{title}</div><div class="bs">{sub}</div></div>'
    css = """
    .head { margin-bottom: 10px; }
    .lane { margin-bottom: 10px; }
    .ln { font-size: 17px; color: var(--muted); letter-spacing: .12em; margin-bottom: 10px; }
    .row { display: flex; gap: 13px; }
    .bx { flex: 1; padding: 12px; text-align: center; }
    .bi { font-size: 30px; line-height: 1; }
    .bt { font-size: 20px; font-weight: 700; margin-top: 9px; }
    .bs { font-size: 15px; color: var(--muted); margin-top: 6px; line-height: 1.5; }
    .down { text-align: center; color: #b9cfa8; font-size: 22px; font-weight: 700;
            margin: 0 0 6px; letter-spacing: .3em; }
    .core { padding: 18px 20px; border-radius: 22px; border: 2px solid rgba(79,168,58,.45);
            background: rgba(79,168,58,.07); }
    .ct { font-size: 23px; font-weight: 700; margin-bottom: 5px; }
    .cs { font-size: 16px; color: var(--muted); margin-bottom: 12px; line-height: 1.5; }
    """
    return figure("04-architecture", 1600, 900, css, pad=46, body=f"""
      <div class="head">
        <div class="eyebrow">ARCHITECTURE</div>
        <div class="title" style="margin-top:12px">構成はひとつ。Web も iOS も同じサーバー</div>
      </div>

      <div class="lane"><div class="ln">つかう側</div><div class="row">
        {box("🌐", "ブラウザ / PWA", "Jinja2 · 素のJS · Leaflet<br>ホーム画面に置ける")}
        {box("📱", "iOSアプリ", "SwiftUI（iOS 17+）· Swift 6<br>Bearerトークンで認証")}
      </div></div>
      <div class="down">↓</div>

      <div class="core">
        <div class="ct">☁️ Cloud Run — Flask 3.1 / gunicorn</div>
        <div class="cs">ワーカー1 × スレッド20。生成はリクエストと別スレッドで走るので、
          画面を閉じても最後まで作りきる</div>
        <div class="row">
          {box("🧠", "LangGraph 1.2", "10エージェントの<br>プラン生成")}
          {box("🏷️", "写真の解釈", "付箋づくり·<br>ベストショット選び")}
          {box("🔐", "認証", "Google OAuth 2.0<br>署名つきトークン")}
          {box("🤝", "共有", "公開リンク·<br>メール指定")}
        </div>
      </div>
      <div class="down">↓</div>

      <div class="lane"><div class="ln">たよる先</div><div class="row">
        {box("✨", "Gemini", "3.6 Flash / 3.1 Flash-Lite")}
        {box("🔎", "Tavily", "Web検索")}
        {box("📍", "Google Places", "実在するお店だけ残す")}
        {box("🗺️", "Stadia · OSM · 地理院", "水彩タイルと座標解決")}
        {box("🗄️", "MySQL 8.0 / TiDB", "SQLAlchemy 2.0")}
        {box("🪣", "Cloud Storage", "写真 · 署名つきURL")}
      </div></div>
    """)


# ----------------------------------------------------------------------
# 05 写真が付箋になるまで
# ----------------------------------------------------------------------
def fig_sticker():
    css = """
    .head { margin-bottom: 36px; }
    .row { display: flex; align-items: center; gap: 12px; }
    .st { flex: 1; padding: 26px 20px; text-align: center; }
    .si { font-size: 46px; line-height: 1; }
    .sh { font-size: 24px; font-weight: 700; margin: 14px 0 10px; }
    .sb { font-size: 17px; color: var(--muted); line-height: 1.7; }
    .ar { color: #b9cfa8; font-size: 32px; font-weight: 700; }
    .out { display: flex; gap: 16px; margin-top: 34px; }
    .note { flex: 1; padding: 24px 22px; border-radius: 6px; background: var(--note);
            border: 1px solid rgba(0,0,0,.05);
            box-shadow: 0 6px 16px rgba(120,110,90,.14); }
    .note:nth-child(2) { background: #e7f3dd; transform: rotate(-1.2deg); }
    .note:nth-child(3) { background: #fde8ee; transform: rotate(.9deg); }
    .nh { font-size: 20px; font-weight: 700; margin-bottom: 8px; }
    .nb { font-size: 16px; color: #6b635b; line-height: 1.7; }
    """
    return figure("05-sticker", 1600, 645, css, """
      <div class="head">
        <div class="eyebrow">旅のあと</div>
        <div class="title" style="margin-top:12px">写真を入れるだけ。あとはちゃむがやっておく</div>
      </div>
      <div class="row">
        <div class="card st"><div class="si">📷</div><div class="sh">写真を入れる</div>
          <div class="sb">まとめて放り込むだけ。<br>HEIC もそのまま</div></div>
        <div class="ar">→</div>
        <div class="card st"><div class="si">🧭</div><div class="sh">EXIF を読む</div>
          <div class="sb">撮った時刻・場所・枚数から<br>その日の輪郭をつくる</div></div>
        <div class="ar">→</div>
        <div class="card st"><div class="si">✨</div><div class="sh">AIが読む</div>
          <div class="sb">縮めた写真と特徴量を<br>いっしょに渡して解釈させる</div></div>
        <div class="ar">→</div>
        <div class="card st"><div class="si">🍀</div><div class="sh">ことばになる</div>
          <div class="sb">説明ではなく、<br>そのときの気分を短く</div></div>
      </div>
      <div class="out">
        <div class="note"><div class="nh">🏷️ 思い出の付箋</div>
          <div class="nb">「海沿いの風、つよかった。」<br>写真そのものではなく、その日の感じを6〜14字で</div></div>
        <div class="note"><div class="nh">🏅 ちゃむが選ぶ一枚</div>
          <div class="nb">たくさんの中から飾りたい一枚を選んで、金の額に入れる</div></div>
        <div class="note"><div class="nh">🐾 足あとマップ</div>
          <div class="nb">写真のGPSから歩いた道のりを描く。プランと重ねれば予定と実際の比較に</div></div>
      </div>
    """)


# ----------------------------------------------------------------------
# 06 技術スタック
# ----------------------------------------------------------------------
def fig_stack():
    groups = [
        ("🧠", "AI", ["LangGraph 1.2", "LangChain", "Gemini 3.6 Flash", "Gemini 3.1 Flash-Lite",
                      "Tavily Search"]),
        ("⚙️", "バックエンド", ["Python 3.13", "Flask 3.1", "SQLAlchemy 2.0",
                            "MySQL 8.0 / TiDB", "gunicorn"]),
        ("🗺️", "地図・位置", ["Leaflet", "Stadia Maps（水彩）", "Google Places",
                          "OSM Nominatim", "国土地理院"]),
        ("☁️", "インフラ", ["Cloud Run", "Docker", "Cloud Storage", "Secret Manager",
                        "Google OAuth 2.0", "GitHub Actions"]),
        ("🎨", "フロント", ["Jinja2", "素のJavaScript", "PWA", "Zen Maru Gothic"]),
        ("📱", "iOS", ["SwiftUI（iOS 17+）", "Swift 6", "XcodeGen", "URLProtocol でテスト"]),
    ]
    cells = ""
    for icon, name, items in groups:
        li = "".join(f"<li>{x}</li>" for x in items)
        cells += f'<div class="card g"><div class="gh"><span class="gi">{icon}</span>{name}</div>' \
                 f'<ul>{li}</ul></div>'
    css = """
    .head { margin-bottom: 32px; }
    .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 18px; }
    .g { padding: 24px 26px; }
    .gh { font-size: 25px; font-weight: 700; display: flex; align-items: center; gap: 12px;
          padding-bottom: 14px; border-bottom: 1.5px solid var(--border); }
    .gi { font-size: 30px; }
    ul { list-style: none; padding: 16px 0 0; }
    li { font-size: 18px; color: #5d564f; line-height: 2.0; padding-left: 20px;
         position: relative; }
    li::before { content: '🍀'; position: absolute; left: 0; font-size: 12px; top: 6px; }
    """
    return figure("06-stack", 1600, 900, css, f"""
      <div class="head">
        <div class="eyebrow">TECH STACK</div>
        <div class="title" style="margin-top:12px">使っている技術</div>
      </div>
      <div class="grid">{cells}</div>
    """)


# ----------------------------------------------------------------------
# 07 数字
# ----------------------------------------------------------------------
def fig_numbers():
    """ここの数字は README と同じ数え方。作り直す前に必ず測り直すこと。"""
    nums = [
        ("10", "エージェント", "手分けしてプランを組む"),
        ("67", "ルート", "Web · 共有 · iOS用API"),
        ("139", "自動テスト", "ネットにつながずに回る"),
        ("11", "ブラウザ検査", "本物のChromiumで画面を触る"),
        ("2", "プラットフォーム", "Web / iOS · 同じサーバー"),
    ]
    cells = ""
    for n, label, sub in nums:
        cells += f'<div class="card n"><div class="v">{n}</div>' \
                 f'<div class="l">{label}</div><div class="s">{sub}</div></div>'
    css = """
    .head { margin-bottom: 36px; }
    .row { display: flex; gap: 18px; }
    .n { flex: 1; padding: 34px 18px 28px; text-align: center; }
    .v { font-size: 76px; font-weight: 700; line-height: 1; color: #3b8a2c; }
    .l { font-size: 23px; font-weight: 700; margin-top: 14px; }
    .s { font-size: 16px; color: var(--muted); margin-top: 8px; line-height: 1.6; }
    .foot { margin-top: 34px; font-size: 19px; color: var(--muted); line-height: 1.8;
            border-left: 4px solid #e7ddca; padding-left: 22px; }
    """
    return figure("07-numbers", 1600, 575, css, f"""
      <div class="head">
        <div class="eyebrow">NUMBERS</div>
        <div class="title" style="margin-top:12px">数字で見るたびメイト</div>
      </div>
      <div class="row">{cells}</div>
      <div class="foot">
        テストは <span class="em">APIキーなしで全部通る</span>（AIも外部APIも差し替えてある）ので、
        CI は push のたびに Ubuntu と macOS の2ジョブで回っている。<br>
        画面まわりは「構文は正しいのに何も起きない」壊れ方をするので、
        本物のブラウザで触って確かめる検査を別に持たせている。
      </div>
    """)


FIGURES = [fig_cover, fig_journey, fig_agents, fig_architecture,
           fig_sticker, fig_stack, fig_numbers]


SCALE = 2       # 2倍で撮る。スライドで大きく映しても粗くならない
SLACK = 240     # ウィンドウ枠のぶんの余裕。撮ったあと切り落とす


def render(fig, font_css: str, tmp: Path) -> Path:
    """1枚ぶんのHTMLをChromiumで撮る。

    --window-size で指定した高さがそのまま表示領域になるわけではなく、
    ウィンドウ枠のぶんだけ短くなる（この環境では87px）。図の下が切れて
    地の色が出てしまうので、多めに撮ってから正確な大きさへ切り落とす。
    """
    page = tmp / f"{fig['name']}.html"
    page.write_text(f"<!doctype html><meta charset='utf-8'><style>{font_css}</style>{fig['html']}")
    shot = tmp / f"{fig['name']}.raw.png"
    subprocess.run([
        CHROME, "--headless", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
        f"--force-device-scale-factor={SCALE}",
        f"--window-size={fig['w']},{fig['h'] + SLACK}",
        f"--screenshot={shot}", f"--user-data-dir={tmp / 'profile'}",
        "--virtual-time-budget=4000",
        page.as_uri(),
    ], check=True, capture_output=True, timeout=120)

    from PIL import Image
    img = Image.open(shot)
    want = (fig["w"] * SCALE, fig["h"] * SCALE)
    if img.size[0] < want[0] or img.size[1] < want[1]:
        raise SystemExit(f"{fig['name']}: 撮れた大きさが足りない {img.size} < {want}")
    out = OUT / f"{fig['name']}.png"
    img.crop((0, 0, *want)).save(out, optimize=True)
    return out


def main():
    if not Path(CHROME).exists():
        raise SystemExit(f"Chromium が見つからない: {CHROME}（CHROME_PATH で指定できる）")
    OUT.mkdir(parents=True, exist_ok=True)

    figs = [f() for f in FIGURES]
    chars = "".join(sorted({c for f in figs for c in re.sub(r"<[^>]+>", "", f["html"])}))
    font_css = _font_css(chars)

    tmp = Path(tempfile.mkdtemp(prefix="slides-"))
    try:
        for fig in figs:
            out = render(fig, font_css, tmp)
            print(f"  ✓ {out.name}  {fig['w']}×{fig['h']} → {out.stat().st_size // 1024}KB")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"▸ {len(figs)}枚を {OUT.relative_to(ROOT)} に書き出しました")


if __name__ == "__main__":
    main()
