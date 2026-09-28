"""
Post Approval Monitor & Anti-Rejection Blacklist
=================================================
Theo dõi và kiểm tra xem bài viết đăng lên Group Facebook có được Admin duyệt hay không:
1. Quét các bài viết trong lịch sử 'post_history' và 'posted_logs' có trạng thái chờ duyệt hoặc mới đăng.
2. Truy cập feed của group qua Playwright để xác định:
   - Bài viết đã xuất hiện trên bảng tin -> Đánh dấu 'APPROVED', reset chuỗi bị từ chối / chờ duyệt.
   - Bài viết đang bị chờ duyệt (Admin giữ duyệt / thông báo pending) -> Đánh dấu 'PENDING', tăng strike.
   - Bài viết không tìm thấy sau 24h hoặc bị xóa / từ chối -> Đánh dấu 'REJECTED', tăng strike.
3. Nếu 1 nhóm liên tục BỊ CHỜ DUYỆT hoặc TỪ CHỐI 2 BÀI VIẾT (threshold >= 2):
   -> Tự động đánh dấu 'posting_restricted = 1' (Ngừng đăng bài vào nhóm này).
   -> Tự động RỜI NHÓM (Auto-Leave) ngay lập tức trên Playwright session, không tốn thời gian với nhóm chặn affiliate!
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
    """Kiểm tra tình trạng duyệt bài trên Facebook Group và tự động out group nếu bị chờ duyệt hoặc từ chối nhiều lần."""

    MAX_CONSECUTIVE_REJECTIONS = 2  # Bị chờ duyệt hoặc từ chối 2 lần liên tiếp -> Tự động RỜI NHÓM (Auto-Leave)
    CHECK_AFTER_HOURS = 2.0         # Có thể bắt đầu rà soát sau khi đăng 2 giờ
    REJECTION_TIMEOUT_HOURS = 24.0  # Sau 24h không thấy xuất hiện trên feed và không pending -> Coi như bị từ chối

    def __init__(self, db: Optional[DatabaseManager] = None):
        self.db = db or DatabaseManager()
        self.feedback_monitor = JoinFeedbackMonitor(self.db)

    def check_pending_approvals(self, auto_leave_on_blacklist: bool = True, max_strikes: int = 2, account_id: Optional[object] = None) -> Dict:
        """
        Quét các bài đăng gần đây lên FB Group và kiểm tra xem có được duyệt không.
        Nếu bị chờ duyệt hoặc từ chối liên tiếp >= max_strikes (mặc định 2 lần) thì TỰ ĐỘNG OUT GROUP!
        """
        from modules.outreach.fb_account_manager import resolve_fb_account
        acc, fb_cookie, fb_profile = resolve_fb_account(self.db, account_id=account_id, allow_rotation=False)
        acc_name = acc.get("name") if acc else "Nick Facebook"
        post_mon_logger.info(f"🔎 Kiểm tra duyệt bài Facebook bằng tài khoản: [{acc_name}]")

        if not fb_cookie and not fb_profile:
            raise RuntimeError("Chưa cấu hình thông tin đăng nhập Facebook!")

        threshold = max_strikes or self.MAX_CONSECUTIVE_REJECTIONS

        # Lấy danh sách các bài đăng FB_GROUP cần kiểm tra duyệt từ post_history và posted_logs
        posts_to_check = []
        with self.db.get_connection() as conn:
            # 1. Từ post_history
            ph_rows = conn.execute("""
                SELECT ph.id, ph.target_id as group_id, ph.deal_id, ph.content, ph.posted_at, 
                       ph.approval_status, ph.status as raw_status, g.name as group_name, g.url as group_url,
                       COALESCE(g.consecutive_rejections, 0) as consecutive_rejections,
                       COALESCE(g.pending_approval_count, 0) as pending_approval_count,
                       'post_history' as source_table
                FROM post_history ph
                JOIN fb_groups g ON ph.target_id = g.group_id
                WHERE ph.target_type = 'FB_GROUP'
                  AND (ph.approval_status = 'PENDING' OR ph.approval_status IS NULL)
                  AND g.status != 'LEFT'
                ORDER BY ph.posted_at DESC
                LIMIT 25
            """).fetchall()
            posts_to_check.extend([dict(r) for r in ph_rows])

            # 2. Từ posted_logs (nếu có các bài post thực tế)
            pl_rows = conn.execute("""
                SELECT pl.id, g.group_id, pl.item_id as deal_id, pl.content_snippet as content, pl.posted_at,
                       pl.approval_status, pl.status as raw_status, g.name as group_name, g.url as group_url,
                       COALESCE(g.consecutive_rejections, 0) as consecutive_rejections,
                       COALESCE(g.pending_approval_count, 0) as pending_approval_count,
                       'posted_logs' as source_table
                FROM posted_logs pl
                JOIN fb_groups g ON (
                    g.url = pl.group_url 
                    OR pl.group_url LIKE '%' || g.group_id || '%' 
                    OR g.name = pl.group_name
                )
                WHERE pl.type = 'POST'
                  AND (pl.approval_status = 'PENDING' OR (pl.approval_status IS NULL AND pl.status IN ('PENDING_APPROVAL', 'SUCCESS')))
                  AND g.status != 'LEFT'
                ORDER BY pl.posted_at DESC
                LIMIT 25
            """).fetchall()

            existing_keys = {(p["group_id"], self._get_content_fingerprint(p["content"])) for p in posts_to_check}
            for pl in pl_rows:
                d = dict(pl)
                k = (d["group_id"], self._get_content_fingerprint(d["content"]))
                if k not in existing_keys:
                    posts_to_check.append(d)
                    existing_keys.add(k)

        if not posts_to_check:
            post_mon_logger.info("Không có bài đăng Facebook nào đang chờ kiểm tra duyệt.")
            return {"total": 0, "approved": 0, "rejected": 0, "still_pending": 0, "groups_restricted": 0, "groups_left": 0}

        post_mon_logger.info(f"📝 Bắt đầu kiểm tra {len(posts_to_check)} bài đăng xem đã được duyệt chưa (Ngưỡng tự out: {threshold} lần)...")

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

            # Nhóm các bài viết theo group để chỉ tải trang group 1 lần
            groups_cache: Dict[str, Dict] = {}

            for post in posts_to_check:
                post_id = post["id"]
                group_id = post["group_id"]
                group_name = post.get("group_name", "Group")
                group_url = post["group_url"]
                content = post.get("content", "")
                posted_at = post.get("posted_at")
                raw_status = post.get("raw_status") or ""
                src_table = post.get("source_table", "post_history")

                # Lấy trích đoạn ngắn của nội dung bài viết
                snippet = self._get_content_fingerprint(content)
                post_mon_logger.info(f"🔍 Kiểm tra bài post #{post_id} tại nhóm [{group_name}] - Trích đoạn: '{snippet}'")

                try:
                    # Nạp feed của nhóm nếu chưa nạp trong phiên này
                    if group_url not in groups_cache:
                        page.goto(group_url, timeout=35000, wait_until="domcontentloaded")
                        page.wait_for_timeout(3000)
                        # Scroll 2 lần để nạp các bài mới nhất
                        page.evaluate("window.scrollBy(0, 1500)")
                        page.wait_for_timeout(1500)
                        page.evaluate("window.scrollBy(0, 1500)")
                        page.wait_for_timeout(1500)

                        feed_text = page.locator("body").inner_text()
                        feed_lower = feed_text.lower()

                        # Nhận diện thông báo bài viết đang chờ phê duyệt trên giao diện Facebook
                        has_pending_notice = any(term in feed_lower for term in [
                            "bài viết của bạn đang chờ phê duyệt",
                            "1 bài viết đang chờ phê duyệt",
                            "bài viết đang chờ phê duyệt",
                            "bài viết đang chờ",
                            "đang chờ phê duyệt",
                            "pending approval",
                            "chờ phê duyệt",
                            "quản lý bài viết đang chờ",
                            "your post is pending approval"
                        ])

                        groups_cache[group_url] = {
                            "feed_text": feed_text,
                            "has_pending_notice": has_pending_notice,
                            "is_left": False
                        }
                    else:
                        feed_text = groups_cache[group_url]["feed_text"]
                        has_pending_notice = groups_cache[group_url]["has_pending_notice"]

                    # Nếu group này vừa mới bị out trong vòng lặp trước thì bỏ qua các bài còn lại
                    if groups_cache[group_url].get("is_left"):
                        post_mon_logger.info(f"Nhóm [{group_name}] đã được out group, bỏ qua check bài #{post_id}.")
                        continue

                    # 1. Kiểm tra xem snippet có xuất hiện trên feed công khai của nhóm không
                    is_visible_on_feed = bool(snippet and snippet in feed_text)

                    # Tính thời gian đã trôi qua kể từ khi đăng
                    hours_since_post = 0.0
                    if posted_at:
                        try:
                            clean_time = str(posted_at).replace("Z", "+00:00")
                            post_time = datetime.fromisoformat(clean_time)
                            if post_time.tzinfo is None:
                                post_time = post_time.replace(tzinfo=timezone.utc)
                            hours_since_post = (datetime.now(timezone.utc) - post_time).total_seconds() / 3600.0
                        except Exception:
                            pass

                    # TRƯỜNG HỢP 1: BÀI ĐÃ ĐƯỢC DUYỆT CÔNG KHAI
                    if is_visible_on_feed:
                        post_mon_logger.info(f"✅ Bài viết #{post_id} ĐÃ ĐƯỢC DUYỆT công khai trên nhóm [{group_name}]!")
                        self.db.update_post_approval_status(post_id, "APPROVED", source_table=src_table)
                        self.db.reset_group_post_rejections(group_id)
                        results["approved"] += 1

                    # TRƯỜNG HỢP 2: BÀI BỊ CHỜ DUYỆT (Admin giữ kiểm duyệt / có banner pending)
                    elif has_pending_notice or raw_status == "PENDING_APPROVAL":
                        post_mon_logger.warning(
                            f"⏳ Bài viết #{post_id} BỊ CHỜ DUYỆT tại nhóm [{group_name}] (Admin đang giữ xét duyệt)."
                        )
                        self.db.update_post_approval_status(post_id, "PENDING", source_table=src_table)
                        results["still_pending"] += 1

                        # Ghi nhận số lần bị giữ chờ duyệt liên tiếp
                        is_restricted = self.db.record_group_post_rejection(
                            group_id,
                            max_consecutive_rejections=threshold,
                            reason="PENDING"
                        )

                        if is_restricted:
                            results["groups_restricted"] += 1
                            post_mon_logger.warning(
                                f"🚫 [HẠN CHẾ NHÓM]: Nhóm [{group_name}] liên tục BỊ CHỜ DUYỆT ({threshold} bài liên tiếp). "
                                f"Đã đánh dấu posting_restricted=1 (Ngừng đăng bài aff)!"
                            )

                            if auto_leave_on_blacklist:
                                post_mon_logger.info(f"🚪 [AUTO-LEAVE]: Đang tự động rời nhóm [{group_name}] do bị giữ chờ duyệt nhiều lần...")
                                try:
                                    left = self.feedback_monitor.leave_group(group_url, page=page)
                                    self.db.update_group_status(group_id, "LEFT")
                                    with self.db.get_connection() as conn:
                                        conn.execute(
                                            "UPDATE fb_groups SET health_verdict = 'PENDING_OUT', enabled = 0 WHERE group_id = ?",
                                            (group_id,)
                                        )
                                        conn.commit()
                                    results["groups_left"] += 1
                                    groups_cache[group_url]["is_left"] = True
                                    post_mon_logger.info(f"🚪 Đã tự động out nhóm [{group_name}] thành công!")
                                except Exception as e_leave:
                                    post_mon_logger.warning(f"Không thể tự động rời nhóm: {e_leave}")

                    # TRƯỜNG HỢP 3: BÀI BỊ TỪ CHỐI / XÓA / TIMEOUT SAU 24H
                    elif hours_since_post >= self.REJECTION_TIMEOUT_HOURS or hours_since_post >= self.CHECK_AFTER_HOURS:
                        post_mon_logger.warning(
                            f"❌ Bài viết #{post_id} không xuất hiện sau {hours_since_post:.1f}h trên nhóm [{group_name}]. Đánh dấu REJECTED."
                        )
                        self.db.update_post_approval_status(post_id, "REJECTED", source_table=src_table)
                        results["rejected"] += 1

                        # Ghi nhận số lần bị từ chối liên tiếp
                        is_restricted = self.db.record_group_post_rejection(
                            group_id,
                            max_consecutive_rejections=threshold,
                            reason="REJECTED"
                        )

                        if is_restricted:
                            results["groups_restricted"] += 1
                            post_mon_logger.warning(
                                f"🚫 [HẠN CHẾ NHÓM]: Nhóm [{group_name}] đã TỪ CHỐI {threshold} bài viết liên tiếp. "
                                f"Đã đánh dấu posting_restricted=1 (Ngừng đăng bài)!"
                            )

                            if auto_leave_on_blacklist:
                                post_mon_logger.info(f"🚪 [AUTO-LEAVE]: Đang tự động rời nhóm [{group_name}] do liên tục bị từ chối bài...")
                                try:
                                    left = self.feedback_monitor.leave_group(group_url, page=page)
                                    self.db.update_group_status(group_id, "LEFT")
                                    with self.db.get_connection() as conn:
                                        conn.execute(
                                            "UPDATE fb_groups SET health_verdict = 'REJECTED_OUT', enabled = 0 WHERE group_id = ?",
                                            (group_id,)
                                        )
                                        conn.commit()
                                    results["groups_left"] += 1
                                    groups_cache[group_url]["is_left"] = True
                                    post_mon_logger.info(f"🚪 Đã tự động out nhóm [{group_name}] thành công!")
                                except Exception as e_leave:
                                    post_mon_logger.warning(f"Không thể tự động rời nhóm: {e_leave}")
                    else:
                        post_mon_logger.info(
                            f"⏳ Bài viết #{post_id} mới đăng {hours_since_post:.1f}h (< {self.CHECK_AFTER_HOURS}h). Giữ trạng thái PENDING."
                        )
                        results["still_pending"] += 1

                except Exception as e:
                    post_mon_logger.error(f"Lỗi kiểm tra bài viết #{post_id}: {e}")

            if browser:
                browser.close()
            else:
                context.close()

        post_mon_logger.info(
            f"🏁 Hoàn thành kiểm tra duyệt bài: Approved={results['approved']}, "
            f"Still Pending={results['still_pending']}, Rejected={results['rejected']}, "
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
