import sys
import os
import sqlite3
from pathlib import Path
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')

test_image = Path(r"C:\Users\sangt\OneDrive\Documents\auto-aff\data\processed_images\10064787319_banner.jpg")
assert test_image.exists(), f"Image not found: {test_image}"

conn = sqlite3.connect('data/affiliate_system.db')
conn.row_factory = sqlite3.Row
acc = conn.execute('SELECT * FROM fb_accounts WHERE id = 3').fetchone()
fb_cookie = acc['cookie']

cookies = []
for item in fb_cookie.split(';'):
    if '=' in item:
        k, v = item.strip().split('=', 1)
        cookies.append({'name': k, 'value': v, 'domain': '.facebook.com', 'path': '/'})

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        viewport={'width': 1280, 'height': 900}
    )
    context.add_cookies(cookies)
    page = context.new_page()

    group_url = 'https://www.facebook.com/groups/2713539318943150/'
    print(f'Navigating to {group_url}...')
    page.goto(group_url, timeout=35000, wait_until='domcontentloaded')
    page.wait_for_timeout(3500)

    trigger = page.locator("div[role='button']:has-text('Bạn viết gì đi')").first
    trigger.click()
    page.wait_for_timeout(2500)

    # Find visible dialog
    dialogs = page.locator("div[role='dialog']").all()
    target_dialog = None
    for d in dialogs:
        try:
            if d.is_visible():
                text = (d.inner_text() or '').lower()
                if any(k in text for k in ['tạo bài viết', 'create post', 'bài viết', 'thêm vào bài']):
                    target_dialog = d
                    break
                elif not target_dialog:
                    target_dialog = d
        except Exception:
            pass

    if not target_dialog:
        print("ERROR: Target dialog not found!")
        browser.close()
        sys.exit(1)

    print("Found target dialog!")
    tb = target_dialog.locator("div[role='textbox'], div[contenteditable='true']").first
    if tb.is_visible():
        tb.click()
        page.keyboard.insert_text('Test thử nghiệm tải kèm hình ảnh sản phẩm...')
        print("Filled text.")

    # Check file inputs before click
    inputs_before = target_dialog.locator("input[type='file']").all()
    print(f"File inputs in dialog before clicking photo btn: {len(inputs_before)}")
    all_inputs_before = page.locator("input[type='file']").all()
    print(f"File inputs across whole page before clicking photo btn: {len(all_inputs_before)}")

    # Click photo button
    photo_selectors = [
        "div[aria-label*='Ảnh/video']",
        "div[aria-label*='Photo/video']",
        "div[role='button']:has-text('Ảnh/video')",
        "div[role='button']:has-text('Photo/video')",
        "div[aria-label*='Thêm vào bài viết của bạn'] div[role='button']",
        "span:has-text('Ảnh/video')"
    ]
    clicked_btn = False
    for p_sel in photo_selectors:
        btn = target_dialog.locator(p_sel).first
        if btn.is_visible(timeout=1000):
            print(f"Clicking photo button: {p_sel}")
            btn.click()
            page.wait_for_timeout(2000)
            clicked_btn = True
            break

    if not clicked_btn:
        print("Warning: Could not find visible photo button inside dialog, checking whole page...")
        for p_sel in photo_selectors:
            btn = page.locator(p_sel).first
            if btn.is_visible(timeout=1000):
                print(f"Clicking photo button on page: {p_sel}")
                btn.click()
                page.wait_for_timeout(2000)
                clicked_btn = True
                break

    # Check file inputs after click
    inputs_after = target_dialog.locator("input[type='file']").all()
    print(f"File inputs in dialog after clicking photo btn: {len(inputs_after)}")
    all_inputs_after = page.locator("input[type='file']").all()
    print(f"File inputs across whole page after clicking photo btn: {len(all_inputs_after)}")

    # Upload file
    uploaded = False
    file_input = target_dialog.locator("input[type='file']").first
    if file_input.count() > 0:
        print("Setting input files on dialog file_input...")
        file_input.set_input_files(str(test_image))
        uploaded = True
    elif len(all_inputs_after) > 0:
        print("Setting input files on page file_input...")
        page.locator("input[type='file']").last.set_input_files(str(test_image))
        uploaded = True
    else:
        print("ERROR: No input[type='file'] found anywhere!")

    if uploaded:
        print("Waiting 4s for Facebook to process image...")
        page.wait_for_timeout(4000)
        # Check if thumbnail or image preview appears
        img_preview = target_dialog.locator("img[src*='blob:'], img[src*='scontent'], div[aria-label*='Ảnh'], div[aria-label*='Photo']").all()
        print(f"Found {len(img_preview)} image preview elements in dialog!")

    Path('logs').mkdir(exist_ok=True)
    screenshot_path = 'logs/debug_photo_upload_result.png'
    page.screenshot(path=screenshot_path)
    print(f"Screenshot saved to {screenshot_path}")

    browser.close()
