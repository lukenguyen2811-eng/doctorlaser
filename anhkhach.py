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
BO_TOI_DA = 7  # bộ <= 7 ảnh có 1 nhãn khớp chắc = 1 khách; bộ dài hơn có thể là 2 khách liền nhau
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
    if "khuon_mat" not in {r[1] for r in conn.execute("PRAGMA table_info(photos)")}:
        conn.execute("ALTER TABLE photos ADD COLUMN khuon_mat TEXT")  # mã người (uuid) app Ảnh nhận ra
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
            return not (g and os.path.exists(g)) and (tai_het or not _co_xem(p, thang_dir))

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
                     " / ".join(x for x in cac_chu if x.strip()), chu_ocr, _ma_nguoi(p)))
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
                         path, path, os.path.splitext(rel)[0].replace(os.sep, " / "), "", ""))
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
            " chu_thich, ocr, khuon_mat) VALUES (?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET ngay=excluded.ngay, thoi_gian=excluded.thoi_gian,"
            " duong_dan=excluded.duong_dan, anh_xem=excluded.anh_xem,"
            " chu_thich=excluded.chu_thich,"
            " ocr=CASE WHEN excluded.ocr != '' THEN excluded.ocr ELSE photos.ocr END,"
            " khuon_mat=CASE WHEN excluded.khuon_mat != '' THEN excluded.khuon_mat ELSE photos.khuon_mat END",
            r,
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


def _tu_ten_kh(ten: str) -> list[tuple[str, str]]:
    """Tên KiotViet bỏ ghi chú: ngoặc '(...)' (kể cả thiếu ngoặc đóng) và đuôi 'KH7332 GT', 'GT',
    'BS LUONG', 'EM BS LƯƠNG'... Luôn giữ ít nhất chữ đầu; bỏ hết thì trả tên gốc."""
    tu = _tu_goc(re.sub(r"\([^)]*\)?", " ", ten or ""))
    for i in range(1, len(tu)):
        k = tu[i][1]
        if k in _GHI_CHU_TEN or re.fullmatch(r"(kh)?\d+(gt)?", k):
            j = i
            if k == "bs":
                while j > 1 and tu[j - 1][1] in _TRUOC_BS:
                    j -= 1
            tu = tu[:j]
            break
    return tu or _tu_goc(ten)


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
    if ma and re.search(rf"\b{re.escape(ma)}\b", chu):
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
    r"(?<![^\W\d_])([^\W\d_]+(?:\s+[^\W\d_]+){0,2})\s+(\d{1,2})\s*[/.\-]\s*(\d{1,2})\s*[/.\-]\s*(\d{2,4})(?!\d)")
# Chữ chung trên ảnh/sản phẩm: có mặt trong đoạn tên -> không phải nhãn ('Doctor Laser 1/10/26', 'HSD').
_KHONG_PHAI_TEN = {"doctor", "laser", "dr", "clinic", "spa", "bs", "bac", "si", "ngay", "date", "hsd", "nsx",
                   "exp", "mfg", "lot", "het", "phong", "kham", "tp", "hcm", "sdt", "tel", "dt", "so"}
# Chữ dịch vụ thường gặp trong nhãn không gạch ('Thanh seo', 'Lan nách'); 'ha' trùng tên Hà -> bỏ.
_TU_DV_THEM = {"nach", "not", "ruoi", "dien", "di", "peel", "tln", "tl", "mat"}
XUNG_HO = {"a", "c", "chi", "anh", "em", "co", "chu", "be"}
# Mã dịch vụ chung/rác trên nhãn ('Lan-tri', 'Mai-tiem', 'test'): khớp thì vẫn dùng để chọn HĐ,
# không khớp thì coi như nhãn không ghi dịch vụ (không hạ điểm 'lệch dịch vụ').
DV_CHUNG = {"tri", "tiem", "test", "giai", "kham", "dieu", "dtri", "lam"}


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
        dv = (set(MA_DV) | set(MA_DV_OCR) | _TU_DV_THEM) - {"ha"}
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
        ra.append({"goc": " ".join(m.group(0).split()), "ten": " ".join(k for _, k in ten),
                   "ten_goc": " ".join(g for g, _ in ten), "ma_dv": ma_dv, "ngay": ngay.isoformat(),
                   "loai": loai, "gach": False})
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
        ten = _tu_goc(m.group(1))
        ra.append({"goc": " ".join(goc.split()), "ten": " ".join(k for _, k in ten),
                   "ten_goc": " ".join(g for g, _ in ten),
                   "ma_dv": tu[0] if tu else "", "ngay": ngay, "loai": loai, "gach": True})
    return ra or _nhan_khong_gach(chu)


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
    tu = khong_dau(dich_vu).split()
    if not ma or not tu:
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


