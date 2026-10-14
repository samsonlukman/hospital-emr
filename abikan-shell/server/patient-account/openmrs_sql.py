"""Read-only OpenMRS MySQL access for Hospital Admin aggregations.

This is not a second analytics store. Queries run against the installed
OpenMRS database with parameterized SQL and Africa/Lagos UTC bounds supplied
by the caller.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

VENDOR = Path(__file__).resolve().parent / "vendor"
if VENDOR.is_dir() and str(VENDOR) not in sys.path:
    sys.path.insert(0, str(VENDOR))

from server import ApiError

DB_HOST = os.environ.get("ABIKAN_OPENMRS_DB_HOST", "").strip()
DB_NAME = os.environ.get("ABIKAN_OPENMRS_DB_NAME", "openmrs").strip() or "openmrs"
DB_USER = os.environ.get("ABIKAN_OPENMRS_DB_USER", "").strip()
DB_PASSWORD = os.environ.get("ABIKAN_OPENMRS_DB_PASSWORD", "")
DB_PORT = int(os.environ.get("ABIKAN_OPENMRS_DB_PORT", "3306") or "3306")


class OpenmrsSqlError(RuntimeError):
    """OpenMRS SQL is not configured or failed. Callers map this to Unavailable."""


def sql_configured() -> bool:
    return bool(DB_HOST and DB_USER)


def _connect() -> Any:
    if not sql_configured():
        raise OpenmrsSqlError("not_configured")
    try:
        import pymysql
    except ImportError as error:
        raise OpenmrsSqlError("driver_missing") from error
    try:
        return pymysql.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.Cursor,
            connect_timeout=8,
            read_timeout=20,
            write_timeout=8,
        )
    except Exception as error:
        raise OpenmrsSqlError("connect_failed") from error


def fetch_one(sql: str, params: tuple[Any, ...] = ()) -> tuple[Any, ...] | None:
    connection = _connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            row = cursor.fetchone()
            return tuple(row) if row else None
    except OpenmrsSqlError:
        raise
    except Exception as error:
        raise OpenmrsSqlError("query_failed") from error
    finally:
        connection.close()


def fetch_int(sql: str, params: tuple[Any, ...] = ()) -> int:
    row = fetch_one(sql, params)
    if not row or row[0] is None:
        return 0
    return int(row[0])


def fetch_all(sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    connection = _connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            return [tuple(row) for row in cursor.fetchall()]
    except OpenmrsSqlError:
        raise
    except Exception as error:
        raise OpenmrsSqlError("query_failed") from error
    finally:
        connection.close()


def execute(sql: str, params: tuple[Any, ...] = ()) -> int:
    connection = _connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            connection.commit()
            return int(cursor.rowcount)
    except OpenmrsSqlError:
        raise
    except Exception as error:
        raise OpenmrsSqlError("query_failed") from error
    finally:
        connection.close()


def unavailable_error() -> ApiError:
    return ApiError(
        503,
        "records_unavailable",
        "Hospital records are temporarily unavailable.",
    )
