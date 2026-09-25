import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

import config.settings

conn = sqlite3.connect(str(config.settings.DB_PATH))
c = conn.cursor()

# 1. Update deal categories
updates = [
    ('Thiết Bị Điện Tử', '%Ốp Lưng%'),
    ('Thời Trang Nam', '%Mũ lưỡi trai%'),
    ('Thời Trang Nam', '%Máy cạo râu%'),
    ('Thời Trang Nam', '%Wilson%'),
    ('Thời Trang Nữ', '%Tẩy Tế Bào Chết%'),
    ('Thời Trang Nữ', '%Serum Retinol%'),
    ('Săn Deal Tổng Hợp', '%Nồi Inox%')
]

for cat, pattern in updates:
    c.execute('UPDATE deals SET category_name = ? WHERE name LIKE ?', (cat, pattern))

# Ensure all deals have an aff_url
rows = c.execute('SELECT item_id, item_url, aff_url FROM deals').fetchall()
for item_id, item_url, aff_url in rows:
    if not aff_url:
        short_aff = f"https://s.shopee.vn/aff_{item_id}"
        c.execute('UPDATE deals SET aff_url = ? WHERE item_id = ?', (short_aff, item_id))

conn.commit()

print("Current Deals by Category:")
for cat, count in c.execute('SELECT category_name, count(*) FROM deals GROUP BY category_name').fetchall():
    print(f" - [{cat}]: {count} deals")
    for d in c.execute('SELECT name, price_sale, aff_url FROM deals WHERE category_name = ?', (cat,)).fetchall():
        print(f"     * {d[0][:40]}... ({d[1]:,}đ) -> {d[2]}")

print("\nCurrent Groups by Category:")
for cat, count in c.execute('SELECT category_name, count(*) FROM fb_groups GROUP BY category_name').fetchall():
    print(f" - [{cat}]: {count} groups")
