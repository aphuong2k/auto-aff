"""
Database Manager - Master Facade
================================
Hệ thống quản lý cơ sở dữ liệu SQLite cho Affiliate Automation.
Tách thành các Repository chuyên biệt theo Repository Pattern:
- database/connection.py: Connection Factory (WAL mode, busy timeout 10s)
- database/migrations.py: Khởi tạo bảng & ALTER TABLE migrations tự động
- database/deal_repo.py: DealRepository (CRUD deals, phân loại, media, giá, freshness)
- database/group_repo.py: GroupRepository (FB Groups, Health score, Anti-dup, Posted logs, Seeding)
- database/account_repo.py: AccountRepository (Multi-account rotation, Workload balancer, Cooldown)
- database/analytics_repo.py: AnalyticsRepository (Click tracking, Đối soát hoa hồng, Subscribers, Vouchers, Settings)
- database/workflow_repo.py: WorkflowRepository (Categories, Learned keywords, Promotions, Cycles, Reports)

Lớp DatabaseManager kế thừa toàn bộ 5 repository trên để đảm bảo 100% tính tương thích ngược (Backward Compatibility).
"""

from pathlib import Path
from typing import Union

from config.settings import DB_PATH
from database.connection import BaseRepository, create_connection
from database.migrations import init_db as run_schema_migrations
from database.deal_repo import DealRepository
from database.group_repo import GroupRepository
from database.account_repo import AccountRepository
from database.analytics_repo import AnalyticsRepository
from database.workflow_repo import WorkflowRepository
from database.deal_hunter_repo import DealHunterRepository


class DatabaseManager(
    DealRepository,
    GroupRepository,
    AccountRepository,
    AnalyticsRepository,
    WorkflowRepository,
    DealHunterRepository
):
    """
    Master Database Manager Facade
    ==============================
    Cung cấp toàn bộ 88+ phương thức truy vấn và cập nhật dữ liệu của hệ thống,
    tương thích hoàn toàn với tất cả module hiện hữu.
    """

    def __init__(self, db_path: Union[str, Path] = DB_PATH):
        BaseRepository.__init__(self, db_path=db_path)
        self.init_db()

    def init_db(self):
        """Khởi tạo toàn bộ cấu trúc bảng SQLite và chạy migrations nếu cần.
        Tự động kích hoạt cơ chế phục hồi nếu phát hiện database disk image is malformed.
        """
        import sqlite3
        try:
            with self.get_connection() as conn:
                run_schema_migrations(conn)
        except sqlite3.DatabaseError as e:
            if "malformed" in str(e).lower():
                import logging
                logging.getLogger("DatabaseManager").warning(
                    f"[AUTO-REPAIR] Phát hiện Database bị hỏng ({e}). Đang tự động phục hồi dữ liệu..."
                )
                from scripts.repair_database import repair_database
                if repair_database(self.db_path):
                    with self.get_connection() as conn:
                        run_schema_migrations(conn)
                else:
                    raise
            else:
                raise
