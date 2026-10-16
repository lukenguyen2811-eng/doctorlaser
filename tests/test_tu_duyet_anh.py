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

    def test_mat_hai_chu_khac_k_chan(self):  # ca B9F837F3: mặt có nhãn của 2 khách khác (không có K) -> phản bác K
        d = A._td_diem([], "K", [{"ten_kh": "Trần Thị Minh", "dich_vu": "Sẹo", "gio": "10:00", "ngay": D, "code": "x"}],
                       {"chu_mat": set(), "chu_nhan_mat": {"A", "B"}, "nhans": [], "gio": None, "co_goc": False,
                        "goi_y": None})
        self.assertEqual(d["mat"], A.TD_MAT_PHAN)
        d = A._td_diem([], "A", [{"ten_kh": "Trần Thị Minh", "dich_vu": "Sẹo", "gio": "10:00", "ngay": D, "code": "x"}],
                       {"chu_mat": set(), "chu_nhan_mat": {"A", "B"}, "nhans": [], "gio": None, "co_goc": False,
                        "goi_y": None})
        self.assertEqual(d["mat"], 0.0)  # âm: K nằm trong số chủ -> không phản bác

    def test_mat_lan_nhieu_khach_khong_chan(self):  # âm (đo moi8): mặt có ảnh nhãn của nhiều khách -> không tính chủ
        self.assertEqual(A._td_chu_mat({"cum": {}}, {}, "u", {"u": {"A": 3, "B": 2}}), set())
        self.assertEqual(A._td_chu_mat({"cum": {}}, {}, "u", {"u": {"A": 7}}), {"A"})
        self.assertEqual(A._td_chu_mat({"cum": {}}, {}, "u", {"u": {"A": 1}}), set())

    def test_ro_buoi(self):  # khách 2 buổi dịch vụ trong ngày: chỉ nhận khi nhãn dịch vụ hoặc giờ phân định rõ
        import datetime as dt_
        vs = [{"code": "a", "ngay": D, "gio": "10:00", "dich_vu": "CSD MỤN"},
              {"code": "b", "ngay": D, "gio": "11:00", "dich_vu": "LASER PICOLIGHT"}]
        ctx = {"gio": dt_.datetime.fromisoformat(f"{D}T10:10:00"), "co_goc": True}
        self.assertFalse(A._td_ro_buoi(vs, vs[0], [], ctx))  # cách HĐ kia 50' (< 90'): không rõ buổi
        self.assertTrue(A._td_ro_buoi(vs, vs[0], ["csd"], ctx))  # nhãn csd chỉ khớp a
        vs[1]["gio"] = "15:00"
        self.assertTrue(A._td_ro_buoi(vs, vs[0], [], ctx))  # giờ sát a, xa b
        vs[1]["dich_vu"] = "KEM REVITALUX"
        vs[1]["gio"] = "10:15"
        self.assertTrue(A._td_ro_buoi(vs, vs[0], [], ctx))  # HĐ kia chỉ sản phẩm

    def test_hd_my_pham_khong_thang_dich_vu(self):  # ca 920BC0D2: tự duyệt chọn HĐ dịch vụ, không HĐ kem gần giờ hơn
        self.hd("K1-a", D, "K1", "Phan Thị An", "U mạch máu", "10:52")
        self.hd("K1-b", D, "K1", "Phan Thị An", "Kem Revitalux", "11:53")
        self.hd("L1-D", D, "L1", "Trần Văn Nam", "CSD", "11:30")
        ids = self.don_vi("11:44", ocr0="An- pico 10/10/26")
        A.ghep_ngay(self.c, D)
        kq = A.tu_duyet_on_dinh(self.c, [D])
        self.assertNotIn("K1-b", {kq[i][0] for i in ids if i in kq})
        self.assertTrue(A._hd_that("U MẠCH MÁU"))
        self.assertFalse(A._hd_that("KEM TRỊ THÂM NÁCH"))  # âm: sản phẩm có chữ 'thâm' vẫn là sản phẩm

    def test_ham_quyet(self):
        d = lambda m, n, g, y: {"mat": m, "nhan": n, "gio": g, "goi_y": y}  # noqa: E731
        self.assertEqual(A._td_quyet({"K": d(3, 0, 1.5, 0), "L": d(-5, 0, 1.5, 0)})[0], "K")
        self.assertIsNone(A._td_quyet({"K": d(3, 0, 0.5, 0.5), "L": d(-5, 0, 0, 0)})[0])  # mặt + giờ xa: không nhận
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
            A.cmd_tu_duyet(SimpleNamespace(thang=["2026-10"], go=True, ghi=False, lap=0))
        r = self.c.execute("SELECT may_hd, ly_do, do_tin FROM photos WHERE id=?", (ids[1],)).fetchone()
        self.assertIsNone(r[0])
        self.assertNotEqual(r[2], "chac")

    def test_lap_on_dinh(self):  # lặp: lượt 1 nhận, lượt 2 không thêm không bỏ -> dừng; ảnh đã nhận vẫn giữ HĐ
        self.hd("K1-D", D, "K1", "Phan Thị Lan", "CSD", "10:05")
        self.hd("L1-D", D, "L1", "Trần Văn Nam", "CSD", "10:20")
        ids = self.don_vi("10:08", ocr0="Lan- pico 10/10/26")
        A.ghep_ngay(self.c, D)
        ra = A.tu_duyet_lap(self.c, [D], 5, in_ra=lambda *x: None)
        self.assertEqual(ra[0]["nhan_moi"], 3)
        self.assertEqual((ra[-1]["nhan_moi"], ra[-1]["bo"], len(ra)), (0, 0, 2))
        self.assertEqual({r[0] for r in self.c.execute("SELECT may_hd FROM photos WHERE id IN (?,?,?)", ids)}, {"K1-D"})

    def test_lap_doi_hd_thi_bo(self):  # âm: ảnh đã tự duyệt mà lượt sau ra HĐ khác -> bỏ, không xét lại
        self.hd("K1-D", D, "K1", "Phan Thị Lan", "CSD", "10:05")
        self.hd("L1-D", D, "L1", "Trần Văn Nam", "CSD", "10:20")
        ids = self.don_vi("10:08", ocr0="Lan- pico 10/10/26")
        A.ghep_ngay(self.c, D)
        for i in ids:  # giả lập lượt trước đã nhận HĐ khác
            self.c.execute("UPDATE photos SET may_hd='L1-D', may_ly_do='x', may_luc='t' WHERE id=?", (i,))
        A.ghep_ngay(self.c, D)
        ra = A.tu_duyet_lap(self.c, [D], 3, in_ra=lambda *x: None)
        self.assertEqual(ra[0]["doi_hd"], 3)
        r = self.c.execute("SELECT may_hd, may_ly_do, do_tin FROM photos WHERE id=?", (ids[1],)).fetchone()
        self.assertIsNone(r[0])
        self.assertTrue(r[1].startswith("BỎ"))
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


