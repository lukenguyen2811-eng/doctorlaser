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


GIA = types.SimpleNamespace(Photo=AnhGia, GIA=True)


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

    def test_ghi_anh_chac_chua_duyet_va_anh_da_duyet(self):
        self.chay("2026-09", "--ghi")
        self.assertEqual(sorted(KHO), ["a", "d"])  # b gợi ý chưa duyệt -> chờ; c bị loại
        kw = KHO["a"]["keywords"]
        for k in ["cu", "KH000001", "0901234567", "Khách A", "Laser Pico", "chưa duyệt"]:
            self.assertIn(k, kw)
        self.assertTrue(KHO["a"]["description"].startswith("chú thích cũ\n"))
        self.assertIn("(chưa duyệt)", KHO["a"]["description"])
        self.assertIn("KH000001", KHO["d"]["keywords"])          # đã duyệt
        self.assertNotIn("chưa duyệt", KHO["d"]["keywords"])
        self.assertNotIn("chưa duyệt", KHO["d"]["description"])

    def test_duyet_xong_thi_bo_chu_chua_duyet(self):
        self.chay("2026-09", "--ghi")
        c = A.ket_noi()
        c.execute("UPDATE photos SET xn_hd='H1', loai_anh='sau' WHERE id='a'")
        c.commit()
        self.chay("2026-09", "--ghi")
        kw = KHO["a"]["keywords"]
        self.assertNotIn("chưa duyệt", kw)
        self.assertIn("sau", kw)
        self.assertEqual(kw.count("KH000001"), 1)
        self.assertNotIn("(chưa duyệt)", KHO["a"]["description"])
        self.assertEqual(KHO["a"]["description"].count("KH000001"), 1)
        c.close()

    def test_gợi_ý_duyet_xong_thi_ghi(self):
        c = A.ket_noi()
        c.execute("UPDATE photos SET xn_hd='H1' WHERE id='b'")
        c.commit()
        self.chay("2026-09", "--ghi")
        self.assertIn("KH000001", KHO["b"]["keywords"])
        c.close()

    def test_chay_khan_va_chay_lai_khong_ghi_trung(self):
        self.chay("2026-09")
        self.assertEqual(KHO, {})
        self.chay("2026-09", "--ghi")
        self.chay("2026-09", "--ghi")
        self.assertEqual(KHO["a"]["keywords"].count("KH000001"), 1)

    def test_nguoi_duyet_doi_khach_thi_ghi_lai_dung_khach(self):
        self.chay("2026-09", "--ghi")
        c = A.ket_noi()
        c.execute("INSERT INTO visits (code,ngay,ma_kh,ten_kh) VALUES ('H2','2026-09-01','KH000002','Khách B')")
        c.execute("UPDATE photos SET xn_hd='H2' WHERE id='a'")  # người duyệt đổi sang khách khác
        c.commit()
        self.chay("2026-09", "--ghi")
        kw = KHO["a"]["keywords"]
        self.assertIn("cu", kw)
        self.assertIn("KH000002", kw)
        self.assertNotIn("KH000001", kw)
        self.assertNotIn("0901234567", kw)
        self.assertNotIn("KH000001", KHO["a"]["description"])
        self.assertTrue(KHO["a"]["description"].startswith("chú thích cũ"))
        c.close()

    def test_loai_anh_thi_go(self):
        self.chay("2026-09", "--ghi")
        c = A.ket_noi()
        c.execute("UPDATE photos SET bo_qua=1 WHERE id='a'")
        c.commit()
        self.chay("--sua", "--ghi")
        self.assertEqual(KHO["a"]["keywords"], ["cu"])
        self.assertEqual(KHO["a"]["description"], "chú thích cũ")
        c.close()

    def test_duyet_dung_khach_thi_khong_go(self):
        self.chay("2026-09", "--ghi")
        c = A.ket_noi()
        c.execute("UPDATE photos SET xn_hd='H1' WHERE id='a'")
        c.commit()
        self.chay("--sua", "--ghi")
        self.assertIn("KH000001", KHO["a"]["keywords"])
        c.close()

    def test_may_ghep_lai_khong_con_chac_thi_go(self):
        self.chay("2026-09", "--ghi")
        c = A.ket_noi()
        c.execute("UPDATE photos SET do_tin='chua_ro', goi_y_hd=NULL WHERE id='a'")
        c.commit()
        self.chay("--sua", "--ghi")
        self.assertEqual(KHO["a"]["keywords"], ["cu"])
        c.close()

    def test_lenh_osascript_dung_tham_so(self):
        with mock.patch("subprocess.run") as run:
            run.return_value = types.SimpleNamespace(returncode=0, stderr="")
            G.ghi_mot(types.SimpleNamespace(), {"id": "U1", "chu_thich": "KH1 · A", "tu_khoa": ["KH1", "chưa duyệt"]})
        cmd, kw = run.call_args
        self.assertEqual(cmd[0][3:], ["U1/L0/001", "KH1 · A", "KH1", "chưa duyệt"])
        self.assertEqual(kw["timeout"], G.HAN_GIAY)

    def test_loi_lien_tiep_thi_dung_luot(self):
        c = A.ket_noi()
        for i in range(8):
            c.execute("INSERT INTO photos (id,nguon,ngay,thoi_gian,ten_file,goi_y_hd,do_tin,bo_qua)"
                      " VALUES (?,'photos','2026-09-02','2026-09-02T10:00:00','I.HEIC','H1','chac',0)", (f"z{i}",))
        c.commit()
        goi = []
        with mock.patch.object(G, "ghi_mot", side_effect=lambda ps, g: goi.append(g) or (_ for _ in ()).throw(RuntimeError("treo"))):
            self.chay("2026-09", "--ghi")
        self.assertEqual(len(goi), G.LOI_LIEN)
        c.close()


if __name__ == "__main__":
    unittest.main()
