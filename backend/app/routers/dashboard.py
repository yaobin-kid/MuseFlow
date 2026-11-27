"""数据看板接口。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..config import settings
from ..db import fetchall, get_runtime_config
from ..events import hub
from ..repo import latest_job_run, list_job_runs, list_logs, list_tasks, task_counts
from ..scheduler import scheduler_status
from ..security import get_current_user
from ..services.navidrome import navidrome
from ..services.rate_limiter import cooldown_snapshot, limiter

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"], dependencies=[Depends(get_current_user)])


async def _status_counts() -> dict[str, int]:
    rows = await fetchall("SELECT status, COUNT(*) AS cnt FROM tracks GROUP BY status")
    return {row["status"]: row["cnt"] for row in rows}


@router.get("/overview")
async def overview() -> dict:
    statuses = await _status_counts()
    platform_rows = await fetchall(
        "SELECT platform, COUNT(DISTINCT track_id) AS cnt FROM track_sources GROUP BY platform"
    )
    cross_rows = await fetchall(
        "SELECT platform_count, COUNT(*) AS cnt FROM tracks WHERE platform_count > 0 GROUP BY platform_count"
    )
    quality_rows = await fetchall(
        "SELECT quality, COUNT(*) AS cnt FROM tasks WHERE status = 'COMPLETED' GROUP BY quality"
    )
    total_tracks = sum(statuses.values())
    pending_statuses = ("SKIPPED_EXISTS", "QUEUED_DOWNLOAD", "DOWNLOADING", "PROCESSING", "COMPLETED", "FAILED")
    high_count = sum(statuses.get(s, 0) for s in pending_statuses)
    downloaded = statuses.get("COMPLETED", 0)
    skipped = statuses.get("SKIPPED_EXISTS", 0)
    counts = await task_counts()
    latest = await latest_job_run()
    return {
        "rate_limit": limiter.usage(),
        "threshold": get_runtime_config().scoring.min_download_score,
        "funnel": {
            "collected": total_tracks,
            "high_score": high_count,
            "skipped": skipped,
            "downloaded": downloaded,
            "low_score": statuses.get("FILTERED_LOW_SCORE", 0),
        },
        "status_counts": statuses,
        "task_counts": counts,
        "platform_distribution": [{"platform": r["platform"], "count": r["cnt"]} for r in platform_rows],
        "cross_distribution": [{"cross": int(r["platform_count"]), "count": r["cnt"]} for r in cross_rows],
        "quality_distribution": [{"quality": r["quality"] or "UNKNOWN", "count": r["cnt"]} for r in quality_rows],
        "latest_run": latest,
        "recent_tasks": await list_tasks(limit=8),
        "recent_logs": await list_logs(limit=40),
        "cooldown": cooldown_snapshot(),
        "scheduler": scheduler_status(),
        "navidrome": {
            "enabled": navidrome_index_enabled(),
            "index_size": navidrome.index_size(),
            "syncing": navidrome.syncing,
            "last_sync_at": navidrome.last_sync_at,
            "last_error": navidrome.last_error,
        },
        "system": {
            "demo_mode": settings.demo_mode,
            "ws_clients": hub.client_count,
            "app_name": settings.app_name,
        },
    }


def navidrome_index_enabled() -> bool:
    from ..db import get_runtime_config

    return get_runtime_config().navidrome.enabled


@router.get("/trend")
async def trend() -> dict:
    runs = await list_job_runs(limit=12)
    runs.reverse()
    return {
        "runs": [
            {
                "id": r["id"],
                "started_at": r["started_at"],
                "status": r["status"],
                "stats": r["stats"],
            }
            for r in runs
        ]
    }


@router.get("/logs")
async def logs(limit: int = Query(200, ge=1, le=500)) -> dict:
    return {"logs": await list_logs(limit=limit)}
