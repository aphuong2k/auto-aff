import logging
import os
from typing import List, Dict, Optional
from pathlib import Path

from database.db_manager import DatabaseManager
from modules.affiliate.content_writer import DealContentWriter
from modules.affiliate.image_stamper import ImageBannerStamper
from modules.affiliate.link_converter import AffiliateLinkConverter
from modules.crawler.promotion_hunter import PromotionHunter
from config.settings import COMMUNITY_INVITE_URL, COMMUNITY_NAME

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

class GeneralDealOutreach:
    """
    Module phụ trách nhánh Săn Deal & Săn Sale Shopee Tổng Hợp (General Deal Groups).
    - Tạo các bài đăng dạng Tổng hợp nhiều deal hot đa ngành thay vì 1 deal đơn lẻ.
    - Nhắc lịch 6 khung giờ vàng & kho mã giảm giá.
    - Kêu gọi thành viên tham gia Kênh Telegram / Nhóm Zalo riêng để xây dựng cộng đồng.
    """

    def __init__(self, db: Optional[DatabaseManager] = None):
        self.db = db or DatabaseManager()
        self.link_converter = AffiliateLinkConverter()
        self.promo_hunter = PromotionHunter(self.db)

    def prepare_general_deals(self, limit: int = 6) -> List[Dict]:
        """Lấy top deals đa ngành + deal 1K và chuyển đổi link sang bridge Anti-Ban"""
        with self.db.get_connection() as conn:
            rows = conn.execute("""
                SELECT * FROM deals 
                ORDER BY deal_score DESC, created_date DESC 
                LIMIT ?
            """, (limit,)).fetchall()
            deals = [dict(r) for r in rows]

        for d in deals:
            item_id = str(d.get("item_id", ""))
            direct_aff = d.get("aff_url") or d.get("item_url", "")
            bridge_url = self.link_converter.get_bridge_url(
                item_id=item_id,
                channel="fb_general_roundup",
                sub_id="roundup_daily",
                direct_aff_url=direct_aff
            )
            d["bridge_url"] = bridge_url
        return deals

    def generate_all_general_posts(self, community_url: str = "", community_name: str = "") -> Dict[str, str]:
        """Tạo trọn bộ 3 định dạng bài đăng cho nhóm chung kèm CTA link nhóm của bạn"""
        url = community_url or os.getenv("COMMUNITY_INVITE_URL", COMMUNITY_INVITE_URL)
        name = community_name or os.getenv("COMMUNITY_NAME", COMMUNITY_NAME) or "Hội Săn Deal Shopee VIP"

        deals = self.prepare_general_deals(limit=6)
        promo_package = self.promo_hunter.get_today_promotion_package()

        post_roundup = DealContentWriter.generate_general_deal_roundup(
            deals=deals,
            promo_package=promo_package,
            community_url=url,
            community_name=name
        )

        post_schedule = DealContentWriter.generate_flash_sale_schedule_post(
            promo_slots=PromotionHunter.FLASH_SALE_SLOTS,
            community_url=url,
            community_name=name
        )

        post_tips = DealContentWriter.generate_voucher_secret_tips_post(
            community_url=url,
            community_name=name
        )

        return {
            "post_roundup": post_roundup,
            "post_schedule": post_schedule,
            "post_tips": post_tips,
            "community_url": url,
            "community_name": name,
            "deal_count": len(deals)
        }

    def generate_daily_header_banner(self, date_str: str = "") -> Path:
        """
        Tạo ảnh Cover Banner Tiêu Đề chuẩn cho bài đăng tổng hợp Shopee trong ngày.
        Theo yêu cầu: 'để ảnh tiêu đề là deal shoppee ngày bn thế thôi đừng ghép vào'
        """
        return ImageBannerStamper.create_daily_cover_banner(date_str=date_str)

    def generate_daily_collage(self) -> Path:
        """Tạo ảnh ghép 4 góc (2x2 Mega Collage Grid) phục vụ bài tổng hợp (tùy chọn)"""
        deals = self.prepare_general_deals(limit=4)
        return ImageBannerStamper.create_mega_deal_collage(deals)
