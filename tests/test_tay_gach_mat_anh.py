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

    def test_chu_dem_khong_mat_gan_gio_chac(self):  # nhãn không có mã nhận ra được + giờ HĐ <= 30' -> chắc
        self.hd("H1", D, "K1", "Lê Thị Phương Thảo", "Laser Fractional", "15:00")
        a = self.anh(D, "15:10:00", "Phương-laser 10/10/26")
        self.assertEqual(self.ghep()[a][:2], ("H1", "chac"))

    def test_ma_dv_lech_khong_dung_gio(self):  # âm (ca 9AF8F874): 'pico' nhận ra được mà HĐ chỉ filler -> không nâng
        self.hd("H1", D, "K1", "Phan Thanh Tình", "Tiêm filler làm đầy hàn", "15:18")
        a = self.anh(D, "15:02:00", "Thanh-pico 10/10/26")
        self.assertNotEqual(self.ghep()[a][1], "chac")

    def test_ma_dv_lech_o_nhan_cung_bo(self):  # âm: nhãn cùng bộ ghi 'pico' lệch HĐ -> ảnh nhãn không mã cũng không nâng
        self.hd("H1", D, "K1", "Phan Thanh Tình", "Tiêm filler làm đầy hàn", "15:18")
        self.anh(D, "15:01:50", "Thanh-pico 10/10/26")
        a = self.anh(D, "15:02:00", "Thanh 10/10/26")
        self.assertNotEqual(self.ghep()[a][1], "chac")

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

    def test_bo_ngan_nhan_khach_khac_thang_mat(self):  # CEO 16/10 lần 4 (ca 195AA4FA): nhãn trong bộ ngắn thắng mặt
        self.cum("K1", "Hồ Văn Hùng")
        ids = self.bo("P-K")
        self.c.execute("UPDATE photos SET khuon_mat='P-LA' WHERE id=?", (ids[0],))  # ảnh nhãn là người khác
        kq = self.ghep()
        self.assertEqual(kq[ids[0]][:2], ("HX", "chac"))
        self.assertNotEqual(kq[ids[4]][:2], ("K1-D", "chac"))
        self.assertIn("cảnh báo: khuôn mặt thuộc khách khác", kq[ids[4]][2])  # giữ cảnh báo như c8
        self.assertEqual(kq[ids[2]][:2], ("HX", "chac"))

    def test_hai_anh_mat_k_mat_thang(self):  # ca BDC6E6FD: >= 2 ảnh trong bộ mang mặt K -> mặt thắng nhãn cùng bộ
        self.cum("K1", "Hồ Văn Hùng")
        ids = self.bo("P-K")
        self.c.execute("UPDATE photos SET khuon_mat='P-LA' WHERE id=?", (ids[0],))
        self.c.execute("UPDATE photos SET khuon_mat='P-K' WHERE id=?", (ids[3],))
        self.assertEqual(self.ghep()[ids[4]][:2], ("K1-D", "chac"))

    def test_mot_anh_lac_mat_giua_chuoi_nhan_thang(self):  # ca D96ACC42: 1 tấm mặt K giữa chuỗi mặt khách nhãn
        self.cum("K1", "Hồ Văn Hùng")
        ids = self.bo("P-LA")
        for i in (0, 1, 3):
            self.c.execute("UPDATE photos SET khuon_mat='P-LA' WHERE id=?", (ids[i],))
        self.c.execute("UPDATE photos SET khuon_mat='P-K' WHERE id=?", (ids[2],))
        self.assertNotEqual(self.ghep()[ids[2]][:2], ("K1-D", "chac"))

    def test_nhan_chinh_anh_hop_k_mat_thang(self):  # ca 645490B4: nhãn trên chính ảnh hợp K -> nhãn bộ không chặn
        self.cum("K1", "Hồ Văn Hùng")
        ids = self.bo("")
        self.c.execute("UPDATE photos SET khuon_mat='P-LA' WHERE id=?", (ids[0],))
        self.c.execute("UPDATE visits SET gio='11:00' WHERE code='K1-D'")
        self.c.execute("UPDATE photos SET khuon_mat='P-K', ocr='Hùng-csd 10/10/26' WHERE id=?", (ids[4],))
        self.assertEqual(self.ghep()[ids[4]][:2], ("K1-D", "chac"))

    def test_anh_nhan_mang_mat_k_thi_mat_thang(self):  # ca 58D8022E: ảnh nhãn có mặt của K (ghi nhầm tên) -> mặt thắng
        self.cum("K1", "Hồ Văn Hùng")
        ids = self.bo("P-K")
        self.c.execute("UPDATE photos SET khuon_mat='P-K' WHERE id=?", (ids[0],))
        self.assertEqual(self.ghep()[ids[4]][:2], ("K1-D", "chac"))

    def test_anh_nhan_khong_mat_thi_mat_thang(self):  # ca 03514DD8: ảnh nhãn không có mặt -> mặt thắng
        self.cum("K1", "Hồ Văn Hùng")
        ids = self.bo("P-K")
        self.assertEqual(self.ghep()[ids[4]][:2], ("K1-D", "chac"))

    def test_bo_dai_mat_manh_van_thang(self):  # ca 01AA0FCF: bộ dài (> 7 tư thế, tách bộ) -> mặt mạnh vẫn nhận
        self.cum("K1", "Hồ Văn Hùng")
        self.hd("HX", D, "KX", "Nguyễn Thị Lan", "CSD", "15:00")
        ids = [self.anh(D, "15:20:00", "Lan-csd 10/10/26")]
        ids += [self.anh(D, f"15:20:{i * 6:02d}", km="P-K" if i == 9 else "") for i in range(1, 10)]
        kq = self.ghep()
        self.assertEqual(kq[ids[9]][:2], ("K1-D", "chac"))

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

    def test_pico_picolight_hon_dom_nau(self):  # ca 040983BF: 'pico' ~ 'Picolight' (tên mã) hơn 'đốm nâu' (chỉ định)
        self.assertEqual(self.chon([("a", "11:59", "LASER ĐỐM NÂU"), ("b", "11:30", "TRẺ HOÁ DA PICOLIGHT")],
                                   quanh=["pico"]), "b")

    def test_co2_ngang_fractional_thi_gio(self):  # ca E514D8DB: 'co2' ~ 'fractional' ngang 'CO2' -> giờ gần hơn
        self.assertEqual(self.chon([("a", "11:50", "LASER FRACTIONAL | TIÊM PRP"),
                                    ("b", "15:01", "LASER CO2 MÀI VIỀN SẸO")], quanh=["co2"]), "a")

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



