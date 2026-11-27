# ---------- 前端构建 ----------
FROM node:20-alpine AS frontend
WORKDIR /app/frontend
ARG NPM_REGISTRY=https://registry.npmmirror.com
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --registry=${NPM_REGISTRY}
COPY frontend/ ./
RUN npm run build

# ---------- 运行时（基础镜像内置上游搜索下载服务） ----------
FROM ghcr.io/juneix/nas-music-kit:latest

ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Shanghai \
    DATA_DIR=/data \
    HOST=0.0.0.0 \
    PORT=8000 \
    TEMP_DOWNLOAD_DIR=/data/downloads/temp \
    FINAL_MUSIC_DIR=/library \
    RUN_UPSTREAM=true \
    UPSTREAM_PORT=8080 \
    UPSTREAM_BASE_URL=http://127.0.0.1:8080 \
    UPSTREAM_LOCAL_DOWNLOAD_DIR=/music

# MusicFlow 放在独立目录，避免与上游 /app/app.py 的模块名 app 冲突
WORKDIR /opt/museflow
COPY backend/requirements.txt ./requirements.txt
RUN pip install -i ${PIP_INDEX_URL} -r requirements.txt

COPY backend/app ./app
COPY --from=frontend /app/backend/app/static ./app/static
COPY docker-entrypoint.sh /usr/local/bin/museflow-entrypoint.sh

# /music 归上游服务专用（只读读取），MusicFlow 的最终音乐库在 /library
RUN chmod +x /usr/local/bin/museflow-entrypoint.sh \
    && mkdir -p /data/downloads/temp /library /music

# 8000：MusicFlow 控制台；8080：内置上游搜索下载服务
EXPOSE 8000 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"

ENTRYPOINT ["/usr/local/bin/museflow-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
