"""采集器工厂。"""
from __future__ import annotations

from ..config import RuntimeConfig
from .apple import AppleCollector
from .base import BaseCollector
from .demo import DemoCollector
from .netease import NeteaseCollector
from .qq import QQCollector
from .spotify import SpotifyCollector


class DemoModeCollector(BaseCollector):
    """演示模式包装器：对任意平台返回演示数据。"""

    def __init__(self, cfg: RuntimeConfig, platform: str) -> None:
        self._inner = DemoCollector(cfg, platform)
        self.platform = platform
        self.cfg = cfg

    async def fetch_playlist(self, playlist: dict):
        return await self._inner.fetch_playlist(playlist)


_COLLECTORS = {
    "netease": NeteaseCollector,
    "qq": QQCollector,
    "spotify": SpotifyCollector,
    "apple": AppleCollector,
}


def get_collector(platform: str, cfg: RuntimeConfig, demo: bool = False) -> BaseCollector:
    if demo:
        return DemoModeCollector(cfg, platform)
    cls = _COLLECTORS.get(platform)
    if cls is None:
        raise ValueError(f"未知平台: {platform}")
    return cls(cfg)
