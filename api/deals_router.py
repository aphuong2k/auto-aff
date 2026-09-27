"""
Deals API Router
================
Endpoints quản lý sản phẩm, cào deal mồi 1K, kiểm tra độ tươi, lịch sử giá và phục vụ ảnh banner.
"""

from typing import Optional, List
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, RedirectResponse

from api.deps import (
    db, RAW_IMAGES_DIR, PROCESSED_IMAGES_DIR
)
from modules.crawler.deal_hunter import DealHunter
from modules.crawler.deal_freshness_checker import DealFreshnessChecker
from modules.crawler.price_history_tracker import PriceHistoryTracker
from modules.affiliate.lazada_provider import LazadaAffiliateProvider
from modules.affiliate.image_stamper import ImageBannerStamper

router = APIRouter(tags=["Deals"])


@router.get("/api/deals")
def get_deals(
    limit: int = 50,
    platform: Optional[str] = "ALL",
    category: Optional[str] = "ALL",
    deal_type: Optional[str] = "ALL",
    search: Optional[str] = None,
    sort_by: str = "score",
    is_stale: Optional[int] = 0
):
    """Lấy danh sách deal hỗ trợ lọc đa sàn (Shopee & Lazada), ngành hàng, loại deal, từ khóa và độ tươi"""
    deals = db.get_deals(
        limit=limit,
        platform=platform,
        is_stale=is_stale if is_stale in [0, 1] else None,
        category_name=category,
        search=search,
        deal_type=deal_type,
        sort_by=sort_by
    )

    for d in deals:
        item_id = str(d.get("item_id", ""))
        banner_file = PROCESSED_IMAGES_DIR / f"{item_id}_banner.jpg"
        d["has_stamped_image"] = banner_file.exists()
        d["stamped_image_url"] = f"/api/deals/image/{item_id}"
        if not d.get("price_badge"):
            d["price_badge"] = "UNVERIFIED"

    return deals


@router.get("/api/deals/loss-leaders")
def get_loss_leaders():
    """Lấy danh sách các Deal Mồi 1K để kích hoạt Cookie 7 ngày của Shopee"""
    deals = db.get_loss_leader_deals(limit=10)
    if not deals:
        hunter = DealHunter(db)
        deals = hunter.fetch_loss_leader_deals(limit=3)
    return deals


@router.post("/api/deals/fetch-loss-leaders")
def fetch_loss_leaders(limit: int = 3):
    """Cào thêm Deal Mồi 1K - Freeship 0Đ để rải link kéo traffic & ghim cookie"""
    hunter = DealHunter(db)
    deals = hunter.fetch_loss_leader_deals(limit=limit)
    return {
        "status": "SUCCESS",
        "message": f"Đã cào thành công {len(deals)} Deal Mồi 1K để kích hoạt Cookie 7 ngày!",
        "deals": deals
    }


@router.post("/api/deals/{item_id}/verify-freshness")
def verify_deal_freshness(item_id: str):
    """Kiểm tra thời gian thực độ tươi & tình trạng còn hàng của deal (Hỗ trợ cả Shopee và Lazada)"""
    deal = db.get_deal_by_id(item_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal không tồn tại")

    platform = str(deal.get("platform", "SHOPEE")).upper()
    if platform == "LAZADA":
        prov = LazadaAffiliateProvider()
        is_fresh = prov.verify_deal_freshness(deal)
    else:
        is_fresh = DealHunter.verify_deal_freshness(deal)

    db.mark_deal_stale(item_id, is_stale=0 if is_fresh else 1)
    return {
        "item_id": item_id,
        "name": deal.get("name"),
        "platform": platform,
        "is_fresh": is_fresh,
        "status": "VALID" if is_fresh else "EXPIRED_OR_OUT_OF_STOCK"
    }


@router.post("/api/deals/verify-all")
def verify_all_deals_api(max_deals: int = 40):
    """Kích hoạt kiểm tra độ tươi hàng loạt cho tất cả các deal đang hoạt động"""
    checker = DealFreshnessChecker(db)
    results = checker.check_all_active_deals(max_deals=max_deals)
    return results


@router.get("/api/deals/image/{item_id}")
def get_deal_image(item_id: str):
    """Phục vụ ảnh banner đã đóng khung Flash Sale cho deal, tự động fallback an toàn"""
    banner_path = PROCESSED_IMAGES_DIR / f"{item_id}_banner.jpg"
    if banner_path.exists():
        return FileResponse(str(banner_path), media_type="image/jpeg")

    deal = db.get_deal_by_id(item_id)
    if deal:
        try:
            path = ImageBannerStamper.stamp_deal_image(deal)
            if path and path.exists():
                return FileResponse(str(path), media_type="image/jpeg")
        except Exception:
            pass

        raw_path = RAW_IMAGES_DIR / f"{item_id}.jpg"
        if raw_path.exists():
            return FileResponse(str(raw_path), media_type="image/jpeg")

        if deal.get("image_url"):
            return RedirectResponse(deal["image_url"], status_code=307)

    try:
        placeholder_deal = deal or {"item_id": item_id, "name": "Shopee Flash Sale", "category_name": "Hot Deal"}
        path = ImageBannerStamper.stamp_deal_image(placeholder_deal)
        if path and path.exists():
            return FileResponse(str(path), media_type="image/jpeg")
    except Exception:
        pass

    raise HTTPException(status_code=404, detail="Ảnh không tồn tại")


@router.get("/api/deals/{item_id}/price-history")
def get_item_price_history(item_id: str):
    """Lấy lịch sử biến động giá và nhận định giảm giá thật / ảo"""
    history = db.get_price_history(item_id)
    deal = db.get_deal_by_id(item_id)
    tracker = PriceHistoryTracker(db)
    verdict = tracker.analyze_price_verdict(deal) if deal else {}
    return {
        "item_id": item_id,
        "history": history,
        "verdict": verdict
    }


@router.get("/api/deals/category-inventory")
def get_deals_category_inventory():
    """Lấy số lượng deal sẵn sàng theo từng ngành hàng để hiển thị trực quan trên giao diện"""
    with db.get_connection() as conn:
        rows = conn.execute("SELECT category_name, count(*) FROM deals WHERE is_stale = 0 GROUP BY category_name").fetchall()
        return {r[0]: r[1] for r in rows}


@router.get("/api/deals/by-category")
def get_deals_by_category(category: str):
    """Lấy danh sách tất cả deal thuộc một ngành cụ thể để người dùng chọn đăng vào nhóm"""
    with db.get_connection() as conn:
        rows = conn.execute("SELECT * FROM deals WHERE category_name = ? AND is_stale = 0 ORDER BY deal_score DESC LIMIT 30", (category,)).fetchall()
        return [dict(r) for r in rows]


@router.post("/api/deals/clear")
def clear_deals():
    db.clear_deals()
    return {"status": "SUCCESS", "message": "Đã xóa toàn bộ dữ liệu deal sản phẩm!"}

