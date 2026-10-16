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
from urllib.parse import parse_qs, quote, urlparse

DB_FILE = os.environ.get("ANH_DB", "anhkhach.db")
PORT = int(os.environ.get("ANH_PORT", "8765"))
GIO_TRUOC, GIO_SAU = 30, 45  # hóa đơn trong [đầu đợt - 30', cuối đợt + 45'] coi là gần giờ chụp
DOT_PHUT = 15  # ảnh cách nhau <= 15 phút coi là cùng một đợt chụp
CHUOI_GIAY = 60  # đợt có nhiều khách: chỉ lan theo chuỗi ảnh chụp liền, 2 ảnh kề nhau cách <= 60 giây
TRUNG_GIAY = 3  # >= 3 ảnh cùng giờ đến từng giây = giờ nhập/lưu, không phải giờ chụp
BO_GIAY = 60  # bộ chụp: mỗi khách chụp mặt 5 kiểu liên tục, 2 ảnh kề nhau cách <= 60 giây
BO_TOI_DA = 7  # bộ <= 7 tư thế (GIÂY khác nhau) có 1 nhãn khớp chắc = 1 khách; dài hơn có thể là 2 khách
# Máy chụp hay lưu 2 bản cùng 1 giây (ảnh nhân đôi): bộ đếm theo số giây khác nhau, không theo số ảnh.
NGHI_GIAY = 30  # bộ dài chỉ 1 nhãn: quãng nghỉ >= 30s sau khi đã đủ BO_DU tư thế = đổi khách (ca thật 31s)
BO_DU = 5  # đủ 1 bộ 5 kiểu rồi mới cắt (quãng nghỉ 49s khi đổi ngồi->nằm giữa bộ 1 khách)
ANH_DUOI = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".tif", ".tiff"}

LOAI_ANH = ["", "trước", "trong", "sau"]
LOAI_NHAN = {"truoc": "trước", "trc": "trước", "sau": "sau"}  # chữ trên nhãn -> ô trước/sau
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
    # Cột thêm sau: DB cũ chưa có -> thêm, giữ nguyên dữ liệu.
    cot = {r[1] for r in conn.execute("PRAGMA table_info(photos)")}
    if "khuon_mat" not in cot:
        conn.execute("ALTER TABLE photos ADD COLUMN khuon_mat TEXT")  # mã người (uuid) app Ảnh nhận ra
    if "ngay_goc" not in cot:
        # 1 = ảnh có EXIF máy chụp (hãng/đời máy) hoặc DateTimeOriginal -> ngày chụp tin được; 0 = không
        # (gửi qua Zalo/Messenger, chụp màn hình...: ngày trên ảnh có thể là NGÀY NHẬN, trễ 1–2 ngày);
        # NULL = chưa quét lại từ khi có cột -> ghép như cũ.
        conn.execute("ALTER TABLE photos ADD COLUMN ngay_goc INTEGER")
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


def _co_xem(p, thang_dir: str | None = None) -> bool:
    """Ảnh đã có bản xem trước trên máy, hoặc ảnh cỡ vừa tai_goc.py --vua đã tải (đủ đọc nhãn)
    -> khỏi tải bản gốc."""
    if thang_dir and os.path.exists(os.path.join(thang_dir, "vua", p.uuid + ".jpg")):
        return True
    return any(os.path.exists(x) for x in (p.path_derivatives or []))


_DONG_MAY = re.compile(r"^\s*(CU-)?KH\w*\s+·\s")  # dòng chú thích do máy ghi: "KH000123 · Tên · SĐT · ..."


def _bo_chu_may_ghi(mo_ta: str | None) -> str:
    """Bỏ các dòng chú thích do chính máy ghi lên app Ảnh (gan_chac / xuat --gan-tu-khoa).
    Không bỏ thì lượt quét sau đọc lại SĐT/mã KH máy vừa ghi -> tự chấm 'chắc' 100 điểm, khoá mãi
    cả ảnh ghép sai (đo 14/10: 2.175 ảnh chắc chỉ nhờ chữ máy tự ghi)."""
    return "\n".join(x for x in (mo_ta or "").split("\n")
                     if x.strip() and not _DONG_MAY.match(x) and "(chưa duyệt)" not in x and x.count(" · ") < 3)


def _la_album_may(ten: str) -> bool:
    """Album máy tạo (xuat --album, album_anh.py): 'KH000123 · Tên', 'DV · ...', tháng 'YYYY-MM'
    — không phải chữ của người."""
    return (bool(_DONG_MAY.match(ten or "")) or (ten or "").startswith("DV · ")
            or bool(re.fullmatch(r"\d{4}-\d{2}", ten or "")))


def _tu_khoa_may_ghi() -> dict[str, set]:
    """Từ khoá máy đã ghi cho từng ảnh (bảng da_gan_chac của gan_chac.py)."""
    try:
        conn = sqlite3.connect(f"file:{DB_FILE}?mode=ro", uri=True)
        ra = {i: set(json.loads(t)) for i, t in conn.execute("SELECT id, tu_khoa FROM da_gan_chac")}
        conn.close()
        return ra
    except Exception:  # noqa: BLE001  (chưa có bảng / DB mới)
        return {}


def _quet_photos(tu: str, den: str, ocr: bool, tai_goc: bool = False, tai_het: bool = False) -> list[tuple]:
    try:
        import osxphotos
    except ImportError:
        sys.exit("Chưa cài osxphotos. Chạy:  .venv/bin/pip install -r requirements_anh.txt")

    da_ghi = _tu_khoa_may_ghi()
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
            return not (g and os.path.exists(g)) and (tai_het or not _co_xem(p, thang_dir))

        _tai_theo_lo([p for p in ds if chua_co(p)], thang_dir)
    rows, thieu = [], 0
    for i, p in enumerate(ds, 1):
        t = p.date.astimezone().replace(tzinfo=None) if p.date.tzinfo else p.date
        tu_cua_may = da_ghi.get(p.uuid, set())
        cac_chu = [p.title or "", _bo_chu_may_ghi(p.description),
                   " ".join(k for k in (p.keywords or []) if k not in tu_cua_may and k != "chưa duyệt"),
                   " ".join(a for a in (p.albums or []) if not _la_album_may(a)),
                   " ".join(x for x in (p.persons or []) if x != "_UNKNOWN_")]
        goc = (p.path_edited if p.hasadjustments else None) or p.path
        if goc and not os.path.exists(goc):
            goc = None
        if not goc and os.path.isdir(thang_dir):  # bản gốc đã tải lần trước
            goc = next((os.path.join(thang_dir, f) for f in os.listdir(thang_dir)
                        if f.startswith(p.uuid)), None)
        if not goc and tai_goc and (tai_het or not _co_xem(p, thang_dir)):
            goc = _tai_ban_goc(p, thang_dir)
        if not goc:
            thieu += 1
        vua = os.path.join(thang_dir, "vua", p.uuid + ".jpg")  # ảnh cỡ vừa do tai_goc.py --vua tải
        xem_nho = next((x for x in (p.path_derivatives or []) if os.path.exists(x)), None) or \
            (vua if os.path.exists(vua) else None)
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
                     " / ".join(x for x in cac_chu if x.strip()), chu_ocr, _ma_nguoi(p),
                     _ngay_goc_photos(p, goc)))
        if i % 25 == 0 or i == len(ds):
            print(f"  {i}/{len(ds)} ảnh...", flush=True)
    if thieu:
        print(f"  ! {thieu} ảnh chưa có bản gốc trên máy (đang đọc bản xem trước nhỏ -> khó đọc nhãn)."
              " Chạy lại với --tai-goc để tải bản gốc tháng này từ iCloud.")
    return rows


def _ma_nguoi(p) -> str:
    """Mã người (uuid nội bộ của app Ảnh) có trên ảnh, cách nhau dấu cách. CHỈ mã — không lưu ảnh
    khuôn mặt, toạ độ hay vector; dữ liệu khuôn mặt không rời app Ảnh."""
    try:
        return " ".join(sorted({pi.uuid for pi in (p.person_info or []) if getattr(pi, "uuid", None)}))
    except Exception:  # noqa: BLE001
        return ""


def _ngay_goc_photos(p, goc: str | None) -> int | None:
    """Ảnh trong Photos có ngày chụp gốc không: hãng/đời máy trong EXIF (app Ảnh đã đọc sẵn) -> 1; không có
    thì đọc DateTimeOriginal ở bản gốc trên máy (nếu có) -> 1/0. Không đọc được thông tin EXIF -> None."""
    try:
        ex = p.exif_info
    except Exception:  # noqa: BLE001
        ex = None
    if ex is not None and (getattr(ex, "camera_make", None) or getattr(ex, "camera_model", None)):
        return 1
    if goc and _ngay_exif(goc):
        return 1
    return 0 if ex is not None else None


def _ngay_exif(path: str) -> dt.datetime | None:
    """DateTimeOriginal (không có thì DateTime) trong EXIF file ảnh; None = không có."""
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
    return None


def _ngay_chup_file(path: str) -> tuple[dt.datetime, int]:
    """(giờ chụp, ngay_goc): EXIF có ngày -> (ngày đó, 1); không -> (giờ sửa file, 0)."""
    t = _ngay_exif(path)
    if t:
        return t, 1
    return dt.datetime.fromtimestamp(os.path.getmtime(path)), 0


def _quet_thu_muc(goc: str, tu: str, den: str) -> list[tuple]:
    goc = os.path.expanduser(goc)
    rows = []
    for root, _, files in os.walk(goc):
        for f in sorted(files):
            if os.path.splitext(f)[1].lower() not in ANH_DUOI:
                continue
            path = os.path.join(root, f)
            t, goc_ngay = _ngay_chup_file(path)
            ngay = t.date().isoformat()
            if not (tu <= ngay <= den):
                continue
            pid = hashlib.sha1(os.path.abspath(path).encode()).hexdigest()[:20]
            # Tên thư mục con + tên file cũng là "chú thích" (hay chứa tên khách).
            rel = os.path.relpath(path, goc)
            rows.append((pid, "thu_muc", ngay, t.isoformat(timespec="seconds"), f,
                         path, path, os.path.splitext(rel)[0].replace(os.sep, " / "), "", "", goc_ngay))
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
            " chu_thich, ocr, khuon_mat, ngay_goc) VALUES (?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET ngay=excluded.ngay, thoi_gian=excluded.thoi_gian,"
            " duong_dan=excluded.duong_dan, anh_xem=excluded.anh_xem,"
            " chu_thich=excluded.chu_thich,"
            " ocr=CASE WHEN excluded.ocr != '' THEN excluded.ocr ELSE photos.ocr END,"
            " khuon_mat=CASE WHEN excluded.khuon_mat != '' THEN excluded.khuon_mat ELSE photos.khuon_mat END,"
            " ngay_goc=COALESCE(excluded.ngay_goc, photos.ngay_goc)",
            tuple(r) + (None,) * (11 - len(r)),  # dòng 10 cột (mã cũ/test) -> ngay_goc NULL
        )
    conn.commit()
    print(f"Đã quét {len(rows)} ảnh trong tháng {m:02d}/{y}.")


# ------------------------- 3. GHÉP -------------------------
# Tên KiotViet hay kèm ghi chú: 'X (KH TỰ ĐẾN)', 'X (EM BS LƯƠNG)', 'X (KH7332 GT)', 'X KH7332 GT',
# 'X BS LUONG' (soát 04-08/2026: 848/2.570 HĐ). Ghi chú làm hỏng so tên: 'Vương' lệch 1 chữ với
# đuôi '... luong' của '(EM BS LƯƠNG)' -> so tên luôn qua _tu_ten_kh (đã bỏ ghi chú).
_GHI_CHU_TEN = {"kh", "gt", "bs", "ktv", "mkt", "tvv", "hotline", "nq", "cskh"}
_TRUOC_BS = {"em", "chau", "nq", "nguoi", "quen"}  # 'em/cháu/người quen BS ...'


def _tu_goc(s: str) -> list[tuple[str, str]]:
    """'Lê Dũng' -> [('lê', 'le'), ('dũng', 'dung')] (chữ còn dấu, chữ không dấu)."""
    ra = []
    for g in re.findall(r"[^\W_]+", unicodedata.normalize("NFC", s or "").lower()):
        k = khong_dau(g)
        if k and " " not in k:
            ra.append((g, k))
    return ra


# Ghi chú sau gạch trong tên KiotViet ('TRẦN BẢO DUY - CON C. TRÚC', 'X (KH8039 GT) -MẪU NÁM 5') (CEO 16/10):
# phần sau gạch có chữ ghi chú/số -> bỏ. Chữ yếu (em/chị/anh/cô/chú/bạn: có thể là tên ghép có gạch) chỉ tính khi
# là chữ đầu phần sau gạch VÀ theo sau còn chữ ('anh trai', 'chị Hương').
_GHI_CHU_GACH = _GHI_CHU_TEN | {"con", "me", "ba", "bo", "chong", "vo", "mau", "khach", "chau", "nguoi", "quen",
                                "gioi", "thieu", "ban", "cu", "moi", "sale", "nv", "tu", "den"}
_GHI_CHU_GACH_YEU = {"em", "chi", "anh", "co", "chu", "di", "cau", "bac", "ong"}


def _cat_gach(s: str) -> str:
    """Cắt tên tại gạch ('-', '–', '—') mà phần sau có chữ ghi chú hoặc số; không thì giữ (tên ghép có gạch)."""
    for m in re.finditer(r"\s*[-–—]+\s*", s):
        if m.start() == 0:
            continue
        sau = khong_dau(s[m.end():]).split()
        if not sau:
            return s[:m.start()]
        if (any(x in _GHI_CHU_GACH or re.search(r"\d", x) for x in sau)
                or (sau[0] in _GHI_CHU_GACH_YEU and len(sau) >= 2)):
            return s[:m.start()]
    return s


def _tu_ten_kh(ten: str) -> list[tuple[str, str]]:
    """Tên KiotViet bỏ ghi chú: ngoặc '(...)' (kể cả thiếu ngoặc đóng), phần sau gạch có chữ ghi chú/số
    ('- CON C. TRÚC', '-MẪU NÁM 5') và đuôi 'KH7332 GT', 'GT', 'BS LUONG', 'EM BS LƯƠNG'... Luôn giữ ít nhất chữ
    đầu; bỏ hết thì trả tên gốc."""
    tu = _tu_goc(_cat_gach(re.sub(r"\([^)]*\)?", " ", ten or "")))
    for i in range(1, len(tu)):
        k = tu[i][1]
        if k in _GHI_CHU_TEN or re.fullmatch(r"(kh)?\d+(gt)?", k):
            j = i
            if k == "bs":
                while j > 1 and tu[j - 1][1] in _TRUOC_BS:
                    j -= 1
            tu = tu[:j]
            break
    if len(tu) > 2 and [k for _, k in tu[-2:]] == ["gan", "spa"]:  # 'CÔ THẢO GẦN SPA' -> 'cô thảo' (cụm cuối)
        tu = tu[:-2]
    return tu or _tu_goc(ten)


# Họ phổ biến (CEO 16/10): tên ĐÚNG 2 chữ mà chữ cuối là họ ('Vy Nguyễn' = ghi kiểu Tên Họ) -> chữ đầu là tên gọi.
# Không gồm chữ vừa là họ vừa là tên (mai, hà, lý, thái, tăng...).
# CEO 16/10: bỏ các chữ vừa là họ vừa hay là TÊN GỌI (Hoàng, Dương, Trường/Trương, Lâm, Vũ, Lương, Trinh)
HO_PHO_BIEN = {"nguyen", "tran", "le", "pham", "huynh", "phan", "vo", "dang", "bui", "do", "ngo",
               "dinh", "doan", "cao", "ta"}


# Họ Việt ĐẦY ĐỦ — chỉ để NHẬN DIỆN tên Việt (khác HO_PHO_BIEN dùng để đảo 'Tên Họ'). Gồm cả chữ vừa là họ vừa là
# tên (hoàng, mai, hà...) và 'văn', 'thị': tên có 1 chữ này = tên Việt (ghi không dấu), không coi là tên Tây.
HO_VIET = HO_PHO_BIEN | {
    "hoang", "duong", "vu", "ho", "ly", "lam", "luong", "trinh", "mai", "ha", "truong", "trieu", "thai", "tang",
    "quach", "lu", "luu", "la", "khuc", "kieu", "ton", "chau", "dao", "diep", "giang", "han", "hua", "kha", "khong",
    "lac", "lieu", "mac", "nghiem", "nong", "ong", "phung", "quan", "tieu", "thach", "thieu", "tong", "u", "van",
    "thi", "au", "banh", "bach", "cu", "dam", "dieu", "hau", "hong", "khuu", "kim", "lai", "lo", "ma",
    "man", "ninh", "on", "phi", "phuong", "quang", "sam", "son", "tat", "thanh", "thao", "tiet", "to", "tra",
    "trac", "vien", "vuong", "vi", "yen"}
# Âm tiết tiếng Việt viết không dấu: phụ âm đầu + vần (1–3 nguyên âm) + phụ âm cuối. Tên Tây hầu hết có ít nhất 1 chữ
# KHÔNG phải âm tiết Việt ('robert', 'luke', 'sharon') -> dùng để chắc chắn không nhận nhầm tên Việt ghi không dấu.
_AM_TIET_VIET = re.compile(r"(ngh|ng|nh|ch|gh|gi|kh|ph|qu|th|tr|[bcdghklmnpqrstvx])?[aeiouy]{1,3}(ng|nh|ch|[cmnpt])?")


def _la_ten_tay(tu: list) -> bool:
    """Tên kiểu nước ngoài (CEO 16/10): >= 2 chữ, không chữ nào có dấu tiếng Việt, không chữ nào là họ Việt
    (HO_VIET), và có ít nhất 1 chữ không phải âm tiết Việt ('ROBERT HAWKINS'). Tên Tây: tên gọi = chữ ĐẦU."""
    if len(tu) < 2:
        return False
    g = [x[0] if isinstance(x, tuple) else x for x in tu]
    k = [x[1] if isinstance(x, tuple) else khong_dau(x) for x in tu]
    return (not _co_dau(g) and not any(x in HO_VIET for x in k)
            and any(not _AM_TIET_VIET.fullmatch(x) for x in k))


def _hoan_vi_goi(tu: list) -> list[int]:
    """Thứ tự chữ để tên gọi đứng cuối: đúng 2 chữ, chữ cuối là họ phổ biến -> đảo ('vy nguyen' -> 'nguyen vy');
    tên Tây (_la_ten_tay) -> chữ đầu xuống cuối ('robert hawkins' -> 'hawkins robert'; tên cuối gốc ở vị trí -2)."""
    n = len(tu)
    if n == 2:
        k = [x[1] if isinstance(x, tuple) else khong_dau(x) for x in tu]
        if k[1] in HO_PHO_BIEN:
            return [1, 0]
    if _la_ten_tay(tu):
        return list(range(1, n)) + [0]
    return list(range(n))


def _thu_tu_goi(tu: list, hv: list[int] | None = None) -> list:
    """Đưa tên về thứ tự 'họ ... tên gọi' (tên gọi = chữ cuối) theo _hoan_vi_goi (hv: dùng hoán vị đã tính, để
    w/wg của 1 nhãn đảo giống nhau). Nhận list chữ (str) hoặc (chữ dấu, chữ không dấu). Dùng chung cho khách lẫn nhãn."""
    hv = _hoan_vi_goi(tu) if hv is None else hv
    return [tu[i] for i in hv] if len(hv) == len(tu) else list(tu)


def _dao_ten(ten: str) -> bool:
    """Tên khách đã đổi thứ tự trong _tu_ten_goi ('Tên Họ' 2 chữ, hoặc tên Tây) -> nhãn cũng đảo theo."""
    tu = _tu_ten_kh(ten)
    return _hoan_vi_goi(tu) != list(range(len(tu)))


def _mot_chu_khop(x: str, t: list[str], tay: bool, gan=None) -> bool:
    """Nhãn 1 chữ x khớp tên khách t (không dấu, thứ tự tên gọi): = tên gọi (chữ cuối); tên Tây: cả tên cuối gốc
    (bỏ chữ 1 ký tự cuối tên: 'JMITH DAVID A' -> tên cuối 'david')."""
    f = gan or (lambda a, b: a == b)
    if not t:
        return False
    if f(x, t[-1]):
        return True
    dai = [y for y in t[:-1] if len(y) > 1]
    return tay and bool(dai) and f(x, dai[-1])


def _duoi_tay(w: list[str], t: list[str]) -> bool:
    """Tên Tây (t đã xoay chữ đầu xuống cuối): nhãn >= 2 chữ khớp đuôi theo THỨ TỰ GỐC ('Cheng Wei' ~ 'WU CHENG WEI')."""
    goc = t[-1:] + t[:-1]
    return len(w) >= 2 and len(goc) >= len(w) and goc[-len(w):] == w


def _tu_ten_goi(ten: str) -> list[tuple[str, str]]:
    """_tu_ten_kh theo thứ tự tên gọi (_thu_tu_goi): chữ cuối luôn là tên gọi."""
    return _thu_tu_goi(_tu_ten_kh(ten))


def _bi_danh(ten: str) -> list[list[str]]:
    """Tên gọi trong ngoặc ('X (LISA)') = ngoặc không có chữ ghi chú/số -> [['lisa']]."""
    ra = []
    for trong in re.findall(r"\(([^)]*)\)?", ten or ""):
        tu = [k for _, k in _tu_goc(trong)]
        if tu and not any(k in _GHI_CHU_TEN or k in ("tu", "den") or re.search(r"\d", k) for k in tu):
            ra.append(tu)
    return ra


def _dau(g: str) -> tuple:
    """Dấu của 1 chữ, không kể vị trí bỏ dấu ('hoà' = 'hòa'; 'dũng' != 'dung')."""
    return g.count("đ"), "".join(sorted(c for c in unicodedata.normalize("NFD", g)
                                        if unicodedata.category(c) == "Mn"))


def ten_sach(ten: str) -> str:
    """'Lê Thị Dung (BS LƯƠNG)' -> 'le thi dung'."""
    return " ".join(k for _, k in _tu_ten_kh(ten))


def _diem(v: sqlite3.Row, chu: str, so: str) -> tuple[int, str]:
    """Mức khớp giữa chữ trên ảnh và 1 hóa đơn (0 = không khớp)."""
    sdt = v["sdt"] or ""
    if len(sdt) >= 9 and sdt[-9:] in so:
        return 100, f"khớp SĐT {sdt}"
    ma = khong_dau(v["ma_kh"])
    # Mã KH ngắn/toàn số ('08', '3') trùng ngày trên nhãn ('19/08/26') -> chỉ tin mã có chữ và đủ dài (KH000123)
    ma_tin = len(ma.replace(" ", "")) >= 4 and re.search(r"[a-z]", ma) and re.search(r"\d", ma)
    if ma_tin and re.search(rf"\b{re.escape(ma)}\b", chu):
        return 100, f"khớp mã KH {v['ma_kh']}"
    ten = ten_sach(v["ten_kh"])
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
# Nhãn KHÔNG gạch: "Cheng wei 13/7/26", "Thanh seo 13/7/26" — tên (1-3 chữ) + ngày đủ năm.
_NHAN_KHONG_GACH = re.compile(
    r"(?<![^\W\d_])([^\W\d_]+(?:[\s+]+[^\W\d_]+){0,5})[\s+]+(\d{1,2})\s*[/.\-]\s*(\d{1,2})\s*[/.\-]\s*(\d{2,4})(?!\d)")
# Chữ chung trên ảnh/sản phẩm: có mặt trong đoạn tên -> không phải nhãn ('Doctor Laser 1/10/26', 'HSD').
_KHONG_PHAI_TEN = {"doctor", "laser", "dr", "clinic", "spa", "bs", "bac", "si", "ngay", "date", "hsd", "nsx",
                   "exp", "mfg", "lot", "het", "phong", "kham", "tp", "hcm", "sdt", "tel", "dt", "so"}
# Chữ dịch vụ thường gặp trong nhãn không gạch ('Thanh seo', 'Lan nách'); 'ha' trùng tên Hà -> bỏ.
_TU_DV_THEM = {"nach", "not", "ruoi", "dien", "di", "peel", "tln", "tl", "mat"}
# Mã trùng tên người/chữ thường -> không coi là dịch vụ trong nhãn KHÔNG gạch ('Tâm Như', 'Chi Như', 'Nhân',
# 'Hà', 'the'); nhãn có gạch thì chữ sau gạch vẫn là mã.
_KHONG_GACH_BO = {"ha", "the", "nhu", "nhan"}
XUNG_HO = {"a", "c", "chi", "anh", "em", "co", "chu", "be"}
# Mã dịch vụ chung/rác trên nhãn ('Lan-tri', 'Mai-tiem', 'test'): khớp thì vẫn dùng để chọn HĐ,
# không khớp thì coi như nhãn không ghi dịch vụ (không hạ điểm 'lệch dịch vụ').
DV_CHUNG = {"tri", "tiem", "test", "giai", "kham", "dieu", "dtri", "lam"}
# Động từ chung đứng trước dịch vụ ('xoá nốt ruồi', 'xoá nhăn'): lấy mã từ chữ sau; tự nó không khớp
# dịch vụ nào ('xoa' không được khớp 'Xóa xăm').
DONG_TU_DV = {"xoa"}


def _dv_chung(ma: str) -> bool:
    """Nhãn coi như không ghi dịch vụ: trống, mã chung, động từ chung, mã 1 chữ ('c', 'M')."""
    return not ma or len(ma) < 2 or ma in DV_CHUNG or ma in DONG_TU_DV