class Vong12(TuDuyet):  # CEO 17/10 lần 12: buổi theo gói (A/B1/B2), L5 mặt yếu, L3 phần còn lại của đơn vị đã chắc
    def nen(self, goi=(("G1", "2026-09-20", "COMBO CSD ( 10 LẦN )"),)):
        self.cum("K1", "Phan Thị Lan", "P-K")
        for code, ngay, dv in goi:
            self.hd(code, ngay, "K1", "Phan Thị Lan", dv, "09:00")
        self.hd("L1-D", D, "L1", "Trần Văn Nam", "CSD", "10:20")
        self.hd("M1-D", D, "M1", "Lê Thị Hoa", "CSD", "18:20")

    def ghep_td(self, *anh):
        ids = [self.anh(D, g, o, km=k) for g, o, k in anh]
        A.ghep_ngay(self.c, D)
        kq = {r[0]: (r[1], r[2], r[3]) for r in self.c.execute("SELECT id, goi_y_hd, do_tin, ly_do FROM photos WHERE ngay=?", (D,))}
        return ids, kq, A.tu_duyet_on_dinh(self.c, [D])

    def test_b2_goi_duy_nhat_goi_y_roi_tu_duyet(self):
        self.nen()
        ids, kq, td = self.ghep_td(("14:00:10", "", "P-K"), ("14:00:15", "", "P-K"))
        self.assertEqual(kq[ids[0]][:2], ("G1", "goi_y"))
        self.assertIn(A._MOC_GOI, kq[ids[0]][2])
        self.assertEqual({td[i][0] for i in ids}, {"G1"})

    def test_b1_nhan_dich_vu_khop_1_goi_chac(self):
        self.nen()
        ids, kq, _ = self.ghep_td(("14:00:10", "Lan - csd 10/10/26", "P-K"), ("14:00:15", "", "P-K"))
        self.assertEqual(kq[ids[0]][:2], ("G1", "chac"))
        self.assertIn("buổi theo gói — ngày chụp 10/10, HĐ gói G1 ngày 20/09", kq[ids[0]][2])

    def test_b3_hai_goi_khong_ap(self):  # âm: >= 2 HĐ gói, không nhãn phân định
        self.nen((("G1", "2026-09-20", "COMBO CSD ( 10 LẦN )"), ("G2", "2026-08-20", "COMBO TRIỆT LÔNG ( 6 LẦN )")))
        ids, kq, td = self.ghep_td(("14:00:10", "", "P-K"), ("14:00:15", "", "P-K"))
        self.assertNotIn(A._MOC_GOI, kq[ids[0]][2] or "")
        self.assertFalse(any(td.get(i, ("",))[0] in ("G1", "G2") for i in ids))

    def test_goi_moi_sau_ngay_chup_khong_ap(self):  # âm: không gói trước ngày chụp, có gói MỚI sau -> không áp (cả A)
        self.nen((("G9", "2026-10-11", "COMBO CSD ( 10 LẦN )"),))
        ids, kq, td = self.ghep_td(("14:00:10", "", "P-K"), ("14:00:15", "", "P-K"))
        self.assertNotIn("G9", {kq[i][0] for i in ids})
        self.assertFalse(any(i in td for i in ids))

    def test_a_hd_1_2_ngay_sau(self):
        self.nen((("S1", "2026-10-11", "CSD MỤN ( LẦN LẺ )"),))
        ids, kq, td = self.ghep_td(("14:00:10", "", "P-K"), ("14:00:15", "", "P-K"))
        self.assertEqual(kq[ids[0]][:2], ("S1", "goi_y"))
        self.assertIn(A._MOC_SAU, kq[ids[0]][2])
        self.assertEqual({td[i][0] for i in ids}, {"S1"})

    def test_tat_lg(self):  # TAT_LUAT=LG -> hành vi cũ
        self.nen()
        A._TAT.add("LG")
        try:
            ids, kq, td = self.ghep_td(("14:00:10", "", "P-K"), ("14:00:15", "", "P-K"))
        finally:
            A._TAT.discard("LG")
        self.assertNotIn(A._MOC_GOI, kq[ids[0]][2] or "")

    # ---- L5 mặt yếu ----
    def test_l5_mat_yeu_la_nguon_phu(self):
        ctx = {"chu_mat": set(), "chu_nhan_mat": set(), "nhans": [], "gio": A.dt.datetime(2026, 10, 10, 10, 8),
               "co_goc": True, "goi_y": None, "chu_mat_yeu": {"K"}}
        v = {"code": "H", "ngay": "2026-10-10", "gio": "10:05", "ten_kh": "x", "dich_vu": "CSD"}
        self.assertEqual(A._td_diem([], "K", [v], ctx)["mat"], A.TD_MAT_YEU)
        self.assertEqual(A._td_diem([], "J", [v], ctx)["mat"], 0.0)  # mặt yếu không phản bác khách khác

    def test_l5_mat_yeu_gio_khong_du(self):  # âm: mặt yếu + giờ sát -> không nhận
        d = {"K": {"mat": A.TD_MAT_YEU, "nhan": 0.0, "gio": 1.5, "goi_y": 0.0},
             "J": {"mat": 0.0, "nhan": 0.0, "gio": -1.5, "goi_y": 0.0}}
        self.assertIsNone(A._td_quyet(d)[0])

    def test_l5_mat_yeu_cong_nhan(self):
        d = {"K": {"mat": A.TD_MAT_YEU, "nhan": A.TD_NHAN_CO, "gio": 0.0, "goi_y": 0.0},
             "J": {"mat": 0.0, "nhan": A.TD_NHAN_PHAN, "gio": 0.0, "goi_y": 0.0}}
        self.assertEqual(A._td_quyet(d)[0], "K")

    def test_l5_mat_yeu_tu_anh_chac_ngay_khac(self):
        self.hd("K1-0", "2026-09-01", "K1", "Phan Thị Lan", "CSD")
        self.anh("2026-09-01", "10:00:00", km="P-W", do_tin="chac", goi_y="K1-0", ly_do="nhãn 'x-csd' khớp")
        cum = A.cum_khach(self.c)
        self.assertNotIn("P-W", cum["cum"])
        self.assertEqual(set(A._td_mat_yeu(self.c, cum)["P-W"]), {A._khoa_hd(self.c, cum, "K1-0", {})})

    # ---- L3 phần còn lại của đơn vị đã có ảnh chắc ----
    def l3(self, ly0="nhãn 'Lan-csd' khớp Phan Thị Lan", km1="", tat=False):
        self.hd("K1-D", D, "K1", "Phan Thị Lan", "CSD", "10:05")
        self.hd("L1-D", D, "L1", "Trần Văn Nam", "CSD", "15:00")
        ids = [self.anh(D, "10:08:10", km="P-K", do_tin="chac", goi_y="K1-D", ly_do=ly0),
               self.anh(D, "10:08:15", km=km1, do_tin="chua_ro"), self.anh(D, "10:08:20", do_tin="chua_ro")]
        if tat:
            A._TAT.add("L3")
        try:
            return ids, A.tu_duyet_on_dinh(self.c, [D])
        finally:
            A._TAT.discard("L3")

    def test_l3_phan_con_lai_theo_anh_chac(self):
        ids, td = self.l3()
        self.assertEqual({td[i][0] for i in ids[1:]}, {"K1-D"})
        self.assertNotIn(ids[0], td)  # ảnh chắc (ghép) không bị ghi đè

    def test_l3_anh_chac_theo_mat_khong_tinh(self):  # âm: ảnh chắc do luật mặt -> không làm nguồn bộ
        ids, td = self.l3(ly0="khuôn mặt thuộc khách K1 (cụm 9 ảnh đã xác nhận) + HĐ cùng ngày")
        self.assertFalse(any(i in td for i in ids))

    def test_l3_xen_ke_mat_khac(self):  # âm: ảnh còn lại mang mặt KHÁC ảnh chắc -> bỏ khỏi đơn vị
        ids, td = self.l3(km1="P-Z")
        self.assertNotIn(ids[1], td)

    def test_l3_tat(self):
        ids, td = self.l3(tat=True)
        self.assertFalse(any(i in td for i in ids))


