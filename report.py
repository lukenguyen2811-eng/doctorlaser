"""Báo cáo ngày (NHÓM 1 — Doanh thu & Sale).

Doanh thu = HÔM QUA (đã chốt sổ). Lead = HÔM NAY (thời gian thực).
Dùng để gửi tự động lúc 8h sáng hoặc gọi thủ công bằng /baocaongay.
"""

import datetime as dt
import re
from collections import Counter, defaultdict

import config


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
    return lines


def _ads_block(yesterday: dt.date, today: dt.date) -> list[str]:
    """Chi phí & hiệu quả Facebook ads: HÔM QUA + lũy kế tháng, kèm ROAS thô."""
    lines = [f"📢 ADS HÔM QUA ({yesterday:%d/%m}):"]
    if not config.meta_enabled():
        lines.append("  - (Chưa kết nối Meta ads)")
        return lines

    import meta

    ds = yesterday.strftime("%Y-%m-%d")
    try:
        t = meta.totals(meta.get_insights(ds, ds))
    except Exception as e:  # noqa: BLE001
        lines.append(f"  - Lỗi đọc Meta ads: {e}")
        return lines

    if t["spend"] <= 0:
        lines.append("  - Chưa có chi tiêu ads hôm qua.")
    else:
        lines.append(f"  - Chi quảng cáo: {_vnd(t['spend'])}")
        lines.append(f"  - Kết quả (tin nhắn/lead): {t['results']}")
        lines.append(
            f"  - CPL (giá mỗi kết quả): {_vnd(t['cpl']) if t['results'] else 'n/a'}"
        )
        lines.append(f"  - CTR: {t['ctr']:.2f}% | Click: {int(t['clicks'])}")
        # ROAS thô = doanh thu hôm qua (KiotViet) / chi ads hôm qua.
        if config.kiotviet_enabled():
            try:
                import kiotviet

                rev = kiotviet.total_revenue(kiotviet.get_invoices_for_date(yesterday))
                lines.append(
                    f"  - ROAS thô (DT hôm qua ÷ chi ads): {rev / t['spend']:.1f}x"
                )
            except Exception:  # noqa: BLE001
                pass

    # Lũy kế tháng (đến hết hôm qua — số đã chốt).
    first = today.replace(day=1)
    if first <= yesterday:
        try:
            tm = meta.totals(meta.get_insights(first.strftime("%Y-%m-%d"), ds))
            if tm["spend"] > 0:
                lines.append(
                    f"  - Lũy kế tháng {today.month} (đến {yesterday:%d/%m}): "
                    f"chi {_vnd(tm['spend'])} | KQ {tm['results']} | "
                    f"CPL {_vnd(tm['cpl']) if tm['results'] else 'n/a'}"
                )
        except Exception:  # noqa: BLE001
            pass
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


def _has_phone(record: dict) -> bool:
    """Lead được coi là ĐÃ LẤY SĐT nếu ô SĐT có >= 8 chữ số (số VN ~9-10 số)."""
    return len(re.sub(r"\D", "", record.get("sdt") or "")) >= 8


def _phone_lines(leads: list[dict]) -> list[str]:
    """Số lượng & tỉ lệ lead lấy được SĐT, kèm bóc tách theo nguồn."""
    n = len(leads) or 1
    got = [r for r in leads if _has_phone(r)]
    lines = [f"Lấy được SĐT: {len(got)}/{len(leads)} ({len(got) / n * 100:.1f}%)"]
    tot = Counter(_group_source(r.get("nguon", "")) for r in leads)
    ok = Counter(_group_source(r.get("nguon", "")) for r in got)
    for name in ("Facebook", "TikTok", "Còn lại"):
        t = tot.get(name, 0)
        if t:
            lines.append(f"  - {name}: {ok.get(name, 0)}/{t} ({ok.get(name, 0) / t * 100:.0f}%)")
    return lines


def _fmt_table(header: list[str], rows: list[list[str]], aligns: list[str]) -> list[str]:
    """Bảng monospace canh cột (cột 'l' canh trái, 'r' canh phải)."""
    cols = len(header)
    widths = [
        max(len(header[i]), max((len(r[i]) for r in rows), default=0))
        for i in range(cols)
    ]

    def fmt(cells: list[str]) -> str:
        out = []
        for i, c in enumerate(cells):
            out.append(c.ljust(widths[i]) if aligns[i] == "l" else c.rjust(widths[i]))
        return " ".join(out).rstrip()

    return [fmt(header)] + [fmt(r) for r in rows]


