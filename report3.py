# -*- coding: utf-8 -*-
"""BÁO CÁO ĐIỀU HÀNH v3 — đọc thẳng app KIOT (BS duyệt 23/10/2026).

Khác v2:
- Ngày báo cáo = NGÀY KINH DOANH của KIOT: 17:30 hôm trước → 17:29 hôm nay.
- Sáng THỨ 2 gộp thứ 7 + chủ nhật (17:30 thứ 6 → 17:29 chủ nhật).
- CRM (data/lead/quan tâm/rác) và lịch hẹn lấy từ KIOT /api/ingest/bao-cao-ngay
  (KIOT là nguồn gốc từ 07/09; Sheet chỉ là gương và gương đang lỗi).
- Doanh thu: KiotViet vẫn là GỐC (sửa tiền sau ngày bên KV không về KIOT);
  KIOT dùng để đối chiếu — lệch thì cảnh báo.
- Chi ads Meta/TikTok chỉ có theo NGÀY LỊCH: lấy các ngày lịch tu..den.

Văn bản giữ đúng nhãn của v2 để report_image vẽ được. Không tên/SĐT khách.
Tương thích Python 3.9:  python3 report3.py 2026-10-22 [2026-10-22]
"""
from __future__ import annotations

import datetime as dt
import os
import sys

import requests

import report2 as r2

KIOT = "https://kiot-production.up.railway.app"


def _now():
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).replace(tzinfo=None)
    except Exception:  # noqa: BLE001
        return dt.datetime.utcnow() + dt.timedelta(hours=7)


def ky_mac_dinh(today=None):
    """Kỳ cho báo cáo 8h sáng: hôm qua; thứ 2 thì gộp T7 + CN."""
    today = today or _now().date()
    den = today - dt.timedelta(days=1)
    tu = today - dt.timedelta(days=2) if today.weekday() == 0 else den
    return tu, den


def _tok():
    return os.environ.get("KIOT_INGEST_TOKEN") or os.environ.get("INGEST_TOKEN") or ""


def kiot_bcn(tu, den):
    r = requests.get(KIOT + "/api/ingest/bao-cao-ngay", headers={"x-ingest-token": _tok()},
                     params={"tu": str(tu), "den": str(den)}, timeout=60)
    if r.status_code != 200 or not (r.json() or {}).get("ok"):
        raise RuntimeError("KIOT bao-cao-ngay trả %s" % r.status_code)
    return r.json()


def kv_kd(H, tu, den):
    """Hóa đơn KiotViet hợp lệ trong cửa sổ KD [tu-1 17:30, den 17:29:59]."""
    t1 = dt.datetime.combine(tu - dt.timedelta(days=1), dt.time(17, 30))
    t2 = dt.datetime.combine(den, dt.time(17, 29, 59))
    base = os.environ.get("KIOTVIET_BASE_URL", "https://public.kiotapi.com")
    items, cur = [], 0
    while True:
        b = requests.get(base + "/invoices", headers=H, params={
            "fromPurchaseDate": t1.strftime("%Y-%m-%d 00:00:00"),
            "toPurchaseDate": t2.strftime("%Y-%m-%d 23:59:59"),
            "includePayment": "true", "pageSize": 100, "currentItem": cur}, timeout=60).json()
        d = b.get("data") or []
        items += d
        cur += 100
        if not d or cur >= b.get("total", 0) or len(items) >= 20000:
            break

    def pt(i):
        try:
            return dt.datetime.fromisoformat((i.get("purchaseDate") or "")[:19])
        except ValueError:
            return None
    w = [i for i in items if pt(i) and t1 <= pt(i) <= t2]
    ok = [i for i in w if not (("hủy" in (i.get("statusValue") or "").lower()) or i.get("status") == 2)]
    huy = [i for i in w if i not in ok]
    prod = {}
    for i in ok:
        for x in i.get("invoiceDetails") or []:
            k = x.get("categoryName") or x.get("productName") or "(khác)"
            prod[k] = prod.get(k, 0.0) + float(x.get("subTotal") or 0)
    return {
        "hd": len(ok), "huy": len(huy), "gia_tri_huy": sum(float(i.get("total") or 0) for i in huy),
        "rev": sum(r2._itien(i) for i in ok),
        "thucthu": sum(float(i.get("totalPayment") or 0) for i in ok),
        "khach": len(set(i.get("customerId") for i in ok if i.get("customerId"))),
        "prod": prod,
    }


