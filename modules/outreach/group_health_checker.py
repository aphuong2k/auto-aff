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

import config.settings
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
        total_posts_found: int,
        real_members: Optional[int] = None,
        is_private: bool = False
    ) -> Tuple[int, str]:
        """
        Tính điểm sức khỏe (0 - 100) và trả về xếp loại (HEALTHY / WARNING / GHOST).
        Có kiểm tra số lượng thành viên thực tế và trạng thái nhóm.
        """
        # Nếu không tìm thấy bài nào trên bảng tin
        if total_posts_found == 0:
            if real_members is not None and real_members < 500:
                return 15, "GHOST"
            return 25, "GHOST"

        score = 100

        # Phạt nặng nhóm quy mô quá nhỏ (group ma hoặc group tự tạo ít tương tác)
        if real_members is not None:
            if real_members < 100:
                score -= 45
            elif real_members < 500:
                score -= 25
            elif real_members >= 10000:
                score += 5

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
            score -= 25
        elif avg_engagement < self.MIN_AVG_ENGAGEMENT_TARGET:
            score -= 15
        elif avg_engagement >= 10.0:
            score += 5  # Thưởng cho nhóm tương tác cao

        # 3. Trừ điểm dựa trên số lượng người đăng khác nhau (loại nhóm chỉ 1 người spam)
        if unique_posters <= 1 and total_posts_found >= 3:
            score -= 20
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
        Trích xuất bài đăng, thời gian, tương tác, số thành viên thực tế và tính điểm.
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

        # Trích xuất số lượng thành viên thực tế từ trang
        real_members = None
        m_match = re.search(r'([\d\.,]+)\s*(k|m|triệu|nghìn)?\s*(?:thành viên|members)', body_text, re.I)
        if m_match:
            try:
                num_part = m_match.group(1).replace(',', '.').strip()
                unit = (m_match.group(2) or '').lower()
                if 'm' in unit or 'triệu' in unit:
                    real_members = int(float(num_part) * 1000000)
                elif 'k' in unit or 'nghìn' in unit:
                    real_members = int(float(num_part) * 1000)
                else:
                    clean = m_match.group(1).replace('.', '').replace(',', '')
                    real_members = int(clean)
            except Exception:
                pass

        is_member = any(term in body_text for term in ["Đã tham gia", "Joined"])
        can_join = any(term in body_text for term in ["Tham gia nhóm", "Join group"])
        is_private = any(term in body_text for term in ["Nhóm Riêng tư", "Private group", "Chỉ thành viên mới nhìn thấy", "Only members can see"])

        # Scroll nhẹ 2-3 lần để nạp các bài đăng
        for _ in range(scroll_times):
            page.evaluate("window.scrollBy(0, 1000)")
            page.wait_for_timeout(1200)

        post_ages_hours: List[float] = []
        engagements: List[float] = []
        posters: set = set()
        total_posts_found = 0

        # Kiểm tra bảng tin feed Facebook hiện đại
        feed = page.locator("div[role='feed']").first
        feed_abbrs = []
        if feed.count() > 0:
            feed_abbrs = feed.locator("abbr").all()

        if feed_abbrs:
            total_posts_found = len(feed_abbrs)
            health_logger.info(f"   Tìm thấy {total_posts_found} bài viết trong feed qua thẻ abbr.")
            for ab in feed_abbrs[:10]:
                try:
                    time_label = ab.get_attribute("aria-label") or ab.inner_text() or ""
                    age = self.parse_relative_time_to_hours(time_label)
                    if age is not None:
                        post_ages_hours.append(age)

                    post_meta = ab.evaluate("""(el) => {
                        let curr = el;
                        while (curr && curr.parentElement && curr.parentElement.getAttribute('role') !== 'feed' && curr.tagName !== 'BODY') {
                            curr = curr.parentElement;
                        }
                        if (!curr) return {author: '', likes: 0, comments: 0};

                        let author = '';
                        const authorEl = curr.querySelector('h2, h3, h4, strong');
                        if (authorEl) author = authorEl.innerText.trim();

                        let likes = 0;
                        let comments = 0;
                        const ariaEls = curr.querySelectorAll('[aria-label]');
                        for (const a of ariaEls) {
                            const label = a.getAttribute('aria-label') || '';
                            if (label.includes('người') || label.includes('thích') || label.includes('cảm xúc')) {
                                const m = label.match(/([0-9\\.,]+)/);
                                if (m) likes = Math.max(likes, parseFloat(m[1].replace(',', '.')));
                            }
                            if (label.includes('bình luận') || label.includes('comment')) {
                                const m = label.match(/([0-9\\.,]+)/);
                                if (m) comments = Math.max(comments, parseFloat(m[1].replace(',', '.')));
                            }
                        }
                        return {author, likes, comments};
                    }""")

                    if post_meta.get("author"):
                        posters.add(post_meta["author"])
                    engagements.append(post_meta.get("likes", 0.0) + post_meta.get("comments", 0.0))
                except Exception as e:
                    health_logger.debug(f"Lỗi phân tích bài viết qua feed abbr: {e}")
        else:
            # Fallback nếu không có role=feed (layout cũ)
            articles = page.locator("div[role='article']").all()
            if not articles:
                articles = page.locator("div[data-pagelet*='FeedUnit'], div[data-ad-preview='message']").all()

            total_posts_found = len(articles)
            health_logger.info(f"   Tìm thấy {total_posts_found} bài viết theo fallback selector.")

            for idx, art in enumerate(articles[:10]):
                try:
                    art_text = art.inner_text()
                    lines = [line.strip() for line in art_text.split("\n") if line.strip()]

                    author = None
                    for line in lines[:3]:
                        if len(line) > 2 and not any(k in line.lower() for k in ["phút", "giờ", "ngày", "thành viên", "quản trị viên", "thích", "bình luận"]):
                            author = line
                            break
                    if author:
                        posters.add(author)

                    post_age = None
                    for line in lines[:6]:
                        age = self.parse_relative_time_to_hours(line)
                        if age is not None:
                            post_age = age
                            break
                    if post_age is not None:
                        post_ages_hours.append(post_age)

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
            total_posts_found=total_posts_found,
            real_members=real_members,
            is_private=is_private
        )

        health_logger.info(
            f"   📊 Kết quả: Score={score} ({verdict}) | TV thực tế: {real_members} | Bài mới nhất: {last_post_hours_ago}h trước | "
            f"Tương tác TB: {avg_engagement} | Tác giả: {unique_posters}"
        )

        return {
            "health_score": score,
            "verdict": verdict,
            "last_post_hours_ago": last_post_hours_ago,
            "avg_engagement": avg_engagement,
            "unique_posters": unique_posters,
            "total_posts_scanned": total_posts_found,
            "real_members": real_members,
            "is_member": is_member,
            "can_join": can_join,
            "is_private": is_private
        }

    def evaluate_and_save(self, group_id: str, group_url: str, page=None, account_id: Optional[object] = None) -> Dict:
        """
        Đánh giá sức khỏe group và lưu ngay kết quả vào CSDL.
        Nếu page=None, sẽ tự mở Playwright context độc lập với tài khoản được chỉ định.
        """
        if page is not None:
            metrics = self.evaluate_page(page, group_url)
        else:
            metrics = self._evaluate_with_new_browser(group_url, account_id=account_id)

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

        # Cập nhật số thành viên thực tế nếu trích xuất được
        if metrics.get("real_members") is not None:
            with self.db.get_connection() as conn:
                conn.execute(
                    "UPDATE fb_groups SET members_count = ? WHERE group_id = ?",
                    (metrics["real_members"], group_id)
                )
                conn.commit()

        # Tự động loại trừ Group ma khỏi hàng đợi đăng bài (status='LEFT', enabled=0)
        if metrics.get("verdict") == "GHOST" or metrics.get("health_score", 100) < 35:
            with self.db.get_connection() as conn:
                conn.execute(
                    "UPDATE fb_groups SET status = 'LEFT', enabled = 0 WHERE group_id = ?",
                    (group_id,)
                )
                conn.commit()

        return metrics

    def batch_evaluate_groups(self, groups: List[Dict], max_check: int = 10, account_id: Optional[object] = None) -> List[Dict]:
        """
        Đánh giá nhiều nhóm Facebook bằng 1 phiên Playwright duy nhất để tối ưu tốc độ và quét chuẩn xác.
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise RuntimeError("Chưa cài đặt Playwright!")

        from modules.outreach.fb_account_manager import resolve_fb_account
        acc, fb_cookie, fb_profile = resolve_fb_account(self.db, account_id=account_id, allow_rotation=False)
        acc_name = acc.get("name") if acc else "Nick Facebook"
        health_logger.info(f"🛡️ Quét live sức khỏe nhóm bằng tài khoản: [{acc_name}]")
        results = []

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
            for g in groups[:max_check]:
                gid = str(g["group_id"])
                url = g["url"]
                health_logger.info(f"Auditing group [{g.get('name')}] ({url})...")
                res = self.evaluate_and_save(gid, url, page=page)
                res["group_id"] = gid
                res["name"] = g.get("name")
                results.append(res)

            if browser:
                browser.close()
            else:
                context.close()

        return results

    def _evaluate_with_new_browser(self, group_url: str, account_id: Optional[object] = None) -> Dict:
        """Mở trình duyệt Playwright tạm thời để đánh giá group."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise RuntimeError("Chưa cài đặt Playwright!")

        from modules.outreach.fb_account_manager import resolve_fb_account
        acc, fb_cookie, fb_profile = resolve_fb_account(self.db, account_id=account_id, allow_rotation=False)

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

