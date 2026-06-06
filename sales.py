"""Tổng hợp số liệu bán hàng từ hóa đơn KiotViet.

Đưa ra số liệu CHÍNH XÁC, gọn (để tiết kiệm token) cho Claude diễn giải.
"""

from collections import Counter, defaultdict


def _vnd(x: float) -> str:
    return f"{int(round(x)):,}".replace(",", ".") + "đ"


def _invoice_date(inv: dict) -> str:
    d = inv.get("purchaseDate") or ""
    return d[:10]  # phần ngày YYYY-MM-DD


def build_summary(invoices: list[dict], customer_total: int | None = None) -> str:
    n = len(invoices)
    if n == 0:
        return "Không có hóa đơn nào trong khoảng thời gian đã chọn."

    total_rev = sum(float(inv.get("total") or 0) for inv in invoices)
    avg = total_rev / n if n else 0

    parts = [
        "BÁO CÁO DOANH THU (KiotViet - hóa đơn thực tế)",
        f"SỐ HÓA ĐƠN: {n}",
        f"TỔNG DOANH THU: {_vnd(total_rev)}",
        f"GIÁ TRỊ TRUNG BÌNH/HÓA ĐƠN: {_vnd(avg)}",
    ]
    if customer_total is not None:
        parts.append(f"TỔNG SỐ KHÁCH HÀNG (toàn hệ thống): {customer_total}")
    parts.append("")

    # Doanh thu theo DỊCH VỤ (từ chi tiết hóa đơn) — phần quan trọng nhất.
    prod_rev: dict[str, float] = defaultdict(float)
    prod_qty: Counter = Counter()
    has_detail = False
    for inv in invoices:
        for d in inv.get("invoiceDetails") or []:
            has_detail = True
            name = (
                d.get("categoryName")
                or d.get("productName")
                or d.get("productCode")
                or "(không rõ)"
            )
            prod_rev[name] += float(d.get("subTotal") or 0)
            prod_qty[name] += float(d.get("quantity") or 0)
    parts.append("DOANH THU THEO DỊCH VỤ:")
    if has_detail:
        for name, v in sorted(prod_rev.items(), key=lambda x: -x[1]):
            pct = (v / total_rev * 100) if total_rev else 0
            parts.append(
                f"  - {name}: {_vnd(v)} ({pct:.1f}%, SL: {int(prod_qty[name])})"
            )
    else:
        parts.append(
            "  (Hóa đơn KiotViet không kèm chi tiết dịch vụ — không tách được "
            "theo dịch vụ. Cần kiểm tra cấu hình API/đơn hàng.)"
        )
    parts.append("")

    # Doanh thu theo ngày
    by_day: dict[str, float] = defaultdict(float)
    for inv in invoices:
        by_day[_invoice_date(inv)] += float(inv.get("total") or 0)
    parts.append("DOANH THU THEO NGÀY:")
    for day in sorted(by_day, reverse=True):
        parts.append(f"  - {day}: {_vnd(by_day[day])}")
    parts.append("")

    # Doanh thu theo chi nhánh
    by_branch: dict[str, float] = defaultdict(float)
    for inv in invoices:
        by_branch[inv.get("branchName") or "(không rõ)"] += float(inv.get("total") or 0)
    if len(by_branch) > 1:
        parts.append("DOANH THU THEO CHI NHÁNH:")
        for b, v in sorted(by_branch.items(), key=lambda x: -x[1]):
            parts.append(f"  - {b}: {_vnd(v)}")
        parts.append("")

    # Top khách hàng theo chi tiêu (từ hóa đơn)
    by_customer: dict[str, float] = defaultdict(float)
    for inv in invoices:
        name = inv.get("customerName") or "Khách lẻ"
        by_customer[name] += float(inv.get("total") or 0)
    top_customers = sorted(by_customer.items(), key=lambda x: -x[1])[:10]
    parts.append("TOP 10 KHÁCH HÀNG (theo chi tiêu trong kỳ):")
    for name, v in top_customers:
        parts.append(f"  - {name}: {_vnd(v)}")

    return "\n".join(parts).strip()
