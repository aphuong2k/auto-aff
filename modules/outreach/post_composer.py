import hashlib
import re
import random
import difflib
from typing import Dict, List, Optional, Tuple, Set

from config.category_mapping import CategoryMatcher
from modules.affiliate.link_converter import AffiliateLinkConverter


class ContentDeduplicator:
    """
    Bộ phân tích và ngăn ngừa trùng lặp nội dung (Anti-Spam & Anti-Pattern).
    - Tính Hash chuẩn hóa của bài viết.
    - So sánh tỷ lệ trùng lặp (Similarity Score) bằng Jaccard Similarity và SequenceMatcher.
    - Cảnh báo nếu bài mới giống bài cũ trên 80% (> 0.8).
    """

    @staticmethod
    def normalize_text(text: str) -> str:
        """Loại bỏ link, emoji, ký tự đặc biệt, số và khoảng trắng thừa để đối chiếu cốt lõi ngữ nghĩa"""
        if not text:
            return ""
        # Bỏ URLs
        t = re.sub(r"https?://\S+", "", text.lower())
        # Bỏ hashtags
        t = re.sub(r"#\w+", "", t)
        # Bỏ số và đơn vị tiền
        t = re.sub(r"\d+[\.,]?\d*\s*(đ|k|vnđ|%|sao|⭐)?", "", t)
        # Chỉ giữ chữ cái tiếng Việt và khoảng trắng
        t = re.sub(r"[^\w\s]", " ", t)
        # Chuẩn hóa khoảng trắng
        return " ".join(t.split())

    @classmethod
    def hash_content(cls, text: str) -> str:
        """Tạo mã SHA256 ngắn gọn đại diện cho nội dung đã chuẩn hóa"""
        norm = cls.normalize_text(text)
        return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]

    @classmethod
    def calculate_similarity(cls, text1: str, text2: str) -> float:
        """
        Tính toán độ tương đồng giữa 2 đoạn văn bản (0.0 đến 1.0).
        Kết hợp Jaccard Similarity (tập hợp từ vựng) và SequenceMatcher (trật tự chuỗi).
        """
        norm1 = cls.normalize_text(text1)
        norm2 = cls.normalize_text(text2)

        if not norm1 or not norm2:
            return 0.0

        words1 = set(norm1.split())
        words2 = set(norm2.split())

        if not words1 or not words2:
            return 0.0

        # Jaccard index
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        jaccard = len(intersection) / len(union) if union else 0.0

        # Sequence matcher ratio
        seq_ratio = difflib.SequenceMatcher(None, norm1, norm2).ratio()

        # Tổng hợp có trọng số
        return round(0.5 * jaccard + 0.5 * seq_ratio, 3)

    @classmethod
    def is_similar_to_history(
        cls,
        new_text: str,
        history_texts: List[str],
        threshold: float = 0.80
    ) -> Tuple[bool, float, str]:
        """
        Kiểm tra bài đăng mới có bị trùng lặp > threshold (mặc định 80%) với lịch sử gần đây không.
        Trả về: (is_duplicate, max_similarity, matched_sample)
        """
        max_sim = 0.0
        most_similar = ""

        for past_text in history_texts:
            if not past_text:
                continue
            sim = cls.calculate_similarity(new_text, past_text)
            if sim > max_sim:
                max_sim = sim
                most_similar = past_text

        is_dup = max_sim >= threshold
        return is_dup, max_sim, most_similar


