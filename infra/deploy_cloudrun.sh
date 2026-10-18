#!/usr/bin/env bash
# Simplest deploy: ONE Cloud Run service serving the web app + API at one public URL.
# The ADK root-cause agent runs in-process. Login = demo token (give it to judges).
#   PROJECT=my-proj ./infra/push_secrets.sh                 # once: .env -> Secret Manager
#   PROJECT=my-proj ./infra/deploy_cloudrun.sh        # us-central1 (cheapest tier); REGION=... to change
# The YOLO weights (models/best.pt) are baked into the image. To use other weights, set
#   YOLO_WEIGHTS=gs://... YOLO_LABEL_COUNTS='{"IMP-200":5639}'   (single quotes keep the JSON intact)
# Prereqs: gcloud auth login; billing enabled. Every secret comes from Secret Manager, never from
# env vars or the image: SENPAIQC_GEMINI_API_KEY and SENPAIQC_DEMO_TOKEN (infra/push_secrets.sh).
# Override the names with GEMINI_SECRET / TOKEN_SECRET.
set -euo pipefail
: "${PROJECT:?set PROJECT}"
REGION="${REGION:-us-central1}"
# Storage, Firestore and BigQuery locations cannot change after creation, so each region gets its own.
SUFFIX="${SUFFIX:-us}"
BUCKET="${BUCKET:-$PROJECT-senpaiqc-$SUFFIX}"
FIRESTORE_DB="${FIRESTORE_DB:-senpaiqc-$SUFFIX}"
BQ_DATASET="${BQ_DATASET:-senpaiqc_$SUFFIX}"
SA="senpaiqc-api@$PROJECT.iam.gserviceaccount.com"
GEMINI_SECRET="${GEMINI_SECRET:-SENPAIQC_GEMINI_API_KEY}"
TOKEN_SECRET="${TOKEN_SECRET:-SENPAIQC_DEMO_TOKEN}"
MAX_INSTANCES="${MAX_INSTANCES:-2}"  # caps cost: worst case MAX_INSTANCES x AI_CALLS_PER_DAY Gemini calls a day
cd "$(dirname "$0")/.."

gcloud config set project "$PROJECT"
gcloud services enable aiplatform.googleapis.com run.googleapis.com firestore.googleapis.com storage.googleapis.com \
  bigquery.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com cloudbuild.googleapis.com \
  pubsub.googleapis.com

gcloud storage buckets describe "gs://$BUCKET" >/dev/null 2>&1 || \
  gcloud storage buckets create "gs://$BUCKET" --location "$REGION" --uniform-bucket-level-access
gcloud firestore databases describe --database "$FIRESTORE_DB" >/dev/null 2>&1 || \
  gcloud firestore databases create --database "$FIRESTORE_DB" --location "$REGION" --type firestore-native

gcloud iam service-accounts describe "$SA" >/dev/null 2>&1 || gcloud iam service-accounts create senpaiqc-api
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" --member "serviceAccount:$SA" --role roles/storage.objectAdmin
gcloud projects add-iam-policy-binding "$PROJECT" --member "serviceAccount:$SA" --role roles/datastore.user --condition None
gcloud projects add-iam-policy-binding "$PROJECT" --member "serviceAccount:$SA" --role roles/bigquery.jobUser --condition None
# Gemini on Vertex AI: billed to this project, called with the service account (no API key needed).
gcloud projects add-iam-policy-binding "$PROJECT" --member "serviceAccount:$SA" --role roles/aiplatform.user --condition None
# BigQuery dataset + table, and write access for the service account on that dataset only.
# Python client instead of the bq CLI (which breaks on some gcloud installs).
python infra/bq_setup.py "$PROJECT" "$REGION" "$SA" "$BQ_DATASET"
# Large expert videos go browser -> Cloud Storage with a signed URL (Cloud Run caps requests at
# 32 MiB). The service account signs URLs via IAM signBlob, and the bucket must accept the PUT.
gcloud iam service-accounts add-iam-policy-binding "$SA" --member "serviceAccount:$SA" --role roles/iam.serviceAccountTokenCreator
CORS_FILE="$(mktemp)"
printf '[{"origin":["*"],"method":["PUT"],"responseHeader":["Content-Type","x-goog-content-length-range"],"maxAgeSeconds":3600}]' > "$CORS_FILE"
gcloud storage buckets update "gs://$BUCKET" --cors-file="$CORS_FILE"
rm -f "$CORS_FILE"
gcloud services enable iamcredentials.googleapis.com
# Read access to exactly these two secrets, nothing else in the project.
for secret in "$GEMINI_SECRET" "$TOKEN_SECRET"; do
  gcloud secrets describe "$secret" >/dev/null 2>&1 || { echo "Secret $secret not found: run PROJECT=$PROJECT ./infra/push_secrets.sh"; exit 1; }
  gcloud secrets add-iam-policy-binding "$secret" --member "serviceAccount:$SA" --role roles/secretmanager.secretAccessor >/dev/null
