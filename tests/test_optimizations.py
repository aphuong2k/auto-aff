import os
import sys
import unittest
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from database.db_manager import DatabaseManager
from modules.affiliate.image_stamper import ImageBannerStamper
from modules.crawler.price_history_tracker import PriceHistoryTracker
from modules.affiliate.content_writer import DealContentWriter
from modules.affiliate.link_converter import AffiliateLinkConverter
from modules.outreach.fb_group_seeder import FacebookGroupSeeder
import api_server

TEST_DB_PATH = BASE_DIR / "data" / "test_isolated_optimizations.db"

class TestAffiliateOptimizations(unittest.TestCase):

    @classmethod
    def tearDownClass(cls):
        if TEST_DB_PATH.exists():
            try:
                TEST_DB_PATH.unlink()
            except Exception:
                pass

    def tearDown(self):
        if hasattr(self, "_orig_api_server_db") and self._orig_api_server_db:
            api_server.db = self._orig_api_server_db

    def setUp(self):
        self.db = DatabaseManager(TEST_DB_PATH)
        self._orig_api_server_db = getattr(api_server, "db", None)
        api_server.db = self.db
        
        self.sample_deal = {
            "item_id": "test_item_888",
            "cat_id": 11035954,
            "category_name": "Thiết Bị Điện Tử",
            "name": "Tai Nghe Bluetooth Không Dây True Wireless Chống Ồn Cao Cấp",
            "price_original": 550000,
            "price_sale": 249000,
            "discount_percent": 55,
            "rating_star": 4.9,
            "historical_sold": 8900,
            "deal_score": 85.5,
            "item_url": "https://shopee.vn/product/12345/test_item_888",
            "aff_url": "https://shopee.vn/product/12345/test_item_888?utm_source=aff",
            "image_url": ""
        }
        self.db.save_deal(self.sample_deal)

    def test_01_image_banner_stamper(self):
        """Kiểm tra tạo ảnh đóng khung Flash Sale chuẩn 800x800 bằng Pillow"""
        stamped_path = ImageBannerStamper.stamp_deal_image(self.sample_deal)
        self.assertTrue(stamped_path.exists())
        self.assertGreater(stamped_path.stat().st_size, 10000) # File ảnh có kích thước > 10KB
        print(f"\n✅ test_01_image_banner_stamper passed: {stamped_path}")

    def test_02_price_history_tracker(self):
        """Kiểm tra ghi nhận lịch sử giá và phát hiện đáy giá 30 ngày"""
        tracker = PriceHistoryTracker(self.db)
        
        # Ghi nhận các mốc giá cũ cao hơn
        self.db.record_price_history("test_item_888", 350000, 550000, 36, "2026-09-01")
        self.db.record_price_history("test_item_888", 320000, 550000, 41, "2026-09-10")
        self.db.record_price_history("test_item_888", 249000, 550000, 55, "2026-09-21") # Hôm nay giá 249k -> Đáy lịch sử

        verdict = tracker.analyze_price_verdict(self.sample_deal)
        self.assertEqual(verdict["badge"], "HISTORICAL_LOW")
        self.assertTrue(verdict["is_genuine"])
        print(f"✅ test_02_price_history_tracker passed: {verdict}")

    def test_03_content_writer_with_badges(self):
        """Kiểm tra nội dung Telegram & Facebook tự động gắn huy hiệu đáy giá"""
        deal_with_badge = dict(self.sample_deal)
        deal_with_badge["price_badge"] = "HISTORICAL_LOW"
        
        tele_post = DealContentWriter.generate_telegram_post(deal_with_badge)
        self.assertIn("ĐÁY LỊCH SỬ 30 NGÀY", tele_post)
        
        fb_post = DealContentWriter.generate_facebook_post(deal_with_badge)
        self.assertIn("ĐÁY LỊCH SỬ", fb_post)
        print("✅ test_03_content_writer_with_badges passed")

    def test_04_click_analytics_and_redirect(self):
        """Kiểm tra trang trung gian Anti-Ban /r/{item_id} và ghi nhận Sub-ID Analytics"""
        class MockClient:
            host = "127.0.0.1"
        class MockRequest:
            client = MockClient()
            headers = {"referer": "https://facebook.com", "user-agent": "Mozilla/5.0 TestBrowser"}

        response = api_server.anti_ban_redirect("test_item_888", MockRequest(), channel="fb_group", sub_id="grp_test_99")
        self.assertEqual(response.status_code, 200)
        body_text = response.body.decode("utf-8")
        self.assertIn("Flash Sale:", body_text)
        self.assertIn("Đang chuyển hướng", body_text)

        # Kiểm tra Analytics
        analytics = self.db.get_click_analytics()
        self.assertGreaterEqual(analytics["total_clicks"], 1)
        found_channel = any(c["channel"] == "fb_group" for c in analytics["channels"])
        self.assertTrue(found_channel)
        print(f"✅ test_04_click_analytics_and_redirect passed: Total clicks = {analytics['total_clicks']}")

    def test_05_fb_comment_seeder(self):
        """Kiểm tra module gieo bình luận dạo: Tuyệt đối không fake dữ liệu khi chưa đăng nhập và bóc tách chuẩn khi có bài thật"""
        import unittest.mock
        # Tạo nhóm test
        with self.db.get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO fb_groups (group_id, name, url, category_name, members_count, status)
                VALUES ('grp_test_tech', 'Hội Đam Mê Tai Nghe & Đồ Công Nghệ', 'https://facebook.com/groups/tech', 'Thiết Bị Điện Tử', 25000, 'APPROVED')
            """)
            conn.commit()

        seeder = FacebookGroupSeeder(self.db)

        # 1. Khi chưa cấu hình Facebook: Không fake dữ liệu, trả về []
        old_cookie = os.environ.get("FB_COOKIE", "")
        old_profile = os.environ.get("FB_CHROME_PROFILE", "")
        os.environ.pop("FB_COOKIE", None)
        os.environ.pop("FB_CHROME_PROFILE", None)

        no_login_results = seeder.run_seeding_scan(max_groups=1)
        self.assertEqual(len(no_login_results), 0)

        # 2. Khi có tài khoản và phát hiện bài viết thật trên nhóm có nhu cầu xin link
        os.environ["FB_COOKIE"] = "c_user=1000888; xs=mock_xs_val"
        seeder.scan_group_for_real_posts = lambda *args, **kwargs: [{
            "text": "Mọi người cho mình xin link mua tai nghe bluetooth chất lượng tốt tầm giá này với ạ!",
            "url": "https://facebook.com/groups/tech/posts/999888777"
        }]

        class MockPlaywright:
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc_val, exc_tb):
                pass
            class chromium:
                @staticmethod
                def launch(*args, **kwargs):
                    class MockBrowser:
                        def new_context(self, *a, **k):
                            class MockContext:
                                def add_cookies(self, c): pass
                                def new_page(self): return None
                                def close(self): pass
                            return MockContext()
                        def close(self): pass
                    return MockBrowser()

        with unittest.mock.patch("playwright.sync_api.sync_playwright", return_value=MockPlaywright()):
            results = seeder.run_seeding_scan(max_groups=1)
            self.assertGreaterEqual(len(results), 1)
            self.assertEqual(results[0]["target_url"], "https://facebook.com/groups/tech/posts/999888777")
            
            history = self.db.get_comment_seeding_history(limit=5)
            self.assertGreaterEqual(len(history), 1)
            print(f"✅ test_05_fb_comment_seeder passed: Generated comment -> {results[0]['comment'][:60]}...")

        if old_cookie:
            os.environ["FB_COOKIE"] = old_cookie
        else:
            os.environ.pop("FB_COOKIE", None)
        if old_profile:
            os.environ["FB_CHROME_PROFILE"] = old_profile
        else:
            os.environ.pop("FB_CHROME_PROFILE", None)

    def test_06_image_api_endpoint(self):
        """Kiểm tra endpoint phục vụ ảnh /api/deals/image/{item_id}"""
        response = api_server.get_deal_image("test_item_888")
        self.assertTrue(os.path.exists(response.path))
        self.assertEqual(response.media_type, "image/jpeg")
        print(f"✅ test_06_image_api_endpoint passed (Path: {response.path})")

    def test_07_verify_deal_freshness(self):
        """Kiểm tra xác thực độ tươi và tồn kho của deal (Live Freshness Check)"""
        from modules.crawler.deal_hunter import DealHunter
        
        # 1. Deal mồi loss_leader luôn tươi
        loss_deal = {"item_id": "loss_1k_cable", "price_sale": 1000, "discount_percent": 95}
        self.assertTrue(DealHunter.verify_deal_freshness(loss_deal))

        # 2. Deal bình thường có giảm giá và giá hợp lệ
        valid_deal = {"item_id": "item_valid_123", "price_sale": 150000, "discount_percent": 40}
        self.assertTrue(DealHunter.verify_deal_freshness(valid_deal))

        # 3. Deal không có giá sale hoặc giá = 0 -> không tươi
        invalid_deal = {"item_id": "item_invalid_000", "price_sale": 0, "discount_percent": 0}
        self.assertFalse(DealHunter.verify_deal_freshness(invalid_deal))
        print("✅ test_07_verify_deal_freshness passed")

    def test_08_loss_leader_1k_strategy(self):
        """Kiểm tra chiến thuật Deal Mồi 1K kích hoạt Cookie 7 ngày"""
        from modules.crawler.deal_hunter import DealHunter
        hunter = DealHunter(self.db)
        deals = hunter.fetch_loss_leader_deals(limit=2)
        self.assertIsInstance(deals, list)

        # Kiểm tra nội dung bài đăng deal mồi 1K
        sample_loss_deal = {
            "name": "Cáp Sạc Nhanh Dây Dù 1K",
            "price_sale": 1000.0,
            "price_original": 35000.0,
            "price_badge": "LOSS_LEADER_1K",
            "rating_star": 4.9,
            "historical_sold": 45000,
            "item_url": "https://shopee.vn/product/1/2",
            "aff_url": "https://s.shopee.vn/test123"
        }
        post_copy = DealContentWriter.generate_loss_leader_post(sample_loss_deal)
        self.assertIn("DEAL 1K", post_copy)
        self.assertIn("Freeship", post_copy)
        print("✅ test_08_loss_leader_1k_strategy passed")

    def test_09_strict_category_matching_seeding(self):
        """Kiểm tra phân phối rải deal chuẩn xác theo từng ngành hàng của group"""
        seeder = FacebookGroupSeeder(self.db)
        
        # Chuẩn bị deal 2 ngành khác nhau
        tech_deal = dict(self.sample_deal)
        tech_deal["item_id"] = "tech_item_999"
        tech_deal["category_name"] = "Thiết Bị Điện Tử"
        tech_deal["name"] = "Củ sạc nhanh 65W GaN Type-C"
        self.db.save_deal(tech_deal)

        beauty_deal = {
            "item_id": "beauty_item_111",
            "cat_id": 11036279,
            "category_name": "Sắc Đẹp",
            "name": "Son dưỡng môi cấp ẩm chuyên sâu",
            "price_original": 120000,
            "price_sale": 59000,
            "discount_percent": 51,
            "rating_star": 4.9,
            "historical_sold": 15000,
            "deal_score": 90.0,
            "item_url": "https://shopee.vn/beauty-item",
            "aff_url": "https://shopee.vn/beauty-item",
            "image_url": ""
        }
        self.db.save_deal(beauty_deal)

        # 1. Group Công Nghệ PHẢI match với deal Công Nghệ
        matched_tech = seeder.find_best_matching_deal("Cộng Đồng Đam Mê Công Nghệ & Phụ Kiện Điện Tử")
        self.assertIsNotNone(matched_tech)
        self.assertEqual(matched_tech["category_name"], "Thiết Bị Điện Tử")

        # 2. Group Làm Đẹp PHẢI match với deal Mỹ Phẩm / Sắc Đẹp
        matched_beauty = seeder.find_best_matching_deal("Hội Nghiện Skincare & Mỹ Phẩm Hàn Quốc")
        self.assertIsNotNone(matched_beauty)
        self.assertEqual(matched_beauty["category_name"], "Sắc Đẹp")
        print("✅ test_09_strict_category_matching_seeding passed")

    def test_10_daily_cover_banner(self):
        """Kiểm tra tạo ảnh Banner Tiêu Đề Ngày (Cover Banner 1080x1080)"""
        banner_path = ImageBannerStamper.create_daily_cover_banner(date_str="21/09/2026")
        self.assertTrue(os.path.exists(banner_path))
        from PIL import Image
        with Image.open(banner_path) as im:
            self.assertEqual(im.size, (1080, 1080))
        print(f"✅ test_10_daily_cover_banner passed: {banner_path}")

    def test_11_redirect_mode_direct_and_anti_die(self):
        """Kiểm tra cơ chế Anti-Die: direct link Shopee Aff sống vĩnh viễn, không phụ thuộc localhost"""
        from modules.affiliate.link_converter import AffiliateLinkConverter
        converter = AffiliateLinkConverter()
        
        # 1. Chế độ DIRECT (mặc định): Trả về link shopee trực tiếp không chứa localhost
        aff_url = "https://shopee.vn/product/123/456?utm_source=fb"
        bridge = converter.get_bridge_url(
            item_id="item_456",
            channel="fb_group",
            direct_aff_url=aff_url
        )
        self.assertEqual(bridge, aff_url)
        self.assertNotIn("localhost", bridge)
        print("✅ test_11_redirect_mode_direct_and_anti_die passed")

    def test_12_posted_logs(self):
        """Kiểm tra bảng posted_logs lưu trữ đầy đủ link bài viết/comment và ảnh để kiểm tra"""
        log_id = self.db.log_posted_item(
            post_type="POST",
            group_name="Nhóm Nghiện Shopee",
            group_url="https://facebook.com/groups/nghienshopee",
            target_url="https://facebook.com/groups/nghienshopee/posts/999888777",
            item_id="item_test_log",
            item_name="Nồi chiên không dầu Philips 5L",
            content_snippet="Deal nồi chiên Philips giảm 45% cực ngon mn ơi...",
            image_path="/path/to/banner.jpg",
            status="SUCCESS"
        )
        self.assertGreater(log_id, 0)
        
        logs = self.db.get_posted_logs(limit=10)
        self.assertGreaterEqual(len(logs), 1)
        latest = logs[0]
        self.assertEqual(latest["type"], "POST")
        self.assertEqual(latest["target_url"], "https://facebook.com/groups/nghienshopee/posts/999888777")
        self.assertEqual(latest["item_name"], "Nồi chiên không dầu Philips 5L")
        print("✅ test_12_posted_logs passed")

    def test_13_popular_product_prioritization(self):
        """Kiểm tra thuật toán ưu tiên sản phẩm phổ biến: Lượt bán cao + Shop Mall điểm vượt trội"""
        from modules.crawler.deal_hunter import DealHunter
        hunter = DealHunter(self.db)

        # Sản phẩm hot bán 20k đơn, Shop Mall
        popular_deal = {
            "name": "Tai nghe AirDots Pro Max Mall",
            "rating_star": 4.9,
            "historical_sold": 20000,
            "discount_percent": 30,
            "is_mall": True
        }
        score_popular = hunter.calculate_score(popular_deal)

        # Sản phẩm thường chỉ bán 250 đơn, shop thường
        normal_deal = {
            "name": "Tai nghe thường",
            "rating_star": 4.6,
            "historical_sold": 250,
            "discount_percent": 30,
            "is_mall": False
        }
        score_normal = hunter.calculate_score(normal_deal)

        self.assertGreater(score_popular, score_normal)
        self.assertGreaterEqual(score_popular - score_normal, 25.0)  # Phổ biến + Mall phải hơn ít nhất 25 điểm
        print(f"✅ test_13_popular_product_prioritization passed (Popular Mall: {score_popular} vs Normal: {score_normal})")

if __name__ == "__main__":
    unittest.main()

