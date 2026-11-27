"""WebSocket 实时推送。"""
from __future__ import annotations

import json

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from ..db import get_runtime_config
from ..events import hub
from ..repo import list_logs
from ..security import authenticate_ws_token
from ..services.navidrome import navidrome
from ..services.pipeline import is_running
from ..services.rate_limiter import cooldown_snapshot, limiter

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str | None = Query(default=None)) -> None:
    if not authenticate_ws_token(token):
        await websocket.close(code=4401)
        return
    await hub.connect(websocket)
    cfg = get_runtime_config()
    snapshot = {
        "rate_limit": limiter.usage(),
        "cooldown": cooldown_snapshot(),
        "pipeline_running": is_running(),
        "logs": await list_logs(60),
        "navidrome": {"enabled": cfg.navidrome.enabled, "index_size": navidrome.index_size()},
    }
    await websocket.send_text(json.dumps({"type": "init", "data": snapshot}, ensure_ascii=False))
    try:
        while True:
            message = await websocket.receive_text()
            if message == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await hub.disconnect(websocket)
