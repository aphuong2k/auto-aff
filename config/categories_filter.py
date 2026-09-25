import re
from typing import Dict, List

# Danh sách các ngành hàng Shopee KHÔNG làm affiliate (Voucher, nạp tiền, bảo hiểm, sim, vé...)
EXCLUDED_CATEGORY_KEYWORDS = [
    # Tiếng Việt
    "Voucher",
    "Nạp Thẻ",
    "Dịch Vụ",
    "Vé Máy Bay",
    "Bảo Hiểm",
    "Sim",
    "Khóa Học",
    "Ô tô nguyên chiếc",
    "Xe máy",
    "Bất Động Sản",
    # Tiếng Anh (từ API Shopee)
    "Deals Near Me",
    "Services",
    "Tickets",
    "Top-up",
    "Bills",
    "Insurance",
    "Donations",
    "Real Estate",
    "Motorcycles",
    "Automobiles"
]

# Từ điển dịch chuẩn hóa ngành hàng Shopee từ Tiếng Anh sang Tiếng Việt
CATEGORY_TRANSLATIONS: Dict[str, str] = {
    # 27 Ngành hàng cấp 1 chính của Shopee
    "Men Clothes": "Thời Trang Nam",
    "Women Clothes": "Thời Trang Nữ",
    "Men Bags": "Túi Ví Nam",
    "Women Bags": "Túi Ví Nữ",
    "Watches": "Đồng Hồ",
    "Men Shoes": "Giày Dép Nam",
    "Women Shoes": "Giày Dép Nữ",
    "Fashion Accessories": "Phụ Kiện Thời Trang",
    "Computer & Accessories": "Máy Tính & Phụ Kiện",
    "Mobile & Gadgets": "Điện Thoại & Phụ Kiện",
    "Cameras": "Máy Ảnh & Quay Phim",
    "Consumer Electronics": "Thiết Bị Điện Tử",
    "Moms, Kids & Babies": "Mẹ & Bé",
    "Beauty & Personal Care": "Sắc Đẹp & Mỹ Phẩm",
    "Health": "Sức Khỏe",
    "Kid Fashion": "Thời Trang Trẻ Em",
    "Pets": "Thú Cưng",
    "Grocery": "Bách Hóa Online",
    "Home care": "Chăm Sóc Nhà Cửa",
    "Home & Living": "Nhà Cửa & Đời Sống",
    "Automotive": "Ô Tô & Xe Máy",
    "Books & Stationery": "Sách & Văn Phòng Phẩm",
    "Toys": "Đồ Chơi & Quà Tặng",
    "Home Appliances": "Thiết Bị Điện Gia Dụng",
    "Tools & Home Improvement": "Dụng Cụ & Tiện Ích Đời Sống",
    "Sport & Outdoor": "Thể Thao & Dã Ngoại",
    "Deals Near Me": "Voucher & Dịch Vụ",

    # Các biến thể / Danh mục con phổ biến
    "Audio": "Âm Thanh & Tai Nghe",
    "Laptops": "Laptop & Máy Tính",
    "Gaming": "Phụ Kiện Gaming",
    "Keyboards": "Bàn Phím Cơ",
    "Makeup": "Trang Điểm Làm Đẹp",
    "Skincare": "Chăm Sóc Da",
    "Hair Care": "Chăm Sóc Tóc",
    "Jewelry": "Trang Sức",
    "Kitchen & Dining": "Dụng Cụ Nhà Bếp",
    "Bedding": "Chăn Ga Gối Nệm",
    "Furniture": "Nội Thất Nhà Cửa",
    "Lighting": "Đèn Chiếu Sáng Decor",
    "Food & Beverages": "Thực Phẩm & Đồ Uống",
    "Snacks": "Đồ Ăn Vặt",
    "Baby Clothes": "Quần Áo Sơ Sinh",
    "Stationery": "Văn Phòng Phẩm"
}

# Từ điển thay thế từng từ cho các danh mục con linh hoạt
WORD_TRANSLATIONS: Dict[str, str] = {
    "Clothes": "Quần Áo",
    "Clothing": "Quần Áo",
    "Shoes": "Giày Dép",
    "Bags": "Túi Ví",
    "Accessories": "Phụ Kiện",
    "Watches": "Đồng Hồ",
    "Jewelry": "Trang Sức",
    "Beauty": "Làm Đẹp",
    "Care": "Chăm Sóc",
    "Health": "Sức Khỏe",
    "Food": "Thực Phẩm",
    "Electronics": "Điện Tử",
    "Home": "Nhà Cửa",
    "Living": "Đời Sống",
    "Kitchen": "Nhà Bếp",
    "Sports": "Thể Thao",
    "Outdoor": "Dã Ngoại",
    "Kids": "Trẻ Em",
    "Baby": "Em Bé",
    "Men": "Nam",
    "Women": "Nữ",
    "Toys": "Đồ Chơi",
    "Books": "Sách"
}