class NhanQuanHe(Nen):  # CEO 16/10 lần 4 (ca 7C1078AF): 'Con Chị Châu' = người nhà, không phải khách Châu
    def test_doc_quan_he(self):
        n = A.doc_nhan("Con Chị Chậu CSĐ 11/9/23", 2023)[0]
        self.assertEqual(n.get("quan_he"), "con")
        n = A.doc_nhan("Chồng chị Dung- csd 27/2/2023", 2023)[0]
        self.assertEqual((n.get("quan_he"), n["ten"]), ("chong", "chi dung"))
        self.assertIsNone(A.doc_nhan("Em Lan-csd 1/1/26", 2026)[0].get("quan_he"))  # 'Em Lan' là xưng hô
        # âm (đo 16/10): 'Võ'/'Châu' là họ/tên, không phải 'vợ'/'cháu'
        self.assertIsNone(A.doc_nhan("Võ An Dân- tiêm 8/10/22", 2022)[0].get("quan_he"))
        self.assertIsNone(A.doc_nhan("Châu Linh- csd 4/7/24", 2024)[0].get("quan_he"))
        self.assertIsNone(A.doc_nhan("Ba Lan- csd 4/7/24", 2024)[0].get("quan_he"))
        self.assertEqual(A.doc_nhan("Vợ anh Hùng- csd 4/7/24", 2024)[0].get("quan_he"), "vo")
        self.assertEqual(A.doc_nhan("Vo chi Lan- csd 4/7/24", 2024)[0].get("quan_he"), "vo")
        self.assertIsNone(A.doc_nhan("Bạn. Báo -CSD 25/03/2023", 2023)[0].get("quan_he"))  # thiếu xưng hô
        self.assertEqual(A.doc_nhan("Bạn chị Hằng CSD 25/5/23", 2023)[0].get("quan_he"), "ban")
        self.assertEqual(A.doc_nhan("Em chị Lan-csd 1/1/26", 2026)[0].get("quan_he"), "em")

    def test_nhan_quan_he_khong_khop_khach(self):
        self.hd("H1", D, "K1", "Nguyên Châu (KH3710 GT)", "CSD Lightcare IPL", "14:54")
        self.assertIsNone(self.khop("Con Chị Châu- csd 10/10/26")[0])
        self.assertEqual(self.khop("Chị Châu- csd 10/10/26")[:2], ("H1", 85))

    def test_bo_co_nhan_quan_he_khong_lan_chac(self):  # bộ: nhãn người nhà + ảnh sau đó không lên chắc khách chính
        self.hd("H1", D, "K1", "Nguyên Châu", "CSD", "14:54")
        ids = [self.anh(D, "14:53:43", "Con Chị Châu CSD 10/10/26"), self.anh(D, "14:53:46"), self.anh(D, "14:53:53"),
               self.anh(D, "14:54:20", "Chị Châu- csd 10/10/26"), self.anh(D, "14:54:30")]
        kq = self.ghep()
        self.assertNotIn(kq[ids[1]][:2], [("H1", "chac")])
        self.assertNotIn(kq[ids[2]][:2], [("H1", "chac")])
        self.assertEqual(kq[ids[3]][:2], ("H1", "chac"))

    def test_ho_mot_chu_mat_manh_dv_khop_thang(self):  # ca 846FE437: 'Chị Hà' + mặt K + HĐ K CSD; khách 'Lê Hà' lệch dv
        for i, ngay in enumerate(("2026-09-01", "2026-09-15")):
            self.hd(f"K1-{i}", ngay, "K1", "Hà Kim Hạnh", "CSD")
        for i in range(6):
            self.anh("2026-09-01" if i % 2 == 0 else "2026-09-15", f"10:{i:02d}:00", km="P-K", do_tin="chac",
                     goi_y=f"K1-{i % 2}", ly_do="nhãn 'x-csd' khớp")
        self.hd("K1-D", D, "K1", "Hà Kim Hạnh", "CSD IPL ( LẦN LẺ )", "10:55")
        self.hd("HX", D, "KX", "Lê Hà", "Thanh toán công nợ vein | Trị thâm bikini", "12:59")
        a = self.anh(D, "09:44:05", "Chị Hà CSD 10/10/26", km="P-K")
        self.assertEqual(self.ghep()[a][:2], ("K1-D", "chac"))

    def test_ho_mot_chu_khach_khac_cung_dv_van_chan(self):  # âm: khách 'Lê Hà' HĐ cũng CSD -> không chắc K
        for i, ngay in enumerate(("2026-09-01", "2026-09-15")):
            self.hd(f"K1-{i}", ngay, "K1", "Hà Kim Hạnh", "CSD")
        for i in range(6):
            self.anh("2026-09-01" if i % 2 == 0 else "2026-09-15", f"10:{i:02d}:00", km="P-K", do_tin="chac",
                     goi_y=f"K1-{i % 2}", ly_do="nhãn 'x-csd' khớp")
        self.hd("K1-D", D, "K1", "Hà Kim Hạnh", "CSD IPL", "10:55")
        self.hd("HX", D, "KX", "Lê Hà", "CSD mụn", "12:59")
        a = self.anh(D, "09:44:05", "Chị Hà CSD 10/10/26", km="P-K")
        self.assertNotEqual(self.ghep()[a][:2], ("K1-D", "chac"))

    def test_ho_mot_chu_khong_khop_ngay_ke_mua_sp(self):  # ca 846FE437: 'Chị Hà' là HỌ; HĐ ngày kế chỉ mua sản phẩm
        self.hd("H0", "2026-10-09", "K0", "Hà Thanh Thắng", "Thuốc acne cream | Sữa rửa mặt deep cleanser", "18:29")
        self.hd("H1", D, "K1", "Hà Kim Hạnh", "CSD IPL", "10:55")
        hd, d, _ = self.khop("Chị Hà- csd 10/10/26")
        self.assertNotEqual(hd, "H0")
        self.assertLess(d, 80)


