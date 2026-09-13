<p align="center">
  <img src="https://raw.githubusercontent.com/sabatexima/tabimate/main/src/static/img/mate-head.png" alt="ちゃむ" width="130">
</p>

<h1 align="center">たびメイト&nbsp;🍀</h1>

<p align="center">
  <b>旅のしおり、AIが作ります。</b><br>
  帰ってきたら、写真がひとりでに「付箋」になる。
</p>

<p align="center"><i>絵本みたいにやさしい、旅の相棒アプリ。</i></p>

<p align="center">
  <a href="README.md">🇬🇧&nbsp;English</a>
  &nbsp;·&nbsp;
  <a href="https://github.com/sabatexima/tabimate/actions/workflows/ci.yml"><img src="https://github.com/sabatexima/tabimate/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white" alt="Python 3.13">
  <img src="https://img.shields.io/badge/Flask-3.1-000000?logo=flask&logoColor=white" alt="Flask 3.1">
  <img src="https://img.shields.io/badge/LangGraph-1.2-1C3C3C" alt="LangGraph 1.2">
  <img src="https://img.shields.io/badge/Gemini-3.6%20Flash-4285F4?logo=googlegemini&logoColor=white" alt="Gemini">
  <img src="https://img.shields.io/badge/Cloud%20Run-deployed-4285F4?logo=googlecloud&logoColor=white" alt="Cloud Run">
  <img src="https://img.shields.io/badge/Code-MIT-4fa83a" alt="Code: MIT">
  <img src="https://img.shields.io/badge/Artwork-CC%20BY--NC%204.0-f08ba0" alt="Artwork: CC BY-NC 4.0">
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/sabatexima/tabimate/main/docs/img/readme-screens.png" alt="旅の振り返り・保存プラン・プラン詳細" width="760">
</p>

---

## たびメイトって？

**旅行の「計画」と「思い出づくり」を、AIとマスコットの「ちゃむ」に預けられる Web アプリです。**

- 🗺️ 「金沢に2泊3日、2人で」と**話しかけるだけ**で、観光地・お店・宿・時間割・費用まで入った旅のしおりができます
- 📸 帰ってきたら**写真を放り込むだけ**で、AIがその旅の空気を短い付箋にして、アルバムに貼ってくれます
- 🤝 できたしおりも思い出も、リンクひとつで家族や友だちに見せられます

旅行アプリはたくさんあるけれど、たびメイトがこだわったのは **旅の「前」と「後」**。予約サイトが引き受けないところを、絵本のようなやさしい画面で引き受けます。スマホのホーム画面に置けるPWAと、SwiftUI の iOS アプリがあります。

> _「どこ行こう？」から「楽しかったね」まで。_<br>
> _旅のぜんぶに、ちゃむがそっと寄り添います。_

<p align="center">
  <img src="https://raw.githubusercontent.com/sabatexima/tabimate/main/docs/presentation/img/02-journey.png" alt="そうだん → しおり → たび → ふりかえり" width="760"><br>
  <sub>使う流れはこの4つ。相談して、しおりができて、旅に出て、帰ったら振り返る。</sub>
</p>

<table>
<tr>
<td width="33%" align="center"><br>🗺️<br><b>旅の「まえ」</b><br><sub>AIと話すだけで<br>しおりができる</sub><br><br></td>
<td width="33%" align="center"><br>📸<br><b>旅の「あと」</b><br><sub>写真がそのまま<br>思い出の付箋に</sub><br><br></td>
<td width="33%" align="center"><br>🤝<br><b>みんなで</b><br><sub>しおりも思い出も<br>そっとおすそわけ</sub><br><br></td>
</tr>
</table>

---

## できること

### 🗺️ 旅の「まえ」— 話すだけで、しおりができる

> _ちゃむ「どこ行く？ 何泊？ …うん、わかった。まかせて」_

<p align="center">
  <img src="https://raw.githubusercontent.com/sabatexima/tabimate/main/docs/img/readme-chat.png" alt="話しかける → しおりができる" width="760"><br>
  <sub>実際の画面。「金沢に2泊3日、2人で」と話しかけると予算だけ聞き返され、しおりが返ってくる。</sub>
</p>