def _khop_nhan(conn, nhan: dict, ngay_anh: str) -> tuple[str | None, int, str]:
    """Khớp 1 nhãn với hóa đơn cùng ngày ghi trên nhãn (không có thì ngày chụp)."""
    ngay, sai = nhan["ngay"] or ngay_anh, ""
    if abs((dt.date.fromisoformat(ngay) - dt.date.fromisoformat(ngay_anh)).days) > 7:
        # OCR đọc sai số ('8/10/16', '3/11 0/26') -> nhãn viết cùng ngày chụp.
        ngay, sai = ngay_anh, f" (ngày trên nhãn đọc ra {nhan['ngay']}, dùng ngày chụp)"
    visits = conn.execute("SELECT * FROM visits WHERE ngay=?", (ngay,)).fetchall()
    lech_ngay = (f" (nhãn ghi ngày {ngay})" if ngay != ngay_anh else "") + sai
    T = {v["code"]: _tu_ten_kh(v["ten_kh"]) for v in visits}

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
    if v is not None and d < 50 and nhan["ma_dv"]:
        # Lệch dịch vụ: HĐ có thể nhập hôm trước/hôm sau -> khách cùng tên, dịch vụ khớp ở ngày ±1
        # (đúng 1 ngày có) -> chỉ gợi ý 50.
        ke = []
        for lech in (-1, 1):
            n = (dt.date.fromisoformat(ngay) + dt.timedelta(days=lech)).isoformat()
            vs = conn.execute("SELECT * FROM visits WHERE ngay=?", (n,)).fetchall()
            T2 = {x["code"]: _tu_ten_kh(x["ten_kh"]) for x in vs}
            v2, d2, _ = _khop_ten(vs, lambda x: [k for _, k in T2[x["code"]]], T2, nhan, w, wg)
            if v2 is not None and d2 >= 50 and _dv_khop(nhan["ma_dv"], v2["dich_vu"]):
                ke.append((n, v2))
        if len(ke) == 1:
            n, v2 = ke[0]
            return v2["code"], 50, f"nhãn '{nhan['goc']}' khớp tên + dịch vụ {v2['ten_kh']} — HĐ ngày kế ({n})"
    if v is None:
        if d:
            return None, 0, f"nhãn '{nhan['goc']}' trùng {d} khách{lech_ngay} — người chọn"
        return None, 0, f"nhãn '{nhan['goc']}' không thấy khách tên này trong hóa đơn ngày {ngay}"
    ly_do = f"nhãn '{nhan['goc']}' {ly_do} {v['ten_kh']}{lech_ngay}"
    if d > 50 and not nhan.get("gach", True) and not (len(w) >= 2 and t(v) == w):
        d, ly_do = 50, ly_do + " — nhãn không có gạch, chưa khớp đủ họ tên: chỉ gợi ý"
    return v["code"], d, ly_do