class BoXenKe(Nen):  # ca 849E9318: bộ dài có ảnh nhãn khách khác (chỉ gợi ý) chụp xen kẽ -> phần tách không lên chắc
    def test_mat_khach_khac_xen_ke_chan(self):  # ca 849E9318: trong phần có 2 tấm mặt cụm mạnh khách khác xen giữa
        for i, ngay in enumerate(("2026-09-01", "2026-09-15")):
            self.hd(f"KB-{i}", ngay, "KB", "Lê Thị Thanh Bình", "Pico")
        for i in range(6):
            self.anh("2026-09-01" if i % 2 == 0 else "2026-09-15", f"10:{i:02d}:00", km="P-B", do_tin="chac",
                     goi_y=f"KB-{i % 2}", ly_do="nhãn 'x' khớp")
        self.hd("H1", D, "K1", "Nguyễn Hoàng Kim", "Tiêm sẹo lồi", "10:04")
        self.hd("KB-D", D, "KB", "Lê Thị Thanh Bình", "Pico", "13:37")
        self.hd("H2", D, "K2", "Trần Thị Quỳnh Hoa Mai", "CSD", "10:30")
        ids = [self.anh(D, "10:07:00", "Quỳnh Hoa- revivio 10/10/26")]
        ids += [self.anh(D, f"10:07:{5 + i * 5:02d}") for i in range(4)]
        ids.append(self.anh(D, "10:07:55", "Hoàng Kim- Tiêm sẹo lồi 10/10/26"))
        ids += [self.anh(D, f"10:07:{57 + i}", km="P-B" if i == 1 else "") for i in range(3)]
        ids += [self.anh(D, "10:08:01", km="P-B")]
        kq = self.ghep()
        self.assertNotEqual(kq[ids[6]][:2], ("H1", "chac"))

    def test_nhan_khach_khac_trong_phan_chan(self):  # nhãn khách khác (chỉ gợi ý) nằm TRONG phần -> không chắc
        self.hd("H1", D, "K1", "Nguyễn Hoàng Kim", "Tiêm sẹo lồi", "10:04")
        self.hd("H2", D, "K2", "Trần Thị Quỳnh Hoa Mai", "CSD", "10:30")
        ids = [self.anh(D, "10:07:00", "Zxq- abc 10/10/26")]
        ids += [self.anh(D, f"10:07:{5 + i * 5:02d}") for i in range(4)]
        ids.append(self.anh(D, "10:07:55", "Hoàng Kim- Tiêm sẹo lồi 10/10/26"))
        ids.append(self.anh(D, "10:07:57"))
        ids.append(self.anh(D, "10:07:58", "Quỳnh Hoa- revivio 10/10/26"))
        ids += [self.anh(D, f"10:08:0{i}") for i in range(2)]
        kq = self.ghep()
        self.assertNotEqual(kq[ids[6]][:2], ("H1", "chac"))

    def test_nhan_khach_khac_cach_quang_nghi_dai_khong_chan(self):  # âm: nhãn khách khác ở phần kia, nghỉ >= 30s
        self.hd("H1", D, "K1", "Nguyễn Hoàng Kim", "Tiêm sẹo lồi", "10:04")
        self.hd("H2", D, "K2", "Trần Thị Quỳnh Hoa Mai", "CSD", "10:30")  # nhãn khách khác chỉ gợi ý
        ids = [self.anh(D, "10:07:00", "Quỳnh Hoa- revivio 10/10/26")]
        ids += [self.anh(D, f"10:07:{5 + i * 5:02d}") for i in range(4)]
        ids.append(self.anh(D, "10:07:55", "Hoàng Kim- Tiêm sẹo lồi 10/10/26"))
        ids += [self.anh(D, f"10:07:{57 + i}") for i in range(2)] + [self.anh(D, f"10:08:0{i}") for i in range(2)]
        kq = self.ghep()
        self.assertEqual({kq[i][:2] for i in ids[6:]}, {("H1", "chac")})

    def test_nhan_chua_khop_khong_chan(self):  # âm: ảnh nhãn KHÔNG khớp ai (chữ rác) không chặn phần có nhãn chắc
        self.hd("H1", D, "K1", "Nguyễn Hoàng Kim", "Tiêm sẹo lồi", "10:04")
        ids = [self.anh(D, "10:07:52", "Zxq- abc 10/10/26")]
        ids += [self.anh(D, f"10:07:{54 + i}") for i in range(3)]
        ids.append(self.anh(D, "10:08:40", "Hoàng Kim- Tiêm sẹo lồi 10/10/26"))
        ids += [self.anh(D, f"10:08:{42 + i * 3}") for i in range(4)]
        kq = self.ghep()
        self.assertEqual({kq[i][:2] for i in ids[5:]}, {("H1", "chac")})


class BoNhanLechDv(Nen):  # ca C5A407E4: bộ 10 ảnh, nhãn đủ họ tên (năm ghi 2029) + nhãn 'Thanh Ngọc Prp' lệch dịch vụ
    def test_bo_dai_phan_dau_chac_phan_sau_khong(self):  # phần đầu sau nhãn đủ họ tên -> chắc; phần sau nhãn khác -> không
        self.hd("H1", D, "K1", "Chung Thanh Ngọc Liên", "Trẻ hoá da picolight", "10:38")
        ids = [self.anh(D, "12:16:28", "Thanh Ngọc Liên- pico 10/10/29")]
        ids += [self.anh(D, f"12:16:{30 + i * 6}") for i in range(1, 5)]
        ids.append(self.anh(D, "12:18:03", "Thanh Ngọc- Prp 10/10/26"))
        ids += [self.anh(D, f"12:18:{5 + i * 6:02d}") for i in range(1, 5)]
        kq = self.ghep()
        self.assertEqual({kq[i][:2] for i in ids[:5]}, {("H1", "chac")})
        self.assertNotIn(("H1", "chac"), {kq[i][:2] for i in ids[6:]})

    def test_bo_hai_nhan_khac_khach_van_tach(self):  # âm: nhãn thứ 2 của khách KHÁC -> vẫn tách/gợi ý
        self.hd("H1", D, "K1", "Chung Thanh Ngọc Liên", "Trẻ hoá da picolight", "10:38")
        self.hd("H2", D, "K2", "Trần Thị Mai", "PRP", "12:00")
        ids = [self.anh(D, "12:16:28", "Thanh Ngọc Liên- pico 10/10/26")]
        ids += [self.anh(D, f"12:16:{30 + i * 6}") for i in range(1, 5)]
        ids.append(self.anh(D, "12:17:20", "Mai- Prp 10/10/26"))
        ids += [self.anh(D, f"12:17:{25 + i * 6}") for i in range(1, 5)]
        kq = self.ghep()
        self.assertNotIn(("H1", "chac"), {kq[i][:2] for i in ids[6:]})


