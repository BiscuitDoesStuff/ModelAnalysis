"""Reproduce CI locally, offline: python -B tools/ci.py

1. golden fixture files match tests/fixtures/make_golden.py
2. tests/test_units.py
3. unittest discovery over tests/test_*.py
4. golden replay through pipeline.py into a temporary state dir and database
5. tests/smoke.py on that bundle
6. golden coverage: the conditional smoke checks had content to act on
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
PY = [sys.executable, "-B"]
# Child output may be piped; Windows pipes default to the ANSI code page.
ENV = dict(os.environ, PYTHONIOENCODING="utf-8")


def golden_coverage(bundle, recorded=False):
    """Problems that would let smoke pass while skipping the checks the fixture exists for.

    A recorded (real) fixture can't be required to hold what live data doesn't
    offer: registry AA scores were retired in 0a, and single estimates can lapse.
    """
    bundle = Path(bundle)
    a = json.loads(next((bundle / "analysis").glob("*_analysis.json")).read_text(encoding="utf-8"))
    models = a["models"]
    kinds = [(m.get("score_source") or {}).get("kind") for m in models]
    status = [m.get("free_status") for m in models]
    want = {
        "inherited estimates": kinds.count("inherited-estimate") >= (1 if recorded else 2),
        "registry (external) score": recorded or "external" in kinds,
        "verified free": "verified" in status,
        "provisional-l1": "provisional-l1" in status,
        "provisional-l0": "provisional-l0" in status,
        "zen -free fallback": any(m.get("fallback_provider") == "zen" and "free" in m.get("fallback_id", "")
                                  for m in models),
        "effort variants": len({m.get("variant") for m in models} - {""}) >= 3,
        "claudeopus5medium": recorded or any(m.get("slug") == "claudeopus5medium" for m in models),
        "benchlm join": any(m.get("benchlm") for m in models),
        "llmstats join": any(m.get("llmstats_api") or m.get("llmstats_rank") for m in models),
        "bench-only entity": any(m.get("bench_only") for m in models),
        "router row": any(m.get("router") for m in models),
        "complete coverage": json.loads((bundle / "manifest.json").read_text(encoding="utf-8")).get("coverage") == "complete",
    }
    return [name for name, ok in want.items() if not ok]


def replay(snapshot, state, quiet=False):
    """Replay a fixture snapshot with its pinned evidence day and registry; return the bundle.

    The snapshot's `fixture` block names its websites/registry files relative to itself.
    """
    snapshot = Path(snapshot).resolve()
    fixture = json.loads(snapshot.read_text(encoding="utf-8")).get("fixture") or {}
    cmd = PY + ["pipeline.py", "--snapshot", str(snapshot), "--state-dir", str(state / "runs"),
                "--db", str(state / "history.sqlite")]
    for flag, key in (("--websites", "websites"), ("--registry", "registry")):
        if fixture.get(key):
            cmd += [flag, str(snapshot.parent / fixture[key])]
    if fixture.get("as_of"):
        cmd += ["--as-of", fixture["as_of"]]
    subprocess.run(cmd, cwd=ROOT, check=True, env=ENV, stdout=subprocess.DEVNULL if quiet else None)
    current = json.loads((state / "runs" / "current.json").read_text(encoding="utf-8"))
    return state / "runs" / current["bundle"]


def main():
    steps = [("golden fixture up to date", PY + ["tests/fixtures/make_golden.py", "--check"]),
             ("unit checks", PY + ["tests/test_units.py"]),
             ("unittest discovery", PY + ["-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"])]
    for name, cmd in steps:
        print(f"== {name}", flush=True)
        subprocess.run(cmd, cwd=ROOT, check=True)
    # The synthetic fixture always runs; a fixture recorded from a real bundle
    # (tools/record_fixture.py) runs too once it is committed.
    for name in ("golden", "recorded"):
        snapshot = FIXTURES / f"{name}_snapshot.json"
        if not snapshot.exists():
            continue
        with tempfile.TemporaryDirectory() as tmp:
            print(f"== {name} replay", flush=True)
            bundle = replay(snapshot, Path(tmp))
            print(f"== {name} smoke", flush=True)
            subprocess.run(PY + ["tests/smoke.py", "--bundle", str(bundle)], cwd=ROOT, check=True)
            print(f"== {name} coverage", flush=True)
            missing = golden_coverage(bundle, recorded=name == "recorded")
            if missing:
                print(f"{name} fixture no longer covers: " + ", ".join(missing))
                return 1
    print("CI checks passed")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as exc:
        print(f"FAILED: {' '.join(map(str, exc.cmd))} (exit {exc.returncode})")
        sys.exit(1)
