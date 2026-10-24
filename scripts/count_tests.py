"""Print the real number of collected tests. Used by render_docs.py and CI.

python scripts/count_tests.py      ->  "tests: 192"
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def count() -> int:
    out = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    m = re.search(r"^(\d+) tests? collected", out, re.M)
    if not m:
        raise SystemExit(f"could not read test count from pytest output:\n{out[-500:]}")
    return int(m.group(1))


if __name__ == "__main__":
    print(f"tests: {count()}")
