"""Phase 4: research.json validation, AA version ranges, expiry boundaries, refresh tool."""
import contextlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from analysis.enrichment import enrich  # noqa: E402
from analysis.registry import aa_version, evidence_status, validate  # noqa: E402
import refresh_evidence  # noqa: E402

URL = "https://example.invalid/evidence"


def registry(ranges=(("4.3.2", "2026-09-01", None),), checked="2026-09-10", expires="2026-09-20",
             variant="xhigh", version="4.3.2"):
    return {"aa_index_versions": [{"version": v, "valid_from": start, "valid_to": end, "source_url": URL,
                                   "checked_at": start} for v, start, end in ranges],
            "scores": [{"target_slug": "plain", "variant": "", "benchmark": "aa-intelligence-index",
                        "version": version, "value": 39, "source": "t", "url": URL,
                        "checked_at": checked, "expires_at": expires}],
            "inheritance": [{"target_slug": "tgt", "source_slug": "src", "variant": variant, "version": version,
                             "provider": "zen", "route_id": "tgt-free", "selector": "opencode/tgt-free#xhigh",
                             "supported_efforts": ["high", "xhigh"], "cost_blended": 0,
                             "checked_at": checked, "expires_at": expires, "equivalence_urls": [URL],
                             "capability_url": URL, "rationale": "test"}]}


def models(source_score=45.0, source_variant="xhigh"):
    return [{"slug": "src", "id": "src", "score": source_score, "variant": source_variant, "providers": ["openrouter"]},
            {"slug": "tgt", "id": "tgt", "score": None, "variant": "", "providers": ["zen"]},
            {"slug": "plain", "id": "plain", "score": None, "variant": "", "providers": ["nvidia"]}]


def applied(reg, day, rows=None):
    """(inherited estimate applied, registry score applied) on this day."""
    rows = rows or models()
    with contextlib.redirect_stdout(io.StringIO()):
        enrich(rows, reg, day)
    inherited = any((m.get("score_source") or {}).get("kind") == "inherited-estimate" for m in rows)
    plain = next(m for m in rows if m["slug"] == "plain")
    return inherited, plain.get("score") == 39


class RegistryTests(unittest.TestCase):
    def test_boundaries(self):
        reg = registry()
        self.assertEqual(applied(reg, "2026-09-09"), (False, False))  # before checked_at
        self.assertEqual(applied(reg, "2026-09-10"), (True, True))    # checked_at == day
        self.assertEqual(applied(reg, "2026-09-20"), (True, True))    # expires_at == day
        self.assertEqual(applied(reg, "2026-09-21"), (False, False))  # the day after expiry

    def test_version_change_mid_range_retires_old_version_evidence(self):
        reg = registry(ranges=(("4.3.2", "2026-09-01", "2026-09-14"), ("4.4", "2026-09-15", None)))
        self.assertEqual(aa_version(reg, "2026-09-14")[0], "4.3.2")
        self.assertEqual(aa_version(reg, "2026-09-15")[0], "4.4")
        self.assertEqual(applied(reg, "2026-09-14"), (True, True))
        self.assertEqual(applied(reg, "2026-09-15"), (False, False))

    def test_effort_mismatch_and_lost_source_score(self):
        self.assertEqual(applied(registry(), "2026-09-12", models(source_variant="max"))[0], False)
        self.assertEqual(applied(registry(), "2026-09-12", models(source_score=None))[0], False)

    def test_validation_catches_bad_entries(self):
        self.assertEqual(validate(registry()), ([], []))
        bad = registry(checked="2026-09-30", expires="2026-09-20", variant="max")
        bad["scores"][0].update(benchmark="made-up", url="not a url")
        bad["aa_index_versions"].append({"version": "x", "valid_from": "2026-09-05", "valid_to": None,
                                         "source_url": URL, "checked_at": "2026-09-05"})
        errors, _ = validate(bad)
        text = " | ".join(errors)
        for expected in ("checked_at is after expires_at", "not in scales.BENCHMARKS", "url must be",
                         "not in supported_efforts", "overlap"):
            self.assertIn(expected, text)
        with self.assertRaisesRegex(ValueError, "research.json invalid"):
            enrich(models(), bad, "2026-09-12")
        self.assertIn("musespark13", " ".join(validate(json.loads(
            (ROOT / "analysis" / "research.json").read_text(encoding="utf-8")), model_slugs=set())[1]))

    def test_expiry_status_and_legacy_pins(self):
        st = evidence_status(registry(), "2026-09-18")
        self.assertEqual((st["days_left"], [i["key"] for i in st["expiring"]]), (2, ["scores:plain:aa-intelligence-index", "inheritance:tgt"]))
        self.assertEqual(evidence_status(registry(), "2026-09-21")["expired"], ["inheritance:tgt", "scores:plain:aa-intelligence-index"])
        legacy = registry()
        legacy["snapshot_benchmarks"] = {"2026-09-12": "4.3.2"}
        del legacy["aa_index_versions"]
        self.assertEqual(aa_version(legacy, "2026-09-12")[0], "4.3.2")
        self.assertIn("legacy", validate(legacy)[1][0])


class RefreshToolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.reg, self.notes = root / "research.json", root / "run-notes.md"
        shutil.copyfile(ROOT / "analysis" / "research.json", self.reg)
        self.notes.write_text("# Run notes\n\n- older line\n", encoding="utf-8")

    def run_tool(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            refresh_evidence.main(["--registry", str(self.reg), "--notes", str(self.notes), *args])
        return out.getvalue()

    def load(self):
        return json.loads(self.reg.read_text(encoding="utf-8"))

    def test_layout_round_trips(self):
        text = (ROOT / "analysis" / "research.json").read_text(encoding="utf-8")
        self.assertEqual(refresh_evidence.dumps(json.loads(text)), text)

    def test_list_confirm_retire_and_version_change(self):
        self.assertIn("scores:musespark13:llm-stats-overall", self.run_tool("list", "--today", "2026-10-02"))
        self.run_tool("confirm", "scores:musespark13:llm-stats-overall", "--checked", "2026-10-02",
                      "--value", "54.1", "--note", "LLM Stats re-read.")
        score = self.load()["scores"][0]
        self.assertEqual((score["checked_at"], score["expires_at"], score["value"]), ("2026-10-02", "2026-10-09", 54.1))
        self.assertIn("- 2026-10-02 (evidence): confirmed `scores:musespark13:llm-stats-overall` (checked 2026-10-02, "
                      "expires 2026-10-09, value 53.8 -> 54.1). LLM Stats re-read.", self.notes.read_text(encoding="utf-8"))
        self.run_tool("retire", "inheritance:musespark12contributorfree", "--note", "Route left the catalog.")
        self.assertEqual([r["target_slug"] for r in self.load()["inheritance"]], ["musespark13contributorfree"])
        out = self.run_tool("version-new", "4.4", "--from", "2026-10-05", "--url", "https://example.invalid/aa")
        ranges = self.load()["aa_index_versions"]
        self.assertEqual([(r["version"], r["valid_to"]) for r in ranges], [("4.3.2", "2026-10-04"), ("4.4", None)])
        self.assertIn("inheritance:musespark13contributorfree", out)
        self.run_tool("version-confirm", "--checked", "2026-10-06")
        self.assertEqual(self.load()["aa_index_versions"][1]["checked_at"], "2026-10-06")
        self.assertEqual(validate(self.load())[0], [])

    def test_refuses_invalid_input(self):
        before = self.reg.read_text(encoding="utf-8")
        with self.assertRaises(SystemExit):
            self.run_tool("confirm", "scores:nope:x", "--checked", "2026-10-02")
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            self.run_tool("confirm", "scores:musespark13:llm-stats-overall", "--checked", "02/10/2026")
        with self.assertRaises(SystemExit):
            self.run_tool("confirm", "scores:musespark13:llm-stats-overall", "--checked", "2026-10-09",
                          "--expires", "2026-10-01")
        self.assertEqual(self.reg.read_text(encoding="utf-8"), before)


if __name__ == "__main__":
    unittest.main()
