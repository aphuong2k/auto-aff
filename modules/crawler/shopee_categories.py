import requests
import json
import logging
from typing import List, Dict

from config.categories_filter import is_category_allowed, translate_category
from database.db_manager import DatabaseManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

class ShopeeCategoryCrawler:
    CATEGORY_TREE_URL = "https://shopee.vn/api/v4/pages/get_category_tree"
    
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Referer": "https://shopee.vn/"
    }

    def __init__(self, db: DatabaseManager = None, cookie: str = ""):
        self.db = db or DatabaseManager()
        self.cookie = cookie

    def fetch_categories(self) -> List[Dict]:
        """Gọi API Shopee để lấy toàn bộ cây danh mục ngành hàng và dịch chuẩn sang Tiếng Việt"""
        import os
        logging.info("Đang gọi API Shopee lấy cây danh mục ngành hàng...")
        headers = dict(self.HEADERS)
        cookie_val = self.cookie or os.getenv("SHOPEE_COOKIE", "")
        if cookie_val:
            headers["Cookie"] = cookie_val

        try:
            response = requests.get(self.CATEGORY_TREE_URL, headers=headers, timeout=15)
            if response.status_code != 200:
                logging.error(f"❌ [LỖI CÀO DANH MỤC SHOPEE]: Shopee trả về HTTP {response.status_code} - {response.text[:250]}. Hãy kiểm tra SHOPEE_COOKIE trong Cài Đặt!")
                return []
            
            data = response.json()
            raw_categories = data.get("data", {}).get("category_list", [])
            
            valid_categories = []
            for cat in raw_categories:
                cat_id = cat.get("catid")
                raw_name = cat.get("name", "").strip()
                
                # Kiểm tra lọc bỏ danh mục rác (cả tiếng Anh lẫn tiếng Việt)
                if is_category_allowed(raw_name):
                    vi_name = translate_category(raw_name)
                    valid_categories.append({
                        "cat_id": cat_id,
                        "name": vi_name,
                        "raw_name": raw_name,
                        "parent_id": cat.get("parent_catid", 0),
                        "sub_categories": [
                            {
                                "cat_id": sub.get("catid"),
                                "name": translate_category(sub.get("name", "")),
                                "raw_name": sub.get("name", "")
                            }
                            for sub in cat.get("children", [])
                            if is_category_allowed(sub.get("name", ""))
                        ]
                    })
                    # Lưu vào database tên tiếng Việt chuẩn hóa
                    self.db.save_category(cat_id, vi_name)
            
            logging.info(f"Đã lấy thành công {len(valid_categories)} ngành hàng hợp lệ từ Shopee (đã dịch sang Tiếng Việt).")
            return valid_categories

        except Exception as e:
            logging.error(f"Ngoại lệ khi cào danh mục Shopee: {e}")
            return []

if __name__ == "__main__":
    crawler = ShopeeCategoryCrawler()
    cats = crawler.fetch_categories()
    print("\n--- Danh mục Shopee hợp lệ đã dịch sang Tiếng Việt ---")
    for c in cats[:10]:
        print(f"ID: {c['cat_id']} | Tên: {c['name']} (Có {len(c['sub_categories'])} danh mục con)")
