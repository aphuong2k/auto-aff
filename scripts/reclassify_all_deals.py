import sqlite3
import sys
import os
sys.path.insert(0, os.path.abspath('.'))
from database.db_manager import DatabaseManager

sys.stdout.reconfigure(encoding='utf-8')
db = DatabaseManager()

with db.get_connection() as conn:
    deals = conn.execute("SELECT item_id, name, category_name FROM deals").fetchall()
    updated = 0
    for item_id, name, current_cat in deals:
        correct_cat = DatabaseManager.classify_product_niche(name, current_cat)
        if correct_cat != current_cat:
            conn.execute("UPDATE deals SET category_name = ? WHERE item_id = ?", (correct_cat, item_id))
            print(f"🔄 Reclassified: [{name[:45]}...]")
            print(f"   {current_cat} ➔ {correct_cat}")
            updated += 1
    conn.commit()

print(f"\n✅ Đã chuẩn hóa ngành hàng cho {updated}/{len(deals)} deals!")

# Show summary of deals by category
with db.get_connection() as conn:
    rows = conn.execute("SELECT category_name, count(*) FROM deals WHERE is_stale = 0 GROUP BY category_name").fetchall()
    print("\n📦 TỒN KHO DEAL THEO NGÀNH SAU KHI PHÂN LOẠI:")
    for r in rows:
        print(f"  • {r[0]}: {r[1]} deals")