def _nhan_khong_gach(chu: str) -> list[dict]:
    ra = []
    for m in _NHAN_KHONG_GACH.finditer(chu):
        tu = _tu_goc(m.group(1))
        if not tu or any(k in _KHONG_PHAI_TEN for _, k in tu):
            continue
        d, mo, y = m.group(2, 3, 4)
        nam = int(y) + (2000 if len(y) == 2 else 0)
        try:
            ngay = dt.date(nam, int(mo), int(d))
        except ValueError:
            continue
        if nam < 2015:  # ngày sinh, không phải ngày chụp
            continue
        dv = (set(MA_DV) | set(MA_DV_OCR) | _TU_DV_THEM) - _KHONG_GACH_BO
        ten, ma_dv, loai = [], "", ""
        for g, k in tu:
            if k in LOAI_NHAN:
                loai = loai or LOAI_NHAN[k]
            elif k in dv:
                ma_dv = ma_dv or k
            elif not ma_dv and not loai:
                ten.append((g, k))
        if not ten or all(k in XUNG_HO for _, k in ten):
            continue
        # > 3 chữ trước ngày (CEO 16/10 lần 5: 'Phan mỹ tiên Csd mụn+ peel 9-10-2023'): chỉ nhận khi có mã dịch vụ
        # và phần tên <= 3 chữ đứng đầu; không thì như cũ (3 chữ cuối trước ngày).
        if len(tu) > 3 and (not ma_dv or len(ten) > 3):
            tu = tu[-3:]
            ten, ma_dv, loai = [], "", ""
            for g, k in tu:
                if k in LOAI_NHAN:
                    loai = loai or LOAI_NHAN[k]
                elif k in dv:
                    ma_dv = ma_dv or k
                elif not ma_dv and not loai:
                    ten.append((g, k))
            if not ten or all(k in XUNG_HO for _, k in ten):
                continue
        if not ma_dv:  # mã dịch vụ ghi SAU ngày ('Trần Thái Triều Châu 20/7/2022 prp mặt') — CEO 16/10 lần 5
            for k in khong_dau(chu[m.end():m.end() + 25]).split()[:3]:
                if k in LOAI_NHAN:
                    loai = loai or LOAI_NHAN[k]
                elif k in dv:
                    ma_dv = k
                    break
        # Có mã dịch vụ nhận ra được ('Minh Lý Pico 23-11-2023') = nhãn thật của nhân viên -> xử như nhãn có gạch.
        ro = ma_dv in MA_DV or ma_dv in MA_DV_OCR
        ra.append({"goc": " ".join(m.group(0).split()), "ten": " ".join(k for _, k in ten),
                   "ten_goc": " ".join(g for g, _ in ten), "ma_dv": ma_dv, "ngay": ngay.isoformat(),
                   "loai": loai, "gach": ro})
    return ra


def doc_nhan(chu: str, nam_mac_dinh: int) -> list[dict]:
    """Tìm các nhãn 'Tên-dịch vụ ngày/tháng/năm' trong chữ đọc được trên ảnh. Không có nhãn gạch nào
    thì nhận thêm dạng 'Tên ngày/tháng/năm' (gach=False: ghép chỉ cho gợi ý trừ khi khớp đủ họ tên)."""
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
        # Chữ dịch vụ trước ngày: 'sau filler mắt', 'meso trước' -> 'sau'/'trước' là loại ảnh, không phải mã.
        tu = khong_dau(m.group(2) + " " + sau[:n.start() if n else 0]).split()
        loai = next((LOAI_NHAN[w] for w in tu if w in LOAI_NHAN), "")
        tu = [w for w in tu if w not in LOAI_NHAN]
        if len(tu) > 1 and tu[0] in DONG_TU_DV:  # 'xoá nốt ruồi' -> 'not', 'xoá nhăn' -> 'nhan'
            tu = tu[1:]
        ten = _tu_goc(m.group(1))
        ma_dv = " ".join(tu[:2]) if " ".join(tu[:2]) in MA_DV else (tu[0] if tu else "")  # 'peel nhu'
        ra.append({"goc": " ".join(goc.split()), "ten": " ".join(k for _, k in ten),
                   "ten_goc": " ".join(g for g, _ in ten),
                   "ma_dv": ma_dv, "ngay": ngay, "loai": loai, "gach": True})
    return _danh_dau_quan_he(chu, ra or _nhan_khong_gach(chu))


# Nhãn ghi NGƯỜI NHÀ (CEO 16/10 lần 4, ca 7C1078AF 'Con Chị Châu'): chữ quan hệ đứng trước (xưng hô +) tên -> người
# khác, không phải khách <tên>. 'em' chỉ tính khi theo sau là xưng hô ('em chị Lan'; 'Em Lan' là xưng hô của chính khách).
# 'Võ'/'Châu' là họ/tên, 'vợ'/'cháu' mới là quan hệ -> chỉ tính khi theo sau là XƯNG HÔ.
QUAN_HE = {"con", "chồng", "vợ", "mẹ", "ba", "bố", "cháu", "bạn", "em"}


def _la_quan_he(g: str, sau: str | None) -> bool:
    """Chữ g (còn dấu, chữ thường) đứng trước tên là chữ quan hệ; sau = chữ kế tiếp (không dấu) nếu có."""
    # CEO 16/10 lần 4: chữ quan hệ + xưng hô (chị/anh/c/a...) + tên ('Con Chị Châu', 'Bạn chị Hằng'); thiếu xưng hô
    # ('Bạn. Báo', 'Võ An') thì không đoán là người nhà.
    return sau is not None and sau in XUNG_HO and khong_dau(g) in {khong_dau(x) for x in QUAN_HE}


def _danh_dau_quan_he(chu: str, ds: list[dict]) -> list[dict]:
    for n in ds:
        w, wg = n["ten"].split(), n["ten_goc"].split()
        rel = None
        if len(w) >= 2 and len(wg) == len(w) and _la_quan_he(wg[0].lower(), w[1]):
            rel, w, wg = w[0], w[1:], wg[1:]
        else:  # chữ quan hệ nằm ngay trước phần nhãn đọc được ('Con' + 'Chị Châu- csd')
            goc = unicodedata.normalize("NFC", chu or "").lower()
            i = goc.find(unicodedata.normalize("NFC", n["goc"]).lower().split()[0]) if n["goc"].split() else -1
            truoc = re.findall(r"[^\W\d_]+", goc[:i]) if i > 0 else []
            if truoc and w and _la_quan_he(truoc[-1], w[0]):
                rel = khong_dau(truoc[-1])
        if rel:
            n.update(quan_he=rel, ten=" ".join(w), ten_goc=" ".join(wg))
    return ds


def _nap_ma_dv() -> tuple[dict, dict]:
    """Bảng mã viết tắt -> chữ trong tên dịch vụ KiotViet (ma_dich_vu.json, nhân viên sửa được)."""
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ma_dich_vu.json"),
                  encoding="utf-8") as f:
            b = json.load(f)
    except (OSError, ValueError):
        return {}, {}
    return ({k: [khong_dau(x) for x in v["khop"]] for k, v in b.items() if not k.startswith("_")},
            b.get("_ocr_sai", {}))


MA_DV, MA_DV_OCR = _nap_ma_dv()


def _dv_khop(ma: str, dich_vu: str) -> bool:
    """'seo' ~ 'Trị sẹo rỗ'; 'xx' ~ 'Xóa xăm'; 'tln' ~ 'Triệt lông nách'; 'co2' ~ 'Laser Fractional'
    (bảng ma_dich_vu.json)."""
    # 'COMBO TRIỆT LÔNG ( BH 2 NĂM )': 'năm' bảo hành không phải 'nám' (pico).
    tu = re.sub(r"\b(?:bh|bao hanh)(?:\s*\d+\s*(?:nam|thang))?\b", " ", khong_dau(dich_vu)).split()
    if not ma or len(ma) < 2 or ma in DONG_TU_DV or not tu:
        return False
    ma = MA_DV_OCR.get(ma, ma)
    chuoi = f" {' '.join(tu)} "
    if any(f" {k} " in chuoi or (len(k) >= 4 and f" {k}" in chuoi) for k in MA_DV.get(ma, [])):
        return True
    if ma in tu or (len(ma) >= 3 and any(w.startswith(ma) for w in tu)):
        return True
    dau = "".join(w[0] for w in tu)
    return len(ma) >= 2 and ma in dau


def _dv_gan_dung(ma: str, dich_vu: str) -> bool:
    """Mã OCR đọc sai 1 chữ so với đúng 1 mã trong bảng ('picc'~'pico', 'cad'~'csd') rồi khớp dịch vụ.
    Chỉ dùng để KHÔNG hạ điểm 'lệch dịch vụ', không bao giờ nâng lên chắc."""
    if not ma or len(ma) < 3 or ma in MA_DV:
        return False
    k = [k for k in MA_DV if _lech_1(ma, k)]
    return len(k) == 1 and _dv_khop(k[0], dich_vu)


def _lech_1(a: str, b: str) -> bool:
    """a, b khác nhau đúng 1 chữ (thay, thêm hoặc bớt)."""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    ngan, dai = sorted((a, b), key=len)
    return any(dai[:i] + dai[i + 1:] == ngan for i in range(len(dai)))


# Luật tên (Lượng 16/10): nhãn ghi TÊN GỌI. Nhãn >= 2 chữ ('Ngọc Anh') phải khớp ĐÚNG các chữ cuối họ tên
# ('Trần Ngọc Anh'), không khớp 'Nguyễn Thị Anh', không rơi xuống khớp 1 chữ 'Anh'. Chỉ được bớt chữ thừa
# bên trái khi chữ đó không phải tên: chữ chung ('laser', 'doctor'), xưng hô, mã dịch vụ, chữ ghi chú.
_CHU_THUA_TEN = ((_KHONG_PHAI_TEN | XUNG_HO | set(LOAI_NHAN) | DV_CHUNG | DONG_TU_DV | _TU_DV_THEM
                  | _GHI_CHU_TEN | set(MA_DV) | set(MA_DV_OCR) | {"ro"}) - _KHONG_GACH_BO)  # 'rỗ' (sẹo rỗ)


def _bot_duoc(w: list[str], k: int) -> bool:
    """Nhãn w được bớt còn k chữ cuối: nhãn 1 chữ / không bớt -> được; bớt thì các chữ bỏ đi phải là chữ chung."""
    return k == len(w) or len(w) < 2 or all(x in _CHU_THUA_TEN for x in w[:len(w) - k])


def _ten_ngoai(wg: list[str], tg_kh: list[str]) -> bool:
    """Tên kiểu nước ngoài/không dấu ('Cheng Wei' ~ 'Wu Cheng Wei'): cả nhãn lẫn tên khách không có chữ
    tiếng Việt có dấu -> được khớp 'tên nằm trong họ tên' (đảo thứ tự). Tên Việt thì phải khớp đuôi."""
    return not _co_dau(wg) and not _co_dau(tg_kh)


GOI_NGAY = 180  # buổi theo gói: tìm HĐ cùng dịch vụ của khách cùng tên trong 180 ngày trước ngày chụp


def _hd_truoc(conn, ngay_anh: str, bo_nho: dict | None) -> list[dict]:
    """HĐ trong GOI_NGAY ngày TRƯỚC ngày chụp (không gồm ngày chụp), mỗi HĐ kèm chữ tên đã làm sạch
    (còn dấu). Nạp 1 lần cho mỗi ngày chụp (bo_nho do ghep_ngay giữ), dùng chỉ mục visits_ngay."""
    if bo_nho is not None and ngay_anh in bo_nho:
        return bo_nho[ngay_anh]
    d = dt.date.fromisoformat(ngay_anh)
    ds = [dict(v, tg=_tu_ten_goi(v["ten_kh"])) for v in conn.execute(
        "SELECT * FROM visits WHERE ngay BETWEEN ? AND ?",
        ((d - dt.timedelta(days=GOI_NGAY)).isoformat(), (d - dt.timedelta(days=1)).isoformat()))]
    if bo_nho is not None:
        bo_nho[ngay_anh] = ds
    return ds


def _co_dau(wg: list[str]) -> bool:
    """Tên nhãn còn ít nhất 1 chữ có dấu (OCR không làm mất hết dấu)."""
    return any(_dau(g) != (0, "") for g in wg)


def _ten_goi_khop(wg: list[str], tg: list[tuple[str, str]]) -> bool:
    """Luật gói: tên nhãn (còn dấu) = ĐÚNG phần cuối họ tên đã làm sạch, đủ số chữ, cùng chữ VÀ cùng dấu
    ('hoà' = 'hòa'; 'Thu' != 'Thư', 'Hiến' != 'Hiền'). Không nhận khớp một phần ('Như' ~ 'Đinh Như Hằng')."""
    n = len(wg)
    if not n or len(tg) < n:
        return False
    if n == 1 and _la_ten_tay(tg) and khong_dau(wg[0]) == tg[-2][1] and _dau(wg[0]) == _dau(tg[-2][0]):
        return True  # tên Tây: nhãn 1 chữ = tên cuối gốc
    return all(khong_dau(a) == k and _dau(a) == _dau(g) for a, (g, k) in zip(wg, tg[-n:]))


# Chữ chung trong bảng mã (khớp nhiều dịch vụ): luật gói không nhận khớp CHỈ qua chữ này
# ('pico' ~ 'COMBO ĐIỀU TRỊ THÂM MẮT (TIÊM HA + MESO)' qua 'thâm').
_TU_DV_YEU = {"pico": {"tham", "nam"}}


def _vi_tri_dv(ma: str, tu: list[str], yeu: set = frozenset(), du: bool = True) -> int | None:
    """Vị trí chữ đầu tiên trong dòng dịch vụ (đã bỏ dấu, tách chữ) khớp mã; None = không khớp.
    du=False: chỉ xét chữ trong bảng mã (không xét mã viết thẳng/chữ cái đầu)."""
    chuoi = f" {' '.join(tu)} "
    vt = []
    for k in MA_DV.get(ma, []):
        if k in yeu:
            continue
        i = chuoi.find(f" {k} ")
        if i < 0 and len(k) >= 4:
            i = chuoi.find(f" {k}")
        if i >= 0:
            vt.append(chuoi[:i].count(" "))
    if du:
        vt += [i for i, w in enumerate(tu) if w == ma or (len(ma) >= 3 and w.startswith(ma))]
        dau = "".join(w[0] for w in tu)  # 'tl' ~ 'TRIỆT LÔNG'
        if len(ma) >= 2 and ma in dau:
            vt.append(dau.index(ma))
    return min(vt) if vt else None


def _dv_goi_khop(ma: str, dich_vu: str) -> bool:
    """Luật gói: mã dịch vụ trên nhãn khớp dòng dịch vụ CHÍNH của HĐ — bỏ dòng thanh toán công nợ, bỏ chữ
    mô tả trong ngoặc ('... LẦN LẺ (cắt sẹo, laser mài viền, PRP phục hồi)'), không khớp qua chữ chung
    (_TU_DV_YEU), và không có dịch vụ khác đứng trước trong dòng ('ĐIỆN DI C SAU SẸO' là điện di, không phải sẹo)."""
    if _dv_chung(ma):
        return False
    ma = MA_DV_OCR.get(ma, ma)
    cua_ma = set(MA_DV.get(ma, []))
    for x in _ds_dv(dich_vu):
        if "cong no" in khong_dau(x) or "lan le" in khong_dau(x):  # CEO 14/10: mua LẺ thì buổi sau phải có HĐ mới
            continue
        gon = re.sub(r"\([^)]*\)?", " ", x)
        tu = re.sub(r"\b(?:bh|bao hanh)(?:\s*\d+\s*(?:nam|thang))?\b", " ", khong_dau(gon)).split()
        if not tu or not _dv_khop(ma, gon):
            continue
        vt = _vi_tri_dv(ma, tu, _TU_DV_YEU.get(ma, set()))
        if vt is None:
            continue
        # Mã khác (không chung chữ khớp với mã này, vd co2/mv cùng 'mài viền') khớp sớm hơn -> dịch vụ chính là mã khác.
        if any(vk is not None and vk < vt for k, ks in MA_DV.items()
               if k != ma and not (set(ks) & cua_ma) for vk in [_vi_tri_dv(k, tu, du=False)]):
            continue
        return True
    return False


def _anh_mau(conn, ma_kh: str, ngay: str, bo_nho: dict | None = None, gioi_han: int = 2) -> list[str]:
    """id ảnh đã duyệt (xn_hd) hoặc máy chấm 'chac' của mã KH ở NGÀY KHÁC ngày đang xét, ảnh đã duyệt trước.
    Dùng cho luật gói (khách phải có ảnh để so mặt) và ảnh mẫu trên trang duyệt."""
    if not ma_kh:
        return []
    khoa = ("mau", ma_kh, ngay)
    if bo_nho is not None and khoa in bo_nho:
        return bo_nho[khoa]
    codes = [x for (x,) in conn.execute("SELECT code FROM visits WHERE ma_kh=?", (ma_kh,))]
    ds = []
    if codes:
        dau = ",".join("?" * len(codes))
        ds = [x for (x,) in conn.execute(
            f"SELECT id FROM photos WHERE bo_qua=0 AND ngay != ? AND (xn_hd IN ({dau})"
            f" OR (xn_hd IS NULL AND do_tin='chac' AND goi_y_hd IN ({dau})))"
            " ORDER BY xn_hd IS NULL, thoi_gian DESC LIMIT ?", (ngay, *codes, *codes, gioi_han))]
    if bo_nho is not None:
        bo_nho[khoa] = ds
    return ds


def _buoi_theo_goi(conn, nhan: dict, w: list[str], wg: list[str], ngay_anh: str,
                   bo_nho: dict | None) -> tuple[str | None, str]:
    """Luật BUỔI THEO GÓI: ngày đó không có HĐ của khách tên này -> có thể là buổi làm theo gói đã mua
    trước (không ra HĐ mới). Tên nhãn phải còn dấu và khớp ĐÚNG đuôi họ tên (cả dấu, _ten_goi_khop).
    Trong GOI_NGAY ngày trước: khách cùng tên (bất kể dịch vụ) phải đúng 1 mã KH, và khách đó có HĐ
    mà dòng dịch vụ chính khớp mã trên nhãn (_dv_goi_khop) -> HĐ gần nhất. Trả (mã HĐ hoặc None, lý do).
    Chỉ gợi ý — người gọi cho điểm 50."""
    ma = nhan["ma_dv"]
    if _dv_chung(ma) or not w or len(wg) != len(w):  # nhãn không ghi dịch vụ: quá rủi ro
        return None, ""
    if not _co_dau(wg):  # OCR mất hết dấu: 'Thu' hay 'Thư'? không đoán
        return None, ""
    ung: dict[str, list] = {}
    for v in _hd_truoc(conn, ngay_anh, bo_nho):
        if _ten_goi_khop(wg, v["tg"]):
            ung.setdefault(v["ma_kh"] or v["code"], []).append(v)
    if len(ung) > 1:
        return None, (f"; buổi theo gói? {len(ung)} khách cùng tên trong {GOI_NGAY} ngày trước — người chọn")
    hop = [v for vs in ung.values() for v in vs if _dv_goi_khop(ma, v["dich_vu"] or "")]
    if not hop:
        return None, ""
    v = max(hop, key=lambda v: (v["ngay"], v["gio"] or ""))
    if not _anh_mau(conn, v["ma_kh"], ngay_anh, bo_nho):
        # Soát 14/10: 2/3 ca sai là trùng tên với khách vô danh chưa từng có ảnh -> người duyệt không có ảnh
        # để so mặt. Chỉ gợi ý khi mã KH đã có ảnh chắc/đã duyệt ở ngày khác.
        return None, (f"; buổi theo gói? HĐ {v['code']} nhưng khách chưa có ảnh đã xác nhận ngày khác"
                      " — người chọn")
    dv = _ds_dv(v["dich_vu"])
    gon = next((x for x in dv if _dv_goi_khop(ma, x)), dv[0] if dv else "")[:40]
    return v["code"], f"buổi theo gói — HĐ {gon} ngày {v['ngay'][8:10]}/{v['ngay'][5:7]}/{v['ngay'][2:4]}"


LUI_NGAY = (1, 2)  # ảnh không có ngày chụp gốc: ngày trên ảnh có thể là ngày nhận, trễ 1–2 ngày sau ngày chụp


def _hd_ngay_truoc(conn, nhan: dict, w: list[str], wg: list[str], ngay_anh: str,
                   da_thu: str) -> tuple[str | None, str]:
    """Ảnh KHÔNG có ngày chụp gốc (gửi qua Zalo/Messenger...): ngày trên ảnh có thể là ngày NHẬN -> thử HĐ
    ngày D-1, D-2 (D = ngày trên ảnh; KHÔNG thử ngày sau; bỏ ngày đã thử = da_thu). Đúng 1 khách khớp tên
    + dịch vụ (mã dịch vụ trên nhãn phải rõ) -> (mã HĐ, lý do); người gọi cho điểm 50 — không bao giờ 'chac'."""
    ma = nhan["ma_dv"]
    if _dv_chung(ma) or not w:
        return None, ""
    d0 = dt.date.fromisoformat(ngay_anh)
    ung: dict[str, tuple] = {}  # mã KH -> (ngày, HĐ) gần D nhất
    trung = 0
    for lui in LUI_NGAY:
        n = (d0 - dt.timedelta(days=lui)).isoformat()
        if n == da_thu:
            continue
        vs = conn.execute("SELECT * FROM visits WHERE ngay=?", (n,)).fetchall()
        T2 = {x["code"]: _tu_ten_goi(x["ten_kh"]) for x in vs}
        v2, d2, _ = _khop_ten(vs, lambda x: [k for _, k in T2[x["code"]]], T2, nhan, w, wg)
        if v2 is None:
            trung += d2  # d2 = số khách trùng tên trong ngày đó (0 = không thấy)
        elif d2 >= 50 and _dv_khop(ma, v2["dich_vu"]):
            ung.setdefault(v2["ma_kh"] or v2["code"], (n, v2))
    if trung or len(ung) > 1:  # 2+ khách cùng tên (trong 1 ngày hoặc khác ngày) -> không đoán
        return None, "; ảnh không có ngày chụp gốc — nhiều khách khớp ở HĐ 1–2 ngày trước — người chọn"
    if len(ung) != 1:
        return None, ""
    n, v = next(iter(ung.values()))
    return v["code"], (f"khớp tên + dịch vụ {v['ten_kh']} — ảnh không có ngày chụp gốc (có thể gửi qua Zalo)"
                       f" — HĐ ngày {n[8:10]}/{n[5:7]}")


def _dd_mm(ngay: str) -> str:
    return f"{ngay[8:10]}/{ngay[5:7]}"


def _hd_ro_ngay(conn, nhan: dict, kq: tuple, ngay: str) -> bool:
    """Kết quả khớp kq ra HĐ của ĐÚNG ngày `ngay`, điểm >= 50, dịch vụ khớp mã trên nhãn (nếu nhãn ghi)."""
    hd, d, _ = kq
    if not hd or d < 50:
        return False
    v = conn.execute("SELECT ngay, dich_vu FROM visits WHERE code=?", (hd,)).fetchone()
    if not v or v["ngay"] != ngay:
        return False
    ma = nhan["ma_dv"]
    return _dv_chung(ma) or _dv_khop(ma, v["dich_vu"] or "") or _dv_gan_dung(ma, v["dich_vu"] or "")


def _khach_hd(conn, hd: str) -> str:
    v = conn.execute("SELECT ma_kh FROM visits WHERE code=?", (hd,)).fetchone()
    return (v["ma_kh"] if v else None) or hd


def _khop_nhan(conn, nhan: dict, ngay_anh: str, bo_nho: dict | None = None,
               ngay_goc: int | None = None, goc: int | None = None) -> tuple[str | None, int, str]:
    """Khớp 1 nhãn với hóa đơn cùng ngày ghi trên nhãn (không có thì ngày chụp). Không thấy khách tên
    này trong ngày -> ảnh không có ngày chụp gốc (ngay_goc=0) thử HĐ 1–2 ngày trước (_hd_ngay_truoc);
    rồi luật BUỔI THEO GÓI (HĐ cũ cùng dịch vụ). Cả hai chỉ gợi ý 50.
    goc = photos.ngay_goc THẬT của ảnh (1 = có EXIF ngày chụp gốc). Luật ngày (Lượng 16/10): nhân viên có thể ghi
    SAI ngày trên nhãn -> ảnh goc=1 ưu tiên NGÀY CHỤP; chỉ theo ngày nhãn khi ngày chụp không có HĐ khớp tên
    (+ dịch vụ nếu nhãn ghi) mà ngày nhãn có. goc 0/None: ngày nhãn trước như cũ."""
    if nhan.get("quan_he"):
        return None, 0, (f"nhãn '{nhan['goc']}' ghi người nhà ('{nhan['quan_he']}') của khách tên '{nhan['ten']}' —"
                         " không phải khách đó, người chọn")
    ngay, sai = nhan["ngay"] or ngay_anh, ""
    if abs((dt.date.fromisoformat(ngay) - dt.date.fromisoformat(ngay_anh)).days) > 7:
        # OCR đọc sai số ('8/10/16', '3/11 0/26') -> nhãn viết cùng ngày chụp.
        ngay, sai = ngay_anh, f" (ngày trên nhãn đọc ra {nhan['ngay']}, dùng ngày chụp)"
    if goc != 1 or ngay == ngay_anh:
        return _khop_nhan_ngay(conn, nhan, ngay, ngay_anh, bo_nho, ngay_goc, sai)
    chup = _khop_nhan_ngay(conn, nhan, ngay_anh, ngay_anh, bo_nho, ngay_goc, "")
    theo_nhan = _khop_nhan_ngay(conn, nhan, ngay, ngay_anh, bo_nho, ngay_goc, "")
    nhan_ro = _hd_ro_ngay(conn, nhan, theo_nhan, ngay)
    if _hd_ro_ngay(conn, nhan, chup, ngay_anh):
        hd, d, ly_do = chup[0], chup[1], (chup[2] + f" — nhãn ghi ngày {_dd_mm(ngay)} nhưng ảnh chụp ngày"
                                          f" {_dd_mm(ngay_anh)} (có ngày gốc) — theo ngày chụp")
        if nhan_ro and _khach_hd(conn, theo_nhan[0]) != _khach_hd(conn, hd):
            # Ngày nhãn cũng có KHÁCH KHÁC cùng tên + dịch vụ: theo ngày chụp nhưng không chắc -> chỉ gợi ý.
            d, ly_do = min(d, 50), ly_do + f" (ngày {_dd_mm(ngay)} có khách khác cùng tên — chỉ gợi ý)"
        return hd, d, ly_do
    if nhan_ro:
        hd, d, ly_do = theo_nhan
        ly_do += (f" — ảnh chụp ngày {_dd_mm(ngay_anh)} (có ngày gốc) nhưng nhãn ghi ngày {_dd_mm(ngay)},"
                  " ngày chụp không có HĐ khớp — theo ngày nhãn")
        trung = re.search(r" trùng (\d+) khách", chup[2] or "") if chup[0] is None else None
        if trung:  # ngày chụp trùng >= 2 khách cùng tên: không chắc, chỉ gợi ý
            d, ly_do = min(d, 50), ly_do + f" (ngày chụp trùng {trung.group(1)} khách — chỉ gợi ý)"
        return hd, d, ly_do
    return chup


