"""Xếp ảnh khách vào ALBUM trong app Ảnh (đồng bộ iCloud). Lượng duyệt 16/10/2026.

    .venv/bin/python album_anh.py                    # chạy khan: chỉ đếm, KHÔNG gọi app Ảnh
    .venv/bin/python album_anh.py --ghi              # đồng bộ (chạy trong Terminal của Mac Ảnh)
    .venv/bin/python album_anh.py --ghi --chi khach --toi-da 300   # lô 300 album khách, chạy lại làm tiếp

Thư mục cha "Doctor Laser" trong app Ảnh, 3 thư mục con:
  - "Dịch vụ":    album "DV · <nhóm>" theo các dòng dịch vụ của HĐ (1 HĐ nhiều dịch vụ -> nhiều album).
  - "Theo tháng": album "YYYY-MM" theo THÁNG CỦA HÓA ĐƠN.
  - "Khách":      album "<mã KH> · <Tên>" cho khách có ảnh ở >= 2 ngày HĐ khác nhau (CU-KH… và KH… cùng
                  SĐT = 1 khách, tên album dùng mã mới KH…). App Ảnh tự xếp ảnh theo ngày chụp.
Chỉ ảnh máy ghép CHẮC CHẮN (do_tin='chac') hoặc người ĐÃ DUYỆT (xn_hd), chưa bị loại (bo_qua=0).

Cách đồng bộ: tập ảnh đúng của từng album so với bảng da_album (lần ghi trước).
  - không đổi -> bỏ qua (không gọi app Ảnh);
  - đổi -> XOÁ album đó rồi TẠO LẠI đủ ảnh (AppleScript của app Ảnh không gỡ được ảnh khỏi album).
    XOÁ ALBUM KHÔNG XOÁ ẢNH: ảnh vẫn nằm trong thư viện + các album khác;
  - album lần trước có mà nay không còn ảnh (đổi tên khách, ảnh bị loại) -> xoá album.
Chỉ đụng album trong 3 thư mục con trên; album người tạo / album cũ của `xuat --album` không đụng.
Ghi da_album sau MỖI album xong -> dừng giữa chừng chạy lại được. 3 album lỗi liền -> dừng lượt.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import re
import sqlite3
import subprocess
import sys

import anhkhach as A

THU_MUC = A.THU_MUC_ALBUM  # "Doctor Laser"
TM_DV, TM_THANG, TM_KHACH = "Dịch vụ", "Theo tháng", "Khách"
LO = 200  # tối đa bấy nhiêu ảnh mỗi lệnh osascript
HAN_GIAY = 180  # mỗi lệnh osascript có hạn: app Ảnh kẹt thì không treo cả lượt
LOI_LIEN = 3  # 3 album lỗi liền -> dừng lượt
KHACH_TOI_THIEU = 2  # album khách khi có ảnh ở >= 2 ngày HĐ khác nhau

# Nhóm dịch vụ (Lượng 16/10). Mỗi DÒNG dịch vụ vào nhóm KHỚP ĐẦU TIÊN theo thứ tự này để không nuốt nhau
# (sẹo lồi trước sẹo rỗ; mài viền vào sẹo rỗ). Chữ khớp = chữ không dấu (bảng ma_dich_vu.json) — riêng
# 'not ruoi' bỏ khỏi CO2 (để có nhóm Nốt ruồi), 'tham' bỏ khỏi Pico (để có nhóm Trị thâm).
NHOM = [
    ("Sẹo lồi", ["seo loi"]),
    ("Sẹo rỗ", ["seo", "mai vien", "sr"]),
    ("Vein", ["vein"]),
    ("Filler, HA", ["filler", "tiem ha", "lam day"]),
    ("CO2, Fractional", ["co2", "fractional", "mun thit", "fordyce", "tuyen ba"]),
    ("Chăm sóc da, Peel, Điện di", ["csd", "cham soc da", "peel", "dien di", "ipl"]),
    ("Laser Pico", ["pico", "dom nau", "nam", "tan nhang", "doi moi"]),
    ("PRP", ["prp"]),
    ("Xoá xăm", ["xoa xam"]),
    ("Nốt ruồi", ["not ruoi"]),
    ("Botox", ["botox", "xoa nhan"]),
    ("Meso, Skin booster", ["meso", "skin booster"]),
    ("Trị thâm", ["tham"]),
    ("Mụn", ["mun", "acne"]),
    ("Căng chỉ", ["cang chi"]),
    ("Laserlift", ["laser lift", "laserlift", "lifting"]),
    ("Triệt lông", ["triet long"]),
    # CEO 16/10 thêm theo số ảnh bị bỏ sót: nội bì ~860 ảnh, Revivio ~210, HIFU/Thermax/RF, Exosome
    ("Laser nội bì", ["noi bi"]),
    ("Revivio", ["revivio"]),
    ("HIFU, Thermax, RF", ["hifu", "thermax", "rf"]),
    ("Exosome", ["exosome"]),
]
# Dòng không phải dịch vụ làm trên người: công nợ / cọc, và sản phẩm bán kèm (kem, serum, thuốc...).
_KHONG_DV = re.compile(r"\b(cong no|dat coc|chuyen coc)\b")
_SAN_PHAM_DAU = re.compile(r"^(kem|serum|thuoc|sua rua mat|mat na|duong am|khang sinh|chong tham|gel|toner"
                           r"|vien uong|kcn)\b")
_SAN_PHAM_CO = re.compile(r"\b(revskin|medicos|cystamin|cyspera|cosmess|neosporin|trilasma|curiosin"
                          r"|cleanser|cream|\d+ ?(gr|g|ml))\b")


def nhom_dong(dong: str) -> str | None:
    """1 dòng dịch vụ KiotViet -> tên nhóm (None = công nợ, sản phẩm, hoặc không thuộc nhóm nào)."""
    def sach(x):
        x = re.sub(r"\b(?:bh|bao hanh)(?:\s*\d+\s*(?:nam|thang))?\b", " ", A.khong_dau(x))
        return " ".join(x.split())

    k = sach(dong)
    if not k or _KHONG_DV.search(k) or _SAN_PHAM_DAU.search(k) or _SAN_PHAM_CO.search(k):
        return None
    # Tên chính (ngoài ngoặc) trước: 'TIÊM MESO SKIN BOOSTER (..., giảm nám)' là Meso, không phải Pico.
    for chuoi in (sach(re.sub(r"\([^)]*\)?", " ", dong)), k):
        chuoi = f" {chuoi} "
        for ten, khop in NHOM:
            if any(f" {x} " in chuoi or (len(x) >= 4 and f" {x}" in chuoi) for x in khop):
                return ten
    return None


def nhom_hd(dich_vu: str | None) -> list[str]:
    """Các nhóm của 1 HĐ (nhiều dòng ' | '), không trùng, theo thứ tự dòng."""
    return list(dict.fromkeys(n for d in (dich_vu or "").split(" | ") if (n := nhom_dong(d))))


def ten_khach(ten: str) -> str:
    """'LÊ THỊ DUNG (BS LƯƠNG)' -> 'Lê Thị Dung' (bỏ ghi chú như ten_sach, giữ dấu, hoa chữ đầu)."""
    return " ".join(g[:1].upper() + g[1:] for g, _ in A._tu_ten_kh(ten))[:60]


def anh_dung(conn) -> list[sqlite3.Row]:
    """Ảnh được vào album: đã duyệt (xn_hd) hoặc máy ghép chắc chắn; chưa loại; từ app Ảnh."""
    return conn.execute(
        "SELECT p.id, p.thoi_gian, v.code, v.ngay AS ngay_hd, v.ma_kh, v.ten_kh, v.dich_vu FROM photos p"
        " JOIN visits v ON v.code=COALESCE(p.xn_hd, p.goi_y_hd)"
        " WHERE p.bo_qua=0 AND p.nguon='photos' AND (p.xn_hd IS NOT NULL OR p.do_tin='chac')"
        " ORDER BY p.thoi_gian, p.id").fetchall()


def tinh_album(conn, rows=None) -> dict[tuple[str, str], list[str]]:
    """{(thư mục con, tên album): [uuid ảnh theo giờ chụp]} — tập ảnh ĐÚNG lúc này."""
    rows = anh_dung(conn) if rows is None else rows
    ra: dict[tuple[str, str], list[str]] = collections.defaultdict(list)
    for r in rows:
        for n in nhom_hd(r["dich_vu"]):
            ra[(TM_DV, f"DV · {n}")].append(r["id"])
        if r["ngay_hd"]:
            ra[(TM_THANG, r["ngay_hd"][:7])].append(r["id"])
    # Album khách: gom mã theo người (CU-KH… + KH… cùng SĐT = 1 người).
    khoa = A._khoa_khach(conn)
    nguoi: dict[str, dict] = {}
    for r in rows:
        ma = (r["ma_kh"] or "").strip()
        if not ma:
            continue
        g = nguoi.setdefault(khoa.get(ma, ma), {"ngay": set(), "ids": [], "ma": {}})
        g["ngay"].add(r["ngay_hd"])
        g["ids"].append(r["id"])
        if r["ngay_hd"] >= g["ma"].get(ma, ("", ""))[0]:
            g["ma"][ma] = (r["ngay_hd"], r["ten_kh"])
    for g in nguoi.values():
        if len(g["ngay"]) < KHACH_TOI_THIEU:
            continue
        # Tên album: mã mới KH… (không 'CU-'), HĐ gần nhất.
        ma = max(g["ma"], key=lambda m: (not m.startswith("CU-"), g["ma"][m][0], m))
        ten = ten_khach(g["ma"][ma][1])
        ra[(TM_KHACH, f"{ma} · {ten}" if ten else ma)] = g["ids"]
    return {k: list(dict.fromkeys(v)) for k, v in ra.items()}


def _bang(conn) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS da_album (thu_muc TEXT, album TEXT, id TEXT,"
                 " PRIMARY KEY (thu_muc, album, id))")


def da_ghi(conn) -> dict[tuple[str, str], set]:
    """Tập ảnh mỗi album đã ghi lần trước (bảng da_album; chưa có bảng = chưa ghi gì)."""
    ra: dict[tuple[str, str], set] = collections.defaultdict(set)
    try:
        for tm, al, i in conn.execute("SELECT thu_muc, album, id FROM da_album"):
            ra[(tm, al)].add(i)
    except sqlite3.OperationalError:
        pass
    return dict(ra)


def can_doi(muon: dict, cu: dict) -> list[tuple[str, str]]:
    """Album phải xoá + tạo lại (tập ảnh khác lần trước) hoặc chỉ xoá (nay không còn ảnh)."""
    return sorted(k for k in set(muon) | set(cu) if set(muon.get(k, ())) != cu.get(k, set()))


# ---------------------------- app Ảnh (osascript) ----------------------------
# argv: thư mục cha, thư mục con, tên album, "tao"|"xoa", uuid... (<= LO). Tìm thư mục trước khi tạo
# (không trùng); xoá MỌI album trùng tên trong thư mục con (xoá album KHÔNG xoá ảnh khỏi thư viện);
# "tao": tạo album mới + thêm ảnh, trả id album. Ảnh nào không còn trong thư viện thì bỏ qua ảnh đó.
_TAO = """
on viTri(ds, x)
    repeat with i from 1 to count of ds
        if (item i of ds as text) is x then return i
    end repeat
    return 0
