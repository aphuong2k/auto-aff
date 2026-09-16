import requests
import logging
import os
from typing import Dict
from config.settings import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from modules.affiliate.content_writer import DealContentWriter
from database.db_manager import DatabaseManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

class TelegramPublisher:
    """Module tự động đăng deal THẬT vào Kênh hoặc Nhóm Telegram"""

    def __init__(self, bot_token: str = None, chat_id: str = None, db: DatabaseManager = None):
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN", TELEGRAM_BOT_TOKEN)
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID", TELEGRAM_CHAT_ID)
        self.db = db or DatabaseManager()

    def publish_deal(self, deal: Dict) -> bool:
        """Gửi deal thật tới Telegram (Nếu chưa cấu hình Token sẽ báo lỗi rõ ràng)"""
        if not self.bot_token or not self.chat_id:
            raise RuntimeError(
                "Chưa cấu hình Telegram Bot Token hoặc Chat ID! "
                "Hệ thống không thể bắn deal tự động. Vui lòng nhập thông tin tại tab 'Cài Đặt'."
            )

        message_html = DealContentWriter.generate_telegram_post(deal)
        image_url = deal.get("image_url")

        api_url = f"https://api.telegram.org/bot{self.bot_token}/sendPhoto" if image_url else f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        
        payload = {
            "chat_id": self.chat_id,
            "parse_mode": "HTML"
        }
        
        if image_url:
            payload["photo"] = image_url
            payload["caption"] = message_html
        else:
            payload["text"] = message_html

        try:
            resp = requests.post(api_url, json=payload, timeout=15)
            if resp.status_code == 200:
                logging.info(f"✅ Đã gửi deal [{deal['name'][:30]}...] tới Telegram ({self.chat_id}) thành công!")
                return True
            else:
                raise RuntimeError(f"Telegram Bot API trả về lỗi {resp.status_code}: {resp.text}")
        except Exception as e:
            raise RuntimeError(f"Lỗi khi gửi bài tới Telegram: {e}")
