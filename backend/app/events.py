"""实时事件中心：WebSocket 广播 + 日志环形缓冲。"""
from __future__ import annotations

import asyncio
import json
from collections import deque
from datetime import datetime, timezone
from typing import Any, Deque, Set

from fastapi import WebSocket

from .db import execute


def _ts() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class EventHub:
    def __init__(self) -> None:
        self._clients: Set[WebSocket] = set()
        self._logs: Deque[dict] = deque(maxlen=500)
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._clients.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(websocket)

    async def broadcast(self, event_type: str, data: Any) -> None:
        message = json.dumps({"type": event_type, "data": data, "ts": _ts()}, ensure_ascii=False, default=str)
        dead = []
        async with self._lock:
            clients = list(self._clients)
        for client in clients:
            try:
                await client.send_text(message)
            except Exception:
                dead.append(client)
        if dead:
            async with self._lock:
                for client in dead:
                    self._clients.discard(client)

    @property
    def client_count(self) -> int:
        return len(self._clients)

    def recent_logs(self, limit: int = 200) -> list[dict]:
        return list(self._logs)[-limit:]

    async def log(self, level: str, scope: str, message: str) -> None:
        entry = {"ts": _ts(), "level": level.upper(), "scope": scope, "message": message}
        self._logs.append(entry)
        print(f"[{entry['level']}] [{scope}] {message}")
        try:
            await execute(
                "INSERT INTO logs(ts, level, scope, message) VALUES(?, ?, ?, ?)",
                (entry["ts"], entry["level"], scope, message),
            )
        except Exception:
            pass
        await self.broadcast("log", entry)


hub = EventHub()


async def push_rate_limit(usage: dict) -> None:
    await hub.broadcast("rate_limit", usage)


async def push_cooldown(payload: dict) -> None:
    await hub.broadcast("cooldown", payload)


async def push_task(payload: dict) -> None:
    await hub.broadcast("task", payload)


async def push_pipeline(payload: dict) -> None:
    await hub.broadcast("pipeline", payload)
