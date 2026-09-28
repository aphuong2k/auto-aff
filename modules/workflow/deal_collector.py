import os
import sys
import logging
from datetime import datetime
from typing import List, Dict, Optional, Tuple

from config.settings import (
    MIN_RATING_STAR,
    MIN_HISTORICAL_SOLD,
    MIN_DISCOUNT_PERCENT,
    TOP_DEALS_PER_CATEGORY
)
from database.db_manager import DatabaseManager
from modules.crawler.deal_hunter import DealHunter
from modules.crawler.lazada_deal_hunter import LazadaDealHunter

collector_logger = logging.getLogger("DealCollector")
collector_logger.setLevel(logging.INFO)
if not collector_logger.handlers:
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(logging.Formatter("%(asctime)s [DealCollector] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    collector_logger.addHandler(sh)


class DealCollector:
    """
    Trục 1: Pipeline thu thập, thẩm định & chuẩn hóa Deal trung tâm (Deal Data Pipeline).
    - Tách biệt hoàn toàn khỏi luồng duyệt Group Facebook.
    - Cào đa sàn: Shopee & Lazada.
    - Định danh duy nhất theo tuple: (platform, item_id, shop_id).
    - Upsert vào kho dữ liệu deals: cập nhật giá biến động, discount, deal_score, reset is_stale = 0.
    - Áp dụng Quality Gate nghiêm ngặt:
        + rating_star >= 4.6
        + historical_sold >= 500
        + discount_percent >= 15%
        + Ưu tiên Shopee Mall / LazMall / Shop Yêu Thích.
    """

    # Danh mục trọng tâm chuẩn hóa cho toàn hệ thống
    CORE_CATEGORIES = [
        {"cat_id": 11035567, "name": "Thời Trang Nam"},
        {"cat_id": 11035639, "name": "Thời Trang Nữ"},
        {"cat_id": 11036132, "name": "Thiết Bị Điện Tử"},
        {"cat_id": 11036971, "name": "Thiết Bị Điện Gia Dụng"},
        {"cat_id": 0,        "name": "Săn Deal Tổng Hợp"}
    ]

    def __init__(self, db: Optional[DatabaseManager] = None):
        self.db = db or DatabaseManager()
        self.shopee_hunter = DealHunter(self.db)
        self.lazada_hunter = LazadaDealHunter(self.db)

    def is_deal_qualified(self, deal: Dict) -> Tuple[bool, str]:
        """
        Kiểm định chất lượng deal theo tiêu chuẩn khắt khe (Quality Gate).
        Tuyệt đối không đẩy deal rác, deal đánh giá thấp hoặc bán ế vào hệ thống.
        """
        rating = float(deal.get("rating_star") or 0.0)
        sold = int(deal.get("historical_sold") or 0)
        discount = int(deal.get("discount_percent") or 0)
        price_sale = float(deal.get("price_sale") or 0.0)

        if price_sale <= 0:
            return False, "Giá bán không hợp lệ (<= 0)"

        # 1. Đánh giá sao: Tối thiểu 4.6 (hoặc cấu hình)
        min_rating = max(MIN_RATING_STAR, 4.6)
        if rating > 0 and rating < min_rating:
            return False, f"Rating {rating} < {min_rating} sao"

        # 2. Lượt bán: Tối thiểu 500 lượt bán uy tín
        min_sold = max(MIN_HISTORICAL_SOLD, 500)
        if sold < min_sold:
            return False, f"Lượt bán {sold} < {min_sold} lượt"

        # 3. Mức giảm giá: Tối thiểu 15%
        min_disc = max(MIN_DISCOUNT_PERCENT, 15)
        if discount < min_disc:
            return False, f"Giảm giá {discount}% < {min_disc}%"

        return True, "QUALIFIED"

    def upsert_deal(self, deal: Dict) -> str:
        """
        Upsert deal vào CSDL dựa trên platform + item_id + shop_id.
        Cập nhật biến động giá, discount_percent, deal_score, is_stale = 0, updated_at.
        Trả về 'INSERTED', 'UPDATED', hoặc 'SKIPPED'.
        """
        item_id = str(deal.get("item_id", "")).strip()
        if not item_id:
            return "SKIPPED"

        platform = (deal.get("platform") or "SHOPEE").upper()
        shop_id = str(deal.get("shop_id") or "")
        name = deal.get("name", "Sản phẩm")
        category_name = self.db.classify_product_niche(name, deal.get("category_name", ""))
        deal["category_name"] = category_name

        score = float(deal.get("deal_score") or 0.0)
        if score <= 0:
            score = self.shopee_hunter.calculate_score(deal)
        deal["deal_score"] = score

        today = datetime.now().strftime("%Y-%m-%d")
        comm_rate = float(deal.get("commission_rate") or (12.0 if deal.get("is_mall") else 5.0))
        is_extra = 1 if deal.get("is_extra") or comm_rate >= 8.0 else 0

        with self.db.get_connection() as conn:
            # Kiểm tra deal đã tồn tại chưa
            existing = conn.execute("SELECT item_id, price_sale, deal_score FROM deals WHERE item_id = ?", (item_id,)).fetchone()

            if existing:
                conn.execute("""
                    UPDATE deals SET
                        name = ?,
                        category_name = ?,
                        price_original = ?,
                        price_sale = ?,
                        discount_percent = ?,
                        rating_star = ?,
                        historical_sold = ?,
                        deal_score = ?,
                        item_url = COALESCE(?, item_url),
                        aff_url = COALESCE(?, aff_url),
                        image_url = COALESCE(?, image_url),
                        platform = ?,
                        shop_id = ?,
                        is_stale = 0,
                        commission_rate = ?,
                        is_extra = ?,
                        status = 'QUALIFIED',
                        last_checked_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE item_id = ?
                """, (
                    name, category_name, deal.get("price_original"), deal.get("price_sale"),
                    deal.get("discount_percent"), deal.get("rating_star"), deal.get("historical_sold"),
                    score, deal.get("item_url"), deal.get("aff_url"), deal.get("image_url"),
                    platform, shop_id, comm_rate, is_extra, item_id
                ))
                action = "UPDATED"
            else:
                conn.execute("""
                    INSERT INTO deals (
                        item_id, cat_id, category_name, name, price_original,
                        price_sale, discount_percent, rating_star, historical_sold,
                        deal_score, item_url, aff_url, image_url, created_date,
                        platform, shop_id, is_stale, commission_rate, is_extra,
                        status, last_checked_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, 'QUALIFIED', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """, (
                    item_id, deal.get("cat_id"), category_name, name,
                    deal.get("price_original"), deal.get("price_sale"), deal.get("discount_percent"),
                    deal.get("rating_star"), deal.get("historical_sold"), score,
                    deal.get("item_url"), deal.get("aff_url"), deal.get("image_url"),
                    today, platform, shop_id, comm_rate, is_extra
                ))
                action = "INSERTED"

            conn.commit()

        # Tự động ghi nhận lịch sử biến động giá
        if deal.get("price_sale"):
            try:
                self.db.record_price_history(
                    item_id=item_id,
                    price=float(deal["price_sale"]),
                    original_price=float(deal.get("price_original") or deal["price_sale"]),
                    discount_percent=int(deal.get("discount_percent") or 0),
                    recorded_date=today
                )
            except Exception:
                pass

        return action

    def collect_deals_for_category(
        self,
        category_name: str,
        cat_id: Optional[int] = None,
        limit: int = 25
    ) -> Dict:
        """
        Quét và thẩm định deal cho một danh mục ngành hàng cụ thể từ cả Shopee và Lazada.
        """
        collector_logger.info(f"🔍 [COLLECTOR]: Bắt đầu cào deal trung tâm cho ngành [{category_name}]...")
        scanned_count = 0
        qualified_count = 0
        saved_count = 0
        updated_count = 0

        all_raw_deals: List[Dict] = []

        # 1. Cào từ Shopee
        try:
            cid = cat_id or 11035567
            shopee_deals = self.shopee_hunter.search_deals_by_category(cid, category_name, limit=limit)
            for d in shopee_deals:
                d["platform"] = "SHOPEE"
                all_raw_deals.append(d)
        except Exception as e:
            collector_logger.warning(f"⚠️ Lỗi cào Shopee cho ngành [{category_name}]: {e}")

        # 2. Cào từ Lazada
        try:
            laz_deals = self.lazada_hunter.search_deals_by_category(category_name, limit=limit)
            for d in laz_deals:
                d["platform"] = "LAZADA"
                all_raw_deals.append(d)
        except Exception as e:
            collector_logger.warning(f"⚠️ Lỗi cào Lazada cho ngành [{category_name}]: {e}")

        scanned_count = len(all_raw_deals)

        # 3. Lọc qua Quality Gate & Upsert vào DB
        for deal in all_raw_deals:
            is_valid, reason = self.is_deal_qualified(deal)
            if not is_valid:
                continue

            qualified_count += 1
            action = self.upsert_deal(deal)
            if action == "INSERTED":
                saved_count += 1
            elif action == "UPDATED":
                updated_count += 1

        collector_logger.info(
            f"✅ [HOÀN THÀNH NGÀNH {category_name}]: "
            f"Quét {scanned_count} deal | Đạt chuẩn: {qualified_count} | Mới: {saved_count} | Cập nhật: {updated_count}"
        )

        return {
            "category_name": category_name,
            "scanned": scanned_count,
            "qualified": qualified_count,
            "inserted": saved_count,
            "updated": updated_count
        }

    def collect_all_categories(self, limit_per_cat: int = 20) -> Dict:
        """
        Duyệt quét toàn bộ danh mục trọng tâm để làm giàu kho deal (Deal Pool).
        Được gọi độc lập định kỳ bởi Scheduler hoặc thủ công từ nút 'Thu Thập Deal'.
        """
        start_time = datetime.now()
        collector_logger.info("=" * 70)
        collector_logger.info("🚀 [DEAL COLLECTOR]: KHỞI ĐỘNG PHIÊN THU THẬP & THẨM ĐỊNH DEAL TRUNG TÂM")
        collector_logger.info(f"⏰ Thời gian bắt đầu: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        collector_logger.info("=" * 70)

        results = []
        total_scanned = 0
        total_qualified = 0
        total_inserted = 0
        total_updated = 0

        for cat in self.CORE_CATEGORIES:
            res = self.collect_deals_for_category(cat["name"], cat_id=cat.get("cat_id"), limit=limit_per_cat)
            results.append(res)
            total_scanned += res["scanned"]
            total_qualified += res["qualified"]
            total_inserted += res["inserted"]
            total_updated += res["updated"]

        elapsed = round((datetime.now() - start_time).total_seconds(), 2)
        collector_logger.info("=" * 70)
        collector_logger.info(
            f"🎉 [DEAL COLLECTOR HOÀN TẤT TRONG {elapsed}s]:\n"
            f"   • Tổng số deal quét: {total_scanned}\n"
            f"   • Đạt chuẩn Quality Gate: {total_qualified}\n"
            f"   • Deal thêm mới vào kho: {total_inserted}\n"
            f"   • Deal cập nhật biến động giá: {total_updated}"
        )
        collector_logger.info("=" * 70)

        return {
            "status": "SUCCESS",
            "duration_seconds": elapsed,
            "total_scanned": total_scanned,
            "total_qualified": total_qualified,
            "total_inserted": total_inserted,
            "total_updated": total_updated,
            "details": results
        }
