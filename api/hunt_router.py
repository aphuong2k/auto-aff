"""
Deal Hunter API Router
======================
Cung cấp các API endpoint phục vụ tính năng "🔎 Quét & Săn Deal":
- Quản lý danh sách Group / Channel Telegram cần quét
- Thực hiện quét từ Group Telegram hoặc nhập tên sản phẩm bất kỳ
- Tự động nhận diện và gom tin đăng cùng sản phẩm, tính Giá trung bình & Giá tham chiếu
- Cào sản phẩm từ nguồn đã chọn (Tmall / LazMall / Lazada Khác / All)
- So sánh giá, ưu tiên deal thấp hơn giá tham chiếu
- Tự động gửi deal vào Telegram khi đạt điều kiện
- Lưu trữ lịch sử biến động giá, hỗ trợ "Quét Lại" giữ nguyên lịch sử cũ
"""

import logging
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Depends

from api.deps import db
from modules.crawler.telegram_scanner import TelegramScanner
from modules.crawler.facebook_scanner import FacebookScanner
from modules.crawler.product_cluster_engine import ProductClusterEngine
from modules.crawler.multi_source_hunter import MultiSourceHunter
from modules.publisher.telegram_bot import TelegramPublisher

logger = logging.getLogger("HuntRouter")
router = APIRouter(prefix="/api/hunt", tags=["Hunt Deals"])


# --- Pydantic Request Models ---

class TargetCreateRequest(BaseModel):
    name: str = Field(..., description="Tên gợi nhớ nhóm/kênh Telegram")
    identifier: str = Field(..., description="Username (@channel) hoặc link t.me/s/... hoặc chat_id")
    target_type: str = Field(default="CHANNEL", description="CHANNEL, GROUP, hoặc CHAT")
    is_active: bool = Field(default=True)


class FbTargetCreateRequest(BaseModel):
    name: str = Field(..., description="Tên gợi nhớ nhóm Facebook")
    group_url: str = Field(..., description="Link nhóm Facebook (https://www.facebook.com/groups/...) hoặc ID/slug")
    category_name: str = Field(default="Đa ngành", description="Ngành hàng chính của nhóm")
    is_active: bool = Field(default=True)


class ScanHuntRequest(BaseModel):
    mode: str = Field(default="FB_GROUP", description="'FB_GROUP' hoặc 'KEYWORD'")
    facebook_targets: List[str] = Field(default=[], description="Danh sách URL hoặc slug nhóm Facebook cần quét")
    telegram_targets: List[str] = Field(default=[], description="Danh sách identifier nhóm Telegram (tương thích)")
    keyword: Optional[str] = Field(default="", description="Tên sản phẩm nhập trực tiếp (nếu mode là KEYWORD)")
    source_platform: str = Field(default="ALL", description="'TMALL', 'LAZADA_MALL', 'LAZADA_OTHER', hoặc 'ALL'")
    auto_send_telegram: bool = Field(default=False, description="Tự động bắn deal hời vào Telegram")
    min_discount_percent: int = Field(default=5, description="Mức chênh lệch tối thiểu để gửi")
    target_chat_id: Optional[str] = Field(default=None, description="Chat ID đích Telegram (nếu khác mặc định)")


class PostTelegramRequest(BaseModel):
    target_chat_id: Optional[str] = None


# --- 1. Quản lý Mục tiêu Group Facebook ---

@router.get("/fb-targets")
def get_fb_targets():
    """Lấy danh sách các nhóm Facebook cấu hình để quét tin rao bán lấy giá."""
    targets = db.get_facebook_scan_targets()
    if not targets:
        # Khởi tạo các nhóm chợ / pass đồ phổ biến tại Việt Nam
        default_seed = [
            {"name": "Chợ Bàn Phím Cơ & Phụ Kiện Máy Tính Việt Nam", "group_url": "https://www.facebook.com/groups/chophimcovn/", "category_name": "Thiết Bị Điện Tử"},
            {"name": "Góc Pass Đồ Nam & Thời Trang Sneaker Chuẩn", "group_url": "https://www.facebook.com/groups/phoidonamdep/", "category_name": "Thời Trang Nam"},
            {"name": "Hội Chị Em Mê Váy Xinh & Pass Quần Áo Nữ", "group_url": "https://www.facebook.com/groups/passdonudep/", "category_name": "Thời Trang Nữ"},
            {"name": "Hội Review Phụ Kiện Điện Thoại & Cáp Sạc Cũ", "group_url": "https://www.facebook.com/groups/phukiencaploatai/", "category_name": "Thiết Bị Điện Tử"},
            {"name": "Hội Nghiện Nhà & Pass Đồ Gia Dụng Thông Minh", "group_url": "https://www.facebook.com/groups/nghiennhagiadung/", "category_name": "Thiết Bị Điện Gia Dụng"},
        ]
        for s in default_seed:
            db.save_facebook_scan_target(
                name=s["name"],
                group_url=s["group_url"],
                category_name=s["category_name"],
                is_active=1
            )
        targets = db.get_facebook_scan_targets()
    return {"status": "SUCCESS", "targets": targets}


