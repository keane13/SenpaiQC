#!/usr/bin/env bash
# Push SenpaiQC secrets from the local .env to Google Cloud Secret Manager.
#   PROJECT=my-proj ./infra/push_secrets.sh
#
# SenpaiQC uses its OWN secrets (prefix SENPAIQC_), so a new version never changes a shared
# secret that other Cloud Run services read with :latest.
#   .env key          -> Secret Manager name            -> env var on Cloud Run
#   GEMINI_API_KEY    -> SENPAIQC_GEMINI_API_KEY       -> GEMINI_API_KEY
#   DEMO_TOKEN        -> SENPAIQC_DEMO_TOKEN           -> DEMO_TOKEN
# Values are never printed. If DEMO_TOKEN is empty or still the local default, a random token is
# generated and stored; read it once with:
#   gcloud secrets versions access latest --secret SENPAIQC_DEMO_TOKEN --project "$PROJECT"
# A new version is added only when the value changed. Then run ./infra/deploy_cloudrun.sh.
set -euo pipefail
: "${PROJECT:?set PROJECT}"
cd "$(dirname "$0")/.."
ENV_FILE="${ENV_FILE:-.env}"
[ -f "$ENV_FILE" ] || { echo "No $ENV_FILE found"; exit 1; }

env_value() {  # last KEY=value in the env file, without quotes or Windows line endings
  grep -E "^$1=" "$ENV_FILE" | tail -n 1 | cut -d= -f2- | tr -d '\r' | sed -e 's/^"\(.*\)"$/\1/' -e "s/^'\(.*\)'$/\1/"
}

push() {  # push NAME VALUE
  local name="$1" value="$2"
  if ! gcloud secrets describe "$name" --project "$PROJECT" >/dev/null 2>&1; then
    printf %s "$value" | gcloud secrets create "$name" --project "$PROJECT" \
      --replication-policy automatic --labels app=senpaiqc --data-file=- >/dev/null
    echo "created  $name"
  elif [ "$(gcloud secrets versions access latest --secret "$name" --project "$PROJECT" 2>/dev/null)" != "$value" ]; then
    printf %s "$value" | gcloud secrets versions add "$name" --project "$PROJECT" --data-file=- >/dev/null
    echo "updated  $name (new version)"
  else
    echo "unchanged $name"
  fi
}

GEMINI="$(env_value GEMINI_API_KEY)"
[ -n "$GEMINI" ] || { echo "GEMINI_API_KEY is empty in $ENV_FILE"; exit 1; }
push SENPAIQC_GEMINI_API_KEY "$GEMINI"

TOKEN="$(env_value DEMO_TOKEN)"
if [ -z "$TOKEN" ] || [ "$TOKEN" = "senpaiqc-demo" ] || [ "$TOKEN" = "kaizenlens-demo" ] || [ "${#TOKEN}" -lt 12 ]; then
  if gcloud secrets describe SENPAIQC_DEMO_TOKEN --project "$PROJECT" >/dev/null 2>&1; then
    echo "unchanged SENPAIQC_DEMO_TOKEN (local value is the default; keeping the stored token)"
    TOKEN=""
  else
    TOKEN="sq-$(python -c 'import secrets; print(secrets.token_urlsafe(18))')"
    echo "generated a random demo token (the local default must not be used on a public URL)"
  fi
fi
[ -n "$TOKEN" ] && push SENPAIQC_DEMO_TOKEN "$TOKEN"

echo
echo "Done. Read the judges' token with:"
echo "  gcloud secrets versions access latest --secret SENPAIQC_DEMO_TOKEN --project $PROJECT"
