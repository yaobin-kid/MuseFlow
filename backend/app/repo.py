"""数据库领域查询。"""
from __future__ import annotations

import json
from typing import Any, Iterable, Optional

from .db import execute, executemany, fetchall, fetchone, now_iso
from .collectors.catalog import builtin_playlists


# ------------------------------------------------------------------ 歌单
async def ensure_playlists() -> None:
    for pl in builtin_playlists():
        await execute(
            """INSERT INTO playlists(platform, ext_id, name, description, cover, url, source_kind, is_scheduled)
               VALUES(?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(platform, ext_id) DO UPDATE SET
                 name=excluded.name,
                 description=excluded.description,
                 url=excluded.url,
                 source_kind=excluded.source_kind""",
            (
                pl["platform"],
                pl["ext_id"],
                pl["name"],
                pl.get("description", ""),
                pl.get("cover", ""),
                pl.get("url", ""),
                pl.get("source_kind", "chart"),
                1 if pl.get("default_scheduled", True) else 0,
            ),
        )


async def list_playlists() -> list[dict]:
    rows = await fetchall("SELECT * FROM playlists ORDER BY platform, id")
    for row in rows:
        row["is_scheduled"] = bool(row["is_scheduled"])
    return rows


async def get_playlist(playlist_id: int) -> Optional[dict]:
    return await fetchone("SELECT * FROM playlists WHERE id = ?", (playlist_id,))


async def set_playlist_scheduled(playlist_id: int, scheduled: bool) -> None:
    await execute("UPDATE playlists SET is_scheduled = ? WHERE id = ?", (1 if scheduled else 0, playlist_id))


async def update_playlist_fetch(playlist_id: int, count: int, error: str = "") -> None:
    await execute(
        "UPDATE playlists SET last_fetched_at = ?, track_count = ?, last_error = ? WHERE id = ?",
        (now_iso(), count, error, playlist_id),
    )