| | |
|---|---|
| 💬 **会話でプランニング** | 行き先・日数・予算をふつうの会話から読み取り、足りないことだけ1つずつ聞きます。揃ったらAIエージェントたち（LangGraph）が手分けして組み立て。 |
| 🌤️ **天気を読む** | 旅の日の予報を見て、雨なら屋内多め、寒ければあたたかい場所。その曜日に閉まっていそうなお店は外します。 |
| 🍽️ **実在するお店だけ** | 候補は Google Places で突き合わせ。それらしいだけの架空のお店は落とします。 |
| 🗾 **水彩の地図** | 観光・食事・宿を色分けしたピンで、**まわる順**につなぎます。複数日の旅は**日ごとに**切り替えて見られます。ピンから経路案内へ。 |
| 🌏 **海外もOK** | 「パリに3泊」と言えば、フライト・現地時刻・円換算の費用つきでプランが届きます。地名には現地語の表記が添えられ、地図でも見つかります。 |
| 🎒 **持ち物リスト** | 行き先と天気から提案。チェックすると四つ葉が咲きます。 |
| 🍀 **出発カウントダウン** | 「あと12日」。棚を開けるたび、ちょっとうれしい。 |
| 📅 **カレンダー書き出し** | スケジュールを `.ics` で持ち出せます。しおりは印刷・PDF保存もできます。 |
| ✏️ **あとから調整** | 「2日目をゆっくりに」「宿を変えて」もチャットで。★をつけると次からの提案がそっと寄っていきます。 |

### 📸 旅の「あと」— 写真が、ひとりでに言葉になる

> _ちゃむ「おかえり。写真、見せて…いい旅だったね」_

| | |
|---|---|
| 🏷️ **写真から付箋** | 入れた写真をAIが読み、そのときの気分を短いことばにします。 |
| 📖 **旅のアルバム** | クラフト紙にポラロイドと淡い付箋。検索とお気に入りで見返せます。 |
| 🏅 **ちゃむが選ぶ一枚** | たくさんの中から「飾りたい一枚」を選んで、金の額に入れます。 |
| 💰 **旅のおこづかい帳** | 見つもりと実際を並べて記録。浮いたら「◯円うかせた🍀」。 |
| 🐾 **足あとマップ** | 写真のGPSから歩いた道のりを描きます。プランを重ねれば「予定と実際」の比較に。 |
| 📔 **年間ダイジェスト** | 「今年の旅ぜんぶ」を、その年の旅と付箋で1ページに。 |

### 🤝 おすそわけ

- 🔗 **公開リンク** — ログイン不要、閲覧のみ。
- ✉️ **メール指定** — その人だけに、閲覧または編集を許可。
- 📱 **PWA** — ホーム画面に置けば、ちゃむのアイコンからアプリとして開けます。

---

## しくみ

プランは1つのAIが一気に書くのではなく、**役割を分けた10のエージェント**が順に手を入れます。最後の「まとめ役」が納得しなければ、原因のノードだけに差し戻します。

<p align="center">
  <img src="https://raw.githubusercontent.com/sabatexima/tabimate/main/docs/presentation/img/03-agents.png" alt="10のエージェント" width="760"><br>
  <sub>交通費と観光候補は先に並列で。あとは観光 → 宿 → 食 → 時間割 → お金 の順に手を入れ、まとめ役が判定する。</sub>
</p>

サーバーは Cloud Run 上の Flask ひとつ。ブラウザも iOS アプリも同じサーバー・同じアカウント・同じしおりを見にいきます。

<p align="center">
  <img src="https://raw.githubusercontent.com/sabatexima/tabimate/main/docs/presentation/img/04-architecture.png" alt="構成" width="760"><br>
  <sub>つかう側（ブラウザ・iOS）→ Cloud Run 上の Flask → たよる先（Gemini・検索・地図・DB・ストレージ）。</sub>
</p>

---

## 📱 iOSアプリ

SwiftUI のネイティブアプリが [`ios/`](ios/) にあります。同じサーバー・同じアカウント・同じしおり。

下に載せた `/auth/app/*` と `/api/*` を叩き、セッションCookieの代わりに Bearer トークンで認証します（`src/api_auth.py`）。導入とビルドの手順は [`ios/README.md`](ios/README.md) に、CIは push のたびにビルドとテストを回します。

---

## 使っている技術

