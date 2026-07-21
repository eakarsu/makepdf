"""Online SQLite backup and offline restore-integrity verification."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import time
from pathlib import Path

from makepdf.config import JOB_DB_PATH

REQUIRED_TABLES = {
    "api_keys", "audit_events", "billing_exports", "documents", "jobs",
    "usage_daily", "worker_heartbeats",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_database(path: str | Path) -> dict:
    database = Path(path)
    if not database.is_file():
        raise ValueError(f"Database not found: {database}")
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise ValueError(f"SQLite integrity check failed: {integrity}")
        tables = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        missing = REQUIRED_TABLES - tables
        if missing:
            raise ValueError(f"Backup is missing tables: {', '.join(sorted(missing))}")
        previous = "0" * 64
        audit_count = 0
        for row in connection.execute("SELECT * FROM audit_events ORDER BY sequence"):
            if row["previous_hash"] != previous:
                raise ValueError(f"Audit chain break at sequence {row['sequence']}")
            material = "|".join(
                (
                    previous,
                    row["tenant_id"],
                    row["user_id"],
                    row["action"],
                    row["resource_type"],
                    row["resource_id"],
                    row["details_json"],
                    str(row["created_at"]),
                )
            )
            expected = hashlib.sha256(material.encode()).hexdigest()
            if expected != row["event_hash"]:
                raise ValueError(f"Audit digest mismatch at sequence {row['sequence']}")
            previous = expected
            audit_count += 1
        return {
            "sha256": _sha256(database),
            "tables": len(tables),
            "audit_events": audit_count,
            "integrity": "ok",
        }
    finally:
        connection.close()


def backup_database(destination: str | Path, source: str | Path = JOB_DB_PATH) -> dict:
    source_path = Path(source)
    destination_path = Path(destination)
    if not source_path.is_file():
        raise ValueError(f"Source database not found: {source_path}")
    destination_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if destination_path.exists():
        raise ValueError("Refusing to overwrite an existing backup")
    source_db = sqlite3.connect(source_path)
    target_db = sqlite3.connect(destination_path)
    try:
        source_db.execute("PRAGMA wal_checkpoint(FULL)")
        source_db.backup(target_db)
    finally:
        target_db.close()
        source_db.close()
    destination_path.chmod(0o600)
    report = verify_database(destination_path) | {
        "source": str(source_path),
        "created_at": time.time(),
    }
    manifest = destination_path.with_suffix(destination_path.suffix + ".manifest.json")
    manifest.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    manifest.chmod(0o600)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    subcommands = parser.add_subparsers(dest="command", required=True)
    backup = subcommands.add_parser("backup")
    backup.add_argument("destination")
    backup.add_argument("--source", default=str(JOB_DB_PATH))
    verify = subcommands.add_parser("verify")
    verify.add_argument("database")
    args = parser.parse_args()
    report = (
        backup_database(args.destination, args.source)
        if args.command == "backup"
        else verify_database(args.database)
    )
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
