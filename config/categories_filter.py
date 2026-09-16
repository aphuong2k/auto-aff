# Danh sách các ngành hàng Shopee KHÔNG làm affiliate (Voucher, nạp tiền, bảo hiểm, sim, vé...)
EXCLUDED_CATEGORY_KEYWORDS = [
    "Voucher",
    "Nạp Thẻ",
    "Dịch Vụ",
    "Vé Máy Bay",
    "Bảo Hiểm",
    "Sim",
    "Khóa Học",
    "Ô tô nguyên chiếc",
    "Xe máy",
    "Bất Động Sản"
]

# Gợi ý từ khóa tìm kiếm Group Facebook tương ứng với từng nhóm ngành
CATEGORY_GROUP_KEYWORDS = {
    "Thiết Bị Điện Tử": [
        "hội đam mê công nghệ",
        "hội phím cơ việt nam",
        "setup góc làm việc",
        "review đồ công nghệ"
    ],
    "Thiết Bị Điện Gia Dụng": [
        "nghiện nhà",
        "yêu bếp",
        "đồ gia dụng thông minh",
        "review đồ gia dụng tiện ích"
    ],
    "Sức Khỏe": [
        "chăm sóc sức khỏe gia đình",
        "thực phẩm chức năng chính hãng",
        "eat clean & sống khỏe"
    ],
    "Sắc Đẹp": [
        "review mỹ phẩm có tâm",
        "cháy túi vì shopee",
        "hội mê skincare",
        "giao lưu đồ makeup"
    ],
    "Mẹ & Bé": [
        "hội mẹ bỉm thông thái",
        "chăm sóc trẻ sơ sinh",
        "kinh nghiệm nuôi con khoa học",
        "thanh lý & săn deal đồ mẹ và bé"
    ],
    "Thời Trang Nam": [
        "hội phối đồ nam đẹp",
        "thời trang streetwear nam",
        "săn sale quần áo nam"
    ],
    "Thời Trang Nữ": [
        "hội nghiện mặc đẹp",
        "review đồ shopee cho phái đẹp",
        "săn deal thời trang nữ"
    ],
    "Nhà Cửa & Đời Sống": [
        "nghiện decor nhà cửa",
        "mẹo vặt dọn dẹp nhà",
        "sắm sửa đồ nhà bếp"
    ],
    "Đồ Chơi": [
        "hội mê mô hình anime figure",
        "đồ chơi lego việt nam",
        "đồ chơi phát triển trí tuệ cho bé"
    ]
}

def is_category_allowed(category_name: str) -> bool:
    """Kiểm tra ngành hàng có phù hợp để làm affiliate không"""
    for excluded in EXCLUDED_CATEGORY_KEYWORDS:
        if excluded.lower() in category_name.lower():
            return False
    return True