| | |
|---|---|
| 🧠 **AI** | LangGraph 1.2 · LangChain · Gemini 3.6 Flash / 3.1 Flash-Lite · Tavily Search |
| ⚙️ **バックエンド** | Flask 3.1 · SQLAlchemy 2.0 · MySQL 8.0 / TiDB · gunicorn |
| 🗺️ **地図・位置** | Leaflet · Stadia Maps（水彩）· Google Places · OSM Nominatim · 国土地理院（日本のみ） |
| ☁️ **インフラ** | Cloud Run · Docker · Cloud Storage · Secret Manager · Google OAuth 2.0 · GitHub Actions |
| 🎨 **フロント** | Jinja2 · 素のJS · PWA · Zen Maru Gothic · OpenMoji |
| 📱 **iOS** | SwiftUI（iOS 17+）· Swift 6 · XcodeGen |

---

## 動かす

```bash
git clone https://github.com/sabatexima/tabimate && cd tabimate

cp src/.env.example src/.env      # APIキー・OAuth・DB を書き込む

cd src
python3 -m venv .venv && source .venv/bin/activate
pip install -r ../requirements.txt
python3 app.py
```

**http://localhost:5007** を開いてください。テーブルは初回アクセス時に自動で作られます（`CREATE TABLE IF NOT EXISTS`）。

```bash
./deploy.sh    # Cloud Run へ一発（Secret・GCSバケット・IAM まで込み）
```

コンテナも CI も Python 3.13 です。手元では 3.11 でも動くのを確認しています
（3.10 より新しいものを要求している依存はありません）。

`deploy.sh` は `gcloud run deploy --source .` なので、Cloud Build が
リポジトリ直下の `Dockerfile` を拾います。**名前はこの綴りでないといけません。**
一時期 `dockerfile`（小文字）になっていましたが、それだと Cloud Build は
見つけられず、黙って Buildpacks でのビルドに落ちます。イメージの作り方を
変えたら、ビルドログに `FROM python:3.13-slim` が出ているか確認してください。

### 依存を変えるとき

`requirements.txt` は生成物なので直接編集しません。`requirements.in` に足すか
上げてから、コンテナと同じ Python のまっさらな環境で解決し直します。

```bash
python3.13 -m venv /tmp/resolve && /tmp/resolve/bin/pip install -r requirements.in
/tmp/resolve/bin/pip freeze | sort -f > /tmp/pins && cat /tmp/pins   # → requirements.txt
```

そのあと `THIRD_PARTY_NOTICES.md` の依存一覧も作り直してください。
生成用のスクリプトはそのファイルの中に載せてあります。

---

<details>
<summary><b>📖 開発者向け — 詳しい話</b></summary>

<br>

### 設計

3層に分けています。**上の層は下の層を呼び、下の層は上の層を知りません。**

```
  views/        入口。HTTP のことだけ（認可・入力の整形・レスポンス）。SQL は書かない
    │
    ├── chat/       AI（LangGraph のエージェント群・プロンプト・モデル呼び出し）
    ├── services/   ロジック（写真・EXIF・保存先・天気・座標・持ち物・付箋づくり）
    │
  db*.py        永続化（SQLAlchemy Core・素の SQL）。Flask を知らない
```

| 決めごと | 中身 |
|---|---|
| **入口は Blueprint で機能ごと** | `planner`（チャットとプラン）· `auth` · `reflection`（旅の振り返り）· `sharing`。URL の接頭辞と権限の境界が一致する |
| **永続化はテーブルの持ち主ごと** | `db.py`（プラン・チャット）· `db_reflection.py`（旅・写真・付箋）· `db_sharing.py`（共有）。エンジンは `db.get_engine()` の1つを使い回す |
| **外部サービスは差し替えられる** | 保存先は `GCS_BUCKET` の有無で GCS / ローカル（`services/storage.py`）。座標は Google Places → Nominatim → 地理院の順に落ちる（`services/geocoding.py`。探す国は行き先から決まり、地理院は日本のときだけ）。AI・検索・DB はテストで丸ごと差し替える |
| **入口は2つ、中は1つ** | ブラウザはセッション Cookie、アプリは `Authorization: Bearer …`。`api_auth.py` がその要求の間だけ同じセッションに読み替えるので、`login_required` は特別扱いを持たない |
| **横断するものは `src/` 直下** | `logger.py`（全モジュール共通のロガー）· `api_auth.py`（トークン） |
| **フロントはビルド無し** | ページごとに CSS と JS を1つずつ。色・角丸・影のトークンと共通部品（見出し・戻るリンク・共有バナー）は `layout.css`。複数ページで使う部品は `trip-detail.css` / `plan-card.css` に1か所だけ |
| **テストは外に出ない** | AI・DB・ストレージ・天気を差し替え、APIキー無しで回る。画面まわりは本物の Chromium で触って確かめる |
| **iOS は Feature 単位** | `Features/`（画面ごとに View と ViewModel）· `Networking/`（APIClient · Service · Models）· `Design/`（Theme · Components）。UIテストは `URLProtocol` で通信を差し替える |

