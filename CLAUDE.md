# doctorlaser

Bot Telegram phân tích dữ liệu phòng khám Doctor Laser: lead từ Google Sheet,
doanh thu KiotViet, chi phí ads Meta/TikTok, báo cáo ngày. Trả lời bằng tiếng Việt,
dùng Claude để diễn giải số liệu.

## BẮT BUỘC — phối hợp với repo `kiot`

Repo này là **1 trong 2 "nhân viên"**. Repo còn lại: `kiot`.

1. **Đầu mỗi lượt làm việc**, chạy `./scripts/team.sh` để đọc `STATUS.md` của cả 2 bên.
   Nếu `kiot` đang dở việc chạm cùng vùng code → dừng, báo người dùng.
2. **Cuối mỗi lượt**, cập nhật `STATUS.md` của repo này (đang làm / vừa xong /
   đang chờ bên kia / cảnh báo cho bên kia) và commit chung với code.
3. Luật phân vai, ranh giới sở hữu, hợp đồng giao tiếp: đọc `TEAM.md`.
   `TEAM.md` phải giống hệt nhau ở cả 2 repo — sửa một bên thì copy sang bên kia.
4. Không sửa file thuộc mảng của `kiot`. Cần thay đổi thì ghi vào mục
   *Đang chờ bên kia* trong `STATUS.md`.

## Bản đồ mã nguồn

| File | Việc |
|---|---|
| `bot.py` | Bot Telegram, định tuyến câu hỏi, lệnh (lớn nhất, 870 dòng) |
| `config.py` | Đọc biến môi trường / `.env` |
| `sheets.py` | Đọc & làm sạch lead từ Google Sheet (Service Account) |
| `analytics.py` | Tính số liệu lead chính xác trước khi đưa cho Claude |
| `crm.py` | Đọc sheet CRM chatbot (`CRM_DoctorLaser_v3`) |
| `kiotviet.py` | KiotViet Public API — OAuth2 client_credentials, hóa đơn, khách |
| `sales.py` | Tổng hợp số bán hàng từ hóa đơn KiotViet |
| `meta.py` | Meta Marketing API — chi phí & hiệu quả ads |
| `tiktok.py` | TikTok Ads qua endpoint MCP (JSON-RPC) |
| `sync_token.py` | Tự refresh token TikTok rồi đẩy lên Railway |
| `adspend.py` | Chi phí ads theo tháng từ sheet pivot |
| `report.py` | Báo cáo ngày — doanh thu hôm qua, lead hôm nay |
| `strategy.py` | Doanh thu & ROAS theo dịch vụ / kênh / sale |
| `llm.py` | Gọi Claude (`anthropic`) |
| `local_sync.py` | Đồng bộ về máy Mac (SQLite + CSV) |

## Chạy

```bash
pip install -r requirements.txt
cp .env.example .env    # rồi điền key
python bot.py           # Procfile: worker: python bot.py (Railway)
```

## Lưu ý

- **Không commit** `.env`, `service_account.json`, `.tiktok_refresh`, `.token_synced`
  — đã có trong `.gitignore`, giữ nguyên.
- Dữ liệu có số điện thoại khách. Không in dữ liệu thật ra log hay ví dụ trong tài liệu.
- Số liệu phải tính bằng Python (`analytics.py`, `sales.py`) rồi mới đưa cho Claude
  diễn giải — không để mô hình tự cộng trừ.
- Commit message trong repo này viết tiếng Việt **không dấu**, giữ đúng nếp đó.