def _meta_range(d1, d2):
    import json
    r = requests.get("https://graph.facebook.com/v21.0/%s/insights" % r2.META_ACCT, params={
        "level": "account", "fields": "spend,actions",
        "time_range": json.dumps({"since": str(d1), "until": str(d2)}),
        "access_token": os.environ["META_ACCESS_TOKEN"]}, timeout=60)
    if r.status_code != 200:
        raise RuntimeError("Meta %s" % r.status_code)
    sp = kq = 0.0
    for x in r.json().get("data") or []:
        sp += float(x.get("spend") or 0)
        for a in x.get("actions") or []:
            at = a.get("action_type", "")
            if "messaging_conversation_started" in at or at == "lead":
                kq += float(a.get("value") or 0)
    return sp, int(kq)


def _sale(tu, den):
    r = requests.get(KIOT + "/api/ingest/sale-daily", headers={"x-ingest-token": _tok()},
                     params={"tu": str(tu), "den": str(den)}, timeout=30)
    if r.status_code != 200 or not (r.json() or {}).get("ok"):
        raise RuntimeError("sale-daily %s" % r.status_code)
    gop = {}
    for x in r.json().get("rows") or []:
        nv = x.get("nhan_vien") or "?"
        t = gop.setdefault(nv, {"khach": 0, "phut": 0.0, "cuoc": 0, "bm": 0, "lead": 0,
                                "lich": 0, "zalo": 0.0, "bulk": 0})
        t["khach"] += int(x.get("so_khach_tuong_tac") or 0)
        t["phut"] += float(x.get("phut_talktime_khach") or 0)
        t["cuoc"] += int(x.get("so_cuoc_khach") or 0)
        t["bm"] += int(x.get("so_bat_may") or 0)
        t["lead"] += int(x.get("so_lead_cap_nhat") or 0)
        t["lich"] += int(x.get("so_lich_tao") or 0)
        t["zalo"] += float((x.get("zalo_khong_ro_khach") or {}).get("phut") or 0)
        t["bulk"] += int(x.get("so_thao_tac_hang_loat") or 0) + int(x.get("so_doi_trang_thai_don_le") or 0)
    return gop


def _ten_ky(tu, den):
    th = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "CN"]
    if tu == den:
        return "%s %s" % (th[den.weekday()], den.strftime("%d/%m/%Y"))
    return "%s–%s %s–%s" % (th[tu.weekday()], th[den.weekday()],
                            tu.strftime("%d"), den.strftime("%d/%m/%Y"))


def _pct(a, b):
    return "%.0f%%" % (a * 100.0 / b) if b else "N/A"


