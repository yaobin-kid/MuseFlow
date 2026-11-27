"""Apple Music 港台榜单采集（官方 RSS Marketing Tools）。"""
from __future__ import annotations

from .base import BaseCollector, RawTrack

_FEEDS = [
    "https://rss.marketingtools.apple.com/api/v2/{market}/music/most-played/{limit}/songs.json",
    "https://rss.applemarketingtools.com/api/v2/{market}/music/most-played/{limit}/songs.json",
]


class AppleCollector(BaseCollector):
    platform = "apple"

    async def fetch_playlist(self, playlist: dict) -> list[RawTrack]:
        market = playlist["ext_id"]
        last_error: Exception | None = None
        data = None
        for template in _FEEDS:
            try:
                data = await self.http.get_json(template.format(market=market, limit=50))
                break
            except Exception as exc:  # noqa: BLE001
                last_error = exc
        if data is None:
            raise last_error or RuntimeError("Apple 榜单获取失败")
        results = (data.get("feed") or {}).get("results") or []
        rows: list[RawTrack] = []
        for index, item in enumerate(results):
            artwork = item.get("artworkUrl100", "") or ""
            cover = artwork.replace("100x100", "400x400").replace("100x100bb", "400x400bb") if artwork else ""
            rows.append(
                RawTrack(
                    title=item.get("name", ""),
                    artists=[item.get("artistName", "")] if item.get("artistName") else [],
                    album=item.get("albumName", "") or "",
                    release_date=item.get("releaseDate", "") or "",
                    rank=index + 1,
                    cover=cover,
                    extra={"url": item.get("url", ""), "artwork": artwork},
                )
            )
        return rows
