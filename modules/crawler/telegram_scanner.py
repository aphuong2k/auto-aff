"""
Telegram Group & Channel Scanner
================================
Quét và trích xuất tin đăng rao bán sản phẩm từ một hoặc nhiều Group / Channel Telegram:
- Hỗ trợ xem trước Web (https://t.me/s/{channel}) cho các kênh/nhóm công khai (Không cần login)
- Hỗ trợ Telegram Bot API (getUpdates) cho các nhóm có Bot tham gia
- Tự động bóc tách nội dung, tên sản phẩm, giá bán, link ảnh và đường dẫn bài đăng
"""

import re
import os
import logging
from typing import List, Dict, Optional, Any
from urllib.parse import urlparse

import requests
from config.settings import TELEGRAM_BOT_TOKEN
from modules.crawler.product_cluster_engine import ProductClusterEngine

logger = logging.getLogger("TelegramScanner")


class TelegramScanner:
    """Bộ cào & trích xuất tin đăng sản phẩm từ Group/Channel Telegram"""

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8",
    }

    def __init__(self, bot_token: Optional[str] = None):
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN", TELEGRAM_BOT_TOKEN)

    def normalize_identifier(self, raw_input: str) -> str:
        """Chuẩn hóa username hoặc link Telegram thành username sạch (vd: '@muaban' hoặc 'muaban')"""
        clean = raw_input.strip()
        if clean.startswith("https://t.me/s/"):
            return clean.replace("https://t.me/s/", "").split("/")[0].split("?")[0].strip("@")
        elif clean.startswith("http://t.me/s/"):
            return clean.replace("http://t.me/s/", "").split("/")[0].split("?")[0].strip("@")
        elif clean.startswith("https://t.me/"):
            return clean.replace("https://t.me/", "").split("/")[0].split("?")[0].strip("@")
        elif clean.startswith("http://t.me/"):
            return clean.replace("http://t.me/", "").split("/")[0].split("?")[0].strip("@")
        return clean.strip("@")

    def scan_targets(self, targets: List[str], max_posts_per_target: int = 25) -> List[Dict]:
        """
        Quét nhiều mục tiêu Telegram (Group / Channel) đồng thời:
        Trả về danh sách các tin đăng sản phẩm thô sẵn sàng cho bộ gom nhóm (Cluster Engine)
        """
        all_posts: List[Dict] = []
        if not targets:
            return all_posts

        for target in targets:
            t_clean = target.strip()
            if not t_clean:
                continue

            logger.info(f"🔎 Đang quét tin đăng từ nhóm/kênh Telegram: [{t_clean}]...")
            posts = self.scan_single_target(t_clean, limit=max_posts_per_target)
            all_posts.extend(posts)

        logger.info(f"==> Tổng cộng thu thập được {len(all_posts)} tin đăng từ {len(targets)} nhóm Telegram.")
        return all_posts

    def scan_single_target(self, target: str, limit: int = 25) -> List[Dict]:
        """Quét 1 mục tiêu Telegram cụ thể"""
        norm_id = self.normalize_identifier(target)
        posts: List[Dict] = []

        # 1. Thử cào qua Web Preview https://t.me/s/{channel}
        try:
            posts = self._fetch_via_web_preview(norm_id, limit=limit)
        except Exception as e:
            logger.warning(f"Lỗi khi cào web preview của Telegram @{norm_id}: {e}")

        # 2. Nếu web preview không có kết quả và có cấu hình Bot Token, thử qua Bot API getUpdates
        if not posts and self.bot_token:
            try:
                posts = self._fetch_via_bot_updates(target, limit=limit)
            except Exception as e:
                logger.warning(f"Lỗi khi cào Bot API getUpdates: {e}")

        return posts

    def _fetch_via_web_preview(self, channel_username: str, limit: int = 25) -> List[Dict]:
        """
        Cào trực tiếp qua trang xem trước web Telegram công khai (t.me/s/...)
        Trích xuất: Nội dung tin, ảnh đính kèm, đường link bài viết, thời gian
        """
        url = f"https://t.me/s/{channel_username}"
        resp = requests.get(url, headers=self.HEADERS, timeout=12)
        if resp.status_code != 200:
            logger.warning(f"Telegram web preview trả về HTTP {resp.status_code} cho @{channel_username}")
            return []

        html = resp.text

        # Trích xuất các message widget
        msg_blocks = re.findall(
            r'<div class="tgme_widget_message_wrap[^"]*"[^>]*>(.*?)</div>\s*</div>\s*</div>',
            html,
            re.DOTALL
        )
        if not msg_blocks:
            # Fallback pattern tách theo tgme_widget_message
            msg_blocks = re.split(r'<div class="tgme_widget_message\b', html)[1:]

        extracted: List[Dict] = []
        for block in reversed(msg_blocks):
            # Trích xuất nội dung văn bản
            text_match = re.search(r'<div class="tgme_widget_message_text[^>]*>(.*?)</div>', block, re.DOTALL)
            raw_html_text = text_match.group(1) if text_match else ""
            clean_text = re.sub(r'<br\s*/?>', '\n', raw_html_text)
            clean_text = re.sub(r'<[^>]+>', ' ', clean_text).strip()

            if not clean_text or len(clean_text) < 10:
                continue

            # Trích xuất ảnh nếu có
            img_match = re.search(r'background-image:url\(\'([^\']+)\'\)', block)
            img_url = img_match.group(1) if img_match else ""

            # Trích xuất link bài viết (data-post)
            post_link_match = re.search(r'data-post="([^"]+)"', block)
            post_id = post_link_match.group(1) if post_link_match else ""
            post_url = f"https://t.me/{post_id}" if post_id else f"https://t.me/{channel_username}"

            # Trích xuất ngày giờ
            time_match = re.search(r'<time datetime="([^"]+)"', block)
            post_time = time_match.group(1) if time_match else ""

            # Bóc tách giá bán từ nội dung
            price_val = ProductClusterEngine.extract_price_vnd(clean_text)

            extracted.append({
                "source": f"Telegram @{channel_username}",
                "text": clean_text,
                "price": price_val,
                "image_url": img_url,
                "post_url": post_url,
                "date": post_time
            })

            if len(extracted) >= limit:
                break

        return extracted

    def _fetch_via_bot_updates(self, target_identifier: str, limit: int = 25) -> List[Dict]:
        """Cào qua Telegram Bot API getUpdates đối với các nhóm có bot tham gia"""
        if not self.bot_token:
            return []

        url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            return []

        data = resp.json()
        updates = data.get("result", []) or []
        posts: List[Dict] = []

        target_norm = self.normalize_identifier(target_identifier).lower()

        for upd in reversed(updates):
            msg = upd.get("message") or upd.get("channel_post") or {}
            if not msg:
                continue

            chat = msg.get("chat", {})
            chat_id = str(chat.get("id", ""))
            chat_user = str(chat.get("username", "")).lower()
            chat_title = chat.get("title", "")

            # So khớp nếu chỉ định cụ thể chat_id hoặc username
            is_matched = (
                target_norm in chat_id or
                target_norm in chat_user or
                target_norm in chat_title.lower() or
                not target_identifier  # Lấy tất cả nếu không chỉ định
            )
            if not is_matched:
                continue

            text = msg.get("text") or msg.get("caption") or ""
            if not text:
                continue

            price_val = ProductClusterEngine.extract_price_vnd(text)

            # Lấy ảnh nếu có
            photos = msg.get("photo", [])
            img_url = ""
            if photos:
                # Lấy file_id của ảnh kích thước lớn nhất
                largest_photo = photos[-1]
                file_id = largest_photo.get("file_id")
                if file_id:
                    file_info_url = f"https://api.telegram.org/bot{self.bot_token}/getFile?file_id={file_id}"
                    try:
                        f_resp = requests.get(file_info_url, timeout=6)
                        if f_resp.status_code == 200:
                            f_path = f_resp.json().get("result", {}).get("file_path", "")
                            if f_path:
                                img_url = f"https://api.telegram.org/file/bot{self.bot_token}/{f_path}"
                    except Exception:
                        pass

            posts.append({
                "source": f"Telegram: {chat_title or chat_user or chat_id}",
                "text": text,
                "price": price_val,
                "image_url": img_url,
                "post_url": f"https://t.me/{chat_user}" if chat_user else "",
                "date": str(msg.get("date", ""))
            })

            if len(posts) >= limit:
                break

        return posts
