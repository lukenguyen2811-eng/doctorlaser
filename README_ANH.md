# Phân loại ảnh khách hàng theo hóa đơn — chạy trên máy Mac công ty

`anhkhach.py` ghép ảnh trong **Photos/iCloud** với **hóa đơn KiotViet**:
ảnh chụp ngày X chỉ có thể thuộc về khách có hóa đơn ngày X → máy gợi ý, người xác nhận,
rồi xuất ảnh vào thư mục theo từng khách. Ảnh gốc trong Photos **không bị sửa/di chuyển**.

## Cài đặt (1 lần)
1. Làm theo `README_MAC.md` để có file `.env` với KiotViet.
2. Cài Python mới (Python 3.9 có sẵn của macOS KHÔNG chạy được osxphotos) + môi trường riêng:
   ```bash
   brew install python@3.12
   cd ~/doctorlaser && /opt/homebrew/bin/python3.12 -m venv .venv
   .venv/bin/pip install -r requirements_anh.txt
   brew install exiftool      # ghi nhãn VÀO TRONG file ảnh (cần Homebrew: brew.sh)
   ```
3. Cho Terminal quyền đọc Photos: **Cài đặt hệ thống → Quyền riêng tư & Bảo mật →
   Truy cập toàn bộ ổ đĩa → bật Terminal**.
4. (Nên) Photos → Cài đặt → iCloud → **Tải bản gốc về máy Mac này** (nếu đủ ổ cứng).

## Làm thử 1 tháng (ví dụ tháng 9/2025)
Mỗi lần mở Terminal mới: `cd ~/doctorlaser && source .venv/bin/activate` (khi đó `python3` là bản 3.12 của dự án).
```bash
python3 anhkhach.py hoadon 2025-09        # 1. kéo hóa đơn tháng 9 từ KiotViet
python3 anhkhach.py quet 2025-09 --ocr --tai-goc   # 2. đọc ảnh tháng 9 (+ tải bản gốc từ iCloud, đọc nhãn trên ảnh)
python3 anhkhach.py ghep 2025-09          # 3. máy tự gợi ý
python3 anhkhach.py duyet                 # 4. mở trang duyệt (dùng Safari)
python3 anhkhach.py baocao 2025-09        # 5. xem tỷ lệ máy đoán đúng
python3 anhkhach.py xuat 2025-09 ~/KhachHang --gan-tu-khoa --kiot   # 6. xuất ảnh theo khách + báo KIOT
```
Nếu ảnh đã được xuất sẵn ra một thư mục: `python3 anhkhach.py quet 2025-09 --thu-muc ~/AnhXuat`
(tên thư mục con/tên file có tên khách cũng được dùng để ghép).

## Máy ghép thế nào
| Mức | Khi nào |
|---|---|
| **Chắc chắn** | Chú thích/tiêu đề/album/từ khóa/chữ trong ảnh/tên file chứa **SĐT, mã KH hoặc họ tên đầy đủ** của 1 khách có hóa đơn cùng ngày; hoặc **nhãn nhân viên ghi trên ảnh** dạng `Tên-dịch vụ ngày/tháng/năm` (vd `Giang-seo 9/10/26`, cần chạy `quet --ocr`) khớp đúng 1 khách — trùng tên thì dùng chữ viết tắt dịch vụ để tách. Nhận cả `Tên / dv`, dịch vụ nhiều chữ (`Trang-meso mắt`), thiếu ngày hoặc ngày đọc sai (dùng ngày chụp), tên nằm giữa họ tên KiotViet có đuôi ghi chú (`... Vy KH7332 GT`) khi dịch vụ cũng khớp |
| **Gợi ý** | Khớp một phần tên (tên đệm + tên); nhãn khớp gần đúng (OCR sai 1 chữ, tên khớp nhưng dịch vụ lệch); cùng **đợt chụp** (cách nhau ≤15 phút) với ảnh đã khớp; hoặc cả ngày chỉ có 1 hóa đơn |
| **Chưa rõ** | Có hóa đơn nhưng không có dấu hiệu nào → người chọn |
| **Không HĐ** | Ngày đó không có hóa đơn (ảnh cá nhân, ảnh khách chưa thanh toán...) |

