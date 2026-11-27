# ---------- 前端构建 ----------
FROM node:20-alpine AS frontend
WORKDIR /app/frontend
ARG NPM_REGISTRY=https://registry.npmmirror.com
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --registry=${NPM_REGISTRY}
COPY frontend/ ./
RUN npm run build

# ---------- 运行时 ----------
FROM python:3.12-slim

ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Shanghai \
    DATA_DIR=/data \
    HOST=0.0.0.0 \
    PORT=8000 \
    TEMP_DOWNLOAD_DIR=/data/downloads/temp \
    FINAL_MUSIC_DIR=/data/music_library

WORKDIR /app
COPY backend/requirements.txt ./requirements.txt
RUN pip install -i ${PIP_INDEX_URL} -r requirements.txt

COPY backend/app ./app
COPY --from=frontend /app/backend/app/static ./app/static

RUN mkdir -p /data/downloads/temp /data/music_library

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
