# TEAM — Sổ tay phối hợp giữa 2 repo

> File này **giống hệt nhau** ở cả `doctorlaser` và `kiot`.
> Sửa ở một bên thì phải copy sang bên kia trong cùng lượt làm việc.

## Sơ đồ

```
                 ┌─────────────────────┐
                 │   QUẢN LÝ TỔNG      │  (phiên Claude / bạn)
                 │  giao việc, duyệt    │
                 └──────────┬──────────┘
                            │
              ┌─────────────┴─────────────┐
              ▼                           ▼
    ┌───────────────────┐       ┌───────────────────┐
    │   doctorlaser     │       │      kiot         │
    │   "nhân viên A"   │◄─────►│   "nhân viên B"   │
    └───────────────────┘ STATUS└───────────────────┘
      Bot Telegram, lead,         (chưa nhận việc)
      ads, báo cáo
```

## Phân vai — ai sở hữu cái gì

| Mảng | Chủ sở hữu | Ghi chú |
|---|---|---|
| Bot Telegram, xử lý câu hỏi | `doctorlaser` | `bot.py` |
| Lead từ Google Sheet | `doctorlaser` | `sheets.py`, `analytics.py` |
| CRM chatbot | `doctorlaser` | `crm.py` |
| Chi phí ads Meta / TikTok | `doctorlaser` | `meta.py`, `tiktok.py`, `adspend.py`, `sync_token.py` |
| Báo cáo ngày, chiến lược, ROAS | `doctorlaser` | `report.py`, `strategy.py` |
| Gọi Claude | `doctorlaser` | `llm.py` |
| KiotViet (hóa đơn, khách, doanh thu) | **chưa chốt** | Hiện nằm ở `doctorlaser`: `kiotviet.py`, `sales.py`. Xem "Đề xuất" bên dưới. |

**Nguyên tắc:** không sửa file thuộc mảng của repo kia. Cần thay đổi thì ghi vào
mục *Đang chờ bên kia* trong `STATUS.md` của mình.

## Quy tắc bắt buộc mỗi lượt làm việc

1. **Trước khi làm** — đọc `STATUS.md` của repo kia (xem cách ở dưới).
   Nếu bên kia đang dở việc chạm vào cùng chỗ, dừng lại và báo quản lý tổng.
2. **Sau khi làm** — cập nhật `STATUS.md` của repo mình: đang làm gì, vừa xong gì,
   đang chờ bên kia gì, và **cảnh báo** nếu thay đổi này ảnh hưởng bên kia.
3. **Đổi hợp đồng giao tiếp** (mục dưới) thì phải cập nhật `TEAM.md` ở **cả 2 repo**
   và tăng số phiên bản hợp đồng.
4. Commit `STATUS.md` chung với commit code, không để lệch.

## Cách xem trạng thái bên kia

Theo thứ tự ưu tiên:

1. **Clone cạnh nhau** (nhanh nhất, đang dùng trong phiên Claude web):
   ```bash
   ./scripts/team.sh
   ```
   Script đọc `../doctorlaser/STATUS.md` và `../kiot/STATUS.md`.

2. **Qua GitHub** khi chỉ có 1 repo trong máy — cả 2 repo đều **private**, nên
   `curl` raw sẽ trả 404. Dùng công cụ GitHub có xác thực, hoặc clone repo kia:
   ```bash
   git clone https://github.com/lukenguyen2811-eng/kiot ../kiot
   ```

3. **Hỏi quản lý tổng** nếu cả 2 cách trên không được.

## Hợp đồng giao tiếp (contract)

**Phiên bản: v0 — chưa có kênh nào.**

Hiện 2 repo chưa gọi nhau, chưa dùng chung dữ liệu. Khi bắt đầu có, ghi vào đây:
tên kênh (HTTP / sheet / DB), địa chỉ, hình dạng dữ liệu vào–ra, ai đổi được, ai chỉ đọc.

Chưa chốt thì không bên nào được tự ý gọi sang bên kia.

## Đề xuất đang chờ duyệt — ranh giới cho `kiot`

`kiot` hiện rỗng. Đề xuất: tách toàn bộ mảng KiotViet ra khỏi `doctorlaser`.

- `kiot` giữ: OAuth2 token KiotViet, kéo hóa đơn/khách hàng, tổng hợp doanh thu.
  (chuyển `kiotviet.py` + `sales.py` sang)
- `doctorlaser` giữ: bot, lead, ads, báo cáo — và **gọi sang `kiot`** để lấy số bán hàng.
- Hợp đồng lên v1 khi tách: `kiot` cung cấp số liệu, `doctorlaser` chỉ đọc.

**Chưa thực hiện.** Cần quản lý tổng duyệt trước.
