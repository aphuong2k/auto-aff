"""
Unit & Integration Tests for "🔎 Quét & Săn Deal" Feature
==========================================================
Kiểm tra toàn bộ các yêu cầu nghiệp vụ:
1. Quét từ Group Telegram & Nhập trực tiếp tên sản phẩm bất kỳ
2. Bộ lọc nguồn: Tmall / Lazada Mall / Phân loại khác của Lazada / ALL
3. Nhận diện & gom tin đăng cùng sản phẩm, tính Giá trung bình & Giá tham chiếu
4. Lưu dữ liệu & Lịch sử giá; Quét lại cập nhật giá mới nhưng giữ nguyên lịch sử cũ
5. Tự tìm sản phẩm tương ứng, ưu tiên sản phẩm có giá thấp hơn giá tham chiếu
6. Danh sách deal động: ảnh, tên, giá tham chiếu, giá bán, chênh lệch, nguồn, link
7. Tự động gửi deal đạt điều kiện vào Telegram
8. Không giới hạn ngành hàng, không hardcode dữ liệu mẫu
"""

import os
import unittest
from unittest.mock import patch, MagicMock
from database.db_manager import DatabaseManager
from modules.crawler.product_cluster_engine import ProductClusterEngine
from modules.crawler.multi_source_hunter import MultiSourceHunter
from modules.crawler.telegram_scanner import TelegramScanner
from modules.publisher.telegram_bot import TelegramPublisher


