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
    """Đọc MỌI tab: tên tab = kênh (TikTok/Facebook/Google), mỗi dòng = 1 dịch vụ."""
    ss = sheets.open_spreadsheet(config.CHANNEL_SHEET_ID)
    out: list[dict] = []
    for ws in ss.worksheets():
        channel = ws.title.strip()
        try:
            rows = ws.get_all_values()
        except Exception:  # noqa: BLE001
            continue
        for r in rows[1:]:  # bỏ tiêu đề
            c = [x.strip() for x in (r + [""] * 6)]
            d = _date(c[0])
            if not d or not c[1]:
                continue
            if "ví dụ" in (c[5] or "").lower():  # bỏ dòng ví dụ
                continue
            out.append(
                {
                    "date": d,
                    "nguon": channel,
                    "dich_vu": c[1],
                    "chi": _money(c[2]),
                    "thu": _money(c[3]),
                }
            )
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


def by_channel_service(rows: list[dict], from_d: dt.date, to_d: dt.date) -> dict:
    """Tổng hợp lồng: {kênh: {dịch vụ: {chi, thu}}}."""
    agg: dict = defaultdict(lambda: defaultdict(lambda: {"chi": 0, "thu": 0}))
    for r in rows:
        if from_d <= r["date"] <= to_d:
            cell = agg[r["nguon"]][r["dich_vu"]]
            cell["chi"] += r["chi"]
            cell["thu"] += r["thu"]
    return agg


def build_detail_lines(agg: dict) -> list[str]:
    """Dòng chi tiết kênh -> từng dịch vụ + ROAS."""
    if not agg:
        return ["      (chưa có dữ liệu nhập tay)"]
    lines = []
    for ch in sorted(agg, key=lambda c: -sum(s["thu"] for s in agg[c].values())):
        tot_thu = sum(s["thu"] for s in agg[ch].values())
        tot_chi = sum(s["chi"] for s in agg[ch].values())
        roas = (tot_thu / tot_chi) if tot_chi else None
        rt = f", ROAS {roas:.1f}x" if roas else ""
        lines.append(f"      • {ch}: thu {_vnd(tot_thu)} / chi {_vnd(tot_chi)}{rt}")
        for sv, v in sorted(agg[ch].items(), key=lambda x: -x[1]["thu"]):
            r2 = (v["thu"] / v["chi"]) if v["chi"] else None
            r2t = f" (ROAS {r2:.1f}x)" if r2 else ""
            lines.append(f"          - {sv}: thu {_vnd(v['thu'])}/chi {_vnd(v['chi'])}{r2t}")
    return lines
