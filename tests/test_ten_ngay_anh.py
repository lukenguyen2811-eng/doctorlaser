"""Luật TÊN + NGÀY (Lượng 16/10) — DB tạm, dữ liệu bịa.

1. Nhãn ghi TÊN GỌI: nhãn >= 2 chữ ('Ngọc Anh') phải khớp ĐÚNG đuôi họ tên ('Trần Ngọc Anh'), không khớp
   'Nguyễn Thị Anh', không rơi xuống 1 chữ 'Anh'; 'tên nằm trong họ tên' chỉ cho tên nước ngoài/không dấu.
2. Ngày trên nhãn có thể ghi SAI: ảnh có ngày chụp gốc (ngay_goc=1) ưu tiên ngày chụp; không có -> ngày nhãn.

Chạy:  python3 -m unittest tests/test_ten_ngay_anh.py
"""
import datetime as dt
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ANH_DB", os.path.join(tempfile.mkdtemp(), "t.db"))
import anhkhach as A  # noqa: E402

D = "2026-10-10"   # ngày chụp
N = "2026-10-08"   # ngày ghi (sai) trên nhãn


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

    def khop(self, chu, goc=None, ngay_goc=1, ngay_anh=D):
        return A._khop_nhan(self.c, A.doc_nhan(chu, 2026)[0], ngay_anh, None, ngay_goc, goc)

    def anh(self, ngay, gio, ocr, ngay_goc=None, km="", do_tin=None, goi_y=None, ly_do=None):
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


