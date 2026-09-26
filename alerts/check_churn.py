"""4. Alerts — evaluate free_churn from the latest report, print a summary, write an alert file on bad news. Never fails."""
import json, os, glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REP = os.path.join(ROOT, "reports")

MD_CAP = 20


def main():
    r_files = sorted(glob.glob(os.path.join(REP, "*_models.json")), key=os.path.getmtime)
    if not r_files:
        print("alerts: no reports yet (run reports/build_report.py first)")
        return
    with open(r_files[-1], encoding="utf-8") as f:
        r = json.load(f)
    stamp = r.get("stamp", "unknown")
    ch = r.get("free_churn") or {}
    prev = ch.get("prev_day")
    if not prev:
        print(f"alerts {stamp}: no baseline yet (single day in history) — nothing to compare")
        return
    to_paid = ch.get("flipped_to_paid_total", 0)
    to_free = ch.get("flipped_to_free_total", 0)
    level = ch.get("level_changed_total", 0)
    gone = ch.get("disappeared_total", 0)
    new = ch.get("new_total", 0)
    or_paid = ch.get("or_flipped_to_paid_total", 0)
    or_free = ch.get("or_flipped_to_free_total", 0)
    print(f"alerts {stamp} vs {prev}: to_paid={to_paid} to_free={to_free} "
          f"level={level} disappeared={gone} new={new} or_to_paid={or_paid} or_to_free={or_free}")
    bad = to_paid + gone + or_paid
    if not bad:
        if to_free or or_free:
            print(f"alerts {stamp}: good news only ({to_free + or_free} newly free) — no alert file")
        else:
            print(f"alerts {stamp}: no churn — no alert file")
        return
    L = [f"# Churn alert — {stamp} (vs {prev})\n",
         f"Free→paid flips: {to_paid} | disappeared: {gone} | OR free→paid: {or_paid} | "
         f"newly free: {to_free} | level changes: {level} | new listings: {new}\n"]
    for title, items in [("Free→paid (was free-ish, now paid/unlisted-free)", ch.get("flipped_to_paid", [])),
                         ("Disappeared listings", ch.get("disappeared", [])),
                         ("OR free→paid flips", ch.get("or_flipped_to_paid", []))]:
        if items:
            L.append(f"\n## {title}\n")
            L += [f"- `{i}`\n" for i in items[:MD_CAP]]
            if len(items) > MD_CAP:
                L.append(f"_…and {len(items) - MD_CAP} more (see JSON free_churn)_\n")
    if ch.get("flipped_to_free"):
        L.append("\n_Newly free (verify billing before trusting): " +
                 ", ".join(f"`{i}`" for i in ch["flipped_to_free"][:MD_CAP]) + "_\n")
    L.append("\n_Action: re-run on use for fresh data; spot-check billing requirements on flipped "
             "models before trusting free status._\n")
    out = os.path.join(REP, f"{stamp}_churn_alert.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write("".join(L))
    print(f"ALERT written to {out}")


if __name__ == "__main__":
    main()
