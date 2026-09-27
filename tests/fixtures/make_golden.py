"""Deterministic synthetic golden fixture: every smoke check has content to act on.

All model names, prices and scores are invented. No third-party data is
copied, so the fixture is safe to commit to a public repository. Real-shape
drift is caught by the owner's live runs, not here.

    python tests/fixtures/make_golden.py          # rewrite the committed files
    python tests/fixtures/make_golden.py --check  # exit 1 if they are stale

The fixture pins its own evidence day and registry (see FIXTURE), so replays
do not change when analysis/research.json is refreshed or entries expire.
"""
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from pipeline_common import PROVIDERS, SOURCES  # noqa: E402

AS_OF = "2026-09-27"
RUN_ID = "golden-synthetic"
# Paths are relative to the snapshot file (see tools/ci.py replay).
FIXTURE = {"kind": "synthetic", "as_of": AS_OF,
           "registry": "golden_research.json", "websites": "golden_websites.json"}
FETCHED_AT = AS_OF + "T00:00:00+00:00"
EFFORTS5 = ["minimal", "low", "medium", "high", "xhigh"]


def health(status="complete", count=0, scope="catalog", **extra):
    # Fixed timestamp keeps the committed file byte-stable.
    return {"status": status, "complete": status == "complete", "scope": scope, "count": count,
            "fetched_at": FETCHED_AT, "reason": "", "enabled": True, "attempted": True, **extra}


