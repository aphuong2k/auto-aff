"""
Config-Driven Category Mapping & Matcher
=========================================
NGUỒN SỰ THẬT DUY NHẤT cho logic khớp Deal ↔ Group Facebook.

Thay thế toàn bộ if-elif hardcode cứng ở:
- modules/workflow/category_router.py
- modules/outreach/fb_group_poster.py
- modules/outreach/fb_group_seeder.py

Thêm ngành hàng mới = Chỉ cần thêm 1 entry vào CATEGORY_RULES.
"""

from typing import Dict, List, Optional, Tuple


# =============================================================================
# CATEGORY RULES – Nguồn sự thật duy nhất
# =============================================================================

CATEGORY_RULES: List[Dict] = [
    {
        "category_name": "Thiết Bị Điện Tử",
        "aliases": ["Điện Thoại & Phụ Kiện", "Máy Tính & Phụ Kiện", "Consumer Electronics", "Mobile & Gadgets", "Computer & Accessories"],
        "group_keywords": ["iphone", "apple", "công nghệ", "điện tử", "tai nghe", "điện thoại", "android", "linh kiện", "setup", "phím cơ", "gaming"],
        "deal_query_like": ["%Thiết Bị Điện Tử%", "%Điện Thoại%", "%Máy Tính%"],
        "seeder_keywords": ["điện tử", "tai nghe", "cáp", "sạc", "chuột", "bàn phím", "loa", "công nghệ", "phụ kiện"],
        "sub_categories": {
            "iphone": {
                "group_keywords": ["iphone", "apple"],
                "deal_name_like": ["%iPhone%", "%Ốp Lưng%", "%Kính Cường Lực%", "%AirPod%", "%Apple%"],
            },
            "tai_nghe": {
                "group_keywords": ["tai nghe", "airpod", "headphone"],
                "deal_name_like": ["%tai nghe%", "%AirPod%", "%headphone%"],
            },
        },
    },
    {
        "category_name": "Thời Trang Nam",
        "aliases": ["Men Clothes"],
        "group_keywords": ["đồ nam", "quần nam", "áo nam", "thời trang nam", "owen", "aristino", "nam béo", "phối đồ nam", "nam", "men"],
        "deal_query_like": ["Thời Trang Nam"],
        "seeder_keywords": ["thời trang nam", "quần nam", "áo nam"],
        "sub_categories": {
            "dao_cao": {
                "group_keywords": ["cạo râu", "dao cạo"],
                "deal_name_like": ["%cạo râu%", "%dao cạo%"],
            },
        },
    },
    {
        "category_name": "Thời Trang Nữ",
        "aliases": ["Women Clothes"],
        "group_keywords": ["đồ nữ", "quần nữ", "áo nữ", "váy", "nữ", "women", "xinh", "chị em", "làm đẹp", "mặc đẹp", "nấm lùn", "1m50", "genz", "tips phối đồ"],
        "deal_query_like": ["Thời Trang Nữ"],
        "seeder_keywords": ["thời trang nữ", "quần nữ", "áo nữ", "váy"],
    },
    {
        "category_name": "Nhà Cửa & Đời Sống",
        "aliases": ["Thiết Bị Điện Gia Dụng", "Gia Dụng", "Home Appliances", "Home & Living"],
        "group_keywords": ["gia dụng", "nhà cửa", "nội thất", "bếp", "nồi", "nghiện nhà", "yêu bếp", "decor"],
        "deal_query_like": ["%Nhà Cửa%", "%Gia Dụng%", "%Thiết Bị Điện Gia Dụng%"],
        "seeder_keywords": ["gia dụng", "nồi", "chảo", "máy", "bếp", "lau", "nhà cửa"],
    },
    {
        "category_name": "Sắc Đẹp",
        "aliases": ["Sắc Đẹp & Mỹ Phẩm", "Mỹ Phẩm", "Beauty & Personal Care", "Làm Đẹp"],
        "group_keywords": ["mỹ phẩm", "skincare", "makeup", "son", "kem", "serum", "dưỡng", "chăm sóc da"],
        "deal_query_like": ["%Sắc Đẹp%", "%Mỹ Phẩm%"],
        "seeder_keywords": ["sắc đẹp", "mỹ phẩm", "skincare", "son", "kem", "serum", "dưỡng", "làm đẹp"],
    },
    {
        "category_name": "Mẹ & Bé",
        "aliases": ["Moms, Kids & Babies"],
        "group_keywords": ["mẹ bỉm", "mẹ và bé", "sơ sinh", "bỉm", "tã", "sữa bột", "trẻ em"],
        "deal_query_like": ["%Mẹ%Bé%"],
        "seeder_keywords": ["mẹ & bé", "mẹ và bé", "tã", "bỉm", "sữa", "đồ chơi", "trẻ em"],
    },
    {
        "category_name": "Thể Thao & Dã Ngoại",
        "aliases": ["Sport & Outdoor"],
        "group_keywords": ["thể thao", "gym", "chạy bộ", "camping", "dã ngoại", "yoga"],
        "deal_query_like": ["%Thể Thao%", "%Dã Ngoại%"],
        "seeder_keywords": ["thể thao", "gym", "chạy bộ", "camping"],
    },
    {
        "category_name": "Thú Cưng",
        "aliases": ["Pets"],
        "group_keywords": ["thú cưng", "chó", "mèo", "boss", "sen"],
        "deal_query_like": ["%Thú Cưng%", "%Pets%"],
        "seeder_keywords": ["thú cưng", "chó", "mèo"],
    },
    {
        "category_name": "Sách & Văn Phòng Phẩm",
        "aliases": ["Books & Stationery"],
        "group_keywords": ["sách", "đọc sách", "văn phòng phẩm", "bullet journal"],
        "deal_query_like": ["%Sách%", "%Văn Phòng%"],
        "seeder_keywords": ["sách", "văn phòng phẩm"],
    },
]

