"""
Social Outreach & Seeding API Router
====================================
Endpoints tạo nội dung tiếp thị, seeding comment Facebook, đăng bài theo nhóm,
tạo ảnh collage/banner và quản lý lịch sử bài đăng.
"""

import os
import threading
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from api.deps import (
    db, PROCESSED_IMAGES_DIR, gradual_posting_state, load_env_vars
)
from api.models import (
    SingleGroupPostRequest, GradualPostRequest,
    PostedLogCreateModel, PublishPromoPostModel
)
from modules.affiliate.content_writer import DealContentWriter
from modules.outreach.fb_group_seeder import FacebookGroupSeeder

router = APIRouter(tags=["Outreach & Social Copilot"])


@router.get("/api/social/generate-pack")
def generate_social_pack_api(
    item_id: str,
    angle: str = "review",
    channel: str = "fb_feed",
    sub_id: str = "",
    link_mode: str = "direct"
):
    """Tạo trọn gói bài đăng và link tiếp thị Mạng Xã Hội (Facebook, Threads, Comments)"""
    deal = db.get_deal_by_id(item_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Sản phẩm không tồn tại trong kho deal!")

    effective_sub = sub_id or channel
    bridge_url = f"/r/{item_id}?channel={channel}&sub_id={effective_sub}"
    direct_link = deal.get("aff_url") or deal.get("item_url", "")
    target_link = direct_link if (link_mode == "direct" or not bridge_url) else bridge_url

    pack = DealContentWriter.generate_social_copilot_pack(
        deal=deal,
        angle=angle,
        share_url=target_link
    )

    pack["item_id"] = item_id
    pack["channel"] = channel
    pack["sub_id"] = effective_sub
    pack["bridge_url"] = bridge_url
    pack["direct_aff_url"] = direct_link
    pack["target_link"] = target_link
    pack["link_mode"] = link_mode
    pack["image_url"] = f"/api/deals/image/{item_id}"
    pack["deal"] = deal
    return pack


# --- Seeding Bình Luận Dạo ---

@router.post("/api/outreach/seed-comments")
def trigger_seed_comments(max_groups: int = 10, group_id: Optional[str] = None):
    load_env_vars()
    fb_cookie = os.getenv("FB_COOKIE", "")
    fb_profile = os.getenv("FB_CHROME_PROFILE", "")
    if not fb_cookie and not fb_profile:
        raise HTTPException(
            status_code=400,
            detail="Chưa cấu hình Cookie Facebook hoặc Chrome Profile! Vui lòng vào Cài Đặt để cập nhật."
        )
    seeder = FacebookGroupSeeder(db)
    results = seeder.run_seeding_scan(max_groups=max_groups, target_group_id=group_id)
    return {
        "status": "SUCCESS",
        "message": f"Đã quét và xử lý {len(results)} bình luận seeding trên các nhóm Facebook thật!",
        "results": results
    }


@router.get("/api/outreach/seed-comments/history")
def get_seed_comments_history(limit: int = 50):
    return {"history": db.get_comment_seeding_history(limit=limit)}


@router.get("/api/outreach/seeding-logs")
def get_seeding_logs(lines: int = 150):
    from config.settings import FB_SEEDING_LOG_PATH
    if not FB_SEEDING_LOG_PATH.exists():
        return {"logs": "Chưa có file log seeding phát sinh."}
    try:
        with open(FB_SEEDING_LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
            recent_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
            return {"logs": "".join(recent_lines), "total_lines": len(all_lines)}
    except Exception as e:
        return {"logs": f"Lỗi đọc file log seeding: {e}"}


@router.post("/api/outreach/seeding-logs/clear")
def clear_seeding_logs():
    from config.settings import FB_SEEDING_LOG_PATH
    try:
        with open(FB_SEEDING_LOG_PATH, "w", encoding="utf-8") as f:
            f.write("")
        return {"status": "SUCCESS", "message": "Đã xóa nhật ký seeding thành công!"}
    except Exception as e:
        return {"status": "ERROR", "message": str(e)}


# --- Banner & Collage Generation ---

@router.get("/api/outreach/general-posts")
def get_general_outreach_posts():
    from modules.outreach.general_deal_outreach import GeneralDealOutreach
    outreach = GeneralDealOutreach(db)
    load_env_vars()
    url = os.getenv("COMMUNITY_INVITE_URL", "")
    name = os.getenv("COMMUNITY_NAME", "Hội Săn Deal Shopee VIP")
    return outreach.generate_all_general_posts(community_url=url, community_name=name)


@router.post("/api/outreach/generate-collage")
def generate_deal_collage():
    from modules.outreach.general_deal_outreach import GeneralDealOutreach
    outreach = GeneralDealOutreach(db)
    outreach.generate_daily_collage()
    return {
        "status": "SUCCESS",
        "message": "Đã tạo thành công ảnh ghép 4 deal (2x2 Mega Collage Grid) chuẩn 800x800!",
        "image_url": "/api/outreach/collage-image"
    }


@router.get("/api/outreach/collage-image")
def get_collage_image():
    collage_path = PROCESSED_IMAGES_DIR / "daily_mega_collage.jpg"
    if not collage_path.exists():
        from modules.outreach.general_deal_outreach import GeneralDealOutreach
        outreach = GeneralDealOutreach(db)
        collage_path = outreach.generate_daily_collage()
    if collage_path.exists():
        return FileResponse(str(collage_path), media_type="image/jpeg")
    raise HTTPException(status_code=404, detail="Ảnh ghép chưa được tạo")


@router.post("/api/outreach/generate-header-banner")
def generate_header_banner(date_str: Optional[str] = ""):
    from modules.outreach.general_deal_outreach import GeneralDealOutreach
    outreach = GeneralDealOutreach(db)
    banner_path = outreach.generate_daily_header_banner(date_str=date_str or "")
    return {
        "status": "SUCCESS",
        "message": f"Đã tạo thành công ảnh tiêu đề Deal Shopee ngày {datetime.now().strftime('%d/%m/%Y')}!",
        "image_url": "/api/outreach/header-banner-image"
    }


@router.get("/api/outreach/header-banner-image")
def get_header_banner_image():
    banner_path = PROCESSED_IMAGES_DIR / "daily_deal_header_banner.jpg"
    if not banner_path.exists():
        from modules.outreach.general_deal_outreach import GeneralDealOutreach
        outreach = GeneralDealOutreach(db)
        banner_path = outreach.generate_daily_header_banner()
    if banner_path.exists():
        return FileResponse(str(banner_path), media_type="image/jpeg")
    raise HTTPException(status_code=404, detail="Ảnh tiêu đề chưa được tạo")


@router.post("/api/outreach/generate-voucher-banner")
def generate_voucher_banner(date_str: Optional[str] = ""):
    from modules.affiliate.image_stamper import ImageBannerStamper
    banner_path = ImageBannerStamper.create_voucher_banner(date_str=date_str or "")
    return {
        "status": "SUCCESS",
        "message": f"Đã tạo thành công ảnh banner Voucher & Bí Kíp Săn Sale ngày {datetime.now().strftime('%d/%m/%Y')}!",
        "image_url": "/api/outreach/voucher-banner-image"
    }


@router.get("/api/outreach/voucher-banner-image")
def get_voucher_banner_image():
    banner_path = PROCESSED_IMAGES_DIR / "daily_voucher_banner.jpg"
    if not banner_path.exists():
        from modules.affiliate.image_stamper import ImageBannerStamper
        banner_path = ImageBannerStamper.create_voucher_banner()
    if banner_path.exists():
        return FileResponse(str(banner_path), media_type="image/jpeg")
    raise HTTPException(status_code=404, detail="Ảnh banner voucher chưa được tạo")


# --- Posted Logs ---

@router.get("/api/logs/posted")
def get_posted_logs(limit: int = 50, type: Optional[str] = None):
    return {"logs": db.get_posted_logs(limit=limit, post_type=type)}


@router.post("/api/logs/posted")
def create_posted_log(item: PostedLogCreateModel):
    log_id = db.log_posted_item(
        post_type=item.type,
        group_name=item.group_name,
        group_url=item.group_url or "",
        target_url=item.target_url or "",
        item_id=item.item_id or "",
        item_name=item.item_name or "",
        content_snippet=item.content_snippet or "",
        image_path=item.image_path or "",
        status=item.status or "SUCCESS"
    )
    return {
        "status": "SUCCESS",
        "id": log_id,
        "message": "Đã lưu lịch sử bài đăng/comment thành công!"
    }


@router.delete("/api/logs/posted/{log_id}")
def delete_posted_log(log_id: int):
    db.delete_posted_log(log_id)
    return {"status": "SUCCESS", "message": f"Đã xóa log #{log_id}!"}


# --- Đăng Bài Nhóm (Group Poster & Gradual Posting) ---

@router.post("/api/outreach/post-to-group")
@router.post("/api/groups/post-single")
def post_single_group_api(req: SingleGroupPostRequest):
    from modules.outreach.fb_group_poster import FacebookGroupPoster
    poster = FacebookGroupPoster(db)
    res = poster.post_to_single_group(req.group_id, req.deal_id, account_id=req.account_id)
    if res.get("status") == "ERROR":
        raise HTTPException(status_code=500, detail=res.get("message", "Lỗi khi đăng bài"))
    elif res.get("status") == "COOLDOWN_ACTIVE":
        raise HTTPException(status_code=429, detail=res.get("message", "Tất cả tài khoản đang trong thời gian Cooldown."))
    elif res.get("status") == "FAILED":
        raise HTTPException(status_code=400, detail=res.get("message", "Không thể đăng bài vào nhóm này."))
    return res


@router.post("/api/outreach/start-gradual-posting")
@router.post("/api/groups/start-gradual-posting")
def start_gradual_posting_api(req: GradualPostRequest):
    from modules.outreach.fb_group_poster import FacebookGroupPoster, gradual_posting_state
    if gradual_posting_state.get("is_running"):
        return {"status": "ALREADY_RUNNING", "message": "Chu trình đăng bài đang chạy!", "state": gradual_posting_state}

    poster = FacebookGroupPoster(db)

    eff_delay = req.delay_seconds if req.delay_seconds is not None else (req.min_delay_seconds or 60)
    eff_min = eff_delay
    eff_max = eff_delay if req.delay_seconds is not None else (req.max_delay_seconds or eff_delay + 30)
    target_count = len(req.group_ids) if req.group_ids else (req.max_groups or 3)

    def run_job():
        try:
            poster.run_gradual_posting(
                max_groups=target_count,
                min_delay_seconds=eff_min,
                max_delay_seconds=eff_max,
                group_ids=req.group_ids,
                delay_seconds=eff_delay,
                account_id=req.account_id
            )
        except Exception as e:
            gradual_posting_state["is_running"] = False
            gradual_posting_state["status"] = "ERROR"
            gradual_posting_state["last_error"] = str(e)

    thread = threading.Thread(target=run_job, daemon=True)
    thread.start()

    return {
        "status": "STARTED",
        "message": f"Đã khởi động tiến trình đăng tuần tự vào {target_count} nhóm (nhịp nghỉ {eff_delay}s)!",
        "state": gradual_posting_state
    }


@router.post("/api/outreach/stop-gradual-posting")
def stop_gradual_posting_api():
    from modules.outreach.fb_group_poster import gradual_posting_state
    gradual_posting_state["is_running"] = False
    gradual_posting_state["status"] = "STOPPED"
    return {"status": "SUCCESS", "message": "Đã gửi tín hiệu dừng chu trình đăng bài dần!"}


@router.get("/api/outreach/gradual-posting-status")
def get_gradual_posting_status_api():
    from modules.outreach.fb_group_poster import gradual_posting_state
    return gradual_posting_state


# --- Sinh Bài & Bắn Tin Khuyến Mại ---

@router.get("/api/promotions/generated-posts")
def get_promotions_generated_posts():
    vouchers = db.get_voucher_codes()
    links = db.get_campaign_links()

    now = datetime.now()
    date_str = f"{now.day}.{now.month}"

    manual_vouchers = [v for v in vouchers if v.get("voucher_type") == "MANUAL"]
    big_percent_vouchers = [v for v in vouchers if v.get("voucher_type") == "BIG_PERCENT"]

    post_manual = DealContentWriter.generate_manual_vouchers_post(
        vouchers=manual_vouchers,
        wallet_url=links.get("wallet_url", "https://s.shopee.vn/1LPJSANV7v"),
        campaign_date=date_str
    )

    now_hour = now.hour
    all_slots = ["0H", "9H", "12H", "15H", "18H", "20H"]
    slot_hours = [0, 9, 12, 15, 18, 20]
    future_slots = [all_slots[i] for i, h in enumerate(slot_hours) if h >= now_hour]
    if not future_slots:
        future_slots = ["0H", "9H", "12H", "15H"]
    current_slot = future_slots[0] if future_slots else "12H"
    rem_str = ", ".join(future_slots)

    post_back_alert = DealContentWriter.generate_voucher_back_alert_post(
        slot_time=current_slot,
        banner_1=links.get("banner_1_url", "https://s.shopee.vn/6q0WqKvmkf"),
        banner_2=links.get("banner_2_url", "https://s.shopee.vn/7AdjQWuTmi"),
        remaining_slots=rem_str,
        campaign_date=date_str
    )

    post_flash_high = DealContentWriter.generate_flash_high_value_post(
        items=big_percent_vouchers if big_percent_vouchers else None
    )

    post_flat_deal = DealContentWriter.generate_flat_price_deal_post(
        slot_time=current_slot,
        price_label="99K",
        deal_url=links.get("flat_deal_url", "https://s.shopee.vn/5q8Qf8NVyC")
    )

    return {
        "date": date_str,
        "current_slot": current_slot,
        "remaining_slots": rem_str,
        "post_manual_vouchers": post_manual,
        "post_voucher_back_alert": post_back_alert,
        "post_flash_high_value": post_flash_high,
        "post_flat_deal": post_flat_deal,
        "vouchers_count": len(vouchers),
        "campaign_links": links
    }


@router.post("/api/promotions/publish-post")
def publish_voucher_post(req: PublishPromoPostModel):
    load_env_vars()
    if req.target.upper() == "TELEGRAM":
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        if not token or not chat_id:
            raise HTTPException(status_code=400, detail="Chưa cấu hình Telegram Bot Token hoặc Chat ID!")

        from modules.publisher.telegram_bot import TelegramPublisher
        publisher = TelegramPublisher(token=token, chat_id=chat_id, db=db)
        res = publisher.send_message(req.content)
        if res.get("ok"):
            db.log_posted_item(
                post_type="PROMO_POST",
                group_name="Telegram Channel",
                content_snippet=req.content[:100],
                status="SUCCESS"
            )
            return {"status": "SUCCESS", "message": "Đã xuất bản bài viết lên Telegram thành công!"}
        else:
            raise HTTPException(status_code=500, detail=res.get("description", "Lỗi gửi Telegram"))
    elif req.target.upper() == "FB_GROUP":
        if not req.group_id:
            raise HTTPException(status_code=400, detail="Vui lòng chọn nhóm Facebook cần đăng bài!")

        from modules.outreach.fb_group_poster import FacebookGroupPoster
        poster = FacebookGroupPoster(db)
        res = poster.post_to_single_group(
            group_id=req.group_id,
            custom_content=req.content,
            account_id=req.account_id
        )
        return res
    else:
        raise HTTPException(status_code=400, detail="Nền tảng đích không hợp lệ (hỗ trợ 'TELEGRAM' hoặc 'FB_GROUP')")
