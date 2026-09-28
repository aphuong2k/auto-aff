import random
import logging
from typing import Dict, List, Optional, Tuple
from database.db_manager import DatabaseManager
from config.category_mapping import CategoryMatcher

router_logger = logging.getLogger("CategoryRouter")
router_logger.setLevel(logging.INFO)


class CategoryRouter:
    """
    Module định tuyến thông minh giữa Kho Deal (Deal Pool) và Nhóm Facebook (Group Delivery).
    - Hỗ trợ mô hình 1 Deal -> Nhiều Nhóm (One-to-Many Routing).
    - Chống đăng lặp bài tuyệt đối: Mỗi deal chỉ đăng tối đa 1 lần trên 1 group cụ thể (deal_post_history).
    - Cổng kiểm định nghiêm ngặt: Nếu nhóm chưa có deal đạt chuẩn thì BỎ QUA (SKIP).
      Tuyệt đối KHÔNG gượng ép đăng deal cũ, deal ôi thiu hoặc sai danh mục!
    
    Sử dụng CategoryMatcher config-driven thay vì if-elif hardcode.
    """

    def __init__(self, db: Optional[DatabaseManager] = None):
        self.db = db or DatabaseManager()
        self.matcher = CategoryMatcher()

    def route_deal_for_group(self, group: Dict) -> Tuple[Optional[Dict], str, int]:
        """
        Tìm và chỉ định Deal tốt nhất phù hợp cho nhóm được chỉ định.
        Trả về: (selected_deal, status_code, evaluated_count)
        - selected_deal: Deal đạt chuẩn hoặc None nếu không có
        - status_code: 'QUALIFIED', 'SKIPPED_NO_QUALIFIED_DEAL', 'SKIPPED_ALL_POSTED'
        - evaluated_count: Số lượng deal đã được thẩm định
        """
        group_id = str(group.get("group_id", ""))
        group_name = group.get("name") or ""
        group_cat = group.get("category_name") or "Cộng Đồng Chung"

        # 1. Khớp category bằng CategoryMatcher config-driven
        match_result = self.matcher.match_group(group_cat=group_cat, group_name=group_name)
        category_condition = self.matcher.build_deal_query_conditions(match_result)

        # 2. Truy vấn deal phù hợp
        with self.db.get_connection() as conn:
            query = f"""
                SELECT * FROM deals 
                WHERE ({category_condition})
                  AND is_stale = 0
                ORDER BY deal_score DESC, rating_star DESC, historical_sold DESC
                LIMIT 30
            """
            candidates = conn.execute(query).fetchall()

        if not candidates:
            matched_cat = match_result["rule"]["category_name"]
            router_logger.warning(f"⚠️ [ROUTER]: Không có deal nào trong kho thuộc ngành [{matched_cat}] cho nhóm [{group_name}].")
            return None, "SKIPPED_NO_QUALIFIED_DEAL", 0

        evaluated_count = len(candidates)

        # 3. Lọc bỏ các Deal đã từng được đăng lên Group này (Chống đăng lặp)
        unposted_deals = []
        for row in candidates:
            deal_dict = dict(row)
            d_id = str(deal_dict.get("item_id", ""))
            if not self.db.is_deal_posted_to_group(d_id, group_id):
                unposted_deals.append(deal_dict)

        if not unposted_deals:
            router_logger.warning(
                f"⚠️ [ROUTER]: Tất cả {evaluated_count} deal tiềm năng ngành [{group_cat}] "
                f"đã từng được đăng lên nhóm [{group_name}]. Hệ thống bỏ qua để chống spam lặp lại!"
            )
            return None, "SKIPPED_ALL_POSTED", evaluated_count

        # Chọn ngẫu nhiên từ top deal chất lượng cao nhất chưa từng đăng lên nhóm này (tránh lặp lại 1 deal duy nhất)
        candidates_pool = unposted_deals[:min(10, len(unposted_deals))]
        best_deal = random.choice(candidates_pool)
        router_logger.info(
            f"🎯 [ROUTER KHỚP DEAL RANDOM]: Nhóm [{group_name}] ({group_cat}) "
            f"-> Chọn deal ngẫu nhiên: [{best_deal.get('name')[:35]}...] (Score: {best_deal.get('deal_score')}, Giá: {int(best_deal.get('price_sale', 0)):,}đ)"
        )

        return best_deal, "QUALIFIED", evaluated_count
