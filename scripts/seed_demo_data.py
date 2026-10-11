"""Resets the local database and loads the demo requests.

Usage: python scripts/seed_demo_data.py
"""

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from moveflow.demo.seed import seed_demo_data  # noqa: E402
from moveflow.repositories.sqlite_repository import SqliteRequestRepository  # noqa: E402

DB_PATH = ROOT / "data" / "moveflow.db"

if __name__ == "__main__":
    DB_PATH.unlink(missing_ok=True)
    repository = SqliteRequestRepository(DB_PATH)
    seed_demo_data(repository, date.today())
    print(f"Seeded {repository.count()} demo requests into {DB_PATH}")