# Danh mục tổng hợp / săn deal chung – match cuối cùng (catch-all)
GENERAL_DEAL_RULE = {
    "category_name": "Săn Deal Tổng Hợp",
    "aliases": ["Cộng Đồng Chung"],
    "group_keywords": ["săn deal", "voucher", "khuyến mãi", "khuyến mại", "giảm giá", "chợ", "rải link", "cháy túi", "flash sale", "mã giảm"],
}


# =============================================================================
# CATEGORY MATCHER – Engine khớp category thống nhất
# =============================================================================

class CategoryMatcher:
    """
    Engine khớp Deal ↔ Group duy nhất, thay thế toàn bộ if-elif cứng.
    
    Sử dụng:
        matcher = CategoryMatcher()
        rule = matcher.match_group(group_cat="Thiết Bị Điện Tử", group_name="Hội iPhone Việt Nam")
        # rule = {"category_name": "Thiết Bị Điện Tử", "sub_category": "iphone", ...}
        
        sql_conditions = matcher.build_deal_query_conditions(rule)
        # sql_conditions = "category_name LIKE '%Thiết Bị Điện Tử%' OR category_name LIKE '%Điện Thoại%'"
    """

    def __init__(self, rules: Optional[List[Dict]] = None):
        self._rules = rules or CATEGORY_RULES
        self._general_rule = GENERAL_DEAL_RULE

    def match_group(self, group_cat: str, group_name: str = "") -> Dict:
        """
        Tìm CATEGORY_RULE phù hợp nhất cho group dựa trên category_name và tên nhóm.
        
        Trả về dict:
        {
            "rule": <CATEGORY_RULE dict>,
            "matched_by": "category" | "alias" | "keyword" | "general",
            "sub_category": <sub_cat_key> | None,
            "sub_rule": <sub_cat_dict> | None,
        }
        """
        group_name_lower = (group_name or "").lower()
        group_cat_clean = (group_cat or "").strip()

        # 1. Khớp theo category_name hoặc aliases
        for rule in self._rules:
            if group_cat_clean == rule["category_name"]:
                sub_cat, sub_rule = self._check_sub_category(rule, group_name_lower)
                return {"rule": rule, "matched_by": "category", "sub_category": sub_cat, "sub_rule": sub_rule}

            if group_cat_clean in rule.get("aliases", []):
                sub_cat, sub_rule = self._check_sub_category(rule, group_name_lower)
                return {"rule": rule, "matched_by": "alias", "sub_category": sub_cat, "sub_rule": sub_rule}

        # 2. Khớp theo group_keywords trong tên nhóm
        for rule in self._rules:
            if any(kw in group_name_lower for kw in rule.get("group_keywords", [])):
                sub_cat, sub_rule = self._check_sub_category(rule, group_name_lower)
                return {"rule": rule, "matched_by": "keyword", "sub_category": sub_cat, "sub_rule": sub_rule}

        # 3. Check xem có phải nhóm săn deal tổng hợp không
        if group_cat_clean in [self._general_rule["category_name"]] + self._general_rule.get("aliases", []):
            return {"rule": self._general_rule, "matched_by": "general", "sub_category": None, "sub_rule": None}

        if any(kw in group_name_lower for kw in self._general_rule.get("group_keywords", [])):
            return {"rule": self._general_rule, "matched_by": "general", "sub_category": None, "sub_rule": None}

        # 4. Không khớp gì → fallback về general
        return {"rule": self._general_rule, "matched_by": "general", "sub_category": None, "sub_rule": None}

    def _check_sub_category(self, rule: Dict, group_name_lower: str) -> Tuple[Optional[str], Optional[Dict]]:
        """Kiểm tra xem có match sub-category cụ thể hơn không."""
        sub_categories = rule.get("sub_categories", {})
        for sub_key, sub_def in sub_categories.items():
            if any(kw in group_name_lower for kw in sub_def.get("group_keywords", [])):
                return sub_key, sub_def
        return None, None

    def build_deal_query_conditions(self, match_result: Dict) -> str:
        """
        Tạo SQL WHERE conditions cho việc tìm deal phù hợp.
        
        Trả về chuỗi SQL: "category_name LIKE '%X%' OR category_name LIKE '%Y%'"
        Nếu là general → trả về "1=1" (lấy tất cả)
        """
        rule = match_result["rule"]

        if match_result["matched_by"] == "general":
            return "1=1"

        patterns = rule.get("deal_query_like", [])
        if not patterns:
            # Fallback: exact match theo category_name
            safe_name = rule["category_name"].replace("'", "''")
            return f"category_name = '{safe_name}'"

        conditions = []
        for pattern in patterns:
            safe = pattern.replace("'", "''")
            conditions.append(f"category_name LIKE '{safe}'")

        return " OR ".join(conditions)

    def build_sub_category_name_filter(self, match_result: Dict) -> Optional[str]:
        """
        Nếu có sub_category, tạo thêm filter theo deal.name.
        Trả về SQL fragment hoặc None.
        """
        sub_rule = match_result.get("sub_rule")
        if not sub_rule:
            return None

        name_likes = sub_rule.get("deal_name_like", [])
        if not name_likes:
            return None

        conditions = []
        for pattern in name_likes:
            safe = pattern.replace("'", "''")
            conditions.append(f"name LIKE '{safe}'")

        return " OR ".join(conditions)

    def get_seeder_keywords(self, match_result: Dict) -> List[str]:
        """Lấy danh sách keyword để seeder tìm deal theo ngữ cảnh bài viết."""
        rule = match_result["rule"]
        return rule.get("seeder_keywords", [])

    def detect_category_from_text(self, text: str) -> Optional[Dict]:
        """
        Phát hiện ngành hàng từ nội dung bài viết (dùng cho Seeder).
        Trả về match_result dict hoặc None.
        """
        text_lower = (text or "").lower()
        for rule in self._rules:
            seeder_kws = rule.get("seeder_keywords", [])
            if any(kw in text_lower for kw in seeder_kws):
                return {"rule": rule, "matched_by": "seeder_text", "sub_category": None, "sub_rule": None}
        return None
