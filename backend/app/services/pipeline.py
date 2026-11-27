"""采集 → 聚合打分 → Navidrome 去重 → 入队 的完整流水线。"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from ..collectors import get_collector
from ..collectors.catalog import PLATFORM_ORDER
from ..config import RuntimeConfig, settings
from ..db import execute, get_runtime_config, now_iso
from ..events import hub, push_pipeline
from ..repo import (
    create_job_run,
    create_task,
    ensure_playlists,
    finish_job_run,
    get_tracks_sources,
    list_playlists,
    prune_logs,
    update_playlist_fetch,
    update_track_score,
    upsert_track,
)
from .navidrome import navidrome
from .normalize import (
    display_title,
    joined_artist,
    make_track_key,
    normalize_text,
    primary_artist,
    strip_noise,
)
from .notify import notify
from .queue import worker
from .rate_limiter import cooldown, platform_lock
from .scoring import decide_status, score_track

_running = False
progress_state: dict[str, Any] = {}


def dedup_enabled(cfg: RuntimeConfig) -> bool:
    return bool(cfg.navidrome.enabled or settings.demo_mode)


def evaluate_track(track: dict, cfg: RuntimeConfig) -> dict:
    sources = track.get("sources") or []
    breakdown = score_track(track, sources, cfg.scoring)
    exists = False
    if dedup_enabled(cfg):
        exists = navidrome.is_present(
            track["track_key"], track.get("artist", ""), track.get("title", ""), cfg.navidrome.match_mode
        )
    if track.get("downloaded_path"):
        status = "COMPLETED"
    else:
        status = decide_status(breakdown["final_score"], exists, cfg.scoring)
    breakdown["exists_in_library"] = exists
    breakdown["threshold"] = cfg.scoring.min_download_score
    return {
        "track": track,
        "score": breakdown["final_score"],
        "status": status,
        "breakdown": breakdown,
        "platform_count": breakdown["cross_count"],
    }


async def run_collection(trigger: str = "scheduler") -> dict:
    global _running
    if _running:
        return {"status": "busy", "message": "已有采集任务正在运行"}
    cfg = get_runtime_config()
    _running = True
    run_id = await create_job_run(trigger)
    started = time.time()
    stats: dict[str, Any] = {"collected": 0, "high_score": 0, "skipped": 0, "queued": 0, "errors": 0}
    await push_pipeline({"phase": "start", "run_id": run_id, "trigger": trigger})
    await hub.log("INFO", "pipeline", f"采集任务启动（{trigger}），run #{run_id}")
    progress_state.clear()
    progress_state.update({"run_id": run_id, "phase": "collect", "collected": 0})

    try:
        await ensure_playlists()
        playlists = [p for p in await list_playlists() if p["is_scheduled"]]
        if not playlists:
            await hub.log("WARN", "pipeline", "没有已勾选的数据源，任务结束")
            await finish_job_run(run_id, "SUCCESS", stats)
            return {"status": "success", "stats": stats, "run_id": run_id}

        grouped: dict[str, list[dict]] = {}
        for pl in playlists:
            grouped.setdefault(pl["platform"], []).append(pl)

        collected_track_ids: set[int] = set()
        lock = asyncio.Lock()

        async def collect_platform(platform: str, items: list[dict]) -> None:
            async with platform_lock(platform):
                collector = get_collector(platform, cfg, demo=settings.demo_mode)
                for index, pl in enumerate(items):
                    if index > 0:
                        await cooldown(
                            platform,
                            cfg.network.cooldown_base_sec,
                            cfg.network.cooldown_jitter_sec,
                        )
                    await push_pipeline(
                        {
                            "phase": "collecting",
                            "platform": platform,
                            "playlist": pl["name"],
                            "index": index + 1,
                            "total": len(items),
                        }
                    )
                    try:
                        rows = await collector.fetch_playlist(pl)
                    except Exception as exc:  # noqa: BLE001
                        stats["errors"] += 1
                        await update_playlist_fetch(pl["id"], 0, str(exc))
                        await hub.log("ERROR", platform, f"《{pl['name']}》抓取失败：{exc}")
                        continue

                    # 仅保留本次榜单曲目，确保 Navidrome 歌单始终是最新列表
                    await execute("DELETE FROM track_sources WHERE playlist_id = ?", (pl["id"],))
                    for raw in rows:
                        title = display_title(raw.title)
                        artist = joined_artist(raw.artists)
                        key = make_track_key(raw.artists, title, raw.isrc)
                        track_id = await upsert_track(
                            track_key=key,
                            title=title,
                            norm_title=normalize_text(strip_noise(title)),
                            artist=artist,
                            norm_artist=normalize_text(primary_artist(raw.artists)),
                            album=raw.album,
                            isrc=raw.isrc,
                            release_date=raw.release_date,
                            cover=raw.cover,
                            platform=platform,
                            playlist_id=pl["id"],
                            rank=raw.rank,
                            extra=raw.extra,
                            run_id=run_id,
                        )
                        collected_track_ids.add(track_id)
                    await update_playlist_fetch(pl["id"], len(rows))
                    async with lock:
                        stats["collected"] += len(rows)
                        progress_state["collected"] = stats["collected"]
                    await hub.log(
                        "INFO",
                        platform,
                        f"《{pl['name']}》抓取完成，共 {len(rows)} 首",
                    )

        await asyncio.gather(*(collect_platform(p, grouped[p]) for p in grouped if p in PLATFORM_ORDER))

        # ---------------------------------------------------------- 打分与去重
        await push_pipeline({"phase": "scoring", "run_id": run_id})
        await hub.log("INFO", "pipeline", "开始聚合打分与 Navidrome 去重校验…")
        track_rows = await get_tracks_sources("last_run_id = ?", (run_id,))
        for track in track_rows:
            result = evaluate_track(track, cfg)
            score = result["score"]
            status = result["status"]
            await update_track_score(track["id"], score, status, result["breakdown"], result["platform_count"])
            if score >= cfg.scoring.min_download_score:
                stats["high_score"] += 1
            if status == "SKIPPED_EXISTS":
                stats["skipped"] += 1
            elif status == "QUEUED_DOWNLOAD":
                task_id = await create_task(
                    track_id=track["id"],
                    title=track["title"],
                    artist=track["artist"],
                    album=track.get("album", ""),
                    cover=track.get("cover", ""),
                    platform=track.get("sources", [{}])[0].get("platform", "") if track.get("sources") else "",
                    mode="auto",
                    priority=10,
                )
                await worker.enqueue(task_id, 10)
                stats["queued"] += 1

        duration = round(time.time() - started, 1)
        stats["duration_sec"] = duration
        await finish_job_run(run_id, "SUCCESS", stats)
        await prune_logs()
        await hub.log(
            "INFO",
            "pipeline",
            f"采集完成：抓取 {stats['collected']} 首，高分 {stats['high_score']} 首，"
            f"库内已存在 {stats['skipped']} 首，入队 {stats['queued']} 首，耗时 {duration}s",
        )
        await push_pipeline({"phase": "done", "run_id": run_id, "stats": stats})
        await notify(
            "job_completed",
            "自动采集任务完成",
            f"抓取 {stats['collected']} 首 / 高分 {stats['high_score']} 首 / "
            f"去重跳过 {stats['skipped']} 首 / 入队 {stats['queued']} 首",
            stats,
        )
        return {"status": "success", "stats": stats, "run_id": run_id}
    except Exception as exc:  # noqa: BLE001
        await finish_job_run(run_id, "FAILED", stats)
        await hub.log("ERROR", "pipeline", f"采集任务异常：{exc}")
        await notify("error_alert", "采集任务异常", str(exc), stats)
        return {"status": "error", "message": str(exc), "run_id": run_id}
    finally:
        _running = False
        await push_pipeline({"phase": "idle"})


def is_running() -> bool:
    return _running


# ---------------------------------------------------------------------- 演示数据
async def seed_demo_data(cfg: RuntimeConfig) -> None:
    """首次启动且开启演示模式时，填充可展示的示例数据。"""
    if not settings.demo_mode:
        return
    from ..db import fetchone

    existing = await fetchone("SELECT COUNT(*) AS cnt FROM tracks")
    if existing and existing["cnt"] > 0:
        return
    await hub.log("INFO", "demo", "检测到空数据库，正在生成演示数据（DEMO_MODE=true）")
    await ensure_playlists()
    playlists = [p for p in await list_playlists() if p["is_scheduled"]]
    demo_playlists = playlists
    for pl in demo_playlists:
        collector = get_collector(pl["platform"], cfg, demo=True)
        try:
            rows = await collector.fetch_playlist(pl)
        except Exception:
            continue
        for raw in rows:
            title = display_title(raw.title)
            artist = joined_artist(raw.artists)
            await upsert_track(
                track_key=make_track_key(raw.artists, title, raw.isrc),
                title=title,
                norm_title=normalize_text(strip_noise(title)),
                artist=artist,
                norm_artist=normalize_text(primary_artist(raw.artists)),
                album=raw.album,
                isrc=raw.isrc,
                release_date=raw.release_date,
                cover=raw.cover,
                platform=pl["platform"],
                playlist_id=pl["id"],
                rank=raw.rank,
                extra=raw.extra,
                run_id=0,
            )
        await update_playlist_fetch(pl["id"], len(rows))

    # 演示：让部分曲目在本地索引中“已存在”
    demo_existing = [
        ("晴天", "周杰伦", "叶惠美"),
        ("光年之外", "G.E.M. 邓紫棋", "光年之外"),
        ("十年", "陈奕迅", "黑白灰"),
        ("起风了", "买辣椒也用券", "起风了"),
        ("海阔天空", "Beyond", "乐与怒"),
    ]
    from ..db import execute

    for title, artist, album in demo_existing:
        key = make_track_key([artist], title)
        await execute(
            "INSERT OR REPLACE INTO navidrome_index(track_key, artist, title, album, path, synced_at) "
            "VALUES(?, ?, ?, ?, ?, ?)",
            (key, artist, title, album, f"/demo/{artist}/{album}/{title}.flac", now_iso()),
        )
    await navidrome.load_cache()

    tracks = await get_tracks_sources()
    for track in tracks:
        result = evaluate_track(track, cfg)
        await update_track_score(track["id"], result["score"], result["status"], result["breakdown"], result["platform_count"])

    # 演示：生成若干条已完成/失败任务，便于查看队列与音质分布
    from ..db import fetchone
    from ..repo import create_task, update_task

    queued = await get_tracks_sources("status = 'QUEUED_DOWNLOAD' ORDER BY score DESC LIMIT 3")
    demo_quality = ["FLAC", "MP3 320k"]
    for index, track in enumerate(queued):
        task_id = await create_task(
            track_id=track["id"],
            title=track["title"],
            artist=track["artist"],
            album=track.get("album", ""),
            cover=track.get("cover", ""),
            platform=(track.get("sources") or [{}])[0].get("platform", ""),
            mode="auto",
            priority=10,
        )
        if index < 2:
            quality = demo_quality[index]
            path = f"/demo/music_library/{track['artist']}/{track.get('album') or '单曲'}/{track['title']}.flac"
            await update_task(
                task_id,
                status="COMPLETED",
                progress=100,
                quality=quality,
                final_path=path,
                message="演示数据（未真实下载）",
                finished_at=now_iso(),
            )
            await execute("UPDATE tracks SET status = 'COMPLETED', downloaded_path = ? WHERE id = ?", (path, track["id"]))
        else:
            await update_task(
                task_id,
                status="FAILED",
                progress=45,
                message="演示数据：上游未找到匹配音源",
                finished_at=now_iso(),
            )
            await execute("UPDATE tracks SET status = 'FAILED' WHERE id = ?", (track["id"],))
    await hub.log("INFO", "demo", f"演示数据生成完成，共 {len(tracks)} 首聚合曲目")
