# -*- coding: utf-8 -*-
"""Đẩy chi phí quảng cáo THEO NGÀY sang KIOT (/api/ingest/ads-daily).

BS duyệt 19/09 (phương án A): bot báo cáo là nguồn số ads, KIOT là nơi lưu
dùng chung để Dolly tính ROI theo dịch vụ. Mỗi sáng đẩy lại 7 ngày gần nhất
(nền tảng còn điều chỉnh chi tiêu), thay_ca_ngay=true để KIOT thay trọn ảnh
chụp từng (ngày, kênh) — quảng cáo đổi tên/tắt không để dòng mồ côi.

Độ hạt: TikTok mức NHÓM QC (adgroup) / Meta mức MẪU QC (ad). Gồm cả nhóm
"View" 0 kết quả để tính đủ tiền. Không có thông tin khách hàng trong feed.

Tự chứa, Python 3.9-safe. CLI:  python3 adsfeed.py [backfill|N_ngày]
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import time

import requests

KIOT_URL = "https://kiot-production.up.railway.app/api/ingest/ads-daily"
TIKTOK_URL = "https://business-api.tiktok.com/open_mcp/tt-ads-mcp-flat"
TIKTOK_ADV = os.environ.get("TIKTOK_ADVERTISER_ID", "7139812447623446530")
META_ACCT = "act_" + os.environ.get("META_AD_ACCOUNT_ID", "309455834931087").replace("act_", "")
BACKFILL_TU = dt.date(2026, 8, 20)

_DV = (("fil", "filler"), ("sẹo", "sẹo"), ("seo", "sẹo"), ("nám", "nám"),
       ("lift", "laserlift"), ("vein", "vein"), ("mồ hôi", "mồ hôi"), ("mụn", "mụn"))


def _dich_vu(*names):
    for n in names:
        low = (n or "").lower()
        for k, v in _DV:
            if k in low:
                return v
    return "khac"


def _meta_rows(d1, d2):
    """Mức MẪU QC (ad), tách ngày bằng time_increment=1."""
    rows, url = [], "https://graph.facebook.com/v21.0/%s/insights" % META_ACCT
    params = {
        "level": "ad",
        "fields": "campaign_name,adset_name,ad_name,spend,actions",
        "time_range": json.dumps({"since": str(d1), "until": str(d2)}),
        "time_increment": 1, "limit": 200,
        "access_token": os.environ["META_ACCESS_TOKEN"],
    }
    r = requests.get(url, params=params, timeout=90)
    if r.status_code != 200:
        raise RuntimeError("Meta %s: %s" % (r.status_code, r.text[:120]))
    body = r.json()
    data = body.get("data") or []
    guard = 0
    while body.get("paging", {}).get("next") and guard < 50:
        guard += 1
        r = requests.get(body["paging"]["next"], timeout=90)
        if r.status_code != 200:
            break
        body = r.json()
        data += body.get("data") or []
    for x in data:
        sp = float(x.get("spend") or 0)
        if sp <= 0:
            continue
        kq = 0.0
        for a in x.get("actions") or []:
            at = a.get("action_type", "")
            if "messaging_conversation_started" in at or at == "lead":
                kq += float(a.get("value") or 0)
        rows.append({
            "ngay": x.get("date_start"), "kenh": "meta",
            "chien_dich": (x.get("campaign_name") or "?")[:120],
            "nhom_qc": (x.get("adset_name") or "?")[:120],
            "mau_qc": (x.get("ad_name") or "?")[:120],
            "dich_vu": _dich_vu(x.get("ad_name"), x.get("adset_name"),
                                x.get("campaign_name")),
            "chi_tieu": round(sp), "ket_qua_nen_tang": int(kq),
        })
    return rows


def _tiktok_rows(d1, d2):
    """Mức NHÓM QC (adgroup), dimension stat_time_day để tách ngày."""
    body = requests.post(TIKTOK_URL + "/oauth/token", data={
        "grant_type": "refresh_token",
        "refresh_token": os.environ["TIKTOK_REFRESH_TOKEN"],
        "client_id": os.environ["TIKTOK_CLIENT_ID"]},
        headers={"Accept": "application/json"}, timeout=30).json()
    h = {"Authorization": "Bearer " + body["access_token"],
         "Content-Type": "application/json",
         "Accept": "application/json, text/event-stream"}

    def rpc(payload):
        t = requests.post(TIKTOK_URL, data=json.dumps(payload), headers=h,
                          timeout=90).text.strip()
        if not t.startswith("{"):
            for ln in t.splitlines():
                if ln.startswith("data:"):
                    t = ln[5:].strip()
                    break
        return json.loads(t)

    rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                    "clientInfo": {"name": "adsfeed", "version": "1"}}})
    out, page = [], 1
    while True:
        for _ in range(3):
            res = rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                       "params": {"name": "report_integrated_get", "arguments": {
                           "advertiser_id": TIKTOK_ADV, "report_type": "BASIC",
                           "data_level": "AUCTION_ADGROUP",
                           "dimensions": ["adgroup_id", "stat_time_day"],
                           "metrics": ["campaign_name", "adgroup_name", "spend",
                                       "conversion"],
                           "start_date": str(d1), "end_date": str(d2),
                           "page": page, "page_size": 200}}})
            b = json.loads(res["result"]["content"][0]["text"])
            if b.get("code") == 0:
                break
            time.sleep(3)
        if b.get("code") != 0:
            raise RuntimeError("TikTok code %s" % b.get("code"))
        data = b.get("data") or {}
        for it in data.get("list") or []:
            m = it.get("metrics") or {}
            sp = float(m.get("spend") or 0)
            if sp <= 0:
                continue
            ngay = ((it.get("dimensions") or {}).get("stat_time_day") or "")[:10]
            out.append({
                "ngay": ngay, "kenh": "tiktok",
                "chien_dich": (m.get("campaign_name") or "?")[:120],
                "nhom_qc": (m.get("adgroup_name") or "?")[:120],
                "mau_qc": "",
                "dich_vu": _dich_vu(m.get("adgroup_name"), m.get("campaign_name")),
                "chi_tieu": round(sp),
                "ket_qua_nen_tang": int(float(m.get("conversion") or 0)),
            })
        info = data.get("page_info") or {}
        if page >= int(info.get("total_page") or 1):
            break
        page += 1
    return out


def _token():
    tok = os.environ.get("KIOT_INGEST_TOKEN") or os.environ.get("INGEST_TOKEN") or ""
    if not tok:
        raise RuntimeError("Thiếu KIOT_INGEST_TOKEN trên Railway")
    return tok


def push(so_ngay=7, den=None):
    """Đẩy `so_ngay` ngày gần nhất (đến hết hôm qua) sang KIOT. Trả tóm tắt."""
    try:
        from zoneinfo import ZoneInfo
        today = dt.datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()
    except Exception:  # noqa: BLE001
        today = (dt.datetime.utcnow() + dt.timedelta(hours=7)).date()
    d2 = den or (today - dt.timedelta(days=1))
    d1 = max(d2 - dt.timedelta(days=so_ngay - 1), BACKFILL_TU)

    dong = _meta_rows(d1, d2) + _tiktok_rows(d1, d2)
    if not dong:
        return "adsfeed: không có dòng chi tiêu %s → %s" % (d1, d2)
    r = requests.post(KIOT_URL, headers={
        "x-ingest-token": _token(), "Content-Type": "application/json"},
        json={"thay_ca_ngay": True, "dong": dong}, timeout=120)
    if r.status_code != 200:
        raise RuntimeError("KIOT ads-daily lỗi %s: %s" % (r.status_code, r.text[:200]))
    tong = sum(x["chi_tieu"] for x in dong)
    return ("📤 adsfeed → KIOT: %d dòng (%s → %s), tổng chi %s | KIOT: %s"
            % (len(dong), d1.strftime("%d/%m"), d2.strftime("%d/%m"),
               "{:,.0f}đ".format(tong).replace(",", "."), r.text[:120]))


def kiem_tra(tu, den):
    r = requests.get(KIOT_URL, headers={"x-ingest-token": _token()},
                     params={"tu": str(tu), "den": str(den)}, timeout=60)
    return "GET %s→%s: %s %s" % (tu, den, r.status_code, r.text[:400])


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "7"
    if arg == "backfill":
        try:
            from zoneinfo import ZoneInfo
            hom_qua = dt.datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date() - dt.timedelta(days=1)
        except Exception:  # noqa: BLE001
            hom_qua = (dt.datetime.utcnow() + dt.timedelta(hours=7)).date() - dt.timedelta(days=1)
        n = (hom_qua - BACKFILL_TU).days + 1
        print(push(so_ngay=n))
        print(kiem_tra(BACKFILL_TU, hom_qua))
    else:
        print(push(so_ngay=int(arg)))
