"""Shared model-naming helpers and ranking constants (one copy for every stage)."""
import re

# Reasoning-effort variants, strongest first.
EFFORTS = ("max", "xhigh", "high", "medium", "low", "minimal", "none")
# AA Intelligence Index tier floors.
TIERS = {"max": 50, "high": 40, "medium": 30}


def norm(s):
    """Lowercase alphanumerics only; None and empty become ''."""
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def kebab(name):
    return re.sub(r"[^a-z0-9]+", "-", str(name or "").lower()).strip("-")


def base_slug(mid):
    """Tail slug of a route ID: provider namespace and `:tag` suffix removed."""
    return norm(str(mid).split(":")[0].split("/")[-1])


def tier_of(score):
    if score is None:
        return ""
    for tier in ("max", "high", "medium"):
        if score >= TIERS[tier]:
            return tier
    return "below"
