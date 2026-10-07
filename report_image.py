# -*- coding: utf-8 -*-
"""Vẽ BÁO CÁO ĐIỀU HÀNH thành ẢNH PNG để gửi Telegram (theo cách làm của Revskin).

Đọc số từ CHÍNH văn bản do report2.build() tạo ra -> ảnh và tin chữ luôn cùng
một bộ số, không tính lại lần hai. Không chứa tên/SĐT khách (văn bản nguồn đã
không có).

Chạy thử: python3 report_image.py <file_text_bao_cao> <file_png_ra>
"""
from __future__ import annotations

import io
import os
import re
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

_HERE = os.path.dirname(os.path.abspath(__file__))


def _pick(paths):
    for p in paths:
        if os.path.exists(p):
            return font_manager.FontProperties(fname=p)
    return font_manager.FontProperties()


F_REG = _pick([os.path.join(_HERE, "fonts", "BeVietnamPro-Regular.ttf"),
               "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
               "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"])
F_BOLD = _pick([os.path.join(_HERE, "fonts", "BeVietnamPro-Bold.ttf"),
                "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"])

# Bảng màu: xanh y khoa Doctor Laser + nền sáng
NAVY, TEAL, INK, MUTED = "#0E2A47", "#0E7F6E", "#1E2533", "#6B7385"
BG, CARD, LINE, SOFT = "#F2F5F8", "#FFFFFF", "#E2E7EE", "#E6F2EF"
FB, TT, RED, AMBER, GREEN = "#2D6CDF", "#E0457B", "#D64545", "#E9A23B", "#2F9E5B"

W_IN, DPI = 10.8, 100  # 1080 px


# ---------------------------------------------------------------- đọc số
def _n(s):
    s = (s or "").replace(".", "").replace("đ", "").replace(",", ".").strip()
    try:
        return float(s)
    except ValueError:
        return 0.0


def _m(pat, text, g=1, default=""):
    m = re.search(pat, text)
    return m.group(g) if m else default


