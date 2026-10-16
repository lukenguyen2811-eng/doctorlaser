"""Lượng chốt 17/10: ảnh BIÊN LAI CHUYỂN KHOẢN và MÀN HÌNH MÁY laser (kể cả có nhãn tên khách / thông số) KHÔNG lưu
theo khách. DB tạm, dữ liệu bịa.

Chạy:  python3 -m unittest tests/test_khong_luu_anh.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_ten_cuoi_mat_anh import A, D, Nen  # noqa: E402

MAY = "Energy 27.0 mJ  Pulse width 1.5 ms  Fractional  times 2  Ready"
BL = "Chuyển khoản thành công  1.300.000 VND  Vietcombank  Mã giao dịch FT22155006740838"


class NhanDien(unittest.TestCase):
    def test_bien_lai(self):
        self.assertEqual(A.loai_khong_luu(BL)[0], "bien_lai")
        self.assertEqual(A.loai_khong_luu("Techcombank 500 000 VND ngày 4/6/2022 chia sẻ")[0], "bien_lai")

    def test_man_hinh_may(self):
        self.assertEqual(A.loai_khong_luu(MAY)[0], "man_hinh_may")
        self.assertEqual(A.loai_khong_luu("1064 pulsecount 10000 15 Hz 500 mJ 1.56 J/cm2 picosecond")[0], "man_hinh_may")
        self.assertEqual(A.loai_khong_luu("Lan - csd 10/10/26 " + MAY)[0], "man_hinh_may")  # có nhãn tên vẫn là màn hình

    def test_nhan_khach_chu_dich_vu_khong_nham(self):  # âm: nhãn khách có chữ 'pico' / 'fractional' / 'laser lift'
        for t in ("Lan - pico 10/10/26", "Hà - fractional co2 12/3/26", "Thu Trang pico 1064 10/10/26",
                  "Mai - laser lift toning 3/4/25", "Vy - pico 5 lần 20/9/26", ""):
            self.assertIsNone(A.loai_khong_luu(t)[0], t)

    def test_phieu_dieu_tri_khong_nham(self):  # âm (soát BACC2728): phiếu điều trị ghi thông số -> giấy tờ khách
        self.assertIsNone(A.loai_khong_luu("PHIẾU ĐIỀU TRỊ Họ tên ... Energy 20 mJ 10 Hz")[0])

    def test_so_tien_khong_kem_dau_hieu_khac(self):  # âm: 1 dấu hiệu (giá) không đủ biên lai
        self.assertIsNone(A.loai_khong_luu("Combo 1.500.000 đ")[0])


class Ghep(Nen):
    def nen(self):
        self.hd("H1", D, "K1", "Phan Thị Lan", "CSD MỤN", "10:00")
        self.hd("H2", D, "K2", "Trần Văn Nam", "CSD MỤN", "15:00")

    def test_man_hinh_khong_chac_khong_goi_y(self):
        self.nen()
        i = self.anh(D, "10:05:00", "Lan - csd 10/10/26 " + MAY)
        kq = self.ghep()
        self.assertEqual(kq[i][:2], (None, "chua_ro"))
        self.assertTrue(kq[i][2].startswith(A.KHONG_LUU))
        self.assertEqual(self.c.execute("SELECT may_loai FROM photos WHERE id=?", (i,)).fetchone()[0], "man_hinh_may")

    def test_bien_lai_khong_luu(self):
        self.nen()
        i = self.anh(D, "10:05:00", BL)
        self.assertEqual(self.ghep()[i][:2], (None, "chua_ro"))

    def test_man_hinh_khong_lam_neo(self):  # mặc định: nhãn trên màn hình máy không kéo ảnh cùng bộ
        self.nen()
        ids = [self.anh(D, "10:05:00", "Lan - csd 10/10/26 " + MAY), self.anh(D, "10:05:05"), self.anh(D, "10:05:10")]
        kq = self.ghep()
        self.assertFalse([i for i in ids[1:] if kq[i][0] == "H1" and kq[i][1] == "chac"])

    def test_neo_yeu_bat_thi_chi_goi_y(self):  # BAT_LUAT=NHAN_MAY: ảnh cùng bộ chỉ được GỢI Ý
        self.nen()
        ids = [self.anh(D, "22:30:00", "Lan - csd 10/10/26 " + MAY), self.anh(D, "22:30:05")]
        A._BAT.add("NHAN_MAY")
        try:
            kq = self.ghep()
        finally:
            A._BAT.discard("NHAN_MAY")
        self.assertEqual(kq[ids[1]][:2], ("H1", "goi_y"))
        self.assertIn("neo yếu", kq[ids[1]][2])

    def test_anh_khach_nhan_pico_van_chac(self):  # âm
        self.nen()
        i = self.anh(D, "10:05:00", "Phan Thị Lan - pico 10/10/26")
        self.assertEqual(self.ghep()[i][1], "chac")

    def test_trang_duyet_an(self):
        self.nen()
        i = self.anh(D, "10:05:00", BL)
        self.ghep()
        n = self.c.execute(f"SELECT COUNT(*) FROM photos WHERE id=? AND {A.CAN_DUYET}", (i,)).fetchone()[0]
        self.assertEqual(n, 0)

    def test_album_khong_lay(self):
        import album_anh
        self.nen()
        i = self.anh(D, "10:05:00", "Phan Thị Lan - csd 10/10/26")
        j = self.anh(D, "10:06:00", BL)
        self.ghep()
        self.c.execute("UPDATE photos SET nguon='photos'")
        ids = {r["id"] for r in album_anh.anh_dung(self.c)}
        self.assertIn(i, ids)
        self.assertNotIn(j, ids)
