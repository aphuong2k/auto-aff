"""
Shopee & Lazada Affiliate Automation - Main FastAPI Server
==========================================================
Tách thành các Router chuyên biệt theo chuẩn FastAPI:
- api/deals_router.py: CRUD deals, loss-leaders, verify freshness, price history
- api/groups_router.py: FB groups CRUD, sync, auto-categorize, health score, feedback monitor
- api/workflow_router.py: Master workflow steps, Closed-Loop Engine, scheduler, workload
- api/outreach_router.py: Social copilot, comment seeding, banner/collage, group posting
- api/analytics_router.py: Health check, statistics, click analytics, commission, subscribers
- api/settings_router.py: System config (.env), FB accounts, vouchers, campaign links, diagnostics
- api/portal_router.py: Consumer deal hub (/deals), deal detail (/deal/{id}), Anti-Ban redirect (/r/{id})
"""

import os
import sys
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from config.settings import (
    BASE_DIR, ALLOWED_ORIGINS, FRESHNESS_CHECK_INTERVAL_HOURS
)

# Import shared dependencies & singletons
from api.deps import (
    db, commission_tracker, closed_loop_engine, deal_collector, category_router,
    system_state, closed_loop_state, scheduler_state, sale_reminder_state,
    gradual_posting_state, mask_secret, load_env_vars, run_orchestrator_worker
)

# Import modular routers
from api.deals_router import router as deals_router, get_deal_image
from api.groups_router import router as groups_router
from api.workflow_router import router as workflow_router
from api.outreach_router import router as outreach_router
from api.analytics_router import router as analytics_router
from api.settings_router import router as settings_router
from api.portal_router import router as portal_router, anti_ban_redirect
from api.hunt_router import router as hunt_router

# Khởi tạo FastAPI App
app = FastAPI(
    title="Shopee & Lazada Affiliate Automation API",
    description="Hệ thống tự động hóa tiếp thị liên kết Shopee & Lazada đa kênh",
    version="2.0.0"
)

# Cấu hình CORS
_allowed_env = os.getenv("ALLOWED_ORIGINS", ALLOWED_ORIGINS)
_origins = [o.strip() for o in _allowed_env.split(",") if o.strip()]
if not _origins:
    _origins = ["http://localhost:4200", "http://127.0.0.1:4200", "http://localhost:8000", "http://127.0.0.1:8000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins if os.getenv("STRICT_CORS") == "true" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include toàn bộ router modules
app.include_router(deals_router)
app.include_router(groups_router)
app.include_router(workflow_router)
app.include_router(outreach_router)
app.include_router(analytics_router)
app.include_router(settings_router)
app.include_router(portal_router)
app.include_router(hunt_router)

# Phục vụ Frontend Admin Dashboard (Angular production build)
frontend_dist = BASE_DIR / "frontend" / "dist" / "frontend" / "browser"
if frontend_dist.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dist)), name="static")

    @app.get("/{full_path:path}")
    def serve_frontend(full_path: str):
        if full_path.startswith("api/") or full_path == "api":
            raise HTTPException(status_code=404, detail="API route not found")
        if full_path in ["deals", "deal", "r"]:
            pass
        target_file = frontend_dist / full_path
        if target_file.is_file():
            return FileResponse(str(target_file))
        return FileResponse(str(frontend_dist / "index.html"))


# --- Background Scheduler Thread (Quét deal định kỳ, nhắc Flash Sale & độ tươi) ---
def _scheduler_loop():
    _scheduler_loop.last_freshness_check = datetime.now()
    while True:
        try:
            now = datetime.now()
            current_hm = now.strftime("%H:%M")
            today_str = now.strftime("%Y-%m-%d")

            # 1. Quét deal tự động theo lịch hẹn nếu BẬT
            if scheduler_state["enabled"]:
                if current_hm == scheduler_state["time"]:
                    if scheduler_state["last_scheduled_run"] != today_str:
                        if not system_state["is_running"]:
                            scheduler_state["last_scheduled_run"] = today_str
                            print(f"⏰ [AUTO SCHEDULER]: Đến giờ chạy tự động ({scheduler_state['time']}). Đang khởi chạy chu trình...")
                            threading.Thread(target=closed_loop_engine.run_full_cycle, daemon=True).start()

            # 2. Hẹn giờ nhắc Flash Sale & Khuyến mại
            if sale_reminder_state["enabled"]:
                from modules.crawler.promotion_hunter import PromotionHunter
                from modules.publisher.telegram_bot import TelegramPublisher
                from modules.affiliate.content_writer import DealContentWriter
                hunter = PromotionHunter(db)
                for slot in sale_reminder_state["slots"]:
                    if hunter.is_time_for_reminder(slot, sale_reminder_state["remind_before_minutes"], now):
                        if not db.is_sale_reminder_sent(slot, today_str, target="TELEGRAM"):
                            print(f"⏰ Đến thời điểm bắn bài nhắc Flash Sale khung {slot}...")
                            package = hunter.get_today_promotion_package(target_slot=slot)
                            publisher = TelegramPublisher(db=db)
                            publisher.publish_sale_reminder(package)
                            content = DealContentWriter.generate_sale_reminder_post(package)
                            db.log_sale_reminder(slot, today_str, content, target="TELEGRAM")

            # 3. Quét kiểm tra độ tươi mỗi 2 giờ
            if (now - _scheduler_loop.last_freshness_check).total_seconds() > (FRESHNESS_CHECK_INTERVAL_HOURS * 3600):
                _scheduler_loop.last_freshness_check = now
                def _run_freshness():
                    try:
                        from modules.crawler.deal_freshness_checker import DealFreshnessChecker
                        print("🔍 [FRESHNESS CHECKER]: Đang chạy kiểm tra định kỳ độ tươi các deal đang hoạt động...")
                        DealFreshnessChecker(db).check_all_active_deals(max_deals=40)
                    except Exception as fe:
                        print(f"Lỗi kiểm tra độ tươi định kỳ: {fe}")
                threading.Thread(target=_run_freshness, daemon=True).start()

        except Exception as e:
            print(f"Lỗi trong scheduler loop: {e}")
        time.sleep(30)


# Khởi chạy Scheduler thread trong nền
threading.Thread(target=_scheduler_loop, daemon=True).start()

if __name__ == "__main__":
    import uvicorn
    print("\n" + "=" * 60)
    print("🚀 Auto-Affiliate Automation API Server v2.0")
    print("🌐 Dashboard UI:    http://127.0.0.1:8000")
    print("📖 API Swagger:    http://127.0.0.1:8000/docs")
    print("🛍️ Deal Hub:       http://127.0.0.1:8000/deals")
    print("=" * 60 + "\n")
    uvicorn.run("api_server:app", host="127.0.0.1", port=8000, reload=True)