def _khop_nhan_ngay(conn, nhan: dict, ngay: str, ngay_anh: str, bo_nho: dict | None,
                    ngay_goc: int | None, sai: str) -> tuple[str | None, int, str]:
    """_khop_nhan cho 1 ngày HĐ đã chọn (ngày nhãn hoặc ngày chụp)."""
    visits = conn.execute("SELECT * FROM visits WHERE ngay=?", (ngay,)).fetchall()
    lech_ngay = (f" (nhãn ghi ngày {ngay})" if ngay != ngay_anh else "") + sai
    T = {v["code"]: _tu_ten_goi(v["ten_kh"]) for v in visits}

    def t(v):
        return [k for _, k in T[v["code"]]]

    w = nhan["ten"].split()
    wg = (nhan.get("ten_goc") or nhan["ten"]).split()
    if len(wg) != len(w):
        wg = w
    # Xưng hô đầu nhãn ('A Vương', 'C Dung', 'Chị Lan') -> bỏ, trừ khi có khách mang đủ các chữ đó.
    if len(w) > 1 and w[0] in XUNG_HO and not any(set(w) <= set(t(v)) for v in visits):
        w, wg = w[1:], wg[1:]
    v, d, ly_do = _khop_ten(visits, t, T, nhan, w, wg)
    hv = _hoan_vi_goi(list(zip(wg, w)))
    if _thu_tu_goi(w, hv) != w:  # nhãn 'Vy Nguyễn' / 'Robert Hawkins': thử thêm thứ tự tên gọi như tên khách đã đảo
        w2, wg2 = _thu_tu_goi(w, hv), _thu_tu_goi(wg, hv)
        kq = _khop_ten(visits, t, T, nhan, w2, wg2)
        if kq[0] is not None and (v is None or kq[1] > d):
            (v, d, ly_do), w, wg = kq, w2, wg2
    if v is not None and d < 50 and nhan["ma_dv"]:
        # Lệch dịch vụ: HĐ có thể nhập hôm trước/hôm sau -> khách cùng tên, dịch vụ khớp ở ngày ±1
        # (đúng 1 ngày có) -> chỉ gợi ý 50.
        ke = []
        for lech in (-1, 1):
            n = (dt.date.fromisoformat(ngay) + dt.timedelta(days=lech)).isoformat()
            vs = conn.execute("SELECT * FROM visits WHERE ngay=?", (n,)).fetchall()
            T2 = {x["code"]: _tu_ten_goi(x["ten_kh"]) for x in vs}
            v2, d2, _ = _khop_ten(vs, lambda x: [k for _, k in T2[x["code"]]], T2, nhan, w, wg)
            if v2 is not None and d2 >= 50 and _dv_khop(nhan["ma_dv"], v2["dich_vu"]) and _hd_that(v2["dich_vu"]):
                ke.append((n, v2))
        if len(ke) == 1:
            n, v2 = ke[0]
            return v2["code"], 50, f"nhãn '{nhan['goc']}' khớp tên + dịch vụ {v2['ten_kh']} — HĐ ngày kế ({n})"
    if v is None:
        if d:
            return None, 0, f"nhãn '{nhan['goc']}' trùng {d} khách{lech_ngay} — người chọn"
        khong = f"nhãn '{nhan['goc']}' không thấy khách tên này trong hóa đơn ngày {ngay}"
        ly_lui = ""
        if ngay_goc == 0:
            hd_lui, ly_lui = _hd_ngay_truoc(conn, nhan, w, wg, ngay_anh, ngay)
            if hd_lui:
                return hd_lui, 50, f"nhãn '{nhan['goc']}' {ly_lui}"
        hd_goi, ly_goi = _buoi_theo_goi(conn, nhan, w, wg, ngay_anh, bo_nho)
        if hd_goi:  # không bao giờ 'chac': điểm 50 = gợi ý, vẫn làm neo gợi ý cho bộ chụp
            return hd_goi, 50, f"nhãn '{nhan['goc']}' {ly_goi}"
        return None, 0, khong + ly_lui + ly_goi
    ly_do = f"nhãn '{nhan['goc']}' {ly_do} {v['ten_kh']}{lech_ngay}"
    if d > 50 and not nhan.get("gach", True) and not (len(w) >= 2 and t(v) == w):
        d, ly_do = 50, ly_do + " — nhãn không có gạch, chưa khớp đủ họ tên: chỉ gợi ý"
    return v["code"], d, ly_do


def _khop_ten(visits, t, T, nhan, w, wg) -> tuple[sqlite3.Row | None, int, str]:
    """(hóa đơn, điểm, lý do) — hóa đơn None: d = số khách trùng (0 = không thấy)."""
    dv = nhan["ma_dv"]

    def cung_ten(v, k):
        if k == 1 and w:  # nhãn 1 chữ: tên gọi; tên Tây: cả tên cuối gốc ('Robert'/'Hawkins' ~ ROBERT HAWKINS)
            return _mot_chu_khop(w[-1], t(v), _la_ten_tay(T[v["code"]]))
        return (len(t(v)) >= k and t(v)[-k:] == w[-k:]) or (_la_ten_tay(T[v["code"]]) and _duoi_tay(w[-k:], t(v)))

    def ngoai(v):
        return _ten_ngoai(wg, [g for g, _ in T[v["code"]]])

    # Chữ thừa phía trước tên ('Laser Trang') -> thử bớt dần từ trái: 3 chữ, 2 chữ, 1 chữ. Nhãn >= 2 chữ chỉ
    # bớt chữ chung (_bot_duoc): 'Ngọc Anh' không rơi xuống khớp 1 chữ 'Anh' (Lượng 16/10).
    ung, k = [], len(w)
    for k in range(len(w), 0, -1):
        if not _bot_duoc(w, k):
            k = len(w)
            break
        ung = [v for v in visits if cung_ten(v, k)]
        if ung:
            break
    if not ung and w and w[-1] in _GHI_CHU_TEN:
        # Nhãn ghi đúng chữ ghi chú ('KTV-dvm' ~ 'Nguyễn Thị X KTV' = nhân viên làm dịch vụ). Chỉ khi chữ
        # cuối nhãn là chữ ghi chú: nhãn 'Lương' không được khớp '(BS LƯƠNG)'.
        for k in range(len(w), 0, -1):
            ung = [v for v in visits if khong_dau(v["ten_kh"]).split()[-k:] == w[-k:]]
            if ung:
                break
    if not ung and w:  # tên gọi trong ngoặc: nhãn 'Lisa-dvm' ~ 'Nguyễn Thị X (LISA)'
        ung, k = [v for v in visits if any(set(w) <= set(b) for b in _bi_danh(v["ten_kh"]))], len(w)
    gan_dung = False
    w2 = w[next((i for i, x in enumerate(w) if x not in _CHU_THUA_TEN), 0):]  # bỏ chữ chung bên trái
    if not ung and len(w2) >= 2:
        # CEO 16/10: tên Việt có ĐỦ mọi chữ nhãn trong họ tên nhưng không đúng đuôi ('Kim Mỹ' ~ '... Mỹ Kim',
        # 'Cao Thanh' ~ 'Cao Thị Thanh', 'Ngọc Huyền' ~ '... Ngọc Huyền Trân') -> ứng viên, tối đa 50 (gợi ý).
        du = [v for v in visits if not ngoai(v) and set(w2) <= set(t(v))]
        if du:
            hop = du if _dv_chung(dv) else [v for v in du if _dv_khop(dv, v["dich_vu"])]
            chon = hop or du
            if len({v["ma_kh"] or v["code"] for v in chon}) > 1:
                return None, len(chon), ""
            v = min(chon, key=lambda v: v["gio"] or "99")
            if hop and _khoi_lien(w2, wg[len(wg) - len(w2):] if len(wg) == len(w) else w2, T[v["code"]]):
                # CEO 16/10 lần 3: nhãn = các chữ LIỀN NHAU trong họ tên (chữ đệm + tên: 'Hoàng Minh' ~ 'Đỗ Hoàng
                # Minh Khang', 'Ngọc Huyền' ~ 'Nguyễn Ngọc Huyền Trân'), không gồm họ -> khớp tên như đuôi.
                return v, 85, "khớp tên (chữ đệm + tên liền nhau) + dịch vụ" if not _dv_chung(dv) else "khớp tên (chữ đệm + tên liền nhau)"
            if hop or _dv_gan_dung(dv, v["dich_vu"]):
                return v, 50, "có đủ tên nhưng khác thứ tự/vị trí —"
            return v, 40, "có đủ tên nhưng khác thứ tự/vị trí, lệch dịch vụ —"
    if not ung and w:
        # Tên nước ngoài đảo thứ tự ('Cheng Wei' ~ 'Wu Cheng Wei') -> tên nằm trong họ tên; OCR sai
        # 1 chữ ('Thann' ~ 'Thanh'). Chỉ "chắc" khi tên nằm trong họ tên VÀ dịch vụ trên nhãn khớp.
        # Nhãn >= 2 chữ: 'tên nằm trong họ tên' chỉ cho tên nước ngoài/không dấu; lệch 1 chữ OCR chỉ ở chữ
        # cuối, các chữ trước phải khớp đúng đuôi họ tên. Nhãn 1 chữ như cũ.
        def trong(v):  # nhãn 1 chữ = HỌ (chữ đầu tên Việt) không tính (CEO 16/10 lần 4, ca 846FE437 'Chị Hà')
            if len(w) == 1 and not ngoai(v) and t(v) and t(v)[0] == w[0] and w[0] in HO_VIET and w[0] not in t(v)[1:]:
                return False
            return set(w) <= set(t(v)) and (len(w) < 2 or ngoai(v))

        def lech(v):
            return (bool(t(v)) and len(w[-1]) >= 4 and _lech_1(w[-1], t(v)[-1])
                    and (len(w) < 2 or (len(t(v)) >= len(w) and t(v)[-len(w):-1] == w[:-1])))

        ung = [v for v in visits if trong(v)]
        # Nhãn 1 chữ tới đây = không khách nào có TÊN CUỐI khớp, chữ chỉ nằm giữa họ tên (chữ đệm: 'Thảo' ~
        # 'Phạm Đỗ Thảo Vy') -> không bao giờ 85, rơi xuống gợi ý 50 bên dưới (CEO 16/10).
        if len(ung) == 1 and len(w) >= 2 and _dv_khop(dv, ung[0]["dich_vu"]):
            return ung[0], 85, "khớp tên + dịch vụ"
        ung, gan_dung = ung or [v for v in visits if lech(v)], True
    loc_dv = False
    if len(ung) > 1:  # trùng tên -> dùng mã dịch vụ trên nhãn để tách
        loc = [v for v in ung if _dv_khop(dv, v["dich_vu"])]
        ung, loc_dv = loc or ung, bool(loc)
    theo_dau = False
    if len(ung) > 1:  # vẫn trùng (Dung/Dũng) -> ưu tiên khách trùng cả dấu với nhãn; chỉ gợi ý
        kk = len(w) if gan_dung else k
        nhan_dau = [_dau(g) for g in wg[-kk:]]
        dau = [v for v in ung if [_dau(g) for g, _ in T[v["code"]]][-kk:] == nhan_dau]
        if len(dau) == 1:
            ung, theo_dau = dau, True
    if len(ung) == 1 and theo_dau:
        return ung[0], 50, "trùng tên không dấu, chọn khách trùng cả dấu"
    if len(ung) == 1 and not _dv_chung(dv) and not gan_dung and not _dv_khop(dv, ung[0]["dich_vu"]):
        # Khớp đuôi tên nhưng dịch vụ lệch ('Thu' ~ '... Thư' mài sẹo, trong khi khách 'THU (KH TỰ ĐẾN)'
        # làm pico) -> xét khách có tên nằm trong họ tên + dịch vụ khớp; không có thì chỉ gợi ý.
        # Nhãn 1 chữ (k == 1): đã có khách đúng TÊN CUỐI (ung) -> không lấy khách chỉ chứa chữ đó ở giữa họ tên
        # (soát 16/10: 'Thảo-csd' lên chắc 'Phạm Đỗ Thảo Vy' trong khi ngày đó có 'Cô Thảo') (CEO 16/10).
        khac = [v for v in visits if k >= 2 and v["code"] != ung[0]["code"]
                and set(w[-k:]) <= set(t(v)) and _dv_khop(dv, v["dich_vu"])]
        if len(khac) == 1:
            if k >= 2 and not ngoai(khac[0]):  # tên Việt đủ chữ nhưng không đúng đuôi: chỉ gợi ý (CEO 16/10)
                return khac[0], 50, "có đủ tên nhưng khác thứ tự/vị trí + dịch vụ —"
            if k == len(w):
                return khac[0], 85, "khớp tên + dịch vụ"
            return khac[0], 50, "khớp một phần tên + dịch vụ"
        if _dv_gan_dung(dv, ung[0]["dich_vu"]):  # OCR đọc sai 1 chữ của mã ('picc', 'tractional')
            return ung[0], 50, "khớp tên, mã dịch vụ đọc gần đúng"
        # Không HĐ nào của khách khớp mã dịch vụ trên nhãn: điểm 40 = không làm neo lan/bộ chụp.
        return ung[0], 40, "khớp tên nhưng lệch dịch vụ"
    if len(ung) == 1:
        if k < len(w) or gan_dung:  # chỉ khớp một phần / gần đúng -> chỉ gợi ý, người xác nhận
            return ung[0], 50, "khớp một phần tên"
        return ung[0], 85, "khớp tên + dịch vụ" if loc_dv else "khớp"
    if len(ung) > 1 and len({v["ma_kh"] for v in ung}) == 1 and ung[0]["ma_kh"]:
        # Cùng 1 khách có nhiều hóa đơn trong ngày (dịch vụ + mua sản phẩm) -> hóa đơn sớm nhất, chỉ gợi ý.
        gan = [x for x in ung if not loc_dv and _dv_gan_dung(dv, x["dich_vu"])]
        v = min(gan or ung, key=lambda v: v["gio"] or "99")
        if not _dv_chung(dv) and not loc_dv and not gan:  # soát 8b3c1c8: 15/83 ảnh mã dịch vụ không khớp HĐ nào của khách mà vẫn lan
            return v, 40, f"khớp tên nhưng lệch dịch vụ (không HĐ nào trong {len(ung)} HĐ của khách khớp mã) —"
        return v, 50, f"cùng 1 khách có {len(ung)} hóa đơn trong ngày, chọn hóa đơn sớm nhất —"
    return None, len(ung), ""


def _khoi_lien(w: list[str], wg: list[str], tg: list[tuple[str, str]]) -> bool:
    """Nhãn w (>= 2 chữ, không dấu; wg còn dấu) là KHỐI CHỮ LIỀN NHAU đúng thứ tự trong họ tên tg, không bắt đầu ở
    họ (chữ đầu là họ Việt), cùng dấu theo _chu_mot_chieu (nhãn mất dấu vẫn được)."""
    t = [k for _, k in tg]
    n = len(w)
    if n < 2 or len(t) <= n:
        return False
    for i in range(len(t) - n + 1):
        if t[i:i + n] == w and not (i == 0 and t[0] in HO_VIET) \
                and all(_chu_mot_chieu(a, g) for a, (g, _) in zip(wg, tg[i:i + n])):
            return True
    return False


def _ten_kieu_phan(nhan: dict, ten_kh: str) -> bool:
    """Nhãn hợp khách theo kiểu 'một phần' (CEO 16/10 lần 3): đảo thứ tự (mọi chữ có trong họ tên), khối chữ liền nhau,
    hoặc nhãn 1 chữ = chữ đệm / tên (không phải họ). So chữ đúng (không dấu) + dấu một chiều; không nhận lệch OCR."""
    if nhan.get("quan_he"):  # nhãn người nhà: không bao giờ hợp khách <tên>
        return False
    tg = _tu_ten_goi(ten_kh)
    t = [k for _, k in tg]
    w = _ten_nhan_gon(nhan, t, _dao_ten(ten_kh))
    wg = (nhan.get("ten_goc") or nhan["ten"]).split()[-len(w):] if w else []
    tho = nhan["ten"].split()
    if len(tho) > 1 and tho[0] in XUNG_HO:
        tho = tho[1:]
    if not w or not t or len(wg) != len(w) or len(tho) != len(w):  # nhãn có chữ chung thừa ('Laser Tâm'): không
        return False
    ho = {0} if t[0] in HO_VIET and len(t) >= 2 else set()

    def co(a, x):  # chữ x (dấu: a) có ở vị trí không phải họ trong tên khách
        return any(k == x and i not in ho and _chu_mot_chieu(a, g) for i, (g, k) in enumerate(tg))
    return all(co(a, x) for a, x in zip(wg, w)) and len(set(w)) == len(w)


NANG_PHUT = 30  # luật 2 (CEO 16/10 lần 3): nhãn 'một phần' + giờ HĐ cách giờ chụp <= 30' -> chắc


def _nang_ten_phan(conn, nhan: dict, hd: str, ngay: str, visits, p, r, cum: dict | None,
                   mat_nho: dict | None = None, bo_ma: list | None = None) -> bool:
    """Nhãn khớp 'một phần' (đảo thứ tự / chữ đệm / tên gọi) -> nâng chắc khi: HĐ cùng ngày chụp, trong ngày CHỈ 1 khách
    hợp nhãn kiểu đó (hoặc đúng đuôi), và (dịch vụ nhãn khớp HĐ hoặc giờ HĐ cách giờ chụp <= NANG_PHUT phút, ảnh có giờ
    chụp thật); mặt ảnh (nếu thuộc cụm mạnh) không thuộc khách khác."""
    v = next((x for x in visits if x["code"] == hd), None)
    if not v or v["ngay"] != ngay or not _ten_kieu_phan(nhan, v["ten_kh"]):
        return False
    hop = {x["ma_kh"] or x["code"] for x in visits
           if _ten_kieu_phan(nhan, x["ten_kh"]) or _ten_dung_duoi(nhan, x["ten_kh"], ocr=False)}
    if hop != {v["ma_kh"] or v["code"]}:
        return False
    dv = nhan["ma_dv"]
    # Dịch vụ khớp CHẶT: chữ trong bảng ma_dich_vu.json hoặc đúng 1 chữ của tên dịch vụ — không nhận khớp kiểu chữ cái
    # đầu ('ha' ~ 'trieT Long nacH...' — ca 24A56F34 hạ đúng).
    def khop(m):
        return bool(m) and not _dv_chung(m) and (_dv_hang([m], v["dich_vu"]) < 20
                                                 or m in khong_dau(v["dich_vu"] or "").split())
    khop_dv = khop(dv)
    # CEO 16/10 lần 4 (ca 9AF8F874): nhãn (hoặc nhãn cùng bộ) có MÃ DỊCH VỤ nhận ra được mà không khớp HĐ -> không
    # dùng luật giờ; giờ chỉ dùng khi không nhãn nào ghi mã dịch vụ.
    ma_ro = [m for m in [dv] + list(bo_ma or []) if m and (m in MA_DV or m in MA_DV_OCR)]
    gan_gio = (not ma_ro or any(khop(m) for m in ma_ro)) and r["ngay_goc"] != 0 and not r["trung_giay"] \
        and _cach_gio(v, r["gio"]) <= NANG_PHUT * 60
    if not (khop_dv or gan_gio):
        return False
    if cum is not None:
        c = _khach_cua_mat(cum, p["khuon_mat"])
        if c and c["neo"] >= CUM_MANH and _khoa_hd(conn, cum, hd, {}) != c["khach"]:
            return False
    # Mặt trên ảnh không trùng mặt nào trong ảnh đã xác nhận/chắc của khách này (ngày khác) -> có thể người khác
    # (ca 24A56F34: nhãn chữ đệm + HĐ có filler nhưng mặt khác hẳn ảnh cũ của khách) -> không nâng.
    return not _mat_khac_khach(conn, ngay, hd, p["khuon_mat"], {} if mat_nho is None else mat_nho)


def _phut(a: str, b: str) -> float:
    return abs((dt.datetime.fromisoformat(a) - dt.datetime.fromisoformat(b)).total_seconds()) / 60


def _hd_neo(r: dict) -> str | None:
    """HĐ mà ảnh neo được phép lan; neo < 50 (khớp tên lệch dịch vụ) coi như nhãn chưa khớp. Ảnh gợi ý theo
    gói bị cấm làm neo (r['khong_neo']) cũng coi như nhãn chưa khớp."""
    return r["hd"] if r["diem"] >= 50 and not r.get("khong_neo") else None


def _lan_duoc(r: dict, hd: str, hd_lui: set) -> bool:
    """HĐ lấy theo ảnh không có ngày chụp gốc (HĐ 1–2 ngày trước) chỉ lan sang ảnh cũng không có ngày chụp gốc:
    ảnh có EXIF máy chụp thì ngày trên ảnh đúng, không thể là HĐ ngày khác."""
    return hd not in hd_lui or r.get("ngay_goc") == 0


