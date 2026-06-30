"""
scan_apps.py  –  B.M.O app indexer
────────────────────────────────────
Walks the D:\\ drive, collects every .exe it can reach, and writes the
full paths to app_index.txt (one path per line), sorted alphabetically.

Run this once (or whenever you install new software on D:\\):
    python scan_apps.py

main.py will read app_index.txt at runtime — no live D:\\ scan needed.

Skipped directories (too noisy / never contain launchable apps):
    $Recycle.Bin, System Volume Information, Windows, Config.Msi,
    Recovery, PerfLogs — adjust SKIP_DIRS below if needed.
"""

import os
import sys
import time

# ── Configuration ─────────────────────────────────────────────────────────────

SCAN_DRIVE   = "D:\\"
OUTPUT_FILE  = "app_index.txt"     # written next to scan_apps.py

SKIP_DIRS: set[str] = {
    "$recycle.bin",
    "system volume information",
    "config.msi",
    "recovery",
    "perflogs",
    "windows",           # unlikely on D:\\ but just in case
}

# ── Scanner ───────────────────────────────────────────────────────────────────

def scan(drive: str = SCAN_DRIVE) -> list[str]:
    """Return a sorted list of all .exe paths found under *drive*."""
    found: list[str] = []
    skipped_dirs = 0
    errors       = 0

    print(f"Scanning {drive} for .exe files …", flush=True)
    print("(This may take a minute on a large drive)\n", flush=True)

    for root, dirs, files in os.walk(drive, topdown=True):
        # ── Prune skip-listed directories in-place ────────────────────────────
        dirs[:] = [
            d for d in dirs
            if d.lower() not in SKIP_DIRS
        ]

        for filename in files:
            if filename.lower().endswith(".exe"):
                found.append(os.path.join(root, filename))

    return sorted(found, key=str.lower)


def write_index(paths: list[str], output: str = OUTPUT_FILE) -> None:
    """Write *paths* to *output*, one per line."""
    with open(output, "w", encoding="utf-8") as f:
        f.write("\n".join(paths))
        if paths:
            f.write("\n")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not os.path.isdir(SCAN_DRIVE):
        print(f"[scan_apps] ERROR: Drive '{SCAN_DRIVE}' not found.", file=sys.stderr)
        sys.exit(1)

    t0    = time.perf_counter()
    paths = scan(SCAN_DRIVE)
    elapsed = time.perf_counter() - t0

    write_index(paths)

    print(f"Found  : {len(paths):,} .exe files")
    print(f"Saved  : {os.path.abspath(OUTPUT_FILE)}")
    print(f"Time   : {elapsed:.1f}s")
    print("\nDone. Re-run this script after installing new software on D:\\.")