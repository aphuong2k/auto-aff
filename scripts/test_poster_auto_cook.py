"""
Test Auto-Cook on Posting Failure
==================================
Kiểm tra tính năng:
Nếu khi đăng bài, nhóm bị:
- Chưa tham gia (có nút Tham gia nhóm)
- Kẹt chờ duyệt gia nhập (có nút Hủy yêu cầu)
- Chỉ Admin được đăng bài
- Không tìm thấy nút tạo bài viết
-> Hệ thống ngay lập tức TỰ ĐỘNG CHO COOK (status='LEFT', enabled=0, posting_restricted=1)
"""

import sys
import unittest
from unittest.mock import MagicMock, patch

from database.db_manager import DatabaseManager
from modules.outreach.fb_group_poster import FacebookGroupPoster


class TestPosterAutoCook(unittest.TestCase):
    def setUp(self):
        self.db = DatabaseManager()
        self.test_group_id = "test_grp_cook_999"
        self.test_url = "https://www.facebook.com/groups/test_grp_cook_999/"
        with self.db.get_connection() as conn:
            conn.execute("DELETE FROM fb_groups WHERE group_id = ?", (self.test_group_id,))
            conn.commit()

        self.db.save_group(self.test_group_id, "Nhóm Test Cook", self.test_url, "Thời Trang Nữ", 10000)
        self.db.update_group_status(self.test_group_id, "APPROVED")

    def tearDown(self):
        with self.db.get_connection() as conn:
            conn.execute("DELETE FROM fb_groups WHERE group_id = ?", (self.test_group_id,))
            conn.commit()

    def test_auto_cook_when_not_joined(self):
        """Khi mở group thấy nút 'Tham gia nhóm' -> Cho cook ngay lập tức"""
        poster = FacebookGroupPoster(self.db)
        mock_page = MagicMock()
        mock_page.locator.return_value.inner_text.return_value = "Tham gia nhóm để đăng bài và tương tác. Nút Tham gia nhóm"
        mock_page.locator.return_value.count.return_value = 1

        res = poster.post_to_single_group(
            group_id=self.test_group_id,
            custom_content="Nội dung test bài đăng",
            page=mock_page
        )

        self.assertEqual(res["status"], "FAILED")
        self.assertTrue(res.get("cooked"))

        # Kiểm tra trong DB: nhóm đã bị cook (status = 'LEFT', enabled = 0, posting_restricted = 1)
        with self.db.get_connection() as conn:
            g = conn.execute("SELECT status, enabled, posting_restricted, health_verdict FROM fb_groups WHERE group_id = ?", (self.test_group_id,)).fetchone()
            self.assertEqual(g["status"], "LEFT")
            self.assertEqual(g["enabled"], 0)
            self.assertEqual(g["posting_restricted"], 1)
            self.assertEqual(g["health_verdict"], "NOT_JOINED_COOKED")

    def test_auto_cook_when_no_trigger_button(self):
        """Khi không tìm thấy nút tạo bài viết -> Rời nhóm và cho cook ngay lập tức"""
        poster = FacebookGroupPoster(self.db)
        mock_leave = MagicMock(return_value=True)
        poster.feedback_monitor.leave_group = mock_leave

        mock_page = MagicMock()
        mock_page.locator.return_value.inner_text.return_value = "Bảng tin nhóm bình thường không có nút tạo bài viết nào"
        mock_page.locator.return_value.count.return_value = 0
        mock_page.locator.return_value.first.is_visible.return_value = False

        res = poster.post_to_single_group(
            group_id=self.test_group_id,
            custom_content="Nội dung test bài đăng",
            page=mock_page
        )

        self.assertEqual(res["status"], "FAILED")
        self.assertTrue(res.get("cooked"))
        mock_leave.assert_called_with(self.test_url, page=mock_page)

        # Kiểm tra trong DB
        with self.db.get_connection() as conn:
            g = conn.execute("SELECT status, enabled, posting_restricted, health_verdict FROM fb_groups WHERE group_id = ?", (self.test_group_id,)).fetchone()
            self.assertEqual(g["status"], "LEFT")
            self.assertEqual(g["enabled"], 0)
            self.assertEqual(g["posting_restricted"], 1)
            self.assertEqual(g["health_verdict"], "NO_POST_BUTTON_COOKED")


if __name__ == "__main__":
    unittest.main()
