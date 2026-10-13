"""Ghi nhãn ảnh 'chắc chắn' vào app Ảnh (photoscript giả).  python3 -m unittest tests/test_gan_chac.py"""
import json
import os
import sys
import tempfile
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["ANH_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
import anhkhach as A  # noqa: E402
import gan_chac as G  # noqa: E402

KHO = {}


class AnhGia:
    def __init__(self, uuid):
        self.__dict__["_u"] = uuid
        KHO.setdefault(uuid, {"keywords": ["cu"], "description": "chú thích cũ"})

    def __getattr__(self, k):
        return KHO[self._u][k]

    def __setattr__(self, k, v):
        KHO[self._u][k] = v


GIA = types.SimpleNamespace(Photo=AnhGia)


class GanChac(unittest.TestCase):
    def setUp(self):
        KHO.clear()
        c = A.ket_noi()
        for t in ("photos", "visits"):
            c.execute(f"DELETE FROM {t}")
        c.execute("DROP TABLE IF EXISTS da_gan_chac")
        c.execute("INSERT INTO visits (code,ngay,gio,ma_kh,ten_kh,sdt,dich_vu) VALUES"
                  " ('H1','2026-09-01','10:00','KH000001','Khách A','0901234567','Laser Pico')")
        for pid, do_tin, bo_qua, xn in [("a", "chac", 0, None), ("b", "goi_y", 0, None),
                                         ("c", "chac", 1, None), ("d", "chac", 0, "H1")]:
            c.execute("INSERT INTO photos (id,nguon,ngay,thoi_gian,ten_file,goi_y_hd,do_tin,bo_qua,xn_hd)"
                      " VALUES (?,'photos','2026-09-01','2026-09-01T10:00:00','I.HEIC','H1',?,?,?)",
                      (pid, do_tin, bo_qua, xn))
        c.commit()
        c.close()

    def chay(self, *thamso):
        with mock.patch.dict(sys.modules, {"photoscript": GIA}), mock.patch.object(sys, "argv", ["x", *thamso]):
            G.main()

    def test_chi_ghi_anh_chac_chua_duyet_chua_loai(self):
        self.chay("2026-09", "--ghi")
        self.assertEqual(sorted(KHO), ["a"])  # b gợi ý, c bị loại, d đã duyệt (đi đường xuat)
        kw = KHO["a"]["keywords"]
        for k in ["cu", "KH000001", "0901234567", "Khách A", "Laser Pico", "chưa duyệt"]:
            self.assertIn(k, kw)
        self.assertTrue(KHO["a"]["description"].startswith("chú thích cũ\n"))
        self.assertIn("(chưa duyệt)", KHO["a"]["description"])

    def test_chay_khan_va_chay_lai_khong_ghi_trung(self):
        self.chay("2026-09")
        self.assertEqual(KHO, {})
        self.chay("2026-09", "--ghi")
        self.chay("2026-09", "--ghi")
        self.assertEqual(KHO["a"]["keywords"].count("KH000001"), 1)

    def test_sua_go_dung_phan_minh_ghi(self):
        self.chay("2026-09", "--ghi")
        c = A.ket_noi()
        c.execute("INSERT INTO visits (code,ngay,ma_kh,ten_kh) VALUES ('H2','2026-09-01','KH000002','Khách B')")
        c.execute("UPDATE photos SET xn_hd='H2' WHERE id='a'")  # người duyệt đổi sang khách khác
        c.commit()
        self.chay("--sua", "--ghi")
        self.assertEqual(KHO["a"]["keywords"], ["cu"])
        self.assertEqual(KHO["a"]["description"], "chú thích cũ")
        self.assertEqual(c.execute("SELECT count(*) FROM da_gan_chac").fetchone()[0], 0)
        c.close()

    def test_duyet_dung_khach_thi_khong_go(self):
        self.chay("2026-09", "--ghi")
        c = A.ket_noi()
        c.execute("UPDATE photos SET xn_hd='H1' WHERE id='a'")
        c.commit()
        self.chay("--sua", "--ghi")
        self.assertIn("KH000001", KHO["a"]["keywords"])
        c.close()


if __name__ == "__main__":
    unittest.main()
