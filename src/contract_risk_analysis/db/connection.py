"""MySQL connection management — reads config from .env."""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Generator

import pymysql
from dotenv import load_dotenv

load_dotenv()


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


DB_CONFIG = {
    "host": _env("MYSQL_HOST", "localhost"),
    "port": int(_env("MYSQL_PORT", "3306")),
    "user": _env("MYSQL_USER", "root"),
    "password": _env("MYSQL_PASSWORD", ""),
    "database": _env("MYSQL_DATABASE", "contract_risk"),
    "charset": "utf8mb4",
    "autocommit": True,
}


@contextmanager
def get_connection() -> Generator[pymysql.Connection, None, None]:
    """Yield a MySQL connection (auto-close on exit)."""
    conn = pymysql.connect(**DB_CONFIG)
    try:
        yield conn
    finally:
        conn.close()
