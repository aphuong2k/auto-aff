import sys
import unittest
from unittest.mock import patch, MagicMock

sys.stdout.reconfigure(encoding='utf-8')

from database.db_manager import DatabaseManager
from modules.outreach.fb_account_manager import FacebookAccountManager, resolve_fb_account
from modules.outreach.fb_group_poster import FacebookGroupPoster


class TestExplicitAccountSelection(unittest.TestCase):
    def setUp(self):
        self.db = DatabaseManager()

    def test_01_resolve_explicit_account_id(self):
        """Kiểm tra resolve_fb_account khi truyền account_id cụ thể (e.g. 3)"""
        acc, cookie, profile_path = resolve_fb_account(self.db, account_id=3, allow_rotation=False)
        self.assertIsNotNone(acc, "Phải tìm thấy tài khoản #3")
        self.assertEqual(acc.get("id"), 3)
        self.assertEqual(acc.get("name"), "hoàng thanh huyền")
        self.assertTrue(len(cookie) > 0, "Cookie của tài khoản #3 phải tồn tại")
        print("✅ test_01_resolve_explicit_account_id passed: Đã lấy chính xác nick [hoàng thanh huyền] (ID: 3)")

    def test_02_resolve_string_account_id(self):
        """Kiểm tra resolve_fb_account khi truyền account_id dạng chuỗi '3'"""
        acc, cookie, profile_path = resolve_fb_account(self.db, account_id="3", allow_rotation=False)
        self.assertIsNotNone(acc)
        self.assertEqual(acc.get("id"), 3)
        print("✅ test_02_resolve_string_account_id passed: Hỗ trợ truyền ID dạng chuỗi '3'")

    def test_03_resolve_no_account_no_rotation(self):
        """Khi không truyền account_id và allow_rotation=False, hệ thống KHÔNG TỰ Ý XOAY NICK"""
        acc1, _, _ = resolve_fb_account(self.db, account_id=None, allow_rotation=False)
        acc2, _, _ = resolve_fb_account(self.db, account_id=None, allow_rotation=False)
        self.assertEqual(acc1.get("id"), acc2.get("id"), "Khi không bật rotate, phải giữ nguyên tài khoản cố định!")
        print("✅ test_03_resolve_no_account_no_rotation passed: Không tự ý xoay nick khi allow_rotation=False")

    @patch("time.sleep", return_value=None)
    @patch("modules.outreach.fb_group_poster.FacebookGroupPoster.post_to_single_group")
    def test_04_gradual_posting_keeps_selected_account(self, mock_post, mock_sleep):
        """Kiểm tra run_gradual_posting cố định tài khoản đã chọn cho toàn bộ các nhóm"""
        mock_post.return_value = {"status": "SUCCESS", "message": "OK"}
        poster = FacebookGroupPoster(self.db)
        
        # Giả lập nhóm test
        test_group_ids = ["test_g1", "test_g2"]
        with self.db.get_connection() as conn:
            conn.execute("INSERT OR REPLACE INTO fb_groups (group_id, name, url, status) VALUES ('test_g1', 'Test G1', 'https://fb.com/groups/test_g1', 'APPROVED')")
            conn.execute("INSERT OR REPLACE INTO fb_groups (group_id, name, url, status) VALUES ('test_g2', 'Test G2', 'https://fb.com/groups/test_g2', 'APPROVED')")
            conn.commit()

        # Chạy gradual posting với account_id=3 và delay_seconds=0
        poster.run_gradual_posting(group_ids=test_group_ids, delay_seconds=0, account_id=3)
        
        # Kiểm tra mock_post được gọi 2 lần đều với account ID=3
        self.assertEqual(mock_post.call_count, 2)
        for call_args in mock_post.call_args_list:
            called_acc = call_args.kwargs.get("account")
            self.assertIsNotNone(called_acc)
            self.assertEqual(called_acc.get("id"), 3, "Tất cả bài đăng trong đợt phải dùng đúng nick đã chọn (ID: 3)")

        print("✅ test_04_gradual_posting_keeps_selected_account passed: Toàn bộ đợt đăng giữ nguyên nick ID 3")


if __name__ == "__main__":
    unittest.main()
