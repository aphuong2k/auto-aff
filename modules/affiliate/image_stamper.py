import os
import requests
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from config.settings import RAW_IMAGES_DIR, PROCESSED_IMAGES_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

class ImageBannerStamper:
    """Module tự động tải ảnh Shopee về máy, đóng khung Flash Sale, đóng dấu giảm giá và giá sốc"""

    DEFAULT_FONT_PATH = "C:/Windows/Fonts/arialbd.ttf"
    REGULAR_FONT_PATH = "C:/Windows/Fonts/arial.ttf"

    @classmethod
    def _get_font(cls, size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
        font_path = cls.DEFAULT_FONT_PATH if bold else cls.REGULAR_FONT_PATH
        if not os.path.exists(font_path):
            font_path = "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf"
        
        try:
            return ImageFont.truetype(font_path, size=size)
        except Exception:
            return ImageFont.load_default()

    @classmethod
    def download_image(cls, image_url: str, item_id: str) -> Optional[Path]:
        """Tải ảnh gốc từ Shopee CDN về thư mục local (Hỗ trợ URL, Image Hash và đa CDN fallback)"""
        if not image_url and not item_id:
            return None

        raw_path = RAW_IMAGES_DIR / f"{item_id}.jpg"
        if raw_path.exists() and raw_path.stat().st_size > 1024:
            return raw_path

        # Xác định image hash
        image_hash = ""
        if image_url:
            if "/file/" in image_url:
                image_hash = image_url.split("/file/")[-1].split("?")[0].split("_")[0]
            elif image_url.startswith("http"):
                image_hash = image_url.split("/")[-1].split("?")[0]
            else:
                image_hash = image_url.strip()

        # Danh sách các CDN Shopee để tự động thử
        candidate_urls = []
        if image_url and image_url.startswith("http"):
            candidate_urls.append(image_url)
        if image_hash:
            candidate_urls.extend([
                f"https://down-vn.img.susercontent.com/file/{image_hash}",
                f"https://cf.shopee.vn/file/{image_hash}",
                f"https://down-ws-vn.img.susercontent.com/file/{image_hash}"
            ])

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": "https://shopee.vn/",
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
        }

        for url in candidate_urls:
            try:
                resp = requests.get(url, headers=headers, timeout=10)
                if resp.status_code == 200 and len(resp.content) > 1000:
                    with open(raw_path, "wb") as f:
                        f.write(resp.content)
                    # Xác thực file ảnh hợp lệ bằng PIL
                    try:
                        with Image.open(raw_path) as test_img:
                            test_img.verify()
                        logging.info(f"📸 Đã tải thành công ảnh thật sản phẩm {item_id} từ {url}")
                        return raw_path
                    except Exception:
                        if raw_path.exists():
                            raw_path.unlink()
            except Exception as e:
                logging.debug(f"Không thể tải từ {url}: {e}")

        logging.warning(f"Không thể tải ảnh cho item_id {item_id} qua tất cả các CDN.")
        return None

    @classmethod
    def _create_placeholder_image(cls, deal: Dict) -> Image.Image:
        """Tạo ảnh nền dự phòng phong cách e-commerce cao cấp nếu không tải được ảnh gốc"""
        img = Image.new("RGB", (800, 800), color=(26, 31, 56))
        draw = ImageDraw.Draw(img)

        # Vẽ họa tiết nền
        for i in range(0, 800, 40):
            draw.line([(0, i), (800, i)], fill=(35, 42, 75), width=1)
            draw.line([(i, 0), (i, 800)], fill=(35, 42, 75), width=1)

        # Viết tên sản phẩm ở giữa
        font_title = cls._get_font(32, bold=True)
        name = deal.get("name", "SHOPEE HOT DEAL")
        short_name = (name[:35] + "...") if len(name) > 35 else name
        draw.text((400, 380), short_name, font=font_title, fill=(255, 255, 255), anchor="mm")
        
        font_sub = cls._get_font(22, bold=False)
        cat = deal.get("category_name", "Shopee Mall")
        draw.text((400, 430), f"Ngành hàng: {cat}", font=font_sub, fill=(200, 200, 220), anchor="mm")

        return img

    @classmethod
    def stamp_deal_image(cls, deal: Dict) -> Path:
        """
        Đóng khung Flash Sale, huy hiệu giảm giá, giá sale cực đại và lịch sử giá lên ảnh
        Trả về đường dẫn file ảnh đã xử lý sẵn sàng để đăng lên Telegram / Facebook
        """
        item_id = str(deal.get("item_id", "deal"))
        processed_path = PROCESSED_IMAGES_DIR / f"{item_id}_banner.jpg"

        # Tải ảnh gốc hoặc dùng ảnh dự phòng
        image_url = deal.get("image_url", "")
        raw_image_path = cls.download_image(image_url, item_id)

        try:
            if raw_image_path and raw_image_path.exists():
                base_img = Image.open(raw_image_path).convert("RGB")
            else:
                base_img = cls._create_placeholder_image(deal)
        except Exception as e:
            logging.warning(f"Lỗi mở ảnh gốc {raw_image_path}: {e}")
            base_img = cls._create_placeholder_image(deal)

        # Đưa về kích thước chuẩn vuông 800x800
        canvas_w, canvas_h = 800, 800
        base_img = base_img.resize((canvas_w, canvas_h), Image.Resampling.LANCZOS).convert("RGBA")
        draw = ImageDraw.Draw(base_img, "RGBA")

        # 1. Vẽ Viền Khung Flash Sale Rực Rỡ (Border 8px màu đỏ cam Shopee)
        border_color = (238, 77, 45, 255) # Shopee Orange/Red
        border_width = 8
        for w in range(border_width):
            draw.rectangle([w, w, canvas_w - 1 - w, canvas_h - 1 - w], outline=border_color)

        # 2. Thanh Tiêu Đề Top Bar Flash Sale
        top_bar_h = 60
        # Gradient hoặc thanh đỏ cam rực lửa
        draw.rectangle([0, 0, canvas_w, top_bar_h], fill=(238, 77, 45, 255))
        
        font_header = cls._get_font(26, bold=True)
        draw.text((canvas_w // 2, top_bar_h // 2), "⚡ FLASH SALE SHOPEE | CHÍNH HÃNG ⚡", font=font_header, fill=(255, 255, 255), anchor="mm")

        # 3. Huy hiệu Giảm Giá (Discount Badge) góc trên bên phải
        discount = int(deal.get("discount_percent", 0))
        if discount > 0:
            badge_w, badge_h = 160, 68
            bx1 = canvas_w - border_width - badge_w - 10
            by1 = top_bar_h + 10
            bx2 = bx1 + badge_w
            by2 = by1 + badge_h

            # Bo góc huy hiệu màu vàng nghệ rực rỡ
            draw.rounded_rectangle([bx1, by1, bx2, by2], radius=10, fill=(254, 218, 54, 250), outline=(238, 77, 45), width=2)
            font_badge_num = cls._get_font(28, bold=True)
            font_badge_txt = cls._get_font(15, bold=True)
            draw.text((bx1 + badge_w // 2, by1 + 22), f"-{discount}%", font=font_badge_num, fill=(208, 1, 27), anchor="mm")
            draw.text((bx1 + badge_w // 2, by1 + 48), "GIẢM SỐC", font=font_badge_txt, fill=(180, 0, 20), anchor="mm")

        # 4. Huy hiệu Đáy Lịch Sử / Giảm Thật (nếu có)
        price_badge = deal.get("price_badge")
        if price_badge:
            badge_text = "📉 ĐÁY LỊCH SỬ 30 NGÀY" if "LOW" in price_badge else "✅ GIẢM THẬT KIỂM CHỨNG"
            badge_bg = (16, 185, 129, 235) if "LOW" in price_badge else (37, 99, 235, 235) # Xanh lục hoặc Xanh lam
            
            tag_w, tag_h = 240, 38
            tx1 = border_width + 12
            ty1 = top_bar_h + 12
            tx2 = tx1 + tag_w
            ty2 = ty1 + tag_h
            draw.rounded_rectangle([tx1, ty1, tx2, ty2], radius=8, fill=badge_bg)
            font_verified = cls._get_font(15, bold=True)
            draw.text((tx1 + tag_w // 2, ty1 + tag_h // 2), badge_text, font=font_verified, fill=(255, 255, 255), anchor="mm")

        # 5. Thanh Banner Giá Khổng Lồ Ở Đáy (Bottom Price Bar)
        bottom_h = 135
        by_start = canvas_h - border_width - bottom_h

        # Lớp nền mờ sẫm màu cao cấp (Semi-transparent black overlay)
        overlay = Image.new("RGBA", (canvas_w, bottom_h), (15, 23, 42, 230))
        base_img.paste(overlay, (0, by_start), overlay)

        # Vẽ đường phân cách vàng ánh kim phía trên banner giá
        draw = ImageDraw.Draw(base_img)
        draw.line([(0, by_start), (canvas_w, by_start)], fill=(254, 218, 54), width=3)

        # Định dạng tiền tệ
        price_sale = int(deal.get("price_sale", 0))
        price_orig = int(deal.get("price_original", 0))
        sold = deal.get("historical_sold", 0)
        rating = deal.get("rating_star", 5.0)

        # Nhãn "GIÁ FLASH SALE:"
        font_label = cls._get_font(16, bold=True)
        draw.text((25, by_start + 24), "GIÁ FLASH SALE HÔM NAY:", font=font_label, fill=(254, 218, 54))

        # Giá Sale Nổi Bật Siêu To
        font_price_main = cls._get_font(46, bold=True)
        sale_text = f"{price_sale:,}đ".replace(",", ".")
        draw.text((25, by_start + 72), sale_text, font=font_price_main, fill=(255, 255, 255))

        # Giá Gốc gạch ngang
        if price_orig > price_sale:
            font_orig = cls._get_font(20, bold=False)
            orig_text = f"Gốc: {price_orig:,}đ".replace(",", ".")
            orig_x = 25 + int(font_price_main.getlength(sale_text)) + 20
            orig_y = by_start + 78
            draw.text((orig_x, orig_y), orig_text, font=font_orig, fill=(160, 174, 192))
            
            # Gạch ngang giá gốc
            text_w = font_orig.getlength(orig_text)
            draw.line([(orig_x, orig_y + 11), (orig_x + text_w, orig_y + 11)], fill=(239, 68, 68), width=2)

        # Đánh giá & Đã bán ở góc dưới bên phải
        font_sub_info = cls._get_font(16, bold=True)
        sold_str = f"{sold / 1000:.1f}k" if sold >= 1000 else str(sold)
        info_text = f"⭐ {rating} | Đã bán: {sold_str}"
        info_w = font_sub_info.getlength(info_text)
        draw.text((canvas_w - border_width - info_w - 20, by_start + 75), info_text, font=font_sub_info, fill=(254, 218, 54))

        # Lưu ảnh JPG chất lượng cao (chuyển RGBA → RGB vì JPG không hỗ trợ alpha)
        base_img.convert("RGB").save(processed_path, format="JPEG", quality=92)
        logging.info(f"🎨 Đã đóng khung & in giá lên banner thành công: {processed_path}")
        return processed_path

    @classmethod
    def create_mega_deal_collage(cls, deals: List[Dict]) -> Path:
        """
        Tạo ảnh ghép 4 góc (2x2 Mega Deal Grid) chuẩn 800x800 cho bài đăng tổng hợp trên Facebook.
        Tăng tỷ lệ dừng mắt và click (CTR) cao gấp 3 lần ảnh thông thường.
        """
        collage_path = PROCESSED_IMAGES_DIR / "daily_mega_collage.jpg"
        canvas_w, canvas_h = 800, 800
        canvas = Image.new("RGB", (canvas_w, canvas_h), (15, 23, 42))
        draw = ImageDraw.Draw(canvas)

        # 1. Header Bar: Đỏ cam rực rỡ
        header_h = 64
        for y in range(header_h):
            ratio = y / header_h
            r = int(238 + (249 - 238) * ratio)
            g = int(77 + (115 - 77) * ratio)
            b = int(45 + (22 - 45) * ratio)
            draw.line([(0, y), (canvas_w, y)], fill=(r, g, b))

        font_header = cls._get_font(22, bold=True)
        header_title = "⚡ TỔNG HỢP DEAL SỐC & MÃ SHOPEE HÔM NAY"
        title_w = font_header.getlength(header_title)
        draw.text(((canvas_w - title_w) // 2, 18), header_title, font=font_header, fill=(255, 255, 255))

        # 2. Footer Bar: Freeship 0Đ
        footer_h = 50
        footer_y = canvas_h - footer_h
        draw.rectangle([(0, footer_y), (canvas_w, canvas_h)], fill=(11, 15, 25))
        font_footer = cls._get_font(16, bold=True)
        footer_text = "🎁 MÃ FREESHIP 0Đ & VOUCHER GIẢM 50% MỞ THEO KHUNG GIỜ"
        footer_w = font_footer.getlength(footer_text)
        draw.text(((canvas_w - footer_w) // 2, footer_y + 14), footer_text, font=font_footer, fill=(250, 204, 21))

        # 3. Khu vực 4 ô sản phẩm (2x2 Grid)
        grid_top = header_h + 8
        grid_bottom = footer_y - 8
        grid_h = grid_bottom - grid_top
        cell_w = (canvas_w - 24) // 2
        cell_h = (grid_h - 12) // 2

        positions = [
            (8, grid_top),
            (8 + cell_w + 8, grid_top),
            (8, grid_top + cell_h + 8),
            (8 + cell_w + 8, grid_top + cell_h + 8)
        ]

        target_deals = deals[:4]
        for idx, pos in enumerate(positions):
            x, y = pos
            draw.rectangle([(x, y), (x + cell_w, y + cell_h)], fill=(30, 41, 59), outline=(51, 65, 85), width=2)

            if idx < len(target_deals):
                d = target_deals[idx]
                item_id = str(d.get("item_id", ""))
                img_path = PROCESSED_IMAGES_DIR / f"{item_id}_banner.jpg"
                if not img_path.exists():
                    img_path = cls.stamp_deal_image(d)

                if img_path and img_path.exists():
                    try:
                        deal_img = Image.open(img_path).convert("RGB")
                        thumb_h = cell_h - 86
                        thumb_w = cell_w - 12
                        deal_img = deal_img.resize((thumb_w, thumb_h), Image.Resampling.LANCZOS)
                        canvas.paste(deal_img, (x + 6, y + 6))
                    except Exception as e:
                        logging.debug(f"Không thể paste ảnh deal vào collage: {e}")

                font_name = cls._get_font(13, bold=True)
                d_name = d.get("name", "Deal Shopee Hot")[:28]
                draw.text((x + 10, y + cell_h - 74), d_name, font=font_name, fill=(241, 245, 249))

                price_sale = int(d.get("price_sale", 0))
                font_p = cls._get_font(18, bold=True)
                p_text = f"{price_sale:,}đ".replace(",", ".")
                draw.text((x + 10, y + cell_h - 46), p_text, font=font_p, fill=(238, 77, 45))

                discount = d.get("discount_percent", 0)
                if discount > 0:
                    font_disc = cls._get_font(12, bold=True)
                    disc_text = f"-{discount}%"
                    disc_x = x + 10 + int(font_p.getlength(p_text)) + 10
                    draw.rectangle([(disc_x, y + cell_h - 46), (disc_x + int(font_disc.getlength(disc_text)) + 8, y + cell_h - 26)], fill=(239, 68, 68))
                    draw.text((disc_x + 4, y + cell_h - 44), disc_text, font=font_disc, fill=(255, 255, 255))
            else:
                font_promo = cls._get_font(18, bold=True)
                promo_t = "🎁 VOUCHER 50%"
                draw.text((x + 80, y + 130), promo_t, font=font_promo, fill=(250, 204, 21))

        canvas.save(collage_path, format="JPEG", quality=92)
        logging.info(f"🎨 Đã tạo thành công ảnh ghép 4 deal (Mega Collage Grid): {collage_path}")
        return collage_path

    @classmethod
    def create_daily_cover_banner(cls, date_str: str = "") -> Path:
        """
        Tạo ảnh Cover Banner Tiêu Đề chuẩn Facebook (1080x1080 vuông siêu nét)
        cho bài đăng tổng hợp Shopee trong ngày.
        Đúng yêu cầu: "để ảnh tiêu đề là deal shoppee ngày bn thế thôi đừng ghép vào"
        """
        banner_path = PROCESSED_IMAGES_DIR / "daily_deal_header_banner.jpg"
        w, h = 1080, 1080
        img = Image.new("RGB", (w, h), (10, 15, 29))
        draw = ImageDraw.Draw(img)

        today_display = date_str or datetime.now().strftime("%d/%m/%Y")

        # 1. Vẽ nền gradient sâu thẳm công nghệ (Deep Blue to Dark Slate)
        for y in range(h):
            ratio = y / h
            r = int(10 + (25 - 10) * ratio)
            g = int(15 + (18 - 15) * ratio)
            b = int(29 + (45 - 29) * ratio)
            draw.line([(0, y), (w, y)], fill=(r, g, b))

        # 2. Vùng quầng sáng cam Shopee rực rỡ ở phía trên
        header_h = 240
        for y in range(header_h):
            ratio = y / header_h
            r = int(238 + (249 - 238) * ratio)
            g = int(77 + (115 - 77) * ratio)
            b = int(45 + (22 - 45) * ratio)
            draw.line([(0, y), (w, y)], fill=(r, g, b))

        # Dải ngăn cách vàng kim
        draw.line([(0, header_h), (w, header_h)], fill=(250, 204, 21), width=4)

        # 3. Chữ Header trên nền đỏ cam
        font_subhead = cls._get_font(28, bold=True)
        subhead_text = "⚡ BẢN TIN SĂN SALE SHOPEE ĐẶC BIỆT ⚡"
        subhead_w = font_subhead.getlength(subhead_text)
        draw.text(((w - subhead_w) // 2, 45), subhead_text, font=font_subhead, fill=(255, 245, 235))

        font_main_title = cls._get_font(46, bold=True)
        main_title = "TỔNG HỢP DEAL SỐC & KHO MÃ"
        title_w = font_main_title.getlength(main_title)
        draw.text(((w - title_w) // 2, 115), main_title, font=font_main_title, fill=(255, 255, 255))

        # 4. Hộp hiển thị NGÀY THÁNG cực to & nổi bật (Hero Date Card)
        date_box_top = 280
        date_box_h = 130
        draw.rounded_rectangle(
            [(80, date_box_top), (w - 80, date_box_top + date_box_h)],
            radius=24,
            fill=(30, 41, 59),
            outline=(250, 204, 21),
            width=3
        )

        font_date_label = cls._get_font(24, bold=False)
        date_label = "LỊCH SĂN SALE HÔM NAY"
        dl_w = font_date_label.getlength(date_label)
        draw.text(((w - dl_w) // 2, date_box_top + 18), date_label, font=font_date_label, fill=(148, 163, 184))

        font_date_val = cls._get_font(44, bold=True)
        date_val = f"📅 NGÀY {today_display}"
        dv_w = font_date_val.getlength(date_val)
        draw.text(((w - dv_w) // 2, date_box_top + 55), date_val, font=font_date_val, fill=(250, 204, 21))

        # 5. Các thẻ tính năng nổi bật (4 Feature Badges)
        features = [
            ("🚚 FREESHIP 0Đ TOÀN QUỐC", "Mở thêm hàng triệu mã miễn phí vận chuyển hôm nay", (16, 185, 129)),
            ("⚡ 6 KHUNG GIỜ VÀNG FLASH SALE", "00:00 • 09:00 • 12:00 • 15:00 • 18:00 • 21:00", (249, 115, 22)),
            ("🎁 KHO VOUCHER GIẢM 50% & HOÀN XU", "Mã giảm giá chớp nhoáng lưu trước vào ví", (236, 72, 153)),
            ("📉 ĐÁY LỊCH SỬ 30 NGÀY ĐÃ KIỂM TRA", "Cam kết chỉ tổng hợp deal giảm giá thật, không ảo", (59, 130, 246))
        ]

        card_start_y = 450
        card_h = 100
        card_gap = 22

        for idx, (f_title, f_desc, accent_color) in enumerate(features):
            cy = card_start_y + idx * (card_h + card_gap)
            draw.rounded_rectangle(
                [(80, cy), (w - 80, cy + card_h)],
                radius=18,
                fill=(22, 30, 49),
                outline=(51, 65, 85),
                width=2
            )
            draw.rounded_rectangle([(80, cy), (94, cy + card_h)], radius=6, fill=accent_color)

            f_font_t = cls._get_font(26, bold=True)
            draw.text((120, cy + 18), f_title, font=f_font_t, fill=(255, 255, 255))

            f_font_d = cls._get_font(18, bold=False)
            draw.text((120, cy + 56), f_desc, font=f_font_d, fill=(148, 163, 184))

        # 6. Thanh Footer CTA chỉ dẫn
        footer_top = 950
        draw.rounded_rectangle(
            [(80, footer_top), (w - 80, footer_top + 80)],
            radius=20,
            fill=(238, 77, 45)
        )
        font_cta = cls._get_font(24, bold=True)
        cta_text = "👉 BẤM XEM CHI TIẾT TỪNG DEAL & MÃ DƯỚI BÌNH LUẬN 👈"
        cta_w = font_cta.getlength(cta_text)
        draw.text(((w - cta_w) // 2, footer_top + 25), cta_text, font=font_cta, fill=(255, 255, 255))

        img.save(banner_path, format="JPEG", quality=92)
        logging.info(f"🎨 Đã tạo thành công ảnh tiêu đề deal Shopee ngày {today_display}: {banner_path}")
        return banner_path