def _bo_chup(ds: list[dict], hd_lui: set = frozenset(), khoa_hd: dict | None = None) -> None:
    """Luật BỘ CHỤP: phòng khám chụp mỗi khách 5 kiểu liên tục (chính diện, nghiêng 45°/90° hai bên),
    nhãn viết tay thường chỉ ở tấm chính diện. Bộ = chuỗi ảnh liền nhau, 2 ảnh kề cách <= BO_GIAY
    (bỏ ảnh trùng giây >= TRUNG_GIAY). Neo = ảnh có nhãn hoặc đã khớp HĐ điểm >= 50.
    Độ dài bộ, khoảng cách tới neo, số neo đều đếm theo TƯ THẾ = số giây khác nhau (2 bản cùng 1 giây
    là ảnh nhân đôi, tính 1).
    - Bộ <= BO_TOI_DA tư thế, mọi neo cùng 1 HĐ, có neo chắc -> cả bộ 'chac'.
    - Bộ dài hơn: neo ở >= 2 tư thế cùng 1 HĐ + có neo chắc -> 'chac' (ảnh cách neo gần nhất > BO_TOI_DA-1
      tư thế chỉ gợi ý); neo 1 tư thế -> cắt tại quãng nghỉ >= NGHI_GIAY sau khi đủ BO_DU tư thế: phần có
      neo <= BO_TOI_DA tư thế -> 'chac', phần khác chỉ gợi ý (khách sau có thể không viết nhãn); neo 2+
      khách -> cắt tại quãng nghỉ dài nhất giữa 2 neo khác khách liên tiếp, mỗi phần chỉ gợi ý.
    - Không có neo chắc: neo chỉ gợi ý cùng 1 HĐ -> các tấm còn lại gợi ý theo neo. Ảnh có HĐ khác (kể cả người đã duyệt HĐ khác) chặn nâng."""
    cung = [r for r in ds if not r["trung_giay"]]
    bo, truoc = [], None
    for r in cung:
        if truoc is None or (r["gio"] - truoc["gio"]).total_seconds() > BO_GIAY:
            bo.append([])
        bo[-1].append(r)
        truoc = r
    for b in bo:
        if len(b) < 2:
            continue
        neo = [i for i, r in enumerate(b) if r["nhan"] or (r["hd"] and r["diem"] >= 50)]
        if not neo:
            continue
        giay = {g: k for k, g in enumerate(sorted({r["gio"] for r in b}))}
        tt = [giay[r["gio"]] for r in b]  # thứ tự tư thế của từng ảnh
        so_tt, neo_tt = len(giay), {tt[i] for i in neo}
        hd_neo = [_hd_neo(b[i]) for i in neo]
        mot_hd = None not in hd_neo and len(set(hd_neo)) == 1
        if not any(b[i]["diem"] >= 80 for i in neo):
            # Neo chỉ gợi ý (khớp một phần tên): không nâng 'chac' nhưng không để sót tấm nghiêng —
            # mọi tấm còn lại trong bộ ít nhất gợi ý theo neo (khi không có nhãn/HĐ khác trong bộ).
            hd = hd_neo[0]
            if mot_hd and not any((r["hd"] and r["hd"] != hd) or (r["xn"] and r["xn"] != hd) for r in b):
                for r in b:
                    if not r["hd"] and r["do_tin"] != "khong_hd" and _lan_duoc(r, hd, hd_lui):
                        r.update(hd=hd, do_tin="goi_y", diem=40,
                                 ly_do=f"cùng bộ chụp liền {len(b)} ảnh với ảnh gợi ý")
            continue
        if mot_hd:
            hd = hd_neo[0]
            # Ảnh khác (không phải neo) đã có HĐ khác, hoặc người duyệt chọn HĐ khác -> bộ lẫn khách.
            if any((r["hd"] and r["hd"] != hd) or (r["xn"] and r["xn"] != hd) for r in b):
                continue
            nguon = next(b[i] for i in neo if b[i]["diem"] >= 80)
            nhan = re.search(r"nhãn '([^']*)'", nguon["ly_do"] or "")
            tu = f"ảnh có nhãn '{nhan.group(1)}'" if nhan else "ảnh đã khớp chắc"
            dai = so_tt > BO_TOI_DA
            phan = None  # bộ dài 1 nhãn: (đầu, cuối) phần chứa neo sau khi cắt tại quãng nghỉ dài
            if dai and len(neo_tt) < 2:
                cat, dau = [], 0
                for k in range(1, len(b)):
                    if (b[k]["gio"] - b[k - 1]["gio"]).total_seconds() >= NGHI_GIAY and tt[k] - tt[dau] >= BO_DU:
                        cat.append(k)
                        dau = k
                ph = next((x, y) for x, y in zip([0] + cat, cat + [len(b)]) if x <= neo[0] < y)
                if len(cat) and tt[ph[1] - 1] - tt[ph[0]] + 1 <= BO_TOI_DA:
                    phan = ph
            for i, r in enumerate(b):
                if r["diem"] >= 80 or r["do_tin"] == "khong_hd":
                    continue
                if phan:
                    if not phan[0] <= i < phan[1]:
                        if not r["hd"]:
                            r.update(hd=hd, do_tin="goi_y", diem=40,
                                     ly_do=f"bộ chụp liền dài {so_tt} tư thế, ảnh khác phần (cách quãng nghỉ ≥{NGHI_GIAY}s)"
                                     f" với {tu} — có thể khách khác, người chọn")
                        continue
                    r.update(hd=hd, do_tin="chac", diem=80,
                             ly_do=f"cùng bộ chụp {tt[phan[1] - 1] - tt[phan[0]] + 1} tư thế với {tu}"
                             f" (bộ liền {so_tt} tư thế tách tại quãng nghỉ ≥{NGHI_GIAY}s)")
                    continue
                if dai and (len(neo_tt) < 2 or min(abs(tt[i] - tt[j]) for j in neo) > BO_TOI_DA - 1):
                    if not r["hd"]:
                        r.update(hd=hd, do_tin="goi_y", diem=40,
                                 ly_do=f"bộ chụp liền dài {so_tt} tư thế, chỉ 1 nhãn với {tu}"
                                 " — có thể 2 khách liền nhau, người chọn" if len(neo_tt) < 2 else
                                 f"bộ chụp liền dài {so_tt} tư thế, ảnh xa nhãn với {tu} — người chọn")
                    continue
                r.update(hd=hd, do_tin="chac", diem=80,
                         ly_do=f"cùng bộ chụp liền {len(b)} ảnh với {tu}")
            continue
        if so_tt <= BO_TOI_DA:
            continue
        # Bộ dài có neo nhiều khách (hoặc nhãn chưa khớp): cắt tại quãng nghỉ dài nhất giữa 2 neo khác
        # khách liên tiếp; mỗi phần gợi ý theo neo của phần đó (phần có neo chưa khớp thì bỏ).
        cat = []
        for x, y in zip(neo, neo[1:]):
            if _hd_neo(b[x]) != _hd_neo(b[y]) or _hd_neo(b[x]) is None:
                k = max(range(x, y), key=lambda k: (b[k + 1]["gio"] - b[k]["gio"]).total_seconds())
                cat.append(k + 1)
        for dau, cuoi in zip([0] + cat, cat + [len(b)]):
            phan = b[dau:cuoi]
            hds = {_hd_neo(r) for r in phan if r["nhan"] or (r["hd"] and r["diem"] >= 50)}
            if len(hds) != 1 or None in hds:
                continue
            hd = hds.pop()
            # CEO 16/10 lần 4 (ca C5A407E4): phần tách ra ngắn (<= BO_TOI_DA tư thế), có neo CHẮC (nhãn/tên đủ),
            # mọi neo trong phần cùng 1 HĐ, nhãn phần kia không khớp chắc ai -> các tấm còn lại 'chac' như bộ ngắn.
            # Không lên chắc khi trong PHẦN có ảnh xen kẽ của khách khác: ảnh nhãn khớp HĐ khác (kể cả chỉ gợi ý), hoặc
            # ảnh mang mặt thuộc cụm mạnh của khách khác (CEO 16/10 lần 5, ca 849E9318: 4 tấm mặt khách pico xen giữa).
            # Nhãn khách khác ở PHẦN BÊN KIA chỗ cắt không chặn (soát 16/10: D7054521, E6289B82 đúng).
            if len({r["gio"] for r in phan}) <= BO_TOI_DA and any(r["diem"] >= 80 for r in phan) \
                    and not _xen_ke(phan, hd, khoa_hd) \
                    and not any(r["xn"] and r["xn"] != hd for r in phan):
                nguon = next(r for r in phan if r["diem"] >= 80)
                nh = re.search(r"nhãn '([^']*)'", nguon["ly_do"] or "")
                tu = f"ảnh có nhãn '{nh.group(1)}'" if nh else "ảnh đã khớp chắc"
                for r in phan:
                    if not r["hd"] and not r["nhan"] and r["do_tin"] != "khong_hd" and _lan_duoc(r, hd, hd_lui):
                        r.update(hd=hd, do_tin="chac", diem=80,
                                 ly_do=f"cùng bộ chụp {len(phan)} ảnh với {tu} (bộ liền {len(b)} ảnh tách tại quãng"
                                 " nghỉ dài nhất giữa 2 nhãn khác khách)")
                continue
            for r in phan:
                if not r["hd"] and not r["nhan"] and r["do_tin"] != "khong_hd" and r["xn"] in (None, hd) \
                        and _lan_duoc(r, hd, hd_lui):
                    r.update(hd=hd, do_tin="goi_y", diem=40,
                             ly_do=f"tách bộ dài theo quãng nghỉ ({len(b)} ảnh liền, {len(phan)} ảnh phần này)"
                             " — cùng phần với ảnh đã khớp")


def _xen_ke(phan: list[dict], hd: str, khoa_hd: dict | None) -> bool:
    """Trong phần bộ có ảnh của khách khác chụp xen kẽ: ảnh nhãn khớp HĐ khác (kể cả gợi ý), hoặc ảnh mang mặt cụm mạnh
    (r['mat_k'], ghep_ngay gắn trước luật bộ) của khách khác khách của hd."""
    if any(r["nhan"] and r["hd"] and r["hd"] != hd for r in phan):
        return True
    k = (khoa_hd or {}).get(hd)
    return k is not None and any(r.get("mat_k") and r["mat_k"] != k for r in phan)


def _ngay_goc(p) -> int | None:
    """photos.ngay_goc của dòng ảnh (DB/ dòng cũ chưa có cột -> None = coi như có ngày gốc, ghép như cũ)."""
    try:
        return p["ngay_goc"]
    except (IndexError, KeyError):
        return None


def _ngay_khong_tin(photos) -> set:
    """id ảnh mà NGÀY trên ảnh không tin được: ngay_goc=0 VÀ không có ảnh có ngày chụp gốc (ngay_goc=1) cùng ngày
    cách <= BO_GIAY giây. Đo 14/10 (09/2025–10/2026): 3.435/3.869 ảnh ngay_goc=0 nằm sát (<= 60s, đa số < 10s)
    ảnh có EXIF — chụp cùng buổi (bản lưu thêm), ngày đúng; chỉ ảnh đứng riêng mới có thể là ảnh gửi qua Zalo."""
    co = sorted(dt.datetime.fromisoformat(p["thoi_gian"]) for p in photos if _ngay_goc(p) == 1 and p["thoi_gian"])
    ra = set()
    for p in photos:
        if _ngay_goc(p) != 0:
            continue
        t = dt.datetime.fromisoformat(p["thoi_gian"])
        if not any(abs((x - t).total_seconds()) <= BO_GIAY for x in co):
            ra.add(p["id"])
    return ra


_LY_DO_PHAN = ("khớp một phần tên", "có đủ tên nhưng khác thứ tự/vị trí")


def ghep_ngay(conn: sqlite3.Connection, ngay: str, cum: dict | None = None) -> None:
    """cum: bảng cụm mặt -> khách (cum_khach), cmd_ghep tính 1 lần cho cả lượt; None -> tự tính."""
    visits = conn.execute("SELECT * FROM visits WHERE ngay=?", (ngay,)).fetchall()
    photos = conn.execute(
        "SELECT * FROM photos WHERE ngay=? ORDER BY thoi_gian", (ngay,)
    ).fetchall()
    if not photos:
        return
    if cum is None:
        cum = cum_khach(conn)
    bo_nho: dict = {}  # HĐ 180 ngày trước (luật buổi theo gói), nạp 1 lần cho ngày này

    khong_tin = _ngay_khong_tin(photos)  # ảnh không có ngày chụp gốc, đứng riêng (có thể gửi qua Zalo)
    # Chia đợt chụp: ảnh cách ảnh trước > DOT_PHUT phút thì sang đợt mới.
    dot, truoc, ket_qua = 0, None, {}
    for p in photos:
        if truoc and _phut(p["thoi_gian"], truoc) > DOT_PHUT:
            dot += 1
        truoc = p["thoi_gian"]
        ket_qua[p["id"]] = {"dot": dot, "hd": None, "do_tin": "chua_ro", "ly_do": "", "diem": 0,
                            "nhan": False, "gio": dt.datetime.fromisoformat(p["thoi_gian"]),
                            "xn": p["xn_hd"], "ngay_goc": 0 if p["id"] in khong_tin else 1,
                            # luật ngày 16/10: 1 = có EXIF, hoặc ngay_goc=0 sát ảnh EXIF cùng buổi (<= BO_GIAY s)
                            "goc": 1 if _ngay_goc(p) == 0 and p["id"] not in khong_tin else _ngay_goc(p)}
    # Giờ trùng đến từng giây ở >= TRUNG_GIAY ảnh: giờ nhập/lưu -> không lan đợt, không dùng luật giờ.
    dem_giay = {}
    for p in photos:
        dem_giay[p["thoi_gian"]] = dem_giay.get(p["thoi_gian"], 0) + 1
    for p in photos:
        ket_qua[p["id"]]["trung_giay"] = dem_giay[p["thoi_gian"]] >= TRUNG_GIAY

    nhan_ds = {p["id"]: doc_nhan(f"{p['chu_thich']} {p['ocr']}", int(ngay[:4])) for p in photos}
    nhan_that = {p["id"]: _nhan_that(p, int(ngay[:4])) for p in photos}  # luật SĐT người nhà
    _chia_bo([ket_qua[p["id"]] for p in photos])
    mat_nho: dict = {}  # mã KH -> mã người trên ảnh đã xác nhận (luật gói, kiểm khuôn mặt)
    for p in photos:
        r = ket_qua[p["id"]]
        goc = f"{p['chu_thich']} {p['ocr']} {p['ten_file']}"
        r["nhan"] = bool(nhan_ds[p["id"]])
        if not visits and not r["nhan"]:
            r.update(do_tin="khong_hd", ly_do="ngày này không có hóa đơn")
            continue
        chu = khong_dau(goc)
        # Các dãy số dạng SĐT (cho phép cách/chấm/gạch: 0909 123 456).
        so = " ".join(re.sub(r"\D", "", x) for x in re.findall(r"\d[\d .\-]{7,}\d", goc))
        diem = sorted(((_diem(v, chu, so), v["code"]) for v in visits), reverse=True)
        (d, ly_do), code = diem[0] if diem else ((0, ""), None)
        tho = (code, d, ly_do) if d and (len(diem) == 1 or diem[1][0][0] < d) else None
        nguoi_nha = None  # mã KH của SĐT khi nhãn ghi tên khác
        if tho and ly_do.startswith("khớp SĐT"):
            v_sdt = next(v for v in visits if v["code"] == code)
            id_nhan = _nhan_ten_khac(v_sdt["ten_kh"], p, photos, ket_qua, nhan_that)
            if id_nhan:
                # Người nhà dùng chung số: SĐT trên ảnh là của khách này nhưng nhãn (ảnh/bộ chụp) ghi tên khác.
                tho = (code, 50, f"khớp SĐT nhưng nhãn ghi tên khác (ảnh {id_nhan[:8]}) — có thể người nhà dùng chung số")
                nguoi_nha = v_sdt["ma_kh"] or code
        if tho and tho[1] >= 80:
            r.update(hd=code, diem=d, ly_do=ly_do, do_tin="chac")
            continue
        # Nhãn nhân viên ghi trên ảnh (chỉ có tên + dịch vụ viết tắt + ngày). Khớp một phần tên ở trên
        # (50) không chặn nhãn: nhãn cho điểm cao hơn thì lấy nhãn.
        for nhan in nhan_ds[p["id"]]:
            hd, d, ly_do = _khop_nhan(conn, nhan, ngay, bo_nho, r["ngay_goc"], r["goc"])
            if hd and "buổi theo gói" in ly_do and _mat_khac_khach(conn, ngay, hd, p["khuon_mat"], mat_nho):
                hd, d, ly_do = None, 0, ly_do + " — nhưng khuôn mặt khác ảnh đã xác nhận của khách: bỏ, người chọn"
            if hd and d == 50 and any(x in ly_do for x in _LY_DO_PHAN) and "lệch dịch vụ" not in ly_do \
                    and _nang_ten_phan(conn, nhan, hd, ngay, visits, p, r, cum, mat_nho,
                                       [n["ma_dv"] for q in photos if r["bo"] is not None and q["id"] != p["id"]
                                        and ket_qua[q["id"]]["bo"] == r["bo"] for n in nhan_ds[q["id"]]]):
                d, ly_do = 85, ly_do + " — chỉ 1 khách khớp kiểu này trong ngày + dịch vụ/giờ HĐ khớp: chắc"
            r["ly_do"] = ly_do
            if hd:
                if not tho or d > tho[1]:
                    r.update(hd=hd, diem=d, do_tin="chac" if d >= 80 else "goi_y")
                    if d >= 80 and _nhan_khop_dv(conn, nhan, hd):
                        r["khoa_nhan"] = (hd, d, ly_do)  # bậc 1: nhãn trên chính ảnh khớp tên + dịch vụ
                break
        if nguoi_nha and r["hd"] and r["diem"] > 50 and nguoi_nha in {
                x["ma_kh"] or x["code"] for x in visits if x["code"] == r["hd"]}:
            # Nhãn khớp lại chính khách của SĐT (so không dấu: 'Quyền' ~ 'Quyên') -> không nâng lại 'chac'.
            r.update(hd=None, diem=0)
            r.pop("khoa_nhan", None)
        if tho and not r["hd"]:
            r.update(hd=tho[0], diem=tho[1], ly_do=tho[2], do_tin="goi_y")
        r["goi"] = bool(r["hd"]) and "buổi theo gói" in (r["ly_do"] or "")
        r["lui"] = bool(r["hd"]) and r["diem"] == 50 and "ảnh không có ngày chụp gốc (có thể gửi" in (r["ly_do"] or "")

    _chan_neo_goi(photos, ket_qua, nhan_that)

    if not visits:
        # Ngày không HĐ nào (Tết...) mà nhãn khớp HĐ cũ (buổi theo gói): ảnh cùng đợt không còn là
        # 'không HĐ' -> để bộ chụp/đợt lan gợi ý; còn sót thì 'chưa rõ', người chọn.
        dot_co = {r["dot"] for r in ket_qua.values() if r["hd"] and not r.get("lui")}
        dot_lui = {r["dot"] for r in ket_qua.values() if r["hd"] and r.get("lui")}  # chỉ kéo ảnh không ngày gốc
        for r in ket_qua.values():
            if r["do_tin"] == "khong_hd" and (r["dot"] in dot_co or (r["dot"] in dot_lui and r["ngay_goc"] == 0)):
                r["do_tin"] = "chua_ro"

    # HĐ chỉ đến từ ảnh không có ngày chụp gốc khớp HĐ 1–2 ngày trước (không neo nào khác cùng HĐ).
    hd_lui = {r["hd"] for r in ket_qua.values() if r.get("lui")} - {
        r["hd"] for r in ket_qua.values() if r["hd"] and r["diem"] >= 50 and not r.get("lui")}
    # Mặt cụm mạnh của từng ảnh (khoá khách) + khoá khách của HĐ trong ngày: để luật bộ biết ảnh xen kẽ của khách khác.
    nho_k: dict = {}
    khoa_hd = {v["code"]: _khoa_hd(conn, cum, v["code"], nho_k) for v in visits}
    for p in photos:
        c_ = _khach_cua_mat(cum, p["khuon_mat"])
        ket_qua[p["id"]]["mat_k"] = c_["khach"] if c_ and c_["neo"] >= CUM_MANH else None
    _bo_chup([ket_qua[p["id"]] for p in photos], hd_lui, khoa_hd)

    # Ảnh chưa khớp lấy theo ảnh "neo" trong cùng đợt. Neo = ảnh có nhãn (khớp được hay không) hoặc
    # đã khớp hóa đơn điểm >= 50. Một đợt 15' có thể chứa nhiều khách: chỉ lan cả đợt khi mọi neo cùng
    # 1 hóa đơn VÀ có neo khớp mạnh (>= 80); neo chỉ khớp một phần/gần đúng (50) thì chỉ lan theo loạt
    # chụp liền. Ảnh giờ trùng giây không được làm neo cũng không được nhận hóa đơn theo giờ.
    for so_dot in {r["dot"] for r in ket_qua.values()}:
        cung = [r for r in ket_qua.values() if r["dot"] == so_dot and not r["trung_giay"]]
        neo = [r for r in cung if r["nhan"] or (r["hd"] and r["diem"] >= 50)]
        if not neo:
            continue
        cho = [r for r in cung if not r["hd"] and not r["nhan"] and r["do_tin"] != "khong_hd"]
        hd_neo = {_hd_neo(r) for r in neo}
        mot_hd = len(hd_neo) == 1 and None not in hd_neo
        if mot_hd and any(r["diem"] >= 80 for r in neo):
            hd = hd_neo.pop()
            for r in cho:
                r.update(hd=hd, do_tin="goi_y", ly_do="cùng đợt chụp với ảnh đã khớp tên")
            continue
        # Chỉ lan theo CHUỖI ảnh chụp liền (2 ảnh kề nhau cách <= CHUOI_GIAY): quãng trống dài hơn
        # là lúc đổi khách (soát 25 ảnh: 2 ca sai đều lan qua quãng trống > 60s).
        la_neo = {id(n) for n in neo}
        for r in cho:
            i = cung.index(r)
            tim = []  # (giây tới neo, hd) của neo đầu tiên gặp mỗi phía
            for buoc in (-1, 1):
                j = i
                while 0 <= j + buoc < len(cung) and \
                        abs((cung[j + buoc]["gio"] - cung[j]["gio"]).total_seconds()) <= CHUOI_GIAY:
                    j += buoc
                    if id(cung[j]) in la_neo:
                        tim.append((abs((cung[j]["gio"] - r["gio"]).total_seconds()), _hd_neo(cung[j]),
                                    cung[j]["diem"]))
                        break
            tim.sort(key=lambda x: x[0])
            if tim and tim[0][1] and (len(tim) == 1 or tim[1][1] == tim[0][1] or tim[1][0] > tim[0][0]) \
                    and _lan_duoc(r, tim[0][1], hd_lui):
                cach = f"cách {tim[0][0] / 60:.0f}'"
                r.update(hd=tim[0][1], do_tin="goi_y",
                         ly_do=f"lan từ ảnh khớp một phần tên — cùng loạt chụp liền ({cach})" if tim[0][2] < 80
                         else f"đợt có nhiều khách — cùng loạt chụp liền với ảnh đã khớp ({cach})")
            elif mot_hd:
                r["ly_do"] = r["ly_do"] or "ảnh neo trong đợt chỉ khớp một phần tên, không cùng loạt chụp liền — người chọn"
            else:
                r["ly_do"] = r["ly_do"] or "đợt chụp có nhiều khách — người chọn"

    # Đợt chưa khớp: giờ hóa đơn thường cách giờ chụp ~2 phút (đo 184 ảnh chắc chắn 09-10/2026:
    # 80% trong -14..+27 phút) -> đợt chỉ có đúng 1 hóa đơn trong [đầu đợt -30', cuối đợt +45'] thì gợi ý.
    # Chỉ cho đợt không có ảnh nhãn nào; bỏ ảnh giờ trùng giây.
    for so_dot in {r["dot"] for r in ket_qua.values()}:
        tat_ca = [ket_qua[p["id"]] for p in photos if ket_qua[p["id"]]["dot"] == so_dot]
        if any(r["hd"] or r["nhan"] for r in tat_ca):
            continue
        cung = [r for r in tat_ca if not r["trung_giay"]]
        if not cung:
            continue
        dau, cuoi = cung[0]["gio"], cung[-1]["gio"]
        gan = [v for v in visits if v["gio"] and
               dau - dt.timedelta(minutes=GIO_TRUOC) <= dt.datetime.fromisoformat(f"{ngay}T{v['gio'][:5]}")
               <= cuoi + dt.timedelta(minutes=GIO_SAU)]
        if len(gan) == 1:
            for r in cung:
                # Ảnh không có ngày chụp gốc: giờ trên ảnh là giờ nhận, không so với giờ HĐ được.
                if r["do_tin"] != "khong_hd" and r["ngay_goc"] != 0:
                    r.update(hd=gan[0]["code"], do_tin="goi_y",
                             ly_do=f"chỉ 1 hóa đơn gần giờ chụp ({gan[0]['gio'][:5]})")

    # Còn lại: nếu cả ngày chỉ 1 khách -> gợi ý khách đó.
    if len(visits) == 1:
        for r in ket_qua.values():
            if not r["hd"] and r["do_tin"] != "khong_hd":
                r.update(hd=visits[0]["code"], do_tin="goi_y", ly_do="cả ngày chỉ có 1 hóa đơn")

    _goi_y_khuon_mat(conn, ngay, photos, ket_qua)
    # Luật CỤM MẶT -> KHÁCH: nhận lại ảnh theo cụm mặt đã gắn khách, lan bộ chụp, cảnh báo ảnh chắc lệch mặt.
    if cum is None:
        cum = cum_khach(conn)
    _lan_bo_theo_mat(ket_qua, _nhan_lai_theo_mat(conn, ngay, photos, ket_qua, nhan_that, cum), conn)
    _canh_bao_mat(conn, photos, ket_qua, cum)

    _khoa_nhan_tren_anh(ket_qua)

    for r in ket_qua.values():
        if r["trung_giay"] and not r["hd"] and r["do_tin"] != "khong_hd":
            r["ly_do"] = r["ly_do"] or "giờ ảnh trùng từng giây với nhiều ảnh khác (giờ nhập, không phải giờ chụp) — người chọn"

    for pid, r in ket_qua.items():
        conn.execute(
            "UPDATE photos SET dot=?, goi_y_hd=?, do_tin=?, ly_do=? WHERE id=?",
            (r["dot"], r["hd"], r["do_tin"], r["ly_do"], pid),
        )
    # Nhãn ghi 'sau'/'trước' -> điền sẵn ô trước/sau, chỉ khi ô còn trống và ảnh chưa được người duyệt.
    for p in photos:
        loai = next((n["loai"] for n in doc_nhan(f"{p['chu_thich']} {p['ocr']}", int(ngay[:4])) if n["loai"]), "")
        if loai:
            conn.execute("UPDATE photos SET loai_anh=? WHERE id=? AND xn_hd IS NULL AND bo_qua=0"
                         " AND COALESCE(loai_anh,'')=''", (loai, p["id"]))


def _nhan_khop_dv(conn, nhan: dict, hd: str) -> bool:
    """Nhãn ghi mã dịch vụ có trong bảng ma_dich_vu.json và mã đó khớp dịch vụ của HĐ hd."""
    m = MA_DV_OCR.get(nhan["ma_dv"], nhan["ma_dv"])
    if not m or _dv_chung(m) or m not in MA_DV:
        return False
    v = conn.execute("SELECT dich_vu FROM visits WHERE code=?", (hd,)).fetchone()
    return bool(v) and _dv_khop(m, v["dich_vu"] or "")


def _khoa_nhan_tren_anh(ket_qua: dict) -> None:
    """THỨ BẬC bằng chứng (CEO 16/10 lần 5), kiểm CUỐI sau mọi luật: (1) nhãn trên CHÍNH ảnh khớp tên + dịch vụ HĐ
    > (2) cụm mặt mạnh của khách có HĐ cùng ngày > (3) nhãn cùng bộ > (4) giờ. Ảnh có bậc 1 (r['khoa_nhan']) mà luật
    sau (bộ/mặt/cảnh báo mặt/nhãn khách khác) đã đổi HĐ hoặc hạ -> trả lại kết quả của nhãn. Không đụng ảnh đã duyệt."""
    for r in ket_qua.values():
        k = r.get("khoa_nhan")
        if not k or r["xn"]:
            continue
        hd, d, ly_do = k
        if r["hd"] != hd or r["do_tin"] != "chac":
            r.update(hd=hd, diem=d, do_tin="chac",
                     ly_do=ly_do + " — giữ theo nhãn trên chính ảnh (khớp tên + dịch vụ, bậc cao nhất)")


GOI_BO_TOI_DA = 6  # ảnh gợi ý theo gói chỉ làm neo cho bộ chụp <= 6 tư thế


def _chan_neo_goi(photos, ket_qua, nhan_ds) -> None:
    """Ảnh gợi ý theo gói KHÔNG làm neo (không kéo bộ chụp/đợt) khi bộ của nó > GOI_BO_TOI_DA tư thế, hoặc
    đợt có >= 2 nhãn tên khác nhau (soát 14/10: bộ 14 ảnh đợt nhiều khách bị kéo theo 1 nhãn gói)."""
    goi = [p for p in photos if ket_qua[p["id"]].get("goi")]
    if not goi:
        return

    def ten(n):
        w = n["ten"].split()
        return " ".join(w[1:] if len(w) > 1 and w[0] in XUNG_HO else w)

    for p in goi:
        r = ket_qua[p["id"]]
        tt = {ket_qua[q["id"]]["gio"] for q in photos
              if r["bo"] is not None and ket_qua[q["id"]]["bo"] == r["bo"]}
        ten_dot = {ten(n) for q in photos if ket_qua[q["id"]]["dot"] == r["dot"] and not _la_giay_to(q)
                   for n in nhan_ds[q["id"]]}
        if len(tt) > GOI_BO_TOI_DA or len(ten_dot) >= 2:
            r["khong_neo"] = True
            r["ly_do"] += (f" — bộ {len(tt)} tư thế" if len(tt) > GOI_BO_TOI_DA else
                           f" — đợt có {len(ten_dot)} nhãn tên khác nhau") + ": không kéo ảnh khác"


