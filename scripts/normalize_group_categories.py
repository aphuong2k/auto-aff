import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('data/affiliate_system.db')
c1 = conn.execute("UPDATE fb_groups SET category_name = 'Thiết Bị Điện Tử' WHERE category_name = 'Điện Thoại & Phụ Kiện'").rowcount
c2 = conn.execute("UPDATE fb_groups SET category_name = 'Săn Deal Tổng Hợp' WHERE category_name = 'Cộng Đồng Chung'").rowcount
conn.commit()
print(f"Updated {c1} groups to 'Thiết Bị Điện Tử', {c2} groups to 'Săn Deal Tổng Hợp'")

# Check distribution
rows = conn.execute("SELECT category_name, count(*) FROM fb_groups GROUP BY category_name").fetchall()
for r in rows:
    print(f"  - {r[0]}: {r[1]} groups")
