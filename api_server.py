import os
import sys
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

import requests
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from config.settings import (
    BASE_DIR, LOG_FILE_PATH,
    MIN_RATING_STAR, MIN_HISTORICAL_SOLD, MIN_DISCOUNT_PERCENT,
    MAX_GROUPS_TO_JOIN_PER_DAY, TOP_DEALS_PER_CATEGORY,
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    SHOPEE_APP_ID, SHOPEE_SECRET
)
from database.db_manager import DatabaseManager
from main import AffiliateSystemOrchestrator

app = FastAPI(title="Shopee Affiliate & FB Outreach Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

db = DatabaseManager()

# Biến trạng thái runtime
system_state = {
    "is_running": False,
    "last_run_time": None,
    "last_status": "IDLE",
    "last_error": None
}

# Cấu hình Lịch Chạy Hàng Ngày (Scheduler)
scheduler_state = {
    "enabled": True,
    "time": "08:00",
    "cats": 3,
    "last_scheduled_run": None
}

class ConfigModel(BaseModel):
    shopee_app_id: Optional[str] = ""
    shopee_secret: Optional[str] = ""
    shopee_cookie: Optional[str] = ""
    telegram_bot_token: Optional[str] = ""
    telegram_chat_id: Optional[str] = ""
    fb_account_cookie: Optional[str] = ""
    fb_chrome_profile_path: Optional[str] = ""
    min_rating_star: Optional[float] = 4.6
    min_historical_sold: Optional[int] = 200
    min_discount_percent: Optional[int] = 15
    max_groups_per_day: Optional[int] = 3
    top_deals_per_category: Optional[int] = 3

class ScheduleModel(BaseModel):
    enabled: bool
    time: str  # Định dạng "HH:MM" (VD: "08:00")
    cats: int  # Số ngành hàng quét mỗi lần

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

# Background Scheduler Thread
def _scheduler_loop():
    while True:
        try:
            now = datetime.now()
            current_hm = now.strftime("%H:%M")
            today_str = now.strftime("%Y-%m-%d")

            if scheduler_state["enabled"]:
                if current_hm == scheduler_state["time"]:
                    if scheduler_state["last_scheduled_run"] != today_str:
                        if not system_state["is_running"]:
                            scheduler_state["last_scheduled_run"] = today_str
                            threading.Thread(target=_run_worker, args=(scheduler_state["cats"],), daemon=True).start()
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
        "next_run_display": f"{scheduler_state['time']} Hàng ngày" if scheduler_state["enabled"] else "Đã tạm dừng"
    }

@app.post("/api/schedule")
def update_schedule(data: ScheduleModel):
    scheduler_state["enabled"] = data.enabled
    scheduler_state["time"] = data.time
    scheduler_state["cats"] = data.cats
    return {
        "status": "SUCCESS",
        "message": f"Đã cập nhật lịch chạy: {data.time} mỗi ngày (Bật: {data.enabled})"
    }

