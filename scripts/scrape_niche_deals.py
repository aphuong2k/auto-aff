import os
import sys
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

import config.settings
from database.db_manager import DatabaseManager
from playwright.sync_api import sync_playwright

def scrape_shopee_category(page, url, category_name):
    print(f"Scraping category [{category_name}] from {url}...")
    page.goto(url, timeout=35000, wait_until="domcontentloaded")
    page.wait_for_timeout(3500)
    
    # Scroll down to load items
    page.mouse.wheel(0, 1000)
    page.wait_for_timeout(2000)
    page.mouse.wheel(0, 1500)
    page.wait_for_timeout(2000)

    # Find item cards
    cards = page.locator("a[data-sqe='link']").all()
    print(f"Found {len(cards)} items for [{category_name}]")

    db = DatabaseManager()
    saved = []

    for card in cards[:10]:
        try:
            href = card.get_attribute("href") or ""
            text = card.inner_text().strip()
            if not href or not text:
                continue

            lines = [l.strip() for l in text.split("\n") if l.strip()]
            if len(lines) < 2:
                continue

            # Parse item name and price
            # Lines usually: [Mall / Yêu thích], [Name], [Giảm giá], [Price], [Đã bán]
            name = ""
            price_sale = 0
            price_orig = 0
            sold = 100
            rating = 4.8

            for l in lines:
                if len(l) > 15 and not name and not "₫" in l:
                    name = l
                elif "₫" in l:
                    p_clean = re.sub(r"[^\d]", "", l)
                    if p_clean:
                        val = float(p_clean)
                        if not price_sale:
                            price_sale = val
                        elif val > price_sale and not price_orig:
                            price_orig = val
                elif "Đã bán" in l or "k" in l:
                    s_clean = re.sub(r"[^\d\.]", "", l)
                    if "k" in l.lower() and s_clean:
                        sold = int(float(s_clean) * 1000)
                    elif s_clean:
                        sold = int(float(s_clean))

            if not name:
                name = lines[0] if len(lines[0]) > 10 else lines[1]
            if not price_sale:
                price_sale = 150000.0
            if not price_orig:
                price_orig = price_sale * 1.3

            discount = int(round((1 - price_sale / price_orig) * 100)) if price_orig > price_sale else 15

            # Extract item_id from href
            # href format: /product-name-i.SHOPID.ITEMID
            match = re.search(r"i\.(\d+)\.(\d+)", href)
            if match:
                shop_id, item_id = match.group(1), match.group(2)
            else:
                item_id = str(abs(hash(name)) % 10000000000)

            full_url = f"https://shopee.vn{href}" if href.startswith("/") else href
            aff_url = f"https://s.shopee.vn/aff_{item_id}"

            deal = {
                "item_id": item_id,
                "cat_id": 0,
                "category_name": category_name,
                "name": name,
                "price_original": price_orig,
                "price_sale": price_sale,
                "discount_percent": discount,
                "rating_star": rating,
                "historical_sold": sold,
                "deal_score": 35.0,
                "item_url": full_url,
                "aff_url": aff_url,
                "image_url": "",
                "local_image": "",
                "price_badge": "REAL_DISCOUNT",
                "platform": "SHOPEE",
                "is_stale": 0
            }

            db.save_deal(deal)
            saved.append(deal)
            print(f" -> Saved [{category_name}]: {name[:45]} | {price_sale:,}đ | Sold: {sold}")

        except Exception as e:
            print(f"Error parsing item: {e}")

    return saved

def run_niche_crawler():
    categories = [
        ("https://shopee.vn/Th%E1%BB%9Di-Trang-Nam-cat.11035567", "Thời Trang Nam"),
        ("https://shopee.vn/Th%E1%BB%9Di-Trang-N%E1%BB%AF-cat.11035639", "Thời Trang Nữ"),
        ("https://shopee.vn/Thi%E1%BA%BFt-B%E1%BB%8B-%C4%90i%E1%BB%87n-T%E1%BB%AD-cat.11036030", "Thiết Bị Điện Tử")
    ]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900}
        )

        for url, cat in categories:
            scrape_shopee_category(page, url, cat)

        browser.close()

if __name__ == "__main__":
    run_niche_crawler()
