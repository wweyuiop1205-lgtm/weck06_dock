"""Dry-run a non-demo SQLite upgrade on an isolated copy inside Docker."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile


BUSINESS_TABLES = (
    "suppliers", "purchase_orders", "purchase_order_items", "inventory",
    "supply_chain_events", "supply_chain_news", "decision_records",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _check(conn: sqlite3.Connection) -> None:
    if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
        raise RuntimeError("SQLite quick_check failed")


def _counts(conn: sqlite3.Connection, selected: tuple[str, ...] = BUSINESS_TABLES) -> dict[str, int]:
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    return {table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in selected if table in tables}


def _business_digests(conn: sqlite3.Connection, columns_by_table: dict[str, tuple[str, ...]]) -> dict[str, str]:
    """Compare existing values, ignoring columns added by the migration itself."""
    digests = {}
    for table, columns in columns_by_table.items():
        quoted = ",".join('"' + column.replace('"', '""') + '"' for column in columns)
        digest = hashlib.sha256()
        cursor = conn.execute(f'SELECT {quoted} FROM "{table}" ORDER BY rowid')
        for row in cursor:
            digest.update(repr(tuple(row)).encode("utf-8"))
            digest.update(b"\n")
        digests[table] = digest.hexdigest()
    return digests


def probe(source: Path, organization_id: str = "", *,
          backup_root: Path = Path("/backups"), work_root: Path = Path("/tmp/erp-probe")) -> dict:
    source = source.resolve(strict=True)
    backup_root = backup_root.resolve(strict=True)
    work_root = work_root.resolve(strict=True)
    if backup_root not in source.parents or source.suffix != ".db":
        raise ValueError("只能檢查 /backups 內的 .db 備份檔")
    if any(source.with_name(source.name + suffix).exists() for suffix in ("-wal", "-shm")):
        raise ValueError("備份旁仍有 SQLite WAL／SHM；請先產生完整的單檔備份")
    before_hash = _sha256(source)
    with tempfile.TemporaryDirectory(prefix="upgrade-", dir=work_root) as directory:
        target = Path(directory) / "erp.db"
        with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as original:
            _check(original)
            counts_before = _counts(original)
            columns_before = {
                table: tuple(row[1] for row in original.execute(f"PRAGMA table_info({table})"))
                for table in counts_before
            }
            digests_before = _business_digests(original, columns_before)
            with sqlite3.connect(target) as copy:
                original.backup(copy)
        if _sha256(source) != before_hash:
            raise RuntimeError("來源備份檔在複製期間改變")
        from backend import database
        keys = ("ERP_DB_PATH", "ERP_DEMO_MODE", "ERP_ENABLE_DEMO_SEED", "ERP_ORGANIZATION_ID")
        previous_env = {key: os.environ.get(key) for key in keys}
        previous_db_file = database.DB_FILE
        try:
            os.environ["ERP_DB_PATH"] = str(target)
            os.environ["ERP_DEMO_MODE"] = "false"
            os.environ["ERP_ENABLE_DEMO_SEED"] = "false"
            if organization_id:
                os.environ["ERP_ORGANIZATION_ID"] = organization_id
            else:
                os.environ.pop("ERP_ORGANIZATION_ID", None)
            database.DB_FILE = str(target)
            database.init_db()
        finally:
            database.DB_FILE = previous_db_file
            for key, value in previous_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        with sqlite3.connect(target) as upgraded:
            _check(upgraded)
            violations = upgraded.execute("PRAGMA foreign_key_check").fetchall()
            if violations:
                raise RuntimeError(f"Foreign key violations after migration: {len(violations)}")
            counts_after = _counts(upgraded, tuple(counts_before))
            if counts_after != counts_before:
                raise RuntimeError(f"Business row counts changed: {counts_before} -> {counts_after}")
            digests_after = _business_digests(upgraded, columns_before)
            changed = [table for table in columns_before if digests_after[table] != digests_before[table]]
            if changed:
                raise RuntimeError(f"Existing business values changed during migration: {', '.join(changed)}")
            for table in ("news_review_actions", "risk_event_retractions", "what_if_erp_snapshots", "decision_evidence_snapshots"):
                if upgraded.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is None:
                    raise RuntimeError(f"Missing migrated table: {table}")
            upgraded.execute("SELECT review_status,analysis_status,fetched_at FROM supply_chain_news LIMIT 1").fetchall()
        if _sha256(source) != before_hash:
            raise RuntimeError("來源備份檔在演練期間改變")
    return {"status": "ok", "source_sha256": before_hash, "business_counts": counts_after,
            "business_digests": digests_after,
            "source_unchanged": True}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="Read-only /backups/*.db copy")
    parser.add_argument("--organization-id", default="", help="Required for an unbound existing non-demo database")
    args = parser.parse_args()
    print(json.dumps(probe(args.source, args.organization_id), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