次に手を入れるなら、ここが候補です:

- `views/planner.py`（約970行）はチャット・プラン・プラン用API が同居している。`chat` / `plans` / `plan_api` に分けると見通しがよくなる
- `chat/formatter.py` はプランを HTML にする**表示の仕事**が AI の層に置かれている。`chat/` が状態を返し、`views/` 側で整形する形が筋がよい
- `db.py` / `db_reflection.py` / `db_sharing.py` は `db/` パッケージにまとめられる

### 置き場所

```
tabimate/
├── LICENSE                      # コードは MIT
├── LICENSE-ARTWORK              # ちゃむと画像は CC BY-NC 4.0（非営利）
├── THIRD_PARTY_NOTICES.md       # 依存のライセンスと地図の帰属表示
├── requirements.in              # 直接依存（直すのはこちら）
├── requirements.txt             # 解決して固定した結果（生成物）
├── deploy.sh                    # Cloud Run へのデプロイ（Secret / GCS / IAM）
├── Dockerfile                   # python:3.13-slim · gunicorn、ワーカー1 × スレッド20
├── .github/workflows/ci.yml     # 2ジョブ: ubuntu（サーバー＋ロジック）/ macOS（iOS）
├── docs/
│   ├── img/                     # README 用の画面
│   └── presentation/            # 発表資料の図版と、AIへの指示書（PROMPT.md）
├── scripts/
│   ├── check_home_js.sh         # チャット画面を本物のブラウザで動かす
│   ├── check_ios_logic.sh       # iOSのロジックを Linux の Swift で型検査
│   ├── backfill_thumbnails.py
│   └── setup_alerts.sh
├── tests/                       # 「テストとCI」を参照
├── ios/                         # SwiftUIアプリ（XcodeGen。ios/README.md 参照）
└── src/
    ├── app.py                   # Flaskアプリ · Blueprint 登録 · セキュリティヘッダ · テンプレートフィルタ
    ├── api_auth.py              # ネイティブアプリ用の Bearer トークン
    ├── logger.py                # 全モジュール共通のロガー
    ├── db.py                    # travel_plans / chat_messages
    ├── db_reflection.py         # trips / photos / stickers
    ├── db_sharing.py            # 公開リンク / メール共有
    ├── views/                   # planner · auth · reflection · sharing（Blueprint）
    ├── chat/                    # プラン生成: agents · graph · chat · llm · models · formatter
    ├── services/                # exif · features · images · storage · packing
    │                            #   · trip_interpreter（付箋） · weather · geocoding
    ├── templates/               # Jinja2（layout.html を継承。部品は _share_modal.html）
    └── static/
        ├── css/                 # layout.css（トークン・共通部品）＋ ページごと
        │                        #   共有部品: trip-detail.css · plan-card.css · plan-map.css · share-modal.css
        ├── js/                  # ページごと ＋ layout.js · openmoji.js · plan-map.js · footprint-map.js
        └── img/                 # ちゃむ · PWA アイコン
```

### 全体の形

```
          ┌─────────── Flask app (app.py) ────────────┐
 ブラウザ  │  ProxyFix · セキュリティヘッダ              │
 ─────────┤  planner("/")        auth("/auth")         │
 iOSアプリ │  reflection("/reflection")  sharing("/share")
 ─────────┤                                            │
  Bearer  └────┬───────────────┬──────────────┬────────┘
               │               │              │
        chat/ (LangGraph)   db*.py        services/
        エージェント群      (SQLAlchemy)   exif · storage ·
               │               │          interpreter · weather
               ▼               ▼              ▼
      Gemini + Tavily     MySQL / TiDB       GCS · Open-Meteo · Places
```

