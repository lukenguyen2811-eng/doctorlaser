# Phân loại ảnh khách hàng theo hóa đơn — chạy trên máy Mac công ty

`anhkhach.py` ghép ảnh trong **Photos/iCloud** với **hóa đơn KiotViet**:
ảnh chụp ngày X chỉ có thể thuộc về khách có hóa đơn ngày X → máy gợi ý, người xác nhận,
rồi xuất ảnh vào thư mục theo từng khách. Ảnh gốc trong Photos **không bị sửa/di chuyển**.

## Cài đặt (1 lần)
1. Làm theo `README_MAC.md` để có file `.env` với KiotViet.
2. Cài thư viện:
   ```bash
   pip3 install -r requirements_anh.txt
   ```
3. Cho Terminal quyền đọc Photos: **Cài đặt hệ thống → Quyền riêng tư & Bảo mật →
   Truy cập toàn bộ ổ đĩa → bật Terminal**.
4. (Nên) Photos → Cài đặt → iCloud → **Tải bản gốc về máy Mac này** (nếu đủ ổ cứng).

## Làm thử 1 tháng (ví dụ tháng 9/2025)
```bash
python3 anhkhach.py hoadon 2025-09        # 1. kéo hóa đơn tháng 9 từ KiotViet
python3 anhkhach.py quet 2025-09 --ocr    # 2. đọc ảnh tháng 9 trong Photos (+ đọc chữ trong ảnh)
python3 anhkhach.py ghep 2025-09          # 3. máy tự gợi ý
python3 anhkhach.py duyet                 # 4. mở trang duyệt (dùng Safari)
python3 anhkhach.py baocao 2025-09        # 5. xem tỷ lệ máy đoán đúng
python3 anhkhach.py xuat 2025-09 ~/KhachHang --gan-tu-khoa   # 6. xuất ảnh theo khách
```
Nếu ảnh đã được xuất sẵn ra một thư mục: `python3 anhkhach.py quet 2025-09 --thu-muc ~/AnhXuat`
(tên thư mục con/tên file có tên khách cũng được dùng để ghép).

## Máy ghép thế nào
| Mức | Khi nào |
|---|---|
| **Chắc chắn** | Chú thích/tiêu đề/album/từ khóa/chữ trong ảnh/tên file chứa **SĐT, mã KH hoặc họ tên đầy đủ** của 1 khách có hóa đơn cùng ngày |
| **Gợi ý** | Khớp một phần tên (tên đệm + tên); cùng **đợt chụp** (cách nhau ≤15 phút) với ảnh đã khớp; hoặc cả ngày chỉ có 1 hóa đơn |
| **Chưa rõ** | Có hóa đơn nhưng không có dấu hiệu nào → người chọn |
| **Không HĐ** | Ngày đó không có hóa đơn (ảnh cá nhân, ảnh khách chưa thanh toán...) |

## Trang duyệt
- Mỗi ngày 1 trang, ảnh chia theo **đợt chụp**. Chọn khách cho cả đợt → **Áp dụng cho cả đợt**.
- Từng ảnh: chọn khách, **trước/trong/sau**, **vùng**, ghi chú tình trạng → **Lưu**.
- **Không phải ảnh khách** để loại ảnh không liên quan.

## Kết quả
```
~/KhachHang/KH000123_NguyenThiAnh_3456/2025-09-03_TriNamLaser/Truoc_100000_IMG_1234.HEIC
~/KhachHang/danh_sach_anh_2025-09.csv     # mở bằng Excel/Numbers để lọc, tìm kiếm
```
Với `--gan-tu-khoa`, ảnh trong Photos được **thêm** từ khóa `KH:KH000123`, `KH:Nguyễn Thị Ánh`,
`DV:Trị nám Laser`, `Loai:trước`... → gõ vào ô tìm kiếm của Photos (Mac/iPhone) là ra.

## Bảo mật
Ảnh điều trị là dữ liệu sức khỏe nhạy cảm (NĐ 13/2023). `anhkhach.db` và thư mục
`KhachHang/` chỉ nằm trên máy, đã bị chặn khỏi git. Trang duyệt chỉ mở trên chính máy
(localhost), không ai ngoài máy truy cập được.
