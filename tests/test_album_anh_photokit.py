"""album_anh.py ghi album bằng PhotoKit — module Photos GIẢ (không chạm app Ảnh / PhotoKit thật).

Chạy:  python3 -m unittest tests/test_album_anh_photokit.py
"""
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

_GOC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [_GOC, os.path.join(_GOC, "tests")]
os.environ.setdefault("ANH_DB", os.path.join(tempfile.mkdtemp(), "t.db"))
import album_anh as M  # noqa: E402
import test_album_anh_dong_bo as T  # noqa: E402  (dùng lại dữ liệu bịa của DongBo.setUp)


def photos_gia(thu_vien=(), hong=0, hong_trong_khoi=False):
    """Module Photos giả. thu_vien = uuid có trong thư viện. hong = số lần performChanges đầu trả lỗi."""
    st = {"ops": [], "goi": 0, "hong": hong, "trong_khoi": False, "dem_id": 0}

    def moi_id(loai):
        st["dem_id"] += 1
        return f"{loai}{st['dem_id']}/L0/040"

    class KetQua:
        def __init__(self, ds):
            self.ds = list(ds)

        def count(self):
            return len(self.ds)

        def objectAtIndex_(self, i):
            return self.ds[i]

        def firstObject(self):
            return self.ds[0] if self.ds else None

    class PHAsset:
        def __init__(self, u):
            self.u = u

        def localIdentifier(self):
            return f"{self.u}/L0/001"

        @staticmethod
        def fetchAssetsWithLocalIdentifiers_options_(ids, opt):
            return KetQua(KHO[i.split("/")[0]] for i in ids if i.split("/")[0] in KHO)

        @staticmethod
        def fetchAssetsInAssetCollection_options_(a, opt):
            return KetQua(KHO[u] for u in a.anh)

    KHO = {u: PHAsset(u) for u in thu_vien}
    DOI_TUONG = {}

    class PHCollectionList:
        def __init__(self, ten):
            self.ten, self.con, self.id = ten, [], moi_id("TM")
            DOI_TUONG[self.id] = self

        def localizedTitle(self):
            return self.ten

        def localIdentifier(self):
            return self.id

        @staticmethod
        def fetchTopLevelUserCollectionsWithOptions_(opt):
            return KetQua(GOC)

        @staticmethod
        def fetchCollectionsInCollectionList_options_(f, opt):
            return KetQua(f.con)

        @staticmethod
        def fetchCollectionListsWithLocalIdentifiers_options_(ids, opt):
            return KetQua(DOI_TUONG[i] for i in ids if i in DOI_TUONG)

    class PHAssetCollection:
        def __init__(self, ten, anh=()):
            self.ten, self.anh, self.id = ten, list(anh), moi_id("AL")
            DOI_TUONG[self.id] = self

        def localizedTitle(self):
            return self.ten

        def localIdentifier(self):
            return self.id

        @staticmethod
        def fetchAssetCollectionsWithLocalIdentifiers_options_(ids, opt):
            return KetQua(DOI_TUONG[i] for i in ids if i in DOI_TUONG)

    GOC = []

    def can_khoi():
        assert st["trong_khoi"], "change request ngoài performChanges"
        if hong_trong_khoi:
            raise ValueError("khối hỏng")

    class Placeholder:
        def __init__(self, obj):
            self.obj = obj

        def localIdentifier(self):
            return self.obj.id

    class PHCollectionListChangeRequest:
        def __init__(self, f):
            self.f = f

        @staticmethod
        def creationRequestForCollectionListWithTitle_(ten):
            can_khoi()
            f = PHCollectionList(ten)
            GOC.append(f)  # mới tạo nằm ở cấp cao nhất; addChildCollections_ chuyển vào cha
            st["ops"].append(("tao_tm", ten))
            r = PHCollectionListChangeRequest(f)
            r.placeholderForCreatedCollectionList = lambda: Placeholder(f)
            return r

        @staticmethod
        def changeRequestForCollectionList_(f):
            can_khoi()
            return PHCollectionListChangeRequest(f)

        def addChildCollections_(self, ds):
            for ph in ds:
                o = ph.obj
                if o in GOC:
                    GOC.remove(o)
                self.f.con.append(o)

    class PHAssetCollectionChangeRequest:
        def __init__(self, a):
            self.a = a

        @staticmethod
        def creationRequestForAssetCollectionWithTitle_(ten):
            can_khoi()
            a = PHAssetCollection(ten)
            GOC.append(a)
            st["ops"].append(("tao_al", ten))
            r = PHAssetCollectionChangeRequest(a)
            r.placeholderForCreatedAssetCollection = lambda: Placeholder(a)
            return r

        @staticmethod
        def changeRequestForAssetCollection_(a):
            can_khoi()
            return PHAssetCollectionChangeRequest(a)

        @staticmethod
        def deleteAssetCollections_(ds):
            can_khoi()
            for a in ds:
                st["ops"].append(("xoa", a.ten))
                for f in DOI_TUONG.values():
                    if isinstance(f, PHCollectionList) and a in f.con:
                        f.con.remove(a)

        def addAssets_(self, kq):
            us = [x.u for x in (kq.ds if isinstance(kq, KetQua) else kq)]
            st["ops"].append(("them", self.a.ten, us))
            self.a.anh += [u for u in us if u not in self.a.anh]

        def removeAssets_(self, ds):
            us = [x.u for x in ds]
            st["ops"].append(("go", self.a.ten, us))
            self.a.anh = [u for u in self.a.anh if u not in us]

    class Loi:
        def localizedDescription(self):
            return "The operation couldn't be completed. (PHPhotosErrorDomain error 3300.)"

    class Lib:
        def performChangesAndWait_error_(self, khoi, err):
            st["goi"] += 1
            if st["hong"] > 0:
                st["hong"] -= 1
                return False, Loi()
            st["trong_khoi"] = True
            try:
                khoi()
            finally:
                st["trong_khoi"] = False
            return True, None

    class PHPhotoLibrary:
        @staticmethod
        def sharedPhotoLibrary():
            return LIB

    LIB = Lib()
    P = type("Photos", (), {})()
    for k, v in dict(PHAsset=PHAsset, PHCollectionList=PHCollectionList, PHAssetCollection=PHAssetCollection,
                     PHCollectionListChangeRequest=PHCollectionListChangeRequest,
                     PHAssetCollectionChangeRequest=PHAssetCollectionChangeRequest,
                     PHPhotoLibrary=PHPhotoLibrary).items():
        setattr(P, k, v)
    P.st, P.GOC = st, GOC
    return P


