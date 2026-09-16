import sqlite3
import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

from config.settings import DB_PATH

class DatabaseManager:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = str(db_path)
        self.init_db()

    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        """Khởi tạo các bảng SQLite lưu trữ dữ liệu"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # 1. Bảng lưu danh mục
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS categories (
                    cat_id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    parent_id INTEGER,
                    is_active INTEGER DEFAULT 1,
                    last_scanned_at TIMESTAMP
                )
            """)

            # 2. Bảng lưu các Deal hot đã quét
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS deals (
                    item_id TEXT PRIMARY KEY,
                    cat_id INTEGER,
                    category_name TEXT,
                    name TEXT NOT NULL,
                    price_original REAL,
                    price_sale REAL,
                    discount_percent INTEGER,
                    rating_star REAL,
                    historical_sold INTEGER,
                    deal_score REAL,
                    item_url TEXT,
                    aff_url TEXT,
                    image_url TEXT,
                    created_date DATE,
                    FOREIGN KEY (cat_id) REFERENCES categories (cat_id)
                )
            """)

            # 3. Bảng quản lý Group Facebook
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS fb_groups (
                    group_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    url TEXT NOT NULL,
                    category_name TEXT,
                    members_count INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'DISCOVERED', -- DISCOVERED, PENDING, APPROVED, REJECTED
                    join_requested_at TIMESTAMP,
                    approved_at TIMESTAMP,
                    last_posted_at TIMESTAMP
                )
            """)

            # 4. Bảng lịch sử đăng bài
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS post_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target_type TEXT, -- 'TELEGRAM' hoặc 'FB_GROUP'
                    target_id TEXT,
                    deal_id TEXT,
                    posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    content TEXT,
                    status TEXT DEFAULT 'SUCCESS',
                    FOREIGN KEY (deal_id) REFERENCES deals (item_id)
                )
            """)
            conn.commit()

    # --- Category Operations ---
    def save_category(self, cat_id: int, name: str, parent_id: Optional[int] = None):
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
        with self.get_connection() as conn:
            rows = conn.execute("SELECT * FROM categories WHERE is_active = 1").fetchall()
            return [dict(r) for r in rows]

    # --- Deal Operations ---
    def save_deal(self, deal: Dict):
        today = datetime.now().strftime("%Y-%m-%d")
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO deals (
                    item_id, cat_id, category_name, name, price_original,
                    price_sale, discount_percent, rating_star, historical_sold,
                    deal_score, item_url, aff_url, image_url, created_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(item_id) DO UPDATE SET
                    price_sale = excluded.price_sale,
                    discount_percent = excluded.discount_percent,
                    deal_score = excluded.deal_score,
                    created_date = excluded.created_date
            """, (
                str(deal['item_id']), deal.get('cat_id'), deal.get('category_name'),
                deal['name'], deal.get('price_original'), deal.get('price_sale'),
                deal.get('discount_percent'), deal.get('rating_star'), deal.get('historical_sold'),
                deal.get('deal_score'), deal.get('item_url'), deal.get('aff_url'),
                deal.get('image_url'), today
            ))
            conn.commit()

    def get_today_top_deals(self, limit_per_category: int = 3) -> Dict[str, List[Dict]]:
        today = datetime.now().strftime("%Y-%m-%d")
        deals_by_cat = {}
        with self.get_connection() as conn:
            rows = conn.execute("""
                SELECT * FROM deals
                WHERE created_date = ?
                ORDER BY deal_score DESC
            """, (today,)).fetchall()
            
            for row in rows:
                deal = dict(row)
                cat = deal['category_name'] or "Khác"
                if cat not in deals_by_cat:
                    deals_by_cat[cat] = []
                if len(deals_by_cat[cat]) < limit_per_category:
                    deals_by_cat[cat].append(deal)
        return deals_by_cat

    # --- Group Operations ---
    def save_group(self, group_id: str, name: str, url: str, category_name: str, members: int):
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO fb_groups (group_id, name, url, category_name, members_count)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(group_id) DO NOTHING
            """, (group_id, name, url, category_name, members))
            conn.commit()

    def get_groups_by_status(self, status: str) -> List[Dict]:
        with self.get_connection() as conn:
            rows = conn.execute("SELECT * FROM fb_groups WHERE status = ?", (status,)).fetchall()
            return [dict(r) for r in rows]

    def update_group_status(self, group_id: str, status: str):
        with self.get_connection() as conn:
            conn.execute("""
                UPDATE fb_groups SET status = ? WHERE group_id = ?
            """, (status, group_id))
            conn.commit()

    # --- Clean-up Operations ---
    def clear_deals(self):
        """Xóa toàn bộ sản phẩm deal đã lưu trữ"""
        with self.get_connection() as conn:
            conn.execute("DELETE FROM post_history")
            conn.execute("DELETE FROM deals")
            conn.commit()

    def clear_groups(self):
        """Xóa toàn bộ nhóm Facebook đã dò tìm"""
        with self.get_connection() as conn:
            conn.execute("DELETE FROM fb_groups")
            conn.commit()

    def reset_all_data(self, keep_categories: bool = True):
        """Xóa sạch dữ liệu sản phẩm, nhóm ảo và lịch sử"""
        with self.get_connection() as conn:
            conn.execute("DELETE FROM post_history")
            conn.execute("DELETE FROM deals")
            conn.execute("DELETE FROM fb_groups")
            if not keep_categories:
                conn.execute("DELETE FROM categories")
            conn.commit()
            conn.execute("VACUUM")
