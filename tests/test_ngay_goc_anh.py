"""Ảnh KHÔNG có ngày chụp gốc (dữ liệu bịa): gửi qua Zalo/Messenger, chụp màn hình... -> ngày trên ảnh có thể
là NGÀY NHẬN, trễ 1–2 ngày. Nhãn tên không khớp HĐ ngày D -> thử HĐ D-1, D-2 (không thử ngày sau), CHỈ gợi ý.

Chạy:  python3 -m unittest tests/test_ngay_goc_anh.py
"""
import os
import sys
import tempfile
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["ANH_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
import anhkhach as A  # noqa: E402

D = "2026-10-10"


class Nen(unittest.TestCase):
    def setUp(self):
        self.c = A.ket_noi()
        self.c.execute("DELETE FROM visits")
        self.c.execute("DELETE FROM photos")

    def tearDown(self):
        self.c.close()

    def hd(self, code, ngay, ma, ten, dv, gio="10:00"):
        self.c.execute("INSERT INTO visits (code,ngay,gio,ma_kh,ten_kh,dich_vu) VALUES (?,?,?,?,?,?)",
                       (code, ngay, gio, ma, ten, dv))

    def anh(self, id_, gio, ocr, ngay_goc, ngay=D):
        self.c.execute("INSERT INTO photos (id,ngay,thoi_gian,ten_file,chu_thich,ocr,ngay_goc) VALUES"
                       " (?,?,?,'IMG.JPG','',?,?)", (id_, ngay, f"{ngay}T{gio}", ocr, ngay_goc))

    def ket(self, ngay=D):
        A.ghep_ngay(self.c, ngay)
        return {r["id"]: r for r in self.c.execute("SELECT * FROM photos WHERE ngay=?", (ngay,))}

    def khop(self, chu, ngay_goc, ngay_anh=D):
        return A._khop_nhan(self.c, A.doc_nhan(chu, 2026)[0], ngay_anh, None, ngay_goc)


class CotNgayGoc(Nen):
    def test_cot_moi_va_quet_lai_giu(self):
        self.assertIn("ngay_goc", {r[1] for r in self.c.execute("PRAGMA table_info(photos)")})
        self.c.commit()
        a = types.SimpleNamespace(thang="2026-10", thu_muc=None, ocr=False, tai_goc=False, tai_het=False)
        dong = ("u1", "photos", D, f"{D}T09:00:00", "I.JPG", "", "", "", "", "")
        with mock.patch.object(A, "_quet_photos", return_value=[dong + (0,)]):
            A.cmd_quet(a)
        with mock.patch.object(A, "_quet_photos", return_value=[dong + (None,)]):  # không đọc được -> giữ
            A.cmd_quet(a)
        with mock.patch.object(A, "_quet_photos", return_value=[dong]):  # dòng 10 cột kiểu cũ
            A.cmd_quet(a)
        c = A.ket_noi()
        self.assertEqual(c.execute("SELECT ngay_goc FROM photos WHERE id='u1'").fetchone()[0], 0)
        c.close()
        with mock.patch.object(A, "_quet_photos", return_value=[dong + (1,)]):
            A.cmd_quet(a)
        c = A.ket_noi()
        self.assertEqual(c.execute("SELECT ngay_goc FROM photos WHERE id='u1'").fetchone()[0], 1)
        c.close()

    def test_ngay_goc_photos(self):
        ex = types.SimpleNamespace
        self.assertEqual(A._ngay_goc_photos(ex(exif_info=ex(camera_make="Apple", camera_model=None)), None), 1)
        self.assertEqual(A._ngay_goc_photos(ex(exif_info=ex(camera_make=None, camera_model="iPhone 15")), None), 1)
        self.assertEqual(A._ngay_goc_photos(ex(exif_info=ex(camera_make=None, camera_model=None)), None), 0)
        with mock.patch.object(A, "_ngay_exif", return_value=A.dt.datetime(2026, 10, 8, 9, 0)):
            self.assertEqual(A._ngay_goc_photos(ex(exif_info=ex(camera_make=None, camera_model=None)), "/x.jpg"), 1)
        self.assertIsNone(A._ngay_goc_photos(ex(exif_info=None), None))

    def test_thu_muc_theo_exif(self):
        from PIL import Image

        goc = tempfile.mkdtemp()
        p1 = os.path.join(goc, "co.jpg")
        im = Image.new("RGB", (4, 4))
        exif = im.getexif()
        exif.get_ifd(0x8769)[36867] = "2026:10:08 09:00:00"
        im.save(p1, exif=exif)
        Image.new("RGB", (4, 4)).save(os.path.join(goc, "khong.jpg"))
        rows = {r[4]: r for r in A._quet_thu_muc(goc, "2000-01-01", "2100-01-01")}
        self.assertEqual((rows["co.jpg"][2], rows["co.jpg"][10]), ("2026-10-08", 1))
        self.assertEqual(rows["khong.jpg"][10], 0)


class KhopNgayTruoc(Nen):
    def test_d1_goi_y_50(self):
        self.hd("HD9", "2026-10-09", "KH01", "Nguyễn Thị Quyên", "CSD MỤN")
        hd, d, ly_do = self.khop("Quyên-csd", 0)
        self.assertEqual((hd, d), ("HD9", 50))
        self.assertIn("ảnh không có ngày chụp gốc (có thể gửi qua Zalo) — HĐ ngày 09/10", ly_do)

    def test_d2_goi_y(self):
        self.hd("HD8", "2026-10-08", "KH01", "Nguyễn Thị Quyên", "CSD MỤN")
        self.assertEqual(self.khop("Quyên-csd", 0)[:2], ("HD8", 50))

    def test_cung_khach_hai_ngay_chon_ngay_gan(self):
        self.hd("HD8", "2026-10-08", "KH01", "Nguyễn Thị Quyên", "CSD MỤN")
        self.hd("HD9", "2026-10-09", "KH01", "Nguyễn Thị Quyên", "CSD MỤN")
        self.assertEqual(self.khop("Quyên-csd", 0)[:2], ("HD9", 50))

    def test_anh_co_ngay_goc_khong_dung(self):
        self.hd("HD9", "2026-10-09", "KH01", "Nguyễn Thị Quyên", "CSD MỤN")
        for ng in (1, None):
            hd, _, ly_do = self.khop("Quyên-csd", ng)
            self.assertIsNone(hd)
            self.assertNotIn("ngày chụp gốc", ly_do)

    def test_khong_thu_ngay_sau_va_d3(self):
        self.hd("HD11", "2026-10-11", "KH01", "Nguyễn Thị Quyên", "CSD MỤN")
        self.hd("HD7", "2026-10-07", "KH01", "Nguyễn Thị Quyên", "CSD MỤN")
        self.assertIsNone(self.khop("Quyên-csd", 0)[0])

    def test_hai_khach_nguoi_chon(self):
        self.hd("HD9", "2026-10-09", "KH01", "Nguyễn Thị Quyên", "CSD MỤN")
        self.hd("HD8", "2026-10-08", "KH02", "Lê Quyên", "CSD MỤN")
        hd, d, ly_do = self.khop("Quyên-csd", 0)
        self.assertEqual((hd, d), (None, 0))
        self.assertIn("người chọn", ly_do)

    def test_hai_khach_cung_ngay_nguoi_chon(self):
        self.hd("HD9", "2026-10-09", "KH01", "Nguyễn Thị Quyên", "CSD MỤN")
        self.hd("HD9B", "2026-10-09", "KH02", "Lê Quyên", "CSD MỤN")
        self.assertIsNone(self.khop("Quyên-csd", 0)[0])

    def test_lech_dich_vu_hoac_nhan_khong_dich_vu_khong_dung(self):
        self.hd("HD9", "2026-10-09", "KH01", "Nguyễn Thị Quyên", "TRIỆT LÔNG")
        self.assertIsNone(self.khop("Quyên-csd", 0)[0])
        self.assertIsNone(self.khop("Quyên 10/10/26", 0)[0])  # nhãn không ghi dịch vụ

    def test_nhan_ghi_ngay_ro_uu_tien(self):
        self.hd("HD9", "2026-10-09", "KH01", "Nguyễn Thị Quyên", "CSD MỤN")
        hd, d, _ = self.khop("Quyên-csd 9/10/26", 0)
        self.assertEqual((hd, d), ("HD9", 85))  # khớp HĐ ngày trên nhãn như cũ, không qua luật mới

    def test_nhan_ghi_ngay_d_khong_hd_thu_d1(self):
        self.hd("HD9", "2026-10-09", "KH01", "Nguyễn Thị Quyên", "CSD MỤN")
        self.assertEqual(self.khop("Quyên-csd 10/10/26", 0)[:2], ("HD9", 50))

    def test_khach_ngay_d_khop_khong_dung_luat(self):
        self.hd("HD10", D, "KH03", "Trần Quyên", "CSD MỤN")
        self.hd("HD9", "2026-10-09", "KH01", "Nguyễn Thị Quyên", "CSD MỤN")
        self.assertEqual(self.khop("Quyên-csd", 0)[0], "HD10")


class GhepNgay(Nen):
    def test_ghep_goi_y_khong_chac_va_bo_chup_goi_y(self):
        self.hd("HD10", D, "KH05", "Phạm Văn Bình", "PICO", gio="15:00")
        self.hd("HD9", "2026-10-09", "KH01", "Nguyễn Thị Quyên", "CSD MỤN")
        self.anh("a", "10:00:00", "Quyên-csd", 0)
        self.anh("b", "10:00:20", "", 0)
        self.anh("c", "10:00:40", "", 0)
        k = self.ket()
        self.assertEqual((k["a"]["goi_y_hd"], k["a"]["do_tin"]), ("HD9", "goi_y"))
        for i in "bc":
            self.assertEqual((k[i]["goi_y_hd"], k[i]["do_tin"]), ("HD9", "goi_y"))
        self.assertFalse(any(r["do_tin"] == "chac" for r in k.values()))

    def test_anh_khong_ngay_goc_sat_anh_exif_coi_nhu_ngay_dung(self):
        # Đo 14/10: đa số ảnh không EXIF nằm sát (< 10s) ảnh có EXIF = chụp cùng buổi -> ngày đúng, không lùi ngày.
        self.hd("HD10", D, "KH05", "Phạm Văn Bình", "PICO", gio="15:00")
        self.hd("HD9", "2026-10-09", "KH01", "Nguyễn Thị Quyên", "CSD MỤN")
        self.anh("a", "10:00:00", "Quyên-csd", 0)
        self.anh("b", "10:00:05", "", 1)
        k = self.ket()
        self.assertNotEqual(k["a"]["goi_y_hd"], "HD9")
        self.assertNotIn("ngày chụp gốc", k["a"]["ly_do"])
        self.c.execute("DELETE FROM photos")
        self.anh("a", "10:00:00", "Quyên-csd", 0)
        self.anh("b", "10:01:05", "", 1)  # cách 65s: ảnh a đứng riêng
        self.assertEqual(self.ket()["a"]["goi_y_hd"], "HD9")

    def test_ngay_khong_tin(self):
        rows = [{"id": "a", "thoi_gian": f"{D}T10:00:00", "ngay_goc": 0},
                {"id": "b", "thoi_gian": f"{D}T10:00:59", "ngay_goc": 1},
                {"id": "c", "thoi_gian": f"{D}T11:00:00", "ngay_goc": 0},
                {"id": "d", "thoi_gian": f"{D}T11:00:30", "ngay_goc": None},  # chưa quét lại: không làm bằng chứng
                {"id": "e", "thoi_gian": f"{D}T12:00:00", "ngay_goc": None}]
        self.assertEqual(A._ngay_khong_tin(rows), {"c"})

    def test_bo_chup_hd_lui_khong_lan_anh_exif(self):
        t = A.dt.datetime.fromisoformat
        ds = [{"gio": t(f"{D}T10:00:{s:02d}"), "trung_giay": False, "nhan": i == 0, "hd": "HD9" if i == 0 else None,
               "diem": 50 if i == 0 else 0, "do_tin": "goi_y" if i == 0 else "chua_ro", "xn": None, "ly_do": "",
               "ngay_goc": g} for i, (s, g) in enumerate([(0, 0), (20, 1), (40, 0)])]
        A._bo_chup(ds, {"HD9"})
        self.assertEqual([r["hd"] for r in ds], ["HD9", None, "HD9"])
        for r in ds[1:]:
            r.update(hd=None, do_tin="chua_ro")
        A._bo_chup(ds)  # không có hd_lui: như cũ
        self.assertEqual([r["hd"] for r in ds], ["HD9", "HD9", "HD9"])

    def test_ngay_khong_hd_anh_exif_van_khong_hd(self):
        self.hd("HD9", "2026-10-09", "KH01", "Nguyễn Thị Quyên", "CSD MỤN")
        self.anh("a", "10:00:00", "Quyên-csd", 0)
        self.anh("b", "10:05:00", "", 1)
        self.anh("c", "10:00:30", "", 0)
        k = self.ket()
        self.assertEqual((k["a"]["goi_y_hd"], k["a"]["do_tin"]), ("HD9", "goi_y"))
        self.assertEqual(k["b"]["do_tin"], "khong_hd")
        self.assertNotEqual(k["c"]["do_tin"], "khong_hd")

    def test_anh_co_exif_khong_bi_dung(self):
        self.hd("HD10", D, "KH05", "Phạm Văn Bình", "PICO", gio="15:00")
        self.hd("HD9", "2026-10-09", "KH01", "Nguyễn Thị Quyên", "CSD MỤN")
        self.anh("a", "10:00:00", "Quyên-csd", 1)
        self.anh("n", "10:00:20", "Quyên-csd", None)
        k = self.ket()
        self.assertTrue(all(r["goi_y_hd"] != "HD9" for r in k.values()))

    def test_khong_dung_luat_gan_gio_chup(self):
        self.hd("HD10", D, "KH05", "Phạm Văn Bình", "PICO", gio="10:05")
        self.hd("HD10B", D, "KH06", "Lê Văn Hải", "PICO", gio="16:00")
        self.anh("z", "10:00:00", "", 0)
        self.assertIsNone(self.ket()["z"]["goi_y_hd"])
        self.c.execute("DELETE FROM photos")
        self.anh("e", "10:00:00", "", 1)  # đối chứng: ảnh có EXIF vẫn dùng luật giờ
        self.assertEqual(self.ket()["e"]["goi_y_hd"], "HD10")
        self.c.execute("DELETE FROM photos")
        self.anh("f", "10:00:00", "", 1)
        self.anh("g", "10:10:00", "", 0)  # cùng đợt: ảnh EXIF vẫn nhận, ảnh không ngày gốc thì không
        k = self.ket()
        self.assertEqual((k["f"]["goi_y_hd"], k["g"]["goi_y_hd"]), ("HD10", None))


class TrangDuyet(Nen):
    def test_chu_thich_va_hd_hai_ngay_truoc(self):
        self.hd("HD10", D, "KH05", "Phạm Văn Bình", "PICO")
        self.hd("HD9", "2026-10-09", "KH01", "Nguyễn Thị Quyên", "CSD MỤN")
        self.hd("HD8", "2026-10-08", "KH02", "Lê Văn Hải", "PICO")
        self.hd("HD7", "2026-10-07", "KH03", "Trần Văn Tú", "PICO")
        self.hd("HD11", "2026-10-11", "KH04", "Võ Văn Lộc", "PICO")
        self.anh("a", "10:00:00", "", 1)
        t = A._trang_ngay(self.c, D).decode()
        self.assertNotIn("không có ngày chụp gốc", t)
        self.assertNotIn("HD9", t)
        self.anh("b", "10:30:00", "", 0)
        t = A._trang_ngay(self.c, D).decode()
        self.assertEqual(t.count("⚠ không có ngày chụp gốc"), 1)
        for c in ("HD9", "HD8"):
            self.assertIn(f"value='{c}'", t)
        for c in ("HD7", "HD11"):
            self.assertNotIn(c, t)


if __name__ == "__main__":
    unittest.main()
