<p align="center">
  <img src="https://raw.githubusercontent.com/sabatexima/tabimate/main/src/static/img/mate-head.png" alt="ちゃむ" width="130">
</p>

<h1 align="center">たびメイト&nbsp;🍀</h1>

<p align="center">
  <b>旅のしおり、 AIが作ります。</b><br>
  帰ってきたら、写真がひとりでに「付箋」になる。
</p>

<p align="center">
  <i>絵本みたいにやさしい、旅の相棒アプリ。</i>
</p>

<p align="center">
  <a href="README.md">🇬🇧&nbsp;English</a>&nbsp;&nbsp;·&nbsp;&nbsp;
  <a href="https://github.com/sabatexima/tabimate/actions/workflows/ci.yml"><img src="https://github.com/sabatexima/tabimate/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/sabatexima/tabimate/main/docs/img/screen-journal.png" alt="旅の振り返り" width="240">
  <img src="https://raw.githubusercontent.com/sabatexima/tabimate/main/docs/img/screen-bookshelf.png" alt="保存プラン" width="240">
  <img src="https://raw.githubusercontent.com/sabatexima/tabimate/main/docs/img/screen-plan-detail.png" alt="プラン詳細" width="240">
</p>

---

## 🍀 たびメイトって？

> _「どこ行こう？」から「楽しかったね」まで。<br>
> 旅のぜんぶに、ちゃむがそっと寄り添います。_

旅行アプリはたくさんあるけれど、たびメイトがこだわったのは **旅の「前」と「後」** 。

計画はAIとおしゃべりするだけ。帰ってきたら写真を放り込むだけ。
あとはマスコットの **ちゃむ** が、しおりを綴じて、思い出を付箋にして、こっそり額に飾ってくれます。

<table>
<tr>
<td width="33%" align="center"><br>🗺️<br><b>旅の「まえ」</b><br><sub>AIと話すだけで<br>しおりができる</sub><br><br></td>
<td width="33%" align="center"><br>📸<br><b>旅の「あと」</b><br><sub>写真がそのまま<br>思い出の付箋に</sub><br><br></td>
<td width="33%" align="center"><br>🤝<br><b>みんなで</b><br><sub>しおりも思い出も<br>そっとおすそわけ</sub><br><br></td>
</tr>
</table>

---

## ✨ できること

### 🗺️ 旅のまえ &mdash; 話すだけで、しおりができる

> _ちゃむ「どこ行きたい？ 何泊する？ ……うん、まかせて。」_

- 💬 **おしゃべりでプラン作成** &mdash; 行き先・日数・予算などを会話から読み取り、足りないことは1つずつ質問。条件がそろうと、複数のAIエージェント（LangGraph）が力を合わせてプランを組み立てます。
- 🌤️ **お天気を読む** &mdash; 旅行日の予報を見て、雨なら屋内多め・寒いなら…と中身を調整。定休日にあたりそうなお店も避けます。
- 🍽️ **実在するお店だけ** &mdash; Google Placesで裏取りして、"それっぽい創作店" を候補から落とします。
- 🗾 **水彩の地図** &mdash; 観光・グルメ・宿を色分けピンで、**移動する順番**に線でつないで表示。ピンをタップで経路ナビへ。
- 🎒 **持ちものリスト** &mdash; 行き先と天気から、ちゃむが持ちものを提案。チェックすると四つ葉が咲きます。
- 🍀 **出発カウントダウン** &mdash; 「旅まであと12日」。本棚を開くたび、ちょっとわくわく。
- 📅 **カレンダー書き出し** &mdash; スケジュールを `.ics` に。Googleカレンダー等にそのまま入ります。
- ✏️ **あとから微調整** &mdash; 「2日目をゆっくりに」「宿を変えて」もチャットでOK。★をつけると、次の提案にこっそり反映されます。

### 📸 旅のあと &mdash; 写真が、ひとりでに言葉になる

> _ちゃむ「おかえり。写真、見せて。……いい旅だったね。」_

