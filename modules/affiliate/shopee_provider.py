import os
import re
import json
import hashlib
import time
import requests
import logging
from typing import Optional, Dict, Any

from modules.affiliate.provider_base import BaseAffiliateProvider
from config.settings import SHOPEE_APP_ID, SHOPEE_SECRET, SHOPEE_AFF_COOKIE

logger = logging.getLogger("ShopeeAffiliate")

class ShopeeAffiliateProvider(BaseAffiliateProvider):
    """
    Nhà cung cấp Affiliate cho sàn Shopee Việt Nam:
    1. Ưu tiên 1: Shopee Affiliate Open API chính thức (GraphQL generateShortLink với SHA256).
    2. Ưu tiên 2: Cổng Web Shopee Affiliate (affiliate.shopee.vn) qua Cookie đăng nhập.
    3. Ưu tiên 3: Playwright headless browser fallback.
    """

    _cache: Dict[str, str] = {}

    def __init__(
        self,
        app_id: Optional[str] = None,
        secret: Optional[str] = None,
        aff_cookie: Optional[str] = None
    ):
        self.app_id = app_id
        self.secret = secret
        self.aff_cookie = aff_cookie

    @property
    def platform_name(self) -> str:
        return "SHOPEE"

    def is_match_url(self, url: str) -> bool:
        if not url:
            return False
        clean = url.lower()
        return "shopee.vn" in clean or "s.shopee.vn" in clean or "shp.ee" in clean

    def extract_item_id(self, url: str) -> Optional[str]:
        """
        Trích xuất Item ID từ URL Shopee:
        VD: https://shopee.vn/product/12345/67890 -> 67890
        VD: https://shopee.vn/ao-thun-nam-i.12345.67890 -> 67890
        """
        if not url:
            return None
        # Pattern i.{shopid}.{itemid}
        m = re.search(r"i\.\d+\.(\d+)", url)
        if m:
            return m.group(1)
        # Pattern /product/{shopid}/{itemid}
        m = re.search(r"/product/\d+/(\d+)", url)
        if m:
            return m.group(1)
        # Query param itemid=
        m = re.search(r"itemid=(\d+)", url)
        if m:
            return m.group(1)
        return None

    def convert_to_affiliate(self, original_url: str, channel: str = "telegram", sub_id: str = "") -> str:
        """Chuyển đổi URL sản phẩm thành link Affiliate chuẩn của Shopee"""
        if not original_url:
            return ""

        sub_tag = sub_id or channel
        cache_key = f"{original_url}_{sub_tag}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        app_id = self.app_id if self.app_id is not None else os.getenv("SHOPEE_APP_ID", SHOPEE_APP_ID)
        secret = self.secret if self.secret is not None else os.getenv("SHOPEE_SECRET", SHOPEE_SECRET)
        aff_cookie = self.aff_cookie if self.aff_cookie is not None else (os.getenv("SHOPEE_AFF_COOKIE", "") or SHOPEE_AFF_COOKIE or os.getenv("SHOPEE_COOKIE", ""))

        # 1. Gọi Shopee Affiliate Open API chính thức nếu đã có App ID & Secret
        if app_id and secret:
            aff_link = self._call_shopee_affiliate_api(original_url, sub_tag=sub_tag, app_id=app_id, secret=secret)
            if aff_link and aff_link != original_url:
                self._cache[cache_key] = aff_link
                return aff_link

        # 2. Gọi cổng Web Shopee Affiliate (affiliate.shopee.vn) qua Cookie đăng nhập
        if aff_cookie:
            aff_link = self._convert_via_affiliate_portal(original_url, sub_tag=sub_tag, cookie=aff_cookie)
            if aff_link and aff_link != original_url:
                self._cache[cache_key] = aff_link
                return aff_link

        logger.warning(
            f"⚠️ [SHOPEE AFFILIATE]: Không thể sinh link hoa hồng cho [{original_url}]. "
            "Chưa cấu hình SHOPEE_AFF_COOKIE hoặc SHOPEE_APP_ID/SECRET trong Cài Đặt."
        )
        return original_url

    def _call_shopee_affiliate_api(
        self,
        original_url: str,
        sub_tag: str = "",
        app_id: str = "",
        secret: str = ""
    ) -> str:
        endpoint = "https://open-api.affiliate.shopee.vn/graphql"
        timestamp = int(time.time())
        cur_app_id = app_id or self.app_id
        cur_secret = secret or self.secret

        query = """mutation GenerateShortLink($originUrl: String!, $subIds: [String]) {
  generateShortLink(input: {originUrl: $originUrl, subIds: $subIds}) {
    shortLink
  }
}"""
        variables: Dict[str, Any] = {"originUrl": original_url}
        if sub_tag:
            variables["subIds"] = [str(sub_tag)[:20]]

        payload = json.dumps({"query": query, "variables": variables}, separators=(',', ':'))
        factor = f"{cur_app_id}{timestamp}{payload}{cur_secret}"
        signature = hashlib.sha256(factor.encode("utf-8")).hexdigest()

        headers = {
            "Authorization": f"SHA256 Credential={cur_app_id}, Timestamp={timestamp}, Signature={signature}",
            "Content-Type": "application/json"
        }

        try:
            resp = requests.post(endpoint, data=payload, headers=headers, timeout=12)
            if resp.status_code == 200:
                data = resp.json()
                short_link = data.get("data", {}).get("generateShortLink", {}).get("shortLink")
                if short_link and short_link.startswith("http"):
                    logger.info(f"✅ Đã tạo link Shopee Aff chuẩn (Open API): {short_link}")
                    return short_link
        except Exception as e:
            logger.error(f"❌ [LỖI KẾT NỐI SHOPEE OPEN API]: {e}")

        return original_url

    def _convert_via_affiliate_portal(
        self,
        original_url: str,
        sub_tag: str = "",
        cookie: str = ""
    ) -> str:
        endpoint = "https://affiliate.shopee.vn/api/v3/gql?q=batchCustomLink"
        cur_cookie = cookie or self.aff_cookie or os.getenv("SHOPEE_AFF_COOKIE", "") or os.getenv("SHOPEE_COOKIE", "")

        query = """query batchGetCustomLink($linkParams: [CustomLinkParam!], $sourceCaller: SourceCaller) {
  batchCustomLink(linkParams: $linkParams, sourceCaller: $sourceCaller) {
    shortLink
    longLink
    failCode
  }
}"""
        adv_params = {}
        if sub_tag:
            adv_params["subId1"] = str(sub_tag)[:20]

        variables = {
            "linkParams": [{
                "originalLink": original_url,
                "advancedLinkParams": adv_params
            }],
            "sourceCaller": "CUSTOM_LINK_CALLER"
        }

        csrf_token = ""
        for part in cur_cookie.split(";"):
            part = part.strip()
            if part.startswith("csrftoken="):
                csrf_token = part.split("=", 1)[1]
                break

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Cookie": cur_cookie,
            "Content-Type": "application/json",
            "Referer": "https://affiliate.shopee.vn/offer/custom_link",
            "Origin": "https://affiliate.shopee.vn",
            "Accept": "application/json, text/plain, */*",
            "x-requested-with": "XMLHttpRequest"
        }
        if csrf_token:
            headers["x-csrftoken"] = csrf_token

        try:
            resp = requests.post(endpoint, json={"query": query, "variables": variables}, headers=headers, timeout=12)
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("data", {}).get("batchCustomLink", [])
                if items and isinstance(items, list):
                    short_link = items[0].get("shortLink")
                    if short_link and short_link.startswith("http"):
                        logger.info(f"✅ Đã tạo link Shopee Aff chuẩn (Cookie Portal): {short_link}")
                        return short_link
        except Exception as e:
            logger.error(f"❌ [NGOẠI LỆ KẾT NỐI] Cổng Shopee Affiliate Web: {e}")

        return original_url

    def verify_deal_freshness(self, deal: Dict) -> bool:
        """Kiểm tra deal Shopee còn sống hay đã hết hàng/hết sale"""
        from modules.crawler.deal_hunter import DealHunter
        return DealHunter.verify_deal_freshness(deal)