### プラン生成のエージェント

`chat/graph.py` が `StateGraph` を組み、`chat/agents.py` の関数をノードとしてつなぎます。状態は `TravelPlanState`（TypedDict）で流れます。

```
（生成の前に）行き先の国と座標を1回だけ引く → 海外なら各エージェントに指示を足す
（並列で先に）transport · sightseeing_candidates · 天気予報
START
  → sightseeing               観光2〜3件
  → accommodation_candidates → accommodation   残予算の約40%（日帰りなら飛ばす）
  → gourmet_candidates → gourmet               残予算の約25%
  → timekeeper                 時系列のスケジュール
  → cost_manager               費用の内訳
  → balancer                   全体の見直し
        ├─ approved / budget_infeasible → END
        └─ fix_* → 該当ノードへ戻る   （上限: MAX_BALANCER_RETRIES = 5）
             1回目は選び直し（安い）／繰り返し・3回目からは候補集めまで戻る（高い）
```

- **宿なし判定** — `parse_duration()` が (泊数, 日数) を返し、0泊なら宿のノードを飛ばします（夜行での「0泊2日」に対応）。
- **実在チェック** — `GOOGLE_MAPS_API_KEY` があれば候補を Google Places で突き合わせ、架空の名前を落とします。
- **海外の行き先** — 生成の前に行き先の国を決め、海外なら全エージェントに指示を足します。金額は円に換算してレートを明記、往復は航空便、行程は現地時刻と時差・入出国の待ち時間つき、費用に保険と通信費、持ち物にパスポート。スポット名は「日本語名（現地語名）」で書かせ、地図はその現地語名で探します。
- **好みの学習** — 過去の★と一言から `user_preferences` を作り、各エージェントにそっと渡します。
- **地図は日ごとに** — スケジュールの「N日目」の見出しで各ピンがどの日に出るかを決め、複数日なら日ごとに絞れます（宿は前後の2日に属します）。照合できたピンが半分に満たないときは、押すとピンが消えて壊れて見えるので切り替えを出しません。
- **部分的な編集** — 編集の依頼では、関係するノードだけ作り直します。
- **差し戻しの段階** — 1回目は同じ候補プールから選び直します（安い）。同じ指摘が2回続いたとき、または差し戻しが3回目に入ったときは、候補集めまで戻って顔ぶれを入れ替えます（検索とLLMを使うので高い）。後者が要るのは、観光→グルメ→観光と交互に指摘が来ると前者が一度も成立せず、上限まで同じ候補から選び直し続けるためです。候補エージェントには審査の指摘と前回弾かれた顔ぶれを渡します。渡さないと temperature=0 なので同じ候補が返るだけです（検索語は変えないので、入れ替えの材料は同じ検索結果＋除外の指示になります）。
- **再試行** — `invoke_with_retry()` が 429 / 503 / 通信エラーを最大5回、間隔を空けて再試行します。

### 生成は接続より長生きする

プラン生成は別スレッドで走り、**結果の保存もそのスレッドが行います**。ブラウザが繋がったままである必要はありません。

生成には数分かかるので、ここが大事です。もし保存を SSE の送信側でやっていると、リロードで接続が切れた瞬間に generator が止まり、生成がまるごと捨てられてしまいます。

`/chat` はページを出すときに「まだ返事待ちの生成があるか」を載せるので、リロード直後から「考えています」が戻ります。その判断はプロセス内のメモリではなく `chat_messages` の行から決めるため、Cloud Run が複数インスタンスでも食い違いません。

| その `request_id` の行 | 意味 |
|---|---|
| `ai` の行がある | 終わった |
| `user` の行だけ・最近 | まだ作っている |
| `user` の行だけ・20分以上前 | あきらめる（ワーカーが落ちたとみられる） |
| 行が無い | 失敗か中断。後片づけ済み |

チャットに出すプランカードは画面側で `marked.parse()` を通ります。Markdown は空行で HTML の解釈を打ち切るので、`chat/formatter.py` は**空行を含まない HTML** を返します（含めると `<details>` が文字のまま出ます）。

### データベース

