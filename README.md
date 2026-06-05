# Doctor Laser - Bot phân tích dữ liệu Google Sheet

Bot Telegram giúp bạn hỏi-đáp và phân tích dữ liệu khách hàng (lead) từ Google Sheet
của phòng khám **Doctor Laser**. Bạn nhắn câu hỏi tiếng Việt, bot đọc sheet, tính số
liệu và dùng **Claude (Anthropic)** để trả lời.

Ví dụ câu hỏi:
- "Hôm nay có bao nhiêu lead?"
- "Nguồn nào ra nhiều khách nhất?"
- "Tỉ lệ khách ĐÃ ĐẾN trên tổng lead?"
- "Telesale nào phụ trách nhiều khách nhất?"
- "Dịch vụ nào được quan tâm nhất?"

---

## Dữ liệu

Bot đọc bảng theo dõi lead với các cột:

`NGÀY | HỌ VÀ TÊN | SỐ ĐIỆN THOẠI | DỊCH VỤ | NV TRỰC PAGE | TELESALE PHỤ TRÁCH | NGUỒN | GHI CHÚ | TRẠNG THÁI | GỌI LẦN 1 | GỌI LẦN 2`

---

## Cài đặt (làm 1 lần)

### Bước 1 — Cài Python và thư viện

Cần Python 3.11 trở lên.

```bash
pip install -r requirements.txt
```

### Bước 2 — Tạo bot Telegram, lấy token

1. Mở Telegram, tìm **@BotFather**.
2. Gửi `/newbot`, đặt tên và username cho bot.
3. BotFather trả về một **token** dạng `123456:ABC-...`. Lưu lại.

### Bước 3 — Lấy Anthropic API key (cho Claude)

1. Vào https://console.anthropic.com/ → **Settings → API Keys → Create Key**.
2. Sao chép key dạng `sk-ant-...`.

### Bước 4 — Tạo Google Service Account để bot đọc sheet

Vì dữ liệu có số điện thoại (riêng tư), bot dùng **Service Account** để truy cập an toàn.

1. Vào https://console.cloud.google.com/ → tạo một **Project** (hoặc dùng project có sẵn).
2. Bật 2 API: **Google Sheets API** và **Google Drive API**
   (vào *APIs & Services → Library*, tìm và bấm **Enable**).
3. Vào *APIs & Services → Credentials → Create Credentials → **Service account***.
   Đặt tên bất kỳ rồi tạo.
4. Mở service account vừa tạo → tab **Keys → Add key → Create new key → JSON**.
   File JSON sẽ tải về máy.
5. Đổi tên file đó thành `service_account.json` và đặt cùng thư mục với bot
   (hoặc khai báo đường dẫn trong `.env`).
6. Mở file JSON, tìm dòng `"client_email"` (dạng `ten@project.iam.gserviceaccount.com`).
7. Vào **Google Sheet** của bạn → bấm **Share/Chia sẻ** → dán email đó vào và cấp
   quyền **Viewer (Người xem)**. Đây là bước quan trọng để bot đọc được sheet.

### Bước 5 — Tạo file cấu hình `.env`

Sao chép file mẫu rồi điền thông tin:

```bash
cp .env.example .env
```

Mở `.env` và điền:
- `TELEGRAM_BOT_TOKEN` — token ở Bước 2
- `ANTHROPIC_API_KEY` — key ở Bước 3
- `GOOGLE_SHEET_ID` — ID sheet (đã điền sẵn sheet hiện tại)
- `GOOGLE_SHEET_GID` — gid của tab cần phân tích (đã điền sẵn)
- `GOOGLE_SERVICE_ACCOUNT_FILE` — để mặc định `service_account.json` nếu đặt cùng thư mục
- `ALLOWED_TELEGRAM_IDS` — (tùy chọn) giới hạn ai được dùng bot. Để trống = ai cũng dùng được.

---

## Chạy bot

```bash
python bot.py
```

Khi thấy dòng "Bot đang chạy", mở Telegram, vào bot của bạn, gửi `/start` và bắt đầu hỏi.

---

## Deploy lên Railway (chạy 24/7 trên cloud)

Bot chạy nền (polling) nên rất hợp với Railway. Repo đã có sẵn `railway.json` và `Procfile`.

### Bước 1 — Đưa code lên GitHub
Code đã nằm trên GitHub (branch của bạn). Railway sẽ deploy trực tiếp từ đó.

### Bước 2 — Tạo project trên Railway
1. Vào https://railway.app/ → đăng nhập (nên dùng GitHub).
2. **New Project → Deploy from GitHub repo** → chọn repo `doctorlaser`.
3. Railway tự nhận Python (qua `requirements.txt`) và chạy lệnh `python bot.py`.

### Bước 3 — Khai báo biến môi trường (Variables)
Trong project Railway → tab **Variables** → thêm các biến sau:

| Biến | Giá trị |
|------|---------|
| `TELEGRAM_BOT_TOKEN` | token mới từ BotFather |
| `ANTHROPIC_API_KEY` | key `sk-ant-...` |
| `GOOGLE_SHEET_ID` | ID của sheet |
| `GOOGLE_SHEET_GID` | gid của tab cần phân tích |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | **dán toàn bộ nội dung file `service_account.json`** vào đây |
| `ALLOWED_TELEGRAM_IDS` | (tùy chọn) ID Telegram được phép dùng |

> Lưu ý: Trên Railway **không upload file**, nên dùng `GOOGLE_SERVICE_ACCOUNT_JSON`
> (dán cả nội dung JSON, gồm cả dấu ngoặc `{ ... }`). Đừng quên vẫn phải **Share sheet**
> với email `client_email` trong JSON đó (quyền Viewer).

### Bước 4 — Deploy
Railway tự build và chạy. Vào tab **Deployments → Logs**, thấy dòng
"Bot đang chạy" là thành công. Mở Telegram và bắt đầu hỏi.

> Mỗi lần bạn push code mới lên branch, Railway sẽ tự deploy lại.

---

## Các lệnh trong bot

| Lệnh | Tác dụng |
|------|----------|
| `/start`, `/help` | Hướng dẫn sử dụng |
| `/stats` | Xem nhanh số liệu tổng hợp (theo nguồn, trạng thái, dịch vụ, ngày, telesale) |
| `/refresh` | Tải lại dữ liệu mới nhất từ Google Sheet |

Ngoài ra cứ nhắn câu hỏi tự nhiên là bot trả lời.

---

## Lưu ý

- Dữ liệu được cache `SHEET_CACHE_TTL` giây (mặc định 120s) để đỡ gọi Google liên tục.
  Muốn cập nhật ngay, dùng `/refresh`.
- **Không commit** file `.env` và `service_account.json` lên Git (đã có trong `.gitignore`).
- Mỗi câu hỏi sẽ gửi dữ liệu sheet cho Claude; chi phí phụ thuộc lượng dữ liệu.
  Bot đã bật *prompt caching* để các câu hỏi liên tiếp rẻ và nhanh hơn.

---

## Cấu trúc mã nguồn

| File | Vai trò |
|------|---------|
| `bot.py` | Bot Telegram (điểm khởi chạy) |
| `sheets.py` | Đọc & làm sạch dữ liệu từ Google Sheet |
| `analytics.py` | Tính số liệu tổng hợp chính xác |
| `llm.py` | Gọi Claude để phân tích & trả lời |
| `config.py` | Đọc cấu hình từ `.env` |
