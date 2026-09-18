# Shopee Affiliate & Facebook Group Outreach Automation 🚀

Hệ thống tự động hóa toàn diện phục vụ Affiliate Marketing tại Việt Nam:
1. **Lấy danh mục động**: Tự động cào toàn bộ cây danh mục từ Shopee và loại bỏ các ngành hàng rác (Voucher, SIM, Nạp thẻ...).
2. **Săn & Lọc Deal đỉnh**: Tự động tìm kiếm sản phẩm theo ngành hàng, tính điểm theo 4 tiêu chí (% Giảm giá, Lượt bán, Đánh giá $\ge 4.6$, Shop Mall) và chọn ra **Top 3 deal hời nhất mỗi ngành hàng**.
3. **Tạo nội dung & Link Aff**: Tự động chuyển đổi link Shopee sang link Affiliate và viết bài đăng hấp dẫn kèm icon, giá gốc, giá sale.
4. **Bắn Deal lên Kênh Nhà**: Tự động gửi deal kèm hình ảnh vào Kênh/Nhóm **Telegram** thông qua Telegram Bot API.
5. **Dò tìm Group Facebook theo ngành**: Tự động sinh từ khóa cộng đồng tương ứng (ví dụ: *Thời trang Nam* $\rightarrow$ *Hội phối đồ nam đẹp*) và tìm các group $\ge 10.000$ thành viên.
6. **Tự động Join Group thông minh**: Tự động bấm tham gia nhóm và **dùng AI để tự động trả lời các câu hỏi duyệt nhóm của Admin** một cách tự nhiên.
7. **Cơ chế chống khóa nick (Anti-Ban)**: Kiểm soát nghiêm ngặt tối đa 3–5 group/ngày và có giãn cách ngẫu nhiên.

---

## 📁 Cấu trúc thư mục

```
shopee-aff-auto/
├── config/
│   ├── settings.py            # Cấu hình ngưỡng lọc deal, rate limit, tokens
│   └── categories_filter.py   # Lọc ngành hàng & mapping từ khóa group FB
├── database/
│   └── db_manager.py          # Quản lý cơ sở dữ liệu SQLite
├── modules/
│   ├── 1_crawler/
│   │   ├── shopee_categories.py # Cào danh mục động Shopee
│   │   └── deal_hunter.py       # Lọc Top 3 deal/ngành hàng
│   ├── 2_affiliate/
│   │   ├── link_converter.py    # Chuyển đổi link affiliate
│   │   └── content_writer.py    # Soạn bài đăng Telegram / FB
│   ├── 3_publisher/
│   │   └── telegram_bot.py      # Đăng bài lên Telegram
│   └── 4_outreach/
│       ├── fb_group_finder.py   # Tìm kiếm Group Facebook
│       └── fb_auto_joiner.py    # Tự động join group + AI trả lời câu hỏi
├── data/
│   └── affiliate_system.db    # Cơ sở dữ liệu SQLite tự động tạo
├── main.py                    # File điều phối chạy toàn bộ chu trình
└── requirements.txt
```

---

## ⚙️ Hướng dẫn cài đặt & Chạy

### 1. Cài đặt thư viện:
```bash
pip install -r requirements.txt
```

### 2. Cấu hình Kênh Nhà (Telegram) & Affiliate (Tùy chọn):
Chỉnh sửa trong file `config/settings.py` hoặc tạo file `.env`:
```env
TELEGRAM_BOT_TOKEN="your_bot_token_from_botfather"
TELEGRAM_CHAT_ID="@your_channel_username_or_id"
SHOPEE_APP_ID="your_shopee_app_id"
SHOPEE_SECRET="your_shopee_secret"
```
*(Nếu chưa điền token, hệ thống sẽ tự động chạy ở chế độ mô phỏng an toàn để bạn kiểm tra luồng dữ liệu).*

### 3. Khởi chạy hệ thống:

#### Cách 1: Chạy trọn gói Web Dashboard (Cả Backend & Frontend trên 1 cổng)
Frontend Angular đã được build sẵn vào thư mục `frontend/dist`. FastAPI sẽ tự động phục vụ cả giao diện Web lẫn API:
```bash
python api_server.py
```
👉 Mở trình duyệt truy cập: **`http://localhost:8000`**

---

#### Cách 2: Chạy riêng biệt (Dành cho lập trình viên sửa code Frontend)
- **Terminal 1 (Backend FastAPI)**:
  ```bash
  python api_server.py
  # Hoặc chế độ tự reload khi sửa code:
  uvicorn api_server:app --reload --port 8000
  ```
- **Terminal 2 (Frontend Angular Live-Reload)**:
  ```bash
  cd frontend
  npm start
  ```
👉 Mở trình duyệt truy cập: **`http://localhost:4200`** (giao diện sẽ tự động gọi API tới `http://localhost:8000/api`)

---

#### Cách 3: Chạy trực tiếp qua dòng lệnh (CLI - không cần Web UI)
```bash
python main.py --once --cats 3
```
*(Lệnh trên sẽ quét 3 ngành hàng đầu tiên, lọc ra 9 deal hời nhất, tạo bài đăng và tìm kiếm các Group Facebook tương ứng).*
