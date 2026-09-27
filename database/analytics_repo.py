"""
Analytics, Commissions, Subscribers & Settings Repository Module
=================================================================
Quản lý:
- Click Tracking & Sub-ID Analytics
- Hoa hồng, GMV, đơn hàng đa sàn (Shopee & Lazada)
- Đăng ký nhận tin Flash Sale (Subscribers)
- Mã giảm giá nhập tay (Voucher Codes) & Link chiến dịch (Campaign Links)
- Cấu hình hệ thống (System Settings)
"""

from datetime import datetime
from typing import Dict, List, Optional, Any

from database.connection import BaseRepository


class AnalyticsRepository(BaseRepository):
    """Repository quản lý đo lường, chuyển đổi, đối soát hoa hồng & cấu hình hệ thống"""

    def log_click(
        self,
        item_id: str,
        channel: str = "DIRECT",
        sub_id: Optional[str] = None,
        ip: Optional[str] = None,
        referer: Optional[str] = None,
        user_agent: Optional[str] = None,
        platform: str = "SHOPEE"
    ):
        """Ghi nhận lượt click chuyển tiếp Affiliate qua trang trung gian Anti-Ban"""
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO click_analytics (item_id, channel, sub_id, ip, referer, user_agent, platform)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (str(item_id), channel, sub_id, ip, referer, user_agent, platform.upper()))
            conn.commit()

    def get_click_analytics(self, limit_days: int = 30) -> Dict[str, Any]:
        """Thống kê tổng quan lượt click theo kênh, xu hướng ngày và sản phẩm hot"""
        with self.get_connection() as conn:
            total_clicks = conn.execute("SELECT COUNT(*) FROM click_analytics").fetchone()[0]
            
            # Clicks theo kênh (Telegram, Facebook Group, Seeding, Direct)
            channel_rows = conn.execute("""
                SELECT channel, COUNT(*) as clicks 
                FROM click_analytics 
                GROUP BY channel 
                ORDER BY clicks DESC
            """).fetchall()
            channels = [dict(r) for r in channel_rows]

            # Top 10 sản phẩm được click nhiều nhất
            top_rows = conn.execute("""
                SELECT c.item_id, d.name, d.price_sale, d.local_image, d.platform, COUNT(*) as clicks
                FROM click_analytics c
                LEFT JOIN deals d ON c.item_id = d.item_id
                GROUP BY c.item_id
                ORDER BY clicks DESC
                LIMIT 10
            """).fetchall()
            top_items = [dict(r) for r in top_rows]

            # Xu hướng click 7 ngày gần nhất
            daily_rows = conn.execute("""
                SELECT DATE(clicked_at) as date, COUNT(*) as clicks
                FROM click_analytics
                GROUP BY DATE(clicked_at)
                ORDER BY date DESC
                LIMIT 7
            """).fetchall()
            daily = [dict(r) for r in daily_rows]

            return {
                "total_clicks": total_clicks,
                "channels": channels,
                "top_items": top_items,
                "daily_trend": daily
            }

    def record_commission(
        self,
        platform: str,
        order_id: str,
        commission_amount: float,
        order_value: float = 0.0,
        item_id: Optional[str] = None,
        item_name: Optional[str] = None,
        channel: str = "DIRECT",
        sub_id: Optional[str] = None,
        status: str = "PENDING",
        purchase_time: Optional[str] = None
    ) -> int:
        """Ghi nhận một đơn hàng chuyển đổi hoa hồng thành công từ Shopee hoặc Lazada"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO commissions (
                    platform, order_id, item_id, item_name, channel, sub_id,
                    order_value, commission_amount, status, purchase_time
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(order_id) DO UPDATE SET
                    status = excluded.status,
                    commission_amount = excluded.commission_amount,
                    order_value = excluded.order_value
            """, (
                platform.upper(), str(order_id), str(item_id) if item_id else None,
                item_name, channel, sub_id, float(order_value), float(commission_amount),
                status.upper(), purchase_time or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ))
            conn.commit()
            return cursor.lastrowid

    def get_commissions(
        self,
        limit: int = 50,
        platform: Optional[str] = None,
        status: Optional[str] = None
    ) -> List[Dict]:
        """Lấy danh sách các đơn đối soát hoa hồng"""
        query = "SELECT * FROM commissions WHERE 1=1"
        params: List[Any] = []
        if platform and platform.upper() != "ALL":
            query += " AND platform = ?"
            params.append(platform.upper())
        if status and status.upper() != "ALL":
            query += " AND status = ?"
            params.append(status.upper())

        query += " ORDER BY purchase_time DESC LIMIT ?"
        params.append(limit)

        with self.get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def get_commission_stats(self) -> Dict[str, Any]:
        """Thống kê tổng hợp hoa hồng, GMV, đơn hàng theo sàn & theo kênh"""
        with self.get_connection() as conn:
            total_row = conn.execute("""
                SELECT 
                    COUNT(*) as total_orders,
                    COALESCE(SUM(commission_amount), 0) as total_commission,
                    COALESCE(SUM(order_value), 0) as total_gmv,
                    COALESCE(SUM(CASE WHEN status = 'APPROVED' OR status = 'PAID' THEN commission_amount ELSE 0 END), 0) as approved_commission
                FROM commissions
            """).fetchone()

            platform_rows = conn.execute("""
                SELECT 
                    platform,
                    COUNT(*) as orders,
                    COALESCE(SUM(commission_amount), 0) as commission,
                    COALESCE(SUM(order_value), 0) as gmv
                FROM commissions
                GROUP BY platform
            """).fetchall()

            channel_rows = conn.execute("""
                SELECT 
                    channel,
                    COUNT(*) as orders,
                    COALESCE(SUM(commission_amount), 0) as commission
                FROM commissions
                GROUP BY channel
                ORDER BY commission DESC
            """).fetchall()

            total_clicks = conn.execute("SELECT COUNT(*) FROM click_analytics").fetchone()[0] or 1
            conversion_rate = round((total_row["total_orders"] / total_clicks) * 100, 2)
            epc = round(total_row["total_commission"] / total_clicks, 2)

            return {
                "total_orders": total_row["total_orders"],
                "total_commission": round(total_row["total_commission"], 0),
                "approved_commission": round(total_row["approved_commission"], 0),
                "total_gmv": round(total_row["total_gmv"], 0),
                "conversion_rate_pct": conversion_rate,
                "epc_vnd": epc,
                "by_platform": [dict(r) for r in platform_rows],
                "by_channel": [dict(r) for r in channel_rows]
            }

    def get_group_performance_ranking(self, limit: int = 50) -> List[Dict]:
        """Bảng xếp hạng hiệu quả nhóm Facebook theo doanh thu và lượt click thực tế"""
        with self.get_connection() as conn:
            rows = conn.execute("""
                SELECT 
                    g.group_id,
                    g.name as group_name,
                    g.category_name,
                    g.members_count,
                    g.health_score,
                    g.last_posted_at,
                    COUNT(DISTINCT c.id) as total_clicks,
                    COUNT(DISTINCT comm.id) as total_orders,
                    COALESCE(SUM(comm.commission_amount), 0) as total_commission,
                    COALESCE(SUM(comm.order_value), 0) as total_gmv,
                    ROUND(
                        CASE WHEN COUNT(DISTINCT c.id) > 0 
                             THEN (CAST(COUNT(DISTINCT comm.id) AS FLOAT) / COUNT(DISTINCT c.id)) * 100 
                             ELSE 0.0 END, 2
                    ) as conversion_rate
                FROM fb_groups g
                LEFT JOIN click_analytics c ON c.sub_id LIKE 'grp_' || SUBSTR(g.group_id, 1, 8) || '%'
                LEFT JOIN commissions comm ON comm.sub_id LIKE 'grp_' || SUBSTR(g.group_id, 1, 8) || '%'
                WHERE g.enabled = 1
                GROUP BY g.group_id
                ORDER BY total_commission DESC, total_clicks DESC, g.members_count DESC
                LIMIT ?
            """, (limit,)).fetchall()
            return [dict(r) for r in rows]

    def get_template_performance_comparison(self) -> List[Dict]:
        """So sánh hiệu quả chuyển đổi giữa các mẫu bài viết A/B Testing (Template Angles)"""
        with self.get_connection() as conn:
            rows = conn.execute("""
                SELECT 
                    ph.template_id,
                    COUNT(DISTINCT ph.id) as total_posts,
                    COUNT(DISTINCT c.id) as total_clicks,
                    COUNT(DISTINCT comm.id) as total_orders,
                    COALESCE(SUM(comm.commission_amount), 0) as total_commission,
                    ROUND(
                        CASE WHEN COUNT(DISTINCT ph.id) > 0 
                             THEN CAST(COUNT(DISTINCT c.id) AS FLOAT) / COUNT(DISTINCT ph.id)
                             ELSE 0.0 END, 2
                    ) as avg_clicks_per_post,
                    ROUND(
                        CASE WHEN COUNT(DISTINCT c.id) > 0 
                             THEN (CAST(COUNT(DISTINCT comm.id) AS FLOAT) / COUNT(DISTINCT c.id)) * 100 
                             ELSE 0.0 END, 2
                    ) as conversion_rate
                FROM post_history ph
                LEFT JOIN click_analytics c ON c.sub_id LIKE '%' || ph.template_id
                LEFT JOIN commissions comm ON comm.sub_id LIKE '%' || ph.template_id
                WHERE ph.template_id IS NOT NULL AND ph.template_id != ''
                GROUP BY ph.template_id
                ORDER BY total_clicks DESC, total_commission DESC
            """).fetchall()
            return [dict(r) for r in rows]


    def save_subscriber(
        self,
        email: str,
        telegram_id: Optional[str] = None,
        platform_pref: str = "ALL",
        category_pref: str = "ALL",
        min_discount: int = 30
    ) -> bool:
        """Đăng ký nhận deal hot qua email / telegram alert"""
        email = email.strip().lower()
        if not email or "@" not in email:
            return False
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO subscribers (
                    email, telegram_id, platform_preference, category_preference, min_discount, is_active
                ) VALUES (?, ?, ?, ?, ?, 1)
                ON CONFLICT(email) DO UPDATE SET
                    platform_preference = excluded.platform_preference,
                    category_preference = excluded.category_preference,
                    min_discount = excluded.min_discount,
                    is_active = 1
            """, (email, telegram_id, platform_pref.upper(), category_pref, min_discount))
            conn.commit()
            return True

    def get_active_subscribers(self, platform: Optional[str] = None) -> List[Dict]:
        """Lấy danh sách subscriber đang kích hoạt"""
        query = "SELECT * FROM subscribers WHERE is_active = 1"
        params: List[Any] = []
        if platform and platform.upper() != "ALL":
            query += " AND (platform_preference = 'ALL' OR platform_preference = ?)"
            params.append(platform.upper())

        with self.get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def delete_subscriber(self, email: str):
        """Hủy đăng ký nhận tin"""
        with self.get_connection() as conn:
            conn.execute("UPDATE subscribers SET is_active = 0 WHERE email = ?", (email.strip().lower(),))
            conn.commit()

    def get_voucher_codes(self, voucher_type: Optional[str] = None, only_active: bool = True) -> List[Dict]:
        """Lấy danh sách các mã giảm giá nhập tay hoặc mã % lớn"""
        with self.get_connection() as conn:
            query = "SELECT * FROM voucher_codes WHERE 1=1"
            params: List[Any] = []
            if only_active:
                query += " AND is_active = 1"
            if voucher_type:
                query += " AND voucher_type = ?"
                params.append(voucher_type.upper())
            query += " ORDER BY id ASC"
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def save_voucher_code(
        self,
        code: str,
        discount_desc: str,
        apply_url: str = "",
        category_filter: str = "ALL",
        voucher_type: str = "MANUAL",
        min_order: float = 0
    ) -> int:
        """Thêm hoặc cập nhật một mã voucher nhập tay"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                INSERT INTO voucher_codes (code, discount_desc, apply_url, category_filter, voucher_type, min_order, is_active)
                VALUES (?, ?, ?, ?, ?, ?, 1)
            """, (code.strip(), discount_desc.strip(), apply_url.strip(), category_filter.strip(), voucher_type.upper(), min_order))
            conn.commit()
            return cursor.lastrowid

    def delete_voucher_code(self, voucher_id: int) -> bool:
        """Xóa một mã voucher"""
        with self.get_connection() as conn:
            conn.execute("DELETE FROM voucher_codes WHERE id = ?", (voucher_id,))
            conn.commit()
            return True

    def get_campaign_links(self) -> Dict[str, str]:
        """Lấy danh sách các link chiến dịch (ví voucher, banner 1, banner 2, deal 99k...)"""
        default_links = {
            "wallet_url": "https://s.shopee.vn/1LPJSANV7v",
            "banner_1_url": "https://s.shopee.vn/6q0WqKvmkf",
            "banner_2_url": "https://s.shopee.vn/7AdjQWuTmi",
            "flat_deal_url": "https://s.shopee.vn/5q8Qf8NVyC"
        }
        with self.get_connection() as conn:
            rows = conn.execute("SELECT key_name, link_url FROM campaign_links").fetchall()
            db_links = {r[0]: r[1] for r in rows}
            default_links.update(db_links)
            return default_links

    def save_campaign_link(self, key_name: str, link_url: str, title: str = "") -> bool:
        """Lưu hoặc cập nhật một link chiến dịch"""
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO campaign_links (key_name, link_url, title, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key_name) DO UPDATE SET
                    link_url = excluded.link_url,
                    title = COALESCE(excluded.title, campaign_links.title),
                    updated_at = CURRENT_TIMESTAMP
            """, (key_name, link_url, title))
            conn.commit()
            return True

    def seed_default_voucher_campaign(self) -> int:
        """Nạp sẵn bộ mã giảm giá và link chiến dịch thực chiến mẫu"""
        with self.get_connection() as conn:
            default_links = {
                "wallet_url": "https://s.shopee.vn/1LPJSANV7v",
                "banner_1_url": "https://s.shopee.vn/6q0WqKvmkf",
                "banner_2_url": "https://s.shopee.vn/7AdjQWuTmi",
                "flat_deal_url": "https://s.shopee.vn/5q8Qf8NVyC"
            }
            for k, u in default_links.items():
                conn.execute("""
                    INSERT INTO campaign_links (key_name, link_url, title, updated_at)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(key_name) DO UPDATE SET link_url = excluded.link_url, updated_at = CURRENT_TIMESTAMP
                """, (k, u, k))

            existing = conn.execute("SELECT COUNT(*) FROM voucher_codes").fetchone()[0]
            if existing > 0:
                return existing

            demo_vouchers = [
                ("HSBACKTOSCHOOL2509", "giảm 100k từ 129k (lọc)", "", "MANUAL", 129000),
                ("AFFNGAG", "giảm 79k/299k", "https://s.shopee.vn/6AlHwAbTBb", "MANUAL", 299000),
                ("AFFNGAY", "giảm 69k/229k", "https://s.shopee.vn/9fLA6bna5t", "MANUAL", 229000),
                ("AFFRO", "giảm 60k/209k", "https://s.shopee.vn/LnUzSo3pE", "MANUAL", 209000),
                ("AFFGAP", "giảm 50k/169k", "https://s.shopee.vn/qjlaO8hqB", "MANUAL", 169000),
                ("AFFMOG", "giảm 25k/89k", "https://s.shopee.vn/5q8RXc1AWY", "MANUAL", 89000),
                ("AFFRUC", "giảm 39k/139k", "https://s.shopee.vn/8AWMJuJZtc", "MANUAL", 139000),
                ("AFFTRAI", "giảm 20k/89k", "https://s.shopee.vn/50ZKY62yVV", "MANUAL", 89000),
                ("AFFTOAN", "giảm 19k/65k", "https://s.shopee.vn/3VkWlLab0d", "MANUAL", 65000),
                ("AFFQA", "giảm 89k/289k", "https://s.shopee.vn/60Rrjww0wA", "MANUAL", 289000),
                ("AFFDEBUTSEP2, AFFDEBUTSEP3, AFFDEBUTSEP4, AFFDEBUTSEP5", "giảm 25% max 200k đơn từ 100k", "", "MANUAL", 100000),
                ("25% 3Tr", "Mã 25% tối đa 3 Triệu", "https://s.shopee.vn/5LCAq6w5Uc", "BIG_PERCENT", 0),
                ("25% 2.5Tr", "Mã 25% tối đa 2.5 Triệu", "https://s.shopee.vn/5VVb2PvS9f", "BIG_PERCENT", 0),
            ]

            count = 0
            for code, desc, url, vtype, min_ord in demo_vouchers:
                conn.execute("""
                    INSERT INTO voucher_codes (code, discount_desc, apply_url, voucher_type, min_order, is_active)
                    VALUES (?, ?, ?, ?, ?, 1)
                """, (code, desc, url, vtype, min_ord))
                count += 1
            conn.commit()
            return count

    def get_system_setting(self, key: str, default: str = "") -> str:
        """Lấy giá trị cấu hình hệ thống từ CSDL"""
        try:
            with self.get_connection() as conn:
                row = conn.execute("SELECT value FROM system_settings WHERE key = ?", (key,)).fetchone()
                return str(row["value"]) if row else default
        except Exception:
            return default

    def set_system_setting(self, key: str, value: str):
        """Lưu hoặc cập nhật giá trị cấu hình hệ thống vào CSDL"""
        try:
            with self.get_connection() as conn:
                conn.execute("""
                    INSERT INTO system_settings (key, value, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(key) DO UPDATE SET
                        value = excluded.value,
                        updated_at = CURRENT_TIMESTAMP
                """, (key, str(value)))
                conn.commit()
        except Exception as e:
            print(f"Lỗi lưu system setting {key}: {e}")
