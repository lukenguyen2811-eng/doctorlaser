"""Trang ngày duyệt THEO BỘ CHỤP + POST /luu_bo (Lượng 16/10). Dữ liệu bịa.
python3 -m unittest tests/test_duyet_theo_bo.py"""
import datetime as dt
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["ANH_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
import anhkhach as A  # noqa: E402

D = "2026-10-14"


class Nen(unittest.TestCase):
    def setUp(self):
        self.c = A.ket_noi()
        for t in ("photos", "visits"):
            self.c.execute(f"DELETE FROM {t}")
        self.c.commit()

    def tearDown(self):
        self.c.close()

    def hd(self, code, gio, ma, ten, dv, ngay=D):
        self.c.execute("INSERT INTO visits (code,ngay,gio,ma_kh,ten_kh,dich_vu) VALUES (?,?,?,?,?,?)",
                       (code, ngay, gio, ma, ten, dv))

    def anh(self, pid, gio, goi_y=None, do_tin="goi_y", ly_do="", ocr="", xn=None, bo_qua=0, ghi=""):
        self.c.execute("INSERT INTO photos (id,nguon,ngay,thoi_gian,ten_file,chu_thich,ocr,dot,goi_y_hd,do_tin,"
                       "ly_do,xn_hd,bo_qua,ghi_chu) VALUES (?,'photos',?,?,?,'',?,0,?,?,?,?,?,?)",
                       (pid, D, f"{D}T{gio}", pid + ".jpg", ocr, goi_y, do_tin, ly_do, xn, bo_qua, ghi))

    def trang(self, **k):
        self.c.commit()
        return A._trang_ngay(self.c, D, **k).decode()

    def bo_ids(self, t):
        import re
        return [x.split(",") for x in re.findall(r"data-ids='([^']*)'", t)]


class GomBo(Nen):
    def test_quang_tren_60s_tach_bo(self):
        for pid, g in [("a1", "10:00:00"), ("a2", "10:00:30"), ("a3", "10:01:30"),  # 60s -> cùng bộ
                       ("b1", "10:02:31"), ("b2", "10:02:40")]:  # 61s -> bộ mới
            self.anh(pid, g, "H1")
        self.hd("H1", "10:00", "KH1", "Lê Văn A", "Pico")
        self.assertEqual(self.bo_ids(self.trang()), [["a1", "a2", "a3"], ["b1", "b2"]])

    def test_trung_giay_cung_bo_nhung_3_anh_cung_giay_tach_le(self):
        self.anh("x1", "09:00:00")
        self.anh("x2", "09:00:00")  # 2 bản cùng giây = cùng bộ
        self.anh("x3", "09:00:20")
        for i in range(3):  # >= 3 ảnh cùng giây = giờ nhập máy -> mỗi ảnh 1 bộ
            self.anh(f"n{i}", "15:00:00")
        bo = self.bo_ids(self.trang())
        self.assertIn(["x1", "x2", "x3"], bo)
        for i in range(3):
            self.assertIn([f"n{i}"], bo)
        self.assertIn("giờ chụp trùng nhiều ảnh", self.trang())

    def test_an_anh_chac_dem_trong_bo(self):
        self.hd("H1", "10:00", "KH1", "Lê Văn A", "Pico")
        self.anh("c1", "10:00:00", "H1", do_tin="chac")
        self.anh("g1", "10:00:20", "H1")
        t = self.trang()
        self.assertEqual(self.bo_ids(t), [["g1"]])
        self.assertIn("1 ảnh chắc chắn đã ẩn (cùng bộ)", t)
        self.assertIn("còn <b id=conBo>1</b> bộ / <b id=conAnh>1</b> ảnh", t)

    def test_bo_xong_thu_gon(self):
        self.hd("H1", "10:00", "KH1", "Nguyễn Kinh Lương (KH TỰ ĐẾN)", "Xoá xăm")
        self.anh("d1", "10:00:00", "H1", xn="H1")
        t = self.trang()
        self.assertIn("class='bo xong'", t)
        self.assertIn("đã lưu: <b>Lương — Xoá xăm</b>", t)
        self.assertIn("còn <b id=conBo>0</b> bộ", t)


class TenGoiVaThuTu(Nen):
    def test_ten_goi(self):
        self.assertEqual(A.ten_goi("NGUYỄN KINH LƯƠNG (KH TỰ ĐẾN)"), "Lương")
        self.assertEqual(A.ten_goi("NGUYỄN KINH LƯƠNG (KH TỰ ĐẾN)", 2), "Kinh Lương")
        self.assertEqual(A.ten_goi("Lê Thị Dung BS LƯƠNG"), "Dung")  # bỏ ghi chú đuôi
        self.assertEqual(A.ten_goi(""), "")

    def test_thu_tu_goi_y_ten_gio(self):
        luc = dt.datetime(2026, 10, 14, 10, 0)

        def h(c, ten, gio):
            return {"c": c, "w": A.ten_sach(ten).split(), "bd": A._bi_danh(ten),
                    "luc": dt.datetime(2026, 10, 14, *gio)}
        hds = [h("GAN", "Trần Văn Bình", (10, 5)),  # gần giờ nhất
               h("XA", "Phạm Thị Hoa", (17, 0)),
               h("TEN", "Nguyễn Kinh Lương", (15, 0)),  # trùng tên gọi trên nhãn
               h("GY", "Võ Văn Tú", (13, 0))]  # máy gợi ý
        self.assertEqual([hds[i]["c"] for i in A._thu_tu_ung_vien(hds, ["GY"], [["c", "luong"]], luc)],
                         ["GY", "TEN", "GAN", "XA"])
        # âm: nhãn 'Lương' không được khớp 'Lượng'? (so không dấu -> khớp, chỉ xếp trước, không tự chọn)
        self.assertEqual([hds[i]["c"] for i in A._thu_tu_ung_vien(hds, [], [], luc)], ["GAN", "GY", "TEN", "XA"])
        # âm: nhãn 'Kinh' (không phải đuôi họ tên) không khớp
        self.assertEqual([hds[i]["c"] for i in A._thu_tu_ung_vien(hds, [], [["kinh"]], luc)][0], "GAN")

    def test_trang_thu_tu_va_ten_goi_trung(self):
        self.hd("H1", "10:05", "KH1", "Trần Văn Bình", "Pico")
        self.hd("H2", "15:00", "KH2", "Nguyễn Kinh Lương", "Xoá xăm")
        self.hd("H3", "16:00", "KH3", "Lê Thị Bình", "CSD")  # trùng tên gọi 'Bình' -> 2 chữ
        self.anh("p1", "10:00:00", ocr="Lương-xoá xăm 14/10/26", do_tin="chua_ro")
        t = self.trang()
        dl = A.du_lieu_trang(t)
        ma = [v["c"] for v in dl["hd"]]
        import re
        o = [ma[int(i)] for i in re.search(r"data-o='([^']*)'", t).group(1).split(",")]
        self.assertEqual(o[0], "H2")  # khớp tên gọi trên nhãn lên trước HĐ gần giờ
        ten = {v["c"]: v["t"] for v in dl["hd"]}
        self.assertEqual((ten["H1"], ten["H2"], ten["H3"]), ("Văn Bình", "Lương", "Thị Bình"))
        self.assertIn("nhãn: <b>Lương-xoá xăm 14/10/26</b>", t)
        self.assertEqual(t.count("<option"), 0)  # ô chọn sinh bằng JS, không lặp HTML


class CanhBaoVaEscape(Nen):
    def test_bo_nhieu_khach(self):
        self.hd("H1", "10:00", "KH1", "Lê Văn A", "Pico")
        self.hd("H2", "10:10", "KH2", "Trần Thị B", "CSD")
        self.anh("a", "10:00:00", "H1")
        self.anh("b", "10:00:10", "H1")
        self.anh("c", "10:00:20", "H2")
        t = self.trang()
        self.assertIn("bộ có 2 khách khác nhau — nên Tách bộ", t)
        self.assertIn("data-hd='H1'", t)  # chọn sẵn khách đa số

    def test_cung_khach_hai_hd_khong_canh_bao(self):  # âm: 2 HĐ của CÙNG mã KH không phải 2 khách
        self.hd("H1", "10:00", "KH1", "Lê Văn A", "Pico")
        self.hd("H1b", "10:00", "KH1", "Lê Văn A", "CSD")
        self.anh("a", "10:00:00", "H1")
        self.anh("b", "10:00:10", "H1b")
        self.assertNotIn("khách khác nhau", self.trang())

    def test_canh_bao_len_dau(self):
        self.anh("t1", "09:00:00")
        self.anh("t2", "17:00:00", ly_do="cảnh báo: khuôn mặt thuộc khách khác (KH9, cụm 3)")
        self.c.execute("UPDATE photos SET dot=1 WHERE id='t2'")
        t = self.trang()
        self.assertLess(t.index("id='pt2'"), t.index("id='pt1'"))

    def test_escape_xss(self):
        self.hd("H<1>", "10:00", "K<b>1", "<script>alert(1)</script> Văn A", "<img src=x onerror=alert(1)>")
        self.anh("x'><script>alert(2)</script>", "10:00:00", "H<1>",
                 ly_do="<script>alert(3)</script>", ocr="</script><script>alert(4)</script>")
        t = self.trang()
        for i in range(1, 5):
            self.assertNotIn(f"<script>alert({i})</script>", t)
        self.assertNotIn("<img src=x", t)
        dl = A.du_lieu_trang(t)  # JSON nhúng vẫn đọc lại đúng
        self.assertEqual(dl["hd"][0]["c"], "H<1>")


class LuuBo(Nen):
    def setUp(self):
        super().setUp()
        self.hd("H1", "10:00", "KH1", "Nguyễn Kinh Lương", "Xoá xăm")
        for pid in ("a", "b", "c"):
            self.anh(pid, "10:00:0" + pid.replace("a", "0").replace("b", "1").replace("c", "2"), ghi="cũ " + pid)
        self.anh("khac", "11:00:00", ghi="giữ")
        self.c.commit()

    def dong(self, pid):
        return self.c.execute("SELECT * FROM photos WHERE id=?", (pid,)).fetchone()

    def test_luu_ca_bo(self):
        ma, kq = A.luu_bo(self.c, {"ids": ["a", "b", "c"], "hd": "H1", "loai": "sau", "vung": "mặt", "ghi": "tốt"})
        self.assertEqual((ma, kq["n"], kq["ten"], kq["st"]), (200, 3, "Lương", "ok"))
        for pid in "abc":
            r = self.dong(pid)
            self.assertEqual((r["xn_hd"], r["bo_qua"], r["loai_anh"], r["vung"], r["ghi_chu"]),
                             ("H1", 0, "sau", "mặt", "tốt"))
            self.assertTrue(r["xn_luc"])
        r = self.dong("khac")  # không đụng ảnh ngoài danh sách
        self.assertEqual((r["xn_hd"], r["ghi_chu"], r["xn_luc"]), (None, "giữ", None))

    def test_ghi_none_giu_ghi_chu(self):
        A.luu_bo(self.c, {"ids": ["a", "b"], "hd": "H1", "ghi": None})
        self.assertEqual((self.dong("a")["ghi_chu"], self.dong("b")["ghi_chu"]), ("cũ a", "cũ b"))

    def test_bo_qua_ca_bo(self):
        ma, kq = A.luu_bo(self.c, {"ids": ["a", "b"], "hd": "H1", "bo_qua": 1})
        self.assertEqual((ma, kq["st"]), (200, "skip"))
        self.assertEqual((self.dong("a")["bo_qua"], self.dong("a")["xn_hd"]), (1, None))
        self.assertEqual(self.dong("c")["bo_qua"], 0)

    def test_tu_choi(self):
        for d in [{"ids": ["a"], "hd": "KHONG_CO"},  # hd không có
                  {"ids": ["a"], "hd": ""},  # chưa chọn khách
                  {"ids": ["a", "khong_co"], "hd": "H1"},  # 1 id lạ -> từ chối cả lô
                  {"ids": [], "hd": "H1"}, {"ids": "a", "hd": "H1"}, {"ids": [1], "hd": "H1"},
                  {"ids": ["a"], "hd": "H1", "loai": "lạ"}, {"ids": ["a"], "hd": "H1", "vung": "x"},
                  {"ids": ["a"], "hd": ["H1"]}]:
            self.assertEqual(A.luu_bo(self.c, d)[0], 400, d)
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM photos WHERE xn_luc IS NOT NULL").fetchone()[0], 0)

    def test_route_http(self):
        A._Handler.conn = self.c
        srv = A.ThreadingHTTPServer(("127.0.0.1", 0), A._Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        goc = f"http://127.0.0.1:{srv.server_address[1]}"

        def post(duong, d):
            rq = urllib.request.Request(goc + duong, json.dumps(d).encode(), {"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(rq) as r:
                    return r.status, json.loads(r.read())
            except urllib.error.HTTPError as e:
                return e.code, None
        try:
            t = urllib.request.urlopen(goc + "/ngay?d=" + D).read().decode()
            self.assertIn("Đúng khách này (cả bộ 3 ảnh)", t)
            self.assertEqual(post("/luu_bo", {"ids": ["a", "b"], "hd": "NOPE"})[0], 400)
            st, kq = post("/luu_bo", {"ids": ["a", "b", "c"], "hd": "H1", "loai": "trước"})
            self.assertEqual((st, kq["n"]), (200, 3))
            self.assertEqual(self.dong("c")["loai_anh"], "trước")
            self.assertEqual(post("/luu", {"id": "khac", "hd": "NOPE"})[0], 400)  # /luu cũng chặn HĐ lạ
            self.assertEqual(post("/luu", {"id": "khac", "hd": "H1"})[0], 200)
            self.assertEqual(self.dong("khac")["xn_hd"], "H1")
            rq = urllib.request.Request(goc + "/luu_bo", b"{khong json", {"Content-Type": "application/json"})
            with self.assertRaises(urllib.error.HTTPError):
                urllib.request.urlopen(rq)
        finally:
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    unittest.main()
