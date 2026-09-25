import re
import logging
from typing import List, Dict, Optional

from database.db_manager import DatabaseManager
from config.categories_filter import translate_category

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

class GroupKeywordLearner:
    """
    Module tự động học hỏi từ khóa từ tên các Group Facebook đã tìm được.
    Giúp tự động mở rộng chuỗi tìm kiếm (Keyword Expansion) và hỗ trợ phân loại/dịch thuật cho các chu trình sau.
    """

    # Danh sách các từ dừng / từ rác thường gặp trong tên nhóm cần loại bỏ
    STOP_WORDS = {
        "nhóm", "group", "cộng đồng", "hội những người", "hội", "clb", "official",
        "admin", "24/7", "toàn quốc", "hà nội", "tphcm", "sài gòn", "việt nam", "vietnam", "vn",
        "share", "giao lưu", "mua bán", "thanh lý", "chợ", "chính hãng", "uy tín",
        "miễn phí", "tuyển dụng", "bán buôn", "bán sỉ", "giá sỉ", "online", "club"
    }

    # Các từ ngách chuyên sâu đơn lẻ có giá trị cao vẫn giữ lại
    VALUABLE_SINGLE_WORDS = {
        "streetwear", "sneaker", "smartwatch", "camping", "skincare", "figure",
        "vintage", "retro", "decor", "gaming", "unisex", "minimalism", "macbook",
        "iphone", "ipad", "lego", "bếp", "gym", "yoga", "fitness"
    }

    def __init__(self, db: Optional[DatabaseManager] = None):
        self.db = db or DatabaseManager()

    def clean_and_extract_phrases(self, group_name: str) -> List[str]:
        """
        Bóc tách các cụm từ đắt giá từ tên Group Facebook.
        Ví dụ: 'Phối đồ nam đẹp - Streetwear & Vintage Vietnam 2026'
        -> ['phối đồ nam đẹp', 'streetwear', 'vintage']
        """
        if not group_name or not isinstance(group_name, str):
            return []

        # 1. Loại bỏ Emoji và các ký tự đặc biệt trang trí
        text = re.sub(r'[^\w\s\-\–\—\|\•\/\&\,]', ' ', group_name, flags=re.UNICODE)
        
        # 2. Tách theo các ký tự phân cách đoạn phổ biến
        chunks = re.split(r'[\-\–\—\|\•\/\&\,]+', text)
        extracted = []

        for raw_chunk in chunks:
            chunk = raw_chunk.strip().lower()
            if not chunk or len(chunk) < 3:
                continue

            # Tách các từ và lọc bỏ stop words ở đầu / cuối
            words = chunk.split()
            
            # Loại bỏ năm (2023, 2024, 2025, 2026...)
            words = [w for w in words if not (w.isdigit() and len(w) == 4)]
            
            # Lược bỏ từ rác ở đầu cụm (VD: "hội phối đồ nam" -> "phối đồ nam")
            while words and words[0] in self.STOP_WORDS:
                words.pop(0)
            while words and words[-1] in self.STOP_WORDS:
                words.pop()

            if not words:
                continue

            clean_phrase = " ".join(words).strip()
            num_words = len(words)

            # Chỉ giữ các cụm từ có độ dài từ 2 đến 5 từ, hoặc các từ ngách đơn lẻ có giá trị
            if 2 <= num_words <= 5:
                if clean_phrase not in extracted and len(clean_phrase) >= 4:
                    extracted.append(clean_phrase)
            elif num_words == 1 and clean_phrase in self.VALUABLE_SINGLE_WORDS:
                if clean_phrase not in extracted:
                    extracted.append(clean_phrase)
            elif num_words > 5:
                # Nếu cụm từ dài và không có dấu phân cách, bóc tách cụm 2-3 từ có nghĩa
                for window_size in (3, 2):
                    for i in range(len(words) - window_size + 1):
                        sub = words[i:i + window_size]
                        if sub[0] not in self.STOP_WORDS and sub[-1] not in self.STOP_WORDS:
                            sub_phrase = " ".join(sub)
                            if sub_phrase not in extracted and len(sub_phrase) >= 5:
                                extracted.append(sub_phrase)
                                if len(extracted) >= 3:
                                    break
                    if len(extracted) >= 3:
                        break

        return extracted

    def learn_from_group(self, category_name: str, group_name: str) -> List[str]:
        """
        Học các từ khóa từ một nhóm Facebook và lưu vào database.
        """
        vi_category = translate_category(category_name)
        phrases = self.clean_and_extract_phrases(group_name)

        saved = []
        for p in phrases:
            # Lưu vào database, tự động tăng tần suất nếu trùng lặp
            self.db.save_learned_keyword(vi_category, p, group_name)
            saved.append(p)

        if saved:
            logging.info(f"💡 [TỰ HỌC TỪ KHÓA]: Ngành [{vi_category}] học được {len(saved)} cụm từ từ nhóm '{group_name[:30]}...': {saved}")
        return saved

    def get_expanded_keywords(self, category_name: str, limit: int = 5) -> List[str]:
        """
        Lấy danh sách các từ khóa học được tốt nhất của một ngành để mở rộng tìm kiếm.
        """
        vi_category = translate_category(category_name)
        rows = self.db.get_learned_keywords(vi_category, limit=limit)
        return [r["keyword"] for r in rows if r.get("keyword")]

    def seed_from_existing_groups(self) -> int:
        """
        Quét lại toàn bộ các nhóm đã lưu trong database để nạp kho tri thức ban đầu.
        """
        with self.db.get_connection() as conn:
            groups = conn.execute("SELECT name, category_name FROM fb_groups").fetchall()

        total_learned = 0
        for g in groups:
            name = g["name"]
            cat = g["category_name"]
            if name and cat:
                learned = self.learn_from_group(cat, name)
                total_learned += len(learned)

        logging.info(f"🎓 Đã học được tổng cộng {total_learned} từ khóa từ {len(groups)} nhóm hiện có trong DB.")
        return total_learned
