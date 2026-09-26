"""Smoke check for the 9-section report contract. Run: python tests/smoke.py"""
import json, glob, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
fails = []


def check(cond, msg):
    print(("ok  " if cond else "FAIL") + f" {msg}")
    if not cond:
        fails.append(msg)


a_files = sorted(glob.glob(os.path.join(ROOT, "analysis", "*_analysis.json")), key=os.path.getmtime)
r_files = sorted(glob.glob(os.path.join(ROOT, "reports", "*_models.json")), key=os.path.getmtime)
check(a_files and r_files, "analysis + report files exist")
if not (a_files and r_files):
    sys.exit(1)

a = json.load(open(a_files[-1], encoding="utf-8"))
r = json.load(open(r_files[-1], encoding="utf-8"))
check(a.get("stamp") == r.get("stamp"), f"stamps match ({a.get('stamp')})")
check(r.get("thresholds") == {"max": 50, "high": 40, "medium": 30}, "thresholds 50/40/30")
check(len(a.get("models", [])) > 0, f"canonical models non-empty ({len(a.get('models', []))})")

for key in ["all_intel", "all_cost", "all_ratio_paid", "all_ratio_free_by_score",
            "ocf_intel", "ocf_cost", "ocf_ratio_paid",
            "ocf_stack", "ocf_practical", "ocf_outliers"]:
    check(key in r, f"report key {key}")

tiers = set(a.get("thresholds", {})) | {"max", "high", "medium"}
check(set(r["ocf_stack"]) == {"max", "high", "medium"}, "stack has 3 tiers")
for t in ("max", "high", "medium"):
    rows = r["ocf_stack"][t]["rows"]
    check(all(m.get("tier") == t for m in rows), f"stack[{t}] tiers consistent ({len(rows)})")
    check(set(r["ocf_stack"][t]["gaps"]) <= {"O", "C", "F"}, f"stack[{t}] gaps valid")
check(len(r["ocf_practical"]) == 12, f"practical has 12 tier x variant rows ({len(r['ocf_practical'])})")
check({(p["tier"], p["variant"]) for p in r["ocf_practical"]} ==
      {(t, v) for t in ("max", "high", "medium") for v in ("OCF", "OF", "CF", "F")},
      "practical covers all tier x variant combos")
check(set(r["ocf_outliers"]) == {"bargains", "overpriced", "free_gems"}, "outlier classes")

try:
    from openpyxl import load_workbook
    wb = load_workbook(r_files[-1].replace("_models.json", "_models.xlsx"))
    want = {"summary", "All_Intel", "All_Cost", "All_Ratio", "OCF_Intel",
            "OCF_Cost", "OCF_Ratio", "OCF_Outliers", "OCF_Stack", "OCF_Practical"}
    check(set(wb.sheetnames) == want, f"xlsx has 10 tabs ({len(wb.sheetnames)})")
except ImportError:
    print("skip xlsx check (openpyxl missing)")

print(f"{len(fails)} failures")
sys.exit(1 if fails else 0)
