import random
import os
from datetime import datetime
from typing import Dict, List, Optional

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

        # Huy hiệu phân tích giá thực tế
        price_badge = deal.get("price_badge", "")
        badge_line = ""
        if "LOW" in price_badge:
            badge_line = "📉 <b>ĐỘC QUYỀN:</b> <code>[ĐÁY LỊCH SỬ 30 NGÀY - ĐÃ KIỂM CHỨNG]</code>\n"
        elif "REAL" in price_badge:
            badge_line = "✅ <b>ĐỘC QUYỀN:</b> <code>[GIẢM THẬT SỰ - KHÔNG KÊ GIÁ ẢO]</code>\n"
        elif "SUSPICIOUS" in price_badge:
            badge_line = "⚠️ <b>LƯU Ý:</b> <i>Shop có dấu hiệu tăng giá niêm yết trước khi giảm</i>\n"

        platform = str(deal.get("platform", "SHOPEE")).upper()
        plat_name = "Lazada" if platform == "LAZADA" else "Shopee"
        plat_tag = "#LazMall" if platform == "LAZADA" else "#ShopeeMall"

        post = (
            f"{icon} <b>[DEAL {plat_name.upper()} CỰC HỜI HÔM NAY] {deal['name']}</b>\n\n"
            f"📉 <b>Giá sale chỉ:</b> <code>{price_sale:,}đ</code> <i>(Gốc: {price_orig:,}đ - Giảm {discount}%)</i>\n"
            f"{badge_line}"
            f"⭐ <b>Đánh giá:</b> {rating} / 5.0 ({sold:,} lượt mua uy tín)\n"
            f"🏷️ <b>Ngành hàng:</b> #{deal.get('category_name', 'DealHot').replace(' ', '_').replace('&', '_')} {plat_tag}\n"
            f"✅ <i>Cam kết hàng chuẩn {plat_name}, áp thêm mã Freeship 0Đ tại bước thanh toán!</i>\n\n"
            f"👉 <b>Bấm vào đây để săn ngay trên {plat_name}:</b> <a href=\"{aff_url}\">Xem chi tiết sản phẩm</a>"
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

        price_badge = deal.get("price_badge", "")
        badge_text = ""
        if "LOW" in price_badge:
            badge_text = "🔥 ĐẶC BIỆT: Con này đang chạm ĐÁY LỊCH SỬ 30 ngày qua mình vừa check xong!\n"
        elif "REAL" in price_badge:
            badge_text = "✅ ĐÃ KIỂM TRA: Mức giảm thật sự, không có chiêu trò tăng giá ảo nha mn.\n"

        post = (
            f"Góc chia sẻ deal hời cho cả nhà 👇\n"
            f"Con '{deal['name']}' này đang sale sâu quá mn ơi!\n\n"
            f"{badge_text}"
            f"• Giá gốc: {price_orig:,}đ\n"
            f"• Giá flash sale hôm nay: {price_sale:,}đ (-{discount}%)\n"
            f"• Hơn {sold:,} người đã mua, đánh giá {rating} sao cực uy tín.\n\n"
            f"Bác nào đang cần tìm món này thì tranh thủ múc sớm kẻo hết lượt sale nhé.\n"
            f"🔗 Link chốt deal chính hãng: {aff_url}"
        )
        return post

    @classmethod
    def generate_comment_seeding_post(cls, deal: Dict, query_context: str = "") -> str:
        """Tạo câu trả lời bình luận dạng Review trải nghiệm có tâm, tự nhiên như thành viên thật chia sẻ"""
        price_sale = int(deal.get("price_sale", 0))
        price_orig = int(deal.get("price_original", 0))
        rating = deal.get("rating_star", 5.0)
        sold = deal.get("historical_sold", 0)
        aff_url = deal.get("aff_url") or deal.get("item_url", "")

        templates = [
            (
                f"Bác tham khảo con '{deal['name']}' này thử nhé, em mua đợt sale trước dùng hơn 2 tháng thấy ưng bụng lắm. "
                f"Ưu điểm là hàng chuẩn Mall, bền bỉ, nhược điểm là đợt sale giao hơi lâu xíu vì đông đơn thôi. "
                f"Shop chính hãng hơn {sold:,} lượt mua đánh giá {rating}⭐ nè: {aff_url}"
            ),
            (
                f"Đợt trước em cũng đắn đo tìm đỏ mắt như bác, sau săn được con '{deal['name']}' này trên Shopee đang sale từ {price_orig:,}đ còn có {price_sale:,}đ. "
                f"Mua về dùng thấy ngon vượt mong đợi trong tầm giá. Bác vào xem thử gian hàng chính hãng này nhé: {aff_url}"
            ),
            (
                f"Món này vote bác nghía thử con '{deal['name']}' nhé, đúng tiêu chí ngon-bổ-rẻ luôn. "
                f"Hơn {sold:,} người mua đánh giá {rating} sao là hiểu độ uy tín rồi. Bác nhớ lưu thêm mã Freeship áp vào trước khi chốt đơn: {aff_url}"
            ),
            (
                f"Em đang dùng con '{deal['name']}' này đây bác ơi. Trộm vía dùng mượt mà, đáng tiền từng xu. "
                f"Bên Shopee đang Flash Sale giảm còn {price_sale:,}đ (gốc {price_orig:,}đ), bác tranh thủ vào nghía sớm kẻo hết lượt sale: {aff_url}"
            ),
            (
                f"Bác tham khảo thử link này nhé, em vừa săn được con '{deal['name']}' bên gian hàng Shopee Mall xả kho. "
                f"Shop đóng gói cẩn thận, có bảo hành đầy đủ nên an tâm: {aff_url}"
            )
        ]
        return random.choice(templates)

    @classmethod
    def generate_loss_leader_post(cls, deal: Dict) -> str:
        """Tạo bài đăng săn Deal Mồi 1K / Freeship 0Đ để kích hoạt Cookie 7 ngày"""
        price_sale = int(deal.get("price_sale", 1000))
        price_orig = int(deal.get("price_original", 25000))
        aff_url = deal.get("aff_url") or deal.get("item_url", "")

        post = (
            f"🎁 <b>[SĂN DEAL 1K CỰC HỜI] {deal['name']}</b> 🔥\n\n"
            f"⚡ <b>Giá mở bán Flash Sale:</b> <code>{price_sale:,}đ</code> <i>(Giá gốc: {price_orig:,}đ)</i>\n"
            f"🎟️ <b>Đặc biệt:</b> <i>Áp thêm mã Freeship 0Đ tại bước thanh toán là có hàng ship tận giường!</i>\n"
            f"⭐ <b>Đánh giá:</b> {deal.get('rating_star', 4.9)}/5.0 ({deal.get('historical_sold', 0):,} lượt mua uy tín)\n\n"
            f"💡 <b>Mẹo săn deal:</b> Bấm link bên dưới bỏ sẵn vào giỏ hàng, áp mã vận chuyển rồi bấm thanh toán ngay kẻo hết lượt 1K nhé anh em!\n\n"
            f"👉 <b>BẤM VÀO ĐÂY ĐỂ LẤY DEAL 1K:</b>\n"
            f"<a href=\"{aff_url}\">🚀 Gắp Ngay Món Này 1K Về Giỏ</a>"
        )
        return post

    @classmethod
    def generate_sale_reminder_post(cls, promo: Dict) -> str:
        """Tạo bài đăng nhắc nhở khung giờ Flash Sale & Voucher trên Telegram (HTML)"""
        slot_time = promo.get("slot_time", "12:00")
        slot_title = promo.get("slot_title", "Giờ Vàng Săn Sale")
        campaign_name = promo.get("campaign_name", "SIÊU HỘI SĂN SALE SHOPEE")
        aff_url = promo.get("aff_url") or "https://shopee.vn"
        vouchers = promo.get("vouchers", [])

        voucher_lines = []
        for v in vouchers[:4]:
            voucher_lines.append(f"  🎟️ <b>{v.get('badge', 'Voucher')}:</b> {v.get('desc', '')}")
        vouchers_str = "\n".join(voucher_lines) if voucher_lines else "  🎟️ Freeship 0Đ & Voucher 50% chớp nhoáng"

        post = (
            f"⏰ <b>[SẮP ĐẾN GIỜ SALE] KHUNG GIỜ VÀNG {slot_time}!</b> 🔥\n\n"
            f"🎉 <b>Chiến dịch:</b> <i>{campaign_name}</i>\n"
            f"⚡ <b>Tiêu điểm {slot_time}:</b> {slot_title}\n\n"
            f"🎁 <b>CÁC MÃ GIẢM GIÁ HOT NHẤT SẮP MỞ:</b>\n"
            f"{vouchers_str}\n\n"
            f"💡 <b>MẸO NHANH CHO ANH EM:</b>\n"
            f"1. Bấm link bên dưới để vào lưu sẵn voucher vào ví.\n"
            f"2. Cho sẵn hàng vào giỏ từ trước.\n"
            f"3. Đúng {slot_time} vào bấm thanh toán ngay kẻo hết lượt!\n\n"
            f"👉 <b>BẤM VÀO ĐÂY ĐỂ LƯU MÃ & SĂN SALE:</b>\n"
            f"<a href=\"{aff_url}\">🚀 Vào Shopee Săn Deal Ngay</a>"
        )
        return post

    @classmethod
    def generate_fb_sale_reminder_post(cls, promo: Dict) -> str:
        """Tạo bài đăng nhắc nhở khung giờ Flash Sale cho Facebook"""
        slot_time = promo.get("slot_time", "12:00")
        slot_title = promo.get("slot_title", "Giờ Vàng Săn Sale")
        campaign_name = promo.get("campaign_name", "SIÊU HỘI SĂN SALE SHOPEE")
        aff_url = promo.get("aff_url") or "https://shopee.vn"
        vouchers = promo.get("vouchers", [])

        voucher_lines = []
        for v in vouchers[:4]:
            voucher_lines.append(f"• {v.get('badge')}: {v.get('desc')}")
        vouchers_str = "\n".join(voucher_lines) if voucher_lines else "• Freeship 0Đ & Giảm giá 50%"

        post = (
            f"⏰ BÁO THỨC SĂN SALE: CHUẨN BỊ ĐẾN KHUNG {slot_time} RỒI CẢ NHÀ ƠI! 🔥\n\n"
            f"[{campaign_name}]\n"
            f"Khung giờ {slot_time} chuẩn bị tung loạt deal cực sâu:\n"
            f"{slot_title}\n\n"
            f"Danh sách mã hời chuẩn bị mở đợt này:\n"
            f"{vouchers_str}\n\n"
            f"Mn nhanh tay vào lưu mã trước rồi bỏ đồ sẵn vào giỏ nha, đến đúng giờ là chốt đơn kẻo mã bay màu trong 30s đó!\n"
            f"🔗 Link vào lưu mã và chốt deal: {aff_url}"
        )
        return post

    @classmethod
    def generate_community_invite_cta(cls, community_url: str = "", community_name: str = "") -> str:
        """Tạo đoạn Call-to-action kêu gọi tham gia cộng đồng riêng khéo léo"""
        from config.settings import COMMUNITY_INVITE_URL, COMMUNITY_NAME
        url = community_url or os.getenv("COMMUNITY_INVITE_URL", COMMUNITY_INVITE_URL)
        name = community_name or os.getenv("COMMUNITY_NAME", COMMUNITY_NAME) or "Hội Săn Deal Shopee VIP"

        if not url:
            return ""

        cta = (
            f"\n\n💬 THAM GIA CỘNG ĐỒNG SĂN SALE:\n"
            f"Do mã giảm giá và deal 1K thường hết lượt trong 1-2 phút, anh em vào nhóm [{name}] để bot tự động nhắc trước 15 phút kẻo lỡ nhé!\n"
            f"👉 Tham Gia Nhóm Săn Deal Tại Đây: {url}"
        )
        return cta

    @classmethod
    def generate_general_deal_roundup(cls, deals: List[Dict], promo_package: Optional[Dict] = None, community_url: str = "", community_name: str = "") -> str:
        """
        Tạo bài đăng tổng hợp Top Deal Sốc Trong Ngày (Daily Mega Roundup) cho các nhóm săn deal chung.
        Gồm deal hời đa ngành + deal 1K + CTA mời vào nhóm riêng.
        """
        now_str = datetime.now().strftime("%d/%m/%Y")
        lines = [
            f"🔥 [TỔNG HỢP DEAL SỐC & MÃ GIẢM GIÁ SHOPEE HÔM NAY {now_str}] 🔥\n",
            "Chào cả nhà, mình tổng hợp lại loạt deal ngon nhất ngày hôm nay từ nhiều ngành hàng để mọi người tiện lưu và chốt đơn:\n"
        ]

        # 1. Điểm qua các deal giảm sâu
        deal_items = []
        for idx, d in enumerate(deals[:6], 1):
            name = d.get("name", "")[:45]
            price_sale = f"{int(d.get('price_sale', 0)):,}đ".replace(",", ".")
            price_orig = f"{int(d.get('price_original', 0)):,}đ".replace(",", ".")
            discount = d.get("discount_percent", 0)
            url = d.get("bridge_url") or d.get("aff_url") or d.get("item_url") or "https://shopee.vn"
            badge = " [Đáy 30N]" if "LOW" in str(d.get("price_badge", "")) else ""
            deal_items.append(
                f"{idx}. {name}{badge}\n"
                f"   💰 Giá sale: {price_sale} (Gốc: {price_orig} - Giảm {discount}%)\n"
                f"   👉 Link lấy deal: {url}"
            )

        lines.append("\n".join(deal_items))

        # 2. Bổ sung khung giờ vàng sắp tới nếu có
        if promo_package and promo_package.get("upcoming_slot"):
            slot = promo_package["upcoming_slot"]
            lines.append(f"\n⏰ Khung Giờ Vàng Tiếp Theo: {slot.get('slot')} - {slot.get('title')}")
            lines.append("   (Nhớ vào giỏ hàng trước 5 phút để áp mã Freeship 0Đ)")

        # 3. CTA Kéo Member về nhóm riêng
        from config.settings import COMMUNITY_INVITE_URL, COMMUNITY_NAME
        url = community_url or os.getenv("COMMUNITY_INVITE_URL", COMMUNITY_INVITE_URL)
        name = community_name or os.getenv("COMMUNITY_NAME", COMMUNITY_NAME) or "Hội Săn Deal Shopee VIP"
        if url:
            lines.append(
                f"\n📌 Lưu ý: Vì deal ngon và mã 50% thường bay màu rất nhanh, mọi người có thể vào nhóm kín [{name}] để bot tự động hú trước 15p nha:\n"
                f"👉 Link vào nhóm: {url}"
            )

        return "\n".join(lines)

    @classmethod
    def generate_flash_sale_schedule_post(cls, promo_slots: Optional[List[Dict]] = None, community_url: str = "", community_name: str = "") -> str:
        """
        Tạo bài đăng Lịch Trình Khung Giờ Săn Sale trong ngày cho nhóm Facebook chung.
        """
        now_str = datetime.now().strftime("%d/%m/%Y")
        post = (
            f"📅 LỊCH SĂN SALE & KHUNG GIỜ MỞ MÃ SHOPEE HÔM NAY ({now_str}) ⚡\n\n"
            f"Anh em lưu lại lịch 6 khung giờ vàng này để canh vào giỏ hàng nhé:\n\n"
            f"🌙 00:00: Đêm Sale Khủng - Bung voucher 50% & Freeship Đơn 0Đ toàn sàn\n"
            f"🌅 09:00: Săn Deal Hàng Hiệu Mall - Giảm đến 50% chính hãng\n"
            f"☀️ 12:00: Nửa Ngày Nửa Giá - Loạt deal 1K & voucher chớp nhoáng\n"
            f"🕒 15:00: Giờ Vàng Quốc Tế - Freeship Xtra không giới hạn\n"
            f"🌆 18:00: Giờ Tan Tầm - Flash sale đồ gia dụng & công nghệ sốc\n"
            f"🌃 21:00: Chợ Đêm Đồng Giá 1K - Gắp hàng về giỏ ship tận giường\n\n"
            f"💡 Mẹo canh mã: Cho sẵn món đồ vào giỏ trước 10 phút, đúng giờ là bấm thanh toán liền tay.\n"
        )
        from config.settings import COMMUNITY_INVITE_URL, COMMUNITY_NAME
        url = community_url or os.getenv("COMMUNITY_INVITE_URL", COMMUNITY_INVITE_URL)
        name = community_name or os.getenv("COMMUNITY_NAME", COMMUNITY_NAME) or "Hội Săn Deal Shopee VIP"
        if url:
            post += (
                f"\n👉 Anh em muốn được bot hú tự động trước 15p mỗi khung giờ thì vào nhóm nha: {url}"
            )
        return post

    @classmethod
    def generate_voucher_secret_tips_post(cls, community_url: str = "", community_name: str = "") -> str:
        """Tạo bài viết chia sẻ mẹo xếp chồng 3 mã giảm giá trên Shopee và PR group"""
        from config.settings import COMMUNITY_INVITE_URL, COMMUNITY_NAME
        url = community_url or os.getenv("COMMUNITY_INVITE_URL", COMMUNITY_INVITE_URL)
        name = community_name or os.getenv("COMMUNITY_NAME", COMMUNITY_NAME) or "Hội Săn Deal Shopee VIP"
        post = (
            "💡 [BÍ KÍP SHOPEE] CÁCH ÁP DỤNG CÙNG LÚC 3 TẦNG MÃ GIẢM GIÁ TIẾT KIỆM TỐI ĐA 🎁\n\n"
            "Nhiều bạn vẫn mua hàng với giá gốc mà không biết Shopee cho phép áp tối đa 3 loại mã trong 1 đơn hàng:\n"
            "1️⃣ Tầng 1: Mã Miễn Phí Vận Chuyển (Freeship Xtra / Freeship 0Đ)\n"
            "2️⃣ Tầng 2: Voucher từ Shopee (Mã hoàn xu / Mã giảm 10% - 50% toàn sàn)\n"
            "3️⃣ Tầng 3: Voucher từ Shop (Bấm vào gian hàng của Shop để bấm 'Lưu mã' trước)\n\n"
            "👉 Hãy cho sẵn hàng vào giỏ, kiểm tra xem đủ cả 3 ô mã giảm giá chưa rồi mới bấm 'Đặt Hàng' nha!\n"
        )
        if url:
            post += f"\n🔥 Danh sách mã giảm giá mới cập nhật liên tục mỗi ngày tại nhóm [{name}]: {url}"
        return post

    @classmethod
    def generate_manual_vouchers_post(cls, vouchers: List[Dict], wallet_url: str = "", campaign_date: str = "") -> str:
        """
        Dạng 1: Bài danh sách các mã nhập tay còn lượt trong ngày + link list áp dụng (Chuẩn thực chiến affiliate)
        """
        now = datetime.now()
        date_str = campaign_date or f"{now.day}.{now.month}"
        wallet = wallet_url or "https://s.shopee.vn/1LPJSANV7v"

        lines = [
            f"Các mã nhập tay còn lượt {date_str}",
            "Mời ace check list áp đc 🤓\n",
            f"B1: Mở ví voucher: {wallet}\n",
            "B2: Nhập các mã vào (chạm để tự động copy)\n"
        ]

        for v in vouchers:
            code = v.get("code", "").strip()
            desc = v.get("discount_desc", "").strip()
            apply_url = v.get("apply_url", "").strip()
            if not code:
                continue
            if apply_url:
                lines.append(f"• {code} {desc}. Áp list: {apply_url}")
            else:
                lines.append(f"• {code} {desc}")

        return "\n".join(lines)

    @classmethod
    def generate_voucher_back_alert_post(
        cls,
        slot_time: str = "12H",
        banner_1: str = "",
        banner_2: str = "",
        remaining_slots: str = "",
        campaign_date: str = "",
        discount_highlight: str = "50% max 200k"
    ) -> str:
        """
        Dạng 2: Bài báo giờ back mã kèm 2 link banner & mẹo săn thực chiến (canh F5 / thanh toán / time.is)
        """
        now = datetime.now()
        date_str = campaign_date or f"{now.day}.{now.month}"
        b1 = banner_1 or "https://s.shopee.vn/6q0WqKvmkf"
        b2 = banner_2 or "https://s.shopee.vn/7AdjQWuTmi"
        rem_slots = remaining_slots or "12H, 15H, 18H, 20H"
        rem_count = len([s for s in rem_slots.split(",") if s.strip()]) if rem_slots else 4

        post = (
            f"{slot_time} trưa back {discount_highlight} và các mã Extra sẵn ví 🔥\n"
            f"Có công mài sắt có ngày ôke\n"
            f"{rem_count} khung back còn lại hnay {rem_slots} = chẳng có lẽ mình lại k húp đc khung nào 🤡\n\n"
            f"Săn tại 1 trong 2 banner\n"
            f"Banner 1: {b1}\n"
            f"Banner 2 (dễ kéo từ trên xuống để load lại banner hơn): {b2}\n\n"
            f"- Hạn cuối hnay {date_str}. Phải lưu xong mới dùng đc 😎\n\n"
            f"* MẸO SĂN:\n"
            f"❌ 1. Ai chưa từng Lưu > đúng giờ vào đi vào lại/ load đi load lại banner, khoảng 10-50s sẽ hiện nút Lưu\n"
            f"Lưu xong áp thử, nếu Hết thì chuyển bước 2 bên dưới\n\n"
            f"✅ 2. Ai đã Lưu đc rồi > gần đến h đợi sẵn canh sẵn ở bước thanh toán, chọn sẵn Freeship > load đi load lại phần chọn mã > nhảy giờ thì cứ spam back ra vào lại tiếp > hiện mã là chọn và chốt. (Mã có thể hiện chậm 5-25s)\n\n"
            f"- Các khung sau làm tương tự - 0H, 9H, 12H, 15H, 18H, 20H từ nay tới hết {date_str}\n"
            f"- Dùng web time.is/ các app đồng hồ nổi - để check chính xác từng miligiây"
        )
        return post

    @classmethod
    def generate_flash_high_value_post(cls, items: Optional[List[Dict]] = None) -> str:
        """
        Dạng 3: Bắn nhanh loạt mã % lớn / giá trị cao (25% 3Tr, 25% 2.5Tr)
        """
        default_items = [
            {"label": "25% 3Tr", "url": "https://s.shopee.vn/5LCAq6w5Uc"},
            {"label": "25% 2.5Tr", "url": "https://s.shopee.vn/5VVb2PvS9f"}
        ]
        target = items or default_items
        lines = [
            "Lên loạt 25% 24% kìa 🔥\n"
        ]
        for it in target:
            lbl = it.get("label") or it.get("code") or "25%"
            url = it.get("url") or it.get("apply_url") or ""
            lines.append(f"📍 {lbl}: {url}")
        return "\n".join(lines)

    @classmethod
    def generate_flat_price_deal_post(
        cls,
        slot_time: str = "12H",
        price_label: str = "99K",
        deal_url: str = "",
        custom_tip: str = ""
    ) -> str:
        """
        Dạng 4: Bài Deal đồng giá theo khung giờ (12H 99k, 0H 1k) kèm mẹo bật/tắt áp xu 0.1s
        """
        url = deal_url or "https://s.shopee.vn/5q8Qf8NVyC"
        default_tip = "Chờ sẵn bước mua hàng - tới giờ 0.1s bấm bật/tắt áp xu > nhảy giá chốt liền. Mỗi deal chỉ săn số lượng 1. Sp nào có nhiều phân loại nhắn trc hỏi sốp"
        tip = custom_tip or default_tip

        post = (
            f"✨🔥 {slot_time}: Deal đồng giá {price_label}: {url}\n"
            f"Mời ace ngó qua list xem có món nào hợp lý k 🤓\n\n"
            f"* MẸO SĂN: {tip}"
        )
        return post

    @classmethod
    def generate_social_copilot_pack(
        cls,
        deal: Dict,
        angle: str = "review",
        share_url: str = "",
        lazada_url: str = ""
    ) -> Dict[str, str]:
        """
        Bộ sinh nội dung tiếp thị Mạng Xã Hội (Facebook Groups, Threads, Comments, Bio)
        Gồm 4 góc độ tâm lý mua hàng thực chiến:
        1. 'review': Góc review trải nghiệm thật (không bị admin FB coi là spam)
        2. 'loss_leader': Deal mồi 1K & Freeship 0Đ (dễ click nhất, kích hoạt cookie 7 ngày)
        3. 'price_compare': So sánh giá Shopee vs Lazada (kích thích tranh luận, ăn hoa hồng 2 sàn)
        4. 'flash_sale': Cảnh báo giờ vàng sale chạm đáy 30 ngày (FOMO)
        """
        name = deal.get("name", "Sản phẩm ưu đãi hot")
        price_sale = int(deal.get("price_sale", 0))
        price_orig = int(deal.get("price_original", 0))
        discount = int(deal.get("discount_percent", 0))
        rating = round(float(deal.get("rating_star", 5.0) or 5.0), 1)
        sold = int(deal.get("historical_sold", 0) or 0)
        platform = str(deal.get("platform", "SHOPEE")).upper()
        target_link = share_url or deal.get("aff_url") or deal.get("item_url", "")
        cat_name = deal.get("category_name", "Đời Sống")

        badge = str(deal.get("price_badge", ""))
        verdict = "Đáy lịch sử 30 ngày qua" if "LOW" in badge else ("Giảm thật đã kiểm tra" if "REAL" in badge else "Flash Sale chính hãng")

        # 1. Góc Review trải nghiệm thật (Review Style)
        if angle == "review":
            caption = (
                f"Góc review chân thật cho bác nào đang ngắm em '{name}' này nha 👇\n\n"
                f"Mình vừa check lại giá hôm nay thì thấy giảm sâu thật, từ {price_orig:,}đ còn đúng {price_sale:,}đ (-{discount}%).\n"
                f"• Điểm cộng: Shop chính hãng, hơn {sold:,} lượt mua, đánh giá {rating}⭐ cực nhiều feedback ảnh thật.\n"
                f"• Đánh giá giá: [{verdict}].\n"
                f"• Nhược điểm: Đợt sale nhiều người săn nên các mã giảm thêm 15% - 20% ở giỏ hàng bay khá nhanh.\n\n"
                f"Bác nào cần thì tranh thủ nghía qua link shop Mall bên dưới nha:\n"
                f"👉 Link săn sale chính hãng: {target_link}\n\n"
                f"#reviewcotam #giamgiathat #sandeal #shopee"
            )

        # 2. Deal Mồi 1K - Freeship 0Đ (Loss-Leader Cookie Primer)
        elif angle == "loss_leader":
            caption = (
                f"🚨 [KÈO 1K FREESHIP 0Đ - MỞ GIỎ ĂN MÃ] 🚨\n\n"
                f"Shopee đang xả kho em '{name}' này giá đúng {price_sale:,}đ (gốc {price_orig:,}đ) luôn mn ơi!\n"
                f"Mẹo nhỏ cho anh em săn sale: Món này áp được mã Freeship 0Đ tại bước thanh toán. Anh em nhặt món này vào giỏ để kích hoạt đơn và ghim ưu đãi cực hời nha.\n\n"
                f"⭐ Đã bán: {sold:,} sản phẩm | Đánh giá: {rating}⭐\n"
                f"Số lượng có hạn trong khung giờ này thôi, anh em nhặt nhanh kẻo hết slot:\n"
                f"🔗 Link chốt deal 1K: {target_link}\n\n"
                f"#deal1k #freeship0d #sansale #shopeehaul"
            )

        # 3. So Sánh Giá Shopee vs Lazada (Price Arbitrage / Dual Platform)
        elif angle == "price_compare":
            laz_link = lazada_url or "https://c.lazada.vn"
            laz_price = int(price_sale * 1.05)
            caption = (
                f"⚖️ [CHECK GIÁ ĐA SÀN] Con '{name}' này đang sale sốc hôm nay:\n\n"
                f"Vừa soi giá cùng sản phẩm chính hãng giữa 2 sàn cho anh em đỡ mất công tìm:\n"
                f"🟠 Bên Shopee: {price_sale:,}đ (Giảm {discount}% - {verdict})\n"
                f"🔵 Bên Lazada: ~{laz_price:,}đ (Đang có voucher tích lũy)\n\n"
                f"Bác nào có sẵn mã FreeShip sàn nào thì chốt sàn đó cho tiện nhé:\n"
                f"👉 Link Shopee Mall: {target_link}\n"
                f"👉 Link LazMall: {laz_link}\n\n"
                f"Theo các bác thì bên nào ship nhanh hơn? Mn để lại review bên dưới nha! 👇\n"
                f"#sosanhgia #shopeevslazada #sansale #review"
            )

        # 4. Cảnh báo Flash Sale sắp hết giờ (FOMO / Urgency)
        else: # flash_sale
            caption = (
                f"⚡ CẢNH BÁO GIỜ VÀNG FLASH SALE SẮP ĐÓNG ⚡\n\n"
                f"Deal sốc em '{name}' chỉ áp dụng trong khung giờ hôm nay:\n"
                f"• Giá niêm yết: {price_orig:,}đ\n"
                f"• Giá Flash Sale: {price_sale:,}đ ➡️ Tiết kiệm ngay {price_orig - price_sale:,}đ\n"
                f"• Chứng nhận: ⭐ {rating} sao từ {sold:,} người mua thực tế\n"
                f"• Tình trạng: [{verdict}]\n\n"
                f"💡 Hướng dẫn 2 bước:\n"
                f"1. Bấm link bên dưới để mở thẳng ứng dụng\n"
                f"2. Bấm 'Mua ngay' và áp thêm mã Freeship 0Đ tại giỏ hàng\n\n"
                f"👉 Chốt ngay kẻo hết suất: {target_link}\n\n"
                f"#flashsale #shopeevn #dealhot #muasamsieure"
            )

        return {
            "caption": caption,
            "angle": angle,
            "item_name": name,
            "target_link": target_link,
            "platform": platform,
            "price_sale": str(price_sale),
            "discount_percent": str(discount)
        }

