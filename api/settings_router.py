"""
Settings, Configuration & Diagnostics API Router
================================================
Endpoints quản lý cấu hình hệ thống (.env), đa tài khoản Facebook, mã voucher,
link chiến dịch, danh mục hàng hóa và kiểm tra kết nối (Telegram, Shopee, Lazada).
"""

import os
import requests
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Request

from config.settings import (
    BASE_DIR, LOG_FILE_PATH,
    MIN_RATING_STAR, MIN_HISTORICAL_SOLD, MIN_DISCOUNT_PERCENT,
    MAX_GROUPS_TO_JOIN_PER_DAY, TOP_DEALS_PER_CATEGORY
)
from api.deps import (
    db, mask_secret, load_env_vars
)
from api.models import (
    ConfigModel, FbAccountCreateModel, FbAccountUpdateModel,
    CreateVoucherCodeModel, UpdateCampaignLinksModel
)

router = APIRouter(tags=["Settings & Diagnostics"])


@router.get("/api/config")
def get_config():
    """Lấy toàn bộ cấu hình hệ thống hiện tại (che giấu secret nhạy cảm)"""
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


@router.post("/api/config")
def save_config(config: ConfigModel):
    """Lưu cấu hình hệ thống vào file .env"""
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


# --- Facebook Accounts Management ---

@router.get("/api/facebook/accounts")
def get_fb_accounts_api():
    from modules.outreach.fb_account_manager import FacebookAccountManager
    mgr = FacebookAccountManager(db)
    accounts = mgr.get_accounts()
    for acc in accounts:
        raw_cookie = acc.get("cookie", "")
        acc["cookie_masked"] = mask_secret(raw_cookie, show_last=8)
    return {"accounts": accounts, "total": len(accounts)}


@router.post("/api/facebook/accounts")
def add_fb_account_api(req: FbAccountCreateModel):
    from modules.outreach.fb_account_manager import FacebookAccountManager
    mgr = FacebookAccountManager(db)
    acc_id = mgr.add_account(
        name=req.name,
        cookie=req.cookie,
        profile_path=req.profile_path or "",
        daily_post_limit=req.daily_post_limit or 3,
        daily_join_limit=req.daily_join_limit or 3,
        proxy=req.proxy or "",
        notes=req.notes or ""
    )
    return {"status": "SUCCESS", "message": f"Đã thêm tài khoản Facebook [{req.name}] thành công!", "id": acc_id}


@router.put("/api/facebook/accounts/{account_id}")
def update_fb_account_api(account_id: int, req: FbAccountUpdateModel):
    from modules.outreach.fb_account_manager import FacebookAccountManager
    mgr = FacebookAccountManager(db)
    kwargs = {}
    if req.name is not None: kwargs["name"] = req.name
    if req.cookie is not None and "•" not in req.cookie: kwargs["cookie"] = req.cookie
    if req.profile_path is not None: kwargs["profile_path"] = req.profile_path
    if req.daily_post_limit is not None: kwargs["daily_post_limit"] = req.daily_post_limit
    if req.daily_join_limit is not None: kwargs["daily_join_limit"] = req.daily_join_limit
    if req.proxy is not None: kwargs["proxy"] = req.proxy
    if req.notes is not None: kwargs["notes"] = req.notes
    if req.is_active is not None: kwargs["is_active"] = 1 if req.is_active else 0
    if req.status is not None: kwargs["status"] = req.status

    mgr.update_account(account_id, **kwargs)
    return {"status": "SUCCESS", "message": "Đã cập nhật thông tin tài khoản Facebook!"}


@router.delete("/api/facebook/accounts/{account_id}")
def delete_fb_account_api(account_id: int):
    from modules.outreach.fb_account_manager import FacebookAccountManager
    mgr = FacebookAccountManager(db)
    mgr.delete_account(account_id)
    return {"status": "SUCCESS", "message": "Đã xóa tài khoản Facebook!"}


@router.post("/api/facebook/accounts/{account_id}/toggle")
def toggle_fb_account_api(account_id: int, active: bool = True):
    from modules.outreach.fb_account_manager import FacebookAccountManager
    mgr = FacebookAccountManager(db)
    mgr.toggle_account(account_id, is_active=active)
    return {"status": "SUCCESS", "message": f"Đã {'bật' if active else 'tắt'} tài khoản!"}


@router.post("/api/facebook/accounts/{account_id}/test")
def test_fb_account_api(account_id: int):
    acc = db.get_fb_account_by_id(account_id)
    if not acc:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản Facebook!")
    from modules.outreach.fb_account_manager import FacebookAccountManager
    result = FacebookAccountManager.test_cookie_connection(acc.get("cookie", ""))
    return result


