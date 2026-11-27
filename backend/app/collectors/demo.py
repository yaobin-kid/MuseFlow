"""演示数据采集器：无外网环境下也能完整体验控制台。"""
from __future__ import annotations

import urllib.parse

from .base import BaseCollector, RawTrack

# 中英混合的示例曲目（交错排列，保证各平台榜单都能覆盖到英文热门）
DEMO_SONGS = [
    ("晴天", "周杰伦", "叶惠美"),
    ("Anti-Hero", "Taylor Swift", "Midnights"),
    ("稻香", "周杰伦", "魔杰座"),
    ("Blank Space", "Taylor Swift", "1989"),
    ("七里香", "周杰伦", "七里香"),
    ("Cruel Summer", "Taylor Swift", "Lover"),
    ("告白气球", "周杰伦", "周杰伦的床边故事"),
    ("Shape of You", "Ed Sheeran", "÷ (Divide)"),
    ("句号", "G.E.M. 邓紫棋", "启示录"),
    ("Perfect", "Ed Sheeran", "÷ (Divide)"),
    ("光年之外", "G.E.M. 邓紫棋", "光年之外"),
    ("Blinding Lights", "The Weeknd", "After Hours"),
    ("倒数", "G.E.M. 邓紫棋", "倒数"),
    ("Save Your Tears", "The Weeknd", "After Hours"),
    ("孤勇者", "陈奕迅", "孤勇者"),
    ("Levitating", "Dua Lipa", "Future Nostalgia"),
    ("十年", "陈奕迅", "黑白灰"),
    ("As It Was", "Harry Styles", "Harry's House"),
    ("富士山下", "陈奕迅", "What's Going On...?"),
    ("Birds of a Feather", "Billie Eilish", "HIT ME HARD AND SOFT"),
    ("起风了", "买辣椒也用券", "起风了"),
    ("Yellow", "Coldplay", "Parachutes"),
    ("芒种", "音阙诗听", "芒种"),
    ("Easy On Me", "Adele", "30"),
    ("白月光与朱砂痣", "大籽", "白月光与朱砂痣"),
    ("Just the Way You Are", "Bruno Mars", "Doo-Wops & Hooligans"),
    ("漠河舞厅", "柳爽", "漠河舞厅"),
    ("vampire", "Olivia Rodrigo", "GUTS"),
    ("星辰大海", "黄霄雲", "星辰大海"),
    ("Espresso", "Sabrina Carpenter", "Espresso"),
    ("这世界那么多人", "莫文蔚", "这世界那么多人"),
    ("Flowers", "Miley Cyrus", "Endless Summer Vacation"),
    ("如愿", "王菲", "如愿"),
    ("bad guy", "Billie Eilish", "WHEN WE ALL FALL ASLEEP, WHERE DO WE GO?"),
    ("人世间", "雷佳", "人世间"),
    ("Shallow", "Lady Gaga / Bradley Cooper", "A Star Is Born"),
    ("海阔天空", "Beyond", "乐与怒"),
    ("Someone Like You", "Adele", "21"),
    ("光辉岁月", "Beyond", "命运派对"),
    ("Stay", "The Kid LAROI / Justin Bieber", "F*CK LOVE 3"),
    ("喜欢你", "Beyond", "秘密警察"),
    ("Heat Waves", "Glass Animals", "Dreamland"),
    ("挪威的森林", "伍佰 & China Blue", "爱情的尽头"),
    ("Sunflower", "Post Malone / Swae Lee", "Spider-Man: Into the Spider-Verse"),
    ("Last Dance", "伍佰 & China Blue", "爱情的尽头"),
    ("Watermelon Sugar", "Harry Styles", "Fine Line"),
    ("后来", "刘若英", "我等你"),
    ("体面", "于文文", "体面"),
    ("大鱼", "周深", "大鱼"),
    ("可能", "程响", "可能"),
    ("风继续吹", "张国荣", "风继续吹"),
    ("小幸运", "田馥甄", "我的少女时代"),
    ("王妃", "萧敬腾", "王妃"),
]

_JUNK = [
    ("DJ版 社会摇", "网络歌手", "DJ合集"),
    ("喊麦之王", "MC 某某", "喊麦合集"),
    ("伴奏 纯音乐", "未知", "伴奏合集"),
    ("抖音神曲串烧", "群星", "串烧合集"),
    ("【铃声】热门彩铃", "群星", "铃声合集"),
    ("Remix Bootleg 2026", "DJ Unknown", "Remix Pack"),
]


def demo_cover(title: str, artist: str) -> str:
    seed = f"{artist}|{title}".replace("/", " ").replace("\\", " ")
    return f"/api/covers/{urllib.parse.quote(seed, safe='')}.svg"


class DemoCollector(BaseCollector):
    platform: str = "demo"

    def __init__(self, cfg, platform: str = "netease") -> None:
        super().__init__(cfg)
        self.platform = platform

    async def fetch_playlist(self, playlist: dict) -> list[RawTrack]:
        try:
            ext_id = int(playlist.get("ext_id", "0"))
        except Exception:
            raw_ext = str(playlist.get("ext_id", "0"))
            ext_id = sum(ord(ch) for ch in raw_ext)
        offsets = {"netease": 0, "qq": 7, "spotify": 12, "apple": 18}
        base = offsets.get(self.platform, 0) + (ext_id % 6)
        take = 18
        rows: list[RawTrack] = []
        for i in range(take):
            idx = (base + i) % len(DEMO_SONGS)
            title, artist, album = DEMO_SONGS[idx]
            rows.append(
                RawTrack(
                    title=title,
                    artists=[artist],
                    album=album,
                    rank=i + 1,
                    cover=demo_cover(title, artist),
                    extra={"demo": True},
                )
            )
        # 每个平台加入低质样本，用于演示过滤规则
        for j, (title, artist, album) in enumerate(_JUNK[:2]):
            rows.append(
                RawTrack(
                    title=title,
                    artists=[artist],
                    album=album,
                    rank=80 + j,
                    cover=demo_cover(title, artist),
                    extra={"demo": True, "junk": True},
                )
            )
        return rows
