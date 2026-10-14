"""Keep pharmacy-added medicines on the doctor's prescription."""

from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path
from typing import Any

DB_PATH = os.environ.get(
    "ABIKAN_PHARMACY_UNLISTED_DB",
    os.environ.get("ABIKAN_NOTIFICATIONS_DB", "/var/lib/abikan/notifications.sqlite3"),
)
LOCK = threading.Lock()

CREATE_STATEMENT = """
    CREATE TABLE IF NOT EXISTS pharmacy_rx_link (
        order_uuid TEXT PRIMARY KEY,
        group_key TEXT NOT NULL,
        replaced_by TEXT NOT NULL DEFAULT ''
    )
"""


def _connect(path: str | None = None) -> sqlite3.Connection:
    db_path = Path(path or DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(db_path), timeout=10)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute(CREATE_STATEMENT)
    columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(pharmacy_rx_link)")}
    if "replaced_by" not in columns:
        connection.execute(
            "ALTER TABLE pharmacy_rx_link ADD COLUMN replaced_by TEXT NOT NULL DEFAULT ''"
        )
    return connection


def reset_for_tests(path: str) -> None:
    global DB_PATH
    DB_PATH = path
    with LOCK:
        connection = _connect(path)
        try:
            connection.execute("DROP TABLE IF EXISTS pharmacy_rx_link")
            connection.execute(CREATE_STATEMENT)
            connection.commit()
        finally:
            connection.close()


def remember(order_uuid: str, group_key: str) -> None:
    order = str(order_uuid or "").strip()
    group = str(group_key or "").strip()
    if not order or not group or order == group:
        return
    try:
        with LOCK:
            connection = _connect()
            try:
                connection.execute(
                    """
                    INSERT INTO pharmacy_rx_link (order_uuid, group_key, replaced_by)
                    VALUES (?, ?, '')
                    ON CONFLICT(order_uuid) DO UPDATE SET
                        group_key=excluded.group_key
                    """,
                    (order, group),
                )
                connection.commit()
            finally:
                connection.close()
    except (OSError, sqlite3.Error):
        return


def replace(old_uuid: str, new_uuid: str, group_key: str) -> None:
    old = str(old_uuid or "").strip()
    new = str(new_uuid or "").strip()
    group = str(group_key or "").strip()
    if not old or not new or not group:
        return
    with LOCK:
        connection = _connect()
        try:
            connection.execute(
                """
                INSERT INTO pharmacy_rx_link (order_uuid, group_key, replaced_by)
                VALUES (?, ?, ?)
                ON CONFLICT(order_uuid) DO UPDATE SET
                    group_key=excluded.group_key,
                    replaced_by=excluded.replaced_by
                """,
                (old, group, new),
            )
            connection.execute(
                """
                INSERT INTO pharmacy_rx_link (order_uuid, group_key, replaced_by)
                VALUES (?, ?, '')
                ON CONFLICT(order_uuid) DO UPDATE SET
                    group_key=excluded.group_key,
                    replaced_by=''
                """,
                (new, group),
            )
            connection.commit()
        finally:
            connection.close()


def _rows(query: str, params: tuple[Any, ...]) -> list[tuple[Any, ...]]:
    try:
        with LOCK:
            connection = _connect()
            try:
                return list(connection.execute(query, params).fetchall())
            finally:
                connection.close()
    except (OSError, sqlite3.Error):
        return []


def group_for(order_uuid: str) -> str:
    order = str(order_uuid or "").strip()
    if not order:
        return ""
    rows = _rows("SELECT group_key FROM pharmacy_rx_link WHERE order_uuid = ?", (order,))
    return str(rows[0][0] or "") if rows else ""


def resolve(order_uuid: str) -> str:
    current = str(order_uuid or "").strip()
    seen: set[str] = set()
    while current and current not in seen:
        seen.add(current)
        rows = _rows("SELECT replaced_by FROM pharmacy_rx_link WHERE order_uuid = ?", (current,))
        nxt = str(rows[0][0] or "").strip() if rows else ""
        if not nxt:
            return current
        current = nxt
    return str(order_uuid or "").strip()


def members(group_key: str) -> list[str]:
    group = str(group_key or "").strip()
    if not group:
        return []
    rows = _rows(
        """
        SELECT order_uuid FROM pharmacy_rx_link
        WHERE group_key = ? AND replaced_by = ''
        ORDER BY rowid
        """,
        (group,),
    )
    return [str(row[0]) for row in rows if row and row[0]]
