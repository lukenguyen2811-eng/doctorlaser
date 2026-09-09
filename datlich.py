"""Dọn lịch hẹn TRÙNG trong tab 'ĐẶT LỊCH Txx' của sheet CRM.

Tab đặt lịch do hệ thống ghi, nhân viên không được thao tác nên dòng trùng
(cùng NGÀY + SĐT) tồn đọng — ví dụ khách dời giờ tạo dòng mới mà dòng cũ
vẫn còn (kiểm chứng 09/2026: T08 2 dòng, T09 1 dòng).

Luật dọn (an toàn, không mất dữ liệu):
- Trùng = cùng ngày (cột A) + cùng SĐT (cột D, chuẩn hoá 84xx -> 0xx).
- GIỮ dòng DƯỚI CÙNG của nhóm (bản ghi mới nhất — thường là giờ hẹn đã dời).
- Dòng bị loại KHÔNG xoá mất: chép sang tab lưu trữ DAT_LICH_TRUNG_XOA
  (kèm tab gốc + số dòng + thời điểm dọn) rồi mới xoá khỏi tab chính.
"""

import datetime as dt
import re

import config
import sheets

_ARCHIVE_TAB = "DAT_LICH_TRUNG_XOA"
_KEEP_COLS = 10  # cột A..J của tab đặt lịch (ngày -> nguồn)


def _phone(s: str) -> str:
    d = re.sub(r"\D", "", s or "")
    if d.startswith("84") and len(d) >= 11:
        d = "0" + d[2:]
    return d


def tab_thang(day: dt.date) -> str:
    return f"ĐẶT LỊCH T{day.month:02d}"


def _parse_ngay(s: str) -> dt.date | None:
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", (s or "").strip())
    if not m:
        return None
    try:
        return dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def _parse_gio(s: str) -> int:
    """'10h30' -> phút trong ngày để sắp xếp; không đọc được thì đẩy xuống cuối."""
    m = re.match(r"(\d{1,2})\s*[hg:]\s*(\d{0,2})", (s or "").strip().lower())
    if not m:
        return 24 * 60
    return int(m.group(1)) * 60 + int(m.group(2) or 0)


def lich_hen_lines(day: dt.date, tieu_de: str) -> list[str]:
    """Danh sách lịch hẹn của đúng 1 ngày, đọc thẳng tab ĐẶT LỊCH tháng đó.

    Hiển thị đã khử trùng SĐT trong ngày (giữ dòng dưới cùng — bản mới nhất),
    sắp theo giờ hẹn. Trả [] nếu không mở được tab (không làm hỏng báo cáo).
    """
    ss = sheets.open_spreadsheet(config.CRM_SHEET_ID)
    try:
        ws = ss.worksheet(tab_thang(day))
    except Exception:  # noqa: BLE001
        return []
    rows = ws.get_all_values()[1:]
    chon: dict = {}  # khoá SĐT (hoặc tên) -> dòng cuối cùng của ngày
    for r in rows:
        if _parse_ngay(r[0] if len(r) > 0 else "") != day:
            continue
        p = _phone(r[3] if len(r) > 3 else "")
        ten = (r[2] if len(r) > 2 else "").strip()
        if not p and not ten:
            continue
        chon[p or ten.lower()] = r
    lines = [f"{tieu_de} ({day:%d/%m}): {len(chon)} khách"]
    if not chon:
        lines.append("  - (chưa có lịch hẹn)")
        return lines
    for r in sorted(chon.values(), key=lambda x: _parse_gio(x[4] if len(x) > 4 else "")):
        gio = (r[4] if len(r) > 4 else "").strip() or "?"
        ten = (r[2] if len(r) > 2 else "").strip() or "(chưa tên)"
        noidung = (r[5] if len(r) > 5 else "").strip()
        tvtt = (r[7] if len(r) > 7 else "").strip()
        line = f"  • {gio:<6} {ten}"
        if noidung:
            line += f" — {noidung}"
        if tvtt:
            line += f" (TVTT: {tvtt})"
        lines.append(line)
    return lines


def don_trung(day: dt.date | None = None) -> str:
    """Dọn lịch trùng trong tab tháng của `day` (mặc định: hôm nay).

    Trả chuỗi tóm tắt tiếng Việt để bot gửi vào nhóm/ trả lời lệnh.
    """
    day = day or dt.date.today()
    tab = tab_thang(day)
    ss = sheets.open_spreadsheet_rw(config.CRM_SHEET_ID)
    try:
        ws = ss.worksheet(tab)
    except Exception:  # noqa: BLE001
        return f"(không thấy tab {tab} — bỏ qua)"

    rows = ws.get_all_values()
    groups: dict = {}
    for idx, r in enumerate(rows[1:], start=2):  # idx = số dòng thật trên sheet
        if not any(x.strip() for x in r):
            continue
        ngay = (r[0] if len(r) > 0 else "").strip()
        p = _phone(r[3] if len(r) > 3 else "")
        if not ngay or not p:
            continue
        groups.setdefault((ngay, p), []).append(idx)

    remove: list = []
    for idxs in groups.values():
        if len(idxs) > 1:
            remove += idxs[:-1]  # giữ dòng dưới cùng (mới nhất)
    if not remove:
        return f"{tab}: không có lịch trùng."

    # 1) Lưu bản sao sang tab lưu trữ TRƯỚC khi xoá.
    try:
        arch = ss.worksheet(_ARCHIVE_TAB)
    except Exception:  # noqa: BLE001
        arch = ss.add_worksheet(_ARCHIVE_TAB, rows=1000, cols=_KEEP_COLS + 3)
        header = ["Tab gốc", "Dòng", "Lúc dọn"]
        if rows:
            header += rows[0][:_KEEP_COLS]
        arch.append_row(header)
    now = dt.datetime.now().strftime("%d/%m/%Y %H:%M")
    arch.append_rows(
        [[tab, str(i), now] + rows[i - 1][:_KEEP_COLS] for i in sorted(remove)]
    )

    # 2) Xoá từ DƯỚI LÊN để số dòng không bị lệch khi xoá dần.
    for i in sorted(remove, reverse=True):
        ws.delete_rows(i)

    chi_tiet = []
    for i in sorted(remove):
        r = rows[i - 1]
        ten = (r[2] if len(r) > 2 else "").strip() or "(chưa tên)"
        chi_tiet.append(f"  • dòng {i}: {r[0].strip()} · {ten} · {_phone(r[3] if len(r) > 3 else '')}")
    return (
        f"🧹 {tab}: đã dọn {len(remove)} lịch trùng (giữ bản mới nhất, "
        f"bản cũ lưu ở tab {_ARCHIVE_TAB}):\n" + "\n".join(chi_tiet)
    )
