"""Check a restored backup folder (database/medical_records.db and files/) and print a short report.

    python3 verify_backup.py <restored folder> [--strict]

Exits 1 if the database is damaged or unreadable. With --strict, documents whose file is missing also fail
(a document deleted while the backup ran can legitimately miss its file, so this is a warning by default).
The report only has counts, never record contents.
"""

import sqlite3
import sys
from pathlib import Path


def verify(folder: Path, strict: bool) -> int:
    database = folder / "database" / "medical_records.db"
    files = folder / "files"
    if not database.is_file():
        print(f"FAIL  no database at {database}")
        return 1
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            print("FAIL  the database is damaged (integrity check)")
            return 1
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        counts = {
            table: connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in ("users", "medical_records", "doctors", "labs", "documents")
        }
        documents = connection.execute(
            "SELECT d.stored_filename, d.storage_folder, r.user_id FROM documents d "
            "JOIN medical_records r ON r.id = d.record_id"
        ).fetchall()
    finally:
        connection.close()

    # Documents still marked with an old upload folder never had their file moved (it was already missing).
    expected = {Path(user_id) / name for name, _folder, user_id in documents}
    present = {path.relative_to(files) for path in files.rglob("*") if path.is_file()} if files.is_dir() else set()
    missing = len(expected - present)
    extra = len(present - expected)

    print("OK    database integrity check")
    print(f"      schema revision {revision}")
    print("      " + ", ".join(f"{count} {table}" for table, count in counts.items()))
    print(f"      {len(present)} stored files")
    if extra:
        print(f"NOTE  {extra} stored files have no document (an upload or delete was in progress)")
    if missing:
        print(f"{'FAIL' if strict else 'WARN'}  {missing} documents have no file in the backup")
        return 1 if strict else 0
    print("OK    every document has its file")
    return 0


if __name__ == "__main__":
    arguments = [a for a in sys.argv[1:] if a != "--strict"]
    if len(arguments) != 1:
        raise SystemExit(__doc__)
    sys.exit(verify(Path(arguments[0]), strict="--strict" in sys.argv[1:]))
