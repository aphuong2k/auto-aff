import hashlib
import time
import requests
import logging
from typing import Optional
from config.settings import SHOPEE_APP_ID, SHOPEE_SECRET

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

class AffiliateLinkConverter:
    """Module chuyển đổi link gốc sang link Affiliate Shopee hoặc Accesstrade"""

    def __init__(self, app_id: str = SHOPEE_APP_ID, secret: str = SHOPEE_SECRET):
        self.app_id = app_id
        self.secret = secret

    def convert_to_affiliate(self, original_url: str) -> str:
        """
        Nếu đã cấu hình Shopee Open API: Gọi API tạo shortlink aff.
        Nếu chưa cấu hình: Gắn tham số tracking và trả về link để test luồng.
        """
        if self.app_id and self.secret:
            return self._call_shopee_affiliate_api(original_url)
        
        # Mặc định khi chưa có API key: Tạo link kèm tracking tag
        separator = "&" if "?" in original_url else "?"
        simulated_aff_link = f"{original_url}{separator}utm_source=affiliate_bot&utm_medium=auto_deal"
        return simulated_aff_link

    def _call_shopee_affiliate_api(self, original_url: str) -> str:
        """Gọi Shopee Open Platform generate_short_link API"""
        endpoint = "https://open-api.affiliate.shopee.vn/graphql"
        timestamp = int(time.time())
        factor = f"{self.app_id}{timestamp}{original_url}{self.secret}"
        signature = hashlib.sha256(factor.encode("utf-8")).hexdigest()

        headers = {
            "Authorization": f"SHA256 Credential={self.app_id}, Timestamp={timestamp}, Signature={signature}",
            "Content-Type": "application/json"
        }

        query = """
        mutation {
            generateShortLink(input: {originUrl: "%s"}) {
                shortLink
            }
        }
        """ % original_url

        try:
            resp = requests.post(endpoint, json={"query": query}, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                short_link = data.get("data", {}).get("generateShortLink", {}).get("shortLink")
                if short_link:
                    return short_link
        except Exception as e:
            logging.error(f"Lỗi khi gọi Shopee Affiliate API: {e}")

        return original_url
