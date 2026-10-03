#!/bin/bash
set -e

PROJECT_ID="august-bot-462013-g2"
SERVICE_NAME="kabu-app"
REGION="asia-northeast1"
# 振り返り機能の写真保存先（Cloud Storage バケット）
GCS_BUCKET="${GCS_BUCKET:-kabu-trip-photos}"

source "$(dirname "$0")/src/.env"

echo "=== APIを有効化 ==="
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com \
  storage.googleapis.com \
  iamcredentials.googleapis.com \
  places.googleapis.com \
  slides.googleapis.com \
  --project "$PROJECT_ID"

# Cloud Run がデフォルトで使うサービスアカウント（Compute SA）
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" \
  --format="value(projectNumber)" --project "$PROJECT_ID")
SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

echo "=== 必須キーの事前チェック ==="
# 必須キーが .env に無いまま進めると「空のSecretで全機能が静かに無効」になるため止める
for req in GOOGLE_API_KEY TAVILY_API_KEY GOOGLE_CLIENT_SECRET DB_PASS SECRET_KEY; do
  if [ -z "${!req}" ]; then
    echo "ERROR: ${req} が src/.env にありません。設定してから再実行してください。" >&2
    exit 1
  fi
done

echo "=== Secret Manager にシークレットを登録/更新 ==="
# Secret Manager は「有効な版（version）」の数で毎月課金される。
# 以前はデプロイのたびに、値が同じでも全シークレットに新しい版を足し、
# 古い版を一度も消していなかった。デプロイ1回で5〜7版ずつ増え、
# 積み上がった版の保管料が請求の最大項目になっていた。
#   ・値が変わっていなければ版を足さない
#   ・足したあとは、最新 KEEP_SECRET_VERSIONS 個だけ残して古い版を破棄する
# 1つ前を残すのは、.env の書き間違いで壊れたときに戻せるようにするため。
KEEP_SECRET_VERSIONS="${KEEP_SECRET_VERSIONS:-2}"

# 古い版を破棄して、有効な版を最新 KEEP_SECRET_VERSIONS 個に絞る。
# 破棄（destroy）は取り消せない。無効化（disable）では保管が続くので課金も止まらない。
# Cloud Run は :latest を参照しているので、古い版を消しても動作には影響しない。
_prune_secret_versions() {
  local name=$1
  local old
  old=$(gcloud secrets versions list "$name" --project "$PROJECT_ID" \
          --filter="state!=DESTROYED" --sort-by="~createTime" \
          --format="value(name.basename())" | tail -n +"$((KEEP_SECRET_VERSIONS + 1))")
  [ -z "$old" ] && return
  local count
  count=$(printf '%s\n' "$old" | wc -l | tr -d ' ')
  echo "・${name}: 古い版を ${count} 個破棄します（最新 ${KEEP_SECRET_VERSIONS} 個は残す）"
  printf '%s\n' "$old" | while read -r version; do
    gcloud secrets versions destroy "$version" --secret="$name" \
      --project "$PROJECT_ID" --quiet >/dev/null
  done
}

_upsert_secret() {
  local name=$1
  local value=$2
  # 空値の扱い: 既存Secretは上書きしない（値を消す事故防止）。
  # 未作成なら空で作るが警告する（--set-secrets が参照するため存在は必要）。
  if [ -z "$value" ]; then
    if gcloud secrets describe "$name" --project "$PROJECT_ID" &>/dev/null; then
      echo "⚠ ${name} は .env に無いため、既存のSecretの値をそのまま使います"
      _prune_secret_versions "$name"
      return
    fi
    echo "⚠ ${name} は空のSecretとして作成されます。使うときは .env に値を書いて再デプロイしてください"
  fi
  # printf を使うことで改行・特殊文字を安全に扱う
  if gcloud secrets describe "$name" --project "$PROJECT_ID" &>/dev/null; then
    local current
    current=$(gcloud secrets versions access latest --secret="$name" \
                --project "$PROJECT_ID" 2>/dev/null || true)
    if [ "$current" = "$value" ]; then
      echo "・${name} は変更なし（新しい版は作りません）"
    else
      printf '%s' "$value" | gcloud secrets versions add "$name" \
        --data-file=- --project "$PROJECT_ID"
    fi
    # 変更が無くても毎回絞る。以前のデプロイで積み上がった版もここで片付く
    _prune_secret_versions "$name"
  else
    printf '%s' "$value" | gcloud secrets create "$name" \
      --data-file=- --replication-policy=automatic --project "$PROJECT_ID"
  fi
}

