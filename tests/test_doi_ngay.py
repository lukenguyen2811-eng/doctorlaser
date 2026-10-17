"""doi_ngay.py (Lượng 17/10): đổi ngày chụp trong app Ảnh cho ảnh KHÔNG EXIF trễ 1–2 ngày so với HĐ. DB tạm, dữ liệu
bịa, PhotoKit giả.

Chạy:  python3 -m unittest tests/test_doi_ngay.py
"""
import datetime as dt
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_ten_cuoi_mat_anh import A, Nen  # noqa: E402
import doi_ngay as DN  # noqa: E402


class Asset:
    def __init__(self, u, nguon=1):
        self.u, self.nguon, self.ngay = u, nguon, None

    def localIdentifier(self):
        return f"{self.u}/L0/001"

    def sourceType(self):
        return self.nguon


class KQ:
    def __init__(self, ds):
        self.ds = ds

    def count(self):
        return len(self.ds)

    def objectAtIndex_(self, i):
        return self.ds[i]


class P:  # PhotoKit giả
    kho: dict = {}

    class PHAsset:
        @staticmethod
        def fetchAssetsWithLocalIdentifiers_options_(ids, _):
            return KQ([P.kho[i.split("/")[0]] for i in ids if i.split("/")[0] in P.kho])

    class PHAssetChangeRequest:
        @staticmethod
        def changeRequestForAsset_(x):
            class R:
                def setCreationDate_(self, t):
                    x.ngay = t
            return R()

    class PHPhotoLibrary:
        @staticmethod
        def sharedPhotoLibrary():
            class L:
                def performChangesAndWait_error_(self, f, _):
                    f()
                    return True, None
            return L()


class DoiNgay(Nen):
    def setUp(self):
        super().setUp()
        P.kho = {}
        self.kit = DN.DoiKit(P=P, ns=lambda t: t)

    def a(self, ngay, gio, goc=0, ocr="", nguon=1, do_tin="chac", hd="H1"):
        i = self.anh(ngay, gio, ocr, ngay_goc=goc, do_tin=do_tin, goi_y=hd)
        P.kho[i] = Asset(i, nguon)
        return i

    def nen(self):
        self.hd("H1", "2026-10-08", "K1", "Phan Thị Lan", "CSD MỤN", "14:30")

    def test_chon_va_tinh_ngay_giu_thu_tu(self):
        self.nen()
        ids = [self.a("2026-10-10", "09:00:00"), self.a("2026-10-10", "09:00:07"), self.a("2026-10-10", "09:01:00")]
        doi, _ = DN.chon(self.c)
        moi = {d["id"]: d["thoi_gian_moi"] for d in doi}
        self.assertEqual([moi[i] for i in ids], ["2026-10-08T14:30:00", "2026-10-08T14:30:07", "2026-10-08T14:31:00"])

    def test_bo_qua_exif_tre_xa_truoc_hd_may_loai_nhan_ngay_khac(self):  # âm
        self.nen()
        e = self.a("2026-10-10", "09:00:00", goc=1)  # có EXIF
        x = self.a("2026-10-12", "09:00:00")  # trễ 4 ngày -> chỉ liệt kê
        t = self.a("2026-10-07", "09:00:00")  # trước HĐ -> chỉ liệt kê
        m = self.a("2026-10-10", "10:00:00", ocr="Chuyển khoản thành công 1.300.000 VND Vietcombank")
        self.c.execute("UPDATE photos SET may_loai='bien_lai' WHERE id=?", (m,))
        n = self.a("2026-10-10", "11:00:00", ocr="Lan - csd 1/10/26")  # nhãn ngày khác ngày HĐ
        doi, khong = DN.chon(self.c)
        self.assertFalse({d["id"] for d in doi} & {e, x, t, m, n})
        ly = {d["id"]: d["ly_do"] for d in khong}
        self.assertEqual((ly[x], ly[t]), ("trễ > 2 ngày", "ngày ảnh TRƯỚC ngày HĐ"))
        self.assertIn(m, ly)
        self.assertIn(n, ly)
        self.assertNotIn(e, ly)

    def test_goi_y_khong_doi(self):  # âm: chỉ ảnh chắc / đã duyệt
        self.nen()
        g = self.a("2026-10-10", "09:00:00", do_tin="goi_y")
        self.assertFalse(DN.chon(self.c)[0])
        self.assertTrue(g)

    def test_ghi_luu_ngay_cu_truoc_doi_db_va_go(self):
        self.nen()
        i = self.a("2026-10-10", "09:00:00")
        s = self.a("2026-10-10", "09:00:05", nguon=2)  # ảnh album chia sẻ -> bỏ qua
        doi, _ = DN.chon(self.c)
        xong, bo, _ = DN.ghi(self.c, doi, self.kit)
        self.assertEqual((xong, bo), (1, 1))
        self.assertEqual(P.kho[i].ngay, dt.datetime(2026, 10, 8, 14, 30))
        self.assertIsNone(P.kho[s].ngay)
        r = self.c.execute("SELECT ngay, thoi_gian FROM photos WHERE id=?", (i,)).fetchone()
        self.assertEqual(tuple(r), ("2026-10-08", "2026-10-08T14:30:00"))
        cu = self.c.execute("SELECT thoi_gian_cu, trang_thai FROM doi_ngay WHERE id=?", (i,)).fetchone()
        self.assertEqual(tuple(cu), ("2026-10-10T09:00:00", "xong"))
        self.assertFalse(DN.chon(self.c)[0])  # chạy lại không đổi lần 2
        self.assertEqual(DN.go(self.c, self.kit), 1)
        self.assertEqual(P.kho[i].ngay, dt.datetime(2026, 10, 10, 9, 0))
        r = self.c.execute("SELECT ngay, thoi_gian FROM photos WHERE id=?", (i,)).fetchone()
        self.assertEqual(tuple(r), ("2026-10-10", "2026-10-10T09:00:00"))

    def test_hd_khong_gio_mac_dinh_12h(self):
        self.hd("H1", "2026-10-08", "K1", "Phan Thị Lan", "CSD MỤN", "")
        self.a("2026-10-09", "09:00:00")
        self.assertEqual(DN.chon(self.c)[0][0]["thoi_gian_moi"], "2026-10-08T12:00:00")
