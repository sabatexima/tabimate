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
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/sabatexima/tabimate/main/docs/img/screen-journal.png" alt="旅の振り返り" width="240">
  <img src="https://raw.githubusercontent.com/sabatexima/tabimate/main/docs/img/screen-bookshelf.png" alt="保存プラン" width="240">
  <img src="https://raw.githubusercontent.com/sabatexima/tabimate/main/docs/img/screen-plan-detail.png" alt="プラン詳細" width="240">
</p>

---

## たびメイトって？

> _「どこ行こう？」から「楽しかったね」まで。_<br>
> _旅のぜんぶに、ちゃむがそっと寄り添います。_

旅行アプリはたくさんあるけれど、たびメイトがこだわったのは **旅の「前」と「後」**。

計画はAIとおしゃべりするだけ。帰ってきたら写真を放り込むだけ。あとはマスコットの **ちゃむ** が、しおりを綴じて、思い出を付箋にして、こっそり額に飾ってくれます。

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

| | |
|---|---|
| 💬 **会話でプランニング** | 行き先・日数・予算をふつうの会話から読み取り、足りないことだけ1つずつ聞きます。揃ったらAIエージェントたち（LangGraph）が手分けして組み立て。 |
| 🌤️ **天気を読む** | 旅の日の予報を見て、雨なら屋内多め、寒ければあたたかい場所。その曜日に閉まっていそうなお店は外します。 |
| 🍽️ **実在するお店だけ** | 候補は Google Places で突き合わせ。それらしいだけの架空のお店は落とします。 |
| 🗾 **水彩の地図** | 観光・食事・宿を色分けしたピンで、**まわる順**につなぎます。ピンから経路案内へ。 |
| 🎒 **持ち物リスト** | 行き先と天気から提案。チェックすると四つ葉が咲きます。 |
| 🍀 **出発カウントダウン** | 「あと12日」。棚を開けるたび、ちょっとうれしい。 |
| 📅 **カレンダー書き出し** | スケジュールを `.ics` で持ち出せます。 |
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

## 📱 iOSアプリ

SwiftUI のネイティブアプリが [`ios/`](ios/) にあります。同じサーバー・同じアカウント・同じしおり。

下に載せた `/auth/app/*` と `/api/*` を叩き、セッションCookieの代わりに Bearer トークンで認証します（`src/api_auth.py`）。導入とビルドの手順は [`ios/README.md`](ios/README.md) に、CIは push のたびにビルドとテストを回します。

---

## 使っている技術

| | |
|---|---|
| 🧠 **AI** | LangGraph 1.2 · LangChain · Gemini 3.6 Flash / 3.1 Flash-Lite · Tavily Search |
| ⚙️ **バックエンド** | Flask 3.1 · SQLAlchemy 2.0 · MySQL 8.0 / TiDB · gunicorn |
| 🗺️ **地図・位置** | Leaflet · Stadia Maps（水彩）· Google Places · OSM Nominatim · 国土地理院 |
| ☁️ **インフラ** | Cloud Run · Docker · Cloud Storage · Secret Manager · Google OAuth 2.0 · GitHub Actions |
| 🎨 **フロント** | Jinja2 · 素のJS · PWA · Zen Maru Gothic |
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

---

<details>
<summary><b>📖 開発者向け — 詳しい話</b></summary>

<br>

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
| `STICKER_MAX_IMAGES` / `INTERPRETER_IMAGE_MAX_EDGE` | | 付箋生成に使う画像の枚数・リサイズ |

### 置き場所

```
tabimate/
├── deploy.sh                    # Cloud Run へのデプロイ（Secret / GCS / IAM）
├── dockerfile                   # gunicorn、ワーカー1 × スレッド20
├── .github/workflows/ci.yml     # 2ジョブ: ubuntu（サーバー＋ロジック）/ macOS（iOS）
├── scripts/
│   ├── check_home_js.sh         # チャット画面を本物のブラウザで動かす
│   ├── check_ios_logic.sh       # iOSのロジックを Linux の Swift で型検査
│   ├── backfill_thumbnails.py
│   └── setup_alerts.sh
├── tests/                       # 「テストとCI」を参照
├── ios/                         # SwiftUIアプリ（XcodeGen。ios/README.md 参照）
└── src/
    ├── app.py                   # Flaskアプリ · Blueprint · セキュリティヘッダ
    ├── api_auth.py              # ネイティブアプリ用の Bearer トークン
    ├── db.py                    # travel_plans / chat_messages
    ├── db_reflection.py         # trips / photos / stickers
    ├── db_sharing.py            # 公開リンク / メール共有
    ├── geocoding.py             # 地名 → 緯度経度（複数プロバイダ・キャッシュ付き）
    ├── weather.py               # 旅の日の予報（Open-Meteo）
    ├── chat/                    # プラン生成（LangGraph のエージェント群）
    ├── services/                # exif · features · storage · interpreter · packing
    ├── views/                   # planner · auth · reflection · sharing
    ├── templates/               # Jinja2
    └── static/                  # css / js / img
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
               │               │          interpreter
               ▼               ▼              ▼
      Gemini + Tavily     MySQL / TiDB       GCS
```

- **エンジンは1つ** — `db.py` の `get_engine()`（QueuePool）を `db_reflection` / `db_sharing` が使い回します。テーブルは遅延作成。
- **保存先は差し替え式** — `services/storage.py` が `GCS_BUCKET` の有無で GCS とローカルを切り替え。署名URLはキャッシュ＋並列生成。
- **入口は2つ、中は1つ** — ブラウザはセッションCookie、アプリは `Authorization: Bearer …`。`api_auth.authenticate_app_token` がその要求の間だけ同じセッションに読み替えるので、`login_required` は特別扱いを持ちません。

