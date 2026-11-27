"""动态规则与打分预览接口。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ..config import RuntimeConfig, build_default_runtime_config
from ..db import get_runtime_config, save_runtime_config
from ..repo import get_tracks_sources, update_track_score
from ..scheduler import apply_schedule
from ..security import get_current_user
from ..services.pipeline import evaluate_track
from ..services.rate_limiter import apply_rate_limit_config
from ..services.upstream import UpstreamService
from ..services.queue import worker

router = APIRouter(prefix="/api/scoring", tags=["scoring"], dependencies=[Depends(get_current_user)])


class PreviewPayload(BaseModel):
    playlist_id: int | None = None


@router.get("/config")
async def get_config() -> dict:
    return get_runtime_config().model_dump()


@router.put("/config")
async def update_config(payload: RuntimeConfig) -> dict:
    await save_runtime_config(payload)
    apply_rate_limit_config(payload.rate_limit.window_sec, payload.rate_limit.max_requests)
    apply_schedule(payload)
    worker.upstream().reconfigure(payload.upstream)
    return {"ok": True, "config": payload.model_dump()}


@router.post("/reset")
async def reset_config() -> dict:
    cfg = build_default_runtime_config()
    await save_runtime_config(cfg)
    apply_rate_limit_config(cfg.rate_limit.window_sec, cfg.rate_limit.max_requests)
    apply_schedule(cfg)
    return {"ok": True, "config": cfg.model_dump()}


async def _evaluate_all(playlist_id: int | None) -> list[dict]:
    cfg = get_runtime_config()
    if playlist_id:
        tracks = await get_tracks_sources(
            "id IN (SELECT track_id FROM track_sources WHERE playlist_id = ?)", (playlist_id,)
        )
    else:
        tracks = await get_tracks_sources()
    results = []
    for track in tracks:
        evaluated = evaluate_track(track, cfg)
        results.append(
            {
                "id": track["id"],
                "title": track.get("title"),
                "artist": track.get("artist"),
                "album": track.get("album"),
                "cover": track.get("cover", ""),
                "score": evaluated["score"],
                "status": evaluated["status"],
                "platform_count": evaluated["platform_count"],
                "breakdown": evaluated["breakdown"],
                "sources": [
                    {"platform": s["platform"], "playlist_name": s["playlist_name"], "rank": s["rank"]}
                    for s in track.get("sources", [])
                ],
            }
        )
    results.sort(key=lambda x: x["score"], reverse=True)
    return results


@router.post("/preview")
async def preview(payload: PreviewPayload | None = None) -> dict:
    cfg = get_runtime_config()
    playlist_id = payload.playlist_id if payload else None
    results = await _evaluate_all(playlist_id)
    high = [r for r in results if r["score"] >= cfg.scoring.min_download_score]
    summary = {
        "total": len(results),
        "high_score": len(high),
        "queued": len([r for r in high if r["status"] == "QUEUED_DOWNLOAD"]),
        "skipped": len([r for r in results if r["status"] == "SKIPPED_EXISTS"]),
        "filtered": len([r for r in results if r["status"] == "FILTERED_LOW_SCORE"]),
        "avg_score": round(sum(r["score"] for r in results) / len(results), 1) if results else 0,
        "threshold": cfg.scoring.min_download_score,
    }
    return {"summary": summary, "tracks": results[:200]}


@router.post("/recalculate")
async def recalculate(playlist_id: int | None = Query(None)) -> dict:
    results = await _evaluate_all(playlist_id)
    for item in results:
        await update_track_score(item["id"], item["score"], item["status"], item["breakdown"], item["platform_count"])
    cfg = get_runtime_config()
    return {
        "ok": True,
        "total": len(results),
        "high_score": len([r for r in results if r["score"] >= cfg.scoring.min_download_score]),
    }
