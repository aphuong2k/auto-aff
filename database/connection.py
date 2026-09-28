"""
Database Connection & Base Repository
======================================
Cung cấp Connection Factory chuẩn SQLite với:
- WAL Mode (Write-Ahead Logging) cho concurrency cao
- Timeout 10,000ms chống Database Locked
- Row Factory sqlite3.Row cho phép truy cập theo tên cột
"""

import sqlite3
from pathlib import Path
from typing import Union
from config.settings import DB_PATH


def create_connection(db_path: Union[str, Path] = DB_PATH) -> sqlite3.Connection:
    """Tạo kết nối SQLite an toàn với WAL mode và timeout"""
    conn = sqlite3.connect(str(db_path), timeout=10.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # Kích hoạt WAL mode và busy timeout để nhiều tiến trình đọc/ghi đồng thời không bị lock
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA wal_autocheckpoint=100")
    except sqlite3.Error:
        pass
    return conn


class BaseRepository:
    """Lớp cơ sở cho tất cả Repository modules"""

    def __init__(self, db_path: Union[str, Path] = DB_PATH):
        self.db_path = str(db_path)

    def get_connection(self) -> sqlite3.Connection:
        """Lấy một kết nối mới tới database SQLite"""
        return create_connection(self.db_path)
