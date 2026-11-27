"""内置平台与歌单目录。"""
from __future__ import annotations

from ..config import spotify_playlists_from_env

PLATFORM_META: dict[str, dict] = {
    "netease": {"name": "网易云音乐", "region": "CN", "color": "#e60026", "badge": "NE"},
    "qq": {"name": "QQ 音乐", "region": "CN", "color": "#31c27c", "badge": "QQ"},
    "spotify": {"name": "Spotify 全球", "region": "Global", "color": "#1db954", "badge": "SP"},
    "apple": {"name": "Apple Music 全球", "region": "Global", "color": "#fa243c", "badge": "AM"},
}

PLATFORM_ORDER = ["netease", "qq", "spotify", "apple"]

# (ext_id, 名称, 描述, 是否默认纳入调度)
NETEASE_PLAYLISTS = [
    ("3778678", "热歌榜", "网易云音乐全站最热单曲排行", True),
    ("19723756", "飙升榜", "近期播放增速最快的单曲", False),
    ("3779629", "新歌榜", "最新上架的高热度新歌", True),
    ("2884035", "原创榜", "原创音乐人榜单", False),
    ("991319590", "说唱榜", "云音乐说唱音乐榜单", False),
]

QQ_PLAYLISTS = [
    ("26", "热歌榜", "QQ 音乐全站热播榜", True),
    ("62", "飙升榜", "QQ 音乐飙升榜", False),
    ("4", "新歌榜", "QQ 音乐新歌榜", True),
    ("27", "原创榜", "QQ 音乐原创榜", False),
    ("3", "美国 Billboard 榜", "Billboard Hot 100 榜单", True),
    ("5", "英国 UK 榜", "英国官方单曲榜", False),
    ("6", "日本榜", "日本 Oricon 热门单曲", False),
    ("16", "韩国榜", "韩国热门单曲榜", False),
    ("17", "香港榜", "香港地区热门单曲", False),
    ("18", "台湾榜", "台湾地区热门单曲", False),
    ("19", "内地榜", "内地热门单曲榜", False),
]

APPLE_MARKETS = [
    ("us", "美国 Top 50", "Apple Music 美国每日热播榜", True),
    ("gb", "英国 Top 50", "Apple Music 英国每日热播榜", True),
    ("hk", "香港 Top 50", "Apple Music 香港每日热播榜", True),
    ("tw", "台湾 Top 50", "Apple Music 台湾每日热播榜", True),
    ("jp", "日本 Top 50", "Apple Music 日本每日热播榜", False),
    ("kr", "韩国 Top 50", "Apple Music 韩国每日热播榜", False),
    ("sg", "新加坡 Top 50", "Apple Music 新加坡每日热播榜", False),
    ("ca", "加拿大 Top 50", "Apple Music 加拿大每日热播榜", False),
    ("au", "澳大利亚 Top 50", "Apple Music 澳大利亚每日热播榜", False),
]

SPOTIFY_DEFAULT_SCHEDULED = {
    "37i9dQZEVXbMDoHDwVN2tF",
    "37i9dQZEVXbLRQDuF5jeBp",
    "37i9dQZEVXbLnolsZ8PSNw",
    "37i9dQZEVXbMnZEatlmmwA",
    "37i9dQZEVXbL0GavIqMTeb",
}


def builtin_playlists() -> list[dict]:
    result: list[dict] = []
    for ext_id, name, desc, scheduled in NETEASE_PLAYLISTS:
        result.append(
            {
                "platform": "netease",
                "ext_id": ext_id,
                "name": name,
                "description": desc,
                "url": f"https://music.163.com/#/discover/toplist?id={ext_id}",
                "source_kind": "chart",
                "default_scheduled": scheduled,
            }
        )
    for ext_id, name, desc, scheduled in QQ_PLAYLISTS:
        result.append(
            {
                "platform": "qq",
                "ext_id": ext_id,
                "name": name,
                "description": desc,
                "url": f"https://y.qq.com/n/ryqq/toplist/{ext_id}",
                "source_kind": "chart",
                "default_scheduled": scheduled,
            }
        )
    for item in spotify_playlists_from_env():
        result.append(
            {
                "platform": "spotify",
                "ext_id": item["id"],
                "name": item.get("name") or item["id"],
                "description": item.get("description", "Spotify 官方 Top 50 热门榜单"),
                "url": f"https://open.spotify.com/playlist/{item['id']}",
                "source_kind": "chart",
                "default_scheduled": item["id"] in SPOTIFY_DEFAULT_SCHEDULED,
            }
        )
    for ext_id, name, desc, scheduled in APPLE_MARKETS:
        result.append(
            {
                "platform": "apple",
                "ext_id": ext_id,
                "name": name,
                "description": desc,
                "url": f"https://music.apple.com/{ext_id}/charts",
                "source_kind": "chart",
                "default_scheduled": scheduled,
            }
        )
    return result