def parse(text: str) -> dict:
    d = {}
    d["title_day"] = _m(r"BÁO CÁO ĐIỀU HÀNH — (.+)", text)
    d["dt"] = _n(_m(r"Doanh thu gộp \(trước VAT\): ([\d.]+)", text))
    d["thucthu"] = _m(r"Tiền thực thu \(gồm VAT\): ([^\n]+)", text)
    d["khach"] = int(_n(_m(r"Khách duy nhất có hóa đơn: (\d+)", text)))
    d["hd"] = int(_n(_m(r"Số hóa đơn hợp lệ: (\d+)", text)))
    d["tbhd"] = _n(_m(r"TB/hóa đơn: ([\d.]+)", text))
    d["huy"] = _m(r"Hoàn/hủy: ([^|]+)", text).strip()
    blk = _m(r"Top dịch vụ:\n((?:\s+• .+\n)+)", text)
    d["dv"] = [(m.group(1).strip(), _n(m.group(2)), int(m.group(3)))
               for m in re.finditer(r"• (.+?): ([\d.]+)đ \((\d+)%\)", blk)]

    d["fb"] = {
        "chi": _n(_m(r"Facebook: chi ([\d.]+)", text)),
        "kq": _m(r"Facebook: .*?KQ nền tảng: (\d+)", text),
        "lead": _m(r"Facebook: .*?Lead hợp lệ CRM: (\S+)", text).rstrip("|").strip(),
        "cpl": _m(r"Facebook: .*?CPL hợp lệ: ([^\n]+)", text).strip(),
    }
    d["tt"] = {
        "chi": _n(_m(r"TikTok: chi chuyển đổi ([\d.]+)", text)),
        "view": _n(_m(r"chi View ([\d.]+)", text)),
        "kq": _m(r"TikTok: .*?KQ nền tảng: (\d+)", text),
        "lead": _m(r"TikTok: .*?Lead hợp lệ CRM: (\S+)", text).rstrip("|").strip(),
        "cpl": _m(r"TikTok: .*?CPL hợp lệ: ([^\n]+)", text).strip(),
    }
    blk = _m(r"TikTok: chi chuyển đổi.*\n((?:\s+• .+\n)+)", text)
    d["tt_camp"] = [(m.group(1).strip(), _n(m.group(2)), int(m.group(3)))
                    for m in re.finditer(r"• (.+?): ([\d.]+)đ \| (\d+) KQ", blk)]
    d["giamtru"] = _m(r"Giảm trừ: ([^\n]+)", text).strip()
    d["ads"] = _n(_m(r"Tổng chi ads: ([\d.]+)", text))
    d["tyso"] = _m(r"cùng ngày: ([\d.]+) lần", text)

    d["tong_data"] = int(_n(_m(r"Tổng data mới: (\d+)", text)))
    d["qt"] = int(_n(_m(r"Quan tâm chưa số: (\d+)", text)))
    d["rac"] = int(_n(_m(r"Rác: (\d+)", text)))
    d["trung"] = int(_n(_m(r"Trùng: (\d+)", text)))
    d["tho"] = int(_n(_m(r"Lead có số thô: (\d+)", text)))
    d["hople"] = int(_n(_m(r"Lead hợp lệ: (\d+) \(", text)))
    d["pct_sach"] = _m(r"\| ([\d.]+%) data sạch", text)
    d["pct_tho"] = _m(r"Lead có số thô: \d+ \(([\d.]+%)", text)
    d["pct_hople"] = _m(r"Lead hợp lệ: \d+ \(([\d.]+%) tổng data", text)
    blk = _m(r"Theo nguồn \(tổng data \| lead hợp lệ\):\n((?:\s+• .+\n)+)", text)
    d["nguon"] = [(m.group(1).strip(), int(m.group(2)), int(m.group(3)))
                  for m in re.finditer(r"• (.+?): (\d+) \| (\d+)", blk)]

    d["sale_tong"] = _m(r"Toàn đội: ([^\n]+)", text)
    blk = _m(r"CÔNG VIỆC SALE.*\n.*\n((?:\s+• .+\n)+)", text)
    sale = []
    for m in re.finditer(r"• (.+?): (\d+) khách \| (\d+) phút \| (\d+) cuộc/(\d+) bắt máy(.*)", blk):
        rest = m.group(6)
        sale.append({
            "nv": m.group(1), "khach": int(m.group(2)), "phut": int(m.group(3)),
            "cuoc": int(m.group(4)), "bm": int(m.group(5)),
            "lich": int(_n(_m(r"lịch (\d+)", rest, default="0"))),
            "lead": int(_n(_m(r"lead (\d+)", rest, default="0"))),
            "zalo": int(_n(_m(r"Zalo chưa rõ khách (\d+)", rest, default="0"))),
            "bulk": int(_n(_m(r"đã loại (\d+) bulk", rest, default="0"))),
        })
    d["sale"] = sale

    d["lich_ngay"] = _m(r"LỊCH HẸN HÔM NAY (\S+)", text)
    d["lich_tong"] = int(_n(_m(r"Tổng lịch: (\d+)", text)))
    d["lich_sang"] = int(_n(_m(r"Sáng: (\d+)", text)))
    d["lich_chieu"] = int(_n(_m(r"Chiều: (\d+)", text)))
    d["lich_moi"] = int(_n(_m(r"Khách mới: (\d+)", text)))
    d["lich_cu"] = int(_n(_m(r"Khách cũ/tái khám: (\d+)", text)))
    d["qua_tai"] = _m(r"quá tải \(≥3 lịch\): ([^\n]+)", text)
    d["tvtt"] = _m(r"Theo TVTT: ([^\n]+)", text)

    d["lk_thang"] = _m(r"LŨY KẾ THÁNG (\d+)", text)
    d["lk_dt"] = _n(_m(r"LŨY KẾ.*\n\s+- Doanh thu gộp: ([\d.]+)", text))
    d["lk_khach"] = _m(r"LŨY KẾ.*\n.*Khách duy nhất: (\d+)", text)
    d["lk_hd"] = _m(r"LŨY KẾ.*\n.*Hóa đơn: (\d+)", text)
    d["lk_fb"] = _n(_m(r"\(FB ([\d.]+)đ \+ TikTok", text))
    d["lk_tt"] = _n(_m(r"\+ TikTok ([\d.]+)đ\)", text))
    d["lk_ads"] = _n(_m(r"Tổng chi ads: ([\d.]+)đ \(FB", text))
    d["lk_ads_pct"] = _m(r"— ([\d.]+)% doanh thu", text)
    d["lk_lead"] = _m(r"- Lead hợp lệ: (\d+) \| Chốt", text)
    d["lk_chot"] = _m(r"Chốt \(bot đối chiếu hóa đơn\): (\d+ \(\d+%\))", text)

    d["canh_bao"] = re.findall(r"🚨.*\n((?:\s+- .+\n)+)", text)
    d["status_ok"] = text.count(": OK")
    d["status_bad"] = len(re.findall(r"STALE|ERROR", _m(r"TÌNH TRẠNG DỮ LIỆU\n((?:.+\n?)+)", text)))
    d["tiktok_days"] = _m(r"TikTok token: còn (\d+) ngày", text)
    return d


