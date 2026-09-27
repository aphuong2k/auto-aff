import os
import unittest
import tempfile
import sqlite3

from database.db_manager import DatabaseManager
from modules.outreach.post_composer import ContentDeduplicator, LinguisticPermutator, PostComposer


class TestContentDeduplicatorAndComposer(unittest.TestCase):
    """Kiểm tra toàn diện cơ chế chống trùng lặp nội dung, xoay vòng template và ngôn từ vùng miền"""

    def setUp(self):
        self.temp_db_fd, self.temp_db_path = tempfile.mkstemp(suffix=".db")
        self.db = DatabaseManager(self.temp_db_path)
        self.composer = PostComposer(self.db)

    def tearDown(self):
        try:
            os.close(self.temp_db_fd)
            if os.path.exists(self.temp_db_path):
                os.remove(self.temp_db_path)
        except Exception:
            pass

    def test_01_text_normalization_and_hash(self):
        """Kiểm tra chuẩn hóa văn bản loại bỏ link, icon, số tiền và sinh hash chuẩn"""
        raw_text = "Hàng sale sốc 99k! 👉 Mua ngay tại https://shopee.vn/product/123/456 #sale #dealhot"
        norm = ContentDeduplicator.normalize_text(raw_text)
        self.assertNotIn("https", norm)
        self.assertNotIn("#sale", norm)
        self.assertNotIn("99k", norm)

        h1 = ContentDeduplicator.hash_content(raw_text)
        h2 = ContentDeduplicator.hash_content(raw_text + "  \n  ")
        self.assertEqual(h1, h2)
        print(f"✅ test_01_text_normalization_and_hash passed (Hash: {h1})")

    def test_02_similarity_calculation(self):
        """Kiểm tra thuật toán đo độ tương đồng giữa các bài viết"""
        text_a = "Góc phối đồ cho anh em hôm nay. Con áo thun này sale sâu quá giá chỉ 150k"
        text_b = "Góc phối đồ cho anh em hôm nay. Con áo thun này sale sâu quá giá chỉ 150k"
        sim_identical = ContentDeduplicator.calculate_similarity(text_a, text_b)
        self.assertEqual(sim_identical, 1.0)

        text_c = "Review tai nghe bluetooth chống ồn cực ngon cho dân công nghệ giá chỉ 350k"
        sim_different = ContentDeduplicator.calculate_similarity(text_a, text_c)
        self.assertLess(sim_different, 0.4)

        # Bài viết gần giống nhau (> 80%)
        text_d = "Góc phối đồ cho anh em hôm nay nè. Con áo thun này sale sâu quá giá 150k nha"
        sim_close = ContentDeduplicator.calculate_similarity(text_a, text_d)
        self.assertGreaterEqual(sim_close, 0.70)
        print(f"✅ test_02_similarity_calculation passed (Identical: {sim_identical}, Different: {sim_different}, Close: {sim_close})")

    def test_03_duplicate_detection_against_history(self):
        """Kiểm tra phát hiện trùng lặp > 80% với lịch sử nhóm"""
        history = [
            "Góc phối đồ cho anh em nhé. Con áo sơ mi nam này sale sâu chỉ còn 120k",
            "Review tai nghe xịn sò chính hãng âm bass căng đét"
        ]
        new_dup = "Góc phối đồ cho anh em nhé. Con áo sơ mi nam này sale sâu chỉ còn 120k múc ngay"
        is_dup, max_sim, _ = ContentDeduplicator.is_similar_to_history(new_dup, history, threshold=0.80)
        self.assertTrue(is_dup)
        self.assertGreaterEqual(max_sim, 0.80)

        new_unique = "Bác nào mê phong cách thể thao đường phố thì nghía qua con áo khoác gió này nha"
        is_dup2, max_sim2, _ = ContentDeduplicator.is_similar_to_history(new_unique, history, threshold=0.80)
        self.assertFalse(is_dup2)
        self.assertLess(max_sim2, 0.80)
        print(f"✅ test_03_duplicate_detection_against_history passed (Dup max: {max_sim}, Unique max: {max_sim2})")

    def test_04_template_rotation_and_composition(self):
        """Kiểm tra PostComposer tự động xoay vòng template khác nhau khi đăng liên tiếp vào cùng 1 nhóm"""
        # Tạo nhóm test
        with self.db.get_connection() as conn:
            conn.execute("""
                INSERT INTO fb_groups (group_id, name, url, category_name, members_count, status)
                VALUES ('grp_rot_01', 'Hội Đam Mê Công Nghệ', 'https://facebook.com/groups/tech', 'Thiết Bị Điện Tử', 10000, 'APPROVED')
            """)
            conn.commit()

        group = {"group_id": "grp_rot_01", "name": "Hội Đam Mê Công Nghệ", "category_name": "Thiết Bị Điện Tử"}
        deal = {
            "item_id": "item_tech_01",
            "name": "Bàn Phím Cơ Không Dây RGB Hot-swap",
            "price_sale": 499000,
            "price_original": 890000,
            "discount_percent": 44,
            "rating_star": 4.9,
            "historical_sold": 3200,
            "item_url": "https://shopee.vn/product/111/222"
        }

        # Lượt 1
        res1 = self.composer.compose_post_for_group(deal, group)
        tpl1 = res1["template_id"]
        self.assertTrue(tpl1.startswith("TECH_TPL_"))

        # Ghi nhận bài 1 vào posted_logs để tạo lịch sử
        self.db.log_posted_item(
            post_type="POST",
            group_name=group["name"],
            item_id=deal["item_id"],
            item_name=deal["name"],
            content_snippet=res1["content"][:180],
            template_id=tpl1,
            content_hash=res1["content_hash"]
        )

        # Lượt 2: Phải xoay sang template khác
        res2 = self.composer.compose_post_for_group(deal, group)
        tpl2 = res2["template_id"]
        self.assertNotEqual(tpl1, tpl2)
        print(f"✅ test_04_template_rotation_and_composition passed (Turn 1: {tpl1} -> Turn 2: {tpl2})")

    def test_05_linguistic_permutations(self):
        """Kiểm tra bộ trộn ngôn từ vùng miền sinh ngẫu nhiên các hậu tố đa dạng"""
        particles_seen = set()
        for _ in range(50):
            p = LinguisticPermutator.get_particle()
            particles_seen.add(p)
        self.assertGreater(len(particles_seen), 3)
        self.assertTrue(any(p in ["nha", "nhé", "nè", "ạ"] for p in particles_seen))
        print(f"✅ test_05_linguistic_permutations passed (Generated particles: {particles_seen})")


if __name__ == "__main__":
    unittest.main()
