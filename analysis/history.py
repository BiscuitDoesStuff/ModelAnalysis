"""Versioned, publication-gated SQLite route history.

Public API: prepare_run(...), publish_run(db_path, run_id),
prune_history(db_path, now, run_days=90, daily_days=365).
The prepare result is immutable on an identical replay, including its baseline refs.
"""
import datetime as dt
import json
import os
import sqlite3

try:
    from .churn import (RULE_VERSION, PROVIDERS, EVENT_TYPES, build_routes, compare_routes,
                        digest, encoded, event_details, retain_decisive)
except ImportError:
    from churn import (RULE_VERSION, PROVIDERS, EVENT_TYPES, build_routes, compare_routes,
                       digest, encoded, event_details, retain_decisive)

SCHEMA_VERSION = 1
_DDL = (
    "CREATE TABLE history_schema(version INTEGER NOT NULL)",
    """CREATE TABLE history_runs(
        run_id TEXT PRIMARY KEY, started_at TEXT NOT NULL, day TEXT NOT NULL,
        state TEXT NOT NULL CHECK(state IN ('prepared','published')),
        rule_version INTEGER NOT NULL, input_hash TEXT NOT NULL, result_json TEXT NOT NULL)""",
    """CREATE TABLE history_sources(
        run_id TEXT NOT NULL REFERENCES history_runs ON DELETE CASCADE,
        source TEXT NOT NULL, complete INTEGER NOT NULL, health_json TEXT NOT NULL,
        known_free_json TEXT NOT NULL, PRIMARY KEY(run_id,source))""",
    """CREATE TABLE history_routes(
        run_id TEXT NOT NULL, source TEXT NOT NULL, route_id TEXT NOT NULL, route_json TEXT NOT NULL,
        PRIMARY KEY(run_id,source,route_id),
        FOREIGN KEY(run_id,source) REFERENCES history_sources ON DELETE CASCADE)""",
    """CREATE TABLE history_events(
        event_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES history_runs ON DELETE CASCADE,
        source TEXT NOT NULL, event_json TEXT NOT NULL)""",
    """CREATE TABLE history_daily(
        day TEXT NOT NULL, source TEXT NOT NULL, rule_version INTEGER NOT NULL,
        rollup_json TEXT NOT NULL, PRIMARY KEY(day,source,rule_version))""",
    "CREATE INDEX history_runs_order ON history_runs(state,rule_version,started_at,run_id)",
    "CREATE INDEX history_source_baselines ON history_sources(source,complete,run_id)",
)


def _timestamp(value):
    if isinstance(value, dt.datetime):
        parsed = value
    elif isinstance(value, dt.date):
        parsed = dt.datetime.combine(value, dt.time())
    else:
        text = str(value)
        if len(text) == 15 and text[10] == "_":
            parsed = dt.datetime.strptime(text, "%Y-%m-%d_%H%M")
        else:
            parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc).isoformat(timespec="microseconds")


