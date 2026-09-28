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


@router.post("/api/deals/audit-and-clean")
def audit_and_clean_deals_api(
    min_sold: int = 50,
    min_rating: float = 4.0,
    delete_stale: bool = True
):
    """
    Quét toàn bộ kho sản phẩm:
    1. Lọc và xóa bớt các deal lỗi, giá <= 0, ôi thiu (is_stale=1), lượt bán quá thấp (< min_sold) hoặc đánh giá sao kém (< min_rating).
    2. Chuẩn hóa & phân loại lại đúng danh mục ngành hàng theo CategoryMatcher cho toàn bộ sản phẩm còn lại.
    3. Cập nhật tồn kho ngành hàng và trả về báo cáo kết quả chi tiết.
    """
    from config.category_mapping import CategoryMatcher
    from config.categories_filter import translate_category
    matcher = CategoryMatcher()

    with db.get_connection() as conn:
        all_deals = conn.execute("SELECT * FROM deals").fetchall()
        total_scanned = len(all_deals)

        # 1. Tìm các sản phẩm cần xóa bớt
        bad_ids = []
        for d in all_deals:
            item_id = str(d["item_id"])
            price_sale = float(d["price_sale"] or 0)
            name = (d["name"] or "").strip()
            is_stale = int(d["is_stale"] or 0)
            rating = float(d["rating_star"] or 0)
            sold = int(d["historical_sold"] or 0)
            deal_type = str(d["deal_type"] or "").upper() if "deal_type" in d.keys() else ""

            # Điều kiện loại bỏ:
            # - Tên rỗng hoặc giá không hợp lệ
            # - Đã bị đánh dấu stale / hết hạn / hết hàng (nếu delete_stale = True)
            # - Rating thấp < min_rating (đối với sản phẩm có rating)
            # - Lượt bán quá ế (< min_sold), trừ deal mồi 1k
            is_bad = False
            if not name or price_sale <= 0:
                is_bad = True
            elif delete_stale and is_stale == 1:
                is_bad = True
            elif rating > 0 and rating < min_rating:
                is_bad = True
            elif sold < min_sold and price_sale > 1000 and "LOSS_LEADER" not in deal_type:
                is_bad = True

            if is_bad:
                bad_ids.append(item_id)

        # Xóa các deal xấu khỏi CSDL theo batch
        deleted_count = len(bad_ids)
        if bad_ids:
            for i in range(0, len(bad_ids), 100):
                chunk = bad_ids[i:i + 100]
                placeholders = ",".join(["?"] * len(chunk))
                conn.execute(f"DELETE FROM deals WHERE item_id IN ({placeholders})", chunk)
                try:
                    conn.execute(f"DELETE FROM price_history WHERE item_id IN ({placeholders})", chunk)
                except Exception:
                    pass
            conn.commit()

        # 2. Phân loại lại toàn bộ sản phẩm còn lại
        remaining_deals = conn.execute("SELECT item_id, name, category_name FROM deals").fetchall()
        remaining_count = len(remaining_deals)
        reclassified_count = 0

        for d in remaining_deals:
            item_id = str(d["item_id"])
            name = d["name"] or ""
            current_cat = d["category_name"] or ""

            # Nhận diện ngành qua CategoryMatcher
            text_match = matcher.detect_category_from_text(name)
            if text_match:
                new_cat = text_match["rule"]["category_name"]
            else:
                new_cat = db.classify_product_niche(name, current_cat)

            new_cat = translate_category(new_cat)

            if new_cat and new_cat != current_cat:
                conn.execute("UPDATE deals SET category_name = ? WHERE item_id = ?", (new_cat, item_id))
                reclassified_count += 1

        conn.commit()

        # Tính tồn kho sau khi dọn dẹp
        inv_rows = conn.execute("SELECT category_name, count(*) FROM deals WHERE is_stale = 0 GROUP BY category_name").fetchall()
        inv_map = {r[0]: r[1] for r in inv_rows}

    return {
        "status": "SUCCESS",
        "total_scanned": total_scanned,
        "deleted_count": deleted_count,
        "reclassified_count": reclassified_count,
        "remaining_count": remaining_count,
        "category_inventory": inv_map,
        "message": f"Đã quét {total_scanned} sản phẩm: Xóa bỏ {deleted_count} deal lỗi/hết hàng/bán ế, chuẩn hóa lại danh mục cho {reclassified_count} sản phẩm! Hiện còn {remaining_count} sản phẩm chất lượng cao."
    }


@router.post("/api/deals/clear")
def clear_deals():
    db.clear_deals()
    return {"status": "SUCCESS", "message": "Đã xóa toàn bộ dữ liệu deal sản phẩm!"}

