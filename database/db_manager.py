import sqlite3
import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Any

from config.settings import DB_PATH

class DatabaseManager:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = str(db_path)
        self.init_db()

    def get_connection(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
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

            # 5. Bảng từ khóa tự học từ tên nhóm Facebook
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS learned_keywords (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category_name TEXT NOT NULL,
                    keyword TEXT NOT NULL,
                    source_group_name TEXT,
                    frequency INTEGER DEFAULT 1,
                    last_used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(category_name, keyword)
                )
            """)

            # 6. Bảng lưu trữ chương trình khuyến mại, mã giảm giá và khung giờ sale
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sale_promotions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    campaign_type TEXT DEFAULT 'FLASH_SALE', -- 'FLASH_SALE', 'DOUBLE_DAY', 'PAYDAY', 'MID_MONTH'
                    slot_time TEXT, -- '00:00', '12:00', '21:00' hoặc 'ALL_DAY'
                    banner_url TEXT,
                    aff_url TEXT,
                    description TEXT,
                    vouchers_json TEXT, -- Danh sách mã giảm giá dạng JSON
                    is_active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 7. Bảng ghi nhận lịch sử các lần đã bắn bài nhắc giờ sale (chống spam)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sale_reminder_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    slot_time TEXT NOT NULL,
                    campaign_date DATE NOT NULL,
                    target TEXT DEFAULT 'TELEGRAM',
                    content TEXT,
                    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(slot_time, campaign_date, target)
                )
            """)

            # 8. Bảng lịch sử giá sản phẩm (Theo dõi biến động giá & phát hiện giảm giá ảo)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS price_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id TEXT NOT NULL,
                    price REAL NOT NULL,
                    original_price REAL,
                    discount_percent INTEGER,
                    recorded_date DATE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(item_id, recorded_date)
                )
            """)

            # 9. Bảng ghi nhận click & Sub-ID Analytics (Theo dõi hiệu quả kênh chuyển đổi)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS click_analytics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id TEXT NOT NULL,
                    channel TEXT DEFAULT 'DIRECT',
                    sub_id TEXT,
                    ip TEXT,
                    referer TEXT,
                    user_agent TEXT,
                    clicked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 10. Bảng lịch sử Seeding bình luận dạo trên Facebook Group
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS comment_seeding_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    comment_text TEXT,
                    target_post_url TEXT,
                    posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'SUCCESS'
                )
            """)

            # 11. Bảng lưu trữ chi tiết các bài viết và comment đã đăng kèm link Facebook để kiểm tra
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS posted_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT NOT NULL, -- 'POST' hoặc 'COMMENT'
                    group_name TEXT,
                    group_url TEXT,
                    target_url TEXT, -- Link trực tiếp bài viết hoặc comment trên Facebook để bấm vào check
                    item_id TEXT,
                    item_name TEXT,
                    content_snippet TEXT,
                    image_path TEXT,
                    status TEXT DEFAULT 'SUCCESS',
                    posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 12. Bảng quản lý hoa hồng & đối soát doanh thu đa sàn (Shopee & Lazada)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS commissions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform TEXT NOT NULL DEFAULT 'SHOPEE', -- 'SHOPEE' hoặc 'LAZADA'
                    order_id TEXT NOT NULL UNIQUE,
                    item_id TEXT,
                    item_name TEXT,
                    channel TEXT DEFAULT 'DIRECT', -- 'TELEGRAM', 'FB_GROUP', 'WEB', 'DIRECT'
                    sub_id TEXT,
                    order_value REAL DEFAULT 0,
                    commission_amount REAL NOT NULL,
                    status TEXT DEFAULT 'PENDING', -- 'PENDING', 'APPROVED', 'CANCELLED', 'PAID'
                    purchase_time TIMESTAMP,
                    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 13. Bảng đăng ký nhận tin Flash Sale / Deal hời (Retention & Web Push / Email alerts)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS subscribers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE,
                    telegram_id TEXT,
                    platform_preference TEXT DEFAULT 'ALL', -- 'ALL', 'SHOPEE', 'LAZADA'
                    category_preference TEXT DEFAULT 'ALL',
                    min_discount INTEGER DEFAULT 30,
                    is_active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Tự động migrate thêm các cột mở rộng vào bảng deals
            cursor.execute("PRAGMA table_info(deals)")
            existing_cols = [row[1] for row in cursor.fetchall()]
            if "local_image" not in existing_cols:
                cursor.execute("ALTER TABLE deals ADD COLUMN local_image TEXT")
            if "price_badge" not in existing_cols:
                cursor.execute("ALTER TABLE deals ADD COLUMN price_badge TEXT")
            if "platform" not in existing_cols:
                cursor.execute("ALTER TABLE deals ADD COLUMN platform TEXT DEFAULT 'SHOPEE'")
            if "is_stale" not in existing_cols:
                cursor.execute("ALTER TABLE deals ADD COLUMN is_stale INTEGER DEFAULT 0")
            if "last_checked_at" not in existing_cols:
                cursor.execute("ALTER TABLE deals ADD COLUMN last_checked_at TIMESTAMP")
            if "commission_rate" not in existing_cols:
                cursor.execute("ALTER TABLE deals ADD COLUMN commission_rate REAL DEFAULT 5.0")
            if "is_extra" not in existing_cols:
                cursor.execute("ALTER TABLE deals ADD COLUMN is_extra INTEGER DEFAULT 0")

            # Tự động migrate thêm cột platform vào click_analytics
            cursor.execute("PRAGMA table_info(click_analytics)")
            click_cols = [row[1] for row in cursor.fetchall()]
            if "platform" not in click_cols:
                cursor.execute("ALTER TABLE click_analytics ADD COLUMN platform TEXT DEFAULT 'SHOPEE'")

            # Tự động migrate thêm cột group_type vào bảng fb_groups nếu chưa có
            cursor.execute("PRAGMA table_info(fb_groups)")
            fb_cols = [row[1] for row in cursor.fetchall()]
            if "group_type" not in fb_cols:
                cursor.execute("ALTER TABLE fb_groups ADD COLUMN group_type TEXT DEFAULT 'NICHE'")

            # 14. Bảng lưu trữ mã giảm giá nhập tay (Voucher Codes / KOL Vouchers)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS voucher_codes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT NOT NULL,
                    discount_desc TEXT NOT NULL,
                    apply_url TEXT,
                    min_order REAL DEFAULT 0,
                    category_filter TEXT DEFAULT 'ALL',
                    voucher_type TEXT DEFAULT 'MANUAL', -- 'MANUAL', 'BIG_PERCENT', 'FLAT_DEAL'
                    is_active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 15. Bảng cấu hình link chiến dịch (Ví voucher, Banner 1, Banner 2, Deal 99K...)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS campaign_links (
                    key_name TEXT PRIMARY KEY,
                    link_url TEXT NOT NULL,
                    title TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 16. Bảng lưu trữ cấu hình hệ thống & lịch chạy (Settings Key-Value)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS system_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 17. Bảng ghi nhận báo cáo toàn trình các phiên chạy (Tự động hoặc thủ công từng bước)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS workflow_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_type TEXT NOT NULL,          -- 'AUTO_SCHEDULE', 'MANUAL_ALL', 'MANUAL_STEP'
                    step_name TEXT NOT NULL,         -- 'ALL', 'CRAWL_DEALS', 'GENERATE_MEDIA', 'TELEGRAM_PUB', 'FB_GROUP_POST', 'SEEDING', 'FRESHNESS'
                    status TEXT DEFAULT 'SUCCESS',   -- 'SUCCESS', 'RUNNING', 'ERROR', 'PARTIAL'
                    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    ended_at TIMESTAMP,
                    duration_seconds REAL DEFAULT 0,
                    deals_scanned INTEGER DEFAULT 0,
                    deals_saved INTEGER DEFAULT 0,
                    banners_created INTEGER DEFAULT 0,
                    telegram_posts INTEGER DEFAULT 0,
                    fb_posts INTEGER DEFAULT 0,
                    seeding_comments INTEGER DEFAULT 0,
                    summary_text TEXT,
                    error_message TEXT
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

    @staticmethod
    def classify_product_niche(name: str, current_cat: str = "") -> str:
        """Phân loại chính xác ngành hàng dựa trên tên sản phẩm thực tế, tránh râu ông nọ cắm cằm bà kia"""
        import unicodedata
        if not name:
            return current_cat or "Săn Deal Tổng Hợp"
        nl = unicodedata.normalize('NFC', name.lower())

        # 1. Điện tử / Công nghệ / Điện thoại / Phụ kiện
        if any(k in nl for k in ['iphone', 'cáp', 'sạc', 'ốp lưng', 'cường lực', 'tai nghe', 'bluetooth', 'laptop', 'chuột', 'bàn phím', 'baseus', 'anker', 'xiaomi', 'củ sạc', 'sạc nhanh', 'type c', 'usb', 'ipad', 'màn hình']):
            return 'Thiết Bị Điện Tử'

        # 2. Mẹ & Bé
        if any(k in nl for k in ['xe đẩy', 'sữa', 'bỉm', 'tã', 'cho bé', 'sơ sinh', 'trẻ em', 'bình sữa']):
            return 'Mẹ & Bé'

        # 3. Nhà cửa & Đời sống / Gia dụng
        if any(k in nl for k in ['nồi', 'chảo', 'bếp', 'ấm siêu tốc', 'khăn tắm', 'ga giường', 'gối', 'hộp đựng', 'kệ', 'chổi', 'lau nhà', 'sunhouse', 'quạt', 'bàn ủi']):
            return 'Nhà Cửa & Đời Sống'

        # 4. Thời trang nam
        if any(k in nl for k in ['nam', 'polo', 'sơ mi', 'quần âu', 'áo khoác nam', 'quần jean nam', 'cạo râu', 'boxer', 'krik', 'capman', 'giữ nhiệt']):
            if not any(k in nl for k in ['váy', 'đầm', 'nữ', 'croptop', 'chân váy', 'búp bê', 'cao gót', 'kem', 'chống nắng']):
                return 'Thời Trang Nam'

        # 5. Thời trang nữ & Mỹ phẩm làm đẹp
        if any(k in nl for k in ['nữ', 'váy', 'đầm', 'chân váy', 'croptop', 'son', 'kem chống nắng', 'dưỡng ẩm', 'd\'alba', 'búp bê', 'cao gót', 'áo hai dây', 'khăn choàng', 'kem', 'serum', 'làm đẹp', 'nước tẩy trang', 'sữa rửa mặt']):
            return 'Thời Trang Nữ'

        if current_cat in ['Thời Trang Nam', 'Thời Trang Nữ', 'Thiết Bị Điện Tử', 'Nhà Cửa & Đời Sống', 'Săn Deal Tổng Hợp']:
            return current_cat
        return 'Săn Deal Tổng Hợp'

    # --- Deal Operations ---
    def save_deal(self, deal: Dict):
        today = datetime.now().strftime("%Y-%m-%d")
        platform = (deal.get("platform") or "SHOPEE").upper()
        is_stale = 1 if deal.get("is_stale") else 0
        cat_name = self.classify_product_niche(deal.get("name", ""), deal.get("category_name", ""))
        deal["category_name"] = cat_name

        comm_rate = float(deal.get("commission_rate") or (12.0 if deal.get("is_mall") else (8.0 if deal.get("is_preferred") else 5.0)))
        is_extra = 1 if deal.get("is_extra") or comm_rate >= 8.0 else 0

        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO deals (
                    item_id, cat_id, category_name, name, price_original,
                    price_sale, discount_percent, rating_star, historical_sold,
                    deal_score, item_url, aff_url, image_url, created_date,
                    local_image, price_badge, platform, is_stale, commission_rate, is_extra, last_checked_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(item_id) DO UPDATE SET
                    category_name = excluded.category_name,
                    price_sale = excluded.price_sale,
                    discount_percent = excluded.discount_percent,
                    deal_score = excluded.deal_score,
                    created_date = excluded.created_date,
                    platform = COALESCE(excluded.platform, deals.platform),
                    local_image = COALESCE(excluded.local_image, deals.local_image),
                    price_badge = COALESCE(excluded.price_badge, deals.price_badge),
                    aff_url = COALESCE(excluded.aff_url, deals.aff_url),
                    is_stale = excluded.is_stale,
                    commission_rate = excluded.commission_rate,
                    is_extra = excluded.is_extra,
                    last_checked_at = CURRENT_TIMESTAMP
            """, (
                str(deal['item_id']), deal.get('cat_id'), cat_name,
                deal['name'], deal.get('price_original'), deal.get('price_sale'),
                deal.get('discount_percent'), deal.get('rating_star'), deal.get('historical_sold'),
                deal.get('deal_score'), deal.get('item_url'), deal.get('aff_url'),
                deal.get('image_url'), today, deal.get('local_image'), deal.get('price_badge'),
                platform, is_stale, comm_rate, is_extra
            ))
            conn.commit()

        # Tự động lưu lịch sử giá để theo dõi biến động & đáy giá
        if deal.get('price_sale'):
            try:
                self.record_price_history(
                    item_id=str(deal['item_id']),
                    price=float(deal['price_sale']),
                    original_price=float(deal.get('price_original') or deal['price_sale']),
                    discount_percent=int(deal.get('discount_percent') or 0),
                    recorded_date=today
                )
            except Exception:
                pass

    def update_deal_aff_url(self, item_id: str, aff_url: str):
        """Cập nhật link affiliate chính thức cho deal đã cào"""
        if not item_id or not aff_url:
            return
        with self.get_connection() as conn:
            conn.execute("UPDATE deals SET aff_url = ? WHERE item_id = ?", (aff_url, str(item_id)))
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

    def get_loss_leader_deals(self, limit: int = 10) -> List[Dict]:
        """Lấy danh sách các Deal Mồi 1K - Freeship 0Đ để kích hoạt cookie 7 ngày"""
        with self.get_connection() as conn:
            rows = conn.execute("""
                SELECT * FROM deals 
                WHERE price_badge = 'LOSS_LEADER_1K' OR price_sale <= 9000
                ORDER BY deal_score DESC, created_date DESC
                LIMIT ?
            """, (limit,)).fetchall()
            return [dict(r) for r in rows]

    # --- Group Operations ---
    def save_group(self, group_id: str, name: str, url: str, category_name: str, members: int, group_type: str = ""):
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
        with self.get_connection() as conn:
            rows = conn.execute("SELECT * FROM fb_groups WHERE status = ?", (status,)).fetchall()
            return [dict(r) for r in rows]

    def update_group_status(self, group_id: str, status: str):
        with self.get_connection() as conn:
            conn.execute("""
                UPDATE fb_groups SET status = ? WHERE group_id = ?
            """, (status, group_id))
            conn.commit()

    def delete_group(self, group_id: str):
        with self.get_connection() as conn:
            conn.execute("DELETE FROM fb_groups WHERE group_id = ?", (group_id,))
            conn.commit()


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

    def update_deal_media(self, item_id: str, local_image: Optional[str] = None, price_badge: Optional[str] = None):
        """Cập nhật đường dẫn ảnh đã đóng khung và huy hiệu giá cho deal"""
        with self.get_connection() as conn:
            if local_image and price_badge:
                conn.execute("UPDATE deals SET local_image = ?, price_badge = ? WHERE item_id = ?", (local_image, price_badge, str(item_id)))
            elif local_image:
                conn.execute("UPDATE deals SET local_image = ? WHERE item_id = ?", (local_image, str(item_id)))
            elif price_badge:
                conn.execute("UPDATE deals SET price_badge = ? WHERE item_id = ?", (price_badge, str(item_id)))
            conn.commit()

    def get_deal_by_id(self, item_id: str) -> Optional[Dict]:
        """Lấy thông tin chi tiết của deal theo item_id"""
        with self.get_connection() as conn:
            row = conn.execute("SELECT * FROM deals WHERE item_id = ?", (str(item_id),)).fetchone()
            return dict(row) if row else None

    # --- Price History Operations ---
    def record_price_history(self, item_id: str, price: float, original_price: Optional[float] = None, discount_percent: int = 0, recorded_date: Optional[str] = None):
        """Ghi nhận giá của sản phẩm theo ngày để theo dõi biến động & bắt giảm giá ảo"""
        recorded_date = recorded_date or datetime.now().strftime("%Y-%m-%d")
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO price_history (item_id, price, original_price, discount_percent, recorded_date)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(item_id, recorded_date) DO UPDATE SET
                    price = excluded.price,
                    original_price = excluded.original_price,
                    discount_percent = excluded.discount_percent
            """, (str(item_id), price, original_price, discount_percent, recorded_date))
            conn.commit()

    def get_price_history(self, item_id: str, limit_days: int = 30) -> List[Dict]:
        """Lấy lịch sử giá của sản phẩm trong N ngày gần nhất"""
        with self.get_connection() as conn:
            rows = conn.execute("""
                SELECT * FROM price_history
                WHERE item_id = ? AND recorded_date >= date('now', ? || ' days')
                ORDER BY recorded_date ASC
            """, (str(item_id), f"-{limit_days}")).fetchall()
            return [dict(r) for r in rows]

    # --- Click Analytics & Sub-ID Operations ---
    def log_click(self, item_id: str, channel: str = "DIRECT", sub_id: Optional[str] = None, ip: Optional[str] = None, referer: Optional[str] = None, user_agent: Optional[str] = None, platform: str = "SHOPEE"):
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

    # --- Multi-Platform Deal Operations ---
    def get_deals(
        self,
        limit: int = 50,
        platform: Optional[str] = None,
        is_stale: Optional[int] = 0,
        category_name: Optional[str] = None,
        search: Optional[str] = None,
        deal_type: Optional[str] = "ALL",
        sort_by: str = "score"
    ) -> List[Dict]:
        """Truy vấn deal linh hoạt theo Sàn (Shopee/Lazada), độ tươi, ngành hàng, loại deal (1K / Hoa hồng cao), từ khóa tìm kiếm"""
        query = "SELECT * FROM deals WHERE 1=1"
        params: List[Any] = []

        if platform and platform.upper() != "ALL":
            query += " AND platform = ?"
            params.append(platform.upper())

        if is_stale is not None:
            query += " AND is_stale = ?"
            params.append(is_stale)

        if category_name and category_name.upper() != "ALL":
            query += " AND category_name = ?"
            params.append(category_name)

        if deal_type and deal_type.upper() == "LOSS_LEADER":
            query += " AND (price_badge = 'LOSS_LEADER_1K' OR price_sale <= 15000)"
        elif deal_type and deal_type.upper() == "EXTRA":
            query += " AND (is_extra = 1 OR commission_rate >= 8.0)"

        if search:
            query += " AND (name LIKE ? OR category_name LIKE ?)"
            term = f"%{search.strip()}%"
            params.extend([term, term])

        if sort_by == "discount":
            query += " ORDER BY discount_percent DESC, deal_score DESC"
        elif sort_by == "sold":
            query += " ORDER BY historical_sold DESC, deal_score DESC"
        elif sort_by == "price_asc":
            query += " ORDER BY price_sale ASC"
        elif sort_by == "price_desc":
            query += " ORDER BY price_sale DESC"
        else:
            query += " ORDER BY created_date DESC, deal_score DESC"

        query += " LIMIT ?"
        params.append(limit)

        with self.get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def mark_deal_stale(self, item_id: str, is_stale: int = 1):
        """Đánh dấu deal đã hết hàng / hết giảm giá hoặc còn tươi"""
        with self.get_connection() as conn:
            conn.execute("""
                UPDATE deals 
                SET is_stale = ?, last_checked_at = CURRENT_TIMESTAMP 
                WHERE item_id = ?
            """, (is_stale, str(item_id)))
            conn.commit()

    # --- Commission & ROI Analytics Operations ---
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
            # Tổng quan
            total_row = conn.execute("""
                SELECT 
                    COUNT(*) as total_orders,
                    COALESCE(SUM(commission_amount), 0) as total_commission,
                    COALESCE(SUM(order_value), 0) as total_gmv,
                    COALESCE(SUM(CASE WHEN status = 'APPROVED' OR status = 'PAID' THEN commission_amount ELSE 0 END), 0) as approved_commission
                FROM commissions
            """).fetchone()

            # Theo sàn (Shopee vs Lazada)
            platform_rows = conn.execute("""
                SELECT 
                    platform,
                    COUNT(*) as orders,
                    COALESCE(SUM(commission_amount), 0) as commission,
                    COALESCE(SUM(order_value), 0) as gmv
                FROM commissions
                GROUP BY platform
            """).fetchall()

            # Theo kênh (Telegram vs Facebook vs Direct/Web)
            channel_rows = conn.execute("""
                SELECT 
                    channel,
                    COUNT(*) as orders,
                    COALESCE(SUM(commission_amount), 0) as commission
                FROM commissions
                GROUP BY channel
                ORDER BY commission DESC
            """).fetchall()

            # Tỷ lệ chuyển đổi tổng thể (Clicks -> Orders)
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

    # --- Subscribers Operations (Retention & Deal Alerts) ---
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

    # --- Comment Seeding Operations ---
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
                ORDER BY s.posted_at DESC
                LIMIT ?
            """, (limit,)).fetchall()
            return [dict(r) for r in rows]

    # --- Posted Logs Operations (Lưu vết bài viết/comment đã đăng kèm link FB để kiểm tra) ---
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
        status: str = "SUCCESS"
    ) -> int:
        """Lưu lại log bài viết hoặc comment đã đăng lên Facebook kèm link kiểm tra"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO posted_logs (type, group_name, group_url, target_url, item_id, item_name, content_snippet, image_path, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (post_type.upper(), group_name, group_url, target_url, str(item_id), item_name, content_snippet, image_path, status))
            conn.commit()
            return cursor.lastrowid

    def get_posted_logs(self, limit: int = 50, post_type: Optional[str] = None) -> List[Dict]:
        """Lấy danh sách các bài viết / comment đã đăng gần đây kèm link kiểm tra trên FB"""
        with self.get_connection() as conn:
            if post_type:
                rows = conn.execute("""
                    SELECT * FROM posted_logs 
                    WHERE type = ? 
                    ORDER BY posted_at DESC 
                    LIMIT ?
                """, (post_type.upper(), limit)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT * FROM posted_logs 
                    ORDER BY posted_at DESC 
                    LIMIT ?
                """, (limit,)).fetchall()
            return [dict(r) for r in rows]

    def delete_posted_log(self, log_id: int) -> bool:
        """Xóa một bản ghi log bài đăng"""
        with self.get_connection() as conn:
            conn.execute("DELETE FROM posted_logs WHERE id = ?", (log_id,))
            conn.commit()
            return True

    # --- Voucher Code & Campaign Links Operations ---
    def get_voucher_codes(self, voucher_type: Optional[str] = None, only_active: bool = True) -> List[Dict]:
        """Lấy danh sách các mã giảm giá nhập tay hoặc mã % lớn"""
        with self.get_connection() as conn:
            query = "SELECT * FROM voucher_codes WHERE 1=1"
            params = []
            if only_active:
                query += " AND is_active = 1"
            if voucher_type:
                query += " AND voucher_type = ?"
                params.append(voucher_type.upper())
            query += " ORDER BY id ASC"
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def save_voucher_code(self, code: str, discount_desc: str, apply_url: str = "", category_filter: str = "ALL", voucher_type: str = "MANUAL", min_order: float = 0) -> int:
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
        """Nạp sẵn bộ mã giảm giá và link chiến dịch thực chiến mẫu (Chuẩn 25/09)"""
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

    # --- System Settings Operations ---
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

