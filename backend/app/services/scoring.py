"""动态打分引擎。

S = (Σ W_i · P_i) × M_cross + B_trend - D_penalty
"""
from __future__ import annotations

from typing import Any

from ..config import ScoringConfig
from .normalize import normalize_text

PLATFORM_ORDER = ["netease", "qq", "spotify", "apple"]


def base_score_for_rank(rank: int, cfg: ScoringConfig) -> float:
    rank = rank or 9999
    for tier in sorted(cfg.base_score_tiers, key=lambda t: t.max_rank):
        if rank <= tier.max_rank:
            return float(tier.score)
    return 30.0


def _match_rule(rule, track: dict) -> bool:
    if not rule.enabled or not rule.value:
        return False
    field_value = str(track.get(rule.field, "") or "")
    haystack = normalize_text(field_value)
    needle = normalize_text(rule.value)
    if not needle:
        return False
    if rule.op == "contains":
        return needle in haystack
    if rule.op == "not_contains":
        return needle not in haystack
    if rule.op == "equals":
        return haystack == needle
    return False


def score_track(track: dict, sources: list[dict], cfg: ScoringConfig) -> dict[str, Any]:
    """track: {title, artist, album}; sources: [{platform, rank, playlist_name}]."""
    # 同一平台可能出现在多个歌单，取最优名次
    best_per_platform: dict[str, dict] = {}
    for src in sources:
        platform = src.get("platform", "")
        rank = int(src.get("rank") or 9999)
        current = best_per_platform.get(platform)
        if current is None or rank < current["rank"]:
            best_per_platform[platform] = {
                "platform": platform,
                "rank": rank,
                "playlist_name": src.get("playlist_name", ""),
            }

    platform_details = []
    base_total = 0.0
    for platform in PLATFORM_ORDER:
        detail = best_per_platform.get(platform)
        if not detail:
            continue
        weight = float(cfg.platform_weights.get(platform, 0))
        p = base_score_for_rank(detail["rank"], cfg)
        contribution = weight * p
        base_total += contribution
        platform_details.append(
            {
                "platform": platform,
                "rank": detail["rank"],
                "base_score": p,
                "weight": weight,
                "contribution": round(contribution, 3),
                "playlist_name": detail.get("playlist_name", ""),
            }
        )
    # 非内置平台兜底
    for platform, detail in best_per_platform.items():
        if platform in PLATFORM_ORDER:
            continue
        weight = float(cfg.platform_weights.get(platform, 0))
        p = base_score_for_rank(detail["rank"], cfg)
        contribution = weight * p
        base_total += contribution
        platform_details.append(
            {
                "platform": platform,
                "rank": detail["rank"],
                "base_score": p,
                "weight": weight,
                "contribution": round(contribution, 3),
                "playlist_name": detail.get("playlist_name", ""),
            }
        )

    cross_count = len(best_per_platform)
    if cross_count <= 0:
        multiplier = 0.0
    elif cross_count >= 4:
        multiplier = float(cfg.cross_multiplier.get("4", 1.7))
    else:
        multiplier = float(cfg.cross_multiplier.get(str(cross_count), 1.0))

    weighted_total = round(base_total, 3)
    after_cross = round(weighted_total * multiplier, 3)

    bonuses = []
    bonus_total = 0.0
    flags: list[str] = []

    # 黑名单关键词一票否决
    text_for_blacklist = normalize_text(f"{track.get('title', '')}{track.get('artist', '')}")
    hit_keywords = [kw for kw in cfg.blacklist_keywords if kw and normalize_text(kw) in text_for_blacklist]
    if hit_keywords:
        penalty = float(cfg.blacklist_penalty)
        bonus_total += penalty
        flags.extend(hit_keywords)
        bonuses.append(
            {
                "id": "blacklist",
                "name": f"黑名单命中：{', '.join(hit_keywords)}",
                "delta": penalty,
                "matched": True,
            }
        )

    for rule in cfg.bonus_rules:
        if _match_rule(rule, track):
            bonus_total += float(rule.delta)
            bonuses.append(
                {
                    "id": rule.id or rule.name,
                    "name": rule.name or f"{rule.field} {rule.op} {rule.value}",
                    "delta": float(rule.delta),
                    "matched": True,
                }
            )

    final_score = round(after_cross + bonus_total, 2)

    return {
        "final_score": final_score,
        "weighted_total": weighted_total,
        "cross_count": cross_count,
        "cross_multiplier": multiplier,
        "after_cross": after_cross,
        "bonus_total": round(bonus_total, 2),
        "platforms": platform_details,
        "bonuses": bonuses,
        "flags": flags,
        "formula": (
            f"({weighted_total} × {multiplier}) + ({round(bonus_total, 2)}) = {final_score}"
        ),
    }


def decide_status(score: float, exists_in_library: bool, cfg: ScoringConfig) -> str:
    if score < cfg.min_download_score:
        return "FILTERED_LOW_SCORE"
    if exists_in_library:
        return "SKIPPED_EXISTS"
    return "QUEUED_DOWNLOAD"
