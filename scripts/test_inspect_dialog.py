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

def inspect_dialog():
    fb_cookie = os.getenv("FB_COOKIE", "")
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
        page.goto(group_url, timeout=35000, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        trigger = page.locator("div[role='button']:has-text('Bạn viết gì đi'), div[role='button']:has-text('Bạn đang viết gì thế')").first
        if trigger.is_visible():
            print("Clicking trigger to open create post modal...")
            trigger.click()
            page.wait_for_timeout(2500)

            dialog = page.locator("div[role='dialog']").first
            if dialog.is_visible():
                print("Dialog is visible!")
                
                # Check for editable textbox inside dialog
                textboxes = dialog.locator("div[role='textbox'], div[contenteditable='true']").all()
                print(f"Found {len(textboxes)} textboxes in dialog.")
                for idx, tb in enumerate(textboxes):
                    aria = tb.get_attribute("aria-label") or ""
                    print(f" - Textbox #{idx}: aria-label='{aria}'")

                # Check for post button inside dialog
                submit_selectors = [
                    "div[aria-label='Đăng']",
                    "div[aria-label='Post']",
                    "div[role='button']:has-text('Đăng')",
                    "div[role='button']:has-text('Post')"
                ]
                for s in submit_selectors:
                    sub = dialog.locator(s).first
                    if sub.is_visible(timeout=500):
                        print(f"Found submit button: {s} | aria-disabled={sub.get_attribute('aria-disabled')}")

            screenshot_path = str(BASE_DIR / "logs" / "group_dialog.png")
            page.screenshot(path=screenshot_path)
            print(f"Screenshot of modal saved to {screenshot_path}")

        browser.close()

if __name__ == "__main__":
    inspect_dialog()
