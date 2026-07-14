#!/bin/bash
# Cloud Run のエラーを検知してメール通知するアラートを作成する（1回実行すればOK）。
#
# 作成されるもの:
#   1. メール通知チャンネル（ALERT_EMAIL 宛）
#   2. アラートポリシー: 5xxレスポンスが 5分間で 3件 を超えたら通知
#
# 使い方:
#   ALERT_EMAIL=you@example.com ./scripts/setup_alerts.sh
#
# 前提: gcloud にログイン済みで、プロジェクトへの Monitoring 編集権限があること。
set -e

PROJECT_ID="august-bot-462013-g2"
SERVICE_NAME="kabu-app"

if [ -z "$ALERT_EMAIL" ]; then
  echo "使い方: ALERT_EMAIL=you@example.com $0" >&2
  exit 1
fi

echo "=== 通知チャンネル（メール: $ALERT_EMAIL）を作成 ==="
# 既に同じメールのチャンネルがあれば再利用する（冪等）
CHANNEL=$(gcloud beta monitoring channels list --project "$PROJECT_ID" \
  --filter="type=email AND labels.email_address=$ALERT_EMAIL" \
  --format="value(name)" | head -1)
if [ -z "$CHANNEL" ]; then
  CHANNEL=$(gcloud beta monitoring channels create \
    --display-name="tabimate alerts ($ALERT_EMAIL)" \
    --type=email \
    --channel-labels="email_address=$ALERT_EMAIL" \
    --project "$PROJECT_ID" \
    --format="value(name)")
  echo "作成: $CHANNEL"
else
  echo "既存を再利用: $CHANNEL"
fi

echo "=== アラートポリシー（Cloud Run 5xx）を作成 ==="
# 既に同名ポリシーがあれば何もしない（冪等）
EXISTING=$(gcloud alpha monitoring policies list --project "$PROJECT_ID" \
  --filter="displayName='tabimate: Cloud Run 5xx errors'" \
  --format="value(name)" | head -1)
if [ -n "$EXISTING" ]; then
  echo "既に存在します: $EXISTING（変更する場合はコンソールから編集してください）"
  exit 0
fi

POLICY_FILE=$(mktemp)
cat > "$POLICY_FILE" <<JSON
{
  "displayName": "tabimate: Cloud Run 5xx errors",
  "documentation": {
    "content": "たびメイト（Cloud Run: ${SERVICE_NAME}）で 5xx エラーが増えています。\\n\\n確認: gcloud run services logs tail ${SERVICE_NAME} --region asia-northeast1",
    "mimeType": "text/markdown"
  },
  "combiner": "OR",
  "conditions": [
    {
      "displayName": "5xx responses > 3 / 5min",
      "conditionThreshold": {
        "filter": "resource.type = \\"cloud_run_revision\\" AND resource.labels.service_name = \\"${SERVICE_NAME}\\" AND metric.type = \\"run.googleapis.com/request_count\\" AND metric.labels.response_code_class = \\"5xx\\"",
        "aggregations": [
          {
            "alignmentPeriod": "300s",
            "perSeriesAligner": "ALIGN_SUM",
            "crossSeriesReducer": "REDUCE_SUM"
          }
        ],
        "comparison": "COMPARISON_GT",
        "thresholdValue": 3,
        "duration": "0s",
        "trigger": { "count": 1 }
      }
    }
  ],
  "alertStrategy": {
    "autoClose": "86400s",
    "notificationRateLimit": { "period": "3600s" }
  },
  "notificationChannels": ["${CHANNEL}"]
}
JSON

gcloud alpha monitoring policies create \
  --policy-from-file="$POLICY_FILE" \
  --project "$PROJECT_ID"
rm -f "$POLICY_FILE"

echo ""
echo "完了。5分間に5xxが3件を超えると ${ALERT_EMAIL} にメールが届きます。"
echo "（届いたら: gcloud run services logs tail ${SERVICE_NAME} --region asia-northeast1 で原因確認）"
