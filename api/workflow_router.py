"""
Workflow & Closed-Loop Engine API Router
========================================
Endpoints điều khiển toàn trình (5 bước), chu trình tự động khép kín (Closed-Loop Engine),
lịch chạy tự động (Scheduler) và quản lý tải tài khoản Facebook.
"""

import time
import threading
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, HTTPException, BackgroundTasks

from api.deps import (
    db, closed_loop_engine, system_state, closed_loop_state,
    scheduler_state, load_env_vars, run_orchestrator_worker
)
from api.models import (
    ScheduleModel, RunWorkflowRequest, RetryNodeRequest
)

router = APIRouter(tags=["Workflow & Automation"])

_last_run_trigger_time = 0.0


@router.get("/api/status")
def get_status():
    """Lấy trạng thái hệ thống runtime"""
    return system_state


@router.get("/api/schedule")
def get_schedule():
    """Lấy cấu hình lịch chạy tự động"""
    return {
        "enabled": scheduler_state["enabled"],
        "time": scheduler_state["time"],
        "cats": scheduler_state["cats"],
        "last_scheduled_run": scheduler_state["last_scheduled_run"],
        "next_run_display": f"{scheduler_state['time']} Hàng ngày" if scheduler_state["enabled"] else "Đã tạm dừng (Chỉ chạy thủ công)"
    }


@router.post("/api/schedule")
def update_schedule(data: ScheduleModel):
    """Cập nhật cấu hình lịch chạy tự động"""
    scheduler_state["enabled"] = data.enabled
    scheduler_state["time"] = data.time
    scheduler_state["cats"] = data.cats
    db.set_system_setting("auto_schedule_enabled", str(data.enabled).lower())
    db.set_system_setting("auto_schedule_time", data.time)
    db.set_system_setting("auto_schedule_cats", str(data.cats))
    return {
        "status": "SUCCESS",
        "message": f"Đã cập nhật lịch chạy: {data.time} mỗi ngày (Tự động chạy: {'BẬT' if data.enabled else 'TẮT'})"
    }


# --- Thực thi thủ công từng bước độc lập ---

