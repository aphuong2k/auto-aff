import os
import sys
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from database.db_manager import DatabaseManager

router_logger = logging.getLogger("AccountRouter")
router_logger.setLevel(logging.INFO)
if not router_logger.handlers:
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(logging.Formatter("%(asctime)s [AccountRouter] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    router_logger.addHandler(sh)


class AccountRouter:
    """
    Account Rotation Engine & Workload Balancer:
    Dịch vụ điều phối và cân bằng tải độc lập giữa các tài khoản Facebook được phép sử dụng.
    
    Vị trí kiến trúc:
    POST QUEUE -> ACCOUNT ROUTER -> [Account A / B / C] -> POST -> SEEDING -> HISTORY
    
    Quy tắc nghiệp vụ:
    1. Trạng thái minh bạch: Lọc các tài khoản is_active=1, status='ACTIVE'.
    2. Tự động cách ly: Tài khoản gặp Checkpoint hoặc lỗi cookie sẽ bị loại ngay khỏi queue.
    3. Giãn cách an toàn (Cooldown): Sau mỗi lượt đăng, tài khoản tự động vào trạng thái Cooldown (mặc định 15 phút) để chống spam dồn dập.
    4. Cân bằng tải thực tế (Workload Balancer):
       - Ưu tiên tài khoản chưa đăng hôm nay (posts_today == 0).
       - Ưu tiên tài khoản có số bài ít nhất trong chu kỳ hiện tại (posts_current_cycle ASC).
       - Ưu tiên tài khoản có thời điểm sử dụng lâu nhất (last_used_at ASC NULLS FIRST).
    5. Lưu vết kiên cố: Ghi nhận đầy đủ vào account_usage_history, không mất trạng thái khi restart app.
    """

    DEFAULT_COOLDOWN_SECONDS = 900  # 15 phút nghỉ an toàn giữa các lượt đăng của 1 nick

    def __init__(self, db: Optional[DatabaseManager] = None):
        self.db = db or DatabaseManager()

    def select_best_account_for_group(
        self,
        group_id: str,
        task_type: str = "POST"
    ) -> Tuple[Optional[Dict], str, str]:
        """
        Lựa chọn tài khoản tối ưu nhất để thực hiện đăng bài vào nhóm chỉ định.
        Trả về: (selected_account, status_code, message)
        """
        now = datetime.now()
        all_accounts = self.db.get_fb_accounts(only_active=False)

        if not all_accounts:
            router_logger.warning("⚠️ [ACCOUNT ROUTER]: Chưa cấu hình tài khoản Facebook nào trong CSDL!")
            return None, "NO_ACCOUNTS", "Chưa có tài khoản Facebook nào trong hệ thống. Vui lòng thêm tài khoản tại Cài Đặt!"

        # 1. Lọc tài khoản Active (không bị disabled hoặc checkpoint)
        active_accounts = [a for a in all_accounts if a.get("is_active") == 1 and a.get("status") == "ACTIVE"]
        if not active_accounts:
            router_logger.warning("⚠️ [ACCOUNT ROUTER]: Tất cả tài khoản đều bị Vô hiệu hóa hoặc dính Checkpoint!")
            return None, "ALL_CHECKPOINTED", "Tất cả tài khoản Facebook đều đang ở trạng thái CHECKPOINT hoặc BỊ TẮT. Cần cập nhật cookie mới!"

        # 2. Lọc tài khoản chưa chạm giới hạn ngày
        limit_key = "daily_post_limit" if task_type == "POST" else "daily_join_limit"
        today_key = "posts_today" if task_type == "POST" else "joins_today"

        under_limit_accounts = [a for a in active_accounts if a.get(today_key, 0) < a.get(limit_key, 3)]
        if not under_limit_accounts:
            router_logger.warning("⚠️ [ACCOUNT ROUTER]: Tất cả tài khoản đã chạm giới hạn đăng bài trong ngày!")
            return None, "DAILY_LIMIT_REACHED", "Tất cả tài khoản Facebook đã chạm hạn mức đăng bài tối đa trong ngày hôm nay!"

        # 3. Kiểm tra Cooldown
        ready_accounts = []
        min_cooldown_remaining = 999999

        for acc in under_limit_accounts:
            cooldown_str = acc.get("cooldown_until")
            if cooldown_str:
                try:
                    cooldown_dt = datetime.strptime(cooldown_str, "%Y-%m-%d %H:%M:%S")
                    if cooldown_dt > now:
                        remaining = int((cooldown_dt - now).total_seconds())
                        if remaining < min_cooldown_remaining:
                            min_cooldown_remaining = remaining
                        continue  # Bỏ qua vì đang trong thời gian nghỉ cooldown
                except Exception:
                    pass
            ready_accounts.append(acc)

        if not ready_accounts:
            rem_min = max(1, round(min_cooldown_remaining / 60))
            router_logger.info(f"⏳ [ACCOUNT ROUTER]: Tất cả tài khoản đang nghỉ Cooldown. Lượt sớm nhất sẽ sẵn sàng sau ~{rem_min} phút.")
            return None, "ALL_IN_COOLDOWN", f"Tất cả tài khoản đang trong thời gian nghỉ an toàn (Cooldown). Tài khoản sớm nhất sẵn sàng sau {rem_min} phút."

        # 4. Thuật toán Cân bằng tải (Workload Balancing):
        # - Ưu tiên 1: posts_today ít nhất
        # - Ưu tiên 2: posts_current_cycle ít nhất
        # - Ưu tiên 3: last_used_at xa nhất (hoặc chưa từng dùng)
        def sort_key(acc):
            last_used = acc.get("last_used_at")
            last_used_ts = 0 if not last_used else datetime.strptime(last_used, "%Y-%m-%d %H:%M:%S").timestamp()
            posts_today = acc.get("posts_today", 0)
            posts_cycle = acc.get("posts_current_cycle", 0)
            return (posts_today, posts_cycle, last_used_ts)

        ready_accounts.sort(key=sort_key)
        chosen_acc = ready_accounts[0]

        router_logger.info(
            f"🎯 [ACCOUNT ROUTER CHỌN TÀI KHOẢN]: [{chosen_acc.get('name')}] (ID: {chosen_acc.get('id')}) | "
            f"Workload hôm nay: {chosen_acc.get('posts_today', 0)}/{chosen_acc.get('daily_post_limit', 3)} bài | "
            f"Chu kỳ hiện tại: {chosen_acc.get('posts_current_cycle', 0)} bài"
        )

        return chosen_acc, "AVAILABLE", f"Đã chọn tài khoản [{chosen_acc.get('name')}] (Workload: {chosen_acc.get('posts_today', 0)} bài hôm nay)"

    def record_post_result(
        self,
        account_id: int,
        group_id: str,
        deal_id: Optional[str] = None,
        post_url: Optional[str] = None,
        status: str = "SUCCESS",
        error_message: Optional[str] = None,
        duration_seconds: float = 0.0,
        cooldown_seconds: Optional[int] = None
    ):
        """
        Ghi nhận kết quả thực thi và áp đặt cooldown cho tài khoản:
        - Thành công / Chờ duyệt: Đặt cooldown 15 phút (hoặc cấu hình)
        - Checkpoint / Khóa: Tự động đánh dấu CHECKPOINT và tắt is_active = 0
        """
        cd_sec = cooldown_seconds if cooldown_seconds is not None else self.DEFAULT_COOLDOWN_SECONDS
        self.db.record_account_usage_event(
            account_id=account_id,
            group_id=group_id,
            deal_id=deal_id,
            post_url=post_url,
            action_type="POST",
            status=status,
            error_message=error_message,
            duration_seconds=duration_seconds,
            cooldown_seconds=cd_sec
        )

        if status in ["SUCCESS", "PENDING_APPROVAL"]:
            router_logger.info(f"⏱️ [ĐẶT COOLDOWN]: Tài khoản #{account_id} sẽ nghỉ an toàn {round(cd_sec / 60)} phút trước lượt tiếp theo.")
        elif "checkpoint" in (error_message or "").lower():
            router_logger.error(f"🚫 [CÁCH LY TÀI KHOẢN]: Phát hiện Checkpoint tại tài khoản #{account_id}. Đã tự động loại khỏi hàng đợi!")

    def reset_cycle_workload(self):
        """Reset workload chu kỳ khi closed-loop engine hoàn thành toàn bộ danh mục nhóm"""
        router_logger.info("🔄 [RESET WORKLOAD CHU KỲ]: Đã reset posts_current_cycle = 0 cho tất cả tài khoản.")
        self.db.reset_account_cycle_counters()

    def release_cooldown(self, account_id: int):
        """Xóa bỏ cooldown thủ công cho 1 tài khoản"""
        self.db.release_account_cooldown(account_id)
        router_logger.info(f"🔓 [XÓA COOLDOWN]: Đã mở lại tài khoản #{account_id} để sẵn sàng nhận job.")

    def get_workload_status(self) -> List[Dict]:
        """Lấy danh sách tổng hợp tình trạng cân bằng tải và cooldown của từng tài khoản"""
        return self.db.get_available_accounts_for_router(task_type="POST")