def build(tu=None, den=None):
    now = _now()
    if tu is None:
        tu, den = ky_mac_dinh(now.date())
    den = den or tu
    first = den.replace(day=1)
    canh_bao, tinh_trang = [], []

    # ---------- KIOT (CRM, lịch, kết quả, đối chiếu doanh thu) ----------
    bcn = lk = None
    try:
        bcn = kiot_bcn(tu, den)
        lk = kiot_bcn(first, den)
        db = bcn.get("dong_bo") or {}
        kvt, ldt = db.get("kv_tuoi_phut"), db.get("lead_tuoi_phut")
        tinh_trang.append("  - KIOT bao-cao-ngay: OK (KiotViet→KIOT đồng bộ %s phút trước, lead mới nhất %s phút)"
                          % (kvt, ldt))
        if db.get("kvLastSyncError"):
            canh_bao.append("SYNC_FAILURE: KiotViet→KIOT lỗi: %s — phụ trách: Dolly" % str(db["kvLastSyncError"])[:80])
        if kvt is not None and kvt > 60:
            canh_bao.append("DATA_STALE: KiotViet→KIOT chưa đồng bộ %s phút — phụ trách: Dolly" % kvt)
        if ldt is not None and ldt > 12 * 60:
            canh_bao.append("DATA_STALE: KIOT không có lead mới %s giờ — kiểm tra chatbot (Dolly)" % (ldt // 60))
    except Exception as e:  # noqa: BLE001
        tinh_trang.append("  - KIOT bao-cao-ngay: ERROR ⚠️ (%s)" % str(e)[:80])
        canh_bao.append("SYNC_FAILURE: không đọc được KIOT (%s) — CRM/lịch hẹn N/A" % str(e)[:60])

    # ---------- KiotViet (doanh thu gốc) ----------
    kv = kvm = None
    try:
        H = r2._kv_headers()
        kv = kv_kd(H, tu, den)
        kvm = kv_kd(H, first, den)
        tinh_trang.append("  - KiotViet API: OK")
        if bcn:
            dk = bcn.get("doanh_thu") or {}
            lech = abs(float(dk.get("tong_gia_tri_don") or 0) - kv["rev"])
            if dk.get("so_hd_hop_le") != kv["hd"] or lech >= 1000:
                canh_bao.append("Chênh lệch doanh thu KIOT–KiotViet: KIOT %s / %s HĐ vs KiotViet %s / %s HĐ "
                                "— kiểm đồng bộ (Dolly)" % (r2._vnd(float(dk.get("tong_gia_tri_don") or 0)),
                                                         dk.get("so_hd_hop_le"), r2._vnd(kv["rev"]), kv["hd"]))
    except Exception as e:  # noqa: BLE001
        tinh_trang.append("  - KiotViet API: ERROR ⚠️ (%s)" % str(e)[:80])
        canh_bao.append("SYNC_FAILURE: không đọc được KiotViet (%s)" % str(e)[:60])

    # ---------- Ads (theo ngày lịch tu..den) ----------
    fb = tt = None
    try:
        sp, kq = _meta_range(tu, den)
        fb = {"spend": sp, "kq": kq, "thang": r2._meta_spend(first, den)}
        tinh_trang.append("  - Meta Ads API: OK")
    except Exception as e:  # noqa: BLE001
        tinh_trang.append("  - Meta Ads API: ERROR ⚠️ (%s)" % str(e)[:80])
    try:
        t = r2._TT()
        conv = view = kq = 0.0
        camp = []
        for it in t.campaigns(tu, den):
            m = it.get("metrics") or {}
            sp = float(m.get("spend") or 0)
            if sp <= 0:
                continue
            name = (m.get("campaign_name") or "?").strip()
            c_ = float(m.get("conversion") or 0)
            if "view" in name.lower():
                view += sp
            else:
                conv += sp
                kq += c_
            camp.append((name, sp, int(c_)))
        spm = sum(float((x.get("metrics") or {}).get("spend") or 0) for x in t.campaigns(first, den))
        tt = {"conv": conv, "view": view, "kq": int(kq), "camp": camp, "thang": spm, "rt": t.rt_days}
        tinh_trang.append("  - TikTok Ads API: OK")
        if t.rt_days is not None and t.rt_days <= 5:
            canh_bao.append("TikTok cần authorize lại trong %.0f ngày (claude mcp login tiktok-ads "
                            "trên Mac mini) — phụ trách: anh Lương" % max(t.rt_days, 0))
    except Exception as e:  # noqa: BLE001
        tinh_trang.append("  - TikTok Ads API: ERROR ⚠️ (%s)" % str(e)[:80])

    sale = None
    try:
        sale = _sale(tu, den)
    except Exception:  # noqa: BLE001
        sale = None

    # =============================================================== văn bản
    t1 = dt.datetime.combine(tu - dt.timedelta(days=1), dt.time(17, 30))
    p = ["📊 BÁO CÁO ĐIỀU HÀNH — %s" % _ten_ky(tu, den),
         "Ngày kinh doanh: %s → 17:29 %s | Lịch hôm nay cập nhật lúc: %s" % (
             t1.strftime("17:30 %d/%m"), den.strftime("%d/%m"), now.strftime("%H:%M")), ""]
    if canh_bao:
        p.append("🚨 1. VIỆC CẦN XỬ LÝ NGAY")
        p += ["  - " + c for c in canh_bao]
        p.append("")

    p.append("💰 2. KINH DOANH (doanh thu gốc KiotViet)")
    if kv:
        p.append("  - Doanh thu gộp (trước VAT): %s" % r2._vnd(kv["rev"]))
        p.append("  - Hoàn/hủy: %s | Giảm trừ: N/A — chưa có nguồn trả hàng" % (
            "%d hóa đơn hủy (%s)" % (kv["huy"], r2._vnd(kv["gia_tri_huy"])) if kv["huy"] else "0"))
        p.append("  - Tiền thực thu (gồm VAT): %s" % r2._vnd(kv["thucthu"]))
        p.append("  - Khách duy nhất có hóa đơn: %d | Số hóa đơn hợp lệ: %d | TB/hóa đơn: %s" % (
            kv["khach"], kv["hd"], r2._vnd(kv["rev"] / kv["hd"]) if kv["hd"] else "N/A"))
        if bcn:
            dk = bcn["doanh_thu"]
            p.append("  - Khách mới/cũ có hóa đơn (KIOT): %s/%s | Đối chiếu KIOT: %s" % (
                dk.get("khach_moi"), dk.get("khach_cu"),
                "khớp ✓" if dk.get("so_hd_hop_le") == kv["hd"]
                and abs(float(dk.get("tong_gia_tri_don") or 0) - kv["rev"]) < 1000 else "LỆCH ⚠️"))
        if kv["prod"]:
            top = sorted(kv["prod"].items(), key=lambda x: -x[1])[:5]
            khac = kv["rev"] - sum(v for _, v in top)
            p.append("  - Top dịch vụ:")
            for n, v in top:
                p.append("      • %s: %s (%.0f%%)" % (n, r2._vnd(v), v / kv["rev"] * 100 if kv["rev"] else 0))
            if khac > 0:
                p.append("      • Khác: %s (%.0f%%)" % (r2._vnd(khac), khac / kv["rev"] * 100))
    else:
        p.append("  - N/A — KiotViet chưa đọc được")
    p.append("")

    nguon = (bcn or {}).get("crm", {}).get("theo_nguon") or {}

    def _lead(*keys):
        return sum(int((nguon.get(k) or {}).get("lead") or 0) for k in keys)
    lfb, ltt = _lead("Facebook"), _lead("TikTok")
    p.append("📢 3. MARKETING (chi ads theo ngày lịch %s)" % (
        den.strftime("%d/%m") if tu == den else "%s–%s" % (tu.strftime("%d/%m"), den.strftime("%d/%m"))))
    if fb:
        p.append("  Facebook: chi %s | KQ nền tảng: %d | Lead hợp lệ CRM: %s | CPL hợp lệ: %s" % (
            r2._vnd(fb["spend"]), fb["kq"], lfb if bcn else "N/A",
            r2._vnd(fb["spend"] / lfb) if (bcn and lfb) else "N/A"))
    else:
        p.append("  Facebook: N/A — nguồn chưa đọc được")
    if tt:
        p.append("  TikTok: chi chuyển đổi %s | chi View %s | KQ nền tảng: %d | Lead hợp lệ CRM: %s | CPL hợp lệ: %s" % (
            r2._vnd(tt["conv"]), r2._vnd(tt["view"]), tt["kq"], ltt if bcn else "N/A",
            r2._vnd(tt["conv"] / ltt) if (bcn and ltt) else "N/A"))
        for name, sp, c_ in tt["camp"]:
            p.append("      • %s: %s | %d KQ" % (name, r2._vnd(sp), c_))
    else:
        p.append("  TikTok: N/A — nguồn chưa đọc được")
    if fb and tt and kv:
        tot = fb["spend"] + tt["conv"] + tt["view"]
        p.append("  Tổng chi ads: %s | Tỷ số DT toàn phòng khám/chi ads cùng ngày: %.1f lần" % (
            r2._vnd(tot), kv["rev"] / tot if tot else 0))
        p.append("  ⚠️ Tỷ số trên KHÔNG phải ROAS quy nguồn. Chi ads tính theo ngày lịch (nền tảng không cắt 17:30).")
    p.append("")

    p.append("📞 4. CRM — DATA NGÀY KINH DOANH (KIOT, chỉ lead CHAT/MANUAL)")
    if bcn:
        c = bcn["crm"]
        tong = int(c.get("tong_data") or 0)
        p.append("  - Tổng data mới: %d | Quan tâm chưa số: %s | Rác: %s | Trùng: %s" % (
            tong, c.get("quan_tam_chua_so"), c.get("rac"), c.get("trung")))
        p.append("  - Lead có số thô: %s (%s tổng data)" % (c.get("lead_co_so_tho"), _pct(int(c.get("lead_co_so_tho") or 0), tong)))
        p.append("  - Lead hợp lệ: %s (%s tổng data | %s data sạch)" % (
            c.get("lead_hop_le"), _pct(int(c.get("lead_hop_le") or 0), tong),
            "%.1f%%" % (int(c.get("lead_hop_le") or 0) * 100.0 / int(c.get("data_sach") or 0)) if c.get("data_sach") else "N/A"))
        if c.get("ds_lead_trung"):
            p.append("  - Mã lead trùng/rác (xem chi tiết trong KIOT): %s" % ", ".join(c["ds_lead_trung"][:10]))
        rows = [(k, int(v.get("tong") or 0), int(v.get("lead") or 0)) for k, v in nguon.items() if int(v.get("tong") or 0)]
        if rows:
            p.append("  - Theo nguồn (tổng data | lead hợp lệ):")
            for k, t_, l_ in sorted(rows, key=lambda x: -x[1]):
                p.append("      • %s: %d | %d" % (k, t_, l_))
        st = c.get("theo_trang_thai") or {}
        if st:
            p.append("  - Trạng thái lead: " + ", ".join("%s %s" % kv_ for kv_ in sorted(st.items(), key=lambda x: -x[1])))
        pl = c.get("phan_loai") or {}
        p.append("  - Phân loại: " + ", ".join("%s %s" % (k, v) for k, v in pl.items() if v))
        k = bcn.get("ket_qua") or {}
        p.append("  - Kết quả: lịch đặt mới %s | khách đến %s/%s (%s) | chốt khách mới %s (%s)" % (
            k.get("lich_dat_moi"), k.get("da_den"), k.get("lich_hen_trong_ky"),
            "%.0f%%" % (float(k.get("ti_le_den") or 0) * 100), k.get("chot_khach_moi"),
            "%.0f%%" % (float(k.get("ti_le_chot") or 0) * 100)))
        p.append("  Ghi chú: số trên là SỰ KIỆN trong ngày KD từ nhiều cohort — không chia cho nhau để tính conversion.")
    else:
        p.append("  - N/A — KIOT chưa đọc được")
    p.append("")

    p.append("👥 CÔNG VIỆC SALE (talktime với KHÁCH, đã loại gọi nội bộ — theo ngày lịch)")
    if sale:
        tk = sum(v["khach"] for v in sale.values())
        tp = sum(v["phut"] for v in sale.values())
        p.append("  - Toàn đội: %d lượt khách tương tác | %.0f phút talktime" % (tk, tp))
        for nv, v in sorted(sale.items(), key=lambda x: -x[1]["phut"]):
            d = "      • %s: %d khách | %.0f phút | %d cuộc/%d bắt máy" % (nv, v["khach"], v["phut"], v["cuoc"], v["bm"])
            if v["lead"] or v["lich"]:
                d += " | lead %d, lịch %d" % (v["lead"], v["lich"])
            if v["zalo"] >= 0.5:
                d += " | Zalo chưa rõ khách %.0f phút" % v["zalo"]
            if v["bulk"]:
                d += " | đã loại %d bulk" % v["bulk"]
            p.append(d)
    else:
        p.append("  - N/A — sale-daily chưa đọc được")
    p.append("")

    if bcn:
        h = bcn["lich_hen"]["hen_hom_nay"]
        gio = {int(k): v for k, v in (h.get("theo_gio") or {}).items()}
        sang = sum(v for g, v in gio.items() if g < 13)
        ngay = dt.date.fromisoformat(h.get("ngay")) if h.get("ngay") else now.date()
        p.append("🗓 5. LỊCH HẸN HÔM NAY %s (snapshot %s)" % (ngay.strftime("%d/%m"), now.strftime("%H:%M")))
        p.append("  - Tổng lịch: %s | Sáng: %d | Chiều: %d" % (h.get("tong"), sang, int(h.get("tong") or 0) - sang))
        mc = h.get("moi_cu") or {}
        p.append("  - Khách mới: %s | Khách cũ/tái khám: %s | Chưa phân loại: %s" % (mc.get("moi"), mc.get("cu"), mc.get("khong_ro")))
        xn = h.get("xac_nhan") or {}
        p.append("  - Đã xác nhận: %s | Chưa xác nhận: %s" % (xn.get("da"), xn.get("chua")))
        qt = sorted([(g, v) for g, v in gio.items() if v >= 3])
        if qt:
            p.append("  - Khung giờ quá tải (≥3 lịch): %s" % ", ".join("%dh (%d)" % x for x in qt))
        tv = h.get("theo_tvtt") or {}
        if tv:
            p.append("  - Theo TVTT: %s" % ", ".join("%s %s" % x for x in sorted(tv.items(), key=lambda x: -x[1])))
        if h.get("trung_da_bo"):
            p.append("  - Đã bỏ %s lịch trùng khi đếm" % h["trung_da_bo"])
        p.append("  Chi tiết (tên/dịch vụ) xem trong KIOT: %s/#/appointments" % KIOT)
        p.append("")

    p.append("📅 6. LŨY KẾ THÁNG %d — ĐẾN HẾT NGÀY KD %s" % (den.month, den.strftime("%d/%m")))
    if kvm:
        p.append("  - Doanh thu gộp: %s | Khách duy nhất: %d | Hóa đơn: %d" % (r2._vnd(kvm["rev"]), kvm["khach"], kvm["hd"]))
    else:
        p.append("  - Doanh thu: N/A — KiotViet chưa đọc được")
    p.append("  - So với mục tiêu tháng: %s" % (
        "%.0f%%" % (kvm["rev"] / float(os.environ["MONTHLY_TARGET"]) * 100)
        if (kvm and os.environ.get("MONTHLY_TARGET")) else "N/A — chưa đặt mục tiêu"))
    if fb and tt and kvm:
        am = fb["thang"] + tt["thang"]
        p.append("  - Tổng chi ads: %s (FB %s + TikTok %s) — %.1f%% doanh thu" % (
            r2._vnd(am), r2._vnd(fb["thang"]), r2._vnd(tt["thang"]), am / kvm["rev"] * 100 if kvm["rev"] else 0))
    if lk:
        c, k = lk["crm"], lk["ket_qua"]
        p.append("  - Lead hợp lệ: %s | Chốt khách mới: %s (%s)" % (
            c.get("lead_hop_le"), k.get("chot_khach_moi"), "%.0f%%" % (float(k.get("ti_le_chot") or 0) * 100)))
    p.append("")

    p.append("🔄 7. TÌNH TRẠNG DỮ LIỆU")
    p += tinh_trang
    if tt and tt.get("rt") is not None:
        p.append("  - TikTok token: còn %.0f ngày tới hạn authorize lại" % tt["rt"])
    return "\n".join(p)


if __name__ == "__main__":
    a = [dt.date.fromisoformat(x) for x in sys.argv[1:3]]
    print(build(a[0], a[1] if len(a) > 1 else a[0]) if a else build())
