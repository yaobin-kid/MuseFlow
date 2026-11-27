"""Navidrome (Subsonic API) 曲库索引同步与去重。"""
from __future__ import annotations

import asyncio
import hashlib
import random
import string
from typing import Optional

import httpx

from ..config import NavidromeConfig
from ..db import execute, executemany, fetchall, now_iso
from ..events import hub
from .normalize import normalize_text, primary_artist, strip_noise

_PLATFORM_LABELS = {
    "netease": "网易云音乐",
    "qq": "QQ音乐",
    "spotify": "Spotify",
    "apple": "Apple Music",
}


class NavidromeService:
    def __init__(self) -> None:
        self._keys: set[str] = set()
        self._title_index: dict[str, set[str]] = {}
        self._syncing = False
        self._refreshing = False
        self._refresh_task: Optional[asyncio.Task] = None
        self.last_sync_at: str = ""
        self.last_error: str = ""
        self.last_playlist_sync_at: str = ""

    # ---------------------------------------------------------------- 基础
    @staticmethod
    def _auth(cfg: NavidromeConfig) -> dict:
        salt = "".join(random.choices(string.ascii_letters + string.digits, k=8))
        token = hashlib.md5((cfg.password + salt).encode("utf-8")).hexdigest()
        return {"u": cfg.username, "t": token, "s": salt, "v": "1.16.1", "c": "MuseFlow", "f": "json"}

    def _url(self, cfg: NavidromeConfig, endpoint: str) -> str:
        return cfg.url.rstrip("/") + "/rest/" + endpoint

    async def ping(self, cfg: NavidromeConfig) -> tuple[bool, str]:
        if not cfg.url:
            return False, "未配置 Navidrome 地址"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(self._url(cfg, "ping"), params=self._auth(cfg))
                data = resp.json().get("subsonic-response", {})
                if data.get("status") == "ok":
                    return True, "连接成功"
                return False, str(data.get("error") or "认证失败")
        except Exception as exc:  # noqa: BLE001
            return False, f"连接失败: {exc}"

    # ---------------------------------------------------------------- 索引缓存
    async def load_cache(self) -> None:
        rows = await fetchall("SELECT track_key, artist, title FROM navidrome_index")
        self._keys = set()
        self._title_index = {}
        for row in rows:
            self._keys.add(row["track_key"])
            norm_title = normalize_text(strip_noise(row["title"] or ""))
            if norm_title:
                self._title_index.setdefault(norm_title, set()).add(
                    normalize_text(primary_artist(row["artist"] or ""))
                )
        await hub.log("INFO", "navidrome", f"本地曲库索引缓存加载完成，共 {len(self._keys)} 首")

    def is_present(self, track_key: str, artist: str, title: str, mode: str = "strict") -> bool:
        if track_key in self._keys:
            return True
        if mode == "loose":
            norm_title = normalize_text(strip_noise(title or ""))
            if not norm_title:
                return False
            artists = self._title_index.get(norm_title)
            if artists is not None:
                if not artists:
                    return True
                norm_artist = normalize_text(primary_artist(artist or ""))
                for existing in artists:
                    if not existing or not norm_artist:
                        return True
                    if existing in norm_artist or norm_artist in existing:
                        return True
        return False

    def index_size(self) -> int:
        return len(self._keys)

    def add_key(self, track_key: str, artist: str, title: str, album: str = "", path: str = "") -> None:
        self._keys.add(track_key)
        norm_title = normalize_text(strip_noise(title or ""))
        if norm_title:
            self._title_index.setdefault(norm_title, set()).add(normalize_text(primary_artist(artist or "")))

    # ---------------------------------------------------------------- 同步
    async def sync_index(self, cfg: NavidromeConfig) -> int:
        if not cfg.enabled or not cfg.url:
            return 0
        if self._syncing:
            return len(self._keys)
        self._syncing = True
        await hub.log("INFO", "navidrome", "开始同步 Navidrome 曲库索引…")
        try:
            albums = await self._fetch_albums(cfg)
            await hub.log("INFO", "navidrome", f"获取到 {len(albums)} 张专辑，开始拉取曲目")
            semaphore = asyncio.Semaphore(4)
            songs: list[dict] = []

            async def fetch_album(album: dict) -> None:
                async with semaphore:
                    try:
                        async with httpx.AsyncClient(timeout=25) as client:
                            resp = await client.get(
                                self._url(cfg, "getAlbum"),
                                params={"id": album["id"], **self._auth(cfg)},
                            )
                            data = resp.json().get("subsonic-response", {})
                            album_data = data.get("album") or {}
                            songs.extend(album_data.get("song") or [])
                    except Exception as exc:  # noqa: BLE001
                        await hub.log("WARN", "navidrome", f"专辑 {album.get('name')} 拉取失败: {exc}")

            await asyncio.gather(*(fetch_album(a) for a in albums))

            rows = []
            ts = now_iso()
            for song in songs:
                artist = song.get("artist") or song.get("albumArtist") or ""
                title = song.get("title") or ""
                key = f"{normalize_text(primary_artist(artist))}::{normalize_text(strip_noise(title))}"
                rows.append(
                    (
                        key,
                        artist,
                        title,
                        song.get("album") or "",
                        song.get("path") or "",
                        song.get("id") or "",
                        ts,
                    )
                )

            await execute("DELETE FROM navidrome_index")
            for chunk_start in range(0, len(rows), 500):
                chunk = rows[chunk_start : chunk_start + 500]
                await executemany(
                    "INSERT OR REPLACE INTO navidrome_index(track_key, artist, title, album, path, song_id, synced_at) "
                    "VALUES(?, ?, ?, ?, ?, ?, ?)",
                    chunk,
                )

            await self.load_cache()
            self.last_sync_at = ts
            self.last_error = ""
            await hub.log("INFO", "navidrome", f"Navidrome 索引同步完成，共 {len(rows)} 首")
            if cfg.sync_playlists:
                await self.refresh_playlists(cfg)
            return len(rows)
        except Exception as exc:  # noqa: BLE001
            self.last_error = str(exc)
            await hub.log("ERROR", "navidrome", f"索引同步失败: {exc}")
            return 0
        finally:
            self._syncing = False

    async def _fetch_albums(self, cfg: NavidromeConfig, page_size: int = 500) -> list[dict]:
        albums: list[dict] = []
        offset = 0
        async with httpx.AsyncClient(timeout=30) as client:
            while True:
                params = {
                    "type": "alphabeticalByArtist",
                    "size": page_size,
                    "offset": offset,
                    **self._auth(cfg),
                }
                resp = await client.get(self._url(cfg, "getAlbumList2"), params=params)
                data = resp.json().get("subsonic-response", {})
                batch = (data.get("albumList2") or {}).get("album") or []
                albums.extend(batch)
                if len(batch) < page_size:
                    break
                offset += page_size
                if offset > 100000:
                    break
        return albums

    # ---------------------------------------------------------------- 歌单同步
    @staticmethod
    def _playlist_name(cfg: NavidromeConfig, playlist: dict) -> str:
        label = _PLATFORM_LABELS.get(playlist["platform"], playlist["platform"])
        parts = [p for p in ((cfg.playlist_prefix or "").strip(), label, playlist["name"]) if p]
        return " · ".join(parts)

    async def refresh_playlists(self, cfg: NavidromeConfig, resolve_missing: bool = True) -> dict:
        """按当前已调度歌单在 Navidrome 中创建/刷新同名歌单，仅保留最新榜单曲目。"""
        if not cfg.enabled or not cfg.url or not cfg.sync_playlists:
            return {"playlists": 0, "tracks": 0}
        if self._refreshing:
            return {"playlists": 0, "tracks": 0, "busy": True}
        self._refreshing = True
        try:
            playlists = await fetchall("SELECT * FROM playlists WHERE is_scheduled = 1 ORDER BY platform, id")
            if not playlists:
                return {"playlists": 0, "tracks": 0}

            rows = await fetchall("SELECT track_key, song_id FROM navidrome_index")
            song_by_key = {row["track_key"]: (row["song_id"] or "") for row in rows}
            if resolve_missing:
                await self._resolve_missing_ids(cfg, playlists, song_by_key)

            name_map = await self._navidrome_playlist_names(cfg)
            mappings = {row["local_playlist_id"]: row for row in await fetchall("SELECT * FROM navidrome_playlists")}

            synced_playlists = 0
            synced_tracks = 0
            for pl in playlists:
                tracks = await fetchall(
                    """SELECT t.track_key FROM tracks t
                       JOIN track_sources ts ON ts.track_id = t.id
                       WHERE ts.playlist_id = ? ORDER BY ts.rank ASC""",
                    (pl["id"],),
                )
                song_ids: list[str] = []
                seen: set[str] = set()
                for item in tracks:
                    sid = song_by_key.get(item["track_key"]) or ""
                    if sid and sid not in seen:
                        seen.add(sid)
                        song_ids.append(sid)
                if not song_ids:
                    continue

                name = self._playlist_name(cfg, pl)
                mapping = mappings.get(pl["id"]) or {}
                nav_id = mapping.get("navidrome_id") or name_map.get(name, "")
                ok, result_id = await self._upsert_playlist(cfg, nav_id, name, song_ids)
                if not ok:
                    continue
                now = now_iso()
                await execute(
                    """INSERT INTO navidrome_playlists(local_playlist_id, navidrome_id, name, track_count, updated_at)
                       VALUES(?, ?, ?, ?, ?)
                       ON CONFLICT(local_playlist_id) DO UPDATE SET
                         navidrome_id=excluded.navidrome_id, name=excluded.name,
                         track_count=excluded.track_count, updated_at=excluded.updated_at""",
                    (pl["id"], result_id or nav_id, name, len(song_ids), now),
                )
                synced_playlists += 1
                synced_tracks += len(song_ids)

            self.last_playlist_sync_at = now_iso()
            if synced_playlists:
                await hub.log(
                    "INFO",
                    "navidrome",
                    f"Navidrome 歌单同步完成：更新 {synced_playlists} 个歌单，共 {synced_tracks} 首曲目",
                )
            return {"playlists": synced_playlists, "tracks": synced_tracks}
        except Exception as exc:  # noqa: BLE001
            await hub.log("WARN", "navidrome", f"Navidrome 歌单同步失败: {exc}")
            return {"playlists": 0, "tracks": 0, "error": str(exc)}
        finally:
            self._refreshing = False

    async def _resolve_missing_ids(
        self, cfg: NavidromeConfig, playlists: list[dict], song_by_key: dict[str, str]
    ) -> None:
        """为已下载但尚未记录 Navidrome song id 的曲目做 Subsonic 搜索补全。"""
        missing: dict[str, dict] = {}
        for pl in playlists:
            rows = await fetchall(
                """SELECT t.track_key, t.artist, t.title FROM tracks t
                   JOIN track_sources ts ON ts.track_id = t.id
                   WHERE ts.playlist_id = ? AND (t.downloaded_path != '' OR t.status = 'SKIPPED_EXISTS')""",
                (pl["id"],),
            )
            for row in rows:
                key = row["track_key"]
                if not song_by_key.get(key) and key not in missing:
                    missing[key] = row
        if not missing:
            return

        semaphore = asyncio.Semaphore(3)

        async def resolve(row: dict) -> None:
            async with semaphore:
                sid = await self.ensure_song_id(cfg, row["track_key"], row["artist"], row["title"])
                if sid:
                    song_by_key[row["track_key"]] = sid

        await asyncio.gather(*(resolve(row) for row in list(missing.values())[:120]))

    async def ensure_song_id(self, cfg: NavidromeConfig, track_key: str, artist: str, title: str) -> str:
        """通过 search3 在 Navidrome 中定位曲目并缓存 song id。"""
        if not title:
            return ""
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(
                    self._url(cfg, "search3"),
                    params={
                        "query": f"{artist} {title}".strip(),
                        "songCount": 20,
                        "artistCount": 0,
                        "albumCount": 0,
                        **self._auth(cfg),
                    },
                )
                data = resp.json().get("subsonic-response", {})
                songs = (data.get("searchResult3") or {}).get("song") or []
        except Exception:  # noqa: BLE001
            return ""

        target_title = normalize_text(strip_noise(title))
        target_artist = normalize_text(primary_artist(artist))
        matched = None
        for song in songs:
            if normalize_text(strip_noise(song.get("title") or "")) != target_title:
                continue
            song_artist = normalize_text(primary_artist(song.get("artist") or song.get("albumArtist") or ""))
            if target_artist and song_artist and not (
                target_artist in song_artist or song_artist in target_artist
            ):
                continue
            matched = song
            break
        if not matched or not matched.get("id"):
            return ""

        sid = str(matched["id"])
        await execute(
            """INSERT INTO navidrome_index(track_key, artist, title, album, path, song_id, synced_at)
               VALUES(?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(track_key) DO UPDATE SET song_id=excluded.song_id, synced_at=excluded.synced_at""",
            (
                track_key,
                matched.get("artist") or artist,
                matched.get("title") or title,
                matched.get("album") or "",
                matched.get("path") or "",
                sid,
                now_iso(),
            ),
        )
        return sid

    async def _navidrome_playlist_names(self, cfg: NavidromeConfig) -> dict[str, str]:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(self._url(cfg, "getPlaylists"), params=self._auth(cfg))
                data = resp.json().get("subsonic-response", {})
                items = (data.get("playlists") or {}).get("playlist") or []
                return {item.get("name"): item.get("id") for item in items if item.get("id")}
        except Exception:  # noqa: BLE001
            return {}

    async def _upsert_playlist(
        self, cfg: NavidromeConfig, nav_id: str, name: str, song_ids: list[str]
    ) -> tuple[bool, str]:
        payload = list(self._auth(cfg).items())
        payload.append(("name", name))
        payload.extend(("songId", sid) for sid in song_ids[:500])
        if nav_id:
            payload.append(("playlistId", nav_id))
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(self._url(cfg, "createPlaylist"), data=payload)
                data = resp.json().get("subsonic-response", {})
                if data.get("status") != "ok":
                    if nav_id:
                        # 远端歌单已被删除，回退为新建
                        return await self._upsert_playlist(cfg, "", name, song_ids)
                    return False, ""
                playlist = data.get("playlist") or {}
                return True, playlist.get("id") or nav_id
        except Exception as exc:  # noqa: BLE001
            await hub.log("WARN", "navidrome", f"歌单《{name}》写入失败: {exc}")
            return False, ""

    def request_refresh(self, cfg: NavidromeConfig, delay: Optional[int] = None) -> None:
        """下载完成后延迟触发一次歌单刷新（同一时间只保留一个待执行任务）。"""
        if not cfg.enabled or not cfg.url or not cfg.sync_playlists:
            return
        if self._refresh_task and not self._refresh_task.done():
            return
        wait = cfg.playlist_refresh_delay_sec if delay is None else delay
        snapshot = cfg.model_copy(deep=True)
        self._refresh_task = asyncio.create_task(
            self._delayed_refresh(snapshot, wait), name="navidrome-playlist-refresh"
        )

    async def _delayed_refresh(self, cfg: NavidromeConfig, delay: int) -> None:
        try:
            await asyncio.sleep(max(5, delay))
            await self.refresh_playlists(cfg)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            await hub.log("WARN", "navidrome", f"延迟刷新 Navidrome 歌单失败: {exc}")

    async def start_scan(self, cfg: NavidromeConfig) -> tuple[bool, str]:
        if not cfg.enabled or not cfg.url:
            return False, "Navidrome 未启用"
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(self._url(cfg, "startScan"), params=self._auth(cfg))
                data = resp.json().get("subsonic-response", {})
                if data.get("status") == "ok":
                    await hub.log("INFO", "navidrome", "已触发 Navidrome 增量扫库")
                    return True, "已触发扫库"
                return False, str(data.get("error") or "触发失败")
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)

    @property
    def syncing(self) -> bool:
        return self._syncing


navidrome = NavidromeService()
