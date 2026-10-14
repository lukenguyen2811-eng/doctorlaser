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

    def hd(self, code, ngay, ma, ten, dv, gio="10:00", mau=True):
        self.c.execute("INSERT INTO visits (code,ngay,gio,ma_kh,ten_kh,dich_vu) VALUES (?,?,?,?,?,?)",
                       (code, ngay, gio, ma, ten, dv))
        if mau:  # luật gói đòi mã KH đã có ảnh chắc/đã duyệt ở ngày khác -> mặc định cho 1 ảnh chắc ngày HĐ
            self.c.execute("INSERT INTO photos (id,ngay,thoi_gian,ten_file,chu_thich,ocr,goi_y_hd,do_tin) VALUES"
                           " (?,?,?,'IMG.HEIC','','',?,'chac')", (f"mau{code}", ngay, f"{ngay}T09:00:00", code))

    def anh_ngay(self, ngay):
        return {x["id"]: x for x in self.c.execute("SELECT * FROM photos WHERE ngay=?", (ngay,))}

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
        self.assertIn("2 khách cùng tên trong 180 ngày trước", ly_do)
        self.assertIn("người chọn", ly_do)

    def test_hai_khach_chi_mot_khach_mua_goi_van_nguoi_chon(self):
        # Bỏ mẹo 'chỉ 1 khách mua gói' (soát 14/10: nam/nữ trùng tên Giang): trùng tên là người chọn.
        self.hd("HDA", "2026-08-10", "KH01", "Nguyễn Thị Quyên", "COMBO CSD ( 10 LẦN )")
        self.hd("HDA2", "2026-09-10", "KH01", "Nguyễn Thị Quyên", "CSD MỤN")
        self.hd("HDB", "2026-09-30", "KH02", "Lê Quyên", "CSD MỤN")
        hd, _, ly_do = self.khop("Quyên-csd 9/10/26")
        self.assertIsNone(hd)
        self.assertIn("2 khách cùng tên", ly_do)

    def test_trung_ten_khac_dich_vu_van_nguoi_chon(self):
        self.hd("HDA", "2026-08-10", "KH01", "Phạm Thị Hương", "PEEL DA MỤN (LẦN LẺ)")
        self.hd("HDB", "2026-09-01", "KH02", "Trần Văn Hương", "TRIỆT LÔNG")  # khác dịch vụ vẫn tính
        hd, _, ly_do = self.khop("Hương-csd 9/10/26")
        self.assertIsNone(hd)
        self.assertIn("2 khách cùng tên", ly_do)

    def test_ten_khac_dau_khong_ap(self):
        self.hd("HDG", "2026-08-10", "KH01", "Nguyễn Thị Hiền", "DẶM FILLER LÀM ĐẦY")
        self.assertIsNone(self.khop("Hiến-filler 9/10/26")[0])
        self.hd("HDT", "2026-08-10", "KH02", "Lê Thị Thư", "CSD MỤN")
        self.assertIsNone(self.khop("Thu-csd 9/10/26")[0])  # nhãn mất dấu -> không áp
        self.assertIsNone(self.khop("Thú-csd 9/10/26")[0])  # Thú != Thư
        self.assertEqual(self.khop("Thư-csd 9/10/26")[:2], ("HDT", 50))
        self.hd("HDN", "2026-08-10", "KH03", "Phước An", "PEEL DA MỤN")
        self.assertIsNone(self.khop("A Ân - csd 9/10/26")[0])  # Ân != An

    def test_vi_tri_dau_khong_tinh(self):
        self.hd("HDH", "2026-08-10", "KH01", "Lê Thị Hòa", "CSD MỤN")
        self.assertEqual(self.khop("Hoà-csd 9/10/26")[:2], ("HDH", 50))  # hoà = hòa

    def test_nhan_mat_het_dau_khong_ap(self):
        self.hd("HDG", "2026-08-10", "KH01", "Nguyễn Thị Quyên", "COMBO CSD ( 10 LẦN )")
        self.assertIsNone(self.khop("Quyen-csd 9/10/26")[0])

    def test_chi_khop_nguyen_ten_goi(self):
        self.hd("HDH", "2026-08-10", "KH01", "Đinh Như Hằng", "CSD MỤN")
        self.assertIsNone(self.khop("Như-csd 9/10/26")[0])  # chữ giữa họ tên
        self.hd("HDA", "2026-08-10", "KH02", "Trần Anh", "CSD MỤN")
        self.assertIsNone(self.khop("Ngọc Anh-csd 9/10/26")[0])  # nhãn tên kép, khách tên đơn
        self.hd("HDM", "2026-08-10", "KH03", "Nguyễn Thị Trúc Mai", "CSD MỤN")
        self.assertEqual(self.khop("Trúc Mai-csd 9/10/26")[:2], ("HDM", 50))
        self.assertIsNone(self.khop("Mai Trúc-csd 9/10/26")[0])  # đảo thứ tự

    def test_dv_goi_dong_chinh(self):
        f = A._dv_goi_khop
        tham_mat = ("COMBO ĐIỀU TRỊ THÂM MẮT ( TIÊM HA LÀM ĐẦY + TIÊM MESO + SERUM ) | TIÊM LÀM ĐẦY HÕM MẮT"
                    " | TIÊM MESO SKIN BOOSTER (căng bóng, trắng sáng, giảm nám) | MELASMA-REVSKIN")
        self.assertFalse(f("pico", tham_mat))
        self.assertTrue(A._dv_khop("pico", tham_mat))  # luật khác vẫn như cũ
        self.assertTrue(f("pico", "PICO TRỊ NÁM"))
        self.assertTrue(f("meso", tham_mat))
        self.assertFalse(f("prp", "ĐIỀU TRỊ SẸO RỖ ĐA PHƯƠNG THỨC LẦN LẺ (cắt sẹo, laser mài viền, PRP phục hồi)"))
        # CEO 14/10: dòng LẦN LẺ không tính là gói (mua lẻ thì buổi sau phải có HĐ mới).
        self.assertFalse(f("seo", "ĐIỀU TRỊ SẸO RỖ ĐA PHƯƠNG THỨC LẦN LẺ (cắt sẹo, laser mài viền, PRP phục hồi)"))
        self.assertFalse(f("prp", "TIÊM PRP PREMIUM ( LẦN LẺ )"))
        self.assertFalse(f("csd", "CSD MỤN (lan le)"))
        self.assertTrue(f("csd", "TIÊM PRP PREMIUM ( LẦN LẺ ) | CSD MỤN"))  # dòng khác vẫn xét
        self.assertFalse(f("seo", "THANH TOÁN CÔNG NỢ CSD | ĐIỆN DI C SAU SẸO"))
        self.assertFalse(f("csd", "THANH TOÁN CÔNG NỢ CSD"))
        self.assertTrue(f("csd", "KEM REVITALUX | CSD MỤN"))
        self.assertTrue(f("csd", "COMBO CSD ( 10 LẦN )"))
        self.assertTrue(f("prp", "COMBO TIÊM PRP PREMIUM ( 4 + 1 )"))
        self.assertTrue(f("tl", "TRIỆT LÔNG"))
        self.assertTrue(f("co2", "LASER FRACTIONAL"))
        self.assertFalse(f("tri", "ĐIỀU TRỊ SẸO RỖ"))

    def test_pico_khong_khop_combo_tham_mat(self):
        self.hd("HDC", "2026-08-10", "KH01", "Nguyễn Ngọc Hân",
                "COMBO ĐIỀU TRỊ THÂM MẮT ( TIÊM HA LÀM ĐẦY + TIÊM MESO + SERUM )")
        self.assertIsNone(self.khop("Hân-pico 9/10/26")[0])
        self.assertIsNone(self.khop("Hân-meso 9/10/26")[0])  # meso chỉ nằm trong ngoặc mô tả
        self.assertEqual(self.khop("Hân-tt 9/10/26")[:2], ("HDC", 50))  # 'thâm' là chữ chính của mã tt

    def test_combo_lan_le_khong_tinh_la_goi(self):
        self.hd("HDA", "2026-08-10", "KH01", "Nguyễn Thị Quyên", "COMBO CSD MỤN + PEEL DA MỤN ( LẦN LẺ )")
        self.hd("HDB", "2026-09-01", "KH02", "Lê Quyên", "CSD MỤN")
        self.assertIsNone(self.khop("Quyên-csd 9/10/26")[0])  # 2 khách cùng tên -> người chọn

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
        self.hd("HDN", "2026-10-09", "KH01", "Nguyễn Thị Quyên", "KEM REVITALUX", mau=False)
        self.assertEqual(self.khop("Quyên-csd 9/10/26")[:2], ("HDN", 40))

    def test_trung_ten_trong_ngay_khong_chay_luat_goi(self):
        self.hd("HDG", "2026-08-10", "KH01", "Nguyễn Thị Quyên", "COMBO CSD ( 10 LẦN )")
        self.hd("HDX", "2026-10-09", "KH03", "Phạm Quyên", "PICO", mau=False)
        self.hd("HDY", "2026-10-09", "KH04", "Võ Quyên", "PICO", mau=False)
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
        r = self.anh_ngay("2026-02-20")
        self.assertEqual({x["do_tin"] for x in r.values()}, {"goi_y"})
        self.assertEqual({x["goi_y_hd"] for x in r.values()}, {"HDG"})
        self.assertIn("buổi theo gói", r["p0"]["ly_do"])
        # Trang duyệt: HĐ cũ cùng năm hiện trong mục "Hóa đơn ngày khác" với ngày dd/mm.
        trang = A._trang_ngay(self.c, "2026-02-20").decode()
        self.assertIn("Hóa đơn ngày khác", trang)
        self.assertIn("<option value='HDG' selected>20/01 ", trang)

    def test_ngay_co_hd_khach_khac_bo_chup_chi_goi_y(self):
        self.hd("HDG", "2026-08-10", "KH01", "Nguyễn Thị Quyên", "COMBO CSD ( 10 LẦN )")
        self.hd("HDK", "2026-10-09", "KH09", "Trần Văn Khác", "PICO", gio="15:00", mau=False)
        for i in range(5):
            tg = f"2026-10-09T10:00:{i * 10:02d}"
            self.c.execute("INSERT INTO photos (id,ngay,thoi_gian,ten_file,chu_thich,ocr) VALUES (?,?,?,?,?,?)",
                           (f"p{i}", tg[:10], tg, "IMG.HEIC", "", "Quyên-csd 9/10/26" if i == 2 else ""))
        A.ghep_ngay(self.c, "2026-10-09")
        r = list(self.c.execute("SELECT do_tin, goi_y_hd FROM photos WHERE ngay='2026-10-09'"))
        self.assertEqual({tuple(x) for x in r}, {("goi_y", "HDG")})

    def test_trang_duyet_hd_khac_nam_co_nam(self):
        self.hd("HDG", "2025-12-15", "KH01", "Nguyễn Thị Quyên", "COMBO CSD ( 10 LẦN )")
        self.c.execute("INSERT INTO photos (id,ngay,thoi_gian,ten_file,chu_thich,ocr) VALUES"
                       " ('q1','2026-02-20','2026-02-20T10:00:00','IMG.HEIC','','Quyên-csd 20/2/26')")
        A.ghep_ngay(self.c, "2026-02-20")
        p = self.anh_ngay("2026-02-20")["q1"]
        self.assertEqual((p["goi_y_hd"], p["do_tin"]), ("HDG", "goi_y"))
        trang = A._trang_ngay(self.c, "2026-02-20").decode()
        self.assertIn("<option value='HDG' selected>15/12/25 ", trang)

    def anh_mat(self, km_nay, km_cu):
        self.hd("HDG", "2026-08-10", "KH01", "Nguyễn Thị Quyên", "COMBO CSD ( 10 LẦN )")
        # Ảnh đã duyệt ngày khác của KH01.
        self.c.execute("INSERT INTO photos (id,ngay,thoi_gian,ten_file,chu_thich,ocr,xn_hd,khuon_mat) VALUES"
                       " ('cu','2026-08-10','2026-08-10T10:00:00','IMG.HEIC','','', 'HDG', ?)", (km_cu,))
        self.c.execute("INSERT INTO photos (id,ngay,thoi_gian,ten_file,chu_thich,ocr,khuon_mat) VALUES"
                       " ('q1','2026-10-09','2026-10-09T10:00:00','IMG.HEIC','','Quyên-csd 9/10/26', ?)", (km_nay,))
        A.ghep_ngay(self.c, "2026-10-09")
        return self.c.execute("SELECT * FROM photos WHERE id='q1'").fetchone()

    def test_khuon_mat_khac_khong_goi_y(self):
        p = self.anh_mat("M1", "M2")
        self.assertIsNone(p["goi_y_hd"])
        self.assertIn("khuôn mặt khác", p["ly_do"])

    def test_khuon_mat_chung_van_goi_y(self):
        p = self.anh_mat("M1 M3", "M2 M3")
        self.assertEqual((p["goi_y_hd"], p["do_tin"]), ("HDG", "goi_y"))

    def test_khong_du_khuon_mat_van_goi_y(self):
        self.assertEqual(self.anh_mat("M1", "")["goi_y_hd"], "HDG")  # ảnh cũ không có mã người
        self.c.execute("DELETE FROM photos")
        self.c.execute("DELETE FROM visits")
        self.assertEqual(self.anh_mat("", "M2")["goi_y_hd"], "HDG")  # ảnh này không có mã người

    def test_bo_nho_nap_mot_lan_moi_ngay(self):
        self.hd("HDG", "2026-08-10", "KH01", "Nguyễn Thị Quyên", "COMBO CSD ( 10 LẦN )")
        bo = {}
        A._khop_nhan(self.c, A.doc_nhan("Quyên-csd 9/10/26", 2026)[0], "2026-10-09", bo)
        self.assertIn("2026-10-09", bo)
        self.c.execute("DELETE FROM visits")  # đã nạp: lần sau dùng bộ nhớ, không truy vấn lại
        self.assertEqual(A._khop_nhan(self.c, A.doc_nhan("Quyên-csd 9/10/26", 2026)[0], "2026-10-09", bo)[0],
                         "HDG")

    # ---- Soát lần 2 (14/10): khách phải có ảnh chắc/đã duyệt ngày khác; ảnh gói không kéo bộ dài/đợt nhiều khách
    def test_khach_chua_co_anh_xac_nhan_khong_goi_y(self):
        self.hd("HDG", "2026-08-10", "KH01", "Nguyễn Thị Quyên", "COMBO CSD ( 10 LẦN )", mau=False)
        hd, d, ly_do = self.khop("Quyên-csd 9/10/26")
        self.assertIsNone(hd)
        self.assertIn("chưa có ảnh đã xác nhận ngày khác", ly_do)

    def test_anh_goi_y_bo_qua_cung_ngay_khong_tinh_la_mau(self):
        self.hd("HDG", "2026-08-10", "KH01", "Nguyễn Thị Quyên", "COMBO CSD ( 10 LẦN )", mau=False)
        ins = ("INSERT INTO photos (id,ngay,thoi_gian,ten_file,goi_y_hd,do_tin,xn_hd,bo_qua) VALUES"
               " (?,?,?,'IMG.HEIC',?,?,?,?)")
        self.c.execute(ins, ("g1", "2026-08-10", "2026-08-10T09:00:00", "HDG", "goi_y", None, 0))  # chỉ gợi ý
        self.c.execute(ins, ("b1", "2026-08-10", "2026-08-10T09:01:00", "HDG", "chac", None, 1))  # bỏ qua
        self.c.execute(ins, ("s1", "2026-10-09", "2026-10-09T09:00:00", "HDG", "chac", "HDG", 0))  # cùng ngày chụp
        self.assertIsNone(self.khop("Quyên-csd 9/10/26")[0])
        self.c.execute(ins, ("x1", "2026-09-01", "2026-09-01T09:00:00", None, "chua_ro", "HDG", 0))  # đã duyệt
        self.assertEqual(self.khop("Quyên-csd 9/10/26")[:2], ("HDG", 50))

    def test_anh_mau_uu_tien_da_duyet(self):
        self.hd("HDG", "2026-08-10", "KH01", "Nguyễn Thị Quyên", "COMBO CSD ( 10 LẦN )")
        self.c.execute("INSERT INTO photos (id,ngay,thoi_gian,ten_file,xn_hd) VALUES"
                       " ('x1','2026-07-01','2026-07-01T09:00:00','IMG.HEIC','HDG')")
        self.assertEqual(A._anh_mau(self.c, "KH01", "2026-10-09"), ["x1", "mauHDG"])
        self.assertEqual(A._anh_mau(self.c, "KH01", "2026-08-10"), ["x1"])  # bỏ ảnh của chính ngày đang xét
        self.assertEqual(A._anh_mau(self.c, "", "2026-10-09"), [])

    def bo(self, ngay, n, nhan_o=0, cach=10, phut=0, id_="p", nhan="Quyên-csd 9/10/26"):
        for i in range(n):
            tg = f"{ngay}T10:{phut + (i * cach) // 60:02d}:{(i * cach) % 60:02d}"
            self.c.execute("INSERT INTO photos (id,ngay,thoi_gian,ten_file,chu_thich,ocr) VALUES (?,?,?,?,?,?)",
                           (f"{id_}{i}", ngay, tg, "IMG.HEIC", "", nhan if i == nhan_o else ""))

    def test_bo_dai_hon_6_tu_the_anh_goi_khong_keo(self):
        self.hd("HDG", "2026-08-10", "KH01", "Nguyễn Thị Quyên", "COMBO CSD ( 10 LẦN )")
        self.hd("HDK", "2026-10-09", "KH09", "Trần Văn Khác", "PICO", gio="15:00", mau=False)
        self.hd("HDL", "2026-10-09", "KH08", "Trần Văn Lạ", "PICO", gio="16:00", mau=False)  # ngày > 1 HĐ
        self.bo("2026-10-09", 7)
        A.ghep_ngay(self.c, "2026-10-09")
        r = self.anh_ngay("2026-10-09")
        self.assertEqual((r["p0"]["goi_y_hd"], r["p0"]["do_tin"]), ("HDG", "goi_y"))
        self.assertIn("bộ 7 tư thế", r["p0"]["ly_do"])
        self.assertEqual({r[f"p{i}"]["goi_y_hd"] for i in range(1, 7)}, {None})

    def test_bo_6_tu_the_anh_goi_van_keo_goi_y(self):
        self.hd("HDG", "2026-08-10", "KH01", "Nguyễn Thị Quyên", "COMBO CSD ( 10 LẦN )")
        self.hd("HDK", "2026-10-09", "KH09", "Trần Văn Khác", "PICO", gio="15:00", mau=False)
        self.bo("2026-10-09", 6)
        A.ghep_ngay(self.c, "2026-10-09")
        r = self.anh_ngay("2026-10-09")
        self.assertEqual({(x["goi_y_hd"], x["do_tin"]) for x in r.values()}, {("HDG", "goi_y")})

    def test_dot_hai_nhan_ten_khac_anh_goi_khong_keo(self):
        self.hd("HDG", "2026-08-10", "KH01", "Nguyễn Thị Quyên", "COMBO CSD ( 10 LẦN )")
        self.hd("HDK", "2026-10-09", "KH09", "Trần Văn Khác", "PICO", gio="15:00", mau=False)
        self.hd("HDL", "2026-10-09", "KH08", "Trần Văn Lạ", "PICO", gio="16:00", mau=False)  # ngày > 1 HĐ
        self.bo("2026-10-09", 5)
        self.bo("2026-10-09", 5, phut=5, id_="k", nhan="Mai-pico 9/10/26")  # bộ khác cùng đợt, nhãn tên khác
        A.ghep_ngay(self.c, "2026-10-09")
        r = self.anh_ngay("2026-10-09")
        self.assertEqual(r["p0"]["goi_y_hd"], "HDG")
        self.assertIn("đợt có 2 nhãn tên khác nhau", r["p0"]["ly_do"])
        self.assertEqual({r[f"p{i}"]["goi_y_hd"] for i in range(1, 5)}, {None})

    def test_dot_cung_mot_ten_hai_nhan_van_keo(self):
        # 2 nhãn cùng tên (viết lại ở tấm khác, có xưng hô) không tính là 2 tên.
        self.hd("HDG", "2026-08-10", "KH01", "Nguyễn Thị Quyên", "COMBO CSD ( 10 LẦN )")
        self.hd("HDK", "2026-10-09", "KH09", "Trần Văn Khác", "PICO", gio="15:00", mau=False)
        self.bo("2026-10-09", 5)
        self.c.execute("UPDATE photos SET ocr='C Quyên-csd 9/10/26' WHERE id='p3'")
        A.ghep_ngay(self.c, "2026-10-09")
        r = self.anh_ngay("2026-10-09")
        self.assertEqual({x["goi_y_hd"] for x in r.values()}, {"HDG"})

    def test_trang_duyet_anh_mau_so_mat(self):
        self.hd("HDG", "2026-08-10", "KH01", "Nguyễn Thị Quyên", "COMBO CSD ( 10 LẦN )")
        anh = os.path.join(tempfile.mkdtemp(), "m.jpg")
        with open(anh, "wb") as fh:
            fh.write(b"x")
        self.c.execute("UPDATE photos SET anh_xem=? WHERE id='mauHDG'", (anh,))
        self.c.execute("INSERT INTO photos (id,ngay,thoi_gian,ten_file,chu_thich,ocr) VALUES"
                       " ('q1','2026-10-09','2026-10-09T10:00:00','IMG.HEIC','','Quyên-csd 9/10/26')")
        self.c.execute("INSERT INTO photos (id,ngay,thoi_gian,ten_file,chu_thich,ocr) VALUES"
                       " ('q2','2026-10-09','2026-10-09T12:00:00','IMG.HEIC','','')")
        A.ghep_ngay(self.c, "2026-10-09")
        trang = A._trang_ngay(self.c, "2026-10-09").decode()
        self.assertIn("So mặt — ảnh đã xác nhận của KH01", trang)
        self.assertEqual(trang.count("src='/anh/mauHDG'"), 1)  # chỉ ảnh gợi ý theo gói có ô so mặt
        self.c.execute("UPDATE photos SET anh_xem=NULL WHERE id='mauHDG'")
        trang = A._trang_ngay(self.c, "2026-10-09").decode()
        self.assertIn("chưa có ảnh đã xác nhận trên máy", trang)
        self.assertNotIn("/anh/mauHDG", trang)
        self.c.execute("UPDATE photos SET xn_hd='HDG' WHERE id='q1'")  # đã duyệt -> không hiện nữa
        self.assertNotIn("So mặt", A._trang_ngay(self.c, "2026-10-09").decode())

    def test_trang_duyet_anh_mau_escape(self):
        self.hd("HDG", "2026-08-10", "K<b>1", "Nguyễn Thị Quyên", "COMBO CSD ( 10 LẦN )", mau=False)
        anh = os.path.join(tempfile.mkdtemp(), "m.jpg")
        with open(anh, "wb") as fh:
            fh.write(b"x")
        self.c.execute("INSERT INTO photos (id,ngay,thoi_gian,ten_file,xn_hd,anh_xem) VALUES"
                       " (?, '2026-08-10','2026-08-10T09:00:00','IMG.HEIC','HDG',?)", ("x'><s>", anh))
        o = A._o_anh_mau(self.c, "K<b>1", "2026-10-09", {})
        self.assertNotIn("<s>", o)
        self.assertNotIn("<b>", o)
        self.assertIn("/anh/x&#x27;&gt;&lt;s&gt;", o)

    def test_hd_lan_le_khong_ap_goi(self):
        self.hd("HDL", "2026-09-01", "KH01", "Nguyễn Thị Quyên", "TIÊM PRP PREMIUM ( LẦN LẺ )")
        self.assertIsNone(self.khop("Quyên-prp 9/10/26")[0])
        self.hd("HDC", "2026-08-01", "KH01", "Nguyễn Thị Quyên", "COMBO TIÊM PRP PREMIUM ( 4 + 1 )")
        self.assertEqual(self.khop("Quyên-prp 9/10/26")[:2], ("HDC", 50))  # gói cũ hơn vẫn được, bỏ HĐ lẻ


if __name__ == "__main__":
    unittest.main()