# ---------------------------------------------------------------- vẽ
def _tr(v):
    """Tiền gọn: 62.355.000 -> 62,4tr ; 1.633.707.000 -> 1,63 tỷ."""
    if v >= 1e9:
        return ("%.2f tỷ" % (v / 1e9)).replace(".", ",")
    if v >= 1e6:
        return ("%.1ftr" % (v / 1e6)).replace(".", ",")
    if v >= 1e3:
        return ("%.0fk" % (v / 1e3))
    return "%.0f" % v


class _Canvas:
    def __init__(self, h_px):
        self.h = h_px
        self.fig = plt.figure(figsize=(W_IN, h_px / DPI), dpi=DPI)
        self.fig.patch.set_facecolor(BG)
        self.ax = self.fig.add_axes([0, 0, 1, 1])
        self.ax.set_xlim(0, 1080)
        self.ax.set_ylim(h_px, 0)
        self.ax.axis("off")

    def text(self, x, y, s, size=20, bold=False, color=INK, ha="left", va="top"):
        self.ax.text(x, y, s, fontsize=size * 0.72, fontproperties=F_BOLD if bold else F_REG,
                     color=color, ha=ha, va=va)

    def card(self, x, y, w, h, fc=CARD, ec=LINE):
        self.ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=18",
                                         fc=fc, ec=ec, lw=1.2))

    def rect(self, x, y, w, h, fc):
        self.ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=6",
                                         fc=fc, ec="none"))

    def section(self, y, title):
        self.text(48, y, title, 24, True, NAVY)
        return y + 44


