"""平台采集器基类与网络辅助。"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from ..config import NetworkConfig, RuntimeConfig
from ..events import hub


@dataclass
class RawTrack:
    title: str
    artists: list[str]
    album: str = ""
    isrc: str = ""
    release_date: str = ""
    rank: int = 0
    cover: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


class PlatformHttp:
    """按平台分流代理，并在被盾拦截时回退到 FlareSolverr。"""

    def __init__(self, platform: str, cfg: RuntimeConfig) -> None:
        self.platform = platform
        self.cfg: RuntimeConfig = cfg
        self.network: NetworkConfig = cfg.network

    def _proxy(self) -> Optional[str]:
        if not self.network.proxy_url:
            return None
        if self.network.platform_use_proxy.get(self.platform, False):
            return self.network.proxy_url
        return None

    async def _client(self) -> httpx.AsyncClient:
        proxy = self._proxy()
        return httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=15.0),
            follow_redirects=True,
            proxy=proxy,
            headers={"User-Agent": _UA},
        )

    async def get_json(self, url: str, params: dict | None = None, headers: dict | None = None) -> Any:
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                async with await self._client() as client:
                    resp = await client.get(url, params=params, headers=headers or {})
                    if resp.status_code in (403, 429, 503):
                        text = await self._try_flaresolverr(url)
                        if text:
                            return _maybe_json(text)
                        resp.raise_for_status()
                    resp.raise_for_status()
                    return resp.json()
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt == 0 and self.network.flaresolverr_enabled:
                    text = await self._try_flaresolverr(url)
                    if text:
                        return _maybe_json(text)
                await asyncio.sleep(1.5)
        raise last_error or RuntimeError("请求失败")

    async def get_text(self, url: str, headers: dict | None = None) -> str:
        async with await self._client() as client:
            resp = await client.get(url, headers=headers or {})
            resp.raise_for_status()
            return resp.text

    async def _try_flaresolverr(self, url: str) -> Optional[str]:
        if not self.network.flaresolverr_enabled or not self.network.flaresolverr_url:
            return None
        await hub.log("INFO", self.platform, f"触发 FlareSolverr 过盾：{url}")
        try:
            async with httpx.AsyncClient(timeout=self.network.flaresolverr_timeout_sec + 15) as client:
                resp = await client.post(
                    self.network.flaresolverr_url,
                    json={
                        "cmd": "request.get",
                        "url": url,
                        "maxTimeout": self.network.flaresolverr_timeout_sec * 1000,
                    },
                )
                data = resp.json()
                return (data.get("solution") or {}).get("response")
        except Exception as exc:  # noqa: BLE001
            await hub.log("WARN", self.platform, f"FlareSolverr 调用失败：{exc}")
            return None


def _maybe_json(text: str) -> Any:
    import json

    try:
        return json.loads(text)
    except Exception:
        return text


_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class BaseCollector:
    platform: str = ""

    def __init__(self, cfg: RuntimeConfig) -> None:
        self.cfg = cfg
        self.http = PlatformHttp(self.platform, cfg)

    async def fetch_playlist(self, playlist: dict) -> list[RawTrack]:  # pragma: no cover - 抽象方法
        raise NotImplementedError

    async def check(self) -> tuple[bool, str]:
        return True, ""
