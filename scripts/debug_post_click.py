import sys
import os
import sqlite3
from pathlib import Path
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')
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
    page.goto(group_url, timeout=35000, wait_until='domcontentloaded')
    page.wait_for_timeout(3500)

    trigger = page.locator("div[role='button']:has-text('Bạn viết gì đi')").first
    trigger.click()
    page.wait_for_timeout(2500)

    # NEW LOGIC: find visible dialog
    dialogs = page.locator("div[role='dialog']").all()
    target_dialog = None
    for d in dialogs:
        try:
            if d.is_visible():
                text = (d.inner_text() or '').lower()
                if any(k in text for k in ['tạo bài viết', 'create post', 'bài viết', 'thêm vào bài']):
                    target_dialog = d
                    print('Found post dialog with text match!')
                    break
                elif not target_dialog:
                    target_dialog = d
        except Exception:
            pass

    if target_dialog:
        print('Target dialog found!')
        tb = target_dialog.locator("div[role='textbox'], div[contenteditable='true']").first
        print('Textbox visible:', tb.is_visible())
        if tb.is_visible():
            tb.click()
            page.keyboard.insert_text('Test soạn bài viết tự động...')
            print('Inserted text successfully!')
            
            # Check submit button
            submit_selectors = [
                "div[aria-label='Đăng']",
                "div[aria-label='Post']",
                "div[role='button']:has-text('Đăng')",
                "div[role='button']:has-text('Post')"
            ]
            for s in submit_selectors:
                btn = target_dialog.locator(s).first
                if btn.is_visible(timeout=500):
                    print(f'Submit button found: {s}, aria-disabled={btn.get_attribute("aria-disabled")}')
    else:
        print('Target dialog NOT found!')

    page.screenshot(path='logs/debug_post_dialog_fixed.png')
    browser.close()