class Vong13(Vong12):  # CEO 17/10 lần 13: chỉ siết
    def test_l5_tat_mac_dinh(self):
        self.assertFalse(A._luat_bat("L5"))
        A._BAT.add("L5")
        try:
            self.assertTrue(A._luat_bat("L5"))
        finally:
            A._BAT.discard("L5")

    def test_l3_bo_anh_phieu(self):  # ca 2DBFC2D8: ảnh phiếu giấy trong đơn vị đã chắc -> không theo
        self.hd("K1-D", D, "K1", "Phan Thị Lan", "CSD", "10:05")
        self.hd("L1-D", D, "L1", "Trần Văn Nam", "CSD", "15:00")
        ids = [self.anh(D, "10:08:10", km="P-K", do_tin="chac", goi_y="K1-D", ly_do="nhãn 'Lan-csd' khớp Phan Thị Lan"),
               self.anh(D, "10:08:15", "HỌ TÊN: Trần Văn Nam  SĐT: 0909", do_tin="chua_ro"),
               self.anh(D, "10:08:20", do_tin="chua_ro")]
        td = A.tu_duyet_on_dinh(self.c, [D])
        self.assertNotIn(ids[1], td)
        self.assertEqual(td[ids[2]][0], "K1-D")  # âm: ảnh thường vẫn theo

    def test_lg_nhuong_nhan_ten_khac_trong_bo(self):  # ca A37410F4: bộ có nhãn tên khách khác -> không gợi ý gói
        self.nen()
        ids, kq, td = self.ghep_td(("14:00:10", "", "P-K"), ("14:00:15", "", "P-K"), ("14:00:20", "Hoa - pico 10/10/26", "P-K"))
        self.assertFalse(any(A._MOC_GOI in (kq[i][2] or "") for i in ids))  # luật gói nhường (gợi ý cũ 'HĐ gần nhất' giữ như base)
        self.assertFalse(any(td.get(i, ("",))[0] == "G1" for i in ids))

    def test_lg_nhan_ten_khac_mat_khac_van_ap(self):  # âm: nhãn tên khác trên ảnh mặt KHÁC (người khác chụp liền)
        self.nen()
        ids, kq, _ = self.ghep_td(("14:00:10", "", "P-K"), ("14:00:15", "", "P-K"), ("14:00:20", "Hoa - pico 10/10/26", "P-H"))
        self.assertIn(A._MOC_GOI, kq[ids[0]][2] or "")

    def test_lg_nhan_ten_goi_cum_manh_van_ap(self):  # âm, ma21 DAD02C68: nhãn tên gọi khác ('Cẩm Lan') cùng mặt cụm mạnh K
        self.nen()
        ids, kq, _ = self.ghep_td(("14:00:10", "", "P-K"), ("14:00:15", "Cẩm Lan - csd 10/10/26", "P-K"))
        self.assertIn(A._MOC_GOI, kq[ids[0]][2] or "")

    def test_lg_nhan_cung_ten_van_ap(self):  # âm: nhãn trong bộ là tên chính khách -> vẫn áp
        self.nen()
        ids, kq, _ = self.ghep_td(("14:00:10", "", "P-K"), ("14:00:15", "Lan - csd 10/10/26", "P-K"))
        self.assertEqual(kq[ids[1]][:2], ("G1", "chac"))


