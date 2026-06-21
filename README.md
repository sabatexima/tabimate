# たびメイト（TabiMate）

AI が旅の「前」と「後」に寄り添う旅行アプリです。1つの Flask アプリに、旅行プラン作成と旅の振り返り＋共有をまとめています。

1. **旅行プラン作成チャット**（メイン機能）
   チャットで条件を伝えると、複数の AI エージェントが分担して観光・グルメ・宿泊・スケジュール・費用を設計し、審査役の AI が予算・無理のなさ・テーマ一貫性などを確認し、合格するまで自動で組み直したプランを返します。

2. **旅の振り返り（付箋）**
   旅の写真をアップロードすると、Gemini が写真と撮影メタデータから、旅の空気感を“少しズラして”切り取った短い言葉（**付箋／sticker**）を生成します。

3. **共有**
   旅やプランを公開リンクやメール指定で共有できます。公開リンクはログイン不要で閲覧可能。メール共有は本人だけがアクセスします。

ログインは Google アカウント（OAuth / OpenID Connect）。本番は Google Cloud Run + Cloud SQL + Cloud Storage 上で動作します。

---

## 主な機能

### 1. 旅行プラン作成チャット
- 自然な会話から旅行条件（必須7項目）を構造化抽出し、足りない項目を1つずつ質問。
- 条件が揃うと LangGraph のワークフローで多段エージェントがプランを生成。
- 交通手段（新幹線・飛行機・車・高速バス・おまかせ）を希望できる。希望に応じて往復費の試算方法とスケジュールの組み方が変わる（未指定は「おまかせ」で最適選択）。
- バランサー（審査役）が予算超過・スケジュール矛盾・テーマ不一致などを検出し、最大5回まで自動で差し戻し→再生成。
- 応答は SSE（Server-Sent Events）でストリーミング。生成中は「考え中（thinking）」を送り続け、途中キャンセルも可能。
- 完成プランは保存でき、保存プラン一覧から閲覧・削除できる。
- Web 検索（Tavily）で実在性・最新情報を補強。

### 2. 旅の振り返り（付箋）
- 旅（trip）を作成し、写真を複数枚アップロード（GCS またはローカル保存）。
- 写真の EXIF から撮影時刻・GPS を抽出し、コード側で特徴量（時間帯の偏り・移動距離・滞在範囲など）に要約。
- 特徴量＋代表写真を Gemini に渡し、付箋を3〜6枚生成。再生成のたびに付け直す。
- トップページは SNS フィード風。各旅カードは大きなサムネイル＋付箋バッジ。
- 旅のタイトルは後から編集可能。旅・写真の削除時はストレージ実体も掃除して孤立ファイルを残さない。

### 3. 共有
- 公開リンク: トークンURL（`/s/<token>`）を知る人が閲覧可能（ログイン不要）。
- メール指定: 指定メールでログインした本人だけが閲覧/編集（`/shared/...`）。
- 権限は `view`（閲覧のみ）/ `edit`（編集可）。編集は旅（写真追加・付箋生成）でのみ有効で、プランは常に閲覧専用。
- 所有者本人は常にフル権限。リンクの取り消しやグラントの削除も可能。
- 共有された側（受領者）も、自分宛の共有を自分の一覧から解除できる（相手の元データは消えない／再共有されれば再表示）。
- 共有された旅・プランは「共有された一覧」だけでなく、アルバム・保存プランにも統合表示される。

---

## 技術スタック

| 領域 | 採用技術 |
|------|----------|
| Web フレームワーク | Flask 3.1（Blueprint 4構成）+ Gunicorn（gthread, 1 worker / 20 threads, timeout 600） |
| プロキシ対応 | Werkzeug `ProxyFix`（Cloud Run の X-Forwarded-Proto/Host を信頼） |
| LLM | Google Gemini（`gemini-2.5-flash`）via `langchain-google-genai`、`with_structured_output` で型付き出力 |
| エージェント基盤 | LangGraph（`StateGraph`、条件分岐＋差し戻しループ） |
| Web 検索 | Tavily（`langchain-tavily`, max_results=8） |
| 認証 | Google OAuth / OpenID Connect（Authlib） |
| DB | MySQL 互換（Cloud SQL / TiDB Cloud / ローカル MySQL）+ SQLAlchemy 2.0（QueuePool） |
| 画像 | Pillow（EXIF 抽出・縮小・JPEG/Base64 化） |
| ストレージ | Google Cloud Storage（v4 署名付きURL / IAM signBlob）またはローカル FS |
| キャンセル状態共有 | Redis（任意）/ プロセス内 set フォールバック |
| インフラ | Google Cloud Run（ソースデプロイ）, Secret Manager, Cloud Storage |

