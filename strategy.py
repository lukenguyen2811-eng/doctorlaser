"""Phân tích chiến lược: doanh thu & ROAS theo dịch vụ / kênh / nhân viên sale.

Đọc sheet "doanh thu theo dịch vụ" gồm:
- Bảng GIAO DỊCH (mỗi dòng 1 đơn): Tháng, Ngày, Tên KH, SĐT, Saler, Dịch Vụ,
  Nguồn, Doanh Thu, Note.
- Bảng PIVOT cuối sheet: với mỗi dịch vụ có dòng "Chi" (chi phí ads) và "Thu"
  (doanh thu) theo Facebook/Tiktok/Tổng -> tính ROAS.
"""

import re
import time
from collections import defaultdict

import config
import sheets

_DSV = {
    "sẹo rỗ", "sẹo lồi", "filler", "botox", "nám", "vein", "laserlift",
    "mụn", "prp", "nốt ruồi", "mồ hôi", "thâm mắt", "chăm sóc da", "khác",
    "đốt u tuyến bã",
}

_cache: tuple[float, dict] | None = None


def _money(s: str) -> int:
    digits = re.sub(r"[^\d]", "", s or "")
    return int(digits) if digits else 0


def _vnd(x: float) -> str:
    return f"{int(round(x)):,}".replace(",", ".") + "đ"


def _fetch() -> dict:
    ws = sheets.open_worksheet(config.ADS_SERVICE_SHEET_ID, config.ADS_SERVICE_GID)
    rows = ws.get_all_values()

    transactions: list[dict] = []
    pivot: dict[str, dict] = {}
    last_service: str | None = None  # tên dịch vụ chỉ ghi ở dòng "Chi", dòng "Thu" để trống

    for r in rows:
        c = [x.strip() for x in (r + [""] * 9)]
        # --- Dòng giao dịch: cột 0 là số (tháng), có dịch vụ + doanh thu ---
        if c[0].isdigit() and c[5] and _money(c[7]) > 0:
            transactions.append(
                {
                    "thang": c[0],
                    "saler": c[4] or "(không rõ)",
                    "dich_vu": c[5],
                    "nguon": c[6] or "(không rõ)",
                    "doanh_thu": _money(c[7]),
                }
            )
            continue
        # --- Dòng pivot: tên dịch vụ ở cột 0 (dòng Chi); dòng Thu để trống cột 0 ---
        if c[0].lower() in _DSV:
            last_service = c[0]
        kind = c[1].lower()
        if last_service and kind in ("chi", "thu"):
            fb, tt, tong = _money(c[2]), _money(c[3]), _money(c[4])
            entry = pivot.setdefault(last_service, {})
            # Có thể có 2 bảng pivot (kỳ gần + lũy kế) -> giữ bản có Tổng lớn hơn.
            if tong >= entry.get(f"{kind}_tong", 0):
                entry[f"{kind}_fb"] = fb
                entry[f"{kind}_tt"] = tt
                entry[f"{kind}_tong"] = tong

    return {"transactions": transactions, "pivot": pivot}


def get_data(force: bool = False) -> dict:
    global _cache
    now = time.time()
    if not force and _cache and (now - _cache[0]) < config.SHEET_CACHE_TTL:
        return _cache[1]
    data = _fetch()
    _cache = (now, data)
    return data


def _sum_by(transactions: list[dict], field: str) -> list[tuple[str, int, int]]:
    """Trả về [(giá trị, tổng doanh thu, số đơn)] sắp theo doanh thu giảm dần."""
    rev: dict[str, int] = defaultdict(int)
    cnt: dict[str, int] = defaultdict(int)
    for t in transactions:
        rev[t[field]] += t["doanh_thu"]
        cnt[t[field]] += 1
    out = [(k, rev[k], cnt[k]) for k in rev]
    return sorted(out, key=lambda x: -x[1])


def build_summary(data: dict) -> str:
    tx = data["transactions"]
    pivot = data["pivot"]
    parts: list[str] = []

    if tx:
        total = sum(t["doanh_thu"] for t in tx)
        months = sorted({t["thang"] for t in tx}, key=lambda m: int(m))
        parts.append(
            f"DOANH THU THEO ĐƠN (tháng {', '.join(months)}): "
            f"{len(tx)} đơn, tổng {_vnd(total)}"
        )
        parts.append("")

        parts.append("Doanh thu theo DỊCH VỤ:")
        for name, rev, cnt in _sum_by(tx, "dich_vu"):
            parts.append(f"  - {name}: {_vnd(rev)} ({cnt} đơn)")
        parts.append("")

        parts.append("Doanh thu theo KÊNH (nguồn):")
        for name, rev, cnt in _sum_by(tx, "nguon"):
            parts.append(f"  - {name}: {_vnd(rev)} ({cnt} đơn)")
        parts.append("")

        parts.append("Doanh thu theo NHÂN VIÊN SALE:")
        for name, rev, cnt in _sum_by(tx, "saler"):
            parts.append(f"  - {name}: {_vnd(rev)} ({cnt} đơn)")
        parts.append("")

    # ROAS theo dịch vụ (từ bảng pivot Chi/Thu)
    if pivot:
        parts.append("CHI PHÍ ADS & ROAS THEO DỊCH VỤ (từ bảng tổng hợp):")
        rows = []
        for sv, e in pivot.items():
            chi = e.get("chi_tong", 0)
            thu = e.get("thu_tong", 0)
            roas = (thu / chi) if chi else None
            rows.append((sv, chi, thu, roas))
        # Sắp theo ROAS giảm dần (None xuống cuối)
        rows.sort(key=lambda x: (x[3] is None, -(x[3] or 0)))
        for sv, chi, thu, roas in rows:
            roas_txt = f"ROAS {roas:.1f}x" if roas else "ROAS n/a"
            parts.append(
                f"  - {sv}: chi ads {_vnd(chi)} | doanh thu {_vnd(thu)} | {roas_txt}"
            )

    return "\n".join(parts).strip() or "Chưa có dữ liệu doanh thu theo dịch vụ."
