import logging
from typing import Dict, List, Optional
from database.db_manager import DatabaseManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

class PriceHistoryTracker:
    """Module theo dõi biến động giá lịch sử & phát hiện giảm giá ảo / đáy giá 30 ngày"""

    def __init__(self, db: Optional[DatabaseManager] = None):
        self.db = db or DatabaseManager()

    def analyze_price_verdict(self, deal: Dict) -> Dict:
        """
        Phân tích độ tin cậy của mức giảm giá:
        - HISTORICAL_LOW: Giá thấp nhất từng ghi nhận (Đáy lịch sử)
        - REAL_DISCOUNT: Giảm thật so với trung bình giá 7-30 ngày
        - SUSPICIOUS_MARKUP: Nghi vấn kê giá gốc lên cao rồi giảm ảo
        - HOT_DISCOUNT: Sản phẩm mới theo dõi nhưng có mức giảm sâu uy tín
        """
        item_id = str(deal.get("item_id", ""))
        current_sale = float(deal.get("price_sale", 0))
        current_orig = float(deal.get("price_original", current_sale))
        discount = int(deal.get("discount_percent", 0))

        if current_sale <= 0:
            return {"badge": "NORMAL", "badge_text": "Giá thường", "is_genuine": True}

        history = self.db.get_price_history(item_id, limit_days=30)
        
        # Nếu chưa có lịch sử (sản phẩm mới quét lần đầu)
        if len(history) <= 1:
            if discount >= 35 and deal.get("rating_star", 0) >= 4.8 and deal.get("historical_sold", 0) >= 500:
                return {
                    "badge": "HOT_DISCOUNT",
                    "badge_text": "⚡ GIẢM SÂU ĐÁNH GIÁ TỐT",
                    "min_price": current_sale,
                    "max_price": current_orig,
                    "avg_price": current_sale,
                    "history_count": len(history),
                    "is_genuine": True,
                    "savings": int(current_orig - current_sale)
                }
            return {
                "badge": "UNVERIFIED",
                "badge_text": "Mới ghi nhận",
                "min_price": current_sale,
                "max_price": current_orig,
                "avg_price": current_sale,
                "history_count": len(history),
                "is_genuine": True,
                "savings": int(current_orig - current_sale)
            }

        past_prices = [float(h["price"]) for h in history]
        min_past_price = min(past_prices)
        max_past_price = max(past_prices)
        avg_past_price = sum(past_prices) / len(past_prices)

        # 1. Phát hiện Tăng Giá Ảo (Suspicious Markup)
        # Nếu giá gốc hiện tại cao hơn hẳn max giá gốc quá khứ và giá sale không hề rẻ hơn
        past_orig_prices = [float(h.get("original_price") or h["price"]) for h in history if h.get("original_price")]
        if past_orig_prices:
            avg_past_orig = sum(past_orig_prices) / len(past_orig_prices)
            if current_orig > avg_past_orig * 1.3 and current_sale >= avg_past_price:
                return {
                    "badge": "SUSPICIOUS_MARKUP",
                    "badge_text": "⚠️ NGHI VẤN TĂNG GIÁ ẢO",
                    "min_price": min_past_price,
                    "max_price": max_past_price,
                    "avg_price": round(avg_past_price, 0),
                    "history_count": len(history),
                    "is_genuine": False,
                    "savings": 0
                }

        # 2. Đáy lịch sử 30 ngày (Historical Low)
        if current_sale <= min_past_price:
            return {
                "badge": "HISTORICAL_LOW",
                "badge_text": "📉 ĐÁY LỊCH SỬ 30 NGÀY",
                "min_price": current_sale,
                "max_price": max_past_price,
                "avg_price": round(avg_past_price, 0),
                "history_count": len(history),
                "is_genuine": True,
                "savings": int(max(max_past_price - current_sale, current_orig - current_sale))
            }

        # 3. Giảm thật đã kiểm chứng (Real Discount)
        if current_sale < avg_past_price * 0.92:
            return {
                "badge": "REAL_DISCOUNT",
                "badge_text": "✅ GIẢM THẬT ĐÃ KIỂM CHỨNG",
                "min_price": min_past_price,
                "max_price": max_past_price,
                "avg_price": round(avg_past_price, 0),
                "history_count": len(history),
                "is_genuine": True,
                "savings": int(avg_past_price - current_sale)
            }

        return {
            "badge": "STABLE",
            "badge_text": "Giá ổn định",
            "min_price": min_past_price,
            "max_price": max_past_price,
            "avg_price": round(avg_past_price, 0),
            "history_count": len(history),
            "is_genuine": True,
            "savings": int(current_orig - current_sale)
        }

    def enrich_deal(self, deal: Dict) -> Dict:
        """Đính kèm thông tin phân tích lịch sử giá vào deal và lưu xuống DB"""
        verdict = self.analyze_price_verdict(deal)
        deal["price_badge"] = verdict["badge"]
        deal["price_verdict_text"] = verdict["badge_text"]
        deal["price_analysis"] = verdict

        self.db.update_deal_media(
            item_id=str(deal.get("item_id")),
            price_badge=verdict["badge"]
        )
        return deal
