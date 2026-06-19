# たびメイト

AIエージェントが協力して旅行プランを自動生成するWebアプリ。チャット形式で旅行条件を入力するだけで、交通・観光・グルメ・宿泊を含む詳細な旅程を提案します。旅の振り返り機能（写真アップロード・謎アチーブメント・AIレポート）も備えています。

---

## 主な機能

### プランナー（旅行プラン生成チャット）
- 出発地・目的地・日程・テーマ・予算・人数・特別条件を入力
- 複数のAIエージェントが並列・逐次で分担してプランを生成
  - **交通エージェント** — 往復交通費を試算し残予算を算出
  - **観光エキスパート** — Webを検索してスポットを候補抽出 → 選定
  - **宿泊エージェント** — 予算内の宿泊施設を候補抽出 → 選定
  - **グルメハンター** — スポット周辺の飲食店を候補抽出 → 選定
  - **タイムキーパー** — 営業時間・移動時間を考慮したスケジュール作成
  - **料金マネージャー** — 日別費用の見積もり作成
  - **バランサー** — プラン全体を審査し、問題があれば差し戻し（最大5回）
- SSE（Server-Sent Events）によるストリーミング応答

### 旅の振り返り
- 写真アップロード（EXIF から撮影日時・位置情報を抽出）
- **謎アチーブメント** — 旅の行動パターンからAIが称号を生成（取得条件は非公開）
- **AIレポート** — トーン・エリアを選んで旅の文章レポートを自動生成

### 認証
- Google OAuth 2.0 によるログイン

---

## 技術スタック

| 分類 | 採用技術 |
|---|---|
| Webフレームワーク | Flask + Gunicorn |
| AI オーケストレーション | LangGraph / LangChain |
| LLM | Google Gemini 2.5 Flash |
| Web 検索 | Tavily Search |
| データベース | MySQL 8.0 |
| ストレージ（本番） | Google Cloud Storage |
| キャッシュ（本番） | Redis |
| コンテナ | Docker / Docker Compose |
| 認証 | Google OAuth 2.0（Authlib） |

---

## セットアップ

### 前提条件

- Docker / Docker Compose
- Python 3.11+（ローカル開発の場合）
- 以下の APIキー・認証情報
  - `GOOGLE_API_KEY` — Gemini API
  - `TAVILY_API_KEY` — Tavily Web 検索
  - `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` — Google OAuth

### 環境変数

`src/.env` を作成して以下を設定してください。

```env
GOOGLE_API_KEY=your_gemini_api_key
TAVILY_API_KEY=your_tavily_api_key
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
SECRET_KEY=your_flask_secret_key

# DB（Docker Compose を使う場合はデフォルトのままでOK）
DB_HOST=db
DB_PORT=3306
DB_NAME=travel_db
DB_USER=kabu-user
DB_PASS=kabu-pass-2025

# 本番のみ
# REDIS_URL=redis://...
# GCS_BUCKET=your_bucket_name
```

### Docker で起動（推奨）

```bash
# 初回（イメージのビルドから）
./start.sh build

# 2回目以降
./start.sh
```

アプリは http://localhost:5007 で起動します。

### ローカルで起動

```bash
pip install -r requirements.txt
cd src
python app.py
```

---

## プロジェクト構成

```
tabimate/
├── src/
│   ├── app.py                 # Flask アプリ本体・Blueprint 登録
│   ├── db.py                  # プランナー用 DB 操作
│   ├── db_reflection.py       # 振り返り機能用 DB 操作
│   ├── chat/
│   │   ├── agents.py          # LangGraph ノード（各エージェント）
│   │   ├── chat.py            # チャット会話管理
│   │   ├── formatter.py       # AI 応答のフォーマット
│   │   ├── graph.py           # LangGraph ワークフロー定義
│   │   ├── llm.py             # LLM クライアント・Web 検索
│   │   ├── logger.py          # ロガー設定
│   │   └── models.py          # Pydantic モデル（State・出力型）
│   ├── services/
│   │   ├── exif.py            # 写真 EXIF メタデータ抽出
│   │   ├── features.py        # 写真メタデータの集計・特徴量化
│   │   ├── storage.py         # GCS / ローカル FS ストレージ抽象
│   │   └── trip_interpreter.py # AI 称号・レポート生成
│   ├── views/
│   │   ├── auth.py            # Google OAuth ログイン
│   │   ├── planner.py         # プランナー API・画面
│   │   └── reflection.py      # 振り返り API・画面
│   └── templates/             # Jinja2 HTML テンプレート
├── docker-mysql/              # MySQL 初期化スクリプト・設定
├── docker-compose.yml
├── dockerfile
├── requirements.txt
└── start.sh
```

---

## エージェントのワークフロー

```
START
  └─ transport（交通費試算）
      └─ sightseeing_candidates（観光候補抽出）
          └─ sightseeing（観光スポット選定）
              └─ accommodation_candidates（宿泊候補抽出）
                  └─ accommodation（宿泊施設選定）
                      └─ gourmet_candidates（飲食店候補抽出）
                          └─ gourmet（飲食店選定）
                              └─ timekeeper（スケジュール作成）
                                  └─ cost_manager（費用見積もり）
                                      └─ balancer（プラン審査）
                                            ├─ approved  → END
                                            ├─ budget_infeasible → END
                                            └─ fix_*     → 対象ノードへ差し戻し（最大5回）
```

---

## テスト

```bash
pytest tests/
```