- 🏷️ **写真から付箋を生成** &mdash; アップした写真をAIが読み取って、旅の空気を短い言葉の「付箋」に。（例:「曇り空が同行者」）
- 📖 **トラベルジャーナル** &mdash; ポラロイドとパステルの付箋を貼ったクラフト台紙。検索・お気に入りで見返せます。
- 🏅 **ちゃむのベストショット** &mdash; たくさんの写真から「飾りたい一枚」を選んで、金の額縁に。
- 💰 **旅の会計** &mdash; 見積もりと実際に使った額をならべて記録。予算内なら「◯円おトク🍀」。
- 🐾 **足あとマップ** &mdash; 写真のGPSから歩いた道を地図に。プランを重ねれば「計画 vs 実際」も見られます。
- 📔 **年間ダイジェスト** &mdash; 「一年の旅のきろく」。その年の旅と付箋を、まるっと振り返り。

### 🤝 わけあう

- 🔗 **公開リンク** で、ログイン不要のおすそわけ（閲覧専用）。
- ✉️ **メール指定** で、相手だけに閲覧／編集を許可。
- 📱 **PWA対応** &mdash; ホーム画面に追加すれば、ちゃむのアイコンからアプリとして起動できます。

---

## 🛠️ 何でできてる？

|  |  |
|---|---|
| 🧠 **AI** | LangGraph · LangChain · Gemini 3.5 Flash / 3.1 Flash-Lite · Tavily Search |
| ⚙️ **バックエンド** | Flask 3.1 · SQLAlchemy · MySQL 8.0 / TiDB · gunicorn |
| 🗺️ **地図・位置情報** | Leaflet · Stadia Maps（水彩タイル）· Google Places · OSM Nominatim · 国土地理院 |
| ☁️ **インフラ** | Google Cloud Run · Docker · Cloud Storage · Secret Manager · Google OAuth 2.0 · GitHub Actions |
| 🎨 **フロント** | Jinja2 · Vanilla JS · PWA · Zen Maru Gothic |

---

## 🚀 動かしてみる

```bash
# 1. クローン
git clone <repo-url> && cd tabimate

# 2. 環境変数を用意（最低限：APIキー・OAuth・DB接続）
cp src/.env.example src/.env   # → 中身を埋める

# 3. 依存を入れて起動
cd src
python3 -m venv .venv && source .venv/bin/activate
pip install -r ../requirements.txt
python3 app.py
```

ブラウザで **http://localhost:5007** へ。DBのテーブルは初回アクセス時に自動でできます（`CREATE TABLE IF NOT EXISTS`）。

> 🍀 **本番へは1コマンド** &mdash; `./deploy.sh` が Cloud Run へのデプロイ（Secret・GCSバケット・IAM権限の設定込み）を全部やってくれます。

---

<details>
<summary><b>📖 もっと詳しく（開発者向けドキュメント）</b></summary>

<br>

### 環境変数

`src/.env`（ローカル）または Cloud Run の環境変数 / Secret Manager で設定します。`src/.env` は Git 管理対象外です。

| 変数 | 必須 | 用途 |
|------|------|------|
| `SECRET_KEY` | 本番 | Flask セッション署名鍵 |
| `GOOGLE_API_KEY` | ✓ | Gemini API キー |
| `TAVILY_API_KEY` | ✓ | Tavily Web 検索 |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | ✓ | Google OAuth |
| `DB_USER` / `DB_PASS` / `DB_NAME` / `DB_HOST` / `DB_PORT` | ✓ | DB 接続情報 |
| `STADIA_API_KEY` | | 地図の水彩タイル（未設定時は標準OSMタイル） |
| `GOOGLE_MAPS_API_KEY` | | Google Placesでジオコーディング強化。未設定なら無料スタック（Nominatim＋地理院）のみ |
| `DB_SSL` / `DB_SSL_CA` | △ | TLS接続（TiDB Cloud は `DB_SSL=true` 必須） |
| `CLOUD_SQL_INSTANCE` | △ | 設定時は Cloud SQL Connector 経由 |
| `GCS_BUCKET` | △ | 設定時は GCS、未設定ならローカルFS |
| `LOCAL_UPLOAD_DIR` / `SIGNED_URL_TTL_SECONDS` / `GCS_SIGNER_SA` | | ローカル保存先・署名URL有効秒数・署名用SA |
| `REDIS_URL` | | 生成中リクエスト状態を Redis で共有 |
| `STICKER_MAX_IMAGES` / `INTERPRETER_IMAGE_MAX_EDGE` 等 | | 付箋生成の画像枚数/縮小サイズ |

