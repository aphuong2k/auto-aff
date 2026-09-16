import os
import logging
import urllib.parse
from typing import List, Dict

from config.settings import MIN_GROUP_MEMBERS
from config.categories_filter import CATEGORY_GROUP_KEYWORDS
from database.db_manager import DatabaseManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

class FacebookGroupFinder:
    """Module tự động tìm kiếm Group Facebook THẬT liên quan theo ngành hàng"""

    def __init__(self, db: DatabaseManager = None):
        self.db = db or DatabaseManager()

    def get_search_keywords_for_category(self, category_name: str) -> List[str]:
        """Lấy danh sách từ khóa tìm group từ danh mục Shopee"""
        for cat_key, keywords in CATEGORY_GROUP_KEYWORDS.items():
            if cat_key.lower() in category_name.lower() or category_name.lower() in cat_key.lower():
                return keywords
        
        clean_name = category_name.replace("&", "").strip()
        return [
            f"hội review {clean_name}",
            f"giao lưu {clean_name}",
            f"săn deal {clean_name}"
        ]

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

        keywords = self.get_search_keywords_for_category(category_name)
        logging.info(f"Đang tìm kiếm Group Facebook THẬT cho ngành [{category_name}] với từ khóa: {keywords}")

        # Thao tác tìm kiếm thật qua Playwright (nếu có profile/cookie)
        discovered_groups = self._search_via_playwright(keywords[:2], category_name, max_groups, fb_cookie, fb_profile)
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
                        if "/groups/" in href and text and len(text) > 3:
                            clean_url = href.split("?")[0]
                            group_id = clean_url.rstrip("/").split("/")[-1]
                            
                            # Lưu vào database
                            group_data = {
                                "group_id": group_id,
                                "name": text,
                                "url": clean_url,
                                "category_name": category_name,
                                "members_count": 10000,
                                "status": "DISCOVERED"
                            }
                            self.db.save_group(group_id, text, clean_url, category_name, 10000)
                            discovered.append(group_data)

                            if len(discovered) >= max_groups:
                                break
                except Exception as e:
                    logging.warning(f"Lỗi khi cào từ khóa '{kw}': {e}")

            context.close()

        if not discovered:
            logging.warning(f"Không tìm thấy group nào hoặc Facebook yêu cầu đăng nhập lại.")
        return discovered
