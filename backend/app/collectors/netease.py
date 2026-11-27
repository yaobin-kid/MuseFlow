"""网易云音乐榜单采集。"""
from __future__ import annotations

from .base import BaseCollector, RawTrack


class NeteaseCollector(BaseCollector):
    platform = "netease"

    async def fetch_playlist(self, playlist: dict) -> list[RawTrack]:
        ext_id = playlist["ext_id"]
        url = "https://music.163.com/api/playlist/detail"
        data = await self.http.get_json(
            url,
            params={"id": ext_id},
            headers={"Referer": "https://music.163.com/"},
        )
        result = data.get("result") or data.get("playlist") or {}
        playlist_obj = result.get("playlist") if isinstance(result.get("playlist"), dict) else result
        tracks = playlist_obj.get("tracks") or result.get("tracks") or []
        result_rows: list[RawTrack] = []
        for index, item in enumerate(tracks):
            name = item.get("name") or ""
            artists = [a.get("name", "") for a in (item.get("ar") or item.get("artists") or []) if a]
            album_obj = item.get("al") or item.get("album") or {}
            release = ""
            cover = ""
            if isinstance(album_obj, dict):
                release = str(album_obj.get("publishTime") or "")
                cover = album_obj.get("picUrl") or ""
            result_rows.append(
                RawTrack(
                    title=name,
                    artists=artists,
                    album=(album_obj or {}).get("name", "") if isinstance(album_obj, dict) else "",
                    rank=index + 1,
                    cover=cover,
                    extra={"netease_id": item.get("id"), "url": f"https://music.163.com/song?id={item.get('id')}"},
                )
            )
        return result_rows
