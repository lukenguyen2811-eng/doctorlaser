"""Khớp SĐT nhưng nhãn ghi tên khác (dữ liệu bịa): người nhà dùng chung số -> không 'chac' theo SĐT,
chỉ gợi ý 50, và không kéo cả bộ chụp lên 'chac'.

Chạy:  python3 -m unittest tests/test_sdt_nguoi_nha_anh.py
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["ANH_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
import anhkhach as A  # noqa: E402

NGAY = "2026-10-09"


def LY_(id_):  # noqa: N802
    return f"khớp SĐT nhưng nhãn ghi tên khác (ảnh {id_[:8]}) — có thể người nhà dùng chung số"


class SdtNguoiNha(unittest.TestCase):
    def setUp(self):
        self.c = A.ket_noi()
        self.c.execute("DELETE FROM visits")
        self.c.execute("DELETE FROM photos")
        self.c.execute("INSERT INTO visits (code,ngay,gio,ma_kh,ten_kh,sdt,dich_vu) VALUES"
                       " ('HD1',?,'10:00','KH01','Nguyễn Thị Lan','0909123456','CSD MỤN')", (NGAY,))

    def tearDown(self):
        self.c.close()

    def anh(self, id_, giay, ocr, phut=0):
        tg = f"{NGAY}T10:{phut:02d}:{giay:02d}"
        self.c.execute("INSERT INTO photos (id,ngay,thoi_gian,ten_file,chu_thich,ocr) VALUES (?,?,?,?,?,?)",
                       (id_, NGAY, tg, "IMG.HEIC", "", ocr))

    def ket(self):
        A.ghep_ngay(self.c, NGAY)
        return {r["id"]: r for r in self.c.execute("SELECT * FROM photos")}

    def test_sdt_khong_nhan_van_chac(self):
        self.anh("a", 0, "0909 123 456")
        r = self.ket()["a"]
        self.assertEqual((r["goi_y_hd"], r["do_tin"]), ("HD1", "chac"))

    def test_sdt_nhan_cung_ten_van_chac(self):
        self.anh("a", 0, "0909123456 Lan-csd 9/10/26")
        self.assertEqual(self.ket()["a"]["do_tin"], "chac")
        self.c.execute("DELETE FROM photos")
        self.anh("b", 0, "0909123456 C Lan - csd 9/10/26")  # xưng hô
        self.assertEqual(self.ket()["b"]["do_tin"], "chac")

    def test_sdt_nhan_ten_khac_tren_anh_ha_goi_y(self):
        self.anh("a", 0, "0909123456 Hùng-csd 9/10/26")
        r = self.ket()["a"]
        self.assertEqual((r["goi_y_hd"], r["do_tin"]), ("HD1", "goi_y"))
        self.assertEqual(r["ly_do"], LY_("a"))

    def test_nhan_ten_khac_cung_bo_ha_va_khong_keo_bo(self):
        self.anh("a", 0, "0909123456")
        self.anh("b", 10, "Hùng-csd 9/10/26")
        for i in range(2, 5):
            self.anh(f"x{i}", i * 10, "")
        r = self.ket()
        self.assertEqual(r["a"]["do_tin"], "goi_y")
        self.assertEqual(r["a"]["ly_do"], LY_("b"))  # lý do ghi ảnh có nhãn gây hạ
        self.assertNotIn("chac", {x["do_tin"] for x in r.values()})

    def test_nhan_ten_khac_cung_dot_khac_bo_khong_ha(self):
        # Soát lần 2 (ca 0402184F): nhãn gần nhất trong ĐỢT là khách khác cùng đợt -> chỉ xét cùng bộ chụp.
        self.anh("a", 0, "0909123456")
        self.anh("b", 0, "Hùng-csd 9/10/26", phut=5)  # cách 5' = bộ khác, cùng đợt
        self.assertEqual(self.ket()["a"]["do_tin"], "chac")

    def test_bo_co_nhan_dung_ten_khong_xet_dot(self):
        # Bộ của ảnh có nhãn đúng tên khách -> nhãn tên khác ở bộ khác trong đợt không hạ.
        self.anh("a", 0, "0909123456")
        self.anh("b", 10, "Lan-csd 9/10/26")
        self.anh("c", 0, "Hùng-csd 9/10/26", phut=5)
        self.assertEqual(self.ket()["a"]["do_tin"], "chac")

    def test_nhan_ten_khac_la_khach_co_hd_thi_lay_nhan(self):
        self.c.execute("INSERT INTO visits (code,ngay,gio,ma_kh,ten_kh,sdt,dich_vu) VALUES"
                       " ('HD2',?,'10:05','KH02','Trần Văn Hùng','','CSD MỤN')", (NGAY,))
        self.anh("a", 0, "0909123456 Hùng-csd 9/10/26")
        r = self.ket()["a"]
        self.assertEqual((r["goi_y_hd"], r["do_tin"]), ("HD2", "chac"))

    def test_nhan_khac_dau_cung_khach_khong_nang_lai_chac(self):
        # KH007916-giống: SĐT của 'Lê Thị Cẩm Quyên', nhãn 'Quyền' (người nhà) -> nhãn khớp không dấu không nâng lại.
        self.c.execute("UPDATE visits SET ten_kh='Lê Thị Cẩm Quyên'")
        self.anh("a", 0, "0909123456 Quyền-csd 9/10/26")
        r = self.ket()["a"]
        self.assertEqual((r["goi_y_hd"], r["do_tin"], r["ly_do"]), ("HD1", "goi_y", LY_("a")))
        self.c.execute("DELETE FROM photos")
        self.anh("b", 0, "0909123456 Cẩm Quyên- csd 9/10/26")
        self.assertEqual(self.ket()["b"]["do_tin"], "chac")

    def test_ma_kh_khong_bi_ha(self):
        self.anh("a", 0, "KH01 Hùng-csd 9/10/26")  # khớp mã KH: luật này chỉ cho SĐT
        self.assertEqual(self.ket()["a"]["do_tin"], "chac")

    def test_ten_nhan_hop(self):
        f = A._ten_nhan_hop
        n = lambda t: A.doc_nhan(t, 2026)[0]  # noqa: E731
        self.assertTrue(f(n("Lan-csd 9/10/26"), "Nguyễn Thị Lan"))
        self.assertTrue(f(n("Thị Lan-csd 9/10/26"), "Nguyễn Thị Lan (BS LƯƠNG)"))
        self.assertTrue(f(n("Lisa-csd 9/10/26"), "Nguyễn Thị Lan (LISA)"))
        self.assertTrue(f(n("Thanb-csd 9/10/26"), "Lê Thanh"))  # OCR lệch 1 chữ
        self.assertFalse(f(n("Hùng-csd 9/10/26"), "Nguyễn Thị Lan"))
        self.assertFalse(f(n("A Hùng-csd 9/10/26"), "Nguyễn Thị Lan"))
        self.assertFalse(f(n("Quyền-csd 9/10/26"), "Lê Thị Cẩm Quyên"))  # khác dấu = tên khác
        self.assertTrue(f(n("Cẩm Quyên- csd 9/10/26"), "Lê Thị Cẩm Quyên"))
        self.assertTrue(f(n("Quyen-csd 9/10/26"), "Lê Thị Cẩm Quyên"))  # nhãn mất dấu: so không dấu
        self.assertTrue(f(n("Lân-csd 9/10/26"), "NGUYEN THI LAN"))  # tên khách không dấu: so không dấu
        self.assertTrue(f(n("SAU SẸO Yến - csd 30/3/26"), "Tạ Thị Mai Yến"))  # chữ thừa bên trái

    def test_chu_thich_may_ghi_khong_la_nhan(self):
        # Chú thích do gan_chac/xuat ghi ('KH… · tên · SĐT · …' + mã HĐ) không được đọc thành nhãn tên khác.
        self.c.execute("INSERT INTO photos (id,ngay,thoi_gian,ten_file,chu_thich,ocr) VALUES (?,?,?,?,?,?)",
                       ("a", NGAY, f"{NGAY}T10:00:00", "IMG.HEIC",
                        "KH01 · Nguyễn Thị Lan · 0909123456 · 2026-10-09 · CSD MỤN KH01 CU-HD000001", ""))
        self.assertEqual(self.ket()["a"]["do_tin"], "chac")

    # ---- Soát lần 2 (14/10): dấu một chiều, chỉ cùng bộ, bỏ giấy tờ
    def test_chu_mot_chieu(self):
        f = A._chu_mot_chieu
        for nhan, ten in (("kiêu", "kiều"), ("hăng", "hằng"), ("truyên", "truyền"), ("huyên", "huyền"),
                          ("kieu", "kiều"), ("kiều", "kiều"), ("hoà", "hòa"), ("Kiêu", "kiều")):
            self.assertTrue(f(nhan, ten), (nhan, ten))
        for nhan, ten in (("quyền", "quyên"), ("nhân", "nhàn"), ("kiếu", "kiều"), ("hàng", "hằng"),
                          ("hăng", "hàng"), ("thú", "thư"), ("dũng", "dung"), ("đức", "dực")):
            self.assertFalse(f(nhan, ten), (nhan, ten))

    def test_nhan_thieu_dau_huyen_khong_ha(self):
        # Ca D00C9D78/3FDF8ABB/E8748330: OCR mất dấu huyền trên ê/ă -> vẫn là khách của SĐT.
        for ten, nhan in (("Nguyễn Minh Kiều", "Kiêu-csd 9/10/26"), ("Lê Võ Lệ Hằng", "Hăng-csd 9/10/26"),
                          ("Nguyễn Thị Ngọc Huyền", "Huyên-csd 9/10/26"), ("Nguyễn Kim Truyền (KH TỰ ĐẾN)",
                                                                         "Truyên-csd 9/10/26")):
            self.c.execute("DELETE FROM photos")
            self.c.execute("UPDATE visits SET ten_kh=?", (ten,))
            self.anh("a", 0, nhan)
            self.anh("b", 10, "0909123456")
            self.assertEqual(self.ket()["b"]["do_tin"], "chac", ten)

    def test_nhan_khac_chu_cai_van_ha(self):
        # Ca 406156ED: tên khách 'Nhàn', nhãn cùng bộ 'Nhân' (â≠a) -> hạ, lý do ghi ảnh nhãn; cả bộ có SĐT
        # (như ca thật) -> không ảnh nào 'chac', bộ không kéo lên.
        self.c.execute("UPDATE visits SET ten_kh='Võ Phạm Thanh Nhàn'")
        self.anh("n1", 0, "0909123456 Nhân-csd 9/10/26")
        self.anh("s1", 10, "0909123456")
        self.anh("s2", 20, "0909123456")
        r = self.ket()
        self.assertEqual((r["s1"]["do_tin"], r["s1"]["ly_do"]), ("goi_y", LY_("n1")))
        self.assertEqual({x["do_tin"] for x in r.values()}, {"goi_y"})

    def test_giay_to_trong_bo_khong_tinh_nhan(self):
        self.anh("a", 0, "0909123456")
        self.anh("g", 10, "DOCTOR LASER PHIẾU KHÁM DA Hùng-csd 9/10/26")  # chữ in trên phiếu khám
        self.assertEqual(self.ket()["a"]["do_tin"], "chac")

    def test_giay_to_co_sdt_xet_nhan_cung_bo(self):
        # Ảnh chính là phiếu khám có SĐT: nhãn trên phiếu bỏ, nhãn viết tay cùng bộ vẫn xét.
        self.anh("g", 0, "PHIẾU KHÁM DA 0909123456 Hùng-csd 9/10/26")
        self.anh("b", 10, "Hùng-csd 9/10/26")
        self.assertEqual(self.ket()["g"]["ly_do"], LY_("b"))
        self.c.execute("UPDATE photos SET ocr='' WHERE id='b'")
        self.assertEqual(self.ket()["g"]["do_tin"], "chac")

    def test_la_giay_to(self):
        g = lambda o: A._la_giay_to({"ocr": o})  # noqa: E731
        self.assertTrue(g("DOCTOR LASER Phòng khám Da liễu PHIẾU KHÁM DA 0909"))
        self.assertTrue(g(" ".join(["chu"] * 25)))
        self.assertFalse(g("Lan-csd 9/10/26"))
        self.assertFalse(g(None))


if __name__ == "__main__":
    unittest.main()
