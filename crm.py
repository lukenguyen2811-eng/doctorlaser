"""Đọc dữ liệu từ CRM chatbot (Google Sheet CRM_DoctorLaser_v3).

Pipeline chatbot phân loại mọi hội thoại thành 3 nhóm:
- RAC        : spam / không nhu cầu
- QUAN_TAM   : có nhu cầu nhưng CHƯA cho SĐT
- LEADS      : ĐÃ cho SĐT

Module này thay cho sheet tay ở báo cáo ngày (/baocaongay) và /stats.
"Tổng data" = RAC + QUAN_TAM + LEADS.
"""

import datetime as dt
import re
import time
from collections import Counter

import config
import sheets

# Vị trí cột (0-based) từng tab. "tg" = thời điểm nhận (ngày + giờ).
_LEADS_COL = {
    "ngay": 1, "nguon": 2, "sdt": 3, "ho_ten": 4, "dich_vu": 5,
    "phan_loai": 6, "nhan_vien": 8, "trang_thai": 9, "khach_cu": 13,
    "ma": 17, "tg": 19,
}
_QUANTAM_COL = {"ma": 0, "ngay": 1, "nguon": 3, "dich_vu": 5, "trang_thai": 8, "tg": 15}
_RAC_COL = {"ma": 0, "ngay": 1, "nguon": 2, "trang_thai": 6, "tg": 7}

_cache: dict[str, tuple[float, list[dict]]] = {}

# Chuẩn hoá NGUỒN: chatbot và sale ghi hoa/thường lẫn lộn ("TikTok"/"TIKTOK",
# "Facebook"/"FACEBOOK") làm 1 kênh bị tách thành nhiều dòng và % ra lead sai.
# Gộp về 1 tên hiển thị chung ngay khi đọc sheet.
_NGUON_ALIAS = {
    "tiktok": "TikTok",
    "facebook": "Facebook",
    "fb": "Facebook",
    "zalo": "Zalo",
    "hotline": "Hotline",
    "facebook - seo": "Facebook - SEO",
    "fb - seo": "Facebook - SEO",
    "seo (web / zalo oa)": "SEO (Web/Zalo OA)",
    "seo (web/zalo oa)": "SEO (Web/Zalo OA)",
    "seo": "SEO (Web/Zalo OA)",
}


def _norm_nguon(s: str) -> str:
    key = re.sub(r"\s+", " ", (s or "").strip()).lower()
    if not key:
        return ""
    # Nguồn lạ chưa có alias: viết hoa chữ đầu mỗi từ để mọi biến thể
    # hoa/thường vẫn gộp về cùng 1 dòng.
    return _NGUON_ALIAS.get(key, key.title())


def enabled() -> bool:
    return bool(config.CRM_SHEET_ID)


def _fetch(tab: str, colmap: dict) -> list[dict]:
    ss = sheets.open_spreadsheet(config.CRM_SHEET_ID)
    ws = ss.worksheet(tab)
    rows = ws.get_all_values()
    out: list[dict] = []
    for r in rows[1:]:  # bỏ tiêu đề
        c = [x.strip() for x in (r + [""] * 20)]
        rec = {k: c[i] for k, i in colmap.items()}
        if not any(rec.values()):
            continue
        if "nguon" in rec:
            rec["nguon"] = _norm_nguon(rec["nguon"])
        out.append(rec)
    return out


def _get(tab: str, colmap: dict, force: bool) -> list[dict]:
    now = time.time()
    hit = _cache.get(tab)
    if not force and hit and (now - hit[0]) < config.SHEET_CACHE_TTL:
        return hit[1]
    data = _fetch(tab, colmap)
    _cache[tab] = (now, data)
    return data


def get_leads(force: bool = False) -> list[dict]:
    return _get(config.CRM_LEADS_TAB, _LEADS_COL, force)


def get_quan_tam(force: bool = False) -> list[dict]:
    return _get("QUAN_TAM", _QUANTAM_COL, force)


def get_rac(force: bool = False) -> list[dict]:
    return _get("RAC", _RAC_COL, force)


def parse_date(s: str) -> dt.date | None:
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", (s or "").strip())
    if not m:
        return None
    try:
        return dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def parse_dt(s: str) -> dt.datetime | None:
    """Parse 'dd/mm/yyyy HH:MM' -> datetime (cột thời gian nhận)."""
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})[ T]+(\d{1,2}):(\d{2})", (s or "").strip())
    if not m:
        return None
    try:
        return dt.datetime(
            int(m.group(3)), int(m.group(2)), int(m.group(1)),
            int(m.group(4)), int(m.group(5)),
        )
    except ValueError:
        return None


