"""
Analytics & Commission API Router
=================================
Endpoints thống kê hệ thống, kiểm tra sức khỏe cấu hình (health),
click tracking analytics, hoa hồng đối soát đa sàn (Shopee & Lazada) và quản lý Subscribers.
"""

import os
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException

from api.deps import (
    db, commission_tracker, system_state, scheduler_state, load_env_vars
)
from api.models import CommissionImportModel, SubscriberRegisterModel

router = APIRouter(tags=["Analytics & Revenue"])


@router.get("/api/health")
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


@router.get("/api/stats")
def get_stats():
    """Lấy thống kê tổng quan toàn hệ thống"""
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


@router.get("/api/analytics/clicks")
def get_click_analytics():
    """Lấy danh sách nhật ký click link chuyển đổi"""
    return db.get_click_analytics()


# --- Hoa Hồng & Đối Soát Doanh Thu ---

@router.get("/api/commissions")
def get_commissions_api(limit: int = 50, platform: Optional[str] = "ALL", status: Optional[str] = "ALL"):
    """Lấy danh sách các đơn hàng chuyển đổi hoa hồng"""
    return {
        "commissions": db.get_commissions(limit=limit, platform=platform, status=status)
    }


@router.get("/api/commissions/stats")
def get_commission_stats_api():
    """Thống kê tổng hợp doanh thu, hoa hồng, EPC, CR theo sàn & kênh"""
    raw_stats = db.get_commission_stats()

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


@router.post("/api/commissions/import")
def import_commissions_api(data: CommissionImportModel):
    """Nhập báo cáo đơn hàng CSV từ cổng Shopee / Lazada Affiliate"""
    csv_raw = data.csv_content or data.csv_text or ""
    res = commission_tracker.parse_and_import_csv(csv_raw, platform=data.platform or "SHOPEE")
    return res


@router.post("/api/commissions/seed-demo")
def seed_demo_commissions_api():
    """Tạo lại dữ liệu đối soát hoa hồng mẫu để hiển thị biểu đồ & bảng"""
    commission_tracker.seed_initial_demo_commissions()
    return {
        "status": "SUCCESS",
        "message": "Đã nạp thành công 6 bản ghi đối soát hoa hồng mẫu đa sàn (Shopee & Lazada)!"
    }


# --- Subscribers ---

@router.post("/api/subscribers/register")
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


@router.get("/api/subscribers")
def get_subscribers_api(platform: Optional[str] = "ALL"):
    """Lấy danh sách các subscriber đang hoạt động"""
    return {
        "subscribers": db.get_active_subscribers(platform=platform)
    }


# --- Revenue Feedback Loop & A/B Testing Analytics ---

@router.get("/api/analytics/group-ranking")
def get_group_ranking_api(limit: int = 50):
    """Bảng xếp hạng hiệu quả nhóm Facebook theo doanh thu (GMV, Hoa Hồng, Clicks, CR)"""
    return {
        "ranking": db.get_group_performance_ranking(limit=limit)
    }


@router.get("/api/analytics/template-performance")
def get_template_performance_api():
    """Báo cáo so sánh hiệu quả A/B Testing giữa các Template Content Angles"""
    return {
        "templates": db.get_template_performance_comparison()
    }

