"""SQLite online backup and explicit offline restore from Docker containers."""

from datetime import datetime, timezone
from pathlib import Path
import argparse
import os
import sqlite3
from uuid import uuid4

from backend import database


BACKUP_DIR = Path("/backups")


def _verified(path: Path) -> None:
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
        if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise RuntimeError(f"SQLite integrity check failed: {path.name}")


def backup() -> Path:
    source = Path(database.DB_FILE)
    if not source.is_file():
        raise FileNotFoundError(f"Database not found: {source}")
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = BACKUP_DIR / f"erp-{stamp}-{uuid4().hex[:8]}.db"
    try:
        with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as src:
            with sqlite3.connect(destination) as dst:
                src.backup(dst)
        _verified(destination)
        destination.chmod(0o600)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    print(f"backup created: {destination}")
    return destination


def restore(name: str) -> None:
    if os.getenv("ERP_ALLOW_RESTORE") != "I_UNDERSTAND":
        raise RuntimeError("Set ERP_ALLOW_RESTORE=I_UNDERSTAND after stopping API and web")
    if Path(name).name != name or not name.endswith(".db"):
        raise ValueError("Supply a backup filename within /backups")
    source = BACKUP_DIR / name
    if not source.is_file():
        raise FileNotFoundError(source)
    _verified(source)
    target = Path(database.DB_FILE)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        backup()
    with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as src:
        with sqlite3.connect(target) as dst:
            src.backup(dst)
    _verified(target)
    print(f"restored: {source.name} -> {target}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("backup", "restore", "verify"))
    parser.add_argument("name", nargs="?")
    args = parser.parse_args()
    if args.action == "backup":
        backup()
    elif args.action == "verify":
        _verified(Path(database.DB_FILE))
        print("database integrity: ok")
    else:
        if not args.name:
            parser.error("restore requires a backup filename")
        restore(args.name)


if __name__ == "__main__":
    main()