_upsert_secret "GOOGLE_API_KEY"       "$GOOGLE_API_KEY"
_upsert_secret "TAVILY_API_KEY"       "$TAVILY_API_KEY"
_upsert_secret "GOOGLE_CLIENT_SECRET" "$GOOGLE_CLIENT_SECRET"
_upsert_secret "DB_PASS"              "$DB_PASS"
_upsert_secret "SECRET_KEY"           "$SECRET_KEY"
_upsert_secret "STADIA_API_KEY"       "$STADIA_API_KEY"
# 任意: Google Places によるジオコーディング強化（未設定なら空でよい）
_upsert_secret "GOOGLE_MAPS_API_KEY"  "$GOOGLE_MAPS_API_KEY"

echo "=== Cloud Run サービスアカウントに Secret Manager アクセス権を付与 ==="
for secret in GOOGLE_API_KEY TAVILY_API_KEY GOOGLE_CLIENT_SECRET DB_PASS SECRET_KEY STADIA_API_KEY GOOGLE_MAPS_API_KEY; do
  gcloud secrets add-iam-policy-binding "$secret" \
    --member="serviceAccount:${SA}" \
    --role="roles/secretmanager.secretAccessor" \
    --project "$PROJECT_ID" 2>/dev/null || true
done

echo "=== 写真用 Cloud Storage バケットを作成/確認 ==="
if ! gcloud storage buckets describe "gs://${GCS_BUCKET}" --project "$PROJECT_ID" &>/dev/null; then
  gcloud storage buckets create "gs://${GCS_BUCKET}" \
    --location="$REGION" \
    --uniform-bucket-level-access \
    --project "$PROJECT_ID"
fi

echo "=== バケットへの読み書き権限を付与 ==="
gcloud storage buckets add-iam-policy-binding "gs://${GCS_BUCKET}" \
  --member="serviceAccount:${SA}" \
  --role="roles/storage.objectAdmin" \
  --project "$PROJECT_ID"

echo "=== 署名付きURL生成（IAM signBlob）権限を付与 ==="
# Cloud Run のデフォルトSAは秘密鍵を持たないため、自分自身に対する
# serviceAccountTokenCreator 権限で signBlob 署名を行う。
gcloud iam service-accounts add-iam-policy-binding "$SA" \
  --member="serviceAccount:${SA}" \
  --role="roles/iam.serviceAccountTokenCreator" \
  --project "$PROJECT_ID"

echo "=== Cloud Run にデプロイ ==="
gcloud run deploy "$SERVICE_NAME" \
  --source . \
  --region "$REGION" \
  --platform managed \
  --allow-unauthenticated \
  --timeout=3600 \
  --concurrency=20 \
  --max-instances=3 \
  --set-env-vars "DB_HOST=${DB_HOST},DB_PORT=${DB_PORT},DB_USER=${DB_USER},DB_NAME=${DB_NAME},DB_SSL=true,GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID},GCS_BUCKET=${GCS_BUCKET}" \
  --set-secrets "GOOGLE_API_KEY=GOOGLE_API_KEY:latest,TAVILY_API_KEY=TAVILY_API_KEY:latest,GOOGLE_CLIENT_SECRET=GOOGLE_CLIENT_SECRET:latest,DB_PASS=DB_PASS:latest,SECRET_KEY=SECRET_KEY:latest,STADIA_API_KEY=STADIA_API_KEY:latest,GOOGLE_MAPS_API_KEY=GOOGLE_MAPS_API_KEY:latest" \
  --project "$PROJECT_ID"