---

## アーキテクチャ全体像

```
         ┌──────────── Flask app (app.py) ────────────┐
         │  ProxyFix + 4 Blueprints                   │
         │                                             │
 ブラウザ─┤  planner      ("/")        旅行プラン作成チャット │
         │  auth         ("/auth")    Google OAuth        │
         │  reflection   ("/reflection") 旅の振り返り（付箋）│
         │  sharing      ("/share")   共有管理               │
         └──────┬───────────────┬──────────┬──────────┘
                │               │          │
        chat/ (LangGraph)   db.py /   services/
        多段エージェント     db_reflection.py  exif・features・
                │           （SQLAlchemy） storage・
                ▼               │       trip_interpreter
        Gemini + Tavily         ▼
                          MySQL/TiDB
```

- **エントリポイント**: `src/app.py`。`.env` を読み込み、4つの Blueprint を登録し、OAuth を初期化する。
- **DB エンジンは共有**: `db.py` の `get_engine()` が生成する SQLAlchemy エンジン（QueuePool）を `db_reflection.py` / `db_sharing.py` も再利用する。テーブルは `CREATE TABLE IF NOT EXISTS` による遅延作成。
- **ストレージは抽象化**: `services/storage.py` が GCS とローカル FS を切り替える（`GCS_BUCKET` の有無で判定）。
- **共有は2方式**: `views/sharing.py` が公開リンク（トークン）とメールグラントを一元管理し、owner / edit / view の権限でアクセス制御する。

---

## ディレクトリ構成

```
tabimate/
├── README.md
├── requirements.txt          # Python 依存（gemini/langgraph/flask/gcs 等）
├── dockerfile                # ubuntu22.04 + python3.10 + gunicorn（Cloud Run ビルド用）
├── deploy.sh                 # Cloud Run デプロイ（Secret/GCS/IAM 設定込み）
├── tests/
│   └── test_smoke.py         # プラン生成の通し実行スモークテスト
└── src/
    ├── app.py                # Flask アプリ生成・Blueprint 登録
    ├── db.py                 # travel_plans / chat_messages の DAO + 共有エンジン
    ├── db_reflection.py      # trips / photos / stickers ほかの DAO
    ├── db_sharing.py         # 共有リンク/メールグラントの DAO
    ├── chat/                 # 旅行プラン生成（LLM/エージェント）
    │   ├── chat.py           #  会話の司令塔（条件抽出→質問 or プラン生成）
    │   ├── graph.py          #  LangGraph ワークフロー定義・実行
    │   ├── agents.py         #  各エージェント（ノード）の実装
    │   ├── models.py         #  TravelPlanState と構造化出力スキーマ
    │   ├── llm.py            #  Gemini/Tavily クライアント・リトライ
    │   ├── formatter.py      #  完成プラン → HTML カード整形
    │   └── logger.py         #  ロガー設定
    ├── services/             # 振り返り機能の部品
    │   ├── exif.py           #  EXIF から撮影時刻・GPS 抽出
    │   ├── features.py       #  写真メタデータ → 特徴量集計
    │   ├── storage.py        #  GCS / ローカル FS の抽象化
    │   └── trip_interpreter.py #  Gemini で付箋生成（トークンログ付き）
    ├── views/                # Blueprint（ルーティング）
    │   ├── planner.py        #  チャット・SSE・保存プラン
    │   ├── auth.py           #  Google OAuth ログイン
    │   ├── reflection.py     #  旅・写真・付箋の API と画面
    │   └── sharing.py        #  共有リンク/メール共有/権限制御
    └── templates/            # Jinja2 テンプレート
        ├── layout.html, home.html, saved_plans.html, sidebar.html
        ├── _share_modal.html
        └── reflection/
            ├── index.html    #  旅一覧（フィード風・付箋バッジ）
            └── trip.html     #  旅詳細（付箋ヒーロー・写真・編集/削除）
        └── shared/
            ├── index.html    #  自分に共有された旅・プラン一覧
            ├── trip.html     #  共有旅の詳細（編集可）
            └── plan.html     #  共有プランの詳細（閲覧専用）
    └── static/               # CSS / JS / 画像
        ├── css/
        ├── js/
        └── img/
```

