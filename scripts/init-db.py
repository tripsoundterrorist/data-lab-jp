from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "db" / "schema.sql"
DATABASE_PATH = ROOT / "data" / "data-lab.db"


def safe_error(summary: str) -> None:
    print(f"Error: {summary}", file=sys.stderr)


def main() -> int:
    if DATABASE_PATH.exists():
        print("Database already exists; initialization skipped.")
        return 0

    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(DATABASE_PATH)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
            raise RuntimeError("Foreign keys were not enabled.")
        connection.commit()
    except Exception:
        if connection is not None:
            connection.close()
            connection = None
        DATABASE_PATH.unlink(missing_ok=True)
        safe_error("Database initialization failed.")
        return 1
    finally:
        if connection is not None:
            connection.close()

    print("Database initialization completed successfully.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        safe_error("Unexpected database initialization failure.")
        raise SystemExit(1)