class ThuBac(Nen):  # CEO 16/10 lần 5: nhãn trên chính ảnh khớp tên + dịch vụ thắng mọi luật sau
    def test_khoa_nhan_thang_canh_bao_mat(self):
        for i, ngay in enumerate(("2026-09-01", "2026-09-15")):
            self.hd(f"KX-{i}", ngay, "KX", "Lê Thị Hoa", "Botox")
        for i in range(6):
            self.anh("2026-09-01" if i % 2 == 0 else "2026-09-15", f"10:{i:02d}:00", km="P-X", do_tin="chac",
                     goi_y=f"KX-{i % 2}", ly_do="nhãn 'x' khớp")
        self.hd("H1", D, "K1", "Trần Thị Lan", "CSD", "15:00")
        a = self.anh(D, "15:10:00", "Lan-csd 10/10/26", km="P-X")  # mặt giống khách khác (cụm mạnh)
        k = self.ghep()[a]
        self.assertEqual(k[:2], ("H1", "chac"))

    def test_ham_khoa(self):
        kq = {"a": {"khoa_nhan": ("H1", 85, "nhãn"), "hd": "H2", "do_tin": "goi_y", "xn": None, "diem": 40, "ly_do": ""},
              "b": {"khoa_nhan": ("H1", 85, "nhãn"), "hd": "H2", "do_tin": "goi_y", "xn": "H2", "diem": 40, "ly_do": ""},
              "c": {"hd": "H2", "do_tin": "goi_y", "xn": None, "diem": 40, "ly_do": ""}}
        A._khoa_nhan_tren_anh(kq)
        self.assertEqual((kq["a"]["hd"], kq["a"]["do_tin"]), ("H1", "chac"))
        self.assertEqual(kq["b"]["hd"], "H2")  # đã duyệt: không đụng
        self.assertEqual(kq["c"]["hd"], "H2")  # không có nhãn bậc 1: không đụng


class NhanKhongGachMa(Nen):  # CEO 16/10 lần 5: nhãn không gạch có mã dịch vụ
    def test_ma_sau_ngay(self):
        n = A.doc_nhan("Trần Thái Triều Châu 20/7/2022 prp mặt", 2022)[0]
        self.assertEqual((n["ten"], n["ma_dv"], n["gach"]), ("thai trieu chau", "prp", True))

    def test_ten_ma_nhieu_chu(self):  # ca CE200A6D
        n = A.doc_nhan("Phan mỹ tiên Csd mụn+ peel 9-10-2023", 2023)[0]
        self.assertEqual((n["ten"], n["ma_dv"], n["gach"]), ("phan my tien", "csd", True))

    def test_dai_khong_ma_nhu_cu(self):  # âm: > 3 chữ không mã -> chỉ 3 chữ cuối như cũ
        n = A.doc_nhan("Ghi chu cho chi Lan Anh Thu 9-10-2023", 2023)[0]
        self.assertEqual(n["ten"], "lan anh thu")

    def test_minh_ly_pico_chac(self):  # ca 5339B869
        self.hd("H1", D, "K1", "Võ Lê Minh Lý", "Trẻ hoá da picolight | CSD mụn", "10:05")
        self.assertEqual(self.khop("Minh Lý Pico 10/10/2026")[:2], ("H1", 85))

    def test_khong_ma_van_chi_goi_y(self):  # âm: nhãn không gạch không mã -> như cũ (chưa đủ họ tên chỉ gợi ý)
        self.hd("H1", D, "K1", "Võ Lê Minh Lý", "Trẻ hoá da picolight", "10:05")
        self.assertEqual(self.khop("Minh Lý 10/10/2026")[1], 50)

    def test_dong_nghia_ho_loi(self):  # ca 2B7A8D9D
        self.hd("H1", D, "K1", "Phan Thị Mỹ Trí", "Dặm botox xoá nhăn", "11:05")
        self.assertEqual(self.khop("Chị Trí - Cười hở lợi 10/10/26")[:2], ("H1", 85))

    def test_bu_kim_xep_sau(self):  # ca 7CA6F7F8
        self.assertFalse(A._hd_that("BÙ KIM RF ( HỖ TRỢ KHI LÀM VỚI PRP )"))
        self.assertTrue(A._hd_that("CSD MỤN"))