| テーブル | 役割 |
|---|---|
| `travel_plans` | 保存プラン（条件と結果をJSONで）。ご希望（交通手段・運転の可否・時間）、座標キャッシュ、カスタムピン、持ち物、実費、★も持ちます |
| `chat_messages` | チャット履歴。プランの行には `plan_json`（編集時に使う「前のプラン」）も |
| `trips` | 旅（名前・日付）、表紙写真、ベストショット、紐づけたプラン |
| `photos` / `stickers` | 写真（パス・撮影時刻・GPS）/ 付箋（表示する言葉と内部の根拠） |
| `share_links` / `share_grants` | 公開リンク / メールでの共有 |

所有権は常に `user_id`（Google の `sub`）で確認します。旅を消すと、関連する行と実体の写真まで連鎖して消えます。

### 環境変数

`src/.env`（ローカル）か Cloud Run の環境変数 / Secret Manager に設定します。`src/.env` は Git に含めません。

| 変数 | 必須 | 用途 |
|---|---|---|
| `SECRET_KEY` | 本番 | Flask のセッション署名鍵 |
| `GOOGLE_API_KEY` | ✓ | Gemini のAPIキー |
| `TAVILY_API_KEY` | ✓ | Tavily のWeb検索 |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | ✓ | Google OAuth（Web版のログイン） |
| `DB_USER` / `DB_PASS` / `DB_NAME` / `DB_HOST` / `DB_PORT` | ✓ | データベース接続 |
| `GOOGLE_IOS_CLIENT_ID` | アプリ | iOSアプリのIDトークンを検証する宛先。無ければ `GOOGLE_CLIENT_ID` を使い、**どちらも無いときはサインインを断ります**（宛先が未設定だと、ライブラリが `aud` の検証をまるごと省いてしまうため） |
| `APP_TOKEN_MAX_AGE_SEC` | | アプリ用トークンの有効期間（既定30日） |
| `STADIA_API_KEY` | | 水彩タイル（無ければ通常のOSMタイル）。⚠️ 仕組み上ブラウザに出るので、**Stadia 側で必ずドメイン制限**を |
| `GOOGLE_MAPS_API_KEY` | | Google Places を使った座標解決。未設定なら無料スタック（Nominatim + 地理院）のみ |
| `DB_SSL` / `DB_SSL_CA` | 条件 | TLS接続（TiDB Cloud は `DB_SSL=true` が必須） |
| `CLOUD_SQL_INSTANCE` | 条件 | 設定すると Cloud SQL Connector 経由で接続 |
| `GCS_BUCKET` | 条件 | 設定すると GCS、無ければローカルのファイルシステム |
| `LOCAL_UPLOAD_DIR` / `SIGNED_URL_TTL_SECONDS` / `GCS_SIGNER_SA` | | 保存先 · 署名URLの有効期間 · 署名用SA |
| `REDIS_URL` | | 生成中の状態をインスタンス間で共有する |
| `GEMINI_MODEL_STRONG` / `GEMINI_MODEL_LITE` | | 使うモデルの上書き（既定 `gemini-3.6-flash` / `gemini-3.1-flash-lite`）。新モデルを1行で戻せます |
| `MAX_CONTENT_LENGTH_MB` | | 1リクエストあたりのアップロード上限（既定100） |
| `SEARCH_SNIPPET_CHARS` / `SEARCH_QUERY_CHARS` | | Web検索の結果をどこまで残すかと、1クエリあたりの上限（600 / 2400）。モデルに渡す量を抑える |
| `INTERPRETER_MODEL` | | 付箋づくりとベストショット選びに使うモデル（既定 `gemini-3.1-flash-lite`） |
| `STICKER_MAX_IMAGES` / `INTERPRETER_IMAGE_MAX_EDGE` | | 付箋づくりに送る写真の枚数（6）と、送る前に縮める長辺（512px）。付箋のコストはここで決まる |
| `INTERPRETER_MAX_IMAGES` | | 枚数を指定しない呼び出しのための既定値（4）。いまはどちらの呼び出しも自前で指定しているので（付箋は `STICKER_MAX_IMAGES`、ベストショットは間引いた写真を全部＝最大12枚）、ここだけ変えても効きません |
| `INTERPRETER_PRICE_INPUT_PER_M` / `INTERPRETER_PRICE_OUTPUT_PER_M` | | 概算コストをログに出すためだけの百万トークン単価（0.25 / 1.50） |

