import random
from typing import Dict

class DealContentWriter:
    """Module tự động tạo nội dung bài đăng cuốn hút cho Kênh Telegram và Group Facebook"""

    HEADER_ICONS = ["🔥", "⚡", "💥", "🏷️", "📢"]

    @classmethod
    def generate_telegram_post(cls, deal: Dict) -> str:
        icon = random.choice(cls.HEADER_ICONS)
        discount = deal.get("discount_percent", 0)
        price_sale = int(deal.get("price_sale", 0))
        price_orig = int(deal.get("price_original", 0))
        rating = deal.get("rating_star", 5.0)
        sold = deal.get("historical_sold", 0)
        aff_url = deal.get("aff_url") or deal.get("item_url", "")

        post = (
            f"{icon} <b>[DEAL CỰC HỜI HÔM NAY] {deal['name']}</b>\n\n"
            f"📉 <b>Giá sale chỉ:</b> <code>{price_sale:,}đ</code> <i>(Gốc: {price_orig:,}đ - Giảm {discount}%)</i>\n"
            f"⭐ <b>Đánh giá:</b> {rating} / 5.0 ({sold:,} lượt mua)\n"
            f"🏷️ <b>Ngành hàng:</b> #{deal.get('category_name', 'DealHot').replace(' ', '_').replace('&', '_')}\n"
            f"✅ <i>Cam kết hàng chuẩn, áp thêm voucher sàn trước khi thanh toán!</i>\n\n"
            f"👉 <b>Bấm vào đây để săn ngay:</b> <a href=\"{aff_url}\">Xem chi tiết sản phẩm</a>"
        )
        return post

    @classmethod
    def generate_facebook_post(cls, deal: Dict) -> str:
        discount = deal.get("discount_percent", 0)
        price_sale = int(deal.get("price_sale", 0))
        price_orig = int(deal.get("price_original", 0))
        rating = deal.get("rating_star", 5.0)
        sold = deal.get("historical_sold", 0)
        aff_url = deal.get("aff_url") or deal.get("item_url", "")

        post = (
            f"Góc chia sẻ deal hời cho cả nhà 👇\n"
            f"Con '{deal['name']}' này đang sale sâu quá mn ơi!\n\n"
            f"• Giá gốc: {price_orig:,}đ\n"
            f"• Giá flash sale hôm nay: {price_sale:,}đ (-{discount}%)\n"
            f"• Hơn {sold:,} người đã mua, đánh giá {rating} sao cực uy tín.\n\n"
            f"Bác nào đang cần tìm món này thì tranh thủ múc sớm kẻo hết lượt sale nhé.\n"
            f"🔗 Link chốt deal chính hãng: {aff_url}"
        )
        return post
