"""Lượng chốt 17/10: ảnh BIÊN LAI CHUYỂN KHOẢN và MÀN HÌNH MÁY laser (kể cả có nhãn tên khách / thông số) KHÔNG lưu
theo khách. DB tạm, dữ liệu bịa.

Chạy:  python3 -m unittest tests/test_khong_luu_anh.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_ten_cuoi_mat_anh import A, D, Nen  # noqa: E402

MAY = "Energy 27.0 mJ  Pulse width 1.5 ms  Fractional  times 2  Ready"
BL = "Chuyển khoản thành công  1.300.000 VND  Vietcombank  Mã giao dịch FT22155006740838"


class NhanDien(unittest.TestCase):
    def test_bien_lai(self):
        self.assertEqual(A.loai_khong_luu(BL)[0], "bien_lai")
        self.assertEqual(A.loai_khong_luu("Techcombank 500 000 VND ngày 4/6/2022 chia sẻ")[0], "bien_lai")

    def test_man_hinh_may(self):
        self.assertEqual(A.loai_khong_luu(MAY)[0], "man_hinh_may")
        self.assertEqual(A.loai_khong_luu("1064 pulsecount 10000 15 Hz 500 mJ 1.56 J/cm2 picosecond")[0], "man_hinh_may")
        self.assertEqual(A.loai_khong_luu("Lan - csd 10/10/26 " + MAY)[0], "man_hinh_may")  # có nhãn tên vẫn là màn hình

    def test_nhan_khach_chu_dich_vu_khong_nham(self):  # âm: nhãn khách có chữ 'pico' / 'fractional' / 'laser lift'
        for t in ("Lan - pico 10/10/26", "Hà - fractional co2 12/3/26", "Thu Trang pico 1064 10/10/26",
                  "Mai - laser lift toning 3/4/25", "Vy - pico 5 lần 20/9/26", ""):
            self.assertIsNone(A.loai_khong_luu(t)[0], t)

    def test_nhan_buoc_song_khong_nham(self):  # âm, soát FA1F90D3: nhãn 'Tên - laser 532-1064 ngày' là ảnh khách
        for t in ("Phan Thị Lan - laser 532-1064 26/10/2022", "Lan - pico 1064nm 755 3/4/25", "Hà 1470nm lifting 2/2/26"):
            self.assertIsNone(A.loai_khong_luu(t)[0], t)
        self.assertEqual(A.loai_khong_luu("1064 532 Energy 0040 mJ")[0], "man_hinh_may")  # có từ chữ -> vẫn màn hình

    def test_phieu_dieu_tri_khong_nham(self):  # âm (soát BACC2728): phiếu điều trị ghi thông số -> giấy tờ khách
        self.assertIsNone(A.loai_khong_luu("PHIẾU ĐIỀU TRỊ Họ tên ... Energy 20 mJ 10 Hz")[0])

    def test_so_tien_khong_kem_dau_hieu_khac(self):  # âm: 1 dấu hiệu (giá) không đủ biên lai
        self.assertIsNone(A.loai_khong_luu("Combo 1.500.000 đ")[0])


class Ghep(Nen):
    def nen(self):
        self.hd("H1", D, "K1", "Phan Thị Lan", "CSD MỤN", "10:00")
        self.hd("H2", D, "K2", "Trần Văn Nam", "CSD MỤN", "15:00")

    def test_man_hinh_khong_chac_khong_goi_y(self):
        self.nen()
        i = self.anh(D, "10:05:00", "Lan - csd 10/10/26 " + MAY)
        kq = self.ghep()
        self.assertEqual(kq[i][:2], (None, "chua_ro"))
        self.assertTrue(kq[i][2].startswith(A.KHONG_LUU))
        self.assertEqual(self.c.execute("SELECT may_loai FROM photos WHERE id=?", (i,)).fetchone()[0], "man_hinh_may")

    def test_bien_lai_khong_luu(self):
        self.nen()
        i = self.anh(D, "10:05:00", BL)
        self.assertEqual(self.ghep()[i][:2], (None, "chua_ro"))

    def test_man_hinh_khong_lam_neo(self):  # mặc định: nhãn trên màn hình máy không kéo ảnh cùng bộ
        self.nen()
        ids = [self.anh(D, "10:05:00", "Lan - csd 10/10/26 " + MAY), self.anh(D, "10:05:05"), self.anh(D, "10:05:10")]
        kq = self.ghep()
        self.assertFalse([i for i in ids[1:] if kq[i][0] == "H1" and kq[i][1] == "chac"])

    def test_neo_yeu_bat_thi_chi_goi_y(self):  # BAT_LUAT=NHAN_MAY: ảnh cùng bộ chỉ được GỢI Ý
        self.nen()
        ids = [self.anh(D, "22:30:00", "Lan - csd 10/10/26 " + MAY), self.anh(D, "22:30:05")]
        A._BAT.add("NHAN_MAY")
        try:
            kq = self.ghep()
        finally:
            A._BAT.discard("NHAN_MAY")
        self.assertEqual(kq[ids[1]][:2], ("H1", "goi_y"))
        self.assertIn("neo yếu", kq[ids[1]][2])

    def test_anh_khach_nhan_pico_van_chac(self):  # âm
        self.nen()
        i = self.anh(D, "10:05:00", "Phan Thị Lan - pico 10/10/26")
        self.assertEqual(self.ghep()[i][1], "chac")

    def test_trang_duyet_an(self):
        self.nen()
        i = self.anh(D, "10:05:00", BL)
        self.ghep()
        n = self.c.execute(f"SELECT COUNT(*) FROM photos WHERE id=? AND {A.CAN_DUYET}", (i,)).fetchone()[0]
        self.assertEqual(n, 0)

    def test_album_khong_lay(self):
        import album_anh
        self.nen()
        i = self.anh(D, "10:05:00", "Phan Thị Lan - csd 10/10/26")
        j = self.anh(D, "10:06:00", BL)
        self.ghep()
        self.c.execute("UPDATE photos SET nguon='photos'")
        ids = {r["id"] for r in album_anh.anh_dung(self.c)}
        self.assertIn(i, ids)
        self.assertNotIn(j, ids)


class KhCuKhachKhac(Nen):  # CEO 17/10 lần 16 (G4): nhãn 'Tên kh cũ dd/m dịch vụ' chỉ khách khác -> hạ chắc cả bộ
    def test_ha_chac_theo_nhan_kh_cu(self):
        self.hd("H1", "2026-10-10", "K1", "Trần Thị Kim Ngân", "PICO", "16:14")
        self.hd("H2", "2026-10-09", "K2", "Lâm Thị Nhung", "PICO", "16:56")
        ids = [self.anh("2026-10-10", "12:23:00", "Lam t nhung kh cũ 9/10 prp pico", km="P-X", do_tin="chac"),
               self.anh("2026-10-10", "12:23:05", km="P-X")]
        self.c.execute("UPDATE photos SET goi_y_hd='H1'")
        # giả lập ghép đã cho chắc H1 (bộ theo 1 HĐ trong ngày) rồi chạy luật
        kq = {i: {"hd": "H1", "do_tin": "chac", "xn": None, "bo": 1, "mat_ds": {"P-X"}, "ly_do": ""} for i in ids}
        ps = self.c.execute("SELECT * FROM photos ORDER BY thoi_gian").fetchall()
        A._goi_y_nhan_khong_nam(self.c, "2026-10-10", ps, kq)
        self.assertEqual({(kq[i]["hd"], kq[i]["do_tin"]) for i in ids}, {("H2", "goi_y")})

    def test_cung_khach_khong_ha(self):  # âm: nhãn chỉ đúng khách của HĐ đang gắn (HĐ khác ngày) -> giữ
        self.hd("H1", "2026-10-10", "K2", "Lâm Thị Nhung", "PICO", "16:14")
        self.hd("H2", "2026-10-09", "K2", "Lâm Thị Nhung", "PICO", "16:56")
        i = self.anh("2026-10-10", "12:23:00", "Lam t nhung kh cũ 9/10 prp pico", km="P-X")
        kq = {i: {"hd": "H1", "do_tin": "chac", "xn": None, "bo": 1, "mat_ds": {"P-X"}, "ly_do": ""}}
        A._goi_y_nhan_khong_nam(self.c, "2026-10-10", self.c.execute("SELECT * FROM photos").fetchall(), kq)
        self.assertEqual(kq[i]["do_tin"], "chac")


class KhCuTuDuyet(unittest.TestCase):  # G4: tự duyệt không nhận khách bị nhãn 'kh cũ' phản bác
    def test_nhan_kn_phan_bac(self):
        n = A._nhan_khong_nam("Lam t nhung kh cũ 9/10 prp pico", 2026)
        ctx = {"chu_mat": {"K"}, "chu_nhan_mat": set(), "nhans": [], "gio": A.dt.datetime(2026, 10, 10, 12, 23),
               "co_goc": False, "goi_y": None, "nhan_kn": n}
        v = {"code": "H1", "ngay": "2026-10-10", "gio": "16:14", "ten_kh": "Trần Thị Kim Ngân", "dich_vu": "PICO"}
        self.assertEqual(A._td_diem([], "K", [v], ctx)["nhan"], A.TD_NHAN_PHAN)
        v2 = dict(v, ten_kh="Lâm Thị Nhung")  # âm: nhãn hợp khách -> không phản bác
        self.assertEqual(A._td_diem([], "K", [v2], ctx)["nhan"], 0.0)


class TruocSau(Nen):  # CEO 17/10 lần 16: ảnh 'HÌNH ẢNH TRƯỚC SAU' ghi ngày khác HĐ -> gợi ý
    def nen(self, ocr):
        self.hd("H1", D, "K1", "Phan Thị Lan", "CSD MỤN", "10:00")
        i = self.anh(D, "10:05:00", "Phan Thị Lan - csd 10/10/26", ngay_goc=1)
        self.c.execute("UPDATE photos SET chu_thich=? WHERE id=?", (ocr, i))
        return i, self.ghep()

    def test_ghi_ngay_khac_ha(self):
        i, kq = self.nen("HÌNH ẢNH TRƯỚC SAU 24/4")
        self.assertEqual(kq[i][:2], ("H1", "goi_y"))
        self.assertIn("ảnh trước–sau", kq[i][2])

    def test_khong_ghi_ngay_giu(self):  # âm
        i, kq = self.nen("HÌNH ẢNH TRƯỚC SAU")
        self.assertEqual(kq[i][1], "chac")

    def test_ghi_dung_ngay_hd_giu(self):  # âm
        i, kq = self.nen("HÌNH ẢNH TRƯỚC SAU 10/10")
        self.assertEqual(kq[i][1], "chac")


class TrungTen(Nen):  # CEO 17/10 lần 17: nhãn hợp >= 2 khách cùng tên, mặt (ngày khác) thuộc khách khác
    def chay(self, lich, mat="P-X", nhan="Lan - csd 10/10/26"):
        import datetime as dt
        self.hd("H1", D, "K1", "Nguyễn Thị Lan", "CSD MỤN", "10:00")
        self.hd("H2", D, "K2", "Trần Thị Lan", "CSD MỤN", "10:30")
        i = self.anh(D, "10:05:00", nhan, km=mat)
        visits = self.c.execute("SELECT * FROM visits WHERE ngay=?", (D,)).fetchall()
        photos = self.c.execute("SELECT * FROM photos WHERE ngay=?", (D,)).fetchall()
        j = self.anh(D, "10:05:05", km=mat)
        kq = {i: {"hd": "H1", "do_tin": "chac", "xn": None, "ly_do": "nhãn khớp", "gio": dt.datetime(2026, 10, 10, 10, 5),
                  "mat_ds": set(mat.split()), "bo": 1},
              j: {"hd": "H1", "do_tin": "chac", "xn": None, "ly_do": "cùng bộ chụp liền 2 ảnh với ảnh có nhãn",
                  "gio": dt.datetime(2026, 10, 10, 10, 5, 5), "mat_ds": set(mat.split()), "bo": 1}}
        self.j = j
        cum = {"lich": lich, "khoa": {}, "cum": {}, "nhom": {}}
        A._ha_trung_ten(self.c, D, visits, photos, kq, cum, {i: A.doc_nhan(nhan, 2026), j: []})
        self.kq = kq
        return kq[i]

    def test_mat_khach_cung_ten_khac_goi_y_hd_do(self):
        r = self.chay({"P-X": {"K2": {"2026-09-01"}}})
        self.assertEqual((r["hd"], r["do_tin"]), ("H2", "goi_y"))
        self.assertEqual(self.kq[self.j]["do_tin"], "goi_y")  # ảnh cùng bộ lan theo nhãn hạ theo

    def test_mat_khach_ngoai_ha_giu_hd(self):
        r = self.chay({"P-X": {"K9": {"2026-09-01"}}})
        self.assertEqual((r["hd"], r["do_tin"]), ("H1", "goi_y"))

    def test_mat_dung_khach_giu(self):  # âm
        self.assertEqual(self.chay({"P-X": {"K1": {"2026-09-01"}, "K2": {"2026-08-01"}}})["do_tin"], "chac")

    def test_chi_lich_su_cung_ngay_giu(self):  # âm: lịch sử chỉ ở chính ngày này
        self.assertEqual(self.chay({"P-X": {"K2": {D}}})["do_tin"], "chac")

    def test_nhan_chi_hop_1_khach_giu(self):  # âm
        self.assertEqual(self.chay({"P-X": {"K2": {"2026-09-01"}}}, nhan="Nguyễn Thị Lan - csd 10/10/26")["do_tin"], "chac")

    def test_anh_2_mat_giu(self):  # âm
        self.assertEqual(self.chay({"P-X": {"K2": {"2026-09-01"}}}, mat="P-X P-Y")["do_tin"], "chac")


class TrungTenChuDem(TrungTen):  # ca 7095980C: nhãn 1 chữ 'Thảo' trùng chữ đệm khách khác ('Phương Thảo Nhi')
    def chay(self, lich, mat="P-X", nhan="Thảo - csd 10/10/26"):
        import datetime as dt
        self.hd("H1", D, "K1", "Nguyễn Huỳnh Phương Thảo", "CSD MỤN", "10:00")
        self.hd("H2", D, "K2", "Lê Phương Thảo Nhi", "CSD MỤN", "10:30")
        i = self.anh(D, "10:05:00", nhan, km=mat)
        visits = self.c.execute("SELECT * FROM visits WHERE ngay=?", (D,)).fetchall()
        photos = self.c.execute("SELECT * FROM photos WHERE ngay=?", (D,)).fetchall()
        kq = {i: {"hd": "H1", "do_tin": "chac", "xn": None, "ly_do": "nhãn khớp", "gio": dt.datetime(2026, 10, 10, 10, 5),
                  "mat_ds": set(mat.split()), "bo": 1}}
        A._ha_trung_ten(self.c, D, visits, photos, kq, {"lich": lich, "khoa": {}, "cum": {}, "nhom": {}},
                        {i: A.doc_nhan(nhan, 2026)})
        return kq[i]

    def test_mat_khach_cung_ten_khac_goi_y_hd_do(self):
        r = self.chay({"P-X": {"K2": {"2026-09-01"}}})
        self.assertEqual((r["hd"], r["do_tin"]), ("H2", "goi_y"))

    def test_mat_dung_khach_giu(self):  # âm
        self.assertEqual(self.chay({"P-X": {"K1": {"2026-09-01"}}})["do_tin"], "chac")

    test_mat_khach_ngoai_ha_giu_hd = test_chi_lich_su_cung_ngay_giu = test_anh_2_mat_giu = None
    test_nhan_chi_hop_1_khach_giu = None


class TrungTenDichVu(TrungTen):  # âm (kiểm toán DEB408D6): dịch vụ trên nhãn chỉ khớp HĐ khách được gắn -> giữ
    def chay(self, lich, mat="P-X", nhan="Lan - căng chỉ 10/10/26"):
        import datetime as dt
        self.hd("H1", D, "K1", "Nguyễn Thị Lan", "CĂNG CHỈ", "10:00")
        self.hd("H2", D, "K2", "Trần Thị Lan", "CSD MỤN", "10:30")
        i = self.anh(D, "10:05:00", nhan, km=mat)
        visits = self.c.execute("SELECT * FROM visits WHERE ngay=?", (D,)).fetchall()
        photos = self.c.execute("SELECT * FROM photos WHERE ngay=?", (D,)).fetchall()
        kq = {i: {"hd": "H1", "do_tin": "chac", "xn": None, "ly_do": "nhãn khớp", "gio": dt.datetime(2026, 10, 10, 10, 5),
                  "mat_ds": set(mat.split()), "bo": 1}}
        A._ha_trung_ten(self.c, D, visits, photos, kq, {"lich": lich, "khoa": {}, "cum": {}, "nhom": {}},
                        {i: A.doc_nhan(nhan, 2026)})
        return kq[i]

    def test_mat_khach_ngoai_giu(self):  # mặt lịch sử là khách NGOÀI (không cùng tên hôm nay) -> dịch vụ thắng, giữ
        self.assertEqual(self.chay({"P-X": {"K9": {"2026-09-01"}}})["do_tin"], "chac")

    def test_mat_khach_cung_ten_khac_goi_y_hd_do(self):  # ca 995EB43C: mặt là khách cùng tên khác hôm nay -> vẫn hạ
        r = self.chay({"P-X": {"K2": {"2026-09-01"}}})
        self.assertEqual((r["hd"], r["do_tin"]), ("H2", "goi_y"))

    test_mat_khach_ngoai_ha_giu_hd = None


class MotNguoiHaiMa(Nen):  # vòng 18: 1 người 2 mã KH
    def test_cung_ho_ten_khac_he_gop(self):  # ca 20F1A53F
        self.hd("A1", "2020-01-01", "CU-KH000798", "Võ Thị Mỹ Lệ", "CSD")
        self.hd("A2", "2026-01-01", "KH004655", "VÕ THỊ MỸ LỆ (BS LƯƠNG)", "CSD")
        k = A._khoa_khach(self.c, theo_ten=True)
        self.assertEqual(k["CU-KH000798"], k["KH004655"])
        k0 = A._khoa_khach(self.c)  # mặc định (luật mặt): chỉ SĐT
        self.assertNotEqual(k0["CU-KH000798"], k0["KH004655"])

    def test_cung_he_hoac_2_chu_cuoi_khong_gop(self):  # âm
        self.hd("A1", "2026-01-01", "KH000001", "Võ Thị Mỹ Lệ", "CSD")
        self.hd("A2", "2026-01-02", "KH000002", "Võ Thị Mỹ Lệ", "CSD")  # cùng hệ
        self.hd("A3", "2020-01-02", "CU-KH000003", "Trần Văn Mỹ Lệ", "CSD")  # chỉ trùng 2 chữ cuối
        k = A._khoa_khach(self.c, theo_ten=True)
        self.assertEqual(len({k["KH000001"], k["KH000002"], k["CU-KH000003"]}), 3)


class TrungTenGop(TrungTen):  # vòng 18 (ca 7749626F): mặt có dấu gộp 2 người, nhãn không hợp tên chủ mặt -> bỏ bằng chứng mặt
    def chay2(self, lan, ten_chu="Hoàng Văn Bình"):
        self.hd("X9", "2026-09-01", "K9", ten_chu, "CSD")
        import datetime as dt
        self.hd("H1", D, "K1", "Nguyễn Thị Lan", "CSD MỤN", "10:00")
        self.hd("H2", D, "K2", "Trần Thị Lan", "CSD MỤN", "10:30")
        i = self.anh(D, "10:05:00", "Lan - csd 10/10/26", km="P-X")
        visits = self.c.execute("SELECT * FROM visits WHERE ngay=?", (D,)).fetchall()
        photos = self.c.execute("SELECT * FROM photos WHERE ngay=?", (D,)).fetchall()
        kq = {i: {"hd": "H1", "do_tin": "chac", "xn": None, "ly_do": "nhãn khớp", "gio": dt.datetime(2026, 10, 10, 10, 5),
                  "mat_ds": {"P-X"}, "bo": 1}}
        cum = {"lich": {"P-X": {"K9": {"2026-09-01"}}}, "khoa": {}, "cum": {}, "nhom": {}, "lan": {"P-X"} if lan else set()}
        A._ha_trung_ten(self.c, D, visits, photos, kq, cum, {i: A.doc_nhan("Lan - csd 10/10/26", 2026)})
        return kq[i]

    def test_gop_nhan_khong_hop_chu_giu(self):
        self.assertEqual(self.chay2(True)["do_tin"], "chac")

    def test_khong_gop_van_ha(self):  # âm
        self.assertEqual(self.chay2(False)["do_tin"], "goi_y")

    def test_gop_nhan_hop_chu_van_ha(self):  # âm: chủ mặt có tên hợp nhãn ('Lan')
        self.assertEqual(self.chay2(True, "Phạm Thị Lan")["do_tin"], "goi_y")


class TrungTenHaiMa(TrungTen):  # vòng 18 (20F1A53F): mặt lịch sử thuộc mã KHÁC HỆ cùng họ tên đầy đủ = cùng người -> giữ
    def test_mat_khach_ngoai_ha_giu_hd(self):
        self.hd("Z1", "2020-01-01", "CU-KH1", "Nguyễn Thị Lan", "CSD")
        self.assertEqual(self.chay({"P-X": {"CU-KH1": {"2026-09-01"}}})["do_tin"], "chac")

    test_mat_khach_cung_ten_khac_goi_y_hd_do = None
