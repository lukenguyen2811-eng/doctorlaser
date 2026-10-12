"""Gợi ý theo khuôn mặt (mã người app Ảnh) trong ghep_ngay — DB tạm, ảnh giả có khuon_mat.

Chạy:  python3 -m unittest tests/test_khuon_mat_anh.py
"""
import os
import sqlite3
import sys
import tempfile
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ANH_DB", os.path.join(tempfile.mkdtemp(), "t.db"))
import anhkhach as A  # noqa: E402


class KhuonMat(unittest.TestCase):
    def setUp(self):
        self.tam = tempfile.mkdtemp()
        self.p = mock.patch.object(A, "DB_FILE", os.path.join(self.tam, "k.db"))
        self.p.start()
        self.c = A.ket_noi()
        for code, ngay, gio, ma, ten in [
            ("H1", "2026-09-05", "10:00", "KH1", "Khach Mot"),     # lần trước của KH1 (ảnh đã duyệt)
            ("H2", "2026-10-03", "09:00", "KH1", "Khach Mot"),     # hôm nay KH1
            ("H3", "2026-10-03", "09:10", "KH2", "Khach Hai"),     # hôm nay KH2 (cùng giờ -> luật giờ không tách)
            ("H4", "2026-09-06", "11:00", "KH2", "Khach Hai"),
            ("H5", "2026-10-02", "16:00", "KH3", "Khach Ba"),      # KH3 có HĐ hôm qua (ngày nhãn)
            ("H6", "2026-09-07", "08:00", "KH3", "Khach Ba"),
            ("H7", "2026-09-07", "08:30", "CU-KH1", "Nguoi Cu"),   # mã cũ = khách khác
        ]:
            self.c.execute("INSERT INTO visits VALUES (?,?,?,?,?,?,?,?)", (code, ngay, gio, ma, ten, "", "Laser", ""))

    def tearDown(self):
        self.c.close()
        self.p.stop()

    def anh(self, pid, ngay, gio, km, xn=None, do_tin=None, goi_y=None, ocr="", bo_qua=0):
        self.c.execute("INSERT INTO photos (id,nguon,ngay,thoi_gian,ten_file,chu_thich,ocr,khuon_mat,xn_hd,"
                       "do_tin,goi_y_hd,bo_qua) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                       (pid, "photos", ngay, f"{ngay}T{gio}:00", "IMG.HEIC", "", ocr, km, xn, do_tin, goi_y, bo_qua))

    def ghep(self, ngay="2026-10-03"):
        A.ghep_ngay(self.c, ngay)
        return {r[0]: (r[1], r[2], r[3]) for r in
                self.c.execute("SELECT id, goi_y_hd, do_tin, ly_do FROM photos WHERE ngay=?", (ngay,))}

    def test_khuon_mat_da_duyet_goi_y(self):
        self.anh("cu", "2026-09-05", "10:05", "P-A", xn="H1")
        self.anh("moi", "2026-10-03", "09:20", "P-A")
        hd, do_tin, ly_do = self.ghep()["moi"]
        self.assertEqual((hd, do_tin), ("H2", "goi_y"))  # không bao giờ 'chac'
        self.assertIn("cùng khuôn mặt", ly_do)

    def test_anh_chac_lam_nguon(self):
        self.anh("cu", "2026-09-05", "10:05", "P-A", do_tin="chac", goi_y="H1")
        self.anh("moi", "2026-10-03", "09:20", "P-A")
        self.assertEqual(self.ghep()["moi"][:2], ("H2", "goi_y"))

    def test_chi_goi_y_khong_lam_nguon(self):  # âm: ảnh 'goi_y' chưa duyệt không đủ làm mốc
        self.anh("cu", "2026-09-05", "10:05", "P-A", do_tin="goi_y", goi_y="H1")
        self.anh("moi", "2026-10-03", "09:20", "P-A")
        self.assertEqual(self.ghep()["moi"][:2], (None, "chua_ro"))

    def test_bo_qua_khong_lam_nguon(self):  # âm
        self.anh("cu", "2026-09-05", "10:05", "P-A", xn="H1", bo_qua=1)
        self.anh("moi", "2026-10-03", "09:20", "P-A")
        self.assertEqual(self.ghep()["moi"][:2], (None, "chua_ro"))

    def test_khach_khong_co_hd_hom_nay(self):  # âm: KH3 không có HĐ ngày 03/10
        self.anh("cu", "2026-09-07", "08:05", "P-C", xn="H6")
        self.anh("moi", "2026-10-03", "09:20", "P-C")
        self.assertEqual(self.ghep()["moi"][:2], (None, "chua_ro"))

    def test_ngay_nhan_cho_hd_ngay_khac(self):  # nhãn ghi 2/10 (không khớp tên) -> HĐ KH3 ngày 2/10
        self.anh("cu", "2026-09-07", "08:05", "P-C", xn="H6")
        self.anh("moi", "2026-10-03", "09:20", "P-C", ocr="Zzz-co2 2/10/26")
        self.assertEqual(self.ghep()["moi"][:2], ("H5", "goi_y"))

    def test_hai_khach_cung_thoa_nguoi_chon(self):  # âm: 2 người trên ảnh, cả 2 khách có HĐ hôm nay
        self.anh("c1", "2026-09-05", "10:05", "P-A", xn="H1")
        self.anh("c2", "2026-09-06", "11:05", "P-B", xn="H4")
        self.anh("moi", "2026-10-03", "09:20", "P-A P-B")
        self.assertEqual(self.ghep()["moi"][:2], (None, "chua_ro"))

    def test_ma_nguoi_gan_nhieu_khach_bo(self):  # âm: bác sĩ có mặt trong ảnh của KH1 và KH2
        self.anh("c1", "2026-09-05", "10:05", "P-BS P-A", xn="H1")
        self.anh("c2", "2026-09-06", "11:05", "P-BS", xn="H4")
        self.anh("moi", "2026-10-03", "09:20", "P-BS")
        self.assertEqual(self.ghep()["moi"][:2], (None, "chua_ro"))

    def test_ma_cu_khac_khach(self):  # âm: mặt gắn cả KH1 và CU-KH1 -> coi là 2 khách -> bỏ
        self.anh("c1", "2026-09-05", "10:05", "P-A", xn="H1")
        self.anh("c2", "2026-09-07", "08:35", "P-A", xn="H7")
        self.anh("moi", "2026-10-03", "09:20", "P-A")
        self.assertEqual(self.ghep()["moi"][:2], (None, "chua_ro"))

    def test_khong_de_luat_manh_hon(self):  # nhãn khớp tên vẫn thắng
        self.anh("c1", "2026-09-05", "10:05", "P-A", xn="H1")
        self.anh("moi", "2026-10-03", "09:20", "P-A", ocr="Hai-laser 3/10/26")
        self.assertEqual(self.ghep()["moi"][:2], ("H3", "chac"))

    def test_anh_chac_cung_ngay_lam_nguon(self):  # ảnh nhãn hôm nay 'chac' -> ảnh khác đợt cùng mặt
        self.anh("n", "2026-10-03", "08:00", "P-A", ocr="Mot-laser 3/10/26")
        self.anh("moi", "2026-10-03", "14:00", "P-A")
        r = self.ghep()
        self.assertEqual(r["n"][:2], ("H2", "chac"))
        self.assertEqual(r["moi"][:2], ("H2", "goi_y"))

    def test_cot_moi_tren_db_cu(self):  # DB cũ chưa có cột -> thêm, giữ dữ liệu
        f = os.path.join(self.tam, "cu.db")
        c = sqlite3.connect(f)
        c.execute("CREATE TABLE photos (id TEXT PRIMARY KEY, nguon TEXT, ngay TEXT, thoi_gian TEXT, ten_file TEXT,"
                  " duong_dan TEXT, anh_xem TEXT, chu_thich TEXT, ocr TEXT, dot INTEGER, goi_y_hd TEXT, do_tin TEXT,"
                  " ly_do TEXT, xn_hd TEXT, loai_anh TEXT, vung TEXT, ghi_chu TEXT, bo_qua INTEGER DEFAULT 0,"
                  " xn_luc TEXT, da_xuat TEXT)")
        c.execute("INSERT INTO photos (id, xn_hd) VALUES ('x', 'H9')")
        c.commit()
        c.close()
        with mock.patch.object(A, "DB_FILE", f):
            c = A.ket_noi()
            c2 = A.ket_noi()  # mở lần 2 không lỗi
        self.assertEqual(tuple(c.execute("SELECT xn_hd, khuon_mat FROM photos").fetchone()), ("H9", None))
        c.close()
        c2.close()

    def test_ma_nguoi_tu_osxphotos(self):  # chỉ lấy uuid, bỏ trùng; lỗi -> rỗng
        p = types.SimpleNamespace(person_info=[types.SimpleNamespace(uuid="B", name="_UNKNOWN_"),
                                               types.SimpleNamespace(uuid="A", name="X"),
                                               types.SimpleNamespace(uuid="B", name="")])
        self.assertEqual(A._ma_nguoi(p), "A B")
        self.assertEqual(A._ma_nguoi(types.SimpleNamespace()), "")

    def test_quet_giu_khuon_mat_cu_khi_rong(self):
        self.c.commit()
        rows = [("u1", "photos", "2026-10-03", "2026-10-03T09:00:00", "I.HEIC", "", "", "", "", "P-A")]
        a = types.SimpleNamespace(thang="2026-10", thu_muc=None, ocr=False, tai_goc=False, tai_het=False)
        with mock.patch.object(A, "_quet_photos", return_value=rows):
            A.cmd_quet(a)
        rows[0] = rows[0][:9] + ("",)
        with mock.patch.object(A, "_quet_photos", return_value=rows):
            A.cmd_quet(a)
        c = A.ket_noi()
        self.assertEqual(c.execute("SELECT khuon_mat FROM photos WHERE id='u1'").fetchone()[0], "P-A")
        c.close()


if __name__ == "__main__":
    unittest.main()
