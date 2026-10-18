#!/usr/bin/env bash
# Deploy SenpaiQC to Google Cloud. Review before running; it creates billable resources.
#   PROJECT=my-proj REGION=us-central1 ./infra/deploy.sh
# Prereqs: gcloud auth login; firebase-tools installed and logged in; secrets pushed with infra/push_secrets.sh:
#   printf %s "$KEY" | gcloud secrets create gemini-api-key --data-file=- --project "$PROJECT"
set -euo pipefail
: "${PROJECT:?set PROJECT}"
REGION="${REGION:-us-central1}"
BUCKET="${BUCKET:-$PROJECT-senpaiqc}"
cd "$(dirname "$0")/.."

gcloud config set project "$PROJECT"
gcloud services enable run.googleapis.com firestore.googleapis.com storage.googleapis.com \
  bigquery.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com cloudbuild.googleapis.com

# Storage, Firestore, BigQuery
gcloud storage buckets describe "gs://$BUCKET" >/dev/null 2>&1 || gcloud storage buckets create "gs://$BUCKET" --location "$REGION" --uniform-bucket-level-access
gcloud firestore databases describe >/dev/null 2>&1 || gcloud firestore databases create --location "$REGION"
sed "s/PROJECT/$PROJECT/g; s/DATASET/senpaiqc/g; s/REGION/$REGION/g" infra/bigquery.sql | bq query --use_legacy_sql=false

# Least-privilege service accounts
for sa in senpaiqc-api senpaiqc-agent; do
  gcloud iam service-accounts describe "$sa@$PROJECT.iam.gserviceaccount.com" >/dev/null 2>&1 || \
    gcloud iam service-accounts create "$sa"
done
API_SA="senpaiqc-api@$PROJECT.iam.gserviceaccount.com"
AGENT_SA="senpaiqc-agent@$PROJECT.iam.gserviceaccount.com"
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" --member "serviceAccount:$API_SA" --role roles/storage.objectAdmin
for sa in "$API_SA" "$AGENT_SA"; do
  gcloud projects add-iam-policy-binding "$PROJECT" --member "serviceAccount:$sa" --role roles/datastore.user --condition None
  gcloud projects add-iam-policy-binding "$PROJECT" --member "serviceAccount:$sa" --role roles/bigquery.jobUser --condition None
  gcloud secrets add-iam-policy-binding "${GEMINI_SECRET:-SENPAIQC_GEMINI_API_KEY}" --member "serviceAccount:$sa" --role roles/secretmanager.secretAccessor
done
bq add-iam-policy-binding --member "serviceAccount:$API_SA" --role roles/bigquery.dataEditor "$PROJECT:senpaiqc" 2>/dev/null || true
bq add-iam-policy-binding --member "serviceAccount:$AGENT_SA" --role roles/bigquery.dataViewer "$PROJECT:senpaiqc" 2>/dev/null || true

COMMON_ENV="BACKEND=gcp,GCP_PROJECT=$PROJECT,GCS_BUCKET=$BUCKET,BQ_DATASET=senpaiqc,AUTH_MODE=firebase"

# Agent (private)
cp infra/agent.Dockerfile Dockerfile
gcloud run deploy senpaiqc-agent --source . --region "$REGION" --service-account "$AGENT_SA" \
  --no-allow-unauthenticated --memory 1Gi --timeout 300 \
  --set-env-vars "$COMMON_ENV" --set-secrets "GEMINI_API_KEY=${GEMINI_SECRET:-SENPAIQC_GEMINI_API_KEY}:latest"
AGENT_URL=$(gcloud run services describe senpaiqc-agent --region "$REGION" --format 'value(status.url)')
gcloud run services add-iam-policy-binding senpaiqc-agent --region "$REGION" --member "serviceAccount:$API_SA" --role roles/run.invoker

# API (public; every route except /api/health needs a Firebase ID token)
cp infra/api.Dockerfile Dockerfile
gcloud run deploy senpaiqc-api --source . --region "$REGION" --service-account "$API_SA" \
  --allow-unauthenticated --memory 2Gi --cpu 2 --timeout 120 \
  --set-env-vars "$COMMON_ENV,AGENT_URL=$AGENT_URL,YOLO_WEIGHTS=${YOLO_WEIGHTS:-},ROBOT_MODE=${ROBOT_MODE:-false}" \
  --set-secrets "GEMINI_API_KEY=${GEMINI_SECRET:-SENPAIQC_GEMINI_API_KEY}:latest"
rm -f Dockerfile

# Web (Firebase Hosting rewrites /api/** to the API service)
( cd client && npm ci && npm run build )
sed -i "s/\"region\": \"[^\"]*\"/\"region\": \"$REGION\"/" firebase.json
firebase deploy --only hosting,firestore:rules --project "$PROJECT"
echo "Seed demo data once:  BACKEND=gcp GCP_PROJECT=$PROJECT GCS_BUCKET=$BUCKET python server/api/seed.py"
