"""SQLite 数据层：建表、连接与通用读写辅助。"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

import aiosqlite

from .config import RuntimeConfig, build_default_runtime_config, settings

_db: Optional[aiosqlite.Connection] = None
_write_lock = asyncio.Lock()


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS playlists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    ext_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    cover TEXT DEFAULT '',
    url TEXT DEFAULT '',
    source_kind TEXT DEFAULT 'chart',
    is_scheduled INTEGER DEFAULT 0,
    last_fetched_at TEXT,
    last_error TEXT,
    track_count INTEGER DEFAULT 0,
    UNIQUE(platform, ext_id)
);

CREATE TABLE IF NOT EXISTS tracks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track_key TEXT UNIQUE NOT NULL,
    title TEXT DEFAULT '',
    norm_title TEXT DEFAULT '',
    artist TEXT DEFAULT '',
    norm_artist TEXT DEFAULT '',
    album TEXT DEFAULT '',
    isrc TEXT DEFAULT '',
    release_date TEXT DEFAULT '',
    cover TEXT DEFAULT '',
    platform_count INTEGER DEFAULT 0,
    score REAL DEFAULT 0,
    status TEXT DEFAULT 'PENDING',
    breakdown TEXT DEFAULT '{}',
    first_seen TEXT,
    last_seen TEXT,
    last_run_id INTEGER DEFAULT 0,
    downloaded_path TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS track_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id INTEGER NOT NULL,
    platform TEXT NOT NULL,
    playlist_id INTEGER NOT NULL,
    rank INTEGER DEFAULT 0,
    extra TEXT DEFAULT '{}',
    seen_at TEXT,
    UNIQUE(track_id, playlist_id)
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id INTEGER,
    title TEXT DEFAULT '',
    artist TEXT DEFAULT '',
    album TEXT DEFAULT '',
    cover TEXT DEFAULT '',
    platform TEXT DEFAULT '',
    mode TEXT DEFAULT 'auto',
    priority INTEGER DEFAULT 10,
    attempts INTEGER DEFAULT 0,
    status TEXT DEFAULT 'QUEUED',
    progress INTEGER DEFAULT 0,
    quality TEXT DEFAULT '',
    message TEXT DEFAULT '',
    source TEXT DEFAULT '',
    source_id TEXT DEFAULT '',
    temp_path TEXT DEFAULT '',
    final_path TEXT DEFAULT '',
    upstream_meta TEXT DEFAULT '{}',
    created_at TEXT,
    updated_at TEXT,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS navidrome_index (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track_key TEXT UNIQUE NOT NULL,
    artist TEXT DEFAULT '',
    title TEXT DEFAULT '',
    album TEXT DEFAULT '',
    path TEXT DEFAULT '',
    song_id TEXT DEFAULT '',
    synced_at TEXT
);

CREATE TABLE IF NOT EXISTS navidrome_playlists (
    local_playlist_id INTEGER PRIMARY KEY,
    navidrome_id TEXT DEFAULT '',
    name TEXT DEFAULT '',
    track_count INTEGER DEFAULT 0,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS navidrome_platform_playlists (
    platform TEXT PRIMARY KEY,
    navidrome_id TEXT DEFAULT '',
    name TEXT DEFAULT '',
    track_count INTEGER DEFAULT 0,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS job_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trigger TEXT DEFAULT 'scheduler',
    status TEXT DEFAULT 'RUNNING',
    started_at TEXT,
    finished_at TEXT,
    stats TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    level TEXT DEFAULT 'INFO',
    scope TEXT DEFAULT '',
    message TEXT
);

CREATE INDEX IF NOT EXISTS idx_track_sources_track ON track_sources(track_id);
CREATE INDEX IF NOT EXISTS idx_track_sources_playlist ON track_sources(playlist_id);
CREATE INDEX IF NOT EXISTS idx_tracks_status ON tracks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_logs_ts ON logs(ts);
"""


async def init_db() -> None:
    global _db
    path = os.path.join(settings.data_dir, "museflow.db")
    os.makedirs(settings.data_dir, exist_ok=True)
    _db = await aiosqlite.connect(path)
    _db.row_factory = aiosqlite.Row
    await _db.executescript(SCHEMA)
    await _db.commit()
    await _ensure_column("tracks", "cover", "cover TEXT DEFAULT ''")
    await _ensure_column("tasks", "cover", "cover TEXT DEFAULT ''")
    await _ensure_column("navidrome_index", "song_id", "song_id TEXT DEFAULT ''")
    await _db.commit()


