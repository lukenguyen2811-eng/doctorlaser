"""HỒI QUY chọn HĐ trong cùng khách (CEO 16/10 lần 8) — gom MỌI ca C 'tệ' của các file soát (soat_moi … soat_moi7),
dữ liệu bịa (chỉ tên dịch vụ + giờ, không tên khách).

BÀI HỌC (đã sai lặp 3 lần — vòng 5, 6, 7):
  (c) chọn HĐ LUÔN theo dịch vụ ghi trên nhãn trước giờ: mã nhãn khớp ĐÚNG CHỮ (chính mã / chữ nhân viên viết / chữ cũng
      là 1 mã trong bảng) xếp trên đồng nghĩa phụ ('csd' -> 'CSD MỤN' hơn 'ĐIỆN DI C', 'PEEL'); giờ chỉ phân định khi dịch
      vụ ngang; không nhãn dịch vụ thì loại HĐ chỉ sản phẩm/thu tiền rồi theo giờ.
  (a) luật 'nhãn ghi tên khác trong bộ' chỉ được xét ảnh CÙNG MÃ MẶT với ảnh nhãn, và so tên mờ (OCR lệch, biệt danh) —
      vòng 7 xét cả bộ, hạ oan 16/20.
Ca mâu thuẫn giữa các vòng soát (không đưa vào): 79054138 (vòng 7 chấm 'điện di sát giờ' đúng) ngược 10 ca vòng 8 ('csd'
-> HĐ CSD dù xa giờ); F7FE5B87 cùng kiểu với 79054138.

Chạy:  python3 -m unittest tests/test_hoi_quy_chon_hd.py
"""
import datetime as dt
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_ten_cuoi_mat_anh import A, D  # noqa: E402

# (uuid ca thật, giờ chụp, [(mã HĐ, giờ HĐ, dịch vụ)], mã nhãn chính ảnh, mã nhãn cùng bộ/đợt, chữ nhãn, HĐ đúng)
CA = [
    # soat_moi (vòng 2)
    ("D14C5AD7", "11:58", [("a", "11:51", "LASER FRACTIONAL | CSD MỤN"), ("b", "11:53", "LASER MỤN THỊT VÙNG BỤNG")],
     [], ["co2"], "", "a"),
    ("EB9573DF", "17:11", [("a", "17:22", "TIÊM MESOTHERAPY | XÓA VEIN MŨI"), ("b", "19:21", "PEEL DA MỤN (LẦN LẺ)")],
     ["xvm"], ["csd"], "", "a"),
    ("C27CEF61", "17:58", [("a", "08:21", "Laser Picolight toàn mặt trị nám"),
                           ("b", "18:29", "MELASMA-REVSKIN | TIÊM MESO SKIN BOOSTER (căng bóng, giảm nám)")],
     [], ["pico"], "", "a"),
    ("28355FAE", "13:26", [("a", "11:52", "TIÊM FILLER LÀM ĐẦY HÀN ( 1CC )"), ("b", "13:29", "TIÊM TAN FILLER LÀM ĐẦY")],
     [], ["filler"], "sau filler", "a"),
    ("4ACBA65E", "09:36", [("a", "09:25", "TIÊM MESOTHERAPY | XÓA VEIN MẶT"), ("b", "09:28", "THUỐC TRỊ THÂM MEDICOS ARBUTIN")],
     [], [], "", "a"),
    # soat_moi3 (vòng 4)
    ("E514D8DB", "10:51", [("a", "10:40", "LASER NỐT RUỒI | LASER FRACTIONAL | TIÊM PRP PREM"),
                           ("b", "14:01", "LASER CO2 MÀI VIỀN SẸO | LASER ĐỐT MỤN THỊT MẶT")], [], ["co2"], "", "a"),
    ("F4BC5627", "09:07", [("a", "16:06", "TRẺ HOÁ DA PICOLIGHT | TIÊM PRP PREMIUM ( LẦN LẺ )"),
                           ("b", "16:44", "GÓI TRẺ HOÁ DA PICOLIGHT | TIÊM FILLER THẨM MỸ")], ["prp"], [], "prp mặt", "a"),
    ("7CA6F7F8", "10:12", [("a", "10:22", "CSD MỤN"), ("b", "10:48", "BÙ KIM RF ( HỖ TRỢ KHI LÀM VỚI PRP )")],
     [], [], "", "a"),
    # soat_moi4 (vòng 5)
    ("B76B82C7", "15:58", [("a", "15:54", "CSD MỤN ( LẦN LẺ ) | TRIỆT LÔNG MẶT / MÉP ( 1 LẦN )"),
                           ("b", "15:56", "ĐẶT CỌC CSD | COMBO CSD ( 10 LẦN )")], ["csd"], [], "", "a"),
    ("A1519E26", "11:34", [("a", "11:16", "CSD MỤN ( LẦN LẺ )"), ("b", "14:14", "TRIỆT LÔNG MÉP/MẶT | PEEL DA MỤN (LẦN LẺ)")],
     [], ["peel"], "", "b"),
    # soat_moi5 (vòng 6)
    ("374C2565", "16:28", [("a", "17:03", "TIÊM SẸO LỒI"), ("b", "16:43", "ĐẶT CỌC | TIÊM TAN FILLER LÀM ĐẦY")],
     ["tiem giai"], [], "tiem giai mat", "b"),
    ("7A6D7343", "14:47", [("a", "17:14", "TIÊM XÓA NHĂN"), ("b", "14:52", "THANH TOÁN CÔNG NỢ VEIN | LASER NỘI BÌ (2 VÙNG)")],
     [], [], "", "b"),
    ("3DE67A93", "09:03", [("a", "08:55", "ĐIỀU TRỊ SẸO RỖ ĐA PHƯƠNG THỨC"), ("b", "10:50", "LASER NỐT RUỒI LẦN LẺ")],
     [], ["seo"], "", "a"),
    ("59BE90A2", "13:31", [("a", "13:17", "KEM REVITALUX | ĐIỀU TRỊ SẸO RỖ"), ("b", "14:47", "LASER ĐỐT MỤN THỊT MẶT")],
     [], [], "", "a"),
    # soat_moi6 (vòng 7)
    ("C86699A4", "17:37", [("a", "18:28", "COMBO PICOLIGHT 5 LẦN"), ("b", "18:30", "TẾ BÀO GỐC NHỎ ĐIỆN DI")],
     [], ["csd"], "cham soc da dien di c tbg", "b"),
    # soat_moi7 (vòng 8): nhãn 'csd' -> HĐ có chữ CSD, không phải điện di / peel / IPL gần giờ hơn
    ("3333FEAF", "10:00", [("a", "11:30", "CSD MỤN ( LẦN LẺ )"), ("b", "10:05", "ĐIỆN DI C | MẶT NẠ")], ["csd"], [], "", "a"),
    ("86332E60", "10:00", [("a", "11:00", "CSD MỤN"), ("b", "10:04", "PEEL DA MỤN (LẦN LẺ)")], [], ["csd"], "", "a"),
    ("BF1FC7E4", "10:00", [("a", "10:50", "CSD MỤN"), ("b", "10:03", "PEEL THÂM")], [], ["csd"], "", "a"),
    ("B74C17EC", "10:00", [("a", "11:10", "CSD MỤN"), ("b", "10:02", "ĐIỆN DI C SAU SẸO")], [], ["csd"], "", "a"),
    ("36B3B330", "10:00", [("a", "11:20", "COMBO CSD ( 10 LẦN )"), ("b", "10:06", "ĐIỆN DI C SAU SẸO")], [], ["csd"], "", "a"),
    ("1F338143", "10:00", [("a", "10:40", "CSD MỤN"), ("b", "10:01", "PEEL DA MỤN")], [], ["csd"], "", "a"),
    ("54B2A28B", "10:00", [("a", "11:00", "CSD MỤN"), ("b", "10:05", "ĐIỆN DI C SAU SẸO")], [], ["csd"], "", "a"),
    ("290D2AA1", "10:00", [("a", "11:00", "COMBO CSD MỤN & IPL"), ("b", "10:05", "CHĂM SÓC DA VỚI IPL ÁNH SÁNG")],
     [], ["csd"], "csd mun", "a"),
    ("B01A93ED", "10:00", [("a", "10:45", "CSD MỤN"), ("b", "10:02", "ĐIỆN DI C")], ["csd"], [], "", "a"),
    ("2BA84ADB", "10:00", [("a", "11:00", "COMBO CSD ( 10 LẦN )"), ("b", "10:05", "ĐIỆN DI C SAU SẸO")], [], ["csd"], "", "a"),
]


class HoiQuyChonHd(unittest.TestCase):
    def test_moi_ca_c_te(self):
        sai = []
        for u, gio, hds, ma, quanh, chu, dung in CA:
            vs = [{"code": c, "ngay": D, "gio": g, "dich_vu": dv} for c, g, dv in hds]
            r = {"hd": None, "gio": dt.datetime.fromisoformat(f"{D}T{gio}:00"), "goc": 1}
            got = A._chon_hd_mat(vs, [D], r, list(ma), list(quanh), chu)["code"]
            if got != dung:
                sai.append(f"{u}: ra {got}, đúng {dung}")
        self.assertEqual(sai, [], "\n".join(sai))


if __name__ == "__main__":
    unittest.main()
