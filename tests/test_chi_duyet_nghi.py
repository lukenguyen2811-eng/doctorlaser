"""Trang duyệt chỉ hiện ảnh cần duyệt (Lượng 16/10).  python3 -m unittest tests/test_chi_duyet_nghi.py"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["ANH_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
import anhkhach as A  # noqa: E402


class ChiDuyetNghi(unittest.TestCase):
    def setUp(self):
        self.c = A.ket_noi()
        for t in ("photos", "visits"):
            self.c.execute(f"DELETE FROM {t}")
        self.c.execute("INSERT INTO visits (code,ngay,gio,ma_kh,ten_kh,dich_vu) VALUES ('H1','2026-10-05','10:00','KH1','Khách A','Pico')")
        for pid, gio, do_tin, ly_do, xn in [("chac1", "10:00", "chac", "nhãn khớp", None),
                                            ("goiy1", "10:01", "goi_y", "cùng bộ", None),
                                            ("chuaro", "15:00", "chua_ro", "", None),
                                            ("canhbao", "17:00", "goi_y", "cảnh báo: khuôn mặt thuộc khách khác", None),
                                            ("daduyet", "18:00", "goi_y", "", "H1")]:
            self.c.execute("INSERT INTO photos (id,nguon,ngay,thoi_gian,ten_file,goi_y_hd,do_tin,ly_do,xn_hd,dot,chu_thich,ocr)"
                           " VALUES (?,'photos','2026-10-05',?,?, 'H1',?,?,?,?, '', '')",
                           (pid, f"2026-10-05T{gio}:00", pid + ".jpg", do_tin, ly_do, xn, {"10": 0, "15": 1, "17": 2, "18": 3}[gio[:2]]))
        self.c.commit()

    def tearDown(self):
        self.c.close()

    def test_trang_ngay_an_anh_chac(self):
        t = A._trang_ngay(self.c, "2026-10-05").decode()
        self.assertNotIn("id='pchac1'", t)
        for pid in ("goiy1", "chuaro", "canhbao", "daduyet"):
            self.assertIn(f"id='p{pid}'", t)  # ảnh đã duyệt vẫn hiện để sửa lại
        self.assertIn("1 ảnh chắc chắn đã ẩn", t)
        self.assertLess(t.index("id='pcanhbao'"), t.index("id='pgoiy1'"))  # cảnh báo lên đầu

    def test_xem_ca_anh_chac(self):
        self.assertIn("id='pchac1'", A._trang_ngay(self.c, "2026-10-05", tat_ca=True).decode())

    def test_trang_chu_dem_can_duyet(self):
        t = A._trang_chu(self.c).decode()
        self.assertIn("cần duyệt 3", t)  # goiy1, chuaro, canhbao (không tính chắc và đã duyệt)
        self.assertIn("1 cảnh báo", t)


if __name__ == "__main__":
    unittest.main()
