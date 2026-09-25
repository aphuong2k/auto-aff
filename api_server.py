import os
import sys
import time
import html as html_escape_module
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

import requests
from fastapi import FastAPI, BackgroundTasks, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from pydantic import BaseModel

from config.settings import (
    BASE_DIR, LOG_FILE_PATH, RAW_IMAGES_DIR, PROCESSED_IMAGES_DIR,
    MIN_RATING_STAR, MIN_HISTORICAL_SOLD, MIN_DISCOUNT_PERCENT,
    MAX_GROUPS_TO_JOIN_PER_DAY, TOP_DEALS_PER_CATEGORY,
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    SHOPEE_APP_ID, SHOPEE_SECRET, SHOPEE_AFF_COOKIE
)
from database.db_manager import DatabaseManager
from main import AffiliateSystemOrchestrator

from modules.crawler.deal_hunter import DealHunter
from modules.crawler.promotion_hunter import PromotionHunter
from modules.crawler.price_history_tracker import PriceHistoryTracker
from modules.publisher.telegram_bot import TelegramPublisher
from modules.affiliate.content_writer import DealContentWriter
from modules.affiliate.image_stamper import ImageBannerStamper
from modules.outreach.fb_group_seeder import FacebookGroupSeeder

from config.settings import (
    LAZADA_APP_KEY, LAZADA_APP_SECRET, LAZADA_AFF_COOKIE, LAZADA_TRACKING_URL,
    API_ADMIN_KEY, ALLOWED_ORIGINS, FRESHNESS_CHECK_INTERVAL_HOURS
)
from modules.crawler.lazada_deal_hunter import LazadaDealHunter
from modules.affiliate.lazada_provider import LazadaAffiliateProvider
from modules.crawler.deal_freshness_checker import DealFreshnessChecker
from modules.affiliate.commission_tracker import CommissionTracker
from modules.portal.deal_hub_renderer import DealHubRenderer
from modules.portal.deal_detail_renderer import DealDetailRenderer

app = FastAPI(title="Shopee & Lazada Affiliate Automation API")

# Cấu hình CORS an toàn
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

db = DatabaseManager()
commission_tracker = CommissionTracker(db)
# Nạp dữ liệu đối soát mẫu ban đầu nếu trống để hiển thị biểu đồ
commission_tracker.seed_initial_demo_commissions()

def mask_secret(val: Optional[str], show_last: int = 4) -> str:
    """Che giấu thông tin nhạy cảm (token, cookie, secret) khi trả về frontend"""
    if not val:
        return ""
    val = val.strip().strip('"')
    if len(val) <= show_last:
        return "•" * len(val)
    return "•" * 8 + val[-show_last:]

# Biến trạng thái runtime
system_state = {
    "is_running": False,
    "last_run_time": None,
    "last_status": "IDLE",
    "last_error": None
}

# Cấu hình Lịch Chạy Quét Deal Hàng Ngày (Scheduler)
# QUY TẮC: Mặc định TẮT (enabled=False). Không tự động quét deal khi khởi động!
# Chỉ khi người dùng chủ động BẬT trên giao diện mới chạy theo giờ cấu hình!
default_enabled = db.get_system_setting("auto_schedule_enabled", "false").lower() == "true"
default_time = db.get_system_setting("auto_schedule_time", "08:00")
default_cats = int(db.get_system_setting("auto_schedule_cats", "3"))

scheduler_state = {
    "enabled": default_enabled,
    "time": default_time,
    "cats": default_cats,
    "last_scheduled_run": datetime.now().strftime("%Y-%m-%d")  # Đánh dấu đã qua hôm nay lúc khởi động để KHÔNG tự động quét deal ngay khi bật server!
}

# Cấu hình Hẹn Giờ Nhắc Flash Sale & Khuyến Mại
sale_reminder_state = {
    "enabled": True,
    "remind_before_minutes": 15,
    "slots": ["00:00", "09:00", "12:00", "15:00", "18:00", "21:00"]
}

class SaleReminderConfigModel(BaseModel):
    enabled: bool
    remind_before_minutes: int

class ConfigModel(BaseModel):
    shopee_app_id: Optional[str] = ""
    shopee_secret: Optional[str] = ""
    shopee_cookie: Optional[str] = ""
    shopee_aff_cookie: Optional[str] = ""
    lazada_app_key: Optional[str] = ""
    lazada_app_secret: Optional[str] = ""
    lazada_aff_cookie: Optional[str] = ""
    lazada_tracking_url: Optional[str] = ""
    telegram_bot_token: Optional[str] = ""
    telegram_chat_id: Optional[str] = ""
    fb_account_cookie: Optional[str] = ""
    fb_chrome_profile_path: Optional[str] = ""
    min_rating_star: Optional[float] = 4.6
    min_historical_sold: Optional[int] = 200
    min_discount_percent: Optional[int] = 15
    max_groups_per_day: Optional[int] = 3
    top_deals_per_category: Optional[int] = 3
    community_invite_url: Optional[str] = ""
    community_name: Optional[str] = "Hội Săn Deal Shopee VIP"
    redirect_mode: Optional[str] = "direct"
    redirect_base_url: Optional[str] = ""
    api_admin_key: Optional[str] = ""

class SubscriberRegisterModel(BaseModel):
    email: str
    telegram_id: Optional[str] = None
    platform_preference: Optional[str] = "ALL"
    category_preference: Optional[str] = "ALL"
    min_discount: Optional[int] = 30

class CommissionImportModel(BaseModel):
    platform: Optional[str] = "SHOPEE"
    csv_content: Optional[str] = ""
    csv_text: Optional[str] = ""

class PostedLogCreateModel(BaseModel):
    type: str = "POST"  # 'POST' hoặc 'COMMENT'
    group_name: str
    group_url: Optional[str] = ""
    target_url: Optional[str] = ""
    item_id: Optional[str] = ""
    item_name: Optional[str] = ""
    content_snippet: Optional[str] = ""
    image_path: Optional[str] = ""
    status: Optional[str] = "SUCCESS"

class ScheduleModel(BaseModel):
    enabled: bool
    time: str  # Định dạng "HH:MM" (VD: "08:00")
    cats: int  # Số ngành hàng quét mỗi lần

class SingleGroupPostRequest(BaseModel):
    group_id: str
    deal_id: Optional[str] = None

class GradualPostRequest(BaseModel):
    max_groups: Optional[int] = 3
    min_delay_seconds: Optional[int] = 180
    max_delay_seconds: Optional[int] = 300

class UpdateGroupCategoryRequest(BaseModel):
    category_name: str

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

load_env_vars()

def _run_worker(cats: int, run_type: str = "MANUAL_ALL"):
    system_state["is_running"] = True
    system_state["last_status"] = "RUNNING"
    system_state["last_error"] = None
    start_time = datetime.now()
    report_id = db.create_workflow_report(
        run_type=run_type,
        step_name="ALL",
        summary_text=f"Chu trình toàn trình 5 bước ({cats} ngành hàng) - Khởi chạy lúc {start_time.strftime('%H:%M:%S')}"
    )
    load_env_vars()
    try:
        orchestrator = AffiliateSystemOrchestrator()
        orchestrator.run_daily_workflow(max_categories=cats)
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

# Background Scheduler Thread (Vừa quét deal vừa hẹn giờ nhắc sale)
def _scheduler_loop():
    # Khởi tạo thời điểm kiểm tra độ tươi là hiện tại để KHÔNG chạy dồn dập ngay lúc khởi động
    _scheduler_loop.last_freshness_check = datetime.now()
    while True:
        try:
            now = datetime.now()
            current_hm = now.strftime("%H:%M")
            today_str = now.strftime("%Y-%m-%d")

            # 1. Kiểm tra chạy quét deal định kỳ hàng ngày (CHỈ CHẠY KHI NGƯỜI DÙNG BẬT VÀ ĐÚNG GIỜ HẸN)
            if scheduler_state["enabled"]:
                if current_hm == scheduler_state["time"]:
                    if scheduler_state["last_scheduled_run"] != today_str:
                        if not system_state["is_running"]:
                            scheduler_state["last_scheduled_run"] = today_str
                            print(f"⏰ [AUTO SCHEDULER]: Đến giờ chạy tự động ({scheduler_state['time']}). Đang khởi chạy chu trình hàng ngày...")
                            threading.Thread(target=_run_worker, args=(scheduler_state["cats"], "AUTO_SCHEDULE"), daemon=True).start()

            # 2. Kiểm tra hẹn giờ nhắc Flash Sale & Khuyến mại
            if sale_reminder_state["enabled"]:
                hunter = PromotionHunter(db)
                for slot in sale_reminder_state["slots"]:
                    if hunter.is_time_for_reminder(slot, sale_reminder_state["remind_before_minutes"], now):
                        if not db.is_sale_reminder_sent(slot, today_str, target="TELEGRAM"):
                            print(f"⏰ Đến thời điểm bắn bài nhắc Flash Sale khung {slot} (trước {sale_reminder_state['remind_before_minutes']} phút)...")
                            package = hunter.get_today_promotion_package(target_slot=slot)
                            publisher = TelegramPublisher(db=db)
                            publisher.publish_sale_reminder(package)
                            content = DealContentWriter.generate_sale_reminder_post(package)
                            db.log_sale_reminder(slot, today_str, content, target="TELEGRAM")

            # 3. Quét kiểm tra độ tươi của Deal mỗi 2 giờ (Chủ động phát hiện link die / hết hàng)
            if (now - _scheduler_loop.last_freshness_check).total_seconds() > (FRESHNESS_CHECK_INTERVAL_HOURS * 3600):
                _scheduler_loop.last_freshness_check = now
                def _run_freshness():
                    try:
                        print("🔍 [FRESHNESS CHECKER]: Đang chạy kiểm tra định kỳ độ tươi các deal đang hoạt động...")
                        DealFreshnessChecker(db).check_all_active_deals(max_deals=40)
                    except Exception as fe:
                        print(f"Lỗi kiểm tra độ tươi định kỳ: {fe}")
                threading.Thread(target=_run_freshness, daemon=True).start()

        except Exception as e:
            print(f"Lỗi trong scheduler loop: {e}")
        time.sleep(30)

threading.Thread(target=_scheduler_loop, daemon=True).start()

@app.get("/api/status")
def get_status():
    return system_state

@app.get("/api/schedule")
def get_schedule():
    return {
        "enabled": scheduler_state["enabled"],
        "time": scheduler_state["time"],
        "cats": scheduler_state["cats"],
        "last_scheduled_run": scheduler_state["last_scheduled_run"],
        "next_run_display": f"{scheduler_state['time']} Hàng ngày" if scheduler_state["enabled"] else "Đã tạm dừng (Chỉ chạy thủ công)"
    }

@app.post("/api/schedule")
def update_schedule(data: ScheduleModel):
    scheduler_state["enabled"] = data.enabled
    scheduler_state["time"] = data.time
    scheduler_state["cats"] = data.cats
    db.set_system_setting("auto_schedule_enabled", str(data.enabled).lower())
    db.set_system_setting("auto_schedule_time", data.time)
    db.set_system_setting("auto_schedule_cats", str(data.cats))
    return {
        "status": "SUCCESS",
        "message": f"Đã cập nhật lịch chạy: {data.time} mỗi ngày (Tự động chạy: {'BẬT' if data.enabled else 'TẮT'})"
    }

# --- MASTER WORKFLOW: THỰC THI THỦ CÔNG TỪNG BƯỚC ĐỘC LẬP & BÁO CÁO ---

