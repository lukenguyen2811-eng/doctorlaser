# -*- coding: utf-8 -*-
"""Tổng hợp CÔNG VIỆC SALE THEO TUẦN — gửi sáng thứ 6 cạnh khối cohort.

So sánh 7 ngày gần nhất (đến hết hôm qua) với 7 ngày liền trước, theo từng
nhân viên: khách tương tác, phút talktime với khách (đã loại nội bộ tổng
đài), cuộc/bắt máy, lead cập nhật, lịch tạo, phút Zalo (chưa phân loại
khách/nội bộ — ghi riêng). Nguồn: KIOT /api/ingest/sale-daily.

Tự chứa, Python 3.9-safe. Chạy tay: python3 saletuan.py
"""
from __future__ import annotations

import datetime as dt
import os
from collections import defaultdict

import requests

_URL = "https://kiot-production.up.railway.app/api/ingest/sale-daily"


def _fetch(tu, den):
    tok = os.environ.get("KIOT_INGEST_TOKEN") or os.environ.get("INGEST_TOKEN") or ""
    if not tok:
        raise RuntimeError("Thiếu KIOT_INGEST_TOKEN")
    r = requests.get(_URL, headers={"x-ingest-token": tok},
                     params={"tu": str(tu), "den": str(den)}, timeout=60)
    if r.status_code != 200 or not (r.json() or {}).get("ok"):
        raise RuntimeError("sale-daily trả %s" % r.status_code)
    return r.json().get("rows") or []


def _gop(rows):
    """Gộp theo nhân viên: [khách, phút, cuộc, bắt máy, lead, lịch, zalo_phút]."""
    out = defaultdict(lambda: [0, 0.0, 0, 0, 0, 0, 0.0])
    for x in rows:
        t = out[x.get("nhan_vien") or "?"]
        t[0] += int(x.get("so_khach_tuong_tac") or 0)
        t[1] += float(x.get("phut_talktime_khach") or 0)
        t[2] += int(x.get("so_cuoc_khach") or 0)
        t[3] += int(x.get("so_bat_may") or 0)
        t[4] += int(x.get("so_lead_cap_nhat") or 0)
        t[5] += int(x.get("so_lich_tao") or 0)
        t[6] += float((x.get("zalo_khong_ro_khach") or {}).get("phut") or 0)
    return out


def build() -> str:
    try:
        from zoneinfo import ZoneInfo
        today = dt.datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()
    except Exception:  # noqa: BLE001
        today = (dt.datetime.utcnow() + dt.timedelta(hours=7)).date()
    d2 = today - dt.timedelta(days=1)
    d1 = d2 - dt.timedelta(days=6)
    p2 = d1 - dt.timedelta(days=1)
    p1 = p2 - dt.timedelta(days=6)

    nay = _gop(_fetch(d1, d2))
    truoc = _gop(_fetch(p1, p2))

    def _d(v, o):
        if o <= 0:
            return ""
        ch = (v - o) / o * 100
        return " (%+.0f%%)" % ch if abs(ch) >= 5 else " (~)"

    lines = ["👥 CÔNG VIỆC SALE TUẦN %s–%s (so với 7 ngày liền trước)" % (
        d1.strftime("%d/%m"), d2.strftime("%d/%m"))]
    tk = sum(v[0] for v in nay.values())
    tk0 = sum(v[0] for v in truoc.values())
    tp = sum(v[1] for v in nay.values())
    tp0 = sum(v[1] for v in truoc.values())
    lines.append("  - Toàn đội: %d lượt khách%s | %.0f phút talktime%s" % (
        tk, _d(tk, tk0), tp, _d(tp, tp0)))
    for nv, t in sorted(nay.items(), key=lambda x: -x[1][1]):
        t0 = truoc.get(nv, [0, 0.0, 0, 0, 0, 0, 0.0])
        dong = ("      • %s: %d khách%s | %.0f phút%s | %d cuộc/%d bắt máy"
                % (nv, t[0], _d(t[0], t0[0]), t[1], _d(t[1], t0[1]), t[2], t[3]))
        if t[4] or t[5]:
            dong += " | lead %d, lịch %d" % (t[4], t[5])
        if t[6] > 0:
            dong += " | Zalo %.0f phút" % t[6]
        lines.append(dong)
    lines.append("")
    lines.append("Ghi chú: phút talktime = đàm thoại với KHÁCH qua tổng đài (đã loại "
                 "nội bộ). Phút Zalo ghi riêng — chưa phân loại được khách/nội bộ.")
    return "\n".join(lines)


if __name__ == "__main__":
    print(build())
