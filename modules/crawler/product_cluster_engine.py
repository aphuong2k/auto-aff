"""
Product Recognizer & Clustering Engine
======================================
Hệ thống tự động nhận diện, làm sạch và gom các tin đăng cùng một sản phẩm:
- Bóc tách tên sản phẩm, thương hiệu, model và giá bán từ tin rao bán (Telegram / mạng xã hội)
- Chuẩn hóa tiếng Việt không dấu và từ khóa cốt lõi (Cluster Key)
- Gom các bài đăng cùng sản phẩm vào 1 cụm (Cluster)
- Tính toán Giá trung bình (avg_price) và Giá tham chiếu thị trường (reference_price)
"""

import re
import statistics
import unicodedata
from typing import List, Dict, Tuple, Optional


class ProductClusterEngine:
    """Bộ máy gom nhóm sản phẩm & tính giá tham chiếu thị trường"""

    # Các từ rác/quảng cáo thường gặp trong tin đăng bán
    STOP_WORDS = [
        "chính hãng", "chinh hang", "fullbox", "full box", "like new", "likenew",
        "new seal", "nguyên seal", "nguyen seal", "bảo hành", "bao hanh",
        "freeship", "free ship", "thanh lý", "thanh ly", "pass lại", "pass lai",
        "cần bán", "can ban", "xả kho", "xa kho", "giá sốc", "gia soc",
        "siêu rẻ", "sieu re", "hot deal", "hot sale", "cực hot", "nhanh tay",
        "hàng sẵn", "hang san", "ship cod", "cod toàn quốc", "auth", "authentic",
        "bao test", "hàng mới", "hang moi", "đập hộp", "dap hop", "bán gấp"
    ]

    @classmethod
    def remove_vietnamese_accents(cls, text: str) -> str:
        """Chuyển chuỗi tiếng Việt có dấu thành không dấu để chuẩn hóa so sánh"""
        if not text:
            return ""
        text = unicodedata.normalize("NFD", text)
        text = re.sub(r"[\u0300-\u036f]", "", text)
        text = text.replace("đ", "d").replace("Đ", "d")
        return text.lower().strip()

    @classmethod
    def extract_price_vnd(cls, text: str) -> Optional[float]:
        """
        Trích xuất giá tiền từ văn bản tiếng Việt:
        Hỗ trợ các định dạng:
        - '450k', '450 k', '450K' -> 450,000
        - '1tr2', '1tr200', '1.2tr', '1,2 triệu' -> 1,200,000
        - '2tr', '2 triệu' -> 2,000,000
        - '350.000đ', '350,000 vnđ', '350000' -> 350,000
        - 'chỉ 99k', 'pass 150k'
        """
        if not text:
            return None

        clean_text = text.lower()

        # 1. Tìm mẫu triệu lẻ (vd: 1tr2, 1tr350, 2tr5)
        m_tr_le = re.search(r"(\d+)\s*(?:tr|trieu|triệu)\s*(\d{1,3})(?:k|\b)", clean_text)
        if m_tr_le:
            base_tr = int(m_tr_le.group(1)) * 1_000_000
            dec_str = m_tr_le.group(2)
            if len(dec_str) == 1:
                sub_val = int(dec_str) * 100_000
            elif len(dec_str) == 2:
                sub_val = int(dec_str) * 10_000
            else:
                sub_val = int(dec_str) * 1_000
            return float(base_tr + sub_val)

        # 2. Tìm mẫu triệu thập phân (vd: 1.5tr, 1,2 triệu)
        m_tr_dec = re.search(r"(\d+[.,]\d+)\s*(?:tr|trieu|triệu)", clean_text)
        if m_tr_dec:
            num = float(m_tr_dec.group(1).replace(",", "."))
            return round(num * 1_000_000, 0)

        # 3. Tìm mẫu triệu tròn (vd: 2tr, 3 triệu)
        m_tr = re.search(r"(\d+)\s*(?:tr|trieu|triệu)\b", clean_text)
        if m_tr:
            return float(int(m_tr.group(1)) * 1_000_000)

        # 4. Tìm mẫu nghìn có đuôi k (vd: 450k, 99 k, 1200k)
        m_k = re.search(r"(\d+(?:[.,]\d+)?)\s*k\b", clean_text)
        if m_k:
            num = float(m_k.group(1).replace(",", "."))
            return round(num * 1_000, 0)

        # 5. Tìm số đầy đủ kèm ký hiệu tiền (vd: 350.000đ, 500,000 đ, 250000 vnd)
        m_vnd = re.search(r"(\d{1,3}(?:[.,]\d{3})+|\d{4,9})\s*(?:đ|d|vnd|vnđ|dong|đồng)\b", clean_text)
        if m_vnd:
            raw_num = re.sub(r"[^\d]", "", m_vnd.group(1))
            val = float(raw_num)
            if 1_000 <= val <= 200_000_000:
                return val

        # 6. Tìm cụm từ 'giá: 450000' hoặc 'pass: 350000'
        m_gia = re.search(r"(?:giá|gia|pass|bán|ban)\s*[:=-]?\s*(\d{4,9})\b", clean_text)
        if m_gia:
            val = float(m_gia.group(1))
            if 1_000 <= val <= 200_000_000:
                return val

        return None

    @classmethod
    def clean_product_title(cls, raw_title: str) -> str:
        """Làm sạch tiêu đề tin đăng, loại bỏ links, tags, emoji và stop words"""
        if not raw_title:
            return ""

        # Bỏ URLs và liên kết Telegram
        text = re.sub(r"https?://\S+|t\.me/\S+", "", raw_title)
        # Bỏ số điện thoại
        text = re.sub(r"0\d{8,10}", "", text)
        # Bỏ hashtag
        text = re.sub(r"#\w+", "", text)
        # Bỏ các cụm giá đã bóc tách (vd: 1tr2, 2tr5, 450k, 350.000đ...)
        text = re.sub(r"\d+\s*(?:tr|trieu|triệu)\s*\d+\b", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\d+(?:[.,]\d+)?\s*(?:k|tr|triệu|đ|vnd|vnđ|nghìn|ngàn)\b", "", text, flags=re.IGNORECASE)
        # Bỏ chỉ dẫn size phụ (vd: size 42, sz 40, size M, size XL...)
        text = re.sub(r"\b(?:size|sz)\s*(?:\d+|[smlxlxxl]+)\b", "", text, flags=re.IGNORECASE)
        # Bỏ từ 'giá' độc lập hoặc 'pass', 'bán' ở đầu/cuối
        text = re.sub(r"\b(?:giá|gia|giá bán|pass|bán|cần bán|thanh lý|mới mua|được tặng|chưa dùng|1 tuần|hôm qua)\b", "", text, flags=re.IGNORECASE)
        # Bỏ ký tự đặc biệt thừa
        text = re.sub(r"[\[\]\(\)\{\}\*\|\+\=~`!@#\$%\^&;:<>\?/\\]", " ", text)

        # Bỏ stop words
        clean_no_acc = cls.remove_vietnamese_accents(text)
        for sw in cls.STOP_WORDS:
            sw_no_acc = cls.remove_vietnamese_accents(sw)
            if sw_no_acc in clean_no_acc:
                text = re.sub(r"\b" + re.escape(sw) + r"\b", "", text, flags=re.IGNORECASE)
                clean_no_acc = cls.remove_vietnamese_accents(text)

        # Chuẩn hóa khoảng trắng và gọt đầu gọt đuôi
        cleaned = re.sub(r"\s+", " ", text).strip(" -:,.")
        return cleaned[:100]

    @classmethod
    def generate_cluster_key(cls, product_name: str) -> str:
        """
        Tạo Khóa Cụm (Cluster Key) chuẩn hóa để gom nhóm các tin đăng cùng sản phẩm:
        - Chuyển sang không dấu
        - Tách các từ quan trọng (giữ các số đơn như 1 trong Air Force 1)
        - Trích xuất tên thương hiệu + model số (vd: aula f75, dareu ek87, iphone 15 pro max)
        """
        no_acc = cls.remove_vietnamese_accents(product_name)
        # Loại bỏ các từ quá chung chung
        generic_words = {
            "ban", "mua", "can", "cai", "chiec", "con", "bo", "em", "hang", "san",
            "pham", "tot", "dep", "gia", "re", "sale", "deal", "chinh", "hang",
            "ngay", "nay", "moi", "cu", "thanh", "ly", "tuan", "tang", "size", "sz"
        }
        tokens = [t for t in re.split(r"[^\w\d]+", no_acc) if (len(t) > 1 or t.isdigit()) and t not in generic_words]

        if not tokens:
            return "general_product"

        # Nhận diện cặp Brand + Model (vd: aula + f75, sony + wh1000xm4)
        # Sắp xếp các token chứa số hoặc viết hoa trước, các token định danh
        model_tokens = [t for t in tokens if any(c.isdigit() for c in t)]
        brand_tokens = [t for t in tokens if not any(c.isdigit() for c in t)]

        # Ghép các token cốt lõi
        sorted_tokens = model_tokens + brand_tokens[:6]
        return "_".join(sorted_tokens[:6])

    @classmethod
    def calculate_similarity(cls, key1: str, key2: str) -> float:
        """Tính độ tương đồng Jaccard giữa 2 cụm từ khóa"""
        set1 = set(key1.split("_"))
        set2 = set(key2.split("_"))
        if not set1 or not set2:
            return 0.0

        # Kiểm tra nếu cả 2 đều có model number (chứa số) và trùng model number
        models1 = {t for t in set1 if any(c.isdigit() for c in t)}
        models2 = {t for t in set2 if any(c.isdigit() for c in t)}
        if models1 and models2 and (models1.intersection(models2)):
            # Cùng model (vd: f75, 1000xm4, ek87, g102), chỉ cần thêm 1 từ thương hiệu/chủng loại là cùng cụm
            common_words = set1.intersection(set2)
            if len(common_words) >= 2:
                return 0.85

        intersection = len(set1.intersection(set2))
        union = len(set1.union(set2))
        return intersection / union if union > 0 else 0.0

    @classmethod
    def cluster_messages(
        cls,
        raw_items: List[Dict],
        similarity_threshold: float = 0.55
    ) -> List[Dict]:
        """
        Gom nhóm danh sách tin đăng sản phẩm (từ Telegram hoặc từ khóa):
        Mỗi raw_item có thể có: {"text": str, "title": str, "price": Optional[float], "source": str}

        Đầu ra trả về danh sách các cụm:
        [
            {
                "cluster_key": str,
                "product_name": str,
                "reference_price": float, # Giá tham chiếu (Median hoặc Baseline giá)
                "avg_price": float,       # Giá trung bình
                "min_price": float,
                "max_price": float,
                "sample_count": int,
                "source_samples": List[Dict]
            }, ...
        ]
        """
        clusters: List[Dict] = []

        for item in raw_items:
            raw_text = item.get("text") or item.get("title") or item.get("name") or ""
            if not raw_text.strip():
                continue

            # 1. Trích xuất hoặc lấy giá có sẵn
            price = item.get("price")
            if price is None or price <= 0:
                price = cls.extract_price_vnd(raw_text)

            # 2. Làm sạch tiêu đề
            cleaned_title = cls.clean_product_title(raw_text)
            if not cleaned_title or len(cleaned_title) < 3:
                cleaned_title = raw_text[:60]

            cluster_key = cls.generate_cluster_key(cleaned_title)

            # 3. Tìm cụm tương đồng đã có
            matched_cluster = None
            for c in clusters:
                if c["cluster_key"] == cluster_key:
                    matched_cluster = c
                    break
                sim = cls.calculate_similarity(c["cluster_key"], cluster_key)
                if sim >= similarity_threshold:
                    matched_cluster = c
                    break

            sample_entry = {
                "raw_text": raw_text[:120],
                "cleaned_title": cleaned_title,
                "price": price or 0.0,
                "source": item.get("source", "Telegram")
            }

            if matched_cluster:
                matched_cluster["samples"].append(sample_entry)
                if price and price > 0:
                    matched_cluster["prices"].append(price)
                # Giữ tên sản phẩm nào dài và chi tiết hơn
                if len(cleaned_title) > len(matched_cluster["product_name"]):
                    matched_cluster["product_name"] = cleaned_title
            else:
                clusters.append({
                    "cluster_key": cluster_key,
                    "product_name": cleaned_title,
                    "samples": [sample_entry],
                    "prices": [price] if (price and price > 0) else []
                })

        # 4. Tính toán giá tham chiếu và giá trung bình cho từng cụm
        results = []
        for c in clusters:
            prices = c["prices"]
            if prices:
                avg_price = round(sum(prices) / len(prices), 0)
                # Giá tham chiếu sử dụng Median (Trung vị) để loại bỏ giá ảo/bất thường
                ref_price = round(statistics.median(prices), 0)
                min_price = min(prices)
                max_price = max(prices)
            else:
                # Nếu không có giá nào bóc tách được (vd chỉ có từ khóa người dùng nhập)
                avg_price = 0.0
                ref_price = 0.0
                min_price = 0.0
                max_price = 0.0

            results.append({
                "cluster_key": c["cluster_key"],
                "product_name": c["product_name"],
                "category_name": "Đa ngành",
                "reference_price": ref_price,
                "avg_price": avg_price,
                "min_price": min_price,
                "max_price": max_price,
                "sample_count": len(c["samples"]),
                "source_samples": c["samples"]
            })

        # Sắp xếp các cụm có nhiều tin đăng nhất lên đầu
        results.sort(key=lambda x: (x["sample_count"], x["reference_price"]), reverse=True)
        return results
