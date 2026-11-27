"""下载与后处理队列接口。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ..db import fetchone
from ..events import hub, push_task
from ..repo import delete_task, get_task, list_tasks, set_track_status, task_counts, update_task
from ..security import get_current_user
from ..services.queue import worker
from ..services.rate_limiter import limiter

router = APIRouter(prefix="/api/tasks", tags=["tasks"], dependencies=[Depends(get_current_user)])


@router.get("")
async def tasks(
    status: str = Query(""),
    mode: str = Query(""),
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    rows = await list_tasks(status=status, limit=limit, mode=mode)
    return {"tasks": rows, "counts": await task_counts(), "quota": limiter.usage()}


@router.post("/{task_id}/retry")
async def retry(task_id: int) -> dict:
    task = await get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task["status"] in ("DOWNLOADING", "PROCESSING"):
        raise HTTPException(status_code=400, detail="任务正在执行中")
    await update_task(task_id, status="QUEUED", progress=0, message="重新排队", finished_at=None)
    if task.get("track_id"):
        await set_track_status(task["track_id"], "QUEUED_DOWNLOAD")
    await worker.enqueue(task_id, 0 if task["mode"] == "manual" else 10)
    await hub.log("INFO", "tasks", f"任务 #{task_id} 已重新入队")
    await push_task(await get_task(task_id))
    return {"ok": True}


@router.post("/{task_id}/cancel")
async def cancel(task_id: int) -> dict:
    task = await get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task["status"] in ("DOWNLOADING", "PROCESSING", "COMPLETED"):
        raise HTTPException(status_code=400, detail="当前状态无法取消")
    await update_task(task_id, status="CANCELLED", message="已取消")
    if task.get("track_id"):
        await set_track_status(task["track_id"], "CANCELLED")
    await push_task(await get_task(task_id))
    return {"ok": True}


@router.delete("/{task_id}")
async def remove(task_id: int) -> dict:
    task = await get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task["status"] in ("DOWNLOADING", "PROCESSING"):
        raise HTTPException(status_code=400, detail="任务正在执行中，无法删除")
    await delete_task(task_id)
    if task.get("track_id") and task["status"] != "COMPLETED":
        track = await fetchone("SELECT downloaded_path FROM tracks WHERE id = ?", (task["track_id"],))
        if track and not track["downloaded_path"]:
            await set_track_status(task["track_id"], "PENDING")
    await hub.log("INFO", "tasks", f"任务 #{task_id} 记录已删除")
    return {"ok": True}