def in_business_day(records: list[dict], day: dt.date) -> list[dict]:
    """Bản ghi thuộc 'ngày báo cáo' D = [D-1 18:00, D 18:00) — trọn 24 giờ.

    Ví dụ báo cáo ngày 23/7: lấy từ 18h ngày 22/7 đến (trước) 18h ngày 23/7.

    - Có cột giờ ("tg"): lọc chính xác theo cửa sổ.
    - Chưa có giờ (bản cũ): fallback đếm theo NGÀY (Ngày vào == D).
    """
    start = dt.datetime.combine(
        day - dt.timedelta(days=1), dt.time(config.CRM_DAY_START_HOUR, 0)
    )
    end = dt.datetime.combine(day, dt.time(config.CRM_DAY_END_HOUR, 0))
    out = []
    for r in records:
        tv = parse_dt(r.get("tg", ""))
        if tv is not None:
            if start <= tv < end:
                out.append(r)
        elif parse_date(r.get("ngay", "")) == day:
            out.append(r)
    return out


def has_phone(r: dict) -> bool:
    return len(re.sub(r"\D", "", r.get("sdt") or "")) >= 8


def on_day(records: list[dict], day: dt.date) -> list[dict]:
    return [r for r in records if parse_date(r.get("ngay", "")) == day]


def in_month(records: list[dict], year: int, month: int) -> list[dict]:
    out = []
    for r in records:
        d = parse_date(r.get("ngay", ""))
        if d and d.year == year and d.month == month:
            out.append(r)
    return out


# Giữ tên cũ để tương thích.
leads_on = on_day
leads_in_month = in_month


def _counter(rows: list[dict], field: str, empty: str = "(không rõ)") -> Counter:
    return Counter((r.get(field) or empty).strip() or empty for r in rows)


def dedupe_quan_tam(quan_tam: list[dict], leads: list[dict]) -> list[dict]:
    """Loại khỏi QUAN_TÂM những hội thoại ĐÃ lên LEADS (cùng mã hội thoại).

    Khi khách cho SĐT, chatbot thêm dòng vào LEADS nhưng dòng QUAN_TÂM vẫn còn
    -> 1 người bị đếm 2 lần trong tổng data. Khớp theo 'Mã hội thoại' để khử.
    """
    lead_ids = {r.get("ma") for r in leads if r.get("ma")}
    return [r for r in quan_tam if not (r.get("ma") and r.get("ma") in lead_ids)]


def dedupe_rac(rac: list[dict], leads: list[dict], quan_tam: list[dict]) -> list[dict]:
    """Loại khỏi RÁC những hội thoại đang nằm ở LEADS hoặc QUAN_TÂM.

    Chatbot đổi nhóm hội thoại nhưng dòng cũ ở RÁC vẫn còn -> 1 người bị đếm
    2 lần (kiểm chứng 09/2026: 9 hội thoại tháng 9 vừa ở RÁC vừa ở nhóm khác).
    Ưu tiên trạng thái tốt nhất: LEADS > QUAN_TÂM > RÁC.
    """
    keep_ids = {r.get("ma") for r in leads if r.get("ma")}
    keep_ids |= {r.get("ma") for r in quan_tam if r.get("ma")}
    return [r for r in rac if not (r.get("ma") and r.get("ma") in keep_ids)]