def render(text: str) -> bytes:
    d = parse(text)
    H = 3000
    c = _Canvas(H)
    X0, WC = 40, 1000

    # Header
    c.ax.add_patch(FancyBboxPatch((0, 0), 1080, 150, boxstyle="square,pad=0", fc=NAVY, ec="none"))
    c.text(48, 34, "DOCTOR LASER · BÁO CÁO ĐIỀU HÀNH", 22, True, "#9FD8CD")
    c.text(48, 72, d["title_day"], 40, True, "white")
    c.text(1032, 44, "Chốt đến 23:59", 18, False, "#B9C6D6", ha="right")
    y = 180

    # Cảnh báo
    if d["canh_bao"]:
        lines = [ln.strip("- ").strip() for ln in d["canh_bao"][0].strip().split("\n")][:3]
        hh = 60 + 34 * len(lines)
        c.card(X0, y, WC, hh, fc="#FDECEC", ec="#F3C1C1")
        c.text(68, y + 20, "CẦN XỬ LÝ NGAY", 22, True, RED)
        for i, ln in enumerate(lines):
            c.text(68, y + 58 + 34 * i, ln[:88], 17, False, INK)
        y += hh + 24

    # KPI tiles
    tiles = [
        ("DOANH THU", _tr(d["dt"]), "%d khách · %d HĐ" % (d["khach"], d["hd"]), TEAL),
        ("THỰC THU", _tr(_n(d["thucthu"])) if _n(d["thucthu"]) else "N/A",
         "TB/HĐ %s · hủy %s" % (_tr(d["tbhd"]), d["huy"] or "0"), NAVY),
        ("CHI ADS", _tr(d["ads"]), "DT/ads cùng ngày %s lần" % d["tyso"], AMBER),
        ("LEAD HỢP LỆ", str(d["hople"]), "%s data sạch" % d["pct_sach"], FB),
    ]
    tw = (WC - 3 * 20) / 4
    for i, (lab, val, sub, col) in enumerate(tiles):
        x = X0 + i * (tw + 20)
        c.card(x, y, tw, 170)
        c.rect(x, y, tw, 8, col)
        c.text(x + 22, y + 28, lab, 16, True, MUTED)
        c.text(x + 22, y + 60, val, 40, True, INK)
        c.text(x + 22, y + 126, sub, 14, False, MUTED)
    y += 200
    if d["giamtru"] and d["giamtru"].startswith("N/A"):
        c.text(48, y - 14, "Giảm trừ/trả hàng: " + d["giamtru"], 14, False, MUTED)
        y += 16

    # Top dịch vụ
    y = c.section(y, "Doanh thu theo dịch vụ")
    hh = 40 + 52 * len(d["dv"])
    c.card(X0, y, WC, hh)
    mx = max([v for _, v, _ in d["dv"]] or [1])
    for i, (ten, v, pct) in enumerate(d["dv"]):
        yy = y + 26 + 52 * i
        c.text(68, yy + 6, ten.title()[:26], 18, False, INK)
        bw = 440 * v / mx
        c.rect(420, yy + 4, 440, 30, SOFT)
        c.rect(420, yy + 4, max(bw, 6), 30, TEAL)
        c.text(1012, yy + 6, "%s · %d%%" % (_tr(v), pct), 18, True, INK, ha="right")
    y += hh + 30

    # Marketing
    y = c.section(y, "Marketing")
    hm = 250 + 36 * len(d["tt_camp"])
    c.card(X0, y, WC, hm)
    hdr = ["Kênh", "Chi", "KQ nền tảng", "Lead CRM", "CPL hợp lệ"]
    xs = [68, 290, 480, 660, 830]
    for x, h in zip(xs, hdr):
        c.text(x, y + 24, h, 16, True, MUTED)
    rows = [("Facebook", d["fb"], FB), ("TikTok", d["tt"], TT)]
    for i, (ten, r, col) in enumerate(rows):
        yy = y + 70 + 56 * i
        c.rect(68, yy + 6, 10, 26, col)
        c.text(90, yy + 4, ten, 20, True, INK)
        c.text(290, yy + 4, _tr(r["chi"]), 20, False, INK)
        c.text(480, yy + 4, str(r["kq"]), 20, False, INK)
        c.text(660, yy + 4, str(r["lead"]), 20, True, INK)
        c.text(830, yy + 4, r["cpl"].replace(".000đ", "k").replace("đ", ""), 20, False, INK)
    c.text(68, y + 186, "Chiến dịch TikTok", 16, True, MUTED)
    for i, (ten, chi, kq) in enumerate(d["tt_camp"]):
        yy = y + 218 + 36 * i
        c.text(90, yy, ten[:40], 17, False, INK)
        c.text(700, yy, _tr(chi), 17, True, INK)
        c.text(830, yy, ("%d KQ" % kq) if kq else "nhận diện", 17, False,
               INK if kq else MUTED)
    c.text(68, y + hm - 36, "Tổng ads %s · DT/ads cùng ngày %s lần — KHÔNG phải ROAS quy nguồn"
           % (_tr(d["ads"]), d["tyso"]), 14, False, MUTED)
    y += hm + 30

    # CRM
    y = c.section(y, "Data & lead (00:00–23:59)")
    c.card(X0, y, WC, 300)
    funnel = [("Tổng data", d["tong_data"], NAVY, ""),
              ("Có số thô", d["tho"], FB, d["pct_tho"] + " tổng data"),
              ("Lead hợp lệ", d["hople"], TEAL, d["pct_hople"] + " · " + d["pct_sach"] + " sạch"),
              ("Quan tâm", d["qt"], AMBER, "chưa có số"),
              ("Rác + trùng", d["rac"] + d["trung"], MUTED, "trùng %d" % d["trung"])]
    fw = (WC - 60) / 5
    for i, (lab, v, col, sub) in enumerate(funnel):
        x = X0 + 30 + i * fw
        c.text(x, y + 22, lab, 15, True, MUTED)
        c.text(x, y + 48, str(v), 34, True, col)
        if sub:
            c.text(x, y + 92, sub, 13, False, MUTED)
    c.text(68, y + 124, "Theo nguồn: tổng data / lead hợp lệ", 16, True, MUTED)
    mx = max([t for _, t, _ in d["nguon"]] or [1])
    for i, (ten, t, l) in enumerate(d["nguon"][:4]):
        yy = y + 152 + 34 * i
        c.text(68, yy, ten, 17, False, INK)
        c.rect(300, yy + 2, 560 * t / mx, 22, "#D7E2F0")
        c.rect(300, yy + 2, max(560 * l / mx, 4), 22, TEAL)
        c.text(1012, yy, "%d / %d" % (t, l), 17, True, INK, ha="right")
    y += 330

    # Sale
    y = c.section(y, "Công việc sale (talktime với khách)")
    hh = 80 + 46 * len(d["sale"])
    c.card(X0, y, WC, hh)
    c.text(68, y + 20, d["sale_tong"], 17, True, TEAL)
    hdr = ["Nhân viên", "Khách", "Phút", "Cuộc/bắt máy", "Lead", "Lịch", "Zalo", "Bulk"]
    xs = [68, 300, 395, 510, 690, 775, 855, 940]
    for x, h in zip(xs, hdr):
        c.text(x, y + 56, h, 15, True, MUTED)
    mxp = max([s["phut"] for s in d["sale"]] or [1]) or 1
    for i, s in enumerate(d["sale"]):
        yy = y + 92 + 46 * i
        if i % 2 == 0:
            c.rect(52, yy - 6, WC - 24, 40, "#F7F9FB")
        c.text(68, yy, s["nv"], 18, True, INK)
        c.text(300, yy, str(s["khach"]), 18, False, INK)
        c.rect(395, yy + 4, 90 * s["phut"] / mxp, 20, SOFT)
        c.text(399, yy, str(s["phut"]), 18, True, TEAL)
        c.text(510, yy, "%d/%d" % (s["cuoc"], s["bm"]), 18, False, INK)
        c.text(690, yy, str(s["lead"]), 18, False, INK)
        c.text(775, yy, str(s["lich"]), 18, False, INK)
        c.text(855, yy, str(s["zalo"]) if s["zalo"] else "–", 18, False, MUTED)
        c.text(940, yy, str(s["bulk"]) if s["bulk"] else "–", 18, False,
               RED if s["bulk"] >= 10 else MUTED)
    y += hh + 30

    # Lịch hẹn + lũy kế (2 cột)
    half = (WC - 20) / 2
    c.text(48, y, "Lịch hôm nay %s" % d["lich_ngay"], 24, True, NAVY)
    c.text(48 + half + 20, y, "Lũy kế tháng %s" % d["lk_thang"], 24, True, NAVY)
    y += 44
    c.card(X0, y, half, 290)
    c.text(68, y + 22, str(d["lich_tong"]), 52, True, TEAL)
    c.text(160, y + 40, "lịch hẹn", 20, False, MUTED)
    c.text(68, y + 110, "Sáng %d · Chiều %d" % (d["lich_sang"], d["lich_chieu"]), 18, False, INK)
    c.text(68, y + 145, "Khách mới %d · Cũ/tái khám %d" % (d["lich_moi"], d["lich_cu"]), 18, False, INK)
    if d["tvtt"]:
        c.text(68, y + 180, "TVTT: " + d["tvtt"][:34], 17, False, INK)
    if d["qua_tai"]:
        c.text(68, y + 220, "Quá tải: " + d["qua_tai"], 17, True, AMBER)
    c.text(68, y + 254, "Xác nhận lịch: chưa có nguồn", 14, False, MUTED)
    x2 = X0 + half + 20
    c.card(x2, y, half, 290)
    c.text(x2 + 28, y + 22, _tr(d["lk_dt"]), 44, True, TEAL)
    c.text(x2 + 28, y + 90, "%s khách · %s hóa đơn" % (d["lk_khach"], d["lk_hd"]), 18, False, INK)
    c.text(x2 + 28, y + 125, "Chi ads %s (%s%% DT)" % (_tr(d["lk_ads"]), d["lk_ads_pct"]), 18, False, INK)
    c.text(x2 + 28, y + 158, "FB %s · TikTok %s" % (_tr(d["lk_fb"]), _tr(d["lk_tt"])), 16, False, MUTED)
    c.text(x2 + 28, y + 195, "Lead hợp lệ %s · Chốt %s" % (d["lk_lead"], d["lk_chot"]), 18, False, INK)
    c.text(x2 + 28, y + 240, "Mục tiêu tháng: chưa đặt", 16, False, MUTED)
    y += 320

    # Footer trạng thái
    ok = d["status_bad"] == 0
    c.card(X0, y, WC, 70, fc=SOFT if ok else "#FDECEC", ec=LINE)
    c.text(68, y + 22, ("Dữ liệu: tất cả nguồn OK" if ok else "Có nguồn dữ liệu lỗi — xem tin chữ")
           + ("   ·   TikTok token còn %s ngày" % d["tiktok_days"] if d["tiktok_days"] else ""),
           18, True, GREEN if ok else RED)
    y += 100

    # Cắt chiều cao vừa nội dung
    c.ax.set_ylim(y, 0)
    c.fig.set_size_inches(W_IN, y / DPI)
    buf = io.BytesIO()
    c.fig.savefig(buf, format="png", dpi=DPI, facecolor=BG)
    plt.close(c.fig)
    return buf.getvalue()


