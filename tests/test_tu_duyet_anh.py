"""TỰ DUYỆT (CEO 16/10 lần 7) — DB tạm, dữ liệu bịa.

Máy tự duyệt đơn vị ảnh gợi ý/chưa rõ khi có >= 2 nguồn bằng chứng độc lập (mặt, nhãn, giờ, gợi ý), không bị phản bác,
hơn hạng 2 rõ và bỏ từng nguồn vẫn hạng 1. Không đụng ảnh người đã duyệt; ghi tách cột may_*; gỡ được.

Chạy:  python3 -m unittest tests/test_tu_duyet_anh.py
"""
import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_ten_cuoi_mat_anh import A, D, Nen  # noqa: E402


class TuDuyet(Nen):
    def cum(self, ma, ten, km, n=6):  # cụm mặt mạnh của khách ma (ảnh nhãn ở 2 ngày cũ)
        for i, ngay in enumerate(("2026-09-01", "2026-09-15")):
            self.hd(f"{ma}-{i}", ngay, ma, ten, "CSD")
        for i in range(n):
            ngay = "2026-09-01" if i % 2 == 0 else "2026-09-15"
            self.anh(ngay, f"1{i}:00:00", km=km, do_tin="chac", goi_y=f"{ma}-{i % 2}", ly_do="nhãn 'x-csd' khớp")

    def don_vi(self, gio0, km="", ocr0="", n=3):
        ids = [self.anh(D, f"{gio0}:{10 + i * 5:02d}", ocr0 if i == 0 else "", km=km) for i in range(n)]
        return ids

    def chay(self):
        A.ghep_ngay(self.c, D)
        return A.tu_duyet_on_dinh(self.c, [D])

    def test_mat_va_gio_nhan(self):
        self.cum("K1", "Phan Thị Lan", "P-K")
        self.hd("K1-D", D, "K1", "Phan Thị Lan", "CSD", "10:05")
        self.hd("L1-D", D, "L1", "Trần Văn Nam", "CSD", "10:20")
        self.hd("M1-D", D, "M1", "Lê Thị Hoa", "CSD", "10:25")
        # ảnh 2 mặt (mặt khách + người khác) -> luật mặt của ghép không nhận (> 1 mặt? <= 2 vẫn nhận) -> dùng bộ không cụm
        ids = self.don_vi("10:08", km="P-K P-Z")
        self.c.execute("UPDATE photos SET do_tin='chua_ro' WHERE id IN (%s)" % ",".join("?" * len(ids)), ids)
        kq = A.tu_duyet_on_dinh(self.c, [D])
        self.assertEqual({kq[i][0] for i in ids if i in kq}, {"K1-D"})

    def test_chi_gio_khong_nhan(self):  # âm: 1 nguồn (giờ) không đủ
        self.hd("K1-D", D, "K1", "Phan Thị Lan", "CSD", "10:05")
        self.hd("L1-D", D, "L1", "Trần Văn Nam", "CSD", "15:00")
        ids = self.don_vi("10:08")
        kq = self.chay()
        self.assertFalse(any(i in kq for i in ids))

    def test_mat_khach_khac_khong_nhan_k(self):  # âm: mặt của khách khác (có HĐ ngày khác giờ xa) -> không gán K
        self.cum("L1", "Trần Văn Nam", "P-L")
        self.hd("K1-D", D, "K1", "Phan Thị Lan", "CSD", "10:05")
        self.hd("L1-D", D, "L1", "Trần Văn Nam", "CSD", "16:00")
        ids = self.don_vi("10:08", km="P-L P-Z")
        self.c.execute("UPDATE photos SET do_tin='chua_ro' WHERE id IN (%s)" % ",".join("?" * len(ids)), ids)
        kq = A.tu_duyet_on_dinh(self.c, [D])
        self.assertNotIn("K1-D", {kq[i][0] for i in ids if i in kq})

    def test_nhan_ten_la_khong_nhan(self):  # âm: nhãn ghi tên không có HĐ trong ngày -> mọi khách bị phản bác
        self.cum("K1", "Phan Thị Lan", "P-K")
        self.hd("K1-D", D, "K1", "Phan Thị Lan", "CSD", "10:05")
        ids = self.don_vi("10:08", km="P-K P-Z", ocr0="Hoàng Huy- csd 10/10/26")
        self.c.execute("UPDATE photos SET do_tin='chua_ro' WHERE id IN (%s)" % ",".join("?" * len(ids)), ids)
        kq = A.tu_duyet_on_dinh(self.c, [D])
        self.assertFalse(any(i in kq for i in ids))

    def test_khong_dung_anh_da_duyet(self):  # âm: đơn vị có ảnh người đã duyệt -> bỏ qua cả đơn vị
        self.cum("K1", "Phan Thị Lan", "P-K")
        self.hd("K1-D", D, "K1", "Phan Thị Lan", "CSD", "10:05")
        ids = self.don_vi("10:08", km="P-K P-Z")
        self.c.execute("UPDATE photos SET do_tin='chua_ro' WHERE id IN (%s)" % ",".join("?" * len(ids)), ids)
        self.c.execute("UPDATE photos SET xn_hd='K1-D' WHERE id=?", (ids[0],))
        kq = A.tu_duyet_on_dinh(self.c, [D])
        self.assertFalse(any(i in kq for i in ids))

    def test_lech_chu_dau_khong_hop(self):  # ca B9F837F3: 'Linh' lệch 1 ký tự với 'Minh' nhưng khác chữ đầu -> không hợp
        n = A.doc_nhan("Linh- sẹo 10/10/26", 2026)[0]
        self.assertTrue(A._ten_nhan_hop(n, "Trần Thị Minh"))  # luật ghép (giữ nguyên) vẫn coi là hợp
        self.assertFalse(A._td_hop(n, "Trần Thị Minh"))
        self.assertTrue(A._td_hop(A.doc_nhan("Thaor- csd 10/10/26", 2026)[0], "Phan Thị Thảo"))  # cùng chữ đầu: OCR

    def test_mat_thuoc_khach_nhan_ngay_khac(self):  # ca B9F837F3: mặt có >= 2 ảnh nhãn đúng tên khách khác -> chặn
        for i, ngay in enumerate(("2026-09-01", "2026-09-15")):
            self.hd(f"L-{i}", ngay, "KL", "Ngô Thị Linh", "Sẹo")
            self.anh(ngay, "10:00:00", km="P-L", do_tin="chac", goi_y=f"L-{i}", ly_do="nhãn 'Linh-sẹo' khớp")
        self.hd("M-D", D, "KM", "Trần Thị Minh", "Điều trị sẹo", "10:05")
        self.hd("X-D", D, "KX", "Lê Văn Tâm", "Pico", "16:00")
        ids = self.don_vi("10:08", km="P-L", ocr0="Linh- sẹo 10/10/26")
        A.ghep_ngay(self.c, D)
        self.c.execute("UPDATE photos SET do_tin='goi_y', goi_y_hd='M-D' WHERE id IN (%s)" % ",".join("?" * len(ids)), ids)
        kq = A.tu_duyet_on_dinh(self.c, [D])
        self.assertFalse(any(i in kq for i in ids))

    def test_ham_quyet(self):
        d = lambda m, n, g, y: {"mat": m, "nhan": n, "gio": g, "goi_y": y}  # noqa: E731
        self.assertEqual(A._td_quyet({"K": d(3, 0, 1.5, 0), "L": d(-5, 0, 1.5, 0)})[0], "K")
        self.assertIsNone(A._td_quyet({"K": d(0, 0, 1.5, 0.5), "L": d(0, 0, 0, 0)})[0])  # điểm thấp
        self.assertIsNone(A._td_quyet({"K": d(3, 0, 1.5, 0), "L": d(3, 0, 0.5, 0)})[0])  # biên nhỏ
        self.assertIsNone(A._td_quyet({"K": d(0, 3.5, 0, 0), "L": d(0, 0, 0, 0)})[0])  # 1 nguồn
        self.assertIsNone(A._td_quyet({"K": d(0, 3.5, 0, 0.5), "L": d(0, 0, 0, 0)})[0])  # gợi ý không phải nguồn độc lập
        # leave-one-out: bỏ 'mat' thì L (giờ +1.5, gợi ý) vượt K (giờ +0.5)
        self.assertIsNone(A._td_quyet({"K": d(3, 0, 0.5, 0.5), "L": d(0, 0, 1.5, 0.5)})[0])

    def test_ghi_va_go(self):  # nhãn hợp tên (lệch dịch vụ -> ghép chỉ gợi ý) + giờ -> tự duyệt; ghi rồi gỡ được
        self.hd("K1-D", D, "K1", "Phan Thị Lan", "CSD", "10:05")
        self.hd("L1-D", D, "L1", "Trần Văn Nam", "CSD", "10:20")
        ids = self.don_vi("10:08", ocr0="Lan- pico 10/10/26")
        A.ghep_ngay(self.c, D)
        self.assertNotEqual(self.c.execute("SELECT do_tin FROM photos WHERE id=?", (ids[0],)).fetchone()[0], "chac")
        kq = A.tu_duyet_on_dinh(self.c, [D])
        self.assertEqual({kq[i][0] for i in ids}, {"K1-D"})
        luc = "2026-10-16T22:00:00"
        for i, (hd, _, ly) in kq.items():
            self.c.execute("UPDATE photos SET may_hd=?, may_ly_do=?, may_luc=? WHERE id=?", (hd, ly, luc, i))
        A.ghep_ngay(self.c, D)
        r = self.c.execute("SELECT goi_y_hd, do_tin, ly_do, xn_hd FROM photos WHERE id=?", (ids[1],)).fetchone()
        self.assertEqual((r[0], r[1], r[3]), ("K1-D", "chac", None))
        self.assertTrue(r[2].startswith("tự duyệt: "))
        with unittest.mock.patch.object(A, "ket_noi", lambda: self.c):
            A.cmd_tu_duyet(SimpleNamespace(thang=["2026-10"], go=True, ghi=False))
        r = self.c.execute("SELECT may_hd, ly_do, do_tin FROM photos WHERE id=?", (ids[1],)).fetchone()
        self.assertIsNone(r[0])
        self.assertNotEqual(r[2], "chac")

    def test_xn_khong_bi_de(self):  # âm: ảnh đã duyệt có may_hd (dữ liệu cũ) -> ghép không áp tự duyệt
        self.hd("K1-D", D, "K1", "Phan Thị Lan", "CSD", "10:05")
        a = self.anh(D, "10:08:10")
        self.c.execute("UPDATE photos SET xn_hd='K1-D', may_hd='L1-D', may_ly_do='x' WHERE id=?", (a,))
        A.ghep_ngay(self.c, D)
        self.assertFalse((self.c.execute("SELECT ly_do FROM photos WHERE id=?", (a,)).fetchone()[0] or "")
                         .startswith("tự duyệt"))

    def test_mat_hoc_lap(self):  # vòng lặp: 2 đơn vị nhận theo nhãn+giờ dạy mặt P-N -> đơn vị 3 chỉ mặt+giờ được nhận
        self.hd("N1-a", "2026-10-08", "N1", "Đỗ Thị Ngân", "CSD", "10:05")
        self.hd("N1-b", "2026-10-09", "N1", "Đỗ Thị Ngân", "CSD", "10:05")
        self.hd("N1-c", D, "N1", "Đỗ Thị Ngân", "CSD", "10:05")
        for ngay in ("2026-10-08", "2026-10-09", D):
            self.hd(f"X-{ngay}", ngay, "X1", "Lý Văn Tâm", "Pico", "16:00")
        for ngay, ocr in (("2026-10-08", "Ngân 10:00"), ("2026-10-09", "Ngân 10:00"), (D, "")):
            for i in range(3):
                pid = self.anh(ngay, f"10:08:{10 + i * 5}", km="P-N")
                if ngay != D and i == 0:
                    self.c.execute("UPDATE photos SET ocr='Ngân- csd' WHERE id=?", (pid,))
        ngays = ["2026-10-08", "2026-10-09", D]
        for ngay in ngays:
            A.ghep_ngay(self.c, ngay)
        self.c.execute("UPDATE photos SET do_tin='chua_ro', goi_y_hd=NULL WHERE do_tin != 'chac' OR do_tin IS NULL")
        self.c.execute("UPDATE photos SET do_tin='chua_ro', goi_y_hd=NULL, ly_do='' WHERE ngay IN (?,?,?)", ngays)
        kq = A.tu_duyet_on_dinh(self.c, ngays)
        ids3 = [r[0] for r in self.c.execute("SELECT id FROM photos WHERE ngay=?", (D,))]
        self.assertEqual({kq[i][0] for i in ids3 if i in kq}, {"N1-c"})


import unittest.mock  # noqa: E402

if __name__ == "__main__":
    unittest.main()