---

## プラン生成エージェントの仕組み

`chat/graph.py` が LangGraph の `StateGraph` を定義し、`chat/agents.py` の各関数をノードとして連結します。状態は `chat/models.py` の `TravelPlanState`（TypedDict）として全ノード間で受け渡されます。

### フロー

```
START
  → transport（希望の交通手段で往復費を概算・残予算算出。車=ガソリン＋高速を人数割り等、未指定はおまかせ）
  → sightseeing_candidates（観光候補 5〜8件）
  → sightseeing（観光スポット 2〜3件を選定）
  → accommodation_candidates（宿泊候補 3〜5件 / 日帰りなら空）
  → accommodation（宿泊 1〜2件を選定 / 残予算の40%が目安上限）
  → gourmet_candidates（飲食候補 4〜6件）
  → gourmet（飲食 2〜3件を選定 / 残予算の25%が食費目安）
  → timekeeper（時系列スケジュール組み立て）
  → cost_manager（日別＋合計の費用見積もり）
  → balancer（全体審査）
        └─ route_after_balancer で分岐：
             approved / budget_infeasible → END
             fix_sightseeing → sightseeing へ
             fix_gourmet / fix_accommodation / fix_budget → accommodation へ
             fix_time → timekeeper へ
             （同じ問題の繰り返しは観光選定まで戻す）
```

- **審査観点**: 予算 / スケジュールの現実性 / 疲労度 / テーマ一貫性 /（宿泊ありなら）特別条件の充足。
- **差し戻し上限**: `MAX_BALANCER_RETRIES = 5`。`recursion_limit = 60` でループ暴走を防止。
- **予算配分**: 宿泊は残予算の40%（`ACCOMMODATION_BUDGET_RATIO`）、食費は25%（`FOOD_BUDGET_RATIO`）が目安上限。
- **交通費が予算超過**なら `transport_agent` が `ValueError` を投げ、ユーザーに「予算超過」を通知して中断。
- **日帰り判定**: `is_day_trip()` が期間文字列を見て宿泊ノードをスキップ。
- **ユーザー要望の反映**: 再プラン時、`user_feedback` を各エージェントのプロンプトに「最優先」で差し込む。
- **Web 検索**: `chat/llm.py` の `build_search_context()` が Tavily で公式/ガイド情報を集め、候補抽出の根拠にする（スコア閾値 0.3）。
- **リトライ**: `invoke_with_retry()` がレート制限（429/503）や接続エラーを指数/線形バックオフで最大5回リトライ。

### 共有の仕組み

`views/sharing.py` が公開リンクとメール共有を管理します。

- **公開リンク**（`/s/<token>`）: トークンを知る人がログイン不要で閲覧可能。権限はリンク作成時に指定（デフォルトは `view`）。トークンは推測困難なランダム文字列。
- **メール共有**: 指定したメールアドレスでログインした本人だけが `/shared/...` で閲覧可能。`view` または `edit` 権限を付与できる（`edit` は旅の写真追加・付箋生成に有効）。
- **権限制御**: 所有者本人→常にフル権限。それ以外は「有効なトークン」または「自分のメール宛グラント」がある場合のみアクセス可能。
- **写真配信**: 本番では GCS の署名付きURL（IAM signBlob方式）で配信するため、共有閲覧者でも追加の認証なしに写真を表示できる。
- **オブジェクトモデル**: `db_sharing.py` が `share_links` と `share_grants` を管理。リンクの取り消し・グラントの削除は所有者が行えるほか、受領者本人も自分宛のグラントを `delete_grant_as_grantee()` で解除できる。

