"""下载后处理：标签补全、封面刮削、标准化目录与原子移动。"""
from __future__ import annotations

import os
import shutil
from typing import Optional

import httpx

from ..events import hub
from .normalize import sanitize_filename


def _read_tags(path: str) -> dict:
    try:
        from mutagen import File as MutagenFile

        audio = MutagenFile(path, easy=True)
        if not audio:
            return {}
        tags = audio.tags or {}
        return {k: (v[0] if isinstance(v, list) and v else v) for k, v in tags.items()}
    except Exception:
        return {}


async def _fetch_cover(artist: str, album: str) -> Optional[bytes]:
    if not artist:
        return None
    query = f"{artist} {album}".strip()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://itunes.apple.com/search",
                params={"term": query, "entity": "album", "limit": 1},
            )
            results = resp.json().get("results") or []
            if not results:
                return None
            artwork = results[0].get("artworkUrl100") or ""
            artwork = artwork.replace("100x100", "600x600")
            if not artwork:
                return None
            img = await client.get(artwork)
            if img.status_code == 200:
                return img.content
    except Exception:
        return None
    return None


def _has_embedded_cover(path: str) -> bool:
    try:
        ext = os.path.splitext(path)[1].lower()
        if ext == ".flac":
            from mutagen.flac import FLAC

            return bool(FLAC(path).pictures)
        if ext == ".mp3":
            from mutagen.id3 import ID3

            return any(frame.FrameID == "APIC" for frame in ID3(path).values())
        if ext in (".m4a", ".mp4"):
            from mutagen.mp4 import MP4

            return bool(MP4(path).tags and MP4(path).tags.get("covr"))
    except Exception:
        return False
    return False


def _embed_cover(path: str, data: bytes) -> None:
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".flac":
            from mutagen.flac import FLAC, Picture

            audio = FLAC(path)
            pic = Picture()
            pic.type = 3
            pic.mime = "image/jpeg"
            pic.desc = "Cover"
            pic.data = data
            audio.clear_pictures()
            audio.add_picture(pic)
            audio.save()
        elif ext == ".mp3":
            from mutagen.id3 import APIC, ID3

            tags = ID3(path)
            tags.delall("APIC")
            tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=data))
            tags.save(path)
        elif ext in (".m4a", ".mp4"):
            from mutagen.mp4 import MP4, MP4Cover

            audio = MP4(path)
            if audio.tags is None:
                audio.add_tags()
            audio.tags["covr"] = [MP4Cover(data, imageformat=MP4Cover.FORMAT_JPEG)]
            audio.save()
    except Exception as exc:  # noqa: BLE001
        _ = exc


def _write_text_tags(path: str, title: str, artist: str, album: str) -> None:
    try:
        from mutagen import File as MutagenFile

        audio = MutagenFile(path, easy=True)
        if not audio:
            return
        if audio.tags is None:
            try:
                audio.add_tags()
            except Exception:
                return
        audio.tags["title"] = [title]
        audio.tags["artist"] = [artist]
        if album:
            audio.tags["album"] = [album]
        audio.save()
    except Exception as exc:  # noqa: BLE001
        _ = exc


def _quality_of(path: str, meta: dict) -> str:
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    if ext == "flac":
        return "FLAC"
    bitrate = str((meta or {}).get("bitrate") or "")
    if ext == "mp3":
        return f"MP3 {bitrate}k" if bitrate and bitrate != "999" else "MP3 320k"
    return ext.upper() or "UNKNOWN"


async def post_process(
    *,
    temp_path: Optional[str],
    title: str,
    artist: str,
    album: str,
    temp_dir: str,
    final_dir: str,
    lyric_path: Optional[str] = None,
    cover_bytes: Optional[bytes] = None,
    upstream_meta: dict | None = None,
) -> dict:
    """整理并移动文件，返回 {final_path, quality, cover, lyrics}。"""
    meta = upstream_meta or {}
    if not temp_path or not os.path.exists(temp_path):
        raise FileNotFoundError("下载文件不存在，无法进行整理（上游可能未返回音频文件）")

    tags = _read_tags(temp_path)
    title = title or tags.get("title") or os.path.splitext(os.path.basename(temp_path))[0]
    artist = artist or tags.get("artist") or "未知艺术家"
    album = album or tags.get("album") or "未知专辑"

    _write_text_tags(temp_path, title, artist, album)

    cover_saved = False
    cover_data = cover_bytes
    has_cover = _has_embedded_cover(temp_path)
    if not cover_data and not has_cover:
        cover_data = await _fetch_cover(artist, album)
    if cover_data:
        if not has_cover:
            _embed_cover(temp_path, cover_data)
        cover_saved = True

    artist_dir = sanitize_filename(artist, "未知艺术家")
    album_dir = sanitize_filename(album, "未知专辑")
    ext = os.path.splitext(temp_path)[1] or ".flac"
    filename = sanitize_filename(title, "未命名") + ext
    target_dir = os.path.join(final_dir, artist_dir, album_dir)
    os.makedirs(target_dir, exist_ok=True)
    target_path = os.path.join(target_dir, filename)

    if cover_saved and cover_data:
        try:
            with open(os.path.join(target_dir, "cover.jpg"), "wb") as fh:
                fh.write(cover_data)
        except Exception:
            pass

    if os.path.exists(target_path):
        os.remove(temp_path)
        await hub.log("INFO", "postprocess", f"目标已存在，跳过覆盖：{target_path}")
    else:
        shutil.move(temp_path, target_path)

    lyrics_saved = False
    if lyric_path and os.path.exists(lyric_path):
        try:
            lrc_target = os.path.join(target_dir, sanitize_filename(title, "未命名") + ".lrc")
            shutil.move(lyric_path, lrc_target)
            lyrics_saved = True
        except Exception:
            pass

    await hub.log("INFO", "postprocess", f"整理完成：{target_path}")
    return {
        "final_path": target_path,
        "quality": _quality_of(target_path, meta),
        "cover": cover_saved,
        "lyrics": lyrics_saved,
    }
