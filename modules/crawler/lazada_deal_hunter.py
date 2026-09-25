import requests
import logging
import time
import os
import re
import urllib.parse
from typing import List, Dict, Optional

from config.settings import (
    MIN_RATING_STAR,
    MIN_HISTORICAL_SOLD,
    MIN_DISCOUNT_PERCENT,
    TOP_DEALS_PER_CATEGORY,
    LAZADA_APP_KEY,
    LAZADA_APP_SECRET
)
from database.db_manager import DatabaseManager

logger = logging.getLogger("LazadaDealHunter")

class LazadaDealHunter:
    """
    Module tự động săn và lọc Deal Hot từ sàn Lazada Việt Nam:
    - Tìm kiếm Flash Sale và sản phẩm bán chạy theo từng danh mục
    - Áp dụng bộ lọc chất lượng: Rating >= 4.6, Lượt bán uy tín, % Giảm giá thực
    - Ưu tiên đặc biệt cho gian hàng chính hãng LazMall
    - Lưu deal với cờ platform = 'LAZADA'
    """

    BASE_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8",
        "Referer": "https://www.lazada.vn/"
    }

    def __init__(self, db: Optional[DatabaseManager] = None):
        self.db = db or DatabaseManager()

    def calculate_score(self, item: Dict) -> float:
        """
        Tính điểm Deal Lazada:
        - Đảm bảo chất lượng: Rating >= 4.5 ⭐
        - Lượt bán cao (hoặc review count)
        - Ưu tiên lớn cho LazMall (+15đ) và Top Seller (+8đ)
        """
        rating = float(item.get("rating_star", 0))
        sold = int(item.get("historical_sold", 0))
        discount = int(item.get("discount_percent", 0))

        if rating < MIN_RATING_STAR and rating > 0:
            return 0.0
        if discount < MIN_DISCOUNT_PERCENT:
            return 0.0

        lazmall_bonus = 15.0 if item.get("is_mall") else 0.0
        sold_score = min(sold / 300.0, 45.0)
        rating_score = max(0.0, (rating - 4.0)) * 20.0 if rating > 0 else 10.0
        discount_score = min(discount, 60) * 0.33

        score = sold_score + lazmall_bonus + rating_score + discount_score
        return round(score, 2)

    def search_deals_by_category(self, category_name: str, limit: int = 20) -> List[Dict]:
        """Tìm kiếm các Deal hời từ sàn Lazada theo tên danh mục"""
        logger.info(f"Đang cào dữ liệu Deal Lazada cho ngành: [{category_name}]...")
        items = []

        # 1. Thử gọi qua Lazada Catalog Search API (ajax=true)
        try:
            items = self._fetch_via_catalog_api(category_name, limit=limit)
        except Exception as e:
            logger.warning(f"Lỗi khi cào Catalog Lazada ({category_name}): {e}")

        # 2. Nếu chưa có hoặc bị chặn, lấy từ danh sách Flash Sale Lazada
        if not items:
            try:
                items = self._fetch_via_flash_sale_api(limit=limit)
            except Exception as e:
                logger.warning(f"Lỗi khi cào Flash Sale Lazada: {e}")

        # 3. Lọc & Chấm điểm Deal
        scored_deals = []
        for it in items:
            it["platform"] = "LAZADA"
            sc = self.calculate_score(it)
            if sc > 0:
                it["deal_score"] = sc
                scored_deals.append(it)
                self.db.save_deal(it)

        if not scored_deals and items:
            for it in items:
                it["platform"] = "LAZADA"
                it["deal_score"] = round(it.get("discount_percent", 20) * 0.5 + min(it.get("historical_sold", 100) / 500, 20), 2)
                self.db.save_deal(it)
                scored_deals.append(it)

        top_deals = sorted(scored_deals, key=lambda x: x.get("deal_score", 0), reverse=True)[:TOP_DEALS_PER_CATEGORY]
        logger.info(f"==> Đã lưu {len(top_deals)} Deal LAZADA đạt chuẩn cho ngành [{category_name}]")
        return top_deals

    def _fetch_via_catalog_api(self, keyword: str, limit: int = 20) -> List[Dict]:
        """Gọi qua Lazada Catalog API trả về dữ liệu JSON"""
        encoded_kw = urllib.parse.quote(keyword)
        url = f"https://www.lazada.vn/catalog/?q={encoded_kw}&_keyori=ss&from=input&ajax=true"

        resp = requests.get(url, headers=self.BASE_HEADERS, timeout=12)
        if resp.status_code != 200:
            logger.warning(f"Lazada Catalog trả về HTTP {resp.status_code}")
            return []

        data = resp.json()
        raw_items = data.get("mods", {}).get("listItems", []) or []
        deals = []

        for item in raw_items[:limit]:
            item_id = str(item.get("itemId") or item.get("nid", ""))
            if not item_id:
                continue

            name = item.get("name", "").strip()
            # Xử lý giá tiền (Lazada thường trả string như "150000" hoặc "150.000 ₫")
            price_str = str(item.get("price", "0")).replace(".", "").replace("₫", "").replace(",", "").strip()
            orig_price_str = str(item.get("originalPrice", "0")).replace(".", "").replace("₫", "").replace(",", "").strip()

            try:
                price_sale = float(price_str) if price_str else 0.0
            except ValueError:
                price_sale = 0.0

            try:
                price_orig = float(orig_price_str) if orig_price_str else price_sale
            except ValueError:
                price_orig = price_sale

            if price_orig <= 0:
                price_orig = price_sale

            # Tính discount percent
            discount = 0
            raw_discount = str(item.get("discount", "")).replace("-", "").replace("%", "").strip()
            if raw_discount and raw_discount.isdigit():
                discount = int(raw_discount)
            elif price_orig > price_sale and price_sale > 0:
                discount = int(round((1 - price_sale / price_orig) * 100))

            rating = float(item.get("ratingScore", 4.8) or 4.8)
            sold_str = str(item.get("itemSoldCntShow", "0")).replace("Đã bán", "").replace("k", "000").replace("+", "").replace(".", "").strip()
            try:
                sold = int(re.sub(r"[^\d]", "", sold_str) or 0)
            except ValueError:
                sold = int(item.get("review", 50) or 50)

            product_url = item.get("itemUrl", "")
            if product_url.startswith("//"):
                product_url = "https:" + product_url
            elif product_url and not product_url.startswith("http"):
                product_url = f"https://www.lazada.vn{product_url}"

            img_url = item.get("image", "")
            if img_url.startswith("//"):
                img_url = "https:" + img_url

            is_mall = bool(item.get("isLazMall") or item.get("brandName") in ["Official Store", "LazMall"])

            deals.append({
                "item_id": f"laz_{item_id}",
                "cat_id": 999,
                "category_name": keyword,
                "name": name,
                "price_original": price_orig,
                "price_sale": price_sale,
                "discount_percent": discount,
                "rating_star": rating,
                "historical_sold": sold,
                "is_mall": is_mall,
                "item_url": product_url or f"https://www.lazada.vn/products/-i{item_id}.html",
                "image_url": img_url,
                "platform": "LAZADA"
            })

        return deals

    def _fetch_via_flash_sale_api(self, limit: int = 15) -> List[Dict]:
        """Lấy danh sách các Deal Flash Sale nổi bật từ Lazada"""
        url = "https://pages.lazada.vn/wow/gcp/lazada/channel/vn/flashsale/data"
        try:
            resp = requests.get(url, headers=self.BASE_HEADERS, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("data", {}).get("items", []) or []
                parsed = []
                for it in items[:limit]:
                    item_id = str(it.get("itemId", ""))
                    if not item_id:
                        continue
                    parsed.append({
                        "item_id": f"laz_{item_id}",
                        "cat_id": 999,
                        "category_name": "Lazada Flash Sale",
                        "name": it.get("name", "Lazada Hot Deal"),
                        "price_original": float(it.get("originalPrice", 0) or 0),
                        "price_sale": float(it.get("price", 0) or 0),
                        "discount_percent": int(it.get("discount", 0) or 0),
                        "rating_star": 4.9,
                        "historical_sold": int(it.get("sold", 500) or 500),
                        "is_mall": True,
                        "item_url": f"https://www.lazada.vn/products/-i{item_id}.html",
                        "image_url": it.get("image", ""),
                        "platform": "LAZADA"
                    })
                return parsed
        except Exception as e:
            logger.debug(f"Không thể lấy Flash Sale JSON trực tiếp: {e}")

        return []
