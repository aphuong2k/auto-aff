"""
Group Health Checker & Ghost Group Detector
===========================================
Chấm điểm "sức khỏe" group Facebook trước khi Join hoặc Post:
- Quét các bài viết gần nhất trên bảng tin nhóm.
- Đo lường khoảng cách thời gian từ bài đăng gần nhất (phát hiện nhóm bỏ hoang / đóng băng).
- Đếm tương tác trung bình (reactions + comments).
- Đếm số người đăng khác nhau (loại bỏ nhóm bị 1-2 admin/spammer spam bài).
- Đánh giá xếp loại: HEALTHY (Tốt) / WARNING (Cảnh báo) / GHOST (Group ma).
- Cập nhật trực tiếp điểm sức khỏe vào CSDL.
"""

import os
import re
import time
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone

from database.db_manager import DatabaseManager

health_logger = logging.getLogger("GroupHealthChecker")
health_logger.setLevel(logging.INFO)


class GroupHealthChecker:
    """Đánh giá sức khỏe và phát hiện Group ma trên Facebook."""

    # Ngưỡng cấu hình đánh giá
    MAX_POST_AGE_HOURS_GHOST = 168.0   # > 7 ngày không bài mới -> phạt nặng
    MAX_POST_AGE_HOURS_WARNING = 72.0  # > 3 ngày không bài mới -> cảnh báo
    MIN_AVG_ENGAGEMENT_TARGET = 3.0    # Tối thiểu 3 tương tác/bài
    MIN_UNIQUE_POSTERS_TARGET = 3      # Tối thiểu 3 tác giả khác nhau

    def __init__(self, db: Optional[DatabaseManager] = None):
        self.db = db or DatabaseManager()

    @staticmethod
    def parse_relative_time_to_hours(text: str) -> Optional[float]:
        """
        Chuyển đổi chuỗi thời gian tương đối của Facebook (Việt/Anh) sang số giờ.
        Ví dụ: '1 giờ trước', '2 ngày', 'vừa xong', '30 phút', '5 tháng', '2 yrs', '3d'.
        """
        if not text:
            return None
        text_lower = text.strip().lower()

        # Vừa xong / just now
        if any(term in text_lower for term in ["vừa xong", "just now", "vừa đăng", "mới đây"]):
            return 0.1

        # Phút
        m_match = re.search(r'(\d+)\s*(phút|min|m\b)', text_lower)
        if m_match:
            try:
                return round(float(m_match.group(1)) / 60.0, 2)
            except ValueError:
                pass

        # Giờ
        h_match = re.search(r'(\d+)\s*(giờ|tiếng|hour|hr|h\b)', text_lower)
        if h_match:
            try:
                return float(h_match.group(1))
            except ValueError:
                pass

        # Hôm qua / yesterday
        if any(term in text_lower for term in ["hôm qua", "yesterday"]):
            return 24.0

        # Ngày
        d_match = re.search(r'(\d+)\s*(ngày|day|d\b)', text_lower)
        if d_match:
            try:
                return float(d_match.group(1)) * 24.0
            except ValueError:
                pass

        # Tuần
        w_match = re.search(r'(\d+)\s*(tuần|week|w\b)', text_lower)
        if w_match:
            try:
                return float(w_match.group(1)) * 168.0
            except ValueError:
                pass

        # Tháng
        mo_match = re.search(r'(\d+)\s*(tháng|month|mo\b)', text_lower)
        if mo_match:
            try:
                return float(mo_match.group(1)) * 720.0
            except ValueError:
                pass

        # Năm
        y_match = re.search(r'(\d+)\s*(năm|year|yr|y\b)', text_lower)
        if y_match:
            try:
                return float(y_match.group(1)) * 8760.0
            except ValueError:
                pass

        # Ngày cụ thể: '15 tháng 3 lúc 14:00' hoặc '15 Tháng 3'
        date_match = re.search(r'(\d{1,2})\s*tháng\s*(\d{1,2})', text_lower)
        if date_match:
            try:
                day = int(date_match.group(1))
                month = int(date_match.group(2))
                now = datetime.now()
                post_date = datetime(now.year, month, day)
                if post_date > now:
                    post_date = datetime(now.year - 1, month, day)
                diff_hours = (now - post_date).total_seconds() / 3600.0
                return round(diff_hours, 1)
            except Exception:
                pass

        return None

    @staticmethod
    def parse_count(text: str) -> float:
        """Trích xuất số lượng tương tác (reactions, bình luận) từ text."""
        if not text:
            return 0.0
        match = re.search(r'([\d\.,]+)\s*(k|k\+|tr|triệu|m)?', text.strip(), re.IGNORECASE)
        if match:
            num_part = match.group(1).replace(',', '.').strip()
            unit = (match.group(2) or '').lower()
            try:
                val = float(num_part)
                if 'tr' in unit or 'm' in unit or 'triệu' in unit:
                    return val * 1000000.0
                elif 'k' in unit:
                    return val * 1000.0
                else:
                    clean = match.group(1).replace('.', '').replace(',', '')
                    return float(clean)
            except Exception:
                pass
        return 0.0

    def compute_health_score(
        self,
        last_post_hours_ago: Optional[float],
        avg_engagement: float,
        unique_posters: int,
        total_posts_found: int
    ) -> Tuple[int, str]:
        """
        Tính điểm sức khỏe (0 - 100) và trả về xếp loại (HEALTHY / WARNING / GHOST).
        """
        # Nếu không tìm thấy bài nào trên bảng tin
        if total_posts_found == 0:
            return 20, "GHOST"

        score = 100

        # 1. Trừ điểm dựa trên khoảng cách bài viết gần nhất
        if last_post_hours_ago is None:
            score -= 20
        elif last_post_hours_ago > self.MAX_POST_AGE_HOURS_GHOST:  # > 7 ngày
            score -= 50
        elif last_post_hours_ago > self.MAX_POST_AGE_HOURS_WARNING:  # > 3 ngày
            score -= 25
        elif last_post_hours_ago > 24.0:  # > 1 ngày
            score -= 10

        # 2. Trừ điểm dựa trên tương tác trung bình
        if avg_engagement < 1.0:
            score -= 30
        elif avg_engagement < self.MIN_AVG_ENGAGEMENT_TARGET:
            score -= 15
        elif avg_engagement >= 10.0:
            score += 5  # Thưởng cho nhóm tương tác cao

        # 3. Trừ điểm dựa trên số lượng người đăng khác nhau (loại nhóm chỉ 1 người spam)
        if unique_posters <= 1 and total_posts_found >= 3:
            score -= 25
        elif unique_posters < self.MIN_UNIQUE_POSTERS_TARGET and total_posts_found >= 3:
            score -= 10

        # Giới hạn trong khoảng [0, 100]
        score = max(0, min(100, score))

        if score >= 60:
            verdict = "HEALTHY"
        elif score >= 35:
            verdict = "WARNING"
        else:
            verdict = "GHOST"

        return score, verdict

    def evaluate_page(self, page, group_url: str, scroll_times: int = 3) -> Dict:
        """
        Quét bảng tin của group thông qua Playwright page đã mở sẵn.
        Trích xuất bài đăng, thời gian, tương tác và tính điểm.
        """
        health_logger.info(f"🔍 Bắt đầu kiểm tra sức khỏe group: {group_url}")

        try:
            page.goto(group_url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
        except Exception as e:
            health_logger.warning(f"Không thể mở trang group {group_url}: {e}")
            return {
                "health_score": 10,
                "verdict": "GHOST",
                "last_post_hours_ago": 999.0,
                "avg_engagement": 0.0,
                "unique_posters": 0,
                "total_posts_scanned": 0,
                "error": str(e)
            }

        # Kiểm tra nội dung không khả dụng hoặc bị chặn
        body_text = page.locator("body").inner_text()
        if "Nội dung này hiện không khả dụng" in body_text or "This content isn't available" in body_text:
            health_logger.warning(f"Group {group_url} nội dung không khả dụng hoặc đã bị đóng!")
            return {
                "health_score": 0,
                "verdict": "GHOST",
                "last_post_hours_ago": 9999.0,
                "avg_engagement": 0.0,
                "unique_posters": 0,
                "total_posts_scanned": 0,
                "error": "CONTENT_UNAVAILABLE"
            }

        # Scroll nhẹ 2-3 lần để nạp các bài đăng
        for _ in range(scroll_times):
            page.evaluate("window.scrollBy(0, 1000)")
            page.wait_for_timeout(1500)

        # Trích xuất các bài viết (feed articles)
        # Facebook dùng role='article' hoặc div có data-pagelet='GroupFeed'
        articles = page.locator("div[role='article']").all()
        if not articles:
            articles = page.locator("div[data-pagelet*='FeedUnit']").all()

        total_posts_found = len(articles)
        health_logger.info(f"   Tìm thấy {total_posts_found} bài viết trên bảng tin nhóm.")

        post_ages_hours: List[float] = []
        engagements: List[float] = []
        posters: set = set()

        for idx, art in enumerate(articles[:10]):  # Lấy tối đa 10 bài
            try:
                art_text = art.inner_text()
                lines = [line.strip() for line in art_text.split("\n") if line.strip()]

                # Tìm tên tác giả (thường là dòng 1 hoặc 2)
                author = None
                for line in lines[:3]:
                    if len(line) > 2 and not any(k in line.lower() for k in ["phút", "giờ", "ngày", "thành viên", "quản trị viên", "thích", "bình luận"]):
                        author = line
                        break
                if author:
                    posters.add(author)

                # Tìm chuỗi thời gian đăng bài
                post_age = None
                for line in lines[:6]:
                    age = self.parse_relative_time_to_hours(line)
                    if age is not None:
                        post_age = age
                        break
                if post_age is not None:
                    post_ages_hours.append(post_age)

                # Tìm số lượng reactions & comments
                reacts = 0.0
                comments = 0.0
                for line in lines[-8:]:
                    line_lower = line.lower()
                    if "bình luận" in line_lower or "comments" in line_lower:
                        comments = self.parse_count(line)
                    elif any(icon in line for icon in ["👍", "❤️", "😆", "😮", "😢", "😡"]) or "thích" in line_lower:
                        reacts = self.parse_count(line)
                engagements.append(reacts + comments)

            except Exception as e:
                health_logger.debug(f"Lỗi phân tích bài viết #{idx}: {e}")

        # Tính toán các chỉ số
        last_post_hours_ago = min(post_ages_hours) if post_ages_hours else None
        avg_engagement = round(sum(engagements) / max(1, len(engagements)), 1) if engagements else 0.0
        unique_posters = len(posters)

        score, verdict = self.compute_health_score(
            last_post_hours_ago=last_post_hours_ago,
            avg_engagement=avg_engagement,
            unique_posters=unique_posters,
            total_posts_found=total_posts_found
        )

        health_logger.info(
            f"   📊 Kết quả: Score={score} ({verdict}) | Bài mới nhất: {last_post_hours_ago}h trước | "
            f"Tương tác TB: {avg_engagement} | Tác giả: {unique_posters}"
        )

        return {
            "health_score": score,
            "verdict": verdict,
            "last_post_hours_ago": last_post_hours_ago,
            "avg_engagement": avg_engagement,
            "unique_posters": unique_posters,
            "total_posts_scanned": total_posts_found
        }

    def evaluate_and_save(self, group_id: str, group_url: str, page=None) -> Dict:
        """
        Đánh giá sức khỏe group và lưu ngay kết quả vào CSDL.
        Nếu page=None, sẽ tự mở Playwright context độc lập.
        """
        if page is not None:
            metrics = self.evaluate_page(page, group_url)
        else:
            metrics = self._evaluate_with_new_browser(group_url)

        # Cập nhật CSDL
        last_active = None
        if metrics.get("last_post_hours_ago") is not None:
            from datetime import timedelta
            approx_active = datetime.now() - timedelta(hours=metrics["last_post_hours_ago"])
            last_active = approx_active.strftime("%Y-%m-%d %H:%M:%S")

        self.db.update_group_health(
            group_id=group_id,
            health_score=metrics["health_score"],
            avg_engagement=metrics.get("avg_engagement", 0.0),
            last_active_at=last_active,
            unique_posters=metrics.get("unique_posters", 0),
            health_verdict=metrics.get("verdict", "UNKNOWN")
        )

        return metrics

    def _evaluate_with_new_browser(self, group_url: str) -> Dict:
        """Mở trình duyệt Playwright tạm thời để đánh giá group."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise RuntimeError("Chưa cài đặt Playwright!")

        fb_cookie = os.getenv("FB_COOKIE", "")
        fb_profile = os.getenv("FB_CHROME_PROFILE", "")

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
            metrics = self.evaluate_page(page, group_url)

            if browser:
                browser.close()
            else:
                context.close()

            return metrics
