"""Provider identity rules (analysis/identity.py); pure, network-free."""
import contextlib
import io
from pathlib import Path
import random
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analysis import identity  # noqa: E402
from analysis.enrichment import enrich  # noqa: E402

ALIASES = identity.load_overrides()
EVIDENCE = {"evidence_urls": ["https://example.invalid/a"], "checked_at": "2026-09-27", "rationale": "test"}


def resolve(routes, aa=(), **overrides):
    return identity.resolve(routes, aa, dict(ALIASES, **overrides))


def slug_of(result, provider, rid):
    return result["route_entity"][(provider, rid)]


class IdentityTests(unittest.TestCase):
    def test_same_tail_two_vendors_stay_separate(self):
        r = resolve({"openrouter": ["acme/nova-1"], "nvidia": ["orbit/nova-1"]})
        self.assertEqual(sorted(r["entities"]), ["nova1.acme", "nova1.orbit"])
        (c,) = r["conflicts"]
        self.assertEqual(c["kind"], "vendor-collision")
        self.assertEqual(c["entities"], ["nova1.acme", "nova1.orbit"])

    def test_openrouter_joins_native_openai(self):
        r = resolve({"openrouter": ["openai/gpt-6"], "openai": ["gpt-6"]}, [{"slug": "gpt-6", "creator": "OpenAI"}])
        (e,) = r["entities"].values()
        self.assertEqual((e["slug"], e["key"], e["basis"], e["aa"]), ("gpt6", "openai/gpt6", "exact", "gpt-6"))
        self.assertEqual(e["routes"], {"openai": ["gpt-6"], "openrouter": ["openai/gpt-6"]})

    def test_zen_unique_tail_joins_and_ambiguous_tail_stays_alone(self):
        r = resolve({"openrouter": ["deepseek/deepseek-v4"], "zen": ["deepseek-v4"]})
        self.assertEqual(slug_of(r, "zen", "deepseek-v4"), "deepseekv4")
        self.assertEqual(r["entities"]["deepseekv4"]["basis"], "unique-tail")
        r = resolve({"openrouter": ["acme/nova-1"], "nvidia": ["orbit/nova-1"], "zen": ["nova-1"]})
        self.assertEqual(slug_of(r, "zen", "nova-1"), "nova1.zen")
        self.assertIn("ambiguous-tail", {c["kind"] for c in r["conflicts"]})
        self.assertEqual(r["entities"]["nova1.zen"]["conflicts"][0]["kind"], "ambiguous-tail")

    def test_aa_slugs_differing_only_in_creator(self):
        aa = [{"slug": "atlas-2", "creator": "Acme"}, {"slug": "atlas-2-", "creator": "Orbit"}]
        r = resolve({"openrouter": ["acme/atlas-2"]}, aa)
        self.assertEqual(r["aa_entity"]["atlas-2"], "atlas2.acme")
        self.assertEqual(r["aa_entity"]["atlas-2-"], "atlas2.orbit")
        self.assertEqual(r["entities"]["atlas2.acme"]["routes"], {"openrouter": ["acme/atlas-2"]})
        # Same creator twice: the first slug is kept and the duplicate is recorded, not overwritten.
        r = resolve({}, [{"slug": "atlas-2", "creator": "Acme"}, {"slug": "atlas2", "creator": "Acme"}])
        self.assertEqual(r["aa_entity"], {"atlas-2": "atlas2"})
        self.assertEqual([c["kind"] for c in r["conflicts"]], ["aa-duplicate"])

    def test_unaliased_aa_creator_joins_single_entity_and_is_flagged(self):
        r = resolve({"openrouter": ["newco/zeta-1"]}, [{"slug": "zeta-1", "creator": "NewCo Labs"}])
        self.assertEqual(r["aa_entity"]["zeta-1"], "zeta1")
        self.assertEqual([c["kind"] for c in r["conflicts"]], ["aa-creator-unaliased"])

    def test_step5_aliases_join_without_conflict(self):
        # Owner's 2026-09-27 replay: AA credits Grok to "SpaceX AI" and LongCat to "LongCat".
        r = resolve({"openrouter": ["x-ai/grok-4.5", "meituan/longcat-2.0"], "zen": ["grok-4.5"]},
                    [{"slug": "grok-4-5", "creator": "SpaceX AI"}, {"slug": "longcat-2-0", "creator": "LongCat"}])
        self.assertEqual(r["conflicts"], [])
        self.assertEqual((r["aa_entity"]["grok-4-5"], r["entities"]["grok45"]["key"]), ("grok45", "xai/grok45"))
        self.assertEqual(r["entities"]["longcat20"]["key"], "meituan/longcat20")

    def test_explicit_join_and_split(self):
        routes = {"openrouter": ["acme/nova-1"], "nvidia": ["orbit/nova-1"]}
        join = dict(EVIDENCE, routes=[{"provider": "openrouter", "id": "acme/nova-1"},
                                      {"provider": "nvidia", "id": "orbit/nova-1"}])
        r = resolve(routes, joins=[join])
        (e,) = r["entities"].values()
        self.assertEqual((e["basis"], e["routes"]), ("explicit", {"nvidia": ["orbit/nova-1"], "openrouter": ["acme/nova-1"]}))
        split = dict(EVIDENCE, routes=[{"provider": "nvidia", "id": "acme/nova-1"}])
        r = resolve({"openrouter": ["acme/nova-1"], "nvidia": ["acme/nova-1"]}, splits=[split])
        self.assertEqual(len(r["entities"]), 2)
        self.assertEqual(r["entities"][slug_of(r, "nvidia", "acme/nova-1")]["basis"], "explicit")

    def test_vendor_alias(self):
        r = resolve({"openrouter": ["meta-llama/llama-4"], "nvidia": ["meta/llama-4"]}, [{"slug": "llama-4", "creator": "Meta"}])
        (e,) = r["entities"].values()
        self.assertEqual((e["slug"], e["vendor"], e["basis"]), ("llama4", "meta", "alias"))

    def test_zen_free_route_churn_group_follows_paid_counterpart(self):
        r = resolve({"openrouter": ["moonshotai/kimi-k3"], "zen": ["kimi-k3-free"]})
        self.assertEqual(r["entities"]["kimik3free"]["canonical_id"], "kimik3")
        self.assertEqual(r["entities"]["kimik3"]["canonical_id"], "kimik3")

    def test_result_does_not_depend_on_input_order(self):
        routes = {"openrouter": ["acme/nova-1", "openai/gpt-6", "meta-llama/llama-4", "x/a:free"],
                  "nvidia": ["orbit/nova-1", "meta/llama-4"], "openai": ["gpt-6"], "zen": ["nova-1", "a-free", "b"]}
        aa = [{"slug": "gpt-6", "creator": "OpenAI"}, {"slug": "nova-1", "creator": "Acme"}, {"slug": "b", "creator": "Bee"}]
        expected = resolve(routes, aa)
        rng = random.Random(7)
        for _ in range(5):
            shuffled = {p: rng.sample(ids, len(ids)) for p, ids in reversed(list(routes.items()))}
            self.assertEqual(resolve(shuffled, rng.sample(aa, len(aa))), expected)

    def test_override_validation(self):
        self.assertEqual(identity.validate_overrides(ALIASES), [])
        bad = {"joins": [{"routes": [{"provider": "openrouter", "id": "a/b"}], "evidence_urls": ["nope"],
                          "checked_at": "27/09/2026"}]}
        problems = identity.validate_overrides(bad)
        self.assertEqual(len(problems), 4)

    def test_enrich_reports_registry_slugs_that_match_no_model(self):
        models = [{"slug": "present", "score": None, "variant": "", "providers": []}]
        registry = {"snapshot_benchmarks": {"2026-09-27": "4.3.2"},
                    "scores": [{"target_slug": "gone", "variant": "", "benchmark": "aa-intelligence-index",
                                "version": "4.3.2", "value": 1, "source": "t", "url": "https://example.invalid/x",
                                "checked_at": "2026-09-27", "expires_at": "2026-09-27"}],
                    "inheritance": []}
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(enrich(models, registry, "2026-09-27"), ["gone"])
        self.assertIn("match no model", out.getvalue())


if __name__ == "__main__":
    unittest.main()
