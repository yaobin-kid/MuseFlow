"""上游 API 滑动窗口限流器与平台级冷却。"""
from __future__ import annotations

import asyncio
import random
import time
from collections import deque
from typing import Deque

from ..events import hub, push_cooldown, push_rate_limit


class SlidingWindowLimiter:
    """任意 window_sec 秒内最多 max_requests 次调用。"""

    def __init__(self, window_sec: int = 300, max_requests: int = 50) -> None:
        self.window_sec = window_sec
        self.max_requests = max_requests
        self._timestamps: Deque[float] = deque()
        self._lock = asyncio.Lock()

    def reconfigure(self, window_sec: int, max_requests: int) -> None:
        self.window_sec = max(1, window_sec)
        self.max_requests = max(1, max_requests)

    def _prune(self, now: float) -> None:
        while self._timestamps and self._timestamps[0] <= now - self.window_sec:
            self._timestamps.popleft()

    def usage(self) -> dict:
        now = time.time()
        self._prune(now)
        used = len(self._timestamps)
        reset_in = 0
        if self._timestamps:
            reset_in = max(0, int(round(self._timestamps[0] + self.window_sec - now)))
        return {
            "used": used,
            "max": self.max_requests,
            "remaining": max(0, self.max_requests - used),
            "window_sec": self.window_sec,
            "reset_in": reset_in,
            "percent": round(used / self.max_requests * 100, 1) if self.max_requests else 0,
        }

    async def wait_seconds(self) -> float:
        async with self._lock:
            now = time.time()
            self._prune(now)
            if len(self._timestamps) < self.max_requests:
                return 0.0
            return max(0.0, self._timestamps[0] + self.window_sec - now)

    async def acquire(self) -> None:
        while True:
            async with self._lock:
                now = time.time()
                self._prune(now)
                if len(self._timestamps) < self.max_requests:
                    self._timestamps.append(now)
                    usage = self.usage()
                    break
                wait = max(0.05, self._timestamps[0] + self.window_sec - now)
            await push_rate_limit({**self.usage(), "waiting": True, "wait_seconds": round(wait, 1)})
            await asyncio.sleep(wait)
        await push_rate_limit({**usage, "waiting": False})

    async def wait_until_available(self) -> None:
        """仅等待配额可用，不消耗令牌（用于前端展示）。"""
        wait = await self.wait_seconds()
        if wait <= 0:
            return
        remaining = int(wait)
        while remaining > 0:
            await push_rate_limit({**self.usage(), "waiting": True, "wait_seconds": remaining})
            step = min(1, remaining)
            await asyncio.sleep(step)
            remaining -= step


limiter = SlidingWindowLimiter()


def apply_rate_limit_config(window_sec: int, max_requests: int) -> None:
    limiter.reconfigure(window_sec, max_requests)


# ------------------------------------------------------------------ 平台冷却
_cooldown_state: dict[str, dict] = {}
_platform_locks: dict[str, asyncio.Lock] = {}


def platform_lock(platform: str) -> asyncio.Lock:
    if platform not in _platform_locks:
        _platform_locks[platform] = asyncio.Lock()
    return _platform_locks[platform]


def cooldown_snapshot() -> dict:
    return {platform: dict(state) for platform, state in _cooldown_state.items()}


async def cooldown(platform: str, base_sec: int, jitter_sec: int) -> None:
    total = max(0, base_sec) + random.randint(0, max(0, jitter_sec))
    if total <= 0:
        return
    await hub.log(
        "INFO",
        "cooldown",
        f"{platform} 平台进入冷却 {total}s（基础 {base_sec}s + 抖动）",
    )
    for remaining in range(total, 0, -1):
        _cooldown_state[platform] = {
            "platform": platform,
            "remaining": remaining,
            "total": total,
            "active": True,
        }
        await push_cooldown(_cooldown_state[platform])
        await asyncio.sleep(1)
    _cooldown_state[platform] = {"platform": platform, "remaining": 0, "total": total, "active": False}
    await push_cooldown(_cooldown_state[platform])