class SietVong6(Nen):  # CEO 16/10 lần 6: chỉ siết
    def test_cat_bo_nghi_ngan_chi_goi_y(self):  # ca ADA0268E: 2 nhãn khác khách, chỗ cắt nghỉ 8s -> phần tách gợi ý
        self.hd("H1", D, "K1", "Bùi Nguyễn Nhất Anh", "CSD", "16:00")
        self.hd("H2", D, "K2", "Mai Ngọc Bích", "Laser Revivio", "16:33")
        ids = [self.anh(D, "16:18:52", "Nhất Anh- csd 10/10/26"), self.anh(D, "16:18:56"),
               self.anh(D, "16:19:04"), self.anh(D, "16:19:07"), self.anh(D, "16:19:09", "Ngọc Bích-Revivio 10/10/26")]
        ids += [self.anh(D, f"16:19:{15 + i * 5}") for i in range(4)]
        kq = self.ghep()
        self.assertNotEqual(kq[ids[3]][:2], ("H2", "chac"))
        self.assertNotEqual(kq[ids[2]][1], "chac")

    def test_bo_ngan_qua_nghi_mat_khong_khop_goi_y(self):  # ca 756A1CC3: 3 tấm nhãn có mặt, nghỉ 41s, 3 tấm không mặt
        self.hd("H1", D, "K1", "Nguyễn Thị Thu Trang", "Tiêm filler", "18:38")
        ids = [self.anh(D, "16:04:47", "Trang- filler 10/10/26", km="P-T"), self.anh(D, "16:04:49", km="P-T"),
               self.anh(D, "16:04:50", km="P-T"), self.anh(D, "16:05:31"), self.anh(D, "16:05:41"), self.anh(D, "16:05:43")]
        kq = self.ghep()
        self.assertEqual(kq[ids[1]][:2], ("H1", "chac"))
        self.assertNotEqual(kq[ids[4]][1], "chac")

    def test_bo_ngan_qua_nghi_cung_mat_van_chac(self):  # âm: sau quãng nghỉ vẫn cùng mặt ảnh nhãn -> chắc
        self.hd("H1", D, "K1", "Nguyễn Thị Thu Trang", "Tiêm filler", "18:38")
        ids = [self.anh(D, "16:04:47", "Trang- filler 10/10/26", km="P-T"), self.anh(D, "16:04:49", km="P-T"),
               self.anh(D, "16:04:50", km="P-T"), self.anh(D, "16:05:31", km="P-T"), self.anh(D, "16:05:41")]
        self.assertEqual(self.ghep()[ids[4]][:2], ("H1", "chac"))

    def test_nhan_ten_du_phay_ocr(self):  # ca 25DD7129: 'Lê Thi Hạnh ein, prp' -> tên + mã (ein = vein)
        n = A.doc_nhan("Lê Thi Hạnh ein, prp 11/6/2022", 2022)[0]
        self.assertEqual((n["ten"], n["ma_dv"]), ("le thi hanh", "vein"))
        self.assertEqual(A.doc_nhan("Gia Hân 13/7/26", 2026)[0]["ten"], "gia han")  # âm: 'Hân' có dấu không đoán mã

    def test_ten_khong_bat_dau_chu_viet_tat(self):  # âm (đo moi5): 'T' (Thị) / 'xăm' không đứng đầu tên
        for t, ten in [("Lương T Ngọc Thuỳ Pico 18/8/22", "ngoc thuy"), ("Xóa xăm Quốc Đạt XX 7/8/23", "quoc dat"),
                       ("Nguyễn Hồ g Thảo Vy Pico 14/5/22", "thao vy")]:
            self.assertEqual(A.doc_nhan(t, 2022)[0]["ten"], ten, t)

    def test_nhan_sau_chu_thich_tieu_de(self):  # ca CBA533E0: chú thích 'HÌNH ẢNH TRƯỚC SAU' trước nhãn
        n = A.doc_nhan("HÌNH ẢNH TRƯỚC SAU Huynh Lê Hưng 12/4/22 Csd mụn", 2022)[0]
        self.assertEqual((n["ten"], n["ma_dv"]), ("huynh le hung", "csd"))

    def test_nhan_ngay_khac_khoa_hd_ngay_nhan(self):  # ca CBA533E0: nhãn ngày 12/4 + csd, ảnh 16/4 -> giữ HĐ IPL 12/4
        self.hd("H1", "2026-10-06", "K1", "Huỳnh Lê Hưng", "Chăm sóc da với IPL ánh sáng", "14:30")
        self.hd("H2", "2026-10-06", "K1", "Huỳnh Lê Hưng", "Revskin - sữa rửa mặt", "15:01")
        a = self.anh(D, "10:42:40", "Huynh Lê Hưng 6/10/26 Csd mụn")
        self.assertEqual(self.ghep()[a][:2], ("H1", "chac"))

    def test_combo_dat_coc_xep_sau(self):  # ca B76B82C7
        import datetime as dt_
        vs = [{"code": "a", "ngay": D, "gio": "15:54", "dich_vu": "CSD MỤN ( LẦN LẺ ) | TRIỆT LÔNG MẶT"},
              {"code": "b", "ngay": D, "gio": "15:56", "dich_vu": "ĐẶT CỌC CSD | COMBO CSD ( 10 LẦN )"}]
        r = {"hd": None, "gio": dt_.datetime.fromisoformat(f"{D}T15:58:38"), "goc": 1}
        self.assertEqual(A._chon_hd_mat(vs, [D], r, ["csd"])["code"], "a")

    def test_cat_ngan_anh_truoc_nhan_cung_mat_chac(self):  # ca D65A6555: ảnh trước nhãn cùng mặt ảnh nhãn -> chắc
        self.hd("H1", D, "K1", "Bùi Nguyễn Nhất Anh", "CSD", "16:00")
        self.hd("H2", D, "K2", "Mai Ngọc Bích", "Laser Revivio", "16:33")
        ids = [self.anh(D, "16:18:52", "Nhất Anh- csd 10/10/26", km="P-A"), self.anh(D, "16:18:56", km="P-A"),
               self.anh(D, "16:19:04", km="P-B"), self.anh(D, "16:19:07", km="P-B"),
               self.anh(D, "16:19:09", "Ngọc Bích-Revivio 10/10/26", km="P-B")]
        ids += [self.anh(D, f"16:19:{15 + i * 5}", km="P-B") for i in range(4)]
        self.assertEqual(self.ghep()[ids[3]][:2], ("H2", "chac"))

    def test_cat_ngan_anh_truoc_nhan_mat_ben_kia_goi_y(self):  # ca ADA0268E: mặt ảnh trước nhãn = mặt nhãn bên kia
        self.hd("H1", D, "K1", "Bùi Nguyễn Nhất Anh", "CSD", "16:00")
        self.hd("H2", D, "K2", "Mai Ngọc Bích", "Laser Revivio", "16:33")
        ids = [self.anh(D, "16:18:52", "Nhất Anh- csd 10/10/26", km="P-A"), self.anh(D, "16:18:56", km="P-A"),
               self.anh(D, "16:19:04", km="P-A"), self.anh(D, "16:19:07", km="P-A"),
               self.anh(D, "16:19:09", "Ngọc Bích-Revivio 10/10/26", km="P-B")]
        ids += [self.anh(D, f"16:19:{15 + i * 5}", km="P-B") for i in range(4)]
        kq = self.ghep()
        self.assertNotEqual(kq[ids[3]][:2], ("H2", "chac"))
        # tách theo người (vòng 9 phần 4): cùng mã mặt ảnh nhãn bên kia, chụp liền -> chắc HĐ bên kia (ca 07308BE4)
        self.assertEqual(kq[ids[3]][:2], ("H1", "chac"))

    def test_combo_hon_san_pham(self):  # ca DA329CFE: combo CSD mụn hơn HĐ chỉ sữa rửa mặt
        self.assertLess(A._hang_hd("COMBO CSD MỤN ( 10 LẦN )"), A._hang_hd("REVSKIN - SỬA RỬA MẶT DEEP CLEASER"))
        self.assertLess(A._hang_hd("CSD MỤN"), A._hang_hd("COMBO CSD MỤN ( 10 LẦN )"))

    def test_cat_ngan_anh_sau_nhan_van_chac(self):  # âm của ADA0268E: ảnh SAU nhãn của phần vẫn chắc
        self.hd("H1", D, "K1", "Bùi Nguyễn Nhất Anh", "CSD", "16:00")
        self.hd("H2", D, "K2", "Mai Ngọc Bích", "Laser Revivio", "16:33")
        ids = [self.anh(D, "16:18:52", "Nhất Anh- csd 10/10/26"), self.anh(D, "16:18:56"),
               self.anh(D, "16:19:04"), self.anh(D, "16:19:07"), self.anh(D, "16:19:09", "Ngọc Bích-Revivio 10/10/26")]
        ids += [self.anh(D, f"16:19:{15 + i * 5}") for i in range(4)]
        kq = self.ghep()
        self.assertEqual({kq[i][:2] for i in ids[5:]}, {("H2", "chac")})

    def test_peel_la_ma(self):  # ca A1519E26: nhãn cùng bộ 'peel' -> HĐ có peel, không phải HĐ csd gần giờ hơn
        import datetime as dt_
        vs = [{"code": "a", "ngay": D, "gio": "11:16", "dich_vu": "CSD MỤN ( LẦN LẺ )"},
              {"code": "b", "ngay": D, "gio": "14:14", "dich_vu": "TRIỆT LÔNG MÉP/MẶT | PEEL DA MỤN (LẦN LẺ)"}]
        r = {"hd": None, "gio": dt_.datetime.fromisoformat(f"{D}T11:34:45"), "goc": 1}
        self.assertEqual(A._chon_hd_mat(vs, [D], r, [], ["peel"])["code"], "b")


