"""
Join Feedback Monitor & Auto-Leave System
==========================================
Theo dõi phản hồi xét duyệt tham gia nhóm Facebook:
1. Định kỳ kiểm tra các nhóm đang ở trạng thái 'PENDING'.
2. Nếu được duyệt -> Tự động chuyển trạng thái thành 'APPROVED' để đưa vào danh sách đăng bài.
3. Nếu bị từ chối / Nội dung không khả dụng -> Đánh dấu 'REJECTED'.
4. Nếu chờ quá lâu (> 7 ngày hoặc check >= 3 lần) không được duyệt:
   -> Tự động HỦY YÊU CẦU / RỜI NHÓM (Auto-Leave) và đánh dấu 'TIMEOUT_LEFT'
   -> Không làm rác danh sách nhóm đang chờ của nick Facebook.
5. Cung cấp API / hàm rời nhóm chủ động khi cần dọn dẹp group ma hoặc group kém hiệu quả.
"""

import os
import time
import logging
from typing import Dict, List, Optional
from datetime import datetime, timezone

from database.db_manager import DatabaseManager

monitor_logger = logging.getLogger("JoinFeedbackMonitor")
monitor_logger.setLevel(logging.INFO)


class JoinFeedbackMonitor:
    """Theo dõi kết quả duyệt tham gia nhóm và tự động rời nhóm quá hạn."""

    # Cấu hình tự động dọn dẹp
    PENDING_TIMEOUT_HOURS = 168.0   # 7 ngày
    MAX_CHECK_ATTEMPTS = 3          # Tối đa 3 lần check mà vẫn pending -> auto-leave

    def __init__(self, db: Optional[DatabaseManager] = None):
        self.db = db or DatabaseManager()

    def check_pending_joins(self) -> Dict:
        """
        Quét toàn bộ danh sách group có status='PENDING' trong CSDL.
        Dùng Playwright kiểm tra tình trạng duyệt và xử lý auto-leave nếu quá hạn.
        """
        pending_groups = self.db.get_groups_by_status("PENDING")
        if not pending_groups:
            monitor_logger.info("Không có nhóm nào đang ở trạng thái PENDING chờ kiểm tra.")
            return {"total": 0, "approved": 0, "still_pending": 0, "rejected": 0, "left": 0}

        monitor_logger.info(f"📋 Bắt đầu kiểm tra {len(pending_groups)} nhóm đang chờ duyệt...")

        fb_cookie = os.getenv("FB_COOKIE", "")
        fb_profile = os.getenv("FB_CHROME_PROFILE", "")

        if not fb_cookie and not fb_profile:
            raise RuntimeError("Chưa cấu hình tài khoản Facebook (Cookie hoặc Chrome Profile) để kiểm tra!")

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise RuntimeError("Chưa cài đặt Playwright!")

        results = {
            "total": len(pending_groups),
            "approved": 0,
            "still_pending": 0,
            "rejected": 0,
            "left": 0
        }

        with sync_playwright() as p:
            if fb_profile and os.path.exists(fb_profile):
                context = p.chromium.launch_persistent_context(
                    user_data_dir=fb_profile,
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled"]
                )
                browser = None
            else:
                browser = p.chromium.launch(
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled"]
                )
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                )
                if fb_cookie:
                    cookie_list = []
                    for item in fb_cookie.split(";"):
                        if "=" in item:
                            k, v = item.strip().split("=", 1)
                            cookie_list.append({"name": k, "value": v, "domain": ".facebook.com", "path": "/"})
                    if cookie_list:
                        context.add_cookies(cookie_list)

            page = context.new_page()

            for group in pending_groups:
                group_id = group["group_id"]
                group_name = group.get("name", "Group")
                group_url = group["url"]
                check_count = (group.get("join_check_count") or 0) + 1

                monitor_logger.info(f"🔎 Kiểm tra nhóm [{group_name}] ({group_url}) - Lần check #{check_count}")

                try:
                    page.goto(group_url, timeout=35000, wait_until="domcontentloaded")
                    page.wait_for_timeout(3000)

                    body_text = page.locator("body").inner_text()

                    # 1. Trường hợp: ĐÃ ĐƯỢC DUYỆT THÀNH CÔNG
                    if "Đã tham gia" in body_text or "Joined" in body_text or page.locator("div[aria-label='Đã tham gia']").is_visible(timeout=1000):
                        monitor_logger.info(f"🎉 Nhóm [{group_name}] ĐÃ ĐƯỢC DUYỆT! Cập nhật status='APPROVED'")
                        self.db.update_group_join_feedback(group_id, "APPROVED", check_count)
                        results["approved"] += 1
                        continue

                    # 2. Trường hợp: NỘI DUNG BỊ KHÓA / BỊ TỪ CHỐI / GROUP DIE
                    if "Nội dung này hiện không khả dụng" in body_text or "This content isn't available" in body_text:
                        monitor_logger.warning(f"❌ Nhóm [{group_name}] không khả dụng hoặc bị từ chối/block. Cập nhật status='REJECTED'")
                        self.db.update_group_join_feedback(group_id, "REJECTED", check_count)
                        results["rejected"] += 1
                        continue

                    # 3. Trường hợp: VẪN ĐANG CHỜ DUYỆT (Hủy yêu cầu / Pending)
                    is_pending = (
                        "Hủy yêu cầu" in body_text or
                        "Cancel request" in body_text or
                        "Đang chờ phê duyệt" in body_text or
                        "Pending approval" in body_text
                    )

                    # Kiểm tra xem có quá hạn chờ duyệt không
                    requested_at = group.get("join_requested_at")
                    hours_pending = 0.0
                    if requested_at:
                        try:
                            req_time = datetime.fromisoformat(requested_at.replace("Z", "+00:00"))
                            now = datetime.now(timezone.utc)
                            hours_pending = (now - req_time).total_seconds() / 3600.0
                        except Exception:
                            pass

                    # Điều kiện kích hoạt Auto-Leave:
                    # - Chờ quá PENDING_TIMEOUT_HOURS (7 ngày) HOẶC
                    # - Đã check >= MAX_CHECK_ATTEMPTS (3 lần) mà vẫn không duyệt
                    should_auto_leave = (
                        (hours_pending >= self.PENDING_TIMEOUT_HOURS and hours_pending > 0) or
                        (check_count >= self.MAX_CHECK_ATTEMPTS)
                    )

                    if should_auto_leave and is_pending:
                        monitor_logger.warning(
                            f"⏰ Nhóm [{group_name}] chờ duyệt quá lâu (Đã check {check_count} lần, {hours_pending:.1f}h). "
                            f"Kích hoạt AUTO-LEAVE hủy yêu cầu..."
                        )
                        left_success = self.cancel_pending_request(page)
                        if left_success:
                            self.db.update_group_join_feedback(group_id, "TIMEOUT_LEFT", check_count)
                            results["left"] += 1
                            monitor_logger.info(f"🚪 Đã tự động hủy yêu cầu nhóm [{group_name}] thành công.")
                        else:
                            self.db.update_group_join_feedback(group_id, "TIMEOUT_LEFT", check_count)
                            results["left"] += 1
                    elif is_pending:
                        monitor_logger.info(f"⏳ Nhóm [{group_name}] vẫn đang chờ Admin duyệt. Cập nhật lượt check #{check_count}")
                        self.db.update_group_join_feedback(group_id, "PENDING", check_count)
                        results["still_pending"] += 1
                    else:
                        # Nút Tham gia nhóm hiển thị -> Yêu cầu cũ đã bị từ chối
                        if page.locator("div[aria-label='Tham gia nhóm']").is_visible(timeout=1000) or "Tham gia nhóm" in body_text:
                            monitor_logger.warning(f"❌ Nhóm [{group_name}] đã từ chối yêu cầu gia nhập. Cập nhật status='REJECTED'")
                            self.db.update_group_join_feedback(group_id, "REJECTED", check_count)
                            results["rejected"] += 1
                        else:
                            self.db.update_group_join_feedback(group_id, "PENDING", check_count)
                            results["still_pending"] += 1

                except Exception as e:
                    monitor_logger.error(f"Lỗi kiểm tra nhóm [{group_name}]: {e}")

                time.sleep(2)  # Delay nhẹ giữa các group

            if browser:
                browser.close()
            else:
                context.close()

        monitor_logger.info(
            f"🏁 Hoàn thành kiểm tra: Approved={results['approved']}, Still Pending={results['still_pending']}, "
            f"Rejected={results['rejected']}, Auto-Left={results['left']}"
        )
        return results

    def cancel_pending_request(self, page) -> bool:
        """Playwright: Click 'Hủy yêu cầu' / 'Cancel request' để rút lui khỏi group."""
        try:
            cancel_selectors = [
                "div[aria-label='Hủy yêu cầu']",
                "div[aria-label='Cancel request']",
                "div[role='button']:has-text('Hủy yêu cầu')",
                "div[role='button']:has-text('Cancel request')",
                "div[role='button']:has-text('Đang chờ')"
            ]
            for sel in cancel_selectors:
                btn = page.locator(sel).first
                if btn.is_visible(timeout=1500):
                    btn.click()
                    page.wait_for_timeout(1000)
                    # Xác nhận popup nếu có
                    confirm_btn = page.locator("div[role='dialog'] div[role='button']:has-text('Hủy yêu cầu'), div[role='dialog'] div[role='button']:has-text('Xác nhận')").first
                    if confirm_btn.is_visible(timeout=1500):
                        confirm_btn.click()
                        page.wait_for_timeout(1500)
                    return True
        except Exception as e:
            monitor_logger.debug(f"Lỗi khi bấm hủy yêu cầu: {e}")
        return False

    def leave_group(self, group_url: str) -> bool:
        """
        Rời khỏi nhóm Facebook đã tham gia (Áp dụng khi nhóm thành group ma hoặc liên tục bị từ chối bài).
        """
        fb_cookie = os.getenv("FB_COOKIE", "")
        fb_profile = os.getenv("FB_CHROME_PROFILE", "")

        if not fb_cookie and not fb_profile:
            raise RuntimeError("Chưa cấu hình thông tin đăng nhập Facebook!")

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise RuntimeError("Chưa cài đặt Playwright!")

        success = False
        with sync_playwright() as p:
            if fb_profile and os.path.exists(fb_profile):
                context = p.chromium.launch_persistent_context(
                    user_data_dir=fb_profile,
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled"]
                )
                browser = None
            else:
                browser = p.chromium.launch(
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled"]
                )
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                )
                if fb_cookie:
                    cookie_list = []
                    for item in fb_cookie.split(";"):
                        if "=" in item:
                            k, v = item.strip().split("=", 1)
                            cookie_list.append({"name": k, "value": v, "domain": ".facebook.com", "path": "/"})
                    if cookie_list:
                        context.add_cookies(cookie_list)

            page = context.new_page()

            try:
                page.goto(group_url, timeout=35000, wait_until="domcontentloaded")
                page.wait_for_timeout(3000)

                # 1. Tìm nút 'Đã tham gia' / 'Joined'
                joined_btn = page.locator("div[aria-label='Đã tham gia'], div[aria-label='Joined'], div[role='button']:has-text('Đã tham gia')").first
                if joined_btn.is_visible(timeout=2000):
                    joined_btn.click()
                    page.wait_for_timeout(1000)

                    # Chọn mục 'Rời nhóm' / 'Leave group' trong menu
                    leave_menu_item = page.locator("div[role='menuitem']:has-text('Rời khỏi nhóm'), div[role='menuitem']:has-text('Rời nhóm'), div[role='menuitem']:has-text('Leave group')").first
                    if leave_menu_item.is_visible(timeout=2000):
                        leave_menu_item.click()
                        page.wait_for_timeout(1000)

                        # Xác nhận dialog rời nhóm
                        confirm_dialog_btn = page.locator("div[role='dialog'] div[role='button']:has-text('Rời khỏi nhóm'), div[role='dialog'] div[role='button']:has-text('Rời nhóm'), div[role='dialog'] div[role='button']:has-text('Leave group')").first
                        if confirm_dialog_btn.is_visible(timeout=2000):
                            confirm_dialog_btn.click()
                            page.wait_for_timeout(2000)
                            success = True
                            monitor_logger.info(f"🚪 Đã rời nhóm thành công: {group_url}")

                # Hoặc nếu là nút Hủy yêu cầu đang chờ
                if not success and self.cancel_pending_request(page):
                    success = True
                    monitor_logger.info(f"🚪 Đã hủy yêu cầu tham gia thành công: {group_url}")

            except Exception as e:
                monitor_logger.error(f"Lỗi khi rời nhóm {group_url}: {e}")

            if browser:
                browser.close()
            else:
                context.close()

        return success
