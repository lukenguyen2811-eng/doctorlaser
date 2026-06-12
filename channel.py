"""Đọc dữ liệu chi phí ads & doanh thu theo NGUỒN do nhân viên điền tay.

Sheet có các cột: Ngày | Nguồn/Kênh | Chi phí quảng cáo | Doanh thu nguồn |
Nhân viên | Ghi chú. Dùng để bổ sung "doanh thu/ROAS theo kênh" — thứ KiotViet
không lưu.
"""

import datetime as dt
import re
import time
from collections import defaultdict

import config
import sheets

_cache: tuple[float, list] | None = None


def _money(s: str) -> int:
    d = re.sub(r"[^\d]", "", s or "")
    return int(d) if d else 0


def _vnd(x: float) -> str:
    return f"{int(round(x)):,}".replace(",", ".") + "đ"


def _date(s: str) -> dt.date | None:
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", (s or "").strip())
    if not m:
        return None
    d, mo, y = (int(x) for x in m.groups())
    try:
        return dt.date(y, mo, d)
    except ValueError:
        return None


def _fetch() -> list[dict]:
    ws = sheets.open_worksheet(config.CHANNEL_SHEET_ID, config.CHANNEL_GID or None)
    rows = ws.get_all_values()
    out: list[dict] = []
    for r in rows[1:]:  # bỏ tiêu đề
        c = [x.strip() for x in (r + [""] * 6)]
        d = _date(c[0])
        if not d or not c[1]:
            continue
        if "ví dụ" in (c[5] or "").lower():  # bỏ dòng ví dụ
            continue
        out.append({"date": d, "nguon": c[1], "chi": _money(c[2]), "thu": _money(c[3])})
    return out


def get_data(force: bool = False) -> list[dict]:
    global _cache
    now = time.time()
    if not force and _cache and (now - _cache[0]) < config.SHEET_CACHE_TTL:
        return _cache[1]
    data = _fetch()
    _cache = (now, data)
    return data


def by_channel(rows: list[dict], from_d: dt.date, to_d: dt.date) -> dict:
    agg: dict[str, dict] = defaultdict(lambda: {"chi": 0, "thu": 0})
    for r in rows:
        if from_d <= r["date"] <= to_d:
            agg[r["nguon"]]["chi"] += r["chi"]
            agg[r["nguon"]]["thu"] += r["thu"]
    return agg


def build_lines(agg: dict) -> list[str]:
    """Tạo các dòng 'kênh: thu / chi / ROAS', sắp theo doanh thu giảm dần."""
    if not agg:
        return ["      (chưa có dữ liệu nhập tay)"]
    lines = []
    for ch, v in sorted(agg.items(), key=lambda x: -x[1]["thu"]):
        roas = (v["thu"] / v["chi"]) if v["chi"] else None
        rt = f", ROAS {roas:.1f}x" if roas else ""
        lines.append(
            f"      • {ch}: thu {_vnd(v['thu'])} / chi {_vnd(v['chi'])}{rt}"
        )
    return lines
