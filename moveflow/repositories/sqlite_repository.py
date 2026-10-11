import sqlite3
from collections.abc import Collection, Iterator
from contextlib import contextmanager
from pathlib import Path

from moveflow.domain.enums import RequestStatus
from moveflow.domain.models import MoveRequest

_SCHEMA = """
CREATE TABLE IF NOT EXISTS move_requests (
    id           TEXT PRIMARY KEY,
    community_id TEXT NOT NULL,
    status       TEXT NOT NULL,
    phone        TEXT,
    updated_at   TEXT NOT NULL,
    payload      TEXT NOT NULL
)
"""


class SqliteRequestRepository:
    """Stores each request as a JSON document, with a few columns for filtering.

    The answers a request carries differ per community, so a document-style row
    avoids schema migrations whenever a community adds a field.
    """

    def __init__(self, db_path: Path):
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(_SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._db_path)
        try:
            with conn:  # commits on success, rolls back on error
                yield conn
        finally:
            conn.close()

    def save(self, request: MoveRequest) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO move_requests (id, community_id, status, phone, updated_at, payload)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status = excluded.status,
                    phone = excluded.phone,
                    updated_at = excluded.updated_at,
                    payload = excluded.payload
                """,
                (
                    request.id,
                    request.community_id,
                    request.status.value,
                    request.phone,
                    request.updated_at.isoformat(),
                    request.model_dump_json(),
                ),
            )

    def get(self, request_id: str) -> MoveRequest | None:
        with self._connect() as conn:
            row = conn.execute("SELECT payload FROM move_requests WHERE id = ?", (request_id,)).fetchone()
        return MoveRequest.model_validate_json(row[0]) if row else None

    def list(
        self,
        community_id: str | None = None,
        statuses: Collection[RequestStatus] | None = None,
    ) -> list[MoveRequest]:
        query = "SELECT payload FROM move_requests WHERE 1 = 1"
        params: list[str] = []
        if community_id is not None:
            query += " AND community_id = ?"
            params.append(community_id)
        if statuses is not None:
            query += f" AND status IN ({', '.join('?' for _ in statuses)})"
            params.extend(status.value for status in statuses)
        query += " ORDER BY updated_at DESC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [MoveRequest.model_validate_json(row[0]) for row in rows]

    def list_for_resident(self, community_id: str, phone: str) -> list[MoveRequest]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM move_requests WHERE community_id = ? AND phone = ? ORDER BY updated_at DESC",
                (community_id, phone),
            ).fetchall()
        return [MoveRequest.model_validate_json(row[0]) for row in rows]

    def count(self) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM move_requests").fetchone()[0]
