"""Closed list of observation units/scales. Values on different scales never meet
in a rank or ratio; only RANKING_UNIT feeds ranking, tiers and ratios."""

RANKING_UNIT = "aa-index"
UNITS = {
    "aa-index": "Artificial Analysis Intelligence Index (0-100)",
    "benchlm-100": "BenchLM score (0-100)",
    "llmstats-trueskill": "LLM Stats TrueSkill score",
    "llmstats-conservative": "LLM Stats conservative TrueSkill rating",
    "llmstats-rank": "LLM Stats category rank",
    "benchmark-native": "the benchmark's own scale",
    "percent": "percent",
    "usd-per-1m-blended-3to1": "USD per 1M tokens, 3:1 input:output blend",
    "usd-per-1m": "USD per 1M tokens",
    "usd-per-test": "USD per test",
    "tokens": "tokens",
    "effort-list": "reasoning effort names",
    "duration": "time",
    "label": "categorical text",
}
# Fields that carry a benchmark result (need a benchmark and a URL or a reason).
SCORE_PREFIXES = ("score", "rating.", "rank.", "bench.")


def is_score(field):
    return field == "score" or field.startswith(SCORE_PREFIXES)


def problems(observation):
    """Why an observation breaks the provenance contract (empty when valid)."""
    out = []
    if observation.get("unit") not in UNITS:
        out.append(f"unit {observation.get('unit')!r} not in the scale list")
    if is_score(observation.get("field", "")):
        if not observation.get("benchmark"):
            out.append("score without benchmark")
        if not observation.get("url") and not observation.get("url_unavailable_reason"):
            out.append("score without url or url_unavailable_reason")
    if not observation.get("observed_at"):
        out.append("missing observed_at")
    return out

# Registry benchmarks and the scale each one is on.
BENCHMARKS = {"aa-intelligence-index": "aa-index", "llm-stats-overall": "llmstats-trueskill"}