class ThuTuHdVong7(unittest.TestCase):  # CEO 16/10 lần 7: dịch vụ nhãn -> loại HĐ chỉ SP/thu tiền -> giờ; hạng buổi chỉ khi < 20'
    import datetime as _dt

    def chon(self, vs, gio, ma=(), quanh=()):
        vs = [{"code": c, "ngay": D, "gio": g, "dich_vu": dv} for c, g, dv in vs]
        r = {"hd": None, "gio": self._dt.datetime.fromisoformat(f"{D}T{gio}"), "goc": 1}
        return A._chon_hd_mat(vs, [D], r, list(ma), list(quanh))["code"]

    def test_tiem_giai_la_tan_filler(self):  # ca 374C2565
        self.assertEqual(self.chon([("a", "17:03", "TIÊM SẸO LỒI"), ("b", "16:43", "ĐẶT CỌC | TIÊM TAN FILLER LÀM ĐẦY")],
                                   "16:28:12", ma=[A.doc_nhan("Hoa- tiêm giải mắt 10/10/26", 2026)[0]["ma_dv"]]), "b")

    def test_dong_thanh_toan_khong_de_gio(self):  # ca 7A6D7343: dòng thanh toán công nợ không đè giờ
        self.assertEqual(self.chon([("a", "17:14", "TIÊM XÓA NHĂN"), ("b", "14:52", "THANH TOÁN CÔNG NỢ VEIN | LASER NỘI BÌ")],
                                   "14:47:37"), "b")

    def test_laser_lift_la_noi_bi(self):
        self.assertEqual(self.chon([("a", "14:50", "TIÊM XÓA NHĂN"), ("b", "17:14", "LASER NỘI BÌ (2 VÙNG)")],
                                   "14:47:37", ma=["laser lift"]), "b")

    def test_chu_dv_lap_trong_hd(self):  # ca B51FBC22: nhãn 'exosome' (không có trong bảng) đúng chữ trong tên HĐ
        self.assertEqual(self.chon([("a", "09:47", "LASER FRACTIONAL"), ("b", "16:39", "TIÊM EXOSOME")], "09:30:13",
                                   quanh=["exosome"]), "b")
        self.assertEqual(self.chon([("a", "09:47", "CSD MỤN"), ("b", "16:39", "BÙ KIM RF")], "09:30:13",
                                   quanh=["kim"]), "a")  # âm: chữ ngắn lạ không xếp hạng

    def test_nhan_gach_duoi(self):  # ca 226F532B: 'Nhat Minh_sẹo'
        n = A.doc_nhan("Nhat Minh_sẹo 1 1/1 1/25", 2025)[0]
        self.assertEqual((n["ten"], n["ma_dv"]), ("nhat minh", "seo"))

    def test_gio_thang_khi_khong_nhan(self):  # ca 59BE90A2: 14' vs 76', không nhãn dịch vụ -> giờ thắng
        self.assertEqual(self.chon([("a", "14:47", "LASER ĐỐT MỤN THỊT MẶT"),
                                    ("b", "13:17", "KEM REVITALUX | ĐIỀU TRỊ SẸO RỖ")], "13:31:41"), "b")

    def test_hang_buoi_chi_khi_gio_sat(self):  # B76B82C7 giữ: chênh 2' -> buổi CSD hơn đặt cọc/combo
        self.assertEqual(self.chon([("a", "15:54", "CSD MỤN | TRIỆT LÔNG MẶT"), ("b", "15:56", "ĐẶT CỌC CSD | COMBO CSD")],
                                   "15:58:38", ma=["csd"]), "a")
        # chênh > 20' -> giờ thắng dù HĐ gần là combo
        self.assertEqual(self.chon([("a", "15:00", "CSD MỤN"), ("b", "15:56", "COMBO CSD ( 10 LẦN )")], "15:58:38",
                                   ma=["csd"]), "b")