def _khop_ten(visits, t, T, nhan, w, wg) -> tuple[sqlite3.Row | None, int, str]:
    """(hóa đơn, điểm, lý do) — hóa đơn None: d = số khách trùng (0 = không thấy)."""
    dv = nhan["ma_dv"]

    def cung_ten(v, k):
        return len(t(v)) >= k and t(v)[-k:] == w[-k:]

    # Chữ thừa phía trước tên ('Laser Trang') -> thử bớt dần từ trái: 3 chữ, 2 chữ, 1 chữ.
    ung, k = [], len(w)
    for k in range(len(w), 0, -1):
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
    if not ung and w:
        # Tên nước ngoài đảo thứ tự ('Cheng Wei' ~ 'Wu Cheng Wei') -> tên nằm trong họ tên; OCR sai
        # 1 chữ ('Thann' ~ 'Thanh'). Chỉ "chắc" khi tên nằm trong họ tên VÀ dịch vụ trên nhãn khớp.
        def trong(v):
            return set(w) <= set(t(v))

        def lech(v):
            return bool(t(v)) and len(w[-1]) >= 4 and _lech_1(w[-1], t(v)[-1])

        ung = [v for v in visits if trong(v)]
        if len(ung) == 1 and _dv_khop(dv, ung[0]["dich_vu"]):
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
    if len(ung) == 1 and dv and dv not in DV_CHUNG and not gan_dung and not _dv_khop(dv, ung[0]["dich_vu"]):
        # Khớp đuôi tên nhưng dịch vụ lệch ('Thu' ~ '... Thư' mài sẹo, trong khi khách 'THU (KH TỰ ĐẾN)'
        # làm pico) -> xét khách có tên nằm trong họ tên + dịch vụ khớp; không có thì chỉ gợi ý.
        khac = [v for v in visits if v["code"] != ung[0]["code"]
                and set(w[-k:]) <= set(t(v)) and _dv_khop(dv, v["dich_vu"])]
        if len(khac) == 1:
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
        if dv and dv not in DV_CHUNG and not loc_dv and not gan:  # soát 8b3c1c8: 15/83 ảnh mã dịch vụ không khớp HĐ nào của khách mà vẫn lan
            return v, 40, f"khớp tên nhưng lệch dịch vụ (không HĐ nào trong {len(ung)} HĐ của khách khớp mã) —"
        return v, 50, f"cùng 1 khách có {len(ung)} hóa đơn trong ngày, chọn hóa đơn sớm nhất —"
    return None, len(ung), ""


def _phut(a: str, b: str) -> float:
    return abs((dt.datetime.fromisoformat(a) - dt.datetime.fromisoformat(b)).total_seconds()) / 60


def _hd_neo(r: dict) -> str | None:
    """HĐ mà ảnh neo được phép lan; neo < 50 (khớp tên lệch dịch vụ) coi như nhãn chưa khớp."""
    return r["hd"] if r["diem"] >= 50 else None


