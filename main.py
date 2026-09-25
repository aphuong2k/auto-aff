import argparse
import logging
import sys
import io
from datetime import datetime
from typing import List, Dict

# Thiết lập mã hóa UTF-8 cho Console Windows để không bị lỗi ký tự Tiếng Việt
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from config.settings import (
    LOG_FILE_PATH, TOP_DEALS_PER_CATEGORY, MAX_GROUPS_TO_JOIN_PER_DAY,
    MIN_RATING_STAR, MIN_HISTORICAL_SOLD, MIN_DISCOUNT_PERCENT
)
from database.db_manager import DatabaseManager
from modules.crawler.shopee_categories import ShopeeCategoryCrawler
from modules.crawler.deal_hunter import DealHunter
from modules.crawler.lazada_deal_hunter import LazadaDealHunter
from modules.crawler.price_history_tracker import PriceHistoryTracker
from modules.affiliate.link_converter import AffiliateLinkConverter
from modules.affiliate.content_writer import DealContentWriter
from modules.affiliate.image_stamper import ImageBannerStamper
from modules.publisher.telegram_bot import TelegramPublisher
from modules.outreach.fb_group_finder import FacebookGroupFinder
from modules.outreach.fb_auto_joiner import FacebookAutoJoiner
from modules.outreach.fb_group_seeder import FacebookGroupSeeder
from modules.outreach.general_deal_outreach import GeneralDealOutreach

# Cấu hình Logger ghi đồng thời ra Console và File log (UTF-8)
logger = logging.getLogger("AffiliateAuto")
logger.setLevel(logging.INFO)
logger.handlers.clear()

formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

file_handler = logging.FileHandler(LOG_FILE_PATH, mode="a", encoding="utf-8")
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

