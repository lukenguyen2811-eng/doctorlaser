"""Đọc nhãn nhân viên ghi trên ảnh + ghép với hóa đơn (dữ liệu bịa).

Chạy:  python3 -m unittest tests/test_nhan_anh.py
Mẫu chữ lấy theo đúng kiểu OCR thật đọc ra tháng 10/2026 (tên đã thay).
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["ANH_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
import anhkhach as A  # noqa: E402


class DocNhan(unittest.TestCase):
    def mot(self, chu):
        ds = A.doc_nhan(chu, 2026)
        self.assertEqual(len(ds), 1, (chu, ds))
        return ds[0]

    def test_kieu_cu(self):
        n = self.mot("Giang-sẹo 9/10/26")
        self.assertEqual((n["ten"], n["ma_dv"], n["ngay"]), ("giang", "seo", "2026-10-09"))

    def test_dich_vu_nhieu_chu_va_so(self):
        self.assertEqual(self.mot("Tam-meso mắt 5/10/26")["ngay"], "2026-10-05")
        n = self.mot("Bich-co2 nốt ruồi 5/10/26")
        self.assertEqual((n["ten"], n["ma_dv"], n["ngay"]), ("bich", "co2", "2026-10-05"))
        self.assertEqual(self.mot("Bich-co2 môi. 8/10/26")["ngay"], "2026-10-08")

    def test_xuyet_va_rac(self):
        self.assertEqual(self.mot("Kieu / pico 7/10/26")["ten"], "kieu")
        n = self.mot("Lee min- csd C32•8/10/26")
        self.assertEqual((n["ten"], n["ma_dv"], n["ngay"]), ("lee min", "csd", "2026-10-08"))

    def test_hai_o_chu_ten_rieng_ngay_rieng(self):  # Vision trả tên và ngày thành 2 ô
        n = self.mot("Hoà-Ha mắt 8/10126")
        self.assertEqual((n["ten"], n["ma_dv"], n["ngay"]), ("hoa", "ha", "2026-10-08"))

    def test_thieu_ngay(self):
        self.assertIsNone(self.mot("Hoà-Ha mắt")["ngay"])

    def test_chi_co_ngay_khong_la_nhan(self):
        self.assertEqual(A.doc_nhan("6/10/26", 2026), [])
        self.assertEqual(A.doc_nhan("Doctor Laser 1/10/26", 2026), [])

    def test_hai_nhan_tren_mot_anh(self):
        ds = A.doc_nhan("Tam-pico 1/10/26 Bich-csd 2/10/26", 2026)
        self.assertEqual([(n["ten"], n["ngay"]) for n in ds],
                         [("tam", "2026-10-01"), ("bich", "2026-10-02")])


class KhopNhan(unittest.TestCase):
    def setUp(self):
        self.c = A.ket_noi()
        self.c.execute("DELETE FROM visits")
        for code, ngay, ten, dv in [
            ("HD1", "2026-10-08", "Nguyễn Thị Hoà", "Tiêm HA mắt"),
            ("HD2", "2026-10-08", "Trần Văn Elan", "Laser Pico"),
            ("HD3", "2026-10-05", "Lê Thị Tâm", "Meso mắt"),
            ("HD4", "2026-10-05", "Phạm Tâm", "Trị sẹo rỗ"),
            ("HD5", "2026-10-06", "Võ Minh Anh", "CSD"),
            ("HD6", "2026-10-03", "Manami Yoshida", "CSD"),
            ("HD7", "2026-10-03", "Đỗ Văn Thanh", "Botox"),
            ("HD8", "2026-10-09", "Đoàn Thanh Vy KH7332 GT", "CSD mụn lần lẻ"),
            ("HD9", "2026-10-08", "Lý Thị Hoà", "Tiêm HA mắt"),
        ]:
            self.c.execute("INSERT INTO visits (code,ngay,ten_kh,dich_vu) VALUES (?,?,?,?)",
                           (code, ngay, ten, dv))

    def tearDown(self):
        self.c.close()

    def khop(self, chu, ngay_anh):
        return A._khop_nhan(self.c, A.doc_nhan(chu, 2026)[0], ngay_anh)

    def test_nam_doc_sai_dung_ngay_chup(self):
        hd, d, ly_do = self.khop("Elan- pico 8/10/16", "2026-10-08")
        self.assertEqual((hd, d), ("HD2", 85))
        self.assertIn("dùng ngày chụp", ly_do)

    def test_trung_ten_trung_dich_vu_nguoi_chon(self):
        hd, d, ly_do = self.khop("Hoà / Ha mắt 08/10/26", "2026-10-09")
        self.assertIsNone(hd)
        self.assertIn("trùng 2 khách (nhãn ghi ngày 2026-10-08)", ly_do)

    def test_thieu_ngay_dung_ngay_chup(self):
        self.assertEqual(self.khop("Elan-pico", "2026-10-08")[:2], ("HD2", 85))

    def test_trung_ten_tach_bang_dich_vu(self):
        self.assertEqual(self.khop("Tâm-meso mắt 5/10/26", "2026-10-05")[0], "HD3")
        self.assertEqual(self.khop("Tâm-sẹo 5/10/26", "2026-10-05")[0], "HD4")

    def test_chu_thua_truoc_ten_chi_goi_y(self):
        hd, d, _ = self.khop("Laser Anh-csd 6/10/26", "2026-10-06")
        self.assertEqual((hd, d), ("HD5", 50))  # khớp đuôi tên -> không 'chắc chắn'

    def test_ten_trong_ho_ten_co_duoi_ghi_chu(self):
        self.assertEqual(self.khop("Vy-csd 9/10/26", "2026-10-09")[:2], ("HD8", 85))  # + dịch vụ khớp
        self.assertEqual(self.khop("Vy-pico 9/10/26", "2026-10-09")[:2], ("HD8", 50))  # dịch vụ lệch
        self.assertEqual(self.khop("Manami- csd 3/10/26", "2026-10-03")[:2], ("HD6", 85))

    def test_ocr_sai_mot_chu_chi_goi_y(self):
        self.assertEqual(self.khop("Thann-botox 3/10/26", "2026-10-03")[:2], ("HD7", 50))
        self.assertIsNone(self.khop("Thao-botox 3/10/26", "2026-10-03")[0])  # lệch 2 chữ
        self.assertIsNone(self.khop("Tan-botox 3/10/26", "2026-10-03")[0])  # tên ngắn: không đoán

    def test_lech_1(self):
        self.assertTrue(A._lech_1("thann", "thanh"))
        self.assertTrue(A._lech_1("thnh", "thanh"))
        self.assertFalse(A._lech_1("thanh", "thanh"))
        self.assertFalse(A._lech_1("thao", "thanh"))

    def test_khong_co_khach_ten_nay(self):
        self.assertIsNone(self.khop("Quang-pico 8/10/26", "2026-10-08")[0])

    def test_ghep_ngay_danh_dau_muc_tin(self):
        self.c.execute("DELETE FROM photos")
        for pid, tg, ocr in [("p1", "2026-10-06T10:00:00", "Laser Anh-csd 6/10/26"),
                             ("p2", "2026-10-06T15:00:00", "6/10/26")]:
            self.c.execute("INSERT INTO photos (id,ngay,thoi_gian,ten_file,chu_thich,ocr)"
                           " VALUES (?,?,?,?,?,?)", (pid, tg[:10], tg, "IMG.HEIC", "", ocr))
        A.ghep_ngay(self.c, "2026-10-06")
        r = dict(self.c.execute("SELECT id, do_tin FROM photos").fetchall())
        self.assertEqual(r["p1"], "goi_y")

    def test_trang_duyet_chon_duoc_hoa_don_ngay_khac(self):
        self.c.execute("DELETE FROM photos")
        self.c.execute("INSERT INTO photos (id,ngay,thoi_gian,ten_file,chu_thich,ocr,dot)"
                       " VALUES ('p9','2026-10-10','2026-10-10T09:43:00','IMG.jpg','','Hoà-Ha mắt 8/10/26',0)")
        A.ghep_ngay(self.c, "2026-10-10")
        self.assertEqual(self.c.execute("SELECT goi_y_hd FROM photos").fetchone()[0], None)  # trùng 2 Hoà
        self.c.execute("UPDATE photos SET goi_y_hd='HD2'")
        trang = A._trang_ngay(self.c, "2026-10-10").decode()
        self.assertIn("<option value='HD2' selected>08/10", trang)
        self.assertIn("Hóa đơn ngày khác", trang)


if __name__ == "__main__":
    unittest.main()
