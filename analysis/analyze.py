"""2. Data Analysis — normalize all providers, free-classify, rank. Route churn lives in history.py."""
import json, os, datetime
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline_common import atomic_json, check_identity, SCHEMA_VERSION

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def is_free_or(pricing):
    try:
        return float(pricing.get("prompt", 1)) == 0 and float(pricing.get("completion", 1)) == 0
    except Exception:
        return False

def aa_score(ev):
    try:
        value = (ev or {}).get("artificial_analysis_intelligence_index")
        import math
        score = float(value) if value is not None else None
        return score if score is not None and math.isfinite(score) else None
    except Exception:
        return None

def aa_creator(m):
    c = m.get("model_creator", "")
    return c.get("name", "") if isinstance(c, dict) else str(c)

try:
    from .common import EFFORTS as EFFORTS_ORDERED, TIERS, base_slug, tier_of
    from .identity import load_overrides as load_identity_overrides, resolve as resolve_identity
except ImportError:
    from common import EFFORTS as EFFORTS_ORDERED, TIERS, base_slug, tier_of
    from identity import load_overrides as load_identity_overrides, resolve as resolve_identity


def parse_variant(aa_name="", aa_slug=""):
    """Extract reasoning-effort variant from AA name or slug. Returns '' when none."""
    n = str(aa_name or "").lower()
    s = str(aa_slug or "").lower()
    # Parenthesized form: "Muse Spark 1.3 (max)" / "(xhigh)".
    import re as _re
    m = _re.search(r"\((max|xhigh|high|medium|low|minimal|none)\)", n)
    if m:
        return m.group(1)
    # Long form: "Max Effort", "Xhigh Effort", "Adaptive Reasoning, High Effort".
    for v in EFFORTS_ORDERED:
        if f"{v} effort" in n:
            return v
    # Slug suffix: "muse-spark-1-3-xhigh", "claude-opus-5-medium".
    for v in EFFORTS_ORDERED:
        if s.endswith("-" + v) or f"-{v}-" in f"-{s}-":
            # Avoid false positives like "minimal" inside other words: slug tokens are hyphen-separated so this is safe.
            return v
    return ""

