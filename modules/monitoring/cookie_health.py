"""
Module CookieHealthChecker: Giám sát trạng thái hoạt động của Cookie Shopee & Facebook.
Tự động cảnh báo qua Telegram khi cookie hết hạn hoặc gặp Checkpoint.
"""

import os
import time
import logging
import requests
from datetime import datetime
from typing import Dict, Optional, Any

from modules.common.resilience import retry_with_backoff, shopee_circuit_breaker
from modules.outreach.fb_account_manager import FbAccountManager
from database.db_manager import DatabaseManager

logger = logging.getLogger(__name__)


class CookieHealthChecker:
    """Giám sát định kỳ và cảnh báo tức thì khi cookie sàn / mạng xã hội bị lỗi"""

    SHOPEE_TEST_URL = "https://shopee.vn/api/v4/flash_sale/flash_sale_get_items"
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )

    _latest_status: Dict[str, Any] = {
        "last_checked": None,
        "shopee": {"status": "UNKNOWN", "valid": False, "message": "Chưa kiểm tra"},
        "facebook": {"status": "UNKNOWN", "valid": False, "message": "Chưa kiểm tra"},
        "all_healthy": False
    }

    def __init__(self, db: Optional[DatabaseManager] = None):
        self.db = db or DatabaseManager()

    def check_shopee_cookie(self, cookie: Optional[str] = None) -> Dict[str, Any]:
        """
        Kiểm tra tính hợp lệ của Cookie Shopee bằng request nhẹ tới Flash Sale API.
        """
        cookie_val = cookie if cookie is not None else (os.getenv("SHOPEE_COOKIE", "") or os.getenv("SHOPEE_AFF_COOKIE", ""))
        if not cookie_val:
            return {
                "status": "MISSING",
                "valid": False,
                "message": "Chưa cấu hình SHOPEE_COOKIE trong file .env hoặc Cài Đặt"
            }

        headers = {
            "User-Agent": self.USER_AGENT,
            "Cookie": cookie_val,
            "Accept": "application/json",
            "Referer": "https://shopee.vn/flash_sale"
        }

        try:
            resp = requests.get(
                self.SHOPEE_TEST_URL,
                headers=headers,
                params={"limit": 1},
                timeout=10
            )

            if resp.status_code == 200:
                data = resp.json()
                if "data" in data or "items" in str(data):
                    return {
                        "status": "HEALTHY",
                        "valid": True,
                        "status_code": 200,
                        "message": "Cookie Shopee hoạt động tốt, đã xác thực dữ liệu"
                    }

            if resp.status_code in (401, 403):
                return {
                    "status": "EXPIRED",
                    "valid": False,
                    "status_code": resp.status_code,
                    "message": "Cookie Shopee đã hết hạn hoặc bị WAF chặn (HTTP 403)"
                }

            return {
                "status": "WARNING",
                "valid": True,
                "status_code": resp.status_code,
                "message": f"Shopee phản hồi mã HTTP {resp.status_code}"
            }
        except Exception as e:
            logger.warning(f"Lỗi khi kiểm tra Cookie Shopee: {e}")
            return {
                "status": "ERROR",
                "valid": False,
                "message": f"Không thể kết nối máy chủ Shopee: {str(e)}"
            }

    def check_facebook_cookie(self, cookie: Optional[str] = None) -> Dict[str, Any]:
        """
        Kiểm tra tính hợp lệ của Cookie Facebook bằng request nhẹ tới mbasic.facebook.com/me.
        """
        cookie_val = cookie
        if cookie_val is None:
            # Tìm cookie từ danh sách tài khoản active trong CSDL
            try:
                accounts = self.db.get_all_accounts()
                active_accs = [a for a in accounts if a.get("status") == "ACTIVE" and a.get("cookie")]
                if active_accs:
                    cookie_val = active_accs[0]["cookie"]
            except Exception:
                pass

            if not cookie_val:
                cookie_val = os.getenv("FB_COOKIE", "")

        if not cookie_val:
            return {
                "status": "MISSING",
                "valid": False,
                "message": "Chưa cấu hình FB_COOKIE trong CSDL hoặc file .env"
            }

        res = FbAccountManager.test_cookie_connection(cookie_val)
        status = res.get("status", "ERROR")
        valid = (status == "SUCCESS")

        return {
            "status": "HEALTHY" if valid else status,
            "valid": valid,
            "uid": res.get("uid"),
            "message": res.get("message", "")
        }

    def check_all(self, alert_on_failure: bool = True) -> Dict[str, Any]:
        """
        Kiểm tra toàn bộ cookie và tự động gửi cảnh báo Telegram nếu có sự cố.
        """
        shopee_res = self.check_shopee_cookie()
        fb_res = self.check_facebook_cookie()

        all_healthy = (shopee_res.get("valid", False) and fb_res.get("valid", False))
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        result = {
            "last_checked": now_str,
            "shopee": shopee_res,
            "facebook": fb_res,
            "all_healthy": all_healthy
        }
        CookieHealthChecker._latest_status = result

        # Gửi cảnh báo Telegram nếu có lỗi và cờ alert_on_failure được bật
        if alert_on_failure and not all_healthy:
            self._send_telegram_alert(shopee_res, fb_res)

        return result

    def _send_telegram_alert(self, shopee_res: Dict, fb_res: Dict):
        """Gửi thông báo khẩn cấp tới Telegram quản trị viên"""
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        if not bot_token or not chat_id:
            return

        issues = []
        if not shopee_res.get("valid", False):
            issues.append(f"🟠 <b>Shopee Cookie</b>: {shopee_res.get('status')} - {shopee_res.get('message')}")
        if not fb_res.get("valid", False):
            issues.append(f"🔵 <b>Facebook Cookie</b>: {fb_res.get('status')} - {fb_res.get('message')}")

        if not issues:
            return

        issues_text = "\n".join(issues)
        msg = (
            "🚨 <b>[CẢNH BÁO HỆ THỐNG] PHÁT HIỆN COOKIE HẾT HẠN HOẶC LỖI</b> 🚨\n\n"
            f"{issues_text}\n\n"
            "👉 <i>Vui lòng truy cập Cổng Quản Trị -> Tab 'Cài Đặt' để cập nhật Cookie mới nhằm tránh gián đoạn tiến trình quét deal và đăng bài!</i>"
        )

        try:
            requests.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={"chat_id": chat_id, "text": msg, "parse_mode": "HTML"},
                timeout=10
            )
            logger.info("📢 Đã gửi thông báo cảnh báo Cookie qua Telegram.")
        except Exception as e:
            logger.warning(f"Không thể gửi thông báo cảnh báo qua Telegram: {e}")

    @classmethod
    def get_latest_status(cls) -> Dict[str, Any]:
        """Trả về kết quả kiểm tra gần nhất"""
        return cls._latest_status