# ---------------- 1. TÊN ----------------
class LuatTen(Nen):
    def test_ngoc_anh_khop_dung_duoi(self):
        self.hd("H1", D, "K1", "Trần Ngọc Anh", "CSD")
        self.hd("H2", D, "K2", "Nguyễn Thị Anh", "CSD")
        self.assertEqual(self.khop("Ngọc Anh-csd")[:2], ("H1", 85))

    def test_ngoc_anh_khong_khop_thi_anh(self):  # âm: không rơi xuống khớp 1 chữ 'Anh'
        self.hd("H2", D, "K2", "Nguyễn Thị Anh", "CSD")
        self.assertIsNone(self.khop("Ngọc Anh-csd")[0])

    def test_ngoc_anh_nam_giua_ten_viet_chi_goi_y(self):  # CEO 16/10 (2): đủ chữ, sai vị trí -> tối đa 50
        self.hd("H3", D, "K3", "Lê Ngọc Anh Thư", "CSD")
        hd, d, ly_do = self.khop("Ngọc Anh-csd")
        self.assertEqual((hd, d), ("H3", 50))
        self.assertIn("có đủ tên nhưng khác thứ tự/vị trí", ly_do)

    def test_dao_thu_tu_co_ho_ten_goi_3_chu_chi_goi_y(self):  # (2)
        for i, (nhan, ten) in enumerate([("Kim Mỹ", "Trần Thị Mỹ Kim"), ("Cao Thanh", "Cao Thị Thanh"),
                                          ("Ngọc Huyền", "Nguyễn Ngọc Huyền Trân"), ("Trần Hà", "Hà Trần")]):
            self.c.execute("DELETE FROM visits")
            self.hd(f"H{i}", D, f"K{i}", ten, "CSD")
            # CEO 16/10: 'Hà Trần' (2 chữ, cuối là họ phổ biến) = tên gọi Hà -> 'Trần Hà' khớp đúng như đuôi.
            self.assertEqual(self.khop(f"{nhan}-csd")[:2], (f"H{i}", 85 if ten == "Hà Trần" else 50), nhan)

    def test_du_chu_hai_khach_nguoi_chon(self):  # âm (2): 2 khách đủ chữ -> không đoán
        self.hd("H1", D, "K1", "Trần Thị Mỹ Kim", "CSD")
        self.hd("H2", D, "K2", "Lê Kim Mỹ Hoa", "CSD")
        self.assertEqual(self.khop("Kim Mỹ-csd")[:2], (None, 0))

    def test_du_chu_lech_dich_vu_40(self):  # (2) + lệch dịch vụ -> 40, không làm neo
        self.hd("H1", D, "K1", "Trần Thị Mỹ Kim", "Pico")
        self.assertEqual(self.khop("Kim Mỹ-csd")[:2], ("H1", 40))

    def test_thieu_mot_chu_khong_khop(self):  # âm (3): thiếu chữ 'Ngọc' -> không khớp, không rơi xuống 'Anh'
        self.hd("H2", D, "K2", "Nguyễn Thị Anh", "CSD")
        self.hd("H4", D, "K4", "Phạm Anh Ngân", "CSD")
        self.assertIsNone(self.khop("Ngọc Anh-csd")[0])

    def test_gan_spa_cum_cuoi(self):  # ten_sach bỏ 'gần spa' cuối -> khớp đúng đuôi, chắc
        self.assertEqual(A.ten_sach("CÔ THẢO GẦN SPA"), "co thao")
        self.assertEqual(A.ten_sach("Gần Spa"), "gan spa")  # cả tên chỉ có cụm này: giữ
        self.hd("H1", D, "K1", "CÔ THẢO GẦN SPA", "TIÊM FILLER")
        self.assertEqual(self.khop("Cô Thảo - trc filler môi 10/10/26")[:2], ("H1", 85))

    def test_khong_dau_van_phai_khop_duoi(self):  # nhãn mất dấu, tên khách có dấu -> vẫn là tên Việt
        self.hd("H2", D, "K2", "Nguyễn Thị Anh", "CSD")
        self.hd("H3", D, "K3", "Lê Ngọc Anh Thư", "CSD")
        self.assertEqual(self.khop("Ngoc Anh-csd")[:2], ("H3", 50))  # (2): chỉ gợi ý
        self.hd("H1", D, "K1", "Trần Ngọc Anh", "CSD")
        self.assertEqual(self.khop("Ngoc Anh-csd")[0], "H1")

    def test_ten_nuoc_ngoai_dao_thu_tu_van_khop(self):
        self.hd("H1", D, "K1", "Wu Cheng Wei", "CSD")
        self.assertEqual(self.khop("Cheng Wei-csd")[:2], ("H1", 85))
        self.hd("H9", D, "K9", "Cheng Wei Lin", "Pico")
        self.assertEqual(self.khop("Cheng Wei-csd")[0], "H1")  # 2 khách chứa tên -> dịch vụ tách

    def test_nhan_mot_chu_nhu_cu(self):
        self.hd("H2", D, "K2", "Nguyễn Thị Anh", "CSD")
        self.assertEqual(self.khop("Anh-csd")[:2], ("H2", 85))

    def test_bot_chu_chung_ben_trai_van_duoc(self):  # 'Laser Trang' -> 'Trang' (chữ chung, không phải tên)
        self.hd("H1", D, "K1", "Lê Thu Trang", "CSD")
        self.assertEqual(self.khop("Laser Trang-csd")[0], "H1")
        self.assertEqual(self.khop("Rỗ Trang-csd")[0], "H1")  # 'rỗ' = sẹo rỗ, không phải tên

    def test_ocr_lech_mot_chu_phai_dung_chu_truoc(self):
        self.hd("H1", D, "K1", "Trần Ngọc Thanh", "CSD")
        self.assertEqual(self.khop("Ngọc Thann-csd")[:2], ("H1", 50))
        self.c.execute("DELETE FROM visits")
        self.hd("H2", D, "K2", "Trần Văn Thanh", "CSD")
        self.assertIsNone(self.khop("Ngọc Thann-csd")[0])  # âm: 'Ngọc' != 'Văn'

    def test_lech_dich_vu_khong_lay_khach_chua_ten_o_giua(self):  # âm: nhánh 'khac' cũng phải khớp đuôi
        self.hd("H1", D, "K1", "Trần Ngọc Anh", "Pico")
        self.hd("H3", D, "K3", "Lê Ngọc Anh Thư", "CSD")
        hd, d, _ = self.khop("Ngọc Anh-csd")
        self.assertEqual((hd, d), ("H3", 50))  # khách đủ chữ + đúng dịch vụ: chỉ gợi ý, không 85

    def test_ten_nhan_hop(self):
        n2 = {"ten": "ngoc anh", "ten_goc": "ngọc anh"}
        self.assertTrue(A._ten_nhan_hop(n2, "Trần Ngọc Anh"))
        self.assertFalse(A._ten_nhan_hop(n2, "Nguyễn Thị Anh"))
        self.assertTrue(A._ten_nhan_hop(n2, "Lê Ngọc Anh Thư"))  # (2) đủ chữ: không phải 'tên khác'
        self.assertTrue(A._ten_nhan_hop({"ten": "kim my", "ten_goc": "kim mỹ"}, "Trần Thị Mỹ Kim"))
        self.assertFalse(A._ten_nhan_hop({"ten": "ngoc mai", "ten_goc": "ngọc mai"}, "Trịnh Xuân Mai"))
        self.assertTrue(A._ten_nhan_hop({"ten": "anh", "ten_goc": "anh"}, "Nguyễn Thị Anh"))  # 1 chữ như cũ
        self.assertTrue(A._ten_nhan_hop({"ten": "cheng wei", "ten_goc": "cheng wei"}, "Wu Cheng Wei"))
        self.assertTrue(A._ten_nhan_hop({"ten": "laser trang", "ten_goc": "laser trang"}, "Lê Thu Trang"))


