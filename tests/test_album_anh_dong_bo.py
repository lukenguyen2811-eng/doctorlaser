"""album_anh.py: album Dịch vụ / Theo tháng / Khách — osascript GIẢ (không chạm app Ảnh thật).

Chạy:  python3 -m unittest tests/test_album_anh_dong_bo.py
"""
import io
import os
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ANH_DB", os.path.join(tempfile.mkdtemp(), "t.db"))
import album_anh as M  # noqa: E402
import anhkhach as A  # noqa: E402


class NhomDichVu(unittest.TestCase):
    def test_seo_loi_khong_vao_seo_ro(self):
        self.assertEqual(M.nhom_dong("TIÊM SẸO LỒI"), "Sẹo lồi")
        self.assertEqual(M.nhom_hd("TIÊM SẸO LỒI"), ["Sẹo lồi"])
        self.assertEqual(M.nhom_dong("COMBO SẸO RỖ NHẸ 2 LẦN"), "Sẹo rỗ")
        self.assertEqual(M.nhom_dong("LASER MÀI VIỀN SẸO RỖ TOÀN MẶT - LẦN LẺ"), "Sẹo rỗ")

    def test_san_pham_cong_no_khong_vao_nhom(self):  # âm
        for d in ["KEM TRỊ THÂM NÁCH UNDERARM COSMESS", "SERUM REVSKIN", "THUỐC NÁM CYSPERA",
                  "THUỐC XỊT HỖ TRỢ ĐT VẾT THƯƠNG HỞ VÀ GIẢM SẸO WOUND", "MẶT NẠ CYSTELASMA ( HỘP )",
                  "BLEMISH CLEAR CREAM _ REVSKIN 10g", "THANH TOÁN CÔNG NỢ VEIN", "ĐẶT CỌC", "EYELIFT SERUM"]:
            self.assertIsNone(M.nhom_dong(d), d)
        self.assertEqual(M.nhom_hd("SERUM REVSKIN | KEM REVITALUX"), [])

    def test_hd_hai_dich_vu_hai_album(self):
        self.assertEqual(M.nhom_hd("LASER PICOLIGHT ( LẦN LẺ ) | TIÊM PRP PREMIUM ( LẦN LẺ ) | SERUM REVSKIN"),
                         ["Laser Pico", "PRP"])

    def test_khong_nuot_nhau(self):
        self.assertEqual(M.nhom_dong("ĐỐT NỐT RUỒI"), "Nốt ruồi")  # không bị CO2 nuốt
        self.assertEqual(M.nhom_dong("TRỊ THÂM NÁCH ( LẦN LẺ )"), "Trị thâm")  # không bị Pico nuốt
        self.assertEqual(M.nhom_dong("TIÊM MESO SKIN BOOSTER (căng bóng, trắng sáng, giảm nám)"),
                         "Meso, Skin booster")  # chữ 'nám' trong ngoặc không kéo sang Pico
        self.assertEqual(M.nhom_dong("COMBO TRIỆT LÔNG NÁCH ( BH 2 NĂM )"), "Triệt lông")  # 'năm' BH ≠ nám
        self.assertEqual(M.nhom_dong("DẶM VEIN MẶT"), "Vein")
        self.assertEqual(M.nhom_dong("ĐIỆN DI SERUM"), "Chăm sóc da, Peel, Điện di")  # dịch vụ, không phải SP

    def test_ten_khach(self):
        self.assertEqual(M.ten_khach("LÊ THỊ DUNG (BS LƯƠNG)"), "Lê Thị Dung")


def chay_gia():
    """subprocess.run giả: ghi lại mọi lệnh osascript, trả id album khi tạo."""
    goi = []

    def run(cmd, **kw):
        goi.append(cmd)
        return types.SimpleNamespace(returncode=0, stdout="ALB/L0/040\n" if cmd[2] == M._TAO else "", stderr="")
    return goi, run


