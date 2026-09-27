"""
Facebook Account Repository Module
===================================
Quản lý toàn bộ thao tác CRUD liên quan tới Facebook Accounts, Multi-Account Rotation,
Workload Balancing và Cooldown Tracking.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from database.connection import BaseRepository


class AccountRepository(BaseRepository):
    """Repository quản lý danh sách tài khoản Facebook & luân phiên tài khoản"""

    def get_fb_accounts(self, only_active: bool = False) -> List[Dict]:
        """Lấy danh sách các tài khoản Facebook trong hệ thống"""
        self.reset_fb_accounts_daily_counters_if_needed()
        with self.get_connection() as conn:
            query = "SELECT * FROM fb_accounts"
            if only_active:
                query += " WHERE is_active = 1 AND status != 'DISABLED'"
            query += " ORDER BY id ASC"
            rows = conn.execute(query).fetchall()
            return [dict(r) for r in rows]

    def get_fb_account_by_id(self, account_id: int) -> Optional[Dict]:
        """Lấy chi tiết 1 tài khoản Facebook"""
        with self.get_connection() as conn:
            row = conn.execute("SELECT * FROM fb_accounts WHERE id = ?", (account_id,)).fetchone()
            return dict(row) if row else None

    def save_fb_account(
        self,
        name: str,
        cookie: str,
        profile_path: str = "",
        daily_post_limit: int = 3,
        daily_join_limit: int = 3,
        proxy: str = "",
        notes: str = "",
        is_active: int = 1
    ) -> int:
        """Thêm tài khoản Facebook mới"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                INSERT INTO fb_accounts (
                    name, cookie, profile_path, daily_post_limit, daily_join_limit,
                    proxy, notes, is_active, last_posted_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_DATE)
            """, (
                name.strip(), cookie.strip(), profile_path.strip(),
                daily_post_limit, daily_join_limit, proxy.strip(),
                notes.strip(), 1 if is_active else 0
            ))
            conn.commit()
            return cursor.lastrowid

    def update_fb_account(self, account_id: int, **kwargs) -> bool:
        """Cập nhật thông tin tài khoản Facebook"""
        if not kwargs:
            return False
        fields = []
        values = []
        for k, v in kwargs.items():
            if k in ["name", "cookie", "profile_path", "daily_post_limit", "daily_join_limit", "proxy", "notes", "is_active", "status", "posts_today", "joins_today", "last_used_at", "last_posted_date"]:
                fields.append(f"{k} = ?")
                values.append(v)
        if not fields:
            return False
        values.append(account_id)
        with self.get_connection() as conn:
            conn.execute(f"UPDATE fb_accounts SET {', '.join(fields)} WHERE id = ?", tuple(values))
            conn.commit()
            return True

    def delete_fb_account(self, account_id: int) -> bool:
        """Xóa tài khoản Facebook"""
        with self.get_connection() as conn:
            conn.execute("DELETE FROM fb_accounts WHERE id = ?", (account_id,))
            conn.commit()
            return True

    def reset_fb_accounts_daily_counters_if_needed(self):
        """Tự động reset số bài đăng & join nhóm trong ngày nếu bước sang ngày mới"""
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            with self.get_connection() as conn:
                conn.execute("""
                    UPDATE fb_accounts 
                    SET posts_today = 0, joins_today = 0, last_posted_date = ?
                    WHERE last_posted_date IS NULL OR last_posted_date != ?
                """, (today, today))
                conn.commit()
        except Exception:
            pass

    def get_next_rotating_fb_account(self, task_type: str = "POST") -> Optional[Dict]:
        """
        Lấy tài khoản Facebook tiếp theo theo cơ chế Round-Robin luân phiên:
        - Phải đang Active (is_active = 1, status != 'DISABLED')
        - Chưa chạm hạn mức ngày (posts_today < daily_post_limit hoặc joins_today < daily_join_limit)
        - Ưu tiên tài khoản chưa dùng hoặc được dùng lâu nhất (last_used_at ASC NULLS FIRST)
        """
        self.reset_fb_accounts_daily_counters_if_needed()
        with self.get_connection() as conn:
            if task_type.upper() == "POST":
                cond = "posts_today < daily_post_limit"
            else:
                cond = "joins_today < daily_join_limit"

            query = f"""
                SELECT * FROM fb_accounts 
                WHERE is_active = 1 AND status != 'DISABLED' AND {cond}
                ORDER BY 
                    CASE WHEN last_used_at IS NULL THEN 0 ELSE 1 END,
                    last_used_at ASC,
                    id ASC
                LIMIT 1
            """
            row = conn.execute(query).fetchone()
            return dict(row) if row else None

    def increment_fb_account_usage(self, account_id: int, task_type: str = "POST", success: bool = True, error_msg: str = ""):
        """Ghi nhận lượt sử dụng tài khoản Facebook và cập nhật trạng thái an toàn"""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        today = datetime.now().strftime("%Y-%m-%d")
        with self.get_connection() as conn:
            if task_type.upper() == "POST":
                inc_sql = "posts_today = posts_today + 1"
            else:
                inc_sql = "joins_today = joins_today + 1"

            # Checkpoint detection
            status_update = ""
            err_lower = error_msg.lower()
            if any(term in err_lower for term in ["checkpoint", "bị khóa", "khóa nick", "login", "cookie hết hạn", "phiên đăng nhập"]):
                status_update = ", status = 'CHECKPOINT'"

            conn.execute(f"""
                UPDATE fb_accounts 
                SET {inc_sql}, last_used_at = ?, last_posted_date = ? {status_update}
                WHERE id = ?
            """, (now_str, today, account_id))
            conn.commit()

    def record_account_usage_event(
        self,
        account_id: int,
        group_id: str,
        deal_id: Optional[str] = None,
        post_url: Optional[str] = None,
        action_type: str = "POST",
        status: str = "SUCCESS",
        error_message: Optional[str] = None,
        duration_seconds: float = 0.0,
        cooldown_seconds: int = 900
    ):
        """Ghi nhận sự kiện sử dụng tài khoản vào account_usage_history và cập nhật trạng thái/cooldown"""
        now = datetime.now()
        now_str = now.strftime("%Y-%m-%d %H:%M:%S")
        today = now.strftime("%Y-%m-%d")
        cooldown_dt = (now + timedelta(seconds=cooldown_seconds)).strftime("%Y-%m-%d %H:%M:%S") if status == "SUCCESS" else None

        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO account_usage_history (
                    account_id, group_id, deal_id, post_url, action_type, status, error_message, duration_seconds, used_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (account_id, str(group_id), str(deal_id) if deal_id else None, post_url, action_type, status, error_message, round(duration_seconds, 2)))

            status_update = ""
            err_lower = (error_message or "").lower()
            if any(term in err_lower for term in ["checkpoint", "bị khóa", "khóa nick", "login", "cookie hết hạn", "phiên đăng nhập"]):
                status_update = ", status = 'CHECKPOINT', is_active = 0"

            inc_sql = "posts_today = posts_today + 1, posts_current_cycle = posts_current_cycle + 1, total_posts = total_posts + 1" if action_type == "POST" else "joins_today = joins_today + 1"

            conn.execute(f"""
                UPDATE fb_accounts SET
                    {inc_sql},
                    last_used_at = ?,
                    last_posted_date = ?,
                    cooldown_until = COALESCE(?, cooldown_until)
                    {status_update}
                WHERE id = ?
            """, (now_str, today, cooldown_dt, account_id))
            conn.commit()

    def get_available_accounts_for_router(self, task_type: str = "POST") -> List[Dict]:
        """
        Lấy danh sách tất cả các tài khoản Facebook khả dụng cho Account Router:
        - is_active = 1, status = 'ACTIVE'
        - Chưa chạm daily_post_limit
        - Kiểm tra tính toán trạng thái cooldown thời gian thực
        """
        self.reset_fb_accounts_daily_counters_if_needed()
        now = datetime.now()
        with self.get_connection() as conn:
            limit_cond = "posts_today < daily_post_limit" if task_type == "POST" else "joins_today < daily_join_limit"
            rows = conn.execute(f"""
                SELECT * FROM fb_accounts 
                WHERE is_active = 1 AND status = 'ACTIVE' AND {limit_cond}
                ORDER BY 
                    CASE WHEN last_used_at IS NULL THEN 0 ELSE 1 END,
                    last_used_at ASC,
                    posts_today ASC,
                    id ASC
            """).fetchall()

            accounts = []
            for r in rows:
                acc = dict(r)
                cooldown_str = acc.get("cooldown_until")
                in_cooldown = False
                cooldown_remaining_sec = 0
                if cooldown_str:
                    try:
                        cooldown_dt = datetime.strptime(cooldown_str, "%Y-%m-%d %H:%M:%S")
                        if cooldown_dt > now:
                            in_cooldown = True
                            cooldown_remaining_sec = int((cooldown_dt - now).total_seconds())
                    except Exception:
                        pass
                acc["is_in_cooldown"] = in_cooldown
                acc["cooldown_remaining_sec"] = cooldown_remaining_sec
                accounts.append(acc)

            return accounts

    def get_account_usage_history(self, limit: int = 50, account_id: Optional[int] = None) -> List[Dict]:
        """Lấy danh sách lịch sử sử dụng tài khoản kèm tên tài khoản và nhóm"""
        with self.get_connection() as conn:
            query = """
                SELECT h.*, a.name as account_name, g.name as group_name, g.category_name
                FROM account_usage_history h
                LEFT JOIN fb_accounts a ON h.account_id = a.id
                LEFT JOIN fb_groups g ON h.group_id = g.group_id
                WHERE 1=1
            """
            params: List[Any] = []
            if account_id:
                query += " AND h.account_id = ?"
                params.append(account_id)
            query += " ORDER BY h.id DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(query, tuple(params)).fetchall()
            return [dict(r) for r in rows]

    def reset_account_cycle_counters(self):
        """Reset số bài đăng trong chu kỳ hiện tại (posts_current_cycle = 0) khi chu kỳ rollover"""
        with self.get_connection() as conn:
            conn.execute("UPDATE fb_accounts SET posts_current_cycle = 0")
            conn.commit()

    def release_account_cooldown(self, account_id: int):
        """Xóa bỏ cooldown thủ công cho một tài khoản"""
        with self.get_connection() as conn:
            conn.execute("UPDATE fb_accounts SET cooldown_until = NULL WHERE id = ?", (account_id,))
            conn.commit()