@router.post("/api/facebook/accounts/rotate-preview")
def preview_rotate_account_api(task_type: str = "POST"):
    from modules.outreach.fb_account_manager import FacebookAccountManager
    mgr = FacebookAccountManager(db)
    acc, msg = mgr.get_next_account(task_type=task_type)
    if not acc:
        return {"status": "UNAVAILABLE", "message": msg, "account": None}
    acc_copy = dict(acc)
    acc_copy["cookie_masked"] = mask_secret(acc_copy.get("cookie", ""), show_last=8)
    rem = max(0, int(acc_copy.get("daily_post_limit", 5)) - int(acc_copy.get("posts_today", 0)))
    return {"status": "SUCCESS", "message": msg, "account": acc_copy, "remaining_posts": rem}


# --- Từ Khóa Tự Học ---

@router.get("/api/keywords/learned")
def get_learned_keywords(category_name: Optional[str] = None, limit: int = 50):
    keywords = db.get_learned_keywords(category_name=category_name, limit=limit)
    return {"keywords": keywords, "total": len(keywords)}


@router.post("/api/keywords/learned/seed")
def seed_learned_keywords():
    from modules.outreach.group_keyword_learner import GroupKeywordLearner
    learner = GroupKeywordLearner(db)
    count = learner.seed_from_existing_groups()
    return {"status": "SUCCESS", "message": f"Đã học được {count} từ khóa từ các nhóm hiện có trong cơ sở dữ liệu!"}


@router.post("/api/keywords/learned/clear")
def clear_learned_keywords():
    db.clear_learned_keywords()
    return {"status": "SUCCESS", "message": "Đã xóa toàn bộ từ khóa tự học!"}


# --- Vouchers & Campaign Links ---

@router.get("/api/promotions/voucher-codes")
def get_voucher_codes_api():
    return {
        "vouchers": db.get_voucher_codes(),
        "campaign_links": db.get_campaign_links()
    }


@router.post("/api/promotions/voucher-codes")
def create_voucher_code_api(data: CreateVoucherCodeModel):
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


@router.delete("/api/promotions/voucher-codes/{voucher_id}")
def delete_voucher_code_api(voucher_id: int):
    db.delete_voucher_code(voucher_id)
    return {"status": "SUCCESS", "message": f"Đã xóa mã voucher #{voucher_id}!"}


@router.post("/api/promotions/voucher-codes/seed-demo")
def seed_demo_vouchers_api():
    with db.get_connection() as conn:
        conn.execute("DELETE FROM voucher_codes")
        conn.commit()
    count = db.seed_default_voucher_campaign()
    return {
        "status": "SUCCESS",
        "message": f"Đã nạp lại {count} mã giảm giá và link chiến dịch thực chiến mẫu thành công!"
    }


@router.post("/api/promotions/campaign-links")
def update_campaign_links_api(links: UpdateCampaignLinksModel):
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
        "links": db.get_campaign_links()
    }


# --- Categories ---

@router.api_route("/api/categories", methods=["GET", "POST"])
def get_categories_api(request: Request = None, scan: bool = False):
    if scan:
        try:
            from modules.crawler.shopee_categories import ShopeeCategoryCrawler
            crawler = ShopeeCategoryCrawler(db)
            crawler.fetch_categories()
        except Exception:
            pass
    cats = db.get_active_categories()
    if not cats and not scan:
        try:
            from modules.crawler.shopee_categories import ShopeeCategoryCrawler
            crawler = ShopeeCategoryCrawler(db)
            crawler.fetch_categories()
            cats = db.get_active_categories()
        except Exception:
            pass

    with db.get_connection() as conn:
        deal_rows = conn.execute("SELECT category_name, COUNT(*) as cnt FROM deals WHERE is_stale = 0 GROUP BY category_name").fetchall()
        deal_map = {r["category_name"]: r["cnt"] for r in deal_rows}

    results = []
    for c in cats:
        cd = dict(c)
        cd["deals_count"] = deal_map.get(cd.get("name"), 0)
        results.append(cd)

    return {"categories": results, "total": len(results)}


