"""
Shopee & Lazada Affiliate Automation - Master Orchestrator (Unified CLI)
========================================================================
Hợp nhất toàn bộ luồng vận hành theo kiến trúc 2 trục chính:
- Trục 1: DealCollector – Pipeline thu thập, thẩm định Quality Gate & làm giàu Deal Pool.
- Trục 2: ClosedLoopEngine – State Machine khép kín điều phối Facebook Outreach (Routing, Account Balancer, Posting, Seeding).
- Kênh Nhà: TelegramPublisher & ImageBannerStamper (Đóng khung Flash Sale, gửi Telegram).
- Nhóm PR: GeneralDealOutreach (Bản tin Mega Deal, ảnh ghép 2x2 Collage).

Được bảo vệ bởi Mutex Lock (SYSTEM_WORKFLOW_LOCK) chống chạy song song xung đột tài nguyên.
"""

import argparse
import io
import logging
import sys
import threading
from datetime import datetime
from typing import Dict, List, Optional

# Thiết lập mã hóa UTF-8 cho Console Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from config.settings import LOG_FILE_PATH, TOP_DEALS_PER_CATEGORY
from database.db_manager import DatabaseManager
from modules.workflow.deal_collector import DealCollector
from modules.workflow.closed_loop_engine import ClosedLoopEngine
from modules.crawler.price_history_tracker import PriceHistoryTracker
from modules.affiliate.link_converter import AffiliateLinkConverter
from modules.publisher.telegram_bot import TelegramPublisher
from modules.outreach.general_deal_outreach import GeneralDealOutreach