class LinguisticPermutator:
    """Bộ tạo biến thể ngôn ngữ và trộn từ ngữ vùng miền ngẫu nhiên"""

    PARTICLES = ["nha", "nhé", "nè", "ạ", "ha", "nghen", "nhá", "đó nha", "nhe"]

    ADDRESSING = {
        "men": ["anh em", "mọi người", "cả nhà", "bác nào", "các bro", "mn"],
        "women": ["chị em", "các nàng", "cả nhà mình", "chị em mình", "mọi người", "mn"],
        "tech": ["anh em", "mọi người", "bác nào", "cả nhà", "dân công nghệ", "mn"],
        "beauty": ["chị em", "các nàng", "chị em mình", "mọi người", "mn"],
        "general": ["cả nhà", "mọi người", "anh em", "mn", "bác nào"]
    }

    DISCOVERY_HOOKS = [
        "Góc chia sẻ deal ngon bổ rẻ",
        "Vừa săn được deal hời cho",
        "Mách nước cho",
        "Lướt sàn thấy con này sale sâu quá share cho",
        "Bác nào đang tìm món này thì nghía qua",
        "Deal hời chuẩn xịn xò hôm nay cho"
    ]

    SALE_BADGES = [
        "đang sale chạm đáy",
        "giá flash sale cực sốc",
        "rẻ hơn ngày thường rất nhiều",
        "sale sập sàn hôm nay",
        "giá ngon vượt mong đợi",
        "mức giảm thật sự rất hời"
    ]

    CTAS = [
        "Bác nào cần thì tranh thủ múc sớm kẻo hết lượt",
        "Tranh thủ chốt sớm kẻo bay màu mã giảm",
        "Vào gắp ngay kẻo hết size/hết suất khuyến mãi",
        "Link gian hàng chính hãng săn deal tại đây",
        "Lưu thêm mã Freeship 0Đ áp lúc thanh toán cho hời"
    ]

    @classmethod
    def get_particle(cls) -> str:
        return random.choice(cls.PARTICLES)

    @classmethod
    def get_addressing(cls, group_type: str = "general") -> str:
        pool = cls.ADDRESSING.get(group_type, cls.ADDRESSING["general"])
        return random.choice(pool)


