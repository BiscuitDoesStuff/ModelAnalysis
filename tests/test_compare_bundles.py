"""tools/compare_bundles.py reports identity splits for new and pre-identity bundles."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tests" / "fixtures")]
import compare_bundles  # noqa: E402
import make_golden  # noqa: E402
import pipeline  # noqa: E402
from pipeline_common import atomic_json  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"


class CompareBundlesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def publish(self, name, snap):
        atomic_json(self.root / f"{name}.json", snap)
        with contextlib.redirect_stdout(io.StringIO()):
            return pipeline.run(state_dir=self.root / name, db_path=self.root / f"{name}.sqlite",
                                snapshot_path=self.root / f"{name}.json",
                                registry_path=FIXTURES / "golden_research.json", as_of=make_golden.AS_OF)

    def strip_routes(self, bundle):
        """Make a bundle look pre-identity: tail slugs, no per-model routes (old ownership rule)."""
        run_id = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))["run_id"]
        path = bundle / "analysis" / f"{run_id}_analysis.json"
        a = json.loads(path.read_text(encoding="utf-8"))
        for m in a["models"]:
            m.pop("routes", None)
            m["slug"] = m["slug"].split(".")[0]
        path.write_text(json.dumps(a), encoding="utf-8")

    def test_split_of_a_pre_identity_merge(self):
        # Step 5 situation: the same snapshot, where the old rule merged a tail across vendors.
        snap = make_golden.snapshot()
        snap["openrouter"].append(make_golden.or_row("orbit/gpt-6", "Orbit: GPT-6", "0.000001", "0.000001"))
        old = self.publish("old", snap)
        self.strip_routes(old)
        self.publish("new", snap)
        result = compare_bundles.compare(old, self.root / "new")  # a state folder resolves via current.json
        # nova-1 is the golden fixture's own two-vendor collision (plus its ambiguous Zen route).
        self.assertEqual(result["splits"], {"gpt6": ["gpt6.openai", "gpt6.orbit"],
                                            "nova1": ["nova1.acme", "nova1.orbit", "nova1.zen"]})
        self.assertIn("gpt6 -> gpt6.openai, gpt6.orbit", compare_bundles.format_report(result))

    def test_new_vendor_route_renames_and_adds(self):
        old = self.publish("old", make_golden.snapshot())
        snap = make_golden.snapshot()
        snap["openrouter"].append(make_golden.or_row("orbit/gpt-6", "Orbit: GPT-6", "0.000001", "0.000001"))
        new = self.publish("new", snap)
        result = compare_bundles.compare(old, new)
        self.assertEqual((result["splits"], result["renamed"]), ({}, {"gpt6": "gpt6.openai"}))
        self.assertEqual(result["added"], ["gpt6.orbit"])
        self.assertFalse(result["score_changes"])  # the score follows the renamed entity

    def test_identical_runs_report_nothing(self):
        old = self.publish("old", make_golden.snapshot())
        new = self.publish("new", make_golden.snapshot())
        result = compare_bundles.compare(old, new)
        for key in ("splits", "merges", "renamed", "added", "removed", "rank_changes", "score_changes"):
            self.assertFalse(result[key], key)


if __name__ == "__main__":
    unittest.main()
