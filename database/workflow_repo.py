"""
Workflow, Cycles & Reporting Repository Module
===============================================
Quản lý:
- Danh mục sản phẩm (Categories)
- Từ khóa tự học (Learned Keywords)
- Chương trình khuyến mại & Nhắc giờ sale (Promotions & Reminders)
- Chu kỳ quét Node Group (System Cycles)
- Thống kê tiến độ hàng ngày (Daily Report Stats)
- Báo cáo toàn trình các phiên chạy (Workflow Reports)
- Khôi phục / Xóa sạch dữ liệu (Reset All Data)
"""

from datetime import datetime
from typing import Dict, List, Optional, Any

from database.connection import BaseRepository


class WorkflowRepository(BaseRepository):
    """Repository quản lý chu trình, vòng lặp quét, báo cáo vận hành & danh mục"""

    # --- Category Operations ---
    def save_category(self, cat_id: int, name: str, parent_id: Optional[int] = None):
        """Lưu hoặc cập nhật danh mục Shopee/Lazada"""
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO categories (cat_id, name, parent_id, last_scanned_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(cat_id) DO UPDATE SET
                    name = excluded.name,
                    parent_id = excluded.parent_id,
                    last_scanned_at = CURRENT_TIMESTAMP
            """, (cat_id, name, parent_id))
            conn.commit()

    def get_active_categories(self) -> List[Dict]:
        """Lấy danh mục đang kích hoạt"""
        with self.get_connection() as conn:
            rows = conn.execute("SELECT * FROM categories WHERE is_active = 1").fetchall()
            return [dict(r) for r in rows]

    def get_all_categories(self) -> List[Dict]:
        """Lấy tất cả danh mục hợp lệ đã lưu trong CSDL"""
        return self.get_active_categories()

    # --- Learned Keywords Operations ---
    def save_learned_keyword(self, category_name: str, keyword: str, source_group_name: str = ""):
        """Lưu hoặc tăng tần suất từ khóa tự học được từ tên group"""
        clean_kw = keyword.strip().lower()
        if not clean_kw or len(clean_kw) < 2:
            return
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO learned_keywords (category_name, keyword, source_group_name, frequency, last_used_at)
                VALUES (?, ?, ?, 1, CURRENT_TIMESTAMP)
                ON CONFLICT(category_name, keyword) DO UPDATE SET
                    frequency = frequency + 1,
                    source_group_name = excluded.source_group_name,
                    last_used_at = CURRENT_TIMESTAMP
            """, (category_name, clean_kw, source_group_name))
            conn.commit()

    def get_learned_keywords(self, category_name: Optional[str] = None, limit: int = 20) -> List[Dict]:
        """Lấy danh sách các từ khóa đã học được theo ngành hàng, sắp xếp theo độ phổ biến"""
        with self.get_connection() as conn:
            if category_name:
                rows = conn.execute("""
                    SELECT * FROM learned_keywords
                    WHERE category_name = ?
                    ORDER BY frequency DESC, id DESC
                    LIMIT ?
                """, (category_name, limit)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT * FROM learned_keywords
                    ORDER BY frequency DESC, id DESC
                    LIMIT ?
                """, (limit,)).fetchall()
            return [dict(r) for r in rows]

    def clear_learned_keywords(self):
        """Xóa toàn bộ từ khóa đã học"""
        with self.get_connection() as conn:
            conn.execute("DELETE FROM learned_keywords")
            conn.commit()

    # --- Sale Promotions & Reminder Operations ---
    def save_promotion(self, promo: Dict):
        """Lưu hoặc cập nhật chương trình khuyến mại/voucher"""
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO sale_promotions (
                    title, campaign_type, slot_time, banner_url, aff_url, description, vouchers_json, is_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                promo.get("title", ""),
                promo.get("campaign_type", "FLASH_SALE"),
                promo.get("slot_time", "ALL_DAY"),
                promo.get("banner_url", ""),
                promo.get("aff_url", ""),
                promo.get("description", ""),
                promo.get("vouchers_json", "[]"),
                promo.get("is_active", 1)
            ))
            conn.commit()

    def get_active_promotions(self) -> List[Dict]:
        """Lấy danh sách các chương trình khuyến mại đang kích hoạt"""
        with self.get_connection() as conn:
            rows = conn.execute("""
                SELECT * FROM sale_promotions
                WHERE is_active = 1
                ORDER BY id DESC
            """).fetchall()
            return [dict(r) for r in rows]

    def log_sale_reminder(self, slot_time: str, campaign_date: str, content: str, target: str = "TELEGRAM"):
        """Ghi nhận lịch sử đã bắn bài nhắc giờ sale"""
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO sale_reminder_history (slot_time, campaign_date, target, content, sent_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(slot_time, campaign_date, target) DO UPDATE SET
                    content = excluded.content,
                    sent_at = CURRENT_TIMESTAMP
            """, (slot_time, campaign_date, target, content))
            conn.commit()

    def is_sale_reminder_sent(self, slot_time: str, campaign_date: str, target: str = "TELEGRAM") -> bool:
        """Kiểm tra xem khung giờ sale này hôm nay đã gửi bài nhắc chưa"""
        with self.get_connection() as conn:
            row = conn.execute("""
                SELECT id FROM sale_reminder_history
                WHERE slot_time = ? AND campaign_date = ? AND target = ?
            """, (slot_time, campaign_date, target)).fetchone()
            return row is not None

    def get_recent_reminders(self, limit: int = 20) -> List[Dict]:
        """Lấy lịch sử các lần nhắc gần đây"""
        with self.get_connection() as conn:
            rows = conn.execute("""
                SELECT * FROM sale_reminder_history
                ORDER BY sent_at DESC
                LIMIT ?
            """, (limit,)).fetchall()
            return [dict(r) for r in rows]

    # --- System Cycles Operations ---
    def get_or_create_active_cycle(self, total_groups: int = 0) -> Dict:
        """Lấy chu kỳ đang ACTIVE hoặc tự động tạo chu kỳ mới (#001, #002...)"""
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM system_cycles WHERE status = 'ACTIVE' ORDER BY cycle_number DESC LIMIT 1"
            ).fetchone()
            if row:
                cycle_dict = dict(row)
                if total_groups > 0 and cycle_dict.get("total_groups", 0) != total_groups:
                    conn.execute("UPDATE system_cycles SET total_groups = ? WHERE cycle_id = ?", (total_groups, cycle_dict["cycle_id"]))
                    conn.commit()
                    cycle_dict["total_groups"] = total_groups
                return cycle_dict

            # Nếu chưa có cycle active: tạo cycle tiếp theo
            last_cycle = conn.execute("SELECT MAX(cycle_number) as max_c FROM system_cycles").fetchone()
            next_num = (last_cycle["max_c"] or 0) + 1 if last_cycle else 1

            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO system_cycles (cycle_number, status, total_groups, current_group_pointer)
                VALUES (?, 'ACTIVE', ?, 0)
            """, (next_num, total_groups))
            cycle_id = cursor.lastrowid
            conn.commit()
            return {
                "cycle_id": cycle_id,
                "cycle_number": next_num,
                "status": "ACTIVE",
                "total_groups": total_groups,
                "completed_groups": 0,
                "skipped_groups": 0,
                "failed_groups": 0,
                "current_group_pointer": 0,
                "current_group_id": None
            }

    def update_cycle_progress(
        self,
        cycle_id: int,
        pointer: int,
        current_group_id: Optional[str] = None,
        completed_inc: int = 0,
        skipped_inc: int = 0,
        failed_inc: int = 0,
        deals_found_inc: int = 0,
        posts_inc: int = 0,
        seedings_inc: int = 0
    ):
        """Cập nhật tiến độ chu kỳ (pointer, số nhóm đã hoàn thành/bỏ qua/lỗi)"""
        with self.get_connection() as conn:
            conn.execute("""
                UPDATE system_cycles SET
                    current_group_pointer = ?,
                    current_group_id = COALESCE(?, current_group_id),
                    completed_groups = completed_groups + ?,
                    skipped_groups = skipped_groups + ?,
                    failed_groups = failed_groups + ?,
                    total_deals_found = total_deals_found + ?,
                    total_posts = total_posts + ?,
                    total_seedings = total_seedings + ?
                WHERE cycle_id = ?
            """, (pointer, current_group_id, completed_inc, skipped_inc, failed_inc, deals_found_inc, posts_inc, seedings_inc, cycle_id))
            conn.commit()

    def complete_current_cycle(self, cycle_id: int):
        """Đóng chu kỳ hiện tại và ghi nhận thời gian hoàn thành"""
        with self.get_connection() as conn:
            conn.execute("""
                UPDATE system_cycles SET
                    status = 'COMPLETED',
                    completed_at = CURRENT_TIMESTAMP
                WHERE cycle_id = ?
            """, (cycle_id,))
            conn.commit()

    def get_all_cycles(self, limit: int = 20) -> List[Dict]:
        """Lấy danh sách các chu kỳ quét đã chạy"""
        with self.get_connection() as conn:
            rows = conn.execute("SELECT * FROM system_cycles ORDER BY cycle_number DESC LIMIT ?", (limit,)).fetchall()
            return [dict(r) for r in rows]

    def get_daily_report_stats(self, date_str: Optional[str] = None) -> Dict:
        """Tổng hợp báo cáo tiến độ và hiệu suất theo ngày"""
        today = date_str or datetime.now().strftime("%Y-%m-%d")
        with self.get_connection() as conn:
            total_groups = conn.execute("SELECT COUNT(*) as c FROM fb_groups WHERE enabled = 1").fetchone()["c"]
            scanned_today = conn.execute("SELECT COUNT(*) as c FROM group_scan_history WHERE scan_date = ?", (today,)).fetchone()["c"]
            completed = conn.execute("SELECT COUNT(*) as c FROM group_scan_history WHERE scan_date = ? AND status = 'COMPLETED'", (today,)).fetchone()["c"]
            skipped = conn.execute("SELECT COUNT(*) as c FROM group_scan_history WHERE scan_date = ? AND status = 'SKIPPED'", (today,)).fetchone()["c"]
            failed = conn.execute("SELECT COUNT(*) as c FROM group_scan_history WHERE scan_date = ? AND status LIKE '%FAILED%'", (today,)).fetchone()["c"]
            
            deals_posted = conn.execute("SELECT COUNT(*) as c FROM group_scan_history WHERE scan_date = ? AND deal_posted_id IS NOT NULL", (today,)).fetchone()["c"]
            deals_seeded = conn.execute("SELECT SUM(deals_seeded) as s FROM group_scan_history WHERE scan_date = ?", (today,)).fetchone()["s"] or 0
            
            active_cycle = conn.execute("SELECT * FROM system_cycles WHERE status = 'ACTIVE' ORDER BY cycle_number DESC LIMIT 1").fetchone()
            cycle_dict = dict(active_cycle) if active_cycle else {"cycle_number": 1, "completed_groups": 0, "total_groups": total_groups}

            return {
                "date": today,
                "total_groups": total_groups,
                "scanned_today": scanned_today,
                "completed": completed,
                "skipped": skipped,
                "failed": failed,
                "deals_posted": deals_posted,
                "deals_seeded": deals_seeded,
                "success_rate": round((completed / max(scanned_today, 1)) * 100, 1) if scanned_today > 0 else 0.0,
                "current_cycle": cycle_dict
            }

    # --- Workflow Reports Operations ---
    def create_workflow_report(self, run_type: str, step_name: str, summary_text: str = "") -> int:
        """Khởi tạo một bản ghi báo cáo tiến trình (Status: RUNNING) và trả về report_id"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO workflow_reports (run_type, step_name, status, summary_text, started_at)
                    VALUES (?, ?, 'RUNNING', ?, CURRENT_TIMESTAMP)
                """, (run_type, step_name, summary_text))
                conn.commit()
                return cursor.lastrowid
        except Exception as e:
            print(f"Lỗi khởi tạo workflow report: {e}")
            return 0

    def update_workflow_report(self, report_id: int, **kwargs):
        """Cập nhật kết quả chi tiết của phiên chạy khi hoàn thành hoặc có lỗi"""
        if not report_id:
            return
        try:
            fields = []
            values = []
            for k, v in kwargs.items():
                fields.append(f"{k} = ?")
                values.append(v)
            if not fields:
                return

            fields.append("ended_at = CURRENT_TIMESTAMP")
            values.append(report_id)

            sql = f"UPDATE workflow_reports SET {', '.join(fields)} WHERE id = ?"
            with self.get_connection() as conn:
                conn.execute(sql, tuple(values))
                conn.commit()
        except Exception as e:
            print(f"Lỗi cập nhật workflow report #{report_id}: {e}")

    def get_workflow_reports(self, limit: int = 25) -> List[Dict]:
        """Lấy danh sách các báo cáo phiên chạy gần nhất để hiển thị giao diện"""
        try:
            with self.get_connection() as conn:
                rows = conn.execute("""
                    SELECT * FROM workflow_reports 
                    ORDER BY id DESC LIMIT ?
                """, (limit,)).fetchall()
                return [dict(r) for r in rows]
        except Exception as e:
            print(f"Lỗi lấy danh sách workflow reports: {e}")
            return []

    def reset_all_data(self, keep_categories: bool = True):
        """Xóa sạch toàn bộ dữ liệu sản phẩm, nhóm và lịch sử"""
        with self.get_connection() as conn:
            conn.execute("DELETE FROM post_history")
            conn.execute("DELETE FROM deals")
            conn.execute("DELETE FROM fb_groups")
            conn.execute("DELETE FROM price_history")
            conn.execute("DELETE FROM click_analytics")
            conn.execute("DELETE FROM comment_seeding_history")
            conn.execute("DELETE FROM sale_promotions")
            conn.execute("DELETE FROM sale_reminder_history")
            conn.execute("DELETE FROM posted_logs")
            conn.execute("DELETE FROM commissions")
            if not keep_categories:
                conn.execute("DELETE FROM categories")
            conn.commit()
            conn.execute("VACUUM")