`K_SERVICE` は Cloud Run が自動で設定するもので、本番かどうかの判定に使って
います（Cookieのsecure化、`SECRET_KEY` 未設定なら起動しない、など）。
自分で設定しないでください。

### HTTP エンドポイント

**画面** — `/`（ようこそ）· `/chat` · `/saved_plans` · `/plan/<id>` · `/plan/<id>/print` · `/reflection/` · `/reflection/digest` · `/reflection/trips/<id>` · `/shared` · `/s/<token>` · `/terms` · `/privacy`

**チャット** — `/send_message`（SSE）· `/get_messages` · `/reset_chat` · `/abort_request` · `/generation_status`

**プラン** — `/save_plan` · `/get_my_plans` · `/get_shared_plans` · `/edit_saved_plan/<id>` · `/apply_saved_plan/<id>` · `/delete_plan/<id>` · `/rate_plan/<id>` · `/save_actual_total/<id>` · `/save_plan_pins/<id>` · `/export_plan_ics/<id>` · `/api/packing_list/<id>` · `/api/plan_geo/<id>` · `/api/plan_weather/<id>` · `/api/geocode`

**おもいで** — `/reflection/trips`（POST）· `/reflection/trips/<id>`（GET / PATCH / DELETE）· `…/photos` · `…/stickers` · `…/stickers/generate` · `…/best_shots` · `…/favorite` · `…/linked-plan` · `/reflection/photo/<path>`

**共有** — `/share/<type>/<id>`（状態）· `…/link` · `…/grant` · `/share/link/<id>` · `/share/grant/<id>` · `/shared/<type>/<id>` · `/shared/trip/<id>/…`（編集権限がある人の写真・付箋操作）· `/shared/plan/<id>/ics`

**ネイティブアプリ用** — `/auth/app/signin` · `/auth/app/me` · `/api/ideas` · `/api/chat_messages` · `/reflection/api/trips` · `/reflection/api/trips/<id>` · `/reflection/api/digest`

**認証** — `/auth/login` · `/auth/callback` · `/auth/logout`

`/`・`/terms`・`/privacy`・`/api/ideas`・`/auth/*` と公開ビュー `/s/<token>` 以外は `@login_required` の内側です。未認証のとき、APIには `401 JSON` を返し、ブラウザはログイン画面へ送ります。全部で67ルートあります。

### テストとCI

```bash
pytest tests/ -k "not smoke"    # 238件のオフラインテスト（APIキーもDBも不要）
scripts/check_home_js.sh        # チャット画面を本物のブラウザで動かす
scripts/check_ios_logic.sh      # iOSのロジックを Linux の Swift で型検査
python tests/test_smoke.py      # プラン生成の通し確認（APIキーが要ります）
```

| 検査 | 見ているもの |
|---|---|
| `test_units.py`（38） | サムネイルのキー、URL生成、パストラバーサル、地名の表記ゆれ、行き先の国の判定、アプリ用トークンの発行と検証 |
| `test_ios_routes.py`（44） | iOSアプリが叩くURLが、そのメソッドでサーバーに実在すること |
| `test_regression.py`（56） | 一度戻ってきたことのある不具合。テンプレートの `url_for` が実在の endpoint を指すこと、プランカードに空行が無いこと、公開リンクの旅で写真が枠に入ること、「運転しない」が保存と修正の往復で消えないことなど |
| `test_generation_status.py`（18） | リロード後の復元。pending / done / gone の判断と、ページが載せる情報 |
| `test_app_api.py`（16） | ネイティブアプリ向けAPIの認可とJSONの形 |
| `test_send_message_survives_disconnect.py`（7） | ブラウザが去っても生成が捨てられないこと |
| `test_pipeline.py`（53） | AIの返事だけ偽物にして、プラン生成を丸ごと通す。旅の形（日帰り〜5泊・国内/海外・運転の可否）を総当たりして、プロンプトに埋め残しや空欄が無いか、条件どおりの指示が出入りするか、差し戻しで指摘が候補集めに届くかを見る |
| `test_static_js.py`（6） | JSとテンプレートが噛み合っていること（名前・要素のid）と、地図が各ピンをどの日に割り当てるか |
| `tests/js/home_chat.html`（11場面） | チャット画面をヘッドレスChromiumで実際に動かす |

