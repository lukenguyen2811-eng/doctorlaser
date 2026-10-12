"""Tải bản gốc theo loạt: giả lập lệnh xuất của Photos (không đụng Photos thật).

Chạy:  python3 -m unittest tests/test_tai_theo_lo.py
"""
import os
import sys
import tempfile
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import anhkhach as A  # noqa: E402


def anh(uuid, ten, sua=False):
    return types.SimpleNamespace(uuid=uuid, original_filename=ten, hasadjustments=sua)


class TaiTheoLo(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.lenh = []

    def gia_photos(self, xuat):
        """xuat: tên file Photos 'xuất' ra cho mỗi lần gọi (hoặc Exception)."""
        lan = iter(xuat)

        def run(cmd, **kw):
            self.lenh.append(cmd)
            ra = next(lan)
            if isinstance(ra, Exception):
                raise ra
            for f in ra:
                open(os.path.join(cmd[3], f), "w").close()
        return mock.patch.object(A.subprocess, "run", side_effect=run)

    def test_ghep_file_ve_uuid_bo_mov_va_ten_trung(self):
        ds = [anh("U1", "IMG_1.HEIC"), anh("U2", "IMG_2.JPG"),
              anh("U3", "IMG_3.HEIC"), anh("U4", "IMG_3.HEIC"),  # trùng tên -> để tải lẻ
              anh("U5", "IMG_5.HEIC", sua=True)]                 # ảnh đã sửa -> tải lẻ
        with self.gia_photos([["IMG_1.HEIC", "IMG_1.MOV", "IMG_2.JPG", "IMG_3.HEIC", "IMG_3 (1).HEIC"]]):
            A._tai_theo_lo(ds, self.dir)
        self.assertEqual(sorted(os.listdir(self.dir)), ["U1.heic", "U2.jpg"])
        cmd = self.lenh[0]
        self.assertEqual(cmd[0:2], ["osascript", "-e"])
        self.assertEqual(cmd[5:], ["U1/L0/001", "U2/L0/001", "U3/L0/001", "U4/L0/001"])

    def test_chia_loat_va_loat_loi_khong_chan_loat_sau(self):
        ds = [anh(f"U{i}", f"IMG_{i}.HEIC") for i in range(5)]
        with mock.patch.object(A, "LO_TAI", 2), \
                self.gia_photos([A.subprocess.TimeoutExpired("osascript", 1), ["IMG_2.HEIC"], ["IMG_4.HEIC"]]):
            A._tai_theo_lo(ds, self.dir)
        self.assertEqual(len(self.lenh), 3)
        self.assertEqual(sorted(os.listdir(self.dir)), ["U2.heic", "U4.heic"])  # thư mục tạm đã dọn

    def test_bo_qua_anh_da_tai(self):
        open(os.path.join(self.dir, "U1.heic"), "w").close()
        with self.gia_photos([]):
            A._tai_theo_lo([anh("U1", "IMG_1.HEIC")], self.dir)
        self.assertEqual(self.lenh, [])


if __name__ == "__main__":
    unittest.main()