### プラン生成のエージェント

`chat/graph.py` が `StateGraph` を組み、`chat/agents.py` の関数をノードとしてつなぎます。状態は `TravelPlanState`（TypedDict）で流れます。

```
START
  → transport                  往復の交通費 · 残予算
  → sightseeing_candidates → sightseeing       観光2〜3件
  → accommodation_candidates → accommodation   残予算の約40%（日帰りなら飛ばす）
  → gourmet_candidates → gourmet               残予算の約25%
  → timekeeper                 時系列のスケジュール
  → cost_manager               費用の内訳
  → balancer                   全体の見直し
        ├─ approved / budget_infeasible → END
        └─ fix_* → 該当ノードへ戻る   （上限: MAX_BALANCER_RETRIES = 5）
```

- **宿なし判定** — `parse_duration()` が (泊数, 日数) を返し、0泊なら宿のノードを飛ばします（夜行での「0泊2日」に対応）。
- **実在チェック** — `GOOGLE_MAPS_API_KEY` があれば候補を Google Places で突き合わせ、架空の名前を落とします。
- **好みの学習** — 過去の★と一言から `user_preferences` を作り、各エージェントにそっと渡します。
- **部分的な編集** — 編集の依頼では、関係するノードだけ作り直します。
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

### データベース

| テーブル | 役割 |
|---|---|
| `travel_plans` | 保存プラン（条件と結果をJSONで）。座標キャッシュ、カスタムピン、持ち物、実費、★も持ちます |
| `chat_messages` | チャット履歴。プランの行には `plan_json`（編集時に使う「前のプラン」）も |
| `trips` | 旅（名前・日付）、表紙写真、ベストショット、紐づけたプラン |
| `photos` / `stickers` | 写真（パス・撮影時刻・GPS）/ 付箋（表示する言葉と内部の根拠） |
| `share_links` / `share_grants` | 公開リンク / メールでの共有 |

所有権は常に `user_id`（Google の `sub`）で確認します。旅を消すと、関連する行と実体の写真まで連鎖して消えます。

### HTTP エンドポイント

**画面** — `/`（ようこそ）· `/chat` · `/saved_plans` · `/plan/<id>` · `/plan/<id>/print` · `/reflection/` · `/reflection/digest` · `/reflection/trips/<id>` · `/shared` · `/s/<token>` · `/terms` · `/privacy`

**チャット** — `/send_message`（SSE）· `/get_messages` · `/reset_chat` · `/abort_request` · `/generation_status`

**プラン** — `/save_plan` · `/get_my_plans` · `/get_shared_plans` · `/edit_saved_plan/<id>` · `/apply_saved_plan/<id>` · `/delete_plan/<id>` · `/rate_plan/<id>` · `/save_actual_total/<id>` · `/save_plan_pins/<id>` · `/export_plan_ics/<id>` · `/api/packing_list/<id>` · `/api/plan_geo/<id>` · `/api/plan_weather/<id>` · `/api/geocode`

**おもいで** — `/reflection/trips`（POST）· `/reflection/trips/<id>`（GET / PATCH / DELETE）· `…/photos` · `…/stickers` · `…/stickers/generate` · `…/best_shots` · `…/favorite` · `…/linked-plan` · `/reflection/photo/<path>`

**共有** — `/share/<type>/<id>`（状態）· `…/link` · `…/grant` · `/share/link/<id>` · `/share/grant/<id>` · `/shared/<type>/<id>` · `/shared/trip/<id>/…`（編集権限がある人の写真・付箋操作）· `/shared/plan/<id>/ics`

**ネイティブアプリ用** — `/auth/app/signin` · `/auth/app/me` · `/api/ideas` · `/api/chat_messages` · `/reflection/api/trips` · `/reflection/api/trips/<id>` · `/reflection/api/digest`

**認証** — `/auth/login` · `/auth/callback` · `/auth/logout`

`/`・`/terms`・`/privacy`・`/api/ideas`・`/auth/*` と公開ビュー `/s/<token>` 以外は `@login_required` の内側です。未認証のとき、APIには `401 JSON` を返し、ブラウザはログイン画面へ送ります。

### テストとCI

```bash
pytest tests/ -k "not smoke"    # 139件のオフラインテスト（APIキーもDBも不要）
scripts/check_home_js.sh        # チャット画面を本物のブラウザで動かす
scripts/check_ios_logic.sh      # iOSのロジックを Linux の Swift で型検査
python tests/test_smoke.py      # プラン生成の通し確認（APIキーが要ります）
```

| 検査 | 見ているもの |
|---|---|
| `test_units.py`（29） | サムネイルのキー、URL生成、パストラバーサル、地名の表記ゆれ、アプリ用トークンの発行と検証 |
| `test_ios_routes.py`（44） | iOSアプリが叩くURLが、そのメソッドでサーバーに実在すること |
| `test_regression.py`（23） | 一度戻ってきたことのある不具合 |
| `test_generation_status.py`（18） | リロード後の復元。pending / done / gone の判断と、ページが載せる情報 |
| `test_app_api.py`（16） | ネイティブアプリ向けAPIの認可とJSONの形 |
| `test_send_message_survives_disconnect.py`（7） | ブラウザが去っても生成が捨てられないこと |
| `test_static_js.py`（2） | JSとテンプレートが噛み合っていること（名前・要素のid） |
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

<p align="center">
  <img src="https://raw.githubusercontent.com/sabatexima/tabimate/main/src/static/img/mate.png" alt="ちゃむ" width="90"><br>
  <sub><i>また旅に出たくなったら、ちゃむを呼んでくださいね。🍀</i></sub>
</p>
