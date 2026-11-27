"""Spotify 港台榜单采集（Client Credentials 授权）。"""
from __future__ import annotations

import time

from ..config import settings
from .base import BaseCollector, RawTrack


class SpotifyCollector(BaseCollector):
    platform = "spotify"

    def __init__(self, cfg) -> None:
        super().__init__(cfg)
        self._token: str = ""
        self._token_expire: float = 0.0
        self._token_failed: bool = False

    async def _access_token(self) -> str:
        if self._token and time.time() < self._token_expire - 30:
            return self._token
        if self._token_failed or not settings.spotify_client_id or not settings.spotify_client_secret:
            raise RuntimeError("未配置 SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET")
        async with await self.http._client() as client:
            resp = await client.post(
                "https://accounts.spotify.com/api/token",
                data={"grant_type": "client_credentials"},
                auth=(settings.spotify_client_id, settings.spotify_client_secret),
            )
            if resp.status_code != 200:
                self._token_failed = True
                raise RuntimeError(f"Spotify 授权失败: {resp.status_code}")
            payload = resp.json()
            self._token = payload["access_token"]
            self._token_expire = time.time() + int(payload.get("expires_in", 3600))
            return self._token

    async def fetch_playlist(self, playlist: dict) -> list[RawTrack]:
        token = await self._access_token()
        playlist_id = playlist["ext_id"]
        url = f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks"
        data = await self.http.get_json(
            url,
            params={"limit": 100, "market": settings.spotify_market, "additional_types": "track"},
            headers={"Authorization": f"Bearer {token}"},
        )
        items = data.get("items") or []
        rows: list[RawTrack] = []
        rank = 0
        for item in items:
            track = item.get("track") or {}
            if not track:
                continue
            rank += 1
            artists = [a.get("name", "") for a in (track.get("artists") or []) if a]
            album = track.get("album") or {}
            images = album.get("images") or []
            cover = images[0].get("url", "") if images else ""
            rows.append(
                RawTrack(
                    title=track.get("name", ""),
                    artists=artists,
                    album=album.get("name", ""),
                    release_date=album.get("release_date", "") or "",
                    rank=rank,
                    cover=cover,
                    extra={"url": (track.get("external_urls") or {}).get("spotify", ""), "spotify_id": track.get("id")},
                )
            )
        return rows