def _bo_chup(ds: list[dict]) -> None:
    """Luật BỘ CHỤP: phòng khám chụp mỗi khách 5 kiểu liên tục (chính diện, nghiêng 45°/90° hai bên),
    nhãn viết tay thường chỉ ở tấm chính diện. Bộ = chuỗi ảnh liền nhau, 2 ảnh kề cách <= BO_GIAY
    (bỏ ảnh trùng giây). Neo = ảnh có nhãn hoặc đã khớp HĐ điểm >= 50.
    - Bộ <= BO_TOI_DA ảnh, mọi neo cùng 1 HĐ, có neo chắc -> cả bộ 'chac'.
    - Bộ dài hơn: >= 2 neo cùng 1 HĐ + có neo chắc -> 'chac' (ảnh cách neo gần nhất > BO_TOI_DA-1 tấm
      chỉ gợi ý); 1 neo -> chỉ gợi ý (khách sau có thể không viết nhãn); neo 2+ khách -> cắt tại quãng
      nghỉ dài nhất giữa 2 neo khác khách liên tiếp, mỗi phần chỉ gợi ý theo neo của phần đó.
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
        hd_neo = [_hd_neo(b[i]) for i in neo]
        mot_hd = None not in hd_neo and len(set(hd_neo)) == 1
        if not any(b[i]["diem"] >= 80 for i in neo):
            # Neo chỉ gợi ý (khớp một phần tên): không nâng 'chac' nhưng không để sót tấm nghiêng —
            # mọi tấm còn lại trong bộ ít nhất gợi ý theo neo (khi không có nhãn/HĐ khác trong bộ).
            hd = hd_neo[0]
            if mot_hd and not any((r["hd"] and r["hd"] != hd) or (r["xn"] and r["xn"] != hd) for r in b):
                for r in b:
                    if not r["hd"] and r["do_tin"] != "khong_hd":
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
            dai = len(b) > BO_TOI_DA
            for i, r in enumerate(b):
                if r["diem"] >= 80 or r["do_tin"] == "khong_hd":
                    continue
                if dai and (len(neo) < 2 or min(abs(i - j) for j in neo) > BO_TOI_DA - 1):
                    if not r["hd"]:
                        r.update(hd=hd, do_tin="goi_y", diem=40,
                                 ly_do=f"bộ chụp liền dài {len(b)} ảnh, chỉ {len(neo)} nhãn với {tu}"
                                 " — có thể 2 khách liền nhau, người chọn" if len(neo) < 2 else
                                 f"bộ chụp liền dài {len(b)} ảnh, ảnh xa nhãn với {tu} — người chọn")
                    continue
                r.update(hd=hd, do_tin="chac", diem=80,
                         ly_do=f"cùng bộ chụp liền {len(b)} ảnh với {tu}")
            continue
        if len(b) <= BO_TOI_DA:
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
            for r in phan:
                if not r["hd"] and not r["nhan"] and r["do_tin"] != "khong_hd" and r["xn"] in (None, hd):
                    r.update(hd=hd, do_tin="goi_y", diem=40,
                             ly_do=f"tách bộ dài theo quãng nghỉ ({len(b)} ảnh liền, {len(phan)} ảnh phần này)"
                             " — cùng phần với ảnh đã khớp")


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
        ket_qua[p["id"]] = {"dot": dot, "hd": None, "do_tin": "chua_ro", "ly_do": "", "diem": 0,
                            "nhan": False, "gio": dt.datetime.fromisoformat(p["thoi_gian"]),
                            "xn": p["xn_hd"]}
    # Giờ trùng đến từng giây ở >= TRUNG_GIAY ảnh: giờ nhập/lưu -> không lan đợt, không dùng luật giờ.
    dem_giay = {}
    for p in photos:
        dem_giay[p["thoi_gian"]] = dem_giay.get(p["thoi_gian"], 0) + 1
    for p in photos:
        ket_qua[p["id"]]["trung_giay"] = dem_giay[p["thoi_gian"]] >= TRUNG_GIAY

    for p in photos:
        r = ket_qua[p["id"]]
        goc = f"{p['chu_thich']} {p['ocr']} {p['ten_file']}"
        r["nhan"] = bool(doc_nhan(f"{p['chu_thich']} {p['ocr']}", int(ngay[:4])))
        if not visits and not r["nhan"]:
            r.update(do_tin="khong_hd", ly_do="ngày này không có hóa đơn")
            continue
        chu = khong_dau(goc)
        # Các dãy số dạng SĐT (cho phép cách/chấm/gạch: 0909 123 456).
        so = " ".join(re.sub(r"\D", "", x) for x in re.findall(r"\d[\d .\-]{7,}\d", goc))
        diem = sorted(((_diem(v, chu, so), v["code"]) for v in visits), reverse=True)
        (d, ly_do), code = diem[0] if diem else ((0, ""), None)
        tho = (code, d, ly_do) if d and (len(diem) == 1 or diem[1][0][0] < d) else None
        if tho and d >= 80:
            r.update(hd=code, diem=d, ly_do=ly_do, do_tin="chac")
            continue
        # Nhãn nhân viên ghi trên ảnh (chỉ có tên + dịch vụ viết tắt + ngày). Khớp một phần tên ở trên
        # (50) không chặn nhãn: nhãn cho điểm cao hơn thì lấy nhãn.
        for nhan in doc_nhan(f"{p['chu_thich']} {p['ocr']}", int(ngay[:4])):
            hd, d, ly_do = _khop_nhan(conn, nhan, ngay)
            r["ly_do"] = ly_do
            if hd:
                if not tho or d > tho[1]:
                    r.update(hd=hd, diem=d, do_tin="chac" if d >= 80 else "goi_y")
                break
        if tho and not r["hd"]:
            r.update(hd=tho[0], diem=tho[1], ly_do=tho[2], do_tin="goi_y")

    _bo_chup([ket_qua[p["id"]] for p in photos])

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
            if tim and tim[0][1] and (len(tim) == 1 or tim[1][1] == tim[0][1] or tim[1][0] > tim[0][0]):
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
                if r["do_tin"] != "khong_hd":
                    r.update(hd=gan[0]["code"], do_tin="goi_y",
                             ly_do=f"chỉ 1 hóa đơn gần giờ chụp ({gan[0]['gio'][:5]})")

    # Còn lại: nếu cả ngày chỉ 1 khách -> gợi ý khách đó.
    if len(visits) == 1:
        for r in ket_qua.values():
            if not r["hd"] and r["do_tin"] != "khong_hd":
                r.update(hd=visits[0]["code"], do_tin="goi_y", ly_do="cả ngày chỉ có 1 hóa đơn")

    _goi_y_khuon_mat(conn, ngay, photos, ket_qua)

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
            if vs:
                ung[ma] = vs[0]
        if len(ung) == 1:
            v = next(iter(ung.values()))
            r.update(hd=v["code"], do_tin="goi_y", diem=40,
                     ly_do="cùng khuôn mặt với ảnh đã xác nhận của khách")


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
         f" Xanh = đã duyệt hết.</span>{_o_tim()}</header><main><div class=days>"]
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

    def dong(v):  # 1 dòng hóa đơn; tên khách là link sang trang diễn tiến
        ngay_hd = "" if v["ngay"] == ngay else f"{v['ngay'][8:10]}/{v['ngay'][5:7]} "
        ten = html.escape(v["ten_kh"] or "")
        if v["ma_kh"]:
            ten = f"<a href='{_link_khach(v['ma_kh'])}'>{ten}</a>"
        return (f"<span class=small>{html.escape(ngay_hd + (v['gio'] or ''))} · {ten} "
                f"({html.escape(v['ma_kh'] or '')}) · {html.escape((v['dich_vu'] or '')[:50])}"
                f" · HĐ {html.escape(v['code'])}</span>")

    theo_ma = {v["code"]: v for v in visits + visits_khac}

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
        "<br>".join(dong(v) for v in visits)
        or "<span class=small>Không có hóa đơn ngày này.</span>") + (
        "<br><b>Hóa đơn ngày khác (theo nhãn trên ảnh):</b><br>" + "<br>".join(dong(v) for v in visits_khac)
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
            chu = html.escape(((p["chu_thich"] or "") + " " + (p["ocr"] or "")).strip()[:120])
            v_hd = theo_ma.get(hd)
            den_kh = (f"<div class=small><a href='{_link_khach(v_hd['ma_kh'])}'>→ diễn tiến "
                      f"{html.escape(v_hd['ma_kh'])}</a></div>" if v_hd and v_hd["ma_kh"] else "")
            o.append(
                f"<div class='ph {st}' id='p{p['id']}' data-id='{p['id']}' data-dot='{so}'>"
                + (f"<img loading=lazy src='/anh/{p['id']}' onclick=\"zoom(this.src)\">"
                   if p["anh_xem"] and os.path.exists(p["anh_xem"]) else
                   "<div class=small style='height:200px;display:flex;align-items:center;justify-content:center;"
                   "background:#eee;text-align:center'>Ảnh còn trên iCloud,<br>chưa tải về máy</div>") +
                f"<div class=small>{p['thoi_gian'][11:16]} · {html.escape(p['ten_file'])} "
                f"<span class='tag {p['do_tin']}'>{NHAN_NGAN.get(p['do_tin'], '')}</span></div>"
                f"<div class=small>{html.escape(p['ly_do'] or '')}{' · ' + chu if chu else ''}</div>{den_kh}"
                f"{chon_hd(hd, 'hd')}{chon(LOAI_ANH, p['loai_anh'], 'loai', '— trước/sau —')}{chon(VUNG, p['vung'], 'vung', '— vùng —')}"
                f"<input class=ghi placeholder='ghi chú (tình trạng, kết quả...)' value='{html.escape(p['ghi_chu'] or '')}'>"
                f"<div style='display:flex;gap:6px;margin-top:6px'>"
                f"<button class=p onclick=\"luu('{p['id']}',{{}})\">✓ Lưu</button>"
                f"<button onclick=\"luu('{p['id']}',{{bo_qua:1}})\">Không phải ảnh khách</button></div></div>")
        o.append("</div></div>")
    o.append("</main>")
    return _trang(f"Ảnh {ngay}", "".join(o))


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
