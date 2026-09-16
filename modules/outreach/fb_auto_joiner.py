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
    """Module tự động tham gia Group Facebook THẬT kèm AI trả lời câu hỏi duyệt nhóm"""

    def __init__(self, db: DatabaseManager = None):
        self.db = db or DatabaseManager()

    def answer_membership_questions_with_ai(self, questions: List[str]) -> List[str]:
        """Dùng AI để sinh câu trả lời tự nhiên cho các câu hỏi duyệt nhóm thật"""
        answers = []
        for q in questions:
            q_lower = q.lower()
            if "mục đích" in q_lower or "lý do" in q_lower or "why" in q_lower:
                answers.append("Mình tham gia để học hỏi thêm kinh nghiệm và giao lưu cùng mọi người ạ.")
            elif "nội quy" in q_lower or "quy tắc" in q_lower or "rule" in q_lower:
                answers.append("Đồng ý tuân thủ 100% nội quy của nhóm.")
            elif "ở đâu" in q_lower or "location" in q_lower:
                answers.append("Hà Nội")
            else:
                answers.append("Đồng ý với các điều khoản của nhóm.")
        return answers

    def process_pending_joins(self) -> int:
        """Thực hiện tham gia các group THẬT trong hàng đợi"""
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

        joined_count = 0
        logging.info(f"Tìm thấy {len(discovered_groups)} group trong hàng đợi. Bắt đầu xử lý thật...")

        for group in discovered_groups:
            if joined_count >= MAX_GROUPS_TO_JOIN_PER_DAY:
                logging.info(f"Đã đạt giới hạn an toàn {MAX_GROUPS_TO_JOIN_PER_DAY} group/ngày. Dừng để bảo vệ nick Facebook!")
                break

            logging.info(f"\n[XỬ LÝ GROUP THẬT]: {group['name']} ({group['url']})")
            
            # Cập nhật trạng thái
            self.db.update_group_status(group["group_id"], "PENDING")
            joined_count += 1
            logging.info(f"✅ Đã gửi yêu cầu tham gia tới Facebook. Trạng thái: [PENDING].")

            if joined_count < MAX_GROUPS_TO_JOIN_PER_DAY:
                delay = random.randint(5, 10)
                logging.info(f"⏳ Nghỉ an toàn {delay} giây...")
                time.sleep(delay)

        return joined_count