def main(input_path=None, output_dir=None, websites_path=None, registry_path=None, as_of=None, identity_path=None):
    """as_of/registry_path pin the evidence day and registry for fixture replays (default: run day, research.json)."""
    if input_path is None:
        raise ValueError("analysis requires an explicit input snapshot")
    with open(input_path, encoding="utf-8") as f:
        snap = json.load(f)
    stamp = str(snap.get("retrieved_at", datetime.datetime.now().strftime("%Y-%m-%d_%H%M")))
    day = as_of or snap.get("started_at", stamp)[:10]

    ors = snap.get("openrouter", []) if isinstance(snap.get("openrouter"), list) else []
    oai = snap.get("openai", []) if isinstance(snap.get("openai"), list) else []
    ant = snap.get("anthropic", []) if isinstance(snap.get("anthropic"), list) else []
    nvidia = snap.get("nvidia", []) if isinstance(snap.get("nvidia"), list) else []
    zenmux = snap.get("zenmux", []) if isinstance(snap.get("zenmux"), list) else []
    zen = snap.get("zen", []) if isinstance(snap.get("zen"), list) else []
    modelsdev_raw = snap.get("modelsdev", [])
    modelsdev = modelsdev_raw if isinstance(modelsdev_raw, list) else []
    aa_raw = snap.get("aa", {})
    aa = aa_raw.get("data", []) if isinstance(aa_raw, dict) else []
    # Optional enrichment must belong to this exact run.
    websites = {}
    if websites_path is not None:
        with open(websites_path, encoding="utf-8") as _wf:
            websites = json.load(_wf)
        check_identity(websites, snap.get("run_id", stamp), "website snapshot")

    or_rows = [{"id": m.get("id", ""), "name": m.get("name", ""), "context": m.get("context_length"),
                "free": (is_free_or(m.get("pricing", {})) or str(m.get("id", "")).endswith(":free"))
                        and (m.get("architecture") or {}).get("output_modalities") == ["text"]
                        and not str(m.get("id", "")).startswith("openrouter/")}
               for m in ors]
    free_ids = sorted([r["id"] for r in or_rows if r["free"]])

    oai_rows = [{"id": m.get("id", ""), "owned_by": m.get("owned_by", ""), "shutdown": m.get("shutdown_date", "")} for m in oai]
    ant_rows = [{"id": m.get("id", ""), "name": m.get("display_name", ""),
                 "ctx_in": m.get("max_input_tokens"), "ctx_out": m.get("max_tokens")} for m in ant]
    nvidia_rows = [{"id": m.get("id", ""), "owned_by": m.get("owned_by", "")} for m in nvidia]
    zenmux_rows = [{"id": m.get("id", ""), "owned_by": m.get("owned_by", "")} for m in zenmux]
    zen_rows = [{"id": m.get("id", ""), "owned_by": m.get("owned_by", "")} for m in zen]

    aa_rows = []
    for m in aa:
        p = m.get("pricing", {}) or {}
        try:
            zero = float(p.get("price_1m_input_tokens", 1)) == 0 and float(p.get("price_1m_output_tokens", 1)) == 0
        except Exception:
            zero = False
        aa_rows.append({"id": m.get("slug", "") or m.get("id", ""), "name": m.get("name", ""),
                        "creator": aa_creator(m), "score": aa_score(m.get("evaluations")),
                        "cost_blended": p.get("price_1m_blended_3_to_1"), "zero_price": zero})

    # Canonical deduped models (reports-layer union; raw snapshots untouched).
    def or_cost_per_1m(pricing):
        try:
            p = float((pricing or {}).get("prompt", -1))
            c = float((pricing or {}).get("completion", -1))
            if p < 0 or c < 0:
                return None
            return round((3 * p + c) / 4 * 1e6, 4)
        except Exception:
            return None

    def aa_cost(value):
        try:
            return None if value is None else round(float(value), 4)
        except Exception:
            return None

    def family_of(slug, variant):
        s = str(slug or "").split(".")[0]  # split entities: <tail>.<vendor>
        if "__" in s:
            s = s.split("__")[0]
        v = str(variant or "")
        if v and s.endswith(v):
            base = s[: -len(v)]
            return base or s
        for eff in EFFORTS_ORDERED:
            if eff and s.endswith(eff) and len(s) > len(eff):
                return s[: -len(eff)]
        return s or str(slug or "")

    or_free = {r["id"] for r in or_rows if r["free"]}
    or_ctx = {r["id"]: r["context"] for r in or_rows}
    or_name = {m.get("id", ""): m.get("name", "") for m in ors}
    or_price = {m.get("id", ""): m.get("pricing", {}) for m in ors}
    or_reasoning = {}
    for m in ors:
        r = m.get("reasoning") or {}
        eff = r.get("supported_efforts") or []
        if eff or r.get("default_effort"):
            or_reasoning[m.get("id", "")] = {
                "efforts": list(eff),
                "default_effort": r.get("default_effort", ""),
            }
    ant_name = {m.get("id", ""): m.get("display_name", "") for m in ant}
    zenmux_name = {m.get("id", ""): m.get("display_name", "") for m in zenmux}
    # Tier 1: promote ZenMux capabilities/pricings (previously id-only).
    zenmux_by_slug = {}
    for m in zenmux:
        if not isinstance(m, dict):
            continue
        mid = m.get("id", "")
        if not mid:
            continue
        caps = m.get("capabilities", {}) or {}
        pricings = m.get("pricings", {}) or {}
        def _first_val(lst):
            try:
                if isinstance(lst, list) and lst:
                    return float(lst[0].get("value", "nan"))
            except Exception:
                return None
            return None
        zenmux_by_slug.setdefault(base_slug(mid), []).append({
            "id": mid,
            "reasoning": caps.get("reasoning"),
            "output_modalities": list(m.get("output_modalities", []) or []),
            "prompt_per_mtok": _first_val(pricings.get("prompt")),
            "completion_per_mtok": _first_val(pricings.get("completion")),
            "context_length": m.get("context_length"),
        })
    # Tier 1: models.dev minimal projection indexed by tail slug.
    md_by_slug = {}
    for r in modelsdev:
        if not isinstance(r, dict):
            continue
        rid = r.get("id", "")
        if not rid:
            continue
        md_by_slug.setdefault(base_slug(rid), []).append(r)
    def _entry():
        return {"or": [], "oai": [], "ant": [],
                "nvidia": [], "zenmux": [], "zen": [], "aa": None,
                "benchlm": None, "llm": None}

    # Provider identity (analysis/identity.py): vendor-aware joins, recorded conflicts.
    ident = resolve_identity(
        {"openrouter": [m.get("id", "") for m in ors], "openai": [m.get("id", "") for m in oai],
         "anthropic": [m.get("id", "") for m in ant], "nvidia": [m.get("id", "") for m in nvidia],
         "zenmux": [m.get("id", "") for m in zenmux], "zen": [m.get("id", "") for m in zen]},
        [{"slug": r["id"], "creator": r["creator"]} for r in aa_rows],
        load_identity_overrides(identity_path))
    union_keys = {"openrouter": "or", "openai": "oai", "anthropic": "ant",
                  "nvidia": "nvidia", "zenmux": "zenmux", "zen": "zen"}
    aa_by_id = {r["id"]: r for r in aa_rows}
    union = {}
    for slug, e in ident["entities"].items():
        entry = union.setdefault(slug, _entry())
        for provider, ids in e["routes"].items():
            entry[union_keys[provider]].extend(ids)
        entry["aa"] = aa_by_id.get(e["aa"]) if e["aa"] else None
    by_tail = {}
    for slug, e in ident["entities"].items():
        by_tail.setdefault(e["tail"], []).append(slug)

    def bench_entity(key):
        """Benchmark rows attach to the one entity with their tail, else become reference-only."""
        found = by_tail.get(key, [])
        if len(found) > 1:
            return None
        if not found:
            by_tail[key] = [key]
            ident["entities"][key] = {"slug": key, "tail": key, "vendor": "", "key": f"?/{key}",
                                      "basis": "exact", "routes": {}, "aa": None,
                                      "canonical_id": key, "conflicts": []}
        return union.setdefault(by_tail[key][0], _entry())
    # Benchmark-only rows (no provider listing): complete the BenchLM board and
    # LLM Stats ranked set as reference-only entities. No AA score, no callable
    # ID, excluded from OCF/stack — same precedent as AA-only rows.
    _bench_snap = snap.get("benchlm", {}) if isinstance(snap.get("benchlm"), dict) else {}
    for m in (_bench_snap.get("leaderboard", []) if isinstance(_bench_snap.get("leaderboard"), list) else []):
        if isinstance(m, dict) and m.get("model"):
            entry = bench_entity(base_slug(m["model"]))
            if entry is not None and entry["benchlm"] is None:
                entry["benchlm"] = m
    _llm_snap = snap.get("llmstats", {}) if isinstance(snap.get("llmstats"), dict) else {}
    for cat_rows in ((_llm_snap.get("rankings", {}) or {}).values() if isinstance(_llm_snap.get("rankings"), dict) else []):
        for r in cat_rows if isinstance(cat_rows, list) else []:
            if isinstance(r, dict) and (r.get("model_id") or r.get("model_name")):
                entry = bench_entity(base_slug(r.get("model_id", "") or r.get("model_name", "")))
                if entry is not None and entry["llm"] is None:
                    entry["llm"] = r

    identity_conflicts = ident["conflicts"]
    if identity_conflicts:
        print(f"note: {len(identity_conflicts)} identity conflicts (kept separate or flagged): " +
              ", ".join(sorted({c.get("tail", c.get("route", "")) for c in identity_conflicts}))[:300])

    models = []
    for key in sorted(union):
        u = union[key]
        zen_free_ids = [i for i in u["zen"] if str(i).endswith("-free")]
        free = any(i in or_free for i in u["or"]) or bool(zen_free_ids)
        zen_free = bool(zen_free_ids)
        ent = ident["entities"][key]
        aa_match = u["aa"]
        aa_creator_name = ""
        try:
            if aa_match:
                c = aa_match.get("creator", "")
                aa_creator_name = str(c or "").lower()
        except Exception:
            aa_creator_name = ""
        groups = []
        if u["oai"] or any(i.lstrip("~").split("/")[0].lower() == "openai" for i in u["or"] if "/" in i.lstrip("~")):
            groups.append("O")
        if u["ant"] or any(i.lstrip("~").split("/")[0].lower() == "anthropic" for i in u["or"] if "/" in i.lstrip("~")):
            groups.append("C")
        # AA-only variant rows carry no provider, but creator tells us O/C.
        # This keeps e.g. Claude Opus 5 (medium) and GPT variants visible in OCF views
        # as separate ranked rows instead of being filtered out.
        if not u["oai"] and not u["ant"] and not u["or"] and aa_match:
            if aa_creator_name == "anthropic" and "C" not in groups:
                groups.append("C")
            elif aa_creator_name == "openai" and "O" not in groups:
                groups.append("O")
        if free:
            groups.append("F")
        providers = []
        if u["or"]:
            providers.append("openrouter")
        if u["oai"]:
            providers.append("openai")
        if u["ant"]:
            providers.append("anthropic")
        if u["nvidia"]:
            providers.append("nvidia")
        if u["zenmux"]:
            providers.append("zenmux")
        if u["zen"]:
            providers.append("zen")
        score = aa_match["score"] if aa_match else None
        cost = aa_cost(aa_match["cost_blended"]) if aa_match else None
        cost_source = "aa" if cost is not None else ""
        if cost is None:
            for i in u["or"]:
                cost = or_cost_per_1m(or_price.get(i))
                if cost is not None:
                    cost_source = "or-derived"
                    break
        if cost is None:
            cost_source = "none"
        ratio = round(score / cost, 4) if score is not None and cost and cost > 0 else None
        or_ids = sorted(u["or"])
        disp_or = next((i for i in or_ids if i in or_free), or_ids[0] if or_ids else "")
        _bench_name = (u["benchlm"] or {}).get("model", "") if isinstance(u.get("benchlm"), dict) else ""
        _llm_name = (u["llm"] or {}).get("model_name", "") if isinstance(u.get("llm"), dict) else ""
        disp = (u["oai"] or u["ant"] or ([disp_or] if disp_or else []) or
                u["nvidia"] or u["zenmux"] or u["zen"] or
                ([aa_match.get("slug", "") or aa_match.get("id", "")] if aa_match else []) or
                ([_bench_name] if _bench_name else []) or
                ([_llm_name] if _llm_name else []) or [""])[0]
        name = (next((or_name.get(i, "") for i in or_ids if or_name.get(i)), "") or
                next((ant_name.get(i, "") for i in u["ant"] if ant_name.get(i)), "") or
                next((zenmux_name.get(i, "") for i in u["zenmux"] if zenmux_name.get(i)), "") or
                ((aa_match or {}).get("name", "")) or
                ((u["nvidia"][:1] + [""])[0]) or ((u["zen"][:1] + [""])[0]) or
                _bench_name or _llm_name)
        router = disp_or.lower().lstrip("~").startswith("openrouter/")
        aa_zero = bool(aa_match and aa_match.get("zero_price"))
        has_or = bool(u["or"])
        if free:
            free_status = "verified"
            free_evidence = []
            if any(i in or_free for i in u["or"]):
                free_evidence.append("or:strict-free")
            if zen_free:
                free_evidence.append("zen:free-route")
            if aa_zero:
                free_evidence.append("aa:zero-price")
        elif aa_zero and has_or:
            free_status = "provisional-l1"
            free_evidence = ["aa:zero-price", "or:listed"]
        elif aa_zero:
            free_status = "provisional-l0"
            free_evidence = ["aa:zero-price"]
        else:
            free_status = "none"
            free_evidence = []
        aa_slug_raw = (aa_match or {}).get("slug", "") or (aa_match or {}).get("id", "")
        aa_name_raw = (aa_match or {}).get("name", "")
        variant = parse_variant(aa_name_raw, aa_slug_raw)
        efforts, default_effort = [], ""
        for i in or_ids:
            r = or_reasoning.get(i)
            if r and (r.get("efforts") or r.get("default_effort")):
                efforts = list(r.get("efforts") or [])
                default_effort = str(r.get("default_effort") or "")
                break
        efforts_source = "or" if efforts else ""
        default_effort_source = "or" if default_effort else ("unspecified-upstream" if efforts else "")
        # Tier 1: models.dev + ZenMux promotion per canonical slug.
        md_matches = md_by_slug.get(ent["tail"], [])
        zm_matches = zenmux_by_slug.get(ent["tail"], [])
        md_efforts_union = sorted({e for r in md_matches for e in (r.get("reasoning_efforts") or [])})
        md_reasoning_any = any(bool(r.get("reasoning")) for r in md_matches)
        md_has = bool(md_matches)
        md_all_no_reasoning = md_has and all(not r.get("reasoning") for r in md_matches)
        zm_reason_vals = [z.get("reasoning") for z in zm_matches if z.get("reasoning") is not None]
        zm_reason_any = any(v is True for v in zm_reason_vals)
        zm_all_false = bool(zm_reason_vals) and all(v is False for v in zm_reason_vals)
        deprecated_sources = sorted({f"{r.get('provider')}/{r.get('id')}" for r in md_matches if r.get("deprecated")})
        deprecated_upstream = bool(deprecated_sources)
        if u["zen"]:
            md_text = any((r.get("modalities") or {}).get("output") == ["text"] for r in md_matches)
            modality_status = "confirmed-text" if md_text else "modality-unverified"
        else:
            modality_status = ""
        if efforts:
            or_reasoning_status = "listed"
        elif not or_ids:
            or_reasoning_status = "no-or-listing"
        elif md_reasoning_any or zm_reason_any:
            or_reasoning_status = "metadata-missing"
        elif (md_all_no_reasoning and md_has) or zm_all_false:
            or_reasoning_status = "non-reasoning"
        else:
            or_reasoning_status = "metadata-missing"
        zm_reason_flag = True if zm_reason_any else (False if zm_all_false else None)
        zm_out = next((z.get("output_modalities", []) for z in zm_matches if z.get("output_modalities")), [])
        fallback_id, fallback_provider = "", ""
        if not disp_or:
            for prov_key in ("oai", "ant", "nvidia", "zenmux", "zen"):
                if u[prov_key]:
                    fallback_id = sorted(u[prov_key])[0]
                    fallback_provider = {"oai": "openai", "ant": "anthropic"}.get(prov_key, prov_key)
                    break
        models.append({"id": disp, "slug": key, "or_id": disp_or, "name": name, "groups": groups,
                       "providers": providers, "score": score, "cost_blended": cost,
                       "cost_source": cost_source,
                       "bench_only": bool(not providers and not aa_match and (u.get("benchlm") or u.get("llm"))),
                       "ratio": ratio, "context": or_ctx.get(disp_or),
                       "free": free, "router": router, "tier": tier_of(score),
                       "free_status": free_status, "free_evidence": free_evidence,
                       "variant": variant, "aa_variant_name": aa_name_raw,
                       "aa_id": aa_slug_raw,
                       "efforts": efforts, "default_effort": default_effort,
                       "efforts_source": efforts_source, "default_effort_source": default_effort_source,
                       "or_reasoning_status": or_reasoning_status,
                       "deprecated_upstream": deprecated_upstream, "deprecated_sources": deprecated_sources,
                       "modality_status": modality_status,
                       "modelsdev_count": len(md_matches), "modelsdev_efforts": md_efforts_union,
                       "zenmux_reasoning": zm_reason_flag, "zenmux_output": zm_out,
                       "fallback_id": fallback_id, "fallback_provider": fallback_provider,
                       "routes": [{"provider": prov, "id": rid,
                                   "free_evidence": (["or:strict-free"] if prov == "openrouter" and rid in or_free
                                                     else ["zen:free-route"] if prov == "zen" and rid.endswith("-free")
                                                     else [])}
                                  for prov in ("openrouter", "openai", "anthropic", "nvidia", "zenmux", "zen")
                                  for rid in sorted(ent["routes"].get(prov, []))],
                       "identity": {"key": ent["key"], "basis": ent["basis"], "vendor": ent["vendor"],
                                    "tail": ent["tail"], "conflicts": ent["conflicts"]},
                       "canonical_id": ent["canonical_id"]})

    try:
        from .enrichment import enrich
        from .registry import evidence_status
    except ImportError:
        from enrichment import enrich
        from registry import evidence_status
    with open(registry_path or os.path.join(ROOT, 'analysis', 'research.json'), encoding='utf-8') as f:
        research = json.load(f)
    registry_missing = enrich(models, research, day, md_by_slug)

    # Backlog: effort-disambiguation + callable hints (pure local, post-enrich so derived rows group).
    CALLABLE_SET = {"openai", "anthropic", "openrouter", "nvidia", "zenmux", "zen"}
    families = {}
    for m in models:
        fam = family_of(m.get("slug", ""), m.get("variant", ""))
        families.setdefault(fam, []).append(m)
    for fam, members in families.items():
        scored_variants = sorted({x.get("variant", "") for x in members if x.get("score") is not None and x.get("variant")})
        scored_nonempty = len(scored_variants)
        # Sibling efforts source: highest-scored member with OR-listed efforts.
        donors = sorted([x for x in members if x.get("efforts") and x.get("efforts_source") == "or"],
                        key=lambda r: (-(r.get("score") if r.get("score") is not None else -1)))
        donor = donors[0] if donors else None
        callables = [x for x in members if x.get("or_id") or (set(x.get("providers", [])) & CALLABLE_SET)]
        callables_sorted = sorted(callables, key=lambda r: (-(r.get("score") if r.get("score") is not None else -1)))
        best_callable = callables_sorted[0] if callables_sorted else None
        for m in members:
            # variant ambiguity: scored base in a family that already has effort-specific scored rows.
            if m.get("score") is not None and not m.get("variant"):
                if len(members) == 1 and scored_nonempty == 0:
                    m["variant_ambiguous"] = False
                    m["variant_label"] = "base (unspecified effort)"
                elif scored_nonempty >= 1:
                    m["variant_ambiguous"] = True
                    m["variant_label"] = "ambiguous-effort"
                else:
                    m["variant_ambiguous"] = False
                    m["variant_label"] = "base (unspecified effort)"
            else:
                m["variant_ambiguous"] = False
                m["variant_label"] = m.get("variant", "") or ""
            # efforts hint from sibling OR.
            if not m.get("efforts") and donor is not None and donor is not m:
                m["efforts_hint"] = list(donor.get("efforts") or [])
                m["efforts_hint_source"] = "sibling"
                m["efforts_hint_from"] = donor.get("slug", "")
            else:
                m.setdefault("efforts_hint", [])
                m.setdefault("efforts_hint_source", "")
                m.setdefault("efforts_hint_from", "")
            # nearest callable for AA-only (display only, never copyable).
            if not m.get("or_id") and not (set(m.get("providers", [])) & CALLABLE_SET):
                if best_callable is not None:
                    m["nearest_callable"] = best_callable.get("id", "")
                    m["nearest_callable_slug"] = best_callable.get("slug", "")
                else:
                    m.setdefault("nearest_callable", "")
                    m.setdefault("nearest_callable_slug", "")
            else:
                m.setdefault("nearest_callable", "")
                m.setdefault("nearest_callable_slug", "")
            # Backfill Tier 1 / provenance for derived rows (slug has __variant suffix).
            if not m.get("cost_source"):
                m["cost_source"] = "inherited" if m.get("history_excluded") else "none"
            m.setdefault("efforts_source", "inherited" if m.get("history_excluded") else ("or" if m.get("efforts") else ""))
            m.setdefault("default_effort_source", "or" if m.get("default_effort") else ("unspecified-upstream" if m.get("efforts") else ""))
            m.setdefault("or_reasoning_status", "no-or-listing" if not m.get("or_id") and not m.get("efforts") else m.get("or_reasoning_status", ""))
            m.setdefault("deprecated_upstream", False)
            m.setdefault("deprecated_sources", [])
            m.setdefault("modality_status", "")
            m.setdefault("modelsdev_count", 0)
            m.setdefault("modelsdev_efforts", [])
            m.setdefault("zenmux_reasoning", None)
            m.setdefault("zenmux_output", [])

    # Route history (churn) is prepared/published by pipeline.py, never here.
    # v2 entity/observation layer (additive — legacy models[] output preserved).
    try:
        from .crosswalk import attach_crosswalk
        from .observations import build_observations
        from .scales import problems as obs_problems
        from .views import build_views
    except ImportError:
        from crosswalk import attach_crosswalk
        from observations import build_observations
        from scales import problems as obs_problems
        from views import build_views
    bench_meta = attach_crosswalk(models, snap, websites)
    observations = build_observations(models, day, snap.get("source_health", {}))
    bad_obs = [(o["obs_id"], p) for o in observations for p in obs_problems(o)]
    if bad_obs:
        print(f"warn {len(bad_obs)} observation contract problems, e.g. {bad_obs[:3]}")
    views = build_views(models)
    bench_lb = (snap.get("benchlm", {}) or {}).get("leaderboard", []) if isinstance(snap.get("benchlm"), dict) else []
    bench_pr = (snap.get("benchlm", {}) or {}).get("pricing", []) if isinstance(snap.get("benchlm"), dict) else []
    llm_snap = snap.get("llmstats", {}) if isinstance(snap.get("llmstats"), dict) else {}
    vals_snap = snap.get("vals", {}) if isinstance(snap.get("vals"), dict) else {}
    web_stats = {"allowlist": len((websites or {}).get("allowlist", [])),
                 "benchlm_md": len((websites or {}).get("benchlm_md", {})),
                 "llmstats": len((websites or {}).get("llmstats", {})),
                 "vals": len((websites or {}).get("vals", {}))} if websites else {}
    from collections import Counter as _Counter
    _fsc = _Counter(m.get("free_status", "none") for m in models)

    out = {"stamp": stamp, "run_id": snap.get("run_id", stamp), "schema_version": SCHEMA_VERSION,
           "started_at": snap.get("started_at"), "source_health": snap.get("source_health", {}),
           "website_health": websites.get("source_health", {}),
           "day": day, "total_openrouter": len(or_rows), "free_count": len(free_ids),
           "total_openai": len(oai_rows), "openai_ids": sorted([r["id"] for r in oai_rows]),
           "openai_retired": sorted([r["id"] for r in oai_rows if r["shutdown"]])[:50],
           "total_anthropic": len(ant_rows), "anthropic_ids": sorted([r["id"] for r in ant_rows]),
           "total_nvidia": len(nvidia_rows), "nvidia_ids": sorted([r["id"] for r in nvidia_rows]),
           "total_zenmux": len(zenmux_rows), "zenmux_ids": sorted([r["id"] for r in zenmux_rows]),
           "total_zen": len(zen_rows), "zen_ids": sorted([r["id"] for r in zen_rows]),
           "total_modelsdev": len(modelsdev),
           "total_aa": len(aa_rows),
           "total_benchlm": len(bench_lb) if isinstance(bench_lb, list) else 0,
           "total_benchlm_pricing": len(bench_pr) if isinstance(bench_pr, list) else 0,
           "benchlm_meta": bench_meta,
           "llmstats_status": ({"models": llm_snap.get("model_count", 0),
                                  "benchmarks": llm_snap.get("benchmark_count", 0),
                                  "rank_cats": sorted((llm_snap.get("rankings", {}) or {}).keys()),
                                  "details": len(llm_snap.get("details", {}) or {}),
                                  "quota_remaining": (llm_snap.get("meta", {}) or {}).get("quota_remaining"),
                                  **{k: v for k, v in llm_snap.items() if k in ("skipped", "error")}}
                                 if isinstance(llm_snap, dict) else {}),
           "vals_status": ({"count": len(vals_snap.get("models", [])), **{k: v for k, v in vals_snap.items() if k in ("skipped", "error", "source")}}
                           if isinstance(vals_snap, dict) else {}),
           "website_stats": web_stats,
           "views": views,
           "observations_count": len(observations), "observations": observations,
           "free_status_counts": {"verified": _fsc.get("verified", 0),
                                  "provisional-l1": _fsc.get("provisional-l1", 0),
                                  "provisional-l0": _fsc.get("provisional-l0", 0),
                                  "none": _fsc.get("none", 0)},
           "models": models, "identity_conflicts": identity_conflicts,
           "registry_missing_targets": registry_missing,
           "evidence_status": evidence_status(research, day),
           "thresholds": dict(TIERS),
           "cost_method": "aa_blended_primary_or_derived_fallback_per_1M"}
    if output_dir is None:
        raise ValueError("analysis requires an output directory")
    ap = os.path.join(output_dir, f"{stamp}_analysis.json")
    atomic_json(ap, out)
    print(f"{stamp}: OR={len(or_rows)} free={len(free_ids)} OAI={len(oai_rows)} ANT={len(ant_rows)} "
          f"NV={len(nvidia_rows)} ZM={len(zenmux_rows)} ZEN={len(zen_rows)} "
          f"MD={len(modelsdev)} AA={len(aa_rows)} BENCHLM={len(bench_lb) if isinstance(bench_lb, list) else 0} "
          f"VALS={(len(vals_snap.get('models', [])) if isinstance(vals_snap, dict) and isinstance(vals_snap.get('models'), list) else vals_snap)} "
          f"OBS={len(observations)} -> {ap}")
    return ap

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--websites")
    parser.add_argument("--registry")
    parser.add_argument("--as-of")
    parser.add_argument("--identity")
    args = parser.parse_args()
    main(args.input, args.output, args.websites, args.registry, args.as_of, args.identity)
