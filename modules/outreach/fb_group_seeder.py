import os
import time
import random
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from config.settings import FB_SEEDING_LOG_PATH
from database.db_manager import DatabaseManager
from modules.affiliate.content_writer import DealContentWriter
from modules.affiliate.link_converter import AffiliateLinkConverter
from modules.affiliate.image_stamper import ImageBannerStamper

# ==============================================================================
# BỘ LOGGER ĐỘC LẬP CHO RIÊNG TIẾN TRÌNH FACEBOOK SEEDING (GHI VÀO facebook_seeding.log)
# ==============================================================================
seeding_logger = logging.getLogger("FacebookSeeder")
seeding_logger.setLevel(logging.INFO)
seeding_logger.propagate = False

# Đảm bảo không gắn lặp lại handler nếu file được reload
if not any(isinstance(h, logging.FileHandler) and Path(getattr(h, "baseFilename", "")).resolve() == FB_SEEDING_LOG_PATH.resolve() for h in seeding_logger.handlers):
    try:
        fh = logging.FileHandler(str(FB_SEEDING_LOG_PATH), encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
        seeding_logger.addHandler(fh)
    except Exception as e:
        print(f"Không thể khởi tạo FileHandler cho facebook_seeding.log: {e}")

    # Đồng thời đẩy ra console để tiện theo dõi terminal
    sh = logging.StreamHandler()
    sh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    seeding_logger.addHandler(sh)


class FacebookGroupSeeder:
    """
    Module tự động dò tìm bài đăng hỏi mua/xin link trong Group Facebook và gieo comment đề xuất deal.
    - Quét bài viết THẬT từ bảng tin của nhóm bằng Playwright.
    - Nhận diện nhu cầu hỏi mua / xin link qua từ khóa ý định.
    - Nếu phát hiện bài viết thật: Soạn nội dung review phù hợp kèm link Affiliate chuẩn.
    - Có hệ thống nhật ký riêng (logs/facebook_seeding.log) cực kỳ minh bạch, không fake dữ liệu.
    """

    BUYING_INTENT_KEYWORDS = [
        "xin link", "xin chỗ mua", "mua ở đâu", "shop nào bán", "ai có link",
        "review em này", "dùng tốt không", "chỗ nào bán rẻ", "cần tìm mua",
        "pass lại", "xin review", "cho em hỏi chỗ mua", "tư vấn giúp", "ai mua chưa",
        "có nên mua", "loại nào tốt", "mua loại nào", "cho mình xin link", "xin info",
        "chỗ mua uy tín", "ai pass", "tìm mua", "order ở đâu", "mua shopee nào"
    ]

    def __init__(self, db: Optional[DatabaseManager] = None):
        self.db = db or DatabaseManager()
        self.link_converter = AffiliateLinkConverter()

    def has_buying_intent(self, text: str) -> Tuple[bool, str]:
        """
        Kiểm tra văn bản bài viết có chứa ý định tìm mua hoặc xin link hay không.
        Trả về (has_intent, matched_keyword).
        """
        if not text:
            return False, ""
        text_lower = text.lower()
        for kw in self.BUYING_INTENT_KEYWORDS:
            if kw in text_lower:
                return True, kw
        return False, ""

    def find_best_matching_deal(self, post_text: str = "", category_name: Optional[str] = None) -> Optional[Dict]:
        """Tìm sản phẩm đúng 100% ngành hàng của Group Facebook (Strict Category Matching)"""
        with self.db.get_connection() as conn:
            target_cat = category_name or ""
            cat_keywords = {
                "Thiết Bị Điện Tử": ["điện tử", "tai nghe", "cáp", "sạc", "chuột", "bàn phím", "loa", "công nghệ", "phụ kiện"],
                "Thiết Bị Điện Gia Dụng": ["gia dụng", "nồi", "chảo", "máy", "bếp", "lau", "nhà cửa"],
                "Thời Trang Nam": ["thời trang nam", "quần nam", "áo nam"],
                "Thời Trang": ["thời trang", "áo", "quần", "dép", "giày", "túi"],
                "Sắc Đẹp": ["sắc đẹp", "mỹ phẩm", "skincare", "son", "kem", "serum", "dưỡng", "làm đẹp"],
                "Mẹ & Bé": ["mẹ & bé", "mẹ và bé", "tã", "bỉm", "sữa", "đồ chơi", "trẻ em"]
            }

            combined_context = f"{target_cat} {post_text}".lower()

            # 1. Phát hiện ngành hàng phù hợp từ ngữ cảnh bài đăng hoặc tên nhóm
            detected_category = None
            for cat_name, kws in cat_keywords.items():
                if any(kw in combined_context for kw in kws):
                    detected_category = cat_name
                    break

            if detected_category:
                rows = conn.execute("""
                    SELECT * FROM deals 
                    WHERE category_name LIKE ? 
                    ORDER BY deal_score DESC 
                    LIMIT 5
                """, (f"%{detected_category}%",)).fetchall()
                if rows:
                    return dict(random.choice(rows))
                
                # Tìm sản phẩm có tên chứa từ khóa cốt lõi
                for kw in cat_keywords[detected_category]:
                    row = conn.execute("""
                        SELECT * FROM deals 
                        WHERE name LIKE ? 
                        ORDER BY deal_score DESC 
                        LIMIT 1
                    """, (f"%{kw}%",)).fetchone()
                    if row:
                        return dict(row)

            # 2. Khớp theo category_name trực tiếp nếu chưa phát hiện
            if target_cat:
                rows = conn.execute("""
                    SELECT * FROM deals 
                    WHERE category_name LIKE ? 
                    ORDER BY deal_score DESC 
                    LIMIT 5
                """, (f"%{target_cat}%",)).fetchall()
                if rows:
                    return dict(random.choice(rows))

            # 3. Lấy deal có điểm cao nhất trong database
            rows = conn.execute("""
                SELECT * FROM deals 
                ORDER BY deal_score DESC 
                LIMIT 10
            """).fetchall()
            if rows:
                return dict(random.choice(rows))
        return None

    def generate_seeding_comment(self, deal: Dict, group_id: str, post_context: str = "") -> str:
        """Tạo nội dung comment dạng review thực tế với link trực tiếp hoặc link an toàn kèm Sub-ID tracking"""
        item_id = str(deal.get("item_id", ""))
        direct_aff = deal.get("aff_url") or deal.get("item_url", "")
        redirect_mode = os.getenv("REDIRECT_MODE", "direct").lower().strip()

        if redirect_mode == "direct":
            chosen_url = direct_aff
        else:
            chosen_url = self.link_converter.get_bridge_url(
                item_id=item_id,
                channel="fb_seeding",
                sub_id=f"grp_{group_id}",
                direct_aff_url=direct_aff
            )
        deal_copy = dict(deal)
        deal_copy["aff_url"] = chosen_url
        return DealContentWriter.generate_comment_seeding_post(deal_copy, query_context=post_context)

    def scan_group_for_real_posts(self, page, group_url: str, group_name: str = "") -> List[Dict]:
        """Dùng Playwright quét các bài đăng thực tế trên bảng tin nhóm Facebook"""
        real_posts = []
        try:
            seeding_logger.info(f"🌐 [TRUY CẬP]: Đang mở bảng tin nhóm [{group_name}] ({group_url})...")
            page.goto(group_url, timeout=35000, wait_until="domcontentloaded")
            page.wait_for_timeout(3500)

            # 1. Kiểm tra nhóm có tồn tại hoặc tài khoản có quyền xem không
            body_text = ""
            try:
                body_text = page.locator("body").inner_text()
            except Exception:
                pass

            body_lower = body_text.lower()
            if "nội dung này hiện không khả dụng" in body_lower or "this content isn't available" in body_lower:
                seeding_logger.warning(
                    f"⚠️ [KHÔNG KHẢ DỤNG]: Facebook báo nội dung nhóm [{group_name}] hiện không khả dụng "
                    f"(Nhóm có thể đã bị xóa, đổi URL hoặc tài khoản bị giới hạn)."
                )
                return []

            if "yêu cầu tham gia của bạn đang chờ duyệt" in body_lower or ("nhóm riêng tư" in body_lower and "tham gia nhóm" in body_lower):
                seeding_logger.warning(
                    f"⚠️ [CHỜ PHÊ DUYỆT]: Tài khoản Facebook của bạn chưa là thành viên chính thức của nhóm [{group_name}]. "
                    f"Đây là nhóm kín nên bảng tin bị ẩn. Bot sẽ quét lại sau khi quản trị viên duyệt yêu cầu."
                )
                return []

            # 2. Cuộn bảng tin để nạp các bài viết mới
            seeding_logger.info(f"📜 [ĐỌC BẢNG TIN]: Đang cuộn trang để nạp các bài viết mới nhất...")
            page.mouse.wheel(0, 1000)
            page.wait_for_timeout(2500)
            page.mouse.wheel(0, 1000)
            page.wait_for_timeout(2000)

            # 3. Bóc tách các bài viết bằng nhiều selector Facebook phổ biến
            post_elements = page.locator("div[role='article'], div[role='feed'] > div, div[data-ad-preview='message']").all()
            seeding_logger.info(f"🔍 [PHÂN TÍCH]: Đã tìm thấy {len(post_elements)} khối bài viết trên màn hình. Bắt đầu rà soát từ khóa nhu cầu...")

            scanned_count = 0
            for idx, el in enumerate(post_elements[:15], 1):
                try:
                    text = el.inner_text().strip()
                    if not text or len(text) < 15:
                        continue

                    scanned_count += 1
                    snippet = text.replace("\n", " ")[:90]

                    # Kiểm tra bài đăng có ý định tìm mua hoặc xin link hay không
                    has_intent, matched_kw = self.has_buying_intent(text)
                    if has_intent:
                        # Tìm link bài viết thực tế
                        link_el = el.locator("a[href*='/posts/'], a[href*='/permalink/'], a[href*='story.php']").first
                        post_href = ""
                        try:
                            if link_el.is_visible(timeout=800):
                                post_href = link_el.get_attribute("href") or ""
                                if post_href and "?" in post_href:
                                    post_href = post_href.split("?")[0]
                        except Exception:
                            pass

                        final_url = post_href or group_url
                        seeding_logger.info(
                            f"   🔥 [PHÁT HIỆN BÀI ĐĂNG CÓ NHU CẦU]: Bài #{scanned_count} chứa từ khóa: '{matched_kw}'\n"
                            f"      • Trích đoạn: \"{snippet}...\"\n"
                            f"      • Link bài viết: {final_url}"
                        )
                        real_posts.append({
                            "text": text[:350],
                            "url": final_url,
                            "intent_keyword": matched_kw
                        })
                    else:
                        seeding_logger.debug(f"   • Bỏ qua bài #{scanned_count}: \"{snippet}...\" (Không chứa từ khóa hỏi mua)")
                except Exception as ex:
                    continue

            if scanned_count > 0 and not real_posts:
                seeding_logger.info(
                    f"ℹ️ [KẾT QUẢ QUÉT]: Đã rà soát {scanned_count} bài viết gần nhất trong nhóm [{group_name}]. "
                    f"Chưa có bài nào hỏi mua hoặc xin link trong đợt này. "
                    f"Hệ thống tuân thủ an toàn, KHÔNG spam lung tung vào bài không phù hợp."
                )

        except Exception as e:
            seeding_logger.error(f"❌ [LỖI QUÉT NHÓM] [{group_url}]: {e}", exc_info=True)

        return real_posts

    def run_seeding_scan(self, max_groups: int = 10, target_group_id: Optional[str] = None) -> List[Dict]:
        """
        Quét các group Facebook thật đã tham gia (status='APPROVED' hoặc 'PENDING').
        - Nếu chưa có FB_COOKIE: Báo lỗi cấu hình rõ ràng, KHÔNG fake dữ liệu.
        - Nếu có Cookie: Mở Playwright quét bài viết thật và gieo bình luận chuẩn.
        - Ghi toàn bộ tiến trình vào logs/facebook_seeding.log.
        """
        start_time = datetime.now()
        seeding_logger.info("\n" + "=" * 80)
        seeding_logger.info("🚀 BẮT ĐẦU CHU TRÌNH QUÉT & GIEO BÌNH LUẬN SEEDING FACEBOOK (THẬT 100%)")
        seeding_logger.info(f"⏰ Thời gian khởi chạy: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        seeding_logger.info(f"📁 Nhật ký được lưu riêng tại: {FB_SEEDING_LOG_PATH}")
        seeding_logger.info("=" * 80)

        results = []

        # 1. KIỂM TRA CẤU HÌNH TÀI KHOẢN FACEBOOK
        fb_cookie = os.getenv("FB_COOKIE", "").strip()
        fb_profile = os.getenv("FB_CHROME_PROFILE", "").strip()

        if not fb_cookie and not fb_profile:
            seeding_logger.error(
                "❌ [LỖI CẤU HÌNH FACEBOOK]: Chưa cấu hình FB_COOKIE hoặc FB_CHROME_PROFILE trong file .env!\n"
                "   -> Vui lòng vào tab 'Cài Đặt' trên Dashboard để dán Cookie tài khoản Facebook của bạn.\n"
                "   -> Hệ thống dừng tiến trình ngay và tuyệt đối KHÔNG tạo bản ghi giả lập hay link ảo (Dữ liệu thật 100%)."
            )
            return []

        # Trích xuất UID tài khoản từ Cookie để log xác thực
        uid = ""
        for part in fb_cookie.split(";"):
            part_str = part.strip()
            if part_str.startswith("c_user="):
                uid = part_str.split("c_user=", 1)[-1]
                break

        if uid:
            seeding_logger.info(f"🔑 [XÁC THỰC FACEBOOK]: Phát hiện tài khoản Facebook UID: {uid} (Đang dùng Cookie cấu hình)")
        elif fb_profile:
            seeding_logger.info(f"🔑 [XÁC THỰC FACEBOOK]: Sử dụng Chrome Profile tại: {fb_profile}")

        # 2. LẤY DANH SÁCH NHÓM FACEBOOK THẬT TỪ CSDL (BỎ QUA CÁC NHÓM MOCK/TEST CŨ)
        with self.db.get_connection() as conn:
            if target_group_id and target_group_id != "ALL":
                groups = conn.execute("""
                    SELECT * FROM fb_groups 
                    WHERE group_id = ? OR id = ?
                """, (target_group_id, target_group_id)).fetchall()
            else:
                limit_val = 9999 if max_groups >= 999 else max_groups
                groups = conn.execute("""
                    SELECT * FROM fb_groups 
                    WHERE status IN ('APPROVED', 'PENDING')
                    ORDER BY members_count DESC 
                    LIMIT ?
                """, (limit_val,)).fetchall()

        if not groups:
            seeding_logger.warning(
                "ℹ️ [CHƯA CÓ NHÓM HỢP LỆ]: Chưa có nhóm Facebook nào ở trạng thái APPROVED hoặc PENDING trong CSDL.\n"
                "   -> Hãy kích hoạt 'Bắt Đầu Quét Ngay' trên Dashboard để hệ thống tự động dò tìm nhóm đúng ngành hàng."
            )
            return []

        seeding_logger.info(f"📋 [MỤC TIÊU]: Sẽ tiến hành rà soát {len(groups)} nhóm tiềm năng hôm nay:")
        for idx, g_row in enumerate(groups, 1):
            g = dict(g_row)
            seeding_logger.info(f"   {idx}. [{g.get('name')}] | TV: {g.get('members_count', 0):,} | Trạng thái: {g.get('status')} | URL: {g.get('url')}")

        # 3. KHỞI TẠO TRÌNH DUYỆT PLAYWRIGHT ĐỂ DUYỆT BẢNG TIN THẬT
        try:
            from playwright.sync_api import sync_playwright
            seeding_logger.info("🤖 [PLAYWRIGHT]: Đang khởi động trình duyệt Chromium ngầm...")

            with sync_playwright() as p:
                if fb_profile and os.path.exists(fb_profile):
                    context = p.chromium.launch_persistent_context(
                        user_data_dir=fb_profile,
                        headless=True,
                        args=["--disable-blink-features=AutomationControlled"]
                    )
                    browser = None
                else:
                    browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
                    context = browser.new_context(
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                        viewport={"width": 1280, "height": 800}
                    )
                    if fb_cookie:
                        cookie_list = []
                        for item in fb_cookie.split(";"):
                            if "=" in item:
                                k, v = item.strip().split("=", 1)
                                cookie_list.append({"name": k, "value": v, "domain": ".facebook.com", "path": "/"})
                        if cookie_list:
                            context.add_cookies(cookie_list)

                page = context.new_page()

                # Kiểm tra phiên đăng nhập trên Facebook
                try:
                    seeding_logger.info("🔐 [KIỂM TRA PHIÊN]: Đang xác thực phiên đăng nhập Facebook...")
                    page.goto("https://www.facebook.com/", timeout=25000, wait_until="domcontentloaded")
                    page.wait_for_timeout(2000)
                    curr_url = page.url.lower()

                    if "login" in curr_url or "checkpoint" in curr_url:
                        seeding_logger.error(
                            "❌ [PHIÊN ĐĂNG NHẬP HẾT HẠN]: Cookie Facebook của bạn đã hết hạn hoặc bị Facebook yêu cầu xác minh (Checkpoint)!\n"
                            "   -> Hãy đăng nhập lại Facebook trên trình duyệt máy tính, lấy Cookie mới và cập nhật vào tab 'Cài Đặt'."
                        )
                        if browser:
                            browser.close()
                        else:
                            context.close()
                        return []
                    seeding_logger.info("✅ [PHIÊN HỢP LỆ]: Phiên đăng nhập Facebook đang hoạt động tốt.")
                except Exception as e:
                    seeding_logger.warning(f"⚠️ Kiểm tra trang chủ FB có cảnh báo: {e} (Tiếp tục thử vào nhóm trực tiếp)")

                # Duyệt qua từng nhóm Facebook
                for g_row in groups:
                    g = dict(g_row)
                    group_id = str(g.get("group_id", ""))
                    group_name = g.get("name", "")
                    group_url = g.get("url", "") or f"https://facebook.com/groups/{group_id}"
                    cat_name = g.get("category_name", "")

                    seeding_logger.info(f"\n──────────────────────────────────────────────────────────────────────")
                    seeding_logger.info(f"👥 BẮT ĐẦU QUÉT NHÓM: [{group_name}]")
                    seeding_logger.info(f"   • Ngành hàng: [{cat_name}] | Link nhóm: {group_url}")

                    real_posts = self.scan_group_for_real_posts(page, group_url, group_name=group_name)

                    if not real_posts:
                        continue

                    # Nếu tìm thấy bài viết thật có nhu cầu xin link
                    for p_idx, post in enumerate(real_posts[:2], 1):
                        matched_deal = self.find_best_matching_deal(post["text"], category_name=cat_name)
                        if matched_deal:
                            comment = self.generate_seeding_comment(matched_deal, group_id, post_context=post["text"])
                            target_url = post["url"]

                            product_img_path = ImageBannerStamper.stamp_deal_image(matched_deal)
                            img_path_str = str(product_img_path) if product_img_path and product_img_path.exists() else ""

                            # Lưu vào CSDL với link bài viết thật
                            self.db.log_comment_seeding(
                                group_id=group_id,
                                item_id=str(matched_deal["item_id"]),
                                comment_text=comment,
                                target_post_url=target_url,
                                status="DRAFT"
                            )
                            self.db.log_posted_item(
                                post_type="COMMENT",
                                group_name=group_name,
                                group_url=group_url,
                                target_url=target_url,
                                item_id=str(matched_deal["item_id"]),
                                item_name=matched_deal["name"],
                                content_snippet=comment[:180],
                                image_path=img_path_str,
                                status="DRAFT"
                            )

                            results.append({
                                "group_name": group_name,
                                "group_id": group_id,
                                "target_url": target_url,
                                "deal_name": matched_deal["name"],
                                "comment": comment
                            })

                            seeding_logger.info(
                                f"   ✨ [ĐÃ SOẠN BÌNH LUẬN THẬT]: Khớp deal [{matched_deal['name'][:35]}]\n"
                                f"      • Bài viết đích: {target_url}\n"
                                f"      • Nội dung review: \"{comment[:140]}...\"\n"
                                f"      • Đã lưu vào hàng đợi bình luận (Trạng thái: DRAFT - Sẵn sàng gửi)."
                            )

                if browser:
                    browser.close()
                else:
                    context.close()

            duration = (datetime.now() - start_time).total_seconds()
            seeding_logger.info("\n" + "=" * 80)
            seeding_logger.info(f"📊 KẾT QUẢ TIẾN TRÌNH SEEDING (Hoàn thành trong {duration:.2f} giây):")
            seeding_logger.info(f"   • Số nhóm đã rà soát: {len(groups)}")
            seeding_logger.info(f"   • Số bình luận seeding thật đã tạo: {len(results)}")
            seeding_logger.info("=" * 80 + "\n")
            return results

        except Exception as e:
            seeding_logger.error(f"❌ [LỖI THỰC THI PLAYWRIGHT FACEBOOK SEEDING]: {e}", exc_info=True)
            return []
