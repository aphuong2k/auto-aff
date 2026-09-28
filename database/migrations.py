"""
Database Schema Initializer & Migrations
========================================
Quản lý toàn bộ cấu trúc bảng SQLite và các bước ALTER TABLE migration tự động.
"""

import sqlite3


def init_db(conn: sqlite3.Connection):
    """Khởi tạo các bảng SQLite và chạy migration mở rộng cột tự động"""
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
            name TEXT NOT NULL,
            code TEXT,
            discount_value TEXT,
            start_time TIMESTAMP,
            end_time TIMESTAMP,
            slot_hour TEXT, -- Ví dụ: '00:00', '09:00', '12:00'
            url TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 7. Bảng ghi nhận lịch sử đã nhắc giờ sale
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sale_reminder_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slot_time TEXT NOT NULL,
            campaign_date DATE NOT NULL,
            target TEXT NOT NULL, -- 'TELEGRAM' hoặc 'FB_GROUP'
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'SENT',
            message_content TEXT
        )
    """)

    # 8. Bảng lưu trữ lịch sử gieo bình luận dạo (Facebook Seeding History)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS comment_seeding_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id TEXT NOT NULL,
            post_url TEXT NOT NULL,
            deal_id TEXT,
            comment_content TEXT NOT NULL,
            status TEXT DEFAULT 'SUCCESS',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (deal_id) REFERENCES deals (item_id)
        )
    """)

    # 9. Bảng lưu vết lịch sử biến động giá (Price History Tracker)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id TEXT NOT NULL,
            price REAL NOT NULL,
            recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (item_id) REFERENCES deals (item_id)
        )
    """)

    # 10. Bảng lưu trữ click tracking trung gian Anti-Ban & Mobile DeepLink (/r/{id})
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS click_analytics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id TEXT NOT NULL,
            channel TEXT DEFAULT 'DIRECT', -- 'TELEGRAM', 'FB_GROUP', 'FB_SEEDING', 'WEB_PORTAL'
            sub_id TEXT,
            ip TEXT,
            referer TEXT,
            user_agent TEXT,
            clicked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (item_id) REFERENCES deals (item_id)
        )
    """)

    # 11. Bảng lưu vết bằng chứng các bài viết/comment đã đăng lên Facebook
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS posted_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL, -- 'POST' hoặc 'COMMENT'
            group_name TEXT,
            group_url TEXT,
            target_url TEXT, -- Link trực tiếp bài viết hoặc comment trên Facebook để kiểm tra
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

    # 13. Bảng đăng ký nhận tin Flash Sale / Deal hời
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

    # 15. Bảng cấu hình link chiến dịch
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS campaign_links (
            key_name TEXT PRIMARY KEY,
            link_url TEXT NOT NULL,
            title TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 16. Bảng lưu trữ cấu hình hệ thống & lịch chạy
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS system_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 17. Bảng ghi nhận báo cáo toàn trình các phiên chạy
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

    # 18. Bảng quản lý nhiều tài khoản Facebook & luân phiên
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fb_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            cookie TEXT NOT NULL,
            profile_path TEXT DEFAULT '',
            is_active INTEGER DEFAULT 1,
            daily_post_limit INTEGER DEFAULT 3,
            daily_join_limit INTEGER DEFAULT 3,
            posts_today INTEGER DEFAULT 0,
            joins_today INTEGER DEFAULT 0,
            last_used_at TIMESTAMP,
            last_posted_date DATE,
            proxy TEXT DEFAULT '',
            status TEXT DEFAULT 'ACTIVE',
            notes TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 18.1 Bảng lịch sử sử dụng tài khoản Facebook
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS account_usage_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            group_id TEXT NOT NULL,
            deal_id TEXT,
            post_url TEXT,
            action_type TEXT DEFAULT 'POST', -- 'POST', 'SEEDING', 'JOIN'
            status TEXT NOT NULL,            -- 'SUCCESS', 'FAILED', 'CHECKPOINT'
            error_message TEXT,
            duration_seconds REAL DEFAULT 0,
            used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (account_id) REFERENCES fb_accounts (id)
        )
    """)

    # 19. Bảng chống đăng trùng 1 deal vào cùng 1 nhóm Facebook
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS deal_post_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            deal_id TEXT NOT NULL,
            group_id TEXT NOT NULL,
            post_url TEXT,
            account_name TEXT,
            posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(deal_id, group_id)
        )
    """)

    # 20. Bảng lịch sử quét & xử lý từng Node Group
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS group_scan_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            execution_id TEXT NOT NULL,
            group_id TEXT NOT NULL,
            group_name TEXT,
            category_name TEXT,
            cycle_id INTEGER NOT NULL,
            scan_date DATE NOT NULL,
            status TEXT NOT NULL,              -- COMPLETED, SKIPPED, POST_FAILED, SEEDING_FAILED, SCANNING
            current_step TEXT DEFAULT 'READY',
            deals_evaluated INTEGER DEFAULT 0,
            deal_posted_id TEXT,
            deal_posted_name TEXT,
            post_url TEXT,
            deals_seeded INTEGER DEFAULT 0,
            error_message TEXT,
            retry_count INTEGER DEFAULT 0,
            duration_seconds REAL DEFAULT 0,
            worker_id TEXT DEFAULT 'MAIN_WORKER',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(group_id, scan_date)
        )
    """)

    # 21. Bảng quản lý Chu Kỳ Vòng Quét
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS system_cycles (
            cycle_id INTEGER PRIMARY KEY AUTOINCREMENT,
            cycle_number INTEGER UNIQUE NOT NULL,
            status TEXT DEFAULT 'ACTIVE',       -- 'ACTIVE', 'COMPLETED'
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            total_groups INTEGER DEFAULT 0,
            completed_groups INTEGER DEFAULT 0,
            skipped_groups INTEGER DEFAULT 0,
            failed_groups INTEGER DEFAULT 0,
            current_group_pointer INTEGER DEFAULT 0,
            current_group_id TEXT
        )
    """)

    # =========================================================================
    # TỰ ĐỘNG MIGRATE CÁC CỘT MỞ RỘNG (ALTER TABLE)
    # =========================================================================

    # Migrations cho deals
    cursor.execute("PRAGMA table_info(deals)")
    deals_cols = [row[1] for row in cursor.fetchall()]
    for col, c_type in [
        ("local_image", "TEXT"), ("price_badge", "TEXT"), ("platform", "TEXT DEFAULT 'SHOPEE'"),
        ("is_stale", "INTEGER DEFAULT 0"), ("last_checked_at", "TIMESTAMP"),
        ("commission_rate", "REAL DEFAULT 5.0"), ("is_extra", "INTEGER DEFAULT 0"),
        ("shop_id", "TEXT DEFAULT ''"), ("status", "TEXT DEFAULT 'QUALIFIED'"),
        ("updated_at", "TIMESTAMP")
    ]:
        if col not in deals_cols:
            cursor.execute(f"ALTER TABLE deals ADD COLUMN {col} {c_type}")

    # Migrations cho click_analytics
    cursor.execute("PRAGMA table_info(click_analytics)")
    click_cols = [row[1] for row in cursor.fetchall()]
    if "platform" not in click_cols:
        cursor.execute("ALTER TABLE click_analytics ADD COLUMN platform TEXT DEFAULT 'SHOPEE'")

    # Migrations cho fb_groups
    cursor.execute("PRAGMA table_info(fb_groups)")
    fb_cols = [row[1] for row in cursor.fetchall()]
    for col, c_type in [
        ("group_type", "TEXT DEFAULT 'NICHE'"), ("priority", "INTEGER DEFAULT 1"),
        ("enabled", "INTEGER DEFAULT 1"), ("last_scanned_at", "TIMESTAMP"),
        ("last_seeding_at", "TIMESTAMP"), ("max_post_per_day", "INTEGER DEFAULT 1"),
        ("max_seeding_per_day", "INTEGER DEFAULT 2"), ("current_cycle", "INTEGER DEFAULT 1"),
        ("health_score", "INTEGER DEFAULT 50"), ("last_active_at", "TIMESTAMP"),
        ("avg_engagement", "REAL DEFAULT 0.0"), ("unique_posters", "INTEGER DEFAULT 0"),
        ("join_checked_at", "TIMESTAMP"), ("join_check_count", "INTEGER DEFAULT 0"),
        ("posting_restricted", "INTEGER DEFAULT 0"), ("consecutive_rejections", "INTEGER DEFAULT 0"),
        ("health_verdict", "TEXT DEFAULT 'UNKNOWN'"), ("last_template_id", "TEXT DEFAULT ''"),
        ("requires_post_approval", "INTEGER DEFAULT 0"), ("pending_approval_count", "INTEGER DEFAULT 0"),
        ("last_approval_check_at", "TIMESTAMP")
    ]:
        if col not in fb_cols:
            cursor.execute(f"ALTER TABLE fb_groups ADD COLUMN {col} {c_type}")

    # Migrations cho fb_accounts
    cursor.execute("PRAGMA table_info(fb_accounts)")
    acc_cols = [row[1] for row in cursor.fetchall()]
    for col, c_type in [
        ("posts_current_cycle", "INTEGER DEFAULT 0"), ("total_posts", "INTEGER DEFAULT 0"),
        ("cooldown_until", "TIMESTAMP"), ("cooldown_seconds", "INTEGER DEFAULT 900")
    ]:
        if col not in acc_cols:
            cursor.execute(f"ALTER TABLE fb_accounts ADD COLUMN {col} {c_type}")

    # Migrations cho posted_logs
    cursor.execute("PRAGMA table_info(posted_logs)")
    pl_cols = [row[1] for row in cursor.fetchall()]
    for col, c_type in [
        ("account_name", "TEXT DEFAULT ''"),
        ("template_id", "TEXT DEFAULT ''"),
        ("content_hash", "TEXT DEFAULT ''"),
        ("approval_status", "TEXT DEFAULT 'PENDING'"),
        ("approval_checked_at", "TIMESTAMP")
    ]:
        if col not in pl_cols:
            cursor.execute(f"ALTER TABLE posted_logs ADD COLUMN {col} {c_type}")

    # Migrations cho system_cycles
    cursor.execute("PRAGMA table_info(system_cycles)")
    cycle_cols = [row[1] for row in cursor.fetchall()]
    for col, c_type in [
        ("total_deals_found", "INTEGER DEFAULT 0"), ("total_posts", "INTEGER DEFAULT 0"),
        ("total_seedings", "INTEGER DEFAULT 0")
    ]:
        if col not in cycle_cols:
            cursor.execute(f"ALTER TABLE system_cycles ADD COLUMN {col} {c_type}")

    # Migrations cho post_history
    cursor.execute("PRAGMA table_info(post_history)")
    ph_cols = [row[1] for row in cursor.fetchall()]
    for col, c_type in [
        ("approval_status", "TEXT DEFAULT 'PENDING'"),
        ("approval_checked_at", "TIMESTAMP"),
        ("post_url", "TEXT"),
        ("template_id", "TEXT DEFAULT ''"),
        ("content_hash", "TEXT DEFAULT ''")
    ]:
        if col not in ph_cols:
            cursor.execute(f"ALTER TABLE post_history ADD COLUMN {col} {c_type}")

    conn.commit()