# ---------------- 2. NGÀY ----------------
class LuatNgay(Nen):
    def test_co_ngay_goc_nhan_sai_ngay_theo_ngay_chup(self):
        self.hd("HD10", D, "K1", "Nguyễn Thị Quyên", "CSD MỤN")
        hd, d, ly_do = self.khop("Quyên-csd 8/10/26", goc=1)
        self.assertEqual((hd, d), ("HD10", 85))
        self.assertIn("nhãn ghi ngày 08/10 nhưng ảnh chụp ngày 10/10 (có ngày gốc) — theo ngày chụp", ly_do)

    def test_co_ngay_goc_ca_hai_ngay_co_hd_theo_ngay_chup(self):
        self.hd("HD10", D, "K1", "Nguyễn Thị Quyên", "CSD MỤN")
        self.hd("HD8", N, "K1", "Nguyễn Thị Quyên", "CSD MỤN")
        self.assertEqual(self.khop("Quyên-csd 8/10/26", goc=1)[0], "HD10")

    def test_co_ngay_goc_hai_ngay_hai_khach_khac_chi_goi_y(self):  # âm: không nâng 'chac' khi 2 ngày 2 khách
        self.hd("HD10", D, "K2", "Lê Văn Quyên", "CSD")
        self.hd("HD8", N, "K1", "Nguyễn Thị Quyên", "CSD MỤN")
        hd, d, ly_do = self.khop("Quyên-csd 8/10/26", goc=1)
        self.assertEqual((hd, d), ("HD10", 50))
        self.assertIn("có khách khác cùng tên", ly_do)

    def test_ngay_goc_0_sat_anh_exif_coi_nhu_co_ngay_goc(self):
        self.hd("HD10", D, "K1", "Nguyễn Thị Quyên", "CSD MỤN")
        self.hd("HD8", N, "K1", "Nguyễn Thị Quyên", "CSD MỤN")
        self.anh(D, "10:00:00", "", ngay_goc=1)
        a = self.anh(D, "10:00:30", "Quyên-csd 8/10/26", ngay_goc=0)   # sát ảnh EXIF 30s
        b = self.anh(D, "16:00:00", "Quyên-csd 8/10/26", ngay_goc=0)   # đứng riêng: âm, theo nhãn
        k = self.ghep()
        self.assertEqual(k[a][0], "HD10")
        self.assertEqual(k[b][0], "HD8")

    def test_khong_ngay_goc_theo_nhan(self):  # âm: ngay_goc 0 / NULL -> ngày nhãn như cũ
        self.hd("HD10", D, "K1", "Nguyễn Thị Quyên", "CSD MỤN")
        self.hd("HD8", N, "K1", "Nguyễn Thị Quyên", "CSD MỤN")
        self.assertEqual(self.khop("Quyên-csd 8/10/26", goc=None)[0], "HD8")
        self.assertEqual(self.khop("Quyên-csd 8/10/26", goc=0, ngay_goc=0)[0], "HD8")

    def test_co_ngay_goc_ngay_chup_khong_hd_theo_nhan(self):
        self.hd("HD8", N, "K1", "Nguyễn Thị Quyên", "CSD MỤN")
        hd, d, ly_do = self.khop("Quyên-csd 8/10/26", goc=1)
        self.assertEqual((hd, d), ("HD8", 85))
        self.assertIn("ảnh chụp ngày 10/10 (có ngày gốc) nhưng nhãn ghi ngày 08/10", ly_do)
        self.assertIn("theo ngày nhãn", ly_do)

    def test_ngay_chup_lech_dich_vu_theo_nhan(self):  # ngày chụp có khách nhưng dịch vụ lệch -> ngày nhãn
        self.hd("HD10", D, "K1", "Nguyễn Thị Quyên", "TRIỆT LÔNG")
        self.hd("HD8", N, "K1", "Nguyễn Thị Quyên", "CSD MỤN")
        self.assertEqual(self.khop("Quyên-csd 8/10/26", goc=1)[0], "HD8")

    def test_ngay_chup_trung_hai_khach_ngay_nhan_chi_goi_y(self):
        self.hd("HD10", D, "K1", "Nguyễn Thị Quyên", "CSD MỤN")
        self.hd("HD11", D, "K2", "Lê Quyên", "CSD")
        self.hd("HD8", N, "K1", "Nguyễn Thị Quyên", "CSD MỤN")
        hd, d, _ = self.khop("Quyên-csd 8/10/26", goc=1)
        self.assertEqual(hd, "HD8")
        self.assertLessEqual(d, 50)

    def test_khong_ngay_nao_co_hd(self):
        self.hd("HD9", "2026-10-09", "K1", "Nguyễn Thị Quyên", "CSD MỤN")  # ngày kế ngày nhãn, không phải 2 ngày
        hd, d, _ = self.khop("Quyên-csd 8/10/26", goc=1)
        self.assertNotEqual(d, 85)

    def test_ghep_ngay_anh_exif_va_anh_khong_ro(self):
        self.hd("HD10", D, "K1", "Nguyễn Thị Quyên", "CSD MỤN")
        self.hd("HD8", N, "K1", "Nguyễn Thị Quyên", "CSD MỤN")
        a = self.anh(D, "10:00:00", "Quyên-csd 8/10/26", ngay_goc=1)
        b = self.anh(D, "15:00:00", "Quyên-csd 8/10/26", ngay_goc=None)
        k = self.ghep()
        self.assertEqual(k[a][:2], ("HD10", "chac"))
        self.assertIn("theo ngày chụp", k[a][2])
        self.assertEqual(k[b][:2], ("HD8", "chac"))
        self.assertNotIn("theo ngày chụp", k[b][2])


