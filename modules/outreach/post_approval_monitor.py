"""
Post Approval Monitor & Anti-Rejection Blacklist
=================================================
Theo dõi và kiểm tra xem bài viết đăng lên Group Facebook có được Admin duyệt hay không:
1. Quét các bài viết trong lịch sử 'post_history' có status='SUCCESS' hoặc approval_status='PENDING'.
2. Truy cập feed của group qua Playwright để xác định:
   - Bài viết đã xuất hiện trên bảng tin -> Đánh dấu 'APPROVED', reset chuỗi bị từ chối.
   - Bài viết vẫn đang chờ Admin duyệt -> Giữ 'PENDING'.
   - Bài viết không tìm thấy sau 24h hoặc bị xóa/từ chối -> Đánh dấu 'REJECTED'.
3. Nếu 1 nhóm liên tục TỪ CHỐI 3 BÀI VIẾT:
   -> Tự động đánh dấu 'posting_restricted = 1' (Ngừng đăng bài vào nhóm này).
   -> Tự động RỜI NHÓM (Auto-Leave) nếu được cấu hình, không tốn thời gian với nhóm chặn aff.
"""

import os
import time
import logging
from typing import Dict, List, Optional
from datetime import datetime, timezone

from database.db_manager import DatabaseManager
from modules.outreach.join_feedback_monitor import JoinFeedbackMonitor

post_mon_logger = logging.getLogger("PostApprovalMonitor")
post_mon_logger.setLevel(logging.INFO)