class Vong9P1(Nen):  # CEO 16/10 lần 9 phần 4
    def cum_k(self, ten="Đỗ Hồng Phúc"):
        for i, ngay in enumerate(("2026-09-01", "2026-09-15")):
            self.hd(f"K1-{i}", ngay, "K1", ten, "CSD")
        for i in range(6):
            self.anh("2026-09-01" if i % 2 == 0 else "2026-09-15", f"10:{i:02d}:00", km="P-K", do_tin="chac",
                     goi_y=f"K1-{i % 2}", ly_do="nhãn 'x-csd' khớp")
        self.hd("K1-D", D, "K1", ten, "CSD", "15:00")

    def test_nhan_ten_khac_cung_mat_chan(self):  # (a): ảnh nhãn CÙNG MÃ MẶT (mặt không thuộc cụm K) ghi tên khác -> gợi ý
        self.cum_k()
        ids = [self.anh(D, "15:18:59", "Hoàng Huy - csd 10/10/26", km="P-X")]
        ids += [self.anh(D, f"15:19:{5 + i * 6:02d}", km="P-K P-X") for i in range(3)]
        self.assertNotIn("chac", {self.ghep()[i][1] for i in ids})

    def test_nhan_ten_khac_mat_cum_k_khong_chan(self):  # âm (a), ma18: mặt chung thuộc cụm đã xác nhận của K -> tên gọi
        self.cum_k()  # khác của K (23833080, D29C3C28, D25620E8, 16E7973E) -> mặt vẫn chắc
        ids = [self.anh(D, "15:18:59", "Hoàng Huy - csd 10/10/26", km="P-K")]
        ids += [self.anh(D, f"15:19:{5 + i * 6:02d}", km="P-K") for i in range(3)]
        self.assertEqual(self.ghep()[ids[2]][:2], ("K1-D", "chac"))

    def test_nhan_ten_khac_khac_mat_khong_chan(self):  # âm (a): ảnh nhãn là NGƯỜI KHÁC (khác mã mặt) -> mặt vẫn chắc
        self.cum_k()
        ids = [self.anh(D, "15:18:59", "Hoàng Huy - csd 10/10/26", km="P-H")]
        ids += [self.anh(D, f"15:19:{5 + i * 6:02d}", km="P-K") for i in range(3)]
        self.assertEqual(self.ghep()[ids[2]][:2], ("K1-D", "chac"))

    def test_ten_mo_khong_chan(self):  # âm (a): tên nhãn lệch mờ (bỏ dấu / tiền tố rác / i-y) không tính tên khác
        self.cum_k("Đỗ Hồng Phúc")
        for i, ocr in enumerate(("Phuc - csd 10/10/26", "Xq Phúc - csd 10/10/26")):
            self.c.execute("DELETE FROM photos WHERE ngay=?", (D,))
            ids = [self.anh(D, "15:18:59", ocr, km="P-K")] + [self.anh(D, f"15:19:{5 + j * 6:02d}", km="P-K") for j in range(3)]
            self.assertEqual(self.ghep()[ids[2]][:2], ("K1-D", "chac"), ocr)

    def test_nhan_iy(self):  # (c)
        self.assertTrue(A._ten_nhan_hop(A.doc_nhan("Mai Thi- căng chỉ 6/12/24", 2024)[0], "Phan Lâm Mai Thy"))

    def test_nhan_me(self):  # (f)
        self.assertEqual(A.doc_nhan("Mẹ C.Trang - CSD 7/6/2025", 2025)[0].get("quan_he"), "me")

    def test_tach_theo_nguoi(self):  # (b)
        self.hd("H1", D, "K1", "Cao Ngọc Mai Hương", "Trẻ hoá da picolight", "14:30")
        ids = [self.anh(D, "14:37:11", "Nguyên Đình Húy- csd 10/10/26", km="P-H"), self.anh(D, "14:37:16", km="P-M"),
               self.anh(D, "14:37:23", km="P-M"), self.anh(D, "14:37:29", "Ngọc Mai Hương- pico 10/10/26", km="P-M"),
               self.anh(D, "14:37:37", km="P-M"), self.anh(D, "14:37:42", km="P-H")]
        kq = self.ghep()
        self.assertEqual({kq[i][:2] for i in (ids[1], ids[2], ids[4])}, {("H1", "chac")})
        self.assertNotEqual(kq[ids[5]][:2], ("H1", "chac"))


class Vong10(Nen):  # CEO 17/10 lần 10: tách theo người
    def nen(self):
        self.hd("H1", D, "K1", "Cao Ngọc Mai Hương", "Trẻ hoá da picolight", "14:30")
        self.hd("H2", D, "K2", "Nguyễn Đình Huy", "CSD MỤN", "14:31")

    def test_mat_co_nhan_ten_khac_khong_nang(self):  # (1) ca 93257B53: cùng mã mặt có nhãn tên KHÁC (chưa khớp HĐ)
        self.nen()
        ids = [self.anh(D, "14:37:11", "Ngọc Mai Hương- pico 10/10/26", km="P-M"),
               self.anh(D, "14:37:11", "Thu Trang- csd 10/10/26", km="P-M"),
               self.anh(D, "14:37:16", km="P-M"), self.anh(D, "14:37:23", km="P-M")]
        kq = self.ghep()
        self.assertNotIn(("H1", "chac"), {kq[i][:2] for i in ids[1:]})
        self.assertEqual(kq[ids[0]][:2], ("H1", "chac"))  # ảnh neo giữ

    def test_nhan_tren_anh_neo_khong_chan(self):  # âm (1), ma19 2022-09-24: chính ảnh neo có thêm 1 nhãn tên lệch -> vẫn nâng
        self.nen()
        ids = [self.anh(D, "14:37:11", "Cao Ngọc Mai Hương\nMai Lệ Tâm- mụn 10/10/26", km="P-M"),
               self.anh(D, "14:37:16", km="P-M"), self.anh(D, "14:37:23", km="P-M"),
               self.anh(D, "14:37:51", km="P-X"), self.anh(D, "14:38:01", "Nguyễn Đình Huy - csd 10/10/26", km="P-X")]
        kq = self.ghep()  # đợt 2 khách -> luật bộ không lan; tách theo người phải nâng ảnh 2, 3
        self.assertEqual(kq[ids[0]][:2], ("H1", "chac"))
        self.assertEqual(kq[ids[2]][:2], ("H1", "chac"))

    def test_nhan_ocr_la_khong_chan(self):  # âm (1), ma19 8C0380C7: nhãn tên khác nhưng 'dịch vụ' là chữ OCR lạ -> vẫn nâng
        self.nen()
        ids = [self.anh(D, "14:37:11", "Ngọc Mai Hương- pico 10/10/26", km="P-M"),
               self.anh(D, "14:37:14", "Fraxional Inkjecs ny- c 10/10/26", km="P-M"),
               self.anh(D, "14:37:16", km="P-M"), self.anh(D, "14:37:23", km="P-M")]
        kq = self.ghep()
        self.assertEqual(kq[ids[3]][:2], ("H1", "chac"))

    def test_mat_nhan_cung_ten_van_nang(self):  # âm (1): nhãn thứ 2 cùng tên (bỏ dấu) với neo -> vẫn tách theo người
        self.hd("H2", D, "K2", "Nguyễn Đình Huy", "CSD MỤN", "14:31")
        self.hd("H1", D, "K1", "Cao Ngọc Mai Hương", "Trẻ hoá da picolight", "14:30")
        ids = [self.anh(D, "14:37:11", "Nguyên Đình Huy- csd 10/10/26", km="P-H"), self.anh(D, "14:37:16", km="P-M"),
               self.anh(D, "14:37:23", km="P-M"), self.anh(D, "14:37:29", "Ngọc Mai Hương- pico 10/10/26", km="P-M"),
               self.anh(D, "14:37:30", "Ngoc Mai Huong pico 10/10/26", km="P-M"),
               self.anh(D, "14:37:37", km="P-M"), self.anh(D, "14:37:42", km="P-H")]
        kq = self.ghep()
        self.assertEqual({kq[i][:2] for i in (ids[1], ids[2], ids[5])}, {("H1", "chac")})

    @staticmethod
    def r(gio, hd=None, do_tin="chua_ro", ly_do="", mat="", bo=1, nhan=None, xn=None, diem=0):
        import datetime as dt
        return {"hd": hd, "do_tin": do_tin, "ly_do": ly_do, "diem": diem, "xn": xn, "bo": bo,
                "gio": dt.datetime.fromisoformat(f"{D}T{gio}"), "mat_ds": set(mat.split()),
                "nhan": bool(nhan), "nhan_ds": A.doc_nhan(nhan, 2026) if nhan else []}

    def ca_80587249(self, **kw):  # bộ: nhãn H2 (mặt P-H), ảnh mặt P-M chắc theo luật bộ -> H2; neo H1 mặt P-M
        self.nen()
        bo = "cùng bộ chụp liền 2 ảnh với ảnh có nhãn 'x'"
        ds = [self.r("16:46:52", "H2", "chac", "nhãn 'Đình Huy- csd' khớp", "P-H", nhan="Đình Huy- csd 10/10/26", diem=80),
              self.r("16:46:52", "H2", "chac", bo, kw.get("mat", "P-M"), nhan=kw.get("nhan"), xn=kw.get("xn"), diem=80),
              self.r("16:46:53", "H1", "chac", "nhãn 'Mai Hương- pico' khớp", "P-M", bo=2,
                     nhan="Mai Hương- pico 10/10/26", diem=80)]
        A._tach_theo_nguoi(ds, {}, self.c)
        return ds

    def test_bo_chup_doi_theo_mat_neo(self):  # (2) ca 80587249 / 42EC5A61: chắc chỉ do luật bộ chụp -> đổi theo mặt
        ds = self.ca_80587249()
        self.assertEqual((ds[1]["hd"], ds[1]["do_tin"]), ("H1", "chac"))
        self.assertIn("trước: H2", ds[1]["ly_do"])
        self.assertEqual(ds[0]["hd"], "H2")

    def test_bo_chup_khong_doi_anh_nhan(self):  # âm (2): ảnh có nhãn riêng -> không đổi
        self.assertEqual(self.ca_80587249(nhan="Đình Huy- csd 10/10/26")[1]["hd"], "H2")

    def test_bo_chup_khong_doi_da_duyet(self):  # âm (2): ảnh đã duyệt -> không đổi
        self.assertEqual(self.ca_80587249(xn="H2")[1]["hd"], "H2")

    def test_bo_chup_khong_doi_khi_mat_trung_neo_dang_gan(self):  # âm (2): mặt cũng trùng ảnh neo HĐ đang gắn
        self.assertEqual(self.ca_80587249(mat="P-M P-H")[1]["hd"], "H2")

    def test_chac_theo_mat_khong_doi(self):  # âm (2): chắc theo luật mặt / nhãn (không phải luật bộ) -> không đổi
        self.nen()
        ds = [self.r("16:46:52", "H2", "chac", "khuôn mặt thuộc khách K2 (cụm 9 ảnh đã xác nhận) + HĐ cùng ngày", "P-M"),
              self.r("16:46:53", "H1", "chac", "nhãn 'Mai Hương- pico' khớp", "P-M", nhan="Mai Hương- pico 10/10/26",
                     diem=80)]
        A._tach_theo_nguoi(ds, {}, self.c)
        self.assertEqual(ds[0]["hd"], "H2")