# ---------------- 2b. NGÀY trong luật mặt ----------------
class ChonHdMat(unittest.TestCase):
    vs = [{"code": "H14", "ngay": "2026-03-14", "gio": "10:00", "dich_vu": "PRP"},
          {"code": "H19", "ngay": "2026-03-19", "gio": "10:05", "dich_vu": "PRP"}]

    def r(self, hd, goc):
        return {"gio": dt.datetime(2026, 3, 19, 10, 0), "hd": hd, "goc": goc}

    def test_co_ngay_goc_bo_hd_ngay_nhan_dang_gan(self):
        self.assertEqual(A._chon_hd_mat(self.vs, ["2026-03-19", "2026-03-14"], self.r("H14", 1), ["prp"])["code"], "H19")

    def test_khong_ngay_goc_giu_hd_dang_gan(self):  # âm: như cũ
        self.assertEqual(A._chon_hd_mat(self.vs, ["2026-03-14", "2026-03-19"], self.r("H14", None), ["prp"])["code"],
                         "H14")

    def test_co_ngay_goc_ngay_chup_lech_dich_vu_giu(self):  # âm: HĐ ngày chụp không khớp dịch vụ -> giữ
        vs = [self.vs[0], dict(self.vs[1], dich_vu="Kem chống nắng")]
        self.assertEqual(A._chon_hd_mat(vs, ["2026-03-19", "2026-03-14"], self.r("H14", 1), ["prp"])["code"], "H14")
        self.assertEqual(A._chon_hd_mat(vs, ["2026-03-19", "2026-03-14"], self.r(None, 1), ["prp"])["code"], "H14")


