"""Phân loại ẢNH KHÁCH HÀNG theo hóa đơn KiotViet — chạy trên máy Mac công ty.

Ý tưởng: lấy hóa đơn làm gốc. Ảnh chụp ngày X chỉ có thể thuộc về những khách có
hóa đơn ngày X -> máy gợi ý, người xác nhận, rồi xuất ảnh vào thư mục theo khách.

Các bước (làm thử 1 tháng, ví dụ 2025-09):
    python3 anhkhach.py hoadon 2025-09          # 1. kéo hóa đơn tháng từ KiotViet
    python3 anhkhach.py quet 2025-09            # 2. đọc ảnh tháng đó trong Photos (iCloud)
    python3 anhkhach.py quet 2025-09 --ocr      #    ... kèm đọc chữ trong ảnh (chậm hơn)
    python3 anhkhach.py quet 2025-09 --thu-muc ~/AnhXuat   # hoặc đọc từ 1 thư mục ảnh
    python3 anhkhach.py ghep 2025-09            # 3. máy tự gợi ý ảnh nào của khách nào
    python3 anhkhach.py duyet                   # 4. mở trang duyệt http://localhost:8765
    python3 anhkhach.py baocao 2025-09          # 5. đo tỷ lệ máy gợi ý đúng
    python3 anhkhach.py xuat 2025-09 ~/KhachHang [--gan-tu-khoa]   # 6. xuất theo khách

Toàn bộ dữ liệu nằm trong file `anhkhach.db` trên máy. Ảnh KHÔNG bị di chuyển hay
sửa trong Photos (trừ khi bật --gan-tu-khoa: chỉ THÊM từ khóa vào ảnh).
"""

from __future__ import annotations

import argparse
import calendar
import datetime as dt
import hashlib
import html
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import unicodedata
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

DB_FILE = os.environ.get("ANH_DB", "anhkhach.db")
PORT = int(os.environ.get("ANH_PORT", "8765"))
DOT_PHUT = 15  # ảnh cách nhau <= 15 phút coi là cùng một đợt chụp
ANH_DUOI = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".tif", ".tiff"}

LOAI_ANH = ["", "trước", "trong", "sau"]
VUNG = ["", "mặt", "trán", "má", "mũi", "cằm", "cổ", "nách", "tay", "chân",
        "lưng", "bụng", "ngực", "bikini", "toàn thân", "khác"]


# ----------------------------- tiện ích -----------------------------
def khong_dau(s: str) -> str:
    """'Nguyễn Thị Ánh' -> 'nguyen thi anh' (bỏ dấu, chữ thường, chỉ chữ/số)."""
    s = (s or "").replace("đ", "d").replace("Đ", "D")
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", s.lower()).split())


def ten_thu_muc(s: str) -> str:
    return "".join(w.capitalize() for w in khong_dau(s).split()) or "KhongTen"


def chuan_sdt(s: str) -> str:
    d = re.sub(r"\D", "", s or "")
    if d.startswith("84") and len(d) == 11:
        d = "0" + d[2:]
    return d


def thang(s: str) -> tuple[int, int]:
    m = re.fullmatch(r"(\d{4})-(\d{1,2})", s.strip())
    if not m:
        sys.exit(f"Tháng phải có dạng YYYY-MM, ví dụ 2025-09 (nhận được: {s!r})")
    return int(m.group(1)), int(m.group(2))


def khoang_thang(y: int, m: int) -> tuple[str, str]:
    return f"{y:04d}-{m:02d}-01", f"{y:04d}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}"


def ket_noi() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS visits (
            code TEXT PRIMARY KEY, ngay TEXT, gio TEXT, ma_kh TEXT, ten_kh TEXT,
            sdt TEXT, dich_vu TEXT, chi_nhanh TEXT);
        CREATE INDEX IF NOT EXISTS visits_ngay ON visits(ngay);
        CREATE TABLE IF NOT EXISTS photos (
            id TEXT PRIMARY KEY, nguon TEXT, ngay TEXT, thoi_gian TEXT,
            ten_file TEXT, duong_dan TEXT, anh_xem TEXT, chu_thich TEXT, ocr TEXT,
            dot INTEGER,
            goi_y_hd TEXT, do_tin TEXT, ly_do TEXT,
            xn_hd TEXT, loai_anh TEXT, vung TEXT, ghi_chu TEXT,
            bo_qua INTEGER DEFAULT 0, xn_luc TEXT, da_xuat TEXT);
        CREATE INDEX IF NOT EXISTS photos_ngay ON photos(ngay);
        """
    )
    return conn


# ------------------------- 1. HÓA ĐƠN -------------------------
def cmd_hoadon(a) -> None:
    import config
    import kiotviet

    if not config.kiotviet_enabled():
        sys.exit("Chưa cấu hình KiotViet trong .env (KIOTVIET_CLIENT_ID/SECRET/RETAILER).")
    y, m = thang(a.thang)
    invs = kiotviet.get_invoices_for_month(y, m, force=True)
    print(f"Hóa đơn {m:02d}/{y}: {len(invs)}")

    print("Lấy danh bạ khách (SĐT)...")
    sdt_theo_id, sdt_theo_ma = {}, {}
    try:
        for c in kiotviet.get_customers():
            sdt = chuan_sdt(c.get("contactNumber") or "")
            sdt_theo_id[c.get("id")] = sdt
            sdt_theo_ma[c.get("code")] = sdt
    except Exception as e:  # noqa: BLE001
        print(f"  ! không lấy được danh bạ ({e}) — bỏ qua SĐT")

    conn = ket_noi()
    for i in invs:
        ngay_gio = (i.get("purchaseDate") or "")[:19]
        dv = []
        for d in i.get("invoiceDetails") or []:
            ten = (d.get("productName") or "").strip()
            if ten and ten not in dv:
                dv.append(ten)
        conn.execute(
            "INSERT OR REPLACE INTO visits VALUES (?,?,?,?,?,?,?,?)",
            (
                str(i.get("code") or i.get("id")),
                ngay_gio[:10],
                ngay_gio[11:16],
                i.get("customerCode") or "",
                i.get("customerName") or "Khách lẻ",
                sdt_theo_id.get(i.get("customerId"))
                or sdt_theo_ma.get(i.get("customerCode")) or "",
                " | ".join(dv),
                i.get("branchName") or "",
            ),
        )
    conn.commit()
    print(f"Đã lưu vào {os.path.abspath(DB_FILE)}")


# ------------------------- 2. QUÉT ẢNH -------------------------
ANH_GOC = os.environ.get("ANH_GOC", "anh_goc")  # bản gốc tải tạm từ iCloud (chỉ tháng đang xử lý)
OCR_TIN = 0.3  # ngưỡng tin cậy chữ đọc được


def _tai_ban_goc(p, thang_dir: str) -> str | None:
    """Tải bản gốc (bản ĐÃ SỬA nếu có — nhãn nhân viên thường viết bằng công cụ sửa ảnh) về máy."""
    os.makedirs(thang_dir, exist_ok=True)
    co = [os.path.join(thang_dir, f) for f in os.listdir(thang_dir) if f.startswith(p.uuid)]
    if co:
        return co[0]
    sua = bool(p.hasadjustments)
    loi = "Photos không trả về file"
    for _ in range(2):  # iCloud đôi khi chậm -> thử lại 1 lần
        try:
            out = p.export(thang_dir, f"{p.uuid}.jpeg" if sua else None, edited=sua,
                           use_photos_export=True, timeout=180)
        except Exception as e:  # noqa: BLE001
            out, loi = [], str(e)[:120]
        if out:
            dich = os.path.join(thang_dir, p.uuid + os.path.splitext(out[0])[1].lower())
            os.replace(out[0], dich)
            return dich
    print(f"  ! không tải được {p.original_filename}: {loi}")
    return None


LO_TAI = int(os.environ.get("ANH_LO", "20"))  # số ảnh mỗi lần nhờ Photos xuất cùng lúc

_XUAT_LO = """
on run argv
    set thePath to item 1 of argv
    set theTimeOut to (item 2 of argv) as integer
    tell application "Photos"
        set itemList to {}
        repeat with i from 3 to count of argv
            set end of itemList to media item id (item i of argv)
        end repeat
        with timeout of theTimeOut seconds
            export itemList to POSIX file thePath with using originals
        end timeout
    end tell
