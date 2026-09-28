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
        "tech": ["anh em", "mọi người", "bác nào", "cả nhà", "dân công nghệ", "mn", "các đồng bo"],
        "beauty": ["chị em", "các nàng", "cả nhà mình", "hội mê skincare", "chị em mình", "mn"],
        "home": ["cả nhà", "mọi người", "hội yêu bếp", "hội nghiện nhà", "các bác", "mn"],
        "mom": ["các mom", "các mẹ", "mẹ bỉm", "hội mẹ bỉm", "mọi người", "mn"],
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
    - Đa dạng kịch bản: Review có tâm, Săn flash sale, So sánh hàng chợ vs Mall,
      Pass deal gom chung, Hỏi ý kiến thảo luận, Giải pháp nỗi đau.
    - Hỗ trợ chuyên sâu các ngành: Thời Trang Nam, Nữ, Công Nghệ, Gia Dụng, Mỹ Phẩm, Mẹ & Bé, Tổng Hợp.
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
        elif matched_cat == "Thời Trang Nữ":
            return f"WOMEN_TPL_{idx}"
        elif matched_cat in ("Sắc Đẹp", "Mỹ Phẩm"):
            return f"BEAUTY_TPL_{idx}"
        elif matched_cat in ("Nhà Cửa & Đời Sống", "Thiết Bị Điện Gia Dụng"):
            return f"HOME_TPL_{idx}"
        elif matched_cat in ("Mẹ & Bé", "Mẹ và Bé"):
            return f"BABY_TPL_{idx}"
        elif matched_cat == "Thiết Bị Điện Tử":
            return f"TECH_TPL_{idx}"
        return f"GEN_TPL_{idx}"

    def get_best_performing_template(self, category_prefix: str) -> Optional[int]:
        """Lấy chỉ số template (1..6) có tỷ lệ click cao nhất trong quá khứ cho ngành hàng"""
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
    # DANH SÁCH TEMPLATE XOAY VÒNG THEO TỪNG DANH MỤC & KỊCH BẢN ĐA DẠNG
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
        elif tpl_idx == 4:
            content = (
                f"Review nhanh cho {addr} con '{item_name}' cực đáng tiền trong tầm giá {p} ⚡\n\n"
                f"• Giá sale cực sốc: {price_sale:,}đ (Tiết kiệm {price_orig - price_sale:,}đ)\n"
                f"• Đánh giá uy tín: {rating}/5.0 sao từ {sold:,} người mua trước\n\n"
                f"{addr} nhớ bỏ sẵn vào giỏ hàng rồi áp mã vận chuyển để được freeship tận nhà {p}.\n"
                f"🔗 Link chính hãng đây {p}: {tracking_url}\n\n"
                f"#thoitrangnam #dealngon #shopee"
            )
        elif tpl_idx == 5:
            # Kịch bản so sánh hàng chợ vs hàng xịn Mall
            content = (
                f"Kinh nghiệm xương máu của em chia sẻ thật lòng cho {addr} {p} ⚠️\n\n"
                f"Trước hay ham rẻ mua mấy món trôi nổi vài chục ngàn giặt đúng 1 nước là xù lông, bai dão form. "
                f"Đợt này đổi sang em '{item_name}' bên shop Mall chính hãng mặc sướng hẳn, đường may kỹ càng.\n\n"
                f"Nay lướt thấy Mall đang xả kho sale từ {price_orig:,}đ còn đúng {price_sale:,}đ (-{discount}%).\n"
                f"Đã có {sold:,} anh em kiểm chứng {rating}⭐, bác nào cần đồ bền đẹp mặc lâu dài thì tranh thủ múc:\n"
                f"👉 Link Mall chính hãng: {tracking_url}\n\n"
                f"#kinhnghiemmuado #thoitrangnam #hangchinhhang #shopeemall"
            )
        else:
            # Kịch bản hỏi ý kiến / thảo luận tương tác cao
            content = (
                f"Có bác nào trong nhóm mình đang dùng em '{item_name}' này chưa ạ? Cho em xin ít review thực tế với {p} 🤔\n\n"
                f"Thấy đánh giá {rating} sao với hơn {sold:,} lượt bán khủng bên Shopee Mall. "
                f"Nay đang có mã Flash Sale giảm sâu còn {price_sale:,}đ (gốc tận {price_orig:,}đ) nên em tính làm 1-2 cái.\n\n"
                f"Bác nào cũng đang ngắm thì nghía chung deal này nhé:\n"
                f"🔗 Link gian hàng Mall đây ạ: {tracking_url}\n\n"
                f"#hoiykien #reviewthoitrang #gocmuasam #dealnam"
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
        elif tpl_idx == 4:
            content = (
                f"Deal hời cho {addr} tút tát phong cách đây {p} 🌸\n\n"
                f"Mẫu '{item_name}' hot hit bên Shopee Mall đang sale còn {price_sale:,}đ (-{discount}%).\n"
                f"Chất liệu xịn, lên dáng chuẩn, feedback {rating}⭐ hơn {sold:,} lượt mua.\n"
                f"🔗 Link săn deal hời: {tracking_url}\n\n"
                f"#thoitrangnu #doxinh #giamgia #shopee"
            )
        elif tpl_idx == 5:
            # Kịch bản review thực tế sau 1 tháng trải nghiệm
            content = (
                f"Review có tâm sau gần 1 tháng mặc thử em '{item_name}' này cho {addr} đây {p} 💖\n\n"
                f"Ưu điểm lớn nhất là lên form cực chuẩn, che khuyết điểm tốt và giặt máy không lo phai hay bai xù. "
                f"Lúc trước mua giá gốc hơn {price_orig:,}đ, nay lướt Shopee Mall thấy mở Flash Sale còn có {price_sale:,}đ giật mình luôn.\n\n"
                f"Hơn {sold:,} chị em đã feedback {rating} sao, ai chuẩn bị đi chơi / đi làm thì vợt ngay nhé:\n"
                f"👉 Link Shopee Mall chính hãng: {tracking_url}\n\n"
                f"#reviewcotam #doxinhchupanh #shopeehaul #giasoc"
            )
        else:
            # Kịch bản gom chung / giải pháp hack dáng
            content = (
                f"Cứu tinh cho {addr} nào đang đau đầu tìm đồ hack dáng đi chơi/đi làm đây {p} 💃✨\n\n"
                f"Em '{item_name}' này thiết kế siêu nịnh dáng, chất vải mềm mát rũ nhẹ.\n"
                f"Mall đang chạy đợt trợ giá xả kho: Chỉ {price_sale:,}đ (gốc {price_orig:,}đ - giảm tận {discount}%).\n"
                f"Nhớ bỏ giỏ sớm rồi tick thêm mã miễn phí vận chuyển 0Đ lúc thanh toán nha {addr}!\n\n"
                f"🔗 Link săn sale chính hãng: {tracking_url}\n\n"
                f"#hackdang #thoitrangnu #doxinhgiare #shopeesale"
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
        elif tpl_idx == 4:
            content = (
                f"Phát hiện deal phụ kiện công nghệ ngon cho {addr} {p} 👇\n\n"
                f"Con '{item_name}' chính hãng Mall đang sale sốc còn {price_sale:,}đ.\n"
                f"Độ bền cao, tính năng ổn định vượt tầm giá. Áp thêm mã voucher ví để giảm thêm {p}.\n"
                f"🔗 Link chốt deal Shopee: {tracking_url}\n\n"
                f"#reviewcongnghe #phukienchinhhang #shopee"
            )
        elif tpl_idx == 5:
            # Kịch bản cảnh báo hàng trôi nổi vs Mua hàng Mall chuẩn
            content = (
                f"Cảnh báo {addr} đừng ham mấy món phụ kiện điện tử noname trôi nổi bán ngoài đường nha {p} ⚡🔌\n\n"
                f"Mấy món điện tử dùng lâu ngày hay bị chập chờn, chai pin rất nguy hiểm. "
                f"Ai cần đồ bền bỉ, chuẩn bảo hành hãng thì nghía con '{item_name}' này ở Shopee Mall.\n\n"
                f"• Giá sale sốc hôm nay: {price_sale:,}đ (Giá gốc: {price_orig:,}đ)\n"
                f"• Hơn {sold:,} người dùng đánh giá {rating}/5.0 sao chất lượng thực tế\n"
                f"👉 Link săn sale chính hãng: {tracking_url}\n\n"
                f"#canhbao #hangchinhhang #phukientot #shopeemall"
            )
        else:
            # Kịch bản nâng cấp góc làm việc / setup
            content = (
                f"Review nhanh cho {addr} đang muốn nâng cấp góc làm việc / giải trí tại nhà {p} 🖥️🖱️\n\n"
                f"Vừa tậu con '{item_name}' này về test thử thấy quá hời so với số tiền bỏ ra. "
                f"Thiết kế tinh tế, độ trễ thấp, cắm là nhận ngay không cần cài đặt rườm rà.\n"
                f"Hôm nay Mall đang trợ giá chớp nhoáng còn {price_sale:,}đ (tiết kiệm {price_orig - price_sale:,}đ).\n\n"
                f"🔗 Link Mall chốt deal cho bác nào cần: {tracking_url}\n\n"
                f"#setupbanlamviec #dochoicongnghe #techgear #shopeevn"
            )
        return content, tpl_id

    def _render_home_living(self, deal: Dict, group: Dict, tracking_url: str, tpl_idx: int) -> Tuple[str, str]:
        """Kịch bản chuyên biệt cho nhóm Nhà Cửa & Đời Sống / Gia Dụng / Yêu Bếp / Nghiện Nhà"""
        p = LinguisticPermutator.get_particle()
        addr = LinguisticPermutator.get_addressing("home")
        item_name = deal.get("name", "Đồ gia dụng")
        price_sale = int(deal.get("price_sale", 0))
        price_orig = int(deal.get("price_original", 0))
        discount = deal.get("discount_percent", 0)
        sold = deal.get("historical_sold", 0)
        rating = deal.get("rating_star", 5.0)
        tpl_id = f"HOME_TPL_{tpl_idx}"

        if tpl_idx == 1:
            content = (
                f"Góc Yêu Bếp & Nghiện Nhà chia sẻ món đồ cực tiện cho {addr} {p} 🏡🍳\n\n"
                f"Em '{item_name}' này dùng siêu tiện mà nay đang có đợt Flash Sale trợ giá lớn bên Shopee Mall:\n"
                f"• Giá chốt hôm nay: {price_sale:,}đ (Giá gốc: {price_orig:,}đ - Giảm {discount}%)\n"
                f"• Hơn {sold:,} gia đình đã mua và chấm {rating}⭐ hài lòng\n\n"
                f"Bác nào đang muốn căn bếp/ngôi nhà gọn gàng, tiện nghi hơn thì tranh thủ gom sớm {p}:\n"
                f"👉 Link mua chính hãng Shopee Mall: {tracking_url}\n\n"
                f"#nghiennha #yeubep #dogiadung #nhacuadoisong #shopeemall"
            )
        elif tpl_idx == 2:
            content = (
                f"Cứu cánh cho hội bận rộn không có nhiều thời gian dọn dẹp nội trợ đây {addr} ơi ⏱️✨\n\n"
                f"Từ ngày sắm em '{item_name}' này công việc nhà nhàn tênh, tiết kiệm bao nhiêu thời gian.\n"
                f"Hàng chuẩn hãng, gia công chắc chắn, Mall đang sale chạm đáy chỉ {price_sale:,}đ (gốc {price_orig:,}đ).\n"
                f"Đã có {sold:,} người mua kiểm chứng {rating} sao chất lượng.\n\n"
                f"🔗 Link chốt deal hời: {tracking_url}\n\n"
                f"#meovatnhacua #dogiadungthongminh #nhacuatienich #giasale"
            )
        elif tpl_idx == 3:
            content = (
                f"Decor và tân trang lại không gian sống với giá siêu hời cùng {addr} {p} 🪴🌿\n\n"
                f"Mẫu '{item_name}' này để vào góc phòng hay căn bếp trông sang xịn hẳn lên.\n"
                f"Hôm nay Shopee đang có mã trợ giá Flash Sale: Chỉ {price_sale:,}đ (-{discount}%).\n"
                f"Nhớ lấy mã giảm giá 15% và mã Freeship 0Đ tại giỏ hàng trước khi đặt nha {p}!\n\n"
                f"👉 Link xem sản phẩm chi tiết: {tracking_url}\n\n"
                f"#decorphong #nhadep #giadunggiare #shopee"
            )
        elif tpl_idx == 4:
            content = (
                f"Review thật lòng cho {addr}: Mua đồ gia dụng đừng ham đồ nhựa chợ ọp ẹp ⚠️\n\n"
                f"Em này '{item_name}' hoàn thiện dày dặn, chịu nhiệt tốt, dùng bền bỉ cả năm không lo nứt gãy. "
                f"Shop Mall chính hãng đang có đợt trợ giá xả kho rẻ hơn ngày thường rất nhiều:\n"
                f"• Giá sale chỉ còn: {price_sale:,}đ (Tiết kiệm ngay {price_orig - price_sale:,}đ)\n"
                f"• Feedback {rating}/5.0 sao với {sold:,} lượt bán uy tín\n\n"
                f"🔗 Link Mall chính hãng đây {p}: {tracking_url}\n\n"
                f"#dogiadungtot #muasamsale #reviewgiadung #shopeemall"
            )
        elif tpl_idx == 5:
            content = (
                f"Có bác nào trong nhóm mình đang dùng em '{item_name}' này chưa ạ? 👀\n\n"
                f"Thấy mn trong hội khen em này tiện lắm, nay vô tình lướt thấy Flash Sale tụt từ {price_orig:,}đ còn {price_sale:,}đ.\n"
                f"Review hơn {sold:,} lượt mua bảo hàng đóng gói rất kỹ, chuẩn chỉ.\n"
                f"Ai cũng đang ngắm nghía đồ gia dụng thì tham khảo chung deal thơm này nhé:\n"
                f"👉 Link ưu đãi Mall: {tracking_url}\n\n"
                f"#hoinhacua #dogiadung #gocbep #dealhot"
            )
        else:
            content = (
                f"Kèo đồ gia dụng xịn xò cho {addr} sắm sửa nhà cửa hôm nay {p} 🏷️🏠\n\n"
                f"Món '{item_name}' đang có đợt Flash Sale chớp nhoáng: Giảm {discount}% chỉ còn {price_sale:,}đ.\n"
                f"Hàng chính hãng chuẩn chỉ, bảo hành đầy đủ. Áp thêm voucher ví ShopeePay là giá bao rẻ {p}!\n\n"
                f"🔗 Link đặt hàng chính hãng: {tracking_url}\n\n"
                f"#sansalegiadung #nhacuatoiyeu #shopeedeal #freeship"
            )
        return content, tpl_id

    def _render_beauty(self, deal: Dict, group: Dict, tracking_url: str, tpl_idx: int) -> Tuple[str, str]:
        """Kịch bản chuyên biệt cho nhóm Sắc Đẹp / Mỹ Phẩm / Skincare / Makeup"""
        p = LinguisticPermutator.get_particle()
        addr = LinguisticPermutator.get_addressing("beauty")
        item_name = deal.get("name", "Mỹ phẩm")
        price_sale = int(deal.get("price_sale", 0))
        price_orig = int(deal.get("price_original", 0))
        discount = deal.get("discount_percent", 0)
        sold = deal.get("historical_sold", 0)
        rating = deal.get("rating_star", 5.0)
        tpl_id = f"BEAUTY_TPL_{tpl_idx}"

        if tpl_idx == 1:
            content = (
                f"Góc Skincare & Làm Đẹp chuẩn y khoa cho {addr} đây {p} 💄✨\n\n"
                f"Em '{item_name}' này thuộc hàng best-seller, dùng dịu nhẹ không hề kích ứng da.\n"
                f"• Giá gốc: {price_orig:,}đ ➡️ Đang Flash Sale Mall còn: {price_sale:,}đ (-{discount}%)\n"
                f"• Hơn {sold:,} người dùng đánh giá {rating}⭐ cực nhiều feedback thật\n\n"
                f"Chị em tranh thủ đợt sale này trữ sẵn chăm sóc da nha {p}:\n"
                f"👉 Link Shopee Mall chính hãng: {tracking_url}\n\n"
                f"#skincare #duongda #myphamchinhhang #shopeemall #lamdep"
            )
        elif tpl_idx == 2:
            content = (
                f"Cảnh báo {addr} đừng mua mỹ phẩm trôi nổi giá bèo ngoài đường hại da nha ⚠️🌸\n\n"
                f"Đồ bôi lên mặt cứ chọn thẳng gian hàng Mall chính hãng cho yên tâm 100%. "
                f"Em '{item_name}' này shop Mall đang có mã trợ giá cực hời: Chỉ {price_sale:,}đ (gốc {price_orig:,}đ).\n"
                f"Hơn {sold:,} người mua chứng thực chất lượng {rating}/5.0 sao.\n\n"
                f"🔗 Link Mall chính hãng phân phối tại đây {p}: {tracking_url}\n\n"
                f"#myphamchuanauth #chamsocda #reviewskincare #shopee"
            )
        elif tpl_idx == 3:
            content = (
                f"Review chân thật sau gần 3 tuần trải nghiệm em '{item_name}' cho {addr} 💖\n\n"
                f"Cảm nhận rõ rệt là chất mịn thấm nhanh, không bết dính tí nào. "
                f"Trước mình mua đắt hơn nhiều, nay thấy Shopee Mall Flash Sale còn đúng {price_sale:,}đ nên share vội cho mn.\n\n"
                f"Nhớ bỏ giỏ rồi lấy thêm voucher Freeship 0Đ áp lúc thanh toán nha:\n"
                f"👉 Link ưu đãi Mall chính hãng: {tracking_url}\n\n"
                f"#reviewmypham #routineduongda #goclamdep #dealhot"
            )
        elif tpl_idx == 4:
            content = (
                f"Deal mỹ phẩm xinh xỉu cho {addr} tút tát nhan sắc hôm nay {p} 💋✨\n\n"
                f"Mẫu '{item_name}' hot rần rần trên TikTok nay Shopee Mall giảm tận {discount}%, chỉ còn {price_sale:,}đ.\n"
                f"Lên tone cực tự nhiên, hợp mọi loại da. Đã có {sold:,} lượt chốt đơn uy tín.\n\n"
                f"🔗 Link săn deal chính hãng: {tracking_url}\n\n"
                f"#makeuptutorial #sonmoi #kemduong #sansaleshopee"
            )
        elif tpl_idx == 5:
            content = (
                f"Chị em mình trong nhóm có ai đang xài em '{item_name}' này không cho em xin review với {p} 🥰\n\n"
                f"Thấy feedback khen nức nở với hơn {sold:,} lượt mua 5 sao. "
                f"Đặc biệt hôm nay đang Flash Sale giảm từ {price_orig:,}đ xuống còn {price_sale:,}đ hời quá định múc luôn.\n"
                f"Nàng nào cũng đang tìm món này thì nghía chung nhé:\n"
                f"👉 Link Shopee Mall: {tracking_url}\n\n"
                f"#hoimypham #gocchamsocda #lamdepmoingay #shopeevn"
            )
        else:
            content = (
                f"Mách nhỏ {addr} deal skincare giá học sinh sinh viên nhưng chất lượng chuẩn auth {p} 🌸🌿\n\n"
                f"Em '{item_name}' đang sale chạm đáy còn đúng {price_sale:,}đ (tiết kiệm {price_orig - price_sale:,}đ).\n"
                f"Bác nào da dầu mụn hay nhạy cảm thì em này là chân ái luôn đấy ạ.\n\n"
                f"🔗 Link đặt mua chính hãng: {tracking_url}\n\n"
                f"#danhchodamun #skincaregiare #hangauth #shopeesale"
            )
        return content, tpl_id

    def _render_mom_baby(self, deal: Dict, group: Dict, tracking_url: str, tpl_idx: int) -> Tuple[str, str]:
        """Kịch bản chuyên biệt cho nhóm Mẹ & Bé / Hội Mẹ Bỉm Sữa"""
        p = LinguisticPermutator.get_particle()
        addr = LinguisticPermutator.get_addressing("mom")
        item_name = deal.get("name", "Đồ mẹ và bé")
        price_sale = int(deal.get("price_sale", 0))
        price_orig = int(deal.get("price_original", 0))
        discount = deal.get("discount_percent", 0)
        sold = deal.get("historical_sold", 0)
        rating = deal.get("rating_star", 5.0)
        tpl_id = f"BABY_TPL_{tpl_idx}"

        if tpl_idx == 1:
            content = (
                f"Góc Mẹ Bỉm Thông Thái: Chăm con nhàn tênh cùng {addr} {p} 👶🍼\n\n"
                f"Chia sẻ với các mẹ em '{item_name}' này dùng siêu tiện lợi, an toàn tuyệt đối cho bé yêu.\n"
                f"• Giá gốc: {price_orig:,}đ ➡️ Đang Flash Sale Mall còn: {price_sale:,}đ (-{discount}%)\n"
                f"• Hơn {sold:,} mẹ bỉm đã mua và đánh giá {rating}⭐ cực tốt\n\n"
                f"Các mẹ tranh thủ đợt sale này gom sẵn đồ cho con vừa tiết kiệm vừa an tâm nha {p}:\n"
                f"👉 Link Shopee Mall chính hãng: {tracking_url}\n\n"
                f"#mebimthongthai #chamsocconyeu #dometre #shopeemall"
            )
        elif tpl_idx == 2:
            content = (
                f"Đồ cho con nhỏ cứ chọn đúng gian hàng Mall chính hãng cho an tâm 100% các mom ơi 🧸✨\n\n"
                f"Em '{item_name}' chất liệu an toàn, nguồn gốc rõ ràng, không gây kích ứng cho bé.\n"
                f"Shop Mall đang có trợ giá giảm sâu: Chỉ còn {price_sale:,}đ (gốc {price_orig:,}đ).\n"
                f"Hơn {sold:,} mom đã đặt mua và feedback cực hài lòng.\n\n"
                f"🔗 Link mua chính hãng cho các bé: {tracking_url}\n\n"
                f"#chamsocbesosinh #mebe #dochoiantoan #shopeevn"
            )
        elif tpl_idx == 3:
            content = (
                f"Bí kíp tiết kiệm tiền bỉm sữa hàng tháng cho {addr} đây {p} 💰🤱\n\n"
                f"Cứ canh đúng đợt Flash Sale Mall mà mua em '{item_name}' này là tiết kiệm được cả mớ tiền.\n"
                f"Hôm nay sale còn đúng {price_sale:,}đ (tiết kiệm ngay {price_orig - price_sale:,}đ so với giá niêm yết).\n"
                f"Các mom nhớ áp thêm mã miễn phí vận chuyển 0Đ lúc thanh toán nhé:\n\n"
                f"👉 Link săn sale cho bé: {tracking_url}\n\n"
                f"#tietkiemtientieudung #bimsua #sansalemebe #shopee"
            )
        elif tpl_idx == 4:
            content = (
                f"Review thật lòng cho các mom: Món '{item_name}' này mua 1 lần dùng mãi cực bền 🌟\n\n"
                f"Bé nhà mình dùng thích lắm, đường nét bo tròn cẩn thận. "
                f"Shop Mall đang chạy chương trình khuyến mại lớn: Giảm {discount}% chỉ còn {price_sale:,}đ.\n"
                f"Feedback {rating} sao từ {sold:,} phụ huynh đã trải nghiệm thực tế.\n\n"
                f"🔗 Link chốt đơn Mall chính hãng: {tracking_url}\n\n"
                f"#reviewdometre #bimsuachinhhang #mebimsua #dealhot"
            )
        elif tpl_idx == 5:
            content = (
                f"Có mom nào trong nhóm mình đang cho bé dùng món '{item_name}' này chưa ạ? 🍼👶\n\n"
                f"Thấy các mẹ trên diễn đàn khen nhiều quá, nay lướt Shopee thấy Flash Sale giảm từ {price_orig:,}đ còn {price_sale:,}đ.\n"
                f"Mẹ nào cũng đang cần sắm đồ cho con thì tham khảo chung deal hời này nha:\n"
                f"👉 Link ưu đãi tại đây ạ: {tracking_url}\n\n"
                f"#hoimebim #chamsoccon #dososinh #shopeedeal"
            )
        else:
            content = (
                f"Deal hời cho bé yêu - Giải tỏa áp lực chi tiêu cho {addr} hôm nay {p} 💕🧸\n\n"
                f"Món '{item_name}' chính hãng Shopee Mall đang sale chạm đáy: Chỉ {price_sale:,}đ.\n"
                f"Chất lượng chuẩn y khoa, đóng gói cẩn thận. Các mom tranh thủ múc kẻo hết mã trợ giá {p}!\n\n"
                f"🔗 Link đặt mua chính hãng: {tracking_url}\n\n"
                f"#yeucon #mebimthoitrang #dometreem #freeship"
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
        elif tpl_idx == 4:
            content = (
                f"Góc chia sẻ deal hời: Em '{item_name}' đang giảm chạm đáy {p} 👇\n\n"
                f"• Giá flash sale: {price_sale:,}đ (Tiết kiệm {price_orig - price_sale:,}đ)\n"
                f"• {sold:,} lượt mua kiểm chứng chất lượng\n"
                f"Nhớ lưu voucher tại giỏ hàng trước khi bấm thanh toán {p}!\n"
                f"🔗 Link chốt đơn: {tracking_url}\n\n"
                f"#dealhot #muasamsale #shopeemall"
            )
        elif tpl_idx == 5:
            # Kịch bản gom chung / xả kho chớp nhoáng
            content = (
                f"Kèo hời không thể bỏ lỡ cho {addr} hôm nay: Em '{item_name}' Mall vừa mở kho sale chớp nhoáng ⚡💥\n\n"
                f"Giá tụt từ {price_orig:,}đ xuống còn đúng {price_sale:,}đ (-{discount}%).\n"
                f"Đã có hơn {sold:,} người mua thực tế với đánh giá {rating}/5.0 sao chuẩn xịn.\n"
                f"Tranh thủ chốt sớm kẻo hết lượt trợ giá nha cả nhà {p}!\n\n"
                f"👉 Link đặt mua trực tiếp: {tracking_url}\n\n"
                f"#keothom #sansaleshopee #xakho #dealngon"
            )
        else:
            # Kịch bản đánh giá khách quan
            content = (
                f"Lướt sàn thấy con '{item_name}' này đang lọt top bán chạy nhất hôm nay share cho {addr} {p} 📈✨\n\n"
                f"• Đã bán: {sold:,} đơn | Điểm đánh giá: {rating}⭐\n"
                f"• Giá sale sốc: {price_sale:,}đ (Rẻ hơn ngày thường {price_orig - price_sale:,}đ)\n"
                f"Hàng chính hãng phân phối, mua về dùng hay làm quà đều cực hợp lý {p}.\n\n"
                f"🔗 Link gian hàng chính hãng: {tracking_url}\n\n"
                f"#topbanchay #shopeehaul #muasamthongminh #dealhot"
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
                last_tpl_id = self.db.get_group_last_template_id(group_id, group_name=group_name)
                recent_posts = self.db.get_recent_post_contents_for_group(group_name, limit=8)
            except Exception:
                try:
                    last_tpl_id = self.db.get_group_last_template_id(group_id)
                except Exception:
                    pass

        # Xác định render function theo category
        cat_match = self.matcher.match_group(group_cat=group_cat, group_name=group_name)
        rule = cat_match.get("rule", {})
        matched_cat = rule.get("category_name", "")

        if matched_cat == "Thời Trang Nam":
            renderer = self._render_fashion_men
            cat_prefix = "MEN_TPL"
        elif matched_cat == "Thời Trang Nữ":
            renderer = self._render_fashion_women
            cat_prefix = "WOMEN_TPL"
        elif matched_cat in ("Sắc Đẹp", "Mỹ Phẩm"):
            renderer = self._render_beauty
            cat_prefix = "BEAUTY_TPL"
        elif matched_cat in ("Nhà Cửa & Đời Sống", "Thiết Bị Điện Gia Dụng"):
            renderer = self._render_home_living
            cat_prefix = "HOME_TPL"
        elif matched_cat in ("Mẹ & Bé", "Mẹ và Bé"):
            renderer = self._render_mom_baby
            cat_prefix = "BABY_TPL"
        elif matched_cat == "Thiết Bị Điện Tử":
            renderer = self._render_electronics
            cat_prefix = "TECH_TPL"
        else:
            renderer = self._render_general
            cat_prefix = "GEN_TPL"

        total_templates = 6
        # Lọc danh sách template IDs khả dụng, ưu tiên khác last_tpl_id
        tpl_indices = list(range(1, total_templates + 1))
        random.shuffle(tpl_indices)

        # Chuyển index của template vừa dùng xuống cuối cùng để xoay vòng 100%
        if last_tpl_id and "_" in last_tpl_id:
            try:
                last_idx = int(last_tpl_id.split("_")[-1])
                if last_idx in tpl_indices and len(tpl_indices) > 1:
                    tpl_indices.remove(last_idx)
                    tpl_indices.append(last_idx)
            except Exception:
                pass

        # A/B Testing Auto-Select: Nếu có template có CTR cao nhất trong quá khứ cho ngành hàng này, đưa lên đầu ưu tiên (nếu không trùng với bài vừa đăng)
        best_past_idx = self.get_best_performing_template(cat_prefix)
        if best_past_idx and best_past_idx in tpl_indices:
            if not last_tpl_id or f"{cat_prefix}_{best_past_idx}" != last_tpl_id:
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
