import requests
import logging
import os
from typing import Dict
from config.settings import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from modules.affiliate.content_writer import DealContentWriter
from modules.affiliate.image_stamper import ImageBannerStamper
from database.db_manager import DatabaseManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

class TelegramPublisher:
    """Module tự động đăng deal THẬT kèm ảnh đóng khung Flash Sale chuyên nghiệp vào Telegram"""

    def __init__(self, bot_token: str = None, chat_id: str = None, db: DatabaseManager = None):
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN", TELEGRAM_BOT_TOKEN)
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID", TELEGRAM_CHAT_ID)
        self.db = db or DatabaseManager()

    def publish_deal(self, deal: Dict) -> bool:
        """
        Đóng khung Flash Sale lên ảnh, tải về máy và đăng tải trọn bộ ảnh + caption tới Telegram.
        Nếu chưa cấu hình bot token thì vẫn đóng khung ảnh để lưu trữ và hiển thị trên Dashboard.
        """
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN", self.bot_token)
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", self.chat_id)

        # 0. Live Freshness Check: Kiểm tra độ tươi và tồn kho của deal thời gian thực (Shopee & Lazada)
        platform = str(deal.get("platform", "SHOPEE")).upper()
        if platform == "LAZADA":
            from modules.affiliate.lazada_provider import LazadaAffiliateProvider
            is_fresh = LazadaAffiliateProvider().verify_deal_freshness(deal)
        else:
            from modules.crawler.deal_hunter import DealHunter
            is_fresh = DealHunter.verify_deal_freshness(deal)

        if not is_fresh:
            logging.warning(
                f"⚠️ Deal [{deal.get('name', '')[:30]}] ({platform}) đã hết hàng hoặc không còn giá sale tốt. Bỏ qua đăng Telegram!"
            )
            return False

        # 1. Luôn tự động tải ảnh gốc và đóng khung Flash Sale + Giá sốc bằng Pillow
        processed_image_path = None
        try:
            processed_image_path = ImageBannerStamper.stamp_deal_image(deal)
            if processed_image_path and processed_image_path.exists():
                deal["local_image"] = str(processed_image_path)
                self.db.update_deal_media(
                    item_id=str(deal.get("item_id")),
                    local_image=str(processed_image_path),
                    price_badge=deal.get("price_badge")
                )
        except Exception as e:
            logging.warning(f"Lỗi khi đóng khung ảnh deal {deal.get('item_id')}: {e}")

        # 2. Kiểm tra Token Telegram
        if not self.bot_token or not self.chat_id:
            logging.warning(
                f"⚠️ Bỏ qua gửi Telegram cho deal [{deal.get('name', '')[:30]}...]: "
                "Chưa cấu hình TELEGRAM_BOT_TOKEN hoặc TELEGRAM_CHAT_ID trong file .env / Cài Đặt."
            )
            return False

        # Chọn nội dung phù hợp: Deal mồi 1K (kích hoạt Cookie 7 ngày) hay Deal Flash Sale thông thường
        if deal.get("price_badge") == "LOSS_LEADER_1K":
            message_html = DealContentWriter.generate_loss_leader_post(deal)
        else:
            message_html = DealContentWriter.generate_telegram_post(deal)

        # 3. Ưu tiên gửi file ảnh local đã đóng khung qua multipart POST
        if processed_image_path and processed_image_path.exists():
            send_photo_url = f"https://api.telegram.org/bot{self.bot_token}/sendPhoto"
            try:
                with open(processed_image_path, "rb") as photo_file:
                    resp = requests.post(
                        send_photo_url,
                        data={
                            "chat_id": self.chat_id,
                            "caption": message_html,
                            "parse_mode": "HTML"
                        },
                        files={"photo": photo_file},
                        timeout=25
                    )
                if resp.status_code == 200:
                    logging.info(f"✅ Đã gửi deal kèm ẢNH ĐÓNG KHUNG [{deal['name'][:30]}...] tới Telegram ({self.chat_id})!")
                    self.db.log_posted_item(
                        post_type="POST", group_name="Telegram", group_url="",
                        target_url=self.chat_id, item_id=str(deal.get("item_id")),
                        item_name=deal.get("name", ""), content_snippet=message_html[:180],
                        status="SUCCESS"
                    )
                    return True
                else:
                    logging.warning(f"Telegram gửi ảnh local trả về lỗi {resp.status_code}: {resp.text}. Sẽ thử fallback.")
            except Exception as e:
                logging.warning(f"Lỗi khi gửi ảnh local tới Telegram: {e}")

        # 4. Dự phòng 1: Gửi qua URL ảnh Shopee trực tiếp
        image_url = deal.get("image_url")
        if image_url:
            try:
                resp = requests.post(
                    f"https://api.telegram.org/bot{self.bot_token}/sendPhoto",
                    json={"chat_id": self.chat_id, "photo": image_url, "caption": message_html, "parse_mode": "HTML"},
                    timeout=15
                )
                if resp.status_code == 200:
                    logging.info(f"✅ Đã gửi deal qua URL ảnh [{deal['name'][:30]}...] tới Telegram!")
                    self.db.log_posted_item(
                        post_type="POST", group_name="Telegram", group_url="",
                        target_url=self.chat_id, item_id=str(deal.get("item_id")),
                        item_name=deal.get("name", ""), content_snippet=message_html[:180],
                        status="SUCCESS"
                    )
                    return True
            except Exception as e:
                logging.warning(f"Fallback gửi qua URL ảnh Shopee lỗi: {e}")

        # 5. Dự phòng 2: Gửi bài dạng Text nếu ảnh không được
        try:
            resp = requests.post(
                f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                json={"chat_id": self.chat_id, "text": message_html, "parse_mode": "HTML"},
                timeout=15
            )
            if resp.status_code == 200:
                logging.info(f"✅ Đã gửi deal dạng Text [{deal['name'][:30]}...] tới Telegram!")
                self.db.log_posted_item(
                    post_type="POST", group_name="Telegram", group_url="",
                    target_url=self.chat_id, item_id=str(deal.get("item_id")),
                    item_name=deal.get("name", ""), content_snippet=message_html[:180],
                    status="SUCCESS"
                )
                return True
            else:
                logging.warning(f"Gửi text tới Telegram lỗi {resp.status_code}: {resp.text}")
                return False
        except Exception as e:
            logging.warning(f"Lỗi gửi text tới Telegram: {e}")
            return False

    def publish_sale_reminder(self, promo: Dict) -> bool:
        """Gửi thông báo nhắc nhở khung giờ Flash Sale & Voucher tới Telegram"""
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN", self.bot_token)
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", self.chat_id)

        message_html = DealContentWriter.generate_sale_reminder_post(promo)
        banner_url = promo.get("banner_url")

        if not self.bot_token or not self.chat_id:
            logging.warning(
                f"⚠️ Bỏ qua gửi bài nhắc sale khung [{promo.get('slot_time')}]: "
                "Chưa cấu hình TELEGRAM_BOT_TOKEN hoặc TELEGRAM_CHAT_ID trong file .env / Cài Đặt."
            )
            return False

        api_url = f"https://api.telegram.org/bot{self.bot_token}/sendPhoto" if banner_url else f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "parse_mode": "HTML"
        }
        if banner_url:
            payload["photo"] = banner_url
            payload["caption"] = message_html
        else:
            payload["text"] = message_html

        try:
            resp = requests.post(api_url, json=payload, timeout=15)
            if resp.status_code == 200:
                logging.info(f"🔔 [NHẮC SALE THÀNH CÔNG]: Đã gửi bài nhắc khung {promo.get('slot_time')} tới Telegram ({self.chat_id})!")
                return True
            else:
                # Nếu gửi kèm ảnh lỗi do URL ảnh Shopee, thử gửi lại dạng text
                if banner_url:
                    text_resp = requests.post(
                        f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                        json={"chat_id": self.chat_id, "text": message_html, "parse_mode": "HTML"},
                        timeout=15
                    )
                    if text_resp.status_code == 200:
                        logging.info(f"🔔 [NHẮC SALE THÀNH CÔNG]: Đã gửi bài nhắc text khung {promo.get('slot_time')} tới Telegram!")
                        return True
                logging.warning(f"Telegram Bot API trả về lỗi {resp.status_code}: {resp.text}")
                return False
        except Exception as e:
            logging.warning(f"Lỗi khi gửi bài nhắc sale tới Telegram: {e}")
            return False
