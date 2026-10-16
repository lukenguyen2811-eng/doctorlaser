"""Soát 16/10 (189 ảnh chắc bị hạ oan) — DB tạm, dữ liệu bịa.

1. Tên Tây (không dấu, không họ Việt, có chữ không phải âm tiết Việt): tên gọi = chữ ĐẦU; nhãn 1 chữ khớp chữ đầu
   hoặc chữ cuối đều chắc. Tên Việt (kể cả ghi không dấu) giữ luật tên cuối.
2. Tên KiotViet bẩn: cắt tại gạch khi phần sau là ghi chú/số; tên ghép có gạch giữ nguyên.
3. Chữ đệm + mặt mạnh -> chắc; không mặt -> gợi ý 50.
4. Mặt mạnh ưu tiên hơn luật bộ chụp.
5. Luật mặt chọn HĐ trong ngày: dịch vụ nhãn cùng bộ/đợt, rồi giờ gần nhất, rồi HĐ đang gắn.

Chạy:  python3 -m unittest tests/test_tay_gach_mat_anh.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_ten_cuoi_mat_anh import A, D, Nen  # noqa: E402


# ---------------- 1. TÊN TÂY ----------------
class TenTay(Nen):
    def test_nhan_chu_dau_chac(self):  # ca thật 4612A596: 'Robert- prp' ~ 'ROBERT HAWKINS ( KH… GT )'
        self.hd("H1", D, "K1", "ROBERT HAWKINS ( KH008934 GT )", "PRP")
        self.assertEqual(self.khop("Robert- prp 10/10/26")[:2], ("H1", 85))

    def test_nhan_chu_cuoi_van_chac(self):
        self.hd("H1", D, "K1", "ROBERT HAWKINS", "PRP")
        self.assertEqual(self.khop("Hawkins-prp 10/10/26")[:2], ("H1", 85))

    def test_nhan_hai_chu_ten_tay(self):
        self.hd("H1", D, "K1", "LUKE CROSS", "CSD")
        self.assertEqual(self.khop("Luke Cross-csd 10/10/26")[:2], ("H1", 85))

    def test_ten_goi_chu_dau(self):
        self.assertEqual(A.ten_goi("ROBERT HAWKINS ( KH008934 GT )"), "Robert")
        self.assertEqual(A.ten_goi("SHARON YAP"), "Sharon")
        self.assertTrue(A._khop_ten_goi([k for _, k in A._tu_ten_goi("TANYA SHERMAN")], [], [["tanya"]]))

    def test_chu_giua_ten_tay_khong_chac(self):  # âm: chữ giữa không phải chữ đầu/cuối -> chỉ gợi ý
        self.hd("H1", D, "K1", "CEDRICK PAUL DAGDAGAN", "PRP")
        self.assertEqual(self.khop("Paul-prp 10/10/26")[:2], ("H1", 50))

    def test_ten_tay_bo_chu_mot_ky_tu_cuoi(self):  # ca thật D7AFEA48: 'David' ~ 'JMITH DAVID A'
        self.hd("H1", D, "K1", "JMITH DAVID A", "PRP")
        self.assertEqual(self.khop("David-prp 10/10/26")[:2], ("H1", 85))

    def test_ten_viet_khong_doi(self):  # âm: tên Việt có dấu giữ luật tên cuối (chữ đầu là họ)
        self.hd("H1", D, "K1", "Phạm Đỗ Thảo Vy", "CSD")
        self.assertNotEqual(self.khop("Phạm-csd 10/10/26")[1], 85)
        self.assertEqual(A.ten_goi("Phạm Đỗ Thảo Vy"), "Vy")

    def test_ten_viet_khong_dau_khong_doi(self):  # âm: tên Việt ghi không dấu không bị coi là tên Tây
        for ten in ("NGUYEN VAN AN", "ANH TUAN", "MAI HOANG", "THU TRANG"):
            self.assertFalse(A._la_ten_tay(A._tu_ten_kh(ten)), ten)
        self.hd("H1", D, "K1", "ANH TUAN", "CSD")
        self.assertNotEqual(self.khop("Anh-csd 10/10/26")[1], 85)

    def test_nhan_hop_va_mat_ten_tay(self):
        n = {"ten": "robert", "ten_goc": "robert"}
        self.assertTrue(A._ten_nhan_hop(n, "ROBERT HAWKINS"))
        self.assertTrue(A._ten_hop_mat(n, "ROBERT HAWKINS"))
        self.assertTrue(A._ten_dung_duoi(n, "ROBERT HAWKINS"))
        self.assertTrue(A._ten_dung_duoi({"ten": "hawkins", "ten_goc": "hawkins"}, "ROBERT HAWKINS"))
        self.assertFalse(A._ten_nhan_hop({"ten": "peter", "ten_goc": "peter"}, "ROBERT HAWKINS"))


# ---------------- 2. TÊN KH BẨN ----------------
class TenBan(unittest.TestCase):
    def test_cat_gach_ghi_chu(self):
        self.assertEqual(A.ten_sach("NGUYỄN THỊ THANH THÚY (KH008039 GT) -MẪU NÁM 5"), "nguyen thi thanh thuy")
        self.assertEqual(A.ten_sach("TRẦN BẢO DUY - CON C. TRÚC BS LƯƠNG"), "tran bao duy")
        self.assertEqual(A.ten_sach("LÊ VĂN AN - 0909123456"), "le van an")
        self.assertEqual(A.ten_sach("PHAN THỊ HOA - CHỊ GÁI C. LAN"), "phan thi hoa")
        self.assertEqual(A.ten_goi("TRẦN BẢO DUY - CON C. TRÚC BS LƯƠNG"), "Duy")

    def test_ten_ghep_co_gach_giu(self):  # âm: gạch trong tên thật không cắt
        self.assertEqual(A.ten_sach("NGUYỄN THỊ MAI-ANH"), "nguyen thi mai anh")
        self.assertEqual(A.ten_sach("TRẦN NGỌC - HÂN"), "tran ngoc han")
        self.assertEqual(A.ten_sach("LÊ THU - CHI"), "le thu chi")  # chữ yếu đứng một mình: giữ

    def test_ten_ban_khop_nhan(self):
        c = Nen("run")
        c.setUp()
        try:
            c.hd("H1", D, "K1", "TRẦN BẢO DUY - CON C. TRÚC BS LƯƠNG", "CSD")
            self.assertEqual(c.khop("Duy-csd 10/10/26")[:2], ("H1", 85))
            self.assertEqual(c.khop("Trần Bảo Duy-csd 10/10/26")[:2], ("H1", 85))
        finally:
            c.tearDown()


# ---------------- 3–5. LUẬT MẶT ----------------
class MatNen(Nen):
    def cum(self, ma, ten, n=6, km="P-K", hd_d=True, dv="CSD"):  # cụm mặt: n ảnh neo nhãn ở 2 ngày
        for i, ngay in enumerate(("2026-09-01", "2026-09-15")):
            self.hd(f"{ma}-{i}", ngay, ma, ten, dv)
        for i in range(n):
            ngay = "2026-09-01" if i % 2 == 0 else "2026-09-15"
            self.anh(ngay, f"10:{i:02d}:00", km=km, do_tin="chac", goi_y=f"{ma}-{i % 2}", ly_do="nhãn 'x-csd' khớp")
        if hd_d:
            self.hd(f"{ma}-D", D, ma, ten, dv, "15:00")


class ChuDemMat(MatNen):
    def test_chu_dem_mat_manh_chac(self):  # ca thật 24A56F34: 'Phương' ~ 'Lê Thị Phương Thảo' + mặt mạnh
        self.cum("K1", "Lê Thị Phương Thảo")
        a = self.anh(D, "15:10:00", "Phương-csd 10/10/26", km="P-K")
        self.assertEqual(self.ghep()[a][:2], ("K1-D", "chac"))

    def test_dao_hai_chu_mat_manh_chac(self):  # 'Tùng Anh' ~ 'Trần Anh Tùng'
        self.cum("K1", "Trần Anh Tùng")
        a = self.anh(D, "15:10:00", "Tùng Anh-csd 10/10/26", km="P-K")
        self.assertEqual(self.ghep()[a][:2], ("K1-D", "chac"))

    def test_viet_tat_mat_manh_chac(self):  # 'T.Yến' ~ 'Nguyễn Thị Yến'
        self.cum("K1", "Nguyễn Thị Yến")
        self.assertTrue(A._ten_hop_mat({"ten": "t yen", "ten_goc": "t yến"}, "Nguyễn Thị Yến"))

    def test_chu_dem_khong_mat_dv_khop_chac(self):  # CEO 16/10 lần 3: chỉ 1 khách khớp chữ đệm + dịch vụ -> chắc
        self.hd("H1", D, "K1", "Lê Thị Phương Thảo", "CSD")
        a = self.anh(D, "15:10:00", "Phương-csd 10/10/26")
        self.assertEqual(self.ghep()[a][:2], ("H1", "chac"))

    def test_chu_dem_khong_mat_gan_gio_chac(self):  # dịch vụ lệch nhưng giờ HĐ cách giờ chụp <= 30' -> chắc
        self.hd("H1", D, "K1", "Lê Thị Phương Thảo", "Laser Fractional", "15:00")
        a = self.anh(D, "15:10:00", "Phương-pico 10/10/26")
        self.assertEqual(self.ghep()[a][:2], ("H1", "chac"))

    def test_chu_dem_lech_dv_xa_gio_goi_y(self):  # âm (ca 24A56F34): dịch vụ lệch + giờ HĐ cách 2 giờ -> gợi ý
        self.hd("H1", D, "K1", "Lê Thị Phương Thảo", "Triệt lông nách", "11:55")
        a = self.anh(D, "13:53:00", "Phương-ha môi 10/10/26")
        self.assertNotEqual(self.ghep()[a][1], "chac")

    def test_chu_dem_hai_khach_khong_chac(self):  # âm: khách khác cùng ngày có tên cuối 'Phương'
        self.hd("H1", D, "K1", "Lê Thị Phương Thảo", "CSD", "15:00")
        self.hd("H2", D, "K2", "Trần Thu Phương", "Botox", "09:00")
        a = self.anh(D, "15:10:00", "Phương-csd 10/10/26")
        self.assertNotEqual(self.ghep()[a][:2], ("H1", "chac"))

    def test_mat_khac_anh_cu_khong_nang(self):  # âm (ca 24A56F34): mặt khác hẳn ảnh đã chắc của khách -> không nâng
        self.hd("H0", "2026-09-01", "K1", "Lê Thị Phương Thảo", "CSD")
        self.anh("2026-09-01", "10:00:00", km="P-CU", do_tin="chac", goi_y="H0", ly_do="nhãn 'x' khớp")
        self.hd("H1", D, "K1", "Lê Thị Phương Thảo", "CSD | Tiêm filler")
        a = self.anh(D, "15:10:00", "Phương-ha môi 10/10/26", km="P-LA")
        self.assertNotEqual(self.ghep()[a][1], "chac")

    def test_ho_khong_nang(self):  # âm (ca DBBAAD78): nhãn = HỌ ('Trân' ~ 'Trần Hà Anh Thư') -> không chắc
        self.hd("H1", D, "K1", "Trần Hà Anh Thư", "Pico", "15:05")
        a = self.anh(D, "15:10:00", "Trần-pico 10/10/26")
        self.assertNotEqual(self.ghep()[a][1], "chac")

    def test_dao_thu_tu_gan_gio_chac(self):  # ca E243DBDB: 'Trường Sơn' ~ 'Phạm Lý Sơn Trường' + giờ khớp
        self.hd("H1", D, "K1", "Phạm Lý Sơn Trường", "Điện di C sau sẹo", "16:45")
        a = self.anh(D, "16:55:00", "Trường Sơn-csd 10/10/26")
        self.assertEqual(self.ghep()[a][:2], ("H1", "chac"))

    def test_chu_dem_mat_yeu_lech_khong_chac(self):  # âm: cụm chưa mạnh, dịch vụ lệch, giờ xa
        self.cum("K1", "Lê Thị Phương Thảo", n=3)
        a = self.anh(D, "17:50:00", "Phương-botox 10/10/26", km="P-K")
        self.assertNotEqual(self.ghep()[a][1], "chac")


class MatHonBo(MatNen):
    def bo(self, km_cuoi):  # bộ 5 tấm: tấm đầu nhãn khách X, tấm cuối mặt
        self.hd("HX", D, "KX", "Nguyễn Thị Lan", "CSD", "15:00")
        ids = [self.anh(D, "15:20:00", "Lan-csd 10/10/26")]
        for i in range(1, 5):
            ids.append(self.anh(D, f"15:20:{i * 10:02d}", km=km_cuoi if i == 4 else ""))
        return ids

    def test_mat_manh_khong_bi_bo_gan_khach_khac(self):  # ca thật 01AA0FCF
        self.cum("K1", "Hồ Văn Hùng")
        ids = self.bo("P-K")
        kq = self.ghep()
        self.assertEqual(kq[ids[0]][:2], ("HX", "chac"))
        self.assertEqual(kq[ids[4]][:2], ("K1-D", "chac"))
        self.assertIn("khuôn mặt thuộc khách K1", kq[ids[4]][2])
        self.assertEqual(kq[ids[2]][:2], ("HX", "chac"))  # các tấm khác của bộ giữ theo nhãn

    def test_mat_yeu_giu_bo(self):  # âm: cụm chưa mạnh -> luật bộ như cũ
        self.cum("K1", "Hồ Văn Hùng", n=3)
        ids = self.bo("P-K")
        self.assertEqual(self.ghep()[ids[4]][:2], ("HX", "chac"))

    def test_mat_khong_hd_ngay_do_khong_doi_khach(self):  # âm: K không có HĐ ngày chụp -> không gán K
        self.cum("K1", "Hồ Văn Hùng", hd_d=False)
        ids = self.bo("P-K")
        self.assertNotEqual(self.ghep()[ids[4]][1:2], ("K1-D",))
        self.assertNotEqual(self.ghep()[ids[4]][0], "K1-D")


class ChonHdMat(MatNen):
    def ca(self, nhan_dot: bool):
        self.cum("K1", "Phan Thị Lan")
        self.hd("K1-a", D, "K1", "Phan Thị Lan", "Tiêm Botox", "17:20")
        self.hd("K1-b", D, "K1", "Phan Thị Lan", "CSD", "17:40")
        if nhan_dot:  # nhãn cùng đợt (khác bộ) ghi dịch vụ, tên không khớp ai
            self.anh(D, "17:08:00", "Hoa-csd 10/10/26")
        return self.anh(D, "17:15:00", km="P-K")

    def test_dv_nhan_dot_thang_gio(self):  # ca thật 87EEA18F
        a = self.ca(True)
        self.assertEqual(self.ghep()[a][:2], ("K1-b", "chac"))

    def test_khong_nhan_chon_gio_gan_nhat(self):  # đối chứng: không nhãn -> HĐ gần giờ chụp nhất
        a = self.ca(False)
        self.assertEqual(self.ghep()[a][:2], ("K1-a", "chac"))

    def test_tranh_hd_thu_tien(self):  # HĐ đặt cọc gần giờ hơn nhưng chỉ thu tiền -> lấy HĐ dịch vụ
        self.cum("K1", "Phan Thị Lan")
        self.hd("K1-c", D, "K1", "Phan Thị Lan", "ĐẶT CỌC", "17:16")
        self.hd("K1-b", D, "K1", "Phan Thị Lan", "CSD", "17:40")
        a = self.anh(D, "17:15:00", km="P-K")
        self.assertEqual(self.ghep()[a][:2], ("K1-b", "chac"))
        self.assertTrue(A._chi_thu_tien("THANH TOÁN CÔNG NỢ CSD"))
        self.assertFalse(A._chi_thu_tien("THANH TOÁN CÔNG NỢ VEIN | TRẺ HOÁ DA PICOLIGHT"))

    def test_bo_nhan_rac_cung_hd_voi_mat(self):  # ca thật CU-HD026768: tấm có chữ OCR rác + 4 tấm mặt, 2 HĐ cùng KH
        self.cum("K1", "Phan Thị Lan")
        self.hd("K1-a", D, "K1", "Phan Thị Lan", "Tiêm HA", "10:00")
        self.hd("K1-b", D, "K1", "Phan Thị Lan", "CSD", "10:24")
        ids = [self.anh(D, f"10:21:{i * 8:02d}", km="P-K") for i in range(4)]
        kq = self.ghep()
        self.assertEqual({kq[i][:2] for i in ids}, {("K1-b", "chac")})

    def test_bo_chu_rac_hd_khac_cung_khach_van_lan(self):  # ca A6FCB23F: tấm OCR rác gợi ý HĐ khác của CÙNG khách
        self.cum("K1", "Phan Thị Lan")
        self.hd("K1-a", D, "K1", "Phan Thị Lan", "Thanh toán combo | Tiêm PRP", "13:20")
        self.hd("K1-b", D, "K1", "Phan Thị Lan", "Dặm vein mặt", "13:22")
        ids = [self.anh(D, "13:23:39", "xoá-vein", km="P-K")] + \
            [self.anh(D, f"13:23:{50 + i * 3}", km="P-K") for i in range(3)]
        kq = self.ghep()
        self.assertEqual({kq[i][1] for i in ids[1:]}, {"chac"})

    def test_ma_trong_ten_nhan_cung_bo(self):  # ca 57707D17: nhãn bộ 'Khắc Bách XVM' (mã nằm trong phần tên)
        self.cum("K1", "Châu Khắc Bách")
        self.hd("K1-a", D, "K1", "Châu Khắc Bách", "Tiêm mesotherapy | Xóa vein mũi", "17:22")
        self.hd("K1-b", D, "K1", "Châu Khắc Bách", "Peel da mụn", "17:12")
        self.anh(D, "17:11:15", "Khắc Bách XVM 10/10/26", km="P-K")
        a = self.anh(D, "17:11:24", km="P-K")
        self.assertEqual(self.ghep()[a][:2], ("K1-a", "chac"))

    def test_bo_hd_khach_khac_van_chan(self):  # âm: tấm trong bộ khớp chắc HĐ của khách KHÁC -> không lan
        self.cum("K1", "Phan Thị Lan")
        self.hd("K1-a", D, "K1", "Phan Thị Lan", "CSD", "13:20")
        self.hd("HX", D, "KX", "Nguyễn Thị Hoa", "CSD", "13:20")
        ids = [self.anh(D, "13:23:39", "Hoa-csd 10/10/26")] + [self.anh(D, f"13:23:{50 + i * 3}", km="P-K")
                                                              for i in range(3)]
        kq = self.ghep()
        self.assertEqual(kq[ids[0]][:2], ("HX", "chac"))
        self.assertNotIn("với ảnh nhận theo khuôn mặt", kq[ids[0]][2])

    def test_ham_chon_hd(self):
        import datetime as dt
        vs = [{"code": "x1", "ngay": D, "gio": "14:39", "dich_vu": "Tiêm filler"},
              {"code": "x2", "ngay": D, "gio": "17:31", "dich_vu": "CSD"},
              {"code": "x3", "ngay": "2026-10-09", "gio": "17:00", "dich_vu": "CSD"}]
        r = {"hd": "x1", "gio": dt.datetime.fromisoformat(f"{D}T17:15:00"), "goc": 0}
        self.assertEqual(A._chon_hd_mat(vs, [D, "2026-10-09"], r, ["csd"])["code"], "x2")
        self.assertEqual(A._chon_hd_mat(vs, [D, "2026-10-09"], r, [])["code"], "x2")  # giờ gần hơn HĐ đang gắn
        r["hd"] = "x3"  # HĐ đang gắn ở ngày khác (buổi theo nhãn) -> giữ ngày đó (như cũ)
        self.assertEqual(A._chon_hd_mat(vs, [D, "2026-10-09"], r, ["csd"])["code"], "x3")



class ChonHdDv(unittest.TestCase):  # CEO 16/10 lần 3: dịch vụ nhãn (sát nhất) -> dịch vụ thật -> giờ -> HĐ đang gắn
    import datetime as _dt
    R = {"hd": None, "gio": _dt.datetime.fromisoformat(f"{D}T12:00:00"), "goc": 1}

    def chon(self, vs, ma=(), quanh=(), chu=""):
        vs = [{"code": c, "ngay": D, "gio": g, "dich_vu": dv} for c, g, dv in vs]
        return A._chon_hd_mat(vs, [D], dict(self.R), list(ma), list(quanh), chu)["code"]

    def test_co2_fractional_sat_hon_mun_thit(self):  # ca D14C5AD7
        self.assertEqual(self.chon([("a", "11:51", "LASER FRACTIONAL | CSD MỤN"),
                                    ("b", "11:58", "LASER MỤN THỊT VÙNG BỤNG ( LẦN LẺ )")], quanh=["co2"]), "a")

    def test_sau_filler_khong_phai_tan_filler(self):  # ca 28355FAE
        vs = [("a", "11:52", "TIÊM FILLER LÀM ĐẦY HÀN ( 1CC )"), ("b", "11:59", "TIÊM TAN FILLER LÀM ĐẦY")]
        self.assertEqual(self.chon(vs, quanh=["filler"], chu="sau filler"), "a")
        self.assertEqual(self.chon(vs, ma=["filler"], chu="tan filler"), "b")  # nhãn ghi 'tan filler' -> HĐ tan

    def test_pico_sat_hon_chu_nam(self):  # ca C27CEF61
        self.assertEqual(self.chon([("a", "08:21", "Laser Picolight toàn mặt trị nám"),
                                    ("b", "11:50", "MELASMA-REVSKIN | TIÊM MESO SKIN BOOSTER (giảm nám)")],
                                   quanh=["pico"]), "a")

    def test_hd_thuoc_xep_sau(self):  # ca 4ACBA65E: không nhãn, HĐ chỉ bán thuốc gần giờ hơn
        self.assertEqual(self.chon([("a", "11:25", "TIÊM MESOTHERAPY | XÓA VEIN MẶT"),
                                    ("b", "11:58", "THUỐC TRỊ THÂM MEDICOS ARBUTIN")]), "a")

    def test_ma_rac_dung_nhan_quanh(self):  # ca AE3CDAC3: mã OCR rác của chính ảnh -> dùng nhãn cùng bộ/đợt
        self.assertEqual(self.chon([("a", "09:22", "TIÊM FILLER"), ("b", "11:50", "TIÊM PRP PREMIUM")],
                                   ma=["limeorange"], quanh=["filler"]), "a")

    def test_chu_ma_trong_ten_nhan(self):  # ca EB9573DF: 'Khắc Bách xvm' -> 'xvm' ~ 'XÓA VEIN MŨI'
        self.assertEqual(self.chon([("a", "10:22", "TIÊM MESOTHERAPY | XÓA VEIN MŨI ( LẦN LẺ )"),
                                    ("b", "12:01", "PEEL DA MỤN (LẦN LẺ)")], ma=["xvm"], quanh=["csd"]), "a")

    def test_dv_ngang_thi_gio(self):  # ca tốt D2B814B2/5D32A7BC: cùng là dịch vụ, không nhãn -> giờ gần nhất
        self.assertEqual(self.chon([("a", "09:11", "TIÊM MESO SKIN BOOSTER | TIÊM FILLER"),
                                    ("b", "12:01", "TIÊM FILLER THẨM MỸ")]), "b")

    def test_dat_coc_cong_no_xep_sau(self):  # ca tốt D87AB34D, AEBEB0C6
        self.assertEqual(self.chon([("a", "11:59", "ĐẶT CỌC"), ("b", "11:40", "COMBO PICOLIGHT 5 LẦN")]), "b")
        self.assertEqual(self.chon([("a", "11:59", "THANH TOÁN CÔNG NỢ CSD"), ("b", "11:40", "ĐIỆN DI C SAU SẸO")]), "b")


if __name__ == "__main__":
    unittest.main()
