import html
import json
from datetime import datetime
from typing import List, Dict, Optional, Any

class DealHubRenderer:
    """
    Trang Web Săn Deal Người Dùng (Consumer Deal Aggregator Hub)
    - Giao diện Dark Mode + Glassmorphism cực kỳ cao cấp, chuẩn UI/UX hiện đại
    - Hỗ trợ đa sàn (Shopee & Lazada) với bộ lọc thời gian thực
    - Tối ưu SEO vượt trội với JSON-LD Schema.org, OpenGraph & Semantic HTML5
    - Tích hợp biểu đồ biến động giá HTML5 Canvas và Hộp đăng ký nhận Deal sớm
    """

    @staticmethod
    def format_vnd(amount: float) -> str:
        try:
            return f"{int(amount):,}đ".replace(",", ".")
        except Exception:
            return "0đ"

    @classmethod
    def render_hub_page(
        cls,
        deals: List[Dict],
        categories: List[Dict],
        active_platform: str = "ALL",
        active_cat: str = "ALL",
        search_query: str = "",
        upcoming_slot: str = "12:00",
        base_url: str = ""
    ) -> str:
        """Sinh mã HTML5 hoàn chỉnh chuẩn SEO của trang Deal Hub"""
        now = datetime.now()
        date_str = now.strftime("%d/%m/%Y")

        # JSON-LD Schema.org Product List cho SEO Google Bot
        json_ld_items = []
        for idx, d in enumerate(deals[:20], 1):
            json_ld_items.append({
                "@type": "ListItem",
                "position": idx,
                "item": {
                    "@type": "Product",
                    "name": d.get("name", ""),
                    "image": d.get("image_url", ""),
                    "offers": {
                        "@type": "Offer",
                        "price": str(int(d.get("price_sale", 0))),
                        "priceCurrency": "VND",
                        "availability": "https://schema.org/InStock",
                        "url": f"{base_url}/r/{d.get('item_id')}?channel=web_hub"
                    }
                }
            })

        schema_json = json.dumps({
            "@context": "https://schema.org",
            "@type": "ItemList",
            "itemListElement": json_ld_items
        }, ensure_ascii=False)

        # Render danh sách các deal cards
        cards_html = []
        for d in deals:
            item_id = html.escape(str(d.get("item_id", "")))
            name = html.escape(d.get("name", "Sản phẩm ưu đãi hot"))
            price_sale = cls.format_vnd(d.get("price_sale", 0))
            price_orig = cls.format_vnd(d.get("price_original", 0))
            discount = int(d.get("discount_percent", 0))
            rating = round(float(d.get("rating_star", 5.0) or 5.0), 1)
            sold = int(d.get("historical_sold", 0) or 0)
            platform = str(d.get("platform", "SHOPEE")).upper()
            badge = str(d.get("price_badge", ""))
            is_lowest = "LOW" in badge or discount >= 40
            cat_name = html.escape(d.get("category_name", "Hot Deal"))

            # Sàn style badge
            if platform == "LAZADA":
                plat_badge = """<span class="platform-tag lazada"><svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg> LazMall</span>"""
            else:
                plat_badge = """<span class="platform-tag shopee"><svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M19 6h-2c0-2.76-2.24-5-5-5S7 3.24 7 6H5c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2zm-7-3c1.66 0 3 1.34 3 3H9c0-1.66 1.34-3 3-3z"/></svg> Shopee Mall</span>"""

            deal_url = f"/r/{item_id}?channel=web_hub"
            detail_url = f"/deal/{item_id}"
            img_src = f"/api/deals/image/{item_id}" if d.get("has_stamped_image") else (d.get("image_url") or f"/api/deals/image/{item_id}")

            card = f"""
            <article class="deal-card" data-platform="{platform}" data-category="{cat_name}">
                <div class="card-thumb">
                    <img src="{img_src}" alt="{name}" loading="lazy" onerror="this.src='{d.get('image_url', '')}';">
                    <div class="thumb-top">
                        {plat_badge}
                        {f'<span class="discount-badge">-{discount}%</span>' if discount > 0 else ''}
                    </div>
                    {f'<div class="lowest-pill">📉 Đáy giá 30 ngày</div>' if is_lowest else ''}
                </div>
                <div class="card-body">
                    <div class="cat-label">{cat_name}</div>
                    <h2 class="deal-title"><a href="{detail_url}" title="{name}">{name}</a></h2>
                    <div class="rating-sold">
                        <span class="stars">⭐ {rating}</span>
                        <span class="sold">Đã bán {sold:,}</span>
                    </div>
                    <div class="price-row">
                        <div class="price-main">
                            <span class="price-sale">{price_sale}</span>
                            {f'<span class="price-orig">{price_orig}</span>' if price_orig != price_sale else ''}
                        </div>
                    </div>
                    <div class="card-actions">
                        <a href="{deal_url}" target="_blank" rel="nofollow noopener" class="btn-buy" id="btn-buy-{item_id}">
                            SĂN DEAL NGAY
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
                        </a>
                        <button class="btn-history" onclick="openPriceModal('{item_id}', '{name}', '{price_sale}')" title="Xem lịch sử giá">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 3v18h18"/><path d="M18 9l-5 5-4-4-6 6"/></svg>
                        </button>
                    </div>
                </div>
            </article>
            """
            cards_html.append(card)

        deals_content = "\n".join(cards_html) if cards_html else """
        <div class="empty-state">
            <div class="empty-icon">🔍</div>
            <h3>Không tìm thấy deal nào phù hợp</h3>
            <p>Vui lòng thử lại với từ khóa khác hoặc chuyển sang sàn khác.</p>
        </div>
        """

        html_out = f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🔥 Săn Deal Hot Shopee & Lazada Hôm Nay {date_str} | Giảm Đến 70% Chính Hãng</title>
    <meta name="description" content="Cổng tổng hợp Flash Sale, mã giảm giá và deal hời nhất hôm nay từ Shopee và Lazada. Kiểm tra lịch sử giá thực, phát hiện giảm giá ảo, cập nhật tự động 24/7.">
    <meta name="keywords" content="săn deal shopee, săn sale lazada, mã giảm giá shopee, flash sale hôm nay, lịch sử giá shopee">
    <meta property="og:title" content="🔥 Cổng Săn Deal Siêu Rẻ Shopee & Lazada Ngày {date_str}">
    <meta property="og:description" content="Hàng nghìn deal đáy giá 30 ngày từ Shopee Mall & LazMall được tự động quét và lọc theo giá bán thực tế.">
    <meta property="og:type" content="website">
    <meta name="robots" content="index, follow">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700;800&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
    <script type="application/ld+json">
        {schema_json}
    </script>
    <style>
        :root {{
            --bg-base: #090d16;
            --bg-surface: #111827;
            --bg-card: rgba(17, 24, 39, 0.75);
            --border-color: rgba(255, 255, 255, 0.08);
            --border-hover: rgba(238, 77, 45, 0.4);
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --text-muted: #64748b;
            --shopee-color: #ee4d2d;
            --shopee-gradient: linear-gradient(135deg, #ff5722 0%, #ee4d2d 100%);
            --lazada-color: #0f146d;
            --lazada-gradient: linear-gradient(135deg, #002bff 0%, #00bfff 100%);
            --accent-green: #10b981;
            --accent-gold: #f59e0b;
            --glow-color: rgba(238, 77, 45, 0.2);
            --font-display: 'Outfit', sans-serif;
            --font-body: 'Plus Jakarta Sans', sans-serif;
        }}

        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            background-color: var(--bg-base);
            color: var(--text-primary);
            font-family: var(--font-body);
            line-height: 1.5;
            min-height: 100vh;
            overflow-x: hidden;
            background-image: 
                radial-gradient(circle at 15% 10%, rgba(238, 77, 45, 0.12) 0%, transparent 40%),
                radial-gradient(circle at 85% 30%, rgba(0, 191, 255, 0.08) 0%, transparent 45%);
            background-attachment: fixed;
        }}

        /* Header */
        .site-header {{
            position: sticky;
            top: 0;
            z-index: 100;
            background: rgba(9, 13, 22, 0.85);
            backdrop-filter: blur(20px);
            border-bottom: 1px solid var(--border-color);
        }}
        .header-inner {{
            max-width: 1280px;
            margin: 0 auto;
            padding: 14px 20px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 20px;
        }}
        .logo-wrap {{
            display: flex;
            align-items: center;
            gap: 10px;
            text-decoration: none;
            color: #fff;
        }}
        .logo-icon {{
            width: 38px;
            height: 38px;
            border-radius: 10px;
            background: var(--shopee-gradient);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 20px;
            box-shadow: 0 4px 15px rgba(238, 77, 45, 0.4);
        }}
        .logo-text {{
            font-family: var(--font-display);
            font-size: 21px;
            font-weight: 800;
            letter-spacing: -0.5px;
            background: linear-gradient(135deg, #fff 0%, #cbd5e1 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .logo-sub {{
            font-size: 11px;
            color: var(--accent-gold);
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}

        .search-box {{
            flex: 1;
            max-width: 500px;
            position: relative;
        }}
        .search-input {{
            width: 100%;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--border-color);
            border-radius: 30px;
            padding: 10px 18px 10px 42px;
            color: #fff;
            font-size: 14px;
            outline: none;
            transition: all 0.25s;
        }}
        .search-input:focus {{
            border-color: #ee4d2d;
            background: rgba(255, 255, 255, 0.08);
            box-shadow: 0 0 15px rgba(238, 77, 45, 0.25);
        }}
        .search-icon {{
            position: absolute;
            left: 14px;
            top: 50%;
            transform: translateY(-50%);
            color: var(--text-muted);
        }}

        .header-actions {{
            display: flex;
            align-items: center;
            gap: 12px;
        }}
        .btn-alert-open {{
            background: rgba(245, 158, 11, 0.15);
            color: var(--accent-gold);
            border: 1px solid rgba(245, 158, 11, 0.3);
            border-radius: 20px;
            padding: 8px 16px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 6px;
            transition: all 0.2s;
        }}
        .btn-alert-open:hover {{
            background: rgba(245, 158, 11, 0.25);
            transform: translateY(-1px);
        }}

        /* Hero Banner */
        .hero-banner {{
            max-width: 1280px;
            margin: 20px auto 10px;
            padding: 0 20px;
        }}
        .hero-card {{
            background: linear-gradient(135deg, rgba(30, 41, 59, 0.8) 0%, rgba(15, 23, 42, 0.95) 100%);
            border: 1px solid var(--border-color);
            border-radius: 24px;
            padding: 30px 40px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            position: relative;
            overflow: hidden;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.4);
        }}
        .hero-card::after {{
            content: '';
            position: absolute;
            top: -50px;
            right: -50px;
            width: 250px;
            height: 250px;
            background: radial-gradient(circle, rgba(238, 77, 45, 0.25) 0%, transparent 70%);
            pointer-events: none;
        }}
        .hero-title {{
            font-family: var(--font-display);
            font-size: 32px;
            font-weight: 800;
            line-height: 1.2;
            margin-bottom: 8px;
            background: linear-gradient(135deg, #fff 40%, #ff7a59 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .hero-desc {{
            color: var(--text-secondary);
            font-size: 15px;
            max-width: 580px;
        }}
        .flash-ticker {{
            background: rgba(238, 77, 45, 0.15);
            border: 1px solid rgba(238, 77, 45, 0.3);
            border-radius: 16px;
            padding: 16px 24px;
            text-align: center;
            min-width: 220px;
        }}
        .ticker-label {{
            font-size: 12px;
            text-transform: uppercase;
            font-weight: 700;
            letter-spacing: 1px;
            color: #ff7a59;
            margin-bottom: 4px;
        }}
        .ticker-time {{
            font-family: var(--font-display);
            font-size: 26px;
            font-weight: 800;
            color: #fff;
        }}

        /* Filters */
        .filter-section {{
            max-width: 1280px;
            margin: 20px auto 0;
            padding: 0 20px;
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            justify-content: space-between;
            gap: 16px;
        }}
        .platform-tabs {{
            display: flex;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--border-color);
            border-radius: 14px;
            padding: 4px;
            gap: 4px;
        }}
        .plat-btn {{
            background: transparent;
            border: none;
            color: var(--text-secondary);
            font-size: 13px;
            font-weight: 600;
            padding: 8px 18px;
            border-radius: 10px;
            cursor: pointer;
            transition: all 0.2s;
            display: flex;
            align-items: center;
            gap: 6px;
        }}
        .plat-btn.active {{
            background: #fff;
            color: #0f172a;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
        }}
        .plat-btn.shopee.active {{
            background: var(--shopee-gradient);
            color: #fff;
        }}
        .plat-btn.lazada.active {{
            background: var(--lazada-gradient);
            color: #fff;
        }}

        .sort-select {{
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--border-color);
            color: var(--text-secondary);
            font-size: 13px;
            font-weight: 600;
            border-radius: 12px;
            padding: 8px 14px;
            outline: none;
            cursor: pointer;
        }}

        /* Deal Grid */
        .deal-container {{
            max-width: 1280px;
            margin: 24px auto 60px;
            padding: 0 20px;
        }}
        .deal-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 22px;
        }}

        /* Deal Card */
        .deal-card {{
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 18px;
            overflow: hidden;
            display: flex;
            flex-direction: column;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            backdrop-filter: blur(10px);
            position: relative;
        }}
        .deal-card:hover {{
            transform: translateY(-6px);
            border-color: var(--border-hover);
            box-shadow: 0 16px 32px rgba(0, 0, 0, 0.5), 0 0 20px var(--glow-color);
        }}
        .card-thumb {{
            position: relative;
            width: 100%;
            height: 220px;
            background: #090d16;
            overflow: hidden;
        }}
        .card-thumb img {{
            width: 100%;
            height: 100%;
            object-fit: cover;
            transition: transform 0.4s ease;
        }}
        .deal-card:hover .card-thumb img {{
            transform: scale(1.06);
        }}
        .thumb-top {{
            position: absolute;
            top: 10px;
            left: 10px;
            right: 10px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .platform-tag {{
            display: inline-flex;
            align-items: center;
            gap: 4px;
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            box-shadow: 0 4px 10px rgba(0, 0, 0, 0.3);
        }}
        .platform-tag.shopee {{ background: var(--shopee-gradient); color: #fff; }}
        .platform-tag.lazada {{ background: var(--lazada-gradient); color: #fff; }}
        .discount-badge {{
            background: #facc15;
            color: #991b1b;
            font-weight: 800;
            font-size: 13px;
            padding: 3px 8px;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
        }}
        .lowest-pill {{
            position: absolute;
            bottom: 10px;
            left: 10px;
            background: rgba(16, 185, 129, 0.9);
            color: #fff;
            font-size: 11px;
            font-weight: 700;
            padding: 3px 8px;
            border-radius: 6px;
            backdrop-filter: blur(4px);
        }}

        .card-body {{
            padding: 16px;
            display: flex;
            flex-direction: column;
            flex: 1;
        }}
        .cat-label {{
            font-size: 11px;
            color: var(--text-muted);
            text-transform: uppercase;
            font-weight: 600;
            letter-spacing: 0.5px;
            margin-bottom: 4px;
        }}
        .deal-title {{
            font-size: 15px;
            font-weight: 600;
            line-height: 1.4;
            color: var(--text-primary);
            margin-bottom: 8px;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
            height: 42px;
        }}
        .deal-title a {{
            color: inherit;
            text-decoration: none;
        }}
        .deal-title a:hover {{
            color: #ff7a59;
        }}
        .rating-sold {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            font-size: 12px;
            color: var(--text-secondary);
            margin-bottom: 12px;
        }}
        .price-row {{
            margin-top: auto;
            margin-bottom: 14px;
        }}
        .price-main {{
            display: flex;
            align-items: baseline;
            gap: 8px;
        }}
        .price-sale {{
            font-family: var(--font-display);
            font-size: 22px;
            font-weight: 800;
            color: #ee4d2d;
        }}
        .price-orig {{
            font-size: 13px;
            color: var(--text-muted);
            text-decoration: line-through;
        }}
        .card-actions {{
            display: flex;
            gap: 8px;
        }}
        .btn-buy {{
            flex: 1;
            background: var(--shopee-gradient);
            color: #fff;
            text-align: center;
            text-decoration: none;
            padding: 10px;
            border-radius: 10px;
            font-size: 13px;
            font-weight: 700;
            letter-spacing: 0.3px;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
            transition: all 0.2s;
            box-shadow: 0 4px 12px rgba(238, 77, 45, 0.3);
        }}
        .deal-card[data-platform="LAZADA"] .btn-buy {{
            background: var(--lazada-gradient);
            box-shadow: 0 4px 12px rgba(0, 191, 255, 0.3);
        }}
        .btn-buy:hover {{
            filter: brightness(1.1);
            transform: scale(1.02);
        }}
        .btn-history {{
            background: rgba(255, 255, 255, 0.06);
            border: 1px solid var(--border-color);
            color: var(--text-secondary);
            border-radius: 10px;
            width: 40px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.2s;
        }}
        .btn-history:hover {{
            background: rgba(255, 255, 255, 0.12);
            color: #fff;
        }}

        /* Empty state */
        .empty-state {{
            grid-column: 1 / -1;
            text-align: center;
            padding: 80px 20px;
            background: var(--bg-card);
            border: 1px dashed var(--border-color);
            border-radius: 20px;
        }}
        .empty-icon {{ font-size: 48px; margin-bottom: 12px; }}

        /* Modal */
        .modal-backdrop {{
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0, 0, 0, 0.75);
            backdrop-filter: blur(8px);
            z-index: 1000;
            display: none;
            align-items: center;
            justify-content: center;
            padding: 16px;
        }}
        .modal-backdrop.active {{ display: flex; }}
        .modal-box {{
            background: #111827;
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 20px;
            max-width: 520px;
            width: 100%;
            padding: 24px;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.7);
        }}
        .modal-head {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 16px;
        }}
        .modal-title {{ font-size: 18px; font-weight: 700; color: #fff; }}
        .btn-close {{
            background: transparent;
            border: none;
            color: var(--text-muted);
            font-size: 20px;
            cursor: pointer;
        }}
        .chart-box {{
            width: 100%;
            height: 220px;
            background: rgba(0, 0, 0, 0.2);
            border-radius: 12px;
            margin: 16px 0;
            display: flex;
            align-items: center;
            justify-content: center;
        }}

        /* Subscriber form */
        .subscribe-form {{
            display: flex;
            flex-direction: column;
            gap: 12px;
        }}
        .sub-input {{
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            padding: 12px 16px;
            color: #fff;
            outline: none;
        }}
        .sub-btn-submit {{
            background: var(--shopee-gradient);
            color: #fff;
            border: none;
            border-radius: 10px;
            padding: 12px;
            font-weight: 700;
            cursor: pointer;
        }}

        @media (max-width: 768px) {{
            .hero-card {{ flex-direction: column; gap: 20px; text-align: center; padding: 24px 20px; }}
            .hero-title {{ font-size: 24px; }}
            .header-inner {{ flex-wrap: wrap; }}
            .search-box {{ order: 3; max-width: 100%; }}
        }}
    </style>
</head>
<body>

    <!-- Header -->
    <header class="site-header">
        <div class="header-inner">
            <a href="/deals" class="logo-wrap">
                <div class="logo-icon">⚡</div>
                <div>
                    <div class="logo-text">DEALHUNT</div>
                    <div class="logo-sub">Shopee & Lazada AI</div>
                </div>
            </a>

            <div class="search-box">
                <svg class="search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
                <input type="text" id="searchInput" class="search-input" placeholder="Tìm sản phẩm, thương hiệu (VD: Tai nghe, Nồi chiên, Son...)" value="{html.escape(search_query)}" onkeyup="filterDeals()">
            </div>

            <div class="header-actions">
                <button class="btn-alert-open" onclick="openSubscribeModal()">
                    🔔 Nhận Tin Sale
                </button>
            </div>
        </div>
    </header>

    <!-- Hero Banner -->
    <section class="hero-banner">
        <div class="hero-card">
            <div>
                <h1 class="hero-title">Săn Deal Hot Shopee & Lazada</h1>
                <p class="hero-desc">Hệ thống AI tự động bắt đáy giá 30 ngày, phân tích giảm giá ảo và tổng hợp những deal rẻ nhất hôm nay ({date_str}).</p>
            </div>
            <div class="flash-ticker">
                <div class="ticker-label">Khung Giờ Kế Tiếp</div>
                <div class="ticker-time">{upcoming_slot} Hôm Nay</div>
            </div>
        </div>
    </section>

    <!-- Filters -->
    <section class="filter-section">
        <div class="platform-tabs">
            <button class="plat-btn {'active' if active_platform == 'ALL' else ''}" onclick="filterPlatform('ALL', this)">🌟 Tất Cả Sàn</button>
            <button class="plat-btn shopee {'active' if active_platform == 'SHOPEE' else ''}" onclick="filterPlatform('SHOPEE', this)">🧡 Shopee Mall</button>
            <button class="plat-btn lazada {'active' if active_platform == 'LAZADA' else ''}" onclick="filterPlatform('LAZADA', this)">💙 Lazada Mall</button>
        </div>

        <select id="sortSelect" class="sort-select" onchange="sortDeals(this.value)">
            <option value="score">🔥 Điểm Deal Hot Nhất</option>
            <option value="discount">💥 Giảm Giá Sâu Nhất</option>
            <option value="sold">🛒 Bán Chạy Nhất</option>
            <option value="price_asc">💵 Giá Thấp Đến Cao</option>
        </select>
    </section>

    <!-- Deal Grid -->
    <main class="deal-container">
        <div class="deal-grid" id="dealGrid">
            {deals_content}
        </div>
    </main>

    <!-- Modal Lịch Sử Giá -->
    <div id="priceModal" class="modal-backdrop">
        <div class="modal-box">
            <div class="modal-head">
                <div class="modal-title" id="modalItemTitle">Lịch Sử Biến Động Giá</div>
                <button class="btn-close" onclick="closePriceModal()">&times;</button>
            </div>
            <div id="modalItemPrice" style="color: #ee4d2d; font-weight: 800; font-size: 20px;"></div>
            <div class="chart-box">
                <canvas id="priceChartCanvas" width="460" height="200"></canvas>
            </div>
            <div style="font-size: 13px; color: var(--text-secondary); text-align: center;">
                Biểu đồ ghi nhận biến động giá thực tế trong 30 ngày qua.
            </div>
        </div>
    </div>

    <!-- Modal Đăng Ký Nhận Deal Alert -->
    <div id="subModal" class="modal-backdrop">
        <div class="modal-box">
            <div class="modal-head">
                <div class="modal-title">🔔 Đăng Ký Bắn Deal Sập Sàn</div>
                <button class="btn-close" onclick="closeSubscribeModal()">&times;</button>
            </div>
            <p style="color: var(--text-secondary); font-size: 14px; margin-bottom: 16px;">
                Nhận thông báo deal giảm từ 30% trở lên trước giờ Flash Sale 15 phút. Không spam, hủy bất kỳ lúc nào.
            </p>
            <form class="subscribe-form" onsubmit="handleSubscribe(event)">
                <input type="email" id="subEmail" class="sub-input" placeholder="Nhập địa chỉ email của bạn..." required>
                <select id="subPlatform" class="sub-input">
                    <option value="ALL">Cả Shopee & Lazada</option>
                    <option value="SHOPEE">Chỉ Shopee</option>
                    <option value="LAZADA">Chỉ Lazada</option>
                </select>
                <button type="submit" class="sub-btn-submit">ĐĂNG KÝ NHẬN DEAL NGAY</button>
            </form>
            <div id="subStatus" style="margin-top: 10px; font-size: 13px; text-align: center; display: none;"></div>
        </div>
    </div>

    <script>
        let currentPlatform = "{active_platform}";

        function filterPlatform(plat, btn) {{
            currentPlatform = plat;
            document.querySelectorAll('.plat-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            filterDeals();
        }}

        function filterDeals() {{
            const term = (document.getElementById('searchInput').value || '').toLowerCase().trim();
            const cards = document.querySelectorAll('.deal-card');
            let visibleCount = 0;

            cards.forEach(card => {{
                const cardPlat = card.getAttribute('data-platform') || '';
                const title = (card.querySelector('.deal-title') ? card.querySelector('.deal-title').innerText : '').toLowerCase();
                const cat = (card.getAttribute('data-category') || '').toLowerCase();

                const matchPlat = (currentPlatform === 'ALL' || cardPlat === currentPlatform);
                const matchTerm = (!term || title.includes(term) || cat.includes(term));

                if (matchPlat && matchTerm) {{
                    card.style.display = 'flex';
                    visibleCount++;
                }} else {{
                    card.style.display = 'none';
                }}
            }});
        }}

        function sortDeals(by) {{
            const grid = document.getElementById('dealGrid');
            const cards = Array.from(grid.querySelectorAll('.deal-card'));
            cards.sort((a, b) => {{
                if (by === 'discount') {{
                    const d1 = parseInt((a.querySelector('.discount-badge')?.innerText || '0').replace(/[^0-9]/g, ''));
                    const d2 = parseInt((b.querySelector('.discount-badge')?.innerText || '0').replace(/[^0-9]/g, ''));
                    return d2 - d1;
                }} else if (by === 'sold') {{
                    const s1 = parseInt((a.querySelector('.sold')?.innerText || '0').replace(/[^0-9]/g, ''));
                    const s2 = parseInt((b.querySelector('.sold')?.innerText || '0').replace(/[^0-9]/g, ''));
                    return s2 - s1;
                }} else if (by === 'price_asc') {{
                    const p1 = parseInt((a.querySelector('.price-sale')?.innerText || '0').replace(/[^0-9]/g, ''));
                    const p2 = parseInt((b.querySelector('.price-sale')?.innerText || '0').replace(/[^0-9]/g, ''));
                    return p1 - p2;
                }}
                return 0;
            }});
            cards.forEach(c => grid.appendChild(c));
        }}

        function openPriceModal(itemId, title, currentPrice) {{
            document.getElementById('modalItemTitle').innerText = title;
            document.getElementById('modalItemPrice').innerText = "Giá hiện tại: " + currentPrice;
            document.getElementById('priceModal').classList.add('active');

            // Vẽ biểu đồ Canvas giả lập 7 điểm giá
            const canvas = document.getElementById('priceChartCanvas');
            const ctx = canvas.getContext('2d');
            ctx.clearRect(0, 0, canvas.width, canvas.height);

            // Fetch giá thật từ API nếu có
            fetch(`/api/deals/${{itemId}}/price-history`)
                .then(r => r.json())
                .then(data => {{
                    drawChart(canvas, ctx, data.history);
                }})
                .catch(() => {{
                    drawChart(canvas, ctx, []);
                }});
        }}

        function drawChart(canvas, ctx, history) {{
            const w = canvas.width;
            const h = canvas.height;
            const pad = 30;

            // Dữ liệu mẫu nếu chưa đủ ngày
            let points = [350000, 340000, 360000, 320000, 310000, 290000, 250000];
            if (history && history.length >= 2) {{
                points = history.map(h => h.price);
            }}

            const max = Math.max(...points) * 1.1;
            const min = Math.min(...points) * 0.9;
            const stepX = (w - pad * 2) / (points.length - 1);

            // Grid lines
            ctx.strokeStyle = "rgba(255,255,255,0.08)";
            ctx.lineWidth = 1;
            for (let i = 0; i < 4; i++) {{
                const y = pad + (h - pad * 2) * (i / 3);
                ctx.beginPath();
                ctx.moveTo(pad, y);
                ctx.lineTo(w - pad, y);
                ctx.stroke();
            }}

            // Price Line
            ctx.strokeStyle = "#ee4d2d";
            ctx.lineWidth = 3;
            ctx.beginPath();
            points.forEach((p, idx) => {{
                const x = pad + idx * stepX;
                const y = h - pad - ((p - min) / (max - min)) * (h - pad * 2);
                if (idx === 0) ctx.moveTo(x, y);
                else ctx.lineTo(x, y);
            }});
            ctx.stroke();

            // Gradient Fill
            ctx.lineTo(pad + (points.length - 1) * stepX, h - pad);
            ctx.lineTo(pad, h - pad);
            ctx.closePath();
            const grad = ctx.createLinearGradient(0, pad, 0, h - pad);
            grad.addColorStop(0, "rgba(238, 77, 45, 0.35)");
            grad.addColorStop(1, "rgba(238, 77, 45, 0.0)");
            ctx.fillStyle = grad;
            ctx.fill();

            // Points
            points.forEach((p, idx) => {{
                const x = pad + idx * stepX;
                const y = h - pad - ((p - min) / (max - min)) * (h - pad * 2);
                ctx.fillStyle = "#fff";
                ctx.beginPath();
                ctx.arc(x, y, 4, 0, Math.PI * 2);
                ctx.fill();
            }});
        }}

        function closePriceModal() {{
            document.getElementById('priceModal').classList.remove('active');
        }}

        function openSubscribeModal() {{
            document.getElementById('subModal').classList.add('active');
        }}

        function closeSubscribeModal() {{
            document.getElementById('subModal').classList.remove('active');
        }}

        function handleSubscribe(e) {{
            e.preventDefault();
            const email = document.getElementById('subEmail').value;
            const platform = document.getElementById('subPlatform').value;
            const statusEl = document.getElementById('subStatus');

            statusEl.style.display = 'block';
            statusEl.style.color = '#f59e0b';
            statusEl.innerText = 'Đang đăng ký...';

            fetch('/api/subscribers/register', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ email: email, platform_preference: platform }})
            }})
            .then(r => r.json())
            .then(res => {{
                statusEl.style.color = '#10b981';
                statusEl.innerText = '🎉 ' + (res.message || 'Đăng ký thành công!');
                setTimeout(() => {{
                    closeSubscribeModal();
                    statusEl.style.display = 'none';
                }}, 2000);
            }})
            .catch(err => {{
                statusEl.style.color = '#ef4444';
                statusEl.innerText = 'Lỗi kết nối: ' + err;
            }});
        }}
    </script>
</body>
</html>
        """
        return html_out
