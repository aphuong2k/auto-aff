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

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

class FacebookGroupFinder:
    """Module tự động tìm kiếm Group Facebook THẬT liên quan theo ngành hàng"""

    def __init__(self, db: DatabaseManager = None):
        self.db = db or DatabaseManager()
        self.keyword_learner = GroupKeywordLearner(self.db)

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

    def search_groups(self, category_name: str, max_groups: int = 5) -> List[Dict]:
        """
        Tìm kiếm các group Facebook THẬT.
        Yêu cầu đã cấu hình FB_COOKIE hoặc FB_CHROME_PROFILE.
        Nếu chưa cấu hình, báo lỗi rõ ràng để người dùng nhập thông tin!
        """
        fb_cookie = os.getenv("FB_COOKIE", "")
        fb_profile = os.getenv("FB_CHROME_PROFILE", "")

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

                            group_data = {
                                "group_id": group_id,
                                "name": group_name,
                                "url": clean_url,
                                "category_name": category_name,
                                "members_count": real_members,
                                "status": "DISCOVERED"
                            }
                            self.db.save_group(group_id, group_name, clean_url, category_name, real_members)
                            
                            # Tự động học từ khóa từ tên nhóm Facebook vừa phát hiện
                            self.keyword_learner.learn_from_group(category_name, group_name)
                            
                            logging.info(f"   👥 Tìm thấy nhóm thật: [{group_name}] | Thành viên: {real_members:,} | URL: {clean_url}")
                            discovered.append(group_data)

                            if len(discovered) >= max_groups:
                                break
                except Exception as e:
                    logging.warning(f"Lỗi khi cào từ khóa '{kw}': {e}")

            context.close()

        if not discovered:
            logging.warning(f"Không tìm thấy group nào hoặc Facebook yêu cầu đăng nhập lại.")
        return discovered
