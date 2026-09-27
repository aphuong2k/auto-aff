"""
Facebook Group Repository Module
=================================
Quản lý toàn bộ thao tác CRUD liên quan tới Facebook Groups & Outreach Logs:
- Lưu trữ nhóm, phân loại tổng hợp / ngách
- Theo dõi chỉ số sức khỏe (Health Scorer) & group ma (Ghost Groups)
- Phản hồi duyệt thành viên (Join Feedback Monitor) & duyệt bài (Post Approval Monitor)
- Chống đăng trùng deal vào nhóm (Anti-Duplicate Posting)
- Lưu vết bài đăng / bình luận seeding (Posted Logs & Comment Seeding)
"""

from datetime import datetime
from typing import Dict, List, Optional, Any

from database.connection import BaseRepository


class GroupRepository(BaseRepository):
    """Repository quản lý nhóm Facebook & Outreach logs"""

    def save_group(self, group_id: str, name: str, url: str, category_name: str, members: int, group_type: str = ""):
        """Lưu hoặc cập nhật thông tin nhóm Facebook"""
        from config.categories_filter import is_general_deal_group
        if not group_type:
            group_type = "GENERAL" if is_general_deal_group(name) else "NICHE"

        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO fb_groups (group_id, name, url, category_name, members_count, group_type)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(group_id) DO UPDATE SET
                    members_count = excluded.members_count,
                    group_type = excluded.group_type
            """, (group_id, name, url, category_name, members, group_type))
            conn.commit()

    def get_general_deal_groups(self, limit: int = 20) -> List[Dict]:
        """Lấy danh sách các nhóm săn deal / săn sale tổng hợp"""
        with self.get_connection() as conn:
            rows = conn.execute("""
                SELECT * FROM fb_groups 
                WHERE group_type = 'GENERAL' OR name LIKE '%săn deal%' OR name LIKE '%săn sale%' OR name LIKE '%mã giảm giá%'
                ORDER BY members_count DESC 
                LIMIT ?
            """, (limit,)).fetchall()
            return [dict(r) for r in rows]

    def get_groups_by_status(self, status: str) -> List[Dict]:
        """Lấy danh sách nhóm theo trạng thái (APPROVED, PENDING, DISCOVERED...)"""
        with self.get_connection() as conn:
            rows = conn.execute("SELECT * FROM fb_groups WHERE status = ?", (status,)).fetchall()
            return [dict(r) for r in rows]

    def update_group_status(self, group_id: str, status: str):
        """Cập nhật trạng thái nhóm Facebook"""
        with self.get_connection() as conn:
            conn.execute("UPDATE fb_groups SET status = ? WHERE group_id = ?", (status, group_id))
            conn.commit()

    def delete_group(self, group_id: str):
        """Xóa nhóm khỏi CSDL"""
        with self.get_connection() as conn:
            conn.execute("DELETE FROM fb_groups WHERE group_id = ?", (group_id,))
            conn.commit()

    def update_group_health(self, group_id: str, health_score: int, avg_engagement: float, 
                            last_active_at: Optional[str] = None, unique_posters: int = 0, 
                            health_verdict: str = "UNKNOWN"):
        """Cập nhật chỉ số sức khỏe của nhóm Facebook (chống group ma)"""
        with self.get_connection() as conn:
            conn.execute("""
                UPDATE fb_groups 
                SET health_score = ?, 
                    avg_engagement = ?, 
                    last_active_at = COALESCE(?, last_active_at), 
                    unique_posters = ?, 
                    health_verdict = ?
                WHERE group_id = ?
            """, (health_score, avg_engagement, last_active_at, unique_posters, health_verdict, group_id))
            conn.commit()

    def update_group_join_feedback(self, group_id: str, status: str, join_check_count: Optional[int] = None):
        """Cập nhật phản hồi xét duyệt gia nhập nhóm"""
        with self.get_connection() as conn:
            if join_check_count is not None:
                conn.execute("""
                    UPDATE fb_groups 
                    SET status = ?, 
                        join_checked_at = CURRENT_TIMESTAMP, 
                        join_check_count = ?
                    WHERE group_id = ?
                """, (status, join_check_count, group_id))
            else:
                conn.execute("""
                    UPDATE fb_groups 
                    SET status = ?, 
                        join_checked_at = CURRENT_TIMESTAMP, 
                        join_check_count = COALESCE(join_check_count, 0) + 1
                    WHERE group_id = ?
                """, (status, group_id))
            conn.commit()

    def record_group_post_rejection(self, group_id: str, max_consecutive_rejections: int = 3) -> bool:
        """Ghi nhận bài đăng bị từ chối/không duyệt. Nếu liên tiếp >= max -> hạn chế đăng."""
        with self.get_connection() as conn:
            row = conn.execute("SELECT consecutive_rejections FROM fb_groups WHERE group_id = ?", (group_id,)).fetchone()
            current_rej = (row["consecutive_rejections"] or 0) + 1 if row else 1
            restricted = 1 if current_rej >= max_consecutive_rejections else 0
            conn.execute("""
                UPDATE fb_groups 
                SET consecutive_rejections = ?,
                    posting_restricted = ?
                WHERE group_id = ?
            """, (current_rej, restricted, group_id))
            conn.commit()
            return restricted == 1

    def reset_group_post_rejections(self, group_id: str):
        """Reset số lần bị từ chối khi bài viết được duyệt thành công"""
        with self.get_connection() as conn:
            conn.execute("""
                UPDATE fb_groups 
                SET consecutive_rejections = 0,
                    posting_restricted = 0
                WHERE group_id = ?
            """, (group_id,))
            conn.commit()

    def get_ghost_groups(self, max_score: int = 35) -> List[Dict]:
        """Lấy danh sách các nhóm bị đánh giá là group ma hoặc điểm sức khỏe quá thấp"""
        with self.get_connection() as conn:
            rows = conn.execute("""
                SELECT * FROM fb_groups 
                WHERE health_score < ? OR health_verdict = 'GHOST'
                ORDER BY health_score ASC
            """, (max_score,)).fetchall()
            return [dict(r) for r in rows]

    def get_active_approved_groups(self, category_name: Optional[str] = None) -> List[Dict]:
        """Lấy các nhóm đã APPROVED, không bị hạn chế đăng và không phải group ma"""
        with self.get_connection() as conn:
            query = """
                SELECT * FROM fb_groups 
                WHERE status = 'APPROVED' 
                  AND enabled = 1
                  AND (posting_restricted IS NULL OR posting_restricted = 0)
                  AND (health_score IS NULL OR health_score >= 30)
            """
            params = []
            if category_name:
                query += " AND (category_name = ? OR group_type = 'GENERAL')"
                params.append(category_name)
            query += " ORDER BY priority DESC, members_count DESC"
            rows = conn.execute(query, tuple(params)).fetchall()
            return [dict(r) for r in rows]

    def update_post_approval_status(self, post_id: int, status: str):
        """Cập nhật trạng thái duyệt bài trong lịch sử post_history"""
        with self.get_connection() as conn:
            conn.execute("""
                UPDATE post_history 
                SET approval_status = ?, 
                    approval_checked_at = CURRENT_TIMESTAMP 
                WHERE id = ?
            """, (status, post_id))
            conn.commit()

    def is_deal_posted_to_group(self, deal_id: str, group_id: str) -> bool:
        """Kiểm tra deal này đã từng được đăng lên group này chưa (Anti-Duplicate Posting)"""
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM deal_post_history WHERE deal_id = ? AND group_id = ?",
                (str(deal_id), str(group_id))
            ).fetchone()
            return row is not None

    def record_deal_post(self, deal_id: str, group_id: str, post_url: str = "", account_name: str = ""):
        """Ghi nhận deal đã đăng vào nhóm để bảo đảm không đăng trùng lần 2"""
        with self.get_connection() as conn:
            conn.execute("""
                INSERT OR IGNORE INTO deal_post_history (deal_id, group_id, post_url, account_name)
                VALUES (?, ?, ?, ?)
            """, (str(deal_id), str(group_id), post_url or "", account_name or ""))
            conn.commit()

    def is_group_scanned_today(self, group_id: str) -> bool:
        """Kiểm tra nhóm đã được scan/xử lý trong ngày hôm nay chưa"""
        today = datetime.now().strftime("%Y-%m-%d")
        with self.get_connection() as conn:
            row = conn.execute("""
                SELECT 1 FROM group_scan_history 
                WHERE group_id = ? AND scan_date = ? AND status IN ('COMPLETED', 'SKIPPED')
            """, (str(group_id), today)).fetchone()
            return row is not None

    def record_group_scan(
        self,
        execution_id: str,
        group_id: str,
        group_name: str,
        category_name: str,
        cycle_id: int,
        status: str,
        current_step: str = 'COMPLETED',
        deals_evaluated: int = 0,
        deal_posted_id: Optional[str] = None,
        deal_posted_name: Optional[str] = None,
        post_url: Optional[str] = None,
        deals_seeded: int = 0,
        error_message: Optional[str] = None,
        duration_seconds: float = 0,
        retry_count: int = 0
    ) -> int:
        """Ghi nhận hoặc cập nhật lịch sử quét Node Group cho ngày hôm nay (Upsert an toàn)"""
        today = datetime.now().strftime("%Y-%m-%d")
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO group_scan_history (
                    execution_id, group_id, group_name, category_name, cycle_id, scan_date,
                    status, current_step, deals_evaluated, deal_posted_id, deal_posted_name,
                    post_url, deals_seeded, error_message, retry_count, duration_seconds, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(group_id, scan_date) DO UPDATE SET
                    execution_id = excluded.execution_id,
                    cycle_id = excluded.cycle_id,
                    status = excluded.status,
                    current_step = excluded.current_step,
                    deals_evaluated = excluded.deals_evaluated,
                    deal_posted_id = COALESCE(excluded.deal_posted_id, group_scan_history.deal_posted_id),
                    deal_posted_name = COALESCE(excluded.deal_posted_name, group_scan_history.deal_posted_name),
                    post_url = COALESCE(excluded.post_url, group_scan_history.post_url),
                    deals_seeded = excluded.deals_seeded,
                    error_message = excluded.error_message,
                    retry_count = excluded.retry_count,
                    duration_seconds = excluded.duration_seconds,
                    updated_at = CURRENT_TIMESTAMP
            """, (
                execution_id, str(group_id), group_name, category_name, cycle_id, today,
                status, current_step, deals_evaluated, str(deal_posted_id) if deal_posted_id else None,
                deal_posted_name, post_url, deals_seeded, error_message, retry_count, round(duration_seconds, 2)
            ))
            hist_id = cursor.lastrowid
            conn.commit()
            return hist_id

    def get_group_scan_history(
        self,
        limit: int = 50,
        cycle_id: Optional[int] = None,
        group_id: Optional[str] = None
    ) -> List[Dict]:
        """Lấy danh sách lịch sử xử lý từng Node group"""
        with self.get_connection() as conn:
            query = "SELECT * FROM group_scan_history WHERE 1=1"
            params: List[Any] = []
            if cycle_id:
                query += " AND cycle_id = ?"
                params.append(cycle_id)
            if group_id:
                query += " AND group_id = ?"
                params.append(str(group_id))
            query += " ORDER BY id DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(query, tuple(params)).fetchall()
            return [dict(r) for r in rows]

    def seed_default_group_catalog_if_empty(self):
        """Bổ sung danh mục nhóm mẫu nếu CSDL có ít hơn 5 nhóm"""
        with self.get_connection() as conn:
            conn.execute("UPDATE fb_groups SET category_name = 'Thời Trang Nữ' WHERE group_id = '1027765188537633'")
            conn.execute("UPDATE fb_groups SET category_name = 'Thiết Bị Điện Tử' WHERE group_id = 'congdongandroidvietnam'")
            conn.commit()

            count = conn.execute("SELECT COUNT(*) as c FROM fb_groups").fetchone()["c"]
            if count < 5:
                sample_groups = [
                    ("grp_men_01", "Góc Phối Đồ Nam & Pass Đồ Chuẩn", "https://www.facebook.com/groups/phoidonamdep/", "Thời Trang Nam", 28500, "APPROVED"),
                    ("grp_men_02", "Hội Mặc Đẹp & Săn Sale Đồ Nam Shopee", "https://www.facebook.com/groups/sansaledonam/", "Thời Trang Nam", 19200, "APPROVED"),
                    ("grp_women_01", "Hội Chị Em Mê Váy Xinh & Shopee Haul", "https://www.facebook.com/groups/chiemvayxinh/", "Thời Trang Nữ", 45000, "APPROVED"),
                    ("grp_women_02", "Góc Pass Đồ & Review Quần Áo Nữ Shopee", "https://www.facebook.com/groups/passdonudep/", "Thời Trang Nữ", 32100, "APPROVED"),
                    ("grp_tech_01", "Hội Review Phụ Kiện Điện Thoại & Cáp Sạc Tai Nghe", "https://www.facebook.com/groups/phukiencaploatai/", "Thiết Bị Điện Tử", 52000, "APPROVED"),
                    ("grp_tech_02", "Cộng Đồng Góc Máy Đẹp & Setup Bàn Làm Việc", "https://www.facebook.com/groups/setupbanlamviec/", "Thiết Bị Điện Tử", 68000, "APPROVED"),
                    ("grp_home_01", "Hội Nghiện Nhà & Review Đồ Gia Dụng Thông Minh", "https://www.facebook.com/groups/nghiennhagiadung/", "Thiết Bị Điện Gia Dụng", 85000, "APPROVED"),
                    ("grp_home_02", "Yêu Bếp & Mẹo Sắm Nồi Chiên Không Dầu Chảo Bếp", "https://www.facebook.com/groups/yeubepticnhi/", "Thiết Bị Điện Gia Dụng", 41000, "APPROVED"),
                    ("grp_deal_01", "Hội Săn Deal Shopee 1K & Mã Freeship 0Đ VIP", "https://www.facebook.com/groups/sansaleshopee1k/", "Săn Deal Tổng Hợp", 125000, "APPROVED"),
                    ("grp_deal_02", "Cộng Đồng Săn Mã Giảm Giá & Canh Giờ Vàng Back Mã", "https://www.facebook.com/groups/canhmagiamgia/", "Săn Deal Tổng Hợp", 94000, "APPROVED")
                ]

                for gid, name, url, cat, mems, status in sample_groups:
                    conn.execute("""
                        INSERT OR IGNORE INTO fb_groups (group_id, name, url, category_name, members_count, status, priority, enabled)
                        VALUES (?, ?, ?, ?, ?, ?, 1, 1)
                    """, (gid, name, url, cat, mems, status))
                conn.commit()

    def get_eligible_groups_for_cycle(self) -> List[Dict]:
        """
        Lấy danh sách các nhóm hợp lệ để duyệt theo chu kỳ Closed-Loop.
        Ưu tiên theo vòng lặp phản hồi doanh thu (Revenue & Conversion Feedback Loop):
        1. Nhóm có hoa hồng phát sinh cao hơn (Top Revenue).
        2. Nhóm có lượt click tương tác cao hơn (Top Traffic).
        3. Số lượng thành viên lớn và độ uy tín cao.
        Loại trừ nhóm bị chặn (posting_restricted) hoặc nhóm ma (health_score < 30).
        """
        self.seed_default_group_catalog_if_empty()
        with self.get_connection() as conn:
            rows = conn.execute("""
                SELECT g.*,
                       COALESCE((
                           SELECT SUM(comm.commission_amount)
                           FROM commissions comm
                           WHERE comm.sub_id LIKE '%' || g.group_id || '%'
                              OR comm.sub_id LIKE 'grp_' || SUBSTR(g.group_id, 1, 8) || '%'
                       ), 0) as past_commission,
                       COALESCE((
                           SELECT COUNT(*)
                           FROM click_analytics c
                           WHERE c.sub_id LIKE '%' || g.group_id || '%'
                              OR c.sub_id LIKE 'grp_' || SUBSTR(g.group_id, 1, 8) || '%'
                       ), 0) as past_clicks
                FROM fb_groups g
                WHERE g.enabled = 1 
                  AND g.status IN ('APPROVED', 'PENDING', 'DISCOVERED')
                  AND (g.posting_restricted IS NULL OR g.posting_restricted = 0)
                  AND (g.health_score IS NULL OR g.health_score >= 30)
                ORDER BY g.priority DESC, 
                         past_commission DESC, 
                         past_clicks DESC, 
                         g.members_count DESC, 
                         g.group_id ASC
            """).fetchall()
            return [dict(r) for r in rows]

    def clear_groups(self):
        """Xóa toàn bộ nhóm Facebook đã dò tìm"""
        with self.get_connection() as conn:
            conn.execute("DELETE FROM fb_groups")
            conn.commit()

    def log_comment_seeding(self, group_id: str, item_id: str, comment_text: str, target_post_url: Optional[str] = None, status: str = "SUCCESS"):
        """Ghi nhận lịch sử bình luận dạo đề xuất deal trong nhóm Facebook"""
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO comment_seeding_history (group_id, item_id, comment_text, target_post_url, status)
                VALUES (?, ?, ?, ?, ?)
            """, (str(group_id), str(item_id), comment_text, target_post_url, status))
            conn.commit()

    def get_comment_seeding_history(self, limit: int = 50) -> List[Dict]:
        """Lấy danh sách các bình luận seeding gần đây"""
        with self.get_connection() as conn:
            rows = conn.execute("""
                SELECT s.*, g.name as group_name, d.name as deal_name
                FROM comment_seeding_history s
                LEFT JOIN fb_groups g ON s.group_id = g.group_id
                LEFT JOIN deals d ON s.item_id = d.item_id
                ORDER BY s.posted_at DESC, s.id DESC
                LIMIT ?
            """, (limit,)).fetchall()
            return [dict(r) for r in rows]

    def get_seeding_comments_today_count(self, group_id: str) -> int:
        """Đếm số comment seeding đã đăng/gửi vào nhóm trong ngày hôm nay"""
        with self.get_connection() as conn:
            row = conn.execute("""
                SELECT COUNT(*) as cnt FROM comment_seeding_history
                WHERE group_id = ? 
                  AND status IN ('SUBMITTED', 'SUCCESS')
                  AND date(posted_at) = date('now', 'localtime')
            """, (str(group_id),)).fetchone()
            return row["cnt"] if row else 0

    def update_comment_seeding_status(self, group_id: str, item_id: str, target_post_url: str, status: str):
        """Cập nhật trạng thái của bản ghi comment seeding mới nhất khớp thông tin"""
        with self.get_connection() as conn:
            conn.execute("""
                UPDATE comment_seeding_history
                SET status = ?
                WHERE id = (
                    SELECT id FROM comment_seeding_history
                    WHERE group_id = ? AND item_id = ? AND target_post_url = ?
                    ORDER BY id DESC LIMIT 1
                )
            """, (status, str(group_id), str(item_id), target_post_url))
            conn.commit()

    def log_posted_item(
        self,
        post_type: str,
        group_name: str,
        group_url: str = "",
        target_url: str = "",
        item_id: str = "",
        item_name: str = "",
        content_snippet: str = "",
        image_path: str = "",
        status: str = "SUCCESS",
        account_name: str = "",
        template_id: str = "",
        content_hash: str = ""
    ) -> int:
        """Lưu lại log bài viết hoặc comment đã đăng lên Facebook kèm link kiểm tra"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO posted_logs (type, group_name, group_url, target_url, item_id, item_name, content_snippet, image_path, status, account_name, template_id, content_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (post_type.upper(), group_name, group_url, target_url, str(item_id), item_name, content_snippet, image_path, status, account_name, template_id, content_hash))
            conn.commit()
            return cursor.lastrowid

    def get_group_last_template_id(self, group_id: str) -> str:
        """Lấy template_id đã dùng gần nhất cho nhóm để thực hiện xoay vòng template"""
        with self.get_connection() as conn:
            row = conn.execute("SELECT last_template_id FROM fb_groups WHERE group_id = ? OR id = ?", (str(group_id), str(group_id))).fetchone()
            return row["last_template_id"] if row and row["last_template_id"] else ""

    def update_group_last_template_id(self, group_id: str, template_id: str):
        """Cập nhật template_id gần nhất đã dùng cho nhóm"""
        with self.get_connection() as conn:
            conn.execute("UPDATE fb_groups SET last_template_id = ? WHERE group_id = ? OR id = ?", (template_id, str(group_id), str(group_id)))
            conn.commit()

    def get_recent_post_contents_for_group(self, group_name: str, limit: int = 10) -> List[str]:
        """Lấy các nội dung bài đăng gần đây của nhóm để kiểm tra độ trùng lặp"""
        with self.get_connection() as conn:
            rows = conn.execute("""
                SELECT content_snippet FROM posted_logs
                WHERE group_name = ? AND type = 'POST'
                ORDER BY posted_at DESC, id DESC LIMIT ?
            """, (group_name, limit)).fetchall()
            return [r["content_snippet"] for r in rows if r["content_snippet"]]

    def get_posted_logs(self, limit: int = 50, post_type: Optional[str] = None) -> List[Dict]:
        """Lấy danh sách các bài viết / comment đã đăng gần đây kèm link kiểm tra trên FB"""
        with self.get_connection() as conn:
            if post_type:
                rows = conn.execute("""
                    SELECT * FROM posted_logs 
                    WHERE type = ? 
                    ORDER BY posted_at DESC, id DESC 
                    LIMIT ?
                """, (post_type.upper(), limit)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT * FROM posted_logs 
                    ORDER BY posted_at DESC, id DESC 
                    LIMIT ?
                """, (limit,)).fetchall()
            return [dict(r) for r in rows]

    def delete_posted_log(self, log_id: int) -> bool:
        """Xóa một bản ghi log bài đăng"""
        with self.get_connection() as conn:
            conn.execute("DELETE FROM posted_logs WHERE id = ?", (log_id,))
            conn.commit()
            return True
