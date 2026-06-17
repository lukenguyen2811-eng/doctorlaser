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

    total = kiotviet.total_revenue(inv)
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

    # Doanh thu / ROAS theo kênh marketing (từ form nhân viên điền)
    if config.channel_enabled():
        try:
            import channel

            rows = channel.get_data()
            agg = channel.by_channel(rows, yesterday, yesterday)
            lines.append("  - Doanh thu theo kênh marketing (form nhập tay):")
            lines += channel.build_lines(agg)
        except Exception as e:  # noqa: BLE001
            lines.append(
                "  - Doanh thu theo kênh: (chưa đọc được sheet form — kiểm tra "
                f"đã share cho service account & tạo tab chưa) [{type(e).__name__}]"
            )
    else:
        lines.append("  - Doanh thu theo kênh marketing: (cần bổ sung nguồn)")
    return lines


def _status_lines(counter: Counter, total: int, top: int = 6) -> list[str]:
    """Hiện top N trạng thái, gộp phần còn lại thành 'Khác' cho gọn."""
    items = counter.most_common()
    lines = []
    for k, v in items[:top]:
        lines.append(f"      • {k}: {v} ({v / total * 100:.0f}%)")
    rest = items[top:]
    if rest:
        rv = sum(v for _, v in rest)
        lines.append(
            f"      • Khác ({len(rest)} loại): {rv} ({rv / total * 100:.0f}%)"
        )
    return lines


def _group_source(nguon: str) -> str:
    """Gom nguồn về 3 nhóm: Facebook / TikTok / Còn lại."""
    s = (nguon or "").upper()
    if "TIKTOK" in s or "TIK TOK" in s:
        return "TikTok"
    if "FB" in s or "FACEBOOK" in s:
        return "Facebook"
    return "Còn lại"


def _source_lines(leads: list[dict]) -> list[str]:
    """Bảng lead theo nguồn (Facebook/TikTok/Còn lại) kèm số lượng và %."""
    n = len(leads) or 1
    grp = Counter(_group_source(r.get("nguon", "")) for r in leads)
    return [
        f"      • {name}: {grp.get(name, 0)} ({grp.get(name, 0) / n * 100:.0f}%)"
        for name in ("Facebook", "TikTok", "Còn lại")
    ]


def _lead_block(records: list[dict], day: dt.date) -> list[str]:
    lines = [f"📞 LEAD HÔM QUA ({day:%d/%m}):"]
    leads = _leads_on(records, day)
    n = len(leads)
    lines.append(f"  - Tổng lead: {n}")
    if leads:
        lines.append("  - Theo nguồn:")
        lines += _source_lines(leads)
        # Phân loại theo TRẠNG THÁI
        st = Counter(
            (r.get("trang_thai") or "(chưa xử lý)").strip().upper() or "(chưa xử lý)"
            for r in leads
        )
        lines.append("  - Theo trạng thái:")
        lines += _status_lines(st, n, top=7)
        # Nhấn mạnh kết quả chốt
        den = sum(1 for r in leads if _status_has(r, _STATUS_DEN))
        hen = sum(1 for r in leads if _status_has(r, _STATUS_HEN))
        lines.append(
            f"  - Kết quả: đã đặt hẹn {hen} ({hen / n * 100:.1f}%), "
            f"đã đến khám {den} ({den / n * 100:.1f}%)"
        )
    return lines


def _leads_in_month(records: list[dict], today: dt.date) -> list[dict]:
    out = []
    for r in records:
        d = _parse_lead_date(r.get("ngay", ""))
        if d and d.year == today.year and d.month == today.month:
            out.append(r)
    return out


def _month_block(records: list[dict], today: dt.date) -> list[str]:
    import kiotviet

    lines = [f"📅 LŨY KẾ THÁNG {today.month}/{today.year} (đến {today:%d/%m}):"]
    if config.kiotviet_enabled():
        try:
            inv = kiotviet.get_current_month_invoices()
            total = kiotviet.total_revenue(inv)
            lines.append(f"  - Doanh thu tổng: {_vnd(total)}")
            lines.append(f"  - Tổng khách chốt (hóa đơn): {len(inv)}")
        except Exception as e:  # noqa: BLE001
            lines.append(f"  - Doanh thu: lỗi KiotViet: {e}")
    else:
        lines.append("  - Doanh thu: (chưa kết nối KiotViet)")
    mleads = _leads_in_month(records, today)
    lines.append(f"  - Tổng lead: {len(mleads)}")
    if mleads:
        lines.append("  - Lead theo nguồn:")
        lines += _source_lines(mleads)
        st = Counter(
            (r.get("trang_thai") or "(chưa xử lý)").strip().upper() or "(chưa xử lý)"
            for r in mleads
        )
        nm = len(mleads)
        lines.append("  - Lead theo trạng thái:")
        lines += _status_lines(st, nm, top=6)
        den = sum(1 for r in mleads if _status_has(r, _STATUS_DEN))
        hen = sum(1 for r in mleads if _status_has(r, _STATUS_HEN))
        lines.append(
            f"  - Kết quả: đã đặt hẹn {hen} ({hen / nm * 100:.1f}%), "
            f"đã đến khám {den} ({den / nm * 100:.1f}%)"
        )

    # Doanh thu / ROAS theo kênh trong tháng (form nhân viên điền)
    if config.channel_enabled():
        try:
            import channel

            first = today.replace(day=1)
            agg = channel.by_channel(channel.get_data(), first, today)
            if agg:
                lines.append("  - Doanh thu theo kênh (form nhập tay):")
                lines += channel.build_lines(agg)
        except Exception:  # noqa: BLE001
            pass
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

    parts += _lead_block(records, yesterday)
    parts.append("")
    parts += _month_block(records, today)
    return "\n".join(parts)
