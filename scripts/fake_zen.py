"""Stand-in for ZEN during development: a process the watchdog can detect.

The AFTER_SCOPE_FAKE_ZEN marker in the command line is what the simulate config's
zen.cmdline_contains matches. Quit with Ctrl+C ("closing ZEN").
"""

import sys
import time

MARKER = "AFTER_SCOPE_FAKE_ZEN"

if __name__ == "__main__":
    print(f"fake ZEN running (pid marker: {MARKER}) — Ctrl+C to 'close ZEN'")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("fake ZEN closing")
        sys.exit(0)