---

## 旅の振り返り（付箋）の仕組み

### パイプライン

1. **アップロード**（`views/reflection.py: upload_photos`）
   - 1リクエスト最大50枚、許可拡張子のみ（jpg/jpeg/png/heic/webp/gif）。
   - 各写真を `services/exif.py` で撮影時刻・GPS 抽出 → `services/storage.py` で保存 → DB に `storage_path` とメタデータを記録。

2. **特徴量集計**（`services/features.py: aggregate`）
   - 時間帯の偏り（早朝/午前/昼/夕方/夜/深夜）、日別枚数、撮影間隔、GPS のバウンディングボックス・中心・広がり・総移動距離（Haversine）などを算出。
   - 生メタデータ全件を LLM に投げず、人間可読な要約に落としてトークンを節約。

3. **付箋生成**（`services/trip_interpreter.py: interpret_stickers`）
   - 代表写真を均等サンプリングして収集。
   - 写真は縮小（長辺 512px・JPEG q80・Base64 data URL）してマルチモーダルで送信。送付枚数は `STICKER_MAX_IMAGES`（既定6）で制限。
   - few-shot のお手本と厳守ルール（写真の事実から逸脱しない・全体を反映・詩的/擬人化/大喜利可・6〜14字・説明文や見出しにしない）でトーンを統一。
   - 出力スキーマ `StickersOutput`（`StickerItem{text, basis}`）。`basis`（生成根拠）は内部用でユーザーには返さない。
   - 毎回 input/output トークン数と推定コスト（USD）をログ出力。

4. **保存・表示**
   - 既存付箋は再生成時に `replace_stickers()` でまとめて付け直す。
   - 一覧は相関サブクエリで `photo_count` + 最新2枚の付箋を1クエリ取得（N+1 回避）。

---

## データベース設計

すべて `CREATE TABLE IF NOT EXISTS` で初回アクセス時に自動作成されます（utf8mb4）。

| テーブル | 定義元 | 用途 |
|----------|--------|------|
| `travel_plans` | `db.py` | 保存された旅行プラン（条件・成果物を JSON 列で保持） |
| `chat_messages` | `db.py` | チャット履歴（role/content/request_id） |
| `trips` | `db_reflection.py` | 旅（タイトル・期間・所有ユーザー） |
| `photos` | `db_reflection.py` | アップロード写真（storage_path・撮影時刻・GPS） |
| `stickers` | `db_reflection.py` | 付箋（text=表示文・basis=内部の生成根拠） |
| `share_links` | `db_sharing.py` | 公開共有リンク（token/resource_type/resource_id/permission） |
| `share_grants` | `db_sharing.py` | メール指定共有（grantee_email/resource_type/resource_id/permission） |
| `achievements` | `db_reflection.py` | 旧「称号」機能のテーブル（現 UI 未使用・後方互換で残置） |
| `trip_reports` | `db_reflection.py` | 旧「AI 旅レポート」機能のテーブル（現 UI 未使用・残置） |

- 所有権は常に `user_id`（Google の `sub`）で照合し、他人のデータにアクセスできない。
- 旅削除時は `photos` / `stickers` / `achievements` / `trip_reports` を連鎖削除し、写真実体も `storage.delete()` で除去。
- TiDB 互換性のため、付箋プレビューは `GROUP_CONCAT` ではなくスカラーサブクエリで取得している。

---

## HTTP エンドポイント一覧

### planner（`/`） — `views/planner.py`

