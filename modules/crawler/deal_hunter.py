import requests
import logging
import hashlib
import time
import os
from typing import List, Dict, Optional

from config.settings import (
    MIN_RATING_STAR,
    MIN_HISTORICAL_SOLD,
    MIN_DISCOUNT_PERCENT,
    TOP_DEALS_PER_CATEGORY,
    SHOPEE_APP_ID,
    SHOPEE_SECRET
)
from database.db_manager import DatabaseManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

class DealHunter:
    SEARCH_ITEMS_URL = "https://shopee.vn/api/v4/search/search_items"
    
    BASE_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Referer": "https://shopee.vn/",
        "X-Requested-With": "XMLHttpRequest"
    }

    def __init__(self, db: DatabaseManager = None, cookie: str = ""):
        self.db = db or DatabaseManager()
        # Đọc cookie từ tham số hoặc biến môi trường
        self.cookie = cookie or os.getenv("SHOPEE_COOKIE", "")

    def calculate_score(self, item: Dict) -> float:
        """
        Tính điểm sản phẩm - ƯU TIÊN HÀNG ĐẦU CHO CÁC SẢN PHẨM PHỔ BIẾN & BÁN CHẠY NHẤT.
        Yêu cầu người dùng: 'về các sản phẩm hãy ưu tiên các sản phẩm phổ biến hơn'
        - Trọng số cao nhất dành cho Lượt bán thực tế (historical_sold)
        - Ưu tiên lớn cho gian hàng chính hãng Shopee Mall (+15đ) và Shop Yêu Thích (+8đ)
        - Điểm uy tín đánh giá sao (rating_star >= 4.6)
        - Tỷ lệ giảm giá thực tế (discount_percent)
        """
        rating = float(item.get("rating_star", 0))
        sold = int(item.get("historical_sold", 0))
        discount = int(item.get("discount_percent", 0))
        
        # 1. Bộ lọc điều kiện cứng: Phải là sản phẩm đã có lượng mua uy tín
        min_sold = MIN_HISTORICAL_SOLD
        if rating < MIN_RATING_STAR:
            return 0.0
        if sold < min_sold:
            return 0.0
        if discount < MIN_DISCOUNT_PERCENT:
            return 0.0

        # Ưu tiên cực mạnh cho Shop Mall và Shop Yêu Thích vì đây là bảo chứng cho đồ phổ biến
        shop_bonus = 15.0 if item.get("is_mall") else (8.0 if item.get("is_preferred") else 0.0)

        # Điểm lượt bán: Sản phẩm bán 5k, 10k, 50k sẽ bứt phá điểm số (tối đa 45 điểm)
        sold_score = min(sold / 350.0, 45.0)

        # Điểm đánh giá (rating 4.6 - 5.0): tối đa 20 điểm
        rating_score = max(0.0, (rating - 4.0)) * 20.0

        # Điểm giảm giá: tối đa 20 điểm
        discount_score = min(discount, 60) * 0.33

        score = sold_score + shop_bonus + rating_score + discount_score
        return round(score, 2)

    FLASH_SALE_URL = "https://shopee.vn/api/v4/flash_sale/flash_sale_get_items"

    def search_deals_by_category(self, cat_id: int, category_name: str, limit: int = 30) -> List[Dict]:
        """Cào sản phẩm thật 100% từ Shopee (Hỗ trợ Flash Sale & Shopee Open API)"""
        logging.info(f"Đang cào dữ liệu thật trên Shopee cho ngành: [{category_name}] (ID: {cat_id})...")
        self.cookie = os.getenv("SHOPEE_COOKIE", self.cookie)
        
        # 1. Nếu có cấu hình Shopee Affiliate Open API -> Ưu tiên gọi API chính thức
        shopee_app_id = os.getenv("SHOPEE_APP_ID", SHOPEE_APP_ID)
        shopee_secret = os.getenv("SHOPEE_SECRET", SHOPEE_SECRET)
        if shopee_app_id and shopee_secret:
            try:
                deals = self._fetch_via_shopee_open_api(cat_id, category_name, limit)
                if deals:
                    return deals
            except Exception as e:
                logging.warning(f"Lỗi gọi Shopee Open API, chuyển sang cào trực tiếp: {e}")

        # 2. Cào qua Shopee Flash Sale API (Chính xác, deal hời nhất và không bị chặn WAF 403 với Cookie)
        items = self._fetch_via_flash_sale_api(cat_id, category_name, limit)

        # 3. Nếu Flash Sale không có thì thử Search API (có bẫy lỗi WAF 403)
        if not items:
            items = self._fetch_via_search_api(cat_id, category_name, limit)

        if not items:
            logging.warning(f"Không tìm thấy sản phẩm nào phù hợp cho ngành {category_name}.")
            return []

        # Chấm điểm & lọc theo tiêu chuẩn thực tế
        scored_deals = []
        for it in items:
            sc = self.calculate_score(it)
            if sc > 0:
                it["deal_score"] = sc
                scored_deals.append(it)
                self.db.save_deal(it)

        if not scored_deals and items:
            # Nếu bộ lọc quá khắt khe, lấy các deal có giảm giá tốt nhất
            for it in items:
                it["deal_score"] = round(it.get("discount_percent", 0) * 0.5 + min(it.get("historical_sold", 0) / 1000, 20), 2)
                self.db.save_deal(it)
                scored_deals.append(it)

        top_deals = sorted(scored_deals, key=lambda x: x.get("deal_score", 0), reverse=True)[:TOP_DEALS_PER_CATEGORY]
        logging.info(f"==> Đã lọc được {len(top_deals)} deal THẬT đạt chuẩn cho [{category_name}]")
        return top_deals

    def _fetch_via_flash_sale_api(self, cat_id: int, category_name: str, limit: int = 30) -> List[Dict]:
        """Lấy deal hời thật từ Shopee Flash Sale API bằng Cookie"""
        headers = dict(self.BASE_HEADERS)
        if self.cookie:
            headers["Cookie"] = self.cookie

        # Thử lấy theo categoryid trước
        items_data = []
        try:
            r = requests.get(self.FLASH_SALE_URL, headers=headers, params={"categoryid": cat_id, "limit": limit}, timeout=12)
            if r.status_code == 200:
                data = r.json()
                items_data = data.get("data", {}).get("items", []) or []
            else:
                logging.error(f"❌ [LỖI FLASH SALE THEO NGÀNH {cat_id}]: HTTP {r.status_code} - {r.text[:200]}")
        except Exception as e:
            logging.error(f"❌ [NGOẠI LỆ KẾT NỐI FLASH SALE THEO NGÀNH {cat_id}]: {e}")

        # Nếu ngành chưa có deal flash sale thì lấy danh sách Flash Sale chung
        # Ghi chú: category_name sẽ được ghi đè thành 'Flash Sale Chung' để tránh gán sai ngành
        is_general_fallback = False
        if not items_data:
            try:
                r = requests.get(self.FLASH_SALE_URL, headers=headers, params={"limit": 50}, timeout=12)
                if r.status_code == 200:
                    data = r.json()
                    items_data = data.get("data", {}).get("items", []) or []
                    is_general_fallback = True
                    logging.info(f"Ngành [{category_name}] không có Flash Sale riêng, lấy Flash Sale chung toàn sàn.")
                else:
                    logging.error(f"❌ [LỖI FLASH SALE CHUNG]: HTTP {r.status_code} - {r.text[:200]}")
            except Exception as e:
                logging.error(f"❌ [NGOẠI LỆ KẾT NỐI FLASH SALE CHUNG]: {e}")

        parsed_items = []
        for it in items_data:
            itemid = str(it.get("itemid", ""))
            shopid = str(it.get("shopid", ""))
            if not itemid or not shopid:
                continue

            raw_price = (it.get("price", 0) or 0) / 100000.0
            raw_price_before = (it.get("price_before_discount", 0) or 0) / 100000.0
            discount = it.get("raw_discount") or 0
            if not discount and raw_price_before > raw_price:
                discount = int(round((1 - raw_price / raw_price_before) * 100))

            rating = round(it.get("item_rating", {}).get("rating_star", 5.0), 1)
            sold = it.get("historical_sold", 0) or 0
            name = (it.get("name") or it.get("promo_name") or "").strip()

            deal_dict = {
                "item_id": itemid,
                "shop_id": shopid,
                "cat_id": cat_id,
                "category_name": "Flash Sale Chung" if is_general_fallback else category_name,
                "name": name,
                "price_original": raw_price_before if raw_price_before > 0 else raw_price,
                "price_sale": raw_price,
                "discount_percent": discount,
                "rating_star": rating,
                "historical_sold": sold,
                "is_mall": bool(it.get("is_shop_official", False)),
                "is_preferred": bool(it.get("is_shop_preferred", False) or it.get("is_shop_preferred_plus", False)),
                "item_url": f"https://shopee.vn/product/{shopid}/{itemid}",
                "image_url": f"https://down-vn.img.susercontent.com/file/{it.get('image')}" if it.get("image") else ""
            }
            parsed_items.append(deal_dict)

        return parsed_items

    def _fetch_via_search_api(self, cat_id: int, category_name: str, limit: int = 30) -> List[Dict]:
        """Gọi qua Search API Web kèm Cookie (có xử lý WAF)"""
        headers = dict(self.BASE_HEADERS)
        if self.cookie:
            headers["Cookie"] = self.cookie

        params = {
            "by": "sales",
            "categoryids": cat_id,
            "limit": limit,
            "newest": 0,
            "order": "desc",
            "page_type": "search",
            "scenario": "PAGE_OTHERS",
            "version": 2
        }

        try:
            response = requests.get(self.SEARCH_ITEMS_URL, headers=headers, params=params, timeout=15)
        except Exception as e:
            logging.warning(f"Lỗi mạng khi kết nối tới Shopee Search API: {e}")
            return []

        if response.status_code == 403:
            logging.warning("Shopee Search API bị WAF chặn 403 (yêu cầu token JS).")
            return []
        elif response.status_code != 200:
            logging.warning(f"Shopee Search API trả về HTTP {response.status_code}")
            return []

        data = response.json()
        item_sections = data.get("items", []) or []
        items = []
        for entry in item_sections:
            basic = entry.get("item_basic", {})
            if not basic:
                continue
            raw_price = basic.get("price", 0) / 100000.0
            raw_price_before = basic.get("price_before_discount", 0) / 100000.0
            discount = 0
            if raw_price_before > raw_price:
                discount = int(round((1 - raw_price / raw_price_before) * 100))
            elif basic.get("raw_discount"):
                discount = basic.get("raw_discount")

            rating = round(basic.get("item_rating", {}).get("rating_star", 0), 1)
            sold = basic.get("historical_sold", 0)
            item_id = str(basic.get("itemid"))
            shop_id = str(basic.get("shopid"))

            items.append({
                "item_id": item_id,
                "shop_id": shop_id,
                "cat_id": cat_id,
                "category_name": category_name,
                "name": basic.get("name", "").strip(),
                "price_original": raw_price_before if raw_price_before > 0 else raw_price,
                "price_sale": raw_price,
                "discount_percent": discount,
                "rating_star": rating,
                "historical_sold": sold,
                "is_mall": basic.get("show_official_shop_label", False),
                "is_preferred": basic.get("is_preferred_plus", False) or basic.get("show_shopee_verified_label", False),
                "item_url": f"https://shopee.vn/product/{shop_id}/{item_id}",
                "image_url": f"https://down-vn.img.susercontent.com/file/{basic.get('image')}" if basic.get('image') else ""
            })
        return items

    def _fetch_via_shopee_open_api(self, cat_id: int, category_name: str, limit: int) -> List[Dict]:
        """Lấy sản phẩm chính thức qua Shopee Affiliate Open API GraphQL"""
        endpoint = "https://open-api.affiliate.shopee.vn/graphql"
        timestamp = int(time.time())
        app_id = os.getenv("SHOPEE_APP_ID", SHOPEE_APP_ID)
        secret = os.getenv("SHOPEE_SECRET", SHOPEE_SECRET)

        query = """
        query {
            productOfferV2(page: 1, limit: %d) {
                nodes {
                    itemId
                    productName
                    price
                    commissionRate
                    imageUrl
                    offerLink
                    shopType
                    sales
                    ratingStar
                }
            }
        }
        """ % limit

        factor = f"{app_id}{timestamp}{query}{secret}"
        signature = hashlib.sha256(factor.encode("utf-8")).hexdigest()
        headers = {
            "Authorization": f"SHA256 Credential={app_id}, Timestamp={timestamp}, Signature={signature}",
            "Content-Type": "application/json"
        }

        try:
            resp = requests.post(endpoint, json={"query": query}, headers=headers, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                nodes = data.get("data", {}).get("productOfferV2", {}).get("nodes", [])
                results = []
                for n in nodes:
                    raw_price = float(n.get("price", 0))
                    # commissionRate là tỷ lệ hoa hồng affiliate, KHÔNG phải discount
                    # discount_percent cần tính từ giá gốc vs giá sale (Open API chỉ trả 1 giá)
                    deal = {
                        "item_id": str(n.get("itemId")),
                        "cat_id": cat_id,
                        "category_name": category_name,
                        "name": n.get("productName"),
                        "price_original": raw_price,
                        "price_sale": raw_price,
                        "discount_percent": 0,  # Open API không cung cấp giá gốc để tính discount
                        "commission_rate": float(n.get("commissionRate", 0)),
                        "rating_star": float(n.get("ratingStar", 5.0)),
                        "historical_sold": int(n.get("sales", 0)),
                        "is_mall": "OFFICIAL" in str(n.get("shopType", "")),
                        "is_preferred": True,
                        "item_url": n.get("offerLink"),
                        "aff_url": n.get("offerLink"),
                        "image_url": n.get("imageUrl")
                    }
                    score = self.calculate_score(deal)
                    if score > 0:
                        deal["deal_score"] = score
                        results.append(deal)
                        self.db.save_deal(deal)
                return sorted(results, key=lambda x: x["deal_score"], reverse=True)[:TOP_DEALS_PER_CATEGORY]
            else:
                raise RuntimeError(f"Shopee Affiliate API trả về lỗi {resp.status_code}: {resp.text}")
        except Exception as e:
            raise RuntimeError(f"Lỗi khi gọi Shopee Affiliate API: {e}")

    @classmethod
    def verify_deal_freshness(cls, deal: Dict, cookie: str = "") -> bool:
        """
        Kiểm tra thời gian thực xem deal có còn sống và còn giá sale không:
        - Nếu sản phẩm bị xóa, hết hàng hoặc đã tăng lại giá gốc -> Trả về False
        - Nếu vẫn còn giá sale tốt -> Trả về True
        """
        item_id = str(deal.get("item_id", ""))
        shop_id = str(deal.get("shop_id", ""))
        original_sale_price = float(deal.get("price_sale", 0))

        if not item_id or original_sale_price <= 0:
            return False

        if deal.get("price_badge") == "LOSS_LEADER_1K":
            return True

        # Nếu có shop_id hợp lệ, gọi thử API Shopee kiểm tra nhanh
        if shop_id and shop_id.isdigit() and item_id.isdigit():
            headers = dict(cls.BASE_HEADERS)
            cookie_val = cookie or os.getenv("SHOPEE_COOKIE", "")
            if cookie_val:
                headers["Cookie"] = cookie_val
            try:
                check_url = f"https://shopee.vn/api/v4/item/get?itemid={item_id}&shopid={shop_id}"
                resp = requests.get(check_url, headers=headers, timeout=8)
                if resp.status_code == 200:
                    data = resp.json().get("data", {})
                    if data:
                        current_price = (data.get("price", 0) or 0) / 100000.0
                        stock = data.get("stock", 10)
                        # Nếu hết hàng hoặc giá hiện tại tăng vọt cao hơn 25% so với giá sale đã cào
                        if stock <= 0 or (current_price > original_sale_price * 1.25):
                            logging.warning(f"⚠️ Deal [{deal.get('name', '')[:30]}] đã hết hàng hoặc quay về giá gốc ({current_price:,}đ). Bỏ qua!")
                            return False
                        return True
            except Exception as e:
                logging.debug(f"Không thể kiểm tra trực tiếp qua API Shopee: {e}")

        # Dự phòng logic: Deal hợp lệ nếu có giảm giá và thông tin đầy đủ
        return bool(deal.get("discount_percent", 0) >= 10 and original_sale_price > 0)

    def fetch_loss_leader_deals(self, limit: int = 3) -> List[Dict]:
        """
        Săn các Deal Mồi Siêu Rẻ (1K - 15K / Freeship 0Đ) THẬT từ Shopee Flash Sale.
        Tuyệt đối không fake dữ liệu hay tạo deal ảo trong database.
        """
        logging.info("🎯 Đang cào các Deal Mồi Giá Rẻ THẬT từ Shopee Flash Sale...")
        headers = dict(self.BASE_HEADERS)
        cookie_val = self.cookie or os.getenv("SHOPEE_COOKIE", "")
        if cookie_val:
            headers["Cookie"] = cookie_val

        real_deals = []
        try:
            resp = requests.get(self.FLASH_SALE_URL, headers=headers, params={"limit": 60}, timeout=12)
            if resp.status_code == 200:
                data = resp.json().get("data", {})
                items_data = data.get("items", []) or []
                for it in items_data:
                    raw_price = (it.get("price") or 0) / 100000.0
                    raw_price_before = (it.get("price_before_discount") or 0) / 100000.0
                    
                    # Lọc các deal thật có giá sale rẻ (<= 15.000đ)
                    if 0 < raw_price <= 15000:
                        itemid = str(it.get("itemid"))
                        shopid = str(it.get("shopid"))
                        deal_dict = {
                            "item_id": itemid,
                            "shop_id": shopid,
                            "cat_id": it.get("catid", 0),
                            "category_name": "Flash Sale Giá Rẻ",
                            "name": (it.get("name") or it.get("promo_name") or "").strip(),
                            "price_original": raw_price_before if raw_price_before > 0 else raw_price,
                            "price_sale": raw_price,
                            "discount_percent": int(round((1 - raw_price / raw_price_before) * 100)) if raw_price_before > raw_price else 0,
                            "rating_star": round(it.get("item_rating", {}).get("rating_star", 5.0), 1),
                            "historical_sold": it.get("historical_sold", 0) or 0,
                            "is_mall": bool(it.get("is_shop_official", False)),
                            "is_preferred": bool(it.get("is_shop_preferred", False)),
                            "deal_score": 95.0,
                            "price_badge": "LOSS_LEADER_1K",
                            "item_url": f"https://shopee.vn/product/{shopid}/{itemid}",
                            "image_url": f"https://down-vn.img.susercontent.com/file/{it.get('image')}" if it.get("image") else ""
                        }
                        real_deals.append(deal_dict)
                        self.db.save_deal(deal_dict)
                        if len(real_deals) >= limit:
                            break
            elif resp.status_code == 403:
                logging.error("Shopee Flash Sale API bị WAF chặn 403. Vui lòng cập nhật Cookie Shopee trong Cài Đặt!")
            else:
                logging.error(f"Shopee Flash Sale API trả về mã lỗi HTTP {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            logging.error(f"Ngoại lệ khi cào deal rẻ từ Shopee Flash Sale: {e}")

        if not real_deals:
            logging.warning("Không tìm thấy deal rẻ <= 15K nào đang mở trên Flash Sale Shopee thời điểm này (Không fake dữ liệu).")
        else:
            logging.info(f"==> Đã cào được {len(real_deals)} Deal Mồi THẬT từ Shopee Flash Sale!")
        return real_deals


