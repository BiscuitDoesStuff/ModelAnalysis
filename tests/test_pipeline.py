"""End-to-end offline pipeline and crash-recovery tests."""
import contextlib
import datetime as dt
import io
import json
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import pipeline
from pipeline_common import atomic_json, load_config, source_status, SOURCES, PROVIDERS


def snapshot(free=True):
    rows = [{"id": "fixture/model", "name": "Fixture model",
             "pricing": {"prompt": "0" if free else "0.000001", "completion": "0"},
             "architecture": {"output_modalities": ["text"]}}]
    data = {s: [] for s in PROVIDERS}
    data.update(retrieved_at="fixture", run_id="fixture", openrouter=rows,
                aa={"data": []}, modelsdev=[], benchlm={"leaderboard": [], "pricing": [], "meta": {}},
                llmstats={"skipped": "fixture"}, vals={"models": []})
    data["source_health"] = {s: source_status("complete", len(data[s]), scope="catalog") for s in PROVIDERS}
    for s in set(SOURCES) - set(PROVIDERS):
        data["source_health"][s] = source_status("skipped", scope="reference", reason="fixture")
    return data


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = self.root / "state"
        self.db = self.root / "history.sqlite"
        self.input = self.root / "snapshot.json"
        atomic_json(self.input, snapshot())
        # Any accidental network call fails the test, including website enrichment.
        self.network = patch("urllib.request.urlopen", side_effect=AssertionError("offline test attempted network"))
        self.network.start()
        self.addCleanup(self.network.stop)

    def run_pipeline(self, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()):
            return pipeline.run(state_dir=self.state, db_path=self.db, snapshot_path=self.input, **kwargs)

    def current(self):
        return json.loads((self.state / "current.json").read_text(encoding="utf-8"))

    def test_end_to_end_loss_alert_and_retention(self):
        first = self.run_pipeline()
        first_id = self.current()["run_id"]
        atomic_json(self.input, snapshot(False))
        second = self.run_pipeline()
        second_id = self.current()["run_id"]
        report = json.loads((second / "reports" / f"{second_id}_models.json").read_text(encoding="utf-8"))
        self.assertEqual(len(report["churn"]["alert_events"]), 1)
        self.assertEqual(report["churn"]["alert_events"][0]["type"], "verified_free_paid")
        self.assertTrue((second / "reports" / f"{second_id}_churn_alert.md").exists())
        self.assertFalse(list((second / "reports").glob("*_triage_alert.md")))
        third = self.run_pipeline()
        third_id = self.current()["run_id"]
        self.assertFalse(first.exists())
        self.assertTrue(second.exists())
        self.assertFalse((third / "reports" / f"{third_id}_churn_alert.md").exists())
        with closing(sqlite3.connect(self.db)) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM history_runs WHERE state='published'").fetchone()[0], 3)
        self.assertNotEqual(first_id, second_id)

    def test_stage_failures_preserve_current_and_baselines(self):
        old = self.run_pipeline()
        old_pointer = self.current()
        for stage in ("fetch", "websites", "analyze", "report", "site", "alerts", "validate", "before_finalize"):
            with self.subTest(stage=stage):
                def fail(point):
                    if point == stage:
                        raise RuntimeError("injected failure")
                with self.assertRaisesRegex(RuntimeError, "injected"):
                    self.run_pipeline(failpoint=fail)
                self.assertEqual(self.current(), old_pointer)
                self.assertTrue(old.exists())
        with closing(sqlite3.connect(self.db)) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM history_runs WHERE state='published'").fetchone()[0], 1)

    def test_publication_recovers_after_each_commit_boundary(self):
        self.run_pipeline()
        for stage in ("after_finalize", "after_pointer", "after_history"):
            with self.subTest(stage=stage):
                def fail(point):
                    if point == stage:
                        raise RuntimeError("publication interrupted")
                with self.assertRaisesRegex(RuntimeError, "interrupted"):
                    self.run_pipeline(failpoint=fail)
                pipeline.recover_publication(self.state, self.db)
                current = self.current()
                bundle = self.state / current["bundle"]
                manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
                self.assertEqual(manifest["state"], "published")
                pipeline.validate_bundle(bundle, current["run_id"])
                with closing(sqlite3.connect(self.db)) as con:
                    state = con.execute("SELECT state FROM history_runs WHERE run_id=?", (current["run_id"],)).fetchone()[0]
                    self.assertEqual(state, "published")
                previous = self.current()
                pipeline.recover_publication(self.state, self.db)
                self.assertEqual(self.current(), previous)

    def test_cleanup_failure_does_not_undo_publication(self):
        def fail(point):
            if point == "cleanup":
                raise OSError("fixture cleanup failure")
        bundle = self.run_pipeline(failpoint=fail)
        self.assertTrue(bundle.exists())
        self.assertEqual(self.current()["run_id"], bundle.name)

    def test_interrupted_and_killed_staging_is_pruned(self):
        def interrupt(point):
            if point == "report":
                raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            self.run_pipeline(failpoint=interrupt)
        (ctrl_c,) = (self.state / "staging").glob("*/manifest.json")
        self.assertEqual(json.loads(ctrl_c.read_text(encoding="utf-8"))["state"], "failed")
        # A hard kill never reaches the failure handler and leaves `pending`.
        killed, recent = self.state / "staging" / "killed", self.state / "staging" / "recent"
        atomic_json(killed / "manifest.json", {"state": "pending", "started_at": "2020-01-01T00:00:00+00:00"})
        atomic_json(recent / "manifest.json", {"state": "pending", "started_at": dt.datetime.now(dt.timezone.utc).isoformat()})
        manifest = json.loads(ctrl_c.read_text(encoding="utf-8"))
        atomic_json(ctrl_c, dict(manifest, started_at="2020-01-01T00:00:00+00:00"))
        self.run_pipeline()
        self.assertFalse(ctrl_c.parent.exists())
        self.assertFalse(killed.exists())
        self.assertTrue(recent.exists())

    def test_no_usable_catalog_and_mixed_websites_do_not_publish(self):
        self.run_pipeline()
        old = self.current()
        web = self.root / "websites.json"
        atomic_json(web, {"run_id": "different-fixture"})
        with self.assertRaisesRegex(ValueError, "Mixed-run"):
            self.run_pipeline(websites_path=web)
        data = snapshot()
        data["openrouter"] = []
        atomic_json(self.input, data)
        with self.assertRaisesRegex(ValueError, "No usable"):
            self.run_pipeline()
        self.assertEqual(self.current(), old)

    def test_legacy_import_cannot_establish_complete_baseline(self):
        data = snapshot()
        data.pop("source_health")
        atomic_json(self.input, data)
        bundle = self.run_pipeline()
        report = json.loads((bundle / "reports" / f"{bundle.name}_models.json").read_text(encoding="utf-8"))
        self.assertEqual(report["churn"]["coverage"]["complete_sources"], [])
        self.assertEqual(report["source_health"]["openrouter"]["status"], "partial")

    def test_writer_lock_is_exclusive(self):
        with pipeline.writer_lock(self.state):
            with self.assertRaisesRegex(RuntimeError, "Another pipeline"):
                with pipeline.writer_lock(self.state):
                    pass


if __name__ == "__main__":
    unittest.main()
