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
        self.assertEqual(self.khop("Vy-pico 9/10/26", "2026-10-09")[:2], ("HD8", 50))  # dịch vụ lệch
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
        self.assertEqual(self.khop("Thu-pico 21/9/26")[:2], ("HA", 50))

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
        self.assertEqual(r["b"], ("K1", "goi_y"))
        self.assertEqual(r["d"], ("K2", "goi_y"))
        self.assertEqual(r["e"], (None, "chua_ro"))

    def test_chuoi_dai_van_lan(self):  # mỗi ảnh cách ảnh trước 50s -> cả loạt là 1 khách
        r = self.ghep([("a", "10:00:00", "Tâm-laser 7/9/26")] +
                      [(f"x{i}", f"10:0{(i * 50) // 60}:{(i * 50) % 60:02d}", "") for i in range(1, 6)] +
                      [("c", "10:12:00", "Bích-laser 7/9/26")])
        self.assertEqual(r["x5"], ("K1", "goi_y"))  # cách a 4'10" nhưng cùng loạt liền

    def test_quang_trong_qua_60_giay_cat_chuoi(self):  # âm: soát thật 415201A3, BB0D2F19
        r = self.ghep([("a", "10:00:00", "Tâm-laser 7/9/26"), ("b", "10:00:40", ""),
                       ("x", "10:02:20", ""), ("y", "10:02:30", ""),  # trống 100s sau b = đổi khách
                       ("c", "10:09:00", "Bích-laser 7/9/26")])
        self.assertEqual(r["b"], ("K1", "goi_y"))
        self.assertEqual((r["x"], r["y"]), ((None, "chua_ro"), (None, "chua_ro")))

    def test_neo_nhan_chua_khop_chan_lan_ca_dot(self):  # âm: nhãn người khác không khớp HĐ
        r = self.ghep([("a", "10:00:00", "Tâm-laser 7/9/26"), ("b", "10:01:00", ""),
                       ("c", "10:08:00", "Quang-laser 7/9/26"), ("d", "10:09:00", ""),
                       ("e", "10:14:00", "")])
        self.assertEqual(r["b"], ("K1", "goi_y"))  # gần a
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
        self.assertEqual(self.khop("Lisa-csd 15/6/26")[:2], ("H1", 50))  # lệch dịch vụ -> gợi ý
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
        self.assertIn("lan từ ảnh khớp một phần tên", r["b"][2])
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


if __name__ == "__main__":
    unittest.main()
