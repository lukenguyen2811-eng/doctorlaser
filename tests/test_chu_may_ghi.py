"""Quét không đọc lại chữ máy tự ghi lên app Ảnh (vòng tự xác nhận).  python3 -m unittest tests/test_chu_may_ghi.py"""
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["ANH_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
import anhkhach as A  # noqa: E402


class ChuMayGhi(unittest.TestCase):
    def test_bo_dong_chu_thich_may_ghi_giu_chu_nguoi(self):
        mo_ta = ("Giang-sẹo 9/10/26\n"
                 "KH000123 · Khách A · 0901234567 · 2026-10-09 · Laser Pico · (chưa duyệt)\n"
                 "CU-KH000777 · Khách B · 0912000111 · 2025-01-02 · PRP\n"
                 "khách hẹn tái khám")
        ra = A._bo_chu_may_ghi(mo_ta)
        self.assertIn("Giang-sẹo 9/10/26", ra)
        self.assertIn("khách hẹn tái khám", ra)
        self.assertNotIn("0901234567", ra)
        self.assertNotIn("KH000777", ra)

    def test_dong_sdt_nguoi_ghi_van_giu(self):  # âm: nhân viên tự ghi SĐT thì vẫn dùng được
        self.assertEqual(A._bo_chu_may_ghi("Lan 0901234567 pico"), "Lan 0901234567 pico")
        self.assertEqual(A._bo_chu_may_ghi(None), "")

    def test_album_may_tao(self):
        self.assertTrue(A._la_album_may("KH000123 · Khách A"))
        self.assertTrue(A._la_album_may("DV · Laser Pico"))
        self.assertFalse(A._la_album_may("CĂNG CHỈ BS LƯƠNG"))

    def test_doc_tu_khoa_may_ghi(self):
        c = sqlite3.connect(A.DB_FILE)
        c.execute("CREATE TABLE IF NOT EXISTS da_gan_chac (id TEXT PRIMARY KEY, hd TEXT, tu_khoa TEXT, chu_thich TEXT, luc TEXT)")
        c.execute("INSERT OR REPLACE INTO da_gan_chac VALUES ('U1','H1',?, '', '')",
                  (json.dumps(["KH000123", "0901234567", "chưa duyệt"], ensure_ascii=False),))
        c.commit()
        c.close()
        self.assertEqual(A._tu_khoa_may_ghi()["U1"], {"KH000123", "0901234567", "chưa duyệt"})

    def test_khong_co_bang_thi_rong(self):
        with mock.patch.object(A, "DB_FILE", os.path.join(tempfile.mkdtemp(), "trong.db")):
            self.assertEqual(A._tu_khoa_may_ghi(), {})


if __name__ == "__main__":
    unittest.main()
