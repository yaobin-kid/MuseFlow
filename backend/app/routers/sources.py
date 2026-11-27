"""数据源与实时打分预览接口。"""
from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..collectors.catalog import PLATFORM_META, PLATFORM_ORDER
from ..db import fetchone, get_runtime_config
from ..events import hub
from ..repo import (
    create_task,
    ensure_playlists,
    get_playlist,
    get_tracks_sources,
    list_playlist_tracks,
    list_playlists,
    set_playlist_scheduled,
    set_track_status,
    update_track_score,
)
from ..security import get_current_user
from ..services.navidrome import navidrome
from ..services.pipeline import evaluate_track, is_running, run_collection
from ..services.queue import worker
from ..services.rate_limiter import cooldown_snapshot

router = APIRouter(prefix="/api/sources", tags=["sources"], dependencies=[Depends(get_current_user)])


class SchedulePayload(BaseModel):
    is_scheduled: bool


@router.get("/playlists")
async def playlists() -> dict:
    await ensure_playlists()
    rows = await list_playlists()
    grouped = {key: [] for key in PLATFORM_ORDER}
    for row in rows:
        grouped.setdefault(row["platform"], []).append(row)
    platforms = []
    for key in PLATFORM_ORDER:
        meta = PLATFORM_META.get(key, {"name": key, "region": "", "color": "#666", "badge": key[:2].upper()})
        platforms.append(
            {
                "key": key,
                "name": meta["name"],
                "region": meta["region"],
                "color": meta["color"],
                "badge": meta["badge"],
                "playlists": grouped.get(key, []),
            }
        )
    return {"platforms": platforms, "cooldown": cooldown_snapshot(), "running": is_running()}


@router.patch("/playlists/{playlist_id}")
async def update_playlist(playlist_id: int, payload: SchedulePayload) -> dict:
    playlist = await get_playlist(playlist_id)
    if not playlist:
        raise HTTPException(status_code=404, detail="歌单不存在")
    await set_playlist_scheduled(playlist_id, payload.is_scheduled)
    return {"ok": True}


@router.post("/collect")
async def collect_now() -> dict:
    if is_running():
        return {"status": "busy", "message": "采集任务正在运行中"}
    asyncio.create_task(run_collection("manual"))
    return {"status": "started"}


@router.get("/cooldown")
async def cooldown() -> dict:
    return {"cooldown": cooldown_snapshot()}


@router.get("/playlists/{playlist_id}/tracks")
async def playlist_tracks(
    playlist_id: int,
    recalculate: bool = Query(True),
    persist: bool = Query(False),
) -> dict:
    playlist = await get_playlist(playlist_id)
    if not playlist:
        raise HTTPException(status_code=404, detail="歌单不存在")
    rows = await list_playlist_tracks(playlist_id)
    if not rows:
        return {"playlist": playlist, "tracks": []}
    cfg = get_runtime_config()
    ids = [row["id"] for row in rows]
    placeholders = ",".join("?" for _ in ids)
    detailed = await get_tracks_sources(f"id IN ({placeholders})", ids)
    by_id = {item["id"]: item for item in detailed}
    results = []
    for row in rows:
        track = by_id.get(row["id"], row)
        if recalculate:
            evaluated = evaluate_track(track, cfg)
            if persist:
                await update_track_score(
                    track["id"], evaluated["score"], evaluated["status"], evaluated["breakdown"], evaluated["platform_count"]
                )
            track = {**track, **evaluated["breakdown"], "score": evaluated["score"], "status": evaluated["status"]}
        else:
            track = {**track, **(track.get("breakdown") or {}), "score": track.get("score", 0), "status": track.get("status")}
        track["playlist_rank"] = row.get("playlist_rank")
        track["sources"] = [
            {"platform": s["platform"], "playlist_name": s["playlist_name"], "rank": s["rank"]}
            for s in track.get("sources", [])
        ]
        results.append(track)
    # 默认按最终得分从高到低排序，同分时保持榜单原始名次
    results.sort(key=lambda item: (-(item.get("score") or 0), item.get("playlist_rank") or 0))
    return {"playlist": playlist, "tracks": results}


@router.post("/tracks/{track_id}/download")
async def download_track(track_id: int) -> dict:
    """低分/被过滤的曲目手动触发下载，复用自动下载的检索与整理流程。"""
    rows = await get_tracks_sources("id = ?", (track_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="曲目不存在")
    track = rows[0]
    if track.get("downloaded_path"):
        raise HTTPException(status_code=409, detail="该歌曲已入库，无需重复下载")

    cfg = get_runtime_config()
    if cfg.navidrome.enabled and navidrome.is_present(
        track["track_key"],
        track.get("artist", ""),
        track.get("title", ""),
        cfg.navidrome.match_mode,
    ):
        raise HTTPException(status_code=409, detail="Navidrome 曲库中已存在该歌曲")

    active = await fetchone(
        "SELECT id, status FROM tasks WHERE track_id = ? AND status IN "
        "('QUEUED', 'WAITING', 'DOWNLOADING', 'PROCESSING', 'COMPLETED') "
        "ORDER BY id DESC LIMIT 1",
        (track_id,),
    )
    if active:
        raise HTTPException(status_code=409, detail=f"任务 #{active['id']} 已存在（{active['status']}）")

    sources = track.get("sources") or []
    task_id = await create_task(
        track_id=track_id,
        title=track["title"],
        artist=track.get("artist", ""),
        album=track.get("album", ""),
        cover=track.get("cover", ""),
        platform=sources[0]["platform"] if sources else "",
        mode="manual",
        priority=0,
    )
    await set_track_status(track_id, "QUEUED_DOWNLOAD")
    await worker.enqueue(task_id, 0)
    await hub.log(
        "INFO", "sources", f"手动触发下载：{track.get('artist')} - {track['title']}（任务 #{task_id}）"
    )
    return {"ok": True, "task_id": task_id}


@router.get("/pool")
async def pool(
    status: str = Query(""),
    platform: str = Query(""),
    q: str = Query(""),
    limit: int = Query(300, ge=1, le=2000),
) -> dict:
    cfg = get_runtime_config()
    tracks = await get_tracks_sources()
    results = []
    for track in tracks:
        evaluated = evaluate_track(track, cfg)
        item = {
            **track,
            **evaluated["breakdown"],
            "score": evaluated["score"],
            "status": evaluated["status"],
        }
        if status and item["status"] != status:
            continue
        if platform and not any(s["platform"] == platform for s in item.get("sources", [])):
            continue
        if q and q.lower() not in f"{item.get('title','')}{item.get('artist','')}".lower():
            continue
        results.append(item)
    results.sort(key=lambda x: x.get("score", 0), reverse=True)
    return {"total": len(results), "tracks": results[:limit], "threshold": cfg.scoring.min_download_score}
