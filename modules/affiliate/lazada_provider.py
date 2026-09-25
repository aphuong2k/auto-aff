import os
import re
import time
import hmac
import hashlib
import urllib.parse
import logging
import requests
from typing import Dict, Optional, Any

from modules.affiliate.provider_base import BaseAffiliateProvider
from config.settings import (
    LAZADA_APP_KEY, LAZADA_APP_SECRET, LAZADA_AFF_COOKIE, LAZADA_TRACKING_URL
)

logger = logging.getLogger("LazadaAffiliate")

class LazadaAffiliateProvider(BaseAffiliateProvider):
    """
    Nhà cung cấp Affiliate cho sàn Lazada Việt Nam:
    1. Ưu tiên 1: Lazada Open Platform API (lazada.affiliate.link.generate) với HMAC-SHA256
    2. Ưu tiên 2: Lazada Deeplink Tracking URL (c.lazada.vn/t/c... hoặc Tracking Prefix)
    3. Dự phòng: Gắn tracking parameter chuẩn Lazada (ex_channel=affiliate, aff_sub, sub_aff_id)
    """

    _cache: Dict[str, str] = {}

    def __init__(
        self,
        app_key: Optional[str] = None,
        app_secret: Optional[str] = None,
        cookie: Optional[str] = None,
        tracking_url: Optional[str] = None
    ):
        self.app_key = app_key or os.getenv("LAZADA_APP_KEY", LAZADA_APP_KEY)
        self.app_secret = app_secret or os.getenv("LAZADA_APP_SECRET", LAZADA_APP_SECRET)
        self.cookie = cookie or os.getenv("LAZADA_AFF_COOKIE", LAZADA_AFF_COOKIE)
        self.tracking_url = tracking_url or os.getenv("LAZADA_TRACKING_URL", LAZADA_TRACKING_URL)

    @property
    def platform_name(self) -> str:
        return "LAZADA"

    def is_match_url(self, url: str) -> bool:
        if not url:
            return False
        clean = url.lower()
        return "lazada.vn" in clean or "s.lazada.vn" in clean or "c.lazada.vn" in clean

    def extract_item_id(self, url: str) -> Optional[str]:
        """
        Trích xuất Item ID từ URL sản phẩm Lazada:
        Ví dụ: https://www.lazada.vn/products/ao-thun-nam-i123456789-s987654321.html -> laz_123456789
        """
        if not url:
            return None
        # Bắt pattern -i{number}-s{number} hoặc -i{number}.html
        match = re.search(r"-i(\d+)(?:-s\d+)?\.html", url)
        if match:
            return f"laz_{match.group(1)}"
        
        # Bắt query param id=
        parsed = urllib.parse.urlparse(url)
        params = urllib.parse.parse_qs(parsed.query)
        if "id" in params:
            return f"laz_{params['id'][0]}"

        # Trích xuất số bất kỳ trong URL
        digits = re.findall(r"\d{7,15}", url)
        if digits:
            return f"laz_{digits[0]}"

        return None

    def convert_to_affiliate(self, original_url: str, channel: str = "telegram", sub_id: str = "") -> str:
        """Chuyển đổi URL sản phẩm thành link Affiliate Lazada kèm Sub-ID tracking"""
        if not original_url:
            return ""

        sub_tag = sub_id or channel or "aff_auto"
        cache_key = f"{original_url}_{sub_tag}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # 1. Gọi Lazada Open Platform API nếu có App Key & Secret
        app_key = os.getenv("LAZADA_APP_KEY", self.app_key)
        app_secret = os.getenv("LAZADA_APP_SECRET", self.app_secret)
        if app_key and app_secret:
            aff_link = self._call_lazada_open_api(original_url, app_key, app_secret, sub_tag)
            if aff_link and aff_link != original_url:
                self._cache[cache_key] = aff_link
                return aff_link

        # 2. Tạo link qua Lazada Deeplink Tracking URL (nếu có cấu hình LAZADA_TRACKING_URL)
        tracking_prefix = os.getenv("LAZADA_TRACKING_URL", self.tracking_url)
        if tracking_prefix:
            encoded_url = urllib.parse.quote(original_url, safe="")
            sep = "&" if "?" in tracking_prefix else "?"
            aff_link = f"{tracking_prefix}{sep}url={encoded_url}&sub_aff_id={sub_tag}"
            self._cache[cache_key] = aff_link
            return aff_link

        # 3. Tạo Deeplink chuẩn Lazada Affiliate với UTM & Sub Tracking params
        parsed = urllib.parse.urlsplit(original_url)
        q = urllib.parse.parse_qs(parsed.query)
        q["ex_channel"] = ["affiliate"]
        q["aff_sub"] = [sub_tag]
        q["aff_sub2"] = [channel]
        q["utm_source"] = ["affiliate"]
        q["utm_medium"] = [channel]
        new_query = urllib.parse.urlencode(q, doseq=True)
        aff_link = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, new_query, parsed.fragment))
        self._cache[cache_key] = aff_link
        return aff_link

    def _call_lazada_open_api(self, original_url: str, app_key: str, app_secret: str, sub_id: str) -> str:
        """
        Gọi API chính thức của Lazada Open Platform:
        Tạo chữ ký HMAC-SHA256 chuẩn Lazada API.
        """
        endpoint = "https://api.lazada.vn/rest"
        timestamp = str(int(time.time() * 1000))

        params = {
            "app_key": app_key,
            "timestamp": timestamp,
            "sign_method": "sha256",
            "format": "json",
            "action": "lazada.affiliate.link.generate",
            "url": original_url,
            "sub_id1": str(sub_id)[:20]
        }

        # Sắp xếp tham số theo alphabet để tính HMAC-SHA256
        sorted_keys = sorted(params.keys())
        sign_string = "lazada.affiliate.link.generate" + "".join([f"{k}{params[k]}" for k in sorted_keys])
        signature = hmac.new(
            app_secret.encode("utf-8"),
            sign_string.encode("utf-8"),
            hashlib.sha256
        ).hexdigest().upper()
        params["sign"] = signature

        headers = {
            "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        try:
            resp = requests.post(endpoint, data=params, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if "result" in data and "short_url" in data["result"]:
                    short_url = data["result"]["short_url"]
                    logger.info(f"✅ Đã tạo link Lazada Aff chuẩn (Open API): {short_url}")
                    return short_url
                elif "data" in data and "link" in data["data"]:
                    return data["data"]["link"]
                else:
                    logger.warning(f"Lazada Open API trả về: {data}")
        except Exception as e:
            logger.warning(f"Lỗi kết nối Lazada Open API: {e}")

        return original_url

    def verify_deal_freshness(self, deal: Dict) -> bool:
        """Kiểm tra deal Lazada còn hàng và hợp lệ hay không"""
        url = deal.get("item_url") or deal.get("aff_url")
        if not url:
            return False

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8"
        }

        try:
            resp = requests.get(url, headers=headers, timeout=12, allow_redirects=True)
            if resp.status_code in [404, 410]:
                return False
            if resp.status_code == 200:
                text = resp.text.lower()
                # Kiểm tra dấu hiệu hết hàng
                if "sản phẩm này đã hết hàng" in text or "out of stock" in text or '"isoutofstock":true' in text:
                    return False
                return True
        except Exception as e:
            logger.warning(f"Lỗi kiểm tra độ tươi deal Lazada: {e}")

        return True