| メソッド | パス | 説明 |
|----------|------|------|
| GET | `/` | ホーム（チャット画面） |
| GET | `/saved_plans` | 保存プラン一覧画面（要ログイン） |
| POST | `/send_message` | 発話を受け取り AI 応答を SSE ストリーミング（要ログイン・レート制限 5回/60秒） |
| POST | `/abort_request` | 生成中リクエストのキャンセル |
| POST | `/reset_chat` | チャット履歴のリセット |
| GET | `/get_messages` | チャット履歴の取得 |
| POST | `/save_plan` | プラン保存 |
| DELETE | `/delete_plan/<id>` | プラン削除 |
| GET | `/get_my_plans` | 自分の保存プラン一覧（JSON） |
| GET | `/get_shared_plans` | 自分宛に共有されたプラン一覧（JSON・保存プラン画面に統合表示） |

### auth（`/auth`） — `views/auth.py`

| メソッド | パス | 説明 |
|----------|------|------|
| GET | `/auth/login` | Google OAuth 開始 |
| GET | `/auth/callback` | OAuth コールバック（セッションに user_id/email/name 保存） |
| GET | `/auth/logout` | ログアウト（セッションクリア） |

### reflection（`/reflection`） — `views/reflection.py`

| メソッド | パス | 説明 |
|----------|------|------|
| GET | `/reflection/` | 旅一覧（フィード風） |
| GET | `/reflection/trips/<id>` | 旅詳細（付箋・写真） |
| POST | `/reflection/trips` | 旅の作成 |
| PATCH | `/reflection/trips/<id>` | 旅タイトルの編集 |
| DELETE | `/reflection/trips/<id>` | 旅の削除（写真実体・関連データも削除） |
| POST | `/reflection/trips/<id>/photos` | 写真アップロード（最大50枚） |
| GET | `/reflection/photo/<path>` | ローカル保存写真の配信（GCS 時は署名付きURLを使用） |
| POST | `/reflection/trips/<id>/stickers/generate` | 付箋の生成（写真必須） |
| GET | `/reflection/trips/<id>/stickers` | 付箋一覧 |
| DELETE | `/reflection/trips/<id>/stickers/<sid>` | 付箋の削除 |

### sharing（`/share`） — `views/sharing.py`

| メソッド | パス | 説明 |
|----------|------|------|
| GET | `/share/trip|plan/<id>` | 共有一覧（モーダル用JSON） |
| POST | `/share/trip|plan/<id>/link` | 公開リンク作成 |
| DELETE | `/share/link/<id>` | 公開リンク削除 |
| POST | `/share/trip|plan/<id>/grant` | メール共有の追加 |
| DELETE | `/share/grant/<id>` | メール共有の削除（所有者による取消） |
| DELETE | `/shared/grant/<id>` | 共有された側が自分宛の共有を解除（受領者本人のみ） |
| GET | `/s/<token>` | 公開リンク閲覧（ログイン不要） |
| GET | `/shared` | 自分宛の共有一覧 |
| GET | `/shared/trip|plan/<id>` | メール共有による閲覧 |
| POST | `/shared/trip/<id>/photos` | 共有旅への写真追加 |
| DELETE | `/shared/trip/<id>/photos/<photo_id>` | 共有旅の写真削除 |
| POST | `/shared/trip/<id>/stickers/generate` | 共有旅の付箋生成 |
| DELETE | `/shared/trip/<id>/stickers/<sticker_id>` | 共有旅の付箋削除 |
| DELETE | `/shared/trip/<id>` | 共有旅の削除 |

`reflection` と `sharing` + プラン保存系は `@login_required` で保護。

---

## 環境変数

`src/.env`（ローカル）または Cloud Run の環境変数 / Secret Manager で設定します。**秘密情報はコードに直書きせず、必ず環境変数で渡してください。** `src/.env` は Git 管理対象外です。