class PostComposer:
    """
    Trình soạn thảo bài đăng Facebook & Telegram chuyên nghiệp:
    - Xoay vòng template (Template Rotation) tránh đăng lặp cấu trúc.
    - Cấu trúc câu động (Dynamic Sentence Assembly) kết hợp từ ngữ vùng miền.
    - Tự động kiểm tra trùng lặp qua ContentDeduplicator (ngưỡng 80%).
    """

    def __init__(self, db=None):
        self.db = db
        self.matcher = CategoryMatcher()
        self.link_converter = AffiliateLinkConverter()

    def _build_tracking_url(self, deal: Dict, group: Dict, template_id: str = "") -> str:
        item_id = str(deal.get("item_id", ""))
        channel = "fb_group"
        gid_prefix = str(group.get("group_id", ""))[:8]
        if template_id:
            sub_id = f"grp_{gid_prefix}_{template_id}"
        else:
            sub_id = f"grp_{gid_prefix}"
        direct_aff = deal.get("aff_url") or deal.get("item_url", "")
        tracking_url = self.link_converter.get_bridge_url(
            item_id, channel=channel, sub_id=sub_id, direct_aff_url=direct_aff
        )
        if not tracking_url or tracking_url == "#":
            tracking_url = direct_aff
        return tracking_url

    @staticmethod
    def _get_tpl_id(matched_cat: str, idx: int) -> str:
        if matched_cat == "Thời Trang Nam":
            return f"MEN_TPL_{idx}"
        elif matched_cat in ("Thời Trang Nữ", "Sắc Đẹp"):
            return f"WOMEN_TPL_{idx}"
        elif matched_cat == "Thiết Bị Điện Tử":
            return f"TECH_TPL_{idx}"
        return f"GEN_TPL_{idx}"

    def get_best_performing_template(self, category_prefix: str) -> Optional[int]:
        """Lấy chỉ số template (1..4) có tỷ lệ click cao nhất trong quá khứ cho ngành hàng"""
        if not self.db:
            return None
        try:
            with self.db.get_connection() as conn:
                row = conn.execute("""
                    SELECT ph.template_id, COUNT(c.id) as clicks
                    FROM post_history ph
                    JOIN click_analytics c ON c.sub_id LIKE '%' || ph.template_id
                    WHERE ph.template_id LIKE ?
                    GROUP BY ph.template_id
                    ORDER BY clicks DESC
                    LIMIT 1
                """, (f"{category_prefix}%",)).fetchone()
                if row and row["clicks"] > 0:
                    tpl_id = row["template_id"]
                    if "_" in tpl_id:
                        return int(tpl_id.split("_")[-1])
        except Exception:
            pass
        return None


    # =========================================================================
    # DANH SÁCH TEMPLATE XOAY VÒNG THEO TỪNG DANH MỤC
    # =========================================================================

    def _render_fashion_men(self, deal: Dict, group: Dict, tracking_url: str, tpl_idx: int) -> Tuple[str, str]:
        p = LinguisticPermutator.get_particle()
        addr = LinguisticPermutator.get_addressing("men")
        item_name = deal.get("name", "Sản phẩm")
        price_sale = int(deal.get("price_sale", 0))
        price_orig = int(deal.get("price_original", 0))
        discount = deal.get("discount_percent", 0)
        sold = deal.get("historical_sold", 0)
        rating = deal.get("rating_star", 5.0)

        tpl_id = f"MEN_TPL_{tpl_idx}"
        if tpl_idx == 1:
            content = (
                f"Góc phối đồ & pass deal hời cho {addr} {p} 👇\n\n"
                f"Hôm nay lướt Shopee Mall thấy em '{item_name}' này sale sâu quá. "
                f"Giá gốc {price_orig:,}đ đang Flash Sale còn {price_sale:,}đ (-{discount}%).\n\n"
                f"• Đã bán: {sold:,} lượt | Đánh giá {rating}⭐ cực chất\n"
                f"• Hàng Mall chính hãng, chất vải và form dáng chuẩn chỉnh\n\n"
                f"Bác nào đang tìm đồ diện đi chơi / đi làm thì múc sớm kẻo hết size {p}:\n"
                f"👉 Link săn sale Shopee Mall: {tracking_url}\n\n"
                f"#thoitrangnam #phoidonam #dealhot #shopeemall"
            )
        elif tpl_idx == 2:
            content = (
                f"[CHIA SẺ DEAL NGON CHO {addr.upper()}] 🔥\n\n"
                f"Vừa check được mã giảm sâu cho em '{item_name}' này trên Shopee rẻ hơn ngày thường nhiều {p}:\n"
                f"• Giá chốt hôm nay: {price_sale:,}đ (Giá gốc: {price_orig:,}đ)\n"
                f"• Hơn {sold:,} anh em đã mua, review {rating} sao uy tín\n\n"
                f"Hàng shop Mall chuẩn chỉ, áp thêm mã Freeship 0Đ tại bước thanh toán là ngon lành {p}.\n"
                f"🔗 Link chốt deal cho bác nào cần: {tracking_url}\n\n"
                f"#donam #phongcachnam #sansaleshopee #dealngon"
            )
        elif tpl_idx == 3:
            content = (
                f"Bác nào đang cần tìm '{item_name}' thì vào nghía ngay {p}!\n\n"
                f"Đang có đợt Flash Sale chớp nhoáng giảm tận {discount}%, chỉ còn {price_sale:,}đ thôi {p}.\n"
                f"Em này form đẹp, vải thoáng mát, hơn {sold:,} người mua feedback ưng ý.\n\n"
                f"⚡ Tranh thủ chốt sớm kẻo hết mã giảm giá {p}:\n"
                f"👉 Mua tại gian hàng Mall: {tracking_url}\n\n"
                f"#menswear #dealshopee #thoitrang #giare"
            )
        else:
            content = (
                f"Review nhanh cho {addr} con '{item_name}' cực đáng tiền trong tầm giá {p} ⚡\n\n"
                f"• Giá sale cực sốc: {price_sale:,}đ (Tiết kiệm {price_orig - price_sale:,}đ)\n"
                f"• Đánh giá uy tín: {rating}/5.0 sao từ {sold:,} người mua trước\n\n"
                f"{addr} nhớ bỏ sẵn vào giỏ hàng rồi áp mã vận chuyển để được freeship tận nhà {p}.\n"
                f"🔗 Link chính hãng đây {p}: {tracking_url}\n\n"
                f"#thoitrangnam #dealngon #shopee"
            )
        return content, tpl_id

    def _render_fashion_women(self, deal: Dict, group: Dict, tracking_url: str, tpl_idx: int) -> Tuple[str, str]:
        p = LinguisticPermutator.get_particle()
        addr = LinguisticPermutator.get_addressing("women")
        item_name = deal.get("name", "Sản phẩm")
        price_sale = int(deal.get("price_sale", 0))
        price_orig = int(deal.get("price_original", 0))
        discount = deal.get("discount_percent", 0)
        sold = deal.get("historical_sold", 0)
        rating = deal.get("rating_star", 5.0)

        tpl_id = f"WOMEN_TPL_{tpl_idx}"
        if tpl_idx == 1:
            content = (
                f"Góc làm đẹp & phối đồ xinh cho {addr} {p} 🥰\n\n"
                f"Em '{item_name}' này đang sale chạm đáy trên Shopee Mall luôn mn ơi!\n"
                f"• Giá gốc: {price_orig:,}đ ➡️ Flash Sale còn: {price_sale:,}đ (-{discount}%)\n"
                f"• Hơn {sold:,} lượt mua, feedback {rating}⭐ cực nhiều ảnh thật\n\n"
                f"{addr} tranh thủ gom sớm kẻo hết lượt sale {p}, link chính hãng đây ạ:\n"
                f"👉 Link mua ưu đãi Shopee: {tracking_url}\n\n"
                f"#macdep #phoido #shopeesale #lamdep #reviewcungchiem"
            )
        elif tpl_idx == 2:
            content = (
                f"Mách nhỏ {addr} deal cực hời hôm nay {p} 💕\n\n"
                f"Em '{item_name}' này dùng siêu thích mà nay đang có mã giảm sâu:\n"
                f"Giá chỉ còn {price_sale:,}đ (tiết kiệm được {price_orig - price_sale:,}đ so với giá gốc).\n"
                f"Mn nhớ áp thêm voucher giảm giá và freeship tại giỏ hàng {p}!\n\n"
                f"🔗 Link shop Mall chính hãng: {tracking_url}\n\n"
                f"#shopeehaul #doxinh #tipsphoido #hangchinhhang"
            )
        elif tpl_idx == 3:
            content = (
                f"Xinh xỉu luôn {addr} ơi! Em '{item_name}' đang Flash Sale siêu sâu ✨\n\n"
                f"• Chỉ có {price_sale:,}đ thôi (gốc {price_orig:,}đ lận)\n"
                f"• Hơn {sold:,} chị em đã chốt đơn, feedback 5 sao lung linh\n\n"
                f"Nàng nào mê phong cách này thì nhanh tay múc sớm kẻo hết size {p}:\n"
                f"👉 Xem chi tiết & đặt hàng: {tracking_url}\n\n"
                f"#ootd #xinhdep #sansale #shopeefeed"
            )
        else:
            content = (
                f"Deal hời cho {addr} tút tát phong cách đây {p} 🌸\n\n"
                f"Mẫu '{item_name}' hot hit bên Shopee Mall đang sale còn {price_sale:,}đ (-{discount}%).\n"
                f"Chất liệu xịn, lên dáng chuẩn, feedback {rating}⭐ hơn {sold:,} lượt mua.\n"
                f"🔗 Link săn deal hời: {tracking_url}\n\n"
                f"#thoitrangnu #doxinh #giamgia #shopee"
            )
        return content, tpl_id

    def _render_electronics(self, deal: Dict, group: Dict, tracking_url: str, tpl_idx: int) -> Tuple[str, str]:
        p = LinguisticPermutator.get_particle()
        addr = LinguisticPermutator.get_addressing("tech")
        item_name = deal.get("name", "Thiết bị")
        price_sale = int(deal.get("price_sale", 0))
        price_orig = int(deal.get("price_original", 0))
        discount = deal.get("discount_percent", 0)
        sold = deal.get("historical_sold", 0)
        rating = deal.get("rating_star", 5.0)

        badge_line = ""
        price_badge = str(deal.get("price_badge", ""))
        if "LOW" in price_badge:
            badge_line = "📉 [ĐỘC QUYỀN]: Đáy lịch sử 30 ngày qua vừa được kiểm chứng!\n"
        elif "REAL" in price_badge:
            badge_line = "✅ [GIẢM THẬT SỰ]: Mức giảm giá thực tế, không chiêu trò kê giá ảo.\n"

        tpl_id = f"TECH_TPL_{tpl_idx}"
        if tpl_idx == 1:
            content = (
                f"Góc Review & Chia Sẻ Đồ Công Nghệ / Phụ Kiện Giá Hời 📱⚡\n\n"
                f"Chia sẻ {addr} con '{item_name}' này dùng cực ngon mà đang sale sâu:\n"
                f"{badge_line}"
                f"• Giá sale chỉ: {price_sale:,}đ (Giá niêm yết: {price_orig:,}đ - Giảm {discount}%)\n"
                f"• Đã bán hơn {sold:,} chiếc, đánh giá {rating}⭐ uy tín\n"
                f"• Hàng chuẩn Mall chính hãng, độ hoàn thiện cao, dùng rất bền bỉ\n\n"
                f"Bác nào đang tìm phụ kiện ngon bổ rẻ thì vào tham khảo {p}:\n"
                f"👉 Link săn sale Shopee Mall: {tracking_url}\n\n"
                f"#congnghe #phukien #iphone #shopeedeal #reviewcotam"
            )
        elif tpl_idx == 2:
            content = (
                f"[KÈO CÔNG NGHỆ THƠM CHO {addr.upper()}] 🔥⚡\n\n"
                f"Con '{item_name}' đang giảm sâu từ {price_orig:,}đ xuống còn {price_sale:,}đ trên Shopee Mall {p}.\n"
                f"Đã có {sold:,} lượt mua thực tế với điểm đánh giá {rating}/5.0 sao.\n"
                f"Bác nào đang cân nhắc lên đời hoặc mua sơ cua thì vào hốt lẹ kẻo hết mã giảm {p}:\n\n"
                f"🔗 Link chốt đơn Mall chính hãng: {tracking_url}\n\n"
                f"#techreview #dientu #phukiengiare #shopeesale"
            )
        elif tpl_idx == 3:
            content = (
                f"Bác nào mê đồ công nghệ tiện ích thì đừng bỏ lỡ con '{item_name}' này {p}!\n\n"
                f"• Giá flash sale: {price_sale:,}đ (-{discount}% so với giá hãng {price_orig:,}đ)\n"
                f"• Đánh giá: {rating}⭐ từ {sold:,} khách hàng đã trải nghiệm\n"
                f"Bảo hành chính hãng đầy đủ, đóng gói chống sốc kỹ càng {p}.\n\n"
                f"👉 Săn ngay tại gian hàng chính hãng: {tracking_url}\n\n"
                f"#gadgets #congnghedoisong #phukiendienthoai #freeship"
            )
        else:
            content = (
                f"Phát hiện deal phụ kiện công nghệ ngon cho {addr} {p} 👇\n\n"
                f"Con '{item_name}' chính hãng Mall đang sale sốc còn {price_sale:,}đ.\n"
                f"Độ bền cao, tính năng ổn định vượt tầm giá. Áp thêm mã voucher ví để giảm thêm {p}.\n"
                f"🔗 Link chốt deal Shopee: {tracking_url}\n\n"
                f"#reviewcongnghe #phukienchinhhang #shopee"
            )
        return content, tpl_id

    def _render_general(self, deal: Dict, group: Dict, tracking_url: str, tpl_idx: int) -> Tuple[str, str]:
        p = LinguisticPermutator.get_particle()
        addr = LinguisticPermutator.get_addressing("general")
        item_name = deal.get("name", "Sản phẩm")
        price_sale = int(deal.get("price_sale", 0))
        price_orig = int(deal.get("price_original", 0))
        discount = deal.get("discount_percent", 0)
        sold = deal.get("historical_sold", 0)
        rating = deal.get("rating_star", 5.0)

        tpl_id = f"GEN_TPL_{tpl_idx}"
        if tpl_idx == 1:
            content = (
                f"🔥 [TỔNG HỢP DEAL FLASH SALE SHOPEE HÔM NAY] 🔥\n\n"
                f"Vừa săn được em '{item_name}' này giá sale cực sốc {addr} ơi:\n"
                f"• Giá sale hôm nay: {price_sale:,}đ (Gốc: {price_orig:,}đ - Giảm {discount}%)\n"
                f"• Lượt bán: {sold:,} | Đánh giá: {rating}⭐\n\n"
                f"Shop chính hãng Shopee Mall, nhớ áp thêm mã giảm giá và Freeship lúc thanh toán {p}!\n"
                f"👉 Link lấy deal chính hãng: {tracking_url}\n\n"
                f"#dealhot #sansale #shopee #flashsale #giare"
            )
        elif tpl_idx == 2:
            content = (
                f"Deal ngon bổ rẻ cho {addr} hôm nay {p} 🏷️\n\n"
                f"Món '{item_name}' đang sale sập sàn từ {price_orig:,}đ còn đúng {price_sale:,}đ.\n"
                f"Hơn {sold:,} người đã chốt đơn uy tín. Bác nào cần thì tranh thủ múc sớm {p}:\n\n"
                f"🔗 Link đặt mua: {tracking_url}\n\n"
                f"#sansale #dealngon #shopeevn #khuyenmai"
            )
        elif tpl_idx == 3:
            content = (
                f"Bác nào đang tìm '{item_name}' thì vào gắp liền tay {p} ⚡\n\n"
                f"Shopee Mall đang xả kho giảm {discount}%, chỉ còn {price_sale:,}đ thôi {p}.\n"
                f"Hàng chính hãng chuẩn chỉ, đánh giá {rating} sao chất lượng.\n\n"
                f"👉 Link gian hàng ưu đãi: {tracking_url}\n\n"
                f"#giamgia #dealshock #freeship #shopee"
            )
        else:
            content = (
                f"Góc chia sẻ deal hời: Em '{item_name}' đang giảm chạm đáy {p} 👇\n\n"
                f"• Giá flash sale: {price_sale:,}đ (Tiết kiệm {price_orig - price_sale:,}đ)\n"
                f"• {sold:,} lượt mua kiểm chứng chất lượng\n"
                f"Nhớ lưu voucher tại giỏ hàng trước khi bấm thanh toán {p}!\n"
                f"🔗 Link chốt đơn: {tracking_url}\n\n"
                f"#dealhot #muasamsale #shopeemall"
            )
        return content, tpl_id

    # =========================================================================
    # CORE COMPOSER VỚI XOAY VÒNG TEMPLATE & CHECK ĐỘ TRÙNG LẶP DƯỚI 80%
    # =========================================================================

    def compose_post_for_group(
        self,
        deal: Dict,
        group: Dict,
        max_attempts: int = 5
    ) -> Dict:
        """
        Tạo bài đăng độc nhất cho nhóm Facebook:
        - Xoay vòng template khác với template đã dùng gần nhất (last_template_id).
        - Kiểm tra độ trùng lặp với lịch sử gần đây của nhóm (ngưỡng 80%).
        - Nếu trùng lặp > 80%, tự động sinh lại với template hoặc biến thể khác.
        - Trả về: {"content": str, "template_id": str, "content_hash": str, "similarity_score": float, "tracking_url": str}
        """
        group_id = str(group.get("group_id", ""))
        group_name = group.get("name", "")
        group_cat = group.get("category_name", "Cộng Đồng Chung")

        tracking_url = self._build_tracking_url(deal, group)

        # Lấy template_id đã dùng lần trước để tránh trùng lặp liên tiếp
        last_tpl_id = ""
        recent_posts = []
        if self.db:
            try:
                last_tpl_id = self.db.get_group_last_template_id(group_id)
                recent_posts = self.db.get_recent_post_contents_for_group(group_name, limit=8)
            except Exception:
                pass

        # Xác định render function theo category
        cat_match = self.matcher.match_group(group_cat=group_cat, group_name=group_name)
        rule = cat_match.get("rule", {})
        matched_cat = rule.get("category_name", "")

        if matched_cat == "Thời Trang Nam":
            renderer = self._render_fashion_men
        elif matched_cat in ("Thời Trang Nữ", "Sắc Đẹp"):
            renderer = self._render_fashion_women
        elif matched_cat == "Thiết Bị Điện Tử":
            renderer = self._render_electronics
        else:
            renderer = self._render_general

        total_templates = 4
        # Lọc danh sách template IDs khả dụng, ưu tiên khác last_tpl_id
        tpl_indices = list(range(1, total_templates + 1))
        random.shuffle(tpl_indices)

        # A/B Testing Auto-Select: Nếu có template có CTR cao nhất trong quá khứ cho ngành hàng này, đưa lên đầu ưu tiên
        cat_prefix = "MEN_TPL" if matched_cat == "Thời Trang Nam" else (
            "WOMEN_TPL" if matched_cat in ("Thời Trang Nữ", "Sắc Đẹp") else (
                "TECH_TPL" if matched_cat == "Thiết Bị Điện Tử" else "GEN_TPL"
            )
        )
        best_past_idx = self.get_best_performing_template(cat_prefix)
        if best_past_idx and best_past_idx in tpl_indices:
            tpl_indices.remove(best_past_idx)
            tpl_indices.insert(0, best_past_idx)

        best_content = ""
        best_tpl_id = ""
        best_tracking_url = ""
        min_sim_score = 1.0

        for attempt in range(max_attempts):
            idx = tpl_indices[attempt % len(tpl_indices)]
            expected_tpl_id = self._get_tpl_id(matched_cat, idx)
            current_tracking_url = self._build_tracking_url(deal, group, expected_tpl_id)
            content, tpl_id = renderer(deal, group, current_tracking_url, idx)

            # Kiểm tra trùng lặp với bài đăng trước đó
            if recent_posts:
                is_dup, max_sim, _ = ContentDeduplicator.is_similar_to_history(
                    content, recent_posts, threshold=0.80
                )
            else:
                is_dup, max_sim = False, 0.0

            if max_sim < min_sim_score:
                min_sim_score = max_sim
                best_content = content
                best_tpl_id = tpl_id
                best_tracking_url = current_tracking_url

            # Nếu không trùng lặp và khác template lần trước -> chấp nhận ngay
            if not is_dup and (not last_tpl_id or tpl_id != last_tpl_id):
                best_content = content
                best_tpl_id = tpl_id
                best_tracking_url = current_tracking_url
                min_sim_score = max_sim
                break

        # Cập nhật template_id đã dùng cho nhóm
        if self.db and best_tpl_id:
            try:
                self.db.update_group_last_template_id(group_id, best_tpl_id)
            except Exception:
                pass

        content_hash = ContentDeduplicator.hash_content(best_content)

        return {
            "content": best_content,
            "template_id": best_tpl_id,
            "content_hash": content_hash,
            "similarity_score": min_sim_score,
            "tracking_url": best_tracking_url or tracking_url
        }
