"""
Portal & Consumer Deal Hub API Router
=====================================
Endpoints phục vụ Cổng Săn Deal người dùng (/deals), Trang chi tiết sản phẩm chuẩn SEO (/deal/{id})
và Link chuyển hướng trung gian Anti-Ban & Mobile DeepLink Dispatcher (/r/{id}).
"""

import os
import re
import html as html_escape_module
from datetime import datetime
from typing import Optional

import requests
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from api.deps import db
from modules.crawler.promotion_hunter import PromotionHunter
from modules.portal.deal_hub_renderer import DealHubRenderer
from modules.portal.deal_detail_renderer import DealDetailRenderer

router = APIRouter(tags=["Consumer Portal & Redirect"])


@router.get("/r/{item_id}", response_class=HTMLResponse)
def anti_ban_redirect(item_id: str, request: Request, channel: str = "DIRECT", sub_id: str = ""):
    """
    Trang chuyển hướng trung gian Anti-Ban & Mobile DeepLink Dispatcher:
    - Bọc OpenGraph preview chuẩn chỉnh (ảnh full CDN, giá giảm, đáy 30 ngày) cho Facebook, Zalo, Threads
    - Nhận diện thiết bị di động & In-App Browser (FB, Zalo, TikTok)
    - Kích hoạt DeepLink mở thẳng App Shopee / Lazada native đã đăng nhập sẵn
    - Ghi nhận lượt click & Sub-ID Analytics chi tiết
    """
    deal = db.get_deal_by_id(item_id)
    if not deal:
        return HTMLResponse("<h3>Đang chuyển hướng tới sàn TMĐT...</h3><script>window.location.href='https://shopee.vn';</script>")

    client_ip = request.client.host if request.client else ""
    referer = request.headers.get("referer", "")
    user_agent = request.headers.get("user-agent", "")
    platform = str(deal.get("platform", "SHOPEE")).upper()
    plat_name = "Lazada" if platform == "LAZADA" else "Shopee"

    db.log_click(
        item_id=item_id,
        channel=channel,
        sub_id=sub_id,
        ip=client_ip,
        referer=referer,
        user_agent=user_agent,
        platform=platform
    )

    aff_url = deal.get("aff_url") or deal.get("item_url") or ("https://www.lazada.vn" if platform == "LAZADA" else "https://shopee.vn")

    # Chỉ 302 trực tiếp nếu người gọi yêu cầu qua query param (?mode=direct)
    # Mặc định trả về trang HTML trung gian Anti-Ban có đầy đủ OpenGraph & DeepLink native app
    if hasattr(request, "query_params") and request.query_params.get("mode") == "direct":
        return RedirectResponse(url=aff_url, status_code=302)

    price_sale_formatted = f"{int(deal.get('price_sale', 0)):,}đ".replace(",", ".")
    price_orig_formatted = f"{int(deal.get('price_original', 0)):,}đ".replace(",", ".")
    discount = int(deal.get("discount_percent", 0))
    rating = round(float(deal.get("rating_star", 5.0) or 5.0), 1)
    sold = int(deal.get("historical_sold", 0) or 0)
    badge_text = "Đáy lịch sử 30 ngày" if "LOW" in str(deal.get("price_badge", "")) else "Giảm thật đã kiểm chứng"
    deal_name = html_escape_module.escape(deal.get("name", f"Ưu Đãi {plat_name} Hot"))

    ua_lower = (user_agent or "").lower()
    is_in_app = any(x in ua_lower for x in ["fban", "fbav", "fb_iab", "instagram", "zalo", "tiktok", "micromessenger", "line"])
    is_mobile = any(x in ua_lower for x in ["iphone", "ipad", "ipod", "android", "mobile"])
    is_android = "android" in ua_lower

    shop_id = deal.get("shop_id") or ""
    if not shop_id and deal.get("item_url"):
        match = re.search(r"product/(\d+)/(\d+)", deal.get("item_url", "")) or re.search(r"-i\.(\d+)\.(\d+)", deal.get("item_url", ""))
        if match:
            shop_id = match.group(1)

    if platform == "LAZADA":
        app_scheme = f"lazada://product/{item_id}"
        android_intent = f"intent://product/{item_id}#Intent;scheme=lazada;package=com.lazada.android;S.browser_fallback_url={requests.utils.quote(aff_url)};end"
    else:
        if shop_id:
            app_scheme = f"shopee://product/{shop_id}/{item_id}"
            android_intent = f"intent://product/{shop_id}/{item_id}#Intent;scheme=shopee;package=com.shopee.vn;S.browser_fallback_url={requests.utils.quote(aff_url)};end"
        else:
            app_scheme = f"shopee://search?keyword={item_id}"
            android_intent = f"intent://search?keyword={item_id}#Intent;scheme=shopee;package=com.shopee.vn;S.browser_fallback_url={requests.utils.quote(aff_url)};end"

    base_url = str(getattr(request, "base_url", "http://localhost:8000")).rstrip("/")
    og_image = deal.get("image_url") or f"{base_url}/api/deals/image/{item_id}"

    html_content = f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>⚡ Flash Sale: {deal_name}</title>
    <meta property="og:title" content="🔥 [{plat_name.upper()} FLASH SALE] {deal_name}">
    <meta property="og:description" content="Giá chỉ {price_sale_formatted} (Gốc {price_orig_formatted} - Giảm {discount}%). {badge_text}!">
    <meta property="og:image" content="{og_image}">
    <meta property="og:image:width" content="800">
    <meta property="og:image:height" content="800">
    <meta property="og:type" content="product">
    <meta property="og:site_name" content="Cổng Săn Deal Khuyến Mại {plat_name}">
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="🔥 Flash Sale: {deal_name}">
    <meta name="twitter:description" content="Giá chỉ {price_sale_formatted} (-{discount}%). {badge_text}">
    <meta name="twitter:image" content="{og_image}">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }}
        body {{ background: #0b0f19; color: #f8fafc; display: flex; justify-content: center; align-items: center; min-height: 100vh; padding: 12px; }}
        .card {{ background: #131d2e; border: 1px solid #1e293b; border-radius: 20px; max-width: 480px; width: 100%; overflow: hidden; box-shadow: 0 24px 50px rgba(0,0,0,0.6); position: relative; }}
        .in-app-notice {{ background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%); color: #fff; padding: 10px 14px; font-size: 13px; line-height: 1.4; display: flex; align-items: center; gap: 8px; border-bottom: 1px solid rgba(255,255,255,0.15); }}
        .in-app-notice span {{ font-size: 18px; }}
        .top-badge {{ background: { 'linear-gradient(135deg, #0284c7, #2563eb)' if platform == 'LAZADA' else 'linear-gradient(135deg, #ef4444, #ea580c)' }; color: #fff; text-align: center; padding: 10px; font-weight: 800; font-size: 13px; text-transform: uppercase; letter-spacing: 0.8px; display: flex; align-items: center; justify-content: center; gap: 6px; }}
        .img-container {{ position: relative; width: 100%; height: 330px; background: #070a12; display: flex; align-items: center; justify-content: center; overflow: hidden; }}
        .img-container img {{ width: 100%; height: 100%; object-fit: cover; }}
        .discount-pill {{ position: absolute; top: 12px; right: 12px; background: #facc15; color: #991b1b; padding: 6px 14px; border-radius: 30px; font-weight: 800; font-size: 15px; box-shadow: 0 4px 12px rgba(0,0,0,0.4); }}
        .platform-pill {{ position: absolute; top: 12px; left: 12px; background: rgba(0,0,0,0.7); backdrop-filter: blur(8px); color: #fff; padding: 4px 10px; border-radius: 20px; font-size: 12px; font-weight: 700; border: 1px solid rgba(255,255,255,0.15); }}
        .content {{ padding: 20px; }}
        .title {{ font-size: 17px; font-weight: 700; line-height: 1.45; color: #f1f5f9; margin-bottom: 12px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }}
        .verdict-tag {{ display: inline-flex; align-items: center; gap: 6px; background: rgba(16, 185, 129, 0.15); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.3); padding: 5px 12px; border-radius: 8px; font-size: 12px; font-weight: 700; margin-bottom: 14px; }}
        .price-box {{ display: flex; align-items: baseline; gap: 12px; margin-bottom: 14px; }}
        .price-sale {{ font-size: 30px; font-weight: 900; color: { '#38bdf8' if platform == 'LAZADA' else '#ee4d2d' }; }}
        .price-orig {{ font-size: 15px; color: #94a3b8; text-decoration: line-through; }}
        .meta-info {{ display: flex; justify-content: space-between; font-size: 13px; color: #cbd5e1; margin-bottom: 18px; border-top: 1px dashed rgba(255,255,255,0.1); padding-top: 12px; }}
        .btn-deeplink {{ display: flex; align-items: center; justify-content: center; gap: 8px; width: 100%; background: { 'linear-gradient(135deg, #0284c7, #2563eb)' if platform == 'LAZADA' else 'linear-gradient(135deg, #ee4d2d 0%, #f97316 100%)' }; color: #fff; text-align: center; text-decoration: none; padding: 15px; font-size: 15px; font-weight: 800; border-radius: 12px; box-shadow: 0 8px 24px { 'rgba(2, 132, 199, 0.4)' if platform == 'LAZADA' else 'rgba(238, 77, 45, 0.4)' }; transition: transform 0.15s; margin-bottom: 10px; cursor: pointer; border: none; }}
        .btn-deeplink:active {{ transform: scale(0.98); }}
        .btn-web {{ display: block; width: 100%; background: rgba(255,255,255,0.06); color: #94a3b8; border: 1px solid rgba(255,255,255,0.12); text-align: center; text-decoration: none; padding: 10px; font-size: 13px; font-weight: 600; border-radius: 10px; }}
        .countdown {{ text-align: center; font-size: 12px; color: #94a3b8; margin-top: 14px; }}
        .countdown span {{ color: #fbbf24; font-weight: 800; }}
        .progress-bar {{ width: 100%; height: 3px; background: rgba(255,255,255,0.1); margin-top: 10px; border-radius: 2px; overflow: hidden; }}
        .progress-fill {{ height: 100%; background: { '#38bdf8' if platform == 'LAZADA' else '#ee4d2d' }; width: 0%; animation: fillProgress 1.6s linear forwards; }}
        @keyframes fillProgress {{ from {{ width: 0%; }} to {{ width: 100%; }} }}
    </style>
</head>
<body>
    <div class="card">
        {'''<div class="in-app-notice">
            <span>💡</span>
            <div><b>Mở trên App ''' + plat_name + ''':</b> Bấm nút to bên dưới để tự động mở ứng dụng, giữ nguyên đăng nhập và nhận trọn mã giảm giá!</div>
        </div>''' if is_in_app else ''}
        
        <div class="top-badge">
            <span>⚡</span> {plat_name.upper()} FLASH SALE CHÍNH HÃNG
        </div>
        <div class="img-container">
            <img src="{og_image}" alt="{deal_name}" onerror="this.src='/api/deals/image/{item_id}';">
            <div class="platform-pill">{ '🔵 LazMall' if platform == 'LAZADA' else '🟠 Shopee Mall' }</div>
            {f'<div class="discount-pill">-{discount}%</div>' if discount > 0 else ''}
        </div>
        <div class="content">
            <h1 class="title">{deal_name}</h1>
            <div class="verdict-tag">📉 {badge_text}</div>
            <div class="price-box">
                <span class="price-sale">{price_sale_formatted}</span>
                <span class="price-orig">{price_orig_formatted}</span>
            </div>
            <div class="meta-info">
                <span>⭐ {rating} / 5.0 uy tín</span>
                <span>🛒 Đã bán {sold:,} sản phẩm</span>
            </div>

            <button id="btnApp" class="btn-deeplink" onclick="launchAppDirectly()">
                <span>🛍️</span> MỞ TRÊN APP {plat_name.upper()} (ĐÃ ĐĂNG NHẬP)
            </button>

            <a id="btnWeb" href="{aff_url}" class="btn-web">
                Tiếp tục xem trên Trình duyệt Web ↗
            </a>

            <div class="countdown">Đang chuyển hướng tự động sau <span id="sec">2</span>s...</div>
            <div class="progress-bar"><div class="progress-fill"></div></div>
        </div>
    </div>

    <script>
        const targetUrl = "{aff_url}";
        const appScheme = "{app_scheme}";
        const androidIntent = "{android_intent if is_android else ''}";
        const isMobile = { 'true' if is_mobile else 'false' };
        const isAndroid = { 'true' if is_android else 'false' };
        const isInApp = { 'true' if is_in_app else 'false' };

        function launchAppDirectly() {{
            if (isMobile) {{
                if (isAndroid && androidIntent) {{
                    window.location.href = androidIntent;
                }} else {{
                    window.location.href = appScheme;
                    setTimeout(() => {{
                        window.location.href = targetUrl;
                    }}, 1200);
                }}
            }} else {{
                window.location.href = targetUrl;
            }}
        }}

        let s = 2;
        const sEl = document.getElementById('sec');
        const interval = setInterval(() => {{
            s--;
            if (sEl) sEl.textContent = s;
            if (s <= 0) {{
                clearInterval(interval);
                if (isInApp) {{
                    launchAppDirectly();
                }} else {{
                    window.location.href = targetUrl;
                }}
            }}
        }}, 900);
    </script>
</body>
</html>
    """
    return HTMLResponse(content=html_content)


@router.get("/deals", response_class=HTMLResponse)
def serve_deal_hub(platform: str = "ALL", category: str = "ALL", q: str = ""):
    """Trang web săn deal người dùng cực đẹp, hỗ trợ cả Shopee và Lazada, tối ưu SEO Google"""
    deals = db.get_deals(limit=60, platform=platform, is_stale=0, category_name=category, search=q)
    categories = db.get_active_categories()
    hunter = PromotionHunter(db)
    upcoming = hunter.get_upcoming_slot(datetime.now())
    html_content = DealHubRenderer.render_hub_page(
        deals=deals,
        categories=categories,
        active_platform=platform,
        active_cat=category,
        search_query=q,
        upcoming_slot=upcoming.get("slot", "12:00")
    )
    return HTMLResponse(content=html_content)


@router.get("/deal/{item_id}", response_class=HTMLResponse)
def serve_deal_detail(item_id: str):
    """Trang chi tiết deal riêng lẻ chuẩn SEO Schema.org"""
    deal = db.get_deal_by_id(item_id)
    if not deal:
        return HTMLResponse("<h3>Deal không tồn tại hoặc đã hết hạn</h3><p><a href='/deals'>← Về Cổng Săn Deal</a></p>", status_code=404)
    related = db.get_deals(limit=6, category_name=deal.get("category_name"), is_stale=0)
    related = [r for r in related if str(r.get("item_id")) != str(item_id)]
    html_content = DealDetailRenderer.render_detail_page(deal=deal, related_deals=related)
    return HTMLResponse(content=html_content)
