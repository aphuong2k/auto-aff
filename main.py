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

from config.settings import LOG_FILE_PATH, TOP_DEALS_PER_CATEGORY, MAX_GROUPS_TO_JOIN_PER_DAY
from database.db_manager import DatabaseManager
from modules.crawler.shopee_categories import ShopeeCategoryCrawler
from modules.crawler.deal_hunter import DealHunter
from modules.affiliate.link_converter import AffiliateLinkConverter
from modules.affiliate.content_writer import DealContentWriter
from modules.publisher.telegram_bot import TelegramPublisher
from modules.outreach.fb_group_finder import FacebookGroupFinder
from modules.outreach.fb_auto_joiner import FacebookAutoJoiner

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
    """Bộ điều phối toàn trình với hệ thống Log Đầu Vào / Đầu Ra chi tiết"""

    def __init__(self):
        self.db = DatabaseManager()
        self.cat_crawler = ShopeeCategoryCrawler(self.db)
        self.deal_hunter = DealHunter(self.db)
        self.link_converter = AffiliateLinkConverter()
        self.telegram_pub = TelegramPublisher(db=self.db)
        self.group_finder = FacebookGroupFinder(self.db)
        self.auto_joiner = FacebookAutoJoiner(self.db)

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
            categories = [
                {"cat_id": 11035954, "name": "Thiết Bị Điện Tử", "sub_categories": []},
                {"cat_id": 11036670, "name": "Thiết Bị Điện Gia Dụng", "sub_categories": []},
                {"cat_id": 11036279, "name": "Sắc Đẹp", "sub_categories": []},
                {"cat_id": 11036382, "name": "Mẹ & Bé", "sub_categories": []}
            ]

        target_cats = categories[:max_categories]
        logger.info(f"  📤 [ĐẦU RA]: Lấy thành công {len(categories)} ngành hàng hợp lệ từ Shopee.")
        logger.info(f"               Đã chọn {len(target_cats)} ngành hàng mục tiêu hôm nay:")
        for idx, c in enumerate(target_cats, 1):
            sub_count = len(c.get("sub_categories", []))
            logger.info(f"               {idx}. [{c['name']}] (CatID: {c['cat_id']} | {sub_count} danh mục con)")

        # -------------------------------------------------------------
        # BƯỚC 2: CÀO & LỌC TOP DEAL HOT CHO MỖI NGÀNH HÀNG
        # -------------------------------------------------------------
        logger.info("\n" + "─"*70)
        logger.info("🔍 [BƯỚC 2: CÀO & LỌC DEAL HOT THEO NGÀNH HÀNG]")
        logger.info("  📥 [ĐẦU VÀO]: Ngưỡng lọc: Rating >= 4.6 ⭐ | Đã bán >= 200 | Giảm giá >= 15%")
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

            logger.info(f"   📤 [ĐẦU RA NGÀNH {cat_name}]: Tìm thấy {len(top_deals)} deal đạt chuẩn:")
            for d_idx, deal in enumerate(top_deals, 1):
                logger.info(
                    f"       {d_idx}. {deal['name'][:40]}... "
                    f"| Giá sale: {int(deal['price_sale']):,}đ (Gốc: {int(deal['price_original']):,}đ - Giảm {deal['discount_percent']}%) "
                    f"| ⭐ {deal['rating_star']} | Đã bán: {deal['historical_sold']:,} "
                    f"| Điểm Deal: {deal['deal_score']}"
                )

        # -------------------------------------------------------------
        # BƯỚC 3: CONVERT LINK AFFILIATE & SOẠN BÀI ĐĂNG KÊNH NHÀ
        # -------------------------------------------------------------
        logger.info("\n" + "─"*70)
        logger.info("🔗 [BƯỚC 3: CONVERT LINK AFFILIATE & ĐĂNG BÀI KÊNH NHÀ]")
        logger.info(f"  📥 [ĐẦU VÀO]: {len(all_daily_deals)} link sản phẩm gốc Shopee")

        for idx, deal in enumerate(all_daily_deals, 1):
            original_url = deal["item_url"]
            aff_url = self.link_converter.convert_to_affiliate(original_url)
            deal["aff_url"] = aff_url

            logger.info(f"\n   --- Deal #{idx}: {deal['name'][:35]} ---")
            logger.info(f"   Link gốc: {original_url}")
            logger.info(f"   Link Aff: {aff_url}")

            # Đăng lên Telegram
            self.telegram_pub.publish_deal(deal)

        logger.info(f"  📤 [ĐẦU RA]: Đã chuyển đổi thành công {len(all_daily_deals)} link affiliate và soạn bài hoàn tất.")

        # -------------------------------------------------------------
        # BƯỚC 4: DÒ TÌM GROUP FACEBOOK THEO NGÀNH HÀNG
        # -------------------------------------------------------------
        logger.info("\n" + "─"*70)
        logger.info("👥 [BƯỚC 4: DÒ TÌM GROUP FACEBOOK THEO NGÀNH HÀNG]")
        total_discovered_groups = []
        for cat in target_cats:
            cat_name = cat["name"]
            keywords = self.group_finder.get_search_keywords_for_category(cat_name)
            logger.info(f"\n   📥 [ĐẦU VÀO]: Ngành [{cat_name}] -> Từ khóa tìm kiếm: {keywords[:2]}")
            logger.info("                Điều kiện lọc: Thành viên >= 10.000")

            groups = self.group_finder.search_groups(category_name=cat_name, max_groups=2)
            total_discovered_groups.extend(groups)

            logger.info(f"   📤 [ĐẦU RA]: Đã tìm thấy và lưu {len(groups)} group tiềm năng cho ngành [{cat_name}]:")
            for g_idx, g in enumerate(groups, 1):
                logger.info(f"       {g_idx}. {g['name']} | Thành viên: {g['members_count']:,} | URL: {g['url']}")

        # -------------------------------------------------------------
        # BƯỚC 5: TỰ ĐỘNG THAM GIA GROUP VÀ AI TRẢ LỜI CÂU HỎI
        # -------------------------------------------------------------
        logger.info("\n" + "─"*70)
        logger.info("🤖 [BƯỚC 5: TỰ ĐỘNG THAM GIA GROUP (AUTO-JOIN WITH AI)]")
        logger.info(f"  📥 [ĐẦU VÀO]: Hàng đợi group cần join | Giới hạn an toàn: Tối đa {MAX_GROUPS_TO_JOIN_PER_DAY} group/ngày")

        joined_count = self.auto_joiner.process_pending_joins()
        logger.info(f"  📤 [ĐẦU RA]: Đã gửi yêu cầu tham gia thành công cho {joined_count} group hôm nay (Trạng thái: PENDING).")

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
        logger.info(f"  • Group Facebook mới phát hiện: {len(total_discovered_groups)} groups")
        logger.info(f"  • Group Facebook đã xin gia nhập: {joined_count} groups")
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