def or_row(mid, name, prompt, completion, efforts=None, ctx=128000):
    row = {"id": mid, "name": name, "context_length": ctx,
           "pricing": {"prompt": prompt, "completion": completion},
           "architecture": {"output_modalities": ["text"]}}
    if efforts:
        row["reasoning"] = {"supported_efforts": efforts, "default_effort": efforts[len(efforts) // 2]}
    return row


def aa_row(slug, name, creator, score, blended, inp=None, out=None):
    inp = blended if inp is None else inp
    out = blended if out is None else out
    return {"id": "aa-" + slug, "slug": slug, "name": name, "model_creator": {"name": creator},
            "evaluations": {"artificial_analysis_intelligence_index": score},
            "pricing": {"price_1m_input_tokens": inp, "price_1m_output_tokens": out,
                        "price_1m_blended_3_to_1": blended}}


def md_row(provider, mid, cost_in, cost_out, efforts=(), deprecated=False, output=("text",)):
    return {"provider": provider, "id": mid,
            "cost": {"input": cost_in, "output": cost_out, "cache_read": None},
            "modalities": {"input": ["text"], "output": list(output)},
            "reasoning": bool(efforts), "reasoning_efforts": list(efforts), "deprecated": deprecated,
            "limit": {"context": 200000, "output": 32000}, "last_updated": "2026-09-01"}


def zen_row(mid):
    return {"id": mid, "object": "model", "created": 1790000000, "owned_by": "opencode"}


def snapshot():
    openrouter = [
        or_row("openai/gpt-6", "OpenAI: GPT-6", "0.0000025", "0.0000125", ["low", "medium", "high", "xhigh"]),
        or_row("openai/gpt-6-mini", "OpenAI: GPT-6 mini", "0.0000004", "0.0000016", ["low", "medium", "high"]),
        or_row("anthropic/claude-opus-5", "Anthropic: Claude Opus 5", "0.000015", "0.000075", ["low", "medium", "high", "max"]),
        or_row("anthropic/claude-haiku-5", "Anthropic: Claude Haiku 5", "0.000001", "0.000005"),
        or_row("meta/muse-spark-1.3", "Meta: Muse Spark 1.3", "0.000002", "0.000008"),
        or_row("deepseek/deepseek-v4", "DeepSeek: DeepSeek V4", "0.0000005", "0.000002", ["high"]),
        or_row("deepseek/deepseek-v4:free", "DeepSeek: DeepSeek V4 (free)", "0", "0", ["high"]),
        or_row("qwen/qwen3-30b-a3b:free", "Qwen: Qwen3 30B A3B (free)", "0", "0"),
        or_row("z-ai/glm-5.3", "Z.ai: GLM-5.3", "0.0000006", "0.0000022"),
        or_row("moonshotai/kimi-k3", "MoonshotAI: Kimi K3", "0.000001", "0.000004"),
        or_row("openrouter/auto", "Auto Router", "-1", "-1"),
        # Identity cases: alias (meta-llama = meta), a two-vendor tail collision.
        or_row("meta-llama/llama-4-scout", "Meta: Llama 4 Scout", "0.0000002", "0.0000006"),
        or_row("acme/nova-1", "Acme: Nova 1", "0.000001", "0.000003"),
    ]
    openai = [{"id": "gpt-6", "object": "model", "owned_by": "openai"},
              {"id": "gpt-6-mini", "object": "model", "owned_by": "openai"},
              {"id": "gpt-4.1", "object": "model", "owned_by": "openai", "shutdown_date": "2026-12-01"}]
    anthropic = [{"id": "claude-opus-5", "display_name": "Claude Opus 5", "max_input_tokens": 1000000, "max_tokens": 64000},
                 {"id": "claude-haiku-5", "display_name": "Claude Haiku 5", "max_input_tokens": 200000, "max_tokens": 32000}]
    nvidia = [{"id": "deepseek-ai/deepseek-v4", "object": "model", "owned_by": "deepseek-ai"},
              {"id": "meta/llama-4-scout", "object": "model", "owned_by": "meta"},
              {"id": "orbit/nova-1", "object": "model", "owned_by": "orbit"},
              {"id": "nvidia/nemotron-4-ultra", "object": "model", "owned_by": "nvidia"}]
    zenmux = [{"id": "qwen/qwen3-30b-a3b", "display_name": "Qwen3 30B A3B", "owned_by": "qwen",
               "capabilities": {"reasoning": True}, "output_modalities": ["text"], "context_length": 131072,
               "pricings": {"prompt": [{"value": 0.1}], "completion": [{"value": 0.3}]}}]
    zen = [zen_row("muse-spark-1.3-contributor-free"), zen_row("muse-spark-1.2-contributor-free"),
           zen_row("kimi-k3-free"), zen_row("big-pickle"), zen_row("nova-1")]
    modelsdev = [
        md_row("opencode", "muse-spark-1.3-contributor-free", 0, 0, EFFORTS5),
        md_row("opencode", "muse-spark-1.2-contributor-free", 0, 0, EFFORTS5, deprecated=True),
        md_row("opencode", "kimi-k3-free", 0, 0, ["low", "high"]),
        md_row("opencode", "big-pickle", 0, 0),
        md_row("openai", "gpt-6", 2.5, 12.5, ["low", "medium", "high", "xhigh"]),
        md_row("zenmux", "qwen/qwen3-30b-a3b", 0.1, 0.3, ["high"]),
    ]
    aa = {"status": 200, "data": [
        aa_row("gpt-6", "GPT-6 (xhigh)", "OpenAI", 64.2, 5.0, 2.5, 12.5),
        aa_row("gpt-6-mini", "GPT-6 mini (high)", "OpenAI", 46.1, 0.7, 0.4, 1.6),
        aa_row("claude-opus-5", "Claude Opus 5 (max)", "Anthropic", 60.4, 30.0, 15, 75),
        aa_row("claude-opus-5-medium", "Claude Opus 5 (medium)", "Anthropic", 47.3, 30.0, 15, 75),
        aa_row("claude-haiku-5", "Claude Haiku 5", "Anthropic", 36.0, 2.0, 1, 5),
        aa_row("muse-spark-1-3", "Muse Spark 1.3 (max)", "Meta", 48.1, 3.5, 2, 8),
        aa_row("muse-spark-1-3-xhigh", "Muse Spark 1.3 (xhigh)", "Meta", 45.1, 3.5, 2, 8),
        aa_row("muse-spark-1-2", "Muse Spark 1.2 (xhigh)", "Meta", 41.0, 3.0, 2, 6),
        aa_row("deepseek-v4", "DeepSeek V4", "DeepSeek", 52.0, 0.9, 0.5, 2),
        aa_row("qwen3-30b-a3b", "Qwen3 30B A3B", "Alibaba", 33.5, 0.15, 0.1, 0.3),
        aa_row("glm-5-3", "GLM-5.3", "Z.ai", 43.0, 0, 0, 0),
        aa_row("motif-3", "Motif 3", "Motif", 33.6, 0, 0, 0),
        aa_row("kimi-k3", "Kimi K3", "Moonshot AI", 55.0, 1.8, 1, 4),
        aa_row("nemotron-4-ultra", "Nemotron 4 Ultra", "NVIDIA", None, None),
    ]}
    benchlm = {"leaderboard": [
        {"model": "GPT-6", "creator": "OpenAI", "overallScore": 91, "evidenceStatus": "verified",
         "categoryScores": {"reasoning": 93, "coding": 90}, "inputPrice": 2.5, "outputPrice": 12.5},
        {"model": "Claude Opus 5", "creator": "Anthropic", "overallScore": 89, "evidenceStatus": "verified",
         "categoryScores": {"reasoning": 90, "coding": 92}, "inputPrice": 15, "outputPrice": 75},
        {"model": "DeepSeek V4", "creator": "DeepSeek", "overallScore": 80, "evidenceStatus": "partial",
         "categoryScores": {"reasoning": 81}, "inputPrice": 0.5, "outputPrice": 2},
        {"model": "Orion Pro", "creator": "Orion Labs", "overallScore": 77, "evidenceStatus": "self-reported",
         "categoryScores": {"coding": 75}, "inputPrice": 1, "outputPrice": 3}],
        "pricing": [{"model": "GPT-6", "contextWindow": 400000, "sourceType": "api", "inputPrice": 2.5, "outputPrice": 12.5},
                    {"model": "DeepSeek V4", "contextWindow": 128000, "sourceType": "api", "inputPrice": 0.5, "outputPrice": 2}],
        "meta": {"lastUpdated": "2026-09-26", "methodologyVersion": "fixture-1", "mode": "overall"}}
    llm_models = [
        {"id": "gpt-6", "name": "GPT-6", "org": "openai", "family": "gpt-6", "license": "proprietary",
         "open_weight": False, "model_type": "chat", "modalities": ["text"], "context_window": 400000,
         "params": None, "cutoff": "2026-03", "released": "2026-06-01", "providers": [],
         "top_scores": {"general": 1500}, "supports_tools": True, "supports_vision": True,
         "supports_streaming": True, "openai_compatible": True, "url": "https://example.invalid/gpt-6",
         "updated": "2026-09-20"},
        {"id": "muse-spark-1.3", "name": "Muse Spark 1.3", "org": "meta", "family": "muse-spark",
         "license": "proprietary", "open_weight": False, "model_type": "chat", "modalities": ["text"],
         "context_window": 256000, "params": None, "cutoff": "2026-01", "released": "2026-08-01",
         "providers": [], "top_scores": {}, "supports_tools": True, "supports_vision": False,
         "supports_streaming": True, "openai_compatible": True, "url": "https://example.invalid/muse-spark-1.3",
         "updated": "2026-09-20"}]

    def rank(mid, name, org, n, rating):
        return {"model_id": mid, "model_name": name, "org": org, "rank": n, "rating": rating,
                "evals": 12, "min_in": 1.0, "url": "https://example.invalid/" + mid}
    rankings = {"general": [rank("gpt-6", "GPT-6", "openai", 1, 60.1), rank("atlas-2", "Atlas 2", "atlas", 2, 55.0),
                            rank("muse-spark-1.3", "Muse Spark 1.3", "meta", 3, 53.8)],
                "reasoning": [rank("gpt-6", "GPT-6", "openai", 1, 61.0)],
                "code": [rank("claude-opus-5", "Claude Opus 5", "anthropic", 1, 59.0)],
                "agents": [rank("atlas-2", "Atlas 2", "atlas", 1, 50.0)]}
    llmstats = {"models": llm_models, "model_count": len(llm_models),
                "benchmarks": [{"id": "fixture-bench", "name": "Fixture Bench", "categories": ["general"],
                                "verified": True, "model_count": 3}], "benchmark_count": 1,
                "rankings": rankings,
                "details": {"muse-spark-1.3": {"name": "Muse Spark 1.3", "n_benchmarks": 1, "scores": [
                    {"bench": "fixture-bench", "name": "Fixture Bench", "cat": "general", "score": 71.0,
                     "norm": 0.71, "max": 100, "self_reported": False, "verified": True, "rank": 3,
                     "url": "https://example.invalid/fixture-bench"}]}},
                "meta": {"quota_remaining": 200, "quota_day": AS_OF}}
    vals = {"models": [{"href": "/models/openai_gpt-6", "name": "GPT-6"}], "source": "html:vals_index"}

    snap = {"retrieved_at": RUN_ID, "run_id": RUN_ID, "schema_version": 3, "started_at": FETCHED_AT,
            "fixture": FIXTURE, "openrouter": openrouter, "openai": openai, "anthropic": anthropic,
            "nvidia": nvidia, "zenmux": zenmux, "zen": zen, "modelsdev": modelsdev, "aa": aa,
            "benchlm": benchlm, "llmstats": llmstats, "vals": vals}
    snap["source_health"] = {s: health(count=len(snap[s])) for s in PROVIDERS}
    snap["source_health"].update(
        modelsdev=health(count=len(modelsdev), scope="reference"),
        aa=health(count=len(aa["data"]), scope="reference"),
        benchlm=health(count=len(benchlm["leaderboard"]), scope="bounded-reference"),
        llmstats=health(count=len(llm_models), scope="reference"),
        vals=health(count=1, scope="best-effort", complete=False))
    assert set(snap["source_health"]) == set(SOURCES)
    return snap


def websites():
    page = {"fetched_at": FETCHED_AT, "cache_hit": False}
    return {"retrieved_at": RUN_ID, "run_id": RUN_ID, "schema_version": 3,
            "allowlist": [{"slug": "gpt6", "name": "GPT-6"}, {"slug": "musespark13", "name": "Muse Spark 1.3"}],
            "benchlm_md": {"gpt6": {"url": "https://example.invalid/md/gpt-6.md", "benchlm_slug": "gpt-6",
                                    "model": "GPT-6", "md": "# GPT-6\n\nSynthetic fixture page.\n", **page}},
            "llmstats": {"musespark13": {"url": "https://example.invalid/models/muse-spark-1.3",
                                         "llmstats_slug": "muse-spark-1.3", "llmstats_score_hint": 53.8,
                                         "price_hints": [{"value": "2.00", "kind": "input"}], **page}},
            "vals": {"gpt6": {"url": "https://example.invalid/models/openai_gpt-6", "vals_href": "/models/openai_gpt-6",
                              "accuracy_hints": ["71.2"], "cost_per_test_hint": "0.12", "latency_hint": "9 s",
                              "html_len": 1000, **page}},
            "source_health": {src: health(count=1, scope="selected-pages", complete=False, attempted_count=1,
                                          failed_count=0, cache_hits=0, oldest_data_at=FETCHED_AT)
                              for src in ("benchlm_md", "llmstats", "vals")}}


def registry():
    dates = {"checked_at": "2026-09-20", "expires_at": "2026-10-10"}
    rationale = "Synthetic fixture estimate: same checkpoint, pricing-tier route."
    urls = ["https://example.invalid/pricing", "https://example.invalid/equivalence"]

    def inherit(target, source, route):
        return {"target_slug": target, "source_slug": source, "variant": "xhigh", "version": "4.3.2", "provider": "zen",
                "route_id": route, "selector": f"opencode/{route}#xhigh", "supported_efforts": EFFORTS5,
                "cost_blended": 0, **dates, "equivalence_urls": urls,
                "capability_url": "https://example.invalid/models.json", "rationale": rationale}
    return {"aa_index_versions": [{"version": "4.3.2", "valid_from": "2026-09-01", "valid_to": None,
                                   "source_url": "https://example.invalid/aa-methodology", "checked_at": "2026-09-20"}],
            "scores": [
                {"target_slug": "nemotron4ultra", "variant": "", "benchmark": "aa-intelligence-index",
                 "version": "4.3.2", "value": 39, "source": "Synthetic release page",
                 "url": "https://example.invalid/nemotron-4-ultra", **dates,
                 "note": "Registry score for a row the API leaves unscored."},
                {"target_slug": "musespark13", "variant": "unspecified", "benchmark": "llm-stats-overall",
                 "version": "fixture", "value": 53.8, "source": "Synthetic LLM Stats",
                 "url": "https://example.invalid/llm-stats", **dates, "note": "Reference only."}],
            "inheritance": [inherit("musespark13contributorfree", "musespark13xhigh", "muse-spark-1.3-contributor-free"),
                            inherit("musespark12contributorfree", "musespark12", "muse-spark-1.2-contributor-free")]}


FILES = {"golden_snapshot.json": snapshot, "golden_websites.json": websites, "golden_research.json": registry}


def render(build):
    return json.dumps(build(), indent=1, ensure_ascii=False, sort_keys=True) + "\n"


def main(argv=None):
    check = "--check" in (argv if argv is not None else sys.argv[1:])
    stale = []
    for name, build in FILES.items():
        path, text = HERE / name, render(build)
        if check:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                stale.append(name)
        else:
            path.write_text(text, encoding="utf-8", newline="\n")
    if stale:
        print("stale golden fixture files (run python tests/fixtures/make_golden.py): " + ", ".join(stale))
        return 1
    print("golden fixture " + ("up to date" if check else "written") + f": {', '.join(FILES)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
