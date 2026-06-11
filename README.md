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

## Kết nối KiotViet (tùy chọn — dữ liệu hóa đơn & doanh thu)

Khi bật, bot trả lời được cả câu hỏi về **doanh thu, hóa đơn, sản phẩm bán chạy,
khách hàng** (dữ liệu thực tế từ KiotViet), bên cạnh dữ liệu lead từ Google Sheet.

### Lấy thông tin kết nối
1. Đăng nhập KiotViet → **Thiết lập cửa hàng → Thiết lập kết nối API**.
2. Tạo một kết nối, lấy: **Client ID**, **Client Secret**, và **Tên gian hàng**
   (phần `xxx` trong địa chỉ `xxx.kiotviet.vn`).

### Khai báo (trong `.env` hoặc Variables trên Railway)
| Biến | Giá trị |
|------|---------|
| `KIOTVIET_CLIENT_ID` | Client ID |
| `KIOTVIET_CLIENT_SECRET` | Client Secret |
| `KIOTVIET_RETAILER` | Tên gian hàng |
| `KIOTVIET_INVOICE_DAYS` | (tùy chọn) số ngày hóa đơn lấy về, mặc định 30 |

Để trống 3 biến đầu nếu chưa dùng — bot vẫn chạy bình thường với dữ liệu lead.

### Dùng
- Lệnh `/doanhthu` → xem nhanh số liệu bán hàng.
- Hoặc hỏi tự nhiên (bot tự nhận biết câu hỏi bán hàng):
  - *"Doanh thu tuần này bao nhiêu?"*
  - *"Sản phẩm/dịch vụ nào bán chạy nhất?"*
  - *"Top khách hàng chi tiêu nhiều nhất?"*

> Bot chỉ gửi **số liệu tổng hợp** (đã tính sẵn) cho Claude để tiết kiệm chi phí,
> không gửi toàn bộ hóa đơn.

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
| `/baocaongay` | Báo cáo ngày: doanh thu **hôm qua** (KiotViet) + lead **hôm nay** (thời gian thực) + tỷ lệ chốt. Tự gửi mỗi sáng nếu đặt `DAILY_REPORT_CHAT_ID` |
| `/chatid` | Hiện Chat ID hiện tại (để đặt `DAILY_REPORT_CHAT_ID` cho báo cáo tự động) |
| `/stats` | Xem nhanh số liệu lead tổng hợp (theo nguồn, trạng thái, dịch vụ, ngày, telesale) |
| `/doanhthu` | Xem nhanh số liệu bán hàng từ KiotViet (nếu đã kết nối) |
| `/chienluoc` | Phân tích chiến lược: bot hỏi khoảng tháng (vd `4-6`), lọc dữ liệu theo thời gian, ghép chi phí ads theo tháng để ra **ROAS theo từng tháng**, rồi đưa kế hoạch **theo tuần và theo tháng**. Có thể gõ nhanh `/chienluoc 4-6` |
| `/refresh` | Tải lại dữ liệu mới nhất từ Google Sheet (và KiotViet nếu có) |

Ngoài ra cứ nhắn câu hỏi tự nhiên là bot trả lời.

---

## Lưu ý

- Dữ liệu được cache `SHEET_CACHE_TTL` giây (mặc định 120s) để đỡ gọi Google liên tục.
  Muốn cập nhật ngay, dùng `/refresh`.
- **Không commit** file `.env` và `service_account.json` lên Git (đã có trong `.gitignore`).
- Mỗi câu hỏi sẽ gửi dữ liệu cho Claude; chi phí phụ thuộc lượng dữ liệu.
  Để tiết kiệm: bot dùng model **Haiku** (rẻ nhất), mặc định **chỉ gửi số liệu
  tổng hợp** (đã tính sẵn), và chỉ gửi dữ liệu chi tiết từng khách khi câu hỏi
  có từ như "liệt kê", "danh sách", "tìm", "số điện thoại"...
- Đổi model bất cứ lúc nào bằng biến môi trường `CLAUDE_MODEL`
  (ví dụ `claude-sonnet-4-6` hoặc `claude-opus-4-8`) — không cần sửa code.

---

## Cấu trúc mã nguồn

| File | Vai trò |
|------|---------|
| `bot.py` | Bot Telegram (điểm khởi chạy) |
| `sheets.py` | Đọc & làm sạch dữ liệu từ Google Sheet |
| `analytics.py` | Tính số liệu tổng hợp chính xác |
| `llm.py` | Gọi Claude để phân tích & trả lời |
| `config.py` | Đọc cấu hình từ `.env` |
