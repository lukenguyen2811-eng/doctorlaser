# -*- coding: utf-8 -*-
"""BÁO CÁO ĐIỀU HÀNH v2 (Đợt 1 theo spec BS 17/09/2026).

Khác bản cũ (report.py):
- Ngày lịch 00:00-23:59 (Asia/Ho_Chi_Minh) thay cửa sổ 18h→18h.
- Không tên/SĐT khách trên Telegram — chỉ số tổng hợp + mã lead.
- Tách: lead có số thô / lead hợp lệ / data sạch (đúng tử-mẫu số).
- Số khách duy nhất ≠ số hóa đơn; đếm hóa đơn hủy riêng.
- "Tỷ số DT/chi ads cùng ngày" — ghi rõ KHÔNG phải ROAS quy nguồn.
- CPL quản trị = chi ads ÷ lead hợp lệ CRM quy nguồn (N/A nếu 0).
- Dữ liệu thiếu ghi N/A + khối 🔄 tình trạng dữ liệu + 🚨 cảnh báo stale.
- Lũy kế chỉ tính đến hết D-1.

Module TỰ CHỨA và tương thích Python 3.9 để chạy preview local qua
`railway run python3 report2.py 2026-09-16`. Bot gọi qua lệnh /baocaomoi.
Báo cáo 8h production (report.py) GIỮ NGUYÊN tới khi được duyệt.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict

import requests

SHEET_ID = os.environ.get("CRM_SHEET_ID", "1hEUk7ahzKHO9e656piWiI3L9XWIJqVURQa42eKM7rKA")
KIOT_APP_URL = "https://kiot-production.up.railway.app"
TIKTOK_URL = "https://business-api.tiktok.com/open_mcp/tt-ads-mcp-flat"
TIKTOK_ADV = os.environ.get("TIKTOK_ADVERTISER_ID", "7139812447623446530")
META_ACCT = "act_" + os.environ.get("META_AD_ACCOUNT_ID", "309455834931087").replace("act_", "")

_TRUNG = {"TRÙNG", "SPAM/RÁC", "RÁC"}


def _vnd(x):
    return "{:,.0f}".format(round(x)).replace(",", ".") + "đ"


def _pn(s):
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", (s or "").strip())
    if not m:
        return None
    try:
        return dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def _pdt(s):
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})[ T]+(\d{1,2}):(\d{2})", (s or "").strip())
    if not m:
        return None
    try:
        return dt.datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)),
                           int(m.group(4)), int(m.group(5)))
    except ValueError:
        return None


def _phone(s):
    d = re.sub(r"\D", "", s or "")
    if d.startswith("84") and len(d) >= 11:
        d = "0" + d[2:]
    return d


def _c(r, i):
    return r[i].strip() if len(r) > i else ""


def _norm_nguon(s):
    key = re.sub(r"\s+", " ", (s or "").strip()).lower()
    alias = {"tiktok": "TikTok", "facebook": "Facebook", "fb": "Facebook",
             "zalo": "Zalo", "hotline": "Hotline", "facebook - seo": "Facebook - SEO",
             "fb - seo": "Facebook - SEO", "seo (web / zalo oa)": "SEO (Web/Zalo OA)",
             "seo (web/zalo oa)": "SEO (Web/Zalo OA)", "seo": "SEO (Web/Zalo OA)"}
    if not key:
        return "(không rõ)"
    return alias.get(key, key.title())


# --------------------------------------------------------------------------
# Nguồn dữ liệu (mỗi nguồn lỗi -> trả None, KHÔNG thay bằng 0)
# --------------------------------------------------------------------------

def _sheet():
    import gspread
    from google.oauth2.service_account import Credentials

    info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    return gspread.authorize(creds).open_by_key(SHEET_ID)


def _crm_all(ss):
    out = {}
    for tab in ("LEADS", "QUAN_TAM", "RAC", "LOG"):
        out[tab] = [r for r in ss.worksheet(tab).get_all_values() if any(x.strip() for x in r)]
    return out


def _in_day(r, itg, ingay, day):
    tv = _pdt(_c(r, itg))
    if tv is not None:
        return tv.date() == day
    return _pn(_c(r, ingay)) == day


def _kv_headers():
    tk = requests.post("https://id.kiotviet.vn/connect/token", data={
        "scopes": "PublicApi.Access", "grant_type": "client_credentials",
        "client_id": os.environ["KIOTVIET_CLIENT_ID"],
        "client_secret": os.environ["KIOTVIET_CLIENT_SECRET"]},
        headers={"User-Agent": "Mozilla/5.0"}, timeout=30).json()["access_token"]
    return {"Retailer": os.environ.get("KIOTVIET_RETAILER", ""),
            "Authorization": "Bearer " + tk, "User-Agent": "Mozilla/5.0",
            "Accept": "application/json"}


def _kv_invoices(H, d1, d2):
    base = os.environ.get("KIOTVIET_BASE_URL", "https://public.kiotapi.com")
    items, cur = [], 0
    while True:
        b = requests.get(base + "/invoices", headers=H, params={
            "fromPurchaseDate": "%s 00:00:00" % d1, "toPurchaseDate": "%s 23:59:59" % d2,
            "orderBy": "purchaseDate", "includePayment": "true",
            "pageSize": 100, "currentItem": cur}, timeout=60).json()
        d = b.get("data") or []
        items += d
        cur += 100
        if not d or cur >= b.get("total", 0) or len(items) >= 20000:
            break

    def idate(i):
        try:
            return dt.date.fromisoformat((i.get("purchaseDate") or "")[:10])
        except ValueError:
            return None
    d1d, d2d = dt.date.fromisoformat(d1), dt.date.fromisoformat(d2)
    items = [i for i in items if idate(i) and d1d <= idate(i) <= d2d]
    ok = [i for i in items
          if not (("hủy" in (i.get("statusValue") or "").lower()) or i.get("status") == 2)]
    huy = len(items) - len(ok)
    return ok, huy


def _itien(i):
    det = i.get("invoiceDetails") or []
    if det:
        return sum(float(x.get("subTotal") or 0) for x in det)
    return float(i.get("total") or 0)


def _meta_day(d):
    r = requests.get("https://graph.facebook.com/v21.0/%s/insights" % META_ACCT, params={
        "level": "account", "fields": "spend,actions,clicks,impressions",
        "time_range": json.dumps({"since": str(d), "until": str(d)}),
        "access_token": os.environ["META_ACCESS_TOKEN"]}, timeout=60)
    if r.status_code != 200:
        raise RuntimeError("Meta %s" % r.status_code)
    rows = r.json().get("data") or []
    sp = sum(float(x.get("spend") or 0) for x in rows)
    kq = 0.0
    for x in rows:
        for a in x.get("actions") or []:
            at = a.get("action_type", "")
            if "messaging_conversation_started" in at or at == "lead":
                kq += float(a.get("value") or 0)
    return sp, int(kq)


def _meta_spend(d1, d2):
    r = requests.get("https://graph.facebook.com/v21.0/%s/insights" % META_ACCT, params={
        "level": "account", "fields": "spend",
        "time_range": json.dumps({"since": str(d1), "until": str(d2)}),
        "access_token": os.environ["META_ACCESS_TOKEN"]}, timeout=60)
    if r.status_code != 200:
        raise RuntimeError("Meta %s" % r.status_code)
    return sum(float(x.get("spend") or 0) for x in (r.json().get("data") or []))


class _TT:
    def __init__(self):
        self.rt_days = None
        body = requests.post(TIKTOK_URL + "/oauth/token", data={
            "grant_type": "refresh_token",
            "refresh_token": os.environ["TIKTOK_REFRESH_TOKEN"],
            "client_id": os.environ["TIKTOK_CLIENT_ID"]},
            headers={"Accept": "application/json"}, timeout=30).json()
        self.at = body["access_token"]
        exp = body.get("refresh_token_expires_in")
        if exp:
            self.rt_days = float(exp) / 86400
        self.h = {"Authorization": "Bearer " + self.at,
                  "Content-Type": "application/json",
                  "Accept": "application/json, text/event-stream"}
        self._rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                   "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                              "clientInfo": {"name": "report2", "version": "1"}}})

    def _rpc(self, payload):
        t = requests.post(TIKTOK_URL, data=json.dumps(payload), headers=self.h,
                          timeout=60).text.strip()
        if not t.startswith("{"):
            for ln in t.splitlines():
                if ln.startswith("data:"):
                    t = ln[5:].strip()
                    break
        return json.loads(t)

    def campaigns(self, d1, d2):
        for _ in range(3):
            res = self._rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                             "params": {"name": "report_integrated_get", "arguments": {
                                 "advertiser_id": TIKTOK_ADV, "report_type": "BASIC",
                                 "data_level": "AUCTION_CAMPAIGN",
                                 "dimensions": ["campaign_id"],
                                 "metrics": ["campaign_name", "spend", "conversion",
                                             "cost_per_conversion", "impressions"],
                                 "start_date": str(d1), "end_date": str(d2),
                                 "page_size": 100}}})
            body = json.loads(res["result"]["content"][0]["text"])
            if body.get("code") == 0:
                return (body.get("data") or {}).get("list") or []
            time.sleep(3)
        raise RuntimeError("TikTok code %s" % body.get("code"))


# --------------------------------------------------------------------------
# Dựng báo cáo
# --------------------------------------------------------------------------

def build(day=None):
    """Báo cáo điều hành cho ngày D-1 = `day` (mặc định: hôm qua theo VN)."""
    try:
        from zoneinfo import ZoneInfo
        now = dt.datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).replace(tzinfo=None)
    except Exception:  # noqa: BLE001
        now = dt.datetime.utcnow() + dt.timedelta(hours=7)
    today = now.date()
    D = day or (today - dt.timedelta(days=1))
    first = D.replace(day=1)

    canh_bao = []      # 🚨
    tinh_trang = []    # 🔄

    # ---------- CRM ----------
    crm_err = None
    try:
        ss = _sheet()
        tabs = _crm_all(ss)
    except Exception as e:  # noqa: BLE001
        crm_err = str(e)[:120]
        tabs = None

    L = Q = R = None
    if tabs:
        L = tabs["LEADS"][1:]
        Q = tabs["QUAN_TAM"][1:]
        R = tabs["RAC"][1:]
        # freshness từng tab (dòng mới nhất theo cột giờ)
        for tab, rows, itg in (("LEADS", L, 19), ("QUAN_TAM", Q, 15), ("RAC", R, 7)):
            ts = [_pdt(_c(r, itg)) for r in rows if _pdt(_c(r, itg))]
            last = max(ts) if ts else None
            stale = (not last) or (now - last > dt.timedelta(hours=30))
            tinh_trang.append("  - Chatbot → %s: %s (dòng cuối %s)" % (
                tab, "STALE ⚠️" if stale else "OK",
                last.strftime("%d/%m %H:%M") if last else "?"))
            if stale:
                canh_bao.append(
                    "DATA_STALE: tab %s không có dòng mới từ %s — kiểm tra chatbot/tab đầy "
                    "(phụ trách: Dolly)" % (tab, last.strftime("%d/%m %H:%M") if last else "?"))
        # lỗi ghi trong LOG 24h qua
        errs = [r for r in tabs["LOG"][1:]
                if _pdt(_c(r, 0)) and now - _pdt(_c(r, 0)) <= dt.timedelta(hours=24)]
        if errs:
            canh_bao.append("SYNC_FAILURE: %d lỗi ghi CRM trong 24h (tab LOG, mới nhất %s) "
                            "— phụ trách: Dolly" % (len(errs), _c(errs[-1], 1)))
        tinh_trang.append("  - Nhật ký lỗi 24h (LOG): %s" % ("%d lỗi ⚠️" % len(errs) if errs else "0"))

    # Sự kiện CRM ngày D (ngày lịch), loại DATA CŨ import
    ev = None
    if L is not None:
        def _phễu(r):
            goc = _c(r, 21).upper()
            if goc.startswith("IMPORT") or goc == "TEST":
                return False
            return not _c(r, 2).upper().startswith("DATA CŨ")

        Ld = [r for r in L if _in_day(r, 19, 1, D) and _phễu(r)]
        tho = Ld
        trung = [r for r in Ld if _c(r, 9).upper() in _TRUNG]
        hople = [r for r in Ld if _c(r, 9).upper() not in _TRUNG]
        lead_ma = set(_c(r, 17) for r in Ld if _c(r, 17))
        Qd = [r for r in Q if _in_day(r, 15, 1, D) and not (_c(r, 0) and _c(r, 0) in lead_ma)]
        qm = set(_c(r, 0) for r in Qd if _c(r, 0))
        Rd = [r for r in R if _in_day(r, 7, 1, D)
              and not (_c(r, 0) and (_c(r, 0) in lead_ma or _c(r, 0) in qm))]
        tong = len(tho) + len(Qd) + len(Rd)
        sach = tong - len(trung) - len(Rd)
        ev = {"tong": tong, "tho": len(tho), "hople": len(hople), "trung": trung,
              "rac": len(Rd), "qt": len(Qd), "sach": sach,
              "ma_trung": [(_c(r, 0) or "?") for r in trung]}
        # theo nguồn: tổng data + lead hợp lệ
        src_tot = Counter()
        for rows, i in ((tho, 2), (Qd, 3), (Rd, 2)):
            src_tot.update(_norm_nguon(_c(r, i)) for r in rows)
        src_lead = Counter(_norm_nguon(_c(r, 2)) for r in hople)
        ev["src"] = [(n, t, src_lead.get(n, 0)) for n, t in src_tot.most_common()]
        # Quy nguồn ads: chỉ nguồn "Facebook" (Facebook - SEO là organic, không tính)
        ev["lead_fb"] = src_lead.get("Facebook", 0)
        ev["lead_tt"] = src_lead.get("TikTok", 0)

    # Lũy kế CRM tháng đến hết D
    lk_crm = None
    if L is not None:
        Lm = [r for r in L if _pn(_c(r, 1)) and first <= _pn(_c(r, 1)) <= D
              and _phễu(r)]
        hopleM = [r for r in Lm if _c(r, 9).upper() not in _TRUNG]
        chotM = sum(1 for r in hopleM if "chốt" in _c(r, 9).lower())
        lk_crm = {"hople": len(hopleM), "chot": chotM}

    # ---------- KiotViet ----------
    kv_err = None
    kq_kv = lk_kv = None
    try:
        H = _kv_headers()
        inv, huy = _kv_invoices(H, str(D), str(D))
        rev = sum(_itien(i) for i in inv)
        khach = set(i.get("customerId") for i in inv if i.get("customerId"))
        thucthu = sum(
            sum(float(p.get("amount") or 0) for p in (i.get("payments") or []))
            for i in inv)
        prod = defaultdict(float)
        for i in inv:
            for d0 in i.get("invoiceDetails") or []:
                prod[d0.get("categoryName") or d0.get("productName") or "(khác)"] += \
                    float(d0.get("subTotal") or 0)
        kq_kv = {"rev": rev, "hd": len(inv), "huy": huy, "khach": len(khach),
                 "thucthu": thucthu if thucthu > 0 else None, "prod": prod}
        invM, huyM = _kv_invoices(H, str(first), str(D))
        lk_kv = {"rev": sum(_itien(i) for i in invM), "hd": len(invM),
                 "khach": len(set(i.get("customerId") for i in invM if i.get("customerId")))}
        tinh_trang.append("  - KiotViet API: OK")
    except Exception as e:  # noqa: BLE001
        kv_err = str(e)[:100]
        tinh_trang.append("  - KiotViet API: ERROR ⚠️ (%s)" % kv_err)
        canh_bao.append("SYNC_FAILURE: không đọc được KiotViet (%s) — thử /baocaomoi lại sau" % kv_err)

    # ---------- Ads ----------
    fb = None
    try:
        sp, kq = _meta_day(D)
        spM = _meta_spend(first, D)
        fb = {"spend": sp, "kq": kq, "thang": spM}
        tinh_trang.append("  - Meta Ads API: OK")
    except Exception as e:  # noqa: BLE001
        tinh_trang.append("  - Meta Ads API: ERROR ⚠️ (%s)" % str(e)[:80])

    tt = None
    try:
        t = _TT()
        rows = t.campaigns(D, D)
        conv_sp = view_sp = kq = 0.0
        camp_lines = []
        for it in rows:
            m = it.get("metrics") or {}
            sp = float(m.get("spend") or 0)
            if sp <= 0:
                continue
            name = (m.get("campaign_name") or "?").strip()
            c_ = float(m.get("conversion") or 0)
            if "view" in name.lower():
                view_sp += sp
            else:
                conv_sp += sp
                kq += c_
            camp_lines.append((name, sp, int(c_)))
        rowsM = t.campaigns(first, D)
        spM = sum(float((x.get("metrics") or {}).get("spend") or 0) for x in rowsM)
        tt = {"conv": conv_sp, "view": view_sp, "kq": int(kq), "camp": camp_lines,
              "thang": spM, "rt_days": t.rt_days}
        tinh_trang.append("  - TikTok Ads API: OK")
        if t.rt_days is not None and t.rt_days <= 5:
            canh_bao.append("TikTok cần authorize lại trong %.0f ngày (claude mcp login "
                            "tiktok-ads trên Mac mini) — phụ trách: anh Lương" % max(t.rt_days, 0))
    except Exception as e:  # noqa: BLE001
        tinh_trang.append("  - TikTok Ads API: ERROR ⚠️ (%s)" % str(e)[:80])

    # ---------- Phút gọi của sale (từ KIOT, BS yêu cầu 21/09) ----------
    goi = None
    goi_err = "N/A — chờ KIOT mở endpoint calls-daily"
    tok = os.environ.get("KIOT_INGEST_TOKEN") or os.environ.get("INGEST_TOKEN") or ""
    if tok:
        try:
            r = requests.get(
                "https://kiot-production.up.railway.app/api/ingest/calls-daily",
                headers={"x-ingest-token": tok},
                params={"tu": str(D), "den": str(D)}, timeout=30)
            if r.status_code == 200 and (r.json() or {}).get("ok"):
                goi = r.json().get("theo_nhan_vien") or []
                goi_err = None
            else:
                goi_err = "N/A — KIOT calls-daily trả %s" % r.status_code
        except Exception as e:  # noqa: BLE001
            goi_err = "N/A — lỗi đọc KIOT (%s)" % str(e)[:60]

    # ---------- Lịch hẹn hôm nay (snapshot) ----------
    lich = None
    if tabs:
        try:
            rows = ss.worksheet("ĐẶT LỊCH T%02d" % today.month).get_all_values()[1:]
            chon = {}
            for r in rows:
                if _pn(_c(r, 0)) != today:
                    continue
                p = _phone(_c(r, 3))
                k = p or _c(r, 2).lower()
                if k:
                    chon[k] = r
            gio = Counter()
            sang = chieu = moi = cu = 0
            tvtt = Counter()
            for r in chon.values():
                g = _c(r, 4)
                m = re.match(r"(\d{1,2})", g)
                h = int(m.group(1)) if m else 0
                if h and h < 13:
                    sang += 1
                elif h:
                    chieu += 1
                if h:
                    gio[g] += 1
                dta = _c(r, 8).upper()
                if dta == "NEW":
                    moi += 1
                elif dta:
                    cu += 1
                if _c(r, 7):
                    tvtt[_c(r, 7)] += 1
            qua_tai = [(g, n) for g, n in gio.items() if n >= 3]
            lich = {"tong": len(chon), "sang": sang, "chieu": chieu, "moi": moi,
                    "cu": cu, "qua_tai": qua_tai, "tvtt": tvtt}
        except Exception:  # noqa: BLE001
            lich = None

    # ---------------------------------------------------------------
    # Ghép văn bản
    # ---------------------------------------------------------------
    p = ["📊 BÁO CÁO ĐIỀU HÀNH — %s %s" % (
        ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "CN"][D.weekday()],
        D.strftime("%d/%m/%Y")),
        "Kết quả chốt đến hết: %s 23:59 | Lịch hôm nay cập nhật lúc: %s" % (
            D.strftime("%d/%m"), now.strftime("%H:%M")), ""]

    if canh_bao:
        p.append("🚨 1. VIỆC CẦN XỬ LÝ NGAY")
        for cb in canh_bao:
            p.append("  - " + cb)
        p.append("")

    p.append("💰 2. KINH DOANH NGÀY %s" % D.strftime("%d/%m"))
    if kq_kv:
        p.append("  - Doanh thu gộp (trước VAT): %s" % _vnd(kq_kv["rev"]))
        p.append("  - Hoàn/hủy: %s | Giảm trừ: N/A — chưa có nguồn trả hàng"
                 % ("%d hóa đơn hủy" % kq_kv["huy"] if kq_kv["huy"] else "0"))
        p.append("  - Tiền thực thu (gồm VAT): %s" % (
            _vnd(kq_kv["thucthu"]) if kq_kv["thucthu"] is not None else "N/A"))
        p.append("  - Khách duy nhất có hóa đơn: %d | Số hóa đơn hợp lệ: %d | TB/hóa đơn: %s" % (
            kq_kv["khach"], kq_kv["hd"],
            _vnd(kq_kv["rev"] / kq_kv["hd"]) if kq_kv["hd"] else "N/A"))
        if kq_kv["prod"]:
            top = sorted(kq_kv["prod"].items(), key=lambda x: -x[1])[:5]
            khac = kq_kv["rev"] - sum(v for _, v in top)
            p.append("  - Top dịch vụ:")
            for n, v in top:
                p.append("      • %s: %s (%.0f%%)" % (
                    n, _vnd(v), v / kq_kv["rev"] * 100 if kq_kv["rev"] else 0))
            if khac > 0:
                p.append("      • Khác: %s (%.0f%%)" % (_vnd(khac), khac / kq_kv["rev"] * 100))
    else:
        p.append("  - N/A — KiotViet chưa đọc được (%s)" % (kv_err or "?"))
    p.append("")

    p.append("📢 3. MARKETING NGÀY %s" % D.strftime("%d/%m"))
    if fb:
        p.append("  Facebook: chi %s | KQ nền tảng: %d | Lead hợp lệ CRM: %s | CPL hợp lệ: %s" % (
            _vnd(fb["spend"]), fb["kq"],
            str(ev["lead_fb"]) if ev else "N/A",
            _vnd(fb["spend"] / ev["lead_fb"]) if (ev and ev["lead_fb"]) else "N/A"))
    else:
        p.append("  Facebook: N/A — nguồn chưa đọc được")
    if tt:
        p.append("  TikTok: chi chuyển đổi %s | chi View %s | KQ nền tảng: %d | "
                 "Lead hợp lệ CRM: %s | CPL hợp lệ: %s" % (
                     _vnd(tt["conv"]), _vnd(tt["view"]), tt["kq"],
                     str(ev["lead_tt"]) if ev else "N/A",
                     _vnd(tt["conv"] / ev["lead_tt"]) if (ev and ev["lead_tt"]) else "N/A"))
        for name, sp, c_ in tt["camp"]:
            p.append("      • %s: %s | %d KQ" % (name, _vnd(sp), c_))
    else:
        p.append("  TikTok: N/A — nguồn chưa đọc được")
    if fb and tt and kq_kv:
        tot = fb["spend"] + tt["conv"] + tt["view"]
        p.append("  Tổng chi ads: %s | Tỷ số DT toàn phòng khám/chi ads cùng ngày: %.1f lần" % (
            _vnd(tot), (kq_kv["rev"] / tot) if tot else 0))
        p.append("  ⚠️ Tỷ số trên KHÔNG phải ROAS quy nguồn. ROAS quy nguồn D60: N/A (đợt 3)")
    p.append("")

    p.append("📞 4. CRM — SỰ KIỆN NGÀY %s (00:00–23:59)" % D.strftime("%d/%m"))
    if ev:
        t_ = ev["tong"]
        p.append("  - Tổng data mới: %d | Quan tâm chưa số: %d | Rác: %d | Trùng: %d" % (
            t_, ev["qt"], ev["rac"], len(ev["trung"])))
        p.append("  - Lead có số thô: %d (%s tổng data)" % (
            ev["tho"], "%.0f%%" % (ev["tho"] / t_ * 100) if t_ else "N/A"))
        p.append("  - Lead hợp lệ: %d (%s tổng data | %s data sạch)" % (
            ev["hople"],
            "%.0f%%" % (ev["hople"] / t_ * 100) if t_ else "N/A",
            "%.1f%%" % (ev["hople"] / ev["sach"] * 100) if ev["sach"] else "N/A"))
        if ev["ma_trung"]:
            p.append("  - Mã lead trùng/rác (xem chi tiết trong KIOT): %s" %
                     ", ".join(ev["ma_trung"][:10]))
        if ev["src"]:
            p.append("  - Theo nguồn (tổng data | lead hợp lệ):")
            for n, t2, l2 in ev["src"]:
                p.append("      • %s: %d | %d" % (n, t2, l2))
        p.append("  Ghi chú: số trên là SỰ KIỆN trong ngày từ nhiều cohort — "
                 "không chia cho nhau để tính conversion.")
    else:
        p.append("  - N/A — CRM chưa đọc được (%s)" % (crm_err or "?"))
    p.append("")

    p.append("☎️ GỌI CỦA SALE NGÀY %s (Zalo + tổng đài)" % D.strftime("%d/%m"))
    if goi is not None:
        if not goi:
            p.append("  - 0 cuộc gọi được ghi nhận")
        else:
            tong = {}
            for x in goi:
                nv = x.get("nhan_vien") or "?"
                t = tong.setdefault(nv, [0, 0, 0.0])
                t[0] += int(x.get("so_cuoc") or 0)
                t[1] += int(x.get("so_bat_may") or 0)
                t[2] += float(x.get("tong_giay") or 0)
            tc = sum(v[0] for v in tong.values())
            tp = sum(v[2] for v in tong.values()) / 60
            p.append("  - Tổng: %d cuộc | %.0f phút" % (tc, tp))
            for nv, (sc, bm, gy) in sorted(tong.items(), key=lambda x: -x[1][2]):
                p.append("      • %s: %d cuộc (bắt máy %d) | %.0f phút" % (nv, sc, bm, gy / 60))
    else:
        p.append("  - %s" % goi_err)
    p.append("")

    if lich is not None:
        p.append("🗓 5. LỊCH HẸN HÔM NAY %s (snapshot %s)" % (
            today.strftime("%d/%m"), now.strftime("%H:%M")))
        p.append("  - Tổng lịch: %d | Sáng: %d | Chiều: %d" % (
            lich["tong"], lich["sang"], lich["chieu"]))
        p.append("  - Khách mới: %d | Khách cũ/tái khám: %d | Chưa phân loại: %d" % (
            lich["moi"], lich["cu"], lich["tong"] - lich["moi"] - lich["cu"]))
        p.append("  - Đã/chưa xác nhận: N/A — tab chưa có cột xác nhận")
        if lich["qua_tai"]:
            p.append("  - Khung giờ quá tải (≥3 lịch): %s" %
                     ", ".join("%s (%d)" % (g, n) for g, n in lich["qua_tai"]))
        if lich["tvtt"]:
            p.append("  - Theo TVTT: %s" %
                     ", ".join("%s %d" % (k, v) for k, v in lich["tvtt"].most_common()))
        p.append("  Chi tiết (tên/dịch vụ) xem trong KIOT: %s/#/appointments" % KIOT_APP_URL)
        p.append("")

    p.append("📅 6. LŨY KẾ THÁNG %d — ĐẾN HẾT %s" % (D.month, D.strftime("%d/%m")))
    if lk_kv:
        p.append("  - Doanh thu gộp: %s | Khách duy nhất: %d | Hóa đơn: %d" % (
            _vnd(lk_kv["rev"]), lk_kv["khach"], lk_kv["hd"]))
    else:
        p.append("  - Doanh thu: N/A — KiotViet chưa đọc được")
    p.append("  - So với mục tiêu tháng: %s" % (
        "%.0f%%" % (lk_kv["rev"] / float(os.environ["MONTHLY_TARGET"]) * 100)
        if (lk_kv and os.environ.get("MONTHLY_TARGET")) else "N/A — chưa đặt mục tiêu"))
    if fb and tt and lk_kv:
        ads_m = fb["thang"] + tt["thang"]
        p.append("  - Tổng chi ads: %s (FB %s + TikTok %s) — %.1f%% doanh thu" % (
            _vnd(ads_m), _vnd(fb["thang"]), _vnd(tt["thang"]),
            ads_m / lk_kv["rev"] * 100 if lk_kv["rev"] else 0))
    else:
        p.append("  - Tổng chi ads: N/A — thiếu nguồn ads")
    if lk_crm:
        p.append("  - Lead hợp lệ: %d | Chốt (bot đối chiếu hóa đơn): %d (%s)" % (
            lk_crm["hople"], lk_crm["chot"],
            "%.0f%%" % (lk_crm["chot"] / lk_crm["hople"] * 100) if lk_crm["hople"] else "N/A"))
    p.append("")

    p.append("🔄 7. TÌNH TRẠNG DỮ LIỆU")
    p += tinh_trang
    if tt and tt.get("rt_days") is not None:
        p.append("  - TikTok token: còn %.0f ngày tới hạn authorize lại" % tt["rt_days"])
    return "\n".join(p)


if __name__ == "__main__":
    d = dt.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else None
    print(build(d))
