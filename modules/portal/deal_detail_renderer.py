import html
import json
from typing import Dict, List, Optional

class DealDetailRenderer:
    """Renderer cho trang chi tiết Deal riêng lẻ (/deal/{item_id}) tối ưu SEO Google"""

    @staticmethod
    def format_vnd(amount: float) -> str:
        try:
            return f"{int(amount):,}đ".replace(",", ".")
        except Exception:
            return "0đ"

    @classmethod
    def render_detail_page(cls, deal: Dict, related_deals: List[Dict], base_url: str = "") -> str:
        item_id = html.escape(str(deal.get("item_id", "")))
        name = html.escape(deal.get("name", "Chi tiết sản phẩm giảm giá"))
        price_sale = cls.format_vnd(deal.get("price_sale", 0))
        price_orig = cls.format_vnd(deal.get("price_original", 0))
        discount = int(deal.get("discount_percent", 0))
        rating = round(float(deal.get("rating_star", 5.0) or 5.0), 1)
        sold = int(deal.get("historical_sold", 0) or 0)
        platform = str(deal.get("platform", "SHOPEE")).upper()
        cat_name = html.escape(deal.get("category_name", "Hot Deal"))
        img_src = f"/api/deals/image/{item_id}" if deal.get("has_stamped_image") else (deal.get("image_url") or f"/api/deals/image/{item_id}")
        aff_url = f"/r/{item_id}?channel=web_detail"

        # Schema.org JSON-LD
        product_schema = json.dumps({
            "@context": "https://schema.org/",
            "@type": "Product",
            "name": deal.get("name", ""),
            "image": [deal.get("image_url", "")],
            "description": f"Săn sale {name} giá ưu đãi {price_sale} trên {platform}. Giảm {discount}% so với giá gốc {price_orig}.",
            "sku": item_id,
            "offers": {
                "@type": "Offer",
                "url": f"{base_url}{aff_url}",
                "priceCurrency": "VND",
                "price": str(int(deal.get("price_sale", 0))),
                "availability": "https://schema.org/InStock",
                "itemCondition": "https://schema.org/NewCondition"
            },
            "aggregateRating": {
                "@type": "AggregateRating",
                "ratingValue": str(rating),
                "reviewCount": str(max(10, sold // 5))
            }
        }, ensure_ascii=False)

        # Related deals HTML
        rel_html = []
        for r in related_deals[:4]:
            r_id = html.escape(str(r.get("item_id", "")))
            r_name = html.escape(r.get("name", ""))
            r_price = cls.format_vnd(r.get("price_sale", 0))
            r_img = r.get("image_url", f"/api/deals/image/{r_id}")
            rel_html.append(f"""
            <a href="/deal/{r_id}" class="rel-card">
                <img src="{r_img}" alt="{r_name}">
                <div class="rel-info">
                    <div class="rel-title">{r_name}</div>
                    <div class="rel-price">{r_price}</div>
                </div>
            </a>
            """)
        related_content = "".join(rel_html)

        html_out = f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>⚡ {name} - Giá chỉ {price_sale} (Giảm {discount}%) | Deal Săn Sale</title>
    <meta name="description" content="Mua ngay {name} giá tốt nhất hôm nay chỉ {price_sale} (giá gốc {price_orig}). Đánh giá {rating}/5 sao từ {sold:,} người mua trên {platform}.">
    <meta property="og:title" content="🔥 Flash Sale: {name} - Chỉ {price_sale}">
    <meta property="og:description" content="Giá sốc giảm {discount}%. Mua chính hãng trên {platform} ngay!">
    <meta property="og:image" content="{img_src}">
    <meta property="og:type" content="product">
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;700;800&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
    <script type="application/ld+json">
        {product_schema}
    </script>
    <style>
        :root {{
            --bg-base: #090d16;
            --bg-card: rgba(17, 24, 39, 0.85);
            --border-color: rgba(255, 255, 255, 0.1);
            --shopee-gradient: linear-gradient(135deg, #ff5722 0%, #ee4d2d 100%);
            --lazada-gradient: linear-gradient(135deg, #002bff 0%, #00bfff 100%);
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            background: var(--bg-base);
            color: #f8fafc;
            font-family: 'Plus Jakarta Sans', sans-serif;
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{
            max-width: 980px;
            margin: 20px auto;
        }}
        .back-nav {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            color: #94a3b8;
            text-decoration: none;
            font-size: 14px;
            margin-bottom: 20px;
        }}
        .back-nav:hover {{ color: #fff; }}
        .detail-card {{
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 24px;
            padding: 32px;
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 36px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.5);
            backdrop-filter: blur(10px);
        }}
        .detail-img {{
            width: 100%;
            height: 380px;
            border-radius: 16px;
            overflow: hidden;
            background: #000;
        }}
        .detail-img img {{
            width: 100%;
            height: 100%;
            object-fit: cover;
        }}
        .badge-plat {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 700;
            margin-bottom: 12px;
            background: {'var(--lazada-gradient)' if platform == 'LAZADA' else 'var(--shopee-gradient)'};
        }}
        .product-title {{
            font-family: 'Outfit', sans-serif;
            font-size: 24px;
            font-weight: 700;
            line-height: 1.3;
            margin-bottom: 14px;
        }}
        .meta-stats {{
            display: flex;
            gap: 16px;
            font-size: 14px;
            color: #94a3b8;
            margin-bottom: 20px;
            padding-bottom: 16px;
            border-bottom: 1px solid var(--border-color);
        }}
        .price-box {{
            display: flex;
            align-items: baseline;
            gap: 12px;
            margin-bottom: 24px;
        }}
        .sale-price {{
            font-family: 'Outfit', sans-serif;
            font-size: 36px;
            font-weight: 800;
            color: #ee4d2d;
        }}
        .orig-price {{
            font-size: 18px;
            color: #64748b;
            text-decoration: line-through;
        }}
        .disc-pill {{
            background: #facc15;
            color: #991b1b;
            font-weight: 800;
            padding: 4px 10px;
            border-radius: 8px;
            font-size: 14px;
        }}
        .btn-cta {{
            display: block;
            width: 100%;
            background: {'var(--lazada-gradient)' if platform == 'LAZADA' else 'var(--shopee-gradient)'};
            color: #fff;
            text-align: center;
            text-decoration: none;
            padding: 16px;
            font-size: 16px;
            font-weight: 700;
            border-radius: 14px;
            box-shadow: 0 8px 24px rgba(238, 77, 45, 0.4);
            transition: transform 0.2s;
        }}
        .btn-cta:hover {{ transform: scale(1.02); }}
        .related-box {{
            margin-top: 40px;
        }}
        .rel-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
            gap: 16px;
            margin-top: 16px;
        }}
        .rel-card {{
            background: rgba(255,255,255,0.03);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 12px;
            display: flex;
            gap: 10px;
            text-decoration: none;
            color: inherit;
        }}
        .rel-card img {{
            width: 60px;
            height: 60px;
            border-radius: 8px;
            object-fit: cover;
        }}
        .rel-title {{
            font-size: 12px;
            line-height: 1.3;
            max-height: 32px;
            overflow: hidden;
        }}
        .rel-price {{
            font-size: 13px;
            font-weight: 700;
            color: #ee4d2d;
            margin-top: 4px;
        }}
        @media (max-width: 768px) {{
            .detail-card {{ grid-template-columns: 1fr; }}
            .detail-img {{ height: 260px; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <a href="/deals" class="back-nav">← Quay lại Cổng Săn Deal</a>
        <div class="detail-card">
            <div class="detail-img">
                <img src="{img_src}" alt="{name}">
            </div>
            <div>
                <span class="badge-plat">{platform} MALL</span>
                <h1 class="product-title">{name}</h1>
                <div class="meta-stats">
                    <span>⭐ {rating} / 5.0</span>
                    <span>🛒 Đã bán {sold:,}</span>
                    <span>📁 {cat_name}</span>
                </div>
                <div class="price-box">
                    <span class="sale-price">{price_sale}</span>
                    <span class="orig-price">{price_orig}</span>
                    {f'<span class="disc-pill">-{discount}%</span>' if discount > 0 else ''}
                </div>
                <a href="{aff_url}" target="_blank" rel="nofollow noopener" class="btn-cta">
                    MUA NGAY TRÊN {platform} ➔
                </a>
            </div>
        </div>

        {f'<div class="related-box"><h3>Sản Phẩm Cùng Ngành Khác</h3><div class="rel-grid">{related_content}</div></div>' if related_content else ''}
    </div>
</body>
</html>
        """
        return html_out
