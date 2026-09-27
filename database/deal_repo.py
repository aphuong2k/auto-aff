"""
Deal Repository Module
======================
Quản lý toàn bộ thao tác CRUD liên quan tới Deals:
- Lưu trữ, phân loại ngành hàng tự động (dùng CategoryMatcher)
- Cập nhật media (ảnh đóng khung banner, huy hiệu giá)
- Lọc deal đa sàn (Shopee / Lazada), độ tươi, deal mồi 1K, hoa hồng cao
- Lưu vết lịch sử biến động giá (Price History Tracker)
"""

from datetime import datetime
from typing import Dict, List, Optional, Any

from database.connection import BaseRepository


class DealRepository(BaseRepository):
    """Repository quản lý sản phẩm / Deal"""

    @staticmethod
    def classify_product_niche(name: str, current_cat: str = "") -> str:
        """Phân loại chính xác ngành hàng dựa trên CategoryMatcher (nguồn sự thật duy nhất)."""
        from config.category_mapping import CategoryMatcher
        matcher = CategoryMatcher()

        # 1. Nếu current_cat đã được chỉ định rõ và khớp danh mục chuẩn -> giữ nguyên
        if current_cat:
            match = matcher.match_group(group_cat=current_cat)
            if match["matched_by"] != "general":
                return match["rule"]["category_name"]

        # 2. Nếu có tên sản phẩm -> dùng CategoryMatcher để nhận diện ngành hàng
        if name:
            detected = matcher.detect_category_from_text(name)
            if detected and detected["matched_by"] != "general":
                return detected["rule"]["category_name"]

        return current_cat or 'Săn Deal Tổng Hợp'

    def save_deal(self, deal: Dict):
        """Lưu hoặc cập nhật một sản phẩm deal vào CSDL"""
        today = datetime.now().strftime("%Y-%m-%d")
        platform = (deal.get("platform") or "SHOPEE").upper()
        is_stale = 1 if deal.get("is_stale") else 0
        cat_name = self.classify_product_niche(deal.get("name", ""), deal.get("category_name", ""))
        deal["category_name"] = cat_name

        comm_rate = float(deal.get("commission_rate") or (12.0 if deal.get("is_mall") else (8.0 if deal.get("is_preferred") else 5.0)))
        is_extra = 1 if deal.get("is_extra") or comm_rate >= 8.0 else 0

        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO deals (
                    item_id, cat_id, category_name, name, price_original,
                    price_sale, discount_percent, rating_star, historical_sold,
                    deal_score, item_url, aff_url, image_url, created_date,
                    local_image, price_badge, platform, is_stale, commission_rate, is_extra, last_checked_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(item_id) DO UPDATE SET
                    category_name = excluded.category_name,
                    price_sale = excluded.price_sale,
                    discount_percent = excluded.discount_percent,
                    deal_score = excluded.deal_score,
                    created_date = excluded.created_date,
                    platform = COALESCE(excluded.platform, deals.platform),
                    local_image = COALESCE(excluded.local_image, deals.local_image),
                    price_badge = COALESCE(excluded.price_badge, deals.price_badge),
                    aff_url = COALESCE(excluded.aff_url, deals.aff_url),
                    is_stale = excluded.is_stale,
                    commission_rate = excluded.commission_rate,
                    is_extra = excluded.is_extra,
                    last_checked_at = CURRENT_TIMESTAMP
            """, (
                str(deal['item_id']), deal.get('cat_id'), cat_name,
                deal['name'], deal.get('price_original'), deal.get('price_sale'),
                deal.get('discount_percent'), deal.get('rating_star'), deal.get('historical_sold'),
                deal.get('deal_score'), deal.get('item_url'), deal.get('aff_url'),
                deal.get('image_url'), today, deal.get('local_image'), deal.get('price_badge'),
                platform, is_stale, comm_rate, is_extra
            ))
            conn.commit()

    def update_deal_aff_url(self, item_id: str, aff_url: str):
        """Cập nhật link affiliate chính thức cho deal đã cào"""
        if not item_id or not aff_url:
            return
        with self.get_connection() as conn:
            conn.execute("UPDATE deals SET aff_url = ? WHERE item_id = ?", (aff_url, str(item_id)))
            conn.commit()

    def get_today_top_deals(self, limit_per_category: int = 3) -> Dict[str, List[Dict]]:
        """Lấy top deals điểm cao nhất hôm nay theo từng ngành hàng"""
        today = datetime.now().strftime("%Y-%m-%d")
        deals_by_cat: Dict[str, List[Dict]] = {}
        with self.get_connection() as conn:
            rows = conn.execute("""
                SELECT * FROM deals
                WHERE created_date = ?
                ORDER BY deal_score DESC
            """, (today,)).fetchall()
            
            for row in rows:
                deal = dict(row)
                cat = deal['category_name'] or "Khác"
                if cat not in deals_by_cat:
                    deals_by_cat[cat] = []
                if len(deals_by_cat[cat]) < limit_per_category:
                    deals_by_cat[cat].append(deal)
        return deals_by_cat

    def get_loss_leader_deals(self, limit: int = 10) -> List[Dict]:
        """Lấy danh sách các Deal Mồi 1K - Freeship 0 VNĐ để kích hoạt cookie 7 ngày"""
        with self.get_connection() as conn:
            rows = conn.execute("""
                SELECT * FROM deals 
                WHERE price_badge = 'LOSS_LEADER_1K' OR price_sale <= 9000
                ORDER BY deal_score DESC, created_date DESC
                LIMIT ?
            """, (limit,)).fetchall()
            return [dict(r) for r in rows]

    def update_deal_media(self, item_id: str, local_image: Optional[str] = None, price_badge: Optional[str] = None):
        """Cập nhật đường dẫn ảnh đã đóng khung và huy hiệu giá cho deal"""
        with self.get_connection() as conn:
            if local_image and price_badge:
                conn.execute("UPDATE deals SET local_image = ?, price_badge = ? WHERE item_id = ?", (local_image, price_badge, str(item_id)))
            elif local_image:
                conn.execute("UPDATE deals SET local_image = ? WHERE item_id = ?", (local_image, str(item_id)))
            elif price_badge:
                conn.execute("UPDATE deals SET price_badge = ? WHERE item_id = ?", (price_badge, str(item_id)))
            conn.commit()

    def get_deal_by_id(self, item_id: str) -> Optional[Dict]:
        """Lấy thông tin chi tiết của deal theo item_id"""
        with self.get_connection() as conn:
            row = conn.execute("SELECT * FROM deals WHERE item_id = ?", (str(item_id),)).fetchone()
            return dict(row) if row else None

    def record_price_history(self, item_id: str, price: float, original_price: Optional[float] = None, discount_percent: int = 0, recorded_date: Optional[str] = None):
        """Ghi nhận giá của sản phẩm theo ngày để theo dõi biến động & bắt giảm giá ảo"""
        recorded_date = recorded_date or datetime.now().strftime("%Y-%m-%d")
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO price_history (item_id, price, original_price, discount_percent, recorded_date)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(item_id, recorded_date) DO UPDATE SET
                    price = excluded.price,
                    original_price = excluded.original_price,
                    discount_percent = excluded.discount_percent
            """, (str(item_id), price, original_price, discount_percent, recorded_date))
            conn.commit()

    def get_price_history(self, item_id: str, limit_days: int = 30) -> List[Dict]:
        """Lấy lịch sử giá của sản phẩm trong N ngày gần nhất"""
        with self.get_connection() as conn:
            rows = conn.execute("""
                SELECT * FROM price_history
                WHERE item_id = ? AND recorded_date >= date('now', ? || ' days')
                ORDER BY recorded_date ASC
            """, (str(item_id), f"-{limit_days}")).fetchall()
            return [dict(r) for r in rows]

    def get_deals(
        self,
        limit: int = 50,
        platform: Optional[str] = None,
        is_stale: Optional[int] = 0,
        category_name: Optional[str] = None,
        search: Optional[str] = None,
        deal_type: Optional[str] = "ALL",
        sort_by: str = "score"
    ) -> List[Dict]:
        """Truy vấn deal linh hoạt theo Sàn (Shopee/Lazada), độ tươi, ngành hàng, loại deal (1K / Hoa hồng cao), từ khóa tìm kiếm"""
        query = "SELECT * FROM deals WHERE 1=1"
        params: List[Any] = []

        if platform and platform.upper() != "ALL":
            query += " AND platform = ?"
            params.append(platform.upper())

        if is_stale is not None:
            query += " AND is_stale = ?"
            params.append(is_stale)

        if category_name and category_name.upper() != "ALL":
            query += " AND category_name = ?"
            params.append(category_name)

        if deal_type and deal_type.upper() == "LOSS_LEADER":
            query += " AND (price_badge = 'LOSS_LEADER_1K' OR price_sale <= 15000)"
        elif deal_type and deal_type.upper() == "EXTRA":
            query += " AND (is_extra = 1 OR commission_rate >= 8.0)"

        if search:
            query += " AND (name LIKE ? OR category_name LIKE ?)"
            term = f"%{search.strip()}%"
            params.extend([term, term])

        if sort_by == "discount":
            query += " ORDER BY discount_percent DESC, deal_score DESC"
        elif sort_by == "sold":
            query += " ORDER BY historical_sold DESC, deal_score DESC"
        elif sort_by == "price_asc":
            query += " ORDER BY price_sale ASC, deal_score DESC"
        elif sort_by == "price_desc":
            query += " ORDER BY price_sale DESC, deal_score DESC"
        elif sort_by == "newest":
            query += " ORDER BY created_date DESC, deal_score DESC"
        else:
            query += " ORDER BY deal_score DESC"

        query += " LIMIT ?"
        params.append(limit)

        with self.get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def mark_deal_stale(self, item_id: str, is_stale: int = 1):
        """Đánh dấu deal đã hết hàng / hết giảm giá hoặc còn tươi"""
        with self.get_connection() as conn:
            conn.execute("""
                UPDATE deals 
                SET is_stale = ?, last_checked_at = CURRENT_TIMESTAMP 
                WHERE item_id = ?
            """, (is_stale, str(item_id)))
            conn.commit()

    def clear_deals(self):
        """Xóa toàn bộ sản phẩm deal đã lưu trữ"""
        with self.get_connection() as conn:
            conn.execute("DELETE FROM post_history")
            conn.execute("DELETE FROM deals")
            conn.commit()