@router.api_route("/api/categories/scan", methods=["GET", "POST"])
def scan_categories_api(request: Request = None):
    try:
        from modules.crawler.shopee_categories import ShopeeCategoryCrawler
        crawler = ShopeeCategoryCrawler(db)
        fresh_cats = crawler.fetch_categories()
        cats = db.get_active_categories()
        with db.get_connection() as conn:
            deal_rows = conn.execute("SELECT category_name, COUNT(*) as cnt FROM deals WHERE is_stale = 0 GROUP BY category_name").fetchall()
            deal_map = {r["category_name"]: r["cnt"] for r in deal_rows}
        results = []
        for c in cats:
            cd = dict(c)
            cd["deals_count"] = deal_map.get(cd.get("name"), 0)
            results.append(cd)
        return {
            "status": "SUCCESS",
            "message": f"Đã quét thành công {len(fresh_cats) or len(cats)} ngành hàng từ Shopee!",
            "categories": results,
            "total": len(results)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi quét danh mục Shopee: {e}")


# --- Diagnostics & Tests ---

@router.post("/api/test/telegram")
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


@router.post("/api/test/shopee")
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
        user_info = ""
        if cookie:
            try:
                pr = requests.get("https://shopee.vn/api/v2/user/profile/get", headers=headers, timeout=8)
                if pr.status_code == 200:
                    p_data = pr.json().get("data", {})
                    name = p_data.get("nickname") or p_data.get("username")
                    uid = p_data.get("userid")
                    if name:
                        user_info = f" Tài khoản: [{name}] (ID: {uid})."
            except Exception:
                pass

        if r.status_code == 200:
            return {"status": "SUCCESS", "message": f"Kết nối Shopee thành công!{user_info} API cào danh mục & săn deal hoạt động bình thường."}
        elif r.status_code == 403:
            raise HTTPException(status_code=403, detail="Shopee từ chối (403 Forbidden): Cookie của bạn đã hết hạn hoặc không hợp lệ. Vui lòng lấy cookie mới!")
        else:
            raise HTTPException(status_code=r.status_code, detail=f"Shopee trả về lỗi HTTP {r.status_code}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi kết nối tới Shopee: {e}")


@router.post("/api/test/shopee-aff")
def test_shopee_aff():
    load_env_vars()
    aff_cookie = os.getenv("SHOPEE_AFF_COOKIE", "")
    if not aff_cookie:
        raise HTTPException(status_code=400, detail="Chưa điền Cookie cổng Affiliate (affiliate.shopee.vn) trong Cài Đặt!")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Cookie": aff_cookie,
        "Referer": "https://affiliate.shopee.vn/",
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json"
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
            return {"status": "SUCCESS", "message": "Kết nối cổng Shopee Affiliate thành công! Cookie hợp lệ và có quyền tạo link hoa hồng."}

        resp_json = {}
        try:
            resp_json = r.json()
        except Exception:
            pass

        if resp_json.get("is_login") is False:
            raise HTTPException(status_code=403, detail="Cookie Shopee Affiliate bị từ chối: Phiên đăng nhập đã hết hạn!")
        return {"status": "INFO", "message": "Cookie Shopee Affiliate đã được xác nhận (WAF verification bypass cần Open API key để ổn định hơn)."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi kiểm tra cổng Shopee Affiliate: {e}")


@router.post("/api/test/lazada")
def test_lazada():
    load_env_vars()
    from modules.affiliate.lazada_provider import LazadaAffiliateProvider
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


# --- System Reset & Logs ---

@router.get("/api/logs")
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


@router.post("/api/logs/clear")
def clear_logs():
    with open(LOG_FILE_PATH, "w", encoding="utf-8") as f:
        f.write("")
    return {"status": "SUCCESS", "message": "Đã xóa log thành công!"}


@router.post("/api/data/reset")
def reset_all_data():
    db.reset_all_data(keep_categories=True)
    db.clear_learned_keywords()
    with db.get_connection() as conn:
        conn.execute("DELETE FROM voucher_codes")
        conn.execute("DELETE FROM subscribers")
        try:
            conn.execute("UPDATE fb_accounts SET posts_today = 0, joins_today = 0")
        except Exception:
            pass
        conn.commit()
    return {"status": "SUCCESS", "message": "Đã làm sạch toàn bộ dữ liệu ảo (deals, nhóm FB, hoa hồng, voucher)!"}


# --- Cookie Health & Resilience Monitoring ---

@router.get("/api/settings/cookie-health")
def get_cookie_health():
    """Lấy trạng thái kiểm tra Cookie Shopee & Facebook gần nhất"""
    from modules.monitoring.cookie_health import CookieHealthChecker
    status = CookieHealthChecker.get_latest_status()
    if not status.get("last_checked"):
        checker = CookieHealthChecker()
        status = checker.check_all(alert_on_failure=False)
    return status


@router.post("/api/settings/cookie-health/check")
def trigger_cookie_health_check(alert_on_failure: bool = False):
    """Kích hoạt kiểm tra tức thì trạng thái Cookie Shopee & Facebook"""
    from modules.monitoring.cookie_health import CookieHealthChecker
    checker = CookieHealthChecker()
    result = checker.check_all(alert_on_failure=alert_on_failure)
    return result


@router.get("/api/settings/resilience-status")
def get_resilience_status():
    """Lấy thông tin trạng thái hoạt động của các Circuit Breaker (Shopee, Lazada, Telegram, TinyURL)"""
    from modules.common.resilience import get_all_resilience_status
    return get_all_resilience_status()