## Trang duyệt
- Mỗi ngày 1 trang, ảnh chia theo **đợt chụp**. Chọn khách cho cả đợt → **Áp dụng cho cả đợt**.
- Từng ảnh: chọn khách, **trước/trong/sau**, **vùng**, ghi chú tình trạng → **Lưu**.
- **Không phải ảnh khách** để loại ảnh không liên quan.
- **Diễn tiến điều trị của 1 khách:** ô **Tìm khách** ở trang chủ (mã KH, SĐT, tên) → bấm khách,
  hoặc bấm tên khách ở trang ngày. Mỗi lần điều trị (ngày HĐ + dịch vụ) 1 hàng **Trước | Trong | Sau**
  (+ cột *Chưa phân loại*), dưới ảnh là vùng + ghi chú; bấm ảnh để phóng to. Lọc 1 dịch vụ bằng link dịch vụ
  ở đầu trang. Ảnh máy mới gợi ý (chưa ai duyệt) có nhãn **chưa duyệt**; ảnh *Chưa rõ* không hiện.

## Kết quả
```
~/KhachHang/KH000123_NguyenThiAnh_3456/2025-09-03_TriNamLaser/Truoc_100000_IMG_1234.HEIC
~/KhachHang/danh_sach_anh_2025-09.csv     # mở bằng Excel/Numbers để lọc, tìm kiếm
```
Với `--gan-tu-khoa`, ảnh trong Photos được **thêm** từ khóa và chú thích: mã KH, SĐT, họ tên,
dịch vụ, trước/sau, vùng → trên iPad/iPhone (cùng Apple ID, bật Ảnh iCloud) gõ mã KH hoặc SĐT vào ô Tìm kiếm của app Ảnh là ra.

## Bảo mật
Ảnh điều trị là dữ liệu sức khỏe nhạy cảm (NĐ 13/2023). `anhkhach.db` và thư mục
`KhachHang/` chỉ nằm trên máy, đã bị chặn khỏi git. Trang duyệt chỉ mở trên chính máy
(localhost), không ai ngoài máy truy cập được.

## Lưu trữ để KHÔNG BAO GIỜ mất nhãn
Nhãn được ghi ở 4 nơi, mất 1 nơi vẫn còn 3:

| Nơi | Đi theo khi chép / đẩy Google Drive? | Dùng để |
|---|---|---|
| **Tên thư mục + tên file** (`KH000123_NguyenThiAnh_3456/2025-09-03_TriNamLaser/KH000123_2025-09-03_Truoc_...jpg`) | ✅ luôn còn | Tìm trên Google Drive / Finder theo mã KH, tên |
| **Bên trong file ảnh** (từ khóa + chú thích IPTC/XMP, cần `exiftool`) | ✅ còn, kể cả file bị tách lẻ | Lightroom, Bridge, nhập lại Photos, Google Photos |
| **File danh sách CSV** (`danh_sach_anh_YYYY-MM.csv`) + `anhkhach.db` | ✅ (nhớ chép kèm) | Lọc/thống kê bằng Excel, Google Sheet, nghiên cứu |
| **Từ khóa + chú thích trong Photos** (`--gan-tu-khoa`) | ❌ chỉ trong Photos/iCloud | Tìm nhanh trên iPad/iPhone |

**Sao lưu 3-2-1:** Mac mini (bản chính) + ổ cứng ngoài Time Machine + Google Drive.
Đẩy cả thư mục `~/KhachHang` lên Drive bằng app **Google Drive for desktop** (tự đồng bộ).
Dùng tài khoản Google **của công ty** (Workspace), bật xác minh 2 bước, KHÔNG chia sẻ link công khai.

## Tra cứu nhanh cho nhân viên (app KIOT + bot Telegram)
Ảnh **không** được tải lên KIOT. KIOT chỉ giữ **chỉ mục theo hóa đơn**: ngày, dịch vụ, số ảnh
trước/sau, và link mở ảnh trên Google Drive (mặc định là tìm mã KH trong Drive công ty).

- Cần `KIOT_INGEST_TOKEN` trong `.env` (copy `INGEST_TOKEN` của service kiot trên Railway).
- Đẩy chỉ mục: `python3 anhkhach.py daykiot 2025-09` (hoặc thêm `--kiot` khi `xuat`).
  Gửi lại nhiều lần không sao — KIOT ghi đè theo mã hóa đơn.
- **Trên KIOT:** mở hồ sơ khách hoặc hóa đơn → mục **📷 Ảnh điều trị** → **Mở ảnh**.
- **Trên Telegram:** `/anh 0909123456`, `/anh KH000123` hoặc `/anh HD012345`.
  (Bot trên Railway cũng cần biến `KIOT_INGEST_TOKEN` — bot đã dùng sẵn cho các lệnh KIOT khác.)
