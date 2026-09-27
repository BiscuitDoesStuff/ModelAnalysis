"""Alerts from the selected report's trusted, verified-free route losses only."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
MD_CAP = 20
LOSS_TYPES = frozenset(("verified_free_paid", "verified_free_removed"))


def main(input_path=None, output_dir=None):
    if input_path is None or output_dir is None:
        raise ValueError("Explicit input_path and output_dir are required")
    with open(input_path, encoding="utf-8") as stream:
        report = json.load(stream)
    stamp = str(report.get("stamp") or report.get("run_id") or "unknown")
    # A present structured field is authoritative, including an empty/no-loss result.
    churn = (report.get("churn") if "churn" in report else report.get("free_churn")) or {}
    if not churn.get("trusted_route_history"):
        print(f"alerts {stamp}: no trusted route baseline (legacy/informational report)")
        return None
    losses = [e for e in churn.get("events", []) if e.get("type") in LOSS_TYPES
              and e.get("baseline_run_id") and (e.get("before") or {}).get("verified_free") is True]
    if not losses:
        print(f"alerts {stamp}: no verified-free route losses")
        return None
    lines = [f"# Verified-free route loss — {stamp}\n\n",
             f"{len(losses)} verified-free route loss(es).\n"]
    for event in losses[:MD_CAP]:
        lines.append(f"\n- `{event['provider']}:{event['id']}` — {event['type']}\n")
        source_health = (churn.get("source_health") or {}).get(event["provider"]) or {}
        baseline = source_health.get("baseline") or (churn.get("baselines") or {}).get(event["provider"]) or {}
        baseline_time = event.get("baseline_observed_at") or baseline.get("fetched_at") or baseline.get("started_at") or "unknown"
        current_time = event.get("current_observed_at") or source_health.get("fetched_at") or churn.get("started_at") or "unknown"
        lines.append(f"  Baseline observed: {baseline_time}; current observed: {current_time}.\n")
        evidence_time = event.get("before_observed_at") or (event.get("before") or {}).get("observed_at")
        if evidence_time:
            lines.append(f"  Last decisive verified-free evidence: {evidence_time}"
                         f" (run `{event.get('before_run_id') or event['baseline_run_id']}`).\n")
        alternatives = event.get("alternatives") or []
        verified = [r for r in alternatives if r.get("verified_free") is True]
        if verified:
            lines.append("  Verified-free alternatives: " + ", ".join(
                f"`{r['provider']}:{r['id']}`" for r in verified) + ".\n")
        if event.get("unknown_coverage", True):
            lines.append("  Alternative coverage is incomplete or unverified; remaining free access is unknown.\n")
        elif not verified:
            lines.append("  No verified-free alternative in the compared catalogs.\n")
    if len(losses) > MD_CAP:
        lines.append(f"\n… and {len(losses) - MD_CAP} more; see this report's churn events.\n")
    directory = os.fspath(output_dir)
    os.makedirs(directory, exist_ok=True)
    safe_stamp = stamp.replace("/", "_").replace("\\", "_").replace(":", "_")
    path = os.path.join(directory, f"{safe_stamp}_churn_alert.md")
    with open(path, "w", encoding="utf-8") as stream:
        stream.write("".join(lines))
    print(f"ALERT written to {path}")
    return path


if __name__ == "__main__":
    from pipeline_common import stage_cli
    stage_cli(main, __doc__)
