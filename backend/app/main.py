"""MusicFlow 应用入口。"""
from __future__ import annotations

import hashlib
import os
import re
from contextlib import asynccontextmanager
from html import escape
from pathlib import Path
from urllib.parse import unquote

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response

from .config import ensure_dirs, settings
from .db import close_db, get_runtime_config, init_db, load_runtime_config
from .events import hub
from .repo import ensure_playlists, recover_interrupted_tasks
from .routers import auth, dashboard, manual, scoring, settings as settings_router, sources, tasks, ws
from .scheduler import apply_schedule, start_scheduler, stop_scheduler
from .services.navidrome import navidrome
from .services.pipeline import run_collection, seed_demo_data
from .services.queue import worker
from .services.rate_limiter import apply_rate_limit_config

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_dirs()
    await init_db()
    cfg = await load_runtime_config()
    apply_rate_limit_config(cfg.rate_limit.window_sec, cfg.rate_limit.max_requests)
    await ensure_playlists()
    await navidrome.load_cache()
    await seed_demo_data(cfg)
    worker.start()
    recovery = await recover_interrupted_tasks()
    if recovery["failed"]:
        await hub.log("WARN", "system", f"已将 {recovery['failed']} 个重启前中断的任务标记为失败")
    for task_id, priority in recovery["queued"]:
        await worker.enqueue(task_id, priority)
    if recovery["queued"]:
        await hub.log("INFO", "system", f"已恢复 {len(recovery['queued'])} 个排队任务，继续自动下载")
    start_scheduler()
    await hub.log(
        "INFO",
        "system",
        f"{settings.app_name} 启动完成（演示模式：{'开启' if settings.demo_mode else '关闭'}）",
    )
    if settings.collect_on_startup:
        import asyncio

        asyncio.create_task(run_collection("startup"))
    yield
    await worker.stop()
    stop_scheduler()
    await close_db()


app = FastAPI(title="MusicFlow 音乐聚合控制台", version="1.0.0", lifespan=lifespan)

origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials=(origins != ["*"]),
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(sources.router)
app.include_router(scoring.router)
app.include_router(manual.router)
app.include_router(tasks.router)
app.include_router(settings_router.router)
app.include_router(ws.router)


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "app": settings.app_name, "demo_mode": settings.demo_mode}


@app.get("/api/covers/{seed}.svg")
async def generated_cover(seed: str) -> Response:
    """为演示曲目生成确定性的渐变封面。"""
    raw = unquote(seed)
    title = raw.split("|")[-1].strip()
    initial = escape((title[:1] or "♪").upper())
    digest = int(hashlib.md5(raw.encode("utf-8")).hexdigest()[:6], 16)
    hue1 = digest % 360
    hue2 = (hue1 + 46) % 360
    hue3 = (hue1 + 300) % 360
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="320" height="320" viewBox="0 0 320 320">
<defs>
  <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
    <stop stop-color="hsl({hue1},74%,58%)"/>
    <stop offset="0.55" stop-color="hsl({hue2},78%,52%)"/>
    <stop offset="1" stop-color="hsl({hue3},70%,46%)"/>
  </linearGradient>
  <radialGradient id="glow" cx="0.22" cy="0.18" r="0.9">
    <stop stop-color="rgba(255,255,255,0.55)"/>
    <stop offset="1" stop-color="rgba(255,255,255,0)"/>
  </radialGradient>
</defs>
<rect width="320" height="320" fill="url(#g)"/>
<rect width="320" height="320" fill="url(#glow)"/>
<circle cx="248" cy="72" r="92" fill="rgba(255,255,255,0.13)"/>
<circle cx="58" cy="272" r="70" fill="rgba(0,0,0,0.10)"/>
<path d="M206 96v92a28 28 0 1 0 14 24V126l54-14v66a28 28 0 1 0 14 24V88z" fill="rgba(255,255,255,0.18)"/>
<text x="34" y="262" font-family="Inter, 'PingFang SC', 'Microsoft YaHei', sans-serif" font-size="120" font-weight="700" fill="rgba(255,255,255,0.94)">{initial}</text>
</svg>"""
    return Response(svg, media_type="image/svg+xml", headers={"Cache-Control": "public, max-age=86400"})


@app.get("/api/cover")
async def cover_proxy(source: str, id: str) -> Response:
    """代理上游封面数据 API，供 <img> 直接引用。"""
    if not re.fullmatch(r"[a-zA-Z0-9_\-]{1,32}", source or "") or not id or len(id) > 256:
        return Response(status_code=404)
    cfg = get_runtime_config()
    try:
        async with httpx.AsyncClient(
            base_url=cfg.upstream.base_url.rstrip("/"),
            timeout=15,
            follow_redirects=True,
            headers={"User-Agent": "MusicFlow/1.0"},
        ) as client:
            resp = await client.get(cfg.upstream.cover_path, params={"source": source, "id": id})
            content_type = resp.headers.get("content-type", "")
            if resp.status_code == 200 and content_type.startswith("image"):
                return Response(
                    resp.content,
                    media_type=content_type,
                    headers={"Cache-Control": "public, max-age=86400"},
                )
    except Exception:
        pass
    return Response(status_code=404)


@app.get("/{full_path:path}")
async def spa(full_path: str, request: Request):
    if full_path.startswith("api/") or full_path == "api":
        return JSONResponse({"detail": "Not Found"}, status_code=404)
    index = STATIC_DIR / "index.html"
    if full_path:
        candidate = (STATIC_DIR / full_path).resolve()
        try:
            candidate.relative_to(STATIC_DIR.resolve())
            if candidate.is_file():
                if candidate.suffix == ".html":
                    return FileResponse(candidate, headers={"Cache-Control": "no-cache"})
                if full_path.startswith("assets/"):
                    return FileResponse(candidate, headers={"Cache-Control": "public, max-age=31536000, immutable"})
                return FileResponse(candidate)
        except ValueError:
            pass
    if full_path.startswith("assets/"):
        return JSONResponse({"detail": "Asset Not Found"}, status_code=404)
    if index.exists():
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
    return JSONResponse(
        {
            "detail": "前端资源尚未构建，请先在 frontend 目录执行 npm install && npm run build",
            "hint": "或使用 Docker 镜像运行（已内置构建产物）",
        },
        status_code=503,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )
