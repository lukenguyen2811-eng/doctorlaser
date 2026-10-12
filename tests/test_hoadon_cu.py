"""Nạp hóa đơn cũ từ Excel KiotViet cũ (dữ liệu bịa).  python3 -m unittest tests/test_hoadon_cu.py"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["ANH_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
import anhkhach as A  # noqa: E402
import hoadon_cu as H  # noqa: E402

TIEU_DE = ["Chi nhánh", "Mã hóa đơn", "Thời gian", "Mã khách hàng", "Tên khách hàng", "Điện thoại",
           "Trạng thái", "Tên hàng", "Số lượng"]


def tao_xlsx(dong):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["DanhSachChiTietHoaDon_KV"])  # dòng tiêu đề phụ trước dòng cột
    ws.append(TIEU_DE)
    for d in dong:
        ws.append(d)
    f = os.path.join(tempfile.mkdtemp(), "HD.xlsx")
    wb.save(f)
    return f


class NapHoaDonCu(unittest.TestCase):
    def setUp(self):
        self.f = tao_xlsx([
            ["CN1", "HD049977", "31/03/2026 20:13:01", "KH008001", "Khách A", "0901 234 567", "Hoàn thành", "Laser Pico", 1],
            ["CN1", "HD049977", "31/03/2026 20:13:01", "KH008001", "Khách A", "0901 234 567", "Hoàn thành", "Kem Revitalux", 1],
            ["CN1", "HD049977", "31/03/2026 20:13:01", "KH008001", "Khách A", "0901 234 567", "Hoàn thành", "Laser Pico", 1],
            ["CN1", "HD049978", "01/03/2026 09:05:00", "KH000902", "Khách B", "0912000111", "Hoàn thành", "Tiêm PRP", 1],
            ["CN1", "HD049979", "02/03/2026 10:00:00", "KH000903", "Khách C", "", "Đã hủy", "Botox", 1],
        ])
        c = A.ket_noi()
        c.execute("DELETE FROM visits")
        # KiotViet mới: Khách A cùng SĐT, mã mới khác; KH000902 bên mới là NGƯỜI KHÁC (SĐT khác)
        c.execute("INSERT INTO visits VALUES ('HD003001','2026-04-02','10:00','KH009111','Khách A','0901234567','CSD','')")
        c.execute("INSERT INTO visits VALUES ('HD049978','2026-04-03','10:00','KH000902','Người khác','0988777666','CSD','')")
        c.commit()
        c.close()

    def test_gop_dong_thanh_hoa_don_bo_huy(self):
        hd = H.doc_file(self.f)
        self.assertEqual(sorted(hd), ["HD049977", "HD049978"])
        self.assertEqual(hd["HD049977"]["dv"], ["Laser Pico", "Kem Revitalux"])
        self.assertEqual((hd["HD049977"]["ngay"], hd["HD049977"]["gio"]), ("2026-03-31", "20:13"))

    def test_chay_khan_khong_ghi(self):
        with mock.patch.object(sys, "argv", ["x", self.f]):
            H.main()
        c = A.ket_noi()
        self.assertEqual(c.execute("SELECT count(*) FROM visits WHERE code LIKE 'CU-%'").fetchone()[0], 0)
        c.close()

    def test_ghi_khop_sdt_va_khong_gop_nham_ma(self):
        with mock.patch.object(sys, "argv", ["x", self.f, "--ghi"]):
            H.main()
        c = A.ket_noi()
        r = {x[0]: x[1:] for x in c.execute("SELECT code, ma_kh, ngay FROM visits")}
        self.assertEqual(r["CU-HD049977"], ("KH009111", "2026-03-31"))  # nối qua SĐT
        self.assertEqual(r["CU-HD049978"][0], "CU-KH000902")           # mã trùng người khác -> tách
        self.assertEqual(r["HD049978"][0], "KH000902")                  # HĐ mới cùng số không bị đè
        c.close()


if __name__ == "__main__":
    unittest.main()
