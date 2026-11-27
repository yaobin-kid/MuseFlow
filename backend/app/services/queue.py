"""下载调度器：优先级队列 + 全局限流 + 下载/整理流水线。"""
from __future__ import annotations

import asyncio
import os
import time
from typing import Optional

from ..config import RuntimeConfig, settings
from ..db import get_runtime_config
from ..events import hub, push_rate_limit, push_task
from ..repo import get_task, set_track_status, update_task
from .navidrome import navidrome
from .normalize import primary_artist
from .notify import notify
from .postprocess import post_process
from .rate_limiter import limiter
from .upstream import UpstreamService


class DownloadWorker:
    def __init__(self) -> None:
        self.queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._seq = 0
        self._task: Optional[asyncio.Task] = None
        self._upstream: Optional[UpstreamService] = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop(), name="download-worker")
            self._upstream = UpstreamService(get_runtime_config().upstream)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def upstream(self) -> UpstreamService:
        cfg = get_runtime_config()
        if self._upstream is None:
            self._upstream = UpstreamService(cfg.upstream)
        else:
            self._upstream.reconfigure(cfg.upstream)
        return self._upstream

    async def enqueue(self, task_id: int, priority: int = 10) -> None:
        self._seq += 1
        await self.queue.put((priority, self._seq, task_id))

    async def _loop(self) -> None:
        while True:
            _, _, task_id = await self.queue.get()
            try:
                await self._process(task_id)
            except Exception as exc:  # noqa: BLE001
                await hub.log("ERROR", "worker", f"任务 {task_id} 处理异常: {exc}")
            finally:
                self.queue.task_done()

    async def _process(self, task_id: int) -> None:
        task = await get_task(task_id)
        if not task or task["status"] not in ("QUEUED", "WAITING"):
            return
        cfg: RuntimeConfig = get_runtime_config()
        upstream = self.upstream()
        limiter.reconfigure(cfg.rate_limit.window_sec, cfg.rate_limit.max_requests)

        await update_task(task_id, status="DOWNLOADING", progress=5, message="准备上游检索")
        task["status"] = "DOWNLOADING"
        await push_task(task)
        await hub.log("INFO", "worker", f"[{task['mode']}] 开始处理：{task['artist']} - {task['title']}")

        try:
            item = task.get("upstream_meta") or {}
            if not item.get("id"):
                await limiter.acquire()
                best = await upstream.search_best(task["title"], task["artist"])
                if not best:
                    raise RuntimeError("所有音源均未找到匹配音源")
                item = best
                await update_task(
                    task_id,
                    source=item.get("source") or item.get("_searched_source") or "",
                    source_id=str(item.get("id") or ""),
                    upstream_meta=item,
                    progress=25,
                    message=f"已匹配音源 {item.get('_searched_source') or item.get('source') or ''}",
                )
                await push_task(await get_task(task_id))

            await limiter.acquire()
            temp_dir = cfg.paths.temp_download_dir
            meta, temp_path = await upstream.download(item, temp_dir)

            quality = (meta or {}).get("bitrate") or ""
            await update_task(
                task_id,
                status="PROCESSING",
                progress=65,
                message="下载完成，开始整理归档",
                quality=("FLAC" if str((meta or {}).get("filename", "")).lower().endswith(".flac") else f"MP3 {quality}".strip()),
                temp_path=temp_path or "",
            )
            await push_task(await get_task(task_id))

            lyric_path = None
            lyric_name = ""
            try:
                await limiter.acquire()
                lyric_path, lyric_name = await upstream.lyric(item, temp_dir)
            except Exception:
                lyric_path = None

            cover_bytes = None
            try:
                await limiter.acquire()
                cover_bytes = await upstream.fetch_cover(item)
            except Exception:
                cover_bytes = None

            result = await post_process(
                temp_path=temp_path,
                title=item.get("name") or task["title"],
                artist=(item.get("artist") if isinstance(item.get("artist"), str) else primary_artist(item.get("artist") or task["artist"])),
                album=item.get("album") or task["album"],
                temp_dir=temp_dir,
                final_dir=cfg.paths.final_music_dir,
                lyric_path=lyric_path,
                cover_bytes=cover_bytes,
                upstream_meta=meta if isinstance(meta, dict) else {},
            )

            await update_task(
                task_id,
                status="COMPLETED",
                progress=100,
                quality=result["quality"],
                final_path=result["final_path"],
                message="已入库",
                finished_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
            )
            if task.get("track_id"):
                await set_track_status(task["track_id"], "COMPLETED", result["final_path"])

            # 整理入库成功后，清理上游下载目录中的音频与歌词源文件
            await upstream.remove_local(
                (meta or {}).get("filename") if isinstance(meta, dict) else "",
                lyric_name,
            )

            key = f"{_norm(primary_artist(item.get('artist') or task['artist']))}::{_norm(item.get('name') or task['title'])}"
            navidrome.add_key(key, item.get("artist") or task["artist"], item.get("name") or task["title"], item.get("album") or "")

            if cfg.navidrome.enabled and cfg.navidrome.auto_scan_after_move:
                await navidrome.start_scan(cfg.navidrome)
            if cfg.navidrome.enabled:
                # 等待扫库完成后刷新 Navidrome 歌单，保证新歌实时可见
                navidrome.request_refresh(cfg.navidrome)

            await hub.log("INFO", "worker", f"入库完成：{result['final_path']}")
            await notify(
                "manual_download_completed" if task["mode"] == "manual" else "download_completed",
                "下载完成",
                f"{task['artist']} - {task['title']}\n音质：{result['quality']}",
                {"task_id": task_id},
            )
        except Exception as exc:  # noqa: BLE001
            await update_task(
                task_id,
                status="FAILED",
                message=str(exc)[:500],
                finished_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
            )
            if task.get("track_id"):
                await set_track_status(task["track_id"], "FAILED")
            await hub.log("ERROR", "worker", f"任务失败：{task['artist']} - {task['title']}：{exc}")
            await notify("error_alert", "下载失败", f"{task['artist']} - {task['title']}\n{exc}", {"task_id": task_id})
        finally:
            await push_task(await get_task(task_id))
            await push_rate_limit(limiter.usage())


def _norm(text: str) -> str:
    from .normalize import normalize_text, strip_noise

    return normalize_text(strip_noise(text or ""))


worker = DownloadWorker()
