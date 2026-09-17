# -*- coding: utf-8 -*-
"""Phễu COHORT theo tuần (mục 5 spec báo cáo 17/09) — gửi sáng thứ 6 + /cohort.

Cohort = hội thoại có nhu cầu (tab QUAN_TAM), gắn theo NGÀY INBOUND ĐẦU TIÊN
(tuần Thứ 2 → Chủ nhật). Mọi sự kiện sau đó quy ngược về cohort gốc:
- Có số D7   : hội thoại xuất hiện ở LEADS (Gốc lead CHAT/MANUAL) trong 7 ngày
- Đặt lịch D14: SĐT của lead xuất hiện trong tab ĐẶT LỊCH trong 14 ngày
- Hóa đơn D30 : SĐT có hóa đơn KiotViet hợp lệ trong 30 ngày
- Doanh thu D60: tổng tiền hàng các hóa đơn trong 60 ngày
Cửa sổ chưa đủ thời gian quan sát ghi "chưa đủ cửa sổ" — không kết luận.
Mẫu <20 ghi chú "mẫu nhỏ". Không tên/SĐT khách trong báo cáo.

Tự chứa, tương thích Python 3.9 (chạy được local qua railway run để kiểm).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
from collections import defaultdict

import requests

SHEET_ID = os.environ.get("CRM_SHEET_ID", "1hEUk7ahzKHO9e656piWiI3L9XWIJqVURQa42eKM7rKA")
SO_TUAN = 8


def _pn(s):
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", (s or "").strip())
    if not m:
        return None
    try:
        return dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def _ph(s):
    d = re.sub(r"\D", "", s or "")
    if d.startswith("84") and len(d) >= 11:
        d = "0" + d[2:]
    return d


def _c(r, i):
    return r[i].strip() if len(r) > i else ""


def build() -> str:
    try:
        from zoneinfo import ZoneInfo
        today = dt.datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()
    except Exception:  # noqa: BLE001
        today = (dt.datetime.utcnow() + dt.timedelta(hours=7)).date()

    import gspread
    from google.oauth2.service_account import Credentials

    info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    ss = gspread.authorize(creds).open_by_key(SHEET_ID)

    Q = [r for r in ss.worksheet("QUAN_TAM").get_all_values()[1:] if any(x.strip() for x in r)]
    L = [r for r in ss.worksheet("LEADS").get_all_values()[1:] if any(x.strip() for x in r)]
    dl_by_phone = defaultdict(list)
    for tab in ("ĐẶT LỊCH T07", "ĐẶT LỊCH T08", "ĐẶT LỊCH T09",
                "ĐẶT LỊCH T%02d" % today.month):
        try:
            rows = ss.worksheet(tab).get_all_values()[1:]
        except Exception:  # noqa: BLE001
            continue
        for r in rows:
            d = _pn(_c(r, 0))
            p = _ph(_c(r, 3))
            if d and len(p) >= 9:
                dl_by_phone[p].append(d)

    lead_by_ma = {}
    for r in L:
        if _c(r, 21).upper() not in ("CHAT", "MANUAL"):
            continue
        ma, d, p = _c(r, 17), _pn(_c(r, 1)), _ph(_c(r, 3))
        if ma and d and ma not in lead_by_ma:
            lead_by_ma[ma] = (d, p)

    # KiotViet: SĐT -> [(ngày hóa đơn, tiền)] từ 8 tuần + 60 ngày trước
    tk = requests.post("https://id.kiotviet.vn/connect/token", data={
        "scopes": "PublicApi.Access", "grant_type": "client_credentials",
        "client_id": os.environ["KIOTVIET_CLIENT_ID"],
        "client_secret": os.environ["KIOTVIET_CLIENT_SECRET"]},
        headers={"User-Agent": "Mozilla/5.0"}, timeout=30).json()["access_token"]
    H = {"Retailer": os.environ.get("KIOTVIET_RETAILER", ""),
         "Authorization": "Bearer " + tk, "User-Agent": "Mozilla/5.0"}
    base = os.environ.get("KIOTVIET_BASE_URL", "https://public.kiotapi.com")

    def getall(path, params):
        items, cur = [], 0
        while True:
            pr = dict(params)
            pr["pageSize"] = 100
            pr["currentItem"] = cur
            b = requests.get(base + path, headers=H, params=pr, timeout=60).json()
            d = b.get("data") or []
            items += d
            cur += 100
            if not d or cur >= b.get("total", 0) or len(items) >= 25000:
                break
        return items

    tu = today - dt.timedelta(weeks=SO_TUAN, days=today.weekday())
    inv = getall("/invoices", {"fromPurchaseDate": "%s 00:00:00" % tu,
                               "toPurchaseDate": "%s 23:59:59" % today,
                               "orderBy": "purchaseDate"})

    def idate(i):
        try:
            return dt.date.fromisoformat((i.get("purchaseDate") or "")[:10])
        except ValueError:
            return None
    inv = [i for i in inv if idate(i)
           and not (("hủy" in (i.get("statusValue") or "").lower()) or i.get("status") == 2)]
    cust = getall("/customers", {"orderBy": "createdDate", "orderDirection": "Desc"})
    id2ph = {cc.get("id"): _ph(cc.get("contactNumber") or "") for cc in cust}
    inv_by_phone = defaultdict(list)
    for i in inv:
        p = id2ph.get(i.get("customerId") or 0, "")
        if len(p) >= 9:
            det = i.get("invoiceDetails") or []
            t = sum(float(x.get("subTotal") or 0) for x in det) if det \
                else float(i.get("total") or 0)
            inv_by_phone[p].append((idate(i), t))

    first = {}
    for r in Q:
        ma, d = _c(r, 0), _pn(_c(r, 1))
        if ma and d and (ma not in first or d < first[ma]):
            first[ma] = d

    # 8 tuần T2→CN gần nhất đã kết thúc
    mon_this = today - dt.timedelta(days=today.weekday())
    lines = ["📈 PHỄU COHORT THEO TUẦN (đến %s)" % today.strftime("%d/%m"),
             "Cohort = hội thoại có nhu cầu, gắn theo tuần inbound đầu tiên.", ""]
    for k in range(SO_TUAN, 0, -1):
        ws_ = mon_this - dt.timedelta(weeks=k)
        we = ws_ + dt.timedelta(days=6)
        mas = [m for m, d in first.items() if ws_ <= d <= we]
        N = len(mas)

        def du(days):
            return we + dt.timedelta(days=days) <= today
        so = dl_ = hd = hd60 = 0
        dt60 = 0.0
        for m in mas:
            d0 = first[m]
            lp = lead_by_ma.get(m)
            if lp and (lp[0] - d0).days <= 7:
                so += 1
            p = lp[1] if lp else ""
            if p:
                if any(d0 <= dd <= d0 + dt.timedelta(days=14)
                       for dd in dl_by_phone.get(p, [])):
                    dl_ += 1
                if any(d0 <= dd <= d0 + dt.timedelta(days=30)
                       for dd, _ in inv_by_phone.get(p, [])):
                    hd += 1
                s60 = sum(t for dd, t in inv_by_phone.get(p, [])
                          if d0 <= dd <= d0 + dt.timedelta(days=60))
                if s60 > 0:
                    hd60 += 1
                dt60 += s60

        def f(v, days):
            if not du(days):
                return "—"
            return "%d (%.0f%%)" % (v, v / N * 100) if N else "0"
        row = "%s–%s: %d hội thoại | số D7: %s | lịch D14: %s | HĐ D30: %s" % (
            ws_.strftime("%d/%m"), we.strftime("%d/%m"), N,
            f(so, 7), f(dl_, 14), f(hd, 30))
        if du(60):
            row += " | DT D60: %.1ftr (%d KH)" % (dt60 / 1e6, hd60)
        else:
            row += " | DT D60: —"
        if N and N < 20:
            row += "  (mẫu nhỏ)"
        lines.append(row)
    lines.append("")
    lines.append("Ghi chú: '—' = chưa đủ cửa sổ quan sát, không kết luận. "
                 "'Lịch D14' khớp SĐT với tab ĐẶT LỊCH — số ghi thiếu SĐT sẽ bị sót "
                 "(sẽ chính xác hơn khi lấy lịch từ KIOT, đợt 3).")
    return "\n".join(lines)


if __name__ == "__main__":
    print(build())
