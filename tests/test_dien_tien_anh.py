"""Trang diễn tiến điều trị /khach + tìm khách /tim (dữ liệu bịa, DB tạm).

Chạy:  python3 -m unittest tests/test_dien_tien_anh.py
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ANH_DB", os.path.join(tempfile.mkdtemp(), "t.db"))
import anhkhach as A  # noqa: E402


class DienTien(unittest.TestCase):
    def setUp(self):
        self.tam = tempfile.mkdtemp()
        self.p = mock.patch.object(A, "DB_FILE", os.path.join(self.tam, "dt.db"))
        self.p.start()
        self.c = A.ket_noi()
        self.file = os.path.join(self.tam, "a.jpg")
        open(self.file, "wb").close()
        for code, ngay, gio, ma, ten, sdt, dv in [
            ("HD1", "2026-09-05", "10:00", "KH001", "Khach Bia Mot", "0901111234", "Laser Pico | Kem"),
            ("HD2", "2026-10-03", "09:00", "KH001", "Khach Bia Mot", "0901111234", "Laser Pico"),
            ("HD3", "2026-09-20", "15:00", "KH001", "Khach Bia Mot", "0901111234", "Trị sẹo rỗ"),
            ("HD9", "2026-09-05", "10:05", "KH002", "Nguoi <script>alert(1)</script>", "0909999888",
             "Tiêm <b>HA</b>"),
            ("HDL", "2026-09-05", "11:00", "", "Khách lẻ", "", "Laser"),
        ]:
            self.c.execute("INSERT INTO visits VALUES (?,?,?,?,?,?,?,?)", (code, ngay, gio, ma, ten, sdt, dv, ""))
        # (id, ngày chụp, giờ, xn_hd, goi_y_hd, do_tin, loai, vùng, ghi chú, bo_qua)
        for r in [
            ("a1", "2026-09-05", "10:01", "HD1", None, "chac", "trước", "má", "thâm nhiều", 0),
            ("a2", "2026-09-05", "10:20", "HD1", None, "chac", "sau", "", "", 0),
            ("a3", "2026-10-03", "09:05", None, "HD2", "goi_y", "trước", "", "", 0),   # chưa duyệt
            ("a4", "2026-10-03", "09:06", None, "HD2", "chua_ro", "", "", "", 0),     # chưa rõ -> không hiện
            ("a5", "2026-09-20", "15:10", "HD3", None, "goi_y", "", "", "", 0),       # chưa phân loại
            ("a6", "2026-09-05", "10:02", "HD9", "HD1", "goi_y", "trước", "", "", 0),  # người duyệt sang KH002
            ("a7", "2026-09-05", "10:03", None, "HD1", "chac", "trong", "", "", 1),    # bỏ qua
            ("a8", "2026-09-05", "11:05", "HDL", None, "chac", "", "", "", 0),         # khách lẻ không mã
        ]:
            pid, ngay, gio, xn, gy, dtin, loai, vung, ghi, bq = r
            self.c.execute(
                "INSERT INTO photos (id,nguon,ngay,thoi_gian,ten_file,duong_dan,anh_xem,chu_thich,ocr,"
                "xn_hd,goi_y_hd,do_tin,loai_anh,vung,ghi_chu,bo_qua) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (pid, "photos", ngay, f"{ngay}T{gio}:00", "IMG.jpg", self.file, self.file, "", "",
                 xn, gy, dtin, loai, vung, ghi, bq))
        self.c.commit()

    def tearDown(self):
        self.c.close()
        self.p.stop()

    def trang(self, ma, dv=""):
        return A._trang_khach(self.c, ma, dv).decode()

    def test_nhom_theo_lan_va_thu_tu(self):
        t = self.trang("KH001")
        i1, i3, i2 = t.index("05/09/2026"), t.index("20/09/2026"), t.index("03/10/2026")
        self.assertTrue(i1 < i3 < i2)
        self.assertIn("3 lần điều trị", t)
        self.assertIn("4 ảnh (1 chưa duyệt)", t)  # a1 a2 a3 a5
        self.assertIn("…1234", t)
        self.assertNotIn("0901111234", t)

    def test_cot_truoc_trong_sau_va_chua_phan_loai(self):
        t = self.trang("KH001")
        lan1 = t[t.index("05/09/2026"):t.index("20/09/2026")]
        self.assertTrue(lan1.index("<h4>Trước") < lan1.index("/anh/a1") < lan1.index("<h4>Trong")
                        < lan1.index("<h4>Sau") < lan1.index("/anh/a2"))
        self.assertIn("má · thâm nhiều", lan1)
        self.assertNotIn("Chưa phân loại", lan1)
        lan3 = t[t.index("20/09/2026"):t.index("03/10/2026")]
        self.assertIn("Chưa phân loại", lan3)
        self.assertIn("onclick=\"zoom(this.src)\"", t)

    def test_chua_duyet_ghi_nhan_va_chua_ro_khong_hien(self):
        t = self.trang("KH001")
        lan2 = t[t.index("03/10/2026"):]
        self.assertIn("/anh/a3", lan2)
        self.assertIn("chưa duyệt", lan2)
        self.assertNotIn("/anh/a4", t)

    def test_khach_khac_khong_lan_vao(self):  # âm: a6 máy gợi ý HD1 nhưng người đã duyệt sang HD9
        t = self.trang("KH001")
        for pid in ("a6", "a7", "a8"):
            self.assertNotIn(f"/anh/{pid}'", t)
        t2 = self.trang("KH002")
        self.assertIn("/anh/a6", t2)
        self.assertNotIn("/anh/a1'", t2)

    def test_loc_dich_vu(self):
        t = self.trang("KH001", "Laser Pico")
        self.assertIn("2 lần điều trị", t)
        self.assertNotIn("20/09/2026", t)
        self.assertIn("Trị sẹo rỗ", t)  # vẫn có link lọc dịch vụ khác
        self.assertIn("ma=KH001&amp;dv=Laser%20Pico", t)
        self.assertIn("Không có ảnh dịch vụ", self.trang("KH001", "Không có"))

    def test_escape_html(self):  # âm: tên/dịch vụ có thẻ HTML
        t = self.trang("KH002")
        self.assertNotIn("<script>alert", t)
        self.assertIn("&lt;script&gt;", t)
        self.assertNotIn("<b>HA</b>", t)
        t = self.trang("<script>x</script>")
        self.assertNotIn("<script>x", t)

    def test_ma_rong_hoac_khong_co(self):  # âm: mã rỗng không được ra khách lẻ
        for ma in ("", "  ", "KH999"):
            t = self.trang(ma)
            self.assertIn("Không có ảnh nào", t)
            self.assertNotIn("/anh/", t)

    def test_tim(self):
        ma = lambda q: [r["ma_kh"] for r in A._tim_khach(self.c, q)]  # noqa: E731
        self.assertEqual(ma("kh001"), ["KH001"])
        self.assertEqual(ma("1234"), ["KH001"])
        self.assertEqual(ma("0909 999 888"), ["KH002"])
        self.assertEqual(ma("bia mot"), ["KH001"])
        self.assertEqual(ma(""), [])
        self.assertEqual(ma("khach le"), [])  # âm: khách không mã không vào danh sách
        t = A._trang_tim(self.c, "kh00").decode()
        self.assertIn("href='/khach?ma=KH001'", t)
        self.assertIn("2 khách", t)
        self.assertNotIn("<script>alert", t)
        self.assertIn("Không thấy", A._trang_tim(self.c, "<i>zz</i>").decode())
        self.assertNotIn("<i>zz", A._trang_tim(self.c, "<i>zz</i>").decode())

    def test_trang_ngay_co_link_khach(self):
        t = A._trang_ngay(self.c, "2026-09-05").decode()
        self.assertIn("<a href='/khach?ma=KH001'>Khach Bia Mot</a>", t)
        self.assertIn("→ diễn tiến KH001", t)
        self.assertNotIn("<script>alert", t)
        self.assertIn("action='/tim'", A._trang_chu(self.c).decode())

    def test_ma_cu_la_khach_khac(self):  # âm: 'CU-KH001' (KiotViet cũ) KHÔNG gộp với 'KH001'
        self.c.execute("INSERT INTO visits VALUES ('CU-HD5','2019-03-02','08:00','CU-KH001','Nguoi Cu Khac',"
                       "'0907770000','Laser Pico','')")
        self.c.execute("INSERT INTO photos (id,nguon,ngay,thoi_gian,ten_file,duong_dan,anh_xem,chu_thich,ocr,"
                       "xn_hd,do_tin,bo_qua) VALUES ('c1','photos','2019-03-02','2019-03-02T08:05:00','I.jpg',?,?,"
                       "'','','CU-HD5','chac',0)", (self.file, self.file))
        t = self.trang("KH001")
        self.assertNotIn("/anh/c1'", t)
        self.assertNotIn("2019", t)
        t = self.trang("CU-KH001")
        self.assertIn("/anh/c1'", t)
        self.assertNotIn("/anh/a1'", t)
        self.assertIn("1 lần điều trị", t)
        ds = [r["ma_kh"] for r in A._tim_khach(self.c, "KH001")]
        self.assertEqual(sorted(ds), ["CU-KH001", "KH001"])  # 2 dòng riêng, mỗi dòng 1 link
        self.assertIn("href='/khach?ma=CU-KH001'", A._trang_tim(self.c, "KH001").decode())

    def test_route_http(self):  # gọi thật qua server cục bộ (cổng ngẫu nhiên)
        import threading
        import urllib.request

        A._Handler.conn = self.c
        srv = A.ThreadingHTTPServer(("127.0.0.1", 0), A._Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            goc = f"http://127.0.0.1:{srv.server_address[1]}"
            t = urllib.request.urlopen(goc + "/khach?ma=KH001&dv=Laser%20Pico").read().decode()
            self.assertIn("2 lần điều trị", t)
            t = urllib.request.urlopen(goc + "/tim?q=" + "b%C3%ADa").read().decode()  # 'bía' -> không dấu
            self.assertIn("KH001", t)
            self.assertEqual(urllib.request.urlopen(goc + "/anh/a1").status, 200)
        finally:
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    unittest.main()
