<p align="center">
  <img src="https://raw.githubusercontent.com/sabatexima/tabimate/main/src/static/img/mate-head.png" alt="ちゃむ（たびメイトのマスコット）" width="120">
</p>

<h1 align="center">たびメイト（TabiMate）🍀</h1>

<p align="center">
  AI が旅の「前」と「後」に寄り添う、やさしい絵本のような旅行アプリ。<br>
  旅行プラン作成・旅の振り返り（付箋）・共有を、1つの Flask アプリにまとめています。
</p>

<p align="center">
  <a href="README.md">English</a><br><br>
  <a href="https://github.com/sabatexima/tabimate/actions/workflows/ci.yml"><img src="https://github.com/sabatexima/tabimate/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
</p>

## スクリーンショット

| 旅の振り返り（ジャーナル） | 保存プラン（本棚） | プラン詳細（ブックレット） |
|:---:|:---:|:---:|
| <img src="https://raw.githubusercontent.com/sabatexima/tabimate/main/docs/img/screen-journal.png" alt="旅の振り返り" width="250"> | <img src="https://raw.githubusercontent.com/sabatexima/tabimate/main/docs/img/screen-bookshelf.png" alt="保存プラン" width="250"> | <img src="https://raw.githubusercontent.com/sabatexima/tabimate/main/docs/img/screen-plan-detail.png" alt="プラン詳細" width="250"> |

## 目次