def _connect(db_path):
    path = os.fspath(db_path)
    if path != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    con = sqlite3.connect(path, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    try:
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        version = con.execute("SELECT version FROM history_schema").fetchone()[0] if "history_schema" in tables else 0
        if version > SCHEMA_VERSION:
            raise ValueError("History schema is newer than this application")
        if version < SCHEMA_VERSION:
            # SQLite's backup API also includes committed WAL pages. Never copy a live DB file.
            if tables and path != ":memory:":
                backup_path = f"{path}.backup-v{version}.sqlite"
                suffix = 1
                while os.path.exists(backup_path):
                    backup_path = f"{path}.backup-v{version}-{suffix}.sqlite"
                    suffix += 1
                backup = sqlite3.connect(backup_path)
                try:
                    con.backup(backup)
                finally:
                    backup.close()
            with con:
                con.execute("BEGIN IMMEDIATE")
                # Legacy tables remain untouched and are never trusted as route baselines.
                for statement in _DDL:
                    con.execute(statement)
                con.execute("INSERT INTO history_schema VALUES(?)", (SCHEMA_VERSION,))
        return con
    except Exception:
        con.close()
        raise


def _routes(con, run_id, source):
    return {r["route_id"]: json.loads(r["route_json"]) for r in con.execute(
        "SELECT route_id,route_json FROM history_routes WHERE run_id=? AND source=?", (run_id, source))}


def _baseline(con, source, started_at, run_id):
    return con.execute("""SELECT r.*, s.known_free_json, s.health_json FROM history_runs r
        JOIN history_sources s USING(run_id)
        WHERE r.state='published' AND r.rule_version=? AND s.source=? AND s.complete=1
        AND r.run_id!=? AND (r.started_at<? OR (r.started_at=? AND r.run_id<?))
        ORDER BY r.started_at DESC,r.run_id DESC LIMIT 1""",
        (RULE_VERSION, source, run_id, started_at, started_at, run_id)).fetchone()


def _reference(row):
    if row is None:
        return None
    return {"run_id": row["run_id"], "started_at": row["started_at"], "day": row["day"],
            "fetched_at": json.loads(row["health_json"]).get("fetched_at"),
            "rule_version": row["rule_version"]}


def _health(source_health, malformed):
    health = {}
    for source in PROVIDERS:
        raw = (source_health or {}).get(source) or {}
        item = dict(raw) if isinstance(raw, dict) else {}
        item.setdefault("status", "skipped")
        item.setdefault("scope", "unknown")
        item.setdefault("fetched_at", None)
        item["complete"] = (item["status"] == "complete" and item.get("complete") is True
                            and item["scope"] == "catalog" and source not in malformed)
        if source in malformed and item["status"] == "complete":
            item.update(status="partial", coverage_reason="invalid-or-missing-catalog")
        health[source] = item
    return health


def _daily_rollup(con, day, source, candidate=None):
    """Latest complete source catalog today vs prior complete day; preserve observations."""
    rows = con.execute("""SELECT r.*,s.complete,s.health_json,s.known_free_json FROM history_runs r
        JOIN history_sources s USING(run_id) WHERE s.source=? AND r.day=? AND r.rule_version=?
        AND (r.state='published' OR r.run_id=?) ORDER BY r.started_at,r.run_id""",
        (source, day, RULE_VERSION, candidate or "")).fetchall()
    saved = con.execute("SELECT rollup_json FROM history_daily WHERE day=? AND source=? AND rule_version=?",
                        (day, source, RULE_VERSION)).fetchone()
    previous = con.execute("""SELECT rollup_json FROM history_daily WHERE source=? AND day<?
        AND rule_version=? ORDER BY day DESC""", (source, day, RULE_VERSION)).fetchall()
    prior = next((value for row in previous
                  if (value := json.loads(row[0])).get("latest_complete")), None)
    if prior is None:
        # A source's retained baseline may predate the daily-retention window.
        baseline = con.execute("""SELECT r.*,s.health_json,s.known_free_json FROM history_runs r
            JOIN history_sources s USING(run_id) WHERE s.source=? AND s.complete=1
            AND r.state='published' AND r.rule_version=? AND r.day<?
            ORDER BY r.started_at DESC,r.run_id DESC LIMIT 1""", (source, RULE_VERSION, day)).fetchone()
        if baseline:
            prior = {"latest_complete": _reference(baseline),
                     "routes": _routes(con, baseline["run_id"], source),
                     "known_free": json.loads(baseline["known_free_json"])}
    old_saved = json.loads(saved[0]) if saved else {}
    latest = next((row for row in reversed(rows) if row["complete"]), None)
    current_ref = _reference(latest) if latest else old_saved.get("latest_complete")
    current_routes = _routes(con, latest["run_id"], source) if latest else old_saved.get("routes", {})
    known = json.loads(latest["known_free_json"]) if latest else old_saved.get("known_free", [])
    # Rollups can outlive their original runs; keep the newer retained complete catalog.
    retained_ref = old_saved.get("latest_complete")
    if retained_ref and current_ref and (retained_ref["started_at"], retained_ref["run_id"]) > (
            current_ref["started_at"], current_ref["run_id"]):
        current_ref, current_routes = retained_ref, old_saved["routes"]
        known = old_saved.get("known_free", [])
    observed = {e["event_id"]: e for e in old_saved.get("observed_events", [])}
    coverage = {item["run_id"]: item for item in old_saved.get("coverage", [])}
    for row in rows:
        coverage[row["run_id"]] = dict(json.loads(row["health_json"]), run_id=row["run_id"],
                                       started_at=row["started_at"])
        for event in con.execute("SELECT event_json FROM history_events WHERE run_id=? AND source=?",
                                 (row["run_id"], source)):
            value = json.loads(event[0])
            observed[value["event_id"]] = value
    net = compare_routes(prior["routes"], current_routes, prior.get("known_free", [])) if prior and current_ref else []
    baseline_ref = prior["latest_complete"] if prior else None
    if prior is None and current_ref == old_saved.get("latest_complete") and old_saved.get("baseline"):
        # Preserve historical net when its baseline has since aged out of both stores.
        net, baseline_ref = old_saved["net_events"], old_saved["baseline"]
    return {"day": day, "source": source, "rule_version": RULE_VERSION,
            "latest_complete": current_ref, "baseline": baseline_ref,
            "net_events": net, "observed_events": sorted(observed.values(), key=lambda e: (e.get("started_at", ""), e["event_id"])),
            "coverage": sorted(coverage.values(), key=lambda h: (h["started_at"], h["run_id"])),
            "routes": current_routes, "known_free": known}


def _daily_public(rollup):
    return {key: value for key, value in rollup.items() if key not in ("routes", "known_free")}


def prepare_run(db_path, snapshot, models, run_id, started_at, source_health):
    """Atomically stage a run; identical replay returns the original churn dictionary.

    Only publish_run makes a run baseline-eligible. Published input is immutable.
    source_health needs status='complete', complete=True, scope='catalog' to compare.
    """
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("run_id must be a nonempty string")
    started_at = _timestamp(started_at)
    day = started_at[:10]
    input_hash = digest([RULE_VERSION, snapshot, models, started_at, source_health])
    routes, malformed = build_routes(snapshot, models)
    health = _health(source_health, malformed)
    con = _connect(db_path)
    try:
        with con:
            con.execute("BEGIN IMMEDIATE")
            existing = con.execute("SELECT * FROM history_runs WHERE run_id=?", (run_id,)).fetchone()
            if existing and existing["input_hash"] == input_hash:
                return json.loads(existing["result_json"])
            if existing and existing["state"] == "published":
                raise ValueError("Cannot rewrite a published run with different input")
            con.execute("DELETE FROM history_runs WHERE run_id=?", (run_id,))
            con.execute("INSERT INTO history_runs VALUES(?,?,?,?,?,?,?)",
                        (run_id, started_at, day, "prepared", RULE_VERSION, input_hash, "{}"))
            baselines, known = {}, {}
            for source in PROVIDERS:
                baseline = _baseline(con, source, started_at, run_id)
                baselines[source] = baseline
                health[source]["baseline"] = _reference(baseline)
                health[source]["compared"] = bool(baseline and health[source]["complete"])
                known[source] = set(json.loads(baseline["known_free_json"])) if baseline else set()
                if health[source]["complete"]:
                    retain_decisive(routes[source], _routes(con, baseline["run_id"], source) if baseline else {},
                                    run_id, health[source].get("fetched_at") or started_at)
                    known[source].update(mid for mid, route in routes[source].items() if route["verified_free"])
                con.execute("INSERT INTO history_sources VALUES(?,?,?,?,?)",
                            (run_id, source, int(health[source]["complete"]), encoded(health[source]), encoded(sorted(known[source]))))
                con.executemany("INSERT INTO history_routes VALUES(?,?,?,?)",
                                [(run_id, source, mid, encoded(route)) for mid, route in routes[source].items()])
            events = []
            for source in PROVIDERS:
                baseline = baselines[source]
                if not health[source]["compared"]:
                    continue
                changes = compare_routes(_routes(con, baseline["run_id"], source), routes[source],
                                         json.loads(baseline["known_free_json"]))
                for change in changes:
                    event = event_details(change, run_id, baseline["run_id"], routes, health)
                    event["started_at"] = started_at
                    event["current_observed_at"] = event["current_observed_at"] or started_at
                    events.append(event)
                    con.execute("INSERT INTO history_events VALUES(?,?,?,?)",
                                (event["event_id"], run_id, source, encoded(event)))
            counts = {kind: sum(e["type"] == kind for e in events) for kind in EVENT_TYPES}
            result = {"schema_version": SCHEMA_VERSION, "rule_version": RULE_VERSION,
                      "run_id": run_id, "started_at": started_at, "day": day,
                      "trusted_route_history": True, "events": events,
                      "alert_events": [e for e in events if e["alert"]], "counts": counts,
                      "source_health": health,
                      "baselines": {source: health[source]["baseline"] for source in PROVIDERS},
                      "coverage": {"complete_sources": [s for s in PROVIDERS if health[s]["complete"]],
                                   "unknown_sources": [s for s in PROVIDERS if not health[s]["complete"]],
                                   "compared_sources": [s for s in PROVIDERS if health[s]["compared"]]},
                      "daily": {"day": day, "sources": {s: _daily_public(_daily_rollup(con, day, s, run_id))
                                                          for s in PROVIDERS}}}
            con.execute("UPDATE history_runs SET result_json=? WHERE run_id=?", (encoded(result), run_id))
            return result
    finally:
        con.close()


def publish_run(db_path, run_id):
    """Publish a staged run and its daily rollups atomically; safe to repeat."""
    con = _connect(db_path)
    try:
        with con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT * FROM history_runs WHERE run_id=?", (run_id,)).fetchone()
            if row is None:
                raise ValueError(f"Unknown prepared run: {run_id}")
            if row["state"] == "published":
                return json.loads(row["result_json"])
            if row["rule_version"] != RULE_VERSION:
                raise ValueError("Cannot publish a run prepared with a different rule version")
            con.execute("UPDATE history_runs SET state='published' WHERE run_id=?", (run_id,))
            # Rebuild subsequent retained days too, so late publication keeps daily net coherent.
            days = {row["day"]}
            days.update(r[0] for r in con.execute(
                "SELECT DISTINCT day FROM history_daily WHERE day>? AND rule_version=?", (row["day"], RULE_VERSION)))
            for day in sorted(days):
                for source in PROVIDERS:
                    rollup = _daily_rollup(con, day, source)
                    con.execute("INSERT OR REPLACE INTO history_daily VALUES(?,?,?,?)",
                                (day, source, RULE_VERSION, encoded(rollup)))
            return json.loads(row["result_json"])
    finally:
        con.close()


def prune_history(db_path, now, run_days=90, daily_days=365):
    """Prune raw runs and daily rollups, retaining the latest baseline per source/rule.

    A retained baseline retains its exact route data and known-free IDs, even in an
    extended outage. Daily JSON keeps observed losses/restorations after raw pruning.
    """
    if run_days < 0 or daily_days < 0:
        raise ValueError("Retention days must be nonnegative")
    moment = dt.datetime.fromisoformat(_timestamp(now))
    run_cutoff = (moment - dt.timedelta(days=run_days)).isoformat(timespec="microseconds")
    daily_cutoff = (moment - dt.timedelta(days=daily_days)).date().isoformat()
    con = _connect(db_path)
    try:
        with con:
            con.execute("BEGIN IMMEDIATE")
            protected = {r[0] for r in con.execute("""SELECT s.run_id FROM history_sources s
                JOIN history_runs r USING(run_id) WHERE s.complete=1 AND r.state='published'
                AND NOT EXISTS (SELECT 1 FROM history_sources ns JOIN history_runs nr USING(run_id)
                    WHERE ns.source=s.source AND ns.complete=1 AND nr.state='published'
                    AND nr.rule_version=r.rule_version AND
                    (nr.started_at>r.started_at OR (nr.started_at=r.started_at AND nr.run_id>r.run_id)))""")}
            stale = [r[0] for r in con.execute("SELECT run_id FROM history_runs WHERE started_at<?", (run_cutoff,))
                     if r[0] not in protected]
            con.executemany("DELETE FROM history_runs WHERE run_id=?", [(rid,) for rid in stale])
            removed_daily = con.execute("DELETE FROM history_daily WHERE day<?", (daily_cutoff,)).rowcount
            return {"runs_deleted": len(stale), "daily_deleted": removed_daily,
                    "preserved_baseline_runs": sorted(protected)}
    finally:
        con.close()
