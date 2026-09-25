import os
import re
import json
import hashlib
import time
import requests
import logging
from typing import Optional, Dict
import urllib.parse
from config.settings import (
    SHOPEE_APP_ID, SHOPEE_SECRET, SHOPEE_AFF_COOKIE,
    REDIRECT_MODE, REDIRECT_BASE_URL
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

class AffiliateLinkConverter:
    """
    Module chuyển đổi link sản phẩm gốc sang link Affiliate Shopee:
    1. Ưu tiên 1: Shopee Affiliate Open API chính thức (App ID & Secret Key).
    2. Ưu tiên 2: Cổng Web Shopee Affiliate (affiliate.shopee.vn) qua Cookie đăng nhập.
    3. Dự phòng: Rút gọn qua TinyURL Cloud hoặc tạo link tracking test.
    """

    _tinyurl_cache: Dict[str, str] = {}
    _aff_cache: Dict[str, str] = {}

    def __init__(
        self,
        app_id: Optional[str] = None,
        secret: Optional[str] = None,
        aff_cookie: Optional[str] = None
    ):
        self.app_id = app_id
        self.secret = secret
        self.aff_cookie = aff_cookie

    def convert_to_affiliate(self, original_url: str, channel: str = "telegram", sub_id: str = "") -> str:
        """
        Chuyển đổi URL sản phẩm thành link Affiliate chuẩn của tài khoản (Đa sàn Shopee & Lazada):
        - Tự động nhận diện sàn thương mại điện tử dựa trên URL
        - sub_tag: Gắn Sub-ID tracking để biết đơn hàng đến từ kênh nào (Telegram, FB Group, Seeding...).
        """
        if not original_url:
            return ""

        sub_tag = sub_id or channel
        cache_key = f"{original_url}_{sub_tag}"
        if cache_key in self._aff_cache:
            return self._aff_cache[cache_key]

        # 0. ĐA SÀN: Kiểm tra nếu là link Lazada
        if "lazada.vn" in original_url.lower() or "s.lazada.vn" in original_url.lower() or "c.lazada.vn" in original_url.lower():
            try:
                from modules.affiliate.lazada_provider import LazadaAffiliateProvider
                lazada_prov = LazadaAffiliateProvider()
                laz_aff = lazada_prov.convert_to_affiliate(original_url, channel=channel, sub_id=sub_tag)
                if laz_aff and laz_aff != original_url:
                    self._aff_cache[cache_key] = laz_aff
                    return laz_aff
            except Exception as e:
                logging.warning(f"Lỗi khi tạo link Lazada Aff: {e}")

        app_id = self.app_id if self.app_id is not None else os.getenv("SHOPEE_APP_ID", SHOPEE_APP_ID)
        secret = self.secret if self.secret is not None else os.getenv("SHOPEE_SECRET", SHOPEE_SECRET)
        aff_cookie = self.aff_cookie if self.aff_cookie is not None else (os.getenv("SHOPEE_AFF_COOKIE", "") or SHOPEE_AFF_COOKIE or os.getenv("SHOPEE_COOKIE", ""))

        # 1. ƯU TIÊN 1: Gọi Shopee Affiliate Open API chính thức (nếu đã có App ID & Secret)
        if app_id and secret:
            aff_link = self._call_shopee_affiliate_api(original_url, sub_tag=sub_tag, app_id=app_id, secret=secret)
            if aff_link and aff_link != original_url:
                self._aff_cache[cache_key] = aff_link
                return aff_link

        # 2. ƯU TIÊN 2: Gọi cổng Web Shopee Affiliate (affiliate.shopee.vn) qua Cookie đăng nhập
        if aff_cookie:
            aff_link = self._convert_via_affiliate_portal(original_url, sub_tag=sub_tag, cookie=aff_cookie)
            if aff_link and aff_link != original_url:
                self._aff_cache[cache_key] = aff_link
                return aff_link

        # 3. Khi không có cấu hình hoặc cả hai phương thức đều thất bại: Báo lỗi thật, KHÔNG fake link
        logging.error(
            f"❌ [LỖI TẠO LINK AFFILIATE]: Không thể sinh link hoa hồng cho [{original_url}]. "
            "Nguyên nhân: Chưa cấu hình SHOPEE_AFF_COOKIE hoặc SHOPEE_APP_ID/SECRET trong .env (hoặc phiên đăng nhập hết hạn). "
            "Hệ thống giữ nguyên link gốc để bạn nhận biết và sửa cấu hình trong tab Cài Đặt (Không fake dữ liệu)!"
        )
        return original_url

    def _call_shopee_affiliate_api(
        self,
        original_url: str,
        sub_tag: str = "",
        app_id: str = "",
        secret: str = ""
    ) -> str:
        """
        Gọi Shopee Open Platform GraphQL API (generateShortLink):
        - Chữ ký Signature SHA256 chuẩn: SHA256(app_id + timestamp + minified_json_payload + secret).
        - Gửi mảng subIds trong mutation để Shopee lưu Sub-ID vào báo cáo đối soát.
        """
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

        # Payload JSON thu gọn chuẩn không có khoảng trắng thừa để tính đúng chữ ký SHA256
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
                if "errors" in data:
                    logging.error(f"❌ [LỖI SHOPEE OPEN API GRAPHQL]: {data['errors']}")
                short_link = data.get("data", {}).get("generateShortLink", {}).get("shortLink")
                if short_link and short_link.startswith("http"):
                    logging.info(f"✅ Đã tạo link Shopee Aff chuẩn (Open API): {short_link}")
                    return short_link
                else:
                    logging.error(f"❌ [LỖI SHOPEE OPEN API]: Phản hồi không có link hợp lệ: {data}")
            else:
                logging.error(f"❌ [LỖI SHOPEE OPEN API HTTP {resp.status_code}]: {resp.text[:300]}")
        except Exception as e:
            logging.error(f"❌ [LỖI NGOẠI LỆ KẾT NỐI SHOPEE OPEN API]: {e}")

        return original_url

    def _convert_via_affiliate_portal(
        self,
        original_url: str,
        sub_tag: str = "",
        cookie: str = ""
    ) -> str:
        """
        Chuyển đổi link trực tiếp từ cổng Web Shopee Affiliate (affiliate.shopee.vn) bằng Cookie:
        - Sử dụng GraphQL batchCustomLink chuẩn của Shopee Affiliate.
        - Tự động gắn SubID1 tracking theo từng kênh.
        """
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

        # Trích xuất csrftoken từ cookie nếu có để vượt bảo mật
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
                if "errors" in data:
                    logging.error(f"❌ [LỖI CỔNG AFFILIATE GRAPHQL]: {data['errors']}")
                items = data.get("data", {}).get("batchCustomLink", [])
                if items and isinstance(items, list):
                    short_link = items[0].get("shortLink")
                    fail_code = items[0].get("failCode")
                    if fail_code:
                        logging.error(f"❌ [LỖI CỔNG AFFILIATE FAIL_CODE]: Mã lỗi Shopee {fail_code} cho link {original_url}")
                    if short_link and short_link.startswith("http"):
                        logging.info(f"✅ Đã tạo link Shopee Aff chuẩn (Cookie Portal): {short_link}")
                        return short_link
                else:
                    logging.error(f"❌ [LỖI CỔNG AFFILIATE]: Phản hồi không có danh sách link: {data}")
            elif resp.status_code == 403:
                logging.error(f"❌ [LỖI CỔNG AFFILIATE] Shopee từ chối (HTTP 403 WAF): {resp.text[:300]}")
            else:
                logging.error(f"❌ [LỖI CỔNG AFFILIATE] Shopee trả về HTTP {resp.status_code}: {resp.text[:300]}")
        except Exception as e:
            logging.error(f"❌ [NGOẠI LỆ KẾT NỐI] Cổng Shopee Affiliate Web: {e}")

        # Thử dự phòng qua Playwright headless nếu direct request bị WAF chặn
        short_link = self._try_playwright_portal_convert(original_url, sub_tag=sub_tag, cookie=cur_cookie)
        if short_link and short_link.startswith("http"):
            return short_link

        return original_url

    def _try_playwright_portal_convert(self, original_url: str, sub_tag: str = "", cookie: str = "") -> str:
        """Dự phòng: Mở Chromium Playwright tương tác trực tiếp với form Web Custom Link để vượt qua WAF Shopee và lấy link hoa hồng chuẩn"""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logging.error("❌ Chưa cài đặt Playwright! Hãy chạy 'pip install playwright' và 'playwright install'.")
            return ""

        cur_cookie = cookie or self.aff_cookie or os.getenv("SHOPEE_AFF_COOKIE", "") or os.getenv("SHOPEE_COOKIE", "")
        if not cur_cookie:
            logging.error("❌ Chưa cấu hình SHOPEE_AFF_COOKIE!")
            return ""

        cookie_list = []
        for item in cur_cookie.split(";"):
            item = item.strip()
            if "=" in item:
                k, v = item.split("=", 1)
                cookie_list.append({
                    "name": k.strip(),
                    "value": v.strip(),
                    "domain": ".shopee.vn",
                    "path": "/"
                })

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled"]
                )
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
                )
                context.add_cookies(cookie_list)
                page = context.new_page()

                logging.info("🌐 [PLAYWRIGHT AFFILIATE]: Đang mở trang Tạo Link Tùy Chỉnh (offer/custom_link)...")
                page.goto("https://affiliate.shopee.vn/offer/custom_link", timeout=40000, wait_until="networkidle")

                # Kiểm tra nếu bị redirect về login
                if "login" in page.url.lower():
                    logging.error("❌ [LỖI CỔNG AFFILIATE]: Cookie đã hết hạn hoặc không hợp lệ (Bị điều hướng về trang đăng nhập). Vui lòng copy lại Cookie mới từ affiliate.shopee.vn!")
                    browser.close()
                    return ""

                # 1. Điền link vào ô input đầu tiên
                inputs = page.locator("input, textarea").all()
                if not inputs:
                    logging.error("❌ Không tìm thấy ô nhập link trên trang Shopee Affiliate Custom Link!")
                    browser.close()
                    return ""

                inputs[0].fill(original_url)
                page.wait_for_timeout(300)

                # 2. Nếu có sub_tag, điền vào Sub_id1 (ô input thứ hai)
                # QUAN TRỌNG: Form Shopee Affiliate chỉ chấp nhận ký tự chữ và số (a-zA-Z0-9). Ký tự đặc biệt hoặc gạch dưới '_' sẽ làm nút Get Link bị disabled!
                clean_sub = re.sub(r'[^a-zA-Z0-9]', '', str(sub_tag)) if sub_tag else ""
                if clean_sub and len(inputs) > 1:
                    try:
                        inputs[1].fill(clean_sub[:20])
                        page.wait_for_timeout(300)
                    except Exception:
                        pass

                # 3. Click nút 'Get Link' / 'Lấy link' và lắng nghe phản hồi GraphQL
                btn = page.locator("button:has-text('Get Link'), button:has-text('Lấy link')").first
                if not btn.is_visible(timeout=3000):
                    btn = page.locator("button.ant-btn-primary").first

                captured_link = ""
                try:
                    with page.expect_response(
                        lambda r: "batchCustomLink" in r.url and r.request.method == "POST",
                        timeout=15000
                    ) as resp_info:
                        btn.click()

                    res = resp_info.value
                    if res.status == 200:
                        data = res.json()
                        items = data.get("data", {}).get("batchCustomLink", [])
                        if items and isinstance(items, list):
                            captured_link = items[0].get("shortLink") or ""
                            fail_code = items[0].get("failCode")
                            if fail_code:
                                logging.error(f"❌ [LỖI CỔNG AFFILIATE FAIL_CODE]: Shopee trả về mã lỗi {fail_code} cho link {original_url}")
                except Exception as e:
                    logging.warning(f"Chưa bắt được phản hồi qua expect_response: {e}")

                # 4. Dự phòng đọc link hiển thị trên DOM nếu network event bị trễ
                if not captured_link:
                    page.wait_for_timeout(2000)
                    link_els = page.locator("input[readonly], .ant-input[readonly], a[href*='s.shopee.vn']").all()
                    for el in link_els:
                        try:
                            val = el.input_value() if el.evaluate("e => 'value' in e") else el.get_attribute("href")
                            if val and val.startswith("http") and ("shopee" in val or "s.shopee.vn" in val):
                                captured_link = val
                                break
                        except Exception:
                            pass

                browser.close()

                if captured_link and captured_link.startswith("http"):
                    logging.info(f"✅ Đã tạo link Shopee Aff chuẩn (Playwright UI Portal): {captured_link}")
                    return captured_link

        except Exception as e:
            logging.error(f"❌ [LỖI TRÌNH DUYỆT PLAYWRIGHT KHI TẠO LINK AFF]: {e}", exc_info=True)

        return ""

    @classmethod
    def shorten_via_tinyurl(cls, long_url: str) -> str:
        """Rút gọn link vĩnh viễn qua Cloud TinyURL API (Miễn phí, sống 24/7/365, không cần server)"""
        if not long_url:
            return long_url
        if long_url in cls._tinyurl_cache:
            return cls._tinyurl_cache[long_url]
        try:
            api_url = f"https://tinyurl.com/api-create.php?url={urllib.parse.quote(long_url)}"
            resp = requests.get(api_url, timeout=5)
            if resp.status_code == 200 and resp.text.startswith("http"):
                short_url = resp.text.strip()
                cls._tinyurl_cache[long_url] = short_url
                return short_url
        except Exception as e:
            logging.debug(f"Không thể rút gọn qua TinyURL, giữ nguyên link: {e}")
        return long_url

    def get_bridge_url(
        self,
        item_id: str,
        channel: str = "fb_group",
        sub_id: str = "",
        base_url: str = "",
        direct_aff_url: str = ""
    ) -> str:
        """
        Tạo link an toàn để đăng lên Group Facebook hoặc đi rải comment.
        - 'direct': Dùng trực tiếp link Shopee Aff (100% không bao giờ chết dù tắt máy hay người dùng bấm trên điện thoại).
        - 'tinyurl': Tự động rút gọn qua TinyURL cloud.
        - 'custom_domain': Nếu cấu hình domain riêng thì trỏ qua trang trung gian Anti-Ban.
        """
        mode = os.getenv("REDIRECT_MODE", REDIRECT_MODE)
        effective_base = base_url or os.getenv("REDIRECT_BASE_URL", REDIRECT_BASE_URL)
        sub_param = f"&sub_id={sub_id}" if sub_id else ""

        # 1. Nếu có domain riêng công khai (không phải localhost) và người dùng muốn qua trang đệm
        if mode == "custom_domain" and effective_base and "localhost" not in effective_base and "127.0.0.1" not in effective_base:
            return f"{effective_base}/r/{item_id}?channel={channel}{sub_param}"

        # 2. Nếu ở chế độ TinyURL và có link affiliate trực tiếp
        if mode == "tinyurl" and direct_aff_url:
            return self.shorten_via_tinyurl(direct_aff_url)

        # 3. Chế độ MẶC ĐỊNH 'direct': Dùng trực tiếp link Shopee Aff (Sống vĩnh viễn, không chết khi tắt máy)
        if direct_aff_url:
            return direct_aff_url

        # 4. Dự phòng khi truyền base_url cụ thể (dành cho API test hoặc local preview)
        if effective_base:
            return f"{effective_base}/r/{item_id}?channel={channel}{sub_param}"

        return f"https://shopee.vn/search?keyword={item_id}"
