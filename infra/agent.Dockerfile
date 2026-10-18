# ADK root-cause agent service. Build from the repo root: docker build -f infra/agent.Dockerfile .
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
COPY server/api/requirements.txt server/api/requirements.txt
RUN grep -v ultralytics server/api/requirements.txt > /tmp/req.txt && pip install -r /tmp/req.txt
COPY server/api server/api
COPY server/agent server/agent
ENV BACKEND=gcp
CMD exec uvicorn main:app --app-dir server/agent --host 0.0.0.0 --port ${PORT:-8080}
