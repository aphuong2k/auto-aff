import sys
import unittest
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

from database.db_manager import DatabaseManager
from modules.affiliate.provider_base import BaseAffiliateProvider
from modules.affiliate.shopee_provider import ShopeeAffiliateProvider
from modules.affiliate.lazada_provider import LazadaAffiliateProvider
from modules.affiliate.link_converter import AffiliateLinkConverter
from modules.crawler.lazada_deal_hunter import LazadaDealHunter
from modules.crawler.deal_freshness_checker import DealFreshnessChecker
from modules.affiliate.commission_tracker import CommissionTracker
from modules.portal.deal_hub_renderer import DealHubRenderer

class TestMultiPlatformAffiliate(unittest.TestCase):

    def setUp(self):
        self.db = DatabaseManager()

    def test_providers(self):
        shopee = ShopeeAffiliateProvider()
        lazada = LazadaAffiliateProvider()

        self.assertTrue(shopee.is_match_url("https://shopee.vn/product/123/456"))
        self.assertFalse(shopee.is_match_url("https://www.lazada.vn/products/abc-i123.html"))

        self.assertTrue(lazada.is_match_url("https://www.lazada.vn/products/ao-thun-i123.html"))
        self.assertFalse(lazada.is_match_url("https://shopee.vn/product/123/456"))

        # Test link converter routing
        converter = AffiliateLinkConverter()
        laz_link = converter.convert_to_affiliate("https://www.lazada.vn/products/ao-thun-i12345.html", channel="telegram", sub_id="tele_test")
        self.assertIn("ex_channel=affiliate", laz_link)
        self.assertIn("aff_sub=tele_test", laz_link)

    def test_database_multi_platform(self):
        # Save Shopee deal
        deal_shopee = {
            "item_id": "test_shopee_001",
            "name": "Nồi cơm điện tử Shopee",
            "price_sale": 500000,
            "price_original": 800000,
            "discount_percent": 38,
            "rating_star": 4.9,
            "historical_sold": 1500,
            "platform": "SHOPEE",
            "category_name": "Gia Dụng"
        }
        self.db.save_deal(deal_shopee)

        # Save Lazada deal
        deal_lazada = {
            "item_id": "test_laz_001",
            "name": "Nồi chiên không dầu Lazada LazMall",
            "price_sale": 990000,
            "price_original": 1600000,
            "discount_percent": 38,
            "rating_star": 4.8,
            "historical_sold": 2200,
            "platform": "LAZADA",
            "category_name": "Gia Dụng"
        }
        self.db.save_deal(deal_lazada)

        # Query by platform
        shopee_deals = self.db.get_deals(platform="SHOPEE")
        self.assertTrue(any(d["item_id"] == "test_shopee_001" for d in shopee_deals))

        laz_deals = self.db.get_deals(platform="LAZADA")
        self.assertTrue(any(d["item_id"] == "test_laz_001" for d in laz_deals))

    def test_commission_tracker(self):
        tracker = CommissionTracker(self.db)
        tracker.seed_initial_demo_commissions()
        stats = self.db.get_commission_stats()
        self.assertGreater(stats["total_orders"], 0)
        self.assertGreater(stats["total_commission"], 0)
        platforms = [p["platform"] for p in stats["by_platform"]]
        self.assertIn("SHOPEE", platforms)
        self.assertIn("LAZADA", platforms)

    def test_subscribers(self):
        email = "test_user_vip@example.com"
        res = self.db.save_subscriber(email=email, platform_pref="ALL", min_discount=40)
        self.assertTrue(res)
        subs = self.db.get_active_subscribers()
        self.assertTrue(any(s["email"] == email for s in subs))

    def test_deal_hub_renderer(self):
        deals = self.db.get_deals(limit=10)
        cats = self.db.get_active_categories()
        html_out = DealHubRenderer.render_hub_page(deals=deals, categories=cats)
        self.assertIn("DEALHUNT", html_out)
        self.assertIn("schema.org", html_out)
        self.assertIn("LazMall", html_out)

if __name__ == "__main__":
    unittest.main()