end viTri

on themAnh(a, ds)
    tell application "Photos"
        try
            add ds to a
        on error
            repeat with m in ds
                try
                    add {contents of m} to a
                end try
            end repeat
        end try
    end tell
end themAnh

on run argv
    set cha to item 1 of argv
    set con to item 2 of argv
    set ten to item 3 of argv
    tell application "Photos"
        set i to my viTri(name of every folder, cha)
        if i is 0 then
            set f to make new folder named cha
        else
            set f to folder i
        end if
        set j to my viTri(name of every folder of f, con)
        if j is 0 then
            set g to make new folder named con at f
        else
            set g to folder j of f
        end if
        set ns to name of every album of g
        repeat with k from (count of ns) to 1 by -1
            if (item k of ns as text) is ten then delete album k of g
        end repeat
        if (item 4 of argv) is "xoa" then return ""
        set a to make new album named ten at g
        set ds to {}
        repeat with k from 5 to count of argv
            set end of ds to media item id (item k of argv)
        end repeat
        if (count of ds) > 0 then my themAnh(a, ds)
        return id of a
    end tell
end run
"""
# argv: id album, uuid... (<= LO) -> thêm tiếp vào album vừa tạo.
_THEM = """
on run argv
    tell application "Photos"
        set a to album id (item 1 of argv)
        set ds to {}
        repeat with k from 2 to count of argv
            set end of ds to media item id (item k of argv)
        end repeat
        try
            add ds to a
        on error
            repeat with m in ds
                try
                    add {contents of m} to a
                end try
            end repeat
        end try
    end tell
