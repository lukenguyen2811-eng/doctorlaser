"""Ghi mã KH + SĐT + tên + dịch vụ vào app Ảnh cho ảnh máy ghép "CHẮC CHẮN" (chưa cần duyệt) —
để gõ mã KH / SĐT vào ô Tìm kiếm của app Ảnh (iPhone/iPad/Mac) là ra ảnh. Lượng chọn 13/10/2026.

    .venv/bin/python gan_chac.py 2026-04 2026-10           # chạy khan: chỉ đếm
    .venv/bin/python gan_chac.py 2026-04 2026-10 --ghi     # ghi vào app Ảnh (chạy trong Terminal)
    .venv/bin/python gan_chac.py --sua --ghi               # gỡ nhãn của ảnh người duyệt đã đổi khách / loại

- Chỉ ảnh do_tin='chac', chưa bị loại; chú thích có chữ "chưa duyệt", thêm từ khóa "chưa duyệt".
  Ảnh gợi ý / chưa rõ để sau (chỉ ghi khi đã duyệt, qua `anhkhach.py xuat --gan-tu-khoa`).
- Chỉ THÊM vào app Ảnh. Mọi thứ đã ghi được lưu ở bảng da_gan_chac để gỡ đúng phần mình đã ghi
  nếu người duyệt sửa lại khách (--sua).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys

from anhkhach import _nhan, ket_noi, khoang_thang, thang

CHUA_DUYET = "chưa duyệt"


def _bang(conn) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS da_gan_chac (id TEXT PRIMARY KEY, hd TEXT, tu_khoa TEXT,"
                 " chu_thich TEXT, luc TEXT)")


def can_gan(conn, tu: str, den: str) -> list[dict]:
    rows = conn.execute(
        "SELECT p.*, v.ma_kh, v.ten_kh, v.sdt, v.dich_vu FROM photos p JOIN visits v ON v.code=p.goi_y_hd"
        " WHERE p.do_tin='chac' AND p.bo_qua=0 AND p.xn_hd IS NULL AND p.nguon='photos'"
        " AND p.ngay BETWEEN ? AND ? AND p.id NOT IN (SELECT id FROM da_gan_chac)"
        " ORDER BY p.ngay, p.thoi_gian", (tu, den)).fetchall()
    ra = []
    for r in rows:
        d = dict(r)
        d["xn_hd"] = r["goi_y_hd"]  # _nhan đọc mã HĐ ở xn_hd
        tu_khoa, chu_thich = _nhan(d)
        ra.append({"id": r["id"], "hd": r["goi_y_hd"], "ten_file": r["ten_file"],
                   "tu_khoa": tu_khoa + [CHUA_DUYET], "chu_thich": f"{chu_thich} · ({CHUA_DUYET})"})
    return ra


_GHI = """
on run argv
    tell application "Photos"
        set m to media item id (item 1 of argv)
        set kw to keywords of m
        if kw is missing value then set kw to {}
        repeat with i from 3 to count of argv
            set k to item i of argv
            if kw does not contain k then set end of kw to k
        end repeat
        set keywords of m to kw
        set d to description of m
        if d is missing value then set d to ""
        if d does not contain (item 2 of argv) then
            if d is "" then
                set description of m to (item 2 of argv)
            else
                set description of m to d & linefeed & (item 2 of argv)
            end if
        end if
    end tell
