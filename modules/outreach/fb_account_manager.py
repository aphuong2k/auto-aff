import os
import re
import logging
import requests
from typing import List, Dict, Optional, Tuple
from datetime import datetime

logger = logging.getLogger("FacebookAccountManager")

class FacebookAccountManager:
    """
    Trình quản lý và điều phối luân phiên đa tài khoản Facebook (Multi-Account Rotation)
    - Luân phiên theo vòng lặp Round-Robin (Nick 1 -> Nick 2 -> Nick 3)
    - Kiểm soát nghiêm ngặt hạn mức ngày (Anti-Checkpoint per account)
    - Tự động phát hiện phiên đăng nhập còn sống hay chết (Fast Health Check)
    - Tương thích ngược: Tự động đồng bộ FB_COOKIE từ .env nếu chưa thêm nick
    """

    def __init__(self, db_manager):
        self.db = db_manager
        self.sync_from_env_if_empty()

    def sync_from_env_if_empty(self):
        """Nếu CSDL chưa có tài khoản nào nhưng trong .env có FB_COOKIE, tự động nhập thành Nick Mặc Định"""
        try:
            accounts = self.db.get_fb_accounts()
            if not accounts:
                env_cookie = os.getenv("FB_COOKIE", "").strip()
                env_profile = os.getenv("FB_CHROME_PROFILE", "").strip()
                if env_cookie or env_profile:
                    name = "Nick Chính (.env)"
                    uid = self.extract_uid(env_cookie)
                    if uid:
                        name = f"Nick Chính ({uid})"
                    self.db.save_fb_account(
                        name=name,
                        cookie=env_cookie,
                        profile_path=env_profile,
                        daily_post_limit=3,
                        daily_join_limit=3,
                        notes="Tự động đồng bộ từ file cấu hình .env"
                    )
                    logger.info(f"Đã tự động khởi tạo tài khoản Facebook mặc định từ .env: {name}")
        except Exception as e:
            logger.warning(f"Lỗi đồng bộ tài khoản từ .env: {e}")

    @staticmethod
    def extract_uid(cookie: str) -> str:
        """Trích xuất UID (c_user) từ chuỗi cookie Facebook"""
        if not cookie:
            return ""
        m = re.search(r"c_user=(\d+)", cookie)
        return m.group(1) if m else ""

    def get_accounts(self, only_active: bool = False) -> List[Dict]:
        return self.db.get_fb_accounts(only_active=only_active)

    def add_account(
        self,
        name: str,
        cookie: str,
        profile_path: str = "",
        daily_post_limit: int = 3,
        daily_join_limit: int = 3,
        proxy: str = "",
        notes: str = ""
    ) -> int:
        clean_cookie = cookie.strip()
        if not name:
            uid = self.extract_uid(clean_cookie)
            name = f"Nick FB {uid}" if uid else "Nick Facebook Mới"

        return self.db.save_fb_account(
            name=name,
            cookie=clean_cookie,
            profile_path=profile_path.strip(),
            daily_post_limit=max(1, int(daily_post_limit)),
            daily_join_limit=max(1, int(daily_join_limit)),
            proxy=proxy.strip(),
            notes=notes.strip()
        )

    def update_account(self, account_id: int, **kwargs) -> bool:
        return self.db.update_fb_account(account_id, **kwargs)

    def delete_account(self, account_id: int) -> bool:
        return self.db.delete_fb_account(account_id)

    def toggle_account(self, account_id: int, is_active: bool) -> bool:
        return self.db.update_fb_account(account_id, is_active=1 if is_active else 0)

    def get_next_account(self, task_type: str = "POST") -> Tuple[Optional[Dict], str]:
        """
        Chọn tài khoản tiếp theo để thực thi tác vụ:
        Trả về (account_dict, message)
        """
        self.sync_from_env_if_empty()
        all_accounts = self.db.get_fb_accounts()
        if not all_accounts:
            return None, "Chưa có tài khoản Facebook nào trong hệ thống! Vui lòng thêm nick trong tab Tiếp Thị hoặc Cài Đặt."

        active_accounts = [a for a in all_accounts if a.get("is_active") == 1 and a.get("status") != "DISABLED"]
        if not active_accounts:
            return None, "Tất cả tài khoản Facebook đang bị Tắt (Inactive). Vui lòng kích hoạt ít nhất 1 nick."

        acc = self.db.get_next_rotating_fb_account(task_type=task_type)
        if not acc:
            limit_field = "bài đăng" if task_type.upper() == "POST" else "lượt tham gia nhóm"
            return None, f"Tất cả {len(active_accounts)} tài khoản Facebook đang hoạt động đã chạm giới hạn {limit_field} trong ngày hôm nay để bảo vệ nick (Anti-Ban). Bạn có thể nghỉ ngơi hoặc tăng hạn mức trong cài đặt."

        return acc, f"Chọn thành công tài khoản luân phiên: [{acc.get('name')}] (Đã dùng {acc.get('posts_today' if task_type.upper() == 'POST' else 'joins_today')}/{acc.get('daily_post_limit' if task_type.upper() == 'POST' else 'daily_join_limit')} lượt hôm nay)"

    def record_usage(self, account_id: int, task_type: str = "POST", success: bool = True, error_msg: str = ""):
        self.db.increment_fb_account_usage(account_id, task_type=task_type, success=success, error_msg=error_msg)

    @classmethod
    def test_cookie_connection(cls, cookie: str) -> Dict:
        """
        Kiểm tra nhanh xem cookie Facebook có còn hoạt động không bằng HTTP request nhẹ
        (Không cần mở trình duyệt Chromium)
        """
        if not cookie:
            return {"status": "ERROR", "message": "Chuỗi cookie trống!"}

        uid = cls.extract_uid(cookie)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Cookie": cookie,
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
        }

        try:
            # Gửi tới mbasic hoặc mobile profile
            resp = requests.get("https://mbasic.facebook.com/me", headers=headers, timeout=10, allow_redirects=True)
            url_final = resp.url.lower()
            text_final = resp.text.lower()

            if "login" in url_final or "checkpoint" in url_final or "đăng nhập" in text_final:
                return {
                    "status": "EXPIRED",
                    "uid": uid,
                    "message": "Cookie đã hết hạn hoặc nick đang bị Facebook yêu cầu xác minh (Checkpoint)!"
                }

            if resp.status_code == 200:
                return {
                    "status": "SUCCESS",
                    "uid": uid,
                    "message": f"Cookie hoạt động tốt! Kết nối thành công tới Facebook (UID: {uid or 'Đã xác thực'})."
                }

            return {
                "status": "WARNING",
                "uid": uid,
                "message": f"Mã phản hồi từ Facebook: HTTP {resp.status_code}"
            }
        except Exception as e:
            return {
                "status": "ERROR",
                "uid": uid,
                "message": f"Không thể kết nối tới máy chủ Facebook: {e}"
            }


# Backward-compatible alias
FbAccountManager = FacebookAccountManager