def cay(P):
    """{(thư mục con, album): [uuid]} đọc từ thư viện giả, chỉ trong 'Doctor Laser'."""
    cha = [f for f in P.GOC if f.ten == M.THU_MUC]
    ra = {}
    for f in cha:
        for g in f.con:
            for a in g.con:
                ra[(g.ten, a.ten)] = list(a.anh)
    return ra


THU_VIEN = ["a1", "a2", "a3", "a4", "a5", "a6", "a7", "a8", "a9"]


class PhotoKit(unittest.TestCase):
    setUp = T.DongBo.setUp
    tearDown = T.DongBo.tearDown

    def chay(self, P, *thamso):
        with mock.patch.object(M, "_photos", lambda: P), mock.patch.object(M, "_quyen", lambda: None), \
                mock.patch.object(M.subprocess, "run", side_effect=AssertionError("không được gọi osascript")), \
                mock.patch.object(sys, "argv", ["x", *thamso]), redirect_stdout(io.StringIO()) as out:
            try:
                M.main()
            except SystemExit:
                pass
        return out.getvalue()

    def test_tao_dung_thu_muc_album_roi_khong_doi_thi_khong_goi(self):
        P = photos_gia(THU_VIEN)
        out = self.chay(P, "--ghi")
        c = cay(P)
        self.assertEqual(len([f for f in P.GOC if f.ten == M.THU_MUC]), 1)  # thư mục cha không trùng
        self.assertEqual([f.ten for f in P.GOC], [M.THU_MUC])  # không album/thư mục lạc ra cấp cao nhất
        self.assertEqual(sorted(t for o, t in [x[:2] for x in P.st["ops"]] if o == "tao_tm"),
                         sorted([M.THU_MUC, M.TM_DV, M.TM_THANG, M.TM_KHACH]))
        self.assertEqual(c, {k: v for k, v in M.tinh_album(self.c).items()})
        self.assertEqual(c[(M.TM_DV, "DV · Laser Pico")], ["a2", "a6"])
        self.assertEqual(c[(M.TM_KHACH, "KH000888 · Khách Mới Bịa")], ["a7", "a8"])
        self.assertIn("lỗi 0", out)
        goi = P.st["goi"]
        self.chay(P, "--ghi")
        self.assertEqual(P.st["goi"], goi)  # không đổi -> không performChanges nào

    def test_them_thieu_go_thua_khong_xoa_album(self):
        P = photos_gia(THU_VIEN + ["zz"])
        self.chay(P, "--ghi")
        # Có người lỡ thêm tay ảnh zz vào album máy; lần ghi sau (da_album đổi) phải gỡ nó, không xoá album.
        al = next(a for f in P.GOC[0].con for a in f.con if a.ten == "DV · PRP")
        al.anh.append("zz")
        self.c.execute("UPDATE photos SET bo_qua=1 WHERE id='a6'")
        self.c.commit()
        P.st["ops"].clear()
        self.chay(P, "--ghi")
        self.assertEqual(al.anh, ["a2"])
        self.assertIn(("go", "DV · PRP", ["a6", "zz"]), P.st["ops"])
        self.assertFalse([o for o in P.st["ops"] if o[0] in ("tao_al", "xoa", "tao_tm")])
        self.assertEqual({o[1] for o in P.st["ops"]},
                         {"2026-09", "DV · Laser Pico", "DV · PRP", "KH000001 · Trần Thị Bịa"})
        # Ảnh mới duyệt thêm -> chỉ THÊM phần thiếu
        self.c.execute("UPDATE photos SET bo_qua=0 WHERE id='a6'")
        self.c.commit()
        P.st["ops"].clear()
        self.chay(P, "--ghi")
        self.assertIn(("them", "DV · PRP", ["a6"]), P.st["ops"])
        self.assertFalse([o for o in P.st["ops"] if o[0] == "go"])

    def test_album_het_anh_de_rong_hoac_xoa_khi_co_co(self):
        P = photos_gia(THU_VIEN)
        self.chay(P, "--ghi")
        self.c.execute("UPDATE photos SET bo_qua=1 WHERE id='a1'")
        self.c.commit()
        self.chay(P, "--ghi")
        self.assertEqual(cay(P)[(M.TM_DV, "DV · Sẹo lồi")], [])  # còn album, rỗng
        self.assertFalse([o for o in P.st["ops"] if o[0] == "xoa"])  # không xoá -> không hộp thoại
        self.chay(P, "--ghi")  # lần sau không đụng lại
        self.c.execute("UPDATE photos SET bo_qua=1 WHERE id IN ('a7','a8')")
        self.c.commit()
        self.chay(P, "--ghi", "--xoa-rong")
        self.assertIn(("xoa", "KH000888 · Khách Mới Bịa"), P.st["ops"])
        self.assertNotIn((M.TM_KHACH, "KH000888 · Khách Mới Bịa"), cay(P))

    def test_lo_lon_tach_dung_va_anh_mat_khoi_thu_vien(self):
        ids = [f"u{i:05d}" for i in range(4500)]
        P = photos_gia(ids[:4499] + [f"x{i}" for i in range(2500)])
        kit = M.AnhKit(P)
        them, go, khong = kit.ghi(M.TM_THANG, "2026-09", ids)
        self.assertEqual((them, go, khong), (4499, 0, 1))  # u04499 không có trong thư viện -> bỏ qua
        self.assertEqual([len(o[2]) for o in P.st["ops"] if o[0] == "them"], [2000, 2000, 499])
        a = cay(P)[(M.TM_THANG, "2026-09")]
        self.assertEqual(len(a), 4499)
        # Album giả có 2500 ảnh thừa -> gỡ theo lô 2000
        al = P.GOC[0].con[0].con[0]
        al.anh += [f"x{i}" for i in range(2500)]
        P.st["ops"].clear()
        them, go, khong = kit.ghi(M.TM_THANG, "2026-09", ids)
        self.assertEqual((them, go), (0, 2500))
        self.assertEqual([len(o[2]) for o in P.st["ops"] if o[0] == "go"], [2000, 500])
        self.assertEqual(sum(1 for o in P.st["ops"] if o[0] == "them"), 0)  # chỉ u04499 thiếu, không có -> không gọi

    def test_album_san_co_trung_ten_khong_tao_them(self):
        P = photos_gia(THU_VIEN)
        kit = M.AnhKit(P)
        kit.ghi(M.TM_DV, "DV · PRP", ["a2"])
        kit2 = M.AnhKit(P)  # lượt mới đọc lại từ thư viện
        kit2.ghi(M.TM_DV, "DV · PRP", ["a2", "a6"])
        self.assertEqual(sum(1 for o in P.st["ops"] if o[0] == "tao_al"), 1)
        self.assertEqual(sum(1 for o in P.st["ops"] if o[0] == "tao_tm"), 2)
        self.assertEqual(cay(P)[(M.TM_DV, "DV · PRP")], ["a2", "a6"])

    def test_loi_lien_thi_dung_va_lan_sau_lam_lai(self):
        P = photos_gia(THU_VIEN, hong=99)
        out = self.chay(P, "--ghi")
        self.assertEqual(P.st["goi"], M.LOI_LIEN)  # 3 album lỗi liền -> dừng, không gọi tiếp
        self.assertIn("PHPhotosErrorDomain", out)
        self.assertIn("dừng lượt", out)
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM da_album").fetchone()[0], 0)
        P.st["hong"] = 0
        self.chay(P, "--ghi")
        self.assertEqual(cay(P), M.tinh_album(self.c))

    def test_loi_trong_khoi_khong_bi_nuot(self):
        P = photos_gia(THU_VIEN, hong_trong_khoi=True)
        with self.assertRaises(RuntimeError) as e:
            M.AnhKit(P).ghi(M.TM_DV, "DV · PRP", ["a2"])
        self.assertIn("khối hỏng", str(e.exception))

    def test_chi_dv_toi_da_1(self):
        P = photos_gia(THU_VIEN)
        self.chay(P, "--ghi", "--chi", "dv", "--toi-da", "1")
        c = cay(P)
        self.assertEqual(len(c), 1)
        self.assertEqual({k[0] for k in c}, {M.TM_DV})

    def test_chay_khan_khong_dung_photos(self):
        def cam():
            raise AssertionError("chạy khan không được mở PhotoKit")
        with mock.patch.object(M, "_photos", cam), mock.patch.object(M, "_quyen", cam), \
                mock.patch.object(sys, "argv", ["x"]), redirect_stdout(io.StringIO()) as out:
            M.main()
        self.assertIn("CHẠY KHAN", out.getvalue())


if __name__ == "__main__":
    unittest.main()