end run
"""


def _tai_theo_lo(ds: list, thang_dir: str) -> None:
    """Tải bản gốc từ iCloud theo LOẠT: 1 lệnh xuất cho LO_TAI ảnh -> Photos tải song song,
    thay vì chờ từng ảnh (~40-60 giây/ảnh). Ảnh đã sửa, hoặc trùng tên file trong cùng loạt,
    để lại cho cách tải từng ảnh (_tai_ban_goc)."""
    os.makedirs(thang_dir, exist_ok=True)
    da_co = {f.split(".")[0] for f in os.listdir(thang_dir)}
    can = [p for p in ds if p.uuid not in da_co and not p.hasadjustments]
    if not can:
        return
    print(f"Tải bản gốc theo loạt: {len(can)} ảnh, mỗi loạt {LO_TAI}...", flush=True)
    xong = 0
    for i in range(0, len(can), LO_TAI):
        lo = can[i:i + LO_TAI]
        theo_ten: dict[str, list] = {}
        for p in lo:
            theo_ten.setdefault(os.path.splitext(p.original_filename or "")[0].lower(), []).append(p)
        tam = os.path.join(thang_dir, f".lo_{i}")
        shutil.rmtree(tam, ignore_errors=True)
        os.makedirs(tam)
        han = 120 + 30 * len(lo)
        try:
            subprocess.run(["osascript", "-e", _XUAT_LO, os.path.abspath(tam), str(han)]
                           + [f"{p.uuid}/L0/001" for p in lo],
                           check=True, capture_output=True, text=True, timeout=han + 30)
        except Exception as e:  # noqa: BLE001
            print(f"  ! loạt {i // LO_TAI + 1} lỗi ({str(getattr(e, 'stderr', '') or e)[:100]})"
                  " -> các ảnh này tải từng ảnh sau", flush=True)
        for f in sorted(os.listdir(tam)):
            goc, duoi = os.path.splitext(f)
            ung = theo_ten.get(goc.lower(), [])
            if len(ung) != 1 or duoi.lower() not in ANH_DUOI:  # bỏ .mov của Live Photo, tên trùng
                continue
            dich = os.path.join(thang_dir, ung[0].uuid + duoi.lower())
            if not os.path.exists(dich):
                os.replace(os.path.join(tam, f), dich)
                xong += 1
        shutil.rmtree(tam, ignore_errors=True)
        print(f"  {min(i + LO_TAI, len(can))}/{len(can)} ảnh đã thử, tải được {xong}", flush=True)


def _doc_chu(path: str, huong) -> str:
    try:
        from osxphotos.text_detection import detect_text

        # Tên viết tay trên nhãn thường chỉ được Vision chấm 0.3 (ngày in thì 1.0) -> lấy từ 0.3;
        # chữ đọc thừa không hại vì nhãn còn phải khớp tên khách có hóa đơn cùng ngày.
        return " ".join(t for t, tin in detect_text(path, huong or None) if tin >= OCR_TIN)
    except Exception:  # noqa: BLE001
        return ""


def _co_xem(p) -> bool:
    """Ảnh đã có bản xem trước trên máy (thường đủ đọc nhãn) -> khỏi tải bản gốc."""
    return any(os.path.exists(x) for x in (p.path_derivatives or []))


def _quet_photos(tu: str, den: str, ocr: bool, tai_goc: bool = False, tai_het: bool = False) -> list[tuple]:
    try:
        import osxphotos
    except ImportError:
        sys.exit("Chưa cài osxphotos. Chạy:  .venv/bin/pip install -r requirements_anh.txt")

    print("Đang mở thư viện Photos (lần đầu có thể mất vài phút)...")
    db = osxphotos.PhotosDB()
    d0 = dt.datetime.fromisoformat(tu)
    d1 = dt.datetime.fromisoformat(den) + dt.timedelta(days=1)
    ds = [p for p in db.photos(from_date=d0, to_date=d1)
          if not (p.ismovie or p.intrash or getattr(p, "screenshot", False))]
    thang_dir = os.path.join(ANH_GOC, tu[:7])
    if tai_goc:
        def chua_co(p):  # mặc định chỉ tải ảnh chưa có gì trên máy; --tai-het: tải cả ảnh có bản xem trước
            g = (p.path_edited if p.hasadjustments else None) or p.path
            return not (g and os.path.exists(g)) and (tai_het or not _co_xem(p))

        _tai_theo_lo([p for p in ds if chua_co(p)], thang_dir)
    rows, thieu = [], 0
    for i, p in enumerate(ds, 1):
        t = p.date.astimezone().replace(tzinfo=None) if p.date.tzinfo else p.date
        cac_chu = [p.title or "", p.description or "", " ".join(p.keywords or []),
                   " ".join(p.albums or []), " ".join(x for x in (p.persons or []) if x != "_UNKNOWN_")]
        goc = (p.path_edited if p.hasadjustments else None) or p.path
        if goc and not os.path.exists(goc):
            goc = None
        if not goc and os.path.isdir(thang_dir):  # bản gốc đã tải lần trước
            goc = next((os.path.join(thang_dir, f) for f in os.listdir(thang_dir)
                        if f.startswith(p.uuid)), None)
        if not goc and tai_goc and (tai_het or not _co_xem(p)):
            goc = _tai_ban_goc(p, thang_dir)
        if not goc:
            thieu += 1
        xem_nho = next((x for x in (p.path_derivatives or []) if os.path.exists(x)), None)
        chu_ocr = ""
        if ocr:
            if goc:
                chu_ocr = _doc_chu(goc, p.orientation)
            elif xem_nho:  # bản xem trước đã xoay đúng chiều; ngưỡng 0,3 vẫn đọc được tên viết tay
                chu_ocr = _doc_chu(xem_nho, None)
            if not chu_ocr:
                try:
                    chu_ocr = " ".join(x[0] for x in p.detected_text(confidence_threshold=OCR_TIN))
                except Exception:  # noqa: BLE001
                    pass
        xem = goc or xem_nho or p.path
        rows.append((p.uuid, "photos", t.date().isoformat(), t.isoformat(timespec="seconds"),
                     p.original_filename, goc or p.path or "", xem or "",
                     " / ".join(x for x in cac_chu if x.strip()), chu_ocr))
        if i % 25 == 0 or i == len(ds):
            print(f"  {i}/{len(ds)} ảnh...", flush=True)
    if thieu:
        print(f"  ! {thieu} ảnh chưa có bản gốc trên máy (đang đọc bản xem trước nhỏ -> khó đọc nhãn)."
              " Chạy lại với --tai-goc để tải bản gốc tháng này từ iCloud.")
    return rows


def _ngay_chup_file(path: str) -> dt.datetime:
    try:
        from PIL import Image

        try:  # đọc HEIC nếu có pillow-heif
            from pillow_heif import register_heif_opener

            register_heif_opener()
        except ImportError:
            pass
        with Image.open(path) as im:
            exif = im.getexif()
            raw = exif.get_ifd(0x8769).get(36867) or exif.get(306)  # DateTimeOriginal / DateTime
            if raw:
                return dt.datetime.strptime(str(raw).strip()[:19], "%Y:%m:%d %H:%M:%S")
    except Exception:  # noqa: BLE001
        pass
    return dt.datetime.fromtimestamp(os.path.getmtime(path))


def _quet_thu_muc(goc: str, tu: str, den: str) -> list[tuple]:
    goc = os.path.expanduser(goc)
    rows = []
    for root, _, files in os.walk(goc):
        for f in sorted(files):
            if os.path.splitext(f)[1].lower() not in ANH_DUOI:
                continue
            path = os.path.join(root, f)
            t = _ngay_chup_file(path)
            ngay = t.date().isoformat()
            if not (tu <= ngay <= den):
                continue
            pid = hashlib.sha1(os.path.abspath(path).encode()).hexdigest()[:20]
            # Tên thư mục con + tên file cũng là "chú thích" (hay chứa tên khách).
            rel = os.path.relpath(path, goc)
            rows.append((pid, "thu_muc", ngay, t.isoformat(timespec="seconds"), f,
                         path, path, os.path.splitext(rel)[0].replace(os.sep, " / "), ""))
    return rows


def cmd_quet(a) -> None:
    y, m = thang(a.thang)
    tu, den = khoang_thang(y, m)
    rows = _quet_thu_muc(a.thu_muc, tu, den) if a.thu_muc else _quet_photos(tu, den, a.ocr, a.tai_goc, a.tai_het)
    conn = ket_noi()
    for r in rows:
        # Giữ nguyên phần đã duyệt nếu quét lại.
        conn.execute(
            "INSERT INTO photos (id, nguon, ngay, thoi_gian, ten_file, duong_dan, anh_xem,"
            " chu_thich, ocr) VALUES (?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET ngay=excluded.ngay, thoi_gian=excluded.thoi_gian,"
            " duong_dan=excluded.duong_dan, anh_xem=excluded.anh_xem,"
            " chu_thich=excluded.chu_thich,"
            " ocr=CASE WHEN excluded.ocr != '' THEN excluded.ocr ELSE photos.ocr END",
            r,
        )
    conn.commit()
    print(f"Đã quét {len(rows)} ảnh trong tháng {m:02d}/{y}.")


# ------------------------- 3. GHÉP -------------------------
def _diem(v: sqlite3.Row, chu: str, so: str) -> tuple[int, str]:
    """Mức khớp giữa chữ trên ảnh và 1 hóa đơn (0 = không khớp)."""
    sdt = v["sdt"] or ""
    if len(sdt) >= 9 and sdt[-9:] in so:
        return 100, f"khớp SĐT {sdt}"
    ma = khong_dau(v["ma_kh"])
    if ma and re.search(rf"\b{re.escape(ma)}\b", chu):
        return 100, f"khớp mã KH {v['ma_kh']}"
    ten = khong_dau(v["ten_kh"])
    if len(ten.split()) >= 2 and re.search(rf"\b{re.escape(ten)}\b", chu):
        return 80, f"khớp tên '{v['ten_kh']}'"
    w = ten.split()
    if len(w) >= 3:  # tên đệm + tên, ví dụ 'thi anh'
        ngan = " ".join(w[-2:])
        if re.search(rf"\b{re.escape(ngan)}\b", chu):
            return 50, f"khớp một phần tên '{ngan}'"
    return 0, ""


# Nhãn nhân viên ghi trên ảnh: "Giang-seo 9/10/26", "Trang-meso mắt 5/10/26", "Triết-co2 nốt ruồi",
# "Quỳnh / pico 7/10/26", "Cheng wei- csd C32•8/10/26". Đầu nhãn = tên (1-3 chữ) + gạch/xuyệt
# + dịch vụ; ngày tìm ở đoạn ngay sau (có thể thiếu -> dùng ngày chụp).
_NHAN_DAU = re.compile(r"([^\W\d_]+(?:\s+[^\W\d_]+){0,2})\s*[-–—/]\s*([^\W\d_][^\s/]*)")
_NHAN_NGAY = re.compile(r"(\d{1,2})\s*[/.\-]\s*(\d{1,2})(?:\s*[/.\-]\s*(\d{2,4}))?")


def doc_nhan(chu: str, nam_mac_dinh: int) -> list[dict]:
    """Tìm các nhãn 'Tên-dịch vụ ngày/tháng/năm' trong chữ đọc được trên ảnh."""
    chu = chu or ""
    dau = list(_NHAN_DAU.finditer(chu))
    ra = []
    for i, m in enumerate(dau):
        het = dau[i + 1].start() if i + 1 < len(dau) else len(chu)
        sau = chu[m.end():min(het, m.end() + 30)]
        n = _NHAN_NGAY.search(sau)
        ngay = None
        if n:
            d, mo, y = n.groups()
            nam = int(y) if y else nam_mac_dinh
            nam = nam + 2000 if nam < 100 else nam
            try:
                ngay = dt.date(nam, int(mo), int(d)).isoformat()
            except ValueError:
                pass
        goc = chu[m.start():m.end() + (n.end() if n else 0)]
        ra.append({"goc": " ".join(goc.split()), "ten": khong_dau(m.group(1)),
                   "ma_dv": khong_dau(m.group(2)).split(" ")[0], "ngay": ngay})
    return ra


def _dv_khop(ma: str, dich_vu: str) -> bool:
    """'seo' ~ 'Trị sẹo rỗ'; 'xx' ~ 'Xóa xăm'; 'tln' ~ 'Triệt lông nách'."""
    tu = khong_dau(dich_vu).split()
    if not ma or not tu:
        return False
    if ma in tu or (len(ma) >= 3 and any(w.startswith(ma) for w in tu)):
        return True
    dau = "".join(w[0] for w in tu)
    return len(ma) >= 2 and ma in dau


def _lech_1(a: str, b: str) -> bool:
    """a, b khác nhau đúng 1 chữ (thay, thêm hoặc bớt)."""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    ngan, dai = sorted((a, b), key=len)
    return any(dai[:i] + dai[i + 1:] == ngan for i in range(len(dai)))


def _khop_nhan(conn, nhan: dict, ngay_anh: str) -> tuple[str | None, int, str]:
    """Khớp 1 nhãn với hóa đơn cùng ngày ghi trên nhãn (không có thì ngày chụp)."""
    ngay, sai = nhan["ngay"] or ngay_anh, ""
    if abs((dt.date.fromisoformat(ngay) - dt.date.fromisoformat(ngay_anh)).days) > 7:
        # OCR đọc sai số ('8/10/16', '3/11 0/26') -> nhãn viết cùng ngày chụp.
        ngay, sai = ngay_anh, f" (ngày trên nhãn đọc ra {nhan['ngay']}, dùng ngày chụp)"
    visits = conn.execute("SELECT * FROM visits WHERE ngay=?", (ngay,)).fetchall()
    w = nhan["ten"].split()
    lech_ngay = (f" (nhãn ghi ngày {ngay})" if ngay != ngay_anh else "") + sai

    def cung_ten(v, k):
        t = khong_dau(v["ten_kh"]).split()
        return len(t) >= k and t[-k:] == w[-k:]

    # Chữ thừa phía trước tên ('Laser Trang') -> thử bớt dần từ trái: 3 chữ, 2 chữ, 1 chữ.
    ung, k = [], len(w)
    for k in range(len(w), 0, -1):
        ung = [v for v in visits if cung_ten(v, k)]
        if ung:
            break
    gan_dung = False
    if not ung and w:
        # Tên KiotViet có đuôi ghi chú ('... Trang KH TU DEN', '... Vy KH7332 GT'), tên nước ngoài
        # đảo thứ tự ('Cheng Wei' ~ 'Wu Cheng Wei') -> tên nằm trong họ tên; OCR sai 1 chữ
        # ('Thann' ~ 'Thanh'). Chỉ "chắc" khi tên nằm trong họ tên VÀ dịch vụ trên nhãn khớp hóa đơn.
        def trong(v):
            return set(w) <= set(khong_dau(v["ten_kh"]).split())

        def lech(v):
            t = khong_dau(v["ten_kh"]).split()
            return bool(t) and len(w[-1]) >= 4 and _lech_1(w[-1], t[-1])

        ung = [v for v in visits if trong(v)]
        if len(ung) == 1 and _dv_khop(nhan["ma_dv"], ung[0]["dich_vu"]):
            return ung[0]["code"], 85, f"nhãn '{nhan['goc']}' khớp tên + dịch vụ {ung[0]['ten_kh']}{lech_ngay}"
        ung, gan_dung = ung or [v for v in visits if lech(v)], True
    if len(ung) > 1:  # trùng tên -> dùng mã dịch vụ trên nhãn để tách
        loc = [v for v in ung if _dv_khop(nhan["ma_dv"], v["dich_vu"])]
        ung = loc or ung
    if len(ung) == 1:
        if k < len(w) or gan_dung:  # chỉ khớp một phần / gần đúng -> chỉ gợi ý, người xác nhận
            return ung[0]["code"], 50, f"nhãn '{nhan['goc']}' khớp một phần tên {ung[0]['ten_kh']}{lech_ngay}"
        return ung[0]["code"], 85, f"nhãn '{nhan['goc']}' khớp {ung[0]['ten_kh']}{lech_ngay}"
    if len(ung) > 1:
        return None, 0, f"nhãn '{nhan['goc']}' trùng {len(ung)} khách{lech_ngay} — người chọn"
    return None, 0, f"nhãn '{nhan['goc']}' không thấy khách tên này trong hóa đơn ngày {ngay}"


def _phut(a: str, b: str) -> float:
    return abs((dt.datetime.fromisoformat(a) - dt.datetime.fromisoformat(b)).total_seconds()) / 60


def ghep_ngay(conn: sqlite3.Connection, ngay: str) -> None:
    visits = conn.execute("SELECT * FROM visits WHERE ngay=?", (ngay,)).fetchall()
    photos = conn.execute(
        "SELECT * FROM photos WHERE ngay=? ORDER BY thoi_gian", (ngay,)
    ).fetchall()
    if not photos:
        return

    # Chia đợt chụp: ảnh cách ảnh trước > DOT_PHUT phút thì sang đợt mới.
    dot, truoc, ket_qua = 0, None, {}
    for p in photos:
        if truoc and _phut(p["thoi_gian"], truoc) > DOT_PHUT:
            dot += 1
        truoc = p["thoi_gian"]
        ket_qua[p["id"]] = {"dot": dot, "hd": None, "do_tin": "chua_ro", "ly_do": "", "diem": 0}

    for p in photos:
        r = ket_qua[p["id"]]
        goc = f"{p['chu_thich']} {p['ocr']} {p['ten_file']}"
        if not visits and not doc_nhan(f"{p['chu_thich']} {p['ocr']}", int(ngay[:4])):
            r.update(do_tin="khong_hd", ly_do="ngày này không có hóa đơn")
            continue
        chu = khong_dau(goc)
        # Các dãy số dạng SĐT (cho phép cách/chấm/gạch: 0909 123 456).
        so = " ".join(re.sub(r"\D", "", x) for x in re.findall(r"\d[\d .\-]{7,}\d", goc))
        diem = sorted(((_diem(v, chu, so), v["code"]) for v in visits), reverse=True)
        (d, ly_do), code = diem[0] if diem else ((0, ""), None)
        if d and (len(diem) == 1 or diem[1][0][0] < d):
            r.update(hd=code, diem=d, ly_do=ly_do, do_tin="chac" if d >= 80 else "goi_y")
            continue
        # Nhãn nhân viên ghi trên ảnh (chỉ có tên + dịch vụ viết tắt + ngày).
        for nhan in doc_nhan(f"{p['chu_thich']} {p['ocr']}", int(ngay[:4])):
            hd, d, ly_do = _khop_nhan(conn, nhan, ngay)
            r["ly_do"] = ly_do
            if hd:
                r.update(hd=hd, diem=d, do_tin="chac" if d >= 80 else "goi_y")
                break

    # Ảnh chưa khớp lấy theo ảnh đã khớp trong cùng đợt (nếu cả đợt chỉ 1 khách).
    for so_dot in {r["dot"] for r in ket_qua.values()}:
        cung = [r for r in ket_qua.values() if r["dot"] == so_dot]
        khach = {r["hd"] for r in cung if r["hd"] and r["diem"] >= 50}
        if len(khach) == 1:
            hd = khach.pop()
            for r in cung:
                if not r["hd"] and r["do_tin"] != "khong_hd":
                    r.update(hd=hd, do_tin="goi_y", ly_do="cùng đợt chụp với ảnh đã khớp tên")

    # Còn lại: nếu cả ngày chỉ 1 khách -> gợi ý khách đó.
    if len(visits) == 1:
        for r in ket_qua.values():
            if not r["hd"] and r["do_tin"] != "khong_hd":
                r.update(hd=visits[0]["code"], do_tin="goi_y", ly_do="cả ngày chỉ có 1 hóa đơn")

    for pid, r in ket_qua.items():
        conn.execute(
            "UPDATE photos SET dot=?, goi_y_hd=?, do_tin=?, ly_do=? WHERE id=?",
            (r["dot"], r["hd"], r["do_tin"], r["ly_do"], pid),
        )


def cmd_ghep(a) -> None:
    y, m = thang(a.thang)
    tu, den = khoang_thang(y, m)
    conn = ket_noi()
    ngays = [r[0] for r in conn.execute(
        "SELECT DISTINCT ngay FROM photos WHERE ngay BETWEEN ? AND ?", (tu, den))]
    for n in ngays:
        ghep_ngay(conn, n)
    conn.commit()
    in_thong_ke(conn, tu, den)


# ------------------------- 5. BÁO CÁO -------------------------
TEN_DO_TIN = {
    "chac": "Chắc chắn (khớp tên/SĐT/mã)",
    "goi_y": "Gợi ý (cần xem lại)",
    "chua_ro": "Chưa rõ (người chọn)",
    "khong_hd": "Ngày không có hóa đơn",
}


NHAN_NGAN = {"chac": "Chắc chắn", "goi_y": "Gợi ý", "chua_ro": "Chưa rõ", "khong_hd": "Không HĐ"}


def in_thong_ke(conn, tu, den) -> None:
    tong = conn.execute("SELECT COUNT(*) FROM photos WHERE ngay BETWEEN ? AND ?",
                        (tu, den)).fetchone()[0]
    print(f"\nTổng {tong} ảnh ({tu} → {den})")
    for k, ten in TEN_DO_TIN.items():
        n = conn.execute("SELECT COUNT(*) FROM photos WHERE ngay BETWEEN ? AND ? AND do_tin=?",
                         (tu, den, k)).fetchone()[0]
        print(f"  {ten:<32} {n:>6}  ({n * 100 / tong if tong else 0:.0f}%)")


def cmd_baocao(a) -> None:
    y, m = thang(a.thang)
    tu, den = khoang_thang(y, m)
    conn = ket_noi()
    in_thong_ke(conn, tu, den)
    q = "SELECT * FROM photos WHERE ngay BETWEEN ? AND ?"
    rows = conn.execute(q, (tu, den)).fetchall()
    da = [r for r in rows if r["xn_hd"] or r["bo_qua"]]
    print(f"\nĐã duyệt {len(da)}/{len(rows)} ảnh "
          f"({len(da) * 100 / len(rows) if rows else 0:.0f}%), bỏ qua (không phải ảnh khách): "
          f"{sum(1 for r in da if r['bo_qua'])}")
    print("\nĐộ chính xác của máy (trên ảnh đã duyệt):")
    for k in ("chac", "goi_y"):
        nhom = [r for r in da if r["do_tin"] == k]
        dung = sum(1 for r in nhom if not r["bo_qua"] and r["xn_hd"] == r["goi_y_hd"])
        if nhom:
            print(f"  {TEN_DO_TIN[k]:<32} đúng {dung}/{len(nhom)} = {dung * 100 / len(nhom):.0f}%")
    kh = conn.execute(
        "SELECT COUNT(DISTINCT v.ma_kh) FROM photos p JOIN visits v ON v.code=p.xn_hd "
        "WHERE p.ngay BETWEEN ? AND ?", (tu, den)).fetchone()[0]
    print(f"\nSố khách đã có ảnh được gắn nhãn: {kh}")


# ------------------------- 6. XUẤT -------------------------
def cmd_xuat(a) -> None:
    y, m = thang(a.thang)
    tu, den = khoang_thang(y, m)
    dich = os.path.expanduser(a.dich)
    conn = ket_noi()
    rows = conn.execute(
        "SELECT p.*, v.ma_kh, v.ten_kh, v.sdt, v.dich_vu FROM photos p "
        "JOIN visits v ON v.code=p.xn_hd WHERE p.ngay BETWEEN ? AND ? AND p.bo_qua=0",
        (tu, den)).fetchall()
    if not rows:
        sys.exit("Chưa có ảnh nào được xác nhận trong tháng này. Chạy bước 'duyet' trước.")

    co_exif = shutil.which("exiftool") is not None
    if not co_exif:
        print("  ! Chưa có exiftool -> nhãn chỉ nằm ở tên thư mục/file, chưa ghi vào trong file."
              " Cài: brew install exiftool")
    db = None
    if any(r["nguon"] == "photos" for r in rows):
        import osxphotos

        db = osxphotos.PhotosDB()
    so = 0
    for r in rows:
        kh = f"{r['ma_kh'] or 'KhachLe'}_{ten_thu_muc(r['ten_kh'])}"
        if r["sdt"]:
            kh += f"_{r['sdt'][-4:]}"
        dv = ten_thu_muc((r["dich_vu"] or "").split(" | ")[0])[:40] or "DichVu"
        thu_muc = os.path.join(dich, kh, f"{r['ngay']}_{dv}")
        os.makedirs(thu_muc, exist_ok=True)
        # Tên file tự mang mã KH + ngày: file có bị tách lẻ vẫn biết của ai.
        tien_to = "_".join(x for x in [r["ma_kh"] or "KhachLe", r["ngay"],
                                       ten_thu_muc(r["loai_anh"] or ""),
                                       r["thoi_gian"][11:].replace(":", "")] if x)
        ten = f"{tien_to}_{r['ten_file']}"
        dst = os.path.join(thu_muc, ten)
        if not os.path.exists(dst):
            if r["duong_dan"] and os.path.exists(r["duong_dan"]):
                shutil.copy2(r["duong_dan"], dst)
            elif db is not None:
                p = db.get_photo(r["id"])
                out = p.export(thu_muc, ten, use_photos_export=True) if p else []
                if not out:
                    print(f"  ! không xuất được {r['ten_file']} ({r['ngay']})")
                    continue
            else:
                print(f"  ! không thấy file {r['duong_dan']}")
                continue
        so += 1
        if co_exif:
            _ghi_nhan_vao_file(dst, r)
        conn.execute("UPDATE photos SET da_xuat=? WHERE id=?", (dst, r["id"]))
        if a.gan_tu_khoa and r["nguon"] == "photos":
            _gan_tu_khoa(r)
    conn.commit()

    # File tổng hợp để mở bằng Excel/Numbers.
    import csv

    csv_path = os.path.join(dich, f"danh_sach_anh_{y}-{m:02d}.csv")
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["ngay", "gio", "ma_kh", "ten_kh", "sdt", "hoa_don", "dich_vu",
                    "loai_anh", "vung", "ghi_chu", "file"])
        for r in conn.execute(
            "SELECT p.*, v.ma_kh, v.ten_kh, v.sdt, v.dich_vu FROM photos p JOIN visits v "
            "ON v.code=p.xn_hd WHERE p.ngay BETWEEN ? AND ? AND p.bo_qua=0 "
            "ORDER BY v.ma_kh, p.thoi_gian", (tu, den)):
            w.writerow([r["ngay"], r["thoi_gian"][11:16], r["ma_kh"], r["ten_kh"], r["sdt"],
                        r["xn_hd"], r["dich_vu"], r["loai_anh"], r["vung"], r["ghi_chu"],
                        r["da_xuat"]])
    print(f"Đã xuất {so} ảnh vào {dich}\nDanh sách: {csv_path}")
    if a.kiot:
        _day_kiot(conn, tu, den)


def chi_muc_kiot(conn, tu: str, den: str) -> list[dict]:
    """Gom ảnh đã xác nhận theo hóa đơn -> chỉ mục gửi KIOT (không có ảnh, chỉ số đếm)."""
    rows = conn.execute(
        "SELECT p.xn_hd, p.loai_anh, p.vung, v.ma_kh, v.sdt, v.ten_kh, v.ngay, v.dich_vu "
        "FROM photos p JOIN visits v ON v.code=p.xn_hd "
        "WHERE p.ngay BETWEEN ? AND ? AND p.bo_qua=0", (tu, den)).fetchall()
    gom: dict[str, dict] = {}
    for r in rows:
        it = gom.setdefault(r["xn_hd"], {
            "hoa_don": r["xn_hd"], "ma_kh": r["ma_kh"], "sdt": r["sdt"], "ten_kh": r["ten_kh"],
            "ngay": r["ngay"], "dich_vu": r["dich_vu"], "so_anh": 0,
            "loai": {"truoc": 0, "trong": 0, "sau": 0}, "vung": [], "link": ""})
        it["so_anh"] += 1
        k = {"trước": "truoc", "trong": "trong", "sau": "sau"}.get(r["loai_anh"] or "")
        if k:
            it["loai"][k] += 1
        if r["vung"] and r["vung"] not in it["vung"]:
            it["vung"].append(r["vung"])
    return list(gom.values())


def _day_kiot(conn, tu: str, den: str) -> None:
    import anhkiot

    items = chi_muc_kiot(conn, tu, den)
    if not items:
        print("Không có hóa đơn nào có ảnh đã xác nhận để đẩy lên KIOT.")
        return
    kq = anhkiot.day_chi_muc(items)
    loi = f", lỗi {len(kq['loi'])}" if kq["loi"] else ""
    print(f"KIOT: thêm {kq['them']}, cập nhật {kq['cap_nhat']} hóa đơn có ảnh{loi}.")
    for e in kq["loi"][:10]:
        print(f"  ! {e.get('hoa_don')}: {e.get('ly_do')}")


def cmd_daykiot(a) -> None:
    y, m = thang(a.thang)
    tu, den = khoang_thang(y, m)
    _day_kiot(ket_noi(), tu, den)


def _nhan(r) -> tuple[list[str], str]:
    """(danh sách từ khóa, câu chú thích) của 1 ảnh đã xác nhận."""
    tu_khoa = [r["ma_kh"], r["sdt"], r["ten_kh"], r["xn_hd"]]
    tu_khoa += (r["dich_vu"] or "").split(" | ")
    tu_khoa += [r["loai_anh"], r["vung"]]
    tu_khoa = list(dict.fromkeys(k for k in tu_khoa if k))
    chu_thich = " · ".join(x for x in [r["ma_kh"], r["ten_kh"], r["sdt"], r["ngay"],
                                       r["dich_vu"], r["loai_anh"], r["vung"], r["ghi_chu"]] if x)
    return tu_khoa, chu_thich


def _ghi_nhan_vao_file(path: str, r) -> None:
    """Ghi từ khóa + chú thích VÀO TRONG file ảnh (chuẩn IPTC/XMP).

    Nhãn đi theo file: tải về, chép sang ổ khác, đẩy lên Google Drive... vẫn còn.
    Lightroom, Bridge, Photos (khi nhập lại), Google Photos đọc được.
    """
    tu_khoa, chu_thich = _nhan(r)
    lenh = ["exiftool", "-q", "-overwrite_original", "-P", "-charset", "iptc=UTF8",
            "-IPTC:CodedCharacterSet=UTF8"]
    for k in tu_khoa:
        lenh += [f"-XMP-dc:Subject-={k}", f"-XMP-dc:Subject+={k}",
                 f"-IPTC:Keywords-={k}", f"-IPTC:Keywords+={k}"]
    lenh += [f"-XMP-dc:Description={chu_thich}", f"-IPTC:Caption-Abstract={chu_thich}",
             f"-EXIF:ImageDescription={chu_thich}", path]
    kq = subprocess.run(lenh, capture_output=True, text=True)
    if kq.returncode != 0:
        print(f"  ! exiftool lỗi với {os.path.basename(path)}: {kq.stderr.strip()[:200]}")


def _gan_tu_khoa(r) -> None:
    """Ghi mã KH, SĐT, tên... vào Từ khóa + Chú thích của ảnh trong Photos.

    Ảnh đồng bộ qua iCloud -> trên iPad/iPhone gõ mã KH hoặc SĐT vào ô Tìm kiếm
    của app Ảnh là ra. Chỉ THÊM, không xóa từ khóa/chú thích cũ.
    """
    try:
        import photoscript

        p = photoscript.Photo(r["id"])
        moi, nhan = _nhan(r)
        cu = list(p.keywords or [])
        p.keywords = cu + [k for k in moi if k not in cu]
        # Chú thích (caption): tìm được trên iPad/iPhone.
        mo_ta = p.description or ""
        if r["ma_kh"] and r["ma_kh"] not in mo_ta:
            p.description = f"{mo_ta}\n{nhan}".strip()
    except Exception as e:  # noqa: BLE001
        print(f"  ! không gắn được từ khóa cho {r['ten_file']}: {e}")


# ------------------------- 4. TRANG DUYỆT -------------------------
CSS = """
:root{--bg:#f6f7f9;--card:#fff;--line:#dde1e6;--muted:#667;--ok:#1a7f37;--warn:#9a6700;--bad:#b42318}
*{box-sizing:border-box}body{margin:0;font:14px/1.4 -apple-system,system-ui,sans-serif;background:var(--bg);color:#111}
header{position:sticky;top:0;background:#fff;border-bottom:1px solid var(--line);padding:10px 16px;z-index:5;display:flex;gap:12px;align-items:center;flex-wrap:wrap}
a{color:#0b57d0;text-decoration:none}main{padding:16px;max-width:1400px;margin:auto}
.days{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px}
.day{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px}
.day b{font-size:16px}.bar{height:6px;background:#eee;border-radius:3px;margin-top:6px;overflow:hidden}.bar i{display:block;height:100%;background:var(--ok)}
.visits{background:#fff;border:1px solid var(--line);border-radius:8px;padding:8px 12px;margin-bottom:12px}
.dot{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px;margin-bottom:14px}
.dot h3{margin:0 0 8px;font-size:14px;display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:10px}
.ph{border:2px solid var(--line);border-radius:8px;padding:6px;background:#fafbfc}
.ph.ok{border-color:var(--ok)}.ph.skip{opacity:.45}
.ph img{width:100%;height:200px;object-fit:contain;background:#222;border-radius:4px;cursor:zoom-in}
.ph select,.ph input{width:100%;margin-top:4px;font-size:13px;padding:3px}
.tag{font-size:11px;padding:1px 6px;border-radius:9px;color:#fff}.chac{background:var(--ok)}.goi_y{background:var(--warn)}.chua_ro,.khong_hd{background:var(--bad)}
.small{font-size:12px;color:var(--muted)}button{cursor:pointer;padding:4px 10px;border-radius:6px;border:1px solid var(--line);background:#fff}
button.p{background:#0b57d0;color:#fff;border-color:#0b57d0}
#zoom{display:none;position:fixed;inset:0;background:rgba(0,0,0,.9);z-index:9;align-items:center;justify-content:center}#zoom img{max-width:96vw;max-height:96vh}
"""

JS = """
async function luu(id, extra){
  const el=document.getElementById('p'+id);
  const d={id, hd:el.querySelector('.hd').value, loai:el.querySelector('.loai').value,
           vung:el.querySelector('.vung').value, ghi:el.querySelector('.ghi').value, ...extra};
  const r=await fetch('/luu',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)});
  if(!r.ok){alert('Lưu lỗi');return}
  const st=(await r.json()).st; el.className='ph '+st;
}
async function caDot(dot){
  const ps=[...document.querySelectorAll('[data-dot="'+dot+'"]')];
  const hd=document.getElementById('dot'+dot).value;
  for(const el of ps){ el.querySelector('.hd').value=hd; await luu(el.dataset.id,{}); }
}
function zoom(src){const z=document.getElementById('zoom');z.querySelector('img').src=src;z.style.display='flex'}
"""


def _trang(title: str, body: str) -> bytes:
    return (f"<!doctype html><html lang=vi><meta charset=utf-8><meta name=viewport "
            f"content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title>"
            f"<style>{CSS}</style><script>{JS}</script><body>{body}"
            f"<div id=zoom onclick=\"this.style.display='none'\"><img></div></body></html>").encode()


def _trang_chu(conn) -> bytes:
    rows = conn.execute(
        "SELECT ngay, COUNT(*) n, SUM(xn_hd IS NOT NULL OR bo_qua=1) d, "
        "SUM(do_tin='chac') c FROM photos GROUP BY ngay ORDER BY ngay").fetchall()
    o = ["<header><b>Duyệt ảnh khách hàng</b><span class=small>Bấm vào một ngày để duyệt."
         " Xanh = đã duyệt hết.</span></header><main><div class=days>"]
    for r in rows:
        pct = (r["d"] or 0) * 100 // r["n"]
        o.append(f"<a class=day href='/ngay?d={r['ngay']}'><b>{r['ngay'][8:]}/{r['ngay'][5:7]}</b>"
                 f"<div class=small>{r['n']} ảnh · đã duyệt {r['d'] or 0}</div>"
                 f"<div class=bar><i style='width:{pct}%'></i></div></a>")
    if not rows:
        o.append("<p>Chưa có ảnh. Chạy <code>python3 anhkhach.py quet YYYY-MM</code> trước.</p>")
    o.append("</div></main>")
    return _trang("Duyệt ảnh khách", "".join(o))


def _trang_ngay(conn, ngay: str) -> bytes:
    visits = conn.execute("SELECT * FROM visits WHERE ngay=? ORDER BY gio", (ngay,)).fetchall()
    photos = conn.execute("SELECT * FROM photos WHERE ngay=? ORDER BY thoi_gian", (ngay,)).fetchall()
    # Nhãn ghi ngày khác ngày chụp (chụp 10/10, nhãn 'Nam-xx 9/10') -> hóa đơn ngày khác cũng phải chọn được.
    co = {v["code"] for v in visits}
    khac = sorted({p[k] for p in photos for k in ("goi_y_hd", "xn_hd") if p[k] and p[k] not in co})
    visits_khac = [conn.execute("SELECT * FROM visits WHERE code=?", (c,)).fetchone() for c in khac]
    visits_khac = [v for v in visits_khac if v]
    ngays = [r[0] for r in conn.execute("SELECT DISTINCT ngay FROM photos ORDER BY ngay")]
    i = ngays.index(ngay) if ngay in ngays else -1
    nav = "<a href='/'>← Tất cả ngày</a>"
    if i > 0:
        nav += f" · <a href='/ngay?d={ngays[i - 1]}'>‹ {ngays[i - 1]}</a>"
    if 0 <= i < len(ngays) - 1:
        nav += f" · <a href='/ngay?d={ngays[i + 1]}'>{ngays[i + 1]} ›</a>"

    def nhan(v):
        ngay_hd = "" if v["ngay"] == ngay else f"{v['ngay'][8:10]}/{v['ngay'][5:7]} "
        return html.escape(f"{ngay_hd}{v['gio']} · {v['ten_kh']} ({v['ma_kh']}) · {v['dich_vu'][:50]}")

    def chon_hd(gia_tri, cls, extra=""):
        s = [f"<select class={cls} {extra}><option value=''>— chọn khách —</option>"]
        for v in visits + visits_khac:
            sel = " selected" if v["code"] == gia_tri else ""
            s.append(f"<option value='{html.escape(v['code'])}'{sel}>{nhan(v)}</option>")
        return "".join(s) + "</select>"

    def chon(ds, gia_tri, cls, goi_y):
        return f"<select class={cls}>" + "".join(
            f"<option value='{html.escape(x)}'{' selected' if x == (gia_tri or '') else ''}>"
            f"{html.escape(x or goi_y)}</option>" for x in ds) + "</select>"

    o = [f"<header><b>Ngày {ngay}</b> {nav}<span class=small>{len(photos)} ảnh · "
         f"{len(visits)} hóa đơn</span></header><main>"]
    o.append("<div class=visits><b>Hóa đơn trong ngày:</b><br>" + (
        "<br>".join(f"<span class=small>{nhan(v)} · HĐ {html.escape(v['code'])}</span>" for v in visits)
        or "<span class=small>Không có hóa đơn ngày này.</span>") + (
        "<br><b>Hóa đơn ngày khác (theo nhãn trên ảnh):</b><br>" + "<br>".join(
            f"<span class=small>{nhan(v)} · HĐ {html.escape(v['code'])}</span>" for v in visits_khac)
        if visits_khac else "") + "</div>")
    dots: dict[int, list] = {}
    for p in photos:
        dots.setdefault(p["dot"] or 0, []).append(p)
    for so, ps in dots.items():
        goi_y = next((p["goi_y_hd"] for p in ps if p["goi_y_hd"]), "")
        o.append(f"<div class=dot><h3>Đợt chụp {ps[0]['thoi_gian'][11:16]}–{ps[-1]['thoi_gian'][11:16]}"
                 f" ({len(ps)} ảnh) {chon_hd(goi_y, 'x', f'id=dot{so}')}"
                 f"<button class=p onclick='caDot({so})'>Áp dụng cho cả đợt</button></h3><div class=grid>")
        for p in ps:
            st = "skip" if p["bo_qua"] else ("ok" if p["xn_hd"] else "")
            hd = p["xn_hd"] or p["goi_y_hd"] or ""
            chu = html.escape((p["chu_thich"] + " " + (p["ocr"] or "")).strip()[:120])
            o.append(
                f"<div class='ph {st}' id='p{p['id']}' data-id='{p['id']}' data-dot='{so}'>"
                f"<img loading=lazy src='/anh/{p['id']}' onclick=\"zoom(this.src)\">"
                f"<div class=small>{p['thoi_gian'][11:16]} · {html.escape(p['ten_file'])} "
                f"<span class='tag {p['do_tin']}'>{NHAN_NGAN.get(p['do_tin'], '')}</span></div>"
                f"<div class=small>{html.escape(p['ly_do'] or '')}{' · ' + chu if chu else ''}</div>"
                f"{chon_hd(hd, 'hd')}{chon(LOAI_ANH, p['loai_anh'], 'loai', '— trước/sau —')}{chon(VUNG, p['vung'], 'vung', '— vùng —')}"
                f"<input class=ghi placeholder='ghi chú (tình trạng, kết quả...)' value='{html.escape(p['ghi_chu'] or '')}'>"
                f"<div style='display:flex;gap:6px;margin-top:6px'>"
                f"<button class=p onclick=\"luu('{p['id']}',{{}})\">✓ Lưu</button>"
                f"<button onclick=\"luu('{p['id']}',{{bo_qua:1}})\">Không phải ảnh khách</button></div></div>")
        o.append("</div></div>")
    o.append("</main>")
    return _trang(f"Ảnh {ngay}", "".join(o))


def _xem_jpeg(pid: str, path: str) -> str:
    """HEIC/TIFF chỉ Safari xem được -> đổi sang JPEG (sips, lưu đệm trong anh_goc/_xem) cho Chrome."""
    if os.path.splitext(path)[1].lower() not in (".heic", ".heif", ".tif", ".tiff"):
        return path
    dich = os.path.join(ANH_GOC, "_xem", re.sub(r"[^\w-]", "", pid) + ".jpg")
    if not os.path.exists(dich):
        os.makedirs(os.path.dirname(dich), exist_ok=True)
        try:
            subprocess.run(["sips", "-s", "format", "jpeg", "-Z", "1600", path, "--out", dich],
                           check=True, capture_output=True, timeout=60)
        except Exception:  # noqa: BLE001
            return path
    return dich


class _Handler(BaseHTTPRequestHandler):
    conn: sqlite3.Connection

    def log_message(self, *a):  # yên lặng
        pass

    def _gui(self, body: bytes, ctype="text/html; charset=utf-8", code=200):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/":
            return self._gui(_trang_chu(self.conn))
        if u.path == "/ngay":
            return self._gui(_trang_ngay(self.conn, parse_qs(u.query).get("d", [""])[0]))
        if u.path.startswith("/anh/"):
            r = self.conn.execute("SELECT anh_xem FROM photos WHERE id=?",
                                  (u.path[5:],)).fetchone()
            if r and r[0] and os.path.exists(r[0]):
                f = _xem_jpeg(u.path[5:], r[0])
                ext = os.path.splitext(f)[1].lower()
                ctype = {".png": "image/png", ".heic": "image/heic", ".heif": "image/heif",
                         ".tif": "image/tiff", ".tiff": "image/tiff"}.get(ext, "image/jpeg")
                with open(f, "rb") as fh:
                    return self._gui(fh.read(), ctype)
            return self._gui(b"", "text/plain", 404)
        self._gui(b"not found", "text/plain", 404)

    def do_POST(self):
        if self.path != "/luu":
            return self._gui(b"", "text/plain", 404)
        d = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        bo_qua = 1 if d.get("bo_qua") else 0
        hd = None if bo_qua else (d.get("hd") or None)
        self.conn.execute(
            "UPDATE photos SET xn_hd=?, bo_qua=?, loai_anh=?, vung=?, ghi_chu=?, xn_luc=? WHERE id=?",
            (hd, bo_qua, d.get("loai") or "", d.get("vung") or "", d.get("ghi") or "",
             dt.datetime.now().isoformat(timespec="seconds"), d.get("id")),
        )
        self.conn.commit()
        st = "skip" if bo_qua else ("ok" if hd else "")
        self._gui(json.dumps({"st": st}).encode(), "application/json")


def cmd_duyet(a) -> None:
    _Handler.conn = ket_noi()
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), _Handler)
    url = f"http://localhost:{PORT}"
    print(f"Trang duyệt đang chạy: {url}  (Ctrl+C để dừng)")
    print("Mở bằng Safari để xem được ảnh HEIC của iPhone.")
    if not a.khong_mo:
        import webbrowser

        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nĐã dừng.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Phân loại ảnh khách hàng theo hóa đơn KiotViet")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("hoadon", help="kéo hóa đơn 1 tháng từ KiotViet")
    s.add_argument("thang")
    s.set_defaults(f=cmd_hoadon)
    s = sub.add_parser("quet", help="đọc ảnh 1 tháng từ Photos (hoặc thư mục)")
    s.add_argument("thang")
    s.add_argument("--thu-muc", help="đọc từ thư mục ảnh thay vì thư viện Photos")
    s.add_argument("--ocr", action="store_true", help="đọc chữ trong ảnh (tên khách viết tay...)")
    s.add_argument("--tai-goc", action="store_true",
                   help="tải bản gốc từ iCloud cho ảnh chưa có bản nào trên máy")
    s.add_argument("--tai-het", action="store_true",
                   help="cùng --tai-goc: tải cả ảnh đã có bản xem trước (chậm, đọc nhãn rõ hơn)")
    s.set_defaults(f=cmd_quet)
    s = sub.add_parser("ghep", help="máy tự gợi ý ảnh nào của khách nào")
    s.add_argument("thang")
    s.set_defaults(f=cmd_ghep)
    s = sub.add_parser("duyet", help="mở trang duyệt trên trình duyệt")
    s.add_argument("--khong-mo", action="store_true", help="không tự mở trình duyệt")
    s.set_defaults(f=cmd_duyet)
    s = sub.add_parser("baocao", help="thống kê kết quả và độ chính xác")
    s.add_argument("thang")
    s.set_defaults(f=cmd_baocao)
    s = sub.add_parser("xuat", help="xuất ảnh đã xác nhận vào thư mục theo khách")
    s.add_argument("thang")
    s.add_argument("dich", help="thư mục đích, ví dụ ~/KhachHang")
    s.add_argument("--gan-tu-khoa", action="store_true", help="thêm từ khóa vào ảnh trong Photos")
    s.add_argument("--kiot", action="store_true", help="đẩy chỉ mục ảnh lên app KIOT")
    s.set_defaults(f=cmd_xuat)
    s = sub.add_parser("daykiot", help="đẩy chỉ mục ảnh (theo hóa đơn) lên app KIOT")
    s.add_argument("thang")
    s.set_defaults(f=cmd_daykiot)
    a = ap.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