def _chia_bo(ds: list[dict]) -> None:
    """Gắn số bộ chụp (r['bo']) như _bo_chup: chuỗi ảnh liền nhau cách <= BO_GIAY, bỏ ảnh trùng giây (bo=None)."""
    so, truoc = -1, None
    for r in ds:
        r["bo"] = None
        if r["trung_giay"]:
            continue
        if truoc is None or (r["gio"] - truoc["gio"]).total_seconds() > BO_GIAY:
            so += 1
        r["bo"], truoc = so, r


def _ten_nhan_hop(nhan: dict, ten_kh: str) -> bool:
    """Tên trên nhãn có thể là khách này: chữ nhãn (bớt chữ chung thừa bên trái, như _khop_ten) nằm trong họ tên
    đã làm sạch hoặc tên gọi trong ngoặc, hoặc chữ cuối lệch 1 chữ (OCR). Nhãn và tên khách đều còn dấu thì
    phải cùng dấu ('Quyền' != 'Quyên'). Dùng để biết nhãn ghi tên KHÁC hẳn."""
    if nhan.get("quan_he"):  # nhãn người nhà: không bao giờ hợp khách <tên>
        return False
    tg = _tu_ten_goi(ten_kh)
    t = [k for _, k in tg]
    w = nhan["ten"].split()
    wg = (nhan.get("ten_goc") or nhan["ten"]).split()
    if len(wg) != len(w):
        wg = w
    if len(w) > 1 and w[0] in XUNG_HO and not set(w) <= set(t):
        w, wg = w[1:], wg[1:]
    if _dao_ten(ten_kh):  # khách 'Vy Nguyễn' / tên Tây (đã đảo) -> nhãn đảo theo
        hv = _hoan_vi_goi(list(zip(wg, w)))
        w, wg = _thu_tu_goi(w, hv), _thu_tu_goi(wg, hv)
    if not w:
        return True
    dau_kh = _co_dau([g for g, _ in tg])
    for k in range(len(w), 0, -1):
        if not _bot_duoc(w, k):  # luật tên 16/10: nhãn >= 2 chữ chỉ bớt chữ chung bên trái
            break
        # Đủ mọi chữ nhãn (không kể chữ chung bỏ bên trái) có trong họ tên -> có thể là khách này, kể cả khác thứ
        # tự/vị trí (CEO 16/10); thiếu chữ nào ('Ngọc Anh' vs 'Nguyễn Thị Anh') -> tên khác.
        # Nhãn 1 chữ (hoặc còn 1 chữ sau khi bớt chữ chung) chỉ khớp TÊN CUỐI, không khớp chữ đệm (CEO 16/10).
        if (set(w[-k:]) <= set(t)) if k >= 2 else _mot_chu_khop(w[-1], t, _la_ten_tay(tg)):
            if not (dau_kh and _co_dau(wg[-k:])) or all(
                    any(khong_dau(a) == kk and _chu_mot_chieu(a, g) for g, kk in tg) for a in wg[-k:]):
                return True
    if any(set(w) <= set(b) for b in _bi_danh(ten_kh)):
        return True
    return (bool(t) and len(w[-1]) >= 4 and _lech_1(w[-1], t[-1])
            and (len(w) < 2 or (len(t) >= len(w) and t[-len(w):-1] == w[:-1])))


def _ten_nhan_gon(nhan: dict, t: list[str], dao: bool = False) -> list[str]:
    """Chữ tên trên nhãn (không dấu) bỏ xưng hô đầu nhãn (trừ khi khách mang đủ các chữ đó) và chữ chung bên trái."""
    w = nhan["ten"].split()
    if len(w) > 1 and w[0] in XUNG_HO and not set(w) <= set(t):
        w = w[1:]
    while len(w) > 1 and w[0] in _CHU_THUA_TEN:
        w = w[1:]
    return _thu_tu_goi(w) if dao else w  # dao: tên khách đã đảo kiểu 'Tên Họ' (_dao_ten)


def _gan_chu(x: str, y: str) -> bool:
    """Cùng chữ (không dấu) hoặc OCR lệch 1 ký tự (chữ >= 4 ký tự: 'thaor' ~ 'thao')."""
    return x == y or (max(len(x), len(y)) >= 4 and _lech_1(x, y))


def _ten_hop_mat(nhan: dict, ten_kh: str) -> bool:
    """Luật mặt (CEO 16/10): ảnh có mặt thuộc cụm MẠNH của khách K -> nhãn HỢP với K (so không dấu) khi:
    nhãn 1 chữ = TÊN CUỐI của K (lệch 1 ký tự OCR được) hoặc = CHỮ ĐỆM của K ('Phương' ~ 'Lê Thị Phương Thảo' —
    CEO 16/10 lần 2: mặt mạnh thì chữ đệm vẫn chắc; nhãn khớp đúng đuôi khách khác cùng ngày thì nơi gọi chặn);
    nhãn >= 2 chữ: (a) mọi chữ có trong họ tên K (bất kỳ thứ tự), (b) mỗi chữ khớp 1 chữ của K cho lệch 1 ký tự,
    (c) >= 2 chữ khớp chữ của K (chữ đệm + tên thiếu chữ cuối), hoặc (d) chữ cuối nhãn = tên cuối K (chữ đệm ghi
    sai: 'Ngọc Mai' ~ 'Trịnh Xuân Mai'). Chữ viết tắt 1 ký tự ('T.Yến') = chữ cái đầu 1 chữ của K thì bỏ qua."""
    if nhan.get("quan_he"):  # nhãn người nhà: không bao giờ hợp khách <tên>
        return False
    tg = _tu_ten_goi(ten_kh)
    t = [k for _, k in tg]
    w = _ten_nhan_gon(nhan, t, _dao_ten(ten_kh))
    if not w:
        return True
    if not t:
        return False
    if any(set(w) <= set(b) for b in _bi_danh(ten_kh)):
        return True
    w = [x for x in w if len(x) > 1 or not any(y[0] == x for y in t)] or w
    if len(w) == 1:
        return _mot_chu_khop(w[0], t, _la_ten_tay(tg), _gan_chu) or w[0] in t
    return (set(w) <= set(t) or all(any(_gan_chu(x, y) for y in t) for x in w)
            or len(set(w) & set(t)) >= 2 or w[-1] == t[-1])


def _ten_dung_duoi(nhan: dict, ten_kh: str, ocr: bool = True) -> bool:
    """Nhãn khớp ĐÚNG đuôi họ tên (đủ số chữ, không dấu); ocr=True: chữ cuối được lệch 1 ký tự; hoặc tên trong ngoặc."""
    if nhan.get("quan_he"):  # nhãn người nhà: không bao giờ hợp khách <tên>
        return False
    tg = _tu_ten_goi(ten_kh)
    t = [k for _, k in tg]
    w = _ten_nhan_gon(nhan, t, _dao_ten(ten_kh))
    if not w or len(t) < len(w):
        return False
    if t[-len(w):] == w or any(b == w for b in _bi_danh(ten_kh)):
        return True
    if _la_ten_tay(tg) and (_mot_chu_khop(w[0], t, True) if len(w) == 1 else _duoi_tay(w, t)):
        return True  # tên Tây: nhãn 1 chữ = tên cuối gốc / nhãn >= 2 chữ = đuôi theo thứ tự gốc
    return ocr and t[-len(w):-1] == w[:-1] and len(w[-1]) >= 4 and _lech_1(w[-1], t[-1])


_THANH = {"\u0300", "\u0301", "\u0303", "\u0309", "\u0323"}  # dấu thanh: huyền, sắc, ngã, hỏi, nặng


def _tach_thanh(g: str) -> tuple[str, set]:
    """'ều' -> ('êu', {huyền}): chữ cái (còn mũ/móc/trăng, đ) và dấu thanh."""
    nfd = unicodedata.normalize("NFD", g.lower())
    return (unicodedata.normalize("NFC", "".join(c for c in nfd if c not in _THANH)),
            {c for c in nfd if c in _THANH})


def _chu_mot_chieu(a: str, g: str) -> bool:
    """Chữ nhãn a có thể là chữ g của tên khách, so dấu MỘT CHIỀU (OCR hay mất dấu huyền trên ê/ă):
    nhãn THIẾU dấu thanh ('Kiêu' ~ 'Kiều', 'Hăng' ~ 'Hằng') -> cùng chữ; chữ nhãn mất hết dấu -> so không dấu.
    Khác chữ cái ('Nhân' vs 'Nhàn': â≠a) hoặc nhãn có dấu thanh mà tên không có/khác ('Quyền' vs 'Quyên') -> khác."""
    if _dau(a) == (0, ""):
        return khong_dau(a) == khong_dau(g)
    (ca, ta), (cg, tg) = _tach_thanh(a), _tach_thanh(g)
    return ca == cg and (not ta or ta == tg)


_GIAY_TO = ("phieu", "don thuoc", "cam ket", "hoa don", "doctorlaser org")


def _la_giay_to(p) -> bool:
    """Ảnh chụp giấy tờ (phiếu khám, đơn thuốc, cam kết...): chữ in nhiều, không phải nhãn viết tay của bộ chụp."""
    chu = khong_dau(p["ocr"] or "")
    return any(k in chu for k in _GIAY_TO) or len(chu.split()) >= 25


def _nhan_that(p, nam: int) -> list[dict]:
    """Nhãn nhân viên viết trên ảnh, KHÔNG lấy từ chú thích do chính máy ghi (gan_chac/xuat: 'KH… · tên · SĐT ·
    …' + từ khoá mã KH/HĐ) — chú thích đó có ' · ' -> bỏ cả phần chú thích, chỉ đọc chữ OCR trên ảnh."""
    ct = p["chu_thich"] or ""
    return doc_nhan(f"{'' if ' · ' in ct else ct} {p['ocr'] or ''}", nam)


def _nhan_ten_khac(ten_kh: str, p, photos, ket_qua, nhan_ds) -> str | None:
    """Nhãn gần ảnh nhất (chính ảnh, không có thì cả BỘ CHỤP — không lấy cả đợt: đợt có nhiều khách) đều ghi
    tên không khớp khách -> id ảnh có nhãn đó (để ghi vào lý do); không thì None. Bỏ nhãn đọc từ ảnh giấy tờ.
    nhan_ds: id ảnh -> nhãn thật (_nhan_that)."""
    r = ket_qua[p["id"]]
    for cung in (lambda q: q["id"] == p["id"],
                 lambda q: r["bo"] is not None and ket_qua[q["id"]]["bo"] == r["bo"]):
        ds = [(q["id"], n) for q in photos if cung(q) and not _la_giay_to(q) for n in nhan_ds[q["id"]]]
        if ds:
            return None if any(_ten_nhan_hop(n, ten_kh) for _, n in ds) else ds[0][0]
    return None


def _mat_khac_khach(conn, ngay: str, hd: str, km: str | None, mat_nho: dict) -> bool:
    """Luật gói: ảnh có mã người (app Ảnh) và ảnh đã xác nhận/chắc của mã KH đó (ngày khác) cũng có, nhưng
    KHÔNG chung mã người nào -> khác người."""
    if not km:
        return False
    v = conn.execute("SELECT ma_kh FROM visits WHERE code=?", (hd,)).fetchone()
    if not v or not v["ma_kh"]:
        return False
    ma = v["ma_kh"]
    if ma not in mat_nho:
        mat_nho[ma] = {u for (x,) in conn.execute(
            "SELECT p.khuon_mat FROM photos p JOIN visits v ON v.code = "
            "COALESCE(p.xn_hd, CASE WHEN p.do_tin='chac' THEN p.goi_y_hd END) "
            "WHERE v.ma_kh=? AND p.bo_qua=0 AND p.ngay != ? AND COALESCE(p.khuon_mat,'') != ''", (ma, ngay))
            for u in x.split()}
    return bool(mat_nho[ma]) and not (set(km.split()) & mat_nho[ma])


def _nguoi_cua_khach(conn, ngay: str, photos, ket_qua) -> dict[str, set]:
    """mã người (app Ảnh) -> các mã KH, từ ảnh ĐÃ DUYỆT (xn_hd) hoặc máy chấm 'chac'.
    Ngày khác lấy trong DB; ngày đang ghép lấy kết quả vừa tính."""
    m: dict[str, set] = {}

    def them(km, ma):
        for u in (km or "").split():
            if ma:
                m.setdefault(u, set()).add(ma)

    for r in conn.execute(
            "SELECT p.khuon_mat, v.ma_kh FROM photos p JOIN visits v ON v.code = "
            "COALESCE(p.xn_hd, CASE WHEN p.do_tin='chac' THEN p.goi_y_hd END) "
            "WHERE p.bo_qua=0 AND p.ngay != ? AND COALESCE(p.khuon_mat,'') != ''", (ngay,)):
        them(r["khuon_mat"], r["ma_kh"])
    for p in photos:
        r = ket_qua[p["id"]]
        hd = p["xn_hd"] or (r["hd"] if r["do_tin"] == "chac" else None)
        if hd and not p["bo_qua"] and p["khuon_mat"]:
            v = conn.execute("SELECT ma_kh FROM visits WHERE code=?", (hd,)).fetchone()
            them(p["khuon_mat"], v["ma_kh"] if v else None)
    return m


def _goi_y_khuon_mat(conn, ngay: str, photos, ket_qua) -> None:
    """Ảnh chưa có HĐ sau mọi luật: trùng mã người với ảnh đã xác nhận của ĐÚNG 1 khách có HĐ cùng
    ngày (ngày chụp hoặc ngày ghi trên nhãn) -> CHỈ gợi ý, không bao giờ 'chac'.
    Mã người gắn với >= 2 khách (nhân viên/bác sĩ hay lọt ảnh, hoặc app Ảnh gộp nhầm) thì bỏ."""
    cho = [p for p in photos if p["khuon_mat"] and not ket_qua[p["id"]]["hd"]
           and ket_qua[p["id"]]["do_tin"] != "khong_hd"]
    if not cho:
        return
    m = _nguoi_cua_khach(conn, ngay, photos, ket_qua)
    for p in cho:
        r = ket_qua[p["id"]]
        ngays = {ngay} | {n["ngay"] for n in doc_nhan(f"{p['chu_thich']} {p['ocr']}", int(ngay[:4])) if n["ngay"]}
        khach = {next(iter(m[u])) for u in p["khuon_mat"].split() if len(m.get(u, ())) == 1}
        ung = {}
        for ma in khach:
            vs = conn.execute(f"SELECT * FROM visits WHERE ma_kh=? AND ngay IN ({','.join('?' * len(ngays))})"
                              " ORDER BY ngay != ?, gio", (ma, *sorted(ngays), ngay)).fetchall()
            if vs:  # cùng cách chọn với luật cụm mặt (_chon_hd_mat): ngày chụp, không phải HĐ thu tiền, gần giờ chụp
                ung[ma] = min(vs, key=lambda v: (v["ngay"] != ngay, not _hd_that(v["dich_vu"]), _chi_thu_tien(v["dich_vu"]),
                                                 _cach_gio(v, r["gio"])))
        if len(ung) == 1:
            v = next(iter(ung.values()))
            r.update(hd=v["code"], do_tin="goi_y", diem=40,
                     ly_do="cùng khuôn mặt với ảnh đã xác nhận của khách")


# ---------------- CỤM MẶT -> KHÁCH (luật 15/10) ----------------
# App Ảnh gom khuôn mặt thành cụm người (person uuid). Cụm được gắn cho 1 khách khi đủ ảnh "neo mạnh" của
# khách đó (người duyệt, hoặc máy chấm 'chac' theo nhãn/tên/SĐT/mã KH — KHÔNG tính 'chac' do lan bộ/đợt hay do
# chính luật mặt, tránh tự khuếch đại). Cụm có phiếu nhiều khách = nhân viên/bác sĩ/người nhà -> không dùng.
CUM_W_XN, CUM_W_CHAC = 3, 1  # trọng số phiếu: ảnh người duyệt / ảnh máy chấm chắc theo nhãn-tên
CUM_NEO_TOI_THIEU = 3  # >= 3 ảnh neo (hoặc >= 1 ảnh đã duyệt + >= 1 ảnh neo khác)
CUM_TY_LE = 0.9  # khách chính >= 90% phiếu
CUM_LAN_TY_LE, CUM_LAN_ANH = 0.1, 2  # khách thứ 2 >= 10% phiếu hoặc >= 2 ảnh -> cụm lẫn
CUM_NGAY = 2  # ảnh neo của khách chính nằm ở >= 2 ngày khác nhau (1 ngày = 1 buổi, có thể chỉ 1 nhãn lan ra)
CUM_MANH = 5  # cụm >= 5 ảnh neo mới được dùng để CẢNH BÁO hạ ảnh 'chac' đang gắn khách khác
MAT_DIEM = 82  # ảnh nhận theo cụm mặt + HĐ cùng ngày (>= 80: làm neo chắc cho bộ chụp)
MAT_TOI_DA = 2  # chỉ ảnh 1–2 mặt (ảnh nhiều mặt có thể lẫn nhân viên/người nhà)
_NEO_TEN = ("khớp SĐT", "khớp mã KH", "khớp tên '", "nhãn '")
_NEO_BO = re.compile(r"^cùng bộ chụp (?:liền (\d+) ảnh|(\d+) tư thế) với ảnh có nhãn '")


def _doc_mat(km) -> list[str]:
    """photos.khuon_mat -> danh sách mã người. Lưu dạng cách nhau dấu cách (_ma_nguoi); nhận cả JSON list."""
    s = (km or "").strip()
    if not s:
        return []
    if s.startswith("["):
        try:
            return sorted({str(x) for x in json.loads(s) if x})
        except ValueError:
            return []
    return sorted(set(s.split()))


def _la_neo_mat(do_tin: str | None, ly_do: str | None) -> bool:
    """Ảnh máy chấm 'chac' được làm phiếu cho cụm mặt: khớp SĐT/mã KH/tên/nhãn trên chính ảnh, hoặc cùng bộ
    chụp <= BO_TOI_DA với ảnh có nhãn. Không tính chắc do lan bộ từ ảnh 'đã khớp chắc', do đợt, do luật mặt."""
    if do_tin != "chac" or not ly_do or "khuôn mặt" in ly_do:
        return False
    if ly_do.startswith(_NEO_TEN):
        return True
    m = _NEO_BO.match(ly_do)
    return bool(m) and int(m.group(1) or m.group(2)) <= BO_TOI_DA


def _khoa_khach(conn) -> dict[str, str]:
    """mã KH -> khoá người. Hai mã KHÁC HỆ ('CU-KH…' mã cũ vs 'KH…' mã mới, 'CU-…') mà CÙNG SĐT = 1 người.
    Hai mã cùng hệ cùng SĐT (người nhà dùng chung số) vẫn là 2 người."""
    cha: dict[str, str] = {}

    def goc(x):
        while cha.get(x, x) != x:
            x = cha[x]
        return x

    theo_sdt: dict[str, set] = {}
    for ma, sdt in conn.execute("SELECT DISTINCT ma_kh, sdt FROM visits WHERE COALESCE(ma_kh,'') != ''"):
        cha.setdefault(ma, ma)
        s = chuan_sdt(sdt)
        if len(s) >= 9:
            theo_sdt.setdefault(s[-9:], set()).add(ma)
    for mas in theo_sdt.values():
        ds = sorted(mas)
        for i, a in enumerate(ds):
            for b in ds[i + 1:]:
                if re.sub(r"\d+", "", a) != re.sub(r"\d+", "", b):
                    ra, rb = goc(a), goc(b)
                    if ra != rb:
                        cha[max(ra, rb)] = min(ra, rb)
    return {ma: goc(ma) for ma in cha}


def cum_khach(conn) -> dict:
    """Bảng CỤM MẶT -> KHÁCH cho cả DB (tính 1 lần mỗi lượt ghép).
    Trả {'cum': uuid -> {khach, ma, neo, xn, ngay}, 'lan': {uuid lẫn}, 'khoa': mã KH -> khoá người,
    'nhom': khoá -> {mã KH}}. ma = mã KH (trong nhóm) có nhiều ảnh neo nhất, để hiện ảnh mẫu."""
    khoa = _khoa_khach(conn)
    nhom: dict[str, set] = {}
    for ma, k in khoa.items():
        nhom.setdefault(k, set()).add(ma)
    phieu: dict[str, dict] = {}  # uuid -> khoá -> [điểm, số ảnh, số ảnh duyệt, {ngày}, {mã KH: số ảnh}]
    for r in conn.execute(
            "SELECT p.khuon_mat, p.ngay, p.xn_hd, p.do_tin, p.ly_do, v.ma_kh, v.code FROM photos p JOIN visits v"
            " ON v.code = COALESCE(p.xn_hd, CASE WHEN p.do_tin='chac' THEN p.goi_y_hd END)"
            " WHERE p.bo_qua=0 AND COALESCE(p.khuon_mat,'') != ''"):
        mat = _doc_mat(r["khuon_mat"])
        if not 1 <= len(mat) <= MAT_TOI_DA:
            continue
        if r["xn_hd"]:
            w = CUM_W_XN
        elif _la_neo_mat(r["do_tin"], r["ly_do"]):
            w = CUM_W_CHAC
        else:
            continue
        ma = r["ma_kh"] or r["code"]
        k = khoa.get(ma, ma)
        for u in mat:
            x = phieu.setdefault(u, {}).setdefault(k, [0, 0, 0, set(), {}])
            x[0] += w
            x[1] += 1
            x[2] += bool(r["xn_hd"])
            x[3].add(r["ngay"])
            x[4][ma] = x[4].get(ma, 0) + 1
    cum, lan = {}, set()
    for u, ks in phieu.items():
        xep = sorted(ks.items(), key=lambda kv: (-kv[1][0], kv[0]))
        tong = sum(x[0] for _, x in xep)
        k, (diem, so, xn, ngays, mas) = xep[0]
        if len(xep) > 1 and (xep[1][1][0] >= CUM_LAN_TY_LE * tong or xep[1][1][1] >= CUM_LAN_ANH):
            lan.add(u)
            continue
        du_neo = so >= CUM_NEO_TOI_THIEU or (xn >= 1 and so >= 2)
        if du_neo and diem >= CUM_TY_LE * tong and len(ngays) >= CUM_NGAY:
            cum[u] = {"khach": k, "ma": max(mas, key=lambda m: (mas[m], m)), "neo": so, "xn": xn,
                      "ngay": len(ngays)}
    return {"cum": cum, "lan": lan, "khoa": khoa, "nhom": nhom}


def _khach_cua_mat(cum: dict, km) -> dict | None:
    """Ảnh 1–2 mặt có mặt thuộc cụm đã gắn của ĐÚNG 1 khách -> thông tin cụm (cụm nhiều ảnh neo nhất);
    ảnh nhiều mặt, không cụm nào gắn, hoặc mặt thuộc cụm của 2 khách khác nhau -> None."""
    mat = _doc_mat(km)
    if not 1 <= len(mat) <= MAT_TOI_DA:
        return None
    ds = [cum["cum"][u] for u in mat if u in cum["cum"]]
    if not ds or len({x["khach"] for x in ds}) != 1:
        return None
    return max(ds, key=lambda x: x["neo"])


def _khoa_hd(conn, cum: dict, hd: str | None, nho: dict) -> str | None:
    """Khoá người của 1 mã HĐ."""
    if not hd:
        return None
    if hd not in nho:
        v = conn.execute("SELECT ma_kh FROM visits WHERE code=?", (hd,)).fetchone()
        ma = (v["ma_kh"] if v else None) or hd
        nho[hd] = cum["khoa"].get(ma, ma)
    return nho[hd]


def _hd_cua_khach(conn, cum: dict, khach: str, ngays: list[str]) -> list:
    mas = sorted(cum["nhom"].get(khach, set())) or [khach]
    dau, dn = ",".join("?" * len(mas)), ",".join("?" * len(ngays))
    return conn.execute(f"SELECT * FROM visits WHERE (ma_kh IN ({dau}) OR code IN ({dau})) AND ngay IN ({dn})",
                        (*mas, *mas, *ngays)).fetchall()


_THU_TIEN = re.compile(r"^(dat coc|coc|thanh toan|tra no|cong no|thu no)\b")


def _chi_thu_tien(dich_vu: str | None) -> bool:
    """HĐ chỉ là thu tiền (đặt cọc, thanh toán công nợ/combo...) — không phải buổi làm dịch vụ."""
    ds = [khong_dau(x) for x in (dich_vu or "").split("|") if x.strip()]
    return bool(ds) and all(_THU_TIEN.match(x) for x in ds)


# Dòng HĐ là SẢN PHẨM (thuốc, kem, mỹ phẩm) — không phải buổi làm dịch vụ (soát 16/10: ca 4ACBA65E, D66AE5A0).
_SAN_PHAM = re.compile(r"^(kem|thuoc|serum|sua rua|mat na|toner|gel|kcn|xit|vien uong|tinh chat|nuoc|lotion|my pham)\b"
                       r"|\b(cream|serum|pads?|gel|lotion|toner|cleanser|cleaser|sunscreen|mask|\d+\s*(g|ml))\b")
_TU_DV_THAT = re.compile(r"\b(tiem|laser|triet|peel|csd|cham soc|dien di|meso|prp|filler|botox|combo|lieu trinh|dieu tri"
                         r"|tri|xoa|mai|hifu|cang chi|nang|ipl|pico|picolight|fractional|co2|tre hoa|dot|lan le|kham)\b")


