"""Luật TÊN CUỐI + luật MẶT nới (CEO 16/10) — DB tạm, dữ liệu bịa.

1. Nhãn 1 chữ chỉ khớp khi = TÊN CUỐI ('Thảo' ~ 'Nguyễn Thị Thảo'); trùng chữ đệm ('Phạm Đỗ Thảo Vy') -> không
   bao giờ chắc (mọi nhánh), tối đa gợi ý 50 và chỉ khi ngày đó không ai có tên cuối khớp.
2. Ảnh có mặt thuộc cụm MẠNH của khách K + K có HĐ ngày đó: nhãn đảo thứ tự / OCR lệch 1 ký tự / chữ đệm sai /
   thiếu chữ cuối vẫn hợp K -> chắc 82; trừ khi nhãn khớp đúng đuôi tên một khách KHÁC có HĐ cùng ngày.

Chạy:  python3 -m unittest tests/test_ten_cuoi_mat_anh.py
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ANH_DB", os.path.join(tempfile.mkdtemp(), "t.db"))
import anhkhach as A  # noqa: E402

D = "2026-10-10"


class Nen(unittest.TestCase):
    def setUp(self):
        self.tam = tempfile.mkdtemp()
        self.p = mock.patch.object(A, "DB_FILE", os.path.join(self.tam, "t.db"))
        self.p.start()
        self.c = A.ket_noi()
        self.so = 0

    def tearDown(self):
        self.c.close()
        self.p.stop()

    def hd(self, code, ngay, ma, ten, dv, gio="10:00"):
        self.c.execute("INSERT INTO visits (code,ngay,gio,ma_kh,ten_kh,dich_vu) VALUES (?,?,?,?,?,?)",
                       (code, ngay, gio, ma, ten, dv))

    def khop(self, chu, goc=1, ngay_anh=D):
        return A._khop_nhan(self.c, A.doc_nhan(chu, 2026)[0], ngay_anh, None, 1, goc)

    def anh(self, ngay, gio, ocr="", km="", do_tin=None, goi_y=None, ly_do=None, ngay_goc=1):
        self.so += 1
        pid = f"p{self.so}"
        self.c.execute("INSERT INTO photos (id,nguon,ngay,thoi_gian,ten_file,chu_thich,ocr,khuon_mat,do_tin,"
                       "goi_y_hd,ly_do,bo_qua,ngay_goc) VALUES (?,?,?,?,?,?,?,?,?,?,?,0,?)",
                       (pid, "photos", ngay, f"{ngay}T{gio}", "IMG.HEIC", "", ocr, km, do_tin, goi_y, ly_do,
                        ngay_goc))
        return pid

    def ghep(self, ngay=D):
        A.ghep_ngay(self.c, ngay)
        return {r[0]: (r[1], r[2], r[3]) for r in
                self.c.execute("SELECT id, goi_y_hd, do_tin, ly_do FROM photos WHERE ngay=?", (ngay,))}


# ---------------- 1. NHÃN 1 CHỮ = TÊN CUỐI ----------------
class TenCuoi(Nen):
    def test_chu_dem_co_khach_ten_cuoi_khong_lay(self):  # ca thật 31/01: 'Thảo-csd', có 'Cô Thảo' (filler)
        self.hd("HC", D, "KC", "CÔ THẢO GẦN SPA", "TIÊM FILLER")
        self.hd("HV", D, "KV", "PHẠM ĐỖ THẢO VY", "CSD")
        hd, d, _ = self.khop("Thảo-csd 10/10/26")
        self.assertNotEqual(hd, "HV")
        self.assertLess(d, 80)

    def test_chu_dem_khong_ai_ten_cuoi_chi_goi_y(self):
        self.hd("HV", D, "KV", "PHẠM ĐỖ THẢO VY", "CSD")
        self.assertEqual(self.khop("Thảo-csd 10/10/26")[:2], ("HV", 50))

    def test_chu_dem_bot_chu_chung_chi_goi_y(self):  # 'Laser Thảo' còn 1 chữ -> như nhãn 1 chữ
        self.hd("HV", D, "KV", "Phạm Đỗ Thảo Vy", "CSD")
        self.assertLessEqual(self.khop("Laser Thảo-csd 10/10/26")[1], 50)

    def test_ten_cuoi_van_chac(self):  # dương: đúng tên cuối như cũ
        self.hd("HT", D, "KT", "Nguyễn Thị Thảo", "CSD")
        self.hd("HV", D, "KV", "Phạm Đỗ Thảo Vy", "CSD")
        self.assertEqual(self.khop("Thảo-csd 10/10/26")[:2], ("HT", 85))

    def test_ten_cuoi_lech_dv_khong_sang_khach_chu_dem(self):  # âm: nhánh 'khac' không lấy chữ đệm
        self.hd("HT", D, "KT", "Nguyễn Thị Thảo", "Pico")
        self.hd("HV", D, "KV", "Phạm Đỗ Thảo Vy", "CSD")
        self.assertEqual(self.khop("Thảo-csd 10/10/26")[:2], ("HT", 40))

    def test_luat_ngay_chu_dem_khong_chac(self):  # ảnh có ngày gốc, nhãn ghi ngày khác: vẫn không chắc
        self.hd("HV", D, "KV", "Phạm Đỗ Thảo Vy", "CSD")
        self.hd("HN", "2026-10-08", "KN", "Lê Thảo My", "CSD")
        hd, d, _ = self.khop("Thảo-csd 8/10/26", goc=1)
        self.assertLess(d, 80)
        hd, d, _ = self.khop("Thảo-csd 8/10/26", goc=0)
        self.assertLess(d, 80)

    def test_ten_nhan_hop_mot_chu(self):
        self.assertFalse(A._ten_nhan_hop({"ten": "thao", "ten_goc": "thảo"}, "Phạm Đỗ Thảo Vy"))
        self.assertTrue(A._ten_nhan_hop({"ten": "thao", "ten_goc": "thảo"}, "Nguyễn Thảo"))
        self.assertFalse(A._ten_nhan_hop({"ten": "laser thao", "ten_goc": "laser thảo"}, "Phạm Thảo Vy"))

    def test_bo_chup_khong_len_chac(self):  # luật bộ: nhãn chữ đệm không làm neo chắc cho 5 tấm
        self.hd("HC", D, "KC", "Cô Thảo", "TIÊM FILLER", "10:45")
        self.hd("HV", D, "KV", "Phạm Đỗ Thảo Vy", "CSD", "15:32")
        ids = [self.anh(D, "15:48:00", "Thảo-csd 10/10/26")] + [self.anh(D, f"15:48:{s:02d}") for s in (10, 20, 30, 40)]
        k = self.ghep()
        self.assertFalse([i for i in ids if k[i][1] == "chac"])
        self.assertFalse([i for i in ids if k[i][0] == "HV" and k[i][1] != "chua_ro" and "nhãn" in (k[i][2] or "")
                          and "khớp tên + dịch vụ" in k[i][2]])


# ---------------- 1b. TÊN 'Tên Họ' 2 chữ (họ phổ biến cuối) ----------------
class TenHoCuoi(Nen):
    def test_thu_tu_goi(self):
        f = A._thu_tu_goi
        self.assertEqual(f(["vy", "nguyen"]), ["nguyen", "vy"])
        self.assertEqual(f(["mai", "nguyen"]), ["nguyen", "mai"])
        self.assertEqual(f(["nguyen", "mai"]), ["nguyen", "mai"])  # âm: 'mai' không trong danh sách họ
        self.assertEqual(f(["lan", "ha"]), ["lan", "ha"])  # âm: 'hà' vừa là tên
        self.assertEqual(f(["thi", "vy", "nguyen"]), ["thi", "vy", "nguyen"])  # âm: 3 chữ không áp
        self.assertEqual(A.ten_goi("VY NGUYỄN (KH TỰ ĐẾN)"), "Vy")
        self.assertEqual(A.ten_goi("Nguyễn Mai"), "Mai")

    def test_nhan_mot_chu_bang_chu_dau(self):
        self.hd("H1", D, "K1", "Vy Nguyễn", "CSD")
        self.assertEqual(self.khop("Vy-csd 10/10/26")[:2], ("H1", 85))

    def test_nhan_hai_chu_ten_ho(self):
        self.hd("H1", D, "K1", "Vy Nguyễn", "CSD")
        self.assertEqual(self.khop("Vy Nguyễn-csd 10/10/26")[:2], ("H1", 85))
        self.assertEqual(self.khop("Nguyễn Vy-csd 10/10/26")[:2], ("H1", 85))

    def test_mai_nguyen_ten_goi_mai(self):
        self.hd("H1", D, "K1", "Mai Nguyễn", "CSD")
        self.assertEqual(self.khop("Mai-csd 10/10/26")[:2], ("H1", 85))

    def test_nguyen_mai_giu_ten_cuoi(self):  # âm: 'Nguyễn Mai' -> tên gọi Mai, nhãn 'Nguyễn' không khớp tên cuối
        self.hd("H1", D, "K1", "Nguyễn Mai", "CSD")
        self.assertEqual(self.khop("Mai-csd 10/10/26")[:2], ("H1", 85))
        self.assertLessEqual(self.khop("Nguyễn-csd 10/10/26")[1], 50)

    def test_ba_chu_khong_ap(self):  # âm: 'Vy Thị Nguyễn' 3 chữ -> tên cuối vẫn 'Nguyễn', 'Vy' không chắc
        self.hd("H1", D, "K1", "Vy Thị Nguyễn", "CSD")
        self.assertLessEqual(self.khop("Vy-csd 10/10/26")[1], 50)

    def test_ho_cuoi_mot_chu_ho_khong_chac(self):  # âm: 'Vy Nguyễn' -> nhãn 'Nguyễn' là họ, không chắc
        self.hd("H1", D, "K1", "Vy Nguyễn", "CSD")
        self.assertLessEqual(self.khop("Nguyễn-csd 10/10/26")[1], 50)

    def test_nhan_ket_thuc_bang_ho_van_khop_ten_3_chu(self):  # âm (đo 16/10: đảo nhãn cho mọi khách hạ 357 ảnh)
        self.hd("H1", D, "K1", "Nguyễn Thị Thùy Dương", "CSD")
        self.hd("H2", D, "K2", "Trần Minh Hoàng", "Pico")
        self.assertEqual(self.khop("Thùy Dương-csd 10/10/26")[:2], ("H1", 85))
        self.assertEqual(self.khop("Minh Hoàng-pico 10/10/26")[:2], ("H2", 85))
        self.assertTrue(A._ten_nhan_hop({"ten": "thuy duong", "ten_goc": "thùy dương"}, "Nguyễn Thị Thùy Dương"))
        self.assertTrue(A._ten_dung_duoi({"ten": "minh hoang", "ten_goc": "minh hoàng"}, "Trần Minh Hoàng"))

    def test_ten_nhan_hop_va_mat(self):
        n = {"ten": "vy", "ten_goc": "vy"}
        self.assertTrue(A._ten_nhan_hop(n, "Vy Nguyễn"))
        self.assertTrue(A._ten_hop_mat(n, "Vy Nguyễn"))
        self.assertFalse(A._ten_nhan_hop(n, "Vy Thị Nguyễn"))
        self.assertTrue(A._ten_dung_duoi({"ten": "vy nguyen", "ten_goc": "vy nguyễn"}, "Vy Nguyễn"))

    def test_trang_duyet_ten_goi_khop(self):
        self.assertTrue(A._khop_ten_goi([k for _, k in A._tu_ten_goi("Vy Nguyễn")], [], [["vy"]]))
        self.assertFalse(A._khop_ten_goi([k for _, k in A._tu_ten_goi("Vy Thị Nguyễn")], [], [["vy"]]))


# ---------------- 2. LUẬT MẶT NỚI (cụm mạnh) ----------------
class MatNoi(Nen):
    def cum(self, ma, ten, n=6, km="P-K"):  # cụm mạnh: n ảnh neo nhãn ở 2 ngày của khách ma
        for i, ngay in enumerate(("2026-09-01", "2026-09-15")):
            self.hd(f"{ma}-{i}", ngay, ma, ten, "CSD")
        for i in range(n):
            ngay = "2026-09-01" if i % 2 == 0 else "2026-09-15"
            self.anh(ngay, f"10:{i:02d}:00", km=km, do_tin="chac", goi_y=f"{ma}-{i % 2}", ly_do="nhãn 'x-csd' khớp")
        self.hd(f"{ma}-D", D, ma, ten, "CSD", "15:00")

    def mot(self, ocr, km="P-K"):
        a = self.anh(D, "15:10:00", ocr, km=km)
        return self.ghep()[a]

    def test_ocr_lech_mot_ky_tu(self):  # (b) 'Thaor Nguyên' ~ 'Phan Thị Thảo Nguyên'
        self.cum("K1", "Phan Thị Thảo Nguyên")
        k = self.mot("Thaor Nguyên-nang 10/10/26")
        self.assertEqual(k[:2], ("K1-D", "chac"))
        self.assertIn("khuôn mặt thuộc khách K1", k[2])

    def test_dao_thu_tu(self):  # (a) 'Như Thảo' ~ 'Trần Thảo Như'
        self.cum("K1", "Trần Thảo Như")
        self.assertEqual(self.mot("Như Thảo-csd 10/10/26")[:2], ("K1-D", "chac"))

    def test_chu_dem_thieu_chu_cuoi(self):  # (c) 'Hoàng Minh' ~ 'Đỗ Hoàng Minh Khang'
        self.cum("K1", "Đỗ Hoàng Minh Khang")
        self.hd("HX", D, "KX", "Lê Hoàng Duy", "Laser")
        self.assertEqual(self.mot("Hoàng Minh-csd 10/10/26")[:2], ("K1-D", "chac"))

    def test_chu_dem_sai_ten_cuoi_dung(self):  # (d) 'Hoàng Nam' ~ 'Đỗ Hoài Nam'; khách khác 'Kim Phạm Hoài Nam'
        self.cum("K1", "Đỗ Hoài Nam")
        self.hd("HX", D, "KX", "Kim Phạm Hoài Nam", "Kem")
        self.assertEqual(self.mot("Hoàng Nam-csd 10/10/26")[:2], ("K1-D", "chac"))

    def test_ngoc_mai_cum_manh_chac(self):  # (d) 'Ngọc Mai' ~ 'Trịnh Xuân Mai'
        self.cum("K1", "Trịnh Xuân Mai")
        self.hd("HX", D, "KX", "Trần Thị Mai Trang", "CSD")
        self.assertEqual(self.mot("Ngọc Mai-csd 10/10/26")[:2], ("K1-D", "chac"))

    def test_ngoc_mai_cum_yeu_khong_chac(self):  # âm: cụm chưa mạnh (3 ảnh neo) -> luật cũ, tên khác
        self.cum("K1", "Trịnh Xuân Mai", n=3)
        k = self.mot("Ngọc Mai-csd 10/10/26")
        self.assertNotEqual(k[1], "chac")

    def test_khach_khac_dung_duoi_khong_chac(self):  # âm: nhãn khớp đúng tên khách khác có HĐ cùng ngày
        self.cum("K1", "Trịnh Xuân Mai")
        self.hd("HX", D, "KX", "Lê Ngọc Mai", "Pico")  # dịch vụ lệch -> nhãn chỉ 40, không chắc
        k = self.mot("Ngọc Mai-csd 10/10/26")
        self.assertNotEqual(k[1], "chac")
        self.assertIn("khách khác", k[2])

    def test_khach_khac_dung_duoi_dao_thu_tu_khong_chac(self):  # âm (a): 'Như Thảo' có khách 'Lê Như Thảo'
        self.cum("K1", "Trần Thảo Như")
        self.hd("HX", D, "KX", "Lê Như Thảo", "Pico")
        self.assertNotEqual(self.mot("Như Thảo-csd 10/10/26")[1], "chac")

    def test_mot_chu_dem_cum_manh_khong_chac(self):  # âm (luật 1): 'Thảo' ~ chữ đệm của K
        self.cum("K1", "Phạm Đỗ Thảo Vy")
        k = self.mot("Thảo-csd 10/10/26")
        self.assertNotEqual(k[1], "chac")

    def test_mot_chu_ten_cuoi_lech_ocr_chac(self):  # 1 chữ = tên cuối lệch 1 ký tự OCR -> chắc
        self.cum("K1", "Phan Thị Thảo")
        self.assertEqual(self.mot("Thaor-csd 10/10/26")[:2], ("K1-D", "chac"))

    def test_ten_khac_han_khong_chac(self):  # âm: 'Hoàng Lan' ~ 'Đỗ Hoài Nam' -> tên khác
        self.cum("K1", "Đỗ Hoài Nam")
        k = self.mot("Hoàng Lan-csd 10/10/26")
        self.assertNotEqual(k[1], "chac")
        self.assertIn("nhãn ghi tên khác", k[2])

    def test_khong_hd_ngay_do_khong_chac(self):  # âm: K không có HĐ ngày chụp/ngày nhãn
        self.cum("K1", "Trần Thảo Như")
        self.c.execute("DELETE FROM visits WHERE code='K1-D'")
        self.assertNotEqual(self.mot("Như Thảo-csd 10/10/26")[1], "chac")

    def test_ham_ten_hop_mat(self):
        f = A._ten_hop_mat
        n = lambda t: A.doc_nhan(t, 2026)[0]  # noqa: E731
        self.assertTrue(f(n("Thaor Nguyên-x 1/1/26"), "Phan Thị Thảo Nguyên"))
        self.assertTrue(f(n("Hoàng Minh-x 1/1/26"), "Đỗ Hoàng Minh Khang"))
        self.assertTrue(f(n("Ngọc Mai-x 1/1/26"), "Trịnh Xuân Mai"))
        self.assertFalse(f(n("Thảo-x 1/1/26"), "Phạm Đỗ Thảo Vy"))
        self.assertFalse(f(n("Ngọc Lan-x 1/1/26"), "Trịnh Xuân Mai"))
        self.assertFalse(f(n("Vy-x 1/1/26"), "Phạm Thị Vân"))


if __name__ == "__main__":
    unittest.main()