- [技術スタック](#技術スタック)
- [主な機能](#主な機能)
- [環境変数一覧](#環境変数一覧)
- [ディレクトリ構成](#ディレクトリ構成)
- [アーキテクチャ](#アーキテクチャ)
- [開発環境の構築方法](#開発環境の構築方法)
- [データベース設計](#データベース設計)
- [HTTP エンドポイント一覧](#http-エンドポイント一覧)
- [プラン生成エージェントの仕組み](#プラン生成エージェントの仕組み)
- [テスト](#テスト)
- [セキュリティ方針](#セキュリティ方針)
- [トラブルシューティング](#トラブルシューティング)

## 技術スタック

![Flask](https://img.shields.io/badge/Flask-3.1-000000.svg?logo=flask&logoColor=white)
![LangChain](https://img.shields.io/badge/LangChain-1.3-1DA1F2.svg?logo=langchain)
![LangGraph](https://img.shields.io/badge/LangGraph-1.2-1DA1F2.svg?logo=langgraph&logoColor=white)
![Google%20Gemini](https://img.shields.io/badge/Gemini-3.5_Flash_%2F_3.1_Flash--Lite-4285F4.svg?logo=google%20gemini&logoColor=white)
![Tavily](https://img.shields.io/badge/Tavily-Search-F97316.svg?logo=tavily&logoColor=white)
![MySQL](https://img.shields.io/badge/MySQL-8.0-4479A1.svg?logo=mysql&logoColor=white)
![Google%20Cloud%20Run](https://img.shields.io/badge/Cloud_Run-Cloud-4285F4.svg?logo=google%20cloud&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Build-2496ED.svg?logo=docker&logoColor=white)
![Google%20OAuth](https://img.shields.io/badge/Google_OAuth-2.0-4285F4.svg?logo=google&logoColor=white)
![Leaflet](https://img.shields.io/badge/Leaflet-1.9-199900.svg?logo=leaflet&logoColor=white)
![Stadia%20Maps](https://img.shields.io/badge/Stadia_Maps-Watercolor-7AB870.svg)

## 主な機能

### 1. 旅行プラン作成チャット（メイン機能）
- 自然な会話から旅行条件（必須7項目）を構造化抽出し、足りない項目を1つずつ質問。
- 条件が揃うと LangGraph のワークフローで多段エージェントがプランを生成。
- 交通手段（新幹線・飛行機・車・高速バス・おまかせ）を希望できる。希望に応じて往復費の試算方法とスケジュールの組み方が変わる（未指定は「おまかせ」で最適選択）。
- **時間の希望**（「夕方までに帰りたい」「朝はゆっくり」など）を会話から読み取り、スケジュールに最優先で反映。
- **日帰りでも1日をしっかり使う**：スポット数を期間に応じて増やし、スケジュールは「無理のない帰宅時刻 − 復路の所要時間 = 現地出発時刻」と**帰宅時刻から逆算**して組む（昼過ぎに早帰りしない）。
- バランサー（審査役）が予算超過・スケジュール矛盾・テーマ不一致などを検出し、自動で差し戻し→再生成（回数上限あり）。
- **天気を生成に反映**：生成開始時に旅行日の天気予報（Open-Meteo・APIキー不要）を取得し、雨・雪・雷の日は観光選定とスケジュールを屋内中心・屋外短めに寄せる。予報が取れない日（16日より先・日付不明）は天気考慮なし。
- **グルメの定休日チェック**：旅行日の曜日を踏まえ、その日が定休日に当たりそうな店を避けて選ぶ。
- **店・宿の実在チェック**：`GOOGLE_MAPS_API_KEY` 設定時は、グルメ・宿の候補名を生成時に Google Places で実在確認し、LLMが創作した店名を候補から除外する（実在候補が減りすぎる場合は絞り込みを中止して選択肢を保つ）。
- **ハイブリッドモデル**：候補出し・選定・会話抽出は軽量・低コストな `gemini-3.1-flash-lite`、推論の効きどころ（スケジュール作成・費用見積もり・審査）だけ上位の `gemini-3.5-flash`。費用合計の数値ガードで予算超過プランを防止し、構造的に無理な予算は「予算不足」として明示。生成ごとにトークン量と推定コストをログ出力。
- 応答は SSE（Server-Sent Events）でストリーミング。生成中は「考え中（thinking）」を送り続け、途中キャンセルも可能。エラーや通信断はチャットに通知（無反応で止まらない）。
- 完成プランは保存でき、絵本の**「本棚」風の一覧**に並ぶ。表紙をひらくとブックレット風の詳細ページ（`/plan/<id>`）へ移動し、天気・地図・★評価・共有・削除はそこで行う（各セクションは閉じた状態が既定で、全体を見渡してから気になる所だけひらける）。
- **スポットの地図表示**：保存プランに水彩スタイルの地図（Leaflet + Stadia Maps / Stamen Watercolor タイル）を表示。ピンの番号は**スケジュールに登場する順（＝移動する順番）**で、観光（緑・四つ葉アクセント）・グルメ（オレンジ）・宿（青）を横断した通し番号を振り、点線も移動順につなぐ（スケジュールと照合できない旧プランは従来表示に自動フォールバック）。各ピンのポップアップから Google マップの経路ナビへ飛べる。緯度経度は**地図を初めて開いたとき**にジオコーディングしてキャッシュ（`geo_done`）。精度向上のため、目的地周辺を優先（`viewbox`）した上で、表記の正規化（NFKC）→ 括弧注釈・末尾総称を外した再検索 → 「名前, 目的地」での再検索を行い、候補は複数取得して**目的地に最も近いものを採用**（遠すぎる同名別地は棄却）。Nominatim で当たらない地名は**国土地理院の住所検索APIにフォールバック**する（どちらも無料・キー不要）。さらに `GOOGLE_MAPS_API_KEY` を設定すると **Google Places を最優先で使い、OSMに載らない飲食店・宿の名前も高精度に解決**する（任意・月の無料枠内で収まる想定）。共有プランの地図や写真の足あとマップも同じ部品を再利用する。
- **ユーザーによるカスタムピン**：自分のプランの地図をタップして名前・種類（観光/グルメ/宿/メモ）・色を付けたピンを設置でき、ドラッグで移動・削除も可能（Nominatim で見つからない店の補完に便利）。自動で立たなかったスポットは「未配置」チップで一覧表示し、ワンタップ配置できる。ピンは保存（`custom_pins`）され共有閲覧でも表示される。
- **旅行日の天気・カレンダー書き出し**：保存（と共有）プランに旅行日の天気予報ストリップを表示（Open-Meteo・当日〜16日先。座標未取得のプランは目的地名から補完）。「明日」「今週末」などの相対日付もコード側で絶対日付に正規化される。`.ics` カレンダー書き出しは旅行全体の終日イベントに加え、**スケジュール各行を日別の時刻付き予定**として出力（Asia/Tokyo明示・前日リマインダー付き・RFC 5545 準拠）。
- 提示後もチャットで調整可能。「2日目をゆっくりに」「予算を抑えて」「宿を変えて」などで作り直し。**部分編集**にも対応し、指定した領域だけ再生成して他は前回のまま保持する。
- **保存プランもカード上でチャット修正可能**。修正案はまずプレビュー表示し、「更新する」を押したときだけ保存する。
- **★評価による好みの学習**：保存プランを ★1〜5＋ひとことコメントで評価できる（1プラン1評価・上書き式。記録後も「修正」ボタンで再編集でき、誤入力を直せる）。高評価（★4以上）・低評価（★2以下）とコメントを要約し、次回以降のプラン生成に「好み」としてやんわり反映する（明示の要望が最優先／低評価の傾向は避ける）。
- Web 検索（Tavily）で実在性・最新情報を補強。

### 2. 旅の振り返り（付箋）
- 旅（trip）を作成し、写真を複数枚アップロード（GCS またはローカル保存）。HEIC/HEIF はアップロード時に JPEG 変換し、軽量サムネイルを生成（一覧はサムネ、拡大時は原寸）。
- 写真の EXIF から撮影時刻・GPS を抽出し、コード側で特徴量（時間帯の偏り・移動距離・滞在範囲など）に要約。
- 特徴量＋代表写真を Gemini に渡し、付箋を3〜6枚生成。再生成のたびに付け直す。
- 一覧はクラフト台紙の**「トラベルジャーナル」**風。ポラロイド写真とパステルの付箋を旅ごとに左右交互に貼り、検索（かな正規化・複数語AND）・並び替え・お気に入り絞り込みができる。
- 一覧カードの**表紙写真は旅の詳細から自分で選べる**（写真の「表紙」チップ。未選択なら最古の写真）。
- **年間ダイジェスト**：「一年の旅のきろく」ページで、その年の旅を月ごとのミニポラロイド・スタッツ（旅の回数/写真枚数/出発した月）・付箋の「ことばのアルバム」で振り返れる（年切り替え付き）。
- 旅詳細では写真をタップで拡大表示（ライトボックス）。ボタン／キーボード ←→／スワイプで前後の写真へ移動できる。
- **旅の足あとマップ**：GPS（EXIF）を持つ写真を撮影時刻順に並べ、点線で結んで「足あと」として表示する。旅に**保存プランを紐付ける**と、計画した観光スポット（緑）を実際の撮影地（ピンク）に重ねて、計画と実績を見比べられる。
- 旅のタイトルは後から編集可能。旅・写真の削除時はストレージ実体も掃除して孤立ファイルを残さない。

### 3. 共有
- 公開リンク: トークンURL（`/s/<token>`）を知る人が閲覧可能（ログイン不要）。
- メール指定: 指定メールでログインした本人だけが閲覧/編集（`/shared/...`）。
- 権限は `view`（閲覧のみ）/ `edit`（編集可）。旅は写真追加・付箋生成、プランは `edit` のメール共有で受領者がチャット修正（所有者のプランを上書き）できる。公開リンクは安全のため常に閲覧専用。
- 所有者本人は常にフル権限。リンクの取り消しやグラントの削除も可能。
- 共有された側（受領者）も、自分宛の共有を自分の一覧から解除できる（相手の元データは消えない／再共有されれば再表示）。
- 共有された旅・プランは「共有された一覧」だけでなく、アルバム・保存プランにも統合表示される。

### 4. PWA（ホーム画面に追加）
- manifest・アイコン・Service Worker を同梱。スマホのホーム画面に追加すると、ちゃむのアイコンから**アプリとして（ブラウザUIなしで）起動**できる。
- Service Worker はキャッシュを持たない最小構成（SSEストリーミング・OAuth・署名付きURLと衝突しない）。

---

## 環境変数一覧

`src/.env`（ローカル）または Cloud Run の環境変数 / Secret Manager で設定します。秘密情報はコードに直書きせず、必ず環境変数で渡してください。`src/.env` は Git 管理対象外です。

| 変数 | 必須 | 用途 |
|------|------|------|
| `SECRET_KEY` | 本番 | Flask セッション署名鍵 |
| `GOOGLE_API_KEY` | ✓ | Gemini API キー |
| `TAVILY_API_KEY` | ✓ | Tavily Web 検索 |
| `STADIA_API_KEY` | | スポット地図の水彩タイル用 Stadia Maps キー（未設定時は標準 OpenStreetMap タイルにフォールバック） |
| `GOOGLE_MAPS_API_KEY` | | Google Places によるジオコーディング強化（設定時のみ）。OSMに載らない飲食店・宿の名前が地図に立つようになる。未設定なら無料スタック（Nominatim＋地理院）のみ |
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

## ディレクトリ構成

```
tabimate/
├── README.md                 # プロジェクト概要（英語版）
├── README_jp.md              # プロジェクト概要（日本語版）
├── requirements.txt          # Python 依存
├── dockerfile                # ubuntu22.04 + python3.10 + gunicorn
├── deploy.sh                 # Cloud Run デプロイ（Secret/GCS/IAM 設定込み）
├── .github/workflows/ci.yml  # push/PRごとのCI（オフラインテスト・JS構文・テンプレート）
├── scripts/
│   ├── backfill_thumbnails.py # 旧写真のサムネイル一括生成
│   └── setup_alerts.sh       # Cloud Run 5xx のメールアラート作成（1回実行）
├── tests/
│   ├── test_smoke.py         # プラン生成の通し実行スモークテスト
│   └── test_units.py         # APIキー不要のオフラインユニットテスト
└── src/
    ├── .env                  # 環境変数（Git 管理対象外）
    ├── app.py                # Flask アプリ生成・Blueprint 登録
    ├── db.py                 # travel_plans / chat_messages の DAO + 共有エンジン
    ├── db_reflection.py      # trips / photos / stickers ほかの DAO
    ├── db_sharing.py         # 共有リンク/メールグラントの DAO
    ├── geocoding.py          # スポット名→緯度経度（Nominatim・countrycodes=jp・viewbox・フォールバック）。遅延キャッシュ
    ├── weather.py            # 旅行日の天気予報（Open-Meteo）。表示ストリップ＋生成ヒント
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
    ├── templates/            # Jinja2 テンプレート
    │   ├── layout.html, home.html, welcome.html, sidebar.html
    │   ├── saved_plans.html, plan_detail.html
    │   ├── _share_modal.html
    │   └── reflection/
    │       ├── index.html    #  旅一覧（フィード風・付箋バッジ）
    │       └── trip.html     #  旅詳細（付箋ヒーロー・写真・編集/削除）
    │   └── shared/
    │       ├── index.html    #  自分に共有された旅・プラン一覧
    │       ├── trip.html     #  共有旅の詳細（編集可）
    │       └── plan.html     #  共有プランの詳細（閲覧専用）
    └── static/               # CSS / JS / 画像
        ├── css/
        ├── js/
        └── img/
```

---

## アーキテクチャ

```
         ┌──────────── Flask app (app.py) ────────────┐
         │  ProxyFix + 4 Blueprints                   │
         │                                             │
 ブラウザ─┤  planner      ("/")         旅行プラン作成チャット │
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
- **ストレージは抽象化**: `services/storage.py` が GCS とローカル FS を切り替える（`GCS_BUCKET` の有無で判定）。GCS の署名付きURLは**キャッシュ＋並列生成**（`get_urls()`）で写真の多いページの表示を高速化。
- **共有は2方式**: `views/sharing.py` が公開リンク（トークン）とメールグラントを一元管理し、owner / edit / view の権限でアクセス制御する。

---

## 開発環境の構築方法

### 必要環境
- Python 3.10+
- MySQL 8.0（ローカルまたは TiDB Cloud / Cloud SQL のいずれか）
- Docker（オプション：GCS 代替のローカルストレージとして使用）

### セットアップ手順

```bash
# 1. リポジトリをクローン
git clone <repo-url> && cd tabimate/tabimate

# 2. 環境変数ファイルの作成
cp src/.env.example src/.env
# src/.env に以下を設定: SECRET_KEY, GOOGLE_API_KEY, TAVILY_API_KEY,
#   GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET,
#   DB_USER, DB_PASS, DB_NAME, DB_HOST, DB_PORT

# 3. 仮想環境の作成（Python 3.10+ 推奨）
cd src
python3 -m venv .venv
source .venv/bin/activate

# 4. 依存パッケージのインストール
pip install -r ../requirements.txt

# 5. アプリ起動
python3 app.py
```

起動後、`http://localhost:5007`（Flask 開発サーバ）にアクセス。

> **注意**: DB のテーブルは初回アクセス時に `CREATE TABLE IF NOT EXISTS` で自動作成されます（utf8mb4）。

### 本番デプロイ（Cloud Run）

`deploy.sh` が一連の作業を自動化します（`src/.env` を読み込んで使用）。事前に GCP プロジェクトの認証を済ませてください。

```bash
./deploy.sh
```

スクリプトが行うこと:
1. 必要な GCP API を有効化（run / artifactregistry / cloudbuild / secretmanager / storage / iamcredentials）。
2. シークレット（`GOOGLE_API_KEY`, `TAVILY_API_KEY`, `GOOGLE_CLIENT_SECRET`, `DB_PASS`, `SECRET_KEY`, `STADIA_API_KEY`）を Secret Manager に登録/更新し、Cloud Run の SA に閲覧権限を付与。
3. 写真用 GCS バケットを作成し、SA に `objectAdmin` を付与。
4. 署名付きURL のため SA に `serviceAccountTokenCreator`（IAM signBlob）を付与。
5. `gcloud run deploy --source .` でソースデプロイ（リージョン `asia-northeast1`、サービス名、プロジェクトを指定）。

> Cloud Run のデフォルト SA は秘密鍵を持たないため、GCS の署名付きURLは **IAM signBlob 方式**（`service_account_email` + `access_token`）で生成します。

### 現場でよく使うコマンド

```bash
# テスト実行
python tests/test_smoke.py          # 通しスモークテスト
pytest tests/                       # テスト一式

# DB 接続確認（MySQL クライアントがある場合）
mysql -h $DB_HOST -u $DB_USER -p $DB_NAME

# Cloud Run ログ確認
gcloud run services logs tail <サービス名> --region asia-northeast1

# ローカルストレージの掃除
rm -rf src/uploads/*               # ローカル保存写真を全削除
```

---

## データベース設計

| テーブル | 用途 |
|----------|------|
| `travel_plans` | 保存された旅行プラン（条件・成果物を JSON 列で保持）。`spot_coords`/`restaurant_coords`/`accommodation_coords` は地図用の緯度経度キャッシュ、`custom_pins` はユーザー設置ピン、`geo_done` は遅延ジオコーディング実行済みフラグ |
| `chat_messages` | チャット履歴（role/content/request_id）。AIがプランを提示した行には `plan_json`（構造化データ）を併せて保存し、チャット編集時の「前回プラン」として読み戻す |
| `trips` | 旅（タイトル・期間・所有ユーザー）。`linked_plan_id` は足あと重ね合わせ用に保存プランを任意で紐付ける |
| `photos` | アップロード写真（storage_path・撮影時刻・GPS） |
| `stickers` | 付箋（text=表示文・basis=内部の生成根拠） |
| `share_links` | 公開共有リンク（token/resource_type/resource_id/permission） |
| `share_grants` | メール指定共有（grantee_email/resource_type/resource_id/permission） |
| `achievements` | 旧「称号」機能のテーブル（現 UI 未使用・後方互換で残置） |
| `trip_reports` | 旧「AI 旅レポート」機能のテーブル（現 UI 未使用・残置） |

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
| GET | `/plan/<id>` | 保存プランのブックレット風詳細ページ（本人のみ） |
| POST | `/send_message` | 発話を受け取り AI 応答を SSE ストリーミング（要ログイン・レート制限 5回/60秒） |
| POST | `/abort_request` | 生成中リクエストのキャンセル |
| POST | `/reset_chat` | チャット履歴のリセット |
| GET | `/get_messages` | チャット履歴の取得 |
| POST | `/save_plan` | プラン保存 |
| DELETE | `/delete_plan/<id>` | プラン削除 |
| GET | `/get_my_plans` | 自分の保存プラン一覧（JSON） |
| GET | `/get_shared_plans` | 自分宛に共有されたプラン一覧（JSON・保存プラン画面に統合表示） |
| POST | `/edit_saved_plan/<id>` | 保存プランをチャット修正し、修正案を SSE ストリーミング（保存はまだ。所有者または編集権限の受領者） |
| POST | `/apply_saved_plan/<id>` | プレビューした修正を保存（所有者のプランを上書き） |
| POST | `/rate_plan/<id>` | 自分のプランに ★1〜5＋コメントを記録（次回生成の好み反映に利用） |
| POST | `/save_plan_pins/<id>` | ユーザー設置のカスタムピン（名前/種類/色）を検証して保存（本人のみ） |
| GET | `/api/plan_geo/<id>` | 地図用の座標を返す。初回呼び出しでジオコーディングしキャッシュ（本人のみ・geo制限あり） |
| GET | `/api/plan_weather/<id>` | プランの旅行日の天気予報（Open-Meteo・本人のみ・geo制限あり） |
| GET | `/export_plan_ics/<id>` | プランを `.ics`（iCalendar）で書き出し（本人のみ） |
| GET | `/api/geocode` | ジオコーディングのプロキシ（Nominatim・`countrycodes=jp`）。座標未保存の旧プラン用フォールバック（要ログイン・geo制限あり） |

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
| PATCH | `/reflection/trips/<id>/linked-plan` | 旅に保存プランを紐付け／解除（足あと重ね合わせ用） |

### sharing（`/share`） — `views/sharing.py`

| メソッド | パス | 説明 |
|----------|------|------|
| GET | `/share/trip\|plan/<id>` | 共有一覧（モーダル用JSON） |
| POST | `/share/trip\|plan/<id>/link` | 公開リンク作成 |
| DELETE | `/share/link/<id>` | 公開リンク削除 |
| POST | `/share/trip\|plan/<id>/grant` | メール共有の追加 |
| DELETE | `/share/grant/<id>` | メール共有の削除（所有者による取消） |
| DELETE | `/shared/grant/<id>` | 共有された側が自分宛の共有を解除（受領者本人のみ） |
| GET | `/s/<token>` | 公開リンク閲覧（ログイン不要） |
| GET | `/shared` | 自分宛の共有一覧 |
| GET | `/shared/trip\|plan/<id>` | メール共有による閲覧 |
| GET | `/shared/plan/<id>/ics` | 共有プランを `.ics` で書き出し（公開トークン/メール共有の閲覧者） |
| POST | `/shared/trip/<id>/photos` | 共有旅への写真追加 |
| DELETE | `/shared/trip/<id>/photos/<photo_id>` | 共有旅の写真削除 |
| POST | `/shared/trip/<id>/stickers/generate` | 共有旅の付箋生成 |
| DELETE | `/shared/trip/<id>/stickers/<sticker_id>` | 共有旅の付箋削除 |
| DELETE | `/shared/trip/<id>` | 共有旅の削除 |

`reflection` と `sharing` + プラン保存系は `@login_required` で保護。

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
- **予算配分**: 宿泊は残予算の40%、食費は25%が目安上限。
- **交通費が予算超過**なら `transport_agent` が `ValueError` を投げ、ユーザーに「予算超過」を通知して中断。
- **宿泊なし判定**: 共通の `parse_duration()` が期間文字列を（泊数, 日数）に解釈し、泊数 0 なら宿泊ノードをスキップ。「0泊2日」（夜行バス・車中泊）も宿なしのまま、タイムキーパーは日数分の行程を組む。
- **ユーザー要望の反映**: 再プラン時、`user_feedback` を各エージェントのプロンプトに「最優先」で差し込む。
- **時間の希望**: `schedule_pref`（例「夕方までに帰りたい」）をタイムキーパーに最優先制約として注入。日帰りは帰宅時刻から逆算してスケジュールを組む。
- **★評価による好み**: 過去の★評価・コメント（`get_rated_plans`）から `user_preferences` を生成し、観光・宿泊・グルメ・タイムキーパーの各エージェントにやんわり注入。
- **部分編集**: 変更要望から対象領域（`edit_targets`）を判定し、対象ノードだけ再生成（指定外は前回成果物を保持）。前回プランは保存ボタンの `data-plan` から復元。予算に影響する編集（宿・グルメ・交通・費用）は予算/実現性を確認し、超過時は差し戻さず警告で通知する。
- **Web 検索**: `chat/llm.py` の `build_search_context()` が Tavily で公式/ガイド情報を集め、候補抽出の根拠にする（スコア閾値 0.3）。
- **リトライ**: `invoke_with_retry()` がレート制限（429/503）や接続エラーを指数/線形バックオフで最大5回リトライ。

---

## テスト

```bash
python tests/test_smoke.py          # プラン生成の通しスモークテスト
pytest tests/                       # 一式
```

`tests/test_smoke.py` はプラン生成ワークフローを実際に通し実行し、目的地が保持されることと `spots` がリストであることを確認します（Gemini/Tavily の API キーが必要）。

`tests/test_units.py` は **APIキー/DB不要のオフラインテスト**で、純粋関数（サムネイルキー導出・ローカルURL生成/重複集約・パストラバーサル拒否・ジオコーディングの表記ゆらぎ/候補選択）を検証します。

push / PR のたびに **GitHub Actions**（`.github/workflows/ci.yml`）がオフラインテスト・全JSの構文チェック・全テンプレートのコンパイル確認を自動で実行します。

---

## セキュリティ方針

- **秘密情報はコードに直書きしない**。すべて環境変数 / Secret Manager 経由。`src/.env` はコミットしない。
- **セッション堅牢化**: 本番（Cloud Run）で `SECRET_KEY` 未設定なら起動を失敗させる（既知鍵での偽造防止）。Cookie は HttpOnly / SameSite=Lax、本番は Secure。
- **OAuthメール検証**: `email_verified` を確認し、未検証メールのログインを拒否（共有がメール基準のため）。
- **所有権チェック**: 旅・写真・付箋・プラン・共有リンクは常に `user_id` で照合し、他人のデータにアクセスさせない。
- **XSS 対策**: 完成プランの HTML 整形でユーザー由来文字列をすべてエスケープ。
- **パストラバーサル対策**: ローカル写真の読み出し/削除でアップロードディレクトリ外へのアクセスを拒否。
- **レート制限**: チャット送信は 5回/60秒/ユーザー。地図・ジオコーディング・天気など外部APIを叩く系は別枠で約40回/60秒。
- **アップロード制限**: 1リクエスト最大50枚、拡張子ホワイトリスト（拡張子なしは拒否）、リクエストサイズ上限（`MAX_CONTENT_LENGTH`・既定100MB／超過時は413で通知）。
- **セキュリティヘッダ**: 全レスポンスに `X-Content-Type-Options: nosniff` / `X-Frame-Options: SAMEORIGIN` / `Referrer-Policy` を付与。
- **プロキシ信頼**: `ProxyFix` で Cloud Run の forwarded ヘッダのみを信頼し、OAuth コールバック URL を正しいスキーム/ホストで生成。
- **共有リンクの推測困難性**: 十分な長さのランダムトークンを生成し、漏洩リスクを低減。

---

## トラブルシューティング

### .env が見つからない
`src/.env` をルートディレクトリに作成し、上記の環境変数一覧に従って設定してください。

### Docker デーモンが起動していない
```bash
open -a Docker   # macOS
# Docker Desktop の起動を確認してから再実行
```

### MySQL に接続できない
- `DB_HOST` が正しいか確認。接続先が Cloud SQL（`CLOUD_SQL_INSTANCE` 指定）場合はローカル MySQL ホスト名ではなくインスタンス接続名を使用する。
- `DB_SSL=true` が必要な環境（TiDB Cloud 等）では `DB_SSL_CA` も設定してください。

### SIGTERM が頻発する（Cloud Run）
- `deploy.sh` は `--timeout=3600`（gunicorn も 3600 秒）を設定しており、長期旅行のプラン生成（数分〜十数分）でも切れない構成です。手動でデプロイした環境で短い場合は `gcloud run services update <サービス名> --timeout=3600` で延長してください。
- あわせて `--concurrency=20`（gunicorn のスレッド数と一致）と `--max-instances=3`（コスト上限）を設定しています。
- 生成を途中でやめたい場合は、生成中の `abort_request` でクライアント側から明示的にキャンセルする設計になっています。

### 写真の表示が遅い
GCS の署名付きURLは写真ごとに IAM signBlob を呼ぶため、枚数が多いと遅くなります（CPU/メモリ増強では解消しません）。現在は `services/storage.py` の `get_urls()` で**キャッシュ＋並列生成**し、一覧では**サムネイル**を配信（原寸は拡大時のみ）して短縮しています。サムネイル導入前の写真は `scripts/backfill_thumbnails.py` で一括生成できます。コールドスタートをさらに抑えるなら Cloud Run の最小インスタンス1も検討してください。

### Tavily 検索が「string が返ってきた」エラー
検索結果の型が不定（`list` ではなく `str` で返る）ことがあります。`chat/llm.py` の `build_search_context()` で `if not isinstance(results, list)` のガードが入っているか確認してください。過去プロジェクトで同様の `AttributeError`（`.get()` が `str` で使えない）が発生しています。
