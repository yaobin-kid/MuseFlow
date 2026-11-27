"""元数据标准化：繁简转换、去噪、指纹生成。"""
from __future__ import annotations

import re
import unicodedata
from typing import Iterable

try:  # opencc 为可选依赖，缺失时降级为原文
    from opencc import OpenCC

    _cc = OpenCC("t2s")
except Exception:  # pragma: no cover
    _cc = None


# 需要剥离的版本/噪音标签
_NOISE_PATTERNS = [
    r"[\(\（\[\【]\s*(live|现场|演唱会|伴奏|纯音乐|instrumental|karaoke|remix|dj版|dj|remaster(ed)?|"
    r"无损|hi-?res|flac|320k|高音质|原唱|翻唱|片段|铃声|抖音|正式版|电视|电影|剧集|主题曲|插曲|片尾曲|"
    r"ost|feat\.?[^\)\】\]]*|ft\.?[^\)\】\]]*)[^\)\】\]]*[\)\）\]\】]",
    r"[\-\s]+\s*(live|remix|伴奏|纯音乐|instrumental|remastered|dj版)\s*$",
    r"[\-\s]+\s*(feat\.?|ft\.?)\s+.+$",
]
_NOISE_RE = [re.compile(p, flags=re.IGNORECASE) for p in _NOISE_PATTERNS]

_FULLWIDTH = str.maketrans(
    "０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ",
    "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
)


def to_simplified(text: str) -> str:
    if not text:
        return ""
    if _cc is not None:
        try:
            return _cc.convert(text)
        except Exception:
            return text
    return text


def strip_noise(title: str) -> str:
    if not title:
        return ""
    text = title
    for pattern in _NOISE_RE:
        text = pattern.sub("", text)
    # 去掉多余空白与首尾分隔符
    text = re.sub(r"\s{2,}", " ", text).strip(" -_·|")
    return text


def normalize_text(text: str) -> str:
    """用于指纹比对：繁简统一、全半角统一、去标点、小写。"""
    if not text:
        return ""
    text = to_simplified(text)
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(_FULLWIDTH)
    text = text.lower()
    # 保留中日韩、字母、数字
    text = re.sub(r"[^\u4e00-\u9fffa-z0-9]+", "", text)
    return text


def primary_artist(artists: Iterable[str] | str) -> str:
    if isinstance(artists, str):
        parts = re.split(r"\s*(?:/|&|、|,|;|\bfeat\.?\b|\bft\.?\b)\s*", artists, flags=re.IGNORECASE)
    else:
        parts = list(artists)
    parts = [p for p in (part.strip() for part in parts) if p]
    return parts[0] if parts else ""


def joined_artist(artists: Iterable[str] | str) -> str:
    if isinstance(artists, str):
        return artists.strip()
    return " / ".join([a.strip() for a in artists if a and a.strip()])


def make_track_key(artists: Iterable[str] | str, title: str, isrc: str = "") -> str:
    if isrc:
        return f"isrc:{isrc.strip().upper()}"
    artist = normalize_text(primary_artist(artists))
    song = normalize_text(strip_noise(title))
    return f"{artist}::{song}"


def display_title(title: str) -> str:
    return re.sub(r"\s{2,}", " ", to_simplified(title or "")).strip()


def sanitize_filename(name: str, fallback: str = "unknown") -> str:
    name = (name or "").strip()
    name = re.sub(r'[\\/:*?"<>|\r\n\t]', "_", name)
    name = name.strip(" .")
    return name or fallback
