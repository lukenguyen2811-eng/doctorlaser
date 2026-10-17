"""doi_ngay.py (Lượng 17/10): đổi ngày chụp trong app Ảnh cho ảnh KHÔNG EXIF trễ 1–2 ngày so với HĐ. DB tạm, dữ liệu
bịa, PhotoKit giả.

Chạy:  python3 -m unittest tests/test_doi_ngay.py
"""
import datetime as dt
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_ten_cuoi_mat_anh import A, D, Nen  # noqa: E402
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


class ToiDa(DoiNgay):
    def test_toi_da_nhom_moi_nhat(self):
        self.nen()
        self.hd("H2", "2026-09-01", "K2", "Trần Văn Nam", "CSD MỤN", "10:00")
        cu = [self.a("2026-09-02", "09:00:00", hd="H2"), self.a("2026-09-02", "09:00:05", hd="H2")]
        moi = [self.a("2026-10-09", "09:00:00"), self.a("2026-10-09", "09:00:05")]
        doi, _ = DN.chon(self.c)
        self.assertEqual({d["id"] for d in DN.gioi_han(doi, 1)}, set(moi))  # đủ cả nhóm, nhóm mới nhất
        self.assertEqual({d["id"] for d in DN.gioi_han(doi, 0)}, set(cu + moi))
        DN.ghi(self.c, DN.gioi_han(doi, 1), self.kit)
        doi2, _ = DN.chon(self.c)  # chạy lại -> nhóm kế
        self.assertEqual({d["id"] for d in DN.gioi_han(doi2, 1)}, set(cu))


class Vong16b(DoiNgay):  # CEO 17/10 lần 16 sau soát: kiểm cả bộ, giờ tránh chồng, ảnh dời không làm neo, nền
    def test_bo_co_nhan_ngay_khac_chan_ca_bo(self):  # G22/G6
        self.nen()
        ids = [self.a("2026-10-10", "09:00:00"), self.a("2026-10-10", "09:00:05")]
        self.a("2026-10-10", "09:00:10", ocr="Lan - csd 10/10/26", do_tin="goi_y")  # ảnh cùng bộ nhãn ngày ảnh
        doi, khong = DN.chon(self.c)
        self.assertFalse(doi)
        self.assertTrue(all("khác ngày HĐ" in d["ly_do"] for d in khong if d["id"] in ids))

    def test_chu_thich_ddmmyyyy_chan(self):
        self.nen()
        i = self.a("2026-10-10", "09:00:00")
        self.c.execute("UPDATE photos SET chu_thich='10102026' WHERE id=?", (i,))
        self.assertFalse(DN.chon(self.c)[0])

    def test_ocr_nhieu_ngay_bang_ngay_anh_chan(self):  # G19 'CSd 26 02/03/26' -> doc_nhan không đọc
        self.nen()
        self.a("2026-10-10", "09:00:00", ocr="CSd 26 10/10/26")
        self.assertFalse(DN.chon(self.c)[0])

    def test_bo_co_anh_exif_chan(self):  # G19/G4/G8
        self.nen()
        self.a("2026-10-10", "09:00:00")
        self.a("2026-10-10", "09:03:00", goc=1, do_tin="goi_y")
        doi, khong = DN.chon(self.c)
        self.assertFalse(doi)
        self.assertTrue(any("EXIF" in d["ly_do"] for d in khong))

    def test_bo_khach_khac_cach_xa_khong_chan(self):  # âm: ảnh EXIF / nhãn của khách khác ngoài 10' không chặn
        self.nen()
        self.hd("H9", "2026-10-10", "K9", "Trần Văn Nam", "CSD MỤN", "15:00")
        self.a("2026-10-10", "09:00:00")
        self.a("2026-10-10", "15:00:00", goc=1, hd="H9")
        self.assertEqual(len(DN.chon(self.c)[0]), 1)

    def test_gio_moi_tranh_chong_bo_co_san(self):  # B03
        self.nen()
        self.anh("2026-10-08", "14:30:20", ngay_goc=1)  # bộ có sẵn ở ngày HĐ đúng giờ HĐ
        self.a("2026-10-10", "09:00:00")
        d = DN.chon(self.c)[0][0]
        self.assertGreaterEqual(d["thoi_gian_moi"], "2026-10-08T14:31:21")
        self.assertIn("tránh chồng", d["ly_do"])

    def test_anh_doi_giu_hd_khong_lam_neo(self):  # ghép ngày mới: ảnh dời giữ HĐ, ảnh khác không được kéo theo
        self.nen()
        self.hd("H8", "2026-10-08", "K8", "Lê Thị Hoa", "CSD MỤN", "08:00")
        i = self.a("2026-10-10", "09:00:00")
        k = self.anh("2026-10-08", "17:00:00", ngay_goc=0)  # ảnh trống ở ngày mới
        doi, _ = DN.chon(self.c)
        DN.ghi(self.c, doi, self.kit)
        r = self.c.execute("SELECT goi_y_hd, do_tin, ly_do FROM photos WHERE id=?", (i,)).fetchone()
        self.assertEqual(tuple(r)[:2], ("H1", "chac"))
        self.assertIn("đã dời ngày", r[2])
        self.assertNotEqual(self.c.execute("SELECT do_tin FROM photos WHERE id=?", (k,)).fetchone()[0], "chac")

    def test_nen_chan_len_chac_moi_va_doi_hd(self):  # B15
        nen = {"a": ("goi_y", "H1"), "b": ("chac", "H1"), "c": ("chac", "H1")}
        kq = {"a": {"do_tin": "chac", "hd": "H1", "xn": None, "ly_do": ""},
              "b": {"do_tin": "chac", "hd": "H2", "xn": None, "ly_do": ""},
              "c": {"do_tin": "chac", "hd": "H1", "xn": None, "ly_do": ""}}
        A._chan_theo_nen(kq, nen)
        self.assertEqual([kq[x]["do_tin"] for x in "abc"], ["goi_y", "goi_y", "chac"])