@app.get("/api/health")
def get_health():
    """Kiểm tra tính hợp lệ của cấu hình hệ thống (Thiếu gì báo lỗi nấy, không giấu lỗi)"""
    load_env_vars()
    shopee_ok = bool(os.getenv("SHOPEE_COOKIE") or (os.getenv("SHOPEE_APP_ID") and os.getenv("SHOPEE_SECRET")))
    telegram_ok = bool(os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"))
    fb_ok = bool(os.getenv("FB_COOKIE") or os.getenv("FB_CHROME_PROFILE"))

    issues = []
    if not shopee_ok:
        issues.append("Thiếu Cookie Shopee hoặc Shopee Open API (Sẽ bị lỗi 403 nếu quét deal thật).")
    if not telegram_ok:
        issues.append("Thiếu Telegram Bot Token hoặc Chat ID (Không thể bắn deal tự động).")
    if not fb_ok:
        issues.append("Thiếu Cookie Facebook hoặc Profile Chrome (Không thể tìm & join group thật).")

    return {
        "ready": len(issues) == 0,
        "shopee_configured": shopee_ok,
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
        groups_total = conn.execute("SELECT COUNT(*) FROM fb_groups").fetchone()[0]
        groups_pending = conn.execute("SELECT COUNT(*) FROM fb_groups WHERE status = 'PENDING'").fetchone()[0]
        groups_approved = conn.execute("SELECT COUNT(*) FROM fb_groups WHERE status = 'APPROVED'").fetchone()[0]
        groups_discovered = conn.execute("SELECT COUNT(*) FROM fb_groups WHERE status = 'DISCOVERED'").fetchone()[0]

    return {
        "categories_count": cat_count,
        "deals_today": deals_today,
        "deals_total": deals_total,
        "groups_total": groups_total,
        "groups_pending": groups_pending,
        "groups_approved": groups_approved,
        "groups_discovered": groups_discovered,
        "last_run": system_state["last_run_time"],
        "is_running": system_state["is_running"],
        "last_error": system_state["last_error"],
        "schedule": f"{scheduler_state['time']} (Hàng ngày)" if scheduler_state["enabled"] else "Tắt"
    }

@app.get("/api/deals")
def get_deals(limit: int = 30):
    with db.get_connection() as conn:
        rows = conn.execute("""
            SELECT * FROM deals 
            ORDER BY created_date DESC, deal_score DESC 
            LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]

@app.get("/api/groups")
def get_groups():
    with db.get_connection() as conn:
        rows = conn.execute("""
            SELECT * FROM fb_groups 
            ORDER BY members_count DESC 
            LIMIT 50
        """).fetchall()
        return [dict(r) for r in rows]

@app.get("/api/config")
def get_config():
    load_env_vars()
    return {
        "shopee_app_id": os.getenv("SHOPEE_APP_ID", ""),
        "shopee_secret": os.getenv("SHOPEE_SECRET", ""),
        "shopee_cookie": os.getenv("SHOPEE_COOKIE", ""),
        "telegram_bot_token": os.getenv("TELEGRAM_BOT_TOKEN", ""),
        "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID", ""),
        "fb_account_cookie": os.getenv("FB_COOKIE", ""),
        "fb_chrome_profile_path": os.getenv("FB_CHROME_PROFILE", ""),
        "min_rating_star": float(os.getenv("MIN_RATING_STAR", MIN_RATING_STAR)),
        "min_historical_sold": int(os.getenv("MIN_HISTORICAL_SOLD", MIN_HISTORICAL_SOLD)),
        "min_discount_percent": int(os.getenv("MIN_DISCOUNT_PERCENT", MIN_DISCOUNT_PERCENT)),
        "max_groups_per_day": int(os.getenv("MAX_GROUPS_TO_JOIN_PER_DAY", MAX_GROUPS_TO_JOIN_PER_DAY)),
        "top_deals_per_category": int(os.getenv("TOP_DEALS_PER_CATEGORY", TOP_DEALS_PER_CATEGORY))
    }

@app.post("/api/config")
def save_config(config: ConfigModel):
    env_file = BASE_DIR / ".env"
    lines = [
        f'SHOPEE_APP_ID="{config.shopee_app_id or ""}"\n',
        f'SHOPEE_SECRET="{config.shopee_secret or ""}"\n',
        f'SHOPEE_COOKIE="{config.shopee_cookie or ""}"\n',
        f'TELEGRAM_BOT_TOKEN="{config.telegram_bot_token or ""}"\n',
        f'TELEGRAM_CHAT_ID="{config.telegram_chat_id or ""}"\n',
        f'FB_COOKIE="{config.fb_account_cookie or ""}"\n',
        f'FB_CHROME_PROFILE="{config.fb_chrome_profile_path or ""}"\n',
        f'MIN_RATING_STAR={config.min_rating_star}\n',
        f'MIN_HISTORICAL_SOLD={config.min_historical_sold}\n',
        f'MIN_DISCOUNT_PERCENT={config.min_discount_percent}\n',
        f'MAX_GROUPS_TO_JOIN_PER_DAY={config.max_groups_per_day}\n',
        f'TOP_DEALS_PER_CATEGORY={config.top_deals_per_category}\n'
    ]
    with open(env_file, "w", encoding="utf-8") as f:
        f.writelines(lines)

    load_env_vars()
    return {"status": "SUCCESS", "message": "Đã lưu cấu hình thật vào file .env thành công!"}

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
        
        # Thử gửi 1 tin nhắn test
        send_url = f"https://api.telegram.org/bot{token}/sendMessage"
        send_r = requests.post(send_url, json={
            "chat_id": chat_id,
            "text": "🔔 [TEST KẾT NỐI] Hệ thống Shopee Affiliate Automation đã kết nối thành công tới Telegram!"
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

def _run_worker(cats: int):
    system_state["is_running"] = True
    system_state["last_status"] = "RUNNING"
    system_state["last_error"] = None
    load_env_vars()
    try:
        orchestrator = AffiliateSystemOrchestrator()
        orchestrator.run_daily_workflow(max_categories=cats)
        system_state["last_status"] = "COMPLETED"
    except Exception as e:
        system_state["last_status"] = "ERROR"
        system_state["last_error"] = str(e)
    finally:
        system_state["is_running"] = False
        system_state["last_run_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

@app.post("/api/run")
def trigger_run(background_tasks: BackgroundTasks, cats: int = 2):
    if system_state["is_running"]:
        raise HTTPException(status_code=400, detail="Hệ thống đang chạy, vui lòng chờ hoàn thành!")

    background_tasks.add_task(_run_worker, cats)
    return {"status": "STARTED", "message": f"Đã kích hoạt chạy chu trình cho {cats} ngành hàng!"}

# Serve Frontend
frontend_dist = BASE_DIR / "frontend" / "dist" / "frontend" / "browser"
if frontend_dist.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dist)), name="static")

    @app.get("/{full_path:path}")
    def serve_frontend(full_path: str):
        target_file = frontend_dist / full_path
        if target_file.is_file():
            return FileResponse(str(target_file))
        return FileResponse(str(frontend_dist / "index.html"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