def translate_category(name: str) -> str:
    """Dịch tên ngành hàng từ tiếng Anh sang tiếng Việt chuẩn và tự nhiên"""
    if not name or not isinstance(name, str):
        return ""
    
    clean = name.strip()
    clean_lower = clean.lower()

    # 1. Tra cứu chính xác trong danh mục 1-1
    for en_key, vi_val in CATEGORY_TRANSLATIONS.items():
        if en_key.lower() == clean_lower:
            return vi_val
            
    # 2. Tra cứu theo cụm từ chứa bên trong
    for en_key, vi_val in CATEGORY_TRANSLATIONS.items():
        if en_key.lower() in clean_lower or clean_lower in en_key.lower():
            return vi_val

    # 3. Dịch từng từ nếu là tên ghép danh mục con
    result = clean
    for en_word, vi_word in WORD_TRANSLATIONS.items():
        pattern = re.compile(rf"\b{re.escape(en_word)}\b", re.IGNORECASE)
        result = pattern.sub(vi_word, result)

    result = result.replace("&", "&").strip()
    return result

def is_category_allowed(category_name: str) -> bool:
    """Kiểm tra ngành hàng có phù hợp để làm affiliate không (hỗ trợ cả tiếng Anh lẫn tiếng Việt)"""
    if not category_name:
        return False
    cat_lower = category_name.lower()
    for excluded in EXCLUDED_CATEGORY_KEYWORDS:
        if excluded.lower() in cat_lower:
            return False
    return True

# Nhóm các cộng đồng mua sắm "same same" tổng hợp (săn deal, săn sale, mã giảm giá, voucher, cháy túi vì shopee)
GENERAL_SHOPPING_GROUP_KEYWORDS = [
    "cháy túi vì shopee",
    "hội săn deal shopee",
    "săn sale shopee",
    "nghiện săn deal shopee",
    "nghiện săn sale shopee",
    "mã giảm giá shopee",
    "ghiền săn deal shopee",
    "kho voucher shopee",
    "săn deal lazada shopee",
    "review đồ shopee có tâm",
    "kinh nghiệm săn sale shopee"
]

GENERAL_DEAL_IDENTIFIERS = [
    "săn deal", "săn sale", "mã giảm giá", "mã shopee", "voucher", "cháy túi vì shopee",
    "nghiện shopee", "ghiền shopee", "chợ deal", "flash sale", "săn mã", "canh sale",
    "tổng hợp deal", "chia sẻ mã", "săn đồ 1k", "deal hot shopee"
]

def is_general_deal_group(group_name: str) -> bool:
    """Kiểm tra xem nhóm Facebook có phải là nhóm Săn Deal / Săn Sale Tổng Hợp (không chuyên 1 ngành đơn lẻ) hay không"""
    if not group_name:
        return False
    name_lower = group_name.lower()
    return any(ident in name_lower for ident in GENERAL_DEAL_IDENTIFIERS)