class Vong14(Vong12):  # CEO 17/10 lần 14: chỉ siết / sửa gợi ý
    # ---- 2. gói hết buổi + ưu tiên HĐ dịch vụ khớp nhãn ±30 ngày (ca 12CB524D) ----
    def goi(self, dv="COMBO SẸO RỖ ( 4 LẦN )", so_ngay=4):
        self.hd("G4", "2025-09-09", "K1", "Phan Thị Lan", dv, "09:00")
        for i in range(so_ngay):
            ng = f"2025-{9 + i:02d}-15"
            self.hd(f"L{i}", ng, "K1", "Phan Thị Lan", "CSD", "09:00")
            self.anh(ng, "10:00:00", km="P-K", do_tin="chac", goi_y=f"L{i}", ly_do="nhãn 'x-seo' khớp")
        return self.c.execute("SELECT * FROM visits WHERE code='G4'").fetchone()

    def test_goi_het_buoi(self):
        v = self.goi()
        self.assertFalse(A._goi_con_buoi(self.c, v, ["K1"], "2026-02-26"))

    def test_goi_con_buoi(self):  # âm: mới 3/4 buổi
        v = self.goi(so_ngay=3)
        self.assertTrue(A._goi_con_buoi(self.c, v, ["K1"], "2026-02-26"))

    def test_goi_khong_ghi_so_lan_coi_nhu_con(self):  # âm: gói không ghi số lần ('BH 12 tháng') -> không biết -> còn
        v = self.goi(dv="COMBO XÓA VEIN MẶT ( BH 12 THÁNG ) - TẶNG KÈM 2 LẦN IPL")
        self.assertTrue(A._goi_con_buoi(self.c, v, ["K1"], "2026-02-26"))

    def test_uu_tien_hd_dich_vu_khop_nhan_30_ngay(self):  # nhãn co2, gói CSD không khớp -> gợi ý HĐ fractional gần
        self.nen()
        self.hd("F1", "2026-10-03", "K1", "Phan Thị Lan", "LASER FRACTIONAL CO2", "09:00")
        ids, kq, td = self.ghep_td(("14:00:10", "Lan - co2 10/10/26", "P-K"), ("14:00:15", "", "P-K"))
        self.assertEqual(kq[ids[1]][:2], ("F1", "goi_y"))
        self.assertIn("HĐ dịch vụ khớp nhãn", kq[ids[1]][2])
        self.assertNotEqual(td.get(ids[1], ("",))[0], "G1")

    # ---- 1. ảnh cũ lưu lại: ngày trên nhãn lệch > 7 ngày (ca 20FBABFE) ----
    def ds(self, ngay_nhan, mat2="P-K"):
        import datetime as dt
        self.hd("HN", "2026-10-08", "K1", "Phan Thị Lan", "PRP", "09:00")
        self.hd("HC", "2025-03-28", "K1", "Phan Thị Lan", "PRP", "09:00")
        g = dt.datetime(2026, 10, 10, 14, 39)
        x = {"hd": "HN", "do_tin": "chac", "ly_do": "khuôn mặt thuộc khách K1 (cụm 9 ảnh) + HĐ cùng ngày (HĐ ngày 08/10)",
             "diem": 80, "xn": None, "bo": 1, "gio": g, "mat_ds": {"P-K"}, "nhan": False, "nhan_ds": []}
        y = dict(x, mat_ds={mat2}, nhan=True, nhan_ds=A.doc_nhan(f"Lan- prp {ngay_nhan}", 2026))
        A._ha_ngay_nhan_lech(self.c, "2026-10-10", [x, y])
        return x

    def test_nhan_ngay_cu_ha_goi_y_hd_gan_ngay_nhan(self):
        x = self.ds("28/03/2025")
        self.assertEqual((x["hd"], x["do_tin"]), ("HC", "goi_y"))

    def test_nhan_sai_nam_khong_ha(self):  # âm: cùng ngày/tháng, khác năm = OCR sai năm
        self.assertEqual(self.ds("10/10/2023")["do_tin"], "chac")

    def test_nhan_ngay_sau_khong_ha(self):  # âm: ngày nhãn SAU ngày ảnh
        self.assertEqual(self.ds("28/11/2026")["do_tin"], "chac")

    def test_nhan_nguoi_khac_khong_ha(self):  # âm: ảnh nhãn mang mặt khác
        self.assertEqual(self.ds("28/03/2025", mat2="P-Z")["do_tin"], "chac")

    # ---- 3. nhãn không gạch, không năm (ca 2F1DF9D9) ----
    def test_nhan_khong_nam_doc_duoc(self):
        n = A.doc_nhan("Phạm Kim Anh kh mới 22/10 laser đốt mụn L1", 2020)
        self.assertEqual([(x["ten"], x["ngay"], x.get("khong_nam")) for x in n], [("pham kim anh", "2020-10-22", True)])

    def test_nhan_khong_nam_khong_bat_chu_thuong(self):  # âm
        self.assertEqual(A.doc_nhan("giá 1/2 hộp", 2020), [])
        self.assertEqual(A.doc_nhan("Lan 3/4", 2020), [])

    def test_nhan_khong_nam_chi_goi_y(self):
        self.hd("HK", "2026-10-08", "K9", "Phạm Thị Kim Anh", "LASER ĐỐT MỤN", "09:00")
        self.hd("HX", D, "K8", "Trần Văn Nam", "CSD", "11:00")
        i = self.anh(D, "11:27:44", "Phạm Kim Anh kh mới 8/10 laser đốt mụn L1", ngay_goc=0)
        A.ghep_ngay(self.c, D)
        r = self.c.execute("SELECT goi_y_hd, do_tin FROM photos WHERE id=?", (i,)).fetchone()
        self.assertEqual(tuple(r), ("HK", "goi_y"))
