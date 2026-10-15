"""Đọc nhãn nhân viên ghi trên ảnh + ghép với hóa đơn (dữ liệu bịa).

Chạy:  python3 -m unittest tests/test_nhan_anh.py
Mẫu chữ lấy theo đúng kiểu OCR thật đọc ra tháng 10/2026 (tên đã thay).
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["ANH_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
import anhkhach as A  # noqa: E402


class DocNhan(unittest.TestCase):
    def mot(self, chu):
        ds = A.doc_nhan(chu, 2026)
        self.assertEqual(len(ds), 1, (chu, ds))
        return ds[0]

    def test_kieu_cu(self):
        n = self.mot("Giang-sẹo 9/10/26")
        self.assertEqual((n["ten"], n["ma_dv"], n["ngay"]), ("giang", "seo", "2026-10-09"))

    def test_dich_vu_nhieu_chu_va_so(self):
        self.assertEqual(self.mot("Tam-meso mắt 5/10/26")["ngay"], "2026-10-05")
        n = self.mot("Bich-co2 nốt ruồi 5/10/26")
        self.assertEqual((n["ten"], n["ma_dv"], n["ngay"]), ("bich", "co2", "2026-10-05"))
        self.assertEqual(self.mot("Bich-co2 môi. 8/10/26")["ngay"], "2026-10-08")

    def test_xuyet_va_rac(self):
        self.assertEqual(self.mot("Kieu / pico 7/10/26")["ten"], "kieu")
        n = self.mot("Lee min- csd C32•8/10/26")
        self.assertEqual((n["ten"], n["ma_dv"], n["ngay"]), ("lee min", "csd", "2026-10-08"))

    def test_hai_o_chu_ten_rieng_ngay_rieng(self):  # Vision trả tên và ngày thành 2 ô
        n = self.mot("Hoà-Ha mắt 8/10126")
        self.assertEqual((n["ten"], n["ma_dv"], n["ngay"]), ("hoa", "ha", "2026-10-08"))

    def test_thieu_ngay(self):
        self.assertIsNone(self.mot("Hoà-Ha mắt")["ngay"])

    def test_chi_co_ngay_khong_la_nhan(self):
        self.assertEqual(A.doc_nhan("6/10/26", 2026), [])
        self.assertEqual(A.doc_nhan("Doctor Laser 1/10/26", 2026), [])

    def test_hai_nhan_tren_mot_anh(self):
        ds = A.doc_nhan("Tam-pico 1/10/26 Bich-csd 2/10/26", 2026)
        self.assertEqual([(n["ten"], n["ngay"]) for n in ds],
                         [("tam", "2026-10-01"), ("bich", "2026-10-02")])


class KhopNhan(unittest.TestCase):
    def setUp(self):
        self.c = A.ket_noi()
        self.c.execute("DELETE FROM visits")
        for code, ngay, ten, dv in [
            ("HD1", "2026-10-08", "Nguyễn Thị Hoà", "Tiêm HA mắt"),
            ("HD2", "2026-10-08", "Trần Văn Elan", "Laser Pico"),
            ("HD3", "2026-10-05", "Lê Thị Tâm", "Meso mắt"),
            ("HD4", "2026-10-05", "Phạm Tâm", "Trị sẹo rỗ"),
            ("HD5", "2026-10-06", "Võ Minh Anh", "CSD"),
            ("HD6", "2026-10-03", "Manami Yoshida", "CSD"),
            ("HD7", "2026-10-03", "Đỗ Văn Thanh", "Botox"),
            ("HD8", "2026-10-09", "Đoàn Thanh Vy KH7332 GT", "CSD mụn lần lẻ"),
            ("HD9", "2026-10-08", "Lý Thị Hoà", "Tiêm HA mắt"),
        ]:
            self.c.execute("INSERT INTO visits (code,ngay,ten_kh,dich_vu) VALUES (?,?,?,?)",
                           (code, ngay, ten, dv))

    def tearDown(self):
        self.c.close()

    def khop(self, chu, ngay_anh):
        return A._khop_nhan(self.c, A.doc_nhan(chu, 2026)[0], ngay_anh)

    def test_nam_doc_sai_dung_ngay_chup(self):
        hd, d, ly_do = self.khop("Elan- pico 8/10/16", "2026-10-08")
        self.assertEqual((hd, d), ("HD2", 85))
        self.assertIn("dùng ngày chụp", ly_do)

    def test_trung_ten_trung_dich_vu_nguoi_chon(self):
        hd, d, ly_do = self.khop("Hoà / Ha mắt 08/10/26", "2026-10-09")
        self.assertIsNone(hd)
        self.assertIn("trùng 2 khách (nhãn ghi ngày 2026-10-08)", ly_do)

    def test_thieu_ngay_dung_ngay_chup(self):
        self.assertEqual(self.khop("Elan-pico", "2026-10-08")[:2], ("HD2", 85))

    def test_trung_ten_tach_bang_dich_vu(self):
        self.assertEqual(self.khop("Tâm-meso mắt 5/10/26", "2026-10-05")[0], "HD3")
        self.assertEqual(self.khop("Tâm-sẹo 5/10/26", "2026-10-05")[0], "HD4")

    def test_chu_thua_truoc_ten_chi_goi_y(self):
        hd, d, _ = self.khop("Laser Anh-csd 6/10/26", "2026-10-06")
        self.assertEqual((hd, d), ("HD5", 50))  # khớp đuôi tên -> không 'chắc chắn'

    def test_ten_trong_ho_ten_co_duoi_ghi_chu(self):
        self.assertEqual(self.khop("Vy-csd 9/10/26", "2026-10-09")[:2], ("HD8", 85))  # + dịch vụ khớp
        self.assertEqual(self.khop("Vy-pico 9/10/26", "2026-10-09")[:2], ("HD8", 40))  # dịch vụ lệch: 40, không làm neo
        self.assertEqual(self.khop("Manami- csd 3/10/26", "2026-10-03")[:2], ("HD6", 85))

    def test_ocr_sai_mot_chu_chi_goi_y(self):
        self.assertEqual(self.khop("Thann-botox 3/10/26", "2026-10-03")[:2], ("HD7", 50))
        self.assertIsNone(self.khop("Thao-botox 3/10/26", "2026-10-03")[0])  # lệch 2 chữ
        self.assertIsNone(self.khop("Tan-botox 3/10/26", "2026-10-03")[0])  # tên ngắn: không đoán

    def test_lech_1(self):
        self.assertTrue(A._lech_1("thann", "thanh"))
        self.assertTrue(A._lech_1("thnh", "thanh"))
        self.assertFalse(A._lech_1("thanh", "thanh"))
        self.assertFalse(A._lech_1("thao", "thanh"))

    def test_khong_co_khach_ten_nay(self):
        self.assertIsNone(self.khop("Quang-pico 8/10/26", "2026-10-08")[0])

    def test_ghep_ngay_danh_dau_muc_tin(self):
        self.c.execute("DELETE FROM photos")
        for pid, tg, ocr in [("p1", "2026-10-06T10:00:00", "Laser Anh-csd 6/10/26"),
                             ("p2", "2026-10-06T15:00:00", "6/10/26")]:
            self.c.execute("INSERT INTO photos (id,ngay,thoi_gian,ten_file,chu_thich,ocr)"
                           " VALUES (?,?,?,?,?,?)", (pid, tg[:10], tg, "IMG.HEIC", "", ocr))
        A.ghep_ngay(self.c, "2026-10-06")
        r = dict(self.c.execute("SELECT id, do_tin FROM photos").fetchall())
        self.assertEqual(r["p1"], "goi_y")

    def test_trang_duyet_chon_duoc_hoa_don_ngay_khac(self):
        self.c.execute("DELETE FROM photos")
        self.c.execute("INSERT INTO photos (id,ngay,thoi_gian,ten_file,chu_thich,ocr,dot)"
                       " VALUES ('p9','2026-10-10','2026-10-10T09:43:00','IMG.jpg','','Hoà-Ha mắt 8/10/26',0)")
        A.ghep_ngay(self.c, "2026-10-10")
        self.assertEqual(self.c.execute("SELECT goi_y_hd FROM photos").fetchone()[0], None)  # trùng 2 Hoà
        self.c.execute("UPDATE photos SET goi_y_hd='HD2'")
        trang = A._trang_ngay(self.c, "2026-10-10").decode()
        self.assertIn("<option value='HD2' selected>08/10", trang)
        self.assertIn("Hóa đơn ngày khác", trang)
        self.assertIn("chưa tải về máy", trang)  # ảnh chưa có file -> chữ, không khung vỡ
        self.assertNotIn("src='/anh/p9'", trang)


class GioHoaDon(unittest.TestCase):
    def setUp(self):
        self.c = A.ket_noi()
        self.c.execute("DELETE FROM visits")
        self.c.execute("DELETE FROM photos")
        for code, gio in [("H1", "09:50"), ("H2", "11:00"), ("H3", "11:20"), ("H4", "15:00")]:
            self.c.execute("INSERT INTO visits (code,ngay,gio,ten_kh,dich_vu) VALUES (?,?,?,?,?)",
                           (code, "2026-09-05", gio, "Khach " + code, "Laser"))

    def tearDown(self):
        self.c.close()

    def ghep(self, gio_anh):
        for i, g in enumerate(gio_anh):
            self.c.execute("INSERT INTO photos (id,ngay,thoi_gian,ten_file,chu_thich,ocr) VALUES (?,?,?,?,?,?)",
                           (f"p{i}", "2026-09-05", f"2026-09-05T{g}:00", "IMG.HEIC", "", ""))
        A.ghep_ngay(self.c, "2026-09-05")
        return {r[0]: (r[1], r[2]) for r in self.c.execute("SELECT id, goi_y_hd, do_tin FROM photos")}

    def test_mot_hoa_don_gan_gio(self):
        r = self.ghep(["09:40", "09:45"])
        self.assertEqual(r["p0"], ("H1", "goi_y"))
        self.assertEqual(r["p1"], ("H1", "goi_y"))

    def test_hai_hoa_don_gan_gio_nguoi_chon(self):
        self.assertEqual(self.ghep(["10:55"])["p0"], (None, "chua_ro"))  # H2 11:00, H3 11:20

    def test_khong_hoa_don_nao_gan(self):
        self.assertEqual(self.ghep(["13:00"])["p0"], (None, "chua_ro"))

    def test_hoa_don_som_hon_30_phut_khong_tinh(self):
        self.assertEqual(self.ghep(["15:40"])["p0"], (None, "chua_ro"))  # H4 15:00 = 40' trước

    def test_nhan_tren_anh_thang_gio(self):
        self.c.execute("UPDATE visits SET ten_kh='Lê Thị Tâm' WHERE code='H4'")
        self.c.execute("INSERT INTO photos (id,ngay,thoi_gian,ten_file,chu_thich,ocr) VALUES"
                       " ('q','2026-09-05','2026-09-05T09:45:00','IMG.HEIC','','Tâm-laser 5/9/26')")
        A.ghep_ngay(self.c, "2026-09-05")
        self.assertEqual(self.c.execute("SELECT goi_y_hd, do_tin FROM photos").fetchone()[:], ("H4", "chac"))


class TenMotChuLechDichVu(unittest.TestCase):
    """Ca thật 'Thu-pico': 'Thu' ~ đuôi '... Thư' (mài sẹo) trong khi khách 'THU (KH TỰ ĐẾN)' làm pico."""
    def setUp(self):
        self.c = A.ket_noi()
        self.c.execute("DELETE FROM visits")

    def tearDown(self):
        self.c.close()

    def them(self, *ds):
        for code, ten, dv in ds:
            self.c.execute("INSERT INTO visits (code,ngay,ten_kh,dich_vu) VALUES (?,'2026-09-21',?,?)",
                           (code, ten, dv))

    def khop(self, chu):
        return A._khop_nhan(self.c, A.doc_nhan(chu, 2026)[0], "2026-09-21")

    def test_chon_khach_ten_trong_ho_ten_dung_dich_vu(self):
        self.them(("HA", "Phan Ngọc Thư", "Mài viền sẹo"), ("HB", "TRẦN THU (KH TỰ ĐẾN)", "Picolight"))
        hd, d, ly_do = self.khop("Thu-pico 21/9/26")
        self.assertEqual((hd, d), ("HB", 85))
        self.assertIn("dịch vụ", ly_do)

    def test_khong_ai_dung_dich_vu_ha_goi_y(self):  # âm: không nâng 'chắc' khi dịch vụ lệch
        self.them(("HA", "Phan Ngọc Thư", "Mài viền sẹo"))
        self.assertEqual(self.khop("Thu-pico 21/9/26")[:2], ("HA", 40))

    def test_hai_khach_trong_dung_dich_vu_ha_goi_y(self):  # âm: 2 ứng viên khác -> không đoán
        self.them(("HA", "Phan Ngọc Thư", "Mài viền sẹo"), ("HB", "Trần Thu KH TU DEN", "Picolight"),
                  ("HC", "Lê Thu GT", "Pico toàn mặt"))
        # Bỏ ghi chú tên -> 'Trần Thu', 'Lê Thu' cùng đuôi 'thu' + cùng pico -> người chọn (không đoán HA).
        hd, d, ly_do = self.khop("Thu-pico 21/9/26")
        self.assertEqual((hd, d), (None, 0))
        self.assertIn("trùng 2 khách", ly_do)

    def test_dich_vu_khop_giu_chac(self):  # không đổi ca đúng
        self.them(("HA", "Phan Ngọc Thư", "Mài viền sẹo"), ("HB", "TRẦN THU (KH TỰ ĐẾN)", "Picolight"))
        self.assertEqual(self.khop("Thu-mai 21/9/26")[:2], ("HA", 85))


class LanTheoDot(unittest.TestCase):
    def setUp(self):
        self.c = A.ket_noi()
        self.c.execute("DELETE FROM visits")
        self.c.execute("DELETE FROM photos")
        for code, ten, gio in [("K1", "Lê Thị Tâm", "10:00"), ("K2", "Võ Ngọc Bích", "10:05"),
                               ("K3", "Khach Ba", "16:00")]:
            self.c.execute("INSERT INTO visits (code,ngay,gio,ten_kh,dich_vu) VALUES (?,?,?,?,?)",
                           (code, "2026-09-07", gio, ten, "Laser"))

    def tearDown(self):
        self.c.close()

    def ghep(self, anh):
        for pid, gio, ocr in anh:
            self.c.execute("INSERT INTO photos (id,ngay,thoi_gian,ten_file,chu_thich,ocr) VALUES (?,?,?,?,?,?)",
                           (pid, "2026-09-07", f"2026-09-07T{gio}", "IMG.HEIC", "", ocr))
        A.ghep_ngay(self.c, "2026-09-07")
        return {r[0]: (r[1], r[2]) for r in self.c.execute("SELECT id, goi_y_hd, do_tin FROM photos")}

    def test_mot_khach_ca_dot_lan_nhu_cu(self):
        r = self.ghep([("a", "10:00:00", "Tâm-laser 7/9/26"), ("b", "10:06:00", ""), ("c", "10:12:00", "")])
        self.assertEqual(r["a"], ("K1", "chac"))
        self.assertEqual((r["b"], r["c"]), (("K1", "goi_y"), ("K1", "goi_y")))

    def test_hai_khach_mot_dot_lan_theo_chuoi_chup_lien(self):
        r = self.ghep([("a", "10:00:00", "Tâm-laser 7/9/26"), ("b", "10:00:30", ""),
                       ("c", "10:07:00", "Bích-laser 7/9/26"), ("d", "10:07:40", ""),
                       ("e", "10:04:00", "")])  # e lẻ loi giữa 2 khách -> người chọn
        self.assertEqual(r["b"], ("K1", "chac"))  # cùng bộ chụp liền với nhãn chắc
        self.assertEqual(r["d"], ("K2", "chac"))
        self.assertEqual(r["e"], (None, "chua_ro"))

    def test_chuoi_dai_van_lan(self):  # mỗi ảnh cách ảnh trước 50s -> cả loạt là 1 khách
        r = self.ghep([("a", "10:00:00", "Tâm-laser 7/9/26")] +
                      [(f"x{i}", f"10:0{(i * 50) // 60}:{(i * 50) % 60:02d}", "") for i in range(1, 6)] +
                      [("c", "10:12:00", "Bích-laser 7/9/26")])
        self.assertEqual(r["x5"], ("K1", "chac"))  # cách a 4'10" nhưng cùng bộ chụp liền 6 ảnh

    def test_quang_trong_qua_60_giay_cat_chuoi(self):  # âm: soát thật 415201A3, BB0D2F19
        r = self.ghep([("a", "10:00:00", "Tâm-laser 7/9/26"), ("b", "10:00:40", ""),
                       ("x", "10:02:20", ""), ("y", "10:02:30", ""),  # trống 100s sau b = đổi khách
                       ("c", "10:09:00", "Bích-laser 7/9/26")])
        self.assertEqual(r["b"], ("K1", "chac"))
        self.assertEqual((r["x"], r["y"]), ((None, "chua_ro"), (None, "chua_ro")))

    def test_neo_nhan_chua_khop_chan_lan_ca_dot(self):  # âm: nhãn người khác không khớp HĐ
        r = self.ghep([("a", "10:00:00", "Tâm-laser 7/9/26"), ("b", "10:01:00", ""),
                       ("c", "10:08:00", "Quang-laser 7/9/26"), ("d", "10:09:00", ""),
                       ("e", "10:14:00", "")])
        self.assertEqual(r["b"], ("K1", "chac"))  # cùng bộ chụp liền với a
        self.assertEqual(r["c"], (None, "chua_ro"))
        self.assertEqual(r["d"], (None, "chua_ro"))  # gần c (chưa khớp) -> không đoán
        self.assertEqual(r["e"], (None, "chua_ro"))  # cách c 6' -> quá xa

    def test_neo_xa_hon_3_phut_khong_lan(self):  # âm
        r = self.ghep([("a", "10:00:00", "Tâm-laser 7/9/26"), ("b", "10:10:00", "Quang-laser 7/9/26"),
                       ("x", "10:05:00", "")])
        self.assertEqual(r["x"], (None, "chua_ro"))

    def test_dot_co_nhan_khong_dung_luat_gio(self):  # âm: luật 1 HĐ gần giờ chỉ cho đợt không nhãn
        r = self.ghep([("a", "16:00:00", "Quang-laser 7/9/26"), ("b", "16:10:00", "")])
        self.assertEqual(r["b"], (None, "chua_ro"))

    def test_dot_khong_nhan_van_dung_luat_gio(self):
        self.assertEqual(self.ghep([("a", "16:02:00", "")])["a"], ("K3", "goi_y"))

    def test_trung_giay_khong_nhan_lan_dot(self):
        r = self.ghep([("a", "10:00:00", "Tâm-laser 7/9/26")] +
                      [(f"t{i}", "10:02:30", "") for i in range(3)])
        self.assertEqual(r["a"], ("K1", "chac"))
        self.assertEqual({r[f"t{i}"] for i in range(3)}, {(None, "chua_ro")})

    def test_trung_giay_khong_dung_luat_gio(self):
        r = self.ghep([(f"t{i}", "16:02:30", "") for i in range(5)])
        self.assertEqual({r[f"t{i}"] for i in range(5)}, {(None, "chua_ro")})
        self.assertIn("trùng từng giây", self.c.execute("SELECT ly_do FROM photos WHERE id='t0'").fetchone()[0])

    def test_trung_giay_van_khop_bang_nhan_cua_no(self):
        r = self.ghep([("t0", "16:02:30", "Tâm-laser 7/9/26"), ("t1", "16:02:30", ""), ("t2", "16:02:30", "")])
        self.assertEqual(r["t0"], ("K1", "chac"))
        self.assertEqual(r["t1"], (None, "chua_ro"))

    def test_hai_anh_trung_giay_van_tin(self):  # âm: 2 ảnh chụp liền nhau là chuyện thường
        r = self.ghep([("a", "10:00:00", "Tâm-laser 7/9/26"), ("b", "10:02:30", ""), ("c", "10:02:30", "")])
        self.assertEqual((r["b"], r["c"]), (("K1", "goi_y"), ("K1", "goi_y")))


class BoChup(unittest.TestCase):
    """Luật bộ chụp: mỗi khách chụp mặt 5 kiểu liên tục, nhãn chỉ ở tấm chính diện (dữ liệu bịa)."""

    def setUp(self):
        self.c = A.ket_noi()
        self.c.execute("DELETE FROM visits")
        self.c.execute("DELETE FROM photos")
        for code, ten, gio in [("K1", "Lê Thị Tâm", "10:00"), ("K2", "Võ Ngọc Bích", "10:05")]:
            self.c.execute("INSERT INTO visits (code,ngay,gio,ten_kh,dich_vu) VALUES (?,?,?,?,?)",
                           (code, "2026-09-07", gio, ten, "Laser"))

    def tearDown(self):
        self.c.close()

    def ghep(self, anh, xn=None):
        for pid, giay, ocr in anh:
            gio = f"10:{giay // 60:02d}:{giay % 60:02d}"
            self.c.execute("INSERT INTO photos (id,ngay,thoi_gian,ten_file,chu_thich,ocr,xn_hd) VALUES (?,?,?,?,?,?,?)",
                           (pid, "2026-09-07", f"2026-09-07T{gio}", "IMG.HEIC", "", ocr, (xn or {}).get(pid)))
        A.ghep_ngay(self.c, "2026-09-07")
        return {r[0]: (r[1], r[2], r[3]) for r in self.c.execute("SELECT id, goi_y_hd, do_tin, ly_do FROM photos")}

    @staticmethod
    def bo(n, nhan, buoc=15, dau=0):  # n ảnh liền cách nhau `buoc` giây; nhan = {vị trí: chữ}
        return [(f"p{i}", dau + i * buoc, nhan.get(i, "")) for i in range(n)]

    def test_bo_5_mot_nhan_chac_ca_bo(self):
        r = self.ghep(self.bo(5, {0: "Tâm-laser 7/9/26"}))
        self.assertEqual({r[f"p{i}"][:2] for i in range(5)}, {("K1", "chac")})
        self.assertIn("cùng bộ chụp liền 5 ảnh với ảnh có nhãn 'Tâm-laser", r["p3"][2])

    def test_bo_5_co_nhan_khach_khac_khong_nang(self):  # âm
        r = self.ghep(self.bo(5, {0: "Tâm-laser 7/9/26", 3: "Bích-laser 7/9/26"}))
        self.assertEqual((r["p0"][:2], r["p3"][:2]), (("K1", "chac"), ("K2", "chac")))
        self.assertNotIn("chac", {r[f"p{i}"][1] for i in (1, 2, 4)})

    def test_bo_5_co_nhan_chua_khop_khong_nang(self):  # âm: nhãn người không có HĐ
        r = self.ghep(self.bo(5, {0: "Tâm-laser 7/9/26", 4: "Quang-laser 7/9/26"}))
        self.assertNotIn("chac", {r[f"p{i}"][1] for i in (1, 2, 3)})

    def test_quang_trong_90_giay_thanh_2_bo(self):  # âm
        r = self.ghep(self.bo(3, {0: "Tâm-laser 7/9/26"}) + [("x0", 30 + 90, ""), ("x1", 135, "")])
        self.assertEqual({r[f"p{i}"][:2] for i in range(3)}, {("K1", "chac")})
        self.assertNotIn("chac", {r["x0"][1], r["x1"][1]})

    def test_trung_giay_khong_nang(self):  # âm: giờ nhập/lưu, không phải giờ chụp
        r = self.ghep([("a", 0, "Tâm-laser 7/9/26")] + [(f"t{i}", 20, "") for i in range(3)])
        self.assertEqual({r[f"t{i}"][1] for i in range(3)}, {"chua_ro"})

    def test_bo_10_hai_nhan_cung_hd_chac_ca_bo(self):
        r = self.ghep(self.bo(10, {0: "Tâm-laser 7/9/26", 5: "Tâm-laser 7/9/26"}))
        self.assertEqual({r[f"p{i}"][:2] for i in range(10)}, {("K1", "chac")})

    def test_bo_10_hai_nhan_khac_khach_tach_goi_y(self):
        anh = self.bo(10, {0: "Tâm-laser 7/9/26", 5: "Bích-laser 7/9/26"})
        anh[4:] = [(pid, giay + 40, ocr) for pid, giay, ocr in anh[4:]]  # nghỉ dài nhất giữa p3 và p4
        r = self.ghep(anh)
        self.assertEqual({r[f"p{i}"][:2] for i in (1, 2, 3)}, {("K1", "goi_y")})
        self.assertEqual({r[f"p{i}"][:2] for i in (4, 6, 7, 8, 9)}, {("K2", "goi_y")})
        self.assertIn("tách bộ dài theo quãng nghỉ", r["p4"][2])

    def test_bo_8_mot_nhan_chi_goi_y(self):  # âm: khách sau có thể không viết nhãn
        r = self.ghep(self.bo(8, {0: "Tâm-laser 7/9/26"}))
        self.assertEqual(r["p0"][:2], ("K1", "chac"))
        self.assertEqual({r[f"p{i}"][:2] for i in range(1, 8)}, {("K1", "goi_y")})

    def test_bo_dai_anh_xa_nhan_chi_goi_y(self):  # âm: đuôi bộ dài cách nhãn gần nhất > 6 tấm
        r = self.ghep(self.bo(14, {0: "Tâm-laser 7/9/26", 5: "Tâm-laser 7/9/26"}))
        self.assertEqual(r["p11"][:2], ("K1", "chac"))
        self.assertEqual((r["p12"][:2], r["p13"][:2]), (("K1", "goi_y"), ("K1", "goi_y")))

    def test_nguoi_duyet_hd_khac_chan_nang(self):  # âm: người đã chọn HĐ khác cho 1 ảnh trong bộ
        r = self.ghep(self.bo(5, {0: "Tâm-laser 7/9/26"}), xn={"p4": "K2"})
        self.assertNotIn("chac", {r[f"p{i}"][1] for i in (1, 2, 3, 4)})

    def test_khong_neo_chac_giu_luat_cu(self):  # âm: nhãn chỉ khớp một phần tên (50)
        r = self.ghep(self.bo(5, {0: "Laser Tâm-laser 7/9/26"}))
        self.assertNotIn("chac", {r[f"p{i}"][1] for i in range(5)})
        self.assertEqual({r[f"p{i}"][:2] for i in range(5)}, {("K1", "goi_y")})  # không sót tấm nghiêng

    def test_bo_dai_neo_goi_y_khong_sot(self):  # bộ 9 neo gợi ý: không chắc nhưng cả bộ gợi ý
        r = self.ghep(self.bo(9, {0: "Laser Tâm-laser 7/9/26"}, buoc=50))
        self.assertEqual({r[f"p{i}"][:2] for i in range(9)}, {("K1", "goi_y")})

    def test_bo_neo_goi_y_co_nhan_khac_khong_lan_ca_bo(self):  # âm: neo gợi ý + nhãn chưa khớp
        r = self.ghep(self.bo(5, {0: "Laser Tâm-laser 7/9/26", 4: "Quang-laser 7/9/26"}))
        self.assertNotIn("chac", {r[f"p{i}"][1] for i in range(5)})
        self.assertNotIn("cùng bộ chụp liền", r["p3"][2] or "")


    # --- e25e7d9 soát: ảnh nhân đôi (2 bản cùng 1 giây) đếm 1 tư thế; bộ dài 1 nhãn cắt tại quãng nghỉ ---
    @staticmethod
    def doi(n, nhan, buoc=5, dau=0):  # n tư thế, mỗi tư thế 2 bản cùng giây; nhan = {tư thế: chữ} (cả 2 bản)
        return [(f"p{i}{b}", dau + i * buoc, nhan.get(i, "")) for i in range(n) for b in "ab"]

    def test_anh_nhan_doi_bo_7_tu_the_chac_ca_bo(self):  # 14 ảnh = 7 tư thế, nhãn ở 2 bản tấm đầu
        r = self.ghep(self.doi(7, {0: "Tâm-laser 7/9/26"}))
        self.assertEqual({v[:2] for v in r.values()}, {("K1", "chac")})

    def test_anh_nhan_doi_bo_dai_1_nhan_khong_chac(self):  # âm: 2 bản cùng giây = 1 nhãn, không phải 2
        r = self.ghep(self.doi(10, {0: "Tâm-laser 7/9/26"}))
        self.assertEqual({r[f"p{i}{b}"][:2] for i in range(1, 10) for b in "ab"}, {("K1", "goi_y")})
        self.assertIn("chỉ 1 nhãn", r["p3a"][2])

    def test_anh_nhan_doi_khoang_cach_dem_theo_tu_the(self):  # 2 nhãn cách 5 tư thế, đuôi cách > 6 tư thế
        r = self.ghep(self.doi(14, {0: "Tâm-laser 7/9/26", 5: "Tâm-laser 7/9/26"}))
        self.assertEqual({r[f"p{i}{b}"][:2] for i in range(1, 12) for b in "ab"}, {("K1", "chac")})
        self.assertEqual({r[f"p{i}{b}"][:2] for i in (12, 13) for b in "ab"}, {("K1", "goi_y")})

    def test_bo_dai_1_nhan_cat_quang_nghi_30s(self):  # ca thật 42BA8BE0: khách sau vào sau 31s
        anh = self.doi(5, {0: "Tâm-laser 7/9/26"}, buoc=3) + [(f"q{i}", 12 + 31 + i * 5, "") for i in range(5)]
        r = self.ghep(anh)
        self.assertEqual({r[f"p{i}{b}"][:2] for i in range(5) for b in "ab"}, {("K1", "chac")})
        self.assertEqual({r[f"q{i}"][:2] for i in range(5)}, {("K1", "goi_y")})  # sau quãng nghỉ: chỉ gợi ý
        self.assertIn("quãng nghỉ", r["q0"][2])
        self.assertIn("tách tại quãng nghỉ", r["p2a"][2])

    def test_nghi_truoc_khi_du_5_tu_the_khong_cat(self):  # âm: nghỉ 40s sau 3 tư thế -> không cắt, không chắc
        anh = [(f"p{i}", i * 5, "Tâm-laser 7/9/26" if i == 0 else "") for i in range(3)] + \
              [(f"q{i}", 10 + 40 + i * 5, "") for i in range(7)]
        r = self.ghep(anh)
        self.assertNotIn("chac", {r[x][1] for x in r if x != "p0"})

    def test_bo_ngan_nghi_49s_van_chac(self):  # ca thật 42F8E2B3: đổi ngồi->nằm nghỉ 49s, bộ 7 tư thế 1 khách
        anh = [(f"p{i}", i * 10, "Tâm-laser 7/9/26" if i == 0 else "") for i in range(5)] + \
              [("q0", 40 + 49, ""), ("q1", 40 + 49 + 8, "")]
        r = self.ghep(anh)
        self.assertEqual({v[:2] for v in r.values()}, {("K1", "chac")})

    def test_phan_co_nhan_van_dai_khong_chac(self):  # âm: cắt xong phần có nhãn vẫn 9 tư thế -> gợi ý
        anh = self.bo(9, {0: "Tâm-laser 7/9/26"}, buoc=5) + [(f"q{i}", 40 + 31 + i * 5, "") for i in range(5)]
        r = self.ghep(anh)
        self.assertNotIn("chac", {r[x][1] for x in r if x != "p0"})

class LechDichVu(unittest.TestCase):
    """Soát 8b3c1c8: nhãn có mã dịch vụ không khớp HĐ nào của khách được chọn (dữ liệu bịa)."""

    def setUp(self):
        self.c = A.ket_noi()
        self.c.execute("DELETE FROM visits")
        self.c.execute("DELETE FROM photos")
        for code, ngay, gio, ma, ten, dv in [
            ("A1", "2026-09-28", "10:00", "KA", "Nguyễn Thị Quyên", "Mặt nạ"),
            ("A2", "2026-09-28", "10:20", "KA", "Nguyễn Thị Quyên", "Điện di"),
            ("B1", "2026-09-29", "09:00", "KB", "Trần Quyên", "LASER FRACTIONAL"),
            ("C1", "2026-09-28", "11:00", "KC", "Phạm Văn Đông", "Laser Pico"),
        ]:
            self.c.execute("INSERT INTO visits (code,ngay,gio,ma_kh,ten_kh,dich_vu) VALUES (?,?,?,?,?,?)",
                           (code, ngay, gio, ma, ten, dv))

    def tearDown(self):
        self.c.close()

    def khop(self, chu, ngay="2026-09-28"):
        return A._khop_nhan(self.c, A.doc_nhan(chu, 2026)[0], ngay)

    def ghep(self, anh):
        for pid, gio, ocr in anh:
            self.c.execute("INSERT INTO photos (id,ngay,thoi_gian,ten_file,chu_thich,ocr) VALUES (?,?,?,?,?,?)",
                           (pid, "2026-09-28", f"2026-09-28T{gio}", "IMG.HEIC", "", ocr))
        A.ghep_ngay(self.c, "2026-09-28")
        return {r[0]: (r[1], r[2], r[3]) for r in self.c.execute("SELECT id, goi_y_hd, do_tin, ly_do FROM photos")}

    def test_hd_ngay_ke_cho_khach_dung_dich_vu(self):
        hd, d, ly_do = self.khop("Quyên-fractional 28/9/26")
        self.assertEqual((hd, d), ("B1", 50))
        self.assertIn("HĐ ngày kế", ly_do)

    def test_khong_hd_ngay_ke_thi_40_khong_lan(self):  # âm: không gợi ý 50 cho khách lệch dịch vụ
        self.c.execute("DELETE FROM visits WHERE code='B1'")
        hd, d, ly_do = self.khop("Quyên-fractional 28/9/26")
        self.assertEqual((hd, d), ("A1", 40))
        self.assertIn("khớp tên nhưng lệch dịch vụ", ly_do)
        r = self.ghep([("a", "10:00:00", "Quyên-fractional 28/9/26"), ("b", "10:00:15", ""),
                       ("c", "10:00:30", ""), ("d", "10:05:00", "")])
        self.assertEqual(r["a"][:2], ("A1", "goi_y"))
        self.assertEqual({r[x][:2] for x in "bcd"}, {(None, "chua_ro")})  # không lan đợt, không kéo bộ

    def test_ghep_bo_theo_hd_ngay_ke_chi_goi_y(self):
        r = self.ghep([("a", "10:00:00", "Quyên-fractional 28/9/26"), ("b", "10:00:15", "")])
        self.assertEqual(r["a"][:2], ("B1", "goi_y"))
        self.assertEqual(r["b"][:2], ("B1", "goi_y"))
        self.assertNotIn("A1", {r[x][0] for x in "ab"})

    def test_ma_chung_coi_nhu_khong_dich_vu(self):
        self.assertEqual(self.khop("Đông-tri 28/9/26")[:2], ("C1", 85))  # 'tri' không làm lệch
        self.assertEqual(self.khop("Đông-tiem 28/9/26")[:2], ("C1", 85))
        self.assertEqual(self.khop("Quyên-test 28/9/26")[:2], ("A1", 50))  # 2 HĐ cùng khách: như cũ

    def test_ma_chung_khop_van_chon_hd(self):  # 'tiem' khớp HĐ tiêm -> vẫn dùng để chọn
        self.c.execute("INSERT INTO visits (code,ngay,gio,ma_kh,ten_kh,dich_vu) VALUES "
                       "('A3','2026-09-28','10:30','KA','Nguyễn Thị Quyên','Tiêm HA')")
        self.assertEqual(self.khop("Quyên-tiem 28/9/26")[:2], ("A3", 85))

    def test_ma_ocr_sai_1_chu_khong_ha_40(self):
        self.assertEqual(self.khop("Đông-picc 28/9/26")[:2], ("C1", 50))
        self.assertEqual(self.khop("Đông-botox 28/9/26")[:2], ("C1", 40))  # âm: lệch thật

    def test_dich_vu_khop_khong_doi(self):  # nhiều HĐ cùng khách, mã khớp 1 HĐ -> như cũ
        self.assertEqual(self.khop("Quyên-csd 28/9/26")[:2], ("A2", 85))


    def test_ma_mot_chu_coi_nhu_khong_dich_vu(self):  # 'Đông-c' không hạ 40, không lọc theo 'C'
        self.assertEqual(self.khop("Đông-c 28/9/26")[:2], ("C1", 85))
        self.assertEqual(self.khop("Đông-M 28/9/26")[:2], ("C1", 85))

    def test_bao_hanh_nam_khong_khop_pico(self):  # ca thật C0DC564F: HĐ ngày kế '( BH 2 NĂM )' không phải nám
        self.c.execute("INSERT INTO visits (code,ngay,gio,ma_kh,ten_kh,dich_vu) VALUES "
                       "('D0','2026-09-28','14:00','KD','Đặng Thị Nghĩa','BLEMISH CREAM 10g'),"
                       "('D1','2026-09-27','14:00','KD','Đặng Thị Nghĩa','COMBO TRIỆT LÔNG MẶT ( BH 2 NĂM )')")
        hd, d, ly_do = self.khop("Nghĩa-pico 28/9/26")
        self.assertEqual((hd, d), ("D0", 40))
        self.assertNotIn("HĐ ngày kế", ly_do)

    def test_xoa_nhan_lay_ma_chu_sau(self):  # ca thật F77067E4: 'xoá nhăn' -> botox, không ăn 'xóa xăm'
        self.c.execute("INSERT INTO visits (code,ngay,gio,ma_kh,ten_kh,dich_vu) VALUES "
                       "('H0','2026-09-28','09:00','KH','Trần Thị Hồng','TIÊM BOTOX XÓA NHĂN 1 VÙNG'),"
                       "('H1','2026-09-28','09:30','KH2','Lê Thị Hồng','Laser xóa xăm')")
        self.assertEqual(self.khop("Chị Hồng-xóá nhăn 28/9/26")[:2], ("H0", 85))
        self.c.execute("DELETE FROM visits WHERE code='H0'")
        hd, d, _ = self.khop("Chị Hồng-xóá nhăn 28/9/26")  # âm: chỉ còn khách xoá xăm -> lệch, 40
        self.assertEqual((hd, d), ("H1", 40))


class MaDongTuVaBaoHanh(unittest.TestCase):
    def test_xoa_la_dong_tu(self):
        self.assertEqual(A.doc_nhan("Lan-xoá nốt ruồi 9/10/26", 2026)[0]["ma_dv"], "not")
        self.assertEqual(A.doc_nhan("Lan-xoa xăm 9/10/26", 2026)[0]["ma_dv"], "xam")
        self.assertEqual(A.doc_nhan("Lan-xoá 9/10/26", 2026)[0]["ma_dv"], "xoa")  # không có chữ sau: giữ
        self.assertTrue(A._dv_khop("not", "Laser nốt ruồi lần lẻ"))
        self.assertTrue(A._dv_khop("xam", "Laser xóa xăm"))
        self.assertTrue(A._dv_khop("nhan", "DẶM BOTOX XÓA NHĂN"))
        self.assertTrue(A._dv_chung("xoa"))

    def test_xoa_khong_khop_xoa_xam(self):  # âm
        self.assertFalse(A._dv_khop("xoa", "Laser xóa xăm"))
        self.assertFalse(A._dv_khop("xoa", "Xóa vein mặt lần lẻ"))
        self.assertFalse(A._dv_khop("not", "Laser xóa xăm"))
        self.assertFalse(A._dv_khop("nhan", "Laser xóa xăm"))

    def test_bao_hanh_nam(self):
        self.assertFalse(A._dv_khop("pico", "COMBO TRIỆT LÔNG NÁCH ( BH 2 NĂM )"))
        self.assertFalse(A._dv_khop("pico", "Triệt lông bảo hành 1 năm"))
        self.assertTrue(A._dv_khop("pico", "Laser Pico trị nám"))  # nám thật vẫn khớp
        self.assertTrue(A._dv_khop("pico", "Trị nám 5 năm"))  # 'nám' đứng riêng vẫn khớp
        self.assertTrue(A._dv_khop("tln", "COMBO TRIỆT LÔNG NÁCH ( BH 2 NĂM )"))

    def test_nhu_hoa(self):
        self.assertEqual(A.doc_nhan("Lan-peel nhũ 9/10/26", 2026)[0]["ma_dv"], "peel nhu")
        for ma in ("nhu", "peel nhu"):
            self.assertTrue(A._dv_khop(ma, "TRỊ THÂM NHŨ HOA ( LẦN LẺ )"), ma)
            self.assertTrue(A._dv_khop(ma, "COMBO TRỊ THÂM NHŨ ( 6 LẦN )"), ma)
            self.assertFalse(A._dv_khop(ma, "Peel da mụn lần lẻ"), ma)  # âm
        self.assertEqual(A.doc_nhan("Lan-peel thâm 9/10/26", 2026)[0]["ma_dv"], "peel")  # như cũ

    def test_ocr_the_la_tham(self):
        self.assertEqual(A.doc_nhan("Lan- thể 9/10/26", 2026)[0]["ma_dv"], "the")
        self.assertTrue(A._dv_khop("the", "Trị thâm mụn lần lẻ"))
        self.assertFalse(A._dv_khop("the", "Tiêm botox"))  # âm
        n = A.doc_nhan("Lan the 9/10/26", 2026)  # âm: nhãn không gạch -> 'the' không thành mã dịch vụ
        self.assertTrue(not n or n[0]["ma_dv"] == "")

    def test_ten_nhu_nhan_khong_thanh_ma_o_nhan_khong_gach(self):  # âm: ca thật FCE282A8 'Tâm Như peel'
        n = A.doc_nhan("Tâm Như peel 14/3/26", 2026)[0]
        self.assertEqual((n["ten"], n["ma_dv"]), ("tam nhu", "peel"))
        self.assertEqual(A.doc_nhan("Chi Như 06/07/2026", 2026)[0]["ten"], "chi nhu")
        self.assertEqual(A.doc_nhan("Thành Nhân 06/07/2026", 2026)[0]["ten"], "thanh nhan")

    def test_ma_mot_chu_khong_khop(self):  # âm: 'c' không ăn 'Điện di C'
        self.assertFalse(A._dv_khop("c", "Điện di C sau sẹo"))
        self.assertTrue(A._dv_chung("c"))

class TruocSau(unittest.TestCase):
    def test_doc_chu_sau_truoc(self):
        n = A.doc_nhan("Hoàng Anh- sau filler mắt 7/9/26", 2026)[0]
        self.assertEqual((n["ten"], n["ma_dv"], n["loai"], n["ngay"]), ("hoang anh", "filler", "sau", "2026-09-07"))
        self.assertEqual(A.doc_nhan("Tâm-meso trước 5/10/26", 2026)[0]["loai"], "trước")
        self.assertEqual(A.doc_nhan("Tâm-pico 5/10/26", 2026)[0]["loai"], "")
        self.assertEqual(A.doc_nhan("Tâm-pico 5/10/26 sau", 2026)[0]["loai"], "")  # sau ngày: không tính

    def test_dien_o_truoc_sau_khong_de_nguoi_duyet(self):
        c = A.ket_noi()
        c.execute("DELETE FROM photos")
        c.execute("DELETE FROM visits")
        c.execute("INSERT INTO visits (code,ngay,gio,ten_kh,dich_vu) VALUES ('V','2026-09-07','10:00','Lê Hoàng Anh','Filler')")
        for pid, loai, xn in [("a", None, None), ("b", "trước", None), ("c", None, "V")]:
            c.execute("INSERT INTO photos (id,ngay,thoi_gian,ten_file,chu_thich,ocr,loai_anh,xn_hd) VALUES"
                      " (?, '2026-09-07', '2026-09-07T10:0'||?||':00', 'I.HEIC', '', 'Hoàng Anh- sau filler 7/9/26', ?, ?)",
                      (pid, len(pid), loai, xn))
        A.ghep_ngay(c, "2026-09-07")
        r = dict(c.execute("SELECT id, loai_anh FROM photos").fetchall())
        self.assertEqual(r, {"a": "sau", "b": "trước", "c": None})  # b: người đã chọn; c: đã duyệt
        self.assertEqual(c.execute("SELECT goi_y_hd FROM photos WHERE id='a'").fetchone()[0], "V")
        c.close()


class BangMaDichVu(unittest.TestCase):
    def test_ma_viet_tat_cua_nhan_vien(self):
        for ma, dv in [("co2", "Laser Fractional"), ("co2", "Laser đốt mụn thịt mặt lần lẻ"),
                       ("ha", "Dặm filler làm đầy"), ("csd", "Điện di C sau sẹo"), ("csd", "Peel da mụn lần lẻ"),
                       ("dvm", "Xóa vein mặt lần lẻ"), ("dnr", "Laser nốt ruồi lần lẻ"),
                       ("pico", "Laser đốm nâu lần lẻ"), ("xx", "Laser xóa xăm"), ("gsd", "CSD mụn lần lẻ"),
                       ("sl", "Tiêm sẹo lồi"), ("mv", "Combo cắt sẹo rỗ và mài viền"),
                       ("laserlifi", "Laser Lifting mặt")]:
            self.assertTrue(A._dv_khop(ma, dv), (ma, dv))

    def test_khong_khop_nham(self):  # âm
        for ma, dv in [("xx", "Laser Picolight nám"), ("ha", "Tiêm botox"), ("dvm", "Xóa vein chân"),
                       ("sl", "Điều trị sẹo rỗ"), ("pico", "Tiêm PRP"), ("tt", "Tiêm meso"),
                       ("laserlift", "EYELIFT SERUM")]:
            self.assertFalse(A._dv_khop(ma, dv), (ma, dv))

    def test_bang_nap_duoc(self):
        self.assertIn("co2", A.MA_DV)
        self.assertEqual(A.MA_DV_OCR.get("gsd"), "csd")


class TenCoGhiChu(unittest.TestCase):
    """Tên KiotViet kèm ghi chú '(KH TỰ ĐẾN)', '(EM BS LƯƠNG)', 'KH7332 GT'... (soát 04-08/2026)."""
    def setUp(self):
        self.c = A.ket_noi()
        self.c.execute("DELETE FROM visits")

    def tearDown(self):
        self.c.close()

    def them(self, *ds):
        for code, ten, dv in ds:
            self.c.execute("INSERT INTO visits (code,ngay,ten_kh,dich_vu) VALUES (?,'2026-06-15',?,?)",
                           (code, ten, dv))

    def khop(self, chu):
        return A._khop_nhan(self.c, A.doc_nhan(chu, 2026)[0], "2026-06-15")

    def test_lam_sach_ten(self):
        for goc, sach in [("Trần Thị Hoa (EM BS LƯƠNG)", "tran thi hoa"),
                          ("Phạm Văn Vương (KH TỰ ĐẾN)", "pham van vuong"),
                          ("Lê Thị Dung (BS LƯƠNG)", "le thi dung"),
                          ("Đoàn Thanh Vy KH7332 GT", "doan thanh vy"),
                          ("Ngô Mai GT", "ngo mai"), ("Võ Lan 6366GT", "vo lan"),
                          ("Hồ Ngọc Hà (KH7332 GT", "ho ngoc ha"),  # thiếu ngoặc đóng
                          ("Lý Thu Trang NGƯỜI QUEN BS LUONG", "ly thu trang"),
                          ("Đinh Đức Dũng", "dinh duc dung"), ("(KH TỰ ĐẾN)", "kh tu den")]:
            self.assertEqual(A.ten_sach(goc), sach, goc)

    def test_ca_that_vuong_khong_lech_sang_luong(self):
        # Ca thật: 'A Vương-peel' từng ghép vào khách nữ '(EM BS LƯƠNG)' qua lệch 1 chữ vuong~luong.
        self.them(("HN", "Trần Thị Hoa (EM BS LƯƠNG)", "Tiêm HA môi"),
                  ("HV", "Phạm Văn Vương (KH TỰ ĐẾN)", "Peel da mụn lần lẻ"))
        hd, d, ly_do = self.khop("A Vương-peel 15/6/26")
        self.assertEqual((hd, d), ("HV", 85))

    def test_vuong_khong_con_khach_nao_thi_khong_doan(self):  # âm: không lệch 1 chữ sang ghi chú 'LƯƠNG'
        self.them(("HN", "Trần Thị Hoa (EM BS LƯƠNG)", "Peel da mụn lần lẻ"))
        self.assertIsNone(self.khop("A Vương-peel 15/6/26")[0])

    def test_ca_that_dung_tach_bang_dich_vu(self):
        # Ca thật: 'C Dung-mv'; HĐ 'ĐINH ĐỨC DŨNG' điện di C, '... DUNG (BS LƯƠNG)' cắt sẹo + mài viền.
        self.them(("H1", "ĐINH ĐỨC DŨNG", "Điện di C"),
                  ("H2", "LÊ THỊ DUNG (BS LƯƠNG)", "Combo cắt sẹo + mài viền"))
        hd, d, ly_do = self.khop("C Dung-mv 15/6/26")
        self.assertEqual((hd, d), ("H2", 85))
        self.assertIn("dịch vụ", ly_do)

    def test_trung_ten_khong_dau_chon_theo_dau_chi_goi_y(self):
        self.them(("H1", "ĐINH ĐỨC DŨNG", "Peel da"), ("H2", "LÊ THỊ DUNG (BS LƯƠNG)", "CSD mụn"))
        self.assertEqual(self.khop("C Dung-csd 15/6/26")[:2], ("H2", 50))
        self.assertEqual(self.khop("C Dũng-csd 15/6/26")[:2], ("H1", 50))

    def test_trung_ten_cung_dau_nguoi_chon(self):  # âm: cùng dấu, cùng dịch vụ -> không đoán
        self.them(("H1", "Lê Dung", "CSD"), ("H2", "Võ Dung (KH TỰ ĐẾN)", "CSD mụn"))
        self.assertIsNone(self.khop("Dung-csd 15/6/26")[0])

    def test_dau_khong_ke_vi_tri_bo_dau(self):  # 'hoà' = 'hòa' -> vẫn trùng, người chọn
        self.them(("H1", "Nguyễn Thị Hòa", "CSD"), ("H2", "Lý Thị Hoà", "CSD"))
        self.assertIsNone(self.khop("Hoà-csd 15/6/26")[0])

    def test_xung_ho_giu_khi_khach_ten_dung_nhu_vay(self):  # 'Anh Thư' là tên, không phải xưng hô
        self.them(("H1", "Nguyễn Anh Thư", "CSD"), ("H2", "Lê Minh Thư", "CSD"))
        self.assertEqual(self.khop("Anh Thư-csd 15/6/26")[:2], ("H1", 85))

    def test_xung_ho_giu_khi_ho_ten_chua_du_chu(self):  # 'Cô Hạnh' ~ khách 'Lê Cô Hạnh Mỹ'
        self.them(("H1", "Lê Cô Hạnh Mỹ", "Filler"), ("H2", "Trần Hạnh Như", "Filler"))
        self.assertEqual(self.khop("Cô Hạnh-filler 15/6/26")[:2], ("H1", 85))

    def test_nhan_ghi_dung_chu_ghi_chu(self):  # nhân viên làm dịch vụ: tên KiotViet '... KTV'
        self.them(("H1", "Nguyễn Thị Hoa KTV", "Xóa vein mặt lần lẻ"), ("H2", "Lê Thị Hoa", "Peel"))
        self.assertEqual(self.khop("KTV-dvm 15/6/26")[:2], ("H1", 85))

    def test_ten_goi_trong_ngoac(self):  # 'X (LISA)': ngoặc là tên gọi, không phải ghi chú
        self.them(("H1", "Nguyễn Thị Hoa (LISA)", "Xóa vein mặt lần lẻ"), ("H2", "Lê Mai (KH TỰ ĐẾN)", "CSD"))
        self.assertEqual(self.khop("Lisa-dvm 15/6/26")[:2], ("H1", 85))
        self.assertEqual(self.khop("Lisa-csd 15/6/26")[:2], ("H1", 40))  # lệch dịch vụ -> gợi ý 40, không làm neo
        self.assertEqual(A._bi_danh("Lê Mai (KH TỰ ĐẾN) (BS LƯƠNG) (MẪU NÁM 9)"), [])

    def test_ten_trung_chu_ghi_chu_khong_khop(self):  # âm: khách tên Lương không ăn '(BS LƯƠNG)'
        self.them(("H1", "Lê Thị Hoa (BS LƯƠNG)", "CSD"), ("H2", "Trần Hoa (EM BS LUONG)", "CSD"))
        self.assertIsNone(self.khop("Lương-csd 15/6/26")[0])

    def test_xung_ho_mot_chu_khong_bo(self):  # 'Anh-csd' = khách tên Anh
        self.them(("H1", "Võ Minh Anh", "CSD"))
        self.assertEqual(self.khop("Anh-csd 15/6/26")[:2], ("H1", 85))

    def test_lech_dich_vu_tim_khach_khac_ca_khi_khop_mot_phan(self):
        # Nhãn có chữ thừa ('Laser Thu') -> k < len(w): vẫn tìm khách khác đúng dịch vụ, chỉ gợi ý.
        self.them(("HA", "Phan Ngọc Thư", "Mài viền sẹo"), ("HB", "TRẦN THU (KH TỰ ĐẾN)", "Picolight"))
        self.c.execute("DELETE FROM visits WHERE code='HB'")
        self.them(("HB", "Trần Thu Hiền", "Picolight"))
        hd, d, ly_do = self.khop("Laser Thu-pico 15/6/26")
        self.assertEqual((hd, d), ("HB", 50))
        self.assertIn("một phần", ly_do)

    def test_diem_dung_ten_da_lam_sach(self):
        v = {"sdt": "", "ma_kh": "KH000001", "ten_kh": "Phạm Văn Vương (KH TỰ ĐẾN)"}
        self.assertEqual(A._diem(v, "pham van vuong peel", "")[0], 80)
        self.assertEqual(A._diem(v, "kh tu den", "")[0], 0)  # âm: chữ ghi chú không phải tên


class NhanKhongGach(unittest.TestCase):
    def test_doc_nhan_khong_gach(self):
        n = A.doc_nhan("Cheng wei 13/7/26", 2026)
        self.assertEqual([(x["ten"], x["ma_dv"], x["ngay"], x["gach"]) for x in n],
                         [("cheng wei", "", "2026-07-13", False)])
        n = A.doc_nhan("Thanh seo 13/7/26", 2026)[0]
        self.assertEqual((n["ten"], n["ma_dv"]), ("thanh", "seo"))
        self.assertEqual(A.doc_nhan("Thu Ha 13/7/26", 2026)[0]["ten"], "thu ha")  # 'ha' = tên Hà

    def test_khong_phai_nhan(self):  # âm
        for chu in ["6/10/26", "Doctor Laser 1/10/26", "HSD 13/7/26", "Het han 13/7/27",
                    "Pico 13/7/26", "C 13/7/26", "Thanh 13/7/1990", "Thanh 13/7", "Lan 32/7/26"]:
            self.assertEqual(A.doc_nhan(chu, 2026), [], chu)

    def test_co_nhan_gach_thi_bo_qua_dang_khong_gach(self):
        ds = A.doc_nhan("Tam-meso mắt 5/10/26", 2026)
        self.assertEqual([(n["ten"], n["gach"]) for n in ds], [("tam", True)])

    def setUp(self):
        self.c = A.ket_noi()
        self.c.execute("DELETE FROM visits")
        self.c.execute("DELETE FROM photos")
        for code, ten, gio in [("W1", "Wu Cheng Wei", "10:00"), ("W2", "Lê Văn Bảo", "10:10"),
                               ("W3", "Trần Minh Khoa", "16:00")]:
            self.c.execute("INSERT INTO visits (code,ngay,gio,ten_kh,dich_vu) VALUES (?,'2026-07-13',?,?,'CSD')",
                           (code, gio, ten))

    def tearDown(self):
        self.c.close()

    def khop(self, chu):
        return A._khop_nhan(self.c, A.doc_nhan(chu, 2026)[0], "2026-07-13")

    def test_khop_ten_trong_ho_ten_chi_goi_y(self):
        hd, d, ly_do = self.khop("Cheng wei 13/7/26")
        self.assertEqual((hd, d), ("W1", 50))
        self.assertIn("không có gạch", ly_do)

    def test_mot_khach_hai_hoa_don_chon_som_nhat(self):  # ca thật 6EAABB53: dịch vụ 14:03 + mua kem 16:46
        self.c.execute("INSERT INTO visits (code,ngay,gio,ma_kh,ten_kh,dich_vu) VALUES"
                       " ('S2','2026-07-13','16:46','KH9','Lý Gia Hân (BS LƯƠNG)','Kem rửa mặt'),"
                       " ('S1','2026-07-13','14:03','KH9','Lý Gia Hân (BS LƯƠNG)','Điều trị sẹo rỗ')")
        self.assertEqual(self.khop("Gia Hân 13/7/26")[:2], ("S1", 50))

    def test_hai_khach_khac_nhau_cung_ten_nguoi_chon(self):  # âm: khác mã KH -> không đoán
        self.c.execute("INSERT INTO visits (code,ngay,gio,ma_kh,ten_kh,dich_vu) VALUES"
                       " ('S2','2026-07-13','16:46','KH8','Lý Gia Hân','CSD'),"
                       " ('S1','2026-07-13','14:03','KH9','Võ Gia Hân (BS LƯƠNG)','CSD')")
        self.assertIsNone(self.khop("Gia Hân 13/7/26")[0])

    def test_khop_du_ho_ten_moi_chac(self):
        self.assertEqual(self.khop("Le Van Bao 13/7/26")[:2], ("W2", 85))
        self.assertEqual(self.khop("Bao 13/7/26")[:2], ("W2", 50))  # 1 chữ -> chỉ gợi ý

    def test_nhan_khong_gach_chan_luat_gio(self):
        # Ảnh 16:02 có nhãn không gạch tên người không có HĐ -> không được 'chỉ 1 HĐ gần giờ' (W3).
        self.c.execute("INSERT INTO photos (id,ngay,thoi_gian,ten_file,chu_thich,ocr) VALUES"
                       " ('a','2026-07-13','2026-07-13T16:02:00','I.HEIC','','Quang Huy 13/7/26')")
        A.ghep_ngay(self.c, "2026-07-13")
        self.assertEqual(self.c.execute("SELECT goi_y_hd, do_tin FROM photos").fetchone()[:], (None, "chua_ro"))

    def test_chu_chung_khong_chan_luat_gio(self):  # âm: 'Doctor Laser 1/10/26' không phải nhãn
        self.c.execute("INSERT INTO photos (id,ngay,thoi_gian,ten_file,chu_thich,ocr) VALUES"
                       " ('a','2026-07-13','2026-07-13T16:02:00','I.HEIC','','Doctor Laser 13/7/26')")
        A.ghep_ngay(self.c, "2026-07-13")
        self.assertEqual(self.c.execute("SELECT goi_y_hd, do_tin FROM photos").fetchone()[:], ("W3", "goi_y"))


class NeoManhMoiLanCaDot(unittest.TestCase):
    def setUp(self):
        self.c = A.ket_noi()
        self.c.execute("DELETE FROM visits")
        self.c.execute("DELETE FROM photos")
        for code, ten, dv in [("K1", "Lê Thị Tâm", "Laser"), ("K2", "Võ Thị Thanh Trúc", "Laser"),
                              ("K3", "Khách Ba", "Peel")]:
            self.c.execute("INSERT INTO visits (code,ngay,gio,ten_kh,dich_vu) VALUES (?,'2026-08-03',NULL,?,?)",
                           (code, ten, dv))

    def tearDown(self):
        self.c.close()

    def ghep(self, anh):
        for pid, gio, ocr in anh:
            self.c.execute("INSERT INTO photos (id,ngay,thoi_gian,ten_file,chu_thich,ocr) VALUES (?,?,?,?,?,?)",
                           (pid, "2026-08-03", f"2026-08-03T{gio}", "IMG.HEIC", "", ocr))
        A.ghep_ngay(self.c, "2026-08-03")
        return {r[0]: (r[1], r[2], r[3]) for r in self.c.execute("SELECT id, goi_y_hd, do_tin, ly_do FROM photos")}

    def test_neo_50_chi_lan_loat_chup_lien(self):
        r = self.ghep([("a", "10:00:00", "Laser Tâm-laser 3/8/26"), ("b", "10:00:40", ""),
                       ("c", "10:06:00", "")])  # c cách b > 60s: không cùng loạt
        self.assertEqual(r["a"][:2], ("K1", "goi_y"))
        self.assertEqual(r["b"][:2], ("K1", "goi_y"))
        self.assertIn("cùng bộ chụp liền 2 ảnh với ảnh gợi ý", r["b"][2])
        self.assertEqual(r["c"][:2], (None, "chua_ro"))

    def test_neo_manh_van_lan_ca_dot(self):
        r = self.ghep([("a", "10:00:00", "Tâm-laser 3/8/26"), ("c", "10:06:00", "")])
        self.assertEqual(r["c"][:2], ("K1", "goi_y"))
        self.assertEqual(r["c"][2], "cùng đợt chụp với ảnh đã khớp tên")

    def test_mot_phan_ten_khong_chan_nhan_85(self):
        # OCR có 'thanh truc' (khớp một phần tên K2 = 50) và nhãn 'Tâm-laser' (85) -> lấy nhãn.
        r = self.ghep([("a", "10:00:00", "thanh truc. Tâm-laser 3/8/26")])
        self.assertEqual(r["a"][:2], ("K1", "chac"))

    def test_mot_phan_ten_giu_khi_nhan_khong_hon(self):  # âm: nhãn không khớp -> giữ gợi ý 50
        r = self.ghep([("a", "10:00:00", "thanh truc. Quang-laser 3/8/26")])
        self.assertEqual(r["a"][:2], ("K2", "goi_y"))


class MaKhNgan(unittest.TestCase):
    def v(self, ma):
        return {"sdt": "", "ma_kh": ma, "ten_kh": "Khách X"}

    def test_ma_toan_so_ngan_khong_khop_ngay(self):  # âm: KH mã '08' vs nhãn '19/08/26'
        self.assertEqual(A._diem(self.v("08"), A.khong_dau("Lan-pico 19/08/26"), "")[0], 0)
        self.assertEqual(A._diem(self.v("3"), A.khong_dau("Lan-pico 3/10/26"), "")[0], 0)

    def test_ma_chuan_van_khop(self):
        self.assertEqual(A._diem(self.v("KH000123"), A.khong_dau("ghi chú KH000123"), "")[0], 100)
        self.assertEqual(A._diem(self.v("CU-KH000777"), A.khong_dau("CU-KH000777 pico"), "")[0], 100)


if __name__ == "__main__":
    unittest.main()
