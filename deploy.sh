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
  --project "$PROJECT_ID"

# Cloud Run がデフォルトで使うサービスアカウント（Compute SA）
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" \
  --format="value(projectNumber)" --project "$PROJECT_ID")
SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

echo "=== Secret Manager にシークレットを登録/更新 ==="
_upsert_secret() {
  local name=$1
  local value=$2
  # printf を使うことで改行・特殊文字を安全に扱う
  if gcloud secrets describe "$name" --project "$PROJECT_ID" &>/dev/null; then
    printf '%s' "$value" | gcloud secrets versions add "$name" \
      --data-file=- --project "$PROJECT_ID"
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

echo "=== Cloud Run サービスアカウントに Secret Manager アクセス権を付与 ==="
for secret in GOOGLE_API_KEY TAVILY_API_KEY GOOGLE_CLIENT_SECRET DB_PASS SECRET_KEY STADIA_API_KEY; do
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
  --timeout=600 \
  --set-env-vars "DB_HOST=${DB_HOST},DB_PORT=${DB_PORT},DB_USER=${DB_USER},DB_NAME=${DB_NAME},DB_SSL=true,GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID},GCS_BUCKET=${GCS_BUCKET}" \
  --set-secrets "GOOGLE_API_KEY=GOOGLE_API_KEY:latest,TAVILY_API_KEY=TAVILY_API_KEY:latest,GOOGLE_CLIENT_SECRET=GOOGLE_CLIENT_SECRET:latest,DB_PASS=DB_PASS:latest,SECRET_KEY=SECRET_KEY:latest,STADIA_API_KEY=STADIA_API_KEY:latest" \
  --project "$PROJECT_ID"

echo "=== デプロイ完了 ==="
gcloud run services describe "$SERVICE_NAME" \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --format="value(status.url)"
