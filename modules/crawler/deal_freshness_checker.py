import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Any

from database.db_manager import DatabaseManager
from modules.crawler.deal_hunter import DealHunter
from modules.affiliate.lazada_provider import LazadaAffiliateProvider

logger = logging.getLogger("DealFreshnessChecker")

class DealFreshnessChecker:
    """
    Module kiểm tra chủ động độ tươi của deal (Proactive Deal Freshness Checker):
    - Quét định kỳ tất cả các deal đang hoạt động trong ngày hoặc 48h qua
    - Kiểm tra giá hiện tại và tình trạng còn hàng trên Shopee và Lazada
    - Tự động hạ cờ (is_stale=1) các deal đã hết hàng, link chết hoặc hết khuyến mại
    - Ngăn chặn người dùng bấm vào link bị thất vọng (giảm tỷ lệ thoát trang và khiếu nại)
    """

    def __init__(self, db: Optional[DatabaseManager] = None):
        self.db = db or DatabaseManager()
        self.lazada_provider = LazadaAffiliateProvider()

    def check_all_active_deals(self, max_deals: int = 50) -> Dict[str, Any]:
        """Kiểm tra hàng loạt các deal đang hiển thị"""
        logger.info("🔍 Bắt đầu quét kiểm tra độ tươi của tất cả các deal đang hoạt động...")
        deals = self.db.get_deals(limit=max_deals, is_stale=0)
        checked_count = 0
        stale_count = 0
        valid_count = 0
        results = []

        for d in deals:
            item_id = str(d.get("item_id", ""))
            platform = str(d.get("platform", "SHOPEE")).upper()
            is_fresh = True

            try:
                if platform == "LAZADA":
                    is_fresh = self.lazada_provider.verify_deal_freshness(d)
                else:
                    is_fresh = DealHunter.verify_deal_freshness(d)
            except Exception as e:
                logger.warning(f"Lỗi kiểm tra deal {item_id}: {e}")
                is_fresh = True  # Giữ an toàn nếu lỗi mạng tạm thời

            checked_count += 1
            if not is_fresh:
                stale_count += 1
                self.db.mark_deal_stale(item_id, is_stale=1)
                logger.info(f"⚠️ Deal [{item_id}] ({platform}) đã hết hàng hoặc hết sale -> Đã đánh dấu IS_STALE=1")
            else:
                valid_count += 1

            results.append({
                "item_id": item_id,
                "name": d.get("name"),
                "platform": platform,
                "is_fresh": is_fresh,
                "status": "VALID" if is_fresh else "STALE"
            })

            time.sleep(0.3)  # Rate limiting nhẹ giữa các request

        logger.info(f"✅ Hoàn tất kiểm tra độ tươi: {checked_count} deal đã quét, {valid_count} deal tươi, {stale_count} deal hết hàng.")
        return {
            "status": "SUCCESS",
            "checked_count": checked_count,
            "valid_count": valid_count,
            "stale_count": stale_count,
            "results": results
        }
