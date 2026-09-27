"""Evidence-backed enrichment. Never compare scores across benchmark revisions."""
import copy
import datetime
import math

try:
    from .common import tier_of
except ImportError:
    from common import tier_of


def current(record, day):
    return record['checked_at'] <= day <= record['expires_at']


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def enrich(models, registry, day, modelsdev_by_slug=None):
    """Mutate base rows and append explicitly evidenced route/effort estimates.

    Returns registry slugs that match no model (e.g. after an identity split), so a
    slug change can never silently drop evidence.
    """
    datetime.date.fromisoformat(day)
    cohort = registry.get('snapshot_benchmarks', {}).get(day)
    if not cohort:
        known = registry.get('snapshot_benchmarks', {})
        if known:
            latest = max(known)
            cohort = known[latest]
            print(f"warn no AA benchmark pinned for day {day}; defaulting to latest known {cohort} from {latest} — pin this day in research.json")
        else:
            print(f"warn no AA snapshot_benchmarks at all; external AA-version scores stay reference-only")
    by_slug = {m['slug']: m for m in models}
    modelsdev_by_slug = modelsdev_by_slug or {}
    for m in models:
        m['score_source'] = ({'kind': 'aa-api', 'benchmark': 'aa-intelligence-index',
                              'version': cohort, 'checked_at': day,
                              'url': 'https://artificialanalysis.ai/models/' + m.get('aa_id', '')}
                             if m.get('score') is not None else None)
        m['external_scores'] = []
        m['research_notes'] = []
    missing = sorted({s for r in registry.get('scores', []) for s in [r['target_slug']] if s not in by_slug} |
                     {s for r in registry.get('inheritance', []) for s in (r['target_slug'], r['source_slug'])
                      if s not in by_slug})
    if missing:
        print(f"warn research.json slugs match no model: {missing} — renamed or split? update the registry")
    for record in registry.get('scores', []):
        m = by_slug.get(record['target_slug'])
        if m is None:
            continue
        evidence = copy.deepcopy(record)
        evidence['eligible'] = (current(record, day) and finite(record['value']) and
                                record['variant'] == m.get('variant', '') and
                                record['benchmark'] == 'aa-intelligence-index' and
                                bool(cohort) and record['version'] == cohort)
        m['external_scores'].append(evidence)
        if evidence['eligible'] and m.get('score') is None:
            m['score'] = record['value']
            m['score_source'] = dict(evidence, kind='external')
    for record in registry.get('inheritance', []):
        target = by_slug.get(record['target_slug'])
        source = by_slug.get(record['source_slug'])
        if target is None:
            continue
        target['research_notes'].append(record)
        # An estimate is a new effort-specific row, never a silent base-score replacement.
        if (not source or not current(record, day) or not record.get('equivalence_urls') or
                not record.get('capability_url') or not record.get('rationale') or
                record['variant'] not in record['supported_efforts'] or
                source.get('variant') != record['variant'] or not finite(source.get('score')) or
                record['provider'] not in target.get('providers', []) or
                target.get('score') is not None):
            continue
        # Tier 1: validate supported efforts against models.dev capabilities when available.
        md_list = modelsdev_by_slug.get(record['target_slug'], [])
        if md_list:
            md_efforts = set()
            for r in md_list:
                md_efforts.update(r.get('reasoning_efforts') or [])
            if md_efforts and not set(record.get('supported_efforts', [])).issubset(md_efforts):
                continue
        derived = copy.deepcopy(target)
        derived.update(slug=target['slug'] + '__' + record['variant'],
                       id=target['id'] + ' (' + record['variant'] + ')',
                       variant=record['variant'], efforts=record['supported_efforts'],
                       efforts_source='inherited',
                       score=source['score'], history_excluded=True,
                       fallback_id=record['route_id'], fallback_provider=record['provider'],
                       selector=record['selector'], or_id='',
                       cost_source='inherited')
        # Price belongs to the destination route, not the benchmark's paid endpoint.
        derived['cost_blended'] = record['cost_blended']
        derived['score_source'] = dict(record, kind='inherited-estimate',
                                       upstream=source['score_source'])
        models.append(derived)
    for m in models:
        score, cost = m.get('score'), m.get('cost_blended')
        m['ratio'] = round(score / cost, 4) if score is not None and cost and cost > 0 and not m.get('free') else None
        m['tier'] = tier_of(score)
    return missing