# ------------------------------------------------------------------ 曲目
async def upsert_track(
    *,
    track_key: str,
    title: str,
    norm_title: str,
    artist: str,
    norm_artist: str,
    album: str,
    isrc: str,
    release_date: str,
    cover: str = "",
    platform: str,
    playlist_id: int,
    rank: int,
    extra: dict,
    run_id: int,
) -> int:
    row = await fetchone("SELECT id FROM tracks WHERE track_key = ?", (track_key,))
    ts = now_iso()
    if row:
        track_id = row["id"]
        await execute(
            """UPDATE tracks SET
                 title = CASE WHEN title = '' THEN ? ELSE title END,
                 artist = CASE WHEN artist = '' THEN ? ELSE artist END,
                 album = CASE WHEN album = '' THEN ? ELSE album END,
                 isrc = CASE WHEN isrc = '' THEN ? ELSE isrc END,
                 release_date = CASE WHEN release_date = '' THEN ? ELSE release_date END,
                 cover = CASE WHEN cover = '' THEN ? ELSE cover END,
                 last_seen = ?, last_run_id = ?
               WHERE id = ?""",
            (title, artist, album, isrc, release_date, cover, ts, run_id, track_id),
        )
    else:
        track_id = await execute(
            """INSERT INTO tracks(track_key, title, norm_title, artist, norm_artist, album, isrc,
                                  release_date, cover, first_seen, last_seen, last_run_id)
               VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (track_key, title, norm_title, artist, norm_artist, album, isrc, release_date, cover, ts, ts, run_id),
        )
    await execute(
        """INSERT INTO track_sources(track_id, platform, playlist_id, rank, extra, seen_at)
           VALUES(?, ?, ?, ?, ?, ?)
           ON CONFLICT(track_id, playlist_id) DO UPDATE SET
             rank=excluded.rank, extra=excluded.extra, seen_at=excluded.seen_at, platform=excluded.platform""",
        (track_id, platform, playlist_id, rank, json.dumps(extra or {}, ensure_ascii=False), ts),
    )
    return track_id


async def get_tracks_sources(where: str = "", params: Iterable[Any] = ()) -> list[dict]:
    """返回曲目 + 其全部来源，用于打分。"""
    sql = "SELECT * FROM tracks"
    if where:
        sql += f" WHERE {where}"
    tracks = await fetchall(sql, params)
    if not tracks:
        return []
    ids = [t["id"] for t in tracks]
    placeholders = ",".join("?" for _ in ids)
    sources = await fetchall(
        f"""SELECT ts.*, p.name AS playlist_name
            FROM track_sources ts JOIN playlists p ON p.id = ts.playlist_id
            WHERE ts.track_id IN ({placeholders})""",
        ids,
    )
    by_track: dict[int, list[dict]] = {}
    for src in sources:
        by_track.setdefault(src["track_id"], []).append(src)
    for track in tracks:
        track["sources"] = by_track.get(track["id"], [])
        try:
            track["breakdown"] = json.loads(track.get("breakdown") or "{}")
        except Exception:
            track["breakdown"] = {}
    return tracks


async def list_playlist_tracks(playlist_id: int) -> list[dict]:
    rows = await fetchall(
        """SELECT t.*, ts.rank AS playlist_rank, ts.extra AS source_extra
           FROM tracks t JOIN track_sources ts ON ts.track_id = t.id
           WHERE ts.playlist_id = ?
           ORDER BY ts.rank ASC""",
        (playlist_id,),
    )
    for row in rows:
        try:
            row["breakdown"] = json.loads(row.get("breakdown") or "{}")
        except Exception:
            row["breakdown"] = {}
    return rows


async def update_track_score(track_id: int, score: float, status: str, breakdown: dict, platform_count: int) -> None:
    await execute(
        "UPDATE tracks SET score = ?, status = ?, breakdown = ?, platform_count = ? WHERE id = ?",
        (score, status, json.dumps(breakdown, ensure_ascii=False), platform_count, track_id),
    )


async def set_track_status(track_id: int, status: str, downloaded_path: str = "") -> None:
    if downloaded_path:
        await execute("UPDATE tracks SET status = ?, downloaded_path = ? WHERE id = ?", (status, downloaded_path, track_id))
    else:
        await execute("UPDATE tracks SET status = ? WHERE id = ?", (status, track_id))


async def get_track(track_id: int) -> Optional[dict]:
    row = await fetchone("SELECT * FROM tracks WHERE id = ?", (track_id,))
    if row:
        try:
            row["breakdown"] = json.loads(row.get("breakdown") or "{}")
        except Exception:
            row["breakdown"] = {}
    return row


# ------------------------------------------------------------------ 任务
async def create_task(
    *,
    track_id: int | None,
    title: str,
    artist: str,
    album: str = "",
    cover: str = "",
    platform: str = "",
    mode: str = "auto",
    priority: int = 10,
    source: str = "",
    source_id: str = "",
    upstream_meta: dict | None = None,
) -> int:
    existing = None
    if track_id:
        existing = await fetchone(
            "SELECT id FROM tasks WHERE track_id = ? AND status IN ('QUEUED','WAITING','DOWNLOADING','PROCESSING')",
            (track_id,),
        )
    ts = now_iso()
    if existing:
        return existing["id"]
    return await execute(
        """INSERT INTO tasks(track_id, title, artist, album, cover, platform, mode, priority, status,
                             source, source_id, upstream_meta, created_at, updated_at)
           VALUES(?, ?, ?, ?, ?, ?, ?, ?, 'QUEUED', ?, ?, ?, ?, ?)""",
        (
            track_id,
            title,
            artist,
            album,
            cover,
            platform,
            mode,
            priority,
            source,
            source_id,
            json.dumps(upstream_meta or {}, ensure_ascii=False),
            ts,
            ts,
        ),
    )


async def update_task(task_id: int, **fields: Any) -> None:
    if not fields:
        return
    fields["updated_at"] = now_iso()
    keys = ", ".join(f"{k} = ?" for k in fields)
    await execute(f"UPDATE tasks SET {keys} WHERE id = ?", (*fields.values(), task_id))


async def get_task(task_id: int) -> Optional[dict]:
    row = await fetchone("SELECT * FROM tasks WHERE id = ?", (task_id,))
    if row:
        try:
            row["upstream_meta"] = json.loads(row.get("upstream_meta") or "{}")
        except Exception:
            row["upstream_meta"] = {}
    return row


async def list_tasks(status: str = "", limit: int = 100, mode: str = "") -> list[dict]:
    clauses = []
    params: list[Any] = []
    if status:
        statuses = [s for s in status.split(",") if s]
        clauses.append(f"status IN ({','.join('?' for _ in statuses)})")
        params.extend(statuses)
    if mode:
        clauses.append("mode = ?")
        params.append(mode)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)
    rows = await fetchall(f"SELECT * FROM tasks {where} ORDER BY id DESC LIMIT ?", params)
    for row in rows:
        try:
            row["upstream_meta"] = json.loads(row.get("upstream_meta") or "{}")
        except Exception:
            row["upstream_meta"] = {}
    return rows


async def delete_task(task_id: int) -> None:
    await execute("DELETE FROM tasks WHERE id = ?", (task_id,))


async def recover_interrupted_tasks() -> dict:
    """重启恢复：中断的执行中任务标记失败，排队任务返回给调用方重新入队。"""
    ts = now_iso()
    row = await fetchone(
        "SELECT COUNT(*) AS cnt FROM tasks WHERE status IN ('DOWNLOADING', 'PROCESSING')"
    )
    failed = row["cnt"] if row else 0
    if failed:
        await execute(
            "UPDATE tracks SET status = 'FAILED' WHERE id IN ("
            "SELECT track_id FROM tasks WHERE track_id IS NOT NULL "
            "AND status IN ('DOWNLOADING', 'PROCESSING')) "
            "AND status != 'COMPLETED'"
        )
        await execute(
            "UPDATE tasks SET status = 'FAILED', message = '服务重启，任务已中断', "
            "finished_at = ?, updated_at = ? "
            "WHERE status IN ('DOWNLOADING', 'PROCESSING')",
            (ts, ts),
        )

    queued = await fetchall(
        "SELECT id, mode FROM tasks WHERE status IN ('QUEUED', 'WAITING') ORDER BY id"
    )

    # 没有对应任务记录的「待下载」曲目（例如演示数据或任务被删除）恢复为待处理，
    # 否则会一直显示待下载且无法再次触发下载。
    await execute(
        "UPDATE tracks SET status = 'PENDING' WHERE status = 'QUEUED_DOWNLOAD' AND id NOT IN ("
        "SELECT track_id FROM tasks WHERE track_id IS NOT NULL AND status IN "
        "('QUEUED', 'WAITING', 'DOWNLOADING', 'PROCESSING', 'COMPLETED'))"
    )
    return {
        "failed": failed,
        "queued": [(item["id"], 0 if item["mode"] == "manual" else 10) for item in queued],
    }


async def task_counts() -> dict[str, int]:
    rows = await fetchall("SELECT status, COUNT(*) AS cnt FROM tasks GROUP BY status")
    return {row["status"]: row["cnt"] for row in rows}


# ------------------------------------------------------------------ 任务运行
async def create_job_run(trigger: str) -> int:
    return await execute(
        "INSERT INTO job_runs(trigger, status, started_at, stats) VALUES(?, 'RUNNING', ?, '{}')",
        (trigger, now_iso()),
    )


async def finish_job_run(run_id: int, status: str, stats: dict) -> None:
    await execute(
        "UPDATE job_runs SET status = ?, finished_at = ?, stats = ? WHERE id = ?",
        (status, now_iso(), json.dumps(stats, ensure_ascii=False), run_id),
    )


async def latest_job_run() -> Optional[dict]:
    row = await fetchone("SELECT * FROM job_runs ORDER BY id DESC LIMIT 1")
    if row:
        try:
            row["stats"] = json.loads(row.get("stats") or "{}")
        except Exception:
            row["stats"] = {}
    return row


async def list_job_runs(limit: int = 20) -> list[dict]:
    rows = await fetchall("SELECT * FROM job_runs ORDER BY id DESC LIMIT ?", (limit,))
    for row in rows:
        try:
            row["stats"] = json.loads(row.get("stats") or "{}")
        except Exception:
            row["stats"] = {}
    return rows


# ------------------------------------------------------------------ 日志
async def list_logs(limit: int = 200) -> list[dict]:
    rows = await fetchall("SELECT * FROM logs ORDER BY id DESC LIMIT ?", (limit,))
    rows.reverse()
    return rows


async def prune_logs(keep: int = 3000) -> None:
    await execute(
        "DELETE FROM logs WHERE id NOT IN (SELECT id FROM logs ORDER BY id DESC LIMIT ?)", (keep,)
    )