@router.post("/api/workflow/step/crawl")
def workflow_step_crawl(cats: int = 3):
    """BƯỚC 1 (THỦ CÔNG): Quét & Lọc Deal Sốc Đa Sàn (Shopee & Lazada) theo ngành hàng"""
    if system_state["is_running"]:
        raise HTTPException(status_code=400, detail="Hệ thống đang chạy tiến trình khác, vui lòng chờ!")

    def run_step_crawl():
        system_state["is_running"] = True
        system_state["last_status"] = "RUNNING_CRAWL"
        start_t = datetime.now()
        rep_id = db.create_workflow_report("MANUAL_STEP", "CRAWL_DEALS", f"Thủ công Bước 1: Quét deal cho {cats} ngành hàng")
        try:
            from modules.crawler.shopee_categories import ShopeeCategoryCrawler
            from modules.crawler.deal_hunter import DealHunter
            from modules.crawler.lazada_deal_hunter import LazadaDealHunter

            crawler = ShopeeCategoryCrawler(db)
            categories = crawler.fetch_categories()
            if not categories:
                categories = [{"cat_id": c["cat_id"], "name": c["name"]} for c in db.get_all_categories()]
            target_cats = categories[:cats]

            deal_hunter = DealHunter(db)
            lazada_hunter = LazadaDealHunter(db)

            shopee_deals = deal_hunter.hunt_top_deals(target_cats)
            lazada_deals = lazada_hunter.hunt_lazada_deals(target_cats)
            total_deals = len(shopee_deals) + len(lazada_deals)

            dur = (datetime.now() - start_t).total_seconds()
            db.update_workflow_report(
                rep_id,
                status="SUCCESS",
                duration_seconds=round(dur, 2),
                deals_scanned=cats * 20,
                deals_saved=total_deals,
                summary_text=f"Đã quét thành công {total_deals} deal ({len(shopee_deals)} Shopee, {len(lazada_deals)} Lazada)."
            )
            system_state["last_status"] = "COMPLETED"
        except Exception as e:
            dur = (datetime.now() - start_t).total_seconds()
            db.update_workflow_report(rep_id, status="ERROR", duration_seconds=round(dur, 2), error_message=str(e))
            system_state["last_status"] = "ERROR"
            system_state["last_error"] = str(e)
        finally:
            system_state["is_running"] = False
            system_state["last_run_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    threading.Thread(target=run_step_crawl, daemon=True).start()
    return {"status": "STARTED", "message": f"Đã khởi động Bước 1: Đang quét deal cho {cats} ngành hàng..."}


@router.post("/api/workflow/step/create-media")
def workflow_step_media():
    """BƯỚC 2 (THỦ CÔNG): Tạo khung ảnh Flash Sale 800x800, ảnh bìa 1080x1080 và ghép 4 deal"""
    start_t = datetime.now()
    rep_id = db.create_workflow_report("MANUAL_STEP", "GENERATE_MEDIA", "Thủ công Bước 2: Tạo banner Flash Sale & ảnh bài đăng")
    try:
        from modules.affiliate.image_stamper import ImageBannerStamper
        from modules.outreach.general_deal_outreach import GeneralDealOutreach

        deals = db.get_deals(limit=10, is_stale=0)
        stamped_count = 0
        for d in deals:
            img = ImageBannerStamper.stamp_deal_image(d)
            if img:
                stamped_count += 1

        outreach = GeneralDealOutreach(db)
        header_banner = outreach.generate_daily_header_banner()
        collage = outreach.generate_daily_collage()

        dur = (datetime.now() - start_t).total_seconds()
        db.update_workflow_report(
            rep_id,
            status="SUCCESS",
            duration_seconds=round(dur, 2),
            banners_created=stamped_count + 2,
            summary_text=f"Đã đóng khung {stamped_count} ảnh sale 800x800, 1 ảnh bìa 1080x1080 và 1 ảnh ghép collage 4 deal."
        )
        return {
            "status": "SUCCESS",
            "message": f"Đã tạo thành công {stamped_count} ảnh khung sale và 2 bộ ảnh bìa/collage!",
            "banners_created": stamped_count + 2,
            "header_banner": str(header_banner) if header_banner else "",
            "collage": str(collage) if collage else ""
        }
    except Exception as e:
        dur = (datetime.now() - start_t).total_seconds()
        db.update_workflow_report(rep_id, status="ERROR", duration_seconds=round(dur, 2), error_message=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/workflow/step/telegram")
def workflow_step_telegram():
    """BƯỚC 3 (THỦ CÔNG): Bắn loạt deal hot lên Kênh Telegram Channel / Group"""
    start_t = datetime.now()
    rep_id = db.create_workflow_report("MANUAL_STEP", "TELEGRAM_PUB", "Thủ công Bước 3: Bắn tin Kênh Telegram")
    try:
        from modules.publisher.telegram_bot import TelegramPublisher
        publisher = TelegramPublisher(db=db)
        deals = db.get_deals(limit=5, is_stale=0)
        published_count = 0
        for d in deals:
            res = publisher.publish_deal_with_banner(d)
            if res.get("status") == "SUCCESS":
                published_count += 1

        dur = (datetime.now() - start_t).total_seconds()
        db.update_workflow_report(
            rep_id,
            status="SUCCESS",
            duration_seconds=round(dur, 2),
            telegram_posts=published_count,
            summary_text=f"Đã xuất bản thành công {published_count} deal kèm ảnh lên Telegram."
        )
        return {
            "status": "SUCCESS",
            "message": f"Đã xuất bản {published_count} bài viết lên Telegram!",
            "published_count": published_count
        }
    except Exception as e:
        dur = (datetime.now() - start_t).total_seconds()
        db.update_workflow_report(rep_id, status="ERROR", duration_seconds=round(dur, 2), error_message=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/workflow/step/fb-outreach")
def workflow_step_fb_outreach(max_groups: int = 3):
    """BƯỚC 4 (THỦ CÔNG): Đăng bài dần vào nhóm FB theo đúng ngành hàng"""
    start_t = datetime.now()
    rep_id = db.create_workflow_report("MANUAL_STEP", "FB_OUTREACH", f"Thủ công Bước 4: Đăng bài dần vào {max_groups} nhóm Facebook")
    try:
        from modules.outreach.fb_group_poster import FacebookGroupPoster, gradual_posting_state
        if gradual_posting_state.get("is_running"):
            return {"status": "ALREADY_RUNNING", "message": "Chu trình đăng bài FB đang chạy!"}

        poster = FacebookGroupPoster(db)

        def run_fb():
            try:
                poster.run_gradual_posting(max_groups=max_groups, min_delay_seconds=5, max_delay_seconds=15)
                dur = (datetime.now() - start_t).total_seconds()
                db.update_workflow_report(
                    rep_id,
                    status="SUCCESS",
                    duration_seconds=round(dur, 2),
                    fb_posts=max_groups,
                    summary_text=f"Hoàn tất quy trình đăng bài dần vào nhóm Facebook."
                )
            except Exception as fe:
                dur = (datetime.now() - start_t).total_seconds()
                db.update_workflow_report(rep_id, status="ERROR", duration_seconds=round(dur, 2), error_message=str(fe))

        threading.Thread(target=run_fb, daemon=True).start()
        return {"status": "STARTED", "message": f"Đang khởi động đăng bài dần vào {max_groups} nhóm Facebook phù hợp..."}
    except Exception as e:
        dur = (datetime.now() - start_t).total_seconds()
        db.update_workflow_report(rep_id, status="ERROR", duration_seconds=round(dur, 2), error_message=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/workflow/step/seeding")
def workflow_step_seeding(max_groups: int = 3):
    """BƯỚC 5 (THỦ CÔNG): Gieo bình luận seeding kèm link Anti-Ban"""
    start_t = datetime.now()
    rep_id = db.create_workflow_report("MANUAL_STEP", "SEEDING_COMMENTS", f"Thủ công Bước 5: Gieo bình luận seeding {max_groups} nhóm")
    try:
        load_env_vars()
        from modules.outreach.fb_group_seeder import FacebookGroupSeeder
        seeder = FacebookGroupSeeder(db)
        results = seeder.run_seeding_scan(max_groups=max_groups)
        dur = (datetime.now() - start_t).total_seconds()
        db.update_workflow_report(
            rep_id,
            status="SUCCESS",
            duration_seconds=round(dur, 2),
            comments_seeded=len(results),
            summary_text=f"Đã gieo thành công {len(results)} bình luận seeding kèm link Anti-Ban."
        )
        return {
            "status": "SUCCESS",
            "message": f"Đã gieo thành công {len(results)} bình luận seeding!",
            "comments_count": len(results)
        }
    except Exception as e:
        dur = (datetime.now() - start_t).total_seconds()
        db.update_workflow_report(rep_id, status="ERROR", duration_seconds=round(dur, 2), error_message=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/workflow/run-all")
def workflow_run_all(background_tasks: BackgroundTasks, cats: int = 3, req: Optional[RunWorkflowRequest] = None):
    """KÍCH HOẠT CHẠY TOÀN TRÌNH 5 BƯỚC (THỦ CÔNG 1-CLICK)"""
    if system_state["is_running"]:
        raise HTTPException(status_code=400, detail="Hệ thống đang chạy, vui lòng chờ hoàn thành!")
    selected_ids = req.category_ids if req and req.category_ids else None
    num_cats = len(selected_ids) if selected_ids else (req.cats if req and req.cats else cats)
    background_tasks.add_task(run_orchestrator_worker, num_cats, "MANUAL_ALL", selected_ids)
    msg_suffix = f"cho {num_cats} ngành hàng đã chọn" if selected_ids else f"cho {num_cats} ngành hàng"
    return {
        "status": "STARTED",
        "message": f"Đã kích hoạt toàn trình 5 bước {msg_suffix}! Xem tiến trình trong Nhật Ký và Báo Cáo."
    }


@router.get("/api/workflow/reports")
def get_workflow_reports_api(limit: int = 25):
    """Lấy danh sách các báo cáo phiên chạy (Tự động & Thủ công)"""
    return {
        "reports": db.get_workflow_reports(limit=limit)
    }


# --- Closed-Loop Workflow APIs ---

@router.get("/api/closed-loop/status")
def get_closed_loop_status():
    """Lấy trạng thái chi tiết thời gian thực của Vòng Lặp Khép Kín"""
    status = closed_loop_engine.get_workflow_status()
    status["runtime"] = closed_loop_state
    return status


@router.post("/api/closed-loop/run-next")
def run_closed_loop_next():
    """Xử lý thủ công Node Group tiếp theo theo con trỏ hiện tại"""
    if closed_loop_state["is_running"]:
        raise HTTPException(status_code=400, detail="Chu trình đang chạy một tác vụ khác!")

    def _worker():
        closed_loop_state["is_running"] = True
        closed_loop_state["current_action"] = "RUN_NEXT_GROUP"
        closed_loop_state["last_error"] = None
        try:
            res = closed_loop_engine.process_next_group()
            closed_loop_state["last_result"] = res
        except Exception as e:
            closed_loop_state["last_error"] = str(e)
        finally:
            closed_loop_state["is_running"] = False
            closed_loop_state["current_action"] = "IDLE"

    threading.Thread(target=_worker, daemon=True).start()
    return {"status": "STARTED", "message": "Đang xử lý Node Group tiếp theo trong chu kỳ..."}


@router.post("/api/closed-loop/run-cycle")
def run_closed_loop_cycle(max_steps: int = 50):
    """Kích hoạt chạy tự động toàn bộ chu kỳ hiện tại cho đến khi hoàn tất danh mục"""
    if closed_loop_state["is_running"]:
        raise HTTPException(status_code=400, detail="Chu trình đang chạy một tác vụ khác!")

    def _worker():
        closed_loop_state["is_running"] = True
        closed_loop_state["current_action"] = "RUN_FULL_CYCLE"
        closed_loop_state["last_error"] = None
        try:
            res = closed_loop_engine.run_full_cycle(max_steps=max_steps)
            closed_loop_state["last_result"] = res
        except Exception as e:
            closed_loop_state["last_error"] = str(e)
        finally:
            closed_loop_state["is_running"] = False
            closed_loop_state["current_action"] = "IDLE"

    threading.Thread(target=_worker, daemon=True).start()
    return {"status": "STARTED", "message": "Đã bắt đầu chạy toàn bộ chu kỳ nhóm tự động!"}


@router.post("/api/closed-loop/collect-deals")
def collect_deals_api(limit_per_cat: int = 20):
    """Kích hoạt cào và thẩm định deal trung tâm đa sàn"""
    if closed_loop_state["is_running"]:
        raise HTTPException(status_code=400, detail="Chu trình đang chạy một tác vụ khác!")

    def _worker():
        closed_loop_state["is_running"] = True
        closed_loop_state["current_action"] = "COLLECT_DEALS"
        closed_loop_state["last_error"] = None
        try:
            res = closed_loop_engine.collector.collect_all_categories(limit_per_cat=limit_per_cat)
            closed_loop_state["last_result"] = res
        except Exception as e:
            closed_loop_state["last_error"] = str(e)
        finally:
            closed_loop_state["is_running"] = False
            closed_loop_state["current_action"] = "IDLE"

    threading.Thread(target=_worker, daemon=True).start()
    return {"status": "STARTED", "message": "Đang cào và thẩm định deal trung tâm theo tiêu chuẩn Quality Gate..."}


@router.post("/api/closed-loop/retry-node")
def retry_closed_loop_node(data: RetryNodeRequest):
    """Thử lại bước lỗi của Node"""
    res = closed_loop_engine.retry_node(data.group_id)
    if res.get("status") == "ERROR":
        raise HTTPException(status_code=400, detail=res.get("message"))
    return res


@router.get("/api/closed-loop/history")
def get_closed_loop_history(limit: int = 50, cycle_id: Optional[int] = None, group_id: Optional[str] = None):
    """Lấy danh sách nhật ký thực thi từng Node Group"""
    return {
        "history": db.get_group_scan_history(limit=limit, cycle_id=cycle_id, group_id=group_id)
    }


@router.get("/api/closed-loop/cycles")
def get_closed_loop_cycles(limit: int = 20):
    """Lấy danh sách các chu kỳ đã và đang hoạt động"""
    return {
        "cycles": db.get_all_cycles(limit=limit)
    }


@router.get("/api/closed-loop/daily-report")
def get_closed_loop_daily_report(date_str: Optional[str] = None):
    """Lấy báo cáo tổng hợp tiến độ và tỷ lệ thành công theo ngày"""
    return db.get_daily_report_stats(date_str=date_str)


@router.get("/api/accounts/workload")
def get_accounts_workload():
    """Lấy tình trạng phân phối tải & thời gian cooldown của từng tài khoản Facebook"""
    return {
        "accounts": closed_loop_engine.account_router.get_workload_status(),
        "history": db.get_account_usage_history(limit=30)
    }


@router.post("/api/accounts/{account_id}/release-cooldown")
def release_account_cooldown_api(account_id: int):
    """Xóa bỏ thời gian chờ Cooldown thủ công cho tài khoản"""
    closed_loop_engine.account_router.release_cooldown(account_id)
    return {
        "status": "SUCCESS",
        "message": f"Đã giải phóng thời gian chờ Cooldown cho tài khoản #{account_id}!"
    }


@router.post("/api/run")
def trigger_run(background_tasks: BackgroundTasks, req: Optional[RunWorkflowRequest] = None, cats: Optional[int] = None):
    """Kích hoạt chu trình toàn trình"""
    global _last_run_trigger_time
    now_ts = time.time()
    if system_state["is_running"]:
        raise HTTPException(status_code=400, detail="Hệ thống đang chạy, vui lòng chờ hoàn thành!")
    if (now_ts - _last_run_trigger_time) < 15:
        raise HTTPException(status_code=429, detail="Thao tác quá nhanh, vui lòng chờ 15 giây giữa các lần kích hoạt chu trình!")

    selected_ids = req.category_ids if req and req.category_ids else None
    num_cats = len(selected_ids) if selected_ids else (req.cats if req and req.cats else (cats or 2))

    _last_run_trigger_time = now_ts
    background_tasks.add_task(run_orchestrator_worker, num_cats, "MANUAL_ALL", selected_ids)
    cat_msg = f"cho {num_cats} ngành hàng đã chọn" if selected_ids else f"cho {num_cats} ngành hàng"
    return {"status": "STARTED", "message": f"Đã kích hoạt chạy chu trình {cat_msg}!"}
