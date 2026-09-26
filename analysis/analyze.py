"""2. Data Analysis — normalize all providers, free-classify, diff vs sqlite, combined rank."""
import json, os, glob, sqlite3, datetime, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "raw")
DB = os.path.join(ROOT, "analysis", "store.sqlite")
os.makedirs(os.path.dirname(DB), exist_ok=True)

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

def norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


EFFORTS_ORDERED = ["max", "xhigh", "high", "medium", "low", "minimal", "none"]


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

def main():
    raw_files = glob.glob(os.path.join(RAW, "*_models.json"))
    if not raw_files:
        print("no snapshots in raw/")
        return
    files = sorted(raw_files, key=os.path.getmtime)
    with open(files[-1], encoding="utf-8") as f:
        snap = json.load(f)
    stamp = str(snap.get("retrieved_at", datetime.datetime.now().strftime("%Y-%m-%d_%H%M")))
    day = stamp[:10]

    ors = snap.get("openrouter", []) if isinstance(snap.get("openrouter"), list) else []
    oai = snap.get("openai", []) if isinstance(snap.get("openai"), list) else []
    ant = snap.get("anthropic", []) if isinstance(snap.get("anthropic"), list) else []
    groq = snap.get("groq", []) if isinstance(snap.get("groq"), list) else []
    cerebras = snap.get("cerebras", []) if isinstance(snap.get("cerebras"), list) else []
    nvidia = snap.get("nvidia", []) if isinstance(snap.get("nvidia"), list) else []
    zenmux = snap.get("zenmux", []) if isinstance(snap.get("zenmux"), list) else []
    zen = snap.get("zen", []) if isinstance(snap.get("zen"), list) else []
    modelsdev_raw = snap.get("modelsdev", [])
    modelsdev = modelsdev_raw if isinstance(modelsdev_raw, list) else []
    aa_raw = snap.get("aa", {})
    aa = aa_raw.get("data", []) if isinstance(aa_raw, dict) else []

    or_rows = [{"id": m.get("id", ""), "name": m.get("name", ""), "context": m.get("context_length"),
                "free": (is_free_or(m.get("pricing", {})) or str(m.get("id", "")).endswith(":free"))
                        and (m.get("architecture") or {}).get("output_modalities") == ["text"]
                        and not str(m.get("id", "")).startswith("openrouter/")}
               for m in ors]
    free_ids = sorted([r["id"] for r in or_rows if r["free"]])

    oai_rows = [{"id": m.get("id", ""), "owned_by": m.get("owned_by", ""), "shutdown": m.get("shutdown_date", "")} for m in oai]
    ant_rows = [{"id": m.get("id", ""), "name": m.get("display_name", ""),
                 "ctx_in": m.get("max_input_tokens"), "ctx_out": m.get("max_tokens")} for m in ant]
    groq_rows = [{"id": m.get("id", ""), "owned_by": m.get("owned_by", "")} for m in groq]
    cerebras_rows = [{"id": m.get("id", ""), "owned_by": m.get("owned_by", "")} for m in cerebras]
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
    aa_by_slug = {norm(r["id"]): r for r in aa_rows}

    # Canonical deduped models (reports-layer union; raw snapshots untouched).
    TIER_MAX, TIER_HIGH, TIER_MED = 50, 40, 30

    def tier_of(score):
        if score is None:
            return ""
        if score >= TIER_MAX:
            return "max"
        if score >= TIER_HIGH:
            return "high"
        if score >= TIER_MED:
            return "medium"
        return "below"

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

    def base_slug(mid):
        return norm(str(mid).split(":")[0].split("/")[-1])

    def family_of(slug, variant):
        s = str(slug or "")
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
    aa_by_base = {base_slug(k): v for k, v in aa_by_slug.items()}

    def _entry():
        return {"or": [], "oai": [], "ant": [], "groq": [], "cerebras": [],
                "nvidia": [], "zenmux": [], "zen": [], "aa": None}

    union = {}
    for m in ors:
        mid = m.get("id", "")
        union.setdefault(base_slug(mid), _entry())
        union[base_slug(mid)]["or"].append(mid)
    for m in oai:
        union.setdefault(base_slug(m.get("id", "")), _entry())
        union[base_slug(m.get("id", ""))]["oai"].append(m.get("id", ""))
    for m in ant:
        union.setdefault(base_slug(m.get("id", "")), _entry())
        union[base_slug(m.get("id", ""))]["ant"].append(m.get("id", ""))
    for m in groq:
        union.setdefault(base_slug(m.get("id", "")), _entry())
        union[base_slug(m.get("id", ""))]["groq"].append(m.get("id", ""))
    for m in cerebras:
        union.setdefault(base_slug(m.get("id", "")), _entry())
        union[base_slug(m.get("id", ""))]["cerebras"].append(m.get("id", ""))
    for m in nvidia:
        union.setdefault(base_slug(m.get("id", "")), _entry())
        union[base_slug(m.get("id", ""))]["nvidia"].append(m.get("id", ""))
    for m in zenmux:
        union.setdefault(base_slug(m.get("id", "")), _entry())
        union[base_slug(m.get("id", ""))]["zenmux"].append(m.get("id", ""))
    for m in zen:
        union.setdefault(base_slug(m.get("id", "")), _entry())
        union[base_slug(m.get("id", ""))]["zen"].append(m.get("id", ""))
    for m in aa:
        key = base_slug(m.get("slug", "") or m.get("id", ""))
        union.setdefault(key, _entry())
        union[key]["aa"] = m

    collisions = []
    for key, entry in union.items():
        bases = {i.split(":")[0] for i in entry["or"]}
        if len(bases) > 1:
            collisions.append({"slug": key, "ids": sorted(entry["or"])})
    if collisions:
        print(f"note: {len(collisions)} slug-collision merges (same tail slug, kept merged): " +
              ", ".join(c["slug"] for c in collisions[:10]))

    models = []
    for key in sorted(union):
        u = union[key]
        zen_free_ids = [i for i in u["zen"] if str(i).endswith("-free")]
        free = any(i in or_free for i in u["or"]) or bool(zen_free_ids)
        zen_free = bool(zen_free_ids)
        aa_match = aa_by_base.get(key)
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
        if u["groq"]:
            providers.append("groq")
        if u["cerebras"]:
            providers.append("cerebras")
        if u["nvidia"]:
            providers.append("nvidia")
        if u["zenmux"]:
            providers.append("zenmux")
        if u["zen"]:
            providers.append("zen")
        aa_match = aa_by_base.get(key)
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
        disp = (u["oai"] or u["ant"] or ([disp_or] if disp_or else []) or
                u["groq"] or u["cerebras"] or u["nvidia"] or u["zenmux"] or u["zen"] or
                ([aa_match.get("slug", "") or aa_match.get("id", "")] if aa_match else [""]))[0]
        name = (next((or_name.get(i, "") for i in or_ids if or_name.get(i)), "") or
                next((ant_name.get(i, "") for i in u["ant"] if ant_name.get(i)), "") or
                next((zenmux_name.get(i, "") for i in u["zenmux"] if zenmux_name.get(i)), "") or
                ((aa_match or {}).get("name", "")) or
                ((u["groq"][:1] + [""])[0]) or ((u["cerebras"][:1] + [""])[0]) or
                ((u["nvidia"][:1] + [""])[0]) or ((u["zen"][:1] + [""])[0]))
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
        md_matches = md_by_slug.get(key, [])
        zm_matches = zenmux_by_slug.get(key, [])
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
            for prov_key in ("oai", "ant", "groq", "cerebras", "nvidia", "zenmux", "zen"):
                if u[prov_key]:
                    fallback_id = sorted(u[prov_key])[0]
                    fallback_provider = {"oai": "openai", "ant": "anthropic"}.get(prov_key, prov_key)
                    break
        models.append({"id": disp, "slug": key, "or_id": disp_or, "name": name, "groups": groups,
                       "providers": providers, "score": score, "cost_blended": cost,
                       "cost_source": cost_source,
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
                       "fallback_id": fallback_id, "fallback_provider": fallback_provider})

    try:
        from .enrichment import enrich
    except ImportError:
        from enrichment import enrich
    with open(os.path.join(ROOT, 'analysis', 'research.json'), encoding='utf-8') as f:
        enrich(models, json.load(f), day, md_by_slug)

    # Backlog: effort-disambiguation + callable hints (pure local, post-enrich so derived rows group).
    CALLABLE_SET = {"openai", "anthropic", "openrouter", "groq", "cerebras", "nvidia", "zenmux", "zen"}
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

    con = sqlite3.connect(DB)
    cols = [r[1] for r in con.execute("PRAGMA table_info(models)")]
    if cols and "source" not in cols:
        con.execute(f"ALTER TABLE models RENAME TO models_old_{stamp.replace('-', '')}")
    con.execute("CREATE TABLE IF NOT EXISTS models(id TEXT, source TEXT, day TEXT, free INT, PRIMARY KEY(id, source, day))")
    con.execute("CREATE TABLE IF NOT EXISTS free_history(slug TEXT, day TEXT, free_status TEXT, disp_id TEXT, PRIMARY KEY(slug, day))")
    prev_or_rows = con.execute(
        "SELECT id, free FROM models WHERE source='openrouter' AND day="
        "(SELECT MAX(day) FROM models WHERE source='openrouter' AND day<?)", (day,)).fetchall()
    prev_or_free = {r[0]: r[1] for r in prev_or_rows}
    prev_or = set(prev_or_free)
    for r in or_rows:
        con.execute("INSERT OR REPLACE INTO models VALUES(?,?,?,?)", (r["id"], "openrouter", day, int(r["free"])))
    for r in oai_rows:
        con.execute("INSERT OR REPLACE INTO models VALUES(?,?,?,?)", (r["id"], "openai", day, 0))
    for r in ant_rows:
        con.execute("INSERT OR REPLACE INTO models VALUES(?,?,?,?)", (r["id"], "anthropic", day, 0))
    for r in groq_rows:
        con.execute("INSERT OR REPLACE INTO models VALUES(?,?,?,?)", (r["id"], "groq", day, 0))
    for r in cerebras_rows:
        con.execute("INSERT OR REPLACE INTO models VALUES(?,?,?,?)", (r["id"], "cerebras", day, 0))
    for r in nvidia_rows:
        con.execute("INSERT OR REPLACE INTO models VALUES(?,?,?,?)", (r["id"], "nvidia", day, 0))
    for r in zenmux_rows:
        con.execute("INSERT OR REPLACE INTO models VALUES(?,?,?,?)", (r["id"], "zenmux", day, 0))
    for r in zen_rows:
        con.execute("INSERT OR REPLACE INTO models VALUES(?,?,?,?)", (r["id"], "zen", day, 0))
    # Canonical free-status history (non-router rows only; reports filter routers).
    canon = [(m.get("slug") or base_slug(m.get("id", "")), m.get("free_status", "none"), m.get("id", ""))
             for m in models if not m.get("router") and not m.get("history_excluded") and (m.get("slug") or m.get("id"))]
    cur_free = {s: f for s, f, _ in canon}
    cur_disp = {s: d for s, f, d in canon}
    for s, f, d in canon:
        con.execute("INSERT OR REPLACE INTO free_history VALUES(?,?,?,?)", (s, day, f, d))
    con.commit()
    cur_or = {r["id"] for r in or_rows}
    cur_or_free = {r["id"]: int(r["free"]) for r in or_rows}
    new_or = sorted(cur_or - prev_or) if prev_or else []
    removed_or = sorted(prev_or - cur_or) if prev_or else []
    both_or = cur_or & prev_or
    or_to_paid = sorted(i for i in both_or if prev_or_free.get(i) == 1 and cur_or_free.get(i) == 0)
    or_to_free = sorted(i for i in both_or if prev_or_free.get(i) == 0 and cur_or_free.get(i) == 1)
    hist_days = [r[0] for r in con.execute("SELECT DISTINCT day FROM models ORDER BY day")]
    fh_days = [r[0] for r in con.execute("SELECT DISTINCT day FROM free_history ORDER BY day")]
    prev_fh_day = max([d for d in fh_days if d < day], default=None)
    if prev_fh_day:
        prev_free = {r[0]: (r[1], r[2]) for r in con.execute(
            "SELECT slug, free_status, disp_id FROM free_history WHERE day=?", (prev_fh_day,))}
    else:
        prev_free = {}
    _FREEISH = ("verified", "provisional-l1", "provisional-l0")
    new_slugs = sorted(set(cur_free) - set(prev_free)) if prev_free else []
    disappeared = sorted(set(prev_free) - set(cur_free)) if prev_free else []
    to_paid, to_free, level = [], [], []
    for s in set(cur_free) & set(prev_free):
        pf = prev_free[s][0]
        cf = cur_free[s]
        if pf in _FREEISH and cf == "none":
            to_paid.append(s)
        elif pf == "none" and cf in _FREEISH:
            to_free.append(s)
        elif pf != cf:
            level.append(s)
    def _cur_disp(slugs):
        return sorted(cur_disp.get(s, s) for s in slugs)
    free_churn = {"prev_day": prev_fh_day,
                  "new_slugs": _cur_disp(new_slugs)[:50], "new_total": len(new_slugs),
                  "disappeared": sorted(prev_free[s][1] for s in disappeared)[:50],
                  "disappeared_total": len(disappeared),
                  "flipped_to_paid": _cur_disp(to_paid)[:50], "flipped_to_paid_total": len(to_paid),
                  "flipped_to_free": _cur_disp(to_free)[:50], "flipped_to_free_total": len(to_free),
                  "level_changed": _cur_disp(level)[:50], "level_changed_total": len(level),
                  "or_flipped_to_paid": or_to_paid[:50], "or_flipped_to_paid_total": len(or_to_paid),
                  "or_flipped_to_free": or_to_free[:50], "or_flipped_to_free_total": len(or_to_free)}
    from collections import Counter as _Counter
    _fsc = _Counter(m.get("free_status", "none") for m in models)

    out = {"stamp": stamp, "day": day, "total_openrouter": len(or_rows), "free_count": len(free_ids),
           "new_ids_vs_history": new_or[:50], "new_total": len(new_or),
           "removed_ids_vs_history": removed_or[:50], "removed_total": len(removed_or), "history_days": hist_days,
           "total_openai": len(oai_rows), "openai_ids": sorted([r["id"] for r in oai_rows]),
           "openai_retired": sorted([r["id"] for r in oai_rows if r["shutdown"]])[:50],
           "total_anthropic": len(ant_rows), "anthropic_ids": sorted([r["id"] for r in ant_rows]),
           "total_groq": len(groq_rows), "groq_ids": sorted([r["id"] for r in groq_rows]),
           "total_cerebras": len(cerebras_rows), "cerebras_ids": sorted([r["id"] for r in cerebras_rows]),
           "total_nvidia": len(nvidia_rows), "nvidia_ids": sorted([r["id"] for r in nvidia_rows]),
           "total_zenmux": len(zenmux_rows), "zenmux_ids": sorted([r["id"] for r in zenmux_rows]),
           "total_zen": len(zen_rows), "zen_ids": sorted([r["id"] for r in zen_rows]),
           "total_modelsdev": len(modelsdev),
           "total_aa": len(aa_rows),
           "free_churn": free_churn,
           "free_status_counts": {"verified": _fsc.get("verified", 0),
                                  "provisional-l1": _fsc.get("provisional-l1", 0),
                                  "provisional-l0": _fsc.get("provisional-l0", 0),
                                  "none": _fsc.get("none", 0)},
           "models": models, "collisions": collisions,
           "thresholds": {"max": TIER_MAX, "high": TIER_HIGH, "medium": TIER_MED},
           "cost_method": "aa_blended_primary_or_derived_fallback_per_1M"}
    ap = os.path.join(ROOT, "analysis", f"{stamp}_analysis.json")
    with open(ap, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    afiles = sorted(glob.glob(os.path.join(ROOT, "analysis", "*_analysis.json")), key=os.path.getmtime)
    for old in afiles[:-1]:
        os.remove(old)
        print(f"pruned analysis {os.path.basename(old)}")
    print(f"{stamp}: OR={len(or_rows)} free={len(free_ids)} OAI={len(oai_rows)} ANT={len(ant_rows)} "
          f"GROQ={len(groq_rows)} CER={len(cerebras_rows)} NV={len(nvidia_rows)} ZM={len(zenmux_rows)} ZEN={len(zen_rows)} "
          f"MD={len(modelsdev)} AA={len(aa_rows)} new={len(new_or)} removed={len(removed_or)} "
          f"churn_vs={prev_fh_day} to_paid={len(to_paid)} to_free={len(to_free)} gone={len(disappeared)} days={len(hist_days)} -> {ap}")
    con.close()

if __name__ == "__main__":
    main()
