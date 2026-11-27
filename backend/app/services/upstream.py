"""上游聚合搜索/下载服务客户端。"""
from __future__ import annotations

import os
import shutil
import urllib.parse
from typing import Optional

import httpx

from ..config import UpstreamConfig
from ..events import hub
from .normalize import sanitize_filename


class UpstreamService:
    def __init__(self, cfg: UpstreamConfig) -> None:
        self.cfg = cfg

    def reconfigure(self, cfg: UpstreamConfig) -> None:
        self.cfg = cfg

    def _client(self, timeout: float | None = None) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.cfg.base_url.rstrip("/"),
            timeout=httpx.Timeout(timeout or self.cfg.timeout_sec, connect=20.0),
            follow_redirects=True,
            headers={"User-Agent": "MuseFlow/1.0"},
        )

    # ---------------------------------------------------------------- 搜索
    async def search(self, source: str, name: str, pages: int = 1) -> list[dict]:
        async with self._client() as client:
            resp = await client.get("/api/search", params={"source": source, "name": name, "pages": pages})
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict):
                data = data.get("data") or data.get("result") or []
            return data if isinstance(data, list) else []

    async def search_multi(self, name: str) -> list[dict]:
        """按配置的音源顺序聚合搜索，返回带 _source_order 的结果。"""
        results: list[dict] = []
        errors: list[str] = []
        for source in self.cfg.source_order:
            try:
                items = await self.search(source, name)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{source}: {exc}")
                continue
            for item in items[:30]:
                item["_searched_source"] = source
            results.extend(items[:30])
            if len(results) >= 60:
                break
        if errors:
            await hub.log("WARN", "upstream", "部分音源搜索失败: " + "; ".join(errors[:3]))
        return results

    # ---------------------------------------------------------------- 下载
    async def download(self, item: dict, temp_dir: str) -> tuple[dict, Optional[str]]:
        payload = {
            "source": item.get("source") or item.get("_searched_source") or "",
            "id": str(item.get("id") or ""),
            "name": item.get("name") or "",
            "artist": _artist_str(item.get("artist")),
            "album": item.get("album") or "",
            "pic_id": item.get("pic_id") or "",
            "br": self.cfg.preferred_bitrate,
            "lyric": True,
            "vip": False,
        }
        os.makedirs(temp_dir, exist_ok=True)
        async with self._client(timeout=max(self.cfg.timeout_sec, 120)) as client:
            resp = await client.post("/api/download", json=payload)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")

            if not content_type.startswith("application/json"):
                ext = _guess_ext(content_type, payload["name"])
                filename = sanitize_filename(f"{payload['artist']} - {payload['name']}") + ext
                path = os.path.join(temp_dir, filename)
                with open(path, "wb") as fh:
                    fh.write(resp.content)
                return {"status": "success", "filename": filename, "content_type": content_type}, path

            meta = resp.json()
            if isinstance(meta, dict) and meta.get("status") not in (None, "success"):
                raise RuntimeError(meta.get("message") or meta.get("msg") or "上游下载失败")
            filename = (meta or {}).get("filename") or ""
            path = None
            if filename:
                path = self._copy_local(filename, temp_dir) or await self._try_fetch_file(
                    client, filename, temp_dir
                )
            return meta if isinstance(meta, dict) else {"raw": meta}, path

    def _copy_local(self, filename: str, temp_dir: str) -> Optional[str]:
        """内置上游（同容器）直接读取其下载目录，避免依赖 /music 的 HTTP 路由。"""
        base = (self.cfg.local_download_dir or "").strip()
        if not base or not filename:
            return None
        source = os.path.join(base, os.path.basename(filename))
        if not os.path.isfile(source):
            return None
        try:
            os.makedirs(temp_dir, exist_ok=True)
            target = os.path.join(temp_dir, sanitize_filename(filename))
            shutil.copyfile(source, target)
            return target
        except Exception:  # noqa: BLE001
            return None

    async def _try_fetch_file(self, client: httpx.AsyncClient, filename: str, temp_dir: str) -> Optional[str]:
        url = self.cfg.file_path_template.format(filename=urllib.parse.quote(filename))
        try:
            async with client.stream("GET", url) as resp:
                if resp.status_code != 200:
                    await hub.log("WARN", "upstream", f"上游文件获取失败（{resp.status_code}）: {url}")
                    return None
                path = os.path.join(temp_dir, sanitize_filename(filename))
                with open(path, "wb") as fh:
                    async for chunk in resp.aiter_bytes(65536):
                        fh.write(chunk)
                return path
        except Exception as exc:  # noqa: BLE001
            await hub.log("WARN", "upstream", f"上游文件获取异常: {exc}")
            return None

    async def lyric(self, item: dict, temp_dir: str) -> Optional[str]:
        payload = {
            "source": item.get("source") or item.get("_searched_source") or "",
            "id": str(item.get("id") or ""),
            "name": item.get("name") or "",
            "artist": _artist_str(item.get("artist")),
            "vip": False,
        }
        try:
            async with self._client() as client:
                resp = await client.post(self.cfg.lyric_path, json=payload)
                resp.raise_for_status()
                data = resp.json()
                filename = (data or {}).get("filename") or ""
                if filename:
                    path = self._copy_local(filename, temp_dir) or await self._try_fetch_file(
                        client, filename, temp_dir
                    )
                    if path:
                        return path
        except Exception as exc:  # noqa: BLE001
            await hub.log("WARN", "upstream", f"歌词下载失败: {exc}")
        return None

    # ---------------------------------------------------------------- 封面
    async def fetch_cover(self, item: dict) -> Optional[bytes]:
        """调用上游封面数据 API，返回封面图片字节。"""
        source = item.get("source") or item.get("_searched_source") or ""
        cover_id = item.get("pic_id") or item.get("id")
        if not source or not cover_id:
            return None
        try:
            async with self._client(timeout=20) as client:
                resp = await client.get(
                    self.cfg.cover_path, params={"source": source, "id": str(cover_id)}
                )
                content_type = resp.headers.get("content-type", "")
                if resp.status_code == 200 and content_type.startswith("image"):
                    return resp.content
                if resp.status_code == 200 and "json" in content_type:
                    data = resp.json()
                    url = data.get("url") if isinstance(data, dict) else ""
                    if isinstance(url, str) and url.startswith("http"):
                        image = await client.get(url)
                        if image.status_code == 200:
                            return image.content
        except Exception as exc:  # noqa: BLE001
            await hub.log("WARN", "upstream", f"封面获取失败: {exc}")
        return None

    # ---------------------------------------------------------------- 匹配
    def pick_best_match(self, items: list[dict], title: str, artist: str) -> Optional[dict]:
        from .normalize import normalize_text, primary_artist, strip_noise

        target_title = normalize_text(strip_noise(title))
        target_artist = normalize_text(primary_artist(artist))
        best = None
        best_score = -1
        for item in items:
            item_title = normalize_text(strip_noise(item.get("name") or ""))
            item_artist = normalize_text(primary_artist(_artist_str(item.get("artist"))))
            score = 0
            if item_title == target_title:
                score += 60
            elif target_title and target_title in item_title:
                score += 35
            else:
                continue
            if target_artist and item_artist == target_artist:
                score += 40
            elif target_artist and (target_artist in item_artist or item_artist in target_artist):
                score += 20
            if score > best_score:
                best_score = score
                best = item
        return best if best_score >= 55 else None


def _artist_str(value) -> str:
    if isinstance(value, list):
        return " / ".join([v for v in value if v])
    return value or ""


def _guess_ext(content_type: str, name: str) -> str:
    if "flac" in content_type:
        return ".flac"
    if "mpeg" in content_type or "mp3" in content_type:
        return ".mp3"
    if "mp4" in content_type or "m4a" in content_type:
        return ".m4a"
    return ".flac"