### ディレクトリ構成

```
tabimate/
├── deploy.sh                 # Cloud Run デプロイ（Secret/GCS/IAM込み）
├── .github/workflows/ci.yml  # push/PRごとのCI
├── scripts/                  # backfill_thumbnails.py / setup_alerts.sh
├── tests/                    # test_smoke.py（通し）/ test_units.py（オフライン）
└── src/
    ├── app.py                # Flask生成・Blueprint登録
    ├── db.py                 # travel_plans / chat_messages の DAO
    ├── db_reflection.py      # trips / photos / stickers の DAO
    ├── db_sharing.py         # 共有リンク/メールグラントの DAO
    ├── geocoding.py          # スポット名→緯度経度（複数プロバイダ・遅延キャッシュ）
    ├── weather.py            # 旅行日の天気（Open-Meteo）
    ├── chat/                 # 旅行プラン生成（LangGraph / エージェント）
    │   └── chat.py graph.py agents.py models.py llm.py formatter.py logger.py
    ├── services/             # exif · features · storage · trip_interpreter · packing
    ├── views/                # planner · auth · reflection · sharing（Blueprint）
    ├── templates/            # Jinja2（layout / home / welcome / reflection / shared …）
    └── static/               # css / js / img
```

### アーキテクチャ

```
         ┌──────────── Flask app (app.py) ────────────┐
         │  ProxyFix + 4 Blueprints                    │
 ブラウザ ┤  planner("/")  auth("/auth")               │
         │  reflection("/reflection")  sharing("/share")│
         └──────┬───────────────┬──────────┬──────────┘
                │               │          │
        chat/ (LangGraph)   db.py /     services/
        多段エージェント     db_reflection  exif·features·
                │           (SQLAlchemy)  storage·interpreter
                ▼               │
        Gemini + Tavily         ▼
                          MySQL / TiDB
```

- **DBエンジンは共有**: `db.py` の `get_engine()`（QueuePool）を `db_reflection` / `db_sharing` も再利用。テーブルは `CREATE TABLE IF NOT EXISTS` で遅延作成。
- **ストレージは抽象化**: `services/storage.py` が GCS / ローカルFS を切替（`GCS_BUCKET` の有無）。GCS署名URLはキャッシュ＋並列生成で高速化。
- **共有は2方式**: 公開リンク（トークン）とメールグラントを `views/sharing.py` が一元管理し、owner/edit/view で制御。

### プラン生成エージェント（LangGraph）

`chat/graph.py` が `StateGraph` を定義し、`chat/agents.py` の各関数をノードとして連結。状態は `TravelPlanState`（TypedDict）で受け渡し。

```
START
  → transport（往復費・残予算）
  → sightseeing_candidates → sightseeing（観光 2〜3件）
  → accommodation_candidates → accommodation（宿 / 残予算の40%目安・日帰りはスキップ）
  → gourmet_candidates → gourmet（飲食 / 残予算の25%目安）
  → timekeeper（時系列スケジュール）
  → cost_manager（費用見積もり）
  → balancer（全体審査）
        └─ approved / budget_infeasible → END
           fix_* → 該当ノードへ差し戻し（上限 MAX_BALANCER_RETRIES=5）
```

- **宿泊なし判定**: `parse_duration()` が期間を（泊数,日数）に解釈。泊数0なら宿ノードをスキップ（「0泊2日」の夜行にも対応）。
- **候補の実在チェック**: `GOOGLE_MAPS_API_KEY` 設定時、観光・グルメ・宿の候補を Google Places で照合し創作名を除外。
- **好みの学習**: 過去の★評価・コメントから `user_preferences` を作り、各エージェントにやんわり注入。
- **部分編集**: 変更要望から対象ノードだけ再生成（他は前回を保持）。
- **リトライ**: `invoke_with_retry()` が 429/503・接続エラーを最大5回バックオフ再試行。

### データベース