echo "=== Artifact Registry の古いイメージを自動削除する設定 ==="
# --source デプロイはビルドしたコンテナイメージを cloud-run-source-deploy に置く。
# 何もしないとデプロイのたびに数百MBずつ積み上がり、保管料が毎日かかる。
# 最新 KEEP_IMAGES 個だけ残し、それより古いものは削除するポリシーを付ける。
# （Keep は Delete より優先される。削除はポリシーに従って1日1回ほどまとめて行われる）
# 動いているリビジョンは最新のイメージを使っているので、古いものを消しても影響はない。
# 古いリビジョンへの切り戻しは、残した KEEP_IMAGES 個の範囲でだけできる。
KEEP_IMAGES="${KEEP_IMAGES:-3}"
AR_REPO="cloud-run-source-deploy"
if gcloud artifacts repositories describe "$AR_REPO" \
     --location "$REGION" --project "$PROJECT_ID" &>/dev/null; then
  POLICY_FILE=$(mktemp)
  cat > "$POLICY_FILE" <<JSON
[
  {"name": "keep-recent", "action": {"type": "Keep"},
   "mostRecentVersions": {"keepCount": ${KEEP_IMAGES}}},
  {"name": "delete-old", "action": {"type": "Delete"},
   "condition": {"tagState": "any", "olderThan": "1d"}}
]
JSON
  gcloud artifacts repositories set-cleanup-policies "$AR_REPO" \
    --location "$REGION" --project "$PROJECT_ID" \
    --policy="$POLICY_FILE" --no-dry-run --quiet >/dev/null
  rm -f "$POLICY_FILE"
  echo "・${AR_REPO}: 最新 ${KEEP_IMAGES} 個を残して古いイメージを自動削除します"
fi

echo "=== ビルド用にアップロードしたソースの自動削除設定 ==="
# --source デプロイはソース一式を固めて Cloud Storage に置いてからビルドする。
# ビルドが終われば不要だが、そのまま残り続けて保管料がかかる。
# 置き場所は gcloud のバージョンで違う（新: run-sources-<PJ>-<REGION> / 旧: <PJ>_cloudbuild）
# ので、存在する方に「SOURCE_TTL_DAYS 日より古いファイルは消す」ルールを付ける。
# 写真用バケット（GCS_BUCKET）はユーザーのデータなので対象にしない。
SOURCE_TTL_DAYS="${SOURCE_TTL_DAYS:-7}"
LIFECYCLE_FILE=$(mktemp)
cat > "$LIFECYCLE_FILE" <<JSON
{"rule": [{"action": {"type": "Delete"}, "condition": {"age": ${SOURCE_TTL_DAYS}}}]}
JSON
for src_bucket in "run-sources-${PROJECT_ID}-${REGION}" "${PROJECT_ID}_cloudbuild"; do
  if gcloud storage buckets describe "gs://${src_bucket}" --project "$PROJECT_ID" &>/dev/null; then
    gcloud storage buckets update "gs://${src_bucket}" \
      --lifecycle-file="$LIFECYCLE_FILE" --project "$PROJECT_ID" >/dev/null
    echo "・gs://${src_bucket}: ${SOURCE_TTL_DAYS} 日より古いソースを自動削除します"
  fi
done
rm -f "$LIFECYCLE_FILE"

echo "=== 古い Cloud Run リビジョンを削除 ==="
# デプロイごとにリビジョンが1つ増える。料金はかからないが、上で古いイメージを
# 消すと中身の無いリビジョンが残るだけなので、イメージと同じ数だけ残して消す。
# いまトラフィックを受けているリビジョンは Cloud Run 側が削除を拒否するので安全。
old_revisions=$(gcloud run revisions list --service "$SERVICE_NAME" \
                  --region "$REGION" --project "$PROJECT_ID" \
                  --sort-by="~metadata.creationTimestamp" \
                  --format="value(metadata.name)" | tail -n +"$((KEEP_IMAGES + 1))")
if [ -n "$old_revisions" ]; then
  echo "・古いリビジョンを $(printf '%s\n' "$old_revisions" | wc -l | tr -d ' ') 個削除します（最新 ${KEEP_IMAGES} 個は残す）"
  printf '%s\n' "$old_revisions" | while read -r rev; do
    gcloud run revisions delete "$rev" --region "$REGION" \
      --project "$PROJECT_ID" --quiet >/dev/null 2>&1 || true
  done
fi

echo "=== デプロイ完了 ==="
gcloud run services describe "$SERVICE_NAME" \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --format="value(status.url)"
