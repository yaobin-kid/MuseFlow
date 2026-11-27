"""手动搜索直下接口。"""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..db import get_runtime_config
from ..events import hub
from ..repo import create_task, get_task
from ..security import get_current_user
from ..services.queue import worker
from ..services.rate_limiter import limiter
from ..services.upstream import UpstreamService

router = APIRouter(prefix="/api/manual", tags=["manual"], dependencies=[Depends(get_current_user)])


class DownloadPayload(BaseModel):
    item: dict = Field(default_factory=dict)


@router.get("/quota")
async def quota() -> dict:
    return limiter.usage()


@router.get("/search")
async def search(
    q: str = Query(..., min_length=1),
    source: str = Query(""),
    pages: int = Query(1, ge=1, le=5),
) -> dict:
    wait = await limiter.wait_seconds()
    if wait > 0:
        raise HTTPException(
            status_code=429,
            detail=f"上游 5 分钟配额已用尽，请等待 {int(wait)} 秒后再试",
        )
    await limiter.acquire()
    cfg = get_runtime_config()
    service = UpstreamService(cfg.upstream)
    try:
        if source:
            items = await service.search(source, q, pages)
            for item in items:
                item["_searched_source"] = source
        else:
            items = await service.search_multi(q)
    except Exception as exc:  # noqa: BLE001
        await hub.log("WARN", "manual", f"上游搜索失败：{exc}")
        raise HTTPException(status_code=502, detail=f"上游搜索失败: {exc}")
    return {"items": items, "quota": limiter.usage()}


@router.post("/download")
async def download(payload: DownloadPayload) -> dict:
    item = payload.item or {}
    if not item.get("id") or not item.get("source"):
        raise HTTPException(status_code=400, detail="缺少上游曲目信息（source/id）")
    task_id = await create_task(
        track_id=None,
        title=item.get("name", ""),
        artist=_artist(item.get("artist")),
        album=item.get("album", ""),
        cover=_cover(item),
        platform=item.get("source", ""),
        mode="manual",
        priority=0,
        source=item.get("source", ""),
        source_id=str(item.get("id", "")),
        upstream_meta=item,
    )
    await worker.enqueue(task_id, 0)
    await hub.log("INFO", "manual", f"手动直下入队：{item.get('artist')} - {item.get('name')}")
    return {"ok": True, "task": await get_task(task_id)}


def _artist(value) -> str:
    if isinstance(value, list):
        return " / ".join([v for v in value if v])
    return value or ""


def _cover(item: dict) -> str:
    source = item.get("source") or item.get("_searched_source") or ""
    cover_id = item.get("pic_id") or item.get("id") or ""
    if source and cover_id:
        return f"/api/cover?source={quote(source)}&id={quote(str(cover_id))}"
    return item.get("cover") or ""
