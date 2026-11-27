"""系统设置与运维接口。"""
from __future__ import annotations

import re
import time
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..config import RuntimeConfig, build_default_runtime_config, settings
from ..db import fetchone, get_runtime_config, get_setting, save_runtime_config
from ..events import hub
from ..scheduler import apply_schedule, scheduler_status
from ..security import get_current_user
from ..services.navidrome import navidrome
from ..services.queue import worker
from ..services.rate_limiter import apply_rate_limit_config, limiter
from ..services.upstream import UpstreamService

router = APIRouter(prefix="/api/settings", tags=["settings"], dependencies=[Depends(get_current_user)])

DEFAULT_PROXY_TEST_URL = "https://www.google.com/generate_204"


class ProxyTestPayload(BaseModel):
    url: str = DEFAULT_PROXY_TEST_URL


def _mask_proxy(proxy: str) -> str:
    parsed = urlsplit(proxy)
    if parsed.username or parsed.password:
        host = parsed.hostname or ""
        port = f":{parsed.port}" if parsed.port else ""
        return f"{parsed.scheme}://***@{host}{port}"
    return proxy


@router.get("/runtime")
async def get_runtime() -> dict:
    return get_runtime_config().model_dump()


@router.put("/runtime")
async def update_runtime(payload: RuntimeConfig) -> dict:
    await save_runtime_config(payload)
    apply_rate_limit_config(payload.rate_limit.window_sec, payload.rate_limit.max_requests)
    apply_schedule(payload)
    worker.upstream().reconfigure(payload.upstream)
    if payload.navidrome.enabled:
        await navidrome.load_cache()
    await hub.log("INFO", "settings", "运行配置已更新")
    return {"ok": True, "config": payload.model_dump()}


@router.post("/reset")
async def reset_runtime() -> dict:
    cfg = build_default_runtime_config()
    await save_runtime_config(cfg)
    apply_rate_limit_config(cfg.rate_limit.window_sec, cfg.rate_limit.max_requests)
    apply_schedule(cfg)
    worker.upstream().reconfigure(cfg.upstream)
    await hub.log("WARN", "settings", "运行配置已重置为环境变量默认值")
    return {"ok": True, "config": cfg.model_dump()}


@router.get("/system")
async def system_info() -> dict:
    cfg = get_runtime_config()
    return {
        "app_name": settings.app_name,
        "version": "1.0.0",
        "demo_mode": settings.demo_mode,
        "timezone": settings.timezone,
        "data_dir": settings.data_dir,
        "admin_username": settings.admin_username,
        "upstream_base_url": cfg.upstream.base_url,
        "paths": cfg.paths.model_dump(),
        "scheduler": scheduler_status(),
        "navidrome": {
            "enabled": cfg.navidrome.enabled,
            "index_size": navidrome.index_size(),
            "syncing": navidrome.syncing,
            "last_sync_at": navidrome.last_sync_at,
            "last_error": navidrome.last_error,
            "sync_playlists": cfg.navidrome.sync_playlists,
            "playlists": await _playlist_summary(),
        },
        "rate_limit": limiter.usage(),
        "seeded_at": await get_setting("seed_at"),
    }


@router.post("/test-upstream")
async def test_upstream() -> dict:
    cfg = get_runtime_config()
    service = UpstreamService(cfg.upstream)
    try:
        items = await service.search(cfg.upstream.source_order[0] if cfg.upstream.source_order else "netease", "周杰伦")
        return {"ok": True, "message": f"上游连接正常，返回 {len(items)} 条结果"}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"上游连接失败: {exc}")


@router.post("/test-proxy")
async def test_proxy(payload: ProxyTestPayload | None = None) -> dict:
    cfg = get_runtime_config()
    proxy = (cfg.network.proxy_url or "").strip()
    if not proxy:
        raise HTTPException(status_code=400, detail="未配置代理地址，请填写代理并保存后再测试")

    target = ((payload.url if payload else "") or DEFAULT_PROXY_TEST_URL).strip()
    if not target:
        target = DEFAULT_PROXY_TEST_URL
    if len(target) > 2048:
        raise HTTPException(status_code=400, detail="测试地址过长")
    if not re.match(r"^https?://", target, re.IGNORECASE):
        target = "https://" + target
    parsed = urlsplit(target)
    if not parsed.hostname:
        raise HTTPException(status_code=400, detail="测试地址无效，请填写完整网址")

    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(
            proxy=proxy,
            timeout=httpx.Timeout(20.0, connect=15.0),
            follow_redirects=True,
            headers={"User-Agent": "MuseFlow/1.0"},
        ) as client:
            resp = await client.get(target)
        elapsed = int((time.perf_counter() - started) * 1000)
    except Exception as exc:  # noqa: BLE001
        await hub.log("WARN", "settings", f"代理测试失败：{target} → {exc}")
        raise HTTPException(status_code=502, detail=f"代理测试失败：{exc}") from exc

    await hub.log(
        "INFO", "settings", f"代理测试成功：{target} → HTTP {resp.status_code}（{elapsed}ms）"
    )
    return {
        "ok": True,
        "url": target,
        "proxy": _mask_proxy(proxy),
        "status_code": resp.status_code,
        "elapsed_ms": elapsed,
    }


@router.post("/test-navidrome")
async def test_navidrome() -> dict:
    cfg = get_runtime_config()
    ok, message = await navidrome.ping(cfg.navidrome)
    if not ok:
        raise HTTPException(status_code=502, detail=message)
    return {"ok": True, "message": message}


@router.post("/navidrome/sync")
async def sync_navidrome() -> dict:
    cfg = get_runtime_config()
    if not cfg.navidrome.enabled:
        raise HTTPException(status_code=400, detail="Navidrome 未启用")
    count = await navidrome.sync_index(cfg.navidrome)
    return {
        "ok": True,
        "indexed": count,
        "index_size": navidrome.index_size(),
        "playlists": await _playlist_summary(),
    }


@router.post("/navidrome/playlists/sync")
async def sync_navidrome_playlists() -> dict:
    cfg = get_runtime_config()
    if not cfg.navidrome.enabled:
        raise HTTPException(status_code=400, detail="Navidrome 未启用")
    result = await navidrome.refresh_playlists(cfg.navidrome)
    return {"ok": True, **result, "summary": await _playlist_summary()}


async def _playlist_summary() -> dict:
    row = await fetchone("SELECT COUNT(*) AS cnt, SUM(track_count) AS tracks FROM navidrome_playlists")
    return {
        "count": (row or {}).get("cnt") or 0,
        "tracks": (row or {}).get("tracks") or 0,
        "last_sync_at": navidrome.last_playlist_sync_at,
    }


@router.get("/navidrome/status")
async def navidrome_status() -> dict:
    cfg = get_runtime_config()
    return {
        "enabled": cfg.navidrome.enabled,
        "index_size": navidrome.index_size(),
        "syncing": navidrome.syncing,
        "last_sync_at": navidrome.last_sync_at,
        "last_error": navidrome.last_error,
        "match_mode": cfg.navidrome.match_mode,
        "sync_playlists": cfg.navidrome.sync_playlists,
        "playlists": await _playlist_summary(),
    }
