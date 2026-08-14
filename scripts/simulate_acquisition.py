"""Drip synthesized CZI files into the simulate watch directory.

Usage:
    python scripts/simulate_acquisition.py [watch_dir] [count] [interval_seconds]
    python scripts/simulate_acquisition.py --dust [watch_dir]   # drop a dust reference
"""

from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from make_fixture_czi import make_fixture_czi  # noqa: E402  (same directory)

DEFAULT_WATCH = Path.home() / "after_scope_sim" / "scratch"


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dust = "--dust" in sys.argv
    watch = Path(args[0]) if args else DEFAULT_WATCH
    watch.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%H%M%S")
    if dust:
        dest = make_fixture_czi(watch / f"dustref_{stamp}.czi", channels=1)
        print(f"dust reference: {dest}")
        return
    count = int(args[1]) if len(args) > 1 else 3
    interval = float(args[2]) if len(args) > 2 else 5.0
    for i in range(count):
        dest = make_fixture_czi(watch / f"Snap_{stamp}_{i + 1}.czi")
        print(f"acquired: {dest}")
        if i < count - 1:
            time.sleep(interval)


if __name__ == "__main__":
    main()
