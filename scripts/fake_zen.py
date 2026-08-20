"""Stand-in for ZEN during development: a process the watchdog can detect.

The watchdog matches zen.cmdline_contains against the process command line, so the
AFTER_SCOPE_FAKE_ZEN marker must appear in argv — this script re-launches itself
with the marker appended when started plain (`python scripts/fake_zen.py`).
Quit with Ctrl+C ("closing ZEN").
"""

import os
import subprocess
import sys
import time

MARKER = "AFTER_SCOPE_FAKE_ZEN"

if __name__ == "__main__":
    if MARKER not in " ".join(sys.argv):
        child = subprocess.Popen(
            [sys.executable, os.path.abspath(__file__), MARKER]
        )
        try:
            sys.exit(child.wait())
        except KeyboardInterrupt:
            sys.exit(child.wait())
    print(f"fake ZEN running (cmdline marker: {MARKER}) — Ctrl+C to 'close ZEN'")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("fake ZEN closing")
        sys.exit(0)
