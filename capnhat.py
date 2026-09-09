"""Cập nhật tab LEADS tự động: (1) đánh dấu đợt import DATA CŨ 30/08,
(2) ghi trạng thái "Chốt" cho lead đã phát sinh doanh thu KiotViet.

(1) DATA CŨ: ngày 30/08/2026 có 1.047 dòng import data cũ (911 TIKTOK) vào
    thẳng LEADS làm phồng lũy kế tháng 8. Nhận diện: ngày vào 30/08/2026 và
    KHÔNG có Mã hội thoại + KHÔNG có giờ vào (7 dòng chatbot thật có đủ cả 2).
    Xử lý: ghi Nguồn = "DATA CŨ - <nguồn gốc>"; crm.py tự loại các dòng này
    khỏi mọi báo cáo.

(2) CHỐT THEO HÓA ĐƠN: sale bỏ trống trạng thái Chốt (0 lead Chốt từ 10/08 dù
    246 hóa đơn/15 ngày) nên tỉ lệ chốt không đo được. Bot đối chiếu SĐT lead
    với tab KHACH_HANG (đồng bộ KiotViet): khách có Tổng đã thanh toán > 0 và
    Ngày tới gần nhất >= ngày lead vào -> ghi trạng thái "Chốt".
    Không đụng dòng TRÙNG/rác hoặc đã Chốt; sale sửa lại được bất kỳ lúc nào.
"""

import datetime as dt
import re

import config
import sheets

_COL_NGAY = 1
_COL_NGUON = 2
_COL_SDT = 3
_COL_TEN = 4
_COL_TRANGTHAI = 9
_COL_MA = 17
_COL_TG = 19

_NGAY_IMPORT = {"30/08/2026", "30/8/2026"}
_BO_QUA = {"TRÙNG", "SPAM/RÁC", "RÁC"}


def _c(r: list, i: int) -> str:
    return r[i].strip() if len(r) > i else ""


def _phone(s: str) -> str:
    d = re.sub(r"\D", "", s or "")
    if d.startswith("84") and len(d) >= 11:
        d = "0" + d[2:]
    return d


def _parse_ngay(s: str) -> dt.date | None:
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", (s or "").strip())
    if not m:
        return None
    try:
        return dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def _tien(s: str) -> float:
    d = re.sub(r"[^\d]", "", s or "")
    return float(d) if d else 0.0


def danh_dau_data_cu() -> str:
    """Ghi Nguồn = 'DATA CŨ - <gốc>' cho các dòng import 30/08 (chạy 1 lần)."""
    import gspread

    ss = sheets.open_spreadsheet_rw(config.CRM_SHEET_ID)
    ws = ss.worksheet(config.CRM_LEADS_TAB)
    rows = ws.get_all_values()
    cells = []
    for idx, r in enumerate(rows[1:], start=2):
        if _c(r, _COL_NGAY) not in _NGAY_IMPORT:
            continue
        if _c(r, _COL_MA) or _c(r, _COL_TG):
            continue  # lead chatbot thật của ngày 30/08
        goc = _c(r, _COL_NGUON)
        if goc.upper().startswith("DATA CŨ"):
            continue  # đã đánh dấu rồi
        moi = f"DATA CŨ - {goc}" if goc else "DATA CŨ"
        cells.append(gspread.Cell(idx, _COL_NGUON + 1, moi))
    if not cells:
        return "✅ Không còn dòng import 30/08 nào cần đánh dấu DATA CŨ."
    ws.update_cells(cells)
    return (
        f"🏷 Đã ghi Nguồn = \"DATA CŨ - <gốc>\" cho {len(cells)} dòng import 30/08.\n"
        "Báo cáo từ giờ tự loại các dòng này — lũy kế tháng 8 sẽ về đúng số lead thật."
    )


def _kh_da_thanh_toan(so_ngay: int) -> dict:
    """SĐT -> (ngày hóa đơn gần nhất, tổng tiền) từ HÓA ĐƠN KiotViet.

    Đối chiếu thẳng API (hóa đơn `so_ngay`+15 ngày + danh bạ khách) thay vì
    tab KHACH_HANG của sheet — tab đó phụ thuộc Apps Script đồng bộ và từng
    đứng im từ 06/08 khiến lead tháng 8-9 không khớp được.
    """
    import kiotviet

    by_cust: dict = {}  # customerId -> [ngày hóa đơn mới nhất, tổng tiền]
    for i in kiotviet.get_invoices(days=so_ngay + 15):
        cid = i.get("customerId")
        if not cid:
            continue
        try:
            d = dt.date.fromisoformat((i.get("purchaseDate") or "")[:10])
        except ValueError:
            continue
        tien = kiotviet.invoice_revenue(i)
        if cid in by_cust:
            by_cust[cid][0] = max(by_cust[cid][0], d)
            by_cust[cid][1] += tien
        else:
            by_cust[cid] = [d, tien]

    out: dict = {}
    for c in kiotviet.get_customers():
        cid = c.get("id")
        if cid not in by_cust:
            continue
        p = _phone(c.get("contactNumber") or "")
        if len(p) < 9:
            continue
        d, tong = by_cust[cid]
        if tong > 0:
            out[p] = (d, tong)
    return out


def cap_nhat_chot(so_ngay: int = 60) -> str:
    """Ghi trạng thái 'Chốt' cho lead (trong `so_ngay` gần nhất) đã ra doanh thu.

    Điều kiện: SĐT có hóa đơn KiotViet ngày >= ngày lead vào (tổng > 0đ).
    Bỏ qua dòng TRÙNG/rác, DATA CŨ, đã Chốt.
    """
    import gspread

    paid = _kh_da_thanh_toan(so_ngay)
    ss = sheets.open_spreadsheet_rw(config.CRM_SHEET_ID)
    ws = ss.worksheet(config.CRM_LEADS_TAB)
    rows = ws.get_all_values()
    cutoff = dt.date.today() - dt.timedelta(days=so_ngay)

    cells, chi_tiet = [], []
    for idx, r in enumerate(rows[1:], start=2):
        d = _parse_ngay(_c(r, _COL_NGAY))
        if not d or d < cutoff:
            continue
        st = _c(r, _COL_TRANGTHAI)
        if st.upper() in _BO_QUA or "chốt" in st.lower():
            continue
        if _c(r, _COL_NGUON).upper().startswith("DATA CŨ"):
            continue
        p = _phone(_c(r, _COL_SDT))
        if p not in paid:
            continue
        lan_toi, tong = paid[p]
        if lan_toi is None or lan_toi < d:
            continue  # thanh toán là của lần ghé TRƯỚC khi thành lead -> khách cũ
        cells.append(gspread.Cell(idx, _COL_TRANGTHAI + 1, "Chốt"))
        ten = _c(r, _COL_TEN) or "(chưa tên)"
        chi_tiet.append(
            f"  • dòng {idx}: {_c(r, _COL_NGAY)} · {ten} · {p[:3]}***{p[-3:]}"
            f" ({st or 'chưa có trạng thái'} → Chốt, đã chi {tong:,.0f}đ)".replace(",", ".")
        )
    if not cells:
        return "✅ Không có lead mới nào cần cập nhật Chốt."
    ws.update_cells(cells)
    return (
        f"💰 Đã ghi 'Chốt' cho {len(cells)} lead phát sinh doanh thu KiotViet:\n"
        + "\n".join(chi_tiet[:20])
        + (f"\n  • … và {len(chi_tiet) - 20} lead nữa" if len(chi_tiet) > 20 else "")
    )
