import os
import sys
import time
import random
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from config.settings import FB_SEEDING_LOG_PATH, DB_PATH
from database.db_manager import DatabaseManager
from modules.affiliate.link_converter import AffiliateLinkConverter

# Logger chuyên biệt cho việc đăng bài Group Facebook
poster_logger = logging.getLogger("FacebookPoster")
poster_logger.setLevel(logging.INFO)
poster_logger.propagate = False

if not poster_logger.handlers:
    try:
        fh = logging.FileHandler(str(FB_SEEDING_LOG_PATH), encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
        poster_logger.addHandler(fh)
    except Exception:
        pass
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    poster_logger.addHandler(sh)


# Trạng thái tiến trình đăng bài dần toàn cục
gradual_posting_state = {
    "is_running": False,
    "total_target": 0,
    "completed": 0,
    "current_group": "",
    "current_deal": "",
    "next_post_time": None,
    "status": "IDLE",
    "last_result": None,
    "history": []
}


class FacebookGroupPoster:
    """
    Module tự động hóa đăng bài viết (Feed Post) vào các hội nhóm Facebook đã tham gia (APPROVED).
    - Khớp deal thông minh theo danh mục và từ khóa tên nhóm (Thời trang nam, nữ, công nghệ, săn deal).
    - Soạn bài tự nhiên dạng review/pass đồ/chia sẻ deal sâu kèm link Affiliate rút gọn / Anti-ban.
    - Cơ chế đăng bài dần dần (Gradual Posting) có khoảng nghỉ an toàn chống spam của Facebook.
    """

    def __init__(self, db: Optional[DatabaseManager] = None):
        self.db = db or DatabaseManager()
        self.link_converter = AffiliateLinkConverter()

    def find_best_deal_for_group(self, group: Dict, strict: bool = True) -> Optional[Dict]:
        """
        Tìm deal phù hợp nhất với nhóm dựa trên Category và từ khóa trong tên nhóm.
        QUY TẮC NGHIÊM NGẶT: Phải chọn đúng sản phẩm thuộc loại ngành hàng của nhóm.
        Tuyệt đối không lấy râu ông nọ cắm cằm bà kia (VD: không lấy nồi niêu/đồ nữ đăng vào nhóm thời trang nam).
        """
        group_name = (group.get("name") or "").lower()
        group_cat = group.get("category_name") or "Cộng Đồng Chung"

        with self.db.get_connection() as conn:
            # 1. Nhóm Thiết Bị Điện Tử / Công Nghệ / iPhone / Phụ Kiện
            if group_cat in ["Thiết Bị Điện Tử", "Điện Thoại & Phụ Kiện"] or any(k in group_name for k in ["iphone", "apple", "công nghệ", "điện tử", "tai nghe", "điện thoại", "android", "linh kiện"]):
                if any(k in group_name for k in ["iphone", "apple"]):
                    row = conn.execute("""
                        SELECT * FROM deals 
                        WHERE category_name = 'Thiết Bị Điện Tử' 
                          AND (name LIKE '%iPhone%' OR name LIKE '%Ốp Lưng%' OR name LIKE '%Kính Cường Lực%') 
                          AND is_stale = 0 
                        ORDER BY deal_score DESC LIMIT 1
                    """).fetchone()
                    if row:
                        return dict(row)
                
                rows = conn.execute("""
                    SELECT * FROM deals 
                    WHERE category_name = 'Thiết Bị Điện Tử' AND is_stale = 0 
                    ORDER BY deal_score DESC LIMIT 5
                """).fetchall()
                if rows:
                    return dict(random.choice(rows))
                return None  # Không có thì bỏ qua, tuyệt đối không lấy ngành khác

            # 2. Nhóm Thời Trang Nam
            elif group_cat == "Thời Trang Nam" or any(k in group_name for k in ["đồ nam", "quần nam", "áo nam", "thời trang nam", "owen", "aristino", "nam béo", "phối đồ nam"]):
                if any(k in group_name for k in ["cạo râu", "dao cạo"]):
                    row = conn.execute("""
                        SELECT * FROM deals 
                        WHERE category_name = 'Thời Trang Nam' AND name LIKE '%cạo râu%' AND is_stale = 0 
                        ORDER BY deal_score DESC LIMIT 1
                    """).fetchone()
                    if row:
                        return dict(row)

                rows = conn.execute("""
                    SELECT * FROM deals 
                    WHERE category_name = 'Thời Trang Nam' AND is_stale = 0 
                    ORDER BY deal_score DESC LIMIT 5
                """).fetchall()
                if rows:
                    return dict(random.choice(rows))
                return None  # Tuyệt đối không lấy ngành khác

            # 3. Nhóm Thời Trang Nữ & Làm Đẹp
            elif group_cat == "Thời Trang Nữ" or any(k in group_name for k in ["nữ", "chị em", "làm đẹp", "mặc đẹp", "nấm lùn", "1m50", "genz", "tips phối đồ"]):
                rows = conn.execute("""
                    SELECT * FROM deals 
                    WHERE category_name = 'Thời Trang Nữ' AND is_stale = 0 
                    ORDER BY deal_score DESC LIMIT 5
                """).fetchall()
                if rows:
                    return dict(random.choice(rows))
                return None  # Tuyệt đối không lấy ngành khác

            # 4. Nhóm Nhà Cửa & Đời Sống / Gia Dụng
            elif group_cat in ["Nhà Cửa & Đời Sống", "Gia Dụng"] or any(k in group_name for k in ["gia dụng", "nhà cửa", "nội thất", "bếp", "nồi"]):
                rows = conn.execute("""
                    SELECT * FROM deals 
                    WHERE category_name = 'Nhà Cửa & Đời Sống' AND is_stale = 0 
                    ORDER BY deal_score DESC LIMIT 5
                """).fetchall()
                if rows:
                    return dict(random.choice(rows))
                return None  # Tuyệt đối không lấy ngành khác

            # 5. Nhóm Săn Deal Tổng Hợp / Cộng Đồng Chung / Chợ
            elif group_cat in ["Săn Deal Tổng Hợp", "Cộng Đồng Chung"] or any(k in group_name for k in ["săn deal", "voucher", "khuyến mãi", "khuyến mại", "giảm giá", "chợ", "rải link"]):
                rows = conn.execute("""
                    SELECT * FROM deals 
                    WHERE category_name = 'Săn Deal Tổng Hợp' AND is_stale = 0 
                    ORDER BY deal_score DESC LIMIT 10
                """).fetchall()
                if rows:
                    return dict(random.choice(rows))
                return None

            # 6. Danh mục tùy biến khác: Tìm đúng category_name
            else:
                rows = conn.execute("""
                    SELECT * FROM deals 
                    WHERE category_name = ? AND is_stale = 0 
                    ORDER BY deal_score DESC LIMIT 5
                """, (group_cat,)).fetchall()
                if rows:
                    return dict(random.choice(rows))
                
                # Chỉ khi strict=False mới lấy ngẫu nhiên deal bất kỳ
                if not strict:
                    all_deals = conn.execute("SELECT * FROM deals WHERE is_stale = 0 ORDER BY deal_score DESC LIMIT 10").fetchall()
                    if all_deals:
                        return dict(random.choice(all_deals))

        return None

    def generate_post_content(self, deal: Dict, group: Dict) -> str:
        """
        Sinh văn phong bài viết phù hợp với đặc thù nhóm:
        - Nhóm thời trang nam: 'Góc phối đồ / pass deal ngon cho anh em'
        - Nhóm thời trang nữ / làm đẹp: 'Góc làm đẹp / review đồ xinh cho chị em'
        - Nhóm công nghệ: 'Chia sẻ deal phụ kiện/thiết bị chính hãng sale sốc'
        - Nhóm săn sale: 'Flash sale Shopee hời nhất hôm nay'
        """
        group_name = group.get("name", "")
        group_cat = group.get("category_name", "Cộng Đồng Chung")
        item_id = str(deal.get("item_id", ""))
        item_name = deal.get("name", "Sản phẩm Shopee")
        price_sale = int(deal.get("price_sale", 0))
        price_orig = int(deal.get("price_original", 0))
        discount = deal.get("discount_percent", 0)
        rating = deal.get("rating_star", 5.0)
        sold = deal.get("historical_sold", 0)

        # Tạo link affiliate với Sub-ID tracking riêng cho nhóm Facebook này
        channel = "fb_group"
        sub_id = f"grp_{group.get('group_id', '')[:8]}"
        direct_aff = deal.get("aff_url") or deal.get("item_url", "")
        
        # Link chuyển hướng Anti-Ban hoặc link affiliate trực tiếp
        tracking_url = self.link_converter.get_bridge_url(
            item_id, channel=channel, sub_id=sub_id, direct_aff_url=direct_aff
        )
        if not tracking_url or tracking_url == "#":
            tracking_url = direct_aff

        if group_cat == "Thời Trang Nam":
            templates = [
                f"Góc phối đồ & pass deal hời cho anh em nhé 👇\n\n"
                f"Hôm nay lướt Shopee Mall thấy em '{item_name}' này đang sale sốc quá. "
                f"Giá gốc {price_orig:,}đ đang Flash Sale còn có {price_sale:,}đ (-{discount}%).\n\n"
                f"• Hơn {sold:,} người đã mua, đánh giá {rating}⭐ cực uy tín\n"
                f"• Hàng Mall chính hãng, chất lượng chuẩn chỉnh\n\n"
                f"Anh em nào đang cần đồ phối đi chơi / đi làm thì múc sớm kẻo hết size nhé:\n"
                f"👉 Link săn sale Shopee Mall: {tracking_url}\n\n"
                f"#phoidonam #thoitrangnam #shopeemall #sansale #dealhot",

                f"[CHIA SẺ DEAL NGON CHO ANH EM] 🔥\n\n"
                f"Vừa check được mã sale em '{item_name}' này trên Shopee rẻ hơn ngày thường nhiều:\n"
                f"• Giá sale hôm nay: {price_sale:,}đ (Giá gốc: {price_orig:,}đ)\n"
                f"• Đã bán: {sold:,} lượt | Đánh giá: {rating}⭐\n\n"
                f"Hàng shop Mall chuẩn chỉ, có mã Freeship 0Đ áp kèm lúc thanh toán nha mn.\n"
                f"🔗 Link chốt deal cho bác nào cần: {tracking_url}\n\n"
                f"#thoitrangnam #donam #dealngon #shopee"
            ]
        elif group_cat == "Thời Trang Nữ":
            templates = [
                f"Góc làm đẹp & phối đồ xinh cho chị em mình nè 🥰\n\n"
                f"Em '{item_name}' này đang sale chạm đáy trên Shopee Mall luôn mn ơi!\n"
                f"• Giá gốc: {price_orig:,}đ ➡️ Flash Sale còn: {price_sale:,}đ (-{discount}%)\n"
                f"• Hơn {sold:,} lượt mua, feedback {rating}⭐ cực nhiều ảnh thật\n\n"
                f"Chị em tranh thủ gom sớm kẻo hết lượt sale nhé, link chính hãng đây ạ:\n"
                f"👉 Link mua ưu đãi Shopee: {tracking_url}\n\n"
                f"#macdep #phoido #shopeesale #lamdep #reviewcungchiem",

                f"Mách nhỏ chị em deal cực hời hôm nay nha 💕\n\n"
                f"Em '{item_name}' này dùng siêu thích mà nay đang có mã giảm sâu:\n"
                f"Giá chỉ {price_sale:,}đ (tiết kiệm được {price_orig - price_sale:,}đ so với giá gốc).\n"
                f"Mn nhớ áp thêm voucher giảm giá và freeship tại giỏ hàng nha!\n\n"
                f"🔗 Link shop Mall chính hãng: {tracking_url}\n\n"
                f"#shopeehaul #doxinh #tipsphoido #hangchinhhang"
            ]
        elif group_cat == "Thiết Bị Điện Tử":
            templates = [
                f"Góc Review & Chia Sẻ Đồ Công Nghệ / Phụ Kiện Giá Hời 📱⚡\n\n"
                f"Chia sẻ anh em con '{item_name}' này dùng cực ngon mà đang sale sâu:\n"
                f"• Giá sale chỉ: {price_sale:,}đ (Giá niêm yết: {price_orig:,}đ - Giảm {discount}%)\n"
                f"• Đã bán hơn {sold:,} chiếc, đánh giá {rating}⭐ uy tín\n"
                f"• Hàng chuẩn Mall chính hãng, độ hoàn thiện cao, dùng rất bền\n\n"
                f"Bác nào đang tìm phụ kiện ngon bổ rẻ thì vào tham khảo nhé:\n"
                f"👉 Link săn sale Shopee Mall: {tracking_url}\n\n"
                f"#congnghe #phukien #iphone #shopeedeal #reviewcotam"
            ]
        else: # Săn Deal Tổng Hợp / Cộng Đồng Chung
            templates = [
                f"🔥 [TỔNG HỢP DEAL FLASH SALE SHOPEE HÔM NAY] 🔥\n\n"
                f"Vừa săn được em '{item_name}' này giá sale cực sốc mn ơi:\n"
                f"• Giá sale hôm nay: {price_sale:,}đ (Gốc: {price_orig:,}đ - Giảm {discount}%)\n"
                f"• Lượt bán: {sold:,} | Đánh giá: {rating}⭐\n"
                f"• Áp được mã Freeship 0Đ và voucher toàn sàn tại bước thanh toán!\n\n"
                f"Mọi người bấm link bên dưới để chốt deal sớm kẻo hết suất nhé:\n"
                f"👉 Link săn sale chính hãng: {tracking_url}\n\n"
                f"#sansale #shopeevn #voucher #deal1k #flashsale"
            ]

        return random.choice(templates)

    def post_to_single_group(self, group_id: str, deal_id: Optional[str] = None, page=None, auto_close_browser=True, custom_content: Optional[str] = None) -> Dict:
        """
        Thực hiện đăng bài viết thực tế vào tường một nhóm Facebook bằng Playwright.
        Hỗ trợ cả bài đăng deal lẻ theo ngành hoặc bài tổng hợp khuyến mại / mã voucher tùy biến.
        """
        start_time = datetime.now()
        with self.db.get_connection() as conn:
            g_row = conn.execute("SELECT * FROM fb_groups WHERE group_id = ?", (group_id,)).fetchone()
            if not g_row:
                return {"status": "ERROR", "message": f"Không tìm thấy nhóm #{group_id} trong CSDL!"}
            group = dict(g_row)

            if deal_id:
                d_row = conn.execute("SELECT * FROM deals WHERE item_id = ?", (deal_id,)).fetchone()
                deal = dict(d_row) if d_row else None
            elif not custom_content:
                deal = self.find_best_deal_for_group(group)
            else:
                deal = None

        if not custom_content and not deal:
            group_name = group.get("name", group_id)
            group_cat = group.get("category_name", "Chưa phân loại")
            poster_logger.warning(f"⚠️ [BỎ QUA NHÓM {group_name}]: Kho chưa có deal nào thuộc đúng ngành '{group_cat}'. Hệ thống từ chối đăng sản phẩm sai ngành!")
            return {
                "status": "SKIPPED",
                "group_id": group_id,
                "group_name": group_name,
                "category_name": group_cat,
                "message": f"Đã bỏ qua nhóm [{group_name}] vì kho chưa có deal thuộc ngành [{group_cat}]. Hệ thống kiên quyết không đăng bài sai ngành hàng!"
            }

        post_content = custom_content if custom_content else self.generate_post_content(deal, group)
        group_name = group.get("name", group_id)
        group_url = group.get("url") or f"https://www.facebook.com/groups/{group_id}/"

        poster_logger.info(f"\n📝 [CHUẨN BỊ ĐĂNG BÀI]:")
        poster_logger.info(f"   👥 Nhóm: [{group_name}] (ID: {group_id}) | Ngành: {group.get('category_name')}")
        poster_logger.info(f"   🛍️ Deal: [{deal.get('name')[:35]}...] | Giá: {int(deal.get('price_sale', 0)):,}đ")
        poster_logger.info(f"   🌐 URL Nhóm: {group_url}")

        # Khởi tạo Playwright nếu chưa truyền page vào
        created_browser = False
        browser = None
        context = None
        playwright_instance = None

        if page is None:
            try:
                from playwright.sync_api import sync_playwright
                playwright_instance = sync_playwright().start()
                fb_cookie = os.getenv("FB_COOKIE", "").strip()
                fb_profile = os.getenv("FB_CHROME_PROFILE", "").strip()

                if fb_profile and os.path.exists(fb_profile):
                    context = playwright_instance.chromium.launch_persistent_context(
                        user_data_dir=fb_profile,
                        headless=True,
                        args=["--disable-blink-features=AutomationControlled"]
                    )
                else:
                    browser = playwright_instance.chromium.launch(
                        headless=True,
                        args=["--disable-blink-features=AutomationControlled"]
                    )
                    context = browser.new_context(
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                        viewport={"width": 1280, "height": 900}
                    )
                    if fb_cookie:
                        cookies = []
                        for item in fb_cookie.split(";"):
                            if "=" in item:
                                k, v = item.strip().split("=", 1)
                                cookies.append({"name": k, "value": v, "domain": ".facebook.com", "path": "/"})
                        if cookies:
                            context.add_cookies(cookies)

                page = context.new_page()
                created_browser = True
            except Exception as e:
                poster_logger.error(f"❌ [LỖI KHỞI ĐỘNG PLAYWRIGHT]: {e}")
                return {"status": "ERROR", "message": f"Lỗi khởi động trình duyệt Playwright: {e}"}

        try:
            poster_logger.info(f"🌐 [PLAYWRIGHT]: Đang truy cập bảng tin nhóm: {group_url}...")
            page.goto(group_url, timeout=40000, wait_until="domcontentloaded")
            page.wait_for_timeout(3500)

            # 1. Tìm nút bấm kích hoạt khung tạo bài viết
            trigger_selectors = [
                "div[role='button']:has-text('Bạn viết gì đi')",
                "div[role='button']:has-text('Bạn đang viết gì thế')",
                "div[role='button']:has-text('Write something')",
                "div[role='button']:has-text('Tạo bài viết')",
                "div[role='button']:has-text('What\'s on your mind')",
                "div[aria-label*='Tạo bài viết']",
                "span:has-text('Bạn viết gì đi')",
                "span:has-text('Bạn đang viết gì thế')",
                "span:has-text('Write something')"
            ]

            trigger = None
            for sel in trigger_selectors:
                loc = page.locator(sel).first
                if loc.is_visible(timeout=1500):
                    trigger = loc
                    poster_logger.info(f"   🎯 Đã tìm thấy nút tạo bài viết: {sel}")
                    break

            if not trigger:
                poster_logger.warning(f"⚠️ Không tìm thấy khung tạo bài viết trong nhóm [{group_name}]. Có thể nhóm cấm đăng bài hoặc yêu cầu quyền Admin.")
                return {
                    "status": "FAILED",
                    "group_id": group_id,
                    "group_name": group_name,
                    "message": "Không tìm thấy nút tạo bài viết (nhóm hạn chế quyền đăng thành viên)."
                }

            # Bấm mở popup Tạo bài viết
            trigger.click()
            page.wait_for_timeout(2500)

            # 2. Tìm popup hộp thoại soạn bài
            dialog = page.locator("div[role='dialog']").first
            if not dialog.is_visible(timeout=4000):
                poster_logger.warning("Popup soạn bài không mở ra sau khi bấm.")
                return {"status": "FAILED", "group_id": group_id, "group_name": group_name, "message": "Popup soạn bài không mở ra."}

            # 3. Tìm ô nhập văn bản và gõ nội dung bài viết
            textbox = dialog.locator("div[role='textbox'], div[contenteditable='true']").first
            if not textbox.is_visible(timeout=2000):
                poster_logger.warning("Không tìm thấy ô nhập nội dung bài viết.")
                return {"status": "FAILED", "group_id": group_id, "group_name": group_name, "message": "Không tìm thấy ô nhập văn bản."}

            textbox.click()
            page.wait_for_timeout(500)

            # Gõ nội dung bài viết an toàn qua keyboard insert_text (hỗ trợ Unicode tiếng Việt hoàn hảo)
            page.keyboard.insert_text(post_content)
            page.wait_for_timeout(1500)
            poster_logger.info("   ✍️ Đã điền xong nội dung bài viết kèm link Affiliate chuẩn.")

            # 4. Tìm và bấm nút 'Đăng' / 'Post'
            submit_selectors = [
                "div[aria-label='Đăng']",
                "div[aria-label='Post']",
                "div[role='button']:has-text('Đăng')",
                "div[role='button']:has-text('Post')"
            ]

            submit_btn = None
            for s in submit_selectors:
                btn = dialog.locator(s).first
                if btn.is_visible(timeout=1000):
                    submit_btn = btn
                    break

            if not submit_btn:
                poster_logger.warning("Không tìm thấy nút 'Đăng' trong hộp thoại.")
                return {"status": "FAILED", "group_id": group_id, "group_name": group_name, "message": "Không tìm thấy nút Đăng."}

            # Đợi nút Đăng được kích hoạt (hết disable)
            for _ in range(10):
                is_disabled = submit_btn.get_attribute("aria-disabled")
                if is_disabled != "true":
                    break
                page.wait_for_timeout(500)

            poster_logger.info("   🚀 Đang bấm nút 'Đăng' bài viết...")
            submit_btn.click()
            page.wait_for_timeout(4000)

            # 5. Kiểm tra kết quả sau khi đăng
            # Kiểm tra xem có thông báo chờ phê duyệt hay không
            body_text = page.locator("body").inner_text().lower()
            is_pending = "chờ phê duyệt" in body_text or "pending approval" in body_text or "đã được gửi" in body_text

            post_status = "PENDING_APPROVAL" if is_pending else "SUCCESS"
            status_desc = "Đã gửi bài (Chờ Admin duyệt)" if is_pending else "Đã đăng công khai thành công"

            poster_logger.info(f"   ✅ [KẾT QUẢ]: {status_desc} trên nhóm [{group_name}]!")

            # 6. Ghi nhận lịch sử bài đăng vào CSDL
            target_post_url = group_url
            snippet = post_content[:180] + "..." if len(post_content) > 180 else post_content
            self.db.log_posted_item(
                post_type="POST",
                group_name=group_name,
                group_url=group_url,
                target_url=target_post_url,
                item_id=str(deal.get("item_id", "")),
                item_name=deal.get("name", ""),
                content_snippet=snippet,
                status=post_status
            )

            # Cập nhật thời gian đăng bài cuối cho nhóm để xoay tua công bằng
            with self.db.get_connection() as conn:
                conn.execute(
                    "UPDATE fb_groups SET last_posted_at = CURRENT_TIMESTAMP WHERE group_id = ?",
                    (group_id,)
                )
                conn.commit()

            return {
                "status": "SUCCESS",
                "post_status": post_status,
                "group_id": group_id,
                "group_name": group_name,
                "deal_id": deal.get("item_id"),
                "deal_name": deal.get("name"),
                "post_content": post_content,
                "target_url": target_post_url,
                "message": f"{status_desc} vào nhóm [{group_name}]!"
            }

        except Exception as e:
            poster_logger.error(f"❌ [LỖI TRONG KHI ĐĂNG BÀI NHÓM {group_name}]: {e}")
            return {"status": "ERROR", "group_id": group_id, "group_name": group_name, "message": str(e)}

        finally:
            if created_browser and auto_close_browser:
                try:
                    if browser:
                        browser.close()
                    elif context:
                        context.close()
                    if playwright_instance:
                        playwright_instance.stop()
                except Exception:
                    pass

    def run_gradual_posting(self, max_groups: int = 3, min_delay_seconds: int = 180, max_delay_seconds: int = 360) -> List[Dict]:
        """
        Chu trình đăng bài dần dần vào các nhóm Facebook đã tham gia (APPROVED).
        - Ưu tiên nhóm chưa từng đăng bài hoặc đã đăng từ lâu nhất (last_posted_at ASC NULLS FIRST).
        - Nghỉ ngẫu nhiên giữa các bài đăng để đảm bảo an toàn 100% cho tài khoản Facebook.
        """
        global gradual_posting_state
        gradual_posting_state["is_running"] = True
        gradual_posting_state["total_target"] = max_groups
        gradual_posting_state["completed"] = 0
        gradual_posting_state["status"] = "RUNNING"

        poster_logger.info("\n" + "=" * 80)
        poster_logger.info(f"🚀 BẮT ĐẦU CHU TRÌNH ĐĂNG BÀI DẦN VÀO {max_groups} NHÓM FACEBOOK ĐÃ THAM GIA")
        poster_logger.info(f"⏰ Thời gian: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        poster_logger.info(f"⏳ Khoảng nghỉ an toàn giữa các bài: {min_delay_seconds}s - {max_delay_seconds}s")
        poster_logger.info("=" * 80)

        # Lấy danh sách nhóm APPROVED ưu tiên chưa đăng bao giờ
        with self.db.get_connection() as conn:
            groups = conn.execute("""
                SELECT * FROM fb_groups 
                WHERE status = 'APPROVED'
                ORDER BY 
                    CASE WHEN last_posted_at IS NULL THEN 0 ELSE 1 END,
                    last_posted_at ASC,
                    members_count DESC
                LIMIT ?
            """, (max_groups,)).fetchall()

        if not groups:
            poster_logger.warning("Không có nhóm nào ở trạng thái APPROVED trong CSDL!")
            gradual_posting_state["is_running"] = False
            gradual_posting_state["status"] = "NO_GROUPS"
            return []

        results = []
        for idx, g_row in enumerate(groups, 1):
            group = dict(g_row)
            group_id = str(group["group_id"])
            group_name = group.get("name", group_id)

            gradual_posting_state["current_group"] = group_name
            poster_logger.info(f"\n--- Tiến trình [{idx}/{len(groups)}]: Đăng bài vào nhóm [{group_name}] ---")

            res = self.post_to_single_group(group_id)
            results.append(res)
            gradual_posting_state["completed"] += 1
            gradual_posting_state["last_result"] = res
            gradual_posting_state["history"].append(res)

            # Nếu còn nhóm tiếp theo, áp dụng thời gian nghỉ an toàn (Human-like delay)
            if idx < len(groups):
                delay = random.randint(min_delay_seconds, max_delay_seconds)
                next_time = datetime.fromtimestamp(time.time() + delay).strftime("%H:%M:%S")
                gradual_posting_state["next_post_time"] = next_time
                poster_logger.info(f"⏳ [NGHỈ AN TOÀN]: Nghỉ {delay} giây chống spam Facebook. Nhóm tiếp theo sẽ đăng lúc {next_time}...")
                
                # Sleep từng đoạn ngắn 5s để có thể nhận tín hiệu dừng nếu cần
                slept = 0
                while slept < delay and gradual_posting_state["is_running"]:
                    time.sleep(min(5, delay - slept))
                    slept += 5

            if not gradual_posting_state["is_running"]:
                poster_logger.info("Dừng chu trình đăng bài dần theo yêu cầu.")
                break

        gradual_posting_state["is_running"] = False
        gradual_posting_state["status"] = "FINISHED"
        poster_logger.info(f"\n🎉 Hoàn thành chu trình đăng bài dần: Đã xử lý {len(results)} nhóm.")
        return results
