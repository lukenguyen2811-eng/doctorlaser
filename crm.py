"""Đọc dữ liệu LEAD từ CRM chatbot (Google Sheet CRM_DoctorLaser_v3), tab LEADS.

Trong CRM: LEADS = khách ĐÃ cho SĐT. Module này thay cho sheet tay ở
báo cáo ngày (/baocaongay) và /stats — theo yêu cầu "đếm lead/SĐT theo CRM".
"""

import datetime as dt
import re
import time
from collections import Counter

import config
import sheets

# Vị trí cột trong tab LEADS (0-based).
_COL = {
    "ngay": 1,        # Ngày vào
    "nguon": 2,       # Nguồn
    "sdt": 3,         # SĐT
    "ho_ten": 4,      # Tên khách
    "dich_vu": 5,     # Dịch vụ quan tâm
    "phan_loai": 6,   # Phân loại (Nóng/Ấm/Lạnh)
    "nhan_vien": 8,   # Nhân viên
    "trang_thai": 9,  # Trạng thái (Mới/Chốt/Đặt lịch)
    "khach_cu": 13,   # Khách cũ
}

_cache: tuple[float, list[dict]] | None = None


def enabled() -> bool:
    return bool(config.CRM_SHEET_ID)


def _fetch() -> list[dict]:
    ss = sheets.open_spreadsheet(config.CRM_SHEET_ID)
    ws = ss.worksheet(config.CRM_LEADS_TAB)
    rows = ws.get_all_values()
    out: list[dict] = []
    for r in rows[1:]:  # bỏ tiêu đề
        c = [x.strip() for x in (r + [""] * 20)]
        rec = {k: c[i] for k, i in _COL.items()}
        # bỏ dòng rỗng thực sự
        if not (rec["ho_ten"] or rec["sdt"] or rec["trang_thai"]):
            continue
        out.append(rec)
    return out


def get_leads(force: bool = False) -> list[dict]:
    """Danh sách lead (tab LEADS), có cache theo SHEET_CACHE_TTL."""
    global _cache
    now = time.time()
    if not force and _cache and (now - _cache[0]) < config.SHEET_CACHE_TTL:
        return _cache[1]
    data = _fetch()
    _cache = (now, data)
    return data


def parse_date(s: str) -> dt.date | None:
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", (s or "").strip())
    if not m:
        return None
    try:
        return dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def has_phone(r: dict) -> bool:
    return len(re.sub(r"\D", "", r.get("sdt") or "")) >= 8


def leads_on(records: list[dict], day: dt.date) -> list[dict]:
    return [r for r in records if parse_date(r["ngay"]) == day]


def leads_in_month(records: list[dict], year: int, month: int) -> list[dict]:
    out = []
    for r in records:
        d = parse_date(r["ngay"])
        if d and d.year == year and d.month == month:
            out.append(r)
    return out


def _counter(leads: list[dict], field: str, empty: str = "(không rõ)") -> Counter:
    return Counter((r.get(field) or empty).strip() or empty for r in leads)


def lead_lines(leads: list[dict]) -> list[str]:
    """Các dòng thống kê lead từ CRM (dùng trong báo cáo ngày)."""
    n = len(leads)
    got = sum(1 for r in leads if has_phone(r))
    lines = [f"  - Số lead: {n}", f"  - Có SĐT: {got}/{n}" + (f" ({got / n * 100:.0f}%)" if n else "")]
    if not leads:
        return lines
    lines.append("  - Theo nguồn:")
    for name, c in _counter(leads, "nguon").most_common():
        lines.append(f"      • {name}: {c} ({c / n * 100:.0f}%)")
    pl = _counter(leads, "phan_loai", "(chưa)")
    lines.append("  - Phân loại: " + ", ".join(f"{k} {v}" for k, v in pl.most_common()))
    chot = sum(1 for r in leads if "chốt" in (r.get("trang_thai") or "").lower())
    dl = sum(1 for r in leads if "đặt lịch" in (r.get("trang_thai") or "").lower())
    lines.append(
        f"  - Kết quả: Chốt {chot} ({chot / n * 100:.0f}%), "
        f"Đặt lịch {dl} ({dl / n * 100:.0f}%)"
    )
    return lines


def build_summary(leads: list[dict]) -> str:
    """Tóm tắt lead tổng hợp cho /stats (thay analytics.build_summary)."""
    n = len(leads)
    got = sum(1 for r in leads if has_phone(r))

    def block(title: str, counter: Counter) -> list[str]:
        out = [title]
        for name, c in counter.most_common():
            out.append(f"  - {name}: {c} ({c / n * 100:.1f}%)" if n else f"  - {name}: {c}")
        return out

    parts = [
        f"TỔNG LEAD (CRM chatbot): {n}",
        f"Có SĐT: {got}/{n}" + (f" ({got / n * 100:.1f}%)" if n else ""),
        "",
    ]
    parts += block("Theo NGUỒN:", _counter(leads, "nguon"))
    parts.append("")
    parts += block("Theo PHÂN LOẠI:", _counter(leads, "phan_loai", "(chưa)"))
    parts.append("")
    parts += block("Theo TRẠNG THÁI:", _counter(leads, "trang_thai", "(chưa)"))
    parts.append("")
    parts += block("Theo DỊCH VỤ:", _counter(leads, "dich_vu", "(chưa rõ)"))
    parts.append("")
    parts += block("Theo NGÀY:", _counter(leads, "ngay", "(trống)"))
    return "\n".join(parts)
