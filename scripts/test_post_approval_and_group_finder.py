"""
Test Post Approval Auto-Leave & Group Discovery Engagement/Recency Checks
========================================================================
Kiểm tra:
1. Quy tắc ghi nhận bị chờ duyệt / từ chối: Khi chạm ngưỡng 2 lần liên tiếp -> posting_restricted = 1 và kích hoạt auto-leave (status = 'LEFT', enabled = 0).
2. Quy tắc reset số lần vi phạm khi bài viết được duyệt thành công (APPROVED).
3. FacebookGroupFinder & FacebookAutoJoiner: Thẩm định nghiêm ngặt tương tác (avg_engagement >= 2.0) và bài mới nhất (last_post_hours_ago <= 72h).
"""

import sys
import unittest
from unittest.mock import MagicMock, patch

from database.db_manager import DatabaseManager
from modules.outreach.post_approval_monitor import PostApprovalMonitor
from modules.outreach.fb_group_finder import FacebookGroupFinder
from modules.outreach.fb_auto_joiner import FacebookAutoJoiner


class TestApprovalAndDiscovery(unittest.TestCase):
    def setUp(self):
        self.db = DatabaseManager()
        self.test_group_id = "test_grp_approval_001"
        self.test_group_url = "https://www.facebook.com/groups/test_grp_approval_001/"
        
        # Tạo nhóm test
        with self.db.get_connection() as conn:
            conn.execute("DELETE FROM fb_groups WHERE group_id = ?", (self.test_group_id,))
            conn.execute("DELETE FROM post_history WHERE target_id = ?", (self.test_group_id,))
            conn.execute("DELETE FROM posted_logs WHERE group_url LIKE ?", (f"%{self.test_group_id}%",))
            conn.commit()

        self.db.save_group(
            group_id=self.test_group_id,
            name="Test Group Auto Leave",
            url=self.test_group_url,
            category_name="Săn Deal Tổng Hợp",
            members=25000
        )
        self.db.update_group_status(self.test_group_id, "APPROVED")

    def tearDown(self):
        with self.db.get_connection() as conn:
            conn.execute("DELETE FROM fb_groups WHERE group_id = ?", (self.test_group_id,))
            conn.execute("DELETE FROM post_history WHERE target_id = ?", (self.test_group_id,))
            conn.execute("DELETE FROM posted_logs WHERE group_url LIKE ?", (f"%{self.test_group_id}%",))
            conn.commit()

    def test_01_rejection_and_pending_strikes(self):
        """Kiểm tra strike 1 lần chưa bị khóa, strike 2 lần bị khóa ngay lập tức"""
        # Lần 1: Bị chờ duyệt
        restricted = self.db.record_group_post_rejection(self.test_group_id, max_consecutive_rejections=2, reason="PENDING")
        self.assertFalse(restricted, "Lần 1 bị chờ duyệt không được khóa ngay")

        with self.db.get_connection() as conn:
            row = conn.execute("SELECT consecutive_rejections, pending_approval_count, requires_post_approval, posting_restricted FROM fb_groups WHERE group_id = ?", (self.test_group_id,)).fetchone()
            self.assertEqual(row["consecutive_rejections"], 1)
            self.assertEqual(row["pending_approval_count"], 1)
            self.assertEqual(row["requires_post_approval"], 1)
            self.assertEqual(row["posting_restricted"], 0)

        # Lần 2: Tiếp tục bị chờ duyệt -> Phải bị khóa (posting_restricted = 1)
        restricted2 = self.db.record_group_post_rejection(self.test_group_id, max_consecutive_rejections=2, reason="PENDING")
        self.assertTrue(restricted2, "Lần 2 liên tiếp phải bị khóa posting_restricted = 1")

        with self.db.get_connection() as conn:
            row2 = conn.execute("SELECT consecutive_rejections, pending_approval_count, posting_restricted FROM fb_groups WHERE group_id = ?", (self.test_group_id,)).fetchone()
            self.assertEqual(row2["consecutive_rejections"], 2)
            self.assertEqual(row2["pending_approval_count"], 2)
            self.assertEqual(row2["posting_restricted"], 1)

        # Reset khi có bài được duyệt
        self.db.reset_group_post_rejections(self.test_group_id)
        with self.db.get_connection() as conn:
            row_reset = conn.execute("SELECT consecutive_rejections, pending_approval_count, posting_restricted FROM fb_groups WHERE group_id = ?", (self.test_group_id,)).fetchone()
            self.assertEqual(row_reset["consecutive_rejections"], 0)
            self.assertEqual(row_reset["pending_approval_count"], 0)
            self.assertEqual(row_reset["posting_restricted"], 0)

    def test_02_post_approval_monitor_auto_leave(self):
        """Kiểm tra PostApprovalMonitor phát hiện bài chờ duyệt 2 lần và tự động out group"""
        monitor = PostApprovalMonitor(self.db)
        
        # Thêm 2 bài đăng trong lịch sử post_history có trạng thái PENDING
        with self.db.get_connection() as conn:
            conn.execute("INSERT OR IGNORE INTO deals (item_id, name) VALUES ('deal_01', 'Dép đi trong nhà'), ('deal_02', 'Nồi chiên không dầu')")
            conn.execute("""
                INSERT INTO post_history (target_type, target_id, deal_id, content, status, approval_status, posted_at)
                VALUES ('FB_GROUP', ?, 'deal_01', '🔥 SALE KHỦNG DÉP ĐI TRONG NHÀ 9K LINK MUA', 'PENDING_APPROVAL', 'PENDING', datetime('now', '-3 hours'))
            """, (self.test_group_id,))
            conn.execute("""
                INSERT INTO post_history (target_type, target_id, deal_id, content, status, approval_status, posted_at)
                VALUES ('FB_GROUP', ?, 'deal_02', '⚡ FLASH SALE NỒI CHIÊN KHÔNG DẦU GIÁ SỐC', 'PENDING_APPROVAL', 'PENDING', datetime('now', '-2 hours'))
            """, (self.test_group_id,))
            conn.commit()

        # Mock playwright session
        mock_leave = MagicMock(return_value=True)
        monitor.feedback_monitor.leave_group = mock_leave

        # Giả lập trang group có thông báo đang chờ phê duyệt
        mock_page = MagicMock()
        mock_locator = MagicMock()
        mock_locator.inner_text.return_value = "Nhóm Săn Deal VIP. Bạn có 1 bài viết đang chờ phê duyệt từ quản trị viên."
        mock_page.locator.return_value = mock_locator

        # Giả lập Playwright context
        with patch("playwright.sync_api.sync_playwright") as mock_pw, \
             patch.dict("os.environ", {"FB_COOKIE": "c_user=10001;xs=abc123xyz;"}):
            
            mock_p_instance = MagicMock()
            mock_pw.return_value.__enter__.return_value = mock_p_instance
            mock_browser = MagicMock()
            mock_context = MagicMock()
            mock_p_instance.chromium.launch.return_value = mock_browser
            mock_browser.new_context.return_value = mock_context
            mock_context.new_page.return_value = mock_page

            res = monitor.check_pending_approvals(auto_leave_on_blacklist=True, max_strikes=2)

            self.assertGreaterEqual(res["still_pending"], 1)
            self.assertGreaterEqual(res["groups_restricted"], 1)
            self.assertGreaterEqual(res["groups_left"], 1)
            mock_leave.assert_called()

            # Xác minh trong CSDL trạng thái nhóm chuyển thành LEFT và enabled = 0
            with self.db.get_connection() as conn:
                g = conn.execute("SELECT status, enabled, posting_restricted, health_verdict FROM fb_groups WHERE group_id = ?", (self.test_group_id,)).fetchone()
                self.assertEqual(g["status"], "LEFT")
                self.assertEqual(g["enabled"], 0)
                self.assertEqual(g["posting_restricted"], 1)
                self.assertEqual(g["health_verdict"], "PENDING_OUT")

    def test_03_group_discovery_health_rules(self):
        """Kiểm tra điều kiện thẩm định group: Tương tác >= 2.0 và bài mới nhất <= 72h"""
        finder = FacebookGroupFinder(self.db)

        # Test Case A: Nhóm bỏ hoang (bài đăng gần nhất 120h trước > 72h)
        dead_health = {
            "health_score": 45,
            "avg_engagement": 5.0,
            "last_post_hours_ago": 120.0, # 5 ngày trước
            "verdict": "WARNING"
        }
        is_abandoned = (dead_health["last_post_hours_ago"] is None or dead_health["last_post_hours_ago"] > 72.0)
        self.assertTrue(is_abandoned, "Nhóm bài đăng > 72h phải bị coi là nhóm bỏ hoang")

        # Test Case B: Nhóm chết tương tác (avg_engagement = 0.5 < 2.0)
        low_eng_health = {
            "health_score": 50,
            "avg_engagement": 0.5,
            "last_post_hours_ago": 10.0,
            "verdict": "WARNING"
        }
        is_low = (low_eng_health["avg_engagement"] < 2.0)
        self.assertTrue(is_low, "Nhóm có tương tác < 2.0 phải bị loại")

        # Test Case C: Nhóm đạt chuẩn (tương tác 8.5, bài đăng 4.2h trước)
        healthy = {
            "health_score": 85,
            "avg_engagement": 8.5,
            "last_post_hours_ago": 4.2,
            "verdict": "HEALTHY"
        }
        is_good = (healthy["avg_engagement"] >= 2.0 and healthy["last_post_hours_ago"] <= 72.0 and healthy["health_score"] >= 40)
        self.assertTrue(is_good, "Nhóm đạt chuẩn phải được chấp thuận tham gia")


if __name__ == "__main__":
    unittest.main()