# Gợi ý từ khóa tìm kiếm Group Facebook tự nhiên, theo cộng đồng thật của người Việt
CATEGORY_GROUP_KEYWORDS: Dict[str, List[str]] = {
    "Thời Trang Nam": [
        "hội phối đồ nam đẹp",
        "thời trang nam streetwear",
        "săn sale quần áo nam",
        "review đồ nam shopee",
        "chia sẻ style thời trang nam"
    ],
    "Men Clothes": [
        "hội phối đồ nam đẹp",
        "thời trang nam streetwear",
        "săn sale quần áo nam",
        "review đồ nam shopee",
        "chia sẻ style thời trang nam"
    ],
    "Thời Trang Nữ": [
        "hội nghiện mặc đẹp",
        "review đồ shopee cho phái đẹp",
        "săn deal thời trang nữ",
        "hội phối đồ nữ xinh",
        "giao lưu quần áo nữ shopee"
    ],
    "Women Clothes": [
        "hội nghiện mặc đẹp",
        "review đồ shopee cho phái đẹp",
        "săn deal thời trang nữ",
        "hội phối đồ nữ xinh",
        "giao lưu quần áo nữ shopee"
    ],
    "Sắc Đẹp & Mỹ Phẩm": [
        "review mỹ phẩm có tâm",
        "hội mê skincare việt nam",
        "cháy túi vì shopee",
        "giao lưu đồ makeup làm đẹp",
        "săn sale mỹ phẩm chính hãng"
    ],
    "Beauty & Personal Care": [
        "review mỹ phẩm có tâm",
        "hội mê skincare việt nam",
        "cháy túi vì shopee",
        "giao lưu đồ makeup làm đẹp",
        "săn sale mỹ phẩm chính hãng"
    ],
    "Thiết Bị Điện Tử": [
        "hội đam mê công nghệ",
        "review đồ công nghệ",
        "setup góc làm việc",
        "cộng đồng công nghệ gen z",
        "hội săn deal đồ điện tử"
    ],
    "Consumer Electronics": [
        "hội đam mê công nghệ",
        "review đồ công nghệ",
        "setup góc làm việc",
        "cộng đồng công nghệ gen z",
        "hội săn deal đồ điện tử"
    ],
    "Máy Tính & Phụ Kiện": [
        "hội đam mê công nghệ",
        "hội phím cơ việt nam",
        "setup góc làm việc",
        "vọc máy tính pc gaming",
        "review phụ kiện máy tính"
    ],
    "Computer & Accessories": [
        "hội đam mê công nghệ",
        "hội phím cơ việt nam",
        "setup góc làm việc",
        "vọc máy tính pc gaming",
        "review phụ kiện máy tính"
    ],
    "Điện Thoại & Phụ Kiện": [
        "người dùng iphone việt nam",
        "cộng đồng android việt nam",
        "phụ kiện điện thoại thông minh",
        "săn sale ốp lưng cáp sạc",
        "đồ chơi công nghệ tiện ích"
    ],
    "Mobile & Gadgets": [
        "người dùng iphone việt nam",
        "cộng đồng android việt nam",
        "phụ kiện điện thoại thông minh",
        "săn sale ốp lưng cáp sạc",
        "đồ chơi công nghệ tiện ích"
    ],
    "Thiết Bị Điện Gia Dụng": [
        "nghiện nhà",
        "yêu bếp",
        "đồ gia dụng thông minh",
        "review đồ gia dụng tiện ích",
        "săn deal đồ gia dụng"
    ],
    "Home Appliances": [
        "nghiện nhà",
        "yêu bếp",
        "đồ gia dụng thông minh",
        "review đồ gia dụng tiện ích",
        "săn deal đồ gia dụng"
    ],
    "Nhà Cửa & Đời Sống": [
        "nghiện decor nhà cửa",
        "nghiện nhà",
        "yêu bếp",
        "decor phòng trọ đẹp",
        "mẹo vặt dọn dẹp nhà cửa"
    ],
    "Home & Living": [
        "nghiện decor nhà cửa",
        "nghiện nhà",
        "yêu bếp",
        "decor phòng trọ đẹp",
        "mẹo vặt dọn dẹp nhà cửa"
    ],
    "Mẹ & Bé": [
        "hội mẹ bỉm thông thái",
        "chăm sóc trẻ sơ sinh",
        "kinh nghiệm nuôi con khoa học",
        "thanh lý & săn deal đồ mẹ và bé",
        "hội mẹ bỉm sữa săn sale"
    ],
    "Moms, Kids & Babies": [
        "hội mẹ bỉm thông thái",
        "chăm sóc trẻ sơ sinh",
        "kinh nghiệm nuôi con khoa học",
        "thanh lý & săn deal đồ mẹ và bé",
        "hội mẹ bỉm sữa săn sale"
    ],
    "Sức Khỏe": [
        "chăm sóc sức khỏe gia đình",
        "eat clean & sống khỏe",
        "thực phẩm chức năng chính hãng",
        "chia sẻ kiến thức sống khỏe"
    ],
    "Health": [
        "chăm sóc sức khỏe gia đình",
        "eat clean & sống khỏe",
        "thực phẩm chức năng chính hãng",
        "chia sẻ kiến thức sống khỏe"
    ],
    "Giày Dép Nam": [
        "thần kinh giày việt nam",
        "hội mê sneaker việt nam",
        "review giày nam chất lượng",
        "săn sale giày chính hãng"
    ],
    "Men Shoes": [
        "thần kinh giày việt nam",
        "hội mê sneaker việt nam",
        "review giày nam chất lượng",
        "săn sale giày chính hãng"
    ],
    "Giày Dép Nữ": [
        "hội mê giày dép nữ xinh",
        "review giày shopee",
        "săn sale giày dép nữ",
        "phối đồ với giày xinh"
    ],
    "Women Shoes": [
        "hội mê giày dép nữ xinh",
        "review giày shopee",
        "săn sale giày dép nữ",
        "phối đồ với giày xinh"
    ],
    "Túi Ví Nam": [
        "phụ kiện thời trang nam",
        "balo túi xách nam cao cấp",
        "săn sale balo túi ví"
    ],
    "Men Bags": [
        "phụ kiện thời trang nam",
        "balo túi xách nam cao cấp",
        "săn sale balo túi ví"
    ],
    "Túi Ví Nữ": [
        "nghiện túi xách nữ",
        "review túi xách thời trang",
        "săn deal túi ví nữ shopee",
        "túi xách hot trend"
    ],
    "Women Bags": [
        "nghiện túi xách nữ",
        "review túi xách thời trang",
        "săn deal túi ví nữ shopee",
        "túi xách hot trend"
    ],
    "Đồng Hồ": [
        "hội đồng hồ chính hãng việt nam",
        "giao lưu đồng hồ đeo tay",
        "review smartwatch thông minh",
        "săn sale đồng hồ shopee"
    ],
    "Watches": [
        "hội đồng hồ chính hãng việt nam",
        "giao lưu đồng hồ đeo tay",
        "review smartwatch thông minh",
        "săn sale đồng hồ shopee"
    ],
    "Phụ Kiện Thời Trang": [
        "phụ kiện thời trang hot trend",
        "trang sức phụ kiện giá rẻ",
        "săn deal phụ kiện shopee",
        "phụ kiện phối đồ đẹp"
    ],
    "Fashion Accessories": [
        "phụ kiện thời trang hot trend",
        "trang sức phụ kiện giá rẻ",
        "săn deal phụ kiện shopee",
        "phụ kiện phối đồ đẹp"
    ],
    "Thể Thao & Dã Ngoại": [
        "hội chạy bộ việt nam",
        "hội gymer việt nam",
        "đồ thể thao dã ngoại",
        "cắm trại camping việt nam",
        "săn deal đồ thể thao"
    ],
    "Sport & Outdoor": [
        "hội chạy bộ việt nam",
        "hội gymer việt nam",
        "đồ thể thao dã ngoại",
        "cắm trại camping việt nam",
        "săn deal đồ thể thao"
    ],
    "Thú Cưng": [
        "đảo mèo",
        "hội yêu chó cưng",
        "chăm sóc thú cưng cảnh",
        "săn deal phụ kiện thú cưng",
        "hội sen và boss"
    ],
    "Pets": [
        "đảo mèo",
        "hội yêu chó cưng",
        "chăm sóc thú cưng cảnh",
        "săn deal phụ kiện thú cưng",
        "hội sen và boss"
    ],
    "Sách & Văn Phòng Phẩm": [
        "hội mê đọc sách",
        "review sách hay nên đọc",
        "nghiện văn phòng phẩm sổ bút",
        "bullet journal việt nam",
        "săn deal sách hay giá rẻ"
    ],
    "Books & Stationery": [
        "hội mê đọc sách",
        "review sách hay nên đọc",
        "nghiện văn phòng phẩm sổ bút",
        "bullet journal việt nam",
        "săn deal sách hay giá rẻ"
    ],
    "Đồ Chơi & Quà Tặng": [
        "mô hình anime figure việt nam",
        "đồ chơi lego việt nam",
        "đồ chơi trí tuệ cho bé",
        "săn sale đồ chơi shopee"
    ],
    "Toys": [
        "mô hình anime figure việt nam",
        "đồ chơi lego việt nam",
        "đồ chơi trí tuệ cho bé",
        "săn sale đồ chơi shopee"
    ],
    "Bách Hóa Online": [
        "món ngon nhà làm",
        "nghiện ăn vặt shopee",
        "săn deal thực phẩm bách hóa",
        "review đồ ăn vặt ngon"
    ],
    "Grocery": [
        "món ngon nhà làm",
        "nghiện ăn vặt shopee",
        "săn deal thực phẩm bách hóa",
        "review đồ ăn vặt ngon"
    ],
    "Ô Tô & Xe Máy": [
        "chăm sóc xe ô tô xe máy",
        "phụ kiện đồ chơi xe ô tô",
        "độ xe và phụ tùng xe máy",
        "review phụ kiện xe"
    ],
    "Automotive": [
        "chăm sóc xe ô tô xe máy",
        "phụ kiện đồ chơi xe ô tô",
        "độ xe và phụ tùng xe máy",
        "review phụ kiện xe"
    ],
    "Máy Ảnh & Quay Phim": [
        "giao lưu nhiếp ảnh việt nam",
        "chợ máy ảnh và phụ kiện",
        "flycam gimbal máy ảnh việt nam"
    ],
    "Cameras": [
        "giao lưu nhiếp ảnh việt nam",
        "chợ máy ảnh và phụ kiện",
        "flycam gimbal máy ảnh việt nam"
    ],
    "Dụng Cụ & Tiện Ích Đời Sống": [
        "hội tự làm đồ diy việt nam",
        "dụng cụ sửa chữa đồ nghề gia đình",
        "đồ nghề cơ khí thông minh",
        "review dụng cụ cầm tay"
    ],
    "Tools & Home Improvement": [
        "hội tự làm đồ diy việt nam",
        "dụng cụ sửa chữa đồ nghề gia đình",
        "đồ nghề cơ khí thông minh",
        "review dụng cụ cầm tay"
    ]
}