end run
"""
LOI_LIEN = 5  # lỗi liền nhau bấy nhiêu ảnh thì dừng lượt
HAN_GIAY = 90  # app Ảnh có lúc treo/khởi động lại giữa chừng -> 1 ảnh không được chặn cả lượt


def ghi_mot(photoscript, g: dict) -> None:
    """Ghi 1 ảnh bằng osascript có thời hạn (photoscript gọi thẳng thì treo mãi khi app Ảnh kẹt)."""
    if getattr(photoscript, "GIA", False):  # test
        p = photoscript.Photo(g["id"])
        cu = list(p.keywords or [])
        p.keywords = cu + [k for k in g["tu_khoa"] if k not in cu]
        mo_ta = p.description or ""
        if g["chu_thich"] not in mo_ta:
            p.description = f"{mo_ta}\n{g['chu_thich']}".strip()
        return
    import subprocess

    kq = subprocess.run(["osascript", "-e", _GHI, f"{g['id']}/L0/001", g["chu_thich"], *g["tu_khoa"]],
                        capture_output=True, text=True, timeout=HAN_GIAY)
    if kq.returncode != 0:
        raise RuntimeError(kq.stderr.strip()[:100])


def go_mot(photoscript, id_: str, tu_khoa: list[str], chu_thich: str) -> None:
    """Gỡ đúng phần gan_chac đã ghi (từ khóa + dòng chú thích), giữ phần người khác ghi."""
    p = photoscript.Photo(id_)
    p.keywords = [k for k in (p.keywords or []) if k not in set(tu_khoa)]
    p.description = "\n".join(x for x in (p.description or "").split("\n") if x.strip() != chu_thich).strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("tu_thang", nargs="?")
    ap.add_argument("den_thang", nargs="?")
    ap.add_argument("--ghi", action="store_true")
    ap.add_argument("--sua", action="store_true", help="gỡ nhãn ảnh đã được người duyệt đổi khách/loại")
    a = ap.parse_args()
    conn = ket_noi()
    _bang(conn)
    if a.sua:
        sai = conn.execute(
            "SELECT g.* FROM da_gan_chac g JOIN photos p ON p.id=g.id"
            " WHERE p.bo_qua=1 OR (p.xn_hd IS NOT NULL AND p.xn_hd != g.hd)"
            " OR (p.xn_hd IS NULL AND (p.do_tin != 'chac' OR p.goi_y_hd IS NOT g.hd))").fetchall()
        print(f"{len(sai)} ảnh đã ghi nhãn nhưng người duyệt đổi khách / loại, hoặc máy ghép lại không còn"
              " 'chắc chắn' khách đó -> gỡ")
        if a.ghi and sai:
            import photoscript

            for g in sai:
                try:
                    go_mot(photoscript, g["id"], json.loads(g["tu_khoa"]), g["chu_thich"])
                    conn.execute("DELETE FROM da_gan_chac WHERE id=?", (g["id"],))
                    conn.commit()
                except Exception as e:  # noqa: BLE001
                    print(f"  ! {g['id'][:8]}: {str(e)[:100]}")
        return
    if not a.tu_thang:
        sys.exit("Cần tháng: gan_chac.py 2026-04 2026-10 [--ghi]")
    tu = khoang_thang(*thang(a.tu_thang))[0]
    den = khoang_thang(*thang(a.den_thang or a.tu_thang))[1]
    ds = can_gan(conn, tu, den)
    print(f"{len(ds)} ảnh 'chắc chắn' chưa ghi nhãn vào app Ảnh ({tu} → {den})")
    if not a.ghi:
        print("CHẠY KHAN — thêm --ghi để ghi (chạy trong Terminal của Mac Ảnh).")
        return
    import photoscript

    xong = loi = lien = 0
    for i, g in enumerate(ds, 1):
        try:
            ghi_mot(photoscript, g)
            conn.execute("INSERT OR REPLACE INTO da_gan_chac VALUES (?,?,?,?,?)",
                         (g["id"], g["hd"], json.dumps(g["tu_khoa"], ensure_ascii=False), g["chu_thich"],
                          dt.datetime.now().isoformat(timespec="seconds")))
            conn.commit()
            xong += 1
            lien = 0
        except Exception as e:  # noqa: BLE001
            loi += 1
            lien += 1
            print(f"  ! {g['ten_file']}: {str(e)[:100]}", flush=True)
            if lien >= LOI_LIEN:  # app Ảnh treo -> dừng lượt này, lượt sau chạy tiếp
                print(f"  ! {LOI_LIEN} ảnh lỗi liền nhau — app Ảnh có thể đang treo, dừng lượt này.", flush=True)
                break
        if i % 50 == 0 or i == len(ds):
            print(f"  {i}/{len(ds)} — ghi được {xong}, lỗi {loi}", flush=True)
    print(f"Xong: {xong} ảnh đã ghi mã KH/SĐT vào app Ảnh, lỗi {loi}.")


if __name__ == "__main__":
    main()
