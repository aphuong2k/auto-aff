import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
conn = sqlite3.connect('data/affiliate_system.db')
deals = conn.execute("SELECT name, category_name FROM deals WHERE category_name = 'Thời Trang Nam'").fetchall()
print(f"Tổng cộng {len(deals)} deals gắn mác 'Thời Trang Nam':")
for d in deals:
    print(f"  • {d[0]}")
