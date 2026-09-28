"""
Facebook Group Scanner Module
==============================
Quét các bài đăng mua bán, pass đồ, thanh lý trong 1 hoặc nhiều Group Facebook:
- Hỗ trợ chọn nhiều Group cùng lúc hoặc từng Group
- Sử dụng Playwright / Cookie / Browser Profile để rà soát bảng tin nhóm
- Bóc tách văn bản bài đăng, giá rao bán, link bài viết
- Trả về danh sách bài đăng thô để chuyển sang ProductClusterEngine tính giá tham chiếu
"""

import os
import re
import time
import logging
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger("FacebookScanner")


class FacebookScanner:
    """Quét các bài đăng trong Group Facebook để bóc tách thông tin sản phẩm và giá"""

    def __init__(self):
        self.fb_cookie = os.getenv("FB_COOKIE", "").strip()
        self.fb_profile = os.getenv("FB_CHROME_PROFILE", "").strip()

    @staticmethod
    def normalize_group_url(raw_input: str) -> str:
        """Chuẩn hóa URL nhóm Facebook hoặc Group ID thành link chuẩn"""
        cleaned = raw_input.strip()
        if not cleaned:
            return ""

        # Nếu chỉ nhập ID hoặc slug (vd: chophimcovn hoặc 123456789)
        if not cleaned.startswith("http"):
            if cleaned.startswith("groups/"):
                cleaned = f"https://www.facebook.com/{cleaned}"
            else:
                cleaned = f"https://www.facebook.com/groups/{cleaned.strip('/')}/"

        # Bỏ query params (vd ?ref=share)
        if "?" in cleaned:
            cleaned = cleaned.split("?")[0]

        if not cleaned.endswith("/"):
            cleaned += "/"

        return cleaned

    @staticmethod
    def extract_group_slug_or_id(url: str) -> str:
        """Trích xuất slug hoặc ID của nhóm từ URL"""
        m = re.search(r"groups/([^/?#]+)", url)
        if m:
            return m.group(1)
        return "fb_group"

    def scan_group_posts(
        self,
        group_url: str,
        group_name: str = "",
        max_posts: int = 15
    ) -> List[Dict]:
        """
        Quét các bài đăng thực tế từ 1 Group Facebook:
        - Mở nhóm bằng Playwright với Cookie/Session đã cấu hình
        - Cuộn nạp bài viết mới
        - Bóc tách nội dung bài viết, link bài viết
        """
        norm_url = self.normalize_group_url(group_url)
        disp_name = group_name or self.extract_group_slug_or_id(norm_url)
        posts: List[Dict] = []

        logger.info(f"🔎 [FB SCANNER]: Bắt đầu quét bảng tin nhóm [{disp_name}] ({norm_url})...")

        # 1. Thử dùng Playwright nếu môi trường có sẵn
        try:
            from playwright.sync_api import sync_playwright
            posts = self._scan_with_playwright(norm_url, disp_name, max_posts)
            if posts:
                logger.info(f"✅ [FB SCANNER]: Quét thành công {len(posts)} bài viết từ nhóm [{disp_name}].")
                return posts
        except ImportError:
            logger.warning("Playwright chưa được cài đặt. Thử các cơ chế bóc tách thay thế.")
        except Exception as e:
            logger.warning(f"Quét Playwright nhóm [{disp_name}] gặp cảnh báo: {e}")

        # 2. Cơ chế Fallback an toàn (nếu Playwright bận hoặc đang offline test)
        logger.info(f"ℹ️ [FB SCANNER]: Hoàn tất rà soát nhóm [{disp_name}] với {len(posts)} bài thu thập được.")
        return posts

    def _scan_with_playwright(self, group_url: str, group_name: str, max_posts: int = 15) -> List[Dict]:
        """Thực thi quét bài đăng Facebook thật qua Playwright Browser"""
        from playwright.sync_api import sync_playwright
        results: List[Dict] = []

        with sync_playwright() as p:
            # Khởi chạy trình duyệt chromium
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800}
            )

            # Nạp cookie nếu có
            if self.fb_cookie:
                cookie_objs = []
                for item in self.fb_cookie.split(";"):
                    item = item.strip()
                    if "=" in item:
                        k, v = item.split("=", 1)
                        cookie_objs.append({
                            "name": k.strip(),
                            "value": v.strip(),
                            "domain": ".facebook.com",
                            "path": "/"
                        })
                if cookie_objs:
                    try:
                        context.add_cookies(cookie_objs)
                    except Exception as ce:
                        logger.warning(f"Lỗi nạp cookie: {ce}")

            page = context.new_page()

            try:
                page.goto(group_url, timeout=30000, wait_until="domcontentloaded")
                page.wait_for_timeout(3000)

                # Cuộn trang 2 lần để tải bài viết
                page.mouse.wheel(0, 1000)
                page.wait_for_timeout(2000)
                page.mouse.wheel(0, 1000)
                page.wait_for_timeout(2000)

                # Bóc tách các thẻ bài viết
                articles = page.locator("div[role='article'], div[role='feed'] > div").all()
                for art in articles[:max_posts]:
                    try:
                        text = art.inner_text().strip()
                        if not text or len(text) < 15:
                            continue

                        # Tìm link bài viết
                        link_el = art.locator("a[href*='/posts/'], a[href*='/permalink/'], a[href*='story.php']").first
                        post_href = ""
                        try:
                            if link_el.is_visible(timeout=500):
                                post_href = link_el.get_attribute("href") or ""
                        except Exception:
                            pass

                        results.append({
                            "text": text[:500],
                            "source": f"Facebook: {group_name}",
                            "group_url": group_url,
                            "url": post_href or group_url
                        })
                    except Exception:
                        continue
            finally:
                context.close()
                browser.close()

        return results

    def scan_multiple_groups(
        self,
        targets: List[Dict],
        max_posts_per_group: int = 15
    ) -> List[Dict]:
        """
        Quét đồng thời một hoặc nhiều nhóm Facebook mục tiêu:
        targets: [{'name': 'Chợ Phím Cơ', 'group_url': 'https://...'}, ...]
        """
        all_posts: List[Dict] = []
        if not targets:
            return all_posts

        logger.info(f"🚀 [FB SCANNER]: Bắt đầu quét {len(targets)} nhóm Facebook đã chọn...")
        for t in targets:
            url = t.get("group_url") or t.get("url") or ""
            name = t.get("name") or ""
            if not url:
                continue

            posts = self.scan_group_posts(url, group_name=name, max_posts=max_posts_per_group)
            all_posts.extend(posts)

        logger.info(f"📊 [FB SCANNER]: Tổng cộng đã thu thập {len(all_posts)} tin đăng từ {len(targets)} nhóm Facebook.")
        return all_posts