@router.post("/fb-targets")
def create_fb_target(req: FbTargetCreateRequest):
    """Thêm một nhóm Facebook mới vào danh sách theo dõi để quét giá"""
    if not req.name.strip() or not req.group_url.strip():
        raise HTTPException(status_code=400, detail="Tên nhóm và Link nhóm Facebook không được để trống")

    norm_url = FacebookScanner.normalize_group_url(req.group_url)
    slug = FacebookScanner.extract_group_slug_or_id(norm_url)

    target_id = db.save_facebook_scan_target(
        name=req.name.strip(),
        group_url=norm_url,
        group_id=slug,
        category_name=req.category_name.strip() or "Đa ngành",
        is_active=1 if req.is_active else 0
    )
    return {"status": "SUCCESS", "message": "Đã lưu nhóm Facebook mục tiêu", "id": target_id}


@router.delete("/fb-targets/{target_id}")
def delete_fb_target(target_id: int):
    """Xóa nhóm Facebook mục tiêu khỏi danh sách theo dõi"""
    ok = db.delete_facebook_scan_target(target_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Không tìm thấy nhóm Facebook cần xóa")
    return {"status": "SUCCESS", "message": "Đã xóa nhóm Facebook thành công"}


# --- 1.1 Quản lý Mục tiêu Telegram (Duy trì tương thích) ---

@router.get("/targets")
def get_targets():
    """Lấy danh sách các nhóm Telegram cấu hình để quét deal. Tự tạo mẫu nếu trống."""
    targets = db.get_telegram_scan_targets()
    if not targets:
        default_seed = [
            {"name": "Nghiện Săn Deal & Mã Giảm Giá", "identifier": "nghiensandeal", "target_type": "CHANNEL"},
            {"name": "Cộng Đồng Săn Mã Shopee & Lazada", "identifier": "mggshopeevn", "target_type": "CHANNEL"},
            {"name": "Góc Thanh Lý & Trao Đổi Đồ Công Nghệ", "identifier": "deal_cong_nghe", "target_type": "GROUP"},
            {"name": "Hội Săn Hàng Hiệu Giá Tốt", "identifier": "san_hang_hieu_viet", "target_type": "GROUP"},
        ]
        for s in default_seed:
            db.save_telegram_scan_target(s["name"], s["identifier"], s["target_type"], is_active=1)
        targets = db.get_telegram_scan_targets()
    return {"status": "SUCCESS", "targets": targets}


@router.post("/targets")
def create_target(req: TargetCreateRequest):
    """Thêm một nhóm hoặc kênh Telegram mới để theo dõi"""
    if not req.name.strip() or not req.identifier.strip():
        raise HTTPException(status_code=400, detail="Tên và Identifier không được để trống")

    target_id = db.save_telegram_scan_target(
        name=req.name.strip(),
        identifier=req.identifier.strip(),
        target_type=req.target_type,
        is_active=1 if req.is_active else 0
    )
    return {"status": "SUCCESS", "message": "Đã lưu mục tiêu Telegram", "id": target_id}


@router.delete("/targets/{target_id}")
def delete_target(target_id: int):
    """Xóa mục tiêu Telegram"""
    ok = db.delete_telegram_scan_target(target_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Không tìm thấy mục tiêu Telegram cần xóa")
    return {"status": "SUCCESS", "message": "Đã xóa mục tiêu Telegram thành công"}


# --- 2. Bắt đầu Quét & Săn Deal ---

@router.post("/scan")
def execute_hunt_scan(req: ScanHuntRequest):
    """
    Thực hiện quy trình Quét & Săn Deal toàn diện:
    1. Quét tin rao bán từ 1 hoặc nhiều Group Facebook đã chọn HOẶC dùng từ khóa sản phẩm người dùng nhập
    2. Nhận diện và gom nhóm sản phẩm, tính toán Giá trung bình và Giá tham chiếu thị trường
    3. Cào sản phẩm từ nguồn đã chọn (Tmall / LazMall / Lazada Khác / All)
    4. So khớp giá, lọc các sản phẩm có GIÁ THẤP HƠN GIÁ THAM CHIẾU
    5. Lưu kết quả và lịch sử giá
    6. Tự động bắn vào Telegram nếu cấu hình auto_send_telegram=True
    """
    mode = req.mode.upper().strip()
    source_platform = req.source_platform.upper().strip()

    # Nhận diện danh sách nhóm Facebook cần quét
    fb_targets = req.facebook_targets
    if not fb_targets and mode in ["FB_GROUP", "FACEBOOK_GROUP"] and req.telegram_targets:
        fb_targets = req.telegram_targets

    if mode in ["FB_GROUP", "FACEBOOK_GROUP"]:
        input_display = ", ".join(fb_targets)
    elif mode == "TELEGRAM_GROUP":
        input_display = ", ".join(req.telegram_targets)
    else:
        input_display = req.keyword or ""

    if not input_display.strip():
        raise HTTPException(status_code=400, detail="Vui lòng chọn ít nhất 1 nhóm Facebook hoặc nhập tên sản phẩm!")

    # 1. Tạo phiên săn deal mới
    session_id = db.create_hunt_session(
        mode=mode,
        source_platform=source_platform,
        input_query=input_display,
        auto_send_telegram=1 if req.auto_send_telegram else 0,
        min_discount_percent=req.min_discount_percent
    )

    clusters: List[Dict] = []
    hunter = MultiSourceHunter()
    publisher = TelegramPublisher(db=db)

    # 2. Xử lý nguồn dữ liệu đầu vào
    if mode in ["FB_GROUP", "FACEBOOK_GROUP"]:
        # Quét các bài đăng mua bán, pass đồ từ 1 hoặc nhiều nhóm Facebook đã chọn
        fb_scanner = FacebookScanner()
        target_objs = []
        for t in fb_targets:
            norm_url = fb_scanner.normalize_group_url(t)
            slug = fb_scanner.extract_group_slug_or_id(norm_url)
            target_objs.append({"group_url": norm_url, "name": slug})
            db.update_facebook_target_scanned(norm_url)

        raw_posts = fb_scanner.scan_multiple_groups(target_objs, max_posts_per_group=15)

        if raw_posts:
            # Gom nhóm các tin đăng cùng một sản phẩm & tính giá tham chiếu
            clusters = ProductClusterEngine.cluster_messages(raw_posts)
        else:
            # Fallback nếu nhóm chưa có bài mới hoặc chưa đăng nhập Facebook:
            # Tạo cụm tìm kiếm theo tên các nhóm Facebook đã chọn để vẫn săn deal được
            for t in target_objs:
                slug_name = t["name"].replace("_", " ").replace("-", " ")
                clusters.append({
                    "cluster_key": f"fb_{t['name']}",
                    "product_name": slug_name.title(),
                    "category_name": "Facebook Group Deals",
                    "reference_price": 0.0,
                    "avg_price": 0.0,
                    "min_price": 0.0,
                    "max_price": 0.0,
                    "sample_count": 1,
                    "source_samples": [{"raw_text": f"Nhóm Facebook: {t['group_url']}", "price": 0.0, "source": "Facebook"}]
                })
    elif mode == "TELEGRAM_GROUP":
        scanner = TelegramScanner()
        raw_posts = scanner.scan_targets(req.telegram_targets, max_posts_per_target=25)
        for t in req.telegram_targets:
            db.update_telegram_target_scanned(t)

        if raw_posts:
            clusters = ProductClusterEngine.cluster_messages(raw_posts)
        else:
            for t in req.telegram_targets:
                clean_name = scanner.normalize_identifier(t).replace("_", " ")
                clusters.append({
                    "cluster_key": f"tg_{scanner.normalize_identifier(t)}",
                    "product_name": clean_name,
                    "category_name": "Telegram Deals",
                    "reference_price": 0.0,
                    "avg_price": 0.0,
                    "min_price": 0.0,
                    "max_price": 0.0,
                    "sample_count": 1,
                    "source_samples": [{"raw_text": f"Kênh Telegram @{t}", "price": 0.0, "source": "Telegram"}]
                })
    else:
        # Nhập trực tiếp tên bất kỳ sản phẩm nào (bàn phím, quần áo, giày dép, điện thoại, đồ gia dụng...)
        kw = (req.keyword or "").strip()
        cleaned_title = ProductClusterEngine.clean_product_title(kw) or kw
        cluster_key = ProductClusterEngine.generate_cluster_key(cleaned_title)

        clusters = [{
            "cluster_key": cluster_key,
            "product_name": cleaned_title,
            "category_name": "Tìm Kiếm Trực Tiếp",
            "reference_price": 0.0,
            "avg_price": 0.0,
            "min_price": 0.0,
            "max_price": 0.0,
            "sample_count": 1,
            "source_samples": [{"raw_text": kw, "price": 0.0, "source": "User Query"}]
        }]

    # 3. Với mỗi cụm sản phẩm, cào sản phẩm trên nguồn đã chọn (Tmall / LazMall / Lazada / All)
    total_deals_found = 0
    better_deals_count = 0
    all_saved_deals: List[Dict] = []

    for c in clusters:
        c["session_id"] = session_id
        cluster_id = db.save_product_cluster(c)
        c["id"] = cluster_id

        # Tìm kiếm trên sàn với từ khóa của cụm và đối chiếu với giá tham chiếu
        search_kw = c["product_name"]
        deals = hunter.search_deals(
            keyword=search_kw,
            source_platform=source_platform,
            reference_price=c.get("reference_price", 0.0),
            limit=25
        )

        for d in deals:
            d["session_id"] = session_id
            d["cluster_id"] = cluster_id
            deal_id = db.save_hunted_deal(d)
            d["id"] = deal_id
            total_deals_found += 1

            # Ghi nhận lịch sử giá theo thời gian (giữ lại vĩnh viễn)
            db.record_hunt_price_history(
                cluster_key=c["cluster_key"],
                product_name=d["name"],
                platform=d["platform"],
                item_id=d["item_id"],
                price=d["sale_price"],
                reference_price=d["reference_price"]
            )

            # Đếm deal hời (< giá tham chiếu)
            if d.get("is_better_deal"):
                better_deals_count += 1

                # Tự động gửi vào Telegram nếu bật cấu hình
                if req.auto_send_telegram:
                    # Kiểm tra ngưỡng chênh lệch tối thiểu
                    if d.get("savings_percent", 0) >= req.min_discount_percent:
                        sent = publisher.publish_hunted_deal(d, target_chat_id=req.target_chat_id)
                        if sent:
                            db.mark_deal_posted_telegram(deal_id)
                            d["posted_to_telegram"] = True

            all_saved_deals.append(d)

    # 4. Cập nhật thống kê phiên
    db.update_hunt_session(
        session_id=session_id,
        status="COMPLETED",
        total_clusters=len(clusters),
        total_deals_found=total_deals_found,
        better_deals_count=better_deals_count
    )

    # Lấy danh sách deal đã sắp xếp theo thứ tự ưu tiên
    sorted_deals = db.get_deals_by_session(session_id)

    return {
        "status": "SUCCESS",
        "session_id": session_id,
        "summary": {
            "total_clusters": len(clusters),
            "total_deals_found": total_deals_found,
            "better_deals_count": better_deals_count,
            "source_platform": source_platform,
            "mode": mode
        },
        "clusters": clusters,
        "deals": sorted_deals
    }


# --- 3. Quét Lại (Rescan) Giữ Nguyên Lịch Sử Giá ---

@router.post("/rescan/{session_id}")
def rescan_hunt_session(session_id: int):
    """
    Quét lại phiên đã có:
    - Cập nhật giá mới nhất từ các nguồn sàn
    - Giữ nguyên toàn bộ lịch sử giá cũ trong cơ sở dữ liệu
    - Thêm mốc giá mới vào hunt_price_history
    """
    session = db.get_hunt_session_by_id(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Không tìm thấy phiên săn deal")

    clusters = db.get_clusters_by_session(session_id)
    if not clusters:
        raise HTTPException(status_code=400, detail="Phiên không có cụm sản phẩm nào để quét lại")

    hunter = MultiSourceHunter()
    publisher = TelegramPublisher(db=db)
    source_platform = session["source_platform"]
    auto_send = session["auto_send_telegram"]
    min_discount = session["min_discount_percent"]

    total_deals_found = 0
    better_deals_count = 0

    for c in clusters:
        search_kw = c["product_name"]
        deals = hunter.search_deals(
            keyword=search_kw,
            source_platform=source_platform,
            reference_price=c.get("reference_price", 0.0),
            limit=25
        )

        for d in deals:
            d["session_id"] = session_id
            d["cluster_id"] = c["id"]
            deal_id = db.save_hunted_deal(d)
            d["id"] = deal_id
            total_deals_found += 1

            # Ghi nhận điểm giá mới vào lịch sử cũ mà KHÔNG xóa lịch sử trước đó
            db.record_hunt_price_history(
                cluster_key=c["cluster_key"],
                product_name=d["name"],
                platform=d["platform"],
                item_id=d["item_id"],
                price=d["sale_price"],
                reference_price=d["reference_price"]
            )

            if d.get("is_better_deal"):
                better_deals_count += 1
                if auto_send and d.get("savings_percent", 0) >= min_discount:
                    sent = publisher.publish_hunted_deal(d)
                    if sent:
                        db.mark_deal_posted_telegram(deal_id)

    db.update_hunt_session(
        session_id=session_id,
        status="COMPLETED",
        total_clusters=len(clusters),
        total_deals_found=total_deals_found,
        better_deals_count=better_deals_count
    )

    updated_deals = db.get_deals_by_session(session_id)

    return {
        "status": "SUCCESS",
        "message": f"Đã quét lại thành công! Cập nhật {total_deals_found} deal mới và đã lưu vào lịch sử giá.",
        "session_id": session_id,
        "deals": updated_deals,
        "summary": {
            "total_clusters": len(clusters),
            "total_deals_found": total_deals_found,
            "better_deals_count": better_deals_count
        }
    }


# --- 4. Lấy Chi Tiết Phiên & Lịch Sử Giá ---

@router.get("/sessions")
def get_sessions(limit: int = 15):
    """Lấy danh sách các phiên săn deal gần nhất"""
    sessions = db.get_hunt_sessions(limit=limit)
    return {"status": "SUCCESS", "sessions": sessions}


@router.get("/session/{session_id}")
def get_session_detail(session_id: int):
    """Lấy chi tiết phiên: các cụm sản phẩm và toàn bộ deal săn được"""
    session = db.get_hunt_session_by_id(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Không tìm thấy phiên")

    clusters = db.get_clusters_by_session(session_id)
    deals = db.get_deals_by_session(session_id)

    return {
        "status": "SUCCESS",
        "session": session,
        "clusters": clusters,
        "deals": deals
    }


@router.get("/price-history/{cluster_key}")
def get_price_history(cluster_key: str, limit: int = 50):
    """
    Lấy toàn bộ lịch sử biến động giá theo thời gian của một sản phẩm
    (Phục vụ hiển thị biểu đồ & bảng so sánh giá qua các lần quét)
    """
    history = db.get_hunt_price_history_by_cluster(cluster_key, limit=limit)
    return {
        "status": "SUCCESS",
        "cluster_key": cluster_key,
        "count": len(history),
        "history": history
    }


# --- 5. Gửi Deal vào Telegram Thủ Công ---

@router.post("/post-telegram/{deal_id}")
def post_deal_to_telegram(deal_id: int, req: Optional[PostTelegramRequest] = None):
    """Bắn trực tiếp một deal đã săn được vào Group/Channel Telegram"""
    deal = db.get_hunted_deal_by_id(deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Không tìm thấy deal săn được")

    target_chat = req.target_chat_id if req else None
    publisher = TelegramPublisher(db=db)
    success = publisher.publish_hunted_deal(deal, target_chat_id=target_chat)

    if success:
        db.mark_deal_posted_telegram(deal_id)
        return {"status": "SUCCESS", "message": f"Đã gửi deal [{deal['name'][:30]}] thành công tới Telegram!"}
    else:
        raise HTTPException(
            status_code=500,
            detail="Không thể gửi tới Telegram. Vui lòng kiểm tra TELEGRAM_BOT_TOKEN và TELEGRAM_CHAT_ID trong Cài Đặt."
        )


@router.post("/test-telegram")
def test_telegram_connection(req: Optional[PostTelegramRequest] = None):
    """Kiểm tra kết nối và gửi thử thông báo tới Telegram"""
    publisher = TelegramPublisher(db=db)
    test_deal = {
        "name": "Bàn Phím Cơ Không Dây Cao Cấp (Test Kết Nối)",
        "platform": "LAZADA_MALL",
        "seller_name": "Official Flagship Store",
        "reference_price": 850000.0,
        "sale_price": 599000.0,
        "price_diff": 251000.0,
        "savings_percent": 29.5,
        "rating_star": 5.0,
        "historical_sold": 1250,
        "item_url": "https://www.lazada.vn",
        "aff_url": "https://www.lazada.vn",
        "image_url": "https://down-vn.img.susercontent.com/file/vn-11134207-7r98o-lzsm6h8l3mep8d"
    }
    target_chat = req.target_chat_id if req else None
    ok = publisher.publish_hunted_deal(test_deal, target_chat_id=target_chat)
    if ok:
        return {"status": "SUCCESS", "message": "Kết nối Telegram Bot hoạt động hoàn hảo!"}
    else:
        raise HTTPException(status_code=500, detail="Không thể gửi tin nhắn thử nghiệm tới Telegram. Vui lòng kiểm tra lại Token hoặc Chat ID.")
