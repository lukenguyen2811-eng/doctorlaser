# Chạy trên máy Mac — kéo dữ liệu nguồn về máy bạn

`local_sync.py` kéo dữ liệu từ **KiotViet, Meta (Facebook ads), Google Sheet (lead)**
về **1 file database trên máy bạn** (`doctorlaser.db`) + xuất **CSV** (mở bằng
Excel/Numbers). Bạn tự kiểm soát, tích lũy lịch sử. Bot trên Railway vẫn chạy song song.

## Cài đặt (làm 1 lần)

1. **Cài Python 3** (Mac thường có sẵn; nếu chưa: cài qua https://www.python.org/ hoặc `brew install python`).
2. Mở **Terminal**, vào thư mục project (nơi có `local_sync.py`):
   ```bash
   cd ~/Downloads/doctorlaser   # đổi theo nơi bạn để folder
   ```
3. Cài thư viện:
   ```bash
   pip3 install -r requirements.txt
   ```
4. Tạo file **`.env`** (copy từ `.env.example`) và điền credentials các NGUỒN:
   ```
   GOOGLE_SHEET_ID=...
   GOOGLE_SHEET_GID=269413507
   GOOGLE_SERVICE_ACCOUNT_FILE=service_account.json
   KIOTVIET_CLIENT_ID=...
   KIOTVIET_CLIENT_SECRET=...
   KIOTVIET_RETAILER=...
   META_ACCESS_TOKEN=...
   META_AD_ACCOUNT_ID=act_309455834931087
   ```
   (Không cần TELEGRAM/ANTHROPIC cho local_sync.)
5. Đặt file **`service_account.json`** vào cùng thư mục.

## Chạy đồng bộ
```bash
python3 local_sync.py        # 6 tháng gần nhất
python3 local_sync.py 12     # 12 tháng gần nhất
```
Kết quả:
- `doctorlaser.db` — database SQLite (mở bằng "DB Browser for SQLite" nếu muốn)
- `export/leads.csv`, `export/invoices.csv`, `export/ads.csv` — mở bằng Excel/Numbers

## Tự chạy hằng ngày (máy Mac bật cả ngày)
Hẹn giờ bằng cron. Mở Terminal:
```bash
crontab -e
```
Thêm dòng (chạy 7h sáng mỗi ngày — đổi đường dẫn cho đúng):
```
0 7 * * * cd /Users/TENBAN/Downloads/doctorlaser && /usr/bin/python3 local_sync.py >> sync.log 2>&1
```
Lưu lại. Mỗi 7h sáng máy sẽ tự kéo dữ liệu mới về.

## Dữ liệu của bạn
- Toàn bộ nằm **trên máy bạn** (`doctorlaser.db` + `export/`).
- Không tự upload đi đâu. Bạn toàn quyền kiểm soát, sao lưu, phân tích.
