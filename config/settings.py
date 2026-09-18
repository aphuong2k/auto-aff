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
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

DB_PATH = DATA_DIR / "affiliate_system.db"
LOG_FILE_PATH = LOG_DIR / "automation.log"

# Cấu hình Tiêu chuẩn lọc Deal
MIN_RATING_STAR = 4.6
MIN_HISTORICAL_SOLD = 200
MIN_DISCOUNT_PERCENT = 15
TOP_DEALS_PER_CATEGORY = 3

# Cấu hình Rate Limiting Facebook
MAX_GROUPS_TO_JOIN_PER_DAY = 3
MIN_JOIN_DELAY_SECONDS = 300  # 5 phút (thực tế)
MAX_JOIN_DELAY_SECONDS = 900  # 15 phút (thực tế)
MIN_GROUP_MEMBERS = 10000

# Telegram Bot (Để trống nếu chưa có)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Shopee Affiliate API / Custom credentials
SHOPEE_APP_ID = os.getenv("SHOPEE_APP_ID", "")
SHOPEE_SECRET = os.getenv("SHOPEE_SECRET", "")
