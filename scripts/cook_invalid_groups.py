import sqlite3

conn = sqlite3.connect("data/affiliate_system.db")
c = conn.execute("""
    UPDATE fb_groups 
    SET status = 'LEFT', enabled = 0, posting_restricted = 1, health_verdict = 'COOKED' 
    WHERE group_id LIKE 'grp_%' 
       OR name LIKE '%Bạn hiện có thể tham gia%' 
       OR name LIKE '%Quản trị viên đã từ chối bài viết%'
""")
conn.commit()
print("Updated invalid / sample groups count:", c.rowcount)

rows = conn.execute("SELECT group_id, name, status, enabled FROM fb_groups WHERE status = 'APPROVED' AND enabled = 1").fetchall()
print("Remaining APPROVED & enabled groups:", len(rows))
for r in rows:
    print(" -", r[0], ":", r[1][:40])
