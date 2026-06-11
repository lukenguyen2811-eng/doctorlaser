"""Báo cáo ngày (NHÓM 1 — Doanh thu & Sale).

Doanh thu = HÔM QUA (đã chốt sổ). Lead = HÔM NAY (thời gian thực).
Dùng để gửi tự động lúc 8h sáng hoặc gọi thủ công bằng /baocaongay.
"""

import datetime as dt
import re
from collections import Counter, defaultdict

import config
import sheets


def tzinfo() -> dt.tzinfo:
    """Múi giờ VN; nếu container thiếu dữ liệu timezone thì lùi về UTC+7 cố định."""
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(config.TIMEZONE)
    except Exception:  # noqa: BLE001
        return dt.timezone(dt.timedelta(hours=7))

# Trạng thái thể hiện khách đã đến / đã đặt hẹn (để đếm trong báo cáo).
_STATUS_DEN = ("đã đến",)
_STATUS_HEN = ("đã đặt hẹn", "đặt hẹn")


def _vnd(x: float) -> str:
    return f"{int(round(x)):,}".replace(",", ".") + "đ"


def _today() -> dt.date:
    return dt.datetime.now(tzinfo()).date()


def _parse_lead_date(s: str) -> dt.date | None:
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", (s or "").strip())
    if not m:
        return None
    d, mo, y = (int(x) for x in m.groups())
    try:
        return dt.date(y, mo, d)
    except ValueError:
        return None


def _leads_on(records: list[dict], day: dt.date) -> list[dict]:
    return [r for r in records if _parse_lead_date(r.get("ngay", "")) == day]


def _status_has(record: dict, keys) -> bool:
    st = (record.get("trang_thai") or "").strip().lower()
    return any(k in st for k in keys)


def _revenue_block(yesterday: dt.date) -> list[str]:
    import kiotviet  # nhập tại chỗ để tránh lỗi import khi chưa cấu hình

    lines = [f"💰 DOANH THU HÔM QUA ({yesterday:%d/%m}):"]
    if not config.kiotviet_enabled():
        lines.append("  - (Chưa kết nối KiotViet)")
        return lines
    try:
        inv = kiotviet.get_invoices_for_date(yesterday)
    except Exception as e:  # noqa: BLE001
        lines.append(f"  - Lỗi đọc KiotViet: {e}")
        return lines

    if not inv:
        lines.append("  - Chưa có hóa đơn nào hôm qua.")
        return lines

    total = sum(float(i.get("total") or 0) for i in inv)
    lines.append(f"  - Tổng doanh thu: {_vnd(total)}")
    lines.append(f"  - Số khách chốt (hóa đơn): {len(inv)}")

    # Dịch vụ bán chạy nhất hôm qua (từ chi tiết hóa đơn)
    prod: dict[str, float] = defaultdict(float)
    for i in inv:
        for d in i.get("invoiceDetails") or []:
            name = d.get("categoryName") or d.get("productName") or "(không rõ)"
            prod[name] += float(d.get("subTotal") or 0)
    if prod:
        lines.append("  - Dịch vụ bán chạy:")
        for name, v in sorted(prod.items(), key=lambda x: -x[1])[:5]:
            lines.append(f"      • {name}: {_vnd(v)}")
    else:
        lines.append("  - (Hóa đơn không kèm chi tiết dịch vụ)")
    lines.append("  - Doanh thu theo kênh marketing: (cần bổ sung nguồn — KiotViet "
                 "không lưu kênh)")
    return lines


def _lead_block(records: list[dict], today: dt.date, yesterday: dt.date) -> list[str]:
    lines = [f"📞 LEAD HÔM NAY ({today:%d/%m}, tính đến lúc gửi):"]
    tleads = _leads_on(records, today)
    lines.append(f"  - Tổng lead: {len(tleads)}")
    if tleads:
        src = Counter((r.get("nguon") or "(trống)").strip() for r in tleads)
        lines.append(
            "  - Theo kênh: "
            + ", ".join(f"{k} {v}" for k, v in src.most_common())
        )
        # Phân loại theo TRẠNG THÁI
        st = Counter(
            (r.get("trang_thai") or "(chưa xử lý)").strip().upper() or "(chưa xử lý)"
            for r in tleads
        )
        lines.append("  - Theo trạng thái:")
        for k, v in st.most_common():
            pct = v / len(tleads) * 100
            lines.append(f"      • {k}: {v} ({pct:.0f}%)")

    # Tỷ lệ chốt từ lead HÔM QUA (đủ 1 ngày để đánh giá)
    yleads = _leads_on(records, yesterday)
    if yleads:
        den_y = sum(1 for r in yleads if _status_has(r, _STATUS_DEN))
        rate = den_y / len(yleads) * 100
        lines.append("")
        lines.append(
            f"📈 Tỷ lệ chốt từ lead HÔM QUA: {den_y}/{len(yleads)} đến khám "
            f"= {rate:.1f}%"
        )
    return lines


def build_daily() -> str:
    today = _today()
    yesterday = today - dt.timedelta(days=1)

    parts = [f"📊 BÁO CÁO NGÀY — {today:%A %d/%m/%Y}", ""]
    parts += _revenue_block(yesterday)
    parts.append("")

    records = []
    try:
        records = sheets.get_records()
    except Exception as e:  # noqa: BLE001
        parts.append(f"📞 LEAD: lỗi đọc Google Sheet: {e}")
        return "\n".join(parts)

    parts += _lead_block(records, today, yesterday)
    return "\n".join(parts)
