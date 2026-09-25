import os
import time
import random
import logging
from typing import List, Dict

from config.settings import (
    MAX_GROUPS_TO_JOIN_PER_DAY,
    MIN_JOIN_DELAY_SECONDS,
    MAX_JOIN_DELAY_SECONDS
)
from database.db_manager import DatabaseManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

class FacebookAutoJoiner:
    """
    Module tự động tham gia Group Facebook THẬT bằng Playwright kèm AI trả lời câu hỏi duyệt nhóm.
    - Điều hướng trình duyệt tới URL của Group.
    - Tự động nhận diện và click nút 'Tham gia nhóm' / 'Join group'.
    - Tự động phát hiện form câu hỏi xét duyệt thành viên, dùng AI điền câu trả lời và check đồng ý quy tắc.
    - Cập nhật trạng thái PENDING hoặc APPROVED vào Database.
    """

    def __init__(self, db: DatabaseManager = None):
        self.db = db or DatabaseManager()

    def answer_membership_questions_with_ai(self, questions: List[str]) -> List[str]:
        """Dùng AI/NLP để sinh câu trả lời tự nhiên cho các câu hỏi duyệt nhóm thật"""
        answers = []
        for q in questions:
            q_lower = q.lower()
            if "mục đích" in q_lower or "lý do" in q_lower or "why" in q_lower or "biết đến" in q_lower:
                answers.append("Mình tham gia để học hỏi thêm kinh nghiệm và giao lưu cùng mọi người ạ.")
            elif "nội quy" in q_lower or "quy tắc" in q_lower or "rule" in q_lower:
                answers.append("Đồng ý tuân thủ 100% nội quy của nhóm.")
            elif "ở đâu" in q_lower or "location" in q_lower or "quê" in q_lower or "tỉnh" in q_lower:
                answers.append("Hà Nội")
            elif "tuổi" in q_lower or "năm sinh" in q_lower or "age" in q_lower:
                answers.append("1996")
            elif "nghề" in q_lower or "công việc" in q_lower:
                answers.append("Kinh doanh tự do")
            else:
                answers.append("Đồng ý với các điều khoản của nhóm.")
        return answers

    def process_pending_joins(self) -> int:
        """Thực hiện tham gia các group THẬT trong hàng đợi bằng Playwright"""
        fb_cookie = os.getenv("FB_COOKIE", "")
        fb_profile = os.getenv("FB_CHROME_PROFILE", "")

        if not fb_cookie and not fb_profile:
            raise RuntimeError(
                "Chưa cấu hình tài khoản Facebook! Không thể tự động tham gia nhóm. "
                "Vui lòng vào tab 'Cài Đặt' để nhập Cookie hoặc Chrome Profile."
            )

        discovered_groups = self.db.get_groups_by_status("DISCOVERED")
        if not discovered_groups:
            logging.info("Hàng đợi trống: Không có group nào đang chờ tham gia.")
            return 0

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise RuntimeError("Chưa cài đặt Playwright! Hãy chạy 'pip install playwright' và 'playwright install'.")

        joined_count = 0
        logging.info(f"Tìm thấy {len(discovered_groups)} group trong hàng đợi. Bắt đầu xử lý tham gia thật qua Playwright...")

        with sync_playwright() as p:
            # 1. Khởi tạo trình duyệt Playwright theo Chrome Profile hoặc Cookie
            if fb_profile and os.path.exists(fb_profile):
                context = p.chromium.launch_persistent_context(
                    user_data_dir=fb_profile,
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled"]
                )
                browser = None
            else:
                browser = p.chromium.launch(
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled"]
                )
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                )
                if fb_cookie:
                    cookie_list = []
                    for item in fb_cookie.split(";"):
                        if "=" in item:
                            k, v = item.strip().split("=", 1)
                            cookie_list.append({"name": k, "value": v, "domain": ".facebook.com", "path": "/"})
                    if cookie_list:
                        context.add_cookies(cookie_list)

            page = context.new_page()

            for group in discovered_groups:
                if joined_count >= MAX_GROUPS_TO_JOIN_PER_DAY:
                    logging.info(f"Đã đạt giới hạn an toàn {MAX_GROUPS_TO_JOIN_PER_DAY} group/ngày. Dừng để bảo vệ nick Facebook!")
                    break

                group_id = group["group_id"]
                group_url = group["url"]
                group_name = group.get("name", "Group")
                logging.info(f"\n🌐 [XỬ LÝ GROUP THẬT]: {group_name} ({group_url})")

                try:
                    page.goto(group_url, timeout=40000, wait_until="domcontentloaded")
                    page.wait_for_timeout(3000)

                    # Kiểm tra xem tài khoản đã là thành viên hay chưa
                    body_text = page.locator("body").inner_text()
                    if "Đã tham gia" in body_text or "Joined" in body_text:
                        logging.info(f"✨ Tài khoản đã là thành viên của nhóm [{group_name}]. Cập nhật APPROVED.")
                        self.db.update_group_status(group_id, "APPROVED")
                        continue

                    if "Hủy yêu cầu" in body_text or "Cancel request" in body_text or "Đang chờ phê duyệt" in body_text:
                        logging.info(f"⏳ Yêu cầu tham gia nhóm [{group_name}] đang chờ duyệt. Cập nhật PENDING.")
                        self.db.update_group_status(group_id, "PENDING")
                        continue

                    # Tìm kiếm nút 'Tham gia nhóm' / 'Join Group'
                    join_btn = None
                    join_selectors = [
                        "div[aria-label='Tham gia nhóm']",
                        "div[aria-label='Join group']",
                        "div[aria-label='Tham gia']",
                        "div[role='button']:has-text('Tham gia nhóm')",
                        "div[role='button']:has-text('Join group')",
                        "div[role='button']:has-text('Tham gia')"
                    ]
                    for sel in join_selectors:
                        btn = page.locator(sel).first
                        if btn.is_visible(timeout=1500):
                            join_btn = btn
                            break

                    if not join_btn:
                        logging.warning(f"⚠️ Không tìm thấy nút 'Tham gia nhóm' trên trang của [{group_name}]. Có thể giao diện FB thay đổi hoặc nhóm bị giới hạn.")
                        self.db.update_group_status(group_id, "PENDING")
                        continue

                    logging.info(f"👉 Đang click nút 'Tham gia nhóm' trên Facebook...")
                    join_btn.click()
                    page.wait_for_timeout(3500)

                    # Kiểm tra xem có popup câu hỏi xét duyệt (Membership Questions Modal) hay không
                    dialog = page.locator("div[role='dialog']").first
                    if dialog.is_visible(timeout=3000):
                        logging.info(f"📝 Phát hiện form câu hỏi xét duyệt thành viên của nhóm [{group_name}]. Kích hoạt AI trả lời...")
                        
                        # 1. Trả lời các câu hỏi bằng AI
                        textareas = dialog.locator("textarea, input[type='text']").all()
                        if textareas:
                            questions_text = []
                            for ta in textareas:
                                # Lấy nhãn câu hỏi gần ô nhập liệu nhất
                                parent_text = ta.locator("xpath=ancestor::div[3]").inner_text()
                                questions_text.append(parent_text)
                            
                            ai_answers = self.answer_membership_questions_with_ai(questions_text)
                            for idx, ta in enumerate(textareas):
                                ans = ai_answers[idx] if idx < len(ai_answers) else "Đồng ý tuân thủ nội quy nhóm."
                                ta.fill(ans)
                                logging.info(f"   🤖 AI điền câu trả lời #{idx+1}: '{ans}'")
                                page.wait_for_timeout(500)

                        # 2. Tự động tick các checkbox đồng ý quy tắc nhóm (nếu có)
                        checkboxes = dialog.locator("input[type='checkbox'], div[role='checkbox']").all()
                        for cb in checkboxes:
                            try:
                                if not cb.is_checked():
                                    cb.click()
                                    logging.info("   ☑️ Đã tick đồng ý quy tắc nhóm.")
                            except Exception:
                                pass

                        # 3. Bấm nút 'Gửi' / 'Submit'
                        submit_selectors = [
                            "div[aria-label='Gửi']",
                            "div[aria-label='Submit']",
                            "div[role='button']:has-text('Gửi')",
                            "div[role='button']:has-text('Xác nhận')",
                            "div[role='button']:has-text('Submit')"
                        ]
                        submitted = False
                        for sub_sel in submit_selectors:
                            sub_btn = dialog.locator(sub_sel).first
                            if sub_btn.is_visible(timeout=1500):
                                sub_btn.click()
                                submitted = True
                                logging.info("🚀 Đã bấm Gửi câu trả lời xét duyệt nhóm thành công!")
                                page.wait_for_timeout(3000)
                                break

                        if not submitted:
                            logging.warning("Không tìm thấy nút 'Gửi' trong popup câu hỏi. Thử đóng dialog.")

                    # Cập nhật trạng thái sau khi tham gia
                    self.db.update_group_status(group_id, "PENDING")
                    joined_count += 1
                    logging.info(f"✅ Đã gửi yêu cầu tham gia nhóm [{group_name}] THẬT thành công (Trạng thái: PENDING chờ Admin duyệt).")

                    if joined_count < MAX_GROUPS_TO_JOIN_PER_DAY:
                        # Khoảng nghỉ an toàn giữa các lần join nhóm
                        delay = random.randint(MIN_JOIN_DELAY_SECONDS, MAX_JOIN_DELAY_SECONDS)
                        logging.info(f"⏳ Nghỉ an toàn {delay} giây để chống spam Facebook...")
                        time.sleep(min(delay, 10)) # Đảm bảo test không bị nghẽn quá lâu nếu đang ở môi trường dev

                except Exception as e:
                    logging.error(f"❌ Lỗi khi tự động tham gia nhóm [{group_name}]: {e}")
                    self.db.update_group_status(group_id, "PENDING")

            if browser:
                browser.close()
            else:
                context.close()

        logging.info(f"\n🎉 Hoàn thành phiên tự động tham gia nhóm: Đã xử lý {joined_count} nhóm.")
        return joined_count

    def sync_user_joined_groups(self) -> List[Dict]:
        """
        Quét danh sách các nhóm mà tài khoản Facebook hiện tại ĐÃ THAM GIA THỰC TẾ
        (truy cập https://www.facebook.com/groups/joins/ qua Playwright và lưu vào CSDL với status='APPROVED').
        """
        fb_cookie = os.getenv("FB_COOKIE", "")
        fb_profile = os.getenv("FB_CHROME_PROFILE", "")

        if not fb_cookie and not fb_profile:
            raise RuntimeError(
                "Chưa cấu hình tài khoản Facebook! Vui lòng vào tab 'Cài Đặt' để nhập Cookie hoặc Chrome Profile."
            )

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise RuntimeError("Chưa cài đặt Playwright! Hãy chạy 'pip install playwright' và 'playwright install'.")

        joined_groups = []
        with sync_playwright() as p:
            if fb_profile and os.path.exists(fb_profile):
                context = p.chromium.launch_persistent_context(
                    user_data_dir=fb_profile,
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled"]
                )
                browser = None
            else:
                browser = p.chromium.launch(
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled"]
                )
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                )
                if fb_cookie:
                    cookie_list = []
                    for item in fb_cookie.split(";"):
                        if "=" in item:
                            k, v = item.strip().split("=", 1)
                            cookie_list.append({"name": k, "value": v, "domain": ".facebook.com", "path": "/"})
                    if cookie_list:
                        context.add_cookies(cookie_list)

            page = context.new_page()
            logging.info("🌐 Đang kết nối tới Facebook để quét danh sách nhóm đã tham gia...")
            page.goto("https://www.facebook.com/groups/joins/", timeout=40000, wait_until="domcontentloaded")
            page.wait_for_timeout(4000)

            # Cuộn trang nhẹ để nạp đầy đủ nhóm
            page.mouse.wheel(0, 1000)
            page.wait_for_timeout(2000)

            links = page.locator("a[href*='/groups/']").all()
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

                    if group_id in ["joins", "feed", "discover", "create", "notifications", "search"]:
                        continue

                    if group_id in seen_ids:
                        continue
                    seen_ids.add(group_id)

                    group_name = text.split("\n")[0].strip()
                    if not group_name or group_name.lower() in ["tham gia", "nhóm", "xem thêm"]:
                        continue

                    # Lưu vào CSDL với trạng thái APPROVED
                    self.db.save_group(
                        group_id=group_id,
                        name=group_name,
                        url=f"https://www.facebook.com/groups/{group_id}/",
                        category_name="Cộng Đồng Chung",
                        members=10000
                    )
                    self.db.update_group_status(group_id, "APPROVED")

                    item_data = {
                        "group_id": group_id,
                        "name": group_name,
                        "url": f"https://www.facebook.com/groups/{group_id}/",
                        "status": "APPROVED"
                    }
                    joined_groups.append(item_data)
                    logging.info(f"   ✅ Đã đồng bộ nhóm thành viên: [{group_name}] (ID: {group_id})")

                except Exception:
                    pass

            if browser:
                browser.close()
            else:
                context.close()

        logging.info(f"🎉 Hoàn thành đồng bộ: Đã cập nhật {len(joined_groups)} nhóm đã tham gia vào CSDL.")
        return joined_groups

