import os
import sys
import time
import random
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from config.settings import FB_SEEDING_LOG_PATH, DB_PATH
from config.category_mapping import CategoryMatcher
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
    "current_account": "",
    "next_post_time": None,
    "remaining_delay": 0,
    "delay_seconds": 0,
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
        self.matcher = CategoryMatcher()
        self._last_composed_meta: Dict = {}
        from modules.outreach.fb_account_manager import FacebookAccountManager
        self.account_mgr = FacebookAccountManager(self.db)

    def find_best_deal_for_group(self, group: Dict, strict: bool = True) -> Optional[Dict]:
        """
        Tìm deal phù hợp nhất với nhóm dựa trên CategoryMatcher config-driven.
        QUY TẮC NGHIÊM NGẶT: Phải chọn đúng sản phẩm thuộc loại ngành hàng của nhóm.
        Tuyệt đối không lấy râu ông nọ cắm cằm bà kia.
        """
        group_name = group.get("name") or ""
        group_cat = group.get("category_name") or "Cộng Đồng Chung"

        # Khớp category bằng config-driven matcher
        match_result = self.matcher.match_group(group_cat=group_cat, group_name=group_name)
        category_condition = self.matcher.build_deal_query_conditions(match_result)
        sub_name_filter = self.matcher.build_sub_category_name_filter(match_result)

        with self.db.get_connection() as conn:
            # 1. Nếu có sub-category (VD: nhóm iPhone → ưu tiên deal iPhone trước)
            if sub_name_filter:
                row = conn.execute(f"""
                    SELECT * FROM deals 
                    WHERE ({category_condition}) AND ({sub_name_filter})
                      AND is_stale = 0 
                    ORDER BY deal_score DESC LIMIT 1
                """).fetchone()
                if row:
                    return dict(row)

            # 2. Query theo category chính
            if match_result["matched_by"] != "general":
                rows = conn.execute(f"""
                    SELECT * FROM deals 
                    WHERE ({category_condition}) AND is_stale = 0 
                    ORDER BY deal_score DESC LIMIT 5
                """).fetchall()
                if rows:
                    return dict(random.choice(rows))
                return None  # Strict: không lấy ngành khác

            # 3. General / Săn Deal Tổng Hợp → lấy deal score cao nhất
            rows = conn.execute("""
                SELECT * FROM deals 
                WHERE is_stale = 0
                ORDER BY deal_score DESC LIMIT 10
            """).fetchall()
            if rows:
                return dict(random.choice(rows))

            # 4. Chỉ khi strict=False mới lấy ngẫu nhiên deal bất kỳ
            if not strict:
                all_deals = conn.execute("SELECT * FROM deals WHERE is_stale = 0 ORDER BY deal_score DESC LIMIT 10").fetchall()
                if all_deals:
                    return dict(random.choice(all_deals))

        return None

    def generate_post_content(self, deal: Dict, group: Dict) -> str:
        """
        Sinh văn phong bài viết phù hợp với đặc thù nhóm qua PostComposer:
        - Xoay vòng template (Template Rotation)
        - Ngôn từ vùng miền và cấu trúc câu ngẫu nhiên (Linguistic Permutator)
        - Tránh đăng 2 bài giống nhau > 80% (Content Deduplicator)
        """
        from modules.outreach.post_composer import PostComposer
        composer = PostComposer(self.db)
        res = composer.compose_post_for_group(deal, group)
        self._last_composed_meta = res
        return res["content"]

    def post_to_single_group(
        self,
        group_id: str,
        deal_id: Optional[str] = None,
        page=None,
        auto_close_browser=True,
        custom_content: Optional[str] = None,
        account: Optional[Dict] = None
    ) -> Dict:
        """
        Thực hiện đăng bài viết thực tế vào tường một nhóm Facebook bằng Playwright.
        Hỗ trợ cả bài đăng deal lẻ theo ngành hoặc bài tổng hợp khuyến mại / mã voucher tùy biến.
        Hỗ trợ luân phiên đa tài khoản Facebook (Multi-Account Rotation).
        """
        start_time = datetime.now()
        with self.db.get_connection() as conn:
            g_row = conn.execute("SELECT * FROM fb_groups WHERE group_id = ?", (group_id,)).fetchone()
            if not g_row:
                return {"status": "ERROR", "message": f"Không tìm thấy nhóm #{group_id} trong CSDL!"}
            group = dict(g_row)

            # Kiểm tra xem nhóm có bị hạn chế đăng bài (do bị Admin từ chối liên tiếp) không
            if group.get("posting_restricted") == 1:
                group_name = group.get("name", group_id)
                poster_logger.warning(f"🚫 [BỎ QUA NHÓM {group_name}]: Nhóm bị hạn chế đăng bài (posting_restricted=1)!")
                return {
                    "status": "RESTRICTED",
                    "group_id": group_id,
                    "group_name": group_name,
                    "message": f"Nhóm [{group_name}] bị hạn chế đăng do bị Admin từ chối bài."
                }

            # Kiểm tra xem nhóm có phải Group Ma không
            if (group.get("health_score") is not None and group.get("health_score") < 30) or group.get("health_verdict") == "GHOST":
                group_name = group.get("name", group_id)
                poster_logger.warning(f"🚫 [BỎ QUA GROUP MA {group_name}]: Điểm sức khỏe quá thấp ({group.get('health_score')}/100)!")
                return {
                    "status": "SKIPPED_GHOST",
                    "group_id": group_id,
                    "group_name": group_name,
                    "message": f"Nhóm [{group_name}] là group ma, điểm sức khỏe {group.get('health_score')}."
                }

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

        # Xác định tài khoản Facebook sử dụng cho lượt đăng này
        if account is None:
            try:
                from modules.workflow.account_router import AccountRouter
                router = AccountRouter(self.db)
                chosen_acc, r_status, r_msg = router.select_best_account_for_group(group_id, task_type="POST")
                if chosen_acc:
                    account = chosen_acc
                else:
                    poster_logger.warning(f"⚠️ [ACCOUNT ROUTER]: {r_msg}")
                    if r_status in ["ALL_IN_COOLDOWN", "LIMIT_REACHED", "NO_ACTIVE_ACCOUNTS"]:
                        return {
                            "status": "COOLDOWN_ACTIVE" if r_status == "ALL_IN_COOLDOWN" else "FAILED",
                            "group_id": group_id,
                            "group_name": group.get("name", group_id),
                            "message": r_msg
                        }
            except Exception as router_err:
                poster_logger.warning(f"⚠️ Lỗi khởi tạo AccountRouter: {router_err}")
                account, _ = self.account_mgr.get_next_account(task_type="POST")

        if account:
            fb_cookie = account.get("cookie", "").strip()
            fb_profile = account.get("profile_path", "").strip()
            acc_name = account.get("name", "Nick FB")
            acc_id = account.get("id")
        else:
            fb_cookie = os.getenv("FB_COOKIE", "").strip()
            fb_profile = os.getenv("FB_CHROME_PROFILE", "").strip()
            acc_name = "Nick Mặc Định (.env)"
            acc_id = None

        poster_logger.info(f"\n📝 [CHUẨN BỊ ĐĂNG BÀI]:")
        poster_logger.info(f"   👤 Tài khoản FB: [{acc_name}] (Luân phiên)")
        poster_logger.info(f"   👥 Nhóm: [{group_name}] (ID: {group_id}) | Ngành: {group.get('category_name')}")
        if deal:
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
                return {"status": "ERROR", "message": f"Lỗi khởi động trình duyệt Playwright: {e}", "account_name": acc_name}

        try:
            poster_logger.info(f"🌐 [PLAYWRIGHT]: Đang truy cập bảng tin nhóm: {group_url}...")
            page.goto(group_url, timeout=40000, wait_until="domcontentloaded")
            page.wait_for_timeout(3500)

            # 1. Tìm nút bấm kích hoạt khung tạo bài viết
            trigger_selectors = [
                "div[role='button']:has-text('Bạn viết gì đi')",
                "div[role='button']:has-text('Bạn đang viết gì thế')",
                "div[role='button']:has-text('Bạn đang nghĩ gì')",
                "div[role='button']:has-text('Bạn đang nghĩ gì thế')",
                "div[role='button']:has-text('Write something')",
                "div[role='button']:has-text('Tạo bài viết')",
                "div[role='button']:has-text('Tạo bài viết công khai')",
                "div[role='button']:has-text('on your mind')",
                "div[aria-label*='Tạo bài viết']",
                "div[aria-label*='Bạn đang nghĩ gì']",
                "div[aria-label*='Bạn viết gì đi']",
                "div[aria-label*='Write something']",
                "div[aria-label*='on your mind']",
                "span:has-text('Bạn viết gì đi')",
                "span:has-text('Bạn đang viết gì thế')",
                "span:has-text('Bạn đang nghĩ gì')",
                "span:has-text('Write something')",
                "span:has-text('on your mind')"
            ]

            trigger = None
            for sel in trigger_selectors:
                try:
                    loc = page.locator(sel).first
                    if loc.is_visible(timeout=1500):
                        trigger = loc
                        poster_logger.info(f"   🎯 Đã tìm thấy nút tạo bài viết: {sel}")
                        break
                except Exception as sel_err:
                    poster_logger.debug(f"Bỏ qua selector '{sel}' do lỗi cú pháp/tìm kiếm: {sel_err}")

            if not trigger:
                poster_logger.warning(f"⚠️ Không tìm thấy khung tạo bài viết trong nhóm [{group_name}]. Có thể nhóm cấm đăng bài hoặc yêu cầu quyền Admin.")
                return {
                    "status": "FAILED",
                    "group_id": group_id,
                    "group_name": group_name,
                    "message": "Không tìm thấy nút tạo bài viết (nhóm hạn chế quyền đăng thành viên hoặc cần phê duyệt)."
                }

            # Bấm mở popup Tạo bài viết
            trigger.click()
            page.wait_for_timeout(2500)

            # 2. Tìm popup hộp thoại soạn bài đang hiển thị thực tế
            # Chú ý: Facebook thường có các dialog ẩn trong DOM (như thông báo, tin nhắn chat),
            # nên cần quét qua tất cả các dialog và chọn dialog nào đang hiển thị và liên quan đến tạo bài viết.
            dialog = None
            for _ in range(8):  # Thử trong tối đa 4 giây
                dialog_candidates = page.locator("div[role='dialog']").all()
                for d in dialog_candidates:
                    try:
                        if d.is_visible():
                            d_text = (d.inner_text() or "").lower()
                            if any(k in d_text for k in ["tạo bài viết", "create post", "bài viết", "thêm vào bài", "đăng"]):
                                dialog = d
                                break
                            elif not dialog:
                                dialog = d
                    except Exception:
                        pass
                if dialog and dialog.is_visible():
                    break
                page.wait_for_timeout(500)

            # Nếu vẫn không thấy dialog, kiểm tra xem ô soạn bài có mở trực tiếp trên bảng tin không (in-line composer)
            if not dialog or not dialog.is_visible():
                inline_textbox = page.locator("div[data-pagelet='GroupInlineComposer'] div[role='textbox'], div[role='main'] div[role='textbox']").first
                if inline_textbox.is_visible():
                    poster_logger.info("   🎯 Phát hiện ô soạn thảo bài viết mở trực tiếp trên bảng tin (Inline Composer).")
                    dialog = page.locator("div[data-pagelet='GroupInlineComposer'], div[role='main']").first

            if not dialog or not dialog.is_visible():
                poster_logger.warning("Popup soạn bài không mở ra sau khi bấm.")
                return {"status": "FAILED", "group_id": group_id, "group_name": group_name, "message": "Popup soạn bài không mở ra (hộp thoại tạo bài bị ẩn hoặc bị chặn)."}

            # 3. Tìm ô nhập văn bản và gõ nội dung bài viết
            textbox = dialog.locator("div[role='textbox'], div[contenteditable='true']").first
            if not textbox.is_visible(timeout=3000):
                textbox = page.locator("div[role='dialog'] div[role='textbox'], div[contenteditable='true']").first

            if not textbox.is_visible(timeout=2000):
                poster_logger.warning("Không tìm thấy ô nhập nội dung bài viết.")
                return {"status": "FAILED", "group_id": group_id, "group_name": group_name, "message": "Không tìm thấy ô nhập văn bản."}

            textbox.click()
            page.wait_for_timeout(500)

            # Gõ nội dung bài viết an toàn qua keyboard insert_text (hỗ trợ Unicode tiếng Việt hoàn hảo)
            page.keyboard.insert_text(post_content)
            page.wait_for_timeout(1500)
            poster_logger.info("   ✍️ Đã điền xong nội dung bài viết kèm link Affiliate chuẩn.")

            # 3.5. TỰ ĐỘNG ĐÍNH KÈM HÌNH ẢNH BANNER VÀO BÀI VIẾT FACEBOOK (PHOTO ATTACHMENT)
            image_attached = False
            image_file_to_upload = None

            try:
                from modules.affiliate.image_stamper import ImageBannerStamper
                if deal:
                    # Tạo/lấy ảnh banner Flash Sale 800x800 đóng khung sản phẩm chuyên nghiệp
                    poster_logger.info("   🎨 Đang đóng khung ảnh Flash Sale 800x800 cho sản phẩm...")
                    banner_path = ImageBannerStamper.stamp_deal_image(deal)
                    if banner_path and banner_path.exists():
                        image_file_to_upload = banner_path
                else:
                    # Tự động chọn đúng loại ảnh phù hợp với chủ đề bài viết
                    content_lower = (post_content or "").lower()
                    if any(k in content_lower for k in ["voucher", "mã", "bí kíp", "back mã", "hoàn xu", "giảm 50%"]):
                        poster_logger.info("   🎨 Đang chuẩn bị ảnh banner Infographic Voucher & Bí Kíp Săn Sale...")
                        banner_path = ImageBannerStamper.create_voucher_banner()
                    elif any(k in content_lower for k in ["mega deal", "ghép", "roundup"]):
                        poster_logger.info("   🎨 Đang chuẩn bị ảnh ghép 4 góc 2x2 Mega Collage...")
                        from modules.outreach.post_composer import SocialOutreachComposer
                        outreach = SocialOutreachComposer(self.db)
                        banner_path = outreach.generate_daily_collage()
                    else:
                        poster_logger.info("   🎨 Đang chuẩn bị ảnh bìa tiêu đề hôm nay...")
                        banner_path = ImageBannerStamper.create_daily_cover_banner()

                    if banner_path and banner_path.exists():
                        image_file_to_upload = banner_path

                if image_file_to_upload and image_file_to_upload.exists():
                    poster_logger.info(f"   📸 Đang đính kèm file ảnh: {image_file_to_upload.name} vào bài viết...")
                    
                    # 1. Thử tìm input file upload ảnh trực tiếp
                    file_input = dialog.locator("input[type='file'][accept*='image'], input[type='file']").first
                    
                    # 2. Nếu chưa gắn vào DOM, click nút Ảnh/video để kích hoạt input
                    if file_input.count() == 0:
                        photo_btn_selectors = [
                            "div[aria-label*='Ảnh/video']",
                            "div[aria-label*='Photo/video']",
                            "div[role='button']:has-text('Ảnh/video')",
                            "div[role='button']:has-text('Photo/video')",
                            "div[aria-label*='Thêm vào bài viết của bạn'] div[role='button']",
                            "span:has-text('Ảnh/video')"
                        ]
                        for p_sel in photo_btn_selectors:
                            p_btn = dialog.locator(p_sel).first
                            if p_btn.is_visible(timeout=1000):
                                p_btn.click()
                                page.wait_for_timeout(1200)
                                break

                    file_input = dialog.locator("input[type='file'][accept*='image'], input[type='file']").first
                    if file_input.count() > 0:
                        file_input.set_input_files(str(image_file_to_upload))
                        page.wait_for_timeout(3500) # Đợi Facebook tải và hiển thị thumbnail ảnh
                        image_attached = True
                        poster_logger.info(f"   ✅ Đã đính kèm ảnh [{image_file_to_upload.name}] vào bài viết Facebook thành công!")
                    else:
                        poster_logger.warning("   ⚠️ Không tìm thấy ô tải ảnh của Facebook, tiếp tục đăng bài dạng text.")
            except Exception as img_err:
                poster_logger.warning(f"   ⚠️ Lỗi khi đính kèm ảnh vào Facebook: {img_err}. Tiếp tục đăng bài dạng text.")

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
            meta = getattr(self, "_last_composed_meta", {}) or {}
            self.db.log_posted_item(
                post_type="POST",
                group_name=group_name,
                group_url=group_url,
                target_url=target_post_url,
                item_id=str(deal.get("item_id", "")) if deal else "",
                item_name=deal.get("name", "") if deal else "Bài tổng hợp",
                content_snippet=snippet,
                status=post_status,
                account_name=acc_name,
                template_id=meta.get("template_id", ""),
                content_hash=meta.get("content_hash", "")
            )

            # Cập nhật số bài đã đăng trong ngày cho tài khoản và kích hoạt Cooldown
            if acc_id:
                try:
                    from modules.workflow.account_router import AccountRouter
                    router = AccountRouter(self.db)
                    router.record_post_result(
                        account_id=acc_id,
                        group_id=group_id,
                        deal_id=str(deal.get("item_id", "")) if deal else "",
                        post_url=target_post_url,
                        status=post_status,
                        duration_seconds=(datetime.now() - start_time).total_seconds()
                    )
                except Exception as r_err:
                    poster_logger.warning(f"⚠️ Lỗi ghi router result: {r_err}")
                self.account_mgr.record_usage(acc_id, task_type="POST", success=True)

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
                "account_name": acc_name,
                "deal_id": deal.get("item_id") if deal else None,
                "deal_name": deal.get("name") if deal else None,
                "post_content": post_content,
                "has_image": image_attached,
                "image_name": image_file_to_upload.name if image_file_to_upload else None,
                "target_url": target_post_url,
                "message": f"{status_desc}{' (Kèm ảnh banner)' if image_attached else ''} vào nhóm [{group_name}] (Bằng {acc_name})!"
            }

        except Exception as e:
            poster_logger.error(f"❌ [LỖI TRONG KHI ĐĂNG BÀI NHÓM {group_name}]: {e}")
            if acc_id:
                try:
                    from modules.workflow.account_router import AccountRouter
                    router = AccountRouter(self.db)
                    router.record_post_result(
                        account_id=acc_id,
                        group_id=group_id,
                        deal_id=str(deal.get("item_id", "")) if deal else "",
                        post_url="",
                        status="FAILED",
                        error_message=str(e),
                        duration_seconds=(datetime.now() - start_time).total_seconds()
                    )
                except Exception:
                    pass
                self.account_mgr.record_usage(acc_id, task_type="POST", success=False, error_msg=str(e))
            return {"status": "ERROR", "group_id": group_id, "group_name": group_name, "message": str(e), "account_name": acc_name}

        finally:
            if created_browser and auto_close_browser:
                if page:
                    try:
                        page.close()
                    except Exception:
                        pass
                if context:
                    try:
                        context.close()
                    except Exception:
                        pass
                if browser:
                    try:
                        browser.close()
                    except Exception:
                        pass
                if playwright_instance:
                    try:
                        playwright_instance.stop()
                    except Exception:
                        pass
                    pass

    def run_gradual_posting(
        self,
        max_groups: int = 3,
        min_delay_seconds: int = 180,
        max_delay_seconds: int = 360,
        group_ids: Optional[List[str]] = None,
        delay_seconds: Optional[int] = None
    ) -> List[Dict]:
        """
        Chu trình đăng bài dần dần/tuần tự vào các nhóm Facebook đã tham gia (APPROVED).
        - Hỗ trợ danh sách group_ids cụ thể (khi người dùng chọn tất cả hoặc chọn nhiều nhóm).
        - Luân phiên đa tài khoản Facebook (Nick 1 -> Nick 2 -> Nick 3) chống bị checkpoint.
        - Khoảng nghỉ (nhịp nghỉ) tùy chỉnh giữa các bài đăng với bộ đếm ngược thời gian thực.
        """
        global gradual_posting_state
        gradual_posting_state["is_running"] = True
        gradual_posting_state["completed"] = 0
        gradual_posting_state["status"] = "RUNNING"
        gradual_posting_state["remaining_delay"] = 0
        gradual_posting_state["history"] = []

        # Lấy danh sách nhóm
        with self.db.get_connection() as conn:
            if group_ids and len(group_ids) > 0:
                placeholders = ",".join(["?"] * len(group_ids))
                rows = conn.execute(f"""
                    SELECT * FROM fb_groups 
                    WHERE group_id IN ({placeholders})
                """, [str(gid) for gid in group_ids]).fetchall()
                row_map = {str(r["group_id"]): dict(r) for r in rows}
                groups = [row_map[str(gid)] for gid in group_ids if str(gid) in row_map]
            else:
                groups_rows = conn.execute("""
                    SELECT * FROM fb_groups 
                    WHERE status = 'APPROVED'
                    ORDER BY 
                        CASE WHEN last_posted_at IS NULL THEN 0 ELSE 1 END,
                        last_posted_at ASC,
                        members_count DESC
                    LIMIT ?
                """, (max_groups,)).fetchall()
                groups = [dict(r) for r in groups_rows]

        target_total = len(groups)
        gradual_posting_state["total_target"] = target_total

        eff_delay = delay_seconds if (delay_seconds is not None and delay_seconds > 0) else min_delay_seconds
        gradual_posting_state["delay_seconds"] = eff_delay

        poster_logger.info("\n" + "=" * 80)
        poster_logger.info(f"🚀 BẮT ĐẦU CHU TRÌNH ĐĂNG BÀI TUẦN TỰ VÀO {target_total} NHÓM FACEBOOK")
        poster_logger.info(f"⏰ Thời gian: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        poster_logger.info(f"⏳ Nhịp nghỉ giữa các bài: {eff_delay}s (Cấu hình: min={min_delay_seconds}s, max={max_delay_seconds}s)")
        poster_logger.info("=" * 80)

        if not groups:
            poster_logger.warning("Không có nhóm nào hợp lệ để đăng bài!")
            gradual_posting_state["is_running"] = False
            gradual_posting_state["status"] = "NO_GROUPS"
            return []

        results = []
        for idx, group in enumerate(groups, 1):
            group_id = str(group["group_id"])
            group_name = group.get("name", group_id)

            # Lấy nick luân phiên tiếp theo
            acc, acc_msg = self.account_mgr.get_next_account(task_type="POST")
            cur_acc_name = acc.get("name", "Nick Mặc Định") if acc else "Chưa cấu hình"
            gradual_posting_state["current_group"] = f"{group_name} ({cur_acc_name})"
            gradual_posting_state["current_account"] = cur_acc_name

            poster_logger.info(f"\n--- Tiến trình [{idx}/{len(groups)}]: Đăng bài vào nhóm [{group_name}] bằng tài khoản [{cur_acc_name}] ---")
            if not acc:
                poster_logger.warning(f"⚠️ {acc_msg}")

            res = self.post_to_single_group(group_id, deal_id=None, account=acc)
            results.append(res)
            gradual_posting_state["completed"] += 1
            gradual_posting_state["last_result"] = res
            gradual_posting_state["history"].append(res)

            # Nếu còn nhóm tiếp theo, áp dụng nhịp nghỉ an toàn (Delay)
            if idx < len(groups) and gradual_posting_state["is_running"]:
                if delay_seconds is not None and delay_seconds > 0:
                    delay = delay_seconds
                else:
                    delay = random.randint(min_delay_seconds, max(min_delay_seconds, max_delay_seconds))
                
                next_time = datetime.fromtimestamp(time.time() + delay).strftime("%H:%M:%S")
                gradual_posting_state["next_post_time"] = next_time
                gradual_posting_state["remaining_delay"] = delay
                poster_logger.info(f"⏳ [NHỊP NGHỈ AN TOÀN]: Nghỉ {delay} giây chống spam. Nhóm tiếp theo sẽ đăng lúc {next_time}...")
                
                # Đếm ngược 1 giây mỗi lần để người dùng dừng ngay lập tức khi bấm nút Dừng
                slept = 0
                while slept < delay and gradual_posting_state["is_running"]:
                    time.sleep(1)
                    slept += 1
                    gradual_posting_state["remaining_delay"] = max(0, delay - slept)

            if not gradual_posting_state["is_running"]:
                poster_logger.info("Dừng chu trình đăng bài tuần tự theo yêu cầu người dùng.")
                break

        gradual_posting_state["is_running"] = False
        gradual_posting_state["remaining_delay"] = 0
        gradual_posting_state["status"] = "FINISHED"
        poster_logger.info(f"\n🎉 Hoàn thành chu trình đăng bài tuần tự: Đã xử lý {len(results)}/{len(groups)} nhóm.")
        return results