| テーブル | 用途 |
|----------|------|
| `travel_plans` | 保存プラン（条件・成果物をJSON列で）。地図座標キャッシュ・カスタムピン・持ちもの・実績費用・★評価も保持 |
| `chat_messages` | チャット履歴。プラン提示行は `plan_json` も保存（編集時の"前回プラン"） |
| `trips` | 旅（タイトル・期間）。表紙写真・ベストショット・紐付けプランを保持 |
| `photos` / `stickers` | 写真（storage_path・撮影時刻・GPS）／ 付箋（表示文＋内部の生成根拠） |
| `share_links` / `share_grants` | 公開リンク ／ メール指定共有 |

- 所有権は常に `user_id`（Google の `sub`）で照合。旅削除時は関連データと写真実体も連鎖削除。

### 主なHTTPエンドポイント

**planner（`/`）** &mdash; `/`（チャット）· `/saved_plans` · `/plan/<id>` · `/send_message`(SSE) · `/save_plan` · `/edit_saved_plan/<id>` · `/rate_plan/<id>` · `/save_actual_total/<id>` · `/api/packing_list/<id>` · `/api/plan_geo/<id>` · `/api/plan_weather/<id>` · `/export_plan_ics/<id>`

**reflection（`/reflection`）** &mdash; `/trips` · `/trips/<id>` · `/trips/<id>/photos` · `/trips/<id>/stickers/generate` · `/trips/<id>/best_shots` · `/trips/<id>/linked-plan`

**sharing（`/share`, `/shared`, `/s/<token>`）** &mdash; リンク作成/削除 · メール共有の付与/取消 · 公開閲覧 · 共有旅への写真・付箋操作

**auth（`/auth`）** &mdash; `/login` · `/callback` · `/logout`

`reflection`・`sharing`・プラン保存系は `@login_required` で保護。

### テスト & CI

```bash
pytest tests/                # 一式
python tests/test_smoke.py   # プラン生成の通し（APIキー必要）
```

- `test_units.py` は **APIキー/DB不要のオフライン**テスト（サムネキー導出・URL生成・パストラバーサル・ジオコーディングの表記ゆらぎ/候補選択）。
- push / PR ごとに **GitHub Actions** がオフラインテスト・全JSの構文チェック・全テンプレートのコンパイルを自動実行。

### セキュリティ

- 秘密情報はコード直書きせず環境変数 / Secret Manager 経由（`src/.env` はコミットしない）。
- 本番で `SECRET_KEY` 未設定なら起動失敗。Cookie は HttpOnly / SameSite=Lax（本番は Secure）。
- OAuth は `email_verified` を必須化。全リソースを `user_id` で所有権チェック。
- プランHTMLはユーザー文字列をエスケープ（XSS対策）、ローカル写真はパストラバーサル対策。
- レート制限（チャット5回/60秒・外部API系は別枠）、アップロード制限（最大50枚・拡張子ホワイトリスト・サイズ上限）。
- 全レスポンスに `X-Content-Type-Options` / `X-Frame-Options` / `Referrer-Policy`。`ProxyFix` で Cloud Run のforwardedヘッダを信頼。

### トラブルシューティング

- **`.env` が無い** → `src/.env` を作成し環境変数を設定。
- **MySQLに繋がらない** → `DB_HOST` を確認。Cloud SQL は `CLOUD_SQL_INSTANCE`、TiDB は `DB_SSL=true`。
- **生成が504** → `deploy.sh` が `--timeout=3600` を設定済み。手動デプロイ環境なら `gcloud run services update ... --timeout=3600`。
- **写真表示が遅い** → 署名URLは写真ごとにIAM signBlobを呼ぶため。`storage.get_urls()` がキャッシュ＋並列化、一覧はサムネイル配信。旧写真は `scripts/backfill_thumbnails.py`。
- **地図にピンが立たない** → `GOOGLE_MAPS_API_KEY` 設定時は **Places API (New)** の有効化が必要。起動ログの「外部連携」行で有効/無効を確認できます。

</details>

---

<p align="center">
  <img src="https://raw.githubusercontent.com/sabatexima/tabimate/main/src/static/img/mate.png" alt="ちゃむ" width="90"><br>
  <sub><i>また旅に出たくなったら、ちゃむを呼んでね。🍀</i></sub>
</p>
