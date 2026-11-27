"""应用配置：基础配置来自环境变量，业务运行配置支持数据库覆盖。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# 上游搜索/下载 API 支持的 source 取值（见 上游服务.MD）
SUPPORTED_UPSTREAM_SOURCES: List[str] = ["netease", "netease2", "bilibili", "joox", "kuwo"]
DEFAULT_UPSTREAM_SOURCE_ORDER = "netease,netease2,kuwo,joox,bilibili"


class Settings(BaseSettings):
    """基础设施配置，全部可通过环境变量覆盖。"""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "MuseFlow"
    host: str = "0.0.0.0"
    port: int = 8000
    data_dir: str = "./data"

    secret_key: str = "museflow-change-this-secret-key-in-production"
    admin_username: str = "admin"
    admin_password: str = "admin123"
    token_expire_minutes: int = 60 * 24 * 7

    demo_mode: bool = True
    collect_on_startup: bool = False
    timezone: str = "Asia/Shanghai"
    cors_origins: str = "*"

    # ---- 以下为运行配置的默认值，可在控制台「系统设置」中修改并持久化 ----
    proxy_url: str = ""
    flaresolverr_enabled: bool = False
    flaresolverr_url: str = "http://flaresolverr:8191/v1"
    flaresolverr_timeout_sec: int = 60
    cooldown_base_sec: int = 15
    cooldown_jitter_sec: int = 10

    rate_limit_window_sec: int = 300
    rate_limit_max_requests: int = 50

    min_download_score: float = 75
    weight_netease: float = 0.15
    weight_qq: float = 0.15
    weight_spotify: float = 0.35
    weight_apple: float = 0.35
    blacklist_keywords: str = "DJ,喊麦,伴奏,铃声,串烧"

    navidrome_enabled: bool = False
    navidrome_url: str = "http://navidrome:4533"
    navidrome_username: str = "admin"
    navidrome_password: str = ""
    navidrome_match_mode: str = "strict"
    navidrome_auto_scan: bool = True
    navidrome_sync_playlists: bool = True
    navidrome_playlist_prefix: str = "MuseFlow"
    navidrome_playlist_refresh_delay_sec: int = 30

    temp_download_dir: str = "./data/downloads/temp"
    final_music_dir: str = "./data/music_library"

    webhook_enabled: bool = False
    webhook_type: str = "generic"
    webhook_url: str = ""
    webhook_events: str = "job_completed,manual_download_completed,error_alert"

    scheduler_enabled: bool = True
    collect_interval_minutes: int = 360
    navidrome_sync_interval_minutes: int = 60

    upstream_base_url: str = "https://music.gdstudio.xyz"
    upstream_timeout_sec: int = 60
    upstream_bitrate: str = "999"
    upstream_file_path_template: str = "/music/{filename}"
    upstream_source_order: str = DEFAULT_UPSTREAM_SOURCE_ORDER
    upstream_cover_path: str = "/api/pic"
    upstream_lyric_path: str = "/api/lyric"
    upstream_local_download_dir: str = ""

    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    spotify_market: str = "TW"
    spotify_playlists_json: str = ""


settings = Settings()


# --------------------------------------------------------------------------------------
# 运行配置（可持久化，可被控制台编辑）
# --------------------------------------------------------------------------------------
class NetworkConfig(BaseModel):
    proxy_url: str = ""
    platform_use_proxy: dict[str, bool] = Field(
        default_factory=lambda: {"netease": False, "qq": False, "spotify": True, "apple": True}
    )
    flaresolverr_enabled: bool = False
    flaresolverr_url: str = "http://flaresolverr:8191/v1"
    flaresolverr_timeout_sec: int = 60
    cooldown_base_sec: int = 15
    cooldown_jitter_sec: int = 10


class RateLimitConfig(BaseModel):
    window_sec: int = 300
    max_requests: int = 50


class ScoreTier(BaseModel):
    max_rank: int
    score: float


class BonusRule(BaseModel):
    id: str = ""
    name: str = ""
    enabled: bool = True
    field: str = "title"  # title | artist | album
    op: str = "contains"  # contains | not_contains
    value: str = ""
    delta: float = 0


class ScoringConfig(BaseModel):
    min_download_score: float = 75
    platform_weights: dict[str, float] = Field(
        default_factory=lambda: {"netease": 0.15, "qq": 0.15, "spotify": 0.35, "apple": 0.35}
    )
    cross_multiplier: dict[str, float] = Field(
        default_factory=lambda: {"1": 0.4, "2": 1.0, "3": 1.35, "4": 1.7}
    )
    base_score_tiers: List[ScoreTier] = Field(
        default_factory=lambda: [
            ScoreTier(max_rank=10, score=100),
            ScoreTier(max_rank=30, score=80),
            ScoreTier(max_rank=50, score=60),
            ScoreTier(max_rank=100, score=40),
            ScoreTier(max_rank=9999, score=30),
        ]
    )
    blacklist_keywords: List[str] = Field(default_factory=lambda: ["DJ", "喊麦", "伴奏", "铃声", "串烧"])
    blacklist_penalty: float = -200
    bonus_rules: List[BonusRule] = Field(default_factory=list)


class NavidromeConfig(BaseModel):
    enabled: bool = False
    url: str = ""
    username: str = ""
    password: str = ""
    match_mode: str = "strict"
    auto_scan_after_move: bool = True
    sync_playlists: bool = True
    playlist_prefix: str = "MuseFlow"
    playlist_refresh_delay_sec: int = 30


class PathsConfig(BaseModel):
    temp_download_dir: str = "./data/downloads/temp"
    final_music_dir: str = "./data/music_library"


class WebhookConfig(BaseModel):
    enabled: bool = False
    type: str = "generic"  # generic | telegram | bark | wecom | dingtalk | discord
    url: str = ""
    events: List[str] = Field(default_factory=list)


class SchedulerConfig(BaseModel):
    enabled: bool = True
    collect_interval_minutes: int = 360
    navidrome_sync_interval_minutes: int = 60


class UpstreamConfig(BaseModel):
    base_url: str = "https://music.gdstudio.xyz"
    timeout_sec: int = 60
    file_path_template: str = "/music/{filename}"
    preferred_bitrate: str = "999"
    cover_path: str = "/api/pic"
    lyric_path: str = "/api/lyric"
    local_download_dir: str = ""
    source_order: List[str] = Field(default_factory=lambda: list(SUPPORTED_UPSTREAM_SOURCES))


class RuntimeConfig(BaseModel):
    network: NetworkConfig = Field(default_factory=NetworkConfig)
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    navidrome: NavidromeConfig = Field(default_factory=NavidromeConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)
    webhook: WebhookConfig = Field(default_factory=WebhookConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    upstream: UpstreamConfig = Field(default_factory=UpstreamConfig)


def _csv(value: str) -> List[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def _json_or(value: str, default):
    try:
        return json.loads(value) if value else default
    except Exception:
        return default


def build_default_runtime_config(s: Settings = settings) -> RuntimeConfig:
    cfg = RuntimeConfig()
    cfg.network.proxy_url = s.proxy_url
    cfg.network.flaresolverr_enabled = s.flaresolverr_enabled
    cfg.network.flaresolverr_url = s.flaresolverr_url
    cfg.network.flaresolverr_timeout_sec = s.flaresolverr_timeout_sec
    cfg.network.cooldown_base_sec = s.cooldown_base_sec
    cfg.network.cooldown_jitter_sec = s.cooldown_jitter_sec

    cfg.rate_limit.window_sec = s.rate_limit_window_sec
    cfg.rate_limit.max_requests = s.rate_limit_max_requests

    cfg.scoring.min_download_score = s.min_download_score
    cfg.scoring.platform_weights = {
        "netease": s.weight_netease,
        "qq": s.weight_qq,
        "spotify": s.weight_spotify,
        "apple": s.weight_apple,
    }
    cfg.scoring.blacklist_keywords = _csv(s.blacklist_keywords)
    cfg.scoring.bonus_rules = [
        BonusRule(
            id="new_release",
            name="新歌加分（发行 ≤ 30 天 +15）",
            enabled=False,
            field="album",
            op="contains",
            value="",
            delta=15,
        )
    ]

    cfg.navidrome.enabled = s.navidrome_enabled
    cfg.navidrome.url = s.navidrome_url
    cfg.navidrome.username = s.navidrome_username
    cfg.navidrome.password = s.navidrome_password
    cfg.navidrome.match_mode = s.navidrome_match_mode
    cfg.navidrome.auto_scan_after_move = s.navidrome_auto_scan
    cfg.navidrome.sync_playlists = s.navidrome_sync_playlists
    cfg.navidrome.playlist_prefix = s.navidrome_playlist_prefix
    cfg.navidrome.playlist_refresh_delay_sec = s.navidrome_playlist_refresh_delay_sec

    cfg.paths.temp_download_dir = s.temp_download_dir
    cfg.paths.final_music_dir = s.final_music_dir

    cfg.webhook.enabled = s.webhook_enabled
    cfg.webhook.type = s.webhook_type
    cfg.webhook.url = s.webhook_url
    cfg.webhook.events = _csv(s.webhook_events)

    cfg.scheduler.enabled = s.scheduler_enabled
    cfg.scheduler.collect_interval_minutes = s.collect_interval_minutes
    cfg.scheduler.navidrome_sync_interval_minutes = s.navidrome_sync_interval_minutes

    cfg.upstream.base_url = s.upstream_base_url
    cfg.upstream.timeout_sec = s.upstream_timeout_sec
    cfg.upstream.preferred_bitrate = s.upstream_bitrate
    cfg.upstream.file_path_template = s.upstream_file_path_template
    cfg.upstream.cover_path = s.upstream_cover_path
    cfg.upstream.lyric_path = s.upstream_lyric_path
    cfg.upstream.local_download_dir = s.upstream_local_download_dir
    cfg.upstream.source_order = _csv(s.upstream_source_order)
    return cfg


def spotify_playlists_from_env(s: Settings = settings) -> list[dict]:
    raw = _json_or(s.spotify_playlists_json, [])
    if isinstance(raw, list) and raw:
        normalized = []
        for item in raw:
            if isinstance(item, str):
                normalized.append({"id": item, "name": f"Spotify 歌单 {item}"})
            elif isinstance(item, dict) and item.get("id"):
                normalized.append(item)
        if normalized:
            return normalized
    # Spotify 官方 Top 50 榜单（可通过 SPOTIFY_PLAYLISTS_JSON 覆盖）
    return [
        {"id": "37i9dQZEVXbMDoHDwVN2tF", "name": "Global Top 50"},
        {"id": "37i9dQZEVXbLRQDuF5jeBp", "name": "US Top 50"},
        {"id": "37i9dQZEVXbLnolsZ8PSNw", "name": "UK Top 50"},
        {"id": "37i9dQZEVXbMnZEatlmmwA", "name": "Taiwan Top 50"},
        {"id": "37i9dQZEVXbL0GavIqMTeb", "name": "Hong Kong Top 50"},
        {"id": "37i9dQZEVXbKXQ4mDTEBXq", "name": "Japan Top 50"},
        {"id": "37i9dQZEVXbNxXF4SkHj9G", "name": "Korea Top 50"},
        {"id": "37i9dQZEVXbKkidEfWYRuD", "name": "Singapore Top 50"},
        {"id": "37i9dQZEVXbJPcfkRz0wJ0", "name": "Australia Top 50"},
    ]


def ensure_dirs(s: Settings = settings) -> None:
    Path(s.data_dir).mkdir(parents=True, exist_ok=True)
