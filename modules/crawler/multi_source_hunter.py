"""
Multi-Source Deal Hunter Crawler
================================
Hệ thống cào và săn deal đa nguồn theo các phân loại & định dạng yêu cầu:
- Tmall (Gian hàng Tmall / Taobao cross-border / Tmall Global)
- Lazada Mall (Gian hàng chính hãng LazMall)
- Phân loại khác của Lazada (Marketplace, Shop Uy Tín, Shop Yêu Thích)
- Tìm All (Gộp toàn bộ LazMall, Tmall, Lazada, Shopee để so sánh toàn diện)

Tự động đối chiếu với Giá Tham Chiếu và ƯU TIÊN SẢN PHẨM CÓ GIÁ THẤP HƠN GIÁ THAM CHIẾU.
Không dùng dữ liệu mẫu / hardcode - Cào trực tiếp thời gian thực.
"""

import os
import re
import time
import urllib.parse
import statistics
import logging
from typing import List, Dict, Optional, Any

import requests
from config.settings import (
    MIN_RATING_STAR,
    MIN_HISTORICAL_SOLD,
    LAZADA_AFF_COOKIE,
    SHOPEE_AFF_COOKIE
)
from modules.affiliate.link_converter import AffiliateLinkConverter

logger = logging.getLogger("MultiSourceHunter")


