"""Luật CỤM MẶT -> KHÁCH (cum_khach + bước nhận lại / lan bộ / cảnh báo trong ghep_ngay) — DB tạm, dữ liệu bịa.

Chạy:  python3 -m unittest tests/test_cum_mat_anh.py
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ANH_DB", os.path.join(tempfile.mkdtemp(), "t.db"))
import anhkhach as A  # noqa: E402

D = "2026-10-03"
NHAN = "nhãn 'Mot-laser' khớp KHACH MOT"


class CumMat(unittest.TestCase):
    def setUp(self):
        self.tam = tempfile.mkdtemp()
        self.p = mock.patch.object(A, "DB_FILE", os.path.join(self.tam, "c.db"))
        self.p.start()
        self.c = A.ket_noi()
        self.so = 0
        for code, ngay, gio, ma, ten, sdt in [
            ("A1", "2026-09-01", "10:00", "KH1", "Khach Mot", "0901000001"),
            ("A2", "2026-09-10", "10:00", "KH1", "Khach Mot", "0901000001"),
            ("A3", "2026-09-20", "10:00", "KH1", "Khach Mot", "0901000001"),
            ("A4", D, "15:00", "KH1", "Khach Mot", "0901000001"),
            ("B1", "2026-09-01", "11:00", "KH2", "Khach Hai", "0902000002"),
            ("B2", "2026-09-10", "11:00", "KH2", "Khach Hai", "0902000002"),
            ("B3", D, "15:05", "KH2", "Khach Hai", "0902000002"),
            ("C1", "2026-09-01", "12:00", "KH3", "Khach Ba", "0903000003"),
            ("C2", "2026-09-10", "12:00", "KH3", "Khach Ba", "0903000003"),
            ("C3", "2026-09-05", "12:00", "KH3", "Khach Ba", "0903000003"),
            ("E1", "2026-09-02", "09:00", "CU-KH7", "Khach Bay", "0907000007"),  # mã cũ
            ("E2", "2026-09-12", "09:00", "KH7", "Khach Bay", "0907000007"),     # mã mới, cùng SĐT
            ("F1", "2026-09-02", "09:30", "CU-KH8", "Khach Tam", "0908000008"),
            ("F2", "2026-09-12", "09:30", "KH8", "Khach Tam", "0908111118"),     # khác SĐT
            ("G1", "2026-09-03", "09:00", "KH5", "Nguoi Nha A", "0905000005"),
            ("G2", "2026-09-13", "09:00", "KH6", "Nguoi Nha B", "0905000005"),   # cùng hệ, cùng SĐT
            ("X1", D, "18:00", "KH9", "Khach Chin", "0909000009"),               # khách khác hôm nay
        ]:
            self.c.execute("INSERT INTO visits VALUES (?,?,?,?,?,?,?,?)", (code, ngay, gio, ma, ten, sdt, "Laser", ""))

    def tearDown(self):
        self.c.close()
        self.p.stop()

    def anh(self, ngay, gio, km, xn=None, do_tin=None, goi_y=None, ly_do=None, ocr="", pid=None):
        self.so += 1
        pid = pid or f"p{self.so}"
        self.c.execute("INSERT INTO photos (id,nguon,ngay,thoi_gian,ten_file,chu_thich,ocr,khuon_mat,xn_hd,"
                       "do_tin,goi_y_hd,ly_do,bo_qua) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,0)",
                       (pid, "photos", ngay, f"{ngay}T{gio}", "IMG.HEIC", "", ocr, km, xn, do_tin, goi_y, ly_do))
        return pid

    def neo(self, km, hd, ngay, n=1, ly_do=NHAN):
        for i in range(n):
            self.anh(ngay, f"10:{i:02d}:00", km, do_tin="chac", goi_y=hd, ly_do=ly_do)

    def ghep(self, ngay=D):
        A.ghep_ngay(self.c, ngay)
        return {r[0]: (r[1], r[2], r[3]) for r in
                self.c.execute("SELECT id, goi_y_hd, do_tin, ly_do FROM photos WHERE ngay=?", (ngay,))}

    def cum_kh1(self, n=3):  # cụm P-A thuộc KH1: n ảnh neo nhãn ở 2 ngày
        self.neo("P-A", "A1", "2026-09-01", (n + 1) // 2)
        self.neo("P-A", "A2", "2026-09-10", n // 2)

    # ---------- 1. gắn cụm ----------
    def test_gan_cum_du_neo_hai_ngay(self):
        self.cum_kh1()
        c = A.cum_khach(self.c)
        self.assertEqual(c["cum"]["P-A"]["khach"], "KH1")
        self.assertEqual(c["cum"]["P-A"]["neo"], 3)

    def test_mot_ngay_khong_gan(self):
        self.neo("P-A", "A1", "2026-09-01", 4)
        self.assertNotIn("P-A", A.cum_khach(self.c)["cum"])

    def test_hai_neo_khong_duyet_khong_gan(self):
        self.neo("P-A", "A1", "2026-09-01")
        self.neo("P-A", "A2", "2026-09-10")
        self.assertNotIn("P-A", A.cum_khach(self.c)["cum"])

    def test_mot_duyet_mot_neo_du(self):
        self.anh("2026-09-01", "10:00:00", "P-A", xn="A1")
        self.neo("P-A", "A2", "2026-09-10")
        self.assertEqual(A.cum_khach(self.c)["cum"]["P-A"]["khach"], "KH1")

    def test_cum_lan_khong_dung(self):  # nhân viên lọt ảnh của 2 khách
        self.cum_kh1()
        self.neo("P-A", "B1", "2026-09-01", 2)
        c = A.cum_khach(self.c)
        self.assertNotIn("P-A", c["cum"])
        self.assertIn("P-A", c["lan"])

    def test_khach_thu_hai_mot_anh_it_khong_lan(self):
        self.cum_kh1(12)
        self.neo("P-A", "B1", "2026-09-01", 1)  # 1/13 phiếu < 10%, 1 ảnh
        self.assertEqual(A.cum_khach(self.c)["cum"]["P-A"]["khach"], "KH1")

    def test_chac_do_lan_bo_khong_bo_phieu(self):
        self.neo("P-A", "A1", "2026-09-01", 2, ly_do="cùng bộ chụp liền 12 ảnh với ảnh đã khớp chắc")
        self.neo("P-A", "A2", "2026-09-10", 2, ly_do="cùng bộ chụp liền 9 ảnh với ảnh có nhãn 'Mot-laser'")
        self.neo("P-A", "A3", "2026-09-20", 2, ly_do="cùng đợt chụp với ảnh đã khớp tên")
        self.assertNotIn("P-A", A.cum_khach(self.c)["cum"])

    def test_chac_do_luat_mat_khong_bo_phieu(self):
        self.neo("P-A", "A1", "2026-09-01", 2, ly_do="khuôn mặt thuộc khách KH1 (cụm 3 ảnh đã xác nhận) + HĐ cùng ngày")
        self.neo("P-A", "A2", "2026-09-10", 2, ly_do="cùng bộ chụp liền 3 ảnh với ảnh nhận theo khuôn mặt khách KH1")
        self.assertNotIn("P-A", A.cum_khach(self.c)["cum"])

    def test_bo_ngan_co_nhan_bo_phieu(self):
        self.neo("P-A", "A1", "2026-09-01", 2, ly_do="cùng bộ chụp liền 5 ảnh với ảnh có nhãn 'Mot-laser'")
        self.neo("P-A", "A2", "2026-09-10", 1, ly_do="cùng bộ chụp 4 tư thế với ảnh có nhãn 'Mot' (bộ liền 9 tư thế tách)")
        self.assertEqual(A.cum_khach(self.c)["cum"]["P-A"]["khach"], "KH1")

    def test_anh_nhieu_mat_khong_bo_phieu(self):
        for ngay, hd in (("2026-09-01", "A1"), ("2026-09-10", "A2")):
            for i in range(3):
                self.anh(ngay, f"10:0{i}:00", "P-A P-X P-Y", do_tin="chac", goi_y=hd, ly_do=NHAN)
        self.assertNotIn("P-A", A.cum_khach(self.c)["cum"])

    def test_anh_hai_mat_bo_phieu_ca_hai(self):
        self.cum_kh1()
        self.anh("2026-09-20", "10:00:00", "P-A P-B", do_tin="chac", goi_y="A3", ly_do=NHAN)
        c = A.cum_khach(self.c)
        self.assertEqual(c["cum"]["P-A"]["neo"], 4)
        self.assertNotIn("P-B", c["cum"])  # P-B chỉ 1 ảnh

    def test_khuon_mat_json(self):
        self.assertEqual(A._doc_mat('["P-B", "P-A"]'), ["P-A", "P-B"])
        self.assertEqual(A._doc_mat("P-B P-A"), ["P-A", "P-B"])
        self.assertEqual(A._doc_mat(None), [])

    # ---------- mã CU-KH / KH ----------
    def test_cu_kh_va_kh_cung_sdt_la_mot(self):
        self.neo("P-Q", "E1", "2026-09-02", 2)
        self.neo("P-Q", "E2", "2026-09-12", 2)
        c = A.cum_khach(self.c)
        self.assertIn("P-Q", c["cum"])
        self.assertEqual(c["khoa"]["CU-KH7"], c["khoa"]["KH7"])

    def test_cu_kh_va_kh_khac_sdt_la_hai(self):
        self.neo("P-Q", "F1", "2026-09-02", 2)
        self.neo("P-Q", "F2", "2026-09-12", 2)
        c = A.cum_khach(self.c)
        self.assertNotIn("P-Q", c["cum"])
        self.assertIn("P-Q", c["lan"])
        self.assertNotEqual(c["khoa"]["CU-KH8"], c["khoa"]["KH8"])

    def test_cung_he_cung_sdt_nguoi_nha_la_hai(self):
        self.neo("P-Q", "G1", "2026-09-03", 2)
        self.neo("P-Q", "G2", "2026-09-13", 2)
        self.assertIn("P-Q", A.cum_khach(self.c)["lan"])

    # ---------- 2. nhận lại ----------
    def test_nhan_chac_khi_co_hd_cung_ngay_va_lan_bo(self):
        self.cum_kh1()
        a = self.anh(D, "09:00:00", "P-A")
        b = self.anh(D, "09:00:20", "")  # tấm nghiêng cùng bộ, app Ảnh không thấy mặt
        k = self.ghep()
        self.assertEqual(k[a][:2], ("A4", "chac"))
        self.assertIn("khuôn mặt thuộc khách KH1 (cụm 3 ảnh đã xác nhận) + HĐ cùng ngày", k[a][2])
        self.assertEqual(k[b][:2], ("A4", "chac"))
        self.assertIn("theo khuôn mặt khách KH1", k[b][2])

    def test_nhieu_hd_chon_gio_gan(self):
        self.cum_kh1()
        self.c.execute("INSERT INTO visits VALUES ('A5',?,'09:05','KH1','Khach Mot','0901000001','Laser','')", (D,))
        a = self.anh(D, "09:00:00", "P-A")
        self.assertEqual(self.ghep()[a][:2], ("A5", "chac"))

    def test_nhieu_hd_hd_kem_xep_sau(self):  # CEO 16/10 lần 3: HĐ chỉ bán kem gần giờ hơn vẫn xếp sau HĐ dịch vụ
        self.cum_kh1()
        self.c.execute("INSERT INTO visits VALUES ('A5',?,'09:05','KH1','Khach Mot','0901000001','Kem','')", (D,))
        a = self.anh(D, "09:00:00", "P-A")
        self.assertNotEqual(self.ghep()[a][0], "A5")

    def test_anh_nhieu_mat_khong_duoc_nhan(self):
        self.cum_kh1()
        a = self.anh(D, "09:00:00", "P-A P-X P-Y")
        self.assertNotEqual(self.ghep()[a][1], "chac")

    def test_cum_lan_khong_nhan(self):
        self.cum_kh1()
        self.neo("P-A", "B1", "2026-09-01", 2)
        a = self.anh(D, "09:00:00", "P-A")
        k = self.ghep()[a]
        self.assertNotEqual(k[1], "chac")
        self.assertNotIn("khuôn mặt thuộc", k[2] or "")

    def test_nhan_ten_khac_khong_nang(self):
        self.cum_kh1()
        a = self.anh(D, "09:00:00", "P-A", ocr="Tuan-laser 3/10/26")
        k = self.ghep()[a]
        self.assertNotEqual(k[1], "chac")
        self.assertIn("nhãn ghi tên khác", k[2])

    def test_khong_hd_ngay_do_co_hd_goi_cu_goi_y(self):
        self.neo("P-C", "C1", "2026-09-01", 2)
        self.neo("P-C", "C2", "2026-09-10", 2)
        a = self.anh(D, "09:00:00", "P-C")  # KH3 không có HĐ ngày D
        k = self.ghep()[a]
        self.assertEqual(k[:2], ("C2", "goi_y"))
        self.assertIn("không HĐ ngày này", k[2])

    def test_khong_hd_nao_giu_nguyen_ghi_chu(self):
        self.neo("P-C", "C1", "2026-09-01", 2)
        self.neo("P-C", "C2", "2026-09-10", 2)
        self.c.execute("UPDATE visits SET ngay='2025-01-01' WHERE ma_kh='KH3'")  # HĐ quá 180 ngày
        a = self.anh(D, "09:00:00", "P-C")
        k = self.ghep()[a]
        self.assertNotEqual(k[1], "chac")
        self.assertIsNone(k[0])
        self.assertIn("mặt giống khách KH3", k[2])

    def test_khong_ngay_goc_thu_hd_hai_ngay_truoc(self):
        self.neo("P-C", "C1", "2026-09-01", 2)
        self.neo("P-C", "C2", "2026-09-10", 2)
        a = self.anh("2026-09-07", "09:00:00", "P-C")
        self.c.execute("UPDATE photos SET ngay_goc=0 WHERE id=?", (a,))
        k = self.ghep("2026-09-07")[a]
        self.assertEqual(k[:2], ("C3", "chac"))  # HĐ 05/09 = D-2
        self.assertIn("HĐ ngày 05/09", k[2])

    def test_khong_dung_anh_da_duyet(self):
        self.cum_kh1()
        a = self.anh(D, "09:00:00", "P-A", xn="B3")
        self.ghep()
        self.assertEqual(self.c.execute("SELECT xn_hd FROM photos WHERE id=?", (a,)).fetchone()[0], "B3")

    # ---------- 3. cảnh báo ----------
    def test_canh_bao_ha_chac_lech_mat(self):
        self.cum_kh1(6)
        a = self.anh(D, "09:00:00", "P-A", ocr="Hai-laser 3/10/26")  # nhãn khớp KH2 -> chắc
        k = self.ghep()[a]
        self.assertEqual(k[:2], ("B3", "goi_y"))
        self.assertIn("cảnh báo: khuôn mặt thuộc khách khác (KH1, cụm 6 ảnh)", k[2])

    def test_cum_yeu_khong_canh_bao(self):
        self.cum_kh1(4)
        a = self.anh(D, "09:00:00", "P-A", ocr="Hai-laser 3/10/26")
        self.assertEqual(self.ghep()[a][:2], ("B3", "chac"))

    def test_anh_hai_mat_khong_canh_bao(self):
        self.cum_kh1(6)
        a = self.anh(D, "09:00:00", "P-A P-Z", ocr="Hai-laser 3/10/26")
        self.assertEqual(self.ghep()[a][:2], ("B3", "chac"))

    def test_cung_khach_khong_canh_bao(self):
        self.cum_kh1(6)
        a = self.anh(D, "09:00:00", "P-A", ocr="Mot-laser 3/10/26")
        self.assertEqual(self.ghep()[a][:2], ("A4", "chac"))

    def test_da_duyet_chi_bao_mau_thuan(self):
        self.cum_kh1(30)  # ảnh duyệt lệch cũng bỏ phiếu (x3): cụm phải đủ lớn mới còn >= 90%
        a = self.anh(D, "09:00:00", "P-A", xn="B3")
        cum = A.cum_khach(self.c)
        self.assertEqual(A.mau_thuan_da_duyet(self.c, cum), [(a, "B3", "KH1")])
        self.ghep()
        self.assertEqual(self.c.execute("SELECT xn_hd FROM photos WHERE id=?", (a,)).fetchone()[0], "B3")

    # ---------- 4. trang duyệt ----------
    def test_trang_duyet_hien_anh_mau(self):
        self.cum_kh1(6)
        a = self.anh(D, "09:00:00", "P-A", ocr="Hai-laser 3/10/26")
        self.ghep()
        self.assertEqual(A._ma_tu_ly_do_mat(self.c.execute("SELECT ly_do FROM photos WHERE id=?", (a,)).fetchone()[0]),
                         "KH1")
        f = os.path.join(self.tam, "x.jpg")
        open(f, "wb").close()
        self.c.execute("UPDATE photos SET anh_xem=? WHERE ngay != ?", (f, D))
        trang = A._trang_ngay(self.c, D).decode()
        self.assertIn("ảnh đã xác nhận của KH1 (theo khuôn mặt)", trang)
        self.assertIn("Mẫu KH2", trang)  # khách đang gắn: chưa có ảnh mẫu


if __name__ == "__main__":
    unittest.main()


class ChonHdMatUuTien(unittest.TestCase):
    def test_giu_hd_dang_gan_va_uu_tien_ngay_nhan(self):
        import datetime as dt
        vs = [{"code": "H14", "ngay": "2026-03-14", "gio": "10:00", "dich_vu": "PRP"},
              {"code": "H19", "ngay": "2026-03-19", "gio": "10:05", "dich_vu": "PRP"}]
        r = {"gio": dt.datetime(2026, 3, 19, 10, 0), "hd": "H14"}
        self.assertEqual(A._chon_hd_mat(vs, ["2026-03-14", "2026-03-19"], r, ["prp"])["code"], "H14")
        r["hd"] = None  # chưa gắn gì: ngày nhãn (đứng đầu danh sách) thắng ngày chụp
        self.assertEqual(A._chon_hd_mat(vs, ["2026-03-14", "2026-03-19"], r, ["prp"])["code"], "H14")
        self.assertEqual(A._chon_hd_mat(vs, ["2026-03-19"] + ["2026-03-14"], r, ["prp"])["code"], "H19")
