"""xuat --album: album Photos theo khách + theo dịch vụ, photoscript GIẢ (không chạm Photos thật).

Chạy:  python3 -m unittest tests/test_album_anh.py
"""
import os
import sys
import tempfile
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ANH_DB", os.path.join(tempfile.mkdtemp(), "t.db"))
import anhkhach as A  # noqa: E402


def photoscript_gia(co_san=None, thu_muc_co=True):
    """Photos giả: thư mục 'Doctor Laser' + album {tên: [uuid]}; ghi lại mọi lần tạo/thêm/gỡ."""
    nhat_ky = {"tao_album": [], "tao_thu_muc": [], "them": [], "go": []}

    class Photo:
        def __init__(self, uuid):
            self.id, self.uuid = f"{uuid}/L0/001", uuid

    class Album:
        def __init__(self, name, ids=()):
            self.name, self.ids = name, list(ids)

        def photos(self):
            return [Photo(i) for i in self.ids]

        def add(self, photos):
            nhat_ky["them"].append((self.name, [p.uuid for p in photos]))
            self.ids += [p.uuid for p in photos]

        def remove(self, photos):
            nhat_ky["go"].append(self.name)

    class Folder:
        def __init__(self):
            self.ds = [Album(k, v) for k, v in (co_san or {}).items()]

        @property
        def albums(self):
            return list(self.ds)

        def create_album(self, name):
            nhat_ky["tao_album"].append(name)
            al = Album(name)
            self.ds.append(al)
            return al

    tm = Folder()

    class PhotosLibrary:
        def folder(self, name=None, top_level=True):
            return tm if (thu_muc_co and name == A.THU_MUC_ALBUM) else None

        def create_folder(self, name, folder=None):
            nhat_ky["tao_thu_muc"].append(name)
            return tm

    m = types.ModuleType("photoscript")
    m.Photo, m.PhotosLibrary = Photo, PhotosLibrary
    return m, nhat_ky, tm


def dong(ma="KH000123", ten="Khach  Bia\tMot", dv="Laser Pico toàn mặt | Kem dưỡng"):
    return {"ma_kh": ma, "ten_kh": ten, "dich_vu": dv}


class TenAlbum(unittest.TestCase):
    def test_ten(self):
        self.assertEqual(A._ten_album(dong()), ["KH000123 · Khach Bia Mot", "DV · Laser Pico toàn mặt"])

    def test_khach_le_chi_album_dich_vu(self):  # âm: không tạo album khách rỗng mã
        self.assertEqual(A._ten_album(dong(ma="", ten="Khách lẻ")), ["DV · Laser Pico toàn mặt"])
        self.assertEqual(A._ten_album(dong(ma="KH1", dv="")), ["KH1 · Khach Bia Mot"])

    def test_ma_cu_giu_tien_to(self):  # âm: CU-KH… là khách khác KH…
        self.assertEqual(A._ten_album(dong(ma="CU-KH000123"))[0], "CU-KH000123 · Khach Bia Mot")


class XepAlbum(unittest.TestCase):
    def chay(self, theo_album, **kw):
        m, nk, tm = photoscript_gia(**kw)
        with mock.patch.dict(sys.modules, {"photoscript": m}):
            A._xep_album(theo_album)
        return nk, tm

    def test_album_co_san_khong_tao_lai_khong_them_trung(self):
        nk, tm = self.chay({"KH1 · A": ["u1", "u2", "u2"], "DV · Pico": ["u1"]},
                           co_san={"KH1 · A": ["u1"]})
        self.assertEqual(nk["tao_album"], ["DV · Pico"])  # chỉ tạo album chưa có, 1 lần
        self.assertEqual(nk["them"], [("KH1 · A", ["u2"]), ("DV · Pico", ["u1"])])
        self.assertEqual(nk["go"], [])
        self.assertEqual(nk["tao_thu_muc"], [])

    def test_chay_lai_khong_lam_gi(self):  # âm: xuất lại lần 2 không tạo/thêm gì
        nk, _ = self.chay({"KH1 · A": ["u1"]}, co_san={"KH1 · A": ["u1"], "Album khác": ["u9"]})
        self.assertEqual((nk["tao_album"], nk["them"], nk["go"]), ([], [], []))

    def test_chua_co_thu_muc_thi_tao(self):
        nk, _ = self.chay({"KH1 · A": ["u1"]}, thu_muc_co=False)
        self.assertEqual(nk["tao_thu_muc"], [A.THU_MUC_ALBUM])
        self.assertEqual(nk["tao_album"], ["KH1 · A"])


class XuatAlbum(unittest.TestCase):
    """cmd_xuat --album: chỉ ảnh ĐÃ DUYỆT (xn_hd, bo_qua=0) vào album."""

    def setUp(self):
        self.tam = tempfile.mkdtemp()
        self.p = mock.patch.object(A, "DB_FILE", os.path.join(self.tam, "x.db"))
        self.p.start()
        c = A.ket_noi()
        c.execute("INSERT INTO visits VALUES ('HD1','2026-10-05','10:00','KH000123','Khach Bia','0901112233',"
                  "'Trị sẹo rỗ | Kem','')")
        f = os.path.join(self.tam, "a.jpg")
        open(f, "wb").close()
        for pid, xn, gy, bq in [("u1", "HD1", None, 0), ("u2", None, "HD1", 0), ("u3", "HD1", None, 1)]:
            c.execute("INSERT INTO photos (id,nguon,ngay,thoi_gian,ten_file,duong_dan,anh_xem,chu_thich,ocr,"
                      "xn_hd,goi_y_hd,do_tin,bo_qua) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (pid, "photos", "2026-10-05", f"2026-10-05T10:0{pid[1]}:00", f"IMG_{pid}.jpg", f, f,
                       "", "", xn, gy, "chac", bq))
        c.commit()
        c.close()

    def tearDown(self):
        self.p.stop()

    def test_chi_anh_da_duyet(self):
        m, nk, tm = photoscript_gia()
        osx = types.ModuleType("osxphotos")
        osx.PhotosDB = lambda: None
        a = types.SimpleNamespace(thang="2026-10", dich=os.path.join(self.tam, "out"), gan_tu_khoa=False,
                                  kiot=False, album=True)
        with mock.patch.dict(sys.modules, {"photoscript": m, "osxphotos": osx}), \
                mock.patch.object(A.shutil, "which", return_value=None):
            A.cmd_xuat(a)
        self.assertEqual(sorted(nk["tao_album"]), ["DV · Trị sẹo rỗ", "KH000123 · Khach Bia"])
        self.assertEqual(sorted(x for _, ids in nk["them"] for x in ids), ["u1", "u1"])  # u2 chưa duyệt, u3 bỏ qua

    def test_khong_co_co_album_khong_dung_photos(self):  # âm
        m, nk, _ = photoscript_gia()
        osx = types.ModuleType("osxphotos")
        osx.PhotosDB = lambda: None
        a = types.SimpleNamespace(thang="2026-10", dich=os.path.join(self.tam, "out"), gan_tu_khoa=False,
                                  kiot=False, album=False)
        with mock.patch.dict(sys.modules, {"photoscript": m, "osxphotos": osx}), \
                mock.patch.object(A.shutil, "which", return_value=None):
            A.cmd_xuat(a)
        self.assertEqual((nk["tao_album"], nk["them"]), ([], []))


if __name__ == "__main__":
    unittest.main()