class Vong11(Nen):  # CEO 17/10 lần 11 (ca F5256326, HD002294 ngày 24/08/2026)
    def ca(self, nhan_neo="Ngân - csd 24/8/26", mat_khac="P-N", mat_ha="P-H"):
        self.hd("H1", D, "K1", "Trần Thị Kim Ngân", "CSD MỤN", "14:00")
        self.hd("H2", D, "K2", "Nguyễn Thị Thu Hà", "PICO NÁM", "15:00")
        ids = [self.anh(D, "14:25:17", nhan_neo, km="P-N"), self.anh(D, "14:25:17", "Thu - csd 24/8/26", km=mat_khac),
               self.anh(D, "14:25:22", km=mat_khac), self.anh(D, "16:17:34", "Thu Hà - pico 24/8/26", km=mat_ha),
               self.anh(D, "16:17:38", km=mat_ha)]
        return ids, self.ghep()

    def test_neo_cung_mat_nhan_ten_khac_khong_chac(self):  # F5256326: nhãn 1 chữ + cùng mặt có nhãn tên khác -> gợi ý
        ids, kq = self.ca()
        self.assertEqual(kq[ids[0]][:2], ("H1", "goi_y"))

    def test_neo_ho_ten_du_van_chac(self):  # âm: nhãn trên ảnh >= 2 chữ tên khớp -> giữ chắc
        ids, kq = self.ca("Kim Ngân - csd 24/8/26")
        self.assertEqual(kq[ids[0]][:2], ("H1", "chac"))

    def test_nhan_ten_khac_khac_mat_van_chac(self):  # âm: ảnh nhãn tên khác là NGƯỜI KHÁC (khác mã mặt) -> giữ chắc
        ids, kq = self.ca(mat_khac="P-X")
        self.assertEqual(kq[ids[0]][:2], ("H1", "chac"))

    def test_phan_ten_mat_khac_khong_keo_sang_khach(self):  # HD002294: khớp một phần tên, mặt khác hẳn ảnh chắc của K2
        ids, kq = self.ca()
        self.assertNotEqual(kq[ids[1]][0], "H2")
        self.assertNotEqual(kq[ids[2]][0], "H2")
        self.assertEqual(kq[ids[3]][:2], ("H2", "chac"))

    def test_phan_ten_cung_mat_van_goi_y(self):  # âm: mặt trùng ảnh chắc của K2 -> vẫn theo K2
        ids, kq = self.ca(mat_khac="P-H")
        self.assertEqual(kq[ids[1]][0], "H2")


class GiuHdCu(unittest.TestCase):  # CEO 16/10 lần 4 (ca B2A478A3)
    import datetime as _dt

    def test_dam_vein_la_dich_vu_that(self):
        self.assertTrue(A._hd_that("DẶM VEIN MẶT"))

    def test_giu_hd_cu_khi_chenh_gio_nho(self):
        vs = [{"code": "a", "ngay": D, "gio": "10:03", "dich_vu": "DẶM VEIN MẶT"},
              {"code": "b", "ngay": D, "gio": "09:50", "dich_vu": "PICOLIGHT NÁM"}]
        r = {"hd": None, "gio": self._dt.datetime.fromisoformat(f"{D}T09:53:51"), "goc": 1}
        self.assertEqual(A._chon_hd_mat(vs, [D], dict(r), [], [], "", "a")["code"], "a")  # chênh < 20'
        self.assertEqual(A._chon_hd_mat(vs, [D], dict(r), [], [], "")["code"], "b")  # không có HĐ cũ: giờ gần nhất
        vs[0]["gio"] = "10:40"
        self.assertEqual(A._chon_hd_mat(vs, [D], dict(r), [], [], "", "a")["code"], "b")  # chênh > 20': theo giờ


if __name__ == "__main__":
    unittest.main()
