"""Đánh dấu TRÙNG cho lead lặp SĐT trong tab LEADS của sheet CRM.

Cùng 1 SĐT xuất hiện nhiều dòng = 1 khách bị đếm nhiều lần. Luật xử lý
(kiểm chứng bằng data thật 07-09/2026, ví dụ khách "ĐÃ ĐẾN" + "Chốt" 2 dòng):

- GIỮ NGUYÊN dòng có trạng thái tốt nhất: Chốt > Đặt lịch > Đã đến > khác
  (bằng điểm thì giữ dòng vào sớm nhất — bản gốc).
- Các dòng còn lại ghi trạng thái = TRÙNG (cột J). KHÔNG xoá dòng nào,
  KHÔNG đụng dòng đã là TRÙNG/SPAM-RÁC sẵn.
- Dòng TRÙNG tự động bị loại khỏi tỉ lệ báo cáo (xem crm.tach_lead_trung).
"""

import datetime as dt
import re

import config
import sheets

_COL_SDT = 3        # cột D (0-based)
_COL_NGAY = 1       # cột B
_COL_TEN = 4        # cột E
_COL_TRANGTHAI = 9  # cột J

_DA_TRUNG = {"TRÙNG", "SPAM/RÁC", "RÁC"}


def _phone(s: str) -> str:
    d = re.sub(r"\D", "", s or "")
    if d.startswith("84") and len(d) >= 11:
        d = "0" + d[2:]
    return d


def _parse_ngay(s: str) -> dt.date:
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", (s or "").strip())
    if not m:
        return dt.date(2000, 1, 1)
    try:
        return dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return dt.date(2000, 1, 1)


def _diem(trang_thai: str) -> int:
    st = (trang_thai or "").strip().lower()
    if (trang_thai or "").strip().upper() in _DA_TRUNG:
        return -1  # đã xử lý sẵn — không giữ, không sửa
    if "chốt" in st:
        return 4
    if "đặt lịch" in st or "đặt hẹn" in st:
        return 3
    if "đã đến" in st:
        return 2
    return 1


def xu_ly(tu_ngay: dt.date | None = None) -> str:
    """Quét + đánh TRÙNG các dòng lead lặp SĐT (dòng lặp có Ngày >= tu_ngay).

    Trả tóm tắt tiếng Việt. Chỉ ghi cột Trạng thái, không đụng gì khác.
    """
    ss = sheets.open_spreadsheet_rw(config.CRM_SHEET_ID)
    ws = ss.worksheet(config.CRM_LEADS_TAB)
    rows = ws.get_all_values()

    nhom: dict = {}
    for idx, r in enumerate(rows[1:], start=2):
        if not any(x.strip() for x in r):
            continue
        p = _phone(r[_COL_SDT] if len(r) > _COL_SDT else "")
        if len(p) < 9:
            continue
        nhom.setdefault(p, []).append((idx, r))

    danh_dau: list = []   # (số dòng, tên, ngày) sẽ ghi TRÙNG
    for p, g in nhom.items():
        if len(g) < 2:
            continue
        if tu_ngay and not any(
            _parse_ngay(r[_COL_NGAY] if len(r) > _COL_NGAY else "") >= tu_ngay
            for _, r in g
        ):
            continue
        # Giữ dòng điểm cao nhất; điểm bằng nhau thì giữ dòng vào sớm nhất.
        ung_vien = [
            (idx, r) for idx, r in g
            if _diem(r[_COL_TRANGTHAI] if len(r) > _COL_TRANGTHAI else "") >= 0
        ]
        if len(ung_vien) < 2:
            continue  # tối đa 1 dòng chưa xử lý -> không có gì để đánh
        giu = max(
            ung_vien,
            key=lambda x: (
                _diem(x[1][_COL_TRANGTHAI] if len(x[1]) > _COL_TRANGTHAI else ""),
                -_parse_ngay(x[1][_COL_NGAY] if len(x[1]) > _COL_NGAY else "").toordinal(),
                -x[0],
            ),
        )
        for idx, r in ung_vien:
            if idx == giu[0]:
                continue
            danh_dau.append((
                idx,
                (r[_COL_TEN] if len(r) > _COL_TEN else "").strip() or "(chưa tên)",
                (r[_COL_NGAY] if len(r) > _COL_NGAY else "").strip(),
                p,
                giu[0],
            ))

    if not danh_dau:
        return "✅ Không còn lead trùng SĐT nào cần xử lý."

    import gspread

    ws.update_cells(
        [gspread.Cell(idx, _COL_TRANGTHAI + 1, "TRÙNG") for idx, *_ in danh_dau]
    )
    out = [f"🧹 Đã đánh TRÙNG {len(danh_dau)} dòng lead lặp SĐT (giữ dòng trạng thái tốt nhất):"]
    for idx, ten, ngay, p, giu_idx in danh_dau:
        p_an = p[:3] + "***" + p[-3:]
        out.append(f"  • dòng {idx}: {ngay} · {ten} · {p_an} (giữ dòng {giu_idx})")
    out.append("Dòng TRÙNG không bị xoá — chỉ bị loại khỏi tỉ lệ trong báo cáo.")
    return "\n".join(out)
