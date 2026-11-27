"""QQ 音乐榜单采集。"""
from __future__ import annotations

from .base import BaseCollector, RawTrack


class QQCollector(BaseCollector):
    platform = "qq"

    async def fetch_playlist(self, playlist: dict) -> list[RawTrack]:
        ext_id = playlist["ext_id"]
        url = "https://c.y.qq.com/v8/fcg-bin/fcg_v8_toplist_cp.fcg"
        data = await self.http.get_json(
            url,
            params={"topid": ext_id, "format": "json", "page": "detail", "type": "top", "song_num": 100},
            headers={"Referer": "https://y.qq.com/"},
        )
        song_list = data.get("songlist") or []
        rows: list[RawTrack] = []
        for index, wrapper in enumerate(song_list):
            song = wrapper.get("data") or wrapper
            name = song.get("songname") or song.get("title") or ""
            singers = song.get("singer") or []
            if isinstance(singers, dict):
                singers = [singers]
            artists = [s.get("name", "") for s in singers if s]
            album_name = song.get("albumname") or (song.get("album") or {}).get("name", "")
            album_mid = song.get("albummid") or (song.get("album") or {}).get("mid", "")
            cover = (
                f"https://y.gtimg.cn/music/photo_new/T002R300x300M000{album_mid}.jpg"
                if album_mid
                else ""
            )
            rows.append(
                RawTrack(
                    title=name,
                    artists=artists,
                    album=album_name,
                    rank=index + 1,
                    cover=cover,
                    extra={
                        "qq_songmid": song.get("songmid"),
                        "album_mid": album_mid,
                        "url": f"https://y.qq.com/n/ryqq/songDetail/{song.get('songmid', '')}",
                    },
                )
            )
        return rows