end run
"""


def _osa(script: str, *argv: str) -> str:
    kq = subprocess.run(["osascript", "-e", script, *argv], capture_output=True, text=True, timeout=HAN_GIAY)
    if kq.returncode != 0:
        raise RuntimeError(kq.stderr.strip()[:150])
    return kq.stdout.strip()


def ghi_album(thu_muc: str, ten: str, ids: list[str]) -> None:
    """Xoá album (nếu có) rồi tạo lại đủ ảnh, theo lô <= LO ảnh mỗi lệnh. ids rỗng = chỉ xoá."""
    mi = [f"{i}/L0/001" for i in ids]
    if not mi:
        _osa(_TAO, THU_MUC, thu_muc, ten, "xoa")
        return
    al = _osa(_TAO, THU_MUC, thu_muc, ten, "tao", *mi[:LO])
    if not al:
        raise RuntimeError("app Ảnh không trả id album")
    for k in range(LO, len(mi), LO):
        _osa(_THEM, al, *mi[k:k + LO])


def dong_bo(conn, muon: dict, toi_da: int = 0) -> tuple[int, int, int]:
    """Ghi các album đổi. Trả (xong, lỗi, còn lại chưa làm)."""
    _bang(conn)
    doi = can_doi(muon, da_ghi(conn))
    if toi_da:
        doi, con = doi[:toi_da], len(doi) - toi_da
    else:
        con = 0
    xong = loi = lien = 0
    for n, (tm, al) in enumerate(doi, 1):
        ids = muon.get((tm, al), [])
        try:
            # Xoá dấu cũ TRƯỚC: lỡ hỏng giữa chừng thì lần sau thấy khác và làm lại album này.
            conn.execute("DELETE FROM da_album WHERE thu_muc=? AND album=?", (tm, al))
            conn.commit()
            ghi_album(tm, al, ids)
            conn.executemany("INSERT OR IGNORE INTO da_album VALUES (?,?,?)", [(tm, al, i) for i in ids])
            conn.commit()
            xong += 1
            lien = 0
        except Exception as e:  # noqa: BLE001
            loi += 1
            lien += 1
            print(f"  ! {tm}/{al}: {str(e)[:150]}", flush=True)
            if lien >= LOI_LIEN:
                print(f"  ! {LOI_LIEN} album lỗi liền — app Ảnh có thể đang treo, dừng lượt này.", flush=True)
                con += len(doi) - n
                break
        if n % 20 == 0 or n == len(doi):
            print(f"  {n}/{len(doi)} album — xong {xong}, lỗi {loi}  ({dt.datetime.now():%H:%M:%S})", flush=True)
    return xong, loi, con


def in_dem(conn, rows, muon: dict, cu: dict) -> None:
    print(f"{len(rows)} ảnh chắc chắn / đã duyệt (bo_qua=0, từ app Ảnh)")
    for tm in (TM_DV, TM_THANG):
        ds = sorted((k[1], len(v)) for k, v in muon.items() if k[0] == tm)
        print(f"\n[{THU_MUC} / {tm}] {len(ds)} album")
        for ten, so in ds:
            print(f"  {so:>7}  {ten}")
    kh = [len(v) for k, v in muon.items() if k[0] == TM_KHACH]
    print(f"\n[{THU_MUC} / {TM_KHACH}] {len(kh)} album (khách có ảnh ở >= {KHACH_TOI_THIEU} ngày HĐ),"
          f" {sum(kh)} ảnh")
    khong, bo = 0, collections.Counter()
    for r in rows:
        dongs = [d.strip() for d in (r["dich_vu"] or "").split(" | ") if d.strip()]
        if not nhom_hd(r["dich_vu"]):
            khong += 1
            bo.update(dongs)
    print(f"\n{khong} ảnh không vào nhóm dịch vụ nào. 10 dòng dịch vụ hay gặp nhất ở các ảnh đó:")
    for d, so in bo.most_common(10):
        print(f"  {so:>7}  {d}")
    doi = can_doi(muon, cu)
    print(f"\nSo với lần ghi trước (da_album): {len(doi)} album cần xoá + tạo lại / xoá,"
          f" {len(muon) - sum(1 for k in doi if k in muon)} album không đổi.")
    for tm in (TM_DV, TM_THANG, TM_KHACH):
        print(f"  {tm}: {sum(1 for k in doi if k[0] == tm)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ghi", action="store_true", help="đồng bộ vào app Ảnh (mặc định chỉ đếm)")
    ap.add_argument("--chi", choices=["dv", "thang", "khach"], help="chỉ 1 thư mục con")
    ap.add_argument("--toi-da", type=int, default=0, help="tối đa bấy nhiêu album đổi mỗi lượt (0 = hết)")
    a = ap.parse_args()
    if a.ghi:
        conn = A.ket_noi()
    else:  # chạy khan: mở CHỈ ĐỌC, không tạo bảng
        conn = sqlite3.connect(f"file:{A.DB_FILE}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
    rows = anh_dung(conn)
    muon = tinh_album(conn, rows)
    chon = {"dv": TM_DV, "thang": TM_THANG, "khach": TM_KHACH}.get(a.chi)
    cu = da_ghi(conn)
    if chon:
        muon = {k: v for k, v in muon.items() if k[0] == chon}
        cu = {k: v for k, v in cu.items() if k[0] == chon}
    if not a.ghi:
        in_dem(conn, rows, muon, cu)
        print("\nCHẠY KHAN — thêm --ghi để đồng bộ vào app Ảnh (chạy trong Terminal của Mac Ảnh).")
        return
    if chon:  # chỉ đồng bộ thư mục được chọn: album thư mục khác coi như không đổi
        muon = {**{k: sorted(v) for k, v in da_ghi(conn).items() if k[0] != chon}, **muon}
    xong, loi, con = dong_bo(conn, muon, a.toi_da)
    print(f"Xong: {xong} album đã xoá + tạo lại / xoá, lỗi {loi}, còn {con} album chờ lượt sau.")
    if loi or con:
        sys.exit(1)


if __name__ == "__main__":
    main()
