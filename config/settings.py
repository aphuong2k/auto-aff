import os
from pathlib import Path

# Thư mục gốc dự án
BASE_DIR = Path(__file__).resolve().parent.parent

# Nạp .env bằng thuần Python không phụ thuộc thư viện ngoài
_env_file = BASE_DIR / ".env"
if _env_file.exists():
    with open(_env_file, "r", encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if "=" in _line and not _line.startswith("#"):
                _k, _v = _line.split("=", 1)
                os.environ[_k.strip()] = _v.strip().strip('"')

# Thư mục dữ liệu & Log
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"
RAW_IMAGES_DIR = DATA_DIR / "raw_images"
PROCESSED_IMAGES_DIR = DATA_DIR / "processed_images"
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(RAW_IMAGES_DIR, exist_ok=True)
os.makedirs(PROCESSED_IMAGES_DIR, exist_ok=True)

DB_PATH = DATA_DIR / "affiliate_system.db"
LOG_FILE_PATH = LOG_DIR / "automation.log"
FB_SEEDING_LOG_PATH = LOG_DIR / "facebook_seeding.log"

# Cấu hình Tiêu chuẩn lọc Deal
MIN_RATING_STAR = 4.6
MIN_HISTORICAL_SOLD = 500  # Ưu tiên các sản phẩm phổ biến, bán chạy
MIN_DISCOUNT_PERCENT = 15
TOP_DEALS_PER_CATEGORY = 3

# Cấu hình Chuyển Hướng Link (Anti-Die Link)
# 'direct': Dùng trực tiếp link Shopee Aff (100% không bao giờ chết dù máy tắt)
# 'tinyurl': Tự động rút gọn qua TinyURL Cloud API vĩnh viễn
# 'custom_domain': Dùng domain riêng của bạn
REDIRECT_MODE = os.getenv("REDIRECT_MODE", "direct")
REDIRECT_BASE_URL = os.getenv("REDIRECT_BASE_URL", "")

# Cấu hình Rate Limiting Facebook
MAX_GROUPS_TO_JOIN_PER_DAY = 3
MIN_JOIN_DELAY_SECONDS = 300  # 5 phút (thực tế)
MAX_JOIN_DELAY_SECONDS = 900  # 15 phút (thực tế)
MIN_GROUP_MEMBERS = 10000

# Telegram Bot (Để trống nếu chưa có)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Shopee Affiliate API / Portal credentials
SHOPEE_APP_ID = os.getenv("SHOPEE_APP_ID", "")
SHOPEE_SECRET = os.getenv("SHOPEE_SECRET", "")
SHOPEE_AFF_COOKIE = os.getenv("SHOPEE_AFF_COOKIE", "")

# Lazada Affiliate API / Portal credentials (Đa sàn)
LAZADA_APP_KEY = os.getenv("LAZADA_APP_KEY", "")
LAZADA_APP_SECRET = os.getenv("LAZADA_APP_SECRET", "")
LAZADA_AFF_COOKIE = os.getenv("LAZADA_AFF_COOKIE", "")
LAZADA_TRACKING_URL = os.getenv("LAZADA_TRACKING_URL", "")

# Bảo mật API & Quản trị
API_ADMIN_KEY = os.getenv("API_ADMIN_KEY", "")
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:4200,http://127.0.0.1:4200,http://localhost:8000,http://127.0.0.1:8000")

# Chu kỳ kiểm tra độ tươi của Deal (Giờ)
FRESHNESS_CHECK_INTERVAL_HOURS = int(os.getenv("FRESHNESS_CHECK_INTERVAL_HOURS", "2"))

# Cấu hình Kênh Cộng Đồng Riêng (Zalo Group / Telegram Channel / FB Group để kéo Member)
COMMUNITY_INVITE_URL = os.getenv("COMMUNITY_INVITE_URL", "")
COMMUNITY_NAME = os.getenv("COMMUNITY_NAME", "Hội Săn Deal Shopee VIP")

