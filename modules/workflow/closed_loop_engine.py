import os
import sys
import time
import uuid
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from database.db_manager import DatabaseManager
from modules.workflow.deal_collector import DealCollector
from modules.workflow.category_router import CategoryRouter
from modules.workflow.account_router import AccountRouter
from modules.outreach.fb_group_poster import FacebookGroupPoster
from modules.outreach.fb_group_seeder import FacebookGroupSeeder

engine_logger = logging.getLogger("ClosedLoopEngine")
engine_logger.setLevel(logging.INFO)
if not engine_logger.handlers:
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(logging.Formatter("%(asctime)s [ClosedLoop] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    engine_logger.addHandler(sh)


class ClosedLoopEngine:
    """
    Trục 2: Engine điều phối Vòng Đời Tự Động Khép Kín (Closed-Loop Workflow Engine).
    Quản lý danh mục nhóm, con trỏ chu kỳ liên tục, cấm trùng lặp 1 scan/ngày,
    điều phối cân bằng tải qua Account Router độc lập và thực thi State Machine chuẩn hóa:
    
    READY -> ROUTING -> ACCOUNT_ROUTER -> POSTING -> SEEDING -> COMPLETED (hoặc SKIPPED / FAILED)
    """

    def __init__(self, db: Optional[DatabaseManager] = None):
        self.db = db or DatabaseManager()
        self.collector = DealCollector(self.db)
        self.router = CategoryRouter(self.db)
        self.account_router = AccountRouter(self.db)
        self.poster = FacebookGroupPoster(self.db)
        self.seeder = FacebookGroupSeeder(self.db)

    def get_workflow_status(self) -> Dict:
        """
        Lấy trạng thái tổng quan thời gian thực của Vòng lặp Khép kín:
        - Chu kỳ hiện tại (Cycle #N)
        - Vị trí con trỏ (Pointer / Total)
        - Nhóm đang xử lý / nhóm tiếp theo
        - Thống kê hiệu suất ngày
        - 10 node xử lý gần nhất
        """
        groups = self.db.get_eligible_groups_for_cycle()
        total_groups = len(groups)
        cycle = self.db.get_or_create_active_cycle(total_groups=total_groups)
        pointer = cycle.get("current_group_pointer", 0)

        current_group = groups[pointer] if 0 <= pointer < total_groups else None
        next_group = groups[(pointer + 1) % total_groups] if total_groups > 0 else None

        daily_stats = self.db.get_daily_report_stats()
        recent_scans = self.db.get_group_scan_history(limit=10)
        workload_status = self.account_router.get_workload_status()
        account_history = self.db.get_account_usage_history(limit=10)

        return {
            "cycle": cycle,
            "total_groups": total_groups,
            "current_pointer": pointer,
            "current_group": current_group,
            "next_group": next_group,
            "daily_stats": daily_stats,
            "recent_scans": recent_scans,
            "workload_status": workload_status,
            "account_history": account_history
        }

    def process_next_group(self) -> Dict:
        """
        Xử lý Node Group tiếp theo theo vị trí con trỏ (Single-Step Execution).
        Được gọi bởi Background Scheduler định kỳ hoặc khi người dùng bấm 'Chạy Nhóm Tiếp Theo'.
        """
        groups = self.db.get_eligible_groups_for_cycle()
        total_groups = len(groups)

        if total_groups == 0:
            return {
                "status": "ERROR",
                "message": "Không có nhóm Facebook nào ở trạng thái kích hoạt (enabled=1) trong CSDL!"
            }

        cycle = self.db.get_or_create_active_cycle(total_groups=total_groups)
        pointer = cycle.get("current_group_pointer", 0)
        cycle_id = cycle["cycle_id"]

        # 1. Kiểm tra Rollover: Nếu con trỏ vượt quá danh sách -> Đóng chu kỳ cũ, tạo chu kỳ mới
        if pointer >= total_groups:
            engine_logger.info(f"🔄 [ROLLOVER CHU KỲ]: Chu kỳ #{cycle['cycle_number']} đã hoàn tất {total_groups}/{total_groups} nhóm!")
            self.db.complete_current_cycle(cycle_id)
            self.account_router.reset_cycle_workload()
            new_cycle = self.db.get_or_create_active_cycle(total_groups=total_groups)
            pointer = 0
            cycle_id = new_cycle["cycle_id"]
            cycle = new_cycle
            engine_logger.info(f"🚀 [CHU KỲ MỚI]: Bắt đầu Chu kỳ #{new_cycle['cycle_number']}, reset con trỏ về 0.")

        target_group = groups[pointer]
        group_id = str(target_group.get("group_id", ""))
        group_name = target_group.get("name", group_id)
        cat_name = target_group.get("category_name", "Cộng Đồng Chung")

        execution_id = f"exec_{uuid.uuid4().hex[:10]}"
        start_time = datetime.now()

        engine_logger.info("\n" + "=" * 70)
        engine_logger.info(f"⚙️ [CLOSED-LOOP STEP]: Xử lý Nhóm [{pointer + 1}/{total_groups}] - Chu kỳ #{cycle['cycle_number']}")
        engine_logger.info(f"   👥 Nhóm: [{group_name}] (ID: {group_id})")
        engine_logger.info(f"   📂 Ngành hàng: [{cat_name}]")
        engine_logger.info(f"   🆔 Phiên thực thi: {execution_id}")
        engine_logger.info("=" * 70)

        # 2. Guard Constraint: 1 scan/ngày - Nếu hôm nay đã xử lý thành công hoặc bỏ qua nhóm này -> Tịnh tiến con trỏ
        if self.db.is_group_scanned_today(group_id):
            engine_logger.info(f"⏭️ [ĐÃ XỬ LÝ HÔM NAY]: Nhóm [{group_name}] đã được ghi nhận trong ngày hôm nay. Tự động chuyển nhóm tiếp theo.")
            self.db.update_cycle_progress(cycle_id, pointer + 1, current_group_id=group_id)
            return {
                "status": "SKIPPED_ALREADY_DONE_TODAY",
                "group_id": group_id,
                "group_name": group_name,
                "pointer": pointer + 1,
                "cycle_number": cycle["cycle_number"],
                "message": f"Nhóm [{group_name}] đã được xử lý hôm nay theo quy tắc 1 scan/ngày."
            }

        # 3. State Machine: Bắt đầu xử lý Node
        # Bước A: Khớp deal qua Category Router
        deal, route_code, eval_count = self.router.route_deal_for_group(target_group)

        if not deal:
            # Không có deal đạt chuẩn hoặc tất cả đã đăng -> BỎ QUA NGHIÊM NGẶT
            duration = (datetime.now() - start_time).total_seconds()
            skip_msg = "Không có deal đạt chuẩn trong kho" if route_code == "SKIPPED_NO_QUALIFIED_DEAL" else "Tất cả deal ngành này đã từng đăng"
            
            self.db.record_group_scan(
                execution_id=execution_id,
                group_id=group_id,
                group_name=group_name,
                category_name=cat_name,
                cycle_id=cycle_id,
                status="SKIPPED",
                current_step="EVALUATING",
                deals_evaluated=eval_count,
                error_message=f"{route_code}: {skip_msg}",
                duration_seconds=duration
            )
            self.db.update_cycle_progress(cycle_id, pointer + 1, current_group_id=group_id, skipped_inc=1)
            
            engine_logger.warning(f"⏩ [BỎ QUA NHÓM {group_name}]: {skip_msg}. Tịnh tiến con trỏ sang vị trí {pointer + 1}.")
            return {
                "status": "SKIPPED",
                "reason": route_code,
                "message": skip_msg,
                "group_id": group_id,
                "group_name": group_name,
                "pointer": pointer + 1,
                "cycle_number": cycle["cycle_number"]
            }

        deal_id = str(deal.get("item_id", ""))
        deal_name = deal.get("name", "Sản phẩm")

        # Bước B: ĐĂNG BÀI (POSTING) - Lựa chọn & Cân bằng tải qua Account Router
        account, acc_code, acc_msg = self.account_router.select_best_account_for_group(group_id, task_type="POST")

        if not account:
            duration = (datetime.now() - start_time).total_seconds()
            engine_logger.warning(f"⚠️ [ACCOUNT ROUTER]: {acc_msg}")
            
            # Ghi nhận trạng thái không thể đăng bài do tài khoản (cooldown hoặc hết limit)
            self.db.record_group_scan(
                execution_id=execution_id,
                group_id=group_id,
                group_name=group_name,
                category_name=cat_name,
                cycle_id=cycle_id,
                status="POST_FAILED",
                current_step="ACCOUNT_ROUTER",
                deals_evaluated=eval_count,
                deal_posted_id=deal_id,
                deal_posted_name=deal_name,
                error_message=f"{acc_code}: {acc_msg}",
                duration_seconds=duration
            )
            # Tịnh tiến con trỏ để không bị kẹt vĩnh viễn ở một nhóm
            self.db.update_cycle_progress(cycle_id, pointer + 1, current_group_id=group_id, failed_inc=1)
            
            return {
                "status": "POST_FAILED",
                "reason": acc_code,
                "message": acc_msg,
                "group_id": group_id,
                "group_name": group_name,
                "pointer": pointer + 1,
                "cycle_number": cycle["cycle_number"]
            }

        self.db.record_group_scan(
            execution_id=execution_id,
            group_id=group_id,
            group_name=group_name,
            category_name=cat_name,
            cycle_id=cycle_id,
            status="POSTING",
            current_step="POSTING",
            deals_evaluated=eval_count,
            deal_posted_id=deal_id,
            deal_posted_name=deal_name
        )

        post_res = self.poster.post_to_single_group(group_id, deal_id=deal_id, account=account)
        post_status = post_res.get("status")
        duration = (datetime.now() - start_time).total_seconds()

        # Ghi nhận kết quả vào Account Router & đặt Cooldown an toàn
        self.account_router.record_post_result(
            account_id=account["id"],
            group_id=group_id,
            deal_id=deal_id,
            post_url=post_res.get("post_url", ""),
            status=post_status,
            error_message=post_res.get("message", ""),
            duration_seconds=duration
        )

        if post_status not in ["SUCCESS", "PENDING_APPROVAL"]:
            err_msg = post_res.get("message", "Lỗi không xác định khi đăng bài")
            
            self.db.record_group_scan(
                execution_id=execution_id,
                group_id=group_id,
                group_name=group_name,
                category_name=cat_name,
                cycle_id=cycle_id,
                status="POST_FAILED",
                current_step="POSTING",
                deals_evaluated=eval_count,
                deal_posted_id=deal_id,
                deal_posted_name=deal_name,
                error_message=err_msg,
                duration_seconds=duration
            )
            self.db.update_cycle_progress(cycle_id, pointer + 1, current_group_id=group_id, failed_inc=1)
            
            engine_logger.error(f"❌ [ĐĂNG BÀI THẤT BẠI] tại nhóm [{group_name}] với nick [{account.get('name')}]: {err_msg}")
            return {
                "status": "POST_FAILED",
                "message": err_msg,
                "account_name": account.get("name"),
                "group_id": group_id,
                "group_name": group_name,
                "pointer": pointer + 1,
                "cycle_number": cycle["cycle_number"]
            }

        post_url = post_res.get("post_url", target_group.get("url", ""))
        account_name = account.get("name", "")

        # Ghi nhận chống đăng trùng
        self.db.record_deal_post(deal_id, group_id, post_url=post_url, account_name=account_name)

        # Bước C: SEEDING BÌNH LUẬN (SEEDING)
        self.db.record_group_scan(
            execution_id=execution_id,
            group_id=group_id,
            group_name=group_name,
            category_name=cat_name,
            cycle_id=cycle_id,
            status="SEEDING",
            current_step="SEEDING",
            deals_evaluated=eval_count,
            deal_posted_id=deal_id,
            deal_posted_name=deal_name,
            post_url=post_url
        )

        seeded_count = 0
        seeding_error = None
        try:
            seeding_results = self.seeder.run_seeding_scan(target_group_id=group_id)
            seeded_count = len(seeding_results)
        except Exception as seed_err:
            seeding_error = str(seed_err)
            engine_logger.warning(f"⚠️ [SEEDING CẢNH BÁO] tại nhóm [{group_name}]: {seed_err}")

        # Bước D: HOÀN TẤT NODE (COMPLETED / SEEDING_FAILED)
        duration = (datetime.now() - start_time).total_seconds()
        final_status = "SEEDING_FAILED" if seeding_error else "COMPLETED"

        self.db.record_group_scan(
            execution_id=execution_id,
            group_id=group_id,
            group_name=group_name,
            category_name=cat_name,
            cycle_id=cycle_id,
            status=final_status,
            current_step="COMPLETED",
            deals_evaluated=eval_count,
            deal_posted_id=deal_id,
            deal_posted_name=deal_name,
            post_url=post_url,
            deals_seeded=seeded_count,
            error_message=seeding_error,
            duration_seconds=duration
        )

        self.db.update_cycle_progress(
            cycle_id=cycle_id,
            pointer=pointer + 1,
            current_group_id=group_id,
            completed_inc=1 if final_status == "COMPLETED" else 0,
            failed_inc=1 if final_status == "SEEDING_FAILED" else 0,
            posts_inc=1,
            seedings_inc=seeded_count
        )

        engine_logger.info(
            f"🎉 [NODE HOÀN THÀNH {duration:.1f}s]: Nhóm [{group_name}] | "
            f"Deal: [{deal_name[:30]}...] | Bài đăng: {post_status} | Seeding: {seeded_count} cmt"
        )

        return {
            "status": final_status,
            "group_id": group_id,
            "group_name": group_name,
            "deal_id": deal_id,
            "deal_name": deal_name,
            "post_url": post_url,
            "seeded_count": seeded_count,
            "duration_seconds": round(duration, 1),
            "pointer": pointer + 1,
            "cycle_number": cycle["cycle_number"]
        }

    def run_full_cycle(self, max_steps: int = 50) -> Dict:
        """
        Chạy liên tục toàn bộ chu kỳ hiện tại cho đến khi duyệt hết danh mục nhóm
        hoặc đạt ngưỡng max_steps an toàn.
        """
        start_time = datetime.now()
        engine_logger.info("\n" + "#" * 80)
        engine_logger.info("🚀 [RUN FULL CYCLE]: BẮT ĐẦU DUYỆT TỰ ĐỘNG TOÀN BỘ CHU KỲ")
        engine_logger.info("#" * 80)

        step_results = []
        step = 0

        while step < max_steps:
            res = self.process_next_group()
            step_results.append(res)
            step += 1

            # Nếu chu kỳ hoàn tất hoặc gặp lỗi hệ thống
            if res.get("status") == "ERROR":
                break

            # Kiểm tra xem con trỏ đã quay về 0 (chu kỳ đã rollover hoàn thành)
            if res.get("pointer") == 0 and step > 1:
                engine_logger.info("🏁 Đã hoàn thành trọn vẹn chu kỳ nhóm!")
                break

            # Khoảng nghỉ an toàn giữa các nhóm
            time.sleep(2)

        elapsed = round((datetime.now() - start_time).total_seconds(), 2)
        daily_stats = self.db.get_daily_report_stats()

        return {
            "status": "SUCCESS",
            "steps_executed": step,
            "duration_seconds": elapsed,
            "daily_stats": daily_stats,
            "details": step_results
        }

    def retry_node(self, group_id: str) -> Dict:
        """
        Cơ chế Thử lại cấp độ Bước (Step-Level Retry):
        - Nếu Node bị POST_FAILED: Thử lại từ bước Đăng bài (không cần cào lại).
        - Nếu Node bị SEEDING_FAILED: Bài đã đăng xong, CHỈ thử lại bước Seeding!
        """
        today = datetime.now().strftime("%Y-%m-%d")
        with self.db.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM group_scan_history WHERE group_id = ? AND scan_date = ?",
                (str(group_id), today)
            ).fetchone()

            if not row:
                return {"status": "ERROR", "message": f"Không tìm thấy lịch sử xử lý của nhóm #{group_id} trong ngày hôm nay!"}

            record = dict(row)

        engine_logger.info(f"🔄 [RETRY NODE]: Thử lại cho nhóm [{record.get('group_name')}] (Trạng thái trước: {record.get('status')})")

        # Nếu lỗi ở bước Seeding: bài đã đăng, chỉ retry seeding
        if record.get("status") == "SEEDING_FAILED":
            engine_logger.info("   -> Phát hiện bài đăng đã tồn tại, CHỈ thử lại bước Seeding bình luận!")
            try:
                seeding_results = self.seeder.run_seeding_scan(target_group_id=group_id)
                seeded_count = len(seeding_results)
                
                self.db.record_group_scan(
                    execution_id=record["execution_id"],
                    group_id=group_id,
                    group_name=record["group_name"],
                    category_name=record["category_name"],
                    cycle_id=record["cycle_id"],
                    status="COMPLETED",
                    current_step="COMPLETED",
                    deals_evaluated=record["deals_evaluated"],
                    deal_posted_id=record["deal_posted_id"],
                    deal_posted_name=record["deal_posted_name"],
                    post_url=record["post_url"],
                    deals_seeded=seeded_count,
                    retry_count=record.get("retry_count", 0) + 1
                )
                return {"status": "SUCCESS", "message": f"Đã thử lại Seeding thành công ({seeded_count} comments)!"}
            except Exception as e:
                return {"status": "SEEDING_FAILED", "message": f"Thử lại Seeding vẫn thất bại: {e}"}

        # Nếu lỗi ở bước POST_FAILED hoặc chưa đăng:
        deal_id = record.get("deal_posted_id")
        post_res = self.poster.post_to_single_group(group_id, deal_id=deal_id)
        if post_res.get("status") not in ["SUCCESS", "PENDING_APPROVAL"]:
            return {"status": "POST_FAILED", "message": f"Thử lại Đăng bài vẫn thất bại: {post_res.get('message')}"}

        # Đăng bài thành công -> Ghi nhận và chạy tiếp Seeding
        post_url = post_res.get("post_url", "")
        self.db.record_deal_post(deal_id, group_id, post_url=post_url)
        
        seeded_count = 0
        try:
            seeding_results = self.seeder.run_seeding_scan(target_group_id=group_id)
            seeded_count = len(seeding_results)
        except Exception:
            pass

        self.db.record_group_scan(
            execution_id=record["execution_id"],
            group_id=group_id,
            group_name=record["group_name"],
            category_name=record["category_name"],
            cycle_id=record["cycle_id"],
            status="COMPLETED",
            current_step="COMPLETED",
            deals_evaluated=record["deals_evaluated"],
            deal_posted_id=deal_id,
            deal_posted_name=record.get("deal_posted_name"),
            post_url=post_url,
            deals_seeded=seeded_count,
            retry_count=record.get("retry_count", 0) + 1
        )

        return {"status": "SUCCESS", "message": "Đã thử lại thành công toàn bộ Node!"}

    def run_batch(self, max_groups: int = 5) -> Dict:
        """
        Chạy một đợt gồm N nhóm Facebook liên tiếp theo con trỏ chu kỳ.
        Đảm bảo State Machine hoàn tất tuần tự cho từng node.
        """
        results = []
        for i in range(max_groups):
            res = self.process_next_group()
            results.append(res)
            if res.get("status") == "ERROR":
                break
        return {
            "total_processed": len(results),
            "results": results
        }

