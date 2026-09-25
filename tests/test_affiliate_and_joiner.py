import os
import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from database.db_manager import DatabaseManager
from modules.affiliate.link_converter import AffiliateLinkConverter
from modules.outreach.fb_auto_joiner import FacebookAutoJoiner

TEST_DB_PATH = BASE_DIR / "data" / "test_isolated_joiner.db"

class TestAffiliateAndJoiner(unittest.TestCase):

    @classmethod
    def tearDownClass(cls):
        if TEST_DB_PATH.exists():
            try:
                TEST_DB_PATH.unlink()
            except Exception:
                pass

    def setUp(self):
        self.db = DatabaseManager(TEST_DB_PATH)
        self.converter = AffiliateLinkConverter()

    def test_01_update_deal_aff_url(self):
        item_id = "test_aff_deal_123"
        deal = {
            "item_id": item_id,
            "cat_id": 11035567,
            "category_name": "Thời Trang Nam",
            "name": "Áo Thun Nam Cotton Co Giãn",
            "price_original": 150000,
            "price_sale": 79000,
            "discount_percent": 47,
            "rating_star": 4.8,
            "historical_sold": 1200,
            "item_url": "https://shopee.vn/product/123/456",
            "aff_url": None,
            "image_url": ""
        }
        self.db.save_deal(deal)

        saved = self.db.get_deal_by_id(item_id)
        self.assertIsNotNone(saved)

        # Update aff_url
        new_aff_url = "https://s.shopee.vn/test_shortlink"
        self.db.update_deal_aff_url(item_id, new_aff_url)

        updated = self.db.get_deal_by_id(item_id)
        self.assertEqual(updated["aff_url"], new_aff_url)
        print("[PASS] test_01_update_deal_aff_url passed!")

    def test_02_fb_auto_joiner_ai_answers(self):
        joiner = FacebookAutoJoiner(self.db)
        questions = [
            "Lý do bạn muốn tham gia nhóm là gì?",
            "Bạn có đồng ý tuân thủ nội quy nhóm không?",
            "Bạn đang sinh sống ở đâu?"
        ]
        answers = joiner.answer_membership_questions_with_ai(questions)
        self.assertEqual(len(answers), 3)
        self.assertIn("học hỏi", answers[0])
        self.assertIn("nội quy", answers[1])
        self.assertIn("Hà Nội", answers[2])
        print("[PASS] test_02_fb_auto_joiner_ai_answers passed!")

    def test_03_affiliate_link_converter_logic(self):
        # Khi chưa có cấu hình: Hệ thống không fake link mà giữ nguyên URL gốc và log lỗi thật
        raw_url = "https://shopee.vn/product/123/456"
        converter_sim = AffiliateLinkConverter(app_id="", secret="", aff_cookie="")
        link = converter_sim.convert_to_affiliate(raw_url, channel="telegram", sub_id="tele_test")
        self.assertEqual(link, raw_url)
        print("[PASS] test_03_affiliate_link_converter_logic passed!")

if __name__ == "__main__":
    unittest.main()
