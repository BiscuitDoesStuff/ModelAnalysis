"""Phase 3 provenance: observation contract, scale guard, and the audit tool."""
import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tests" / "fixtures")]
import audit_provenance  # noqa: E402
import make_golden  # noqa: E402
import pipeline  # noqa: E402
from analysis import scales  # noqa: E402
from reports.build_report import build_sections  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"


class ProvenanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        root = Path(cls.temp.name)
        with contextlib.redirect_stdout(io.StringIO()):
            cls.bundle = pipeline.run(state_dir=root / "runs", db_path=root / "h.sqlite",
                                      snapshot_path=FIXTURES / "golden_snapshot.json",
                                      websites_path=FIXTURES / "golden_websites.json",
                                      registry_path=FIXTURES / "golden_research.json", as_of=make_golden.AS_OF)
        cls.run_id = json.loads((cls.bundle / "manifest.json").read_text(encoding="utf-8"))["run_id"]
        cls.analysis_path = cls.bundle / "analysis" / f"{cls.run_id}_analysis.json"
        cls.a = json.loads(cls.analysis_path.read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_every_observation_meets_the_contract(self):
        obs = self.a["observations"]
        self.assertEqual(len(obs), self.a["observations_count"])
        self.assertEqual([(o["obs_id"], p) for o in obs for p in scales.problems(o)], [])
        self.assertEqual(len({o["obs_id"] for o in obs}), len(obs))
        health = self.a["source_health"]
        aa = [o for o in obs if o["source"] == "aa" and o["field"] == "score"]
        self.assertTrue(aa and all(o["observed_at"] == health["aa"]["fetched_at"] for o in aa))
        registry = [o for o in obs if o["source"] == "registry"]
        self.assertTrue(registry and all(o["expires_at"] for o in registry))
        prices = {o["source"] for o in obs if o["field"] == "price_blended"}
        self.assertTrue(prices <= {"aa", "openrouter", "registry"} and "or-derived" not in prices)

    def test_displayed_scores_are_aa_index_and_traceable(self):
        by_id = {o["obs_id"]: o for o in self.a["observations"]}
        for m in self.a["models"]:
            if m.get("score") is not None:
                o = by_id[m["provenance"]["score"]["obs_id"]]
                self.assertEqual((o["unit"], o["value"]), (scales.RANKING_UNIT, m["score"]))

    def test_ranks_and_ratios_ignore_other_scales(self):
        """Scale guard: rewriting every non-AA scale leaves rankings, ratios and picks unchanged."""
        base = build_sections(copy.deepcopy(self.a))
        noisy = copy.deepcopy(self.a)
        for m in noisy["models"]:
            if m.get("benchlm"):
                m["benchlm"]["overall"] = 1000
                m["benchlm"]["categories"] = {k: -5 for k in m["benchlm"].get("categories", {})}
            for rank in (m.get("llmstats_rank") or {}).values():
                rank.update(rating=999, rank=1)
            if m.get("llmstats_api"):
                m["llmstats_api"]["top_scores"] = {"general": 5000}
            m["website"] = {"llmstats": {"llmstats_score_hint": 99}, "vals": {"accuracy_hints": ["1.0"]}}
        noisy_sections = build_sections(noisy)
        slugs = lambda rows: [(r["slug"], r.get("ratio"), r.get("tier")) for r in rows]  # noqa: E731
        for key in ("all_intel", "paid_ratio", "ocf_intel", "ocf_ratio", "costed"):
            self.assertEqual(slugs(noisy_sections[key]), slugs(base[key]), key)
        for tier in ("max", "high", "medium"):
            self.assertEqual(slugs(noisy_sections["stack"][tier]["rows"]), slugs(base["stack"][tier]["rows"]))

    def test_audit_passes_then_catches_orphans_and_mismatches(self):
        clean = audit_provenance.audit(self.bundle, 0)
        self.assertGreater(clean["checked"], 100)
        self.assertEqual(set(clean["per_format"]), {"dashboard", "site", "xlsx", "json"})
        for key in ("orphans", "mismatches", "wrong_scale", "missing_version", "missing_url", "stale"):
            self.assertEqual(clean[key], [], key)
        html = self.bundle / "reports" / f"{self.run_id}_report.html"
        original = html.read_text(encoding="utf-8")
        try:
            first = audit_provenance.CELL.search(original)
            oid = first.group(2)
            tampered = original.replace(f"data-obs='{oid}'", "data-obs='0000000000000000'", 1)
            html.write_text(tampered, encoding="utf-8")
            self.assertTrue(audit_provenance.audit(self.bundle, 0)["orphans"])
            tampered = original.replace(f" data-obs='{oid}'", "", 1)  # a shown value with no source
            html.write_text(tampered, encoding="utf-8")
            self.assertTrue(audit_provenance.audit(self.bundle, 0)["orphans"])
            cell = first.group(0)
            wrong = cell.replace(">" + first.group(3) + "<", ">123456<", 1)
            html.write_text(original.replace(cell, wrong, 1), encoding="utf-8")
            self.assertTrue(audit_provenance.audit(self.bundle, 0)["mismatches"])
        finally:
            html.write_text(original, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