# Cấu hình Logger
logger = logging.getLogger("AffiliateAuto")
logger.setLevel(logging.INFO)
if not logger.handlers:
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    try:
        file_handler = logging.FileHandler(LOG_FILE_PATH, mode="a", encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception:
        pass

# Khóa Mutex toàn cục ngăn 2 phiên chạy đồng thời
SYSTEM_WORKFLOW_LOCK = threading.Lock()


class AffiliateSystemOrchestrator:
    """Bộ điều phối hợp nhất toàn hệ thống (Central Orchestrator)"""

    def __init__(self, db: Optional[DatabaseManager] = None):
        self.db = db or DatabaseManager()
        self.collector = DealCollector(self.db)
        self.closed_loop = ClosedLoopEngine(self.db)
        self.price_tracker = PriceHistoryTracker(self.db)
        self.link_converter = AffiliateLinkConverter()
        self.telegram_pub = TelegramPublisher(db=self.db)
        self.general_outreach = GeneralDealOutreach(self.db)

    def run_daily_workflow(
        self,
        max_categories: int = 3,
        selected_cat_ids: Optional[List[int]] = None,
        max_groups: int = 3,
        mode: str = "all"
    ) -> Dict:
        """
        Thực thi chu trình làm việc tự động hợp nhất:
        1. Acquire mutex lock để đảm bảo không bị race condition.
        2. Chạy DealCollector cào và làm giàu deal pool.
        3. Đóng khung banner & phát sóng deal chất lượng lên Telegram.
        4. Chạy ClosedLoopEngine duyệt N nhóm Facebook theo State Machine khép kín.
        5. Soạn bản tin Mega Deal & Collage cho nhóm PR cộng đồng.
        """
        if not SYSTEM_WORKFLOW_LOCK.acquire(blocking=False):
            logger.warning("⚠️ [HỆ THỐNG ĐANG BẬN]: Đã có một tiến trình workflow đang chạy. Yêu cầu mới được hủy để tránh xung đột!")
            return {"status": "LOCKED", "message": "Tiến trình khác đang thực thi."}

        start_time = datetime.now()
        logger.info("\n" + "=" * 80)
        logger.info("🚀 BẮT ĐẦU CHU TRÌNH TỰ ĐỘNG HÓA HỢP NHẤT (UNIFIED AFFILIATE WORKFLOW)")
        logger.info(f"⏰ Thời gian: {start_time.strftime('%Y-%m-%d %H:%M:%S')} | Chế độ: {mode.upper()}")
        logger.info("=" * 80)

        deals_collected = 0
        telegram_posts = 0
        groups_processed = 0
        loop_results = []

        try:
            # -----------------------------------------------------------------
            # TRỤC 1: DEAL COLLECTOR (CÀO & THẨM ĐỊNH DEAL TRUNG TÂM)
            # -----------------------------------------------------------------
            if mode in ["all", "deals", "telegram"]:
                logger.info("\n" + "─" * 70)
                logger.info("📦 [TRỤC 1: THU THẬP & THẨM ĐỊNH DEAL TRUNG TÂM - DEAL COLLECTOR]")

                target_cats = []
                if selected_cat_ids:
                    db_cats = self.db.get_active_categories()
                    target_cats = [c for c in db_cats if int(c.get("cat_id", 0)) in selected_cat_ids]
                if not target_cats:
                    target_cats = self.collector.CORE_CATEGORIES[:max_categories]

                for cat in target_cats:
                    c_name = cat["name"]
                    c_id = cat.get("cat_id")
                    res = self.collector.collect_deals_for_category(category_name=c_name, cat_id=c_id, limit=15)
                    deals_collected += res.get("inserted", 0) + res.get("updated", 0)

            # -----------------------------------------------------------------
            # KÊNH NHÀ: TELEGRAM PUBLISHER & FLASH SALE BANNERS
            # -----------------------------------------------------------------
            if mode in ["all", "telegram"]:
                logger.info("\n" + "─" * 70)
                logger.info("📢 [KÊNH NHÀ: TELEGRAM PUBLISHER & TẠO BANNER GIÁ ĐÁY]")
                today_deals = self.db.get_today_top_deals(limit_per_category=TOP_DEALS_PER_CATEGORY)
                for cat_name, deals in today_deals.items():
                    for deal in deals:
                        try:
                            self.price_tracker.enrich_deal(deal)
                            aff_url = self.link_converter.convert_to_affiliate(
                                deal.get("item_url", ""), channel="telegram", sub_id="tele_main"
                            )
                            deal["aff_url"] = aff_url
                            self.db.update_deal_aff_url(deal.get("item_id", ""), aff_url)
                            self.telegram_pub.publish_deal(deal)
                            telegram_posts += 1
                        except Exception as e:
                            logger.warning(f"⚠️ Lỗi phát deal lên Telegram: {e}")

            # -----------------------------------------------------------------
            # TRỤC 2: CLOSED-LOOP ENGINE (OUTREACH NHÓM FACEBOOK KHÉP KÍN)
            # -----------------------------------------------------------------
            if mode in ["all", "loop"]:
                logger.info("\n" + "─" * 70)
                logger.info(f"🔄 [TRỤC 2: CLOSED-LOOP FB OUTREACH - DUYỆT {max_groups} NHÓM TIẾP THEO]")
                batch_res = self.closed_loop.run_batch(max_groups=max_groups)
                groups_processed = batch_res.get("total_processed", 0)
                loop_results = batch_res.get("results", [])

            # -----------------------------------------------------------------
            # NHÓM PR CỘNG ĐỒNG: BẢN TIN MEGA DEAL & COLLAGE 2x2
            # -----------------------------------------------------------------
            if mode in ["all", "general"]:
                logger.info("\n" + "─" * 70)
                logger.info("🎨 [PR CỘNG ĐỒNG: TẠO BẢN TIN MEGA DEAL & ẢNH GHÉP COLLAGE]")
                try:
                    self.general_outreach.generate_all_general_posts()
                    self.general_outreach.generate_daily_collage()
                except Exception as ge:
                    logger.warning(f"⚠️ Lỗi tạo bản tin cộng đồng: {ge}")

        finally:
            SYSTEM_WORKFLOW_LOCK.release()

        end_time = datetime.now()
        duration = round((end_time - start_time).total_seconds(), 2)
        logger.info("\n" + "=" * 80)
        logger.info("📊 TỔNG KẾT PHIÊN VẬN HÀNH HỢP NHẤT:")
        logger.info(f"  • Thời gian thực thi: {duration}s")
        logger.info(f"  • Deal mới thu thập/cập nhật: {deals_collected}")
        logger.info(f"  • Bài đăng Telegram: {telegram_posts}")
        logger.info(f"  • Nhóm Facebook đã xử lý (Closed-Loop): {groups_processed}")
        logger.info("=" * 80 + "\n")

        return {
            "status": "COMPLETED",
            "duration_seconds": duration,
            "deals_collected": deals_collected,
            "telegram_posts": telegram_posts,
            "groups_processed": groups_processed,
            "loop_results": loop_results
        }


def main():
    parser = argparse.ArgumentParser(description="Shopee & Lazada Affiliate Automation - Unified Master Orchestrator")
    parser.add_argument("--mode", type=str, default="all", choices=["all", "deals", "loop", "telegram", "general"],
                        help="Chế độ chạy: 'all' (toàn trình), 'deals' (chỉ cào deal), 'loop' (chỉ duyệt FB khép kín), 'telegram' (chỉ gửi Telegram)")
    parser.add_argument("--cats", type=int, default=3, help="Số lượng ngành hàng cần cào deal")
    parser.add_argument("--groups", type=int, default=3, help="Số nhóm Facebook cần xử lý theo Closed-Loop")
    args = parser.parse_args()

    orchestrator = AffiliateSystemOrchestrator()
    orchestrator.run_daily_workflow(
        max_categories=args.cats,
        max_groups=args.groups,
        mode=args.mode
    )


if __name__ == "__main__":
    main()
