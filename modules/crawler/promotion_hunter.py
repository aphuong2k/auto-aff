import json
import logging
import random
from datetime import datetime, timedelta
from typing import List, Dict, Optional

from database.db_manager import DatabaseManager
from modules.affiliate.link_converter import AffiliateLinkConverter

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

class PromotionHunter:
    """
    Module thu thập thông tin Chương trình Khuyến Mại, Khung Giờ Flash Sale & Mã Giảm Giá Shopee trong ngày.
    """

    # Danh sách các khung giờ Flash Sale chuẩn của Shopee Việt Nam
    FLASH_SALE_SLOTS = [
        {
            "slot": "00:00",
            "title": "Sale Nửa Đêm - Săn Deal Hủy Diệt 0Đ & Voucher 50%",
            "highlight": "Tung mã Freeship 0Đ, Voucher 50% chớp nhoáng, xả kho điện tử & bách hóa.",
            "banner": "https://cf.shopee.vn/file/vn-50009109-flash-sale-0h.jpg"
        },
        {
            "slot": "09:00",
            "title": "Hàng Hiệu Shopee Mall - Siêu Hội Giảm Giá 50%",
            "highlight": "Hàng loạt thương hiệu Mall xả kho chính hãng, voucher riêng từ các hãng lớn.",
            "banner": "https://cf.shopee.vn/file/vn-50009109-shopee-mall-9h.jpg"
        },
        {
            "slot": "12:00",
            "title": "Nửa Ngày Deal Sốc - Giờ Vàng Xả Kho & Cơm Trưa Săn Sale",
            "highlight": "Deal đồng giá dưới 99K, Freeship đơn từ 0Đ, voucher giảm giá bữa trưa.",
            "banner": "https://cf.shopee.vn/file/vn-50009109-flash-sale-12h.jpg"
        },
        {
            "slot": "15:00",
            "title": "Giờ Vàng Quốc Tế & Hàng Độc Quyền Hot Trend",
            "highlight": "Đồ chơi công nghệ, thời trang xu hướng quốc tế đồng giá giảm 50%.",
            "banner": "https://cf.shopee.vn/file/vn-50009109-international-15h.jpg"
        },
        {
            "slot": "18:00",
            "title": "Top Deal Bán Chạy - Giờ Tan Tầm Săn Sale",
            "highlight": "Săn sale đồ gia dụng, đồ ăn vặt và quần áo thời trang tan tầm.",
            "banner": "https://cf.shopee.vn/file/vn-50009109-top-deals-18h.jpg"
        },
        {
            "slot": "21:00",
            "title": "Sale Đêm Muộn - Đồng Giá Hủy Diệt 1K & Voucher Shopee Live",
            "highlight": "Đại tiệc voucher Shopee Live / Video giảm 50%, đồng giá 1K - 9K trước khi đi ngủ.",
            "banner": "https://cf.shopee.vn/file/vn-50009109-flash-sale-21h.jpg"
        }
    ]

    # Danh mục các chương trình voucher ưu đãi lớn trên Shopee (Thu thập tại shopee.vn/m/ma-giam-gia)
    DAILY_HOT_VOUCHERS = [
        {"code": "LẤY TRÊN BANNER", "desc": "Mã Miễn Phí Vận Chuyển Toàn Sàn đơn từ 0Đ (Thu thập tại mục Freeship)", "badge": "Freeship"},
        {"code": "LẤY TRÊN LIVE", "desc": "Voucher Shopee Live giảm đến 50% (Mở mới vào các khung giờ vàng)", "badge": "Shopee Live"},
        {"code": "LẤY TRÊN VIDEO", "desc": "Voucher Shopee Video giảm đến 50% đơn đầu", "badge": "Shopee Video"},
        {"code": "LẤY TRÊN MALL", "desc": "Voucher Shopee Mall giảm 15% - 20% cho hàng chính hãng", "badge": "Shopee Mall"},
        {"code": "VÍ SHOPEEPAY", "desc": "Voucher độc quyền khi thanh toán qua ShopeePay / Thẻ đối tác", "badge": "ShopeePay"}
    ]

    DEFAULT_PROMO_URL = "https://shopee.vn/m/ma-giam-gia"

    def __init__(self, db: Optional[DatabaseManager] = None):
        self.db = db or DatabaseManager()
        self.link_converter = AffiliateLinkConverter()

    def detect_campaign_day(self, date: Optional[datetime] = None) -> Dict[str, str]:
        """Tự động xác định chiến dịch sale lớn hôm nay (Ngày đôi, Giữa tháng, Lương về)"""
        d = date or datetime.now()
        day = d.day
        month = d.month

        if day == month:
            return {
                "type": "DOUBLE_DAY",
                "name": f"SIÊU ĐẠI TIỆC SALE NGÀY ĐÔI {day}.{month}",
                "tagline": f"Đại Tiệc Bùng Nổ Voucher {day}.{month} - Triệu Deal 0Đ & Miễn Hết Phí Ship!"
            }
        elif day == 15:
            return {
                "type": "MID_MONTH",
                "name": "SIÊU HỘI NỬA THÁNG - SALE GIỮA THÁNG 15",
                "tagline": "Nửa Tháng Săn Deal Khủng - Freeship Toàn Sàn & Xả Hàng Giữa Tháng!"
            }
        elif 25 <= day <= 28:
            return {
                "type": "PAYDAY",
                "name": "SIÊU SALE LƯƠNG VỀ - TƯNG BỪNG MUA SẮM",
                "tagline": "Lương Về Túi Tiền Rủng Rỉnh - Săn Ngay Deal Hàng Hiệu Giảm Đến 50%!"
            }
        elif d.weekday() == 4: # Thứ 6
            return {
                "type": "WEEKEND",
                "name": "SIÊU THỨ 6 RỰC RỠ - SĂN DEAL CUỐI TUẦN",
                "tagline": "Đón Cuối Tuần Rực Rỡ Cùng Hàng Ngàn Voucher Giảm Giá Sốc!"
            }
        else:
            return {
                "type": "DAILY_SALE",
                "name": "NGÀY HỘI SĂN DEAL & VOUCHER SHOPEE",
                "tagline": "Săn Mã Giảm Giá Độc Quyền & Flash Sale Khung Giờ Vàng Mỗi Ngày!"
            }

    def get_upcoming_slot(self, now: Optional[datetime] = None) -> Dict:
        """Xác định khung giờ Flash Sale tiếp theo gần nhất so với hiện tại"""
        current_time = now or datetime.now()
        now_hm = current_time.strftime("%H:%M")

        for item in self.FLASH_SALE_SLOTS:
            if item["slot"] > now_hm:
                return item

        # Nếu đã qua 21:00 thì khung tiếp theo là 00:00 ngày mai
        return self.FLASH_SALE_SLOTS[0]

    def get_current_active_slot(self, now: Optional[datetime] = None) -> Dict:
        """Xác định khung giờ Flash Sale đang diễn ra ngay lúc này"""
        current_time = now or datetime.now()
        now_hm = current_time.strftime("%H:%M")

        active_slot = self.FLASH_SALE_SLOTS[0]
        for item in self.FLASH_SALE_SLOTS:
            if now_hm >= item["slot"]:
                active_slot = item
            else:
                break
        return active_slot

    def get_today_promotion_package(self, target_slot: Optional[str] = None) -> Dict:
        """
        Tổng hợp trọn bộ thông tin khuyến mại, voucher và link affiliate cho bài nhắc sale
        """
        now = datetime.now()
        campaign = self.detect_campaign_day(now)
        
        # Chọn khung giờ mục tiêu
        if target_slot:
            slot_info = next((s for s in self.FLASH_SALE_SLOTS if s["slot"] == target_slot), None)
            if not slot_info:
                slot_info = self.get_upcoming_slot(now)
        else:
            slot_info = self.get_upcoming_slot(now)

        # Chuyển đổi link chiến dịch sang link Affiliate có gắn tracking
        aff_url = self.link_converter.convert_to_affiliate(self.DEFAULT_PROMO_URL)

        package = {
            "date": now.strftime("%Y-%m-%d"),
            "campaign_name": campaign["name"],
            "campaign_tagline": campaign["tagline"],
            "campaign_type": campaign["type"],
            "slot_time": slot_info["slot"],
            "slot_title": slot_info["title"],
            "slot_highlight": slot_info["highlight"],
            "banner_url": slot_info.get("banner"),
            "aff_url": aff_url,
            "vouchers": self.DAILY_HOT_VOUCHERS,
            "generated_at": now.strftime("%Y-%m-%d %H:%M:%S")
        }

        # Tự động lưu hoặc đồng bộ vào Database
        self.db.save_promotion({
            "title": f"[{package['slot_time']}] {package['slot_title']}",
            "campaign_type": package["campaign_type"],
            "slot_time": package["slot_time"],
            "banner_url": package["banner_url"],
            "aff_url": package["aff_url"],
            "description": package["slot_highlight"],
            "vouchers_json": json.dumps(package["vouchers"], ensure_ascii=False),
            "is_active": 1
        })

        return package

    def is_time_for_reminder(self, slot_str: str, remind_before_minutes: int = 15, now: Optional[datetime] = None) -> bool:
        """
        Kiểm tra xem thời điểm hiện tại có trùng với thời điểm cần gửi bài nhắc không.
        Ví dụ: Khung 12:00, nhắc trước 15 phút -> Thời điểm gửi là 11:45.
        """
        d = now or datetime.now()
        try:
            slot_hour, slot_min = map(int, slot_str.split(":"))
            slot_dt = d.replace(hour=slot_hour, minute=slot_min, second=0, microsecond=0)
            
            # Thời điểm cần bắn bài nhắc
            remind_dt = slot_dt - timedelta(minutes=remind_before_minutes)

            # So khớp theo giờ và phút
            return (d.hour == remind_dt.hour and d.minute == remind_dt.minute)
        except Exception as e:
            logging.warning(f"Lỗi kiểm tra thời điểm nhắc sale: {e}")
            return False
