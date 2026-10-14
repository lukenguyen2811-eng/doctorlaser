"""Luật BUỔI THEO GÓI (dữ liệu bịa): ảnh nhãn 'Tên-dịch vụ ngày' mà ngày đó không có HĐ của khách tên
này -> HĐ cũ cùng dịch vụ của khách cùng tên trong 180 ngày trước, CHỈ gợi ý.

Chạy:  python3 -m unittest tests/test_buoi_goi_anh.py
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["ANH_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
import anhkhach as A  # noqa: E402


class BuoiTheoGoi(unittest.TestCase):
    def setUp(self):
        self.c = A.ket_noi()
        self.c.execute("DELETE FROM visits")
        self.c.execute("DELETE FROM photos")

    def tearDown(self):
        self.c.close()

    def hd(self, code, ngay, ma, ten, dv, gio="10:00"):
        self.c.execute("INSERT INTO visits (code,ngay,gio,ma_kh,ten_kh,dich_vu) VALUES (?,?,?,?,?,?)",
                       (code, ngay, gio, ma, ten, dv))

    def khop(self, chu, ngay_anh="2026-10-09"):
        return A._khop_nhan(self.c, A.doc_nhan(chu, 2026)[0], ngay_anh)

    def test_goi_60_ngay_truoc_cung_dich_vu_goi_y(self):
        self.hd("HDG", "2026-08-10", "KH01", "Nguyễn Thị Quyên", "COMBO CSD ( 10 LẦN )")
        hd, d, ly_do = self.khop("Quyên-csd 9/10/26")
        self.assertEqual((hd, d), ("HDG", 50))
        self.assertIn("buổi theo gói — HĐ COMBO CSD ( 10 LẦN ) ngày 10/08/26", ly_do)

    def test_mot_khach_khong_can_chu_goi_chon_hd_gan_nhat(self):
        self.hd("HD1", "2026-06-01", "KH01", "Nguyễn Thị Quyên", "CSD MỤN")
        self.hd("HD2", "2026-09-20", "KH01", "Nguyễn Thị Quyên", "KEM REVITALUX | CSD MỤN")
        self.hd("HD3", "2026-09-25", "KH01", "Nguyễn Thị Quyên", "KEM REVITALUX")  # khác dịch vụ
        self.assertEqual(self.khop("Quyên-csd 9/10/26")[:2], ("HD2", 50))

    def test_khac_dich_vu_khong_ap(self):
        self.hd("HDG", "2026-08-10", "KH01", "Nguyễn Thị Quyên", "COMBO CSD ( 10 LẦN )")
        hd, d, ly_do = self.khop("Quyên-pico 9/10/26")
        self.assertIsNone(hd)
        self.assertIn("không thấy khách tên này", ly_do)

    def test_hai_khach_cung_ten_cung_dich_vu_nguoi_chon(self):
        self.hd("HDA", "2026-08-10", "KH01", "Nguyễn Thị Quyên", "CSD MỤN")
        self.hd("HDB", "2026-09-01", "KH02", "Lê Quyên", "CSD MỤN")
        hd, d, ly_do = self.khop("Quyên-csd 9/10/26")
        self.assertIsNone(hd)
        self.assertIn("2 khách cùng tên có HĐ 'csd'", ly_do)
        self.assertIn("người chọn", ly_do)

    def test_hai_khach_chi_mot_khach_mua_goi_chon_khach_do(self):
        self.hd("HDA", "2026-08-10", "KH01", "Nguyễn Thị Quyên", "COMBO CSD ( 10 LẦN )")
        self.hd("HDA2", "2026-09-10", "KH01", "Nguyễn Thị Quyên", "CSD MỤN")
        self.hd("HDB", "2026-09-30", "KH02", "Lê Quyên", "CSD MỤN")
        self.assertEqual(self.khop("Quyên-csd 9/10/26")[:2], ("HDA2", 50))  # HĐ gần nhất của khách mua gói

    def test_combo_lan_le_khong_tinh_la_goi(self):
        self.hd("HDA", "2026-08-10", "KH01", "Nguyễn Thị Quyên", "COMBO CSD MỤN + PEEL DA MỤN ( LẦN LẺ )")
        self.hd("HDB", "2026-09-01", "KH02", "Lê Quyên", "CSD MỤN")
        self.assertIsNone(self.khop("Quyên-csd 9/10/26")[0])

    def test_qua_180_ngay_khong_ap(self):
        self.hd("HDG", "2026-04-11", "KH01", "Nguyễn Thị Quyên", "COMBO CSD ( 10 LẦN )")  # 181 ngày
        self.assertIsNone(self.khop("Quyên-csd 9/10/26")[0])
        self.hd("HDH", "2026-04-12", "KH01", "Nguyễn Thị Quyên", "COMBO CSD ( 10 LẦN )")  # đúng 180 ngày
        self.assertEqual(self.khop("Quyên-csd 9/10/26")[0], "HDH")

    def test_hd_sau_ngay_chup_khong_tinh(self):
        self.hd("HDS", "2026-10-11", "KH01", "Nguyễn Thị Quyên", "COMBO CSD ( 10 LẦN )")
        self.assertIsNone(self.khop("Quyên-csd 9/10/26")[0])

    def test_nhan_khong_ma_dich_vu_khong_ap(self):
        self.hd("HDG", "2026-08-10", "KH01", "Nguyễn Thị Quyên", "COMBO CSD ( 10 LẦN )")
        self.assertIsNone(self.khop("Quyên 9/10/26")[0])  # nhãn không gạch, không dịch vụ
        self.assertIsNone(self.khop("Quyên-tri 9/10/26")[0])  # mã chung
        self.assertIsNone(self.khop("Quyên-c 9/10/26")[0])  # mã 1 chữ

    def test_ngay_co_khach_cung_ten_khong_chay_luat_goi(self):
        # Trong ngày có khách tên này nhưng lệch dịch vụ -> nhánh cũ (40), không nhảy sang HĐ gói cũ.
        self.hd("HDG", "2026-08-10", "KH01", "Nguyễn Thị Quyên", "COMBO CSD ( 10 LẦN )")
        self.hd("HDN", "2026-10-09", "KH01", "Nguyễn Thị Quyên", "KEM REVITALUX")
        self.assertEqual(self.khop("Quyên-csd 9/10/26")[:2], ("HDN", 40))

    def test_trung_ten_trong_ngay_khong_chay_luat_goi(self):
        self.hd("HDG", "2026-08-10", "KH01", "Nguyễn Thị Quyên", "COMBO CSD ( 10 LẦN )")
        self.hd("HDX", "2026-10-09", "KH03", "Phạm Quyên", "PICO")
        self.hd("HDY", "2026-10-09", "KH04", "Võ Quyên", "PICO")
        hd, _, ly_do = self.khop("Quyên-csd 9/10/26")
        self.assertIsNone(hd)
        self.assertIn("trùng 2 khách", ly_do)

    def test_ghep_ngay_khong_bao_gio_chac_bo_chup_goi_y(self):
        self.hd("HDG", "2026-01-20", "KH01", "Nguyễn Thị Quyên", "COMBO CSD ( 10 LẦN )")
        # Ngày Tết: không HĐ nào. Bộ 5 tư thế, nhãn ở tấm đầu.
        for i in range(5):
            tg = f"2026-02-20T10:00:{i * 10:02d}"
            self.c.execute("INSERT INTO photos (id,ngay,thoi_gian,ten_file,chu_thich,ocr) VALUES (?,?,?,?,?,?)",
                           (f"p{i}", tg[:10], tg, "IMG.HEIC", "", "Quyên-csd 20/2/26" if i == 0 else ""))
        A.ghep_ngay(self.c, "2026-02-20")
        r = {x["id"]: x for x in self.c.execute("SELECT * FROM photos")}
        self.assertEqual({x["do_tin"] for x in r.values()}, {"goi_y"})
        self.assertEqual({x["goi_y_hd"] for x in r.values()}, {"HDG"})
        self.assertIn("buổi theo gói", r["p0"]["ly_do"])
        # Trang duyệt: HĐ cũ cùng năm hiện trong mục "Hóa đơn ngày khác" với ngày dd/mm.
        trang = A._trang_ngay(self.c, "2026-02-20").decode()
        self.assertIn("Hóa đơn ngày khác", trang)
        self.assertIn("<option value='HDG' selected>20/01 ", trang)

    def test_ngay_co_hd_khach_khac_bo_chup_chi_goi_y(self):
        self.hd("HDG", "2026-08-10", "KH01", "Nguyễn Thị Quyên", "COMBO CSD ( 10 LẦN )")
        self.hd("HDK", "2026-10-09", "KH09", "Trần Văn Khác", "PICO", gio="15:00")
        for i in range(5):
            tg = f"2026-10-09T10:00:{i * 10:02d}"
            self.c.execute("INSERT INTO photos (id,ngay,thoi_gian,ten_file,chu_thich,ocr) VALUES (?,?,?,?,?,?)",
                           (f"p{i}", tg[:10], tg, "IMG.HEIC", "", "Quyên-csd 9/10/26" if i == 2 else ""))
        A.ghep_ngay(self.c, "2026-10-09")
        r = list(self.c.execute("SELECT do_tin, goi_y_hd FROM photos"))
        self.assertEqual({tuple(x) for x in r}, {("goi_y", "HDG")})

    def test_trang_duyet_hd_khac_nam_co_nam(self):
        self.hd("HDG", "2025-12-15", "KH01", "Nguyễn Thị Quyên", "COMBO CSD ( 10 LẦN )")
        self.c.execute("INSERT INTO photos (id,ngay,thoi_gian,ten_file,chu_thich,ocr) VALUES"
                       " ('q1','2026-02-20','2026-02-20T10:00:00','IMG.HEIC','','Quyên-csd 20/2/26')")
        A.ghep_ngay(self.c, "2026-02-20")
        p = self.c.execute("SELECT * FROM photos").fetchone()
        self.assertEqual((p["goi_y_hd"], p["do_tin"]), ("HDG", "goi_y"))
        trang = A._trang_ngay(self.c, "2026-02-20").decode()
        self.assertIn("<option value='HDG' selected>15/12/25 ", trang)

    def test_bo_nho_nap_mot_lan_moi_ngay(self):
        self.hd("HDG", "2026-08-10", "KH01", "Nguyễn Thị Quyên", "COMBO CSD ( 10 LẦN )")
        bo = {}
        A._khop_nhan(self.c, A.doc_nhan("Quyên-csd 9/10/26", 2026)[0], "2026-10-09", bo)
        self.assertEqual(list(bo), ["2026-10-09"])
        self.c.execute("DELETE FROM visits")  # đã nạp: lần sau dùng bộ nhớ, không truy vấn lại
        self.assertEqual(A._khop_nhan(self.c, A.doc_nhan("Quyên-csd 9/10/26", 2026)[0], "2026-10-09", bo)[0],
                         "HDG")


if __name__ == "__main__":
    unittest.main()
