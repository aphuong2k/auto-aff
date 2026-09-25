import os
import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

# Ensure settings loads .env
from config.settings import DB_PATH
from database.db_manager import DatabaseManager
from playwright.sync_api import sync_playwright

def sync_user_facebook_groups():
    fb_cookie = os.getenv("FB_COOKIE", "")
    if not fb_cookie:
        print("No FB_COOKIE found!")
        return []

    cookies = []
    for item in fb_cookie.split(";"):
        if "=" in item:
            k, v = item.strip().split("=", 1)
            cookies.append({"name": k, "value": v, "domain": ".facebook.com", "path": "/"})

    db = DatabaseManager()
    joined_groups = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        context.add_cookies(cookies)
        page = context.new_page()

        print("Navigating to https://www.facebook.com/groups/joins/...")
        page.goto("https://www.facebook.com/groups/joins/", timeout=40000, wait_until="domcontentloaded")
        page.wait_for_timeout(4000)

        # Scroll down slightly to trigger lazy-loaded groups
        page.mouse.wheel(0, 1000)
        page.wait_for_timeout(2000)

        links = page.locator("a[href*='/groups/']").all()
        print(f"Total /groups/ links found: {len(links)}")

        seen_ids = set()
        for link in links:
            try:
                href = link.get_attribute("href") or ""
                text = link.inner_text().strip()
                if not href or not text or len(text) < 2:
                    continue

                clean_url = href.split("?")[0].rstrip("/")
                parts = clean_url.split("/groups/")
                if len(parts) < 2:
                    continue
                group_id = parts[1].split("/")[0]

                # Filter internal system paths
                if group_id in ["joins", "feed", "discover", "create", "notifications", "search"]:
                    continue

                if group_id in seen_ids:
                    continue
                seen_ids.add(group_id)

                group_name = text.split("\n")[0].strip()
                if not group_name or group_name.lower() in ["tham gia", "nhóm", "xem thêm"]:
                    continue

                # Update database directly to APPROVED
                db.save_group(
                    group_id=group_id,
                    name=group_name,
                    url=f"https://www.facebook.com/groups/{group_id}/",
                    category_name="Cộng Đồng Chung",
                    members=10000
                )
                db.update_group_status(group_id, "APPROVED")

                joined_groups.append({
                    "group_id": group_id,
                    "name": group_name,
                    "url": f"https://www.facebook.com/groups/{group_id}/",
                    "status": "APPROVED"
                })
                print(f"[APPROVED] Found joined group: [{group_name}] (ID: {group_id})")

            except Exception as e:
                print(f"Error parsing link: {e}")

        browser.close()

    print(f"\nDone! Synced {len(joined_groups)} joined groups to database.")
    return joined_groups

if __name__ == "__main__":
    sync_user_facebook_groups()
