import os
import logging
import urllib.parse
from typing import List, Dict

from config.settings import MIN_GROUP_MEMBERS
from config.categories_filter import (
    CATEGORY_GROUP_KEYWORDS,
    GENERAL_SHOPPING_GROUP_KEYWORDS,
    translate_category
)
from database.db_manager import DatabaseManager
from modules.outreach.group_keyword_learner import GroupKeywordLearner
from modules.outreach.group_health_checker import GroupHealthChecker

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

class FacebookGroupFinder:
    """Module tự động tìm kiếm Group Facebook THẬT liên quan theo ngành hàng (kèm kiểm tra tương tác và bài đăng gần nhất)"""

    def __init__(self, db: DatabaseManager = None):
        self.db = db or DatabaseManager()
        self.keyword_learner = GroupKeywordLearner(self.db)
        self.health_checker = GroupHealthChecker(self.db)

    @staticmethod
    def _parse_members_count(text: str) -> int:
        """Trích xuất số lượng thành viên thực tế từ chuỗi hiển thị của Facebook (không gán giá trị ảo)"""
        import re
        if not text:
            return 0
        match = re.search(r'([\d\.,]+)\s*(k|k\+|tr|triệu|m|m\+)?\s*(thành viên|members|người tham gia)', text, re.IGNORECASE)
        if match:
            num_part = match.group(1).replace(',', '.').strip()
            unit = (match.group(2) or '').lower()
            try:
                val = float(num_part)
                if 'tr' in unit or 'm' in unit or 'triệu' in unit:
                    return int(val * 1000000)
                elif 'k' in unit:
                    return int(val * 1000)
                else:
                    clean_int = match.group(1).replace('.', '').replace(',', '')
                    return int(clean_int)
            except Exception:
                pass
        return 0

    def get_search_keywords_for_category(self, category_name: str) -> List[str]:
        """
        Lấy danh sách từ khóa tìm group từ danh mục Shopee.
        Tự động dịch sang Tiếng Việt chuẩn, sử dụng tên cộng đồng thực tế và bổ sung các nhóm tương đương (same same).
        Tuyệt đối không tự động ghép đuôi tiếng Anh máy móc.
        """
        vi_category = translate_category(category_name)
        matched_keywords = []

        # 1. Tra cứu theo tên Tiếng Việt đã dịch hoặc tên gốc
        for cat_key, keywords in CATEGORY_GROUP_KEYWORDS.items():
            cat_key_vi = translate_category(cat_key)
            if (cat_key.lower() == category_name.lower() or
                cat_key.lower() == vi_category.lower() or
                cat_key_vi.lower() == vi_category.lower() or
                cat_key.lower() in category_name.lower() or
                cat_key_vi.lower() in vi_category.lower() or
                vi_category.lower() in cat_key_vi.lower()):
                matched_keywords = list(keywords)
                break

        # 2. Nếu chưa có danh mục dựng sẵn: sinh từ khóa tự nhiên tiếng Việt (không ghép đuôi tiếng Anh)
        if not matched_keywords:
            clean_name = vi_category.replace("&", "").strip()
            matched_keywords = [
                f"hội {clean_name}",
                f"review {clean_name} có tâm",
                f"săn deal {clean_name}"
            ]

        # 3. Bổ sung các từ khóa đã tự học được từ các nhóm tìm thấy trước đây
        learned_keywords = self.keyword_learner.get_expanded_keywords(vi_category, limit=3)

        # 4. Bổ sung các nhóm tương đương ("same same" - các cộng đồng săn sale/review lớn)
        combined_keywords = []
        for kw in matched_keywords + learned_keywords + GENERAL_SHOPPING_GROUP_KEYWORDS:
            if kw and kw not in combined_keywords:
                combined_keywords.append(kw)

        return combined_keywords

    def search_groups(self, category_name: str, max_groups: int = 5, account_id: Optional[object] = None) -> List[Dict]:
        """
        Tìm kiếm các group Facebook THẬT.
        Yêu cầu đã cấu hình FB_COOKIE hoặc FB_CHROME_PROFILE hoặc tài khoản Facebook.
        """
        from modules.outreach.fb_account_manager import resolve_fb_account
        acc, fb_cookie, fb_profile = resolve_fb_account(self.db, account_id=account_id, allow_rotation=False)
        acc_name = acc.get("name") if acc else "Nick Facebook"
        logging.info(f"🔍 Dò tìm group Facebook bằng tài khoản: [{acc_name}]")

        if not fb_cookie and not fb_profile:
            raise RuntimeError(
                "Chưa cấu hình thông tin đăng nhập Facebook! "
                "Vui lòng vào tab 'Cài Đặt' trên giao diện để nhập Cookie Facebook hoặc đường dẫn Chrome Profile."
            )

        vi_category = translate_category(category_name)
        keywords = self.get_search_keywords_for_category(category_name)
        logging.info(f"Đang tìm kiếm Group Facebook THẬT cho ngành [{vi_category}] với từ khóa tự nhiên: {keywords}")

        # Thao tác tìm kiếm thật qua Playwright (nếu có profile/cookie), lấy 3 từ khóa hàng đầu
        discovered_groups = self._search_via_playwright(keywords[:3], vi_category, max_groups, fb_cookie, fb_profile)
        return discovered_groups

    def _search_via_playwright(self, keywords: List[str], category_name: str, max_groups: int, cookie: str, profile_path: str) -> List[Dict]:
        """Dùng Playwright mở Facebook Search để bóc tách DOM Group thật"""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise RuntimeError("Chưa cài đặt Playwright! Hãy chạy 'pip install playwright' và 'playwright install'.")

        discovered = []
        with sync_playwright() as p:
            if profile_path and os.path.exists(profile_path):
                context = p.chromium.launch_persistent_context(
                    user_data_dir=profile_path,
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled"]
                )
            else:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context()
                if cookie:
                    # Parse cookie string và add vào context
                    cookie_list = []
                    for item in cookie.split(";"):
                        if "=" in item:
                            k, v = item.strip().split("=", 1)
                            cookie_list.append({"name": k, "value": v, "domain": ".facebook.com", "path": "/"})
                    if cookie_list:
                        context.add_cookies(cookie_list)

            page = context.new_page()

            for kw in keywords:
                encoded_kw = urllib.parse.quote(kw)
                search_url = f"https://www.facebook.com/search/groups/?q={encoded_kw}"
                logging.info(f"Đang mở trang tìm kiếm thật: {search_url}")

                try:
                    page.goto(search_url, timeout=30000, wait_until="domcontentloaded")
                    page.wait_for_timeout(3000)

                    # Bóc tách các thẻ group từ kết quả tìm kiếm của Facebook
                    group_links = page.locator("a[href*='/groups/']").all()
                    for link in group_links:
                        href = link.get_attribute("href") or ""
                        text = link.inner_text().strip()
                        if "/groups/" in href and "/search/" not in href and text and len(text) > 3:
                            clean_url = href.split("?")[0]
                            group_id = clean_url.rstrip("/").split("/")[-1]
                            
                            # Bỏ qua các đường dẫn hệ thống nội bộ của FB
                            if group_id in ["groups", "feed", "discover", "joins", "create", "notifications"]:
                                continue
                                
                            # Bóc tách số lượng thành viên thực tế từ Facebook (Regex tiếng Việt & tiếng Anh)
                            card_text = text
                            try:
                                parent_card = link.locator("xpath=ancestor::div[3]").first
                                if parent_card.is_visible(timeout=500):
                                    card_text = parent_card.inner_text()
                            except Exception:
                                pass

                            real_members = self._parse_members_count(card_text)
                            group_name = text.split("\n")[0].strip()

                            # Lọc nhanh: Bỏ qua nhóm quy mô quá nhỏ (< 500 thành viên)
                            if real_members > 0 and real_members < 500:
                                logging.info(f"   ⏩ Bỏ qua nhóm [{group_name}]: Dưới 500 thành viên ({real_members}).")
                                continue

                            # Kiểm tra xem nhóm đã có trong CSDL chưa
                            with self.db.get_connection() as conn:
                                existing = conn.execute("SELECT status FROM fb_groups WHERE group_id = ?", (group_id,)).fetchone()
                                if existing and existing["status"] in ["APPROVED", "LEFT", "SKIPPED_GHOST"]:
                                    continue

                            # KIỂM TRA TƯƠNG TÁC VÀ BÀI ĐĂNG GẦN NHẤT TRƯỚC KHI THAM GIA
                            logging.info(f"   🔍 Đang kiểm tra tương tác và bài đăng gần nhất: [{group_name}] ({clean_url})...")
                            eval_page = context.new_page()
                            try:
                                health = self.health_checker.evaluate_page(eval_page, clean_url, scroll_times=2)
                            except Exception as e_eval:
                                logging.warning(f"Lỗi khi kiểm tra sức khỏe nhóm {clean_url}: {e_eval}")
                                health = {"health_score": 0, "avg_engagement": 0.0, "last_post_hours_ago": None, "verdict": "GHOST"}
                            finally:
                                try:
                                    eval_page.close()
                                except Exception:
                                    pass

                            avg_eng = health.get("avg_engagement", 0.0)
                            last_post_hours = health.get("last_post_hours_ago")
                            score = health.get("health_score", 0)
                            verdict = health.get("verdict", "UNKNOWN")

                            # Quy tắc đánh giá tương tác & độ mới của bài viết:
                            # 1. Tương tác trung bình >= 2.0 (likes/comments)
                            # 2. Bài đăng gần nhất <= 72 giờ (3 ngày)
                            # 3. Điểm sức khỏe >= 40 và không phải GHOST
                            is_low_engagement = (avg_eng < 2.0)
                            is_dead_feed = (last_post_hours is None or last_post_hours > 72.0)
                            is_ghost = (score < 40 or verdict == "GHOST")

                            if is_low_engagement or is_dead_feed or is_ghost:
                                reasons = []
                                if is_low_engagement:
                                    reasons.append(f"Tương tác quá thấp ({avg_eng:.1f} < 2.0)")
                                if is_dead_feed:
                                    hours_desc = f"{last_post_hours:.1f}h" if last_post_hours is not None else "Không tìm thấy bài"
                                    reasons.append(f"Bài đăng gần nhất quá cũ ({hours_desc} > 72h)")
                                if is_ghost:
                                    reasons.append(f"Điểm sức khỏe thấp ({score}/100, {verdict})")

                                logging.warning(
                                    f"   🚫 [BỎ QUA GROUP CHẾT/KHÔNG TƯƠNG TÁC]: [{group_name}] - "
                                    f"Lý do: {', '.join(reasons)}. Không thêm vào danh sách tham gia!"
                                )
                                # Lưu với status SKIPPED_GHOST để lần sau không quét lại
                                self.db.save_group(group_id, group_name, clean_url, category_name, real_members)
                                self.db.update_group_health(group_id, score, avg_eng, None, health.get("unique_posters", 0), "GHOST")
                                self.db.update_group_status(group_id, "SKIPPED_GHOST")
                                continue

                            # Nhóm đạt chuẩn tương tác và độ mới
                            last_active_str = None
                            if last_post_hours is not None:
                                from datetime import timedelta, datetime
                                approx_dt = datetime.now() - timedelta(hours=last_post_hours)
                                last_active_str = approx_dt.strftime("%Y-%m-%d %H:%M:%S")

                            group_data = {
                                "group_id": group_id,
                                "name": group_name,
                                "url": clean_url,
                                "category_name": category_name,
                                "members_count": real_members,
                                "health_score": score,
                                "avg_engagement": avg_eng,
                                "last_post_hours_ago": last_post_hours,
                                "status": "DISCOVERED"
                            }
                            self.db.save_group(group_id, group_name, clean_url, category_name, real_members)
                            self.db.update_group_health(
                                group_id=group_id,
                                health_score=score,
                                avg_engagement=avg_eng,
                                last_active_at=last_active_str,
                                unique_posters=health.get("unique_posters", 0),
                                health_verdict=verdict
                            )
                            self.db.update_group_status(group_id, "DISCOVERED")
                            
                            # Tự động học từ khóa từ tên nhóm Facebook vừa phát hiện
                            self.keyword_learner.learn_from_group(category_name, group_name)
                            
                            logging.info(
                                f"   ✅ [ĐẠT TIÊU CHUẨN THAM GIA]: [{group_name}] | "
                                f"TV: {real_members:,} | Tương tác TB: {avg_eng} | "
                                f"Bài mới nhất: {last_post_hours}h trước | Điểm: {score}/100"
                            )
                            discovered.append(group_data)

                            if len(discovered) >= max_groups:
                                break
                except Exception as e:
                    logging.warning(f"Lỗi khi cào từ khóa '{kw}': {e}")

            context.close()

        if not discovered:
            logging.warning(f"Không tìm thấy group nào hoặc Facebook yêu cầu đăng nhập lại.")
        return discovered