class TestDealHunterFeature(unittest.TestCase):

    def setUp(self):
        self.db = DatabaseManager()

    def test_01_price_extraction_and_cleaning(self):
        """Kiểm tra bóc tách giá tiền tiếng Việt đa dạng và làm sạch tiêu đề"""
        # Test bóc tách giá
        self.assertEqual(ProductClusterEngine.extract_price_vnd("Pass phím cơ 450k"), 450000.0)
        self.assertEqual(ProductClusterEngine.extract_price_vnd("Bán tai nghe 1tr2 fullbox"), 1200000.0)
        self.assertEqual(ProductClusterEngine.extract_price_vnd("Cần pass 1.5tr"), 1500000.0)
        self.assertEqual(ProductClusterEngine.extract_price_vnd("Giá 350.000đ freeship"), 350000.0)
        self.assertEqual(ProductClusterEngine.extract_price_vnd("Thanh lý 2tr"), 2000000.0)
        self.assertEqual(ProductClusterEngine.extract_price_vnd("Áo thun nam 99k"), 99000.0)

        # Test làm sạch tiêu đề
        cleaned = ProductClusterEngine.clean_product_title("Pass lại bàn phím cơ Aula F75 mới mua 1 tuần giá 450k chính hãng freeship")
        self.assertIn("Aula F75", cleaned)
        self.assertNotIn("450k", cleaned)
        self.assertNotIn("chính hãng", cleaned.lower())

    def test_02_product_clustering_and_reference_price(self):
        """Kiểm tra gom tin đăng cùng sản phẩm, tính Giá trung bình & Giá tham chiếu"""
        raw_posts = [
            {"text": "Bán bàn phím cơ Aula F75 giá 400k", "source": "Group 1"},
            {"text": "Pass lại Aula F75 không dây 3 mode giá 500k", "source": "Group 2"},
            {"text": "Cần bán Aula F75 rgb còn mới giá 450.000đ", "source": "Group 3"},
            {"text": "Thanh lý giày sneaker Nike Air Force 1 giá 1tr2", "source": "Group 1"},
            {"text": "Bán Nike Air Force 1 size 42 giá 1.4tr", "source": "Group 2"},
        ]

        clusters = ProductClusterEngine.cluster_messages(raw_posts)
        self.assertGreaterEqual(len(clusters), 2)

        # Tìm cụm Aula F75
        aula_cluster = next((c for c in clusters if "f75" in c["cluster_key"]), None)
        self.assertIsNotNone(aula_cluster)
        self.assertEqual(aula_cluster["sample_count"], 3)
        # 400k, 500k, 450k -> Avg = 450k, Median (Reference Price) = 450k
        self.assertEqual(aula_cluster["avg_price"], 450000.0)
        self.assertEqual(aula_cluster["reference_price"], 450000.0)
        self.assertEqual(aula_cluster["min_price"], 400000.0)
        self.assertEqual(aula_cluster["max_price"], 500000.0)

        # Tìm cụm Nike Air Force 1
        nike_cluster = next((c for c in clusters if "nike" in c["cluster_key"] or "air" in c["cluster_key"]), None)
        self.assertIsNotNone(nike_cluster)
        self.assertEqual(nike_cluster["sample_count"], 2)
        # 1.2tr và 1.4tr -> Avg = 1.3tr, Reference = 1.3tr
        self.assertEqual(nike_cluster["avg_price"], 1300000.0)
        self.assertEqual(nike_cluster["reference_price"], 1300000.0)

    def test_03_telegram_scanner_target_normalization(self):
        """Kiểm tra chuẩn hóa định dạng mục tiêu Telegram"""
        scanner = TelegramScanner()
        self.assertEqual(scanner.normalize_identifier("@nghiensandeal"), "nghiensandeal")
        self.assertEqual(scanner.normalize_identifier("https://t.me/s/deal_cong_nghe"), "deal_cong_nghe")
        self.assertEqual(scanner.normalize_identifier("https://t.me/mggshopeevn?boost"), "mggshopeevn")
        self.assertEqual(scanner.normalize_identifier("muaban_hanoi"), "muaban_hanoi")

    def test_04_multi_source_prioritize_better_deals(self):
        """Kiểm tra cào đa nguồn và ưu tiên sản phẩm có giá thấp hơn giá tham chiếu"""
        hunter = MultiSourceHunter()

        mock_lazada_response = {
            "mods": {
                "listItems": [
                    {
                        "itemId": "111",
                        "name": "Bàn Phím Cơ Aula F75 Pro Chính Hãng",
                        "price": "380000",
                        "originalPrice": "650000",
                        "discount": "41% Off",
                        "ratingScore": 4.9,
                        "itemSoldCntShow": "1.2k Đã bán",
                        "isLazMall": True,
                        "sellerName": "AULA Official Store",
                        "itemUrl": "//www.lazada.vn/products/aula-f75-i111.html",
                        "image": "//img.lazcdn.com/p/111.jpg"
                    },
                    {
                        "itemId": "222",
                        "name": "Bàn Phím Cơ Aula F75 Phiên Bản Giới Hạn",
                        "price": "520000",
                        "originalPrice": "700000",
                        "discount": "25% Off",
                        "ratingScore": 4.7,
                        "itemSoldCntShow": "350 Đã bán",
                        "isLazMall": False,
                        "sellerName": "Game Store",
                        "itemUrl": "//www.lazada.vn/products/aula-f75-i222.html",
                        "image": "//img.lazcdn.com/p/222.jpg"
                    }
                ]
            }
        }

        with patch.object(hunter, "_query_lazada_api", return_value=mock_lazada_response["mods"]["listItems"]):
            # Giá tham chiếu = 450,000đ
            deals = hunter.search_deals("Aula F75", source_platform="ALL", reference_price=450000.0)

            self.assertEqual(len(deals), 2)
            # Item 1 có giá 380,000đ < 450,000đ -> is_better_deal = True
            # Item 2 có giá 520,000đ > 450,000đ -> is_better_deal = False
            self.assertTrue(deals[0]["is_better_deal"])
            self.assertFalse(deals[1]["is_better_deal"])

            # Ưu tiên sản phẩm có giá thấp hơn lên đầu danh sách
            self.assertEqual(deals[0]["item_id"], "laz_111")
            self.assertEqual(deals[0]["sale_price"], 380000.0)
            self.assertEqual(deals[0]["price_diff"], 70000.0)  # Tiết kiệm 70,000đ
            self.assertGreater(deals[0]["savings_percent"], 15.0)

            # Kiểm tra link affiliate được gắn
            self.assertTrue(len(deals[0]["aff_url"]) > 0)

    def test_05_database_persistence_and_rescan_history(self):
        """
        Kiểm tra Lưu dữ liệu & Lịch sử giá:
        Khi bấm Quét Lại, cập nhật dữ liệu mới nhưng vẫn giữ nguyên lịch sử cũ.
        """
        import uuid
        test_cluster_key = f"aula_f75_test_{uuid.uuid4().hex[:8]}"

        # 1. Tạo phiên săn deal
        session_id = self.db.create_hunt_session(
            mode="KEYWORD",
            source_platform="LAZADA_MALL",
            input_query="Bàn phím cơ Aula F75",
            auto_send_telegram=0
        )
        self.assertGreater(session_id, 0)

        # 2. Tạo cụm sản phẩm
        cluster_id = self.db.save_product_cluster({
            "session_id": session_id,
            "cluster_key": test_cluster_key,
            "product_name": "Bàn Phím Cơ Aula F75",
            "reference_price": 500000.0,
            "avg_price": 500000.0,
            "min_price": 450000.0,
            "max_price": 550000.0,
            "sample_count": 3
        })
        self.assertGreater(cluster_id, 0)

        # 3. Ghi nhận giá lần 1 (Ngày 1: Giá 450k)
        self.db.record_hunt_price_history(
            cluster_key=test_cluster_key,
            product_name="Bàn Phím Cơ Aula F75",
            platform="LAZADA_MALL",
            item_id="laz_111",
            price=450000.0,
            reference_price=500000.0
        )

        history_v1 = self.db.get_hunt_price_history_by_cluster(test_cluster_key)
        self.assertEqual(len(history_v1), 1)
        self.assertEqual(history_v1[0]["price"], 450000.0)

        # 4. Giả lập bấm "Quét Lại" (Ngày 2: Giá giảm còn 399k)
        self.db.record_hunt_price_history(
            cluster_key=test_cluster_key,
            product_name="Bàn Phím Cơ Aula F75",
            platform="LAZADA_MALL",
            item_id="laz_111",
            price=399000.0,
            reference_price=500000.0
        )

        # Kiểm tra: Lịch sử giá cũ vẫn còn nguyên vẹn, số bản ghi tăng lên 2!
        history_v2 = self.db.get_hunt_price_history_by_cluster(test_cluster_key)
        self.assertEqual(len(history_v2), 2)
        self.assertEqual(history_v2[0]["price"], 450000.0)  # Lịch sử cũ giữ nguyên
        self.assertEqual(history_v2[1]["price"], 399000.0)  # Dữ liệu mới cập nhật

    def test_06_publish_hunted_deal_to_telegram(self):
        """Kiểm tra định dạng và bắn deal hời vào Telegram"""
        publisher = TelegramPublisher(db=self.db)

        test_deal = {
            "name": "Bàn Phím Cơ Aula F75 Không Dây 3 Chế Độ",
            "platform": "LAZADA_MALL",
            "seller_name": "Aula Official Store",
            "reference_price": 500000.0,
            "sale_price": 380000.0,
            "price_diff": 120000.0,
            "savings_percent": 24.0,
            "rating_star": 5.0,
            "historical_sold": 2500,
            "item_url": "https://www.lazada.vn/products/aula-f75-i111.html",
            "aff_url": "https://c.lazada.vn/t/c.test",
            "image_url": "https://img.lazcdn.com/p/111.jpg"
        }

        # Mock request post tới Telegram Bot API
        with patch("requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_post.return_value = mock_resp

            # Cấu hình bot token test
            publisher.bot_token = "123456:TEST_BOT_TOKEN"
            publisher.chat_id = "@test_channel"

            success = publisher.publish_hunted_deal(test_deal)
            self.assertTrue(success)

            # Kiểm tra payload gửi sang Telegram
            args, kwargs = mock_post.call_args
            caption = kwargs.get("json", {}).get("caption", "")
            self.assertIn("SĂN ĐƯỢC DEAL HỜI", caption)
            self.assertIn("500,000", caption)
            self.assertIn("380,000", caption)
            self.assertIn("-120,000", caption)
            self.assertIn("24.0%", caption)

    def test_07_facebook_scanner_and_target_management(self):
        """
        Kiểm tra nghiệp vụ Quét từ Group Facebook:
        - Chuẩn hóa URL Group Facebook
        - Thêm/Xóa/Chọn mục tiêu Group Facebook trong Database
        - Quét bài rao bán từ 1 hoặc nhiều Group Facebook & gom cụm tính giá tham chiếu
        """
        from modules.crawler.facebook_scanner import FacebookScanner
        scanner = FacebookScanner()

        # 1. Kiểm tra chuẩn hóa URL nhóm Facebook
        self.assertEqual(
            scanner.normalize_group_url("https://www.facebook.com/groups/chophimcovn/?ref=share"),
            "https://www.facebook.com/groups/chophimcovn/"
        )
        self.assertEqual(
            scanner.normalize_group_url("groups/passdonamdep"),
            "https://www.facebook.com/groups/passdonamdep/"
        )
        self.assertEqual(
            scanner.normalize_group_url("chocongngheviet"),
            "https://www.facebook.com/groups/chocongngheviet/"
        )
        self.assertEqual(
            scanner.extract_group_slug_or_id("https://www.facebook.com/groups/chophimcovn/"),
            "chophimcovn"
        )

        # 2. Thêm nhóm Facebook mục tiêu vào CSDL
        test_url = "https://www.facebook.com/groups/test_banphim_vn/"
        target_id = self.db.save_facebook_scan_target(
            name="Chợ Bàn Phím Cơ Test",
            group_url=test_url,
            group_id="test_banphim_vn",
            category_name="Thiết Bị Điện Tử",
            is_active=1
        )
        self.assertGreater(target_id, 0)

        # Lấy danh sách nhóm
        targets = self.db.get_facebook_scan_targets()
        found = next((t for t in targets if t["group_url"] == test_url), None)
        self.assertIsNotNone(found)
        self.assertEqual(found["name"], "Chợ Bàn Phím Cơ Test")

        # 3. Quét các bài rao bán từ nhiều Group Facebook giả định
        mock_posts = [
            {"text": "Pass bàn phím cơ Aula F75 mới mua 1 tuần giá 420k", "source": "Facebook: Chợ Phím 1", "group_url": test_url},
            {"text": "Cần bán Aula F75 không dây 3 mode giá 480k", "source": "Facebook: Chợ Phím 2", "group_url": "https://www.facebook.com/groups/phoidonamdep/"},
        ]

        with patch.object(scanner, "scan_group_posts", return_value=mock_posts):
            scanned = scanner.scan_multiple_groups([
                {"name": "Group 1", "group_url": test_url},
                {"name": "Group 2", "group_url": "https://www.facebook.com/groups/phoidonamdep/"}
            ])
            self.assertGreaterEqual(len(scanned), 2)

            # Gom cụm sản phẩm & tính giá tham chiếu từ các bài rao bán trong Group Facebook
            clusters = ProductClusterEngine.cluster_messages(scanned)
            f75_cluster = next((c for c in clusters if "f75" in c["cluster_key"]), None)
            self.assertIsNotNone(f75_cluster)
            # 420k & 480k -> Reference (Median) = 450k, Avg = 450k
            self.assertEqual(f75_cluster["reference_price"], 450000.0)
            self.assertEqual(f75_cluster["avg_price"], 450000.0)

        # 4. Xóa nhóm Facebook mục tiêu
        ok = self.db.delete_facebook_scan_target(target_id)
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()
