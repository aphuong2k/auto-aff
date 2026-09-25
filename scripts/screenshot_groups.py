import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width': 1400, 'height': 1200})
    page.goto('http://localhost:4200/', timeout=30000, wait_until='networkidle')
    page.wait_for_timeout(2000)

    # Click on the Nhóm Facebook nav item
    nav_btn = page.locator("button.nav-item:has-text('Nhóm Facebook')").first
    if nav_btn.is_visible():
        nav_btn.click()
        page.wait_for_timeout(2500)

    screenshot_path = r"C:\Users\aphuong2k\.gemini\antigravity-ide\brain\f811c224-e211-452c-b5eb-d9d31beb34bb\groups_ui_verified.png"
    page.screenshot(path=screenshot_path, full_page=True)
    print("Screenshot saved to:", screenshot_path)
    browser.close()
