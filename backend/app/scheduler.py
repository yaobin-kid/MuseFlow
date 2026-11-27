"""定时任务调度。"""
from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .config import RuntimeConfig, settings
from .db import get_runtime_config
from .events import hub
from .services.navidrome import navidrome
from .services.pipeline import run_collection

scheduler = AsyncIOScheduler(timezone=settings.timezone)


async def _collect_job() -> None:
    await run_collection("scheduler")


async def _navidrome_job() -> None:
    cfg = get_runtime_config()
    if cfg.navidrome.enabled:
        await navidrome.sync_index(cfg.navidrome)


def apply_schedule(cfg: RuntimeConfig | None = None) -> None:
    cfg = cfg or get_runtime_config()
    for job_id in ("collect", "navidrome_sync"):
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
    if not cfg.scheduler.enabled:
        return
    scheduler.add_job(
        _collect_job,
        "interval",
        minutes=max(1, cfg.scheduler.collect_interval_minutes),
        id="collect",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _navidrome_job,
        "interval",
        minutes=max(1, cfg.scheduler.navidrome_sync_interval_minutes),
        id="navidrome_sync",
        max_instances=1,
        coalesce=True,
    )


def start_scheduler() -> None:
    if not scheduler.running:
        scheduler.start()
    apply_schedule()


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)


def scheduler_status() -> dict:
    jobs = []
    for job in scheduler.get_jobs():
        jobs.append(
            {
                "id": job.id,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                "interval": str(job.trigger),
            }
        )
    return {"running": scheduler.running, "jobs": jobs}