class Vong16c(DoiNgay):  # soát 16b: bản chép ảnh buổi cũ
    def test_nhan_khong_nam_khac_ngay_hd_chan(self):  # N17 '2/10', N29 '12/11'
        self.nen()
        self.a("2026-10-10", "09:00:00", ocr="cs mv co2 lần1 2/10")
        self.assertFalse(DN.chon(self.c)[0])

    def test_nhan_khong_nam_dung_ngay_hd_khong_chan(self):  # âm
        self.nen()
        self.a("2026-10-10", "09:00:00", ocr="Lan prp 8/10")
        self.assertEqual(len(DN.chon(self.c)[0]), 1)

    def test_hinh_anh_truoc_sau_chan(self):
        self.nen()
        i = self.a("2026-10-10", "09:00:00")
        self.c.execute("UPDATE photos SET chu_thich='HÌNH ẢNH TRƯỚC SAU' WHERE id=?", (i,))
        self.assertFalse(DN.chon(self.c)[0])

    def _dhash(self, h_moi, h_exif):
        self.nen()
        self.hd("H0", "2025-02-04", "K1", "Phan Thị Lan", "CSD MỤN", "10:00")
        i = self.a("2026-10-10", "09:00:00")
        e = self.anh("2025-02-04", "10:05:00", ngay_goc=1, do_tin="chac", goi_y="H0")
        self.c.execute("UPDATE photos SET anh_xem=id")
        cu = DN.DHASH
        DN.DHASH = lambda p: {i: h_moi, e: h_exif}.get(p)
        try:
            return DN.chon(self.c)
        finally:
            DN.DHASH = cu

    def test_trung_hinh_exif_cung_khach_chan(self):  # N8
        doi, khong = self._dhash(0b1011, 0b1000)  # lệch 2 bit
        self.assertFalse(doi)
        self.assertTrue(any("trùng hình" in d["ly_do"] for d in khong))

    def test_khac_hinh_khong_chan(self):  # âm: lệch > 4 bit
        doi, _ = self._dhash(0b11111111, 0)
        self.assertEqual(len(doi), 1)


class LienGiay(Nen):  # soát 17/10: đợt nhiều khách không hạ ảnh chụp liền 0–2s ảnh nhãn chắc cùng người/không mặt
    def nen(self):
        self.hd("H1", D, "K1", "Phan Thị Lan", "FILLER", "16:00")
        self.hd("H2", D, "K2", "Trần Văn Nam", "CSD MỤN", "16:10")

    def bo(self, gio, km=""):
        ids = [self.anh(D, "16:51:35", "Phan Thị Lan - filler 10/10/26", km="P-L"), self.anh(D, gio, km=km),
               self.anh(D, "16:52:30", "Trần Văn Nam - csd 10/10/26", km="P-N")]
        return ids, self.ghep()

    def test_lien_1s_khong_mat_chac(self):
        self.nen()
        ids, kq = self.bo("16:51:36")
        self.assertEqual(kq[ids[1]][:2], ("H1", "chac"))

    def test_cach_xa_khong_ap(self):  # âm
        self.nen()
        ids, kq = self.bo("16:51:50")
        self.assertNotEqual(kq[ids[1]][1], "chac")

    def test_mat_khac_khong_ap(self):  # âm
        self.nen()
        ids, kq = self.bo("16:51:36", km="P-Z")
        self.assertNotEqual(kq[ids[1]][1], "chac")


class LienGiayTen(LienGiay):  # neo khớp TÊN đầy đủ trên ảnh (không gạch) cũng tính (ca D410D78E)
    def bo(self, gio, km=""):
        ids = [self.anh(D, "16:51:35", "PHAN THỊ LAN", km="P-L"), self.anh(D, gio, km=km),
               self.anh(D, "16:52:30", "Trần Văn Nam - csd 10/10/26", km="P-N")]
        return ids, self.ghep()


class SuaNho(DoiNgay):  # soát 16c
    def test_nguoi_duyet_khong_doi(self):  # ca C28
        self.nen()
        i = self.a("2026-10-10", "09:00:00", do_tin="chua_ro")
        self.c.execute("UPDATE photos SET xn_hd='H1' WHERE id=?", (i,))
        doi, khong = DN.chon(self.c)
        self.assertFalse(doi)
        self.assertEqual([d["ly_do"] for d in khong if d["id"] == i], ["người đã duyệt (xn_hd) — không tự đổi ngày"])

    def test_nen_cho_luat_lien_giay_cung_hd(self):  # đo = thật: nền gợi ý H1, luật 0–2s nâng chắc H1 -> giữ
        nen = {"a": ("goi_y", "H1"), "b": ("goi_y", "H1")}
        kq = {"a": {"do_tin": "chac", "hd": "H1", "xn": None, "ly_do": "", "lien_nang": True},
              "b": {"do_tin": "chac", "hd": "H1", "xn": None, "ly_do": ""}}
        A._chan_theo_nen(kq, nen)
        self.assertEqual((kq["a"]["do_tin"], kq["b"]["do_tin"]), ("chac", "goi_y"))
