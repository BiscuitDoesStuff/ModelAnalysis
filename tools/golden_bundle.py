"""Replay the synthetic golden fixture into OUT and print the bundle path (offline).

Used by the CI a11y job and for local screenshots:
    python -B tools/golden_bundle.py <out-dir>
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ci import FIXTURES, replay  # noqa: E402


def main(argv):
    if len(argv) != 1:
        print(__doc__)
        return 2
    out = Path(argv[0]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    print(replay(FIXTURES / "golden_snapshot.json", out, quiet=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