class MatTheoNgay(Nen):
    D3 = "2026-10-03"

    def setUp(self):
        super().setUp()
        for code, ngay, ma, ten in [("A1", "2026-09-01", "KH1", "Khach Mot"), ("A2", "2026-09-10", "KH1", "Khach Mot"),
                                    ("A4", self.D3, "KH1", "Khach Mot"), ("A5", "2026-10-01", "KH1", "Khach Mot"),
                                    ("L4", self.D3, "KH9", "Le Mot"), ("L5", "2026-10-01", "KH9", "Le Mot")]:
            self.c.execute("INSERT INTO visits VALUES (?,?,?,?,?,?,?,?)", (code, ngay, "10:00", ma, ten, "", "Laser", ""))
        for i, (hd, ngay) in enumerate([("A1", "2026-09-01"), ("A1", "2026-09-01"), ("A2", "2026-09-10")]):
            self.anh(ngay, f"10:0{i}:00", "", km="P-A", do_tin="chac", goi_y=hd, ly_do="nhãn 'Mot-laser' khớp")

    def test_mat_co_ngay_goc_theo_ngay_chup(self):
        a = self.anh(self.D3, "09:00:00", "Mot-laser 1/10/26", ngay_goc=1, km="P-A")  # nhãn trùng 2 khách
        k = self.ghep(self.D3)[a]
        self.assertEqual(k[:2], ("A4", "chac"))
        self.assertIn("theo ngày chụp", k[2])

    def test_mat_va_nhan_du_chu_khac_vi_tri_len_chac(self):
        self.c.execute("UPDATE visits SET ten_kh='Trần Một Khach' WHERE ma_kh='KH1'")  # nhãn 'Khach Một' đảo thứ tự
        self.c.execute("DELETE FROM visits WHERE ma_kh='KH9'")
        a = self.anh(self.D3, "09:00:00", "Khach Một-laser 3/10/26", ngay_goc=1, km="P-A")
        k = self.ghep(self.D3)[a]
        self.assertEqual(k[:2], ("A4", "chac"))
        self.assertNotIn("nhãn ghi tên khác", k[2])

    def test_mat_nhan_thieu_chu_la_ten_khac(self):  # âm (3)
        self.c.execute("UPDATE visits SET ten_kh='Trần Thị Mot' WHERE ma_kh='KH1'")
        self.c.execute("DELETE FROM visits WHERE ma_kh='KH9'")
        a = self.anh(self.D3, "09:00:00", "Ngọc Mot-laser 3/10/26", ngay_goc=1, km="P-A")
        k = self.ghep(self.D3)[a]
        self.assertNotEqual(k[1], "chac")

    def test_mat_khong_ngay_goc_nhu_cu(self):  # âm: như cũ (luật 'cùng khuôn mặt' đã gắn A4 -> giữ), không ghi chú ngày
        a = self.anh(self.D3, "09:00:00", "Mot-laser 1/10/26", ngay_goc=None, km="P-A")
        k = self.ghep(self.D3)[a]
        self.assertEqual(k[:2], ("A4", "chac"))
        self.assertNotIn("có ngày gốc", k[2])


if __name__ == "__main__":
    unittest.main()