class PostApprovalMonitor:
    """Kiểm tra tình trạng duyệt bài trên Facebook Group và xử lý group từ chối bài."""

    MAX_CONSECUTIVE_REJECTIONS = 3  # Bị từ chối 3 lần liên tiếp -> Hạn chế / Rời nhóm
    CHECK_AFTER_HOURS = 12.0        # Kiểm tra sau khi đăng ít nhất 12 giờ
    REJECTION_TIMEOUT_HOURS = 48.0  # Sau 48h không thấy xuất hiện -> Coi như bị từ chối

    def __init__(self, db: Optional[DatabaseManager] = None):
        self.db = db or DatabaseManager()
        self.feedback_monitor = JoinFeedbackMonitor(self.db)

    def check_pending_approvals(self, auto_leave_on_blacklist: bool = True) -> Dict:
        """
        Quét các bài đăng gần đây lên FB Group và kiểm tra xem có được duyệt không.
        """
        fb_cookie = os.getenv("FB_COOKIE", "")
        fb_profile = os.getenv("FB_CHROME_PROFILE", "")

        if not fb_cookie and not fb_profile:
            raise RuntimeError("Chưa cấu hình thông tin đăng nhập Facebook!")

        # Lấy danh sách các bài đăng FB_GROUP cần kiểm tra duyệt
        with self.db.get_connection() as conn:
            rows = conn.execute("""
                SELECT ph.id, ph.target_id as group_id, ph.deal_id, ph.content, ph.posted_at, 
                       ph.approval_status, g.name as group_name, g.url as group_url,
                       g.consecutive_rejections
                FROM post_history ph
                JOIN fb_groups g ON ph.target_id = g.group_id
                WHERE ph.target_type = 'FB_GROUP'
                  AND (ph.approval_status = 'PENDING' OR ph.approval_status IS NULL)
                ORDER BY ph.posted_at DESC
                LIMIT 20
            """).fetchall()
            posts_to_check = [dict(r) for r in rows]

        if not posts_to_check:
            post_mon_logger.info("Không có bài đăng Facebook nào đang chờ kiểm tra duyệt.")
            return {"total": 0, "approved": 0, "rejected": 0, "still_pending": 0, "groups_restricted": 0}

        post_mon_logger.info(f"📝 Bắt đầu kiểm tra {len(posts_to_check)} bài đăng xem đã được duyệt chưa...")

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise RuntimeError("Chưa cài đặt Playwright!")

        results = {
            "total": len(posts_to_check),
            "approved": 0,
            "rejected": 0,
            "still_pending": 0,
            "groups_restricted": 0,
            "groups_left": 0
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

            # Nhóm các bài viết theo group để tối ưu số lần tải trang
            groups_cache: Dict[str, str] = {}

            for post in posts_to_check:
                post_id = post["id"]
                group_id = post["group_id"]
                group_name = post.get("group_name", "Group")
                group_url = post["group_url"]
                content = post.get("content", "")
                posted_at = post.get("posted_at")

                # Lấy 1 trích đoạn ngắn của nội dung bài viết để tìm kiếm (15-25 ký tự đặc trưng)
                snippet = self._get_content_fingerprint(content)

                post_mon_logger.info(f"🔍 Kiểm tra bài post #{post_id} tại nhóm [{group_name}] - Trích đoạn: '{snippet}'")

                try:
                    # Nạp feed của nhóm (nếu chưa nạp)
                    if group_url not in groups_cache:
                        page.goto(group_url, timeout=35000, wait_until="domcontentloaded")
                        page.wait_for_timeout(3000)
                        # Scroll 2 lần để nạp các bài mới nhất
                        page.evaluate("window.scrollBy(0, 1500)")
                        page.wait_for_timeout(1500)
                        feed_text = page.locator("body").inner_text()
                        groups_cache[group_url] = feed_text
                    else:
                        feed_text = groups_cache[group_url]

                    # 1. Kiểm tra xem snippet có xuất hiện trên feed của nhóm không
                    is_visible_on_feed = bool(snippet and snippet in feed_text)

                    # Tính thời gian đã trôi qua kể từ khi đăng
                    hours_since_post = 0.0
                    if posted_at:
                        try:
                            post_time = datetime.fromisoformat(posted_at.replace("Z", "+00:00"))
                            hours_since_post = (datetime.now(timezone.utc) - post_time).total_seconds() / 3600.0
                        except Exception:
                            pass

                    if is_visible_on_feed:
                        post_mon_logger.info(f"✅ Bài viết #{post_id} đã được DUYỆT hiển thị trên nhóm [{group_name}]!")
                        self.db.update_post_approval_status(post_id, "APPROVED")
                        self.db.reset_group_post_rejections(group_id)
                        results["approved"] += 1

                    elif hours_since_post >= self.REJECTION_TIMEOUT_HOURS:
                        # Quá 48h không thấy xuất hiện trên feed -> Đã bị từ chối
                        post_mon_logger.warning(
                            f"❌ Bài viết #{post_id} không xuất hiện sau {hours_since_post:.1f}h. Đánh dấu REJECTED."
                        )
                        self.db.update_post_approval_status(post_id, "REJECTED")
                        results["rejected"] += 1

                        # Ghi nhận số lần bị từ chối liên tiếp của group
                        is_restricted = self.db.record_group_post_rejection(
                            group_id, 
                            max_consecutive_rejections=self.MAX_CONSECUTIVE_REJECTIONS
                        )

                        if is_restricted:
                            results["groups_restricted"] += 1
                            post_mon_logger.warning(
                                f"🚫 [HẠN CHẾ NHÓM]: Nhóm [{group_name}] đã từ chối {self.MAX_CONSECUTIVE_REJECTIONS} bài viết liên tiếp. "
                                f"Đã đánh dấu posting_restricted=1 (Ngừng đăng bài)!"
                            )

                            if auto_leave_on_blacklist:
                                post_mon_logger.info(f"🚪 Tự động rời nhóm [{group_name}] do liên tục từ chối bài...")
                                try:
                                    left = self.feedback_monitor.cancel_pending_request(page)
                                    if not left:
                                        self.feedback_monitor.leave_group(group_url)
                                    self.db.update_group_status(group_id, "LEFT")
                                    results["groups_left"] += 1
                                    post_mon_logger.info(f"🚪 Đã rời nhóm [{group_name}] thành công.")
                                except Exception as e_leave:
                                    post_mon_logger.warning(f"Không thể tự động rời nhóm: {e_leave}")
                    else:
                        post_mon_logger.info(
                            f"⏳ Bài viết #{post_id} chưa thấy xuất hiện (mới đăng {hours_since_post:.1f}h). Giữ trạng thái PENDING."
                        )
                        results["still_pending"] += 1

                except Exception as e:
                    post_mon_logger.error(f"Lỗi kiểm tra bài viết #{post_id}: {e}")

            if browser:
                browser.close()
            else:
                context.close()

        post_mon_logger.info(
            f"🏁 Hoàn thành kiểm tra bài đăng: Approved={results['approved']}, "
            f"Rejected={results['rejected']}, Pending={results['still_pending']}, "
            f"Restricted={results['groups_restricted']}, Left={results['groups_left']}"
        )
        return results

    @staticmethod
    def _get_content_fingerprint(content: str) -> str:
        """
        Trích xuất một đoạn text đặc trưng từ bài viết (bỏ icon, link) để tìm kiếm trên feed.
        """
        if not content:
            return ""
        lines = [line.strip() for line in content.split("\n") if line.strip()]
        for line in lines:
            # Chọn dòng có chữ thật, không chứa http và độ dài vừa phải
            if "http" not in line and len(line) >= 15:
                # Làm sạch icon cơ bản
                clean = "".join(c for c in line if c.isalnum() or c.isspace() or c in ",.-")
                clean = clean.strip()
                if len(clean) >= 12:
                    return clean[:30]
        return ""