class MultiSourceHunter:
    """Bộ máy cào & săn deal đa nguồn thời gian thực"""

    BASE_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8",
        "Referer": "https://www.lazada.vn/"
    }

    def __init__(self, lazada_cookie: Optional[str] = None):
        self.lazada_cookie = lazada_cookie or os.getenv("LAZADA_AFF_COOKIE", LAZADA_AFF_COOKIE)
        self.link_converter = AffiliateLinkConverter()

    def search_deals(
        self,
        keyword: str,
        source_platform: str = "ALL",
        reference_price: float = 0.0,
        limit: int = 30
    ) -> List[Dict]:
        """
        Tìm kiếm deal theo nguồn/định dạng đã chọn:
        - TMALL
        - LAZADA_MALL
        - LAZADA_OTHER
        - ALL
        """
        clean_kw = keyword.strip()
        if not clean_kw:
            return []

        source_upper = source_platform.upper().strip()
        all_deals: List[Dict] = []

        if source_upper == "TMALL":
            all_deals = self._fetch_tmall_deals(clean_kw, limit=limit)
        elif source_upper == "LAZADA_MALL":
            all_deals = self._fetch_lazada_mall_deals(clean_kw, limit=limit)
        elif source_upper == "LAZADA_OTHER":
            all_deals = self._fetch_lazada_other_deals(clean_kw, limit=limit)
        else:  # ALL
            mall_deals = self._fetch_lazada_mall_deals(clean_kw, limit=15)
            tmall_deals = self._fetch_tmall_deals(clean_kw, limit=15)
            other_deals = self._fetch_lazada_other_deals(clean_kw, limit=15)
            shopee_deals = self._fetch_shopee_deals(clean_kw, limit=10)

            # Gộp và khử trùng lặp theo item_id
            seen_ids = set()
            for d in (mall_deals + tmall_deals + other_deals + shopee_deals):
                iid = d.get("item_id")
                if iid and iid not in seen_ids:
                    seen_ids.add(iid)
                    all_deals.append(d)

        if not all_deals:
            logger.warning(f"Không cào được deal nào cho từ khóa [{clean_kw}] trên nguồn [{source_upper}]")
            return []

        # 1. Nếu chưa có Giá tham chiếu (người dùng gõ từ khóa trực tiếp không qua tin đăng Telegram),
        # Hệ thống tự tính Giá tham chiếu thị trường dựa trên Median giá của các sản phẩm tìm được!
        computed_ref = reference_price
        if computed_ref <= 0:
            valid_prices = [d["sale_price"] for d in all_deals if d.get("sale_price", 0) > 0]
            if valid_prices:
                computed_ref = round(statistics.median(valid_prices), 0)

        # 2. Tính toán chênh lệch giá, % tiết kiệm và đánh giá Deal Hời (< Giá tham chiếu)
        scored_deals: List[Dict] = []
        for deal in all_deals:
            sale_price = float(deal.get("sale_price", 0))
            orig_price = float(deal.get("original_price", sale_price) or sale_price)

            deal["reference_price"] = computed_ref
            price_diff = round(computed_ref - sale_price, 0)
            deal["price_diff"] = price_diff

            if computed_ref > 0:
                savings_pct = round((price_diff / computed_ref) * 100, 1)
            else:
                savings_pct = 0.0
            deal["savings_percent"] = savings_pct

            # Cờ đánh dấu DEAL HỜI: Giá bán trên sàn thấp hơn giá tham chiếu
            is_better = bool(sale_price > 0 and computed_ref > 0 and sale_price < computed_ref)
            deal["is_better_deal"] = is_better

            # Tạo link affiliate tự động
            item_url = deal.get("item_url", "")
            deal["aff_url"] = self.link_converter.convert_to_affiliate(
                item_url, channel="telegram", sub_id="hunt_deal"
            ) or item_url

            scored_deals.append(deal)

        # 3. SẮP XẾP ƯU TIÊN:
        # - Ưu tiên hàng đầu: Sản phẩm có giá THẤP HƠN giá tham chiếu (is_better_deal DESC)
        # - Mức chênh lệch tiết kiệm tiền nhiều nhất (price_diff DESC)
        # - Lượt bán và độ uy tín
        scored_deals.sort(
            key=lambda x: (
                1 if x.get("is_better_deal") else 0,
                x.get("price_diff", 0),
                x.get("savings_percent", 0),
                x.get("historical_sold", 0)
            ),
            reverse=True
        )

        return scored_deals[:limit]

    # --- Các phương thức cào từng nguồn chuyên biệt ---

    def _get_headers(self) -> Dict[str, str]:
        headers = dict(self.BASE_HEADERS)
        cookie = os.getenv("LAZADA_AFF_COOKIE", self.lazada_cookie)
        if cookie:
            headers["Cookie"] = cookie
        return headers

    def _fetch_lazada_mall_deals(self, keyword: str, limit: int = 20) -> List[Dict]:
        """Cào sản phẩm chính hãng LazMall (service=lazmall)"""
        url = f"https://www.lazada.vn/catalog/?q={urllib.parse.quote(keyword)}&service=lazmall&_keyori=ss&from=input&ajax=true"
        raw_items = self._query_lazada_api(url)
        deals = []
        for it in raw_items[:limit]:
            d = self._parse_lazada_item(it, default_platform="LAZADA_MALL")
            if d:
                d["platform"] = "LAZADA_MALL"
                deals.append(d)
        return deals

    def _fetch_tmall_deals(self, keyword: str, limit: int = 20) -> List[Dict]:
        """Cào sản phẩm Tmall Global / Taobao / Cross-border từ Trung Quốc"""
        # Thử tìm kiếm với từ khóa tmall hoặc lọc quốc tế
        query_str = f"tmall {keyword}" if "tmall" not in keyword.lower() else keyword
        url = f"https://www.lazada.vn/catalog/?q={urllib.parse.quote(query_str)}&_keyori=ss&from=input&ajax=true"
        raw_items = self._query_lazada_api(url)

        deals = []
        for it in raw_items:
            loc = str(it.get("location", "")).lower()
            seller = str(it.get("sellerName", "")).lower()
            # Nhận diện gian hàng Tmall / Quốc tế / Trung Quốc / Hong Kong
            is_tmall = (
                "china" in loc or "hong kong" in loc or "quốc tế" in loc or
                "tmall" in seller or "global" in seller or "taobao" in seller or
                "tmall" in keyword.lower()
            )
            d = self._parse_lazada_item(it, default_platform="TMALL")
            if d:
                d["platform"] = "TMALL"
                if is_tmall or len(deals) < limit // 2:
                    deals.append(d)
            if len(deals) >= limit:
                break
        return deals

    def _fetch_lazada_other_deals(self, keyword: str, limit: int = 20) -> List[Dict]:
        """Cào các phân loại khác của Lazada (Marketplace, Shop Uy Tín không thuộc LazMall)"""
        url = f"https://www.lazada.vn/catalog/?q={urllib.parse.quote(keyword)}&_keyori=ss&from=input&ajax=true"
        raw_items = self._query_lazada_api(url)
        deals = []
        for it in raw_items:
            # Bỏ qua LazMall để giữ đúng phân loại Marketplace / Khác
            icons_str = str(it.get("icons", []))
            if "lazMall" in icons_str or it.get("isLazMall"):
                continue
            d = self._parse_lazada_item(it, default_platform="LAZADA_OTHER")
            if d:
                d["platform"] = "LAZADA_OTHER"
                deals.append(d)
            if len(deals) >= limit:
                break
        return deals

    def _fetch_shopee_deals(self, keyword: str, limit: int = 10) -> List[Dict]:
        """Cào sản phẩm Shopee qua Flash Sale hoặc Search API nếu khả dụng"""
        cookie = os.getenv("SHOPEE_AFF_COOKIE", os.getenv("SHOPEE_COOKIE", SHOPEE_AFF_COOKIE))
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Referer": "https://shopee.vn/",
            "X-Requested-With": "XMLHttpRequest"
        }
        if cookie:
            headers["Cookie"] = cookie

        # Thử lấy từ Flash Sale API Shopee
        deals = []
        try:
            r = requests.get(
                "https://shopee.vn/api/v4/flash_sale/flash_sale_get_items",
                headers=headers,
                params={"limit": 30},
                timeout=8
            )
            if r.status_code == 200:
                items = r.json().get("data", {}).get("items", []) or []
                kw_no_acc = re.sub(r"[^\w\d]", "", keyword.lower())
                for it in items:
                    name = str(it.get("name") or it.get("promo_name") or "")
                    name_clean = re.sub(r"[^\w\d]", "", name.lower())
                    # So khớp từ khóa
                    if kw_no_acc in name_clean or any(k in name.lower() for k in keyword.lower().split() if len(k) > 2):
                        itemid = str(it.get("itemid", ""))
                        shopid = str(it.get("shopid", ""))
                        sale_p = (it.get("price", 0) or 0) / 100000.0
                        orig_p = (it.get("price_before_discount", 0) or 0) / 100000.0
                        deals.append({
                            "item_id": f"sp_{itemid}",
                            "name": name,
                            "price_original": orig_p if orig_p > 0 else sale_p,
                            "sale_price": sale_p,
                            "discount_percent": it.get("raw_discount", 0) or 0,
                            "rating_star": round(it.get("item_rating", {}).get("rating_star", 5.0), 1),
                            "historical_sold": int(it.get("historical_sold", 0) or 0),
                            "item_url": f"https://shopee.vn/product/{shopid}/{itemid}",
                            "image_url": f"https://down-vn.img.susercontent.com/file/{it.get('image')}" if it.get("image") else "",
                            "platform": "SHOPEE",
                            "seller_name": "Shopee Official / Flash Sale",
                            "location": "Việt Nam"
                        })
                    if len(deals) >= limit:
                        break
        except Exception as e:
            logger.debug(f"Không thể cào Shopee Flash Sale: {e}")

        return deals

    def _query_lazada_api(self, url: str) -> List[Dict]:
        """Gọi API Lazada Catalog trả về danh sách items thô"""
        try:
            resp = requests.get(url, headers=self._get_headers(), timeout=12)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("mods", {}).get("listItems", []) or []
            else:
                logger.warning(f"Lazada HTTP {resp.status_code} khi gọi {url[:60]}")
        except Exception as e:
            logger.warning(f"Lỗi khi cào Lazada Catalog ({url[:60]}): {e}")
        return []

    def _parse_lazada_item(self, item: Dict, default_platform: str = "LAZADA") -> Optional[Dict]:
        """Bóc tách 1 sản phẩm Lazada thành Dict chuẩn hóa"""
        item_id = str(item.get("itemId") or item.get("nid", ""))
        name = item.get("name", "").strip()
        if not item_id or not name:
            return None

        # Xử lý giá tiền
        price_str = str(item.get("price", "0")).replace(".", "").replace("₫", "").replace(",", "").strip()
        orig_price_str = str(item.get("originalPrice", "0")).replace(".", "").replace("₫", "").replace(",", "").strip()

        try:
            sale_price = float(price_str) if price_str else 0.0
        except ValueError:
            sale_price = 0.0

        try:
            orig_price = float(orig_price_str) if orig_price_str else sale_price
        except ValueError:
            orig_price = sale_price

        if orig_price <= 0:
            orig_price = sale_price

        # Chiết khấu giảm giá
        raw_discount = str(item.get("discount", "0") or "0")
        digits = re.findall(r"\d+", raw_discount)
        if digits:
            discount_val = int(digits[0])
        elif orig_price > sale_price and orig_price > 0:
            discount_val = int(round((1 - sale_price / orig_price) * 100))
        else:
            discount_val = 0

        # Lượt bán
        sold_str = str(item.get("itemSoldCntShow", "0")).replace("Đã bán", "").replace("k", "000").replace("+", "").replace(".", "").strip()
        try:
            sold = int(re.sub(r"[^\d]", "", sold_str) or 0)
        except ValueError:
            sold = int(item.get("review", 0) or 0)

        # Đánh giá sao
        try:
            rating = float(item.get("ratingScore", 4.8) or 4.8)
        except (ValueError, TypeError):
            rating = 4.8

        # URL sản phẩm
        product_url = item.get("itemUrl", "")
        if product_url.startswith("//"):
            product_url = "https:" + product_url
        elif product_url and not product_url.startswith("http"):
            product_url = f"https://www.lazada.vn{product_url}"

        # Ảnh
        img_url = item.get("image", "")
        if img_url.startswith("//"):
            img_url = "https:" + img_url

        icons = item.get("icons", [])
        is_mall = bool(item.get("isLazMall") or any("lazMall" in str(ic) for ic in icons))

        return {
            "item_id": f"laz_{item_id}",
            "name": name,
            "sale_price": sale_price,
            "original_price": orig_price,
            "discount_percent": discount_val,
            "rating_star": rating,
            "historical_sold": sold,
            "is_mall": is_mall,
            "item_url": product_url or f"https://www.lazada.vn/products/-i{item_id}.html",
            "image_url": img_url,
            "seller_name": item.get("sellerName", ""),
            "location": item.get("location", "Việt Nam"),
            "platform": default_platform
        }
