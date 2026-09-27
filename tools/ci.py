"""Reproduce CI locally, offline: python -B tools/ci.py

1. golden fixture files match tests/fixtures/make_golden.py
2. tests/test_units.py
3. unittest discovery over tests/test_*.py
4. golden replay through pipeline.py into a temporary state dir and database
5. tests/smoke.py on that bundle
6. golden coverage: the conditional smoke checks had content to act on
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
PY = [sys.executable, "-B"]


def golden_coverage(bundle):
    """Problems that would let smoke pass while skipping the checks the fixture exists for."""
    bundle = Path(bundle)
    a = json.loads(next((bundle / "analysis").glob("*_analysis.json")).read_text(encoding="utf-8"))
    models = a["models"]
    kinds = [(m.get("score_source") or {}).get("kind") for m in models]
    status = [m.get("free_status") for m in models]
    want = {
        "inherited estimates": kinds.count("inherited-estimate") >= 2,
        "registry (external) score": "external" in kinds,
        "verified free": "verified" in status,
        "provisional-l1": "provisional-l1" in status,
        "provisional-l0": "provisional-l0" in status,
        "zen -free fallback": any(m.get("fallback_provider") == "zen" and "free" in m.get("fallback_id", "")
                                  for m in models),
        "effort variants": len({m.get("variant") for m in models} - {""}) >= 3,
        "claudeopus5medium": any(m.get("slug") == "claudeopus5medium" for m in models),
        "benchlm join": any(m.get("benchlm") for m in models),
        "llmstats join": any(m.get("llmstats_api") or m.get("llmstats_rank") for m in models),
        "bench-only entity": any(m.get("bench_only") for m in models),
        "router row": any(m.get("router") for m in models),
        "complete coverage": json.loads((bundle / "manifest.json").read_text(encoding="utf-8")).get("coverage") == "complete",
    }
    return [name for name, ok in want.items() if not ok]


def replay(snapshot, state):
    """Replay a fixture snapshot with its pinned evidence day and registry; return the bundle."""
    fixture = json.loads(Path(snapshot).read_text(encoding="utf-8")).get("fixture") or {}
    cmd = PY + ["pipeline.py", "--snapshot", str(snapshot), "--state-dir", str(state / "runs"),
                "--db", str(state / "history.sqlite")]
    for flag, key in (("--websites", "websites"), ("--registry", "registry"), ("--as-of", "as_of")):
        if fixture.get(key):
            cmd += [flag, str(ROOT / fixture[key]) if key != "as_of" else fixture[key]]
    subprocess.run(cmd, cwd=ROOT, check=True)
    current = json.loads((state / "runs" / "current.json").read_text(encoding="utf-8"))
    return state / "runs" / current["bundle"]


def main():
    steps = [("golden fixture up to date", PY + ["tests/fixtures/make_golden.py", "--check"]),
             ("unit checks", PY + ["tests/test_units.py"]),
             ("unittest discovery", PY + ["-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"])]
    for name, cmd in steps:
        print(f"== {name}", flush=True)
        subprocess.run(cmd, cwd=ROOT, check=True)
    with tempfile.TemporaryDirectory() as tmp:
        print("== golden replay", flush=True)
        bundle = replay(FIXTURES / "golden_snapshot.json", Path(tmp))
        print("== smoke", flush=True)
        subprocess.run(PY + ["tests/smoke.py", "--bundle", str(bundle)], cwd=ROOT, check=True)
        print("== golden coverage", flush=True)
        missing = golden_coverage(bundle)
        if missing:
            print("golden fixture no longer covers: " + ", ".join(missing))
            return 1
    print("CI checks passed")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as exc:
        print(f"FAILED: {' '.join(map(str, exc.cmd))} (exit {exc.returncode})")
        sys.exit(1)