class AffiliateSystemOrchestrator:
    """Bộ điều phối toàn trình với hệ thống Log Đầu Vào / Đầu Ra chi tiết (Đa Sàn Shopee & Lazada)"""

    def __init__(self):
        self.db = DatabaseManager()
        self.cat_crawler = ShopeeCategoryCrawler(self.db)
        self.deal_hunter = DealHunter(self.db)
        self.lazada_hunter = LazadaDealHunter(self.db)
        self.price_tracker = PriceHistoryTracker(self.db)
        self.link_converter = AffiliateLinkConverter()
        self.telegram_pub = TelegramPublisher(db=self.db)
        self.group_finder = FacebookGroupFinder(self.db)
        self.auto_joiner = FacebookAutoJoiner(self.db)
        self.seeder = FacebookGroupSeeder(self.db)
        self.general_outreach = GeneralDealOutreach(self.db)

    def run_daily_workflow(self, max_categories: int = 3):
        start_time = datetime.now()
        logger.info("\n" + "="*80)
        logger.info("🚀 BẮT ĐẦU CHU TRÌNH TỰ ĐỘNG HÓA SĂN DEAL & FACEBOOK OUTREACH")
        logger.info(f"⏰ Thời gian khởi chạy: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"📁 Log được lưu trực tiếp tại: {LOG_FILE_PATH}")
        logger.info("="*80)

        # -------------------------------------------------------------
        # BƯỚC 1: LẤY DANH MỤC ĐỘNG TỪ SHOPEE
        # -------------------------------------------------------------
        logger.info("\n" + "─"*70)
        logger.info("📦 [BƯỚC 1: LẤY DANH MỤC NGÀNH HÀNG TỪ SHOPEE]")
        logger.info(f"  📥 [ĐẦU VÀO]: Endpoint: {ShopeeCategoryCrawler.CATEGORY_TREE_URL}")
        logger.info("               Bộ lọc blacklist: Loại bỏ Voucher, Nạp thẻ, Sim, Vé...")

        categories = self.cat_crawler.fetch_categories()
        if not categories:
            # Lấy danh mục thực tế từ cơ sở dữ liệu nếu API Shopee bị gián đoạn/WAF
            db_cats = self.db.get_all_categories()
            if db_cats:
                logger.warning(
                    f"⚠️ Không thể cào danh mục mới từ Shopee. "
                    f"Sử dụng {len(db_cats)} danh mục thực tế đã lưu từ các phiên trước trong CSDL."
                )
                categories = [{"cat_id": c["cat_id"], "name": c["name"], "sub_categories": []} for c in db_cats]
            else:
                logger.error(
                    "❌ [LỖI NGHIÊM TRỌNG]: Không thể lấy danh mục từ Shopee và CSDL hoàn toàn trống! "
                    "Vui lòng kiểm tra kết nối mạng hoặc cập nhật SHOPEE_COOKIE trong tab Cài Đặt."
                )
                return

        target_cats = categories[:max_categories]
        logger.info(f"  📤 [ĐẦU RA]: Có {len(categories)} ngành hàng thực tế sẵn sàng.")
        logger.info(f"               Đã chọn {len(target_cats)} ngành hàng mục tiêu hôm nay:")
        for idx, c in enumerate(target_cats, 1):
            sub_count = len(c.get("sub_categories", []))
            logger.info(f"               {idx}. [{c['name']}] (CatID: {c['cat_id']} | {sub_count} danh mục con)")

        # -------------------------------------------------------------
        # BƯỚC 2: CÀO & LỌC TOP DEAL HOT CHO MỖI NGÀNH HÀNG
        # -------------------------------------------------------------
        logger.info("\n" + "─"*70)
        logger.info("🔍 [BƯỚC 2: CÀO & LỌC DEAL HOT THEO NGÀNH HÀNG]")
        logger.info(f"  📥 [ĐẦU VÀO]: Ngưỡng lọc: Rating >= {MIN_RATING_STAR} ⭐ | Đã bán >= {MIN_HISTORICAL_SOLD} | Giảm giá >= {MIN_DISCOUNT_PERCENT}%")
        logger.info(f"               Mục tiêu: Lấy Top {TOP_DEALS_PER_CATEGORY} deal hời nhất mỗi ngành")

        all_daily_deals = []
        for cat in target_cats:
            cat_name = cat["name"]
            cat_id = cat["cat_id"]
            logger.info(f"\n   >>> Quét ngành: [{cat_name}] (ID: {cat_id})")
            
            top_deals = self.deal_hunter.search_deals_by_category(
                cat_id=cat_id,
                category_name=cat_name,
                limit=20
            )
            all_daily_deals.extend(top_deals)

            # Đa Sàn: Săn thêm Deal từ Lazada cho ngành hàng này
            try:
                lazada_deals = self.lazada_hunter.search_deals_by_category(
                    category_name=cat_name,
                    limit=15
                )
                if lazada_deals:
                    all_daily_deals.extend(lazada_deals)
                    logger.info(f"   💙 [LAZADA]: Đã tìm thấy {len(lazada_deals)} deal LazMall cho ngành [{cat_name}]")
            except Exception as le:
                logger.warning(f"   ⚠️ Lỗi cào Lazada ngành [{cat_name}]: {le}")

            logger.info(f"   📤 [ĐẦU RA NGÀNH {cat_name}]: Tìm thấy {len(top_deals)} deal Shopee + {len(lazada_deals) if 'lazada_deals' in locals() else 0} deal Lazada:")
            for d_idx, deal in enumerate(top_deals, 1):
                logger.info(
                    f"       {d_idx}. [{deal.get('platform', 'SHOPEE')}] {deal['name'][:40]}... "
                    f"| Giá sale: {int(deal['price_sale']):,}đ (Gốc: {int(deal['price_original']):,}đ - Giảm {deal['discount_percent']}%) "
                    f"| ⭐ {deal['rating_star']} | Đã bán: {deal['historical_sold']:,} "
                    f"| Điểm Deal: {deal['deal_score']}"
                )

        # Thêm các Deal Mồi 1K (Loss-Leader) để kích hoạt Cookie 7 ngày
        try:
            loss_leaders = self.deal_hunter.fetch_loss_leader_deals(limit=2)
            if loss_leaders:
                all_daily_deals.extend(loss_leaders)
                logger.info(f"   🎯 [DEAL MỒI 1K]: Đã nạp thêm {len(loss_leaders)} sản phẩm 1K - Freeship 0Đ để ghim cookie Shopee 7 ngày.")
        except Exception as e:
            logger.warning(f"   ⚠️ Lỗi khi nạp Deal Mồi 1K: {e}")

        # -------------------------------------------------------------
        # BƯỚC 3: PHÂN TÍCH LỊCH SỬ GIÁ, ĐÓNG KHUNG ẢNH & ĐĂNG BÀI KÊNH NHÀ
        # -------------------------------------------------------------
        logger.info("\n" + "─"*70)
        logger.info("🎨 [BƯỚC 3: PHÂN TÍCH GIÁ, ĐÓNG KHUNG ẢNH FLASH SALE & ĐĂNG BÀI]")
        logger.info(f"  📥 [ĐẦU VÀO]: {len(all_daily_deals)} deal chọn lọc từ Shopee")

        for idx, deal in enumerate(all_daily_deals, 1):
            original_url = deal["item_url"]
            item_id = str(deal.get("item_id", ""))

            # 3.1. Phân tích lịch sử giá & bắt giảm giá ảo
            self.price_tracker.enrich_deal(deal)
            badge_text = deal.get("price_verdict_text", "Giá chuẩn")

            # 3.2. Chuyển đổi link Affiliate Shopee kèm Sub-ID tracking và Link Anti-Ban
            aff_url = self.link_converter.convert_to_affiliate(original_url, channel="telegram", sub_id="tele_main")
            bridge_url = self.link_converter.get_bridge_url(
                item_id, channel="telegram", sub_id="tele_main", direct_aff_url=aff_url
            )
            deal["aff_url"] = aff_url
            deal["bridge_url"] = bridge_url
            # Cập nhật link affiliate chuẩn vào database để link đệm /r/{item_id} và web dùng đúng
            self.db.update_deal_aff_url(item_id, aff_url)

            logger.info(f"\n   --- Deal #{idx}: {deal['name'][:35]} ---")
            logger.info(f"   Đánh giá giá: [{badge_text}]")
            logger.info(f"   Link gốc: {original_url}")
            logger.info(f"   Link Aff: {aff_url}")
            logger.info(f"   Link Bridge: {bridge_url}")

            # 3.3. Tải ảnh & Đóng khung Flash Sale + Đăng tải tới Telegram
            self.telegram_pub.publish_deal(deal)

        logger.info(f"  📤 [ĐẦU RA]: Hoàn tất phân tích giá, đóng khung banner và soạn bài cho {len(all_daily_deals)} deal.")

        # -------------------------------------------------------------
        # BƯỚC 4: DÒ TÌM GROUP FACEBOOK THEO NGÀNH HÀNG
        # -------------------------------------------------------------
        logger.info("\n" + "─"*70)
        logger.info("👥 [BƯỚC 4: DÒ TÌM GROUP FACEBOOK THEO NGÀNH HÀNG]")
        total_discovered_groups = []
        try:
            for cat in target_cats:
                cat_name = cat["name"]
                keywords = self.group_finder.get_search_keywords_for_category(cat_name)
                logger.info(f"\n   📥 [ĐẦU VÀO]: Ngành [{cat_name}] -> Từ khóa tìm kiếm: {keywords[:4]}")
                logger.info("                Điều kiện lọc: Thành viên >= 10.000")

                groups = self.group_finder.search_groups(category_name=cat_name, max_groups=2)
                total_discovered_groups.extend(groups)

                logger.info(f"   📤 [ĐẦU RA]: Đã tìm thấy và lưu {len(groups)} group tiềm năng cho ngành [{cat_name}]:")
                for g_idx, g in enumerate(groups, 1):
                    logger.info(f"       {g_idx}. {g['name']} | Thành viên: {g['members_count']:,} | URL: {g['url']}")
        except Exception as e:
            logger.error(f"  ❌ [LỖI BƯỚC 4: TÌM GROUP FB]: {e}")

        # -------------------------------------------------------------
        # BƯỚC 5: TỰ ĐỘNG THAM GIA GROUP VÀ AI TRẢ LỜI CÂU HỎI
        # -------------------------------------------------------------
        logger.info("\n" + "─"*70)
        logger.info("🤖 [BƯỚC 5: TỰ ĐỘNG THAM GIA GROUP (AUTO-JOIN WITH AI)]")
        logger.info(f"  📥 [ĐẦU VÀO]: Hàng đợi group cần join | Giới hạn an toàn: Tối đa {MAX_GROUPS_TO_JOIN_PER_DAY} group/ngày")

        joined_count = 0
        try:
            joined_count = self.auto_joiner.process_pending_joins()
            logger.info(f"  📤 [ĐẦU RA]: Đã gửi yêu cầu tham gia thành công cho {joined_count} group hôm nay (Trạng thái: PENDING).")
        except Exception as e:
            logger.error(f"  ❌ [LỖI BƯỚC 5: AUTO-JOIN GROUP]: {e}")

        # -------------------------------------------------------------
        # BƯỚC 6: SEEDING BÌNH LUẬN DẠO ĐỀ XUẤT DEAL TRÊN GROUP FACEBOOK
        # -------------------------------------------------------------
        logger.info("\n" + "─"*70)
        logger.info("🌱 [BƯỚC 6: SEEDING BÌNH LUẬN DẠO ĐỀ XUẤT DEAL TRÊN GROUP FACEBOOK]")
        seeded_comments = []
        try:
            seeded_comments = self.seeder.run_seeding_scan(max_groups=2)
            logger.info(f"  📤 [ĐẦU RA]: Đã gieo thành công {len(seeded_comments)} bình luận seeding đề xuất deal vào các group.")
        except Exception as e:
            logger.error(f"  ❌ [LỖI BƯỚC 6: SEEDING COMMENT]: {e}")

        # -------------------------------------------------------------
        # BƯỚC 7: TỔNG HỢP DEAL & LỊCH SALE CHO NHÓM CHUNG (PR CỘNG ĐỒNG)
        # -------------------------------------------------------------
        logger.info("\n" + "─"*70)
        logger.info("📢 [BƯỚC 7: TỔNG HỢP DEAL ĐA NGÀNH & LỊCH SALE PR CỘNG ĐỒNG]")
        general_deal_count = 0
        try:
            general_posts = self.general_outreach.generate_all_general_posts()
            collage_img = self.general_outreach.generate_daily_collage()
            general_deal_count = general_posts.get("deal_count", 0)
            logger.info(f"  📤 [ĐẦU RA]: Đã tạo thành công Bản Tin Mega Deal ({general_deal_count} deals)")
            logger.info(f"               Đã tạo ảnh ghép 4 góc (2x2 Collage Grid): {collage_img}")
            if general_posts.get("community_url"):
                logger.info(f"               Kèm Link PR Nhóm Riêng: {general_posts['community_url']} ({general_posts['community_name']})")
        except Exception as e:
            logger.error(f"  ❌ [LỖI BƯỚC 7: TỔNG HỢP NHÓM CHUNG]: {e}")

        # -------------------------------------------------------------
        # TỔNG KẾT CHU TRÌNH
        # -------------------------------------------------------------
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        logger.info("\n" + "="*80)
        logger.info("📊 BẢNG TỔNG KẾT KẾT QUẢ HÔM NAY:")
        logger.info(f"  • Tổng thời gian thực hiện: {duration:.2f} giây")
        logger.info(f"  • Ngành hàng đã quét: {len(target_cats)} danh mục")
        logger.info(f"  • Sản phẩm Top Deal đã chọn: {len(all_daily_deals)} deals")
        logger.info(f"  • Banner ảnh Flash Sale đã đóng khung: {len(all_daily_deals)} ảnh")
        logger.info(f"  • Group Facebook mới phát hiện: {len(total_discovered_groups)} groups")
        logger.info(f"  • Group Facebook đã xin gia nhập: {joined_count} groups")
        logger.info(f"  • Bình luận seeding đã gieo: {len(seeded_comments)} comments")
        logger.info(f"  • File nhật ký chi tiết: {LOG_FILE_PATH}")
        logger.info("="*80 + "\n")

def main():
    parser = argparse.ArgumentParser(description="Shopee Affiliate & Facebook Group Outreach Automation")
    parser.add_argument("--once", action="store_true", default=True, help="Chạy 1 lần chu trình ngay lập tức")
    parser.add_argument("--cats", type=int, default=2, help="Số lượng ngành hàng cần quét deal")
    args = parser.parse_args()

    orchestrator = AffiliateSystemOrchestrator()
    orchestrator.run_daily_workflow(max_categories=args.cats)

if __name__ == "__main__":
    main()