done
SECRETS="GEMINI_API_KEY=$GEMINI_SECRET:latest,DEMO_TOKEN=$TOKEN_SECRET:latest"
# Optional alert channels, mapped only if infra/push_secrets.sh stored them.
for key in TELEGRAM_BOT_TOKEN TELEGRAM_CHAT_ID GOOGLE_CHAT_WEBHOOK; do
  if gcloud secrets describe "SENPAIQC_$key" >/dev/null 2>&1; then
    gcloud secrets add-iam-policy-binding "SENPAIQC_$key" --member "serviceAccount:$SA" --role roles/secretmanager.secretAccessor >/dev/null
    SECRETS="$SECRETS,$key=SENPAIQC_$key:latest"
  fi
done

# Spike alerts: the app publishes to a topic; a push subscription (created after the deploy) calls
# back /api/alerts/push with an OIDC token signed as the service account, and retries on failure.
TOPIC="${ALERT_TOPIC:-senpaiqc-alerts}"
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT" --format 'value(projectNumber)')
APP_URL="https://senpaiqc-$PROJECT_NUMBER.$REGION.run.app"
PUSH_URL="$APP_URL/api/alerts/push"
gcloud pubsub topics describe "$TOPIC" >/dev/null 2>&1 || gcloud pubsub topics create "$TOPIC" --labels app=senpaiqc
gcloud pubsub topics add-iam-policy-binding "$TOPIC" --member "serviceAccount:$SA" --role roles/pubsub.publisher >/dev/null
gcloud iam service-accounts add-iam-policy-binding "$SA" --role roles/iam.serviceAccountTokenCreator \
  --member "serviceAccount:service-$PROJECT_NUMBER@gcp-sa-pubsub.iam.gserviceaccount.com" >/dev/null

cp infra/api.Dockerfile Dockerfile
trap 'rm -f Dockerfile' EXIT
# "^|^" makes | the separator, so values may contain commas (JSON label counts) and @ (emails).
ENV_VARS="^|^BACKEND=gcp|GCP_PROJECT=$PROJECT|GCS_BUCKET=$BUCKET|BQ_DATASET=$BQ_DATASET|FIRESTORE_DATABASE=$FIRESTORE_DB|AUTH_MODE=demo|USE_VERTEX=${USE_VERTEX:-true}|VERTEX_LOCATION=${VERTEX_LOCATION:-global}|TEXT_MODEL=${TEXT_MODEL:-gemini-3.5-flash-lite}|TEXT_PRICE_IN=${TEXT_PRICE_IN:-0.30}|TEXT_PRICE_OUT=${TEXT_PRICE_OUT:-2.50}|ROBOT_MODE=${ROBOT_MODE:-true}|ALERT_TOPIC=$TOPIC|ALERT_PUSH_AUDIENCE=$PUSH_URL|ALERT_PUSH_SA=$SA|APP_URL=$APP_URL"
[ -n "${YOLO_WEIGHTS:-}" ] && ENV_VARS="$ENV_VARS|YOLO_WEIGHTS=$YOLO_WEIGHTS"
[ -n "${YOLO_LABEL_COUNTS:-}" ] && ENV_VARS="$ENV_VARS|YOLO_LABEL_COUNTS=$YOLO_LABEL_COUNTS"
gcloud run deploy senpaiqc --source . --region "$REGION" --service-account "$SA" \
  --allow-unauthenticated --memory 2Gi --cpu 2 --cpu-boost --timeout 900 \
  --min-instances 0 --max-instances "$MAX_INSTANCES" --concurrency 20 \
  --set-env-vars "$ENV_VARS" \
  --set-secrets "$SECRETS"

SUB="$TOPIC-push"
if gcloud pubsub subscriptions describe "$SUB" >/dev/null 2>&1; then
  gcloud pubsub subscriptions modify-push-config "$SUB" --push-endpoint "$PUSH_URL" \
    --push-auth-service-account "$SA" --push-auth-token-audience "$PUSH_URL"
else
  gcloud pubsub subscriptions create "$SUB" --topic "$TOPIC" --push-endpoint "$PUSH_URL" \
    --push-auth-service-account "$SA" --push-auth-token-audience "$PUSH_URL" \
    --ack-deadline 30 --min-retry-delay 10s --max-retry-delay 600s --message-retention-duration 1d \
    --labels app=senpaiqc
fi

URL=$(gcloud run services describe senpaiqc --region "$REGION" --format 'value(status.url)')
echo "Deployed: $URL"
echo "Judges' token: gcloud secrets versions access latest --secret $TOKEN_SECRET --project $PROJECT"
echo "Seed demo data once (from your machine):"
echo "  python data/generate_process.py && BACKEND=gcp GCP_PROJECT=$PROJECT GCS_BUCKET=$BUCKET BQ_DATASET=$BQ_DATASET FIRESTORE_DATABASE=$FIRESTORE_DB python server/api/seed.py"