def _dong_dv(dich_vu: str | None) -> list[str]:
    return [khong_dau(x) for x in (dich_vu or "").split("|") if khong_dau(x)]


def _hd_that(dich_vu: str | None) -> bool:
    """HĐ có ít nhất 1 dòng là DỊCH VỤ thật (không phải chỉ thu tiền/đặt cọc/công nợ, không phải thuốc/kem/mỹ phẩm):
    chữ dịch vụ chung (_TU_DV_THAT) hoặc chữ trong bảng ma_dich_vu.json ('dặm vein mặt' — ca B2A478A3)."""
    def dv(x):
        return bool(_TU_DV_THAT.search(x)) or any(f" {k} " in f" {x} " for ks in MA_DV.values() for k in ks)
    return any(not _THU_TIEN.match(x) and not _SAN_PHAM.search(x) and not _PHU_DV.match(x) and dv(x)
               for x in _dong_dv(dich_vu))


# Dòng phụ trợ ('BÙ KIM RF (HỖ TRỢ KHI LÀM VỚI PRP)', bảo hành) xếp sau dịch vụ chính (ca 7CA6F7F8).
_PHU_DV = re.compile(r"^(bu|bao hanh|ho tro|tang|khuyen mai)\b")


_TAN = re.compile(r"\b(tan|tieu)\s+filler")


def _dv_hang(mas: list[str], dich_vu: str | None, chu_nhan: str = "") -> int:
    """Mức khớp dịch vụ nhãn với HĐ (nhỏ = khớp sát hơn): vị trí chữ khớp đầu tiên trong bảng ma_dich_vu.json
    ('co2': 'fractional' (1) sát hơn 'mụn thịt' (2)); khớp kiểu viết tắt/đầu chữ = 20; không khớp = 99; không mã nào = 0.
    Dòng 'tan/tiêu filler' không khớp mã filler/ha khi nhãn không ghi 'tan'/'tiêu' ('sau filler' != 'tan filler')."""
    mas = [m for m in mas if not _dv_chung(m)]
    if not mas:
        return 0
    tan_nhan = bool(re.search(r"\b(tan|tieu)\b", khong_dau(chu_nhan)))
    tot = 99
    for x in _dong_dv(dich_vu):
        if _TAN.search(x) and not tan_nhan and any(m in ("ha", "filler") for m in mas):
            continue
        chuoi = f" {x} "
        for m in mas:
            m2 = MA_DV_OCR.get(m, m)
            for i, k in enumerate(MA_DV.get(m2, [])):
                if f" {k} " in chuoi or (len(k) >= 4 and f" {k}" in chuoi):
                    # Hạng thô (CEO 16/10 lần 5, ca E514D8DB): 'co2' ~ 'fractional' ngang 'co2' -> giờ phân định;
                    # chỉ đồng nghĩa phụ ('mụn thịt', 'nám') mới xếp sau.
                    # hạng 0: chính tên mã, hoặc chữ đó cũng là 1 mã trong bảng ('fractional' của 'co2');
                    # hạng 1: đồng nghĩa phụ/chỉ định ('đốm nâu', 'nám' của 'pico'; 'mụn thịt' của 'co2') — ca 040983BF.
                    tot = min(tot, 0 if i == 0 or k in MA_DV else 1)
                    break
            else:
                if _dv_khop(m, x):
                    tot = min(tot, 2)
    return tot


def _cach_gio(v, luc: dt.datetime) -> float:
    """Số giây giữa giờ HĐ và giờ chụp (HĐ không giờ -> rất xa)."""
    try:
        return abs((dt.datetime.fromisoformat(f"{v['ngay']}T{(v['gio'] or '00:00')[:5]}") - luc).total_seconds())
    except ValueError:
        return 1e9


GIU_CU_PHUT = 20  # CEO 16/10 lần 4: không nhãn dịch vụ -> giữ HĐ lần ghép trước nếu chỉ chênh giờ < 20'


def _chon_hd_mat(vs: list, ngays: list[str], r: dict, ma_dvs: list[str], ma_quanh: list[str] | None = None,
                 chu_nhan: str = "", cu: str | None = None):
    """Nhiều HĐ của khách: giữ NGÀY của HĐ đang gợi ý (nếu là của K); rồi theo ngày ưu tiên
    (thứ tự `ngays`: ảnh có ngày gốc -> ngày chụp > ngày nhãn; không -> ngày nhãn > ngày chụp; rồi ngày lùi), dịch vụ
    khớp nhãn (ma_dvs: nhãn của ảnh, không có thì nhãn cùng bộ/đợt), giờ gần giờ chụp nhất, rồi mới tới HĐ đang gắn
    (CEO 16/10: ca 87EEA18F — 3 HĐ cùng ngày, HĐ đang gắn 14:39 thắng HĐ 17:31 khớp dịch vụ nhãn bộ + gần giờ chụp)."""
    def gio(v):
        return _cach_gio(v, r["gio"])

    # CEO 16/10 lần 3: mã nhãn của chính ảnh chỉ dùng khi khớp được ít nhất 1 HĐ của K (chữ OCR rác như 'limeorange'
    # thì bỏ); không thì lấy nhãn cùng bộ/đợt (ma_quanh).
    mas = [m for m in ma_dvs if not _dv_chung(m)]
    mas = [m for m in mas if m in MA_DV or m in MA_DV_OCR]
    if not mas or not any(_dv_hang(mas, v["dich_vu"], chu_nhan) < 99 for v in vs):
        mas = [m for m in (ma_quanh or []) if not _dv_chung(m)]
    # Chỉ mã có trong bảng ma_dich_vu.json mới xếp hạng HĐ (chữ lạ 'kim', 'nhang' khớp nhầm 'BÙ KIM RF' — ca 7CA6F7F8).
    mas = [m for m in mas if m in MA_DV or m in MA_DV_OCR]
    hang = {v["code"]: _dv_hang(mas, v["dich_vu"], chu_nhan) for v in vs}

    def dv_hop(v):
        return hang[v["code"]] < 99
    # HĐ đang gắn mà đúng của khách K thì giữ (soát 15/10: đổi sang HĐ ngày chụp làm sai buổi) — TRỪ khi (luật ngày
    # 16/10) ảnh có ngày gốc, HĐ đang gắn thuộc ngày khác ngày chụp (ngày nhãn) và K có HĐ ngày chụp khớp dịch vụ.
    giu = r["hd"]
    chup = r["gio"].date().isoformat()
    if giu and r.get("goc") == 1 and any(v["code"] == giu and v["ngay"] != chup for v in vs) \
            and any(v["ngay"] == chup and dv_hop(v) for v in vs):
        giu = None
    # HĐ đang gắn của K: giữ NGÀY (buổi) của nó; trong ngày đó chọn lại theo dịch vụ nhãn rồi giờ gần nhất.
    giu_ngay = next((v["ngay"] for v in vs if v["code"] == giu), None)
    # Có ngày gốc: HĐ khớp dịch vụ nhãn đứng trước (ngày chụp không có HĐ khớp dịch vụ mà ngày nhãn có -> ngày nhãn).
    # Thứ tự (CEO 16/10 lần 3): ngày -> dịch vụ khớp nhãn (sát nhất) -> HĐ có dịch vụ thật -> gần giờ chụp -> HĐ đang gắn.
    def khoa(v):
        return (giu_ngay is not None and v["ngay"] != giu_ngay, r.get("goc") == 1 and not dv_hop(v),
                ngays.index(v["ngay"]), hang[v["code"]], not _hd_that(v["dich_vu"]), _chi_thu_tien(v["dich_vu"]))
    tot = min(vs, key=lambda v: (*khoa(v), gio(v), v["code"] != giu))
    # HĐ của lần ghép trước (cu = photos.goi_y_hd) ngang hạng với HĐ tốt nhất, chỉ thua về giờ < GIU_CU_PHUT -> giữ.
    v_cu = next((v for v in vs if v["code"] == cu), None)
    if not mas and v_cu is not None and v_cu["code"] != tot["code"] and khoa(v_cu) == khoa(tot) \
            and abs(gio(v_cu) - gio(tot)) < GIU_CU_PHUT * 60:
        return v_cu
    return tot


def _chu_ma_nhan(n: dict, ten_kh: set) -> list[str]:
    """Mã dịch vụ của 1 nhãn + chữ trong phần tên nhãn không thuộc tên khách ('Khắc Bách XVM' -> 'xvm')."""
    ds = [n["ma_dv"]] if n["ma_dv"] and not _dv_chung(n["ma_dv"]) else []
    return ds + [x for x in n["ten"].split() if x not in ten_kh and len(x) >= 2 and x not in XUNG_HO]


def _nhan_bo_khach_khac(conn, cum: dict, p, photos, ket_qua, k: str, nho: dict) -> bool:
    """Ảnh nằm trong bộ chụp ngắn (<= BO_TOI_DA tư thế) mà bộ có ảnh KHÁC khớp chắc theo chứng cứ riêng (nhãn/tên/SĐT/
    mã KH trên chính ảnh đó) HĐ của khách khác K, VÀ ảnh nhãn đó có mặt người mà không mặt nào thuộc cụm của K (ảnh nhãn
    là người khác) -> True: luật mặt không nhận ảnh này. Ảnh nhãn mang mặt của K (nhân viên ghi nhầm tên) hoặc không có
    mặt -> mặt vẫn thắng (soát 16/10: 58D8022E, 03514DD8 đúng theo mặt); bộ có >= 2 ảnh mang mặt K -> mặt thắng."""
    r = ket_qua[p["id"]]
    if r["bo"] is None:
        return False
    b = [(q, ket_qua[q["id"]]) for q in photos if ket_qua[q["id"]]["bo"] == r["bo"]]
    if len({x["gio"] for _, x in b}) > BO_TOI_DA:
        return False
    def mat_k(q):
        return any(cum["cum"].get(u, {}).get("khach") == k for u in _doc_mat(q["khuon_mat"]))

    def mat_nguoi_khac(q):
        mat = _doc_mat(q["khuon_mat"])
        return 1 <= len(mat) <= MAT_TOI_DA and not mat_k(q)
    # >= 2 ảnh trong bộ mang mặt K (soát 16/10 lần 5, ca BDC6E6FD: 2 tấm cuối bộ là người khác thật) -> mặt thắng;
    # chỉ 1 tấm lạc mặt giữa chuỗi ảnh của khách nhãn (195AA4FA, 3C48643B, D96ACC42) -> nhãn thắng.
    if sum(mat_k(q) for q, _ in b) >= 2:
        return False
    return any(q["id"] != p["id"] and x["hd"] and x["diem"] >= 80 and (x["ly_do"] or "").startswith(_NEO_TEN)
               and _khoa_hd(conn, cum, x["hd"], nho) != k and mat_nguoi_khac(q) for q, x in b)


def _dv_nhan_quanh(p, photos, ket_qua, nhan_ds, ten_kh: set = frozenset()) -> list[str]:
    """Mã dịch vụ trên nhãn các ảnh CÙNG BỘ chụp với p (kể cả chữ mã nằm trong phần tên, _chu_ma_nhan); bộ không có
    thì cùng ĐỢT. Bỏ giấy tờ."""
    r = ket_qua[p["id"]]
    for cung in (lambda q: r["bo"] is not None and ket_qua[q["id"]]["bo"] == r["bo"],
                 lambda q: ket_qua[q["id"]]["dot"] == r["dot"]):
        ds = [m for q in photos if q["id"] != p["id"] and cung(q) and not _la_giay_to(q)
              for n in nhan_ds[q["id"]] for m in _chu_ma_nhan(n, ten_kh)]
        if ds:
            return ds
    return []


def _nhan_lai_theo_mat(conn, ngay: str, photos, ket_qua, nhan_ds, cum: dict) -> list[str]:
    """Luật CỤM MẶT bước 2: ảnh chưa duyệt, chưa 'chac', mặt thuộc cụm của khách K:
    (a) K có HĐ ngày chụp/ngày nhãn (ảnh không ngày gốc: cả D-1, D-2) và nhãn trên ảnh (nếu có) không ghi tên
        khác -> 'chac' MAT_DIEM; (b) không HĐ ngày đó nhưng có HĐ (cùng dịch vụ nhãn, nếu nhãn ghi) trong
        GOI_NGAY ngày trước -> gợi ý 50 (ảnh chưa có HĐ); (c) không HĐ nào -> chỉ ghi chú.
    Trả id ảnh vừa lên 'chac' (để lan bộ chụp)."""
    len_chac, nho = [], {}
    for p in photos:
        r = ket_qua[p["id"]]
        if p["xn_hd"] or p["bo_qua"]:
            continue
        # CEO 16/10 (ca 01AA0FCF): mặt ưu tiên hơn luật BỘ — ảnh 'chac' chỉ do lan bộ chụp (không nhãn riêng) mà mặt
        # thuộc cụm MẠNH của khách K khác khách đang gắn -> xét lại theo mặt (K phải có HĐ ngày đó, xem dưới).
        lan_bo = r["do_tin"] == "chac" and (r["ly_do"] or "").startswith("cùng bộ chụp")
        if r["do_tin"] == "chac" and not lan_bo:
            continue
        c = _khach_cua_mat(cum, p["khuon_mat"])
        if not c:
            continue
        k, ma = c["khach"], c["ma"]
        nhans = [] if _la_giay_to(p) else nhan_ds[p["id"]]
        if lan_bo and (c["neo"] < CUM_MANH or nhans or _khoa_hd(conn, cum, r["hd"], nho) == k):
            continue
        bo_khac = _nhan_bo_khach_khac(conn, cum, p, photos, ket_qua, k, nho)
        ngays = [ngay]
        for n in nhans:
            if n["ngay"] and n["ngay"] not in ngays and abs(
                    (dt.date.fromisoformat(n["ngay"]) - dt.date.fromisoformat(ngay)).days) <= 7:
                if r.get("goc") == 1:  # luật ngày 16/10: có ngày chụp gốc -> ngày chụp trước, nhãn có thể ghi sai
                    ngays.append(n["ngay"])
                else:  # ngày GHI TRÊN NHÃN đứng trước ngày chụp (ảnh lưu lại sau buổi làm)
                    ngays.insert(0, n["ngay"])
        if r["ngay_goc"] == 0:
            d0 = dt.date.fromisoformat(ngay)
            ngays += [(d0 - dt.timedelta(days=x)).isoformat() for x in LUI_NGAY]
        ma_dvs = [n["ma_dv"] for n in nhans if n["ma_dv"]]
        chu_nhan = " ".join(f"{n['ten']} {n['ma_dv']}" for n in nhans)
        mo = f"khách {ma} (cụm {c['neo']} ảnh đã xác nhận)"
        vs = _hd_cua_khach(conn, cum, k, ngays)
        if lan_bo and not vs:
            continue
        if bo_khac and vs:
            # CEO 16/10 lần 4–5: nhãn trong bộ ghi khách khác thắng mặt (ca 195AA4FA) — TRỪ khi nhãn trên CHÍNH ảnh hợp
            # K (645490B4) -> mặt thắng.
            if not any(_ten_nhan_hop(n, x["ten_kh"]) for n in nhans for x in vs):
                continue  # K không có HĐ ngày đó: giữ kết quả luật bộ (cảnh báo mặt ở _canh_bao_mat)
        if vs:
            # Chữ trên nhãn không thuộc tên khách có thể là mã dịch vụ ('Khắc Bách xvm' -> 'xvm').
            tk = {k for x in vs for _, k in _tu_ten_kh(x["ten_kh"])}
            them = [m for n in nhans for m in _chu_ma_nhan(n, tk)]
            ma_quanh = _dv_nhan_quanh(p, photos, ket_qua, nhan_ds, tk)  # nhãn cùng bộ, rồi cùng đợt
            v = _chon_hd_mat(vs, ngays, r, ma_dvs + them, ma_quanh, chu_nhan, p["goi_y_hd"])
            manh = c["neo"] >= CUM_MANH  # cụm mạnh: nhãn hợp K theo luật mặt nới (_ten_hop_mat) — CEO 16/10
            hop = [n for n in nhans if _ten_nhan_hop(n, v["ten_kh"]) or (manh and _ten_hop_mat(n, v["ten_kh"]))]
            if hop and not any(_ten_dung_duoi(n, v["ten_kh"]) for n in hop):
                # Nhãn hợp K nhưng không đúng đuôi, mà khớp ĐÚNG đuôi (đủ tên) một khách KHÁC có HĐ cùng ngày ->
                # ưu tiên khách đó / người chọn, không chắc.
                # CEO 16/10 lần 4 (ca 846FE437 'Chị Hà'): khách khác đúng đuôi nhưng HĐ lệch mã dịch vụ nhãn, trong khi
                # HĐ của K khớp mã đó -> không chặn (mặt mạnh + HĐ cùng ngày + dịch vụ khớp thắng).
                # Chỉ áp cho nhãn 1 chữ là HỌ của K; nhãn là tên thì khách khác đúng đuôi vẫn chặn như cũ.
                tk = [kk_ for _, kk_ in _tu_ten_kh(v["ten_kh"])]
                chi_ho = bool(tk) and tk[0] in HO_VIET and all(_ten_nhan_gon(n, tk) == [tk[0]] for n in hop)
                ma_ro = [m for m in ma_dvs if m in MA_DV or m in MA_DV_OCR] if chi_ho else []
                k_khop = any(_dv_khop(m, v["dich_vu"] or "") for m in ma_ro)
                kk = [x for x in conn.execute(f"SELECT * FROM visits WHERE ngay IN ({','.join('?' * len(ngays))})"
                                              " ORDER BY gio", ngays)
                      if _khoa_hd(conn, cum, x["code"], nho) != k
                      and any(_ten_dung_duoi(n, x["ten_kh"], ocr=False) for n in hop)
                      and not (k_khop and not any(_dv_khop(m, x["dich_vu"] or "") for m in ma_ro))]
                if kk:
                    if not r["hd"]:
                        r.update(hd=kk[0]["code"], do_tin="goi_y", diem=40,
                                 ly_do=f"nhãn khớp đúng tên khách khác ({kk[0]['ma_kh'] or kk[0]['code']}) nhưng"
                                 f" mặt giống {mo} — người chọn")
                    else:
                        r["ly_do"] = (r["ly_do"] or "") + f" — mặt giống {mo}, nhãn khớp đúng tên khách khác"
                    continue
            if nhans and not hop:
                if not r["hd"]:
                    r.update(hd=v["code"], do_tin="goi_y", diem=40,
                             ly_do=f"mặt giống {mo} nhưng nhãn trên ảnh ghi tên khác — người chọn")
                else:
                    r["ly_do"] = (r["ly_do"] or "") + f" — mặt giống {mo}, nhãn ghi tên khác"
                continue
            lech = "" if v["ngay"] == ngay else f" (HĐ ngày {v['ngay'][8:10]}/{v['ngay'][5:7]})"
            nn = [n["ngay"] for n in nhans if n["ngay"] and n["ngay"] != ngay and n["ngay"] in ngays]
            if nn and r.get("goc") == 1:
                lech += (f" — nhãn ghi ngày {_dd_mm(nn[0])} nhưng ảnh chụp ngày {_dd_mm(ngay)} (có ngày gốc) — theo ngày chụp"
                         if v["ngay"] == ngay else
                         f" — ảnh chụp ngày {_dd_mm(ngay)} (có ngày gốc) nhưng nhãn ghi ngày {_dd_mm(v['ngay'])}"
                         " — theo ngày nhãn")
            r.update(hd=v["code"], do_tin="chac", diem=MAT_DIEM, mat=ma,
                     ly_do=f"khuôn mặt thuộc {mo} + HĐ cùng ngày{lech}")
            len_chac.append(p["id"])
            continue
        d0 = dt.date.fromisoformat(ngay)
        tu = (d0 - dt.timedelta(days=GOI_NGAY)).isoformat()
        mas = sorted(cum["nhom"].get(k, set())) or [k]
        dau = ",".join("?" * len(mas))
        cu = [v for v in conn.execute(
            f"SELECT * FROM visits WHERE (ma_kh IN ({dau}) OR code IN ({dau})) AND ngay BETWEEN ? AND ?"
            " ORDER BY ngay DESC, gio DESC", (*mas, *mas, tu, (d0 - dt.timedelta(days=1)).isoformat()))]
        dvs = [m for m in ma_dvs if not _dv_chung(m)]
        if dvs:
            cu = [v for v in cu if any(_dv_goi_khop(m, v["dich_vu"] or "") for m in dvs)]
        if cu and not r["hd"]:
            v = cu[0]
            r.update(hd=v["code"], do_tin="goi_y", diem=50,
                     ly_do=f"mặt thuộc {mo}, không HĐ ngày này — HĐ gần nhất "
                     f"{v['ngay'][8:10]}/{v['ngay'][5:7]}/{v['ngay'][2:4]} (có thể buổi theo gói) — người chọn")
        else:
            r["ly_do"] = ((r["ly_do"] + " — ") if r["ly_do"] else "") + f"mặt giống {mo} (không có HĐ ngày này)"
    return len_chac


def _lan_bo_theo_mat(ket_qua: dict, ids: list[str], conn=None) -> None:
    """Bộ chụp (<= BO_TOI_DA tư thế) có ảnh vừa lên 'chac' theo mặt: các ảnh còn lại cùng bộ lên 'chac' 80 —
    trừ khi bộ có ảnh khớp HĐ khác (điểm >= 50 / 'chac'), người duyệt chọn HĐ khác, hoặc nhãn chưa khớp."""
    for bo in {ket_qua[i]["bo"] for i in ids if ket_qua[i]["bo"] is not None}:
        b = [r for r in ket_qua.values() if r["bo"] == bo]
        hds = {r["hd"] for r in b if r.get("mat")}
        if len(hds) != 1 or len({r["gio"] for r in b}) > BO_TOI_DA:
            continue
        hd = hds.pop()
        ma = _ma_kh_hd(conn, hd)

        def khac(x):  # HĐ x khác hd và (không biết khách / của khách khác); HĐ khác của CÙNG khách không chặn
            return bool(x) and x != hd and (ma is None or _ma_kh_hd(conn, x) != ma)
        if any((khac(r["hd"]) and (r["diem"] >= 50 or r["do_tin"] == "chac"))
               or (r["xn"] and r["xn"] != hd) or (r["nhan"] and r["hd"] != hd and (khac(r["hd"]) or not r["hd"]))
               for r in b):
            continue
        ma = next(r["mat"] for r in b if r.get("mat"))
        for r in b:
            if r["do_tin"] != "chac" and not r["xn"]:
                r.update(hd=hd, do_tin="chac", diem=80,
                         ly_do=f"cùng bộ chụp liền {len(b)} ảnh với ảnh nhận theo khuôn mặt khách {ma}")


def _ma_kh_hd(conn, hd: str | None) -> str | None:
    """Mã KH của 1 HĐ (None: không có conn/HĐ/mã)."""
    if conn is None or not hd:
        return None
    v = conn.execute("SELECT ma_kh FROM visits WHERE code=?", (hd,)).fetchone()
    return (v["ma_kh"] if v else None) or None


def _canh_bao_mat(conn, photos, ket_qua, cum: dict) -> None:
    """Luật CỤM MẶT bước 3: ảnh máy chấm 'chac' (chưa duyệt), đúng 1 mặt, mặt thuộc cụm MẠNH (>= CUM_MANH ảnh
    neo) của khách KHÁC khách đang gắn -> hạ gợi ý, người xem lại. Không đụng ảnh đã duyệt."""
    nho: dict = {}
    for p in photos:
        r = ket_qua[p["id"]]
        if p["xn_hd"] or p["bo_qua"] or r["do_tin"] != "chac" or r.get("mat"):
            continue
        mat = _doc_mat(p["khuon_mat"])
        if len(mat) != 1 or mat[0] not in cum["cum"]:
            continue
        c = cum["cum"][mat[0]]
        if c["neo"] < CUM_MANH or _khoa_hd(conn, cum, r["hd"], nho) == c["khach"]:
            continue
        r.update(do_tin="goi_y", diem=min(r["diem"], 50),
                 ly_do=f"cảnh báo: khuôn mặt thuộc khách khác ({c['ma']}, cụm {c['neo']} ảnh) — người xem lại"
                 f" · máy chấm trước: {r['ly_do']}")


def mau_thuan_da_duyet(conn, cum: dict) -> list[tuple]:
    """Ảnh ĐÃ DUYỆT, 1 mặt, mặt thuộc cụm mạnh của khách khác khách người duyệt chọn -> [(id, xn_hd, mã cụm)].
    Chỉ để báo, không sửa."""
    ra, nho = [], {}
    for r in conn.execute("SELECT id, xn_hd, khuon_mat FROM photos WHERE xn_hd IS NOT NULL AND bo_qua=0"
                          " AND COALESCE(khuon_mat,'') != ''"):
        mat = _doc_mat(r["khuon_mat"])
        if len(mat) != 1 or mat[0] not in cum["cum"]:
            continue
        c = cum["cum"][mat[0]]
        if c["neo"] >= CUM_MANH and _khoa_hd(conn, cum, r["xn_hd"], nho) != c["khach"]:
            ra.append((r["id"], r["xn_hd"], c["ma"]))
    return ra


def cmd_ghep(a) -> None:
    y, m = thang(a.thang)
    tu, den = khoang_thang(y, m)
    conn = ket_noi()
    ngays = [r[0] for r in conn.execute(
        "SELECT DISTINCT ngay FROM photos WHERE ngay BETWEEN ? AND ?", (tu, den))]
    cum = cum_khach(conn) if ngays else None  # bảng cụm mặt tính 1 lần cho cả tháng
    for n in ngays:
        ghep_ngay(conn, n, cum)
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
    so, theo_album = 0, {}
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
        if getattr(a, "album", False) and r["nguon"] == "photos":
            for ten_al in _ten_album(r):
                theo_album.setdefault(ten_al, []).append(r["id"])
    conn.commit()
    if theo_album:
        _xep_album(theo_album)

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


