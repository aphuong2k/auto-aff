"""
Shared Dependencies, Singletons, and Runtime States for API Routers
===================================================================
"""

import os
import threading
from datetime import datetime
from typing import Optional, List, Dict, Any

from config.settings import (
    BASE_DIR, LOG_FILE_PATH, RAW_IMAGES_DIR, PROCESSED_IMAGES_DIR,
    MIN_RATING_STAR, MIN_HISTORICAL_SOLD, MIN_DISCOUNT_PERCENT,
    MAX_GROUPS_TO_JOIN_PER_DAY, TOP_DEALS_PER_CATEGORY,
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    SHOPEE_APP_ID, SHOPEE_SECRET, SHOPEE_AFF_COOKIE,
    LAZADA_APP_KEY, LAZADA_APP_SECRET, LAZADA_AFF_COOKIE, LAZADA_TRACKING_URL,
    API_ADMIN_KEY, ALLOWED_ORIGINS, FRESHNESS_CHECK_INTERVAL_HOURS
)
from database.db_manager import DatabaseManager
from modules.affiliate.commission_tracker import CommissionTracker
from modules.workflow.closed_loop_engine import ClosedLoopEngine
from modules.workflow.deal_collector import DealCollector
from modules.workflow.category_router import CategoryRouter

class _DatabaseProxy:
    """Proxy động ủy quyền các hàm gọi tới api_server.db nếu đã được monkeypatch (trong unit tests),
    hoặc dùng DatabaseManager mặc định."""
    def __getattr__(self, name):
        import sys
        api_mod = sys.modules.get("api_server")
        if api_mod is not None:
            mod_db = getattr(api_mod, "db", None)
            if mod_db is not None and not isinstance(mod_db, _DatabaseProxy):
                return getattr(mod_db, name)
        return getattr(_default_db, name)

# Khởi tạo singletons
_default_db = DatabaseManager()
db: DatabaseManager = _DatabaseProxy()  # type: ignore
commission_tracker = CommissionTracker(db)
closed_loop_engine = ClosedLoopEngine(db)
deal_collector = DealCollector(db)
category_router = CategoryRouter(db)

# Runtime states
system_state: Dict[str, Any] = {
    "is_running": False,
    "last_run_time": None,
    "last_status": "IDLE",
    "last_error": None
}

closed_loop_state: Dict[str, Any] = {
    "is_running": False,
    "current_action": "IDLE",
    "last_result": None,
    "last_error": None
}

default_enabled = db.get_system_setting("auto_schedule_enabled", "false").lower() == "true"
default_time = db.get_system_setting("auto_schedule_time", "08:00")
default_cats = int(db.get_system_setting("auto_schedule_cats", "3"))

scheduler_state: Dict[str, Any] = {
    "enabled": default_enabled,
    "time": default_time,
    "cats": default_cats,
    "last_scheduled_run": datetime.now().strftime("%Y-%m-%d")
}

sale_reminder_state: Dict[str, Any] = {
    "enabled": True,
    "remind_before_minutes": 15,
    "slots": ["00:00", "09:00", "12:00", "15:00", "18:00", "21:00"]
}

gradual_posting_state: Dict[str, Any] = {
    "is_running": False,
    "total_groups": 0,
    "current_index": 0,
    "current_group_name": "",
    "success_count": 0,
    "failed_count": 0,
    "logs": []
}


def mask_secret(val: Optional[str], show_last: int = 4) -> str:
    """Che giấu thông tin nhạy cảm (token, cookie, secret) khi trả về frontend"""
    if not val:
        return ""
    val = val.strip().strip('"')
    if len(val) <= show_last:
        return "•" * len(val)
    return "•" * 8 + val[-show_last:]


def load_env_vars():
    """Nạp các biến môi trường từ file .env"""
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    val = v.strip().strip('"')
                    os.environ[k.strip()] = val


def run_orchestrator_worker(cats: int, run_type: str = "MANUAL_ALL", selected_cat_ids: Optional[List[int]] = None):
    """Worker chạy chu trình 5 bước"""
    from main import AffiliateSystemOrchestrator
    system_state["is_running"] = True
    system_state["last_status"] = "RUNNING"
    system_state["last_error"] = None
    start_time = datetime.now()
    cat_desc = f"{cats} ngành hàng" if not selected_cat_ids else f"{len(selected_cat_ids)} ngành hàng được chọn"
    report_id = db.create_workflow_report(
        run_type=run_type,
        step_name="ALL",
        summary_text=f"Chu trình toàn trình 5 bước ({cat_desc}) - Khởi chạy lúc {start_time.strftime('%H:%M:%S')}"
    )
    load_env_vars()
    try:
        orchestrator = AffiliateSystemOrchestrator()
        orchestrator.run_daily_workflow(max_categories=cats, selected_cat_ids=selected_cat_ids)
        system_state["last_status"] = "COMPLETED"
        end_time = datetime.now()
        dur = (end_time - start_time).total_seconds()
        today_deals = len(db.get_deals(limit=100))
        db.update_workflow_report(
            report_id,
            status="SUCCESS",
            duration_seconds=round(dur, 2),
            deals_scanned=cats * 20,
            deals_saved=today_deals,
            banners_created=today_deals,
            telegram_posts=today_deals,
            fb_posts=0,
            summary_text=f"Hoàn thành chu trình trong {round(dur, 1)}s. Đã quét và chọn {today_deals} top deal đa sàn."
        )
    except Exception as e:
        system_state["last_status"] = "ERROR"
        system_state["last_error"] = str(e)
        end_time = datetime.now()
        dur = (end_time - start_time).total_seconds()
        db.update_workflow_report(
            report_id,
            status="ERROR",
            duration_seconds=round(dur, 2),
            error_message=str(e),
            summary_text=f"Chu trình gặp lỗi: {e}"
        )
    finally:
        system_state["is_running"] = False
        system_state["last_run_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
