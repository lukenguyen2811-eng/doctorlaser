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
        self.hd("H1", D, "K1", "JMITH DAVID A", "PRP")
        self.assertEqual(self.khop("David-prp 10/10/26")[:2], ("H1", 50))

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

    def test_chu_dem_khong_mat_goi_y(self):  # không mặt: 1 khách khớp chữ đệm + dịch vụ -> gợi ý 50
        self.hd("H1", D, "K1", "Lê Thị Phương Thảo", "CSD")
        a = self.anh(D, "15:10:00", "Phương-csd 10/10/26")
        k = self.ghep()[a]
        self.assertEqual(k[:2], ("H1", "goi_y"))

    def test_chu_dem_mat_yeu_khong_chac(self):  # âm: cụm chưa mạnh
        self.cum("K1", "Lê Thị Phương Thảo", n=3)
        a = self.anh(D, "15:10:00", "Phương-csd 10/10/26", km="P-K")
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


if __name__ == "__main__":
    unittest.main()