THU_MUC_ALBUM = "Doctor Laser"


def _ten_album(r) -> list[str]:
    """Album theo khách 'KH000123 · Tên' + album theo dịch vụ 'DV · <dịch vụ đầu của HĐ>'.
    Mã KH giữ nguyên (mã cũ 'CU-KH…' là khách KHÁC 'KH…'). Theo ngày: app Ảnh đã tự nhóm, không tạo."""
    def gon(x):
        return " ".join(re.sub(r"[\x00-\x1f]", " ", x or "").split()).strip(" -·|/")

    ra = []
    if (r["ma_kh"] or "").strip():
        ten = gon(r["ten_kh"])[:60]
        ra.append(f"{r['ma_kh'].strip()} · {ten}" if ten else r["ma_kh"].strip())
    dv = gon((r["dich_vu"] or "").split(" | ")[0])[:60]
    if dv:
        ra.append(f"DV · {dv}")
    return ra


def _xep_album(theo_album: dict[str, list[str]]) -> None:
    """Cho ảnh vào album trong thư mục 'Doctor Laser' của Photos. Chỉ THÊM: tìm album có sẵn
    trước khi tạo, ảnh đã có trong album thì bỏ qua, không gỡ ảnh khỏi album nào."""
    try:
        import photoscript

        lib = photoscript.PhotosLibrary()
        tm = lib.folder(THU_MUC_ALBUM, top_level=True) or lib.create_folder(THU_MUC_ALBUM)
        co = {}
        for al in tm.albums:
            co.setdefault(al.name, al)
    except Exception as e:  # noqa: BLE001
        print(f"  ! không mở được thư mục album '{THU_MUC_ALBUM}' trong Photos: {e}")
        return
    tao = them = 0
    for ten, ids in theo_album.items():
        try:
            al = co.get(ten)
            if al is None:
                al = co[ten] = tm.create_album(ten)
                tao += 1
                da = set()
            else:
                da = {p.uuid for p in al.photos()}
            moi = [i for i in dict.fromkeys(ids) if i not in da]
            if moi:
                al.add([photoscript.Photo(i) for i in moi])
                them += len(moi)
        except Exception as e:  # noqa: BLE001
            print(f"  ! album '{ten}': {e}")
    print(f"Album Photos ('{THU_MUC_ALBUM}'): tạo {tao} album mới, thêm {them} ảnh.")


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
.cot{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:10px}.cot h4{margin:0 0 6px;font-size:13px}
.cot .ph{margin-bottom:8px}.tim input{padding:4px 8px;width:240px}.tag.cd{background:var(--warn)}
.bo{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px;margin-bottom:12px;scroll-margin-top:70px}
.bo.cur{box-shadow:0 0 0 3px #0b57d055}.bo.cb{border-color:var(--bad)}
.bo.xong{background:#eef8f0;border-color:var(--ok);padding:6px 10px}.bo.xong .than{display:none}
.daluu{display:none;margin-left:auto;color:var(--ok)}.bo.xong .daluu{display:inline}
.boh{display:flex;gap:6px;align-items:center;flex-wrap:wrap}
.thumbs{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0}
.t{border:2px solid var(--line);border-radius:6px;display:inline-flex;width:140px;height:140px;background:#222;overflow:hidden;align-items:center;justify-content:center}
.t img{width:100%;height:100%;object-fit:cover;cursor:zoom-in}.t i{color:#ccc;font-size:11px;text-align:center}
.t.ok{border-color:var(--ok)}.t.skip{opacity:.4}
.quyet{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-top:6px}
.quyet .loc{width:170px}.quyet .hd{min-width:280px;max-width:100%;font-size:14px;padding:4px}.quyet .ghi{width:220px}
.quyet input,.quyet select{padding:4px}.nut{display:flex;gap:6px;flex-wrap:wrap;margin-top:4px}
button.lon{font-size:15px;padding:8px 16px;font-weight:600}
.canh{color:var(--bad);font-weight:600;margin:4px 0}.dem{font-size:15px}
.tach{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:10px;margin-top:10px}.tach[hidden]{display:none}
#zoom{display:none;position:fixed;inset:0;background:rgba(0,0,0,.9);z-index:9;align-items:center;justify-content:center}#zoom img{max-width:96vw;max-height:96vh}
"""

JS = """
function zoom(src){const z=document.getElementById('zoom');z.querySelector('img').src=src;z.style.display='flex'}
"""


def _trang(title: str, body: str) -> bytes:
    return (f"<!doctype html><html lang=vi><meta charset=utf-8><meta name=viewport "
            f"content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title>"
            f"<style>{CSS}</style><script>{JS}</script><body>{body}"
            f"<div id=zoom onclick=\"this.style.display='none'\"><img></div></body></html>").encode()


CAN_DUYET = "xn_hd IS NULL AND bo_qua=0 AND COALESCE(do_tin,'')!='chac'"  # Lượng 16/10: chỉ duyệt ảnh chưa chắc/nghi


def _trang_chu(conn, tat_ca: bool = False) -> bytes:
    rows = conn.execute(
        "SELECT ngay, COUNT(*) n, SUM(xn_hd IS NOT NULL OR bo_qua=1) d, SUM(do_tin='chac') c, "
        f"SUM({CAN_DUYET}) can, SUM({CAN_DUYET} AND ly_do LIKE 'cảnh báo:%') cb "
        "FROM photos GROUP BY ngay ORDER BY ngay DESC").fetchall()
    con = [r for r in rows if r["can"]]
    tong = sum(r["can"] for r in rows)
    o = ["<header><b>Duyệt ảnh khách hàng</b><span class=small>"
         f"Còn <b>{tong:,}</b> ảnh cần duyệt (gợi ý / chưa rõ / cảnh báo) ở {len(con)} ngày — ảnh CHẮC CHẮN đã ẩn. "
         + ("<a href='/'>Chỉ ngày còn cần duyệt</a>" if tat_ca else "<a href='/?tat_ca=1'>Xem cả ngày đã xong</a>")
         + f"</span>{_o_tim()}</header><main><div class=days>"]
    for r in (rows if tat_ca else con):
        xong = not r["can"]
        cb = f" · <b style='color:var(--bad)'>⚠ {r['cb']} cảnh báo</b>" if r["cb"] else ""
        tt = "xong" if xong else f"cần duyệt {r['can']}"
        o.append(f"<a class=day href='/ngay?d={r['ngay']}'{' style=opacity:.5' if xong else ''}>"
                 f"<b>{r['ngay'][8:]}/{r['ngay'][5:7]}/{r['ngay'][2:4]}</b>"
                 f"<div class=small>{tt}{cb}</div>"
                 f"<div class=small>{r['n']} ảnh · chắc {r['c'] or 0} · đã duyệt {r['d'] or 0}</div></a>")
    if not rows:
        o.append("<p>Chưa có ảnh. Chạy <code>python3 anhkhach.py quet YYYY-MM</code> trước.</p>")
    elif not con and not tat_ca:
        o.append("<p>Không còn ảnh nào cần duyệt.</p>")
    o.append("</div></main>")
    return _trang("Duyệt ảnh khách", "".join(o))


def ten_goi(ten: str, so_chu: int = 1) -> str:
    """Tên gọi kiểu Việt = chữ cuối của họ tên đã bỏ ghi chú: 'NGUYỄN KINH LƯƠNG (KH TỰ ĐẾN)' -> 'Lương'
    (so_chu=2 -> 'Kinh Lương', dùng khi 2 khách trùng tên gọi)."""
    tu = [g for g, _ in _tu_ten_goi(ten)]
    if not tu:
        return (ten or "").strip()
    return " ".join(w.capitalize() for w in tu[-so_chu:])


def _dv_ngan(dich_vu: str | None) -> str:
    ds = _ds_dv(dich_vu)
    if not ds:
        return ""
    return ds[0][:28] + (f" +{len(ds) - 1}" if len(ds) > 1 else "")


def _luc_hd(v) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat(f"{v['ngay']}T{(v['gio'] or '00:00')[:8]}")
    except (TypeError, ValueError):
        return None


def _gom_bo(photos) -> list[list]:
    """Chia ảnh 1 ngày (đã xếp theo thoi_gian) thành BỘ CHỤP như ghép (_chia_bo): chuỗi ảnh liền, 2 ảnh kề cách
    <= BO_GIAY; ảnh trùng giây (2 bản) vẫn cùng bộ. Giây có >= TRUNG_GIAY ảnh = giờ nhập/lưu, không phải giờ chụp
    -> mỗi ảnh 1 bộ riêng (đo 16/10: ngày 29/08/2019 gom thành bộ 258 ảnh nếu không tách)."""
    dem: dict[str, int] = {}
    for p in photos:
        dem[p["thoi_gian"]] = dem.get(p["thoi_gian"], 0) + 1
    ds = [{"p": p, "gio": dt.datetime.fromisoformat(p["thoi_gian"]),
           "trung_giay": dem[p["thoi_gian"]] >= TRUNG_GIAY} for p in photos if p["thoi_gian"]]
    _chia_bo(ds)
    bo: dict = {}
    for i, r in enumerate(ds):
        bo.setdefault(("bo", r["bo"]) if r["bo"] is not None else ("le", i), []).append(r["p"])
    return list(bo.values())


def _khop_ten_goi(w: list[str], bi_danh: list[list[str]], ten_nhan: list[list[str]]) -> bool:
    """Tên trên nhãn ('C Quyên' -> ['quyen']) là đuôi họ tên khách (không dấu) hoặc là tên gọi trong ngoặc."""
    for t in ten_nhan:
        while len(t) > 1 and t[0] in XUNG_HO:
            t = t[1:]
        if t and (w[-len(t):] == t or t in bi_danh or (len(t) == 1 and _mot_chu_khop(t[0], w, _la_ten_tay(w)))):
            return True
    return False


def _thu_tu_ung_vien(hds: list[dict], goi_y: list[str], ten_nhan: list[list[str]], luc: dt.datetime) -> list[int]:
    """Thứ tự ô chọn khách của 1 bộ: (a) HĐ máy gợi ý / đã duyệt (nhiều ảnh trước), (b) khách có tên gọi khớp tên
    trên nhãn, (c) còn lại; trong (b), (c) HĐ gần giờ bộ chụp trước. hds: [{'c','w','bd','luc'}] -> chỉ số."""
    def xa(i):
        t = hds[i]["luc"]
        return abs((t - luc).total_seconds()) if t else float("inf")

    vi_tri = {h["c"]: i for i, h in enumerate(hds)}
    a = [vi_tri[c] for c in goi_y if c in vi_tri]
    con = [i for i in range(len(hds)) if i not in set(a)]
    b = sorted((i for i in con if _khop_ten_goi(hds[i]["w"], hds[i]["bd"], ten_nhan)), key=xa)
    c = sorted((i for i in con if i not in set(b)), key=xa)
    return a + b + c


def _chu_nhan(n: dict) -> str:
    """Nhãn đọc được: nguyên chữ nhân viên viết ('Lương-xoá xăm 14/10/26'); thiếu thì dựng 'Tên-mã dd/mm'."""
    if n.get("goc"):
        return n["goc"]
    s = (n.get("ten_goc") or n.get("ten") or "").title()
    if n.get("ma_dv"):
        s += f"-{n['ma_dv']}"
    if n.get("ngay"):
        s += f" {int(n['ngay'][8:10])}/{int(n['ngay'][5:7])}"
    if n.get("loai"):
        s += f" ({n['loai']})"
    return s


def _json_nhung(o) -> str:
    """JSON nhúng trong <script type=application/json>: chặn '</script>' và '<!--'."""
    return json.dumps(o, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c").replace(">", "\\u003e")


def du_lieu_trang(trang: str) -> dict:
    """JSON nhúng của trang ngày (HĐ + ảnh) — cho test."""
    m = re.search(r"<script type=application/json id=duLieu>(.*?)</script>", trang, re.S)
    return json.loads(m.group(1)) if m else {}


def _trang_ngay(conn, ngay: str, tat_ca: bool = False) -> bytes:
    """Lượng 16/10: duyệt THEO BỘ CHỤP — mỗi bộ (chuỗi ảnh liền <= BO_GIAY) 1 thẻ, 1 quyết định cho cả bộ
    (POST /luu_bo); 'Tách bộ' mở chọn riêng từng ảnh (/luu). Danh sách HĐ nhúng 1 lần (JSON), ô chọn sinh bằng JS."""
    visits = conn.execute("SELECT * FROM visits WHERE ngay=? ORDER BY gio", (ngay,)).fetchall()
    photos = conn.execute("SELECT * FROM photos WHERE ngay=? ORDER BY thoi_gian", (ngay,)).fetchall()
    # Nhãn ghi ngày khác ngày chụp (chụp 10/10, nhãn 'Nam-xx 9/10') -> hóa đơn ngày khác cũng phải chọn được.
    co = {v["code"] for v in visits}
    khac = sorted({p[k] for p in photos for k in ("goi_y_hd", "xn_hd") if p[k] and p[k] not in co})
    visits_khac = [conn.execute("SELECT * FROM visits WHERE code=?", (c,)).fetchone() for c in khac]
    visits_khac = [v for v in visits_khac if v]
    khong_tin = _ngay_khong_tin(photos)
    visits_lui = []
    if khong_tin:
        # Ảnh không có ngày chụp gốc (gửi qua Zalo...): ngày chụp thật có thể 1–2 ngày TRƯỚC -> bộ có ảnh đó được
        # chọn cả HĐ các ngày đó (không lấy ngày sau).
        d0 = dt.date.fromisoformat(ngay)
        da = co | {v["code"] for v in visits_khac}
        for lui in LUI_NGAY:
            n = (d0 - dt.timedelta(days=lui)).isoformat()
            visits_lui += [v for v in conn.execute("SELECT * FROM visits WHERE ngay=? ORDER BY gio", (n,))
                           if v["code"] not in da]
    ngays = [r[0] for r in conn.execute("SELECT DISTINCT ngay FROM photos ORDER BY ngay")]
    i = ngays.index(ngay) if ngay in ngays else -1
    nav = "<a href='/'>← Tất cả ngày</a>"
    if i > 0:
        nav += f" · <a href='/ngay?d={html.escape(ngays[i - 1])}'>‹ {html.escape(ngays[i - 1])}</a>"
    if 0 <= i < len(ngays) - 1:
        nav += f" · <a href='/ngay?d={html.escape(ngays[i + 1])}'>{html.escape(ngays[i + 1])} ›</a>"

    def ngay_cua(v):  # HĐ ngày khác: 'dd/mm'; khác năm (HĐ gói mua từ năm trước): 'dd/mm/yy'
        if v["ngay"] == ngay:
            return ""
        return f"{v['ngay'][8:10]}/{v['ngay'][5:7]}" + (f"/{v['ngay'][2:4]}" if v["ngay"][:4] != ngay[:4] else "")

    def dong(v):  # 1 dòng hóa đơn; tên khách là link sang trang diễn tiến
        ngay_hd = ngay_cua(v)
        ten = html.escape(v["ten_kh"] or "")
        if v["ma_kh"]:
            ten = f"<a href='{_link_khach(v['ma_kh'])}'>{ten}</a>"
        return (f"<span class=small>{html.escape((ngay_hd + ' ' if ngay_hd else '') + (v['gio'] or ''))} · {ten} "
                f"({html.escape(v['ma_kh'] or '')}) · {html.escape((v['dich_vu'] or '')[:50])}"
                f" · HĐ {html.escape(v['code'])}</span>")

    # ---- danh sách HĐ dựng 1 lần ----
    tat_hd = visits + visits_khac + visits_lui
    lui_ma = {v["code"] for v in visits_lui}
    theo_ma = {v["code"]: v for v in tat_hd}
    goi1: dict[str, set] = {}
    for v in tat_hd:
        goi1.setdefault(khong_dau(ten_goi(v["ten_kh"])), set()).add(v["ma_kh"] or v["code"])
    hds, js_hd = [], []
    for v in tat_hd:
        tg = ten_goi(v["ten_kh"])
        if len(goi1.get(khong_dau(tg), ())) > 1:  # 2 khách cùng tên gọi -> 2 chữ cuối
            tg = ten_goi(v["ten_kh"], 2)
        hds.append({"c": v["code"], "w": [k for _, k in _tu_ten_goi(v["ten_kh"])], "bd": _bi_danh(v["ten_kh"]),
                    "luc": _luc_hd(v)})
        js_hd.append({"c": v["code"], "t": tg, "f": v["ten_kh"] or "", "m": v["ma_kh"] or "",
                      "d": _dv_ngan(v["dich_vu"]), "g": (v["gio"] or "")[:5], "n": ngay_cua(v)})
    idx_lui = {i for i, v in enumerate(tat_hd) if v["code"] in lui_ma}

    def an(p):  # Lượng 16/10: ảnh chắc chắn chưa duyệt ẩn
        return not tat_ca and p["do_tin"] == "chac" and not p["xn_hd"] and not p["bo_qua"]

    def can(p):  # = CAN_DUYET
        return not p["xn_hd"] and not p["bo_qua"] and p["do_tin"] != "chac"

    def ma_khach(hd):
        v = theo_ma.get(hd)
        return (v["ma_kh"] or v["code"]) if v else hd

    nam = int(ngay[:4]) if ngay[:4].isdigit() else dt.date.today().year
    mau_nho: dict = {}
    the: list[tuple] = []  # (khoá xếp, html)
    js_ph: dict = {}
    tong_bo = tong_anh = 0
    dem_giay: dict[str, int] = {}
    for p in photos:
        dem_giay[p["thoi_gian"]] = dem_giay.get(p["thoi_gian"], 0) + 1
    ten_goi_hd = {h["c"]: h["t"] for h in js_hd}
    dot_cb = {p["dot"] for p in photos if not an(p) and (p["ly_do"] or "").startswith("cảnh báo:")}
    for k, bo in enumerate(_gom_bo(photos)):
        hien = [p for p in bo if not an(p)]
        if not hien:
            continue
        so_an = len(bo) - len(hien)
        so_can = sum(1 for p in hien if can(p))
        xong = all(p["xn_hd"] or p["bo_qua"] for p in hien)
        # Phiếu bầu khách: đã duyệt -> xn_hd, chưa -> gợi ý máy (kể cả ảnh chắc đã ẩn cùng bộ).
        phieu: dict[str, int] = {}
        for p in bo:
            hd = p["xn_hd"] or (None if p["bo_qua"] else p["goi_y_hd"])
            if hd:
                phieu[hd] = phieu.get(hd, 0) + 1
        goi_y = sorted(phieu, key=lambda c: -phieu[c])
        hd_chon = goi_y[0] if goi_y else ""
        so_khach = len({ma_khach(c) for c in goi_y})
        nhan_ds = [n for p in bo for n in _nhan_that(p, nam)]
        chu_nhan = list(dict.fromkeys(_chu_nhan(n) for n in nhan_ds if n.get("ten")))[:3]
        p_nhan = next((p for p in hien if _nhan_that(p, nam)), hien[0])
        ly_do = p_nhan["ly_do"] or ""
        cb = any((p["ly_do"] or "").startswith("cảnh báo:") for p in hien)
        if xong:
            muc = ("Đã duyệt", "chac")
        elif cb:
            muc = ("⚠ Cảnh báo", "chua_ro")
        elif any(can(p) and p["do_tin"] == "goi_y" for p in hien):
            muc = ("Gợi ý", "goi_y")
        elif any(can(p) for p in hien):
            muc = ("Chưa rõ", "chua_ro")
        else:
            muc = ("Chắc chắn", "chac")
        kt = [p for p in bo if p["id"] in khong_tin]
        luc = dt.datetime.fromisoformat(hien[0]["thoi_gian"])
        thu_tu = _thu_tu_ung_vien(hds, goi_y, [x for n in nhan_ds if n.get("ten") for x in (n["ten"].split(), _thu_tu_goi(n["ten"].split()))], luc)
        if not kt:
            thu_tu = [x for x in thu_tu if x not in idx_lui]
        # Ô trước/sau, vùng, ghi chú: giá trị chung của các ảnh; trước/sau lấy từ nhãn nếu ảnh chưa có.
        def chung(cot):
            gt = {p[cot] or "" for p in hien}
            return gt.pop() if len(gt) == 1 else ""
        loai = chung("loai_anh") or next((n["loai"] for n in nhan_ds if n.get("loai")), "")
        ghi_rieng = len({p["ghi_chu"] or "" for p in hien}) > 1
        # Ảnh mẫu so mặt (như thẻ ảnh cũ), mỗi khách 1 lần trong bộ.
        mau, da_mau = [], set()

        def them_mau(ma, nhan=""):
            if (ma, nhan) not in da_mau:
                da_mau.add((ma, nhan))
                mau.append(_o_anh_mau(conn, ma, ngay, mau_nho, nhan))
        for p in hien:
            if p["xn_hd"]:
                continue
            v_p = theo_ma.get(p["goi_y_hd"] or "")
            if v_p and v_p["ma_kh"] and "buổi theo gói" in (p["ly_do"] or ""):
                them_mau(v_p["ma_kh"])
            else:
                ma_mat = _ma_tu_ly_do_mat(p["ly_do"])
                if ma_mat:
                    them_mau(ma_mat, "theo khuôn mặt")
                    if "cảnh báo: khuôn mặt" in (p["ly_do"] or "") and v_p and v_p["ma_kh"] and v_p["ma_kh"] != ma_mat:
                        them_mau(v_p["ma_kh"], "khách đang gắn")
        v_chon = theo_ma.get(hd_chon)
        den_kh = (f"<a href='{_link_khach(v_chon['ma_kh'])}'>→ diễn tiến {html.escape(v_chon['ma_kh'])}</a>"
                  if v_chon and v_chon["ma_kh"] else "")
        thumbs = []
        for p in hien:
            st = "skip" if p["bo_qua"] else ("ok" if p["xn_hd"] else "")
            co_anh = bool(p["anh_xem"] and os.path.exists(p["anh_xem"]))
            pid = html.escape(p["id"], quote=True)
            thumbs.append(
                f"<span class='t {st}' id='p{pid}' data-id='{pid}' title='{html.escape(p['thoi_gian'][11:19])} · "
                f"{html.escape(p['ten_file'] or '', quote=True)}'>"
                + (f"<img loading=lazy src='/anh/{pid}' onclick=\"zoom(this.src)\">" if co_anh else
                   "<i>chưa tải về máy</i>") + "</span>")
            js_ph[p["id"]] = {"g": p["thoi_gian"][11:19], "f": p["ten_file"] or "", "t": p["do_tin"] or "",
                              "l": p["ly_do"] or "",
                              "u": ((p["chu_thich"] or "") + " " + (p["ocr"] or "")).strip()[:120],
                              "h": p["xn_hd"] or p["goi_y_hd"] or "", "a": p["loai_anh"] or "",
                              "v": p["vung"] or "", "n": p["ghi_chu"] or "", "s": st, "i": int(co_anh),
                              "k": int(p["id"] in khong_tin)}
        if xong:
            v_x = theo_ma.get(hd_chon)
            if all(p["bo_qua"] for p in hien):
                da_luu = "Không phải ảnh khách"
            elif len({p["xn_hd"] for p in hien if p["xn_hd"]}) > 1:
                da_luu = f"theo từng ảnh ({so_khach} khách)"
            else:
                da_luu = (f"{ten_goi_hd.get(hd_chon, '')} — {_dv_ngan(v_x['dich_vu'])}"
                          if v_x else hd_chon)
        else:
            da_luu = ""
        n = len(hien)
        o = [f"<div class='bo{' xong' if xong else ''}{' cb' if cb else ''}' id='b{k}' data-k='{k}' "
             f"data-ids='{html.escape(','.join(p['id'] for p in hien), quote=True)}' "
             f"data-o='{','.join(map(str, thu_tu))}' data-hd='{html.escape(hd_chon, quote=True)}' "
             f"data-loai='{html.escape(loai, quote=True)}' data-vung='{html.escape(chung('vung'), quote=True)}' "
             f"data-can='{so_can}' data-gr='{int(ghi_rieng)}'>"
             f"<div class=boh><b>{hien[0]['thoi_gian'][11:16]}"
             + (f"–{hien[-1]['thoi_gian'][11:16]}" if hien[-1]["thoi_gian"][11:16] != hien[0]["thoi_gian"][11:16] else "")
             + f"</b> · {n} ảnh <span class='tag {muc[1]}'>{muc[0]}</span>"
             + (f" · nhãn: <b>{' / '.join(html.escape(x) for x in chu_nhan)}</b>" if chu_nhan else
                " · <span class=small>không đọc được nhãn</span>")
             + (f" <span class=small>· {so_an} ảnh chắc chắn đã ẩn (cùng bộ)</span>" if so_an else "")
             + f"<span class=daluu>đã lưu: <b>{html.escape(da_luu)}</b> <button onclick='suaBo({k})'>Sửa</button></span>"
             "</div><div class=than>"]
        if ly_do:
            o.append(f"<div class=small>Máy: {html.escape(ly_do)}</div>")
        if so_khach > 1 and not xong:
            o.append(f"<div class=canh>⚠ bộ có {so_khach} khách khác nhau — nên Tách bộ (đang chọn sẵn khách"
                     " nhiều ảnh nhất)</div>")
        if len({p["thoi_gian"] for p in hien}) > BO_TOI_DA:
            o.append(f"<div class=canh>⚠ bộ dài {len({p['thoi_gian'] for p in hien})} tư thế — có thể 2 khách,"
                     " xem kỹ hoặc Tách bộ</div>")
        if len(bo) == 1 and dem_giay[bo[0]["thoi_gian"]] >= TRUNG_GIAY:
            o.append("<div class=small>giờ chụp trùng nhiều ảnh (giờ nhập máy) — ảnh này duyệt riêng</div>")
        if kt:
            o.append(f"<div class=small style='color:#b45309'>⚠ không có ngày chụp gốc ({len(kt)} ảnh) — "
                     f"chọn được cả HĐ {len(LUI_NGAY)} ngày trước</div>")
        o.append(f"<div class=thumbs>{''.join(thumbs)}</div>")
        if mau or den_kh:
            o.append(f"<div class=small>{den_kh}</div>{''.join(mau)}")
        o.append(f"<div class=quyet><input class=loc placeholder='lọc: tên gọi / mã KH / dịch vụ'>"
                 f"<select class=hd></select><select class=loai></select><select class=vung></select>"
                 f"<input class=ghi placeholder='{'ảnh có ghi chú riêng — để trống giữ nguyên' if ghi_rieng else 'ghi chú (tuỳ chọn)'}'"
                 f" value='{html.escape(chung('ghi_chu'), quote=True)}'>"
                 f"<div class=nut><button class='p lon' onclick='dungBo({k})'>✓ Đúng khách này (cả bộ {n} ảnh)</button>"
                 f"<button onclick='boQuaBo({k})'>Không phải ảnh khách (cả bộ)</button>"
                 f"<button onclick='tachBo({k})'>Tách bộ</button></div></div>"
                 f"<div class=tach hidden></div></div></div>")
        if so_can:
            tong_bo += 1
            tong_anh += so_can
        the.append(((hien[0]["dot"] not in dot_cb, luc), "".join(o)))
    so_an_ngay = sum(1 for p in photos if an(p))
    loc = (f"<a href='/ngay?d={html.escape(ngay)}&tat_ca=1'>Xem cả {so_an_ngay} ảnh chắc chắn</a>" if not tat_ca
           else f"<a href='/ngay?d={html.escape(ngay)}'>Chỉ ảnh cần duyệt</a>")
    o = [f"<header><b>Ngày {html.escape(ngay)}</b> {nav}<span class=dem>còn <b id=conBo>{tong_bo}</b> bộ / "
         f"<b id=conAnh>{tong_anh}</b> ảnh cần duyệt</span><span class=small>{len(photos)} ảnh · "
         f"{len(visits)} hóa đơn · {loc} · Enter = Đúng khách này (bộ đang chọn)</span></header><main>"]
    o.append("<details class=visits><summary><b>Hóa đơn trong ngày</b> "
             f"<span class=small>({len(visits)})</span></summary>" + (
                 "<br>".join(dong(v) for v in visits)
                 or "<span class=small>Không có hóa đơn ngày này.</span>") + (
        "<br><b>Hóa đơn ngày khác (theo nhãn trên ảnh"
        + (f"; có ảnh không có ngày chụp gốc -> thêm HĐ {len(LUI_NGAY)} ngày trước" if khong_tin else "")
        + "):</b><br>" + "<br>".join(dong(v) for v in visits_khac + visits_lui)
        if visits_khac or visits_lui else "") + "</details>")
    if not the:
        o.append("<p>Không còn ảnh nào cần duyệt ngày này.</p>")
    o += [h for _, h in sorted(the, key=lambda x: x[0])]
    o.append(f"</main><script type=application/json id=duLieu>"
             f"{_json_nhung({'hd': js_hd, 'ph': js_ph, 'loai': LOAI_ANH, 'vung': VUNG})}</script>"
             f"<script>{JS_NGAY}</script>")
    return _trang(f"Ảnh {ngay}", "".join(o))

JS_NGAY = r"""
const DL=JSON.parse(document.getElementById('duLieu').textContent);
const HD=DL.hd, PH=DL.ph, CHI={};HD.forEach((v,i)=>CHI[v.c]=i);
let CUR=null;
function kd(s){return (s||'').normalize('NFD').replace(/[̀-ͯ]/g,'').replace(/[đĐ]/g,'d').toLowerCase()}
function chuHd(v){return v.t+' — '+v.d+' — '+(v.n?v.n+' ':'')+v.g+' — '+v.m}
function dienHd(sel,thuTu,chon,loc){
  const q=kd(loc);sel.textContent='';sel.add(new Option('— chọn khách —',''));
  let dau=null;
  for(const i of thuTu){const v=HD[i];if(!v)continue;const t=chuHd(v);
    if(q&&!kd(t+' '+v.f+' '+v.c).includes(q))continue;
    const o=new Option(t,v.c);o.title=v.f+' · HĐ '+v.c;sel.add(o);if(dau===null)dau=v.c;}
  sel.value=(q&&dau!==null)?dau:(chon||'');
}
function dienDs(sel,ds,chon,trong){sel.textContent='';
  for(const x of ds){const o=new Option(x||trong,x);sel.add(o)} sel.value=chon||'';}
function thuTu(b){return b.dataset.o?b.dataset.o.split(',').map(Number):[]}
function ganLoc(loc,sel,tt,chon){
  loc.addEventListener('input',()=>dienHd(sel,tt,chon(),loc.value));
  loc.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();sel.focus()}});
}
function chonBo(b){if(CUR)CUR.classList.remove('cur');CUR=b;if(b)b.classList.add('cur')}
function demLai(b){const n=+b.dataset.can||0;if(!n)return;b.dataset.can=0;
  const x=document.getElementById('conBo'),y=document.getElementById('conAnh');
  x.textContent=Math.max(0,+x.textContent-1);y.textContent=Math.max(0,+y.textContent-n);}
function keTiep(b){const ds=[...document.querySelectorAll('.bo:not(.xong)')];
  const sau=ds.find(x=>b.compareDocumentPosition(x)&Node.DOCUMENT_POSITION_FOLLOWING)||ds[0];
  chonBo(sau||null);if(sau)sau.scrollIntoView({behavior:'smooth',block:'start'});}
function xongBo(b,chu){b.classList.add('xong');b.querySelector('.daluu b').textContent=chu;demLai(b);keTiep(b);}
async function guiBo(k,boQua){
  const b=document.getElementById('b'+k),ids=b.dataset.ids.split(','),q=b.querySelector('.quyet');
  const hd=q.querySelector('.hd').value;
  if(!boQua&&!hd){alert('Chọn khách trước');return}
  if(boQua&&!confirm('Cả bộ '+ids.length+' ảnh KHÔNG phải ảnh khách (ảnh cá nhân, giấy tờ, chụp màn hình)?'))return;
  const ghi=q.querySelector('.ghi').value;
  const d={ids,hd:boQua?'':hd,loai:q.querySelector('.loai').value,vung:q.querySelector('.vung').value,
           ghi:(ghi===''&&b.dataset.gr==='1')?null:ghi,bo_qua:boQua?1:0};
  const r=await fetch('/luu_bo',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)});
  if(!r.ok){alert('Lưu lỗi: '+await r.text());return}
  const j=await r.json();
  for(const id of ids){const t=document.getElementById('p'+id);if(t)t.className='t '+j.st;if(PH[id]){PH[id].s=j.st;PH[id].h=d.hd}}
  b.dataset.hd=d.hd;b.querySelector('.tach').hidden=true;b.querySelector('.tach').textContent='';
  xongBo(b,boQua?'Không phải ảnh khách':(j.ten+' — '+j.dv));
}
function dungBo(k){guiBo(k,false)}
function boQuaBo(k){guiBo(k,true)}
function suaBo(k){const b=document.getElementById('b'+k);b.classList.remove('xong');chonBo(b)}
async function luu(id,extra){
  const el=document.getElementById('q'+id);
  const d={id,hd:el.querySelector('.hd').value,loai:el.querySelector('.loai').value,
           vung:el.querySelector('.vung').value,ghi:el.querySelector('.ghi').value,...extra};
  const r=await fetch('/luu',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)});
  if(!r.ok){alert('Lưu lỗi: '+await r.text());return}
  const st=(await r.json()).st;el.className='ph '+st;
  const t=document.getElementById('p'+id);if(t)t.className='t '+st;
  PH[id].s=st;PH[id].h=d.bo_qua?'':d.hd;
  const b=el.closest('.bo'),ids=b.dataset.ids.split(',');
  if(ids.every(x=>PH[x]&&PH[x].s)){
    const kh=new Set(ids.filter(x=>PH[x].s==='ok').map(x=>PH[x].h));
    xongBo(b,kh.size?('theo từng ảnh ('+kh.size+' khách)'):'Không phải ảnh khách');}
}
function boQua(id){if(confirm('Ảnh này KHÔNG phải ảnh khách (ảnh cá nhân, giấy tờ, chụp màn hình)?'))luu(id,{bo_qua:1})}
const TAG={chac:'Chắc chắn',goi_y:'Gợi ý',chua_ro:'Chưa rõ',khong_hd:'Không HĐ'};
function tachBo(k){
  const b=document.getElementById('b'+k),w=b.querySelector('.tach');
  if(!w.hidden){w.hidden=true;return}
  w.textContent='';const tt=thuTu(b);
  for(const id of b.dataset.ids.split(',')){const p=PH[id];if(!p)continue;
    const c=document.createElement('div');c.className='ph '+(p.s||'');c.id='q'+id;
    if(p.i){const im=document.createElement('img');im.loading='lazy';im.src='/anh/'+encodeURIComponent(id);
      im.onclick=()=>zoom(im.src);c.append(im)}
    const m=document.createElement('div');m.className='small';
    m.textContent=p.g+' · '+p.f+' · '+(TAG[p.t]||'')+(p.k?' · ⚠ thiếu ngày chụp gốc':'');c.append(m);
    const l=document.createElement('div');l.className='small';l.textContent=p.l+(p.u?' · '+p.u:'');c.append(l);
    const loc=document.createElement('input');loc.className='loc';loc.placeholder='lọc khách';
    const s=document.createElement('select');s.className='hd';dienHd(s,tt,p.h,'');
    ganLoc(loc,s,tt,()=>p.h);
    const sl=document.createElement('select');sl.className='loai';dienDs(sl,DL.loai,p.a,'— trước/sau —');
    const sv=document.createElement('select');sv.className='vung';dienDs(sv,DL.vung,p.v,'— vùng —');
    const g=document.createElement('input');g.className='ghi';g.placeholder='ghi chú';g.value=p.n;
    const n=document.createElement('div');n.className='nut';
    const b1=document.createElement('button');b1.className='p';b1.textContent='✓ Lưu ảnh này';b1.onclick=()=>luu(id,{});
    const b2=document.createElement('button');b2.textContent='Không phải ảnh khách';b2.onclick=()=>boQua(id);
    n.append(b1,b2);c.append(loc,s,sl,sv,g,n);w.append(c);}
  w.hidden=false;
}
function khoiTao(){
  for(const b of document.querySelectorAll('.bo')){
    const q=b.querySelector('.quyet'),sel=q.querySelector('.hd'),tt=thuTu(b);
    dienHd(sel,tt,b.dataset.hd,'');ganLoc(q.querySelector('.loc'),sel,tt,()=>b.dataset.hd);
    dienDs(q.querySelector('.loai'),DL.loai,b.dataset.loai,'— trước/sau —');
    dienDs(q.querySelector('.vung'),DL.vung,b.dataset.vung,'— vùng (tuỳ chọn) —');
    b.addEventListener('focusin',()=>chonBo(b));b.addEventListener('click',()=>chonBo(b));
  }
  chonBo(document.querySelector('.bo:not(.xong)'));
  document.addEventListener('keydown',e=>{
    if(e.key!=='Enter'||!CUR||CUR.classList.contains('xong'))return;
    if(['INPUT','SELECT','TEXTAREA','BUTTON'].includes(document.activeElement.tagName))return;
    e.preventDefault();dungBo(CUR.dataset.k);});
}
khoiTao();
"""


_MA_MAT = re.compile(r"(?:khuôn mặt thuộc|mặt giống|mặt thuộc|theo khuôn mặt) khách (?:khác \()?([^\s,()]+)")


def _ma_tu_ly_do_mat(ly_do: str | None) -> str | None:
    """Mã KH ghi trong lý do của luật cụm mặt ('khuôn mặt thuộc khách KH1 (cụm…', 'cảnh báo: khuôn mặt thuộc
    khách khác (KH2, cụm…'), không có -> None."""
    m = _MA_MAT.search(ly_do or "")
    return m.group(1) if m else None


def _o_anh_mau(conn, ma_kh: str, ngay: str, bo_nho: dict, nhan: str = "") -> str:
    """Ảnh gợi ý theo gói: 1–2 ảnh đã duyệt/chắc của mã KH đó (ngày khác) để nhân viên so mặt nhanh.
    Chỉ ảnh đã có bản xem trên máy, qua route /anh/<id> sẵn có."""
    ids = _anh_mau(conn, ma_kh, ngay, bo_nho, gioi_han=6)
    o = []
    for pid in ids:
        q = conn.execute("SELECT id, ngay, anh_xem FROM photos WHERE id=?", (pid,)).fetchone()
        if not q or not q["anh_xem"] or not os.path.exists(q["anh_xem"]):
            continue
        src = html.escape(f"/anh/{q['id']}", quote=True)
        o.append(f"<img loading=lazy src='{src}' title='{html.escape(q['ngay'] or '', quote=True)}'"
                 " style='width:64px;height:64px;object-fit:cover;margin-right:4px' onclick=\"zoom(this.src)\">")
        if len(o) == 2:
            break
    if not o:
        return f"<div class=small>Mẫu {html.escape(ma_kh)}: chưa có ảnh đã xác nhận trên máy để so mặt</div>"
    them = f" ({html.escape(nhan)})" if nhan else ""
    return f"<div class=small>So mặt — ảnh đã xác nhận của {html.escape(ma_kh)}{them}:<br>{''.join(o)}</div>"


# ---------------- Diễn tiến điều trị của 1 khách (trang /khach, /tim) ----------------
# Ảnh thuộc khách: đã duyệt -> theo xn_hd; chưa duyệt -> theo goi_y_hd khi máy chấm chắc/gợi ý.
_HD_CUA_ANH = ("v.code = CASE WHEN p.xn_hd IS NOT NULL THEN p.xn_hd"
               " WHEN p.do_tin IN ('chac','goi_y') THEN p.goi_y_hd END")


def _link_khach(ma: str, dv: str = "") -> str:
    """href (đã escape) tới trang diễn tiến của khách."""
    u = f"/khach?ma={quote(ma or '', safe='')}"
    if dv:
        u += f"&dv={quote(dv, safe='')}"
    return html.escape(u)


def _ds_dv(dich_vu: str | None) -> list[str]:
    return [x.strip() for x in (dich_vu or "").split(" | ") if x.strip()]


def _o_tim(q: str = "") -> str:
    return ("<form class=tim action='/tim' method=get><input name=q placeholder='Tìm khách: mã KH, SĐT, tên'"
            f" value='{html.escape(q)}'> <button>Tìm</button></form>")


def _tim_khach(conn, q: str, gioi_han: int = 200) -> list[sqlite3.Row]:
    """Khách CÓ ẢNH khớp mã KH / SĐT / tên (không dấu, chứa chuỗi)."""
    q = (q or "").strip()
    kd, so = khong_dau(q), re.sub(r"\D", "", q)
    if not kd:
        return []
    rows = conn.execute(
        "SELECT v.ma_kh, MAX(v.ten_kh) ten_kh, MAX(v.sdt) sdt, COUNT(*) so_anh, MAX(v.ngay) cuoi "
        f"FROM photos p JOIN visits v ON {_HD_CUA_ANH} WHERE p.bo_qua=0 AND COALESCE(v.ma_kh,'')!='' "
        "GROUP BY v.ma_kh ORDER BY cuoi DESC").fetchall()
    ra = [r for r in rows if kd in khong_dau(r["ma_kh"]) or kd in khong_dau(r["ten_kh"])
          or (len(so) >= 3 and so in chuan_sdt(r["sdt"] or ""))]
    return ra[:gioi_han]


def _trang_tim(conn, q: str) -> bytes:
    o = [f"<header><a href='/'>← Tất cả ngày</a><b>Tìm khách có ảnh</b>{_o_tim(q)}</header><main>"]
    ds = _tim_khach(conn, q)
    if not (q or "").strip():
        o.append("<p>Gõ mã KH, SĐT hoặc tên khách.</p>")
    elif not ds:
        o.append(f"<p>Không thấy khách có ảnh khớp “{html.escape(q)}”.</p>")
    else:
        o.append(f"<div class=visits><b>{len(ds)} khách</b><br>" + "<br>".join(
            f"<a href='{_link_khach(r['ma_kh'])}'>{html.escape(r['ma_kh'])} · {html.escape(r['ten_kh'] or '')}</a>"
            f" <span class=small>· SĐT …{html.escape((r['sdt'] or '')[-4:]) or '—'} · {r['so_anh']} ảnh"
            f" · lần cuối {html.escape(r['cuoi'] or '')}</span>" for r in ds) + "</div>")
    o.append("</main>")
    return _trang("Tìm khách", "".join(o))


COT_LOAI = [("trước", "Trước"), ("trong", "Trong"), ("sau", "Sau")]


def _trang_khach(conn, ma: str, dv: str = "") -> bytes:
    """Diễn tiến điều trị: mỗi lần (ngày HĐ + dịch vụ) một hàng Trước | Trong | Sau."""
    ma, dv = (ma or "").strip(), (dv or "").strip()
    rows = conn.execute(
        "SELECT p.*, v.code hd, v.ngay ngay_hd, v.gio gio_hd, v.ma_kh, v.ten_kh, v.sdt, v.dich_vu "
        f"FROM photos p JOIN visits v ON {_HD_CUA_ANH} WHERE p.bo_qua=0 AND v.ma_kh=? "
        "ORDER BY v.ngay, v.gio, p.thoi_gian", (ma,)).fetchall() if ma else []
    dau = f"<header><a href='/'>← Tất cả ngày</a>{_o_tim()}</header><main>"
    if not rows:
        return _trang("Không có khách", dau + f"<p>Không có ảnh nào của khách mã “{html.escape(ma)}”.</p></main>")
    cuoi = rows[-1]
    tat_ca_dv = list(dict.fromkeys(x for r in rows for x in _ds_dv(r["dich_vu"])))
    if dv:
        rows = [r for r in rows if dv in _ds_dv(r["dich_vu"])]
    lan: dict[tuple, list] = {}
    for r in rows:
        lan.setdefault((r["ngay_hd"], r["dich_vu"] or ""), []).append(r)
    chua = sum(1 for r in rows if r["xn_hd"] is None)
    loc = " · ".join([f"<a href='{_link_khach(ma)}'>{'<b>Tất cả</b>' if not dv else 'Tất cả'}</a>"] + [
        f"<a href='{_link_khach(ma, x)}'>{'<b>' + html.escape(x) + '</b>' if x == dv else html.escape(x)}</a>"
        for x in tat_ca_dv])
    o = [dau, f"<div class=visits><b>{html.escape(ma)} · {html.escape(cuoi['ten_kh'] or '')}</b>"
         f" <span class=small>SĐT …{html.escape((cuoi['sdt'] or '')[-4:]) or '—'} · {len(lan)} lần điều trị"
         f" · {len(rows)} ảnh{f' ({chua} chưa duyệt)' if chua else ''}</span>"
         f"<br><span class=small>Dịch vụ đã làm:</span> {loc}</div>"]
    if not rows:
        o.append(f"<p>Không có ảnh dịch vụ “{html.escape(dv)}”.</p>")
    for (ngay_hd, ten_dv), ds in lan.items():
        hds = ", ".join(dict.fromkeys(html.escape(r["hd"]) for r in ds))
        o.append(f"<div class=dot><h3>{ngay_hd[8:10]}/{ngay_hd[5:7]}/{ngay_hd[:4]} · {html.escape(ten_dv)}"
                 f" <span class=small>HĐ {hds} · {len(ds)} ảnh</span></h3><div class=cot>")
        def loai(r):  # ô trước/trong/sau; trống hoặc lạ -> 'Chưa phân loại'
            return r["loai_anh"] if r["loai_anh"] in {k for k, _ in COT_LOAI} else ""

        cot = COT_LOAI + ([("", "Chưa phân loại")] if any(not loai(r) for r in ds) else [])
        for k, ten in cot:
            o.append(f"<div><h4>{ten}</h4>")
            for r in (r for r in ds if loai(r) == k):
                anh = (f"<img loading=lazy src='/anh/{html.escape(r['id'])}' onclick=\"zoom(this.src)\">"
                       if r["anh_xem"] and os.path.exists(r["anh_xem"]) else
                       "<div class=small style='height:120px;display:flex;align-items:center;justify-content:center;"
                       "background:#eee'>Ảnh chưa tải về máy</div>")
                nhan = "" if r["xn_hd"] is not None else "<span class='tag cd'>chưa duyệt</span> "
                chi_tiet = " · ".join(html.escape(x) for x in (r["vung"], r["ghi_chu"]) if x)
                o.append(f"<div class='ph{' ok' if r['xn_hd'] else ''}'>{anh}<div class=small>{nhan}"
                         f"<a href='/ngay?d={html.escape(quote(r['ngay'] or ''))}'>{html.escape((r['thoi_gian'] or '')[11:16])}"
                         f" {html.escape(r['ngay'] or '')}</a></div>"
                         + (f"<div class=small>{chi_tiet}</div>" if chi_tiet else "") + "</div>")
            o.append("</div>")
        o.append("</div></div>")
    o.append("</main>")
    return _trang(f"Khách {ma}", "".join(o))


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


BO_ANH_TOI_DA = 900  # /luu_bo: tối đa ảnh 1 lần (giới hạn tham số SQLite)


def luu_bo(conn, d: dict) -> tuple[int, dict]:
    """POST /luu_bo {ids, hd, loai, vung, ghi, bo_qua}: 1 quyết định cho cả bộ chụp. Ghi các cột như /luu
    (xn_hd, bo_qua, loai_anh, vung, ghi_chu, xn_luc) cho ĐÚNG các id gửi lên. Từ chối cả lô nếu có id không có
    thật, hd không có trong visits (trừ bỏ qua), loai/vung ngoài danh sách. ghi=None -> giữ ghi chú cũ từng ảnh."""
    ids = d.get("ids")
    if (not isinstance(ids, list) or not ids or len(ids) > BO_ANH_TOI_DA
            or not all(isinstance(x, str) and x for x in ids)):
        return 400, {"loi": "danh sách ảnh không hợp lệ"}
    ids = list(dict.fromkeys(ids))
    co = {r[0] for r in conn.execute(f"SELECT id FROM photos WHERE id IN ({','.join('?' * len(ids))})", ids)}
    if len(co) != len(ids):
        return 400, {"loi": f"{len(ids) - len(co)} ảnh không có trong dữ liệu"}
    bo_qua = 1 if d.get("bo_qua") else 0
    hd, v = None, None
    if not bo_qua:
        hd = d.get("hd")
        v = conn.execute("SELECT * FROM visits WHERE code=?", (hd,)).fetchone() if isinstance(hd, str) and hd else None
        if not v:
            return 400, {"loi": "hóa đơn không có"}
    loai, vung, ghi = d.get("loai") or "", d.get("vung") or "", d.get("ghi")
    if loai not in LOAI_ANH or vung not in VUNG or not (ghi is None or isinstance(ghi, str)):
        return 400, {"loi": "trước/sau, vùng hoặc ghi chú không hợp lệ"}
    luc = dt.datetime.now().isoformat(timespec="seconds")
    with conn:
        conn.executemany(
            "UPDATE photos SET xn_hd=?, bo_qua=?, loai_anh=?, vung=?, ghi_chu=COALESCE(?, ghi_chu), xn_luc=?"
            " WHERE id=?", [(hd, bo_qua, loai, vung, None if ghi is None else ghi[:500], luc, i) for i in ids])
    return 200, {"st": "skip" if bo_qua else "ok", "n": len(ids),
                 "ten": ten_goi(v["ten_kh"]) if v else "", "dv": _dv_ngan(v["dich_vu"]) if v else ""}


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
            return self._gui(_trang_chu(self.conn, bool(parse_qs(u.query).get("tat_ca"))))
        if u.path == "/ngay":
            q = parse_qs(u.query)
            return self._gui(_trang_ngay(self.conn, q.get("d", [""])[0], bool(q.get("tat_ca"))))
        if u.path == "/khach":
            q = parse_qs(u.query)
            return self._gui(_trang_khach(self.conn, q.get("ma", [""])[0], q.get("dv", [""])[0]))
        if u.path == "/tim":
            return self._gui(_trang_tim(self.conn, parse_qs(u.query).get("q", [""])[0]))
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
        if self.path not in ("/luu", "/luu_bo"):
            return self._gui(b"", "text/plain", 404)
        dai = int(self.headers.get("Content-Length", 0) or 0)
        if dai > 1_000_000:
            return self._gui("quá lớn".encode(), "text/plain; charset=utf-8", 413)
        try:
            d = json.loads(self.rfile.read(dai) or b"{}")
        except ValueError:
            d = None
        if not isinstance(d, dict):
            return self._gui("JSON lỗi".encode(), "text/plain; charset=utf-8", 400)
        if self.path == "/luu_bo":
            ma, kq = luu_bo(self.conn, d)
            return self._gui(json.dumps(kq, ensure_ascii=False).encode(), "application/json; charset=utf-8", ma)
        bo_qua = 1 if d.get("bo_qua") else 0
        hd = None if bo_qua else (d.get("hd") or None)
        # 16/10: chỉ nhận ảnh có thật và HĐ có thật (trước đây gõ bừa vẫn ghi).
        if not self.conn.execute("SELECT 1 FROM photos WHERE id=?", (str(d.get("id")),)).fetchone() or (
                hd and not self.conn.execute("SELECT 1 FROM visits WHERE code=?", (str(hd),)).fetchone()):
            return self._gui("ảnh hoặc hóa đơn không có".encode(), "text/plain; charset=utf-8", 400)
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
    s.add_argument("--album", action="store_true",
                   help="cho ảnh đã duyệt vào album Photos (thư mục 'Doctor Laser'): theo khách + theo dịch vụ")
    s.set_defaults(f=cmd_xuat)
    s = sub.add_parser("daykiot", help="đẩy chỉ mục ảnh (theo hóa đơn) lên app KIOT")
    s.add_argument("thang")
    s.set_defaults(f=cmd_daykiot)
    a = ap.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
