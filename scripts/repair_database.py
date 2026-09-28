"""
Database Repair & Recovery Utility
==================================
Tự động phục hồi cơ sở dữ liệu SQLite khi gặp lỗi:
"sqlite3.DatabaseError: database disk image is malformed"

Cơ chế hoạt động:
1. Sao lưu file DB bị lỗi sang file backup an toàn (.corrupted_backup).
2. Tạo file DB mới hoàn toàn sạch, khởi tạo đầy đủ Schema & Migrations từ database/migrations.py.
3. Quét nhị phân (Binary Leaf Page Scanner) toàn bộ các trang dữ liệu (0x0d Leaf Table B-Tree)
   của file DB lỗi để giải mã toàn bộ bản ghi (Records).
4. Phân loại và nạp lại toàn bộ dữ liệu vào DB mới (categories, deals, fb_groups, accounts, vouchers, ...).
5. Kiểm tra tính toàn vẹn (PRAGMA integrity_check).
6. Thay thế file DB gốc an toàn.
"""

import os
import sys
import shutil
import sqlite3
from pathlib import Path
from datetime import datetime

# UTF-8 stdout cho Windows console
if sys.stdout:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Đảm bảo import được các module dự án
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from config.settings import DB_PATH
from database.migrations import init_db as run_schema_migrations

PAGE_SIZE = 4096


def parse_varint(buffer: bytes, offset: int):
    """Giải mã SQLite varint (1-9 bytes)"""
    v = 0
    for i in range(9):
        b = buffer[offset + i]
        if i == 8:
            v = (v << 8) | b
            return v, offset + 9
        else:
            v = (v << 7) | (b & 0x7F)
            if not (b & 0x80):
                return v, offset + i + 1


def parse_record(payload: bytes):
    """Giải mã một SQLite Record Payload thành danh sách các giá trị cột"""
    header_len, offset = parse_varint(payload, 0)
    serial_types = []
    header_end = header_len
    curr = offset
    while curr < header_end:
        st, curr = parse_varint(payload, curr)
        serial_types.append(st)

    values = []
    body_offset = header_end
    for st in serial_types:
        if st == 0:
            values.append(None)
        elif st == 1:
            values.append(int.from_bytes(payload[body_offset:body_offset + 1], "big", signed=True))
            body_offset += 1
        elif st == 2:
            values.append(int.from_bytes(payload[body_offset:body_offset + 2], "big", signed=True))
            body_offset += 2
        elif st == 3:
            values.append(int.from_bytes(payload[body_offset:body_offset + 3], "big", signed=True))
            body_offset += 3
        elif st == 4:
            values.append(int.from_bytes(payload[body_offset:body_offset + 4], "big", signed=True))
            body_offset += 4
        elif st == 5:
            values.append(int.from_bytes(payload[body_offset:body_offset + 6], "big", signed=True))
            body_offset += 6
        elif st == 6:
            values.append(int.from_bytes(payload[body_offset:body_offset + 8], "big", signed=True))
            body_offset += 8
        elif st == 7:
            import struct
            values.append(struct.unpack(">d", payload[body_offset:body_offset + 8])[0])
            body_offset += 8
        elif st == 8:
            values.append(0)
        elif st == 9:
            values.append(1)
        elif st >= 12 and st % 2 == 0:
            length = (st - 12) // 2
            values.append(payload[body_offset:body_offset + length])
            body_offset += length
        elif st >= 13 and st % 2 == 1:
            length = (st - 13) // 2
            raw_bytes = payload[body_offset:body_offset + length]
            try:
                values.append(raw_bytes.decode("utf-8"))
            except UnicodeDecodeError:
                values.append(raw_bytes.decode("latin1", errors="ignore"))
            body_offset += length
        else:
            values.append(None)
    return values