ブラウザでの検査があるのは、この部分が**構文検査では見つからない壊れ方**をするからです。実際、テンプレート内のスクリプトが `home.js` と同じ名前を宣言していたためスクリプト全体が動かず、季節のチップを押しても無反応になっていました。

**CI** は push と PR のたびに2ジョブを回します。Ubuntu（サーバーのテスト、JS構文、ブラウザ検査、Swiftの型検査、テンプレート検査）と macOS（iOSアプリのビルド、単体テストとUIテスト、警告の一覧）。

### セキュリティ

- 秘密情報は直書きせず、すべて環境変数 / Secret Manager から。`src/.env` はコミットしません。
- 本番で `SECRET_KEY` が無ければ起動しません。CookieはHttpOnly / SameSite=Lax、本番ではSecure。
- OAuth は `email_verified` を必須に。アプリのIDトークンは宛先が未設定なら受け付けません（未設定だとライブラリが `aud` の検証を省いてしまうため）。
- すべてのリソースを `user_id` で所有権チェック。プランのHTMLはユーザー文字列をエスケープし、ローカル写真の配信はパストラバーサルを防ぎます。
- レート制限（チャット 20回/60秒、座標解決 40回/60秒）とアップロード制限（50件まで、拡張子の許可制、サイズ上限）。
- すべての応答に `X-Content-Type-Options` / `X-Frame-Options` / `Referrer-Policy`。`ProxyFix` が Cloud Run の転送ヘッダを信頼します。
- **外部キーの制限**（提供元の管理画面で設定します）:
  - `STADIA_API_KEY` はタイル取得のためブラウザに出ます。Stadia の管理画面で**ドメイン制限**を。
  - `GOOGLE_MAPS_API_KEY` はサーバー専用（`X-Goog-Api-Key` ヘッダで送るのでURLやログに残りません）。GCPでは**アプリケーション制限を「なし」かIP**にし（リファラ制限だとサーバーからの呼び出しが弾かれます）、**Places API (New) に限定**します。
  - `GOOGLE_API_KEY`（Gemini）と `TAVILY_API_KEY` はフロントに渡しません。

### 困ったとき

| 症状 | だいたいの原因 |
|---|---|
| 設定が無くて起動しない | `src/.env` を作って中身を書く |
| MySQLに繋がらない | `DB_HOST` を確認。Cloud SQL は `CLOUD_SQL_INSTANCE`、TiDB は `DB_SSL=true` が要ります |
| 生成が504で切れる | `deploy.sh` は `--timeout=3600` を設定済み。手でデプロイするときも同じ指定を |
| 写真が遅い | 署名URLは写真ごとに IAM signBlob を呼びます。`storage.get_urls()` がキャッシュ＋並列化し、一覧はサムネイルを使用。古い写真は `scripts/backfill_thumbnails.py` で補完を |
| 地図にピンが出ない | `GOOGLE_MAPS_API_KEY` を使うなら **Places API (New)** の有効化が必要。起動ログの `外部連携` の行で有効・無効を確認できます |
| iOSアプリがサインインできない | `GOOGLE_IOS_CLIENT_ID` がサーバーに届いていません。`src/.env` と `deploy.sh` に追加を |

</details>

---

## ライセンス

**コードは MIT** → [LICENSE](LICENSE)。利用・改変・再配布・商用利用、すべて自由です。
条件は著作権表示を残すことだけ。

**ちゃむと画像は CC BY-NC 4.0**（表示・非営利）→ [LICENSE-ARTWORK](LICENSE-ARTWORK)。
非営利ならクレジット付きで自由に使えます。営利で使う場合は別途ご相談を。
営利目的で運用するなら、画像を自分のものに差し替えてください（コードは画像に依存していません）。

土台にしているライブラリ・地図データ・書体は、それぞれのライセンスと帰属表示に
従います。一覧は [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) に。

---

<p align="center">
  <img src="https://raw.githubusercontent.com/sabatexima/tabimate/main/src/static/img/mate.png" alt="ちゃむ" width="90"><br>
  <sub><i>また旅に出たくなったら、ちゃむを呼んでくださいね。🍀</i></sub>
</p>