async def _ensure_column(table: str, column: str, ddl: str) -> None:
    """轻量迁移：为已有数据库补充新列。"""
    assert _db is not None
    cur = await _db.execute(f"PRAGMA table_info({table})")
    rows = await cur.fetchall()
    columns = [row["name"] for row in rows]
    if column not in columns:
        await _db.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


async def close_db() -> None:
    global _db
    if _db is not None:
        await _db.close()
        _db = None


def _conn() -> aiosqlite.Connection:
    if _db is None:
        raise RuntimeError("数据库尚未初始化")
    return _db


async def execute(sql: str, params: Iterable[Any] = ()) -> int:
    async with _write_lock:
        cur = await _conn().execute(sql, tuple(params))
        await _conn().commit()
        return cur.lastrowid or 0


async def executemany(sql: str, rows: Iterable[Iterable[Any]]) -> None:
    async with _write_lock:
        await _conn().executemany(sql, [tuple(r) for r in rows])
        await _conn().commit()


async def fetchall(sql: str, params: Iterable[Any] = ()) -> list[dict]:
    cur = await _conn().execute(sql, tuple(params))
    rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def fetchone(sql: str, params: Iterable[Any] = ()) -> Optional[dict]:
    cur = await _conn().execute(sql, tuple(params))
    row = await cur.fetchone()
    return dict(row) if row else None


# ------------------------------------------------------------------ 运行配置
_runtime_config: Optional[RuntimeConfig] = None


async def load_runtime_config() -> RuntimeConfig:
    global _runtime_config
    row = await fetchone("SELECT value FROM settings WHERE key = 'runtime_config'")
    if row:
        try:
            cfg = RuntimeConfig.model_validate(json.loads(row["value"]))
            if _migrate_legacy_defaults(cfg):
                await save_runtime_config(cfg)
            _runtime_config = cfg
            return cfg
        except Exception:
            pass
    _runtime_config = build_default_runtime_config()
    await save_runtime_config(_runtime_config)
    return _runtime_config


def _migrate_legacy_defaults(cfg: RuntimeConfig) -> bool:
    """把旧版本的默认配置迁移到内置上游与新音乐库目录。"""
    changed = False
    if (
        settings.upstream_local_download_dir
        and cfg.upstream.base_url.rstrip("/") == "https://music.gdstudio.xyz"
        and not cfg.upstream.local_download_dir
    ):
        cfg.upstream.base_url = settings.upstream_base_url
        cfg.upstream.local_download_dir = settings.upstream_local_download_dir
        changed = True

    # /music 是上游下载目录，旧版本若把音乐库或暂存目录指向这里，自动迁移
    legacy_music = "/music"
    for key in ("final_music_dir", "temp_download_dir"):
        current = getattr(cfg.paths, key).rstrip("/")
        default = getattr(settings, key).rstrip("/")
        if current == legacy_music and default != legacy_music:
            setattr(cfg.paths, key, getattr(settings, key))
            changed = True

    # 旧版品牌默认歌单前缀迁移
    if cfg.navidrome.playlist_prefix == "MuseFlow":
        cfg.navidrome.playlist_prefix = settings.navidrome_playlist_prefix
        changed = True

    # 旧版默认音源包含上游已不支持的值（tencent/kugou/migu/spotify/apple）
    legacy_sources = {"netease", "tencent", "kugou", "kuwo", "migu", "joox", "spotify", "apple"}
    if set(cfg.upstream.source_order) == legacy_sources:
        cfg.upstream.source_order = [
            item.strip() for item in settings.upstream_source_order.split(",") if item.strip()
        ]
        changed = True
    return changed


def get_runtime_config() -> RuntimeConfig:
    global _runtime_config
    if _runtime_config is None:
        _runtime_config = build_default_runtime_config()
    return _runtime_config


async def save_runtime_config(cfg: RuntimeConfig) -> None:
    global _runtime_config
    _runtime_config = cfg
    await execute(
        "INSERT INTO settings(key, value, updated_at) VALUES('runtime_config', ?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
        (json.dumps(cfg.model_dump(), ensure_ascii=False), now_iso()),
    )


async def set_setting(key: str, value: Any) -> None:
    await execute(
        "INSERT INTO settings(key, value, updated_at) VALUES(?, ?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
        (key, json.dumps(value, ensure_ascii=False), now_iso()),
    )


async def get_setting(key: str, default: Any = None) -> Any:
    row = await fetchone("SELECT value FROM settings WHERE key = ?", (key,))
    if not row:
        return default
    try:
        return json.loads(row["value"])
    except Exception:
        return default