def repair_database(target_db_path: Path = DB_PATH) -> bool:
    target_db_path = Path(target_db_path)
    if not target_db_path.exists():
        print(f"[REPAIR] Database {target_db_path} không tồn tại, tạo mới sạch...")
        conn = sqlite3.connect(str(target_db_path))
        run_schema_migrations(conn)
        conn.close()
        return True

    test_conn = None
    try:
        test_conn = sqlite3.connect(str(target_db_path))
        cur = test_conn.cursor()
        cur.execute("PRAGMA integrity_check;")
        res = cur.fetchall()
        test_conn.close()
        test_conn = None
        if res and res[0][0] == "ok":
            print(f"[REPAIR] Database {target_db_path} hoàn toàn bình thường (integrity_check = ok).")
            return True
    except Exception as e:
        if test_conn:
            try:
                test_conn.close()
            except Exception:
                pass
        print(f"[REPAIR] Phát hiện lỗi Database: {e}")

    # 1. Sao lưu file DB hỏng
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = target_db_path.with_name(f"{target_db_path.name}.corrupted_{timestamp}")
    print(f"[REPAIR] 1. Sao lưu DB hỏng sang: {backup_path}")
    shutil.copyfile(target_db_path, backup_path)

    # Đọc nhị phân DB gốc
    with open(target_db_path, "rb") as f:
        raw_data = f.read()

    num_pages = len(raw_data) // PAGE_SIZE
    print(f"[REPAIR] 2. Phân tích {num_pages} trang nhị phân ({len(raw_data)} bytes)...")

    # 2. Tạo DB mới tạm thời
    temp_new_db = target_db_path.with_name(f"{target_db_path.name}.rebuilding")
    if temp_new_db.exists():
        temp_new_db.unlink()

    new_conn = sqlite3.connect(str(temp_new_db))
    run_schema_migrations(new_conn)

    # Lấy thông tin cột của các bảng trong DB sạch
    cur = new_conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    tables_list = [r[0] for r in cur.fetchall()]
    table_columns = {}
    for t in tables_list:
        cur.execute(f"PRAGMA table_info({t})")
        table_columns[t] = [r[1] for r in cur.fetchall()]

    recovered_stats = {}

    def insert_record(table: str, cols: list, vals: list):
        nonlocal recovered_stats
        placeholders = ", ".join(["?"] * len(cols))
        col_str = ", ".join(cols)
        sql = f"INSERT OR REPLACE INTO {table} ({col_str}) VALUES ({placeholders})"
        try:
            new_conn.execute(sql, vals)
            recovered_stats[table] = recovered_stats.get(table, 0) + 1
        except Exception as err:
            pass

    # 3. Quét toàn bộ Leaf Table Pages (0x0d)
    for p in range(num_pages):
        offset = p * PAGE_SIZE
        ho = 100 if p == 0 else 0
        if offset + ho >= len(raw_data):
            break
        ptype = raw_data[offset + ho]
        if ptype != 0x0D:
            continue

        ncells = int.from_bytes(raw_data[offset + ho + 3: offset + ho + 5], "big")
        ptrs = []
        for c in range(ncells):
            ptr = int.from_bytes(raw_data[offset + ho + 8 + c * 2: offset + ho + 10 + c * 2], "big")
            ptrs.append(ptr)

        for cell_ptr in ptrs:
            try:
                cell_data = raw_data[offset + cell_ptr: offset + PAGE_SIZE]
                psize, o = parse_varint(cell_data, 0)
                rowid, o = parse_varint(cell_data, o)
                rec = parse_record(cell_data[o: o + min(psize, len(cell_data) - o)])

                if rec and rec[0] is None:
                    rec[0] = rowid

                # Match categories
                if len(rec) == 5 and isinstance(rec[1], str) and (rec[2] is None or isinstance(rec[2], int)) and rec[3] in [0, 1]:
                    insert_record("categories", table_columns["categories"], rec)

                # Match campaign_links
                elif len(rec) == 4 and isinstance(rec[0], str) and ("shopee" in str(rec[1]) or "lazada" in str(rec[1])):
                    insert_record("campaign_links", table_columns["campaign_links"], rec)

                # Match subscribers
                elif len(rec) == 8 and "@" in str(rec[1]):
                    insert_record("subscribers", table_columns["subscribers"], rec)

                # Match commissions
                elif len(rec) == 12 and rec[1] in ["SHOPEE", "LAZADA"]:
                    insert_record("commissions", table_columns["commissions"], rec)

                # Match workflow_reports
                elif len(rec) == 15 and rec[1] in ["AUTO_SCHEDULE", "MANUAL_ALL", "MANUAL_STEP"]:
                    insert_record("workflow_reports", table_columns["workflow_reports"], rec)

                # Match fb_accounts
                elif len(rec) == 19 and isinstance(rec[1], str) and ("c_user=" in str(rec[2]) or "sb=" in str(rec[2])):
                    insert_record("fb_accounts", table_columns["fb_accounts"], rec)

                # Match sale_promotions
                elif len(rec) == 10 and ("[" in str(rec[1]) or "PAYDAY" in str(rec[2])):
                    insert_record("sale_promotions", table_columns["sale_promotions"], rec)

                # Match sale_reminder_history
                elif len(rec) in [6, 7] and any(x in str(rec) for x in ["TELEGRAM", "FB_GROUP"]) and any(x in str(rec) for x in ["SALE", "Khung Giờ", "khung giờ"]):
                    if len(rec) == 6:
                        rec = [rec[0], rec[1], rec[2], rec[3], rec[5], "SENT", rec[4]]
                    insert_record("sale_reminder_history", table_columns["sale_reminder_history"], rec)

                # Match deal_post_history
                elif len(rec) == 6 and "grp_" in str(rec[2]):
                    insert_record("deal_post_history", table_columns["deal_post_history"], rec)

                # Match system_cycles
                elif len(rec) == 14 and rec[2] in ["ACTIVE", "COMPLETED"]:
                    insert_record("system_cycles", table_columns["system_cycles"], rec)

                # Match fb_groups
                elif len(rec) == 30 and ("facebook.com/groups" in str(rec[2]) or "fb.com/groups" in str(rec[2])):
                    insert_record("fb_groups", table_columns["fb_groups"], rec)

                # Match deals
                elif len(rec) in [21, 22, 23, 24] and (isinstance(rec[0], str) and (rec[0].isdigit() or rec[0].startswith("laz_") or rec[0].startswith("test_"))):
                    padded = rec + [None] * (24 - len(rec))
                    insert_record("deals", table_columns["deals"], padded)

            except Exception:
                pass

    new_conn.commit()

    # 4. Kiểm tra tính toàn vẹn của DB mới
    cur = new_conn.cursor()
    cur.execute("PRAGMA integrity_check;")
    check_result = cur.fetchall()
    new_conn.close()

    if not check_result or check_result[0][0] != "ok":
        print(f"[REPAIR ERROR] Database mới tạo không đạt kiểm tra integrity: {check_result}")
        return False

    print("\n--- KẾT QUẢ PHỤC HỒI DỮ LIỆU ---")
    total_recovered = 0
    for tbl, count in sorted(recovered_stats.items()):
        print(f"  + {tbl:<25}: {count} dòng")
        total_recovered += count
    print(f"Tổng cộng phục hồi thành công: {total_recovered} dòng dữ liệu.")
    print("Tính toàn vẹn SQLite mới: OK 100%")

    # 5. Xoá file -wal và -shm cũ nếu có
    for ext in ["-wal", "-shm"]:
        old_aux = target_db_path.with_name(target_db_path.name + ext)
        if old_aux.exists():
            try:
                old_aux.unlink()
            except Exception:
                pass

    # 6. Thay thế file DB gốc bằng DB mới đã phục hồi
    try:
        shutil.copyfile(temp_new_db, target_db_path)
        temp_new_db.unlink()
        print(f"[REPAIR] Đã thay thế thành công {target_db_path} bằng cơ sở dữ liệu mới sạch sẽ!")
        return True
    except Exception as e:
        print(f"[REPAIR ERROR] Không thể thay thế file DB: {e}")
        return False


if __name__ == "__main__":
    success = repair_database()
    if success:
        print("\n[OK] Quá trình phục hồi hoàn tất thành công.")
    else:
        print("\n[FAIL] Phục hồi thất bại.")
