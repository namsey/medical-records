"""Copy the live SQLite database consistently while the app keeps running (SQLite's online backup API).

    python3 snapshot_db.py <live database> <copy>

The copy has no login sessions, is readable by its owner only and must pass SQLite's integrity check.
Only the standard library is used, so this runs with any Python 3 on the server.
"""

import os
import sqlite3
import sys
from pathlib import Path


def snapshot(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise SystemExit(f"Database not found: {source}")
    destination.unlink(missing_ok=True)
    live = sqlite3.connect(source, timeout=30)
    copy = sqlite3.connect(destination)
    try:
        live.backup(copy)
        # A restore signs everyone out: login sessions never go into a backup.
        copy.execute("DELETE FROM sessions")
        copy.commit()
        result = copy.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise SystemExit("The database copy failed SQLite's integrity check")
    finally:
        copy.close()
        live.close()
    os.chmod(destination, 0o600)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    snapshot(Path(sys.argv[1]), Path(sys.argv[2]))
