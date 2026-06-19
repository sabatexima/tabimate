#!/bin/bash
set -e

PROJECT_ID="august-bot-462013-g2"
SERVICE_NAME="kabu-app"
REGION="asia-northeast1"

source "$(dirname "$0")/src/.env"

echo "=== APIを有効化 ==="
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com \
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

echo "=== Cloud Run サービスアカウントに Secret Manager アクセス権を付与 ==="
for secret in GOOGLE_API_KEY TAVILY_API_KEY GOOGLE_CLIENT_SECRET DB_PASS SECRET_KEY; do
  gcloud secrets add-iam-policy-binding "$secret" \
    --member="serviceAccount:${SA}" \
    --role="roles/secretmanager.secretAccessor" \
    --project "$PROJECT_ID" 2>/dev/null || true
done

echo "=== Cloud Run にデプロイ ==="
gcloud run deploy "$SERVICE_NAME" \
  --source . \
  --region "$REGION" \
  --platform managed \
  --allow-unauthenticated \
  --add-cloudsql-instances "${PROJECT_ID}:${REGION}:kabu-db" \
  --set-env-vars "CLOUD_SQL_INSTANCE=${PROJECT_ID}:${REGION}:kabu-db,DB_USER=${DB_USER},DB_NAME=${DB_NAME},GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID}" \
  --set-secrets "GOOGLE_API_KEY=GOOGLE_API_KEY:latest,TAVILY_API_KEY=TAVILY_API_KEY:latest,GOOGLE_CLIENT_SECRET=GOOGLE_CLIENT_SECRET:latest,DB_PASS=DB_PASS:latest,SECRET_KEY=SECRET_KEY:latest" \
  --project "$PROJECT_ID"

echo "=== デプロイ完了 ==="
gcloud run services describe "$SERVICE_NAME" \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --format="value(status.url)"
