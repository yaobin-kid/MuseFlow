#!/bin/sh
# MuseFlow 容器入口：同一容器内同时运行内置上游服务与 MuseFlow 控制台
# /music 固定为上游服务的下载目录（MuseFlow 仅只读读取）；MuseFlow 音乐库在 /library
set -eu

UPSTREAM_PORT="${UPSTREAM_PORT:-8080}"
DATA_DIR="${DATA_DIR:-/data}"
TEMP_DOWNLOAD_DIR="${TEMP_DOWNLOAD_DIR:-/data/downloads/temp}"
FINAL_MUSIC_DIR="${FINAL_MUSIC_DIR:-/library}"

mkdir -p "$DATA_DIR" "$TEMP_DOWNLOAD_DIR" "$FINAL_MUSIC_DIR" /music

UP_PID=""
APP_PID=""

cleanup() {
  if [ -n "$UP_PID" ]; then
    kill "$UP_PID" 2>/dev/null || true
  fi
  if [ -n "$APP_PID" ]; then
    kill "$APP_PID" 2>/dev/null || true
  fi
}
trap cleanup TERM INT

if [ "${RUN_UPSTREAM:-true}" = "true" ]; then
  echo "[entrypoint] 启动内置上游服务 0.0.0.0:${UPSTREAM_PORT}（下载目录 /music）"
  (
    cd /app
    PORT="$UPSTREAM_PORT" exec gunicorn -w 2 -b "0.0.0.0:${UPSTREAM_PORT}" \
      --access-logfile - --error-logfile - app:app
  ) &
  UP_PID=$!

  i=0
  while [ "$i" -lt 30 ]; do
    if python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:${UPSTREAM_PORT}/openapi.json', timeout=2)" >/dev/null 2>&1; then
      echo "[entrypoint] 内置上游服务已就绪"
      break
    fi
    i=$((i + 1))
    sleep 1
  done
fi

"$@" &
APP_PID=$!

STATUS=0
wait "$APP_PID" || STATUS=$?
cleanup
exit "$STATUS"