# ================================================================ BẢN 19H
def parse_kiemtra(text: str) -> dict:
    """Đọc văn bản report.build_data_preview (bản kiểm data 19h cho sale)."""
    d = {}
    d["tieu_de"] = _m(r"KIỂM TRA DATA — (chốt 18h \S+)", text)
    d["cua_so"] = _m(r"KIỂM TRA DATA — chốt 18h \S+ \((.+?)\)", text)
    d["tong"] = int(_n(_m(r"TỔNG DATA: (\d+)", text)))
    d["lead"] = int(_n(_m(r"Lead \(đã có SĐT\): (\d+)", text)))
    d["hople"] = _m(r"hợp lệ (\d+), trùng", text) or str(d["lead"])
    d["trungrac"] = int(_n(_m(r"trùng/rác (\d+)", text, default="0")))
    d["qt"] = int(_n(_m(r"Quan tâm \(chưa SĐT\): (\d+)", text)))
    d["rac"] = int(_n(_m(r"• Rác: (\d+)", text)))
    d["khach_cu_oa"] = _m(r"\(trong đó (\d+) data khách cũ quét OA\)", text)
    st = _m(r"Trạng thái LEAD: ([^\n]+)", text)
    d["trang_thai"] = [(m.group(1).strip(), int(m.group(2)))
                       for m in re.finditer(r"([^,]+?) (\d+)(?:,|$)", st)]
    d["ma_trung"] = re.findall(r"• (L\d+) ·", text)
    blk = _m(r"Theo nguồn \(lead/tổng data nguồn\):\n((?:\s+• .+\n)+)", text)
    d["nguon"] = [(m.group(1).strip(), int(m.group(2)), int(m.group(3)))
                  for m in re.finditer(r"• (.+?): (\d+)/(\d+)", blk)]
    pl = _m(r"Phân loại: ([^\n]+)", text)
    d["phan_loai"] = [(m.group(1).strip(), int(m.group(2)))
                      for m in re.finditer(r"([^,]+?) (\d+)(?:,|$)", pl)]
    d["chot"] = _m(r"Kết quả: Chốt (\d+ \(\d+%\))", text)
    d["datlich"] = _m(r"Đặt lịch (\d+ \(\d+%\))", text)
    d["lich_ngay"] = _m(r"LỊCH HẸN NGÀY MAI \((\S+)\)", text)
    d["lich_tong"] = int(_n(_m(r"LỊCH HẸN NGÀY MAI \(\S+\): (\d+)", text, default="0")))
    gio, tvtt = {}, {}
    for m in re.finditer(r"^\s+• (\d{1,2})h\S*\s+.*?(?:\(TVTT: ([^)]+)\))?$", text, re.M):
        h = int(m.group(1))
        gio[h] = gio.get(h, 0) + 1
        if m.group(2):
            tvtt[m.group(2).strip()] = tvtt.get(m.group(2).strip(), 0) + 1
    d["lich_gio"], d["lich_tvtt"] = gio, tvtt
    return d


