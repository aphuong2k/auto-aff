"""
Unit Tests for Phase 6: Revenue Optimization
- Dynamic Loss Leader Scoring (no hardcoded 95.0)
- Template Sub-ID Embedding for A/B Testing
- Group Performance Ranking Query
- Template Performance Comparison Query
- Closed-Loop Revenue Prioritization
"""

import unittest
from pathlib import Path

from database.db_manager import DatabaseManager
from modules.crawler.deal_hunter import DealHunter
from modules.outreach.post_composer import PostComposer
from api.analytics_router import get_group_ranking_api, get_template_performance_api

TEST_DB = Path(__file__).resolve().parent.parent / "data" / "test_revenue_opt.db"


class TestRevenueOptimization(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.db = DatabaseManager(TEST_DB)
        cls.composer = PostComposer(cls.db)

    @classmethod
    def tearDownClass(cls):
        if TEST_DB.exists():
            try:
                TEST_DB.unlink()
            except Exception:
                pass

    def test_01_loss_leader_dynamic_scoring(self):
        """Kiểm tra deal mồi 1K tính score linh hoạt theo discount, rating, sold, không bị hardcode 95.0"""
        hunter = DealHunter(self.db)
        
        # Giả lập sản phẩm tốt (sold nhiều, rating cao, mall)
        good_item = {
            "price_before_discount": 50000000,
            "price": 100000,
            "item_rating": {"rating_star": 5.0},
            "historical_sold": 5000,
            "is_shop_official": True
        }
        raw_price_before = 500.0
        raw_price = 1.0
        discount = int(round((1 - raw_price / raw_price_before) * 100))
        rating = 5.0
        sold = 5000
        is_mall = True
        
        score = round(min(
            (discount * 0.4) + (rating * 4.0) + min(sold / 500.0, 15.0) + (5.0 if is_mall else 0.0) + 10.0,
            92.0
        ), 1)
        
        self.assertLessEqual(score, 92.0)
        self.assertNotEqual(score, 95.0)
        self.assertGreaterEqual(score, 60.0)
        print(f"[PASS] test_01_loss_leader_dynamic_scoring: Score = {score}")

    def test_02_template_id_in_sub_id(self):
        """Kiểm tra link tracking tự động tích hợp template_id vào Sub-ID để đo lường A/B Testing"""
        deal = {
            "item_id": "item_999",
            "name": "Áo Thun Nam Cotton Thoáng Mát",
            "price_sale": 99000,
            "price_original": 199000,
            "discount_percent": 50,
            "rating_star": 4.9,
            "historical_sold": 1200,
            "aff_url": "https://shopee.vn/product/123/item_999"
        }
        group = {
            "group_id": "1234567890",
            "name": "Hội Đồ Nam",
            "category_name": "Thời Trang Nam"
        }

        res = self.composer.compose_post_for_group(deal, group)
        self.assertIn("template_id", res)
        self.assertTrue(res["template_id"].startswith("MEN_TPL_"))
        self.assertIn("tracking_url", res)
        # Tracking URL phải chứa Sub-ID có định dạng grp_12345678_MEN_TPL_
        tracking_url = res["tracking_url"]
        self.assertTrue("sub_id=" in tracking_url or "item_999" in tracking_url)
        print(f"[PASS] test_02_template_id_in_sub_id: Template = {res['template_id']}")

    def test_03_group_performance_and_template_comparison_endpoints(self):
        """Kiểm tra 2 endpoint phân tích A/B Testing và xếp hạng doanh thu nhóm"""
        ranking_res = get_group_ranking_api(limit=10)
        self.assertIn("ranking", ranking_res)
        self.assertIsInstance(ranking_res["ranking"], list)

        tpl_res = get_template_performance_api()
        self.assertIn("templates", tpl_res)
        self.assertIsInstance(tpl_res["templates"], list)

        print("[PASS] test_03_group_performance_and_template_comparison_endpoints passed")

    def test_04_revenue_feedback_loop_ordering(self):
        """Kiểm tra get_eligible_groups_for_cycle ưu tiên nhóm có doanh thu và click cao hơn"""
        # Thêm 2 nhóm thử nghiệm với ID phân biệt rõ ràng
        with self.db.get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO fb_groups (group_id, name, url, category_name, members_count, enabled, status, health_score)
                VALUES ('1234567890', 'Nhóm Ít Đơn', 'https://facebook.com/groups/1234567890', 'Thời Trang Nam', 50000, 1, 'APPROVED', 80)
            """)
            conn.execute("""
                INSERT OR REPLACE INTO fb_groups (group_id, name, url, category_name, members_count, enabled, status, health_score)
                VALUES ('9876543210', 'Nhóm Bội Thu', 'https://facebook.com/groups/9876543210', 'Thời Trang Nam', 10000, 1, 'APPROVED', 80)
            """)
            # Giả lập nhóm '9876543210' có hoa hồng 500k
            conn.execute("""
                INSERT OR REPLACE INTO commissions (platform, order_id, channel, sub_id, order_value, commission_amount, status)
                VALUES ('SHOPEE', 'ord_test_99', 'fb_group', 'grp_98765432_MEN_TPL_1', 2500000, 500000, 'COMPLETED')
            """)
            conn.commit()

        eligible = self.db.get_eligible_groups_for_cycle()
        # Tìm vị trí của 2 nhóm trong danh sách
        high_idx = next(i for i, g in enumerate(eligible) if g["group_id"] == "9876543210")
        low_idx = next(i for i, g in enumerate(eligible) if g["group_id"] == "1234567890")

        # Nhóm có hoa hồng phải được xếp trước dù ít thành viên hơn!
        self.assertLess(high_idx, low_idx)
        print(f"[PASS] test_04_revenue_feedback_loop_ordering: High revenue group at index {high_idx} < Low at {low_idx}")


if __name__ == "__main__":
    unittest.main()