| 変数 | 必須 | 用途 |
|------|------|------|
| `SECRET_KEY` | 本番 | Flask セッション署名鍵 |
| `GOOGLE_API_KEY` | ✓ | Gemini API キー |
| `TAVILY_API_KEY` | ✓ | Tavily Web 検索 |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | ✓ | Google OAuth |
| `DB_USER` / `DB_PASS` / `DB_NAME` / `DB_HOST` / `DB_PORT` | ✓ | DB 接続情報 |
| `DB_SSL` | △ | `true` で TLS 接続（TiDB Cloud は必須） |
| `DB_SSL_CA` | | CA バンドルのパス（既定 `/etc/ssl/certs/ca-certificates.crt`） |
| `CLOUD_SQL_INSTANCE` | △ | 設定時は Cloud SQL Connector 経由で接続 |
| `GCS_BUCKET` | △ | 設定時は GCS、未設定ならローカル FS に保存 |
| `LOCAL_UPLOAD_DIR` | | ローカル保存先（既定 `src/uploads`） |
| `SIGNED_URL_TTL_SECONDS` | | 署名付きURLの有効秒数（既定 3600） |
| `GCS_SIGNER_SA` | | 署名に使う SA を明示したい場合 |
| `REDIS_URL` | | 設定時は生成中リクエスト状態を Redis で共有 |
| `STICKER_MAX_IMAGES` / `INTERPRETER_IMAGE_MAX_EDGE` 等 | | 付箋生成の画像枚数/縮小サイズ調整 |

---

## ローカル開発

```bash
# src/.env を用意（上記の環境変数を設定）してから
cd src
python3 -m venv .venv
source .venv/bin/activate
pip install -r ../requirements.txt
python3 app.py        # http://localhost:5007 （Flask 開発サーバ）
```

- DB は `DB_HOST`/`DB_PORT`/`DB_USER`/`DB_PASS`/`DB_NAME` で任意の MySQL/TiDB を指定する（テーブルは起動時に遅延作成される）。
- 写真保存先は `GCS_BUCKET` を省略すればローカルの `LOCAL_UPLOAD_DIR` になる。

---

## 本番デプロイ（Cloud Run）

`deploy.sh` が一連の作業を自動化します（`src/.env` を読み込んで使用）。

```bash
./deploy.sh
```

スクリプトが行うこと:
1. 必要な GCP API を有効化（run / artifactregistry / cloudbuild / secretmanager / storage / iamcredentials）。
2. シークレット（GOOGLE_API_KEY, TAVILY_API_KEY, GOOGLE_CLIENT_SECRET, DB_PASS, SECRET_KEY）を Secret Manager に登録/更新し、Cloud Run の SA に閲覧権限を付与。
3. 写真用 GCS バケット（既定 `kabu-trip-photos`）を作成し、SA に `objectAdmin` を付与。
4. 署名付きURL のため SA に `serviceAccountTokenCreator`（IAM signBlob）を付与。
5. `gcloud run deploy --source .` でソースデプロイ（リージョン `asia-northeast1`、サービス `kabu-app`、プロジェクト `august-bot-462013-g2`）。

> Cloud Run のデフォルト SA は秘密鍵を持たないため、GCS の署名付きURL は通常の `generate_signed_url` ではなく **IAM signBlob 方式**（`service_account_email` + `access_token`）で生成します（`services/storage.py`）。

---

## テスト

```bash
python tests/test_smoke.py
# または pytest tests/
```

`tests/test_smoke.py` はプラン生成ワークフローを実際に通し実行し、目的地が保持されることと `spots` がリストであることを確認します（Gemini/Tavily の API キーが必要）。

---

## セキュリティ方針

- **秘密情報はコードに直書きしない**。すべて環境変数 / Secret Manager 経由。`src/.env` はコミットしない。
- **所有権チェック**: 旅・写真・付箋・プラン・共有リンクは常に `user_id` で照合し、他人のデータにアクセスさせない。
- **XSS 対策**: 完成プランの HTML 整形（`formatter.py`）でユーザー由来文字列をすべてエスケープ。
- **パストラバーサル対策**: ローカル写真の読み出し/削除でアップロードディレクトリ外へのアクセスを拒否。
- **レート制限**: チャット送信は 5回/60秒/ユーザー。
- **アップロード制限**: 1リクエスト最大50枚、拡張子ホワイトリスト。
- **プロキシ信頼**: `ProxyFix` で Cloud Run の forwarded ヘッダのみを信頼し、OAuth コールバック URL を正しいスキーム/ホストで生成。
- **共有リンクの推測困難性**: `db_sharing.py` が十分な長さのランダムトークンを生成し、漏洩リスクを低減。