class DongBo(unittest.TestCase):
    def setUp(self):
        c = A.ket_noi()
        for t in ("photos", "visits"):
            c.execute(f"DELETE FROM {t}")
        c.execute("DROP TABLE IF EXISTS da_album")
        hd = [("H1", "2026-08-30", "KH000001", "TRẦN THỊ BỊA (BS LƯƠNG)", "0901111111", "TIÊM SẸO LỒI"),
              ("H2", "2026-09-02", "KH000001", "TRẦN THỊ BỊA", "0901111111",
               "LASER PICOLIGHT ( LẦN LẺ ) | TIÊM PRP PREMIUM | SERUM REVSKIN"),
              ("H3", "2026-09-02", "CU-KH000777", "Khách Cũ", "0902222222", "KEM REVITALUX"),
              ("H4", "2026-09-10", "KH000888", "KHÁCH MỚI BỊA", "84902222222", "CSD MỤN"),
              ("H5", "2026-09-11", "KH000999", "Một Lần", "0903333333", "DẶM VEIN MẶT")]
        for code, ngay, ma, ten, sdt, dv in hd:
            c.execute("INSERT INTO visits (code,ngay,gio,ma_kh,ten_kh,sdt,dich_vu) VALUES (?,?,?,?,?,?,?)",
                      (code, ngay, "10:00", ma, ten, sdt, dv))
        # (id, ngày chụp, gợi ý, mức, đã duyệt, loại)
        anh = [("a1", "2026-09-01", "H1", "chac", None, 0),   # chụp 01/09 nhưng HĐ 30/08 -> tháng 08
               ("a2", "2026-09-02", "H2", "chac", None, 0),
               ("a3", "2026-09-02", "H2", "goi_y", None, 0),  # gợi ý chưa duyệt -> không
               ("a4", "2026-09-02", "H2", "chua_ro", None, 0),  # chưa rõ -> không
               ("a5", "2026-09-02", "H2", "chac", None, 1),   # bị loại -> không
               ("a6", "2026-09-02", None, "goi_y", "H2", 0),  # người đã duyệt -> có
               ("a7", "2026-09-02", "H3", "chac", None, 0),
               ("a8", "2026-09-10", "H4", "chac", None, 0),
               ("a9", "2026-09-11", "H5", "chac", None, 0)]
        for pid, ngay, gy, do_tin, xn, bq in anh:
            c.execute("INSERT INTO photos (id,nguon,ngay,thoi_gian,ten_file,goi_y_hd,do_tin,bo_qua,xn_hd)"
                      " VALUES (?,'photos',?,?,'I.HEIC',?,?,?,?)", (pid, ngay, f"{ngay}T10:00:{pid[1]}0", gy,
                                                                  do_tin, bq, xn))
        c.commit()
        self.c = c

    def tearDown(self):
        self.c.close()

    def test_tap_album(self):
        m = M.tinh_album(self.c)
        self.assertEqual(m[(M.TM_DV, "DV · Sẹo lồi")], ["a1"])
        self.assertEqual(m[(M.TM_DV, "DV · Laser Pico")], ["a2", "a6"])  # HĐ 2 dịch vụ -> 2 album
        self.assertEqual(m[(M.TM_DV, "DV · PRP")], ["a2", "a6"])
        self.assertNotIn((M.TM_DV, "DV · Sẹo rỗ"), m)  # sẹo lồi không vào sẹo rỗ
        self.assertEqual(m[(M.TM_THANG, "2026-08")], ["a1"])  # tháng theo HĐ, không theo ngày chụp
        self.assertEqual(m[(M.TM_THANG, "2026-09")], ["a2", "a6", "a7", "a8", "a9"])
        tat_ca = {i for v in m.values() for i in v}
        self.assertFalse(tat_ca & {"a3", "a4", "a5"})  # gợi ý / chưa rõ / bị loại không vào
        self.assertFalse(any("a7" in v for k, v in m.items() if k[0] == M.TM_DV))  # chỉ sản phẩm

    def test_album_khach(self):
        m = M.tinh_album(self.c)
        kh = {k[1]: v for k, v in m.items() if k[0] == M.TM_KHACH}
        # KH000001: 2 ngày HĐ; CU-KH000777 + KH000888 cùng SĐT = 1 khách, tên theo mã mới KH…
        self.assertEqual(kh, {"KH000001 · Trần Thị Bịa": ["a1", "a2", "a6"],
                              "KH000888 · Khách Mới Bịa": ["a7", "a8"]})  # KH000999 chỉ 1 ngày -> không

    def chay(self, *thamso):
        goi, run = chay_gia()
        if "--ghi" in thamso:  # lớp này thử đường osascript cũ (dự phòng)
            thamso = (*thamso, "--applescript")
        with mock.patch.object(M.subprocess, "run", run), mock.patch.object(sys, "argv", ["x", *thamso]), \
                redirect_stdout(io.StringIO()) as out:
            try:
                M.main()
            except SystemExit:
                pass
        return goi, out.getvalue()

    def test_chay_khan_khong_goi_gi(self):
        goi, out = self.chay()
        self.assertEqual(goi, [])
        self.assertIn("CHẠY KHAN", out)
        self.assertNotIn("da_album", [r[0] for r in self.c.execute("SELECT name FROM sqlite_master")])

    def test_ghi_roi_khong_doi_thi_khong_goi(self):
        goi, _ = self.chay("--ghi")
        ten = sorted(g[5] for g in goi)
        self.assertIn("DV · Sẹo lồi", ten)
        self.assertIn("2026-08", ten)
        self.assertIn("KH000888 · Khách Mới Bịa", ten)
        for g in goi:  # mỗi album: tạo trong đúng thư mục con của 'Doctor Laser'
            self.assertEqual(g[:2], ["osascript", "-e"])
            self.assertEqual(g[3], "Doctor Laser")
            self.assertIn(g[4], (M.TM_DV, M.TM_THANG, M.TM_KHACH))
            self.assertEqual(g[6], "tao")
        g = next(g for g in goi if g[5] == "DV · Laser Pico")
        self.assertEqual(g[7:], ["a2/L0/001", "a6/L0/001"])
        goi2, _ = self.chay("--ghi")
        self.assertEqual(goi2, [])  # không đổi -> không gọi app Ảnh

    def test_doi_thi_xoa_tao_lai_dung_album_do(self):
        self.chay("--ghi")
        self.c.execute("UPDATE photos SET bo_qua=1 WHERE id='a6'")  # người duyệt loại 1 ảnh
        self.c.commit()
        goi, _ = self.chay("--ghi")
        ten = sorted(g[5] for g in goi)
        self.assertEqual(ten, ["2026-09", "DV · Laser Pico", "DV · PRP", "KH000001 · Trần Thị Bịa"])
        g = next(g for g in goi if g[5] == "DV · PRP")
        self.assertEqual((g[6], g[7:]), ("tao", ["a2/L0/001"]))  # _TAO xoá album trùng tên rồi tạo lại
        self.assertIn("delete album", M._TAO)

    def test_album_het_anh_thi_chi_xoa(self):
        self.chay("--ghi")
        self.c.execute("UPDATE photos SET bo_qua=1 WHERE id='a1'")
        self.c.commit()
        goi, _ = self.chay("--ghi")
        g = next(g for g in goi if g[5] == "DV · Sẹo lồi")
        self.assertEqual(g[6:], ["xoa"])
        self.assertEqual(next(g for g in goi if g[5] == "2026-08")[6:], ["xoa"])

    def test_lo_toi_da_200(self):
        goi, run = chay_gia()
        ids = [f"u{i:04d}" for i in range(450)]
        with mock.patch.object(M.subprocess, "run", run):
            M.ghi_album(M.TM_THANG, "2026-09", ids)
        self.assertEqual(len(goi), 3)
        self.assertEqual([len(g) - 7 for g in goi[:1]] + [len(g) - 4 for g in goi[1:]], [200, 200, 50])
        self.assertEqual(goi[1][3], "ALB/L0/040")  # lô sau thêm vào album vừa tạo theo id
        self.assertEqual(goi[2][-1], "u0449/L0/001")

    def test_loi_3_album_lien_thi_dung_va_lan_sau_lam_lai(self):
        goi = []

        def hong(cmd, **kw):
            goi.append(cmd)
            return types.SimpleNamespace(returncode=1, stdout="", stderr="Photos got an error")
        with mock.patch.object(M.subprocess, "run", hong), \
                mock.patch.object(sys, "argv", ["x", "--ghi", "--applescript"]), \
                redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
            M.main()
        self.assertEqual(len(goi), 3)
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM da_album").fetchone()[0], 0)
        goi2, _ = self.chay("--ghi")
        self.assertGreater(len(goi2), 3)

    def test_toi_da_chay_tiep(self):
        goi, _ = self.chay("--ghi", "--toi-da", "2")
        self.assertEqual(len(goi), 2)
        goi2, _ = self.chay("--ghi")
        self.assertFalse({g[5] for g in goi} & {g[5] for g in goi2})  # lượt sau làm tiếp phần còn lại
        self.assertEqual(self.chay("--ghi")[0], [])

    def test_chi_mot_thu_muc(self):
        goi, _ = self.chay("--ghi", "--chi", "khach")
        self.assertEqual({g[4] for g in goi}, {M.TM_KHACH})
        goi2, _ = self.chay("--ghi", "--chi", "dv")
        self.assertEqual({g[4] for g in goi2}, {M.TM_DV})  # không xoá album khách vừa làm


class TenAlbumMay(unittest.TestCase):
    def test_album_thang_la_cua_may(self):  # chữ album máy tạo không lẫn vào chữ quét nhãn
        self.assertTrue(A._la_album_may("2026-09"))
        self.assertTrue(A._la_album_may("DV · Sẹo rỗ"))
        self.assertTrue(A._la_album_may("KH000001 · Trần Thị Bịa"))
        self.assertFalse(A._la_album_may("Nam-xx 9/10/26"))


if __name__ == "__main__":
    unittest.main()