@app.post("/api/workflow/step/crawl")
def workflow_step_crawl(cats: int = 3):
    """BƯỚC 1 (THỦ CÔNG): Quét & Lọc Deal Sốc Đa Sàn (Shopee & Lazada) theo ngành hàng"""
    if system_state["is_running"]:
        raise HTTPException(status_code=400, detail="Hệ thống đang chạy tiến trình khác, vui lòng chờ!")
    
    def run_step_crawl():
        system_state["is_running"] = True
        system_state["last_status"] = "RUNNING_CRAWL"
        start_t = datetime.now()
        rep_id = db.create_workflow_report("MANUAL_STEP", "CRAWL_DEALS", f"Thủ công Bước 1: Quét deal cho {cats} ngành hàng")
        try:
            from modules.crawler.shopee_categories import ShopeeCategoryCrawler
            from modules.crawler.deal_hunter import DealHunter
            from modules.crawler.lazada_deal_hunter import LazadaDealHunter

            crawler = ShopeeCategoryCrawler(db)
            categories = crawler.fetch_categories()
            if not categories:
                categories = [{"cat_id": c["cat_id"], "name": c["name"]} for c in db.get_all_categories()]
            target_cats = categories[:cats]

            deal_hunter = DealHunter(db)
            lazada_hunter = LazadaDealHunter(db)

            shopee_deals = deal_hunter.hunt_top_deals(target_cats)
            lazada_deals = lazada_hunter.hunt_lazada_deals(target_cats)
            total_deals = len(shopee_deals) + len(lazada_deals)

            dur = (datetime.now() - start_t).total_seconds()
            db.update_workflow_report(
                rep_id,
                status="SUCCESS",
                duration_seconds=round(dur, 2),
                deals_scanned=cats * 20,
                deals_saved=total_deals,
                summary_text=f"Đã quét thành công {total_deals} deal ({len(shopee_deals)} Shopee, {len(lazada_deals)} Lazada)."
            )
            system_state["last_status"] = "COMPLETED"
        except Exception as e:
            dur = (datetime.now() - start_t).total_seconds()
            db.update_workflow_report(rep_id, status="ERROR", duration_seconds=round(dur, 2), error_message=str(e))
            system_state["last_status"] = "ERROR"
            system_state["last_error"] = str(e)
        finally:
            system_state["is_running"] = False
            system_state["last_run_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    threading.Thread(target=run_step_crawl, daemon=True).start()
    return {"status": "STARTED", "message": f"Đã khởi động Bước 1: Đang quét deal cho {cats} ngành hàng..."}

@app.post("/api/workflow/step/create-media")
def workflow_step_media():
    """BƯỚC 2 (THỦ CÔNG): Tạo khung ảnh Flash Sale 800x800, ảnh bìa 1080x1080 và ghép 4 deal"""
    start_t = datetime.now()
    rep_id = db.create_workflow_report("MANUAL_STEP", "GENERATE_MEDIA", "Thủ công Bước 2: Tạo banner Flash Sale & ảnh bài đăng")
    try:
        from modules.affiliate.image_stamper import ImageBannerStamper
        from modules.outreach.general_deal_outreach import GeneralDealOutreach

        deals = db.get_deals(limit=10, is_stale=0)
        stamped_count = 0
        for d in deals:
            img = ImageBannerStamper.stamp_deal_image(d)
            if img:
                stamped_count += 1

        outreach = GeneralDealOutreach(db)
        header_banner = outreach.generate_daily_header_banner()
        collage = outreach.generate_daily_collage()

        dur = (datetime.now() - start_t).total_seconds()
        db.update_workflow_report(
            rep_id,
            status="SUCCESS",
            duration_seconds=round(dur, 2),
            banners_created=stamped_count + 2,
            summary_text=f"Đã đóng khung {stamped_count} ảnh sale 800x800, 1 ảnh bìa 1080x1080 và 1 ảnh ghép collage 4 deal."
        )
        return {
            "status": "SUCCESS",
            "message": f"Đã tạo thành công {stamped_count} ảnh khung sale và 2 bộ ảnh bìa/collage!",
            "banners_created": stamped_count + 2,
            "header_banner": str(header_banner) if header_banner else "",
            "collage": str(collage) if collage else ""
        }
    except Exception as e:
        dur = (datetime.now() - start_t).total_seconds()
        db.update_workflow_report(rep_id, status="ERROR", duration_seconds=round(dur, 2), error_message=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/workflow/step/telegram")
def workflow_step_telegram():
    """BƯỚC 3 (THỦ CÔNG): Bắn loạt deal hot lên Kênh Telegram Channel / Group"""
    start_t = datetime.now()
    rep_id = db.create_workflow_report("MANUAL_STEP", "TELEGRAM_PUB", "Thủ công Bước 3: Bắn tin Kênh Telegram")
    try:
        from modules.publisher.telegram_bot import TelegramPublisher
        publisher = TelegramPublisher(db=db)
        deals = db.get_deals(limit=5, is_stale=0)
        published_count = 0
        for d in deals:
            res = publisher.publish_deal_with_banner(d)
            if res.get("status") == "SUCCESS":
                published_count += 1

        dur = (datetime.now() - start_t).total_seconds()
        db.update_workflow_report(
            rep_id,
            status="SUCCESS",
            duration_seconds=round(dur, 2),
            telegram_posts=published_count,
            summary_text=f"Đã xuất bản thành công {published_count} deal kèm ảnh lên Telegram."
        )
        return {
            "status": "SUCCESS",
            "message": f"Đã xuất bản {published_count} bài viết lên Telegram!",
            "published_count": published_count
        }
    except Exception as e:
        dur = (datetime.now() - start_t).total_seconds()
        db.update_workflow_report(rep_id, status="ERROR", duration_seconds=round(dur, 2), error_message=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/workflow/step/fb-outreach")
def workflow_step_fb_outreach(max_groups: int = 3):
    """BƯỚC 4 (THỦ CÔNG): Đăng bài dần vào nhóm FB theo đúng ngành hàng"""
    start_t = datetime.now()
    rep_id = db.create_workflow_report("MANUAL_STEP", "FB_OUTREACH", f"Thủ công Bước 4: Đăng bài dần vào {max_groups} nhóm Facebook")
    try:
        from modules.outreach.fb_group_poster import FacebookGroupPoster, gradual_posting_state
        if gradual_posting_state.get("is_running"):
            return {"status": "ALREADY_RUNNING", "message": "Chu trình đăng bài FB đang chạy!"}

        poster = FacebookGroupPoster(db)
        def run_fb():
            try:
                poster.run_gradual_posting(max_groups=max_groups, min_delay_seconds=5, max_delay_seconds=15)
                dur = (datetime.now() - start_t).total_seconds()
                db.update_workflow_report(
                    rep_id,
                    status="SUCCESS",
                    duration_seconds=round(dur, 2),
                    fb_posts=max_groups,
                    summary_text=f"Hoàn tất quy trình đăng bài dần vào nhóm Facebook."
                )
            except Exception as fe:
                dur = (datetime.now() - start_t).total_seconds()
                db.update_workflow_report(rep_id, status="ERROR", duration_seconds=round(dur, 2), error_message=str(fe))

        threading.Thread(target=run_fb, daemon=True).start()
        return {"status": "STARTED", "message": f"Đang khởi động đăng bài dần vào {max_groups} nhóm Facebook phù hợp..."}
    except Exception as e:
        dur = (datetime.now() - start_t).total_seconds()
        db.update_workflow_report(rep_id, status="ERROR", duration_seconds=round(dur, 2), error_message=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/workflow/step/seeding")
def workflow_step_seeding(max_groups: int = 3):
    """BƯỚC 5 (THỦ CÔNG): Gieo bình luận seeding kèm link Anti-Ban"""
    start_t = datetime.now()
    rep_id = db.create_workflow_report("MANUAL_STEP", "SEEDING_COMMENTS", f"Thủ công Bước 5: Gieo bình luận seeding {max_groups} nhóm")
    try:
        load_env_vars()
        fb_cookie = os.getenv("FB_COOKIE", "")
        fb_profile = os.getenv("FB_CHROME_PROFILE", "")
        if not fb_cookie and not fb_profile:
            raise HTTPException(
                status_code=400,
                detail="Chưa cấu hình Cookie Facebook hoặc Chrome Profile! Vui lòng vào Cài Đặt để cập nhật."
            )
        from modules.outreach.fb_group_seeder import FacebookGroupSeeder
        seeder = FacebookGroupSeeder(db)
        results = seeder.run_seeding_scan(max_groups=max_groups)
        dur = (datetime.now() - start_t).total_seconds()
        db.update_workflow_report(
            rep_id,
            status="SUCCESS",
            duration_seconds=round(dur, 2),
            comments_seeded=len(results),
            summary_text=f"Đã gieo thành công {len(results)} bình luận seeding kèm link Anti-Ban."
        )
        return {
            "status": "SUCCESS",
            "message": f"Đã gieo thành công {len(results)} bình luận seeding!",
            "comments_count": len(results)
        }
    except Exception as e:
        dur = (datetime.now() - start_t).total_seconds()
        db.update_workflow_report(rep_id, status="ERROR", duration_seconds=round(dur, 2), error_message=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/workflow/run-all")
def workflow_run_all(background_tasks: BackgroundTasks, cats: int = 3):
    """KÍCH HOẠT CHẠY TOÀN TRÌNH 5 BƯỚC (THỦ CÔNG 1-CLICK)"""
    if system_state["is_running"]:
        raise HTTPException(status_code=400, detail="Hệ thống đang chạy, vui lòng chờ hoàn thành!")
    background_tasks.add_task(_run_worker, cats, "MANUAL_ALL")
    return {
        "status": "STARTED",
        "message": f"Đã kích hoạt toàn trình 5 bước cho {cats} ngành hàng! Xem tiến trình trong Nhật Ký và Báo Cáo."
    }

@app.get("/api/workflow/reports")
def get_workflow_reports_api(limit: int = 25):
    """Lấy danh sách các báo cáo phiên chạy (Tự động & Thủ công)"""
    return {
        "reports": db.get_workflow_reports(limit=limit)
    }


@app.get("/api/health")
def get_health():
    """Kiểm tra tính hợp lệ của cấu hình hệ thống (Thiếu gì báo lỗi nấy, không giấu lỗi)"""
    load_env_vars()
    shopee_ok = bool(os.getenv("SHOPEE_COOKIE") or (os.getenv("SHOPEE_APP_ID") and os.getenv("SHOPEE_SECRET")))
    lazada_ok = bool(os.getenv("LAZADA_APP_KEY") or os.getenv("LAZADA_TRACKING_URL") or os.getenv("LAZADA_AFF_COOKIE"))
    telegram_ok = bool(os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"))
    fb_ok = bool(os.getenv("FB_COOKIE") or os.getenv("FB_CHROME_PROFILE"))

    issues = []
    if not shopee_ok:
        issues.append("Thiếu Cookie Shopee hoặc Shopee Open API.")
    if not lazada_ok:
        issues.append("Chưa cấu hình Lazada Affiliate (App Key / Secret hoặc Tracking URL).")
    if not telegram_ok:
        issues.append("Thiếu Telegram Bot Token hoặc Chat ID (Không thể bắn deal tự động).")
    if not fb_ok:
        issues.append("Thiếu Cookie Facebook hoặc Profile Chrome (Không thể tìm & join group thật).")

    return {
        "ready": len(issues) <= 1 and (shopee_ok or lazada_ok),
        "shopee_configured": shopee_ok,
        "lazada_configured": lazada_ok,
        "telegram_configured": telegram_ok,
        "facebook_configured": fb_ok,
        "issues": issues
    }

@app.get("/api/stats")
def get_stats():
    today = datetime.now().strftime("%Y-%m-%d")
    with db.get_connection() as conn:
        cat_count = conn.execute("SELECT COUNT(*) FROM categories WHERE is_active = 1").fetchone()[0]
        deals_today = conn.execute("SELECT COUNT(*) FROM deals WHERE created_date = ?", (today,)).fetchone()[0]
        deals_total = conn.execute("SELECT COUNT(*) FROM deals").fetchone()[0]
        deals_shopee = conn.execute("SELECT COUNT(*) FROM deals WHERE platform = 'SHOPEE'").fetchone()[0]
        deals_lazada = conn.execute("SELECT COUNT(*) FROM deals WHERE platform = 'LAZADA'").fetchone()[0]
        groups_total = conn.execute("SELECT COUNT(*) FROM fb_groups").fetchone()[0]
        groups_pending = conn.execute("SELECT COUNT(*) FROM fb_groups WHERE status = 'PENDING'").fetchone()[0]
        groups_approved = conn.execute("SELECT COUNT(*) FROM fb_groups WHERE status = 'APPROVED'").fetchone()[0]
        groups_discovered = conn.execute("SELECT COUNT(*) FROM fb_groups WHERE status = 'DISCOVERED'").fetchone()[0]
        subscribers_count = conn.execute("SELECT COUNT(*) FROM subscribers WHERE is_active = 1").fetchone()[0]
        total_comm = conn.execute("SELECT COALESCE(SUM(commission_amount), 0) FROM commissions").fetchone()[0]

    return {
        "categories_count": cat_count,
        "deals_today": deals_today,
        "deals_total": deals_total,
        "deals_shopee": deals_shopee,
        "deals_lazada": deals_lazada,
        "groups_total": groups_total,
        "groups_pending": groups_pending,
        "groups_approved": groups_approved,
        "groups_discovered": groups_discovered,
        "subscribers_count": subscribers_count,
        "total_commission_vnd": round(total_comm, 0),
        "last_run": system_state["last_run_time"],
        "is_running": system_state["is_running"],
        "last_error": system_state["last_error"],
        "schedule": f"{scheduler_state['time']} (Hàng ngày)" if scheduler_state["enabled"] else "Tắt"
    }

@app.get("/api/deals")
def get_deals(
    limit: int = 50,
    platform: Optional[str] = "ALL",
    category: Optional[str] = "ALL",
    deal_type: Optional[str] = "ALL",
    search: Optional[str] = None,
    sort_by: str = "score",
    is_stale: Optional[int] = 0
):
    """Lấy danh sách deal hỗ trợ lọc đa sàn (Shopee & Lazada), ngành hàng, loại deal (1K / Hoa hồng cao), từ khóa và độ tươi"""
    deals = db.get_deals(
        limit=limit,
        platform=platform,
        is_stale=is_stale if is_stale in [0, 1] else None,
        category_name=category,
        search=search,
        deal_type=deal_type,
        sort_by=sort_by
    )

    # Kiểm tra xem deal đã có ảnh đóng khung local chưa
    for d in deals:
        item_id = str(d.get("item_id", ""))
        banner_file = PROCESSED_IMAGES_DIR / f"{item_id}_banner.jpg"
        d["has_stamped_image"] = banner_file.exists()
        d["stamped_image_url"] = f"/api/deals/image/{item_id}"
        if not d.get("price_badge"):
            d["price_badge"] = "UNVERIFIED"

    return deals

@app.get("/api/deals/loss-leaders")
def get_loss_leaders():
    """Lấy danh sách các Deal Mồi 1K để kích hoạt Cookie 7 ngày của Shopee"""
    deals = db.get_loss_leader_deals(limit=10)
    if not deals:
        hunter = DealHunter(db)
        deals = hunter.fetch_loss_leader_deals(limit=3)
    return deals

@app.post("/api/deals/fetch-loss-leaders")
def fetch_loss_leaders(limit: int = 3):
    """Cào thêm Deal Mồi 1K - Freeship 0Đ để rải link kéo traffic & ghim cookie"""
    hunter = DealHunter(db)
    deals = hunter.fetch_loss_leader_deals(limit=limit)
    return {
        "status": "SUCCESS",
        "message": f"Đã cào thành công {len(deals)} Deal Mồi 1K để kích hoạt Cookie 7 ngày!",
        "deals": deals
    }

@app.post("/api/deals/{item_id}/verify-freshness")
def verify_deal_freshness(item_id: str):
    """Kiểm tra thời gian thực độ tươi & tình trạng còn hàng của deal (Hỗ trợ cả Shopee và Lazada)"""
    deal = db.get_deal_by_id(item_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal không tồn tại")
    
    platform = str(deal.get("platform", "SHOPEE")).upper()
    if platform == "LAZADA":
        prov = LazadaAffiliateProvider()
        is_fresh = prov.verify_deal_freshness(deal)
    else:
        is_fresh = DealHunter.verify_deal_freshness(deal)

    db.mark_deal_stale(item_id, is_stale=0 if is_fresh else 1)
    return {
        "item_id": item_id,
        "name": deal.get("name"),
        "platform": platform,
        "is_fresh": is_fresh,
        "status": "VALID" if is_fresh else "EXPIRED_OR_OUT_OF_STOCK"
    }

@app.post("/api/deals/verify-all")
def verify_all_deals_api(max_deals: int = 40):
    """Kích hoạt kiểm tra độ tươi hàng loạt cho tất cả các deal đang hoạt động"""
    checker = DealFreshnessChecker(db)
    results = checker.check_all_active_deals(max_deals=max_deals)
    return results

@app.get("/api/deals/image/{item_id}")
def get_deal_image(item_id: str):
    """Phục vụ ảnh banner đã đóng khung Flash Sale cho deal, tự động fallback an toàn không bao giờ vỡ ảnh"""
    banner_path = PROCESSED_IMAGES_DIR / f"{item_id}_banner.jpg"
    if banner_path.exists():
        return FileResponse(str(banner_path), media_type="image/jpeg")

    # Nếu chưa có ảnh đã đóng khung, thử đóng khung ngay từ dữ liệu deal
    deal = db.get_deal_by_id(item_id)
    if deal:
        try:
            path = ImageBannerStamper.stamp_deal_image(deal)
            if path and path.exists():
                return FileResponse(str(path), media_type="image/jpeg")
        except Exception as e:
            pass

        # Nếu có ảnh raw
        raw_path = RAW_IMAGES_DIR / f"{item_id}.jpg"
        if raw_path.exists():
            return FileResponse(str(raw_path), media_type="image/jpeg")

        # Nếu có link ảnh Shopee CDN gốc, redirect 307
        if deal.get("image_url"):
            return RedirectResponse(deal["image_url"], status_code=307)

    # Nếu deal chưa có trong CSDL hoặc không tải được ảnh gốc, tạo ảnh placeholder Flash Sale đẹp mắt
    try:
        placeholder_deal = deal or {"item_id": item_id, "name": "Shopee Flash Sale", "category_name": "Hot Deal"}
        path = ImageBannerStamper.stamp_deal_image(placeholder_deal)
        if path and path.exists():
            return FileResponse(str(path), media_type="image/jpeg")
    except Exception:
        pass

    raise HTTPException(status_code=404, detail="Ảnh không tồn tại")

@app.get("/r/{item_id}", response_class=HTMLResponse)
def anti_ban_redirect(item_id: str, request: Request, channel: str = "DIRECT", sub_id: str = ""):
    """
    Trang chuyển hướng trung gian Anti-Ban & Mobile DeepLink Dispatcher:
    - Bọc OpenGraph preview chuẩn chỉnh (ảnh full CDN, giá giảm, đáy 30 ngày) cho Facebook, Zalo, Threads
    - Nhận diện thiết bị di động & In-App Browser (FB, Zalo, TikTok)
    - Kích hoạt DeepLink mở thẳng App Shopee / Lazada native đã đăng nhập sẵn
    - Ghi nhận lượt click & Sub-ID Analytics chi tiết
    """
    deal = db.get_deal_by_id(item_id)
    if not deal:
        return HTMLResponse("<h3>Đang chuyển hướng tới sàn TMĐT...</h3><script>window.location.href='https://shopee.vn';</script>")

    client_ip = request.client.host if request.client else ""
    referer = request.headers.get("referer", "")
    user_agent = request.headers.get("user-agent", "")
    platform = str(deal.get("platform", "SHOPEE")).upper()
    plat_name = "Lazada" if platform == "LAZADA" else "Shopee"
    
    # Ghi nhận lượt click
    db.log_click(
        item_id=item_id,
        channel=channel,
        sub_id=sub_id,
        ip=client_ip,
        referer=referer,
        user_agent=user_agent,
        platform=platform
    )

    aff_url = deal.get("aff_url") or deal.get("item_url") or ("https://www.lazada.vn" if platform == "LAZADA" else "https://shopee.vn")
    
    # Chế độ thử nghiệm chạy thẳng sản phẩm (Tắt trang đệm deeplink nếu cấu hình direct)
    redirect_mode = os.getenv("REDIRECT_MODE", "direct").lower().strip()
    if redirect_mode == "direct" or request.query_params.get("mode") == "direct":
        return RedirectResponse(url=aff_url, status_code=302)

    price_sale_formatted = f"{int(deal.get('price_sale', 0)):,}đ".replace(",", ".")
    price_orig_formatted = f"{int(deal.get('price_original', 0)):,}đ".replace(",", ".")
    discount = int(deal.get("discount_percent", 0))
    rating = round(float(deal.get("rating_star", 5.0) or 5.0), 1)
    sold = int(deal.get("historical_sold", 0) or 0)
    badge_text = "Đáy lịch sử 30 ngày" if "LOW" in str(deal.get("price_badge", "")) else "Giảm thật đã kiểm chứng"
    deal_name = html_escape_module.escape(deal.get("name", f"Ưu Đãi {plat_name} Hot"))

    # Nhận diện In-App Browser & Thiết bị di động
    ua_lower = (user_agent or "").lower()
    is_in_app = any(x in ua_lower for x in ["fban", "fbav", "fb_iab", "instagram", "zalo", "tiktok", "micromessenger", "line"])
    is_mobile = any(x in ua_lower for x in ["iphone", "ipad", "ipod", "android", "mobile"])
    is_android = "android" in ua_lower
    is_ios = any(x in ua_lower for x in ["iphone", "ipad", "ipod"])

    # Xây dựng DeepLink mở thẳng App Shopee / Lazada native
    shop_id = deal.get("shop_id") or ""
    if not shop_id and deal.get("item_url"):
        import re
        match = re.search(r"product/(\d+)/(\d+)", deal.get("item_url", "")) or re.search(r"-i\.(\d+)\.(\d+)", deal.get("item_url", ""))
        if match:
            shop_id = match.group(1)

    if platform == "LAZADA":
        app_scheme = f"lazada://product/{item_id}"
        android_intent = f"intent://product/{item_id}#Intent;scheme=lazada;package=com.lazada.android;S.browser_fallback_url={requests.utils.quote(aff_url)};end"
    else:
        if shop_id:
            app_scheme = f"shopee://product/{shop_id}/{item_id}"
            android_intent = f"intent://product/{shop_id}/{item_id}#Intent;scheme=shopee;package=com.shopee.vn;S.browser_fallback_url={requests.utils.quote(aff_url)};end"
        else:
            app_scheme = f"shopee://search?keyword={item_id}"
            android_intent = f"intent://search?keyword={item_id}#Intent;scheme=shopee;package=com.shopee.vn;S.browser_fallback_url={requests.utils.quote(aff_url)};end"

    # Ảnh OpenGraph tuyệt đối để Facebook/Zalo/Tele cào được thumbnail cực đẹp
    base_url = str(request.base_url).rstrip("/")
    og_image = deal.get("image_url") or f"{base_url}/api/deals/image/{item_id}"

    html_content = f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>⚡ Flash Sale: {deal_name}</title>
    <!-- OpenGraph & Twitter Card SEO Tags cho Mạng Xã Hội -->
    <meta property="og:title" content="🔥 [{plat_name.upper()} FLASH SALE] {deal_name}">
    <meta property="og:description" content="Giá chỉ {price_sale_formatted} (Gốc {price_orig_formatted} - Giảm {discount}%). {badge_text}!">
    <meta property="og:image" content="{og_image}">
    <meta property="og:image:width" content="800">
    <meta property="og:image:height" content="800">
    <meta property="og:type" content="product">
    <meta property="og:site_name" content="Cổng Săn Deal Khuyến Mại {plat_name}">
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="🔥 Flash Sale: {deal_name}">
    <meta name="twitter:description" content="Giá chỉ {price_sale_formatted} (-{discount}%). {badge_text}">
    <meta name="twitter:image" content="{og_image}">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }}
        body {{ background: #0b0f19; color: #f8fafc; display: flex; justify-content: center; align-items: center; min-height: 100vh; padding: 12px; }}
        .card {{ background: #131d2e; border: 1px solid #1e293b; border-radius: 20px; max-width: 480px; width: 100%; overflow: hidden; box-shadow: 0 24px 50px rgba(0,0,0,0.6); position: relative; }}
        .in-app-notice {{ background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%); color: #fff; padding: 10px 14px; font-size: 13px; line-height: 1.4; display: flex; align-items: center; gap: 8px; border-bottom: 1px solid rgba(255,255,255,0.15); }}
        .in-app-notice span {{ font-size: 18px; }}
        .top-badge {{ background: { 'linear-gradient(135deg, #0284c7, #2563eb)' if platform == 'LAZADA' else 'linear-gradient(135deg, #ef4444, #ea580c)' }; color: #fff; text-align: center; padding: 10px; font-weight: 800; font-size: 13px; text-transform: uppercase; letter-spacing: 0.8px; display: flex; align-items: center; justify-content: center; gap: 6px; }}
        .img-container {{ position: relative; width: 100%; height: 330px; background: #070a12; display: flex; align-items: center; justify-content: center; overflow: hidden; }}
        .img-container img {{ width: 100%; height: 100%; object-fit: cover; }}
        .discount-pill {{ position: absolute; top: 12px; right: 12px; background: #facc15; color: #991b1b; padding: 6px 14px; border-radius: 30px; font-weight: 800; font-size: 15px; box-shadow: 0 4px 12px rgba(0,0,0,0.4); }}
        .platform-pill {{ position: absolute; top: 12px; left: 12px; background: rgba(0,0,0,0.7); backdrop-filter: blur(8px); color: #fff; padding: 4px 10px; border-radius: 20px; font-size: 12px; font-weight: 700; border: 1px solid rgba(255,255,255,0.15); }}
        .content {{ padding: 20px; }}
        .title {{ font-size: 17px; font-weight: 700; line-height: 1.45; color: #f1f5f9; margin-bottom: 12px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }}
        .verdict-tag {{ display: inline-flex; align-items: center; gap: 6px; background: rgba(16, 185, 129, 0.15); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.3); padding: 5px 12px; border-radius: 8px; font-size: 12px; font-weight: 700; margin-bottom: 14px; }}
        .price-box {{ display: flex; align-items: baseline; gap: 12px; margin-bottom: 14px; }}
        .price-sale {{ font-size: 30px; font-weight: 900; color: { '#38bdf8' if platform == 'LAZADA' else '#ee4d2d' }; }}
        .price-orig {{ font-size: 15px; color: #94a3b8; text-decoration: line-through; }}
        .meta-info {{ display: flex; justify-content: space-between; font-size: 13px; color: #cbd5e1; margin-bottom: 18px; border-top: 1px dashed rgba(255,255,255,0.1); padding-top: 12px; }}
        
        /* 2 Tầng Nút Hành Động Cho Di Động */
        .btn-deeplink {{ display: flex; align-items: center; justify-content: center; gap: 8px; width: 100%; background: { 'linear-gradient(135deg, #0284c7, #2563eb)' if platform == 'LAZADA' else 'linear-gradient(135deg, #ee4d2d 0%, #f97316 100%)' }; color: #fff; text-align: center; text-decoration: none; padding: 15px; font-size: 15px; font-weight: 800; border-radius: 12px; box-shadow: 0 8px 24px { 'rgba(2, 132, 199, 0.4)' if platform == 'LAZADA' else 'rgba(238, 77, 45, 0.4)' }; transition: transform 0.15s; margin-bottom: 10px; cursor: pointer; border: none; }}
        .btn-deeplink:active {{ transform: scale(0.98); }}
        .btn-web {{ display: block; width: 100%; background: rgba(255,255,255,0.06); color: #94a3b8; border: 1px solid rgba(255,255,255,0.12); text-align: center; text-decoration: none; padding: 10px; font-size: 13px; font-weight: 600; border-radius: 10px; }}
        
        .countdown {{ text-align: center; font-size: 12px; color: #94a3b8; margin-top: 14px; }}
        .countdown span {{ color: #fbbf24; font-weight: 800; }}
        .progress-bar {{ width: 100%; height: 3px; background: rgba(255,255,255,0.1); margin-top: 10px; border-radius: 2px; overflow: hidden; }}
        .progress-fill {{ height: 100%; background: { '#38bdf8' if platform == 'LAZADA' else '#ee4d2d' }; width: 0%; animation: fillProgress 1.6s linear forwards; }}
        @keyframes fillProgress {{ from {{ width: 0%; }} to {{ width: 100%; }} }}
    </style>
</head>
<body>
    <div class="card">
        {'''<div class="in-app-notice">
            <span>💡</span>
            <div><b>Mở trên App {plat_name}:</b> Bấm nút to bên dưới để tự động mở ứng dụng, giữ nguyên đăng nhập và nhận trọn mã giảm giá!</div>
        </div>''' if is_in_app else ''}
        
        <div class="top-badge">
            <span>⚡</span> {plat_name.upper()} FLASH SALE CHÍNH HÃNG
        </div>
        <div class="img-container">
            <img src="{og_image}" alt="{deal_name}" onerror="this.src='/api/deals/image/{item_id}';">
            <div class="platform-pill">{ '🔵 LazMall' if platform == 'LAZADA' else '🟠 Shopee Mall' }</div>
            {f'<div class="discount-pill">-{discount}%</div>' if discount > 0 else ''}
        </div>
        <div class="content">
            <h1 class="title">{deal_name}</h1>
            <div class="verdict-tag">📉 {badge_text}</div>
            <div class="price-box">
                <span class="price-sale">{price_sale_formatted}</span>
                <span class="price-orig">{price_orig_formatted}</span>
            </div>
            <div class="meta-info">
                <span>⭐ {rating} / 5.0 uy tín</span>
                <span>🛒 Đã bán {sold:,} sản phẩm</span>
            </div>

            <!-- Nút DeepLink 1: Mở thẳng App di động -->
            <button id="btnApp" class="btn-deeplink" onclick="launchAppDirectly()">
                <span>🛍️</span> MỞ TRÊN APP {plat_name.upper()} (ĐÃ ĐĂNG NHẬP)
            </button>

            <!-- Nút DeepLink 2: Dự phòng mở Web -->
            <a id="btnWeb" href="{aff_url}" class="btn-web">
                Tiếp tục xem trên Trình duyệt Web ↗
            </a>

            <div class="countdown">Tự động chuyển tiếp sau <span id="sec">2</span>s...</div>
            <div class="progress-bar"><div class="progress-fill"></div></div>
        </div>
    </div>

    <script>
        const targetUrl = "{aff_url}";
        const appScheme = "{app_scheme}";
        const androidIntent = "{android_intent if is_android else ''}";
        const isMobile = { 'true' if is_mobile else 'false' };
        const isAndroid = { 'true' if is_android else 'false' };
        const isInApp = { 'true' if is_in_app else 'false' };

        function launchAppDirectly() {{
            if (isMobile) {{
                if (isAndroid && androidIntent) {{
                    window.location.href = androidIntent;
                }} else {{
                    window.location.href = appScheme;
                    setTimeout(() => {{
                        window.location.href = targetUrl;
                    }}, 1200);
                }}
            }} else {{
                window.location.href = targetUrl;
            }}
        }}

        // Tự động chuyển hướng sau 1.8s
        let s = 2;
        const sEl = document.getElementById('sec');
        const interval = setInterval(() => {{
            s--;
            if (sEl) sEl.textContent = s;
            if (s <= 0) {{
                clearInterval(interval);
                if (isInApp) {{
                    // Trong Facebook/Zalo webview, ưu tiên kích hoạt app scheme
                    launchAppDirectly();
                }} else {{
                    window.location.href = targetUrl;
                }}
            }}
        }}, 900);
    </script>
</body>
</html>
    """
    return HTMLResponse(content=html_content)

# --- SOCIAL OUTREACH COPILOT API ---
@app.get("/api/social/generate-pack")
def generate_social_pack_api(
    item_id: str,
    angle: str = "review",
    channel: str = "fb_feed",
    sub_id: str = "",
    link_mode: str = "direct"
):
    """
    Tạo trọn gói bài đăng và link tiếp thị Mạng Xã Hội (Facebook, Threads, Comments)
    Mặc định link_mode='direct': Gắn thẳng link sản phẩm/affiliate của sàn vào bài đăng để người dùng bấm vào ra thẳng Shopee/Lazada ngay.
    """
    deal = db.get_deal_by_id(item_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Sản phẩm không tồn tại trong kho deal!")

    effective_sub = sub_id or channel
    bridge_url = f"/r/{item_id}?channel={channel}&sub_id={effective_sub}"
    direct_link = deal.get("aff_url") or deal.get("item_url", "")

    # Mặc định dùng thẳng link sàn trực tiếp theo yêu cầu chạy thử nghiệm
    target_link = direct_link if (link_mode == "direct" or not bridge_url) else bridge_url

    pack = DealContentWriter.generate_social_copilot_pack(
        deal=deal,
        angle=angle,
        share_url=target_link
    )

    pack["item_id"] = item_id
    pack["channel"] = channel
    pack["sub_id"] = effective_sub
    pack["bridge_url"] = bridge_url
    pack["direct_aff_url"] = direct_link
    pack["target_link"] = target_link
    pack["link_mode"] = link_mode
    pack["image_url"] = f"/api/deals/image/{item_id}"
    pack["deal"] = deal
    return pack

@app.get("/api/analytics/clicks")
def get_click_analytics():
    return db.get_click_analytics()

@app.get("/api/deals/{item_id}/price-history")
def get_item_price_history(item_id: str):
    history = db.get_price_history(item_id)
    deal = db.get_deal_by_id(item_id)
    tracker = PriceHistoryTracker(db)
    verdict = tracker.analyze_price_verdict(deal) if deal else {}
    return {
        "item_id": item_id,
        "history": history,
        "verdict": verdict
    }

@app.post("/api/outreach/seed-comments")
def trigger_seed_comments(max_groups: int = 3):
    load_env_vars()
    fb_cookie = os.getenv("FB_COOKIE", "")
    fb_profile = os.getenv("FB_CHROME_PROFILE", "")
    if not fb_cookie and not fb_profile:
        raise HTTPException(
            status_code=400,
            detail="Chưa cấu hình Cookie Facebook hoặc Chrome Profile! Vui lòng vào Cài Đặt để cập nhật tài khoản Facebook thật."
        )
    seeder = FacebookGroupSeeder(db)
    results = seeder.run_seeding_scan(max_groups=max_groups)
    return {
        "status": "SUCCESS",
        "message": f"Đã quét và xử lý {len(results)} bình luận seeding trên các nhóm Facebook thật!",
        "results": results
    }

@app.get("/api/outreach/seed-comments/history")
def get_seed_comments_history(limit: int = 50):
    return {"history": db.get_comment_seeding_history(limit=limit)}

@app.get("/api/outreach/seeding-logs")
def get_seeding_logs(lines: int = 150):
    """Lấy nội dung nhật ký chi tiết riêng của module Facebook Seeding"""
    from config.settings import FB_SEEDING_LOG_PATH
    if not FB_SEEDING_LOG_PATH.exists():
        return {"logs": "Chưa có file log seeding phát sinh. Bấm 'Kích Hoạt Gieo Seeding Ngay' để bắt đầu quét!"}
    try:
        with open(FB_SEEDING_LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
            recent_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
            return {"logs": "".join(recent_lines), "total_lines": len(all_lines)}
    except Exception as e:
        return {"logs": f"Lỗi đọc file log seeding: {e}"}

@app.post("/api/outreach/seeding-logs/clear")
def clear_seeding_logs():
    """Xóa trắng file nhật ký Facebook Seeding"""
    from config.settings import FB_SEEDING_LOG_PATH
    try:
        with open(FB_SEEDING_LOG_PATH, "w", encoding="utf-8") as f:
            f.write("")
        return {"status": "SUCCESS", "message": "Đã xóa nhật ký seeding thành công!"}
    except Exception as e:
        return {"status": "ERROR", "message": str(e)}

@app.get("/api/outreach/general-posts")
def get_general_outreach_posts():
    """Tạo trọn bộ các bài đăng tổng hợp deal, lịch sale & tips cho các nhóm săn deal chung kèm link PR nhóm riêng"""
    from modules.outreach.general_deal_outreach import GeneralDealOutreach
    outreach = GeneralDealOutreach(db)
    load_env_vars()
    url = os.getenv("COMMUNITY_INVITE_URL", "")
    name = os.getenv("COMMUNITY_NAME", "Hội Săn Deal Shopee VIP")
    return outreach.generate_all_general_posts(community_url=url, community_name=name)

@app.post("/api/outreach/generate-collage")
def generate_deal_collage():
    """Tạo ảnh ghép 4 góc (2x2 Grid Collage) chuẩn 800x800 cho bài tổng hợp"""
    from modules.outreach.general_deal_outreach import GeneralDealOutreach
    outreach = GeneralDealOutreach(db)
    outreach.generate_daily_collage()
    return {
        "status": "SUCCESS",
        "message": "Đã tạo thành công ảnh ghép 4 deal (2x2 Mega Collage Grid) chuẩn 800x800!",
        "image_url": "/api/outreach/collage-image"
    }

@app.get("/api/outreach/collage-image")
def get_collage_image():
    """Phục vụ ảnh ghép 4 deal JPG"""
    collage_path = PROCESSED_IMAGES_DIR / "daily_mega_collage.jpg"
    if not collage_path.exists():
        from modules.outreach.general_deal_outreach import GeneralDealOutreach
        outreach = GeneralDealOutreach(db)
        collage_path = outreach.generate_daily_collage()
    if collage_path.exists():
        return FileResponse(str(collage_path), media_type="image/jpeg")
    raise HTTPException(status_code=404, detail="Ảnh ghép chưa được tạo")

@app.post("/api/outreach/generate-header-banner")
def generate_header_banner(date_str: Optional[str] = ""):
    """Tạo ảnh tiêu đề Deal Shopee Ngày DD/MM chuẩn đẹp cho bài tổng hợp Facebook"""
    from modules.outreach.general_deal_outreach import GeneralDealOutreach
    outreach = GeneralDealOutreach(db)
    banner_path = outreach.generate_daily_header_banner(date_str=date_str or "")
    return {
        "status": "SUCCESS",
        "message": f"Đã tạo thành công ảnh tiêu đề Deal Shopee ngày {datetime.now().strftime('%d/%m/%Y')}!",
        "image_url": "/api/outreach/header-banner-image"
    }

@app.get("/api/outreach/header-banner-image")
def get_header_banner_image():
    """Phục vụ ảnh tiêu đề Deal Shopee ngày hôm nay JPG"""
    banner_path = PROCESSED_IMAGES_DIR / "daily_deal_header_banner.jpg"
    if not banner_path.exists():
        from modules.outreach.general_deal_outreach import GeneralDealOutreach
        outreach = GeneralDealOutreach(db)
        banner_path = outreach.generate_daily_header_banner()
    if banner_path.exists():
        return FileResponse(str(banner_path), media_type="image/jpeg")
    raise HTTPException(status_code=404, detail="Ảnh tiêu đề chưa được tạo")

# --- Lịch Sử Bài Viết & Comment Đã Đăng (Posted Logs) ---
@app.get("/api/logs/posted")
def get_posted_logs(limit: int = 50, type: Optional[str] = None):
    """Lấy danh sách lịch sử bài viết và comment đã đăng kèm link kiểm tra trên Facebook"""
    return {"logs": db.get_posted_logs(limit=limit, post_type=type)}

@app.post("/api/logs/posted")
def create_posted_log(item: PostedLogCreateModel):
    """Ghi nhận một bài viết hoặc comment vừa đăng lên Facebook để lưu vết"""
    log_id = db.log_posted_item(
        post_type=item.type,
        group_name=item.group_name,
        group_url=item.group_url or "",
        target_url=item.target_url or "",
        item_id=item.item_id or "",
        item_name=item.item_name or "",
        content_snippet=item.content_snippet or "",
        image_path=item.image_path or "",
        status=item.status or "SUCCESS"
    )
    return {
        "status": "SUCCESS",
        "id": log_id,
        "message": "Đã lưu lịch sử bài đăng/comment thành công!"
    }

@app.delete("/api/logs/posted/{log_id}")
def delete_posted_log(log_id: int):
    """Xóa một bản ghi trong lịch sử bài đăng"""
    db.delete_posted_log(log_id)
    return {"status": "SUCCESS", "message": f"Đã xóa log #{log_id}!"}

class AddGroupRequest(BaseModel):
    url: str
    name: Optional[str] = ""
    category_name: Optional[str] = "Cộng Đồng Chung"
    status: Optional[str] = "APPROVED"
    members_count: Optional[int] = 10000

class UpdateGroupStatusRequest(BaseModel):
    status: str

@app.get("/api/groups")
def get_groups(status: Optional[str] = None, limit: int = 200):
    with db.get_connection() as conn:
        if status and status.upper() != "ALL":
            rows = conn.execute("""
                SELECT * FROM fb_groups 
                WHERE status = ?
                ORDER BY members_count DESC 
                LIMIT ?
            """, (status.upper(), limit)).fetchall()
        else:
            rows = conn.execute("""
                SELECT * FROM fb_groups 
                ORDER BY members_count DESC 
                LIMIT ?
            """, (limit,)).fetchall()
        return [dict(r) for r in rows]

@app.get("/api/groups/categorized")
def get_groups_categorized():
    """Lấy danh sách nhóm phân loại rõ ràng: Đã tham gia (Approved) vs Mới tìm thấy (Discovered) vs Chờ duyệt (Pending)"""
    with db.get_connection() as conn:
        rows = conn.execute("SELECT * FROM fb_groups ORDER BY members_count DESC").fetchall()
        all_groups = [dict(r) for r in rows]
        approved = [g for g in all_groups if g.get("status") == "APPROVED"]
        pending = [g for g in all_groups if g.get("status") == "PENDING"]
        discovered = [g for g in all_groups if g.get("status") == "DISCOVERED"]
        return {
            "total": len(all_groups),
            "approved": approved,
            "pending": pending,
            "discovered": discovered,
            "all": all_groups
        }

@app.post("/api/groups/sync-joined")
def sync_joined_groups():
    """Tự động đồng bộ các nhóm mà nick Facebook hiện tại đã tham gia thực tế qua Playwright"""
    from modules.outreach.fb_auto_joiner import FacebookAutoJoiner
    joiner = FacebookAutoJoiner(db)
    try:
        synced = joiner.sync_user_joined_groups()
        return {
            "status": "SUCCESS",
            "message": f"Đã đồng bộ thành công {len(synced)} nhóm Facebook bạn đã tham gia thực tế!",
            "count": len(synced),
            "groups": synced
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/groups/add")
def add_custom_group(req: AddGroupRequest):
    """Thêm một nhóm Facebook mới thủ công (mặc định APPROVED)"""
    url = req.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="Vui lòng nhập đường dẫn URL của nhóm Facebook!")
    
    clean_url = url.split("?")[0].rstrip("/")
    parts = clean_url.split("/groups/")
    if len(parts) >= 2:
        group_id = parts[1].split("/")[0]
    else:
        group_id = str(int(time.time()))
    
    group_name = req.name.strip() if req.name else f"Group Facebook ({group_id})"
    category_name = req.category_name.strip() if req.category_name else "Cộng Đồng Chung"
    status = (req.status or "APPROVED").upper()
    members = req.members_count or 10000

    db.save_group(group_id, group_name, clean_url, category_name, members)
    db.update_group_status(group_id, status)
    return {
        "status": "SUCCESS",
        "message": f"Đã thêm thành công nhóm [{group_name}] với trạng thái {status}!",
        "group": {
            "group_id": group_id,
            "name": group_name,
            "url": clean_url,
            "category_name": category_name,
            "members_count": members,
            "status": status
        }
    }

@app.post("/api/groups/{group_id}/status")
def update_group_status_api(group_id: str, req: UpdateGroupStatusRequest):
    """Cập nhật trạng thái của một nhóm (APPROVED, PENDING, DISCOVERED)"""
    new_status = req.status.upper()
    db.update_group_status(group_id, new_status)
    return {"status": "SUCCESS", "message": f"Đã chuyển trạng thái nhóm #{group_id} sang {new_status}!"}

@app.delete("/api/groups/{group_id}")
def delete_single_group_api(group_id: str):
    """Xóa một nhóm cụ thể khỏi hệ thống"""
    db.delete_group(group_id)
    return {"status": "SUCCESS", "message": f"Đã xóa nhóm #{group_id} khỏi cơ sở dữ liệu!"}

# --- Tự Động Đăng Bài Nhóm (Group Poster & Gradual Posting) ---
@app.post("/api/outreach/post-to-group")
def post_single_group_api(req: SingleGroupPostRequest):
    """Đăng trực tiếp một bài viết với deal phù hợp vào một nhóm Facebook cụ thể"""
    from modules.outreach.fb_group_poster import FacebookGroupPoster
    poster = FacebookGroupPoster(db)
    res = poster.post_to_single_group(req.group_id, req.deal_id)
    if res.get("status") == "ERROR":
        raise HTTPException(status_code=500, detail=res.get("message", "Lỗi khi đăng bài"))
    return res

@app.post("/api/outreach/start-gradual-posting")
def start_gradual_posting_api(req: GradualPostRequest):
    """Khởi động chu trình chạy ngầm đăng bài dần dần vào các nhóm Facebook đã tham gia"""
    from modules.outreach.fb_group_poster import FacebookGroupPoster, gradual_posting_state
    if gradual_posting_state.get("is_running"):
        return {"status": "ALREADY_RUNNING", "message": "Chu trình đăng bài dần đang chạy!", "state": gradual_posting_state}

    poster = FacebookGroupPoster(db)

    def run_job():
        try:
            poster.run_gradual_posting(
                max_groups=req.max_groups or 3,
                min_delay_seconds=req.min_delay_seconds or 180,
                max_delay_seconds=req.max_delay_seconds or 300
            )
        except Exception as e:
            gradual_posting_state["is_running"] = False
            gradual_posting_state["status"] = "ERROR"
            gradual_posting_state["last_error"] = str(e)

    thread = threading.Thread(target=run_job, daemon=True)
    thread.start()

    return {
        "status": "STARTED",
        "message": f"Đã khởi động tiến trình đăng bài dần vào {req.max_groups} nhóm (nghỉ an toàn {req.min_delay_seconds}s - {req.max_delay_seconds}s)!",
        "state": gradual_posting_state
    }

@app.post("/api/outreach/stop-gradual-posting")
def stop_gradual_posting_api():
    """Gửi lệnh dừng chu trình đăng bài dần"""
    from modules.outreach.fb_group_poster import gradual_posting_state
    gradual_posting_state["is_running"] = False
    gradual_posting_state["status"] = "STOPPED"
    return {"status": "SUCCESS", "message": "Đã gửi tín hiệu dừng chu trình đăng bài dần!"}

@app.get("/api/outreach/gradual-posting-status")
def get_gradual_posting_status_api():
    """Lấy trạng thái thời gian thực của tiến trình đăng bài dần"""
    from modules.outreach.fb_group_poster import gradual_posting_state
    return gradual_posting_state

@app.post("/api/groups/auto-categorize")
def auto_categorize_groups_api():
    """Tự động phân loại toàn bộ nhóm theo ngành hàng chuẩn xác dựa vào tên nhóm"""
    import unicodedata
    with db.get_connection() as conn:
        groups = conn.execute("SELECT group_id, name FROM fb_groups").fetchall()
        count = 0
        for gid, name in groups:
            nl = unicodedata.normalize('NFC', (name or "").lower())
            if any(k in nl for k in ['quần áo nam', 'đồ nam', 'thời trang nam', 'quần nam', 'áo nam', 'owen', 'aristino', 'dsquared', 'dsq', 'nam béo mập', 'phối đồ nam', 'men']):
                cat = 'Thời Trang Nam'
            elif any(k in nl for k in ['nữ', 'chị em', 'làm đẹp', 'nấm lùn', '1m50', 'mặc đẹp', 'phối đồ genz', 'mê mặc đẹp', 'tips phối đồ', 'nghiện mặc đẹp', 'phái đẹp']):
                cat = 'Thời Trang Nữ'
            elif any(k in nl for k in ['iphone', 'công nghệ', 'đồ công nghệ', 'tai nghe', 'laptop', 'điện thoại', 'review có tâm', 'android', 'linh kiện', 'apple']):
                cat = 'Thiết Bị Điện Tử'
            elif any(k in nl for k in ['gia dụng', 'nhà cửa', 'nội thất', 'bếp', 'nồi']):
                cat = 'Nhà Cửa & Đời Sống'
            elif any(k in nl for k in ['shopee', 'affililate', 'affiliate', 'rải link', 'săn sale', 'chợ', 'voucher', 'khuyến mãi', 'deal']):
                cat = 'Săn Deal Tổng Hợp'
            else:
                cat = 'Săn Deal Tổng Hợp'
            conn.execute("UPDATE fb_groups SET category_name = ? WHERE group_id = ?", (cat, gid))
            count += 1
        conn.commit()
    return {"status": "SUCCESS", "message": f"Đã phân loại tự động thành công cho {count} nhóm Facebook!", "count": count}

@app.get("/api/groups/with-matched-deals")
def get_groups_with_matched_deals():
    """Lấy danh sách nhóm kèm deal khớp chính xác theo ngành và số lượng deal sẵn sàng trong kho"""
    from modules.outreach.fb_group_poster import FacebookGroupPoster
    poster = FacebookGroupPoster(db)
    with db.get_connection() as conn:
        groups = conn.execute("SELECT * FROM fb_groups ORDER BY members_count DESC").fetchall()
        inv_rows = conn.execute("SELECT category_name, count(*) FROM deals WHERE is_stale = 0 GROUP BY category_name").fetchall()
        inv_map = {r[0]: r[1] for r in inv_rows}

        result = []
        for g in groups:
            gd = dict(g)
            cat_name = gd.get("category_name")
            if cat_name in ['Điện Thoại & Phụ Kiện', 'Công Nghệ']:
                cat_name = 'Thiết Bị Điện Tử'
                gd["category_name"] = cat_name
            matched = poster.find_best_deal_for_group(gd, strict=True)
            gd["matched_deal"] = matched
            gd["category_deals_count"] = inv_map.get(cat_name, 0)
            result.append(gd)
        return result

@app.post("/api/groups/{group_id}/category")
def update_single_group_category(group_id: str, req: UpdateGroupCategoryRequest):
    """Cập nhật trực tiếp ngành hàng cho một nhóm để hệ thống chọn đúng deal"""
    with db.get_connection() as conn:
        conn.execute("UPDATE fb_groups SET category_name = ? WHERE group_id = ?", (req.category_name, group_id))
        conn.commit()
    return {"status": "SUCCESS", "message": f"Đã chuyển nhóm #{group_id} sang ngành '{req.category_name}'!"}

@app.get("/api/deals/category-inventory")
def get_deals_category_inventory():
    """Lấy số lượng deal sẵn sàng theo từng ngành hàng để hiển thị trực quan trên giao diện"""
    with db.get_connection() as conn:
        rows = conn.execute("SELECT category_name, count(*) FROM deals WHERE is_stale = 0 GROUP BY category_name").fetchall()
        return {r[0]: r[1] for r in rows}

@app.get("/api/deals/by-category")
def get_deals_by_category(category: str):
    """Lấy danh sách tất cả deal thuộc một ngành cụ thể để người dùng chọn đăng vào nhóm"""
    with db.get_connection() as conn:
        rows = conn.execute("SELECT * FROM deals WHERE category_name = ? AND is_stale = 0 ORDER BY deal_score DESC LIMIT 30", (category,)).fetchall()
        return [dict(r) for r in rows]

@app.post("/api/deals/clear")
def clear_deals():
    db.clear_deals()
    return {"status": "SUCCESS", "message": "Đã xóa toàn bộ dữ liệu deal sản phẩm!"}

@app.post("/api/groups/clear")
def clear_groups():
    db.clear_groups()
    return {"status": "SUCCESS", "message": "Đã xóa toàn bộ dữ liệu nhóm Facebook!"}

@app.post("/api/data/reset")
def reset_all_data():
    db.reset_all_data(keep_categories=True)
    db.clear_learned_keywords()
    return {"status": "SUCCESS", "message": "Đã làm sạch toàn bộ dữ liệu sản phẩm, nhóm Facebook và từ khóa tự học!"}

@app.get("/api/keywords/learned")
def get_learned_keywords(category_name: Optional[str] = None, limit: int = 50):
    keywords = db.get_learned_keywords(category_name=category_name, limit=limit)
    return {"keywords": keywords, "total": len(keywords)}

@app.post("/api/keywords/learned/seed")
def seed_learned_keywords():
    from modules.outreach.group_keyword_learner import GroupKeywordLearner
    learner = GroupKeywordLearner(db)
    count = learner.seed_from_existing_groups()
    return {"status": "SUCCESS", "message": f"Đã học được {count} từ khóa từ các nhóm hiện có trong cơ sở dữ liệu!"}

@app.post("/api/keywords/learned/clear")
def clear_learned_keywords():
    db.clear_learned_keywords()
    return {"status": "SUCCESS", "message": "Đã xóa toàn bộ từ khóa tự học!"}

# --- Khuyến Mại & Nhắc Giờ Sale (Promotions & Reminders) ---
@app.get("/api/promotions/today")
def get_today_promotions():
    hunter = PromotionHunter(db)
    now = datetime.now()
    package = hunter.get_today_promotion_package()
    upcoming = hunter.get_upcoming_slot(now)
    active = hunter.get_current_active_slot(now)
    
    now_hm = now.strftime("%H:%M")
    slots_with_status = []
    for s in PromotionHunter.FLASH_SALE_SLOTS:
        item = dict(s)
        if now_hm < s["slot"]:
            item["status"] = "UPCOMING"
        elif now_hm >= s["slot"] and (s["slot"] == active["slot"]):
            item["status"] = "ACTIVE"
        else:
            item["status"] = "PASSED"
        item["is_reminded_today"] = db.is_sale_reminder_sent(s["slot"], now.strftime("%Y-%m-%d"), target="TELEGRAM")
        slots_with_status.append(item)

    return {
        "campaign": hunter.detect_campaign_day(now),
        "upcoming_slot": upcoming,
        "active_slot": active,
        "slots": slots_with_status,
        "vouchers": PromotionHunter.DAILY_HOT_VOUCHERS,
        "package": package
    }

@app.get("/api/promotions/config")
def get_promotion_config():
    return sale_reminder_state

@app.post("/api/promotions/config")
def save_promotion_config(cfg: SaleReminderConfigModel):
    sale_reminder_state["enabled"] = cfg.enabled
    sale_reminder_state["remind_before_minutes"] = max(1, min(120, cfg.remind_before_minutes))
    return {
        "status": "SUCCESS",
        "message": f"Đã lưu cấu hình nhắc sale (Nhắc trước {sale_reminder_state['remind_before_minutes']} phút, Trạng thái: {'Bật' if sale_reminder_state['enabled'] else 'Tắt'})!",
        "config": sale_reminder_state
    }

@app.post("/api/promotions/remind-now")
def trigger_remind_now(slot: Optional[str] = None):
    hunter = PromotionHunter(db)
    package = hunter.get_today_promotion_package(target_slot=slot)
    publisher = TelegramPublisher(db=db)
    
    load_env_vars()
    success = publisher.publish_sale_reminder(package)
    now = datetime.now()
    content = DealContentWriter.generate_sale_reminder_post(package)
    db.log_sale_reminder(package["slot_time"], now.strftime("%Y-%m-%d"), content, target="TELEGRAM")

    return {
        "status": "SUCCESS" if success else "FAILED",
        "message": f"Đã gửi thông báo nhắc sale tới Telegram!" if success else "Không thể gửi tới Telegram (Vui lòng kiểm tra TELEGRAM_BOT_TOKEN và TELEGRAM_CHAT_ID trong Cài Đặt)!",
        "package": package,
        "sent_to_telegram": success
    }

# --- Quản Lý Mã Nhập Tay, Link Chiến Dịch & Sinh Bài Đăng Thực Chiến ---
class CreateVoucherCodeModel(BaseModel):
    code: str
    discount_desc: str
    apply_url: Optional[str] = ""
    category_filter: Optional[str] = "ALL"
    voucher_type: Optional[str] = "MANUAL"
    min_order: Optional[float] = 0

class UpdateCampaignLinksModel(BaseModel):
    wallet_url: Optional[str] = None
    banner_1_url: Optional[str] = None
    banner_2_url: Optional[str] = None
    flat_deal_url: Optional[str] = None

class PublishPromoPostModel(BaseModel):
    target: str # 'TELEGRAM' or 'FB_GROUP'
    group_id: Optional[str] = None
    content: str
    post_type_label: Optional[str] = "Bài Khuyến Mại / Voucher"

@app.get("/api/promotions/voucher-codes")
def get_voucher_codes_api():
    """Lấy danh sách toàn bộ mã giảm giá nhập tay, mã % lớn và link chiến dịch"""
    db.seed_default_voucher_campaign()
    return {
        "vouchers": db.get_voucher_codes(),
        "campaign_links": db.get_campaign_links()
    }

@app.post("/api/promotions/voucher-codes")
def create_voucher_code_api(data: CreateVoucherCodeModel):
    """Thêm mới hoặc cập nhật một mã voucher"""
    v_id = db.save_voucher_code(
        code=data.code,
        discount_desc=data.discount_desc,
        apply_url=data.apply_url or "",
        category_filter=data.category_filter or "ALL",
        voucher_type=data.voucher_type or "MANUAL",
        min_order=data.min_order or 0
    )
    return {
        "status": "SUCCESS",
        "message": f"Đã thêm mã [{data.code}] thành công!",
        "id": v_id
    }

@app.delete("/api/promotions/voucher-codes/{voucher_id}")
def delete_voucher_code_api(voucher_id: int):
    """Xóa một mã voucher"""
    db.delete_voucher_code(voucher_id)
    return {"status": "SUCCESS", "message": f"Đã xóa mã voucher #{voucher_id}!"}

@app.post("/api/promotions/voucher-codes/seed-demo")
def seed_demo_vouchers_api():
    """Nạp lại danh sách mã giảm giá và link chiến dịch mẫu chuẩn thực chiến"""
    with db.get_connection() as conn:
        conn.execute("DELETE FROM voucher_codes")
        conn.commit()
    count = db.seed_default_voucher_campaign()
    return {
        "status": "SUCCESS",
        "message": f"Đã nạp lại {count} mã giảm giá và link chiến dịch thực chiến mẫu thành công!"
    }

@app.post("/api/promotions/campaign-links")
def update_campaign_links_api(links: UpdateCampaignLinksModel):
    """Cập nhật link ví voucher, banner 1, banner 2, deal 99k"""
    if links.wallet_url is not None:
        db.save_campaign_link("wallet_url", links.wallet_url, "Link Mở Ví Voucher")
    if links.banner_1_url is not None:
        db.save_campaign_link("banner_1_url", links.banner_1_url, "Link Banner Săn Mã 1")
    if links.banner_2_url is not None:
        db.save_campaign_link("banner_2_url", links.banner_2_url, "Link Banner Săn Mã 2")
    if links.flat_deal_url is not None:
        db.save_campaign_link("flat_deal_url", links.flat_deal_url, "Link Deal Đồng Giá 99K")
    return {
        "status": "SUCCESS",
        "message": "Đã cập nhật các link chiến dịch thành công!",
        "campaign_links": db.get_campaign_links()
    }

@app.get("/api/promotions/generated-posts")
def get_generated_voucher_posts():
    """Tự động sinh trọn bộ 4 dạng bài đăng thực chiến (Manual Vouchers, Back Voucher Alert, High-Value Alert, Flat Deal 99K)"""
    db.seed_default_voucher_campaign()
    vouchers = db.get_voucher_codes()
    links = db.get_campaign_links()
    now = datetime.now()
    date_str = f"{now.day}.{now.month}"

    manual_vouchers = [v for v in vouchers if v.get("voucher_type") == "MANUAL"]
    big_percent_vouchers = [v for v in vouchers if v.get("voucher_type") == "BIG_PERCENT"]

    # 1. Bài danh sách mã nhập tay
    post_manual = DealContentWriter.generate_manual_vouchers_post(
        vouchers=manual_vouchers,
        wallet_url=links.get("wallet_url", "https://s.shopee.vn/1LPJSANV7v"),
        campaign_date=date_str
    )

    # 2. Bài báo giờ back mã kèm 2 banner
    now_hour = now.hour
    all_slots = ["0H", "9H", "12H", "15H", "18H", "20H"]
    slot_hours = [0, 9, 12, 15, 18, 20]
    future_slots = [all_slots[i] for i, h in enumerate(slot_hours) if h >= now_hour]
    if not future_slots:
        future_slots = ["0H", "9H", "12H", "15H"]
    current_slot = future_slots[0] if future_slots else "12H"
    rem_str = ", ".join(future_slots)

    post_back_alert = DealContentWriter.generate_voucher_back_alert_post(
        slot_time=current_slot,
        banner_1=links.get("banner_1_url", "https://s.shopee.vn/6q0WqKvmkf"),
        banner_2=links.get("banner_2_url", "https://s.shopee.vn/7AdjQWuTmi"),
        remaining_slots=rem_str,
        campaign_date=date_str
    )

    # 3. Bài bắn nhanh mã khủng
    post_flash_high = DealContentWriter.generate_flash_high_value_post(
        items=big_percent_vouchers if big_percent_vouchers else None
    )

    # 4. Bài deal đồng giá theo giờ
    post_flat_deal = DealContentWriter.generate_flat_price_deal_post(
        slot_time=current_slot,
        price_label="99K",
        deal_url=links.get("flat_deal_url", "https://s.shopee.vn/5q8Qf8NVyC")
    )

    return {
        "date": date_str,
        "current_slot": current_slot,
        "remaining_slots": rem_str,
        "post_manual_vouchers": post_manual,
        "post_voucher_back_alert": post_back_alert,
        "post_flash_high_value": post_flash_high,
        "post_flat_deal": post_flat_deal,
        "vouchers_count": len(vouchers),
        "campaign_links": links
    }

@app.post("/api/promotions/publish-post")
def publish_voucher_post(req: PublishPromoPostModel):
    """Bắn bài đăng khuyến mại trực tiếp lên Telegram hoặc Facebook Group"""
    load_env_vars()
    if req.target.upper() == "TELEGRAM":
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        if not token or not chat_id:
            raise HTTPException(status_code=400, detail="Chưa cấu hình Telegram Bot Token hoặc Chat ID trong Cài Đặt!")
        
        send_url = f"https://api.telegram.org/bot{token}/sendMessage"
        resp = requests.post(send_url, json={"chat_id": chat_id, "text": req.content}, timeout=12)
        if resp.status_code == 200:
            return {"status": "SUCCESS", "message": "Đã bắn bài đăng khuyến mại thành công lên kênh Telegram!"}
        else:
            raise HTTPException(status_code=400, detail=f"Lỗi gửi Telegram: {resp.text}")

    elif req.target.upper() == "FB_GROUP":
        if not req.group_id:
            raise HTTPException(status_code=400, detail="Vui lòng chọn nhóm Facebook muốn đăng bài!")
        from modules.outreach.fb_group_poster import FacebookGroupPoster
        poster = FacebookGroupPoster(db)
        res = poster.post_to_single_group(req.group_id, custom_content=req.content)
        return res
    else:
        raise HTTPException(status_code=400, detail="Mục tiêu đăng không hợp lệ (Chỉ hỗ trợ TELEGRAM hoặc FB_GROUP)!")

@app.get("/api/config")
def get_config():
    load_env_vars()
    return {
        "shopee_app_id": mask_secret(os.getenv("SHOPEE_APP_ID", ""), show_last=4),
        "shopee_secret": mask_secret(os.getenv("SHOPEE_SECRET", ""), show_last=4),
        "shopee_cookie": mask_secret(os.getenv("SHOPEE_COOKIE", ""), show_last=6),
        "shopee_aff_cookie": mask_secret(os.getenv("SHOPEE_AFF_COOKIE", ""), show_last=6),
        "lazada_app_key": mask_secret(os.getenv("LAZADA_APP_KEY", ""), show_last=4),
        "lazada_app_secret": mask_secret(os.getenv("LAZADA_APP_SECRET", ""), show_last=4),
        "lazada_aff_cookie": mask_secret(os.getenv("LAZADA_AFF_COOKIE", ""), show_last=6),
        "lazada_tracking_url": os.getenv("LAZADA_TRACKING_URL", ""),
        "telegram_bot_token": mask_secret(os.getenv("TELEGRAM_BOT_TOKEN", ""), show_last=5),
        "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID", ""),
        "fb_account_cookie": mask_secret(os.getenv("FB_COOKIE", ""), show_last=6),
        "fb_chrome_profile_path": os.getenv("FB_CHROME_PROFILE", ""),
        "api_admin_key": mask_secret(os.getenv("API_ADMIN_KEY", ""), show_last=4),
        "min_rating_star": float(os.getenv("MIN_RATING_STAR", MIN_RATING_STAR)),
        "min_historical_sold": int(os.getenv("MIN_HISTORICAL_SOLD", MIN_HISTORICAL_SOLD)),
        "min_discount_percent": int(os.getenv("MIN_DISCOUNT_PERCENT", MIN_DISCOUNT_PERCENT)),
        "max_groups_per_day": int(os.getenv("MAX_GROUPS_TO_JOIN_PER_DAY", MAX_GROUPS_TO_JOIN_PER_DAY)),
        "top_deals_per_category": int(os.getenv("TOP_DEALS_PER_CATEGORY", TOP_DEALS_PER_CATEGORY)),
        "community_invite_url": os.getenv("COMMUNITY_INVITE_URL", ""),
        "community_name": os.getenv("COMMUNITY_NAME", "Hội Săn Deal Shopee VIP"),
        "redirect_mode": os.getenv("REDIRECT_MODE", "direct"),
        "redirect_base_url": os.getenv("REDIRECT_BASE_URL", "")
    }

@app.post("/api/config")
def save_config(config: ConfigModel):
    env_file = BASE_DIR / ".env"
    existing_vars = {}
    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    existing_vars[k.strip()] = v.strip()

    def clean_val(new_val: Optional[str], key: str) -> str:
        """Nếu người dùng gửi lại giá trị đã che giấu (chứa •) thì bảo lưu giá trị cũ trong .env"""
        if not new_val or "•" in new_val:
            old = existing_vars.get(key, "").strip('"')
            return f'"{old}"'
        return f'"{new_val.strip()}"'

    config_vars = {
        "SHOPEE_APP_ID": clean_val(config.shopee_app_id, "SHOPEE_APP_ID"),
        "SHOPEE_SECRET": clean_val(config.shopee_secret, "SHOPEE_SECRET"),
        "SHOPEE_COOKIE": clean_val(config.shopee_cookie, "SHOPEE_COOKIE"),
        "SHOPEE_AFF_COOKIE": clean_val(config.shopee_aff_cookie, "SHOPEE_AFF_COOKIE"),
        "LAZADA_APP_KEY": clean_val(config.lazada_app_key, "LAZADA_APP_KEY"),
        "LAZADA_APP_SECRET": clean_val(config.lazada_app_secret, "LAZADA_APP_SECRET"),
        "LAZADA_AFF_COOKIE": clean_val(config.lazada_aff_cookie, "LAZADA_AFF_COOKIE"),
        "LAZADA_TRACKING_URL": f'"{config.lazada_tracking_url or ""}"',
        "API_ADMIN_KEY": clean_val(config.api_admin_key, "API_ADMIN_KEY"),
        "TELEGRAM_BOT_TOKEN": clean_val(config.telegram_bot_token, "TELEGRAM_BOT_TOKEN"),
        "TELEGRAM_CHAT_ID": f'"{config.telegram_chat_id or ""}"',
        "FB_COOKIE": clean_val(config.fb_account_cookie, "FB_COOKIE"),
        "FB_CHROME_PROFILE": f'"{config.fb_chrome_profile_path or ""}"',
        "MIN_RATING_STAR": str(config.min_rating_star),
        "MIN_HISTORICAL_SOLD": str(config.min_historical_sold),
        "MIN_DISCOUNT_PERCENT": str(config.min_discount_percent),
        "MAX_GROUPS_TO_JOIN_PER_DAY": str(config.max_groups_per_day),
        "TOP_DEALS_PER_CATEGORY": str(config.top_deals_per_category),
        "COMMUNITY_INVITE_URL": f'"{config.community_invite_url or ""}"',
        "COMMUNITY_NAME": f'"{config.community_name or "Hội Săn Deal Shopee VIP"}"',
        "REDIRECT_MODE": f'"{config.redirect_mode or "direct"}"',
        "REDIRECT_BASE_URL": f'"{config.redirect_base_url or ""}"',
    }
    existing_vars.update(config_vars)

    with open(env_file, "w", encoding="utf-8") as f:
        for k, v in existing_vars.items():
            f.write(f"{k}={v}\n")

    load_env_vars()
    return {"status": "SUCCESS", "message": "Đã lưu cấu hình an toàn vào file .env thành công!"}

# --- TEST KẾT NỐI (DIAGNOSTICS) ---
@app.post("/api/test/telegram")
def test_telegram():
    load_env_vars()
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        raise HTTPException(status_code=400, detail="Chưa điền Telegram Bot Token hoặc Chat ID trong Cài Đặt!")

    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            raise HTTPException(status_code=400, detail=f"Token không hợp lệ (Mã lỗi {r.status_code}): {r.text}")
        bot_info = r.json().get("result", {})
        
        send_url = f"https://api.telegram.org/bot{token}/sendMessage"
        send_r = requests.post(send_url, json={
            "chat_id": chat_id,
            "text": "🔔 [TEST KẾT NỐI] Hệ thống Shopee & Lazada Affiliate Automation đã kết nối thành công tới Telegram!"
        }, timeout=10)

        if send_r.status_code == 200:
            return {
                "status": "SUCCESS",
                "message": f"Kết nối thành công tới Bot @{bot_info.get('username')} và đã gửi tin nhắn test vào {chat_id}!"
            }
        else:
            raise HTTPException(status_code=400, detail=f"Bot hợp lệ nhưng không gửi được vào chat {chat_id}: {send_r.text}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi kết nối tới Telegram: {e}")

@app.post("/api/test/shopee")
def test_shopee():
    load_env_vars()
    cookie = os.getenv("SHOPEE_COOKIE", "")
    app_id = os.getenv("SHOPEE_APP_ID", "")
    secret = os.getenv("SHOPEE_SECRET", "")

    if not cookie and not (app_id and secret):
        raise HTTPException(status_code=400, detail="Chưa cấu hình Cookie Shopee hoặc Shopee Open API trong Cài Đặt!")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Referer": "https://shopee.vn/"
    }
    if cookie:
        headers["Cookie"] = cookie

    url = "https://shopee.vn/api/v4/pages/get_category_tree"
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            return {"status": "SUCCESS", "message": "Kết nối Shopee thành công! API hoạt động bình thường, không bị chặn 403."}
        elif r.status_code == 403:
            raise HTTPException(status_code=403, detail="Shopee từ chối (403 Forbidden): Cookie của bạn đã hết hạn hoặc không hợp lệ. Vui lòng lấy cookie mới!")
        else:
            raise HTTPException(status_code=r.status_code, detail=f"Shopee trả về lỗi HTTP {r.status_code}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi kết nối tới Shopee: {e}")

@app.post("/api/test/shopee-aff")
def test_shopee_aff():
    load_env_vars()
    aff_cookie = os.getenv("SHOPEE_AFF_COOKIE", "")
    if not aff_cookie:
        raise HTTPException(
            status_code=400,
            detail="Chưa điền Cookie cổng Affiliate (affiliate.shopee.vn) trong Cài Đặt!"
        )

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Cookie": aff_cookie,
        "Referer": "https://affiliate.shopee.vn/",
        "Accept": "application/json, text/plain, */*"
    }
    for part in aff_cookie.split(";"):
        if "csrftoken=" in part:
            headers["x-csrftoken"] = part.strip().split("=", 1)[1]
            break

    url = "https://affiliate.shopee.vn/api/v3/gql?q=batchCustomLink"
    query = """query batchGetCustomLink($linkParams: [CustomLinkParam!], $sourceCaller: SourceCaller) {
  batchCustomLink(linkParams: $linkParams, sourceCaller: $sourceCaller) {
    shortLink
    failCode
  }
}"""
    variables = {
        "linkParams": [{"originalLink": "https://shopee.vn/search?keyword=test"}],
        "sourceCaller": "CUSTOM_LINK_CALLER"
    }

    try:
        r = requests.post(url, headers=headers, json={"query": query, "variables": variables}, timeout=12)
        if r.status_code == 200:
            return {
                "status": "SUCCESS",
                "message": "Kết nối cổng Shopee Affiliate thành công! Cookie hợp lệ và có quyền tạo link hoa hồng."
            }
        elif r.status_code == 403:
            raise HTTPException(
                status_code=403,
                detail="Cookie Shopee Affiliate bị từ chối (403): Phiên đăng nhập đã hết hạn hoặc cookie không hợp lệ. Vui lòng lấy cookie mới!"
            )
        else:
            raise HTTPException(status_code=r.status_code, detail=f"Cổng Shopee Affiliate trả về HTTP {r.status_code}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi kiểm tra cổng Shopee Affiliate: {e}")

@app.post("/api/test/lazada")
def test_lazada():
    """Kiểm tra cấu hình và khả năng tạo link Affiliate sàn Lazada"""
    load_env_vars()
    app_key = os.getenv("LAZADA_APP_KEY", "")
    secret = os.getenv("LAZADA_APP_SECRET", "")
    cookie = os.getenv("LAZADA_AFF_COOKIE", "")
    tracking_url = os.getenv("LAZADA_TRACKING_URL", "")

    if not app_key and not cookie and not tracking_url:
        raise HTTPException(
            status_code=400,
            detail="Chưa cấu hình thông tin Lazada Affiliate (App Key / Secret, Cookie hoặc Tracking URL) trong Cài Đặt!"
        )

    prov = LazadaAffiliateProvider()
    test_link = prov.convert_to_affiliate(
        "https://www.lazada.vn/products/ao-thun-nam-cotton-i12345678.html",
        channel="test",
        sub_id="test_ping"
    )
    if test_link:
        return {
            "status": "SUCCESS",
            "message": f"Kết nối sàn Lazada thành công! Link chuyển đổi mẫu: {test_link[:65]}...",
            "sample_link": test_link
        }
    raise HTTPException(status_code=500, detail="Không thể tạo link chuyển đổi thử nghiệm cho Lazada")

# --- HOA HỒNG & ĐỐI SOÁT DOANH THU (COMMISSION & ROI) ---
@app.get("/api/commissions")
def get_commissions_api(limit: int = 50, platform: Optional[str] = "ALL", status: Optional[str] = "ALL"):
    """Lấy danh sách các đơn hàng chuyển đổi hoa hồng"""
    return {
        "commissions": db.get_commissions(limit=limit, platform=platform, status=status)
    }

@app.get("/api/commissions/stats")
def get_commission_stats_api():
    """Thống kê tổng hợp doanh thu, hoa hồng, EPC, CR theo sàn & kênh"""
    raw_stats = db.get_commission_stats()
    
    # Định dạng dictionary cho sàn và kênh để giao diện Angular bind trực tiếp không lo null
    plat_dict = {
        "SHOPEE": {"platform": "SHOPEE", "commission": 0, "gmv": 0, "orders": 0},
        "LAZADA": {"platform": "LAZADA", "commission": 0, "gmv": 0, "orders": 0}
    }
    for p in raw_stats.get("by_platform", []):
        plat_dict[p["platform"]] = p

    chan_dict = {
        "TELEGRAM": {"channel": "TELEGRAM", "commission": 0, "orders": 0},
        "FB_GROUP": {"channel": "FB_GROUP", "commission": 0, "orders": 0},
        "WEB_HUB": {"channel": "WEB_HUB", "commission": 0, "orders": 0},
        "SEEDING": {"channel": "SEEDING", "commission": 0, "orders": 0},
        "DIRECT": {"channel": "DIRECT", "commission": 0, "orders": 0}
    }
    for c in raw_stats.get("by_channel", []):
        chan_dict[c["channel"]] = c

    return {
        "total_orders": raw_stats.get("total_orders", 0),
        "total_commission": raw_stats.get("total_commission", 0),
        "total_commission_vnd": raw_stats.get("total_commission", 0),
        "approved_commission": raw_stats.get("approved_commission", 0),
        "total_gmv": raw_stats.get("total_gmv", 0),
        "total_gmv_vnd": raw_stats.get("total_gmv", 0),
        "conversion_rate": raw_stats.get("conversion_rate_pct", 0),
        "conversion_rate_pct": raw_stats.get("conversion_rate_pct", 0),
        "epc_vnd": raw_stats.get("epc_vnd", 0),
        "by_platform": plat_dict,
        "by_channel": chan_dict,
        "platforms_list": raw_stats.get("by_platform", []),
        "channels_list": raw_stats.get("by_channel", [])
    }

@app.post("/api/commissions/import")
def import_commissions_api(data: CommissionImportModel):
    """Nhập báo cáo đơn hàng CSV từ cổng Shopee / Lazada Affiliate"""
    csv_raw = data.csv_content or data.csv_text or ""
    res = commission_tracker.parse_and_import_csv(csv_raw, platform=data.platform or "SHOPEE")
    return res

@app.post("/api/commissions/seed-demo")
def seed_demo_commissions_api():
    """Tạo lại dữ liệu đối soát hoa hồng mẫu để hiển thị biểu đồ & bảng"""
    commission_tracker.seed_initial_demo_commissions()
    return {
        "status": "SUCCESS",
        "message": "Đã nạp thành công 6 bản ghi đối soát hoa hồng mẫu đa sàn (Shopee & Lazada)!"
    }

# --- SUBSCRIBERS (RETENTION & DEAL ALERTS) ---
@app.post("/api/subscribers/register")
def register_subscriber_api(sub: SubscriberRegisterModel):
    """Đăng ký nhận deal hot sập sàn qua Email / Web Alert"""
    success = db.save_subscriber(
        email=sub.email,
        telegram_id=sub.telegram_id,
        platform_pref=sub.platform_preference or "ALL",
        category_pref=sub.category_preference or "ALL",
        min_discount=sub.min_discount or 30
    )
    if not success:
        raise HTTPException(status_code=400, detail="Địa chỉ email không hợp lệ!")
    return {
        "status": "SUCCESS",
        "message": "Đăng ký nhận deal thành công! Hệ thống sẽ thông báo ngay khi có deal sập sàn."
    }

@app.get("/api/subscribers")
def get_subscribers_api(platform: Optional[str] = "ALL"):
    """Lấy danh sách các subscriber đang hoạt động"""
    return {
        "subscribers": db.get_active_subscribers(platform=platform)
    }

# --- CỔNG SĂN DEAL NGƯỜI DÙNG (CONSUMER DEAL HUB) ---
@app.get("/deals", response_class=HTMLResponse)
def serve_deal_hub(platform: str = "ALL", category: str = "ALL", q: str = ""):
    """Trang web săn deal người dùng cực đẹp, hỗ trợ cả Shopee và Lazada, tối ưu SEO Google"""
    deals = db.get_deals(limit=60, platform=platform, is_stale=0, category_name=category, search=q)
    categories = db.get_active_categories()
    hunter = PromotionHunter(db)
    upcoming = hunter.get_upcoming_slot(datetime.now())
    html_content = DealHubRenderer.render_hub_page(
        deals=deals,
        categories=categories,
        active_platform=platform,
        active_cat=category,
        search_query=q,
        upcoming_slot=upcoming.get("slot", "12:00")
    )
    return HTMLResponse(content=html_content)

@app.get("/deal/{item_id}", response_class=HTMLResponse)
def serve_deal_detail(item_id: str):
    """Trang chi tiết deal riêng lẻ chuẩn SEO Schema.org"""
    deal = db.get_deal_by_id(item_id)
    if not deal:
        return HTMLResponse("<h3>Deal không tồn tại hoặc đã hết hạn</h3><p><a href='/deals'>← Về Cổng Săn Deal</a></p>", status_code=404)
    related = db.get_deals(limit=6, category_name=deal.get("category_name"), is_stale=0)
    related = [r for r in related if str(r.get("item_id")) != str(item_id)]
    html_content = DealDetailRenderer.render_detail_page(deal=deal, related_deals=related)
    return HTMLResponse(content=html_content)

@app.get("/api/logs")
def get_logs(lines: int = 200):
    if not LOG_FILE_PATH.exists():
        return {"logs": "Chưa có file log phát sinh."}
    try:
        with open(LOG_FILE_PATH, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
            recent_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
            return {"logs": "".join(recent_lines), "total_lines": len(all_lines)}
    except Exception as e:
        return {"logs": f"Lỗi đọc file log: {e}"}

@app.post("/api/logs/clear")
def clear_logs():
    with open(LOG_FILE_PATH, "w", encoding="utf-8") as f:
        f.write("")
    return {"status": "SUCCESS", "message": "Đã xóa log thành công!"}

_last_run_trigger_time = 0.0

@app.post("/api/run")
def trigger_run(background_tasks: BackgroundTasks, cats: int = 2):
    global _last_run_trigger_time
    now_ts = time.time()
    if system_state["is_running"]:
        raise HTTPException(status_code=400, detail="Hệ thống đang chạy, vui lòng chờ hoàn thành!")
    if (now_ts - _last_run_trigger_time) < 15:
        raise HTTPException(status_code=429, detail="Thao tác quá nhanh, vui lòng chờ 15 giây giữa các lần kích hoạt chu trình!")

    _last_run_trigger_time = now_ts
    background_tasks.add_task(_run_worker, cats)
    return {"status": "STARTED", "message": f"Đã kích hoạt chạy chu trình cho {cats} ngành hàng!"}

# Serve Frontend Admin Dashboard
frontend_dist = BASE_DIR / "frontend" / "dist" / "frontend" / "browser"
if frontend_dist.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dist)), name="static")

    @app.get("/{full_path:path}")
    def serve_frontend(full_path: str):
        # Tránh can thiệp các route riêng
        if full_path in ["deals", "deal"]:
            pass
        target_file = frontend_dist / full_path
        if target_file.is_file():
            return FileResponse(str(target_file))
        return FileResponse(str(frontend_dist / "index.html"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)

