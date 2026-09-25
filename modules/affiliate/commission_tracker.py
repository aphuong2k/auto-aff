import os
import csv
import io
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from database.db_manager import DatabaseManager

logger = logging.getLogger("CommissionTracker")

class CommissionTracker:
    """
    Hệ thống theo dõi & đối soát hoa hồng đa sàn (Shopee & Lazada):
    - Nhập và bóc tách báo cáo chuyển đổi (CSV / Excel) từ Shopee và Lazada Affiliate
    - Ánh xạ Sub-ID về kênh chuyển đổi (Telegram, Facebook Group, Seeding, Web Hub)
    - Tính toán EPC (Earning Per Click), CR (Conversion Rate) và GMV theo thời gian thực
    """

    def __init__(self, db: Optional[DatabaseManager] = None):
        self.db = db or DatabaseManager()

    def parse_and_import_csv(self, file_content: str, platform: str = "SHOPEE") -> Dict[str, Any]:
        """
        Nhập báo cáo đơn hàng CSV từ Shopee hoặc Lazada Affiliate Portal:
        - Tự động nhận diện header các cột (Order ID, GMV, Hoa hồng, Sub-ID...)
        """
        platform = platform.upper()
        reader = csv.DictReader(io.StringIO(file_content))
        imported_count = 0
        total_commission = 0.0
        errors = []

        for row_idx, row in enumerate(reader, 1):
            try:
                # Chuẩn hóa tên cột viết hoa/thường không dấu
                clean_row = {k.strip().lower(): (v.strip() if v else "") for k, v in row.items() if k}

                # 1. Trích xuất Mã đơn hàng (Order ID)
                order_id = (
                    clean_row.get("order id") or clean_row.get("mã đơn hàng") or
                    clean_row.get("order_id") or clean_row.get("order sn") or
                    clean_row.get("order no") or f"order_{row_idx}_{int(datetime.now().timestamp())}"
                )

                # 2. Trích xuất Hoa hồng (Commission)
                comm_str = (
                    clean_row.get("commission") or clean_row.get("hoa hồng") or
                    clean_row.get("actual commission") or clean_row.get("commission amount") or
                    clean_row.get("estimated commission") or "0"
                )
                comm_val = float(str(comm_str).replace(",", "").replace("₫", "").replace("VND", "").strip() or 0)

                # 3. Trích xuất Giá trị đơn hàng (GMV / Order value)
                val_str = (
                    clean_row.get("total order value") or clean_row.get("giá trị đơn") or
                    clean_row.get("item price") or clean_row.get("order amount") or
                    clean_row.get("gmv") or "0"
                )
                order_val = float(str(val_str).replace(",", "").replace("₫", "").replace("VND", "").strip() or 0)

                # 4. Trích xuất Sản phẩm
                item_name = clean_row.get("item name") or clean_row.get("tên sản phẩm") or clean_row.get("product name") or "Sản phẩm đối soát"
                item_id = clean_row.get("item id") or clean_row.get("mã sản phẩm") or clean_row.get("sku") or ""

                # 5. Trích xuất Sub-ID & Nhận diện Kênh
                sub_id = clean_row.get("sub_id1") or clean_row.get("sub1") or clean_row.get("sub_id") or clean_row.get("sub aff id") or "direct"
                channel = self._detect_channel_from_sub_id(sub_id)

                # 6. Trích xuất Trạng thái
                raw_status = (clean_row.get("status") or clean_row.get("trạng thái") or "COMPLETED").upper()
                if "HOÀN THÀNH" in raw_status or "COMPLETE" in raw_status or "APPROVED" in raw_status:
                    status = "APPROVED"
                elif "HỦY" in raw_status or "CANCEL" in raw_status:
                    status = "CANCELLED"
                else:
                    status = "PENDING"

                # 7. Thời gian mua hàng
                purch_time = clean_row.get("purchase time") or clean_row.get("thời gian mua") or clean_row.get("order time") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                self.db.record_commission(
                    platform=platform,
                    order_id=order_id,
                    commission_amount=comm_val,
                    order_value=order_val,
                    item_id=item_id,
                    item_name=item_name,
                    channel=channel,
                    sub_id=sub_id,
                    status=status,
                    purchase_time=purch_time
                )
                imported_count += 1
                total_commission += comm_val

            except Exception as e:
                errors.append(f"Dòng {row_idx}: {e}")

        logger.info(f"✅ Đã nạp thành công {imported_count} đơn hàng đối soát hoa hồng cho sàn {platform}")
        return {
            "status": "SUCCESS",
            "imported_count": imported_count,
            "total_commission": round(total_commission, 0),
            "errors": errors[:5]
        }

    def _detect_channel_from_sub_id(self, sub_id: str) -> str:
        """Nhận diện kênh chuyển đổi dựa trên Sub-ID gắn trong link"""
        s = str(sub_id).lower()
        if "tele" in s:
            return "TELEGRAM"
        elif "fb" in s or "group" in s:
            return "FB_GROUP"
        elif "seed" in s or "comment" in s:
            return "SEEDING"
        elif "web" in s or "hub" in s or "deal" in s:
            return "WEB_HUB"
        return "DIRECT"

    def seed_initial_demo_commissions(self):
        """Khởi tạo một số bản ghi đối soát hoa hồng mẫu ban đầu nếu CSDL hoàn toàn trống"""
        with self.db.get_connection() as conn:
            cnt = conn.execute("SELECT COUNT(*) FROM commissions").fetchone()[0]
            if cnt > 0:
                return

        logger.info("Nạp dữ liệu chuyển đổi hoa hồng khởi tạo để hiển thị biểu đồ đối soát...")
        now = datetime.now()
        samples = [
            ("SHOPEE", "SHOPEE-ORD-98214", "Nồi chiên không dầu điện tử 6L", 1250000, 75000, "TELEGRAM", "tele_hotdeal", "APPROVED", (now - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")),
            ("SHOPEE", "SHOPEE-ORD-98215", "Tai nghe Bluetooth True Wireless", 450000, 36000, "FB_GROUP", "fb_group_congnghe", "APPROVED", (now - timedelta(hours=6)).strftime("%Y-%m-%d %H:%M:%S")),
            ("LAZADA", "LAZ-ORD-11029", "Serum Vitamin C Dưỡng Sáng Da 30ml", 380000, 42000, "WEB_HUB", "web_hub_beauty", "APPROVED", (now - timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S")),
            ("SHOPEE", "SHOPEE-ORD-98216", "Áo thun polo nam cao cấp", 199000, 15900, "SEEDING", "seed_cmt_fb", "PENDING", (now - timedelta(hours=14)).strftime("%Y-%m-%d %H:%M:%S")),
            ("LAZADA", "LAZ-ORD-11030", "Bàn chải điện sóng âm thông minh", 590000, 53000, "TELEGRAM", "tele_main", "APPROVED", (now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")),
            ("SHOPEE", "SHOPEE-ORD-98217", "Bộ kem chống nắng SPF50+ PA++++", 320000, 28800, "WEB_HUB", "web_hub_top", "APPROVED", (now - timedelta(days=1, hours=5)).strftime("%Y-%m-%d %H:%M:%S")),
        ]

        for p, oid, name, gmv, comm, chan, sub, st, dt in samples:
            self.db.record_commission(
                platform=p,
                order_id=oid,
                commission_amount=comm,
                order_value=gmv,
                item_name=name,
                channel=chan,
                sub_id=sub,
                status=st,
                purchase_time=dt
            )
