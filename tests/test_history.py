"""Synthetic, network-free history/alert reliability tests: python tests/test_history.py."""
from contextlib import closing
import datetime as dt
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analysis.churn import PROVIDERS, RULE_VERSION, route_evidence
from analysis.history import prepare_run, publish_run, prune_history
from alerts.check_churn import main as alert_main


def route(mid="maker/model", price="0", **extra):
    return dict({"id": mid, "pricing": {"prompt": price, "completion": price},
                 "architecture": {"output_modalities": ["text"]}}, **extra)


def snapshot(rows=None, **providers):
    return dict({p: [] for p in PROVIDERS}, openrouter=rows or [], **providers)


def health(status="complete", **overrides):
    value = {p: {"status": "complete", "complete": True, "scope": "catalog",
                 "fetched_at": "2026-01-01T00:00:00Z"} for p in PROVIDERS}
    value["openrouter"].update(status=status, complete=status == "complete", **overrides)
    return value


class HistoryTests(unittest.TestCase):
    def setUp(self):
        temp_root = Path(tempfile.gettempdir()) / "opencode"
        self.temp = tempfile.TemporaryDirectory(dir=temp_root if temp_root.is_dir() else None)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / "history.sqlite"

    def run_snapshot(self, rid, stamp, snap=None, source_health=None, publish=True, models=None):
        result = prepare_run(self.db, snap if snap is not None else snapshot(), models or [], rid,
                             stamp, source_health if source_health is not None else health())
        if publish:
            publish_run(self.db, rid)
        return result

    def rows(self, query, args=()):
        with closing(sqlite3.connect(self.db)) as con:
            return con.execute(query, args).fetchall()

    def rollup(self, day, source="openrouter"):
        return json.loads(self.rows("SELECT rollup_json FROM history_daily WHERE day=? AND source=?",
                                    (day, source))[0][0])

    def test_first_run_and_unpublished_runs_are_not_baselines(self):
        first = self.run_snapshot("abandoned", "2026-01-01T10:00:00Z", snapshot([route()]), publish=False)
        self.assertEqual(first["events"], [])
        second = self.run_snapshot("new", "2026-01-01T11:00:00Z", snapshot())
        self.assertEqual(second["events"], [])
        self.assertIsNone(second["source_health"]["openrouter"]["baseline"])
        self.assertEqual(self.rollup("2026-01-01")["latest_complete"]["run_id"], "new")

    def test_same_day_removal_and_restoration_preserve_observed_not_net(self):
        self.run_snapshot("yesterday", "2026-01-01T10:00:00Z", snapshot([route()]))
        loss = self.run_snapshot("lost", "2026-01-02T10:00:00Z")
        self.assertEqual(loss["counts"]["verified_free_removed"], 1)
        restored = self.run_snapshot("restored", "2026-01-02T11:00:00Z", snapshot([route()]))
        self.assertEqual(restored["counts"]["free_restored"], 1)
        self.assertEqual(restored["source_health"]["openrouter"]["baseline"]["run_id"], "lost")
        daily = self.rollup("2026-01-02")
        self.assertEqual(daily["net_events"], [])
        self.assertEqual(daily["latest_complete"]["run_id"], "restored")
        observed = [e["type"] for e in daily["observed_events"]]
        self.assertIn("verified_free_removed", observed)
        self.assertIn("free_restored", observed)

    def test_failures_partial_pagination_and_scoped_fetches_do_not_advance_baseline(self):
        self.run_snapshot("good", "2026-01-01T10:00:00Z", snapshot([route()]))
        cases = [health("failed"), health("partial"), health("skipped"), health(scope="probe")]
        # A collector accidentally retaining complete=True still cannot bless a partial page.
        cases[1]["openrouter"].update(complete=True, pages_fetched=1, next_page="next")
        for index, source_health in enumerate(cases):
            result = self.run_snapshot(f"bad-{index}", f"2026-01-02T1{index}:00:00Z",
                                       source_health=source_health)
            self.assertEqual(result["events"], [])
            self.assertFalse(result["source_health"]["openrouter"]["compared"])
            self.assertEqual(result["source_health"]["openrouter"]["baseline"]["run_id"], "good")
        result = self.run_snapshot("recovered", "2026-01-03T10:00:00Z", snapshot([route(price="1")]))
        self.assertEqual(result["counts"]["verified_free_paid"], 1)
        self.assertEqual(result["source_health"]["openrouter"]["baseline"]["run_id"], "good")
        failed_day = self.rollup("2026-01-02")
        self.assertIsNone(failed_day["latest_complete"])
        self.assertEqual(failed_day["net_events"], [])
        self.assertEqual(len(failed_day["coverage"]), 4)

    def test_empty_complete_catalog_is_a_real_baseline(self):
        self.run_snapshot("empty", "2026-01-01", snapshot())
        result = self.run_snapshot("new", "2026-01-02", snapshot([route()]))
        self.assertEqual(result["counts"]["catalog_added"], 1)
        self.assertEqual(result["counts"]["free_added"], 1)

    def test_malformed_catalog_cannot_confirm_removal(self):
        self.run_snapshot("good", "2026-01-01", snapshot([route()]))
        for i, payload in enumerate(({"error": "failed"}, [{"name": "missing-id"}], [route(), route()])):
            snap = snapshot()
            snap["openrouter"] = payload
            result = self.run_snapshot(f"malformed-{i}", f"2026-01-0{i + 2}", snap)
            self.assertFalse(result["source_health"]["openrouter"]["complete"])
            self.assertEqual(result["alert_events"], [])

    def test_unknown_pricing_and_modality_are_not_paid(self):
        self.run_snapshot("good", "2026-01-01", snapshot([route()]))
        for i, value in enumerate((route(pricing={}), route(architecture={}),
                                   route(price="NaN"), route(price="-1"), route(price=None),
                                   route(architecture={"output_modalities": ["image"]}))):
            result = self.run_snapshot(f"unknown-{i}", "2026-01-02", snapshot([value]), publish=False)
            self.assertEqual(result["counts"]["verification_unknown"], 1)
            self.assertEqual(result["counts"]["verified_free_paid"], 0)
            self.assertEqual(result["alert_events"], [])

    def test_strict_openrouter_and_zen_rules(self):
        self.assertEqual(route_evidence("openrouter", route("maker/m:free", pricing={}))[0], "verified_free")
        self.assertEqual(route_evidence("openrouter", route("maker/m:free", architecture={}))[0], "unknown")
        self.assertEqual(route_evidence("openrouter", route("openrouter/free:free"))[0], "ineligible")
        self.assertEqual(route_evidence("openrouter", route(price=True))[0], "unknown")
        self.assertEqual(route_evidence("zen", {"id": "model-free"})[0], "verified_free")
        self.assertEqual(route_evidence("nvidia", route())[0], "unknown")

    def test_unknown_then_paid_carries_traceable_evidence_and_alerts_once(self):
        self.run_snapshot("free", "2026-01-01", snapshot([route()]),
                          health(fetched_at="2026-01-01T00:10:00Z"))
        unknown = self.run_snapshot("unknown", "2026-01-02", snapshot([route(pricing={})]),
                                    health(fetched_at="2026-01-02T00:10:00Z"))
        self.assertEqual(unknown["counts"]["verification_unknown"], 1)
        unknown_route = json.loads(self.rows("SELECT route_json FROM history_routes WHERE run_id='unknown'")[0][0])
        self.assertFalse(unknown_route["verified_free"])
        self.assertEqual(unknown_route["state"], "unknown")
        self.assertEqual(unknown_route["last_decisive"]["observed_run_id"], "free")
        self.assertEqual(unknown_route["last_decisive"]["state"], "verified_free")
        repeat = self.run_snapshot("unknown-again", "2026-01-03", snapshot([route(architecture={})]))
        self.assertEqual(repeat["counts"]["verification_unknown"], 0)
        paid = self.run_snapshot("paid", "2026-01-04", snapshot([route(price="1")]),
                                 health(fetched_at="2026-01-04T00:10:00Z"))
        self.assertEqual(paid["counts"]["verified_free_paid"], 1)
        loss = paid["alert_events"][0]
        self.assertEqual(loss["before"]["observed_run_id"], "free")
        self.assertEqual(loss["before"]["evidence"], ["or:strict-free"])
        self.assertEqual(loss["baseline_before"]["state"], "unknown")
        self.assertEqual(loss["baseline_run_id"], "unknown-again")
        self.assertEqual(loss["before_observed_at"], "2026-01-01T00:10:00Z")
        self.assertEqual(loss["current_observed_at"], "2026-01-04T00:10:00Z")
        repeated = self.run_snapshot("still-paid", "2026-01-05", snapshot([route(price="1")]))
        self.assertEqual(repeated["alert_events"], [])
        self.run_snapshot("paid-unknown", "2026-01-06", snapshot([route(pricing={})]))
        self.assertEqual(self.run_snapshot("paid-again", "2026-01-07", snapshot([route(price="1")]))["alert_events"], [])

    def test_unknown_then_removed_confirms_once_after_evidence_run_pruned(self):
        self.run_snapshot("free", "2025-01-01", snapshot([route()]))
        self.run_snapshot("unknown", "2025-02-01", snapshot([route(pricing={})]))
        prune_history(self.db, "2026-01-01")
        self.assertNotIn(("free",), self.rows("SELECT run_id FROM history_runs"))
        removed = self.run_snapshot("removed", "2026-01-02")
        self.assertEqual(removed["counts"]["verified_free_removed"], 1)
        self.assertEqual(removed["alert_events"][0]["before_run_id"], "free")
        self.assertEqual(self.run_snapshot("still-removed", "2026-01-03")["alert_events"], [])
        # Reappearance without evidence must not revive a resolved historical loss.
        self.run_snapshot("unknown-return", "2026-01-04", snapshot([route(pricing={})]))
        self.assertEqual(self.run_snapshot("paid-return", "2026-01-05", snapshot([route(price="1")]))["alert_events"], [])

    def test_unknown_recovery_free_is_not_a_restoration(self):
        self.run_snapshot("free", "2026-01-01", snapshot([route()]))
        self.run_snapshot("unknown", "2026-01-02", snapshot([route(pricing={})]))
        recovered = self.run_snapshot("reverified", "2026-01-03", snapshot([route()]))
        self.assertEqual(recovered["counts"]["free_restored"], 0)
        self.assertEqual(recovered["counts"]["free_added"], 0)
        self.assertEqual(recovered["alert_events"], [])
        self.assertNotIn("free_restored", [e["type"] for e in self.rollup("2026-01-03")["net_events"]])
        self.run_snapshot("paid", "2026-01-04", snapshot([route(price="1")]))
        self.run_snapshot("unknown-after-paid", "2026-01-05", snapshot([route(pricing={})]))
        restored = self.run_snapshot("restored", "2026-01-06", snapshot([route()]))
        self.assertEqual(restored["counts"]["free_restored"], 1)

    def test_carried_evidence_never_counts_as_current_alternative(self):
        self.run_snapshot("free", "2026-01-01", snapshot([route(), route("maker/model:tag")]))
        result = self.run_snapshot("loss", "2026-01-02", snapshot([route("maker/model:tag", pricing={})]))
        loss = result["alert_events"][0]
        self.assertEqual(loss["alternatives"], [])
        self.assertTrue(loss["unknown_coverage"])
        self.assertEqual(loss["access_status"], "unknown")
        self.assertFalse(loss["unknown_routes"][0]["verified_free"])

    def test_string_ids_are_exact_metadata_poor_catalog_entries(self):
        self.run_snapshot("free", "2026-01-01", snapshot([route()]))
        result = self.run_snapshot("strings", "2026-01-02", snapshot(["maker/model"], zen=["model-free"]))
        self.assertTrue(result["source_health"]["openrouter"]["complete"])
        self.assertEqual(result["counts"]["verification_unknown"], 1)
        self.assertEqual(result["alert_events"], [])
        stored = json.loads(self.rows("SELECT route_json FROM history_routes WHERE run_id='strings' AND source='zen'")[0][0])
        self.assertTrue(stored["verified_free"])
        self.assertEqual(stored["id"], "model-free")
        lost = self.run_snapshot("lost", "2026-01-03", snapshot(zen=["model-free"]))
        self.assertEqual(lost["counts"]["verified_free_removed"], 1)

    def test_duplicate_conflicting_and_invalid_ids_never_become_baselines(self):
        self.run_snapshot("free", "2026-01-01", snapshot([route()]))
        invalid = [[route(price="1"), "maker/model"], ["maker/model", "maker/model"],
                   [""], ["   "], [{"id": 42}], [" maker/model"]]
        for i, rows in enumerate(invalid):
            result = self.run_snapshot(f"invalid-{i}", f"2026-01-0{i + 2}", snapshot(rows))
            self.assertFalse(result["source_health"]["openrouter"]["complete"])
            self.assertEqual(result["alert_events"], [])
            self.assertEqual(result["baselines"]["openrouter"]["run_id"], "free")
        self.assertEqual(self.run_snapshot("paid", "2026-01-09", snapshot([route(price="1")]))["counts"]["verified_free_paid"], 1)

    def test_result_baselines_and_event_reporting_aliases(self):
        self.run_snapshot("free", "2026-01-01", snapshot([route()]))
        result = self.run_snapshot("loss", "2026-01-02")
        self.assertEqual(result["baselines"], {s: result["source_health"][s]["baseline"] for s in PROVIDERS})
        for event in result["events"] + self.rollup("2026-01-02")["net_events"]:
            self.assertEqual(event["kind"], event["type"])
            self.assertEqual(event["source"], event["provider"])
            self.assertEqual(event["route_id"], event["id"])
            self.assertEqual(event["model"], event["canonical_id"])

    def test_exact_route_identity_and_verified_alternative(self):
        snap = snapshot([route("maker/model:free"), route("maker/model", price="1")],
                        zen=[{"id": "model-free"}])
        self.run_snapshot("before", "2026-01-01", snap)
        snap["openrouter"] = [route("maker/model", price="1")]
        result = self.run_snapshot("after", "2026-01-02", snap)
        self.assertEqual(result["counts"]["verified_free_removed"], 1)
        self.assertEqual(result["counts"]["verified_free_paid"], 0)
        event = result["alert_events"][0]
        self.assertEqual(event["id"], "maker/model:free")
        self.assertEqual([(r["provider"], r["id"]) for r in event["alternatives"]], [("zen", "model-free")])
        self.assertEqual(event["access_status"], "verified_alternative")
        self.assertFalse(event["unknown_coverage"])

    def test_zen_created_timestamp_is_not_a_catalog_change(self):
        zen = lambda created, owner="opencode": [{"id": "model-free", "object": "model", "created": created, "owned_by": owner}]
        self.run_snapshot("first", "2026-01-01", snapshot(zen=zen(1)))
        result = self.run_snapshot("second", "2026-01-02", snapshot(zen=zen(2)))
        self.assertEqual(result["counts"]["catalog_changed"], 0)
        result = self.run_snapshot("third", "2026-01-03", snapshot(zen=zen(3, "someone-else")))
        self.assertEqual(result["counts"]["catalog_changed"], 1)
        # Other providers keep `created` in their fingerprint.
        self.run_snapshot("or-1", "2026-01-04", snapshot([route(created=1)]))
        result = self.run_snapshot("or-2", "2026-01-05", snapshot([route(created=2)]))
        self.assertEqual(result["counts"]["catalog_changed"], 1)

    def test_outage_alternatives_and_namespace_collisions(self):
        self.run_snapshot("before", "2026-01-01", snapshot([route()]))
        h = health()
        h["zen"].update(status="failed", complete=False)
        snap = snapshot([route("other/model")], zen=[{"id": "model-free"}])
        result = self.run_snapshot("after", "2026-01-02", snap, h)
        loss = result["alert_events"][0]
        self.assertEqual(loss["alternatives"], [])
        self.assertTrue(loss["unknown_coverage"])
        self.assertIn("zen", loss["unknown_sources"])
        self.assertEqual(loss["access_status"], "unknown")

    def test_explicit_mapping_never_promotes_provisional_routes(self):
        mappings = [{"slug": "model", "free_status": "verified", "routes": [
            {"provider": "openrouter", "id": "maker/first"},
            {"provider": "zen", "id": "other-second-free"},
            {"provider": "nvidia", "id": "third"}]}]
        self.run_snapshot("before", "2026-01-01", snapshot([route("maker/first")]), models=mappings)
        result = self.run_snapshot("after", "2026-01-02",
                                   snapshot(zen=[{"id": "other-second-free"}], nvidia=[{"id": "third"}]),
                                   models=mappings)
        loss = result["alert_events"][0]
        self.assertEqual([r["id"] for r in loss["alternatives"]], ["other-second-free"])
        self.assertTrue(loss["unknown_coverage"])

    def test_replay_and_transactional_prepared_replacement(self):
        self.run_snapshot("before", "2026-01-01", snapshot([route()]))
        first = self.run_snapshot("replay", "2026-01-02", publish=False)
        repeated = self.run_snapshot("replay", "2026-01-02", publish=False)
        self.assertEqual(first, repeated)
        self.assertEqual(self.rows("SELECT count(*) FROM history_events WHERE run_id='replay'")[0][0], 2)
        replaced = self.run_snapshot("replay", "2026-01-02", snapshot([route(price="1")]), publish=False)
        self.assertEqual(replaced["counts"]["verified_free_paid"], 1)
        self.assertEqual(replaced["counts"]["verified_free_removed"], 0)
        self.assertEqual(self.rows("SELECT count(*) FROM history_routes WHERE run_id='replay'")[0][0], 1)
        publish_run(self.db, "replay")
        self.assertEqual(publish_run(self.db, "replay"), replaced)
        self.assertEqual(self.run_snapshot("replay", "2026-01-02", snapshot([route(price="1")])), replaced)
        with self.assertRaisesRegex(ValueError, "published"):
            self.run_snapshot("replay", "2026-01-02")
        self.assertEqual(self.rows("SELECT count(*) FROM history_events WHERE run_id='replay'")[0][0], 2)

    def test_failed_replacement_rolls_back_existing_preparation(self):
        self.run_snapshot("before", "2026-01-01", snapshot([route()]))
        original = self.run_snapshot("pending", "2026-01-02", publish=False)
        with patch("analysis.history.event_details", side_effect=RuntimeError("synthetic failure")):
            with self.assertRaises(RuntimeError):
                self.run_snapshot("pending", "2026-01-02", snapshot([route(price="1")]), publish=False)
        self.assertEqual(self.run_snapshot("pending", "2026-01-02", publish=False), original)

    def test_rule_version_mismatch_is_not_compared(self):
        with patch("analysis.history.RULE_VERSION", RULE_VERSION - 1), patch("analysis.churn.RULE_VERSION", RULE_VERSION - 1):
            self.run_snapshot("old-rule", "2026-01-01", snapshot([route()]))
            self.run_snapshot("old-prepared", "2026-01-02", publish=False)
        result = self.run_snapshot("new-rule", "2026-01-02")
        self.assertEqual(result["alert_events"], [])
        self.assertIsNone(result["source_health"]["openrouter"]["baseline"])
        current_daily = json.loads(self.rows("SELECT rollup_json FROM history_daily WHERE day=? AND source=? AND rule_version=?",
                                             ("2026-01-02", "openrouter", RULE_VERSION))[0][0])
        self.assertIsNone(current_daily["baseline"])
        with self.assertRaisesRegex(ValueError, "different rule version"):
            publish_run(self.db, "old-prepared")
        self.assertEqual(self.rows("SELECT state FROM history_runs WHERE run_id='old-prepared'")[0][0], "prepared")
        with self.assertRaisesRegex(ValueError, "published"):
            self.run_snapshot("old-rule", "2026-01-01", snapshot([route()]))

    def test_legacy_migration_has_sqlite_backup_and_preserves_tables(self):
        with closing(sqlite3.connect(self.db)) as con, con:
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("CREATE TABLE models(id TEXT,free INTEGER)")
            con.execute("INSERT INTO models VALUES('legacy',1)")
            con.execute("CREATE TABLE free_history(slug TEXT,day TEXT,free_status TEXT)")
            con.execute("INSERT INTO free_history VALUES('legacy','2026-01-01','verified')")
        result = self.run_snapshot("first-route-run", "2026-01-02")
        self.assertEqual(result["events"], [])
        self.assertEqual(self.rows("SELECT * FROM models"), [("legacy", 1)])
        backup = list(self.root.glob("*.backup-v0*.sqlite"))
        self.assertEqual(len(backup), 1)
        with closing(sqlite3.connect(backup[0])) as con:
            self.assertEqual(con.execute("SELECT * FROM models").fetchall(), [("legacy", 1)])
            self.assertIsNone(con.execute("SELECT name FROM sqlite_master WHERE name='history_runs'").fetchone())
        self.run_snapshot("next", "2026-01-03")
        self.assertEqual(len(list(self.root.glob("*.backup-v0*.sqlite"))), 1)

    def test_retention_preserves_source_baseline_routes_and_daily_observations(self):
        self.run_snapshot("old", "2024-01-01", snapshot([route()]))
        self.run_snapshot("baseline", "2025-01-01", snapshot([route()]))
        self.run_snapshot("prepared", "2025-01-02", publish=False)
        self.run_snapshot("loss", "2026-01-01")
        self.run_snapshot("restored", "2026-01-01T12:00:00Z", snapshot([route()]))
        h = health("failed")
        self.run_snapshot("recent-failed", "2026-06-01", source_health=h)
        pruned = prune_history(self.db, "2026-06-02")
        ids = {r[0] for r in self.rows("SELECT run_id FROM history_runs")}
        self.assertEqual(ids, {"restored", "recent-failed"})
        self.assertIn("restored", pruned["preserved_baseline_runs"])
        self.assertEqual(self.rows("SELECT route_id FROM history_routes WHERE run_id='restored'"), [("maker/model",)])
        self.assertEqual(self.rows("SELECT count(*) FROM history_daily WHERE day='2025-01-01'")[0][0], 0)
        observed = [e["type"] for e in self.rollup("2026-01-01")["observed_events"]]
        self.assertIn("verified_free_removed", observed)
        self.assertIn("free_restored", observed)
        result = self.run_snapshot("recovery", "2026-06-03")
        self.assertEqual(result["counts"]["verified_free_removed"], 1)
        self.assertEqual(result["source_health"]["openrouter"]["baseline"]["run_id"], "restored")
        self.assertEqual(self.rows("PRAGMA foreign_key_check"), [])

    def test_long_outage_keeps_baseline_beyond_both_windows(self):
        self.run_snapshot("ancient", "2024-01-01", snapshot([route()]))
        self.run_snapshot("failed", "2026-01-01", source_health=health("failed"))
        prune_history(self.db, dt.datetime(2026, 1, 2, tzinfo=dt.timezone.utc))
        self.assertIn(("ancient",), self.rows("SELECT run_id FROM history_runs"))
        result = self.run_snapshot("recovery", "2026-01-03")
        self.assertEqual(result["counts"]["verified_free_removed"], 1)
        self.assertEqual(self.rollup("2026-01-03")["baseline"]["run_id"], "ancient")
        self.assertIn("verified_free_removed", [e["type"] for e in self.rollup("2026-01-03")["net_events"]])

    def test_late_publication_updates_next_day_net(self):
        self.run_snapshot("first", "2026-01-01", snapshot([route()]))
        self.run_snapshot("late", "2026-01-02", snapshot([route(price="1")]), publish=False)
        self.run_snapshot("third", "2026-01-03", snapshot([route()]))
        self.assertEqual(self.rollup("2026-01-03")["net_events"], [])
        publish_run(self.db, "late")
        self.assertIn("free_restored", [e["type"] for e in self.rollup("2026-01-03")["net_events"]])
        self.assertEqual(self.rollup("2026-01-03")["baseline"]["run_id"], "late")

    def test_alerts_use_selected_report_and_write_errors_propagate(self):
        self.run_snapshot("before", "2026-01-01", snapshot([route()]))
        result = self.run_snapshot("after", "2026-01-02")
        report_path = self.root / "selected.json"
        report_path.write_text(json.dumps({"stamp": "selected", "churn": result, "free_churn": {}}), encoding="utf-8")
        alerts = self.root / "alerts"
        out = alert_main(report_path, alerts)
        text = Path(out).read_text(encoding="utf-8")
        self.assertIn("maker/model", text)
        self.assertIn("selected", text)
        self.assertNotIn("provisional", text)
        self.assertEqual([p.name for p in alerts.iterdir()], ["selected_churn_alert.md"])
        blocked = self.root / "not-a-directory"
        blocked.write_text("file", encoding="utf-8")
        with self.assertRaises(OSError):
            alert_main(report_path, blocked)

    def test_alerts_prefer_structured_churn_with_trusted_legacy_fallback(self):
        self.run_snapshot("free", "2026-01-01", snapshot([route()]))
        loss = self.run_snapshot("loss", "2026-01-02")
        path = self.root / "report.json"
        path.write_text(json.dumps({"churn": {}, "free_churn": loss}), encoding="utf-8")
        self.assertIsNone(alert_main(path, self.root / "alerts"))
        path.write_text(json.dumps({"free_churn": loss}), encoding="utf-8")
        self.assertIsNotNone(alert_main(path, self.root / "alerts"))

    def test_alerts_show_baseline_current_and_original_free_evidence_times(self):
        self.run_snapshot("free", "2026-01-01", snapshot([route()]), health(fetched_at="2026-01-01T00:10:00Z"))
        self.run_snapshot("unknown", "2026-01-02", snapshot([route(pricing={})]), health(fetched_at="2026-01-02T00:10:00Z"))
        loss = self.run_snapshot("loss", "2026-01-03", snapshot([route(price="1")]), health(fetched_at="2026-01-03T00:10:00Z"))
        path = self.root / "report.json"
        path.write_text(json.dumps({"churn": loss}), encoding="utf-8")
        output = Path(alert_main(path, self.root / "alerts")).read_text(encoding="utf-8")
        self.assertIn("Baseline observed: 2026-01-02T00:10:00Z", output)
        self.assertIn("current observed: 2026-01-03T00:10:00Z", output)
        self.assertIn("Last decisive verified-free evidence: 2026-01-01T00:10:00Z", output)
        self.assertIn("run `free`", output)

    def test_alerts_require_explicit_paths_and_use_shared_cli(self):
        for kwargs in ({}, {"input_path": "missing.json"}, {"output_dir": self.root}):
            with self.assertRaisesRegex(ValueError, "Explicit"):
                alert_main(**kwargs)
        path = self.root / "report.json"
        path.write_text(json.dumps({"churn": {"trusted_route_history": True, "events": []}}), encoding="utf-8")
        script = Path(__file__).resolve().parents[1] / "alerts" / "check_churn.py"
        proc = subprocess.run([sys.executable, str(script), "--input", str(path), "--output", str(self.root / "out")],
                              cwd=self.root, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("no verified-free route losses", proc.stdout)
        missing = subprocess.run([sys.executable, str(script)], cwd=self.root, capture_output=True, text=True)
        self.assertNotEqual(missing.returncode, 0)

    def test_legacy_and_unknown_reports_do_not_alert(self):
        path = self.root / "report.json"
        reports = [{"prev_day": "2026-01-01", "disappeared_total": 20, "flipped_to_paid_total": 3},
                   {"trusted_route_history": True, "events": [{"type": "verification_unknown"}]}]
        for churn in reports:
            path.write_text(json.dumps({"free_churn": churn}), encoding="utf-8")
            self.assertIsNone(alert_main(path, self.root / "alerts"))
        self.assertFalse((self.root / "alerts").exists())


if __name__ == "__main__":
    unittest.main()