def _source_table(leads: list[dict]) -> list[str]:
    """Bảng lead theo nguồn (Facebook/TikTok/Còn lại) kèm số lượng và %."""
    n = len(leads) or 1
    grp = Counter(_group_source(r.get("nguon", "")) for r in leads)
    rows = [
        [name, str(grp.get(name, 0)), f"{grp.get(name, 0) / n * 100:.0f}%"]
        for name in ("Facebook", "TikTok", "Còn lại")
    ]
    return _fmt_table(["Nguồn", "SL", "%"], rows, ["l", "r", "r"])


def _status_source_table(leads: list[dict]) -> list[str]:
    """Bảng chéo Trạng thái × Nguồn (FB/TikTok/Còn lại) + Tổng + % — đủ mọi trạng thái."""
    grid: dict[str, Counter] = defaultdict(Counter)
    stot: Counter = Counter()
    for r in leads:
        st = (r.get("trang_thai") or "(chưa xử lý)").strip().upper() or "(chưa xử lý)"
        grid[st][_group_source(r.get("nguon", ""))] += 1
        stot[st] += 1
    # Ghim 3 trạng thái quan trọng lên đầu, phần còn lại xếp theo số lượng.
    pinned = ["ĐÃ ĐẾN", "ĐÃ ĐẶT HẸN", "ĐANG TƯ VẤN"]
    pinned_present = [s for s in pinned if s in stot]
    rest = [s for s, _ in stot.most_common() if s not in pinned_present]
    ordered = pinned_present + rest
    n = len(leads) or 1

    def row(label: str, statuses: list[str]) -> list[str]:
        fb = sum(grid[s].get("Facebook", 0) for s in statuses)
        tk = sum(grid[s].get("TikTok", 0) for s in statuses)
        cl = sum(grid[s].get("Còn lại", 0) for s in statuses)
        tot = fb + tk + cl
        return [label, str(fb), str(tk), str(cl), str(tot), f"{tot / n * 100:.0f}%"]

    rows = [row(s, [s]) for s in ordered]
    rows.append(row("TỔNG", ordered))
    return _fmt_table(
        ["Trạng thái", "FB", "TK", "CL", "Tổng", "%"],
        rows,
        ["l", "r", "r", "r", "r", "r"],
    )


def _lead_block(data: dict, day: dt.date) -> list[str]:
    """DATA ngày D — từ CRM chatbot, cửa sổ 18h hôm trước (D-1) → 18h ngày D."""
    import config
    import crm

    leads = crm.in_business_day(data["leads"], day)
    quan_tam = crm.in_business_day(data["quan_tam"], day)
    rac = crm.in_business_day(data["rac"], day)
    prev = day - dt.timedelta(days=1)
    lines = [
        f"📞 DATA NGÀY {day:%d/%m} "
        f"({prev:%d/%m} {config.CRM_DAY_START_HOUR}h → {day:%d/%m} {config.CRM_DAY_END_HOUR}h) — CRM:"
    ]
    lines += crm.funnel_lines(leads, quan_tam, rac)
    lines.append("  Chi tiết LEAD:")
    lines += crm.lead_lines(leads)
    return lines


def _month_block(data: dict, today: dt.date) -> list[str]:
    import crm
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
    lines.append("")
    lines.append("DATA (CRM chatbot):")
    y, m = today.year, today.month
    leads = crm.in_month(data["leads"], y, m)
    quan_tam = crm.in_month(data["quan_tam"], y, m)
    rac = crm.in_month(data["rac"], y, m)
    lines += crm.funnel_lines(leads, quan_tam, rac)
    lines.append("  Chi tiết LEAD:")
    lines += crm.lead_lines(leads)
    return lines


def build_daily(as_of: dt.date | None = None) -> str:
    """Báo cáo ngày.

    - Không truyền gì (lịch tự động 8h sáng): báo cáo cho HÔM QUA, lũy kế đến hôm nay.
    - Truyền `as_of` (vd /baocaongay 4/7): các khối "HÔM QUA" là đúng ngày đó,
      lũy kế tháng tính đến ngày đó.
    """
    if as_of is None:
        header_day = _today()
        day = header_day - dt.timedelta(days=1)
        month_ref = header_day
    else:
        header_day = as_of
        day = as_of
        month_ref = as_of

    parts = [f"📊 BÁO CÁO NGÀY — {header_day:%A %d/%m/%Y}", ""]
    parts += _revenue_block(day)
    parts.append("")
    parts += _ads_block(day, month_ref)
    parts.append("")

    import crm

    try:
        data = {
            "leads": crm.get_leads(),
            "quan_tam": crm.get_quan_tam(),
            "rac": crm.get_rac(),
        }
    except Exception as e:  # noqa: BLE001
        parts.append(f"📞 DATA: lỗi đọc CRM: {e}")
        return "\n".join(parts)

    parts += _lead_block(data, day)
    parts.append("")
    parts += _month_block(data, month_ref)
    return "\n".join(parts)