def funnel_lines(leads: list[dict], quan_tam: list[dict], rac: list[dict]) -> list[str]:
    """Tổng data (RÁC+QUAN_TÂM+LEADS) + trạng thái từng nhóm (đã khử trùng)."""
    quan_tam = dedupe_quan_tam(quan_tam, leads)
    rac = dedupe_rac(rac, leads, quan_tam)
    nl, nq, nr = len(leads), len(quan_tam), len(rac)
    tot = nl + nq + nr
    # Rác mà sale đánh dấu "KHÁCH CŨ QUÉT OA" (khách cũ quét mã Zalo OA) — vẫn là
    # rác nhưng đáng ghi chú riêng để sale biết đó không phải data mới.
    rac_khachcu = sum(
        1 for r in rac if "khách cũ quét" in (r.get("trang_thai") or "").lower()
    )
    lines = [f"  - TỔNG DATA: {tot}"]
    if tot:
        lines.append(f"      • Lead (đã có SĐT): {nl} ({nl / tot * 100:.0f}%)")
        lines.append(f"      • Quan tâm (chưa SĐT): {nq} ({nq / tot * 100:.0f}%)")
        rac_line = f"      • Rác: {nr} ({nr / tot * 100:.0f}%)"
        if rac_khachcu:
            rac_line += f" (trong đó {rac_khachcu} data khách cũ quét OA)"
        lines.append(rac_line)
    if leads:
        st = _counter(leads, "trang_thai", "(chưa)")
        lines.append("  - Trạng thái LEAD: " + ", ".join(f"{k} {v}" for k, v in st.most_common()))
    if quan_tam:
        st = _counter(quan_tam, "trang_thai", "(chưa)")
        lines.append("  - Trạng thái QUAN_TÂM: " + ", ".join(f"{k} {v}" for k, v in st.most_common()))
    return lines


def source_totals(
    leads: list[dict], quan_tam: list[dict], rac: list[dict]
) -> Counter:
    """Tổng data (lead + quan tâm + rác) theo từng nguồn, đã khử trùng."""
    quan_tam = dedupe_quan_tam(quan_tam, leads)
    rac = dedupe_rac(rac, leads, quan_tam)
    total: Counter = Counter()
    for rows in (leads, quan_tam, rac):
        total.update(_counter(rows, "nguon"))
    return total


def lead_lines(
    leads: list[dict],
    quan_tam: list[dict] | None = None,
    rac: list[dict] | None = None,
) -> list[str]:
    """Chi tiết nhóm LEAD (đã có SĐT): theo nguồn, phân loại, kết quả.

    Có quan_tam/rac -> mỗi nguồn hiện 'lead/tổng data' của nguồn đó
    (vd TikTok: 3/10 = 3 lead trên 10 data TikTok).
    """
    n = len(leads)
    if not n:
        return ["  - (Chưa có lead)"]
    lead_src = _counter(leads, "nguon")
    if quan_tam is not None or rac is not None:
        total_src = source_totals(leads, quan_tam or [], rac or [])
        lines = ["  - Theo nguồn (lead/tổng data nguồn):"]
        # Sắp theo tổng data giảm dần; gồm cả nguồn có data nhưng 0 lead.
        for name, tot in total_src.most_common():
            c = lead_src.get(name, 0)
            lines.append(f"      • {name}: {c}/{tot} ({c / tot * 100:.0f}% ra lead)")
    else:
        lines = ["  - Theo nguồn:"]
        for name, c in lead_src.most_common():
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


def build_summary(leads: list[dict], quan_tam: list[dict], rac: list[dict]) -> str:
    """Tóm tắt tổng hợp cho /stats: tổng data + funnel + chi tiết lead."""
    parts = ["TỔNG DATA & PHÂN LOẠI (CRM chatbot):"]
    parts += funnel_lines(leads, quan_tam, rac)
    parts.append("")

    n = len(leads)

    def block(title: str, counter: Counter) -> list[str]:
        out = [title]
        for name, c in counter.most_common():
            out.append(f"  - {name}: {c} ({c / n * 100:.1f}%)" if n else f"  - {name}: {c}")
        return out

    parts.append(f"CHI TIẾT LEAD (đã có SĐT): {n}")
    parts.append("")
    parts.append("Theo NGUỒN (lead/tổng data nguồn):")
    lead_src = _counter(leads, "nguon")
    for name, tot in source_totals(leads, quan_tam, rac).most_common():
        c = lead_src.get(name, 0)
        parts.append(f"  - {name}: {c}/{tot} ({c / tot * 100:.0f}% ra lead)")
    parts.append("")
    parts += block("Theo PHÂN LOẠI:", _counter(leads, "phan_loai", "(chưa)"))
    parts.append("")
    parts += block("Theo TRẠNG THÁI:", _counter(leads, "trang_thai", "(chưa)"))
    parts.append("")
    parts += block("Theo DỊCH VỤ:", _counter(leads, "dich_vu", "(chưa rõ)"))
    parts.append("")
    parts += block("Theo NGÀY:", _counter(leads, "ngay", "(trống)"))
    return "\n".join(parts)
