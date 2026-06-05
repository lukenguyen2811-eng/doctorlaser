"""Đọc chi phí ads theo THÁNG từ sheet pivot (mỗi tab = 1 tháng).

Cấu trúc mỗi tab: theo từng kênh (Facebook/Tiktok/Youtube) có nhiều dòng chỉ số;
dòng có nhãn "Chi Phí Ads" ở cột thứ 2, cột "Tổng" (cột 3) là tổng chi phí tháng
của kênh đó. Tháng lấy từ TÊN TAB (vd "Tháng 8").
"""

import re
import time

import config
import sheets

_CHANNELS = {"facebook": "Facebook", "tiktok": "Tiktok", "youtube": "Youtube"}
_cache: dict = {}  # key -> (timestamp, data)


def _money(s: str) -> int:
    d = re.sub(r"[^\d]", "", s or "")
    return int(d) if d else 0


def _vnd(x: float) -> str:
    return f"{int(round(x)):,}".replace(",", ".") + "đ"


def _month_from_title(title: str) -> int | None:
    for x in re.findall(r"\d+", title or ""):
        if 1 <= int(x) <= 12:
            return int(x)
    return None


def _fetch(months: set[int] | None = None) -> dict:
    """Trả về {tháng: {kênh: chi_phí}}. Chỉ đọc các tab có tháng trong `months`."""
    ss = sheets.open_spreadsheet(config.ADS_MONTHLY_SHEET_ID)
    result: dict[int, dict[str, int]] = {}
    for ws in ss.worksheets():
        month = _month_from_title(ws.title)
        if month is None or (months and month not in months):
            continue  # bỏ qua tab không cần -> nhanh hơn nhiều
        try:
            rows = ws.get_all_values()
        except Exception:  # noqa: BLE001
            continue
        channel = None
        spend: dict[str, int] = {}
        for r in rows:
            c = [x.strip() for x in (r + [""] * 3)]
            if c[0].lower() in _CHANNELS:
                channel = _CHANNELS[c[0].lower()]
            if channel and c[1].lower() == "chi phí ads" and c[2]:
                spend.setdefault(channel, _money(c[2]))
        if spend:
            result[month] = spend
    return result


def get_data(months: set[int] | None = None, force: bool = False) -> dict:
    key = tuple(sorted(months)) if months else "all"
    now = time.time()
    hit = _cache.get(key)
    if not force and hit and (now - hit[0]) < config.SHEET_CACHE_TTL:
        return hit[1]
    data = _fetch(months)
    _cache[key] = (now, data)
    return data


def build_roas(
    spend: dict, revenue_by_month: dict, from_m: int, to_m: int
) -> str:
    """Ghép chi phí ads tháng với doanh thu tháng -> ROAS theo tháng."""
    months = sorted(
        m for m in (set(spend) | set(revenue_by_month)) if from_m <= m <= to_m
    )
    if not months:
        return "Không có dữ liệu chi phí ads trong khoảng tháng đã chọn."

    lines = [
        "CHI PHÍ ADS & ROAS THEO THÁNG (chi phí từ sheet ads tháng; doanh thu là "
        "phần ghi nhận từ ads):"
    ]
    for m in months:
        s = spend.get(m, {})
        total = sum(s.values())
        rev = revenue_by_month.get(m, 0)
        chan = ", ".join(f"{k} {_vnd(v)}" for k, v in s.items())
        line = f"  - Tháng {m}: chi ads {_vnd(total)}"
        if chan:
            line += f" ({chan})"
        if total:
            line += f" | doanh thu {_vnd(rev)} | ROAS {rev / total:.1f}x"
        else:
            line += " | (thiếu chi phí ads)"
        lines.append(line)
    return "\n".join(lines)
