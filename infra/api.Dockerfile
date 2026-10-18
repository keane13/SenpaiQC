# One image = API + web app. Build from the repo root: docker build -f infra/api.Dockerfile .
FROM node:22-slim AS web
WORKDIR /web
COPY client/package.json client/package-lock.json ./
RUN npm ci
COPY client ./
ARG VITE_FIREBASE_API_KEY=""
ENV VITE_FIREBASE_API_KEY=$VITE_FIREBASE_API_KEY
RUN npm run build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
COPY server/api/requirements.txt server/api/requirements.txt
# CPU-only torch keeps the image small enough for Cloud Run.
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch torchvision \
 && pip install -r server/api/requirements.txt
COPY server/api server/api
COPY data/seed_cards.json data/planted_cause.json data/generate_process.py data/
COPY data/samples data/samples
COPY eval/results eval/results
COPY --from=web /web/dist client/dist
# YOLO fast path baked in (3 MB): no GCS step needed. Override YOLO_WEIGHTS to use other weights.
COPY models models
# Label counts as a file: Docker's ENV parsing strips the quotes from inline JSON.
ENV BACKEND=gcp YOLO_WEIGHTS=/app/models/best.pt YOLO_LABEL_COUNTS=/app/models/label_counts.json YOLO_CONFIG_DIR=/tmp/Ultralytics
CMD exec uvicorn main:app --app-dir server/api --host 0.0.0.0 --port ${PORT:-8080}
