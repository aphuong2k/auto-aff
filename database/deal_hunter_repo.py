"""
Deal Hunter & Telegram Scanner Repository
=========================================
Quản lý cơ sở dữ liệu chuyên biệt cho tính năng "Quét & Săn Deal":
- Mục tiêu nhóm Telegram (telegram_scan_targets)
- Phiên quét & săn deal (deal_hunt_sessions)
- Cụm sản phẩm nhận diện gom nhóm & giá tham chiếu (scanned_product_clusters)
- Danh sách deal săn được (hunted_deals)
- Lịch sử biến động giá theo thời gian (hunt_price_history)
"""

import json
import logging
from typing import List, Dict, Optional, Any
from datetime import datetime
from database.connection import BaseRepository

logger = logging.getLogger("DealHunterRepository")


class DealHunterRepository(BaseRepository):
    """Repository quản lý toàn bộ dữ liệu Quét & Săn Deal đa kênh đa nguồn"""

    # --- 1. Quản lý Mục tiêu Telegram (telegram_scan_targets) ---

    def get_telegram_scan_targets(self, only_active: bool = False) -> List[Dict]:
        """Lấy danh sách các nhóm/kênh Telegram được cấu hình để quét deal"""
        query = "SELECT id, name, target_type, identifier, is_active, last_scanned_at, created_at FROM telegram_scan_targets"
        if only_active:
            query += " WHERE is_active = 1"
        query += " ORDER BY id DESC"

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            rows = cursor.fetchall()
            return [
                {
                    "id": r[0],
                    "name": r[1],
                    "target_type": r[2],
                    "identifier": r[3],
                    "is_active": bool(r[4]),
                    "last_scanned_at": r[5],
                    "created_at": r[6],
                }
                for r in rows
            ]

    def save_telegram_scan_target(self, name: str, identifier: str, target_type: str = "CHANNEL", is_active: int = 1) -> int:
        """Thêm hoặc cập nhật mục tiêu nhóm Telegram"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO telegram_scan_targets (name, identifier, target_type, is_active)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(identifier) DO UPDATE SET
                    name = excluded.name,
                    target_type = excluded.target_type,
                    is_active = excluded.is_active
                """,
                (name.strip(), identifier.strip(), target_type, is_active)
            )
            conn.commit()
            return cursor.lastrowid

    def delete_telegram_scan_target(self, target_id: int) -> bool:
        """Xóa mục tiêu Telegram theo ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM telegram_scan_targets WHERE id = ?", (target_id,))
            conn.commit()
            return cursor.rowcount > 0

    def update_telegram_target_scanned(self, identifier: str):
        """Cập nhật thời điểm vừa quét gần nhất của nhóm Telegram"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE telegram_scan_targets SET last_scanned_at = CURRENT_TIMESTAMP WHERE identifier = ?",
                (identifier,)
            )
            conn.commit()

    # --- 1.1 Quản lý Mục tiêu Group Facebook (facebook_scan_targets) ---

    def get_facebook_scan_targets(self, only_active: bool = False) -> List[Dict]:
        """Lấy danh sách các nhóm Facebook được cấu hình để quét tin rao bán lấy giá"""
        query = "SELECT id, name, group_url, group_id, category_name, is_active, last_scanned_at, created_at FROM facebook_scan_targets"
        if only_active:
            query += " WHERE is_active = 1"
        query += " ORDER BY id DESC"

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            rows = cursor.fetchall()
            return [
                {
                    "id": r[0],
                    "name": r[1],
                    "group_url": r[2],
                    "group_id": r[3] or "",
                    "category_name": r[4] or "Đa ngành",
                    "is_active": bool(r[5]),
                    "last_scanned_at": r[6],
                    "created_at": r[7],
                }
                for r in rows
            ]

    def save_facebook_scan_target(
        self,
        name: str,
        group_url: str,
        group_id: str = "",
        category_name: str = "Đa ngành",
        is_active: int = 1
    ) -> int:
        """Thêm hoặc cập nhật nhóm Facebook mục tiêu để quét giá"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO facebook_scan_targets (name, group_url, group_id, category_name, is_active)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(group_url) DO UPDATE SET
                    name = excluded.name,
                    group_id = excluded.group_id,
                    category_name = excluded.category_name,
                    is_active = excluded.is_active
                """,
                (name.strip(), group_url.strip(), group_id.strip(), category_name.strip(), is_active)
            )
            conn.commit()
            return cursor.lastrowid

    def delete_facebook_scan_target(self, target_id: int) -> bool:
        """Xóa nhóm Facebook mục tiêu theo ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM facebook_scan_targets WHERE id = ?", (target_id,))
            conn.commit()
            return cursor.rowcount > 0

    def update_facebook_target_scanned(self, group_url: str):
        """Cập nhật thời gian quét bài gần nhất của nhóm Facebook"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE facebook_scan_targets SET last_scanned_at = CURRENT_TIMESTAMP WHERE group_url = ?",
                (group_url,)
            )
            conn.commit()

    # --- 2. Quản lý Phiên Săn Deal (deal_hunt_sessions) ---

    def create_hunt_session(
        self,
        mode: str,
        source_platform: str,
        input_query: str,
        session_name: Optional[str] = None,
        auto_send_telegram: int = 0,
        min_discount_percent: int = 5
    ) -> int:
        """Tạo một phiên săn deal mới"""
        name = session_name or f"Phiên {mode} - {source_platform} ({datetime.now().strftime('%H:%M %d/%m')})"
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO deal_hunt_sessions (
                    session_name, mode, source_platform, input_query,
                    auto_send_telegram, min_discount_percent, status
                ) VALUES (?, ?, ?, ?, ?, ?, 'RUNNING')
                """,
                (name, mode, source_platform, input_query, auto_send_telegram, min_discount_percent)
            )
            conn.commit()
            return cursor.lastrowid

    def update_hunt_session(
        self,
        session_id: int,
        status: str = "COMPLETED",
        total_clusters: int = 0,
        total_deals_found: int = 0,
        better_deals_count: int = 0
    ):
        """Cập nhật trạng thái và kết quả của phiên săn deal"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE deal_hunt_sessions
                SET status = ?,
                    total_clusters = ?,
                    total_deals_found = ?,
                    better_deals_count = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (status, total_clusters, total_deals_found, better_deals_count, session_id)
            )
            conn.commit()

    def get_hunt_sessions(self, limit: int = 20) -> List[Dict]:
        """Lấy danh sách các phiên săn deal gần đây"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, session_name, mode, source_platform, input_query,
                       auto_send_telegram, min_discount_percent, status,
                       total_clusters, total_deals_found, better_deals_count,
                       created_at, updated_at
                FROM deal_hunt_sessions
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,)
            )
            rows = cursor.fetchall()
            return [
                {
                    "id": r[0],
                    "session_name": r[1],
                    "mode": r[2],
                    "source_platform": r[3],
                    "input_query": r[4],
                    "auto_send_telegram": bool(r[5]),
                    "min_discount_percent": r[6],
                    "status": r[7],
                    "total_clusters": r[8],
                    "total_deals_found": r[9],
                    "better_deals_count": r[10],
                    "created_at": r[11],
                    "updated_at": r[12],
                }
                for r in rows
            ]

    def get_hunt_session_by_id(self, session_id: int) -> Optional[Dict]:
        """Lấy chi tiết 1 phiên theo ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, session_name, mode, source_platform, input_query,
                       auto_send_telegram, min_discount_percent, status,
                       total_clusters, total_deals_found, better_deals_count,
                       created_at, updated_at
                FROM deal_hunt_sessions
                WHERE id = ?
                """,
                (session_id,)
            )
            r = cursor.fetchone()
            if not r:
                return None
            return {
                "id": r[0],
                "session_name": r[1],
                "mode": r[2],
                "source_platform": r[3],
                "input_query": r[4],
                "auto_send_telegram": bool(r[5]),
                "min_discount_percent": r[6],
                "status": r[7],
                "total_clusters": r[8],
                "total_deals_found": r[9],
                "better_deals_count": r[10],
                "created_at": r[11],
                "updated_at": r[12],
            }

    # --- 3. Quản lý Cụm Sản Phẩm (scanned_product_clusters) ---

    def save_product_cluster(self, cluster: Dict) -> int:
        """Lưu hoặc cập nhật cụm sản phẩm và tính toán giá tham chiếu"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO scanned_product_clusters (
                    session_id, cluster_key, product_name, category_name,
                    reference_price, avg_price, min_price, max_price,
                    sample_count, source_samples, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (
                    cluster.get("session_id"),
                    cluster.get("cluster_key"),
                    cluster.get("product_name"),
                    cluster.get("category_name", "Đa ngành"),
                    float(cluster.get("reference_price", 0)),
                    float(cluster.get("avg_price", 0)),
                    float(cluster.get("min_price", 0)),
                    float(cluster.get("max_price", 0)),
                    int(cluster.get("sample_count", 1)),
                    json.dumps(cluster.get("source_samples", []), ensure_ascii=False)
                )
            )
            conn.commit()
            return cursor.lastrowid

    def get_clusters_by_session(self, session_id: int) -> List[Dict]:
        """Lấy danh sách các cụm sản phẩm của một phiên"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, session_id, cluster_key, product_name, category_name,
                       reference_price, avg_price, min_price, max_price,
                       sample_count, source_samples, created_at, updated_at
                FROM scanned_product_clusters
                WHERE session_id = ?
                ORDER BY sample_count DESC, id ASC
                """,
                (session_id,)
            )
            rows = cursor.fetchall()
            clusters = []
            for r in rows:
                samples = []
                try:
                    samples = json.loads(r[10]) if r[10] else []
                except Exception:
                    pass
                clusters.append({
                    "id": r[0],
                    "session_id": r[1],
                    "cluster_key": r[2],
                    "product_name": r[3],
                    "category_name": r[4],
                    "reference_price": r[5],
                    "avg_price": r[6],
                    "min_price": r[7],
                    "max_price": r[8],
                    "sample_count": r[9],
                    "source_samples": samples,
                    "created_at": r[11],
                    "updated_at": r[12],
                })
            return clusters

    # --- 4. Quản lý Deal Săn Được (hunted_deals) ---

    def save_hunted_deal(self, deal: Dict) -> int:
        """Lưu deal tìm thấy từ nguồn đã chọn (Tmall / LazMall / Lazada / Shopee)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO hunted_deals (
                    session_id, cluster_id, platform, item_id, name,
                    reference_price, sale_price, original_price,
                    price_diff, savings_percent, is_better_deal,
                    rating_star, historical_sold, item_url, aff_url,
                    image_url, seller_name, location, status,
                    posted_to_telegram, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (
                    deal.get("session_id"),
                    deal.get("cluster_id"),
                    deal.get("platform", "LAZADA"),
                    str(deal.get("item_id")),
                    deal.get("name"),
                    float(deal.get("reference_price", 0)),
                    float(deal.get("sale_price", 0)),
                    float(deal.get("original_price", 0) or deal.get("sale_price", 0)),
                    float(deal.get("price_diff", 0)),
                    float(deal.get("savings_percent", 0)),
                    1 if deal.get("is_better_deal") else 0,
                    float(deal.get("rating_star", 5.0)),
                    int(deal.get("historical_sold", 0)),
                    deal.get("item_url", ""),
                    deal.get("aff_url", deal.get("item_url", "")),
                    deal.get("image_url", ""),
                    deal.get("seller_name", ""),
                    deal.get("location", ""),
                    deal.get("status", "FOUND"),
                    1 if deal.get("posted_to_telegram") else 0
                )
            )
            conn.commit()
            return cursor.lastrowid

    def get_deals_by_session(
        self,
        session_id: int,
        only_better_deals: bool = False,
        platform_filter: Optional[str] = None
    ) -> List[Dict]:
        """
        Lấy danh sách deal săn được trong phiên:
        - ƯU TIÊN HÀNG ĐẦU: Deal có giá thấp hơn giá tham chiếu (is_better_deal DESC)
        - Tiếp theo: Chênh lệch giảm giá lớn nhất (price_diff DESC)
        """
        query = """
            SELECT id, session_id, cluster_id, platform, item_id, name,
                   reference_price, sale_price, original_price,
                   price_diff, savings_percent, is_better_deal,
                   rating_star, historical_sold, item_url, aff_url,
                   image_url, seller_name, location, status,
                   posted_to_telegram, posted_telegram_at, created_at
            FROM hunted_deals
            WHERE session_id = ?
        """
        params: List[Any] = [session_id]

        if only_better_deals:
            query += " AND is_better_deal = 1"
        if platform_filter and platform_filter.upper() != "ALL":
            query += " AND platform = ?"
            params.append(platform_filter.upper())

        query += " ORDER BY is_better_deal DESC, price_diff DESC, savings_percent DESC, id ASC"

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()
            return [
                {
                    "id": r[0],
                    "session_id": r[1],
                    "cluster_id": r[2],
                    "platform": r[3],
                    "item_id": r[4],
                    "name": r[5],
                    "reference_price": r[6],
                    "sale_price": r[7],
                    "original_price": r[8],
                    "price_diff": r[9],
                    "savings_percent": r[10],
                    "is_better_deal": bool(r[11]),
                    "rating_star": r[12],
                    "historical_sold": r[13],
                    "item_url": r[14],
                    "aff_url": r[15] or r[14],
                    "image_url": r[16],
                    "seller_name": r[17],
                    "location": r[18],
                    "status": r[19],
                    "posted_to_telegram": bool(r[20]),
                    "posted_telegram_at": r[21],
                    "created_at": r[22],
                }
                for r in rows
            ]

    def mark_deal_posted_telegram(self, deal_id: int):
        """Đánh dấu deal đã gửi vào Telegram"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE hunted_deals
                SET posted_to_telegram = 1,
                    posted_telegram_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (deal_id,)
            )
            conn.commit()

    def get_hunted_deal_by_id(self, deal_id: int) -> Optional[Dict]:
        """Lấy 1 deal theo ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, session_id, cluster_id, platform, item_id, name,
                       reference_price, sale_price, original_price,
                       price_diff, savings_percent, is_better_deal,
                       rating_star, historical_sold, item_url, aff_url,
                       image_url, seller_name, location, status,
                       posted_to_telegram, posted_telegram_at, created_at
                FROM hunted_deals
                WHERE id = ?
                """,
                (deal_id,)
            )
            r = cursor.fetchone()
            if not r:
                return None
            return {
                "id": r[0],
                "session_id": r[1],
                "cluster_id": r[2],
                "platform": r[3],
                "item_id": r[4],
                "name": r[5],
                "reference_price": r[6],
                "sale_price": r[7],
                "original_price": r[8],
                "price_diff": r[9],
                "savings_percent": r[10],
                "is_better_deal": bool(r[11]),
                "rating_star": r[12],
                "historical_sold": r[13],
                "item_url": r[14],
                "aff_url": r[15] or r[14],
                "image_url": r[16],
                "seller_name": r[17],
                "location": r[18],
                "status": r[19],
                "posted_to_telegram": bool(r[20]),
                "posted_telegram_at": r[21],
                "created_at": r[22],
            }

    # --- 5. Quản lý Lịch Sử Giá (hunt_price_history) ---

    def record_hunt_price_history(
        self,
        cluster_key: str,
        product_name: str,
        platform: str,
        item_id: str,
        price: float,
        reference_price: float
    ):
        """Ghi nhận một điểm dữ liệu lịch sử giá"""
        diff = reference_price - price
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO hunt_price_history (
                    cluster_key, product_name, platform, item_id,
                    price, reference_price, price_diff, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (cluster_key, product_name, platform, item_id, price, reference_price, diff)
            )
            conn.commit()

    def get_hunt_price_history_by_cluster(self, cluster_key: str, limit: int = 50) -> List[Dict]:
        """
        Lấy toàn bộ lịch sử giá theo thời gian của một cụm/sản phẩm
        (Đảm bảo giữ nguyên các mốc quét cũ khi người dùng bấm Quét Lại)
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, cluster_key, product_name, platform, item_id,
                       price, reference_price, price_diff, recorded_at
                FROM hunt_price_history
                WHERE cluster_key = ?
                ORDER BY recorded_at ASC, id ASC
                LIMIT ?
                """,
                (cluster_key, limit)
            )
            rows = cursor.fetchall()
            return [
                {
                    "id": r[0],
                    "cluster_key": r[1],
                    "product_name": r[2],
                    "platform": r[3],
                    "item_id": r[4],
                    "price": r[5],
                    "reference_price": r[6],
                    "price_diff": r[7],
                    "recorded_at": r[8],
                }
                for r in rows
            ]
