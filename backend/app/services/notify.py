"""Webhook 通知。"""
from __future__ import annotations

import httpx

from ..config import WebhookConfig
from ..db import get_runtime_config
from ..events import hub


async def notify(event: str, title: str, message: str, data: dict | None = None) -> None:
    cfg: WebhookConfig = get_runtime_config().webhook
    if not cfg.enabled or not cfg.url:
        return
    if cfg.events and event not in cfg.events:
        return

    text = f"{title}\n{message}"
    payload: dict
    if cfg.type == "telegram":
        payload = {"text": text, "parse_mode": "HTML"}
    elif cfg.type == "bark":
        payload = {"title": title, "body": message}
    elif cfg.type in ("wecom", "dingtalk"):
        payload = {"msgtype": "text", "text": {"content": text}}
    elif cfg.type == "discord":
        payload = {"content": text}
    else:
        payload = {"event": event, "title": title, "message": message, "data": data or {}}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(cfg.url, json=payload)
            if resp.status_code >= 400:
                await hub.log("WARN", "webhook", f"通知发送失败 {resp.status_code}: {resp.text[:200]}")
    except Exception as exc:  # noqa: BLE001
        await hub.log("WARN", "webhook", f"通知发送异常: {exc}")
