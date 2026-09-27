"""tools/record_fixture.py: trims a real-shaped bundle, scrubs keys, verifies before writing."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests" / "fixtures"))
import make_golden  # noqa: E402
import pipeline  # noqa: E402
from pipeline_common import atomic_json  # noqa: E402
import record_fixture  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
SECRET = "SECRETVALUE-abcdef123456"


def padded_snapshot():
    """The synthetic fixture plus unscored filler, like a real catalog's long tail."""
    snap = make_golden.snapshot()
    snap.pop("fixture")
    snap["openrouter"] += [make_golden.or_row(f"filler/model-{i}", f"Filler {i}", "0.000001", "0.000002")
                           for i in range(40)]
    snap["modelsdev"] += [make_golden.md_row("filler", f"model-{i}", 1, 2) for i in range(40)]
    snap["aa"]["data"] += [make_golden.aa_row(f"filler-model-{i}", f"Filler {i}", "Filler", None, None)
                           for i in range(20)]
    # A credential that leaked into a kept row must be redacted, not copied.
    snap["openrouter"][0]["name"] += " " + SECRET
    snap["openrouter"][0]["description"] = "Long catalog text no stage reads."
    return snap


class RecordFixtureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.out = self.root / "out"

    def bundle(self, snap, web=None):
        atomic_json(self.root / "snap.json", snap)
        atomic_json(self.root / "web.json", web or make_golden.websites())
        with contextlib.redirect_stdout(io.StringIO()):
            return pipeline.run(state_dir=self.root / "runs", db_path=self.root / "h.sqlite",
                                snapshot_path=self.root / "snap.json", websites_path=self.root / "web.json",
                                registry_path=FIXTURES / "golden_research.json", as_of=make_golden.AS_OF)

    def record(self, bundle):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = record_fixture.record(bundle, self.out, registry_path=FIXTURES / "golden_research.json",
                                         secrets=[SECRET])
        return code, buf.getvalue()

    def test_records_trimmed_scrubbed_verified_fixture(self):
        code, log = self.record(self.bundle(padded_snapshot()))
        self.assertEqual(code, 0, log)
        self.assertIn("secret scan: clean", log)
        snap = json.loads((self.out / "recorded_snapshot.json").read_text(encoding="utf-8"))
        self.assertEqual(snap["fixture"]["as_of"], make_golden.AS_OF)
        self.assertFalse([m for m in snap["openrouter"] if m["id"].startswith("filler/")])
        self.assertFalse([m for m in snap["modelsdev"] if m["provider"] == "filler"])
        self.assertIn("openai/gpt-6", {m["id"] for m in snap["openrouter"]})
        self.assertFalse([m for m in snap["openrouter"] if "description" in m])
        self.assertEqual(snap["llmstats"]["model_count"], len(snap["llmstats"]["models"]))
        for name in ("recorded_snapshot.json", "recorded_websites.json", "recorded_research.json"):
            self.assertNotIn(SECRET, (self.out / name).read_text(encoding="utf-8"))

    def test_key_like_string_blocks_writing(self):
        web = make_golden.websites()
        web["benchlm_md"]["gpt6"]["md"] += "\nAuthorization: Bearer abcdefghijklmnopqrstuvwxyz012345\n"
        code, log = self.record(self.bundle(padded_snapshot(), web))
        self.assertEqual(code, 1)
        self.assertIn("recorded_websites.json: $.benchlm_md.gpt6.md", log)
        self.assertNotIn("abcdefghijklmnop", log)
        self.assertFalse(self.out.exists())

    def test_partial_bundle_is_refused(self):
        snap = padded_snapshot()
        snap["source_health"]["llmstats"]["status"] = "failed"
        code, log = self.record(self.bundle(snap))
        self.assertEqual(code, 1)
        self.assertIn("llmstats=failed", log)
        self.assertFalse(self.out.exists())


if __name__ == "__main__":
    unittest.main()
