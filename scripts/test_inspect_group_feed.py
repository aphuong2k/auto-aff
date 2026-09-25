import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

import config.settings
from playwright.sync_api import sync_playwright

def inspect_group_post_box():
    fb_cookie = os.getenv("FB_COOKIE", "")
    if not fb_cookie:
        print("No FB_COOKIE found!")
        return

    cookies = []
    for item in fb_cookie.split(";"):
        if "=" in item:
            k, v = item.strip().split("=", 1)
            cookies.append({"name": k, "value": v, "domain": ".facebook.com", "path": "/"})

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900}
        )
        context.add_cookies(cookies)
        page = context.new_page()

        group_url = "https://www.facebook.com/groups/2859322887636192/"
        print(f"Navigating to {group_url}...")
        page.goto(group_url, timeout=35000, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        # Check page title
        print(f"Page Title: {page.title()}")

        # Look for create post prompt
        selectors = [
            "div[role='button']:has-text('Bạn viết gì đi')",
            "div[role='button']:has-text('Bạn đang viết gì thế')",
            "div[role='button']:has-text('Write something')",
            "div[role='button']:has-text('Tạo bài viết')",
            "div[role='button']:has-text('What\'s on your mind')",
            "div[aria-label*='Tạo bài viết']",
            "div[aria-label*='Write something']",
            "span:has-text('Bạn viết gì đi')",
            "span:has-text('Bạn đang viết gì thế')"
        ]

        found_sel = None
        for sel in selectors:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=1000):
                print(f"Found post box trigger: {sel}")
                found_sel = sel
                break

        if not found_sel:
            # Let's inspect buttons or spans on page
            print("Inspecting all buttons and spans on page...")
            btns = page.locator("div[role='button']").all()
            for b in btns[:20]:
                try:
                    txt = b.inner_text().strip()
                    if txt and len(txt) < 50:
                        print(f" - Button: '{txt}'")
                except:
                    pass

        screenshot_path = str(BASE_DIR / "logs" / "group_inspect.png")
        page.screenshot(path=screenshot_path)
        print(f"Screenshot saved to {screenshot_path}")

        browser.close()

if __name__ == "__main__":
    inspect_group_post_box()