def render_kiemtra(text: str) -> bytes:
    d = parse_kiemtra(text)
    c = _Canvas(2400)
    X0, WC = 40, 1000

    c.ax.add_patch(FancyBboxPatch((0, 0), 1080, 150, boxstyle="square,pad=0", fc=TEAL, ec="none"))
    c.text(48, 32, "DOCTOR LASER · KIỂM TRA DATA CHO SALE", 22, True, "#CDEFE8")
    c.text(48, 70, d["tieu_de"].capitalize(), 40, True, "white")
    c.text(1032, 44, d["cua_so"].replace("→", "–"), 17, False, "#D9F2EC", ha="right")
    y = 176
    c.text(48, y, "Sale rà và sửa phân loại tối nay — báo cáo chính thức gửi 8h sáng mai.",
           16, False, MUTED)
    y += 40

    tiles = [("TỔNG DATA", str(d["tong"]), "cửa sổ 18h – 18h", NAVY),
             ("LEAD CÓ SỐ", str(d["lead"]), "hợp lệ %s · trùng/rác %d" % (d["hople"], d["trungrac"]), TEAL),
             ("QUAN TÂM", str(d["qt"]), "chưa có số — cần nuôi", AMBER),
             ("RÁC", str(d["rac"]),
              ("%s khách cũ quét OA" % d["khach_cu_oa"]) if d["khach_cu_oa"] else "đã loại", MUTED)]
    tw = (WC - 60) / 4
    for i, (lab, val, sub, col) in enumerate(tiles):
        x = X0 + i * (tw + 20)
        c.card(x, y, tw, 170)
        c.rect(x, y, tw, 8, col)
        c.text(x + 22, y + 28, lab, 16, True, MUTED)
        c.text(x + 22, y + 60, val, 44, True, INK)
        c.text(x + 22, y + 128, sub, 14, False, MUTED)
    y += 200

    # Kết quả + phân loại
    y = c.section(y, "Kết quả & mức độ nóng")
    c.card(X0, y, WC, 150)
    c.text(68, y + 24, "Chốt", 16, True, MUTED)
    c.text(68, y + 50, d["chot"] or "0", 30, True, GREEN)
    c.text(330, y + 24, "Đặt lịch", 16, True, MUTED)
    c.text(330, y + 50, d["datlich"] or "0", 30, True, TEAL)
    pcol = {"Nóng": RED, "Ấm": AMBER, "Lạnh": FB}
    tot = sum(v for _, v in d["phan_loai"]) or 1
    xx = 600
    c.text(600, y + 24, "Phân loại lead", 16, True, MUTED)
    for ten, v in d["phan_loai"]:
        w = 400 * v / tot
        c.rect(xx, y + 58, max(w - 4, 4), 34, pcol.get(ten, MUTED))
        if w > 60:
            c.text(xx + 10, y + 63, "%s %d" % (ten, v), 16, True, "white")
        xx += w
    c.text(600, y + 104, " · ".join("%s %d" % kv for kv in d["phan_loai"]), 15, False, MUTED)
    y += 180

    # Trạng thái lead
    y = c.section(y, "Trạng thái lead")
    hh = 40 + 46 * len(d["trang_thai"])
    c.card(X0, y, WC, hh)
    mx = max([v for _, v in d["trang_thai"]] or [1])
    for i, (ten, v) in enumerate(d["trang_thai"]):
        yy = y + 24 + 46 * i
        col = GREEN if "chốt" in ten.lower() else TEAL if "lịch" in ten.lower() else \
            RED if ten.upper() in ("TRÙNG", "SPAM/RÁC") else NAVY
        c.text(68, yy + 4, ten.capitalize(), 18, False, INK)
        c.rect(360, yy + 4, 560 * v / mx, 28, col)
        c.text(1012, yy + 4, str(v), 18, True, INK, ha="right")
    y += hh + 30

    # Theo nguồn
    y = c.section(y, "Theo nguồn — lead / tổng data")
    hh = 40 + 50 * len(d["nguon"])
    c.card(X0, y, WC, hh)
    mx = max([t for _, _, t in d["nguon"]] or [1])
    for i, (ten, l, t) in enumerate(d["nguon"]):
        yy = y + 24 + 50 * i
        c.text(68, yy + 4, ten, 18, False, INK)
        c.rect(300, yy + 4, 520 * t / mx, 28, "#D7E2F0")
        c.rect(300, yy + 4, max(520 * l / mx, 4), 28, TEAL)
        c.text(1012, yy + 4, "%d / %d · %d%%" % (l, t, round(l * 100 / t) if t else 0),
               18, True, INK, ha="right")
    y += hh + 30

    # Lịch ngày mai
    y = c.section(y, "Lịch hẹn ngày mai %s" % d["lich_ngay"])
    c.card(X0, y, WC, 300)
    c.text(68, y + 24, str(d["lich_tong"]), 52, True, TEAL)
    c.text(150, y + 44, "khách", 20, False, MUTED)
    sang = sum(v for h, v in d["lich_gio"].items() if h < 13)
    c.text(68, y + 104, "Sáng %d · Chiều %d" % (sang, d["lich_tong"] - sang), 18, False, INK)
    if d["lich_tvtt"]:
        c.text(68, y + 140, "TVTT: " + ", ".join("%s %d" % kv for kv in
               sorted(d["lich_tvtt"].items(), key=lambda x: -x[1])), 17, False, INK)
    # biểu đồ theo giờ 8h→19h
    gx, gy, gh = 380, y + 40, 180
    mx = max(d["lich_gio"].values() or [1])
    for i, h in enumerate(range(8, 20)):
        v = d["lich_gio"].get(h, 0)
        bh = gh * v / mx if mx else 0
        col = AMBER if v >= 3 else TEAL
        c.rect(gx + i * 52, gy + gh - bh, 38, max(bh, 2), col if v else LINE)
        if v:
            c.text(gx + i * 52 + 19, gy + gh - bh - 26, str(v), 15, True, INK, ha="center")
        c.text(gx + i * 52 + 19, gy + gh + 10, "%dh" % h, 13, False, MUTED, ha="center")
    c.text(68, y + 250, "Cam = khung giờ có từ 3 lịch trở lên", 14, False, MUTED)
    y += 330

    if d["ma_trung"]:
        c.card(X0, y, WC, 70, fc="#FDF3E3", ec="#F1D9A8")
        c.text(68, y + 22, "Lead trùng cần gộp trong KIOT: " + ", ".join(d["ma_trung"][:8]),
               17, True, AMBER)
        y += 90
    c.text(48, y + 4, "Chi tiết từng khách xem ở tin chữ bên dưới / trong KIOT.", 15, False, MUTED)
    y += 50

    c.ax.set_ylim(y, 0)
    c.fig.set_size_inches(W_IN, y / DPI)
    buf = io.BytesIO()
    c.fig.savefig(buf, format="png", dpi=DPI, facecolor=BG)
    plt.close(c.fig)
    return buf.getvalue()


if __name__ == "__main__":
    src, out = sys.argv[1], sys.argv[2]
    with open(src, encoding="utf-8") as f:
        t = f.read()
        png = render_kiemtra(t) if "KIỂM TRA DATA" in t else render(t)
    with open(out, "wb") as f:
        f.write(png)
    print("OK", out, len(png), "bytes")
