"""Tính các số liệu tổng hợp từ dữ liệu lead.

Mục đích: cung cấp con số CHÍNH XÁC cho Claude (mô hình ngôn ngữ hay đếm sai),
để Claude dựa vào đó trả lời thay vì tự đếm tay.
"""

from collections import Counter


def _count_by(records: list[dict], field: str) -> list[tuple[str, int]]:
    counter: Counter = Counter()
    for r in records:
        value = (r.get(field) or "").strip()
        if not value:
            value = "(trống)"
        counter[value] += 1
    return counter.most_common()


def _fmt(pairs: list[tuple[str, int]], total: int) -> str:
    lines = []
    for name, count in pairs:
        pct = (count / total * 100) if total else 0
        lines.append(f"  - {name}: {count} ({pct:.1f}%)")
    return "\n".join(lines) if lines else "  (không có dữ liệu)"


def build_summary(records: list[dict]) -> str:
    """Tạo bản tóm tắt số liệu dạng text để đưa vào prompt."""
    total = len(records)
    parts = [f"TỔNG SỐ LEAD: {total}", ""]

    parts.append("Theo NGUỒN:")
    parts.append(_fmt(_count_by(records, "nguon"), total))
    parts.append("")

    parts.append("Theo TRẠNG THÁI:")
    parts.append(_fmt(_count_by(records, "trang_thai"), total))
    parts.append("")

    parts.append("Theo DỊCH VỤ:")
    parts.append(_fmt(_count_by(records, "dich_vu"), total))
    parts.append("")

    parts.append("Theo TELESALE PHỤ TRÁCH:")
    parts.append(_fmt(_count_by(records, "telesale"), total))
    parts.append("")

    parts.append("Theo NGÀY:")
    parts.append(_fmt(_count_by(records, "ngay"), total))

    return "\n".join(parts)
