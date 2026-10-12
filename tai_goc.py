"""Tải SONG SONG bản gốc ảnh 1 tháng từ iCloud về anh_goc/YYYY-MM (cho `anhkhach.py quet --tai-goc`).

Photos qua AppleScript chỉ xuất từng ảnh một (~2 ảnh/phút). PhotoKit cho nhiều tiến trình
cùng xin iCloud -> nhanh hơn nhiều. Chỉ tải bản tạm của tháng đang xử lý; ảnh trong Photos/iCloud
không bị sửa. Chạy trong Terminal của Mac Ảnh (lần đầu macOS hỏi quyền truy cập Ảnh -> Cho phép):

    .venv/bin/python tai_goc.py 2026-10            # 6 luồng, chỉ ảnh chưa có bản nào trên máy
    .venv/bin/python tai_goc.py 2026-10 --luong 10
    .venv/bin/python tai_goc.py 2026-08 --vua      # ảnh cỡ vừa ~1600px (nhanh hơn, đủ đọc nhãn)
Xong thì chạy:  .venv/bin/python anhkhach.py quet 2026-10 --ocr --tai-goc
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import subprocess
import sys
import time

from anhkhach import ANH_GOC, _co_xem, khoang_thang, thang


def can_tai(tu: str, den: str, thang_dir: str, tai_het: bool = False, vua: bool = False) -> list[str]:
    import osxphotos

    db = osxphotos.PhotosDB()
    d0 = dt.datetime.fromisoformat(tu)
    d1 = dt.datetime.fromisoformat(den) + dt.timedelta(days=1)
    da_co = {f.split(".")[0] for f in os.listdir(thang_dir)}
    if vua:
        da_co |= {f.split(".")[0] for f in os.listdir(os.path.join(thang_dir, "vua"))}
    ra = []
    for p in db.photos(from_date=d0, to_date=d1):
        if p.ismovie or p.intrash or getattr(p, "screenshot", False) or p.uuid in da_co:
            continue
        goc = (p.path_edited if p.hasadjustments else None) or p.path
        if not (goc and os.path.exists(goc)) and (tai_het or not _co_xem(p, thang_dir)):
            ra.append(p.uuid)
    return ra


def tai_vua(u: str, dich: str, canh: int = 1600) -> None:
    """Ảnh cỡ vừa (cạnh dài ~1600px, đã xoay đúng chiều) thay vì bản gốc: đủ đọc nhãn, nhẹ hơn nhiều."""
    import AppKit
    import Foundation
    import Photos

    asset = Photos.PHAsset.fetchAssetsWithLocalIdentifiers_options_([f"{u}/L0/001"], None).firstObject()
    if asset is None:
        raise RuntimeError("không thấy ảnh trong thư viện")
    opt = Photos.PHImageRequestOptions.alloc().init()
    opt.setNetworkAccessAllowed_(True)
    opt.setSynchronous_(True)
    opt.setDeliveryMode_(Photos.PHImageRequestOptionsDeliveryModeHighQualityFormat)
    opt.setResizeMode_(Photos.PHImageRequestOptionsResizeModeFast)
    kq = {}

    def xong(anh, info):
        kq["anh"], kq["info"] = anh, info

    Photos.PHImageManager.defaultManager().requestImageForAsset_targetSize_contentMode_options_resultHandler_(
        asset, Foundation.NSMakeSize(canh, canh), Photos.PHImageContentModeAspectFit, opt, xong)
    anh = kq.get("anh")
    if anh is None:
        raise RuntimeError(str((kq.get("info") or {}).get(Photos.PHImageErrorKey) or "iCloud không trả ảnh")[:80])
    rep = AppKit.NSBitmapImageRep.imageRepWithData_(anh.TIFFRepresentation())
    du_lieu = rep.representationUsingType_properties_(AppKit.NSBitmapImageFileTypeJPEG,
                                                      {AppKit.NSImageCompressionFactor: 0.85})
    tam = dich + ".tam"
    if not du_lieu.writeToFile_atomically_(tam, True):
        raise RuntimeError("không ghi được file")
    os.replace(tam, dich)


def con(thang_dir: str, uuids: list[str], so: int, vua: bool = False) -> None:
    """Tiến trình con: tải lần lượt phần ảnh được giao."""
    from osxphotos.photokit import PHOTOS_VERSION_CURRENT, PhotoLibrary

    lib = PhotoLibrary()
    tam = os.path.join(thang_dir, f".pk_{so}")
    os.makedirs(tam, exist_ok=True)
    for u in uuids:
        if vua:
            try:
                os.makedirs(os.path.join(thang_dir, "vua"), exist_ok=True)
                tai_vua(u, os.path.join(thang_dir, "vua", u + ".jpg"))
                print("ok", flush=True)
            except Exception as e:  # noqa: BLE001
                print(f"loi {u[:8]} {str(e)[:80]}", flush=True)
            continue
        try:
            out = lib.fetch_uuid(u).export(tam, version=PHOTOS_VERSION_CURRENT, overwrite=True)
            anh = [x for x in out if os.path.splitext(x)[1].lower() not in (".mov", ".mp4")]
            if anh:
                os.replace(anh[0], os.path.join(thang_dir, u + os.path.splitext(anh[0])[1].lower()))
            for x in out:
                if os.path.exists(x):
                    os.remove(x)
            print("ok", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"loi {u[:8]} {str(e)[:80]}", flush=True)
    os.rmdir(tam) if not os.listdir(tam) else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("thang")
    ap.add_argument("--luong", type=int, default=6)
    ap.add_argument("--tai-het", action="store_true", help="tải cả ảnh đã có bản xem trước")
    ap.add_argument("--vua", action="store_true",
                    help="tải ảnh cỡ vừa (~1600px) vào anh_goc/YYYY-MM/vua thay vì bản gốc — nhanh, đủ đọc nhãn")
    ap.add_argument("--con", type=int, help=argparse.SUPPRESS)
    a = ap.parse_args()
    y, m = thang(a.thang)
    tu, den = khoang_thang(y, m)
    thang_dir = os.path.join(ANH_GOC, tu[:7])
    os.makedirs(thang_dir, exist_ok=True)

    if a.con is not None:  # tiến trình con nhận danh sách uuid qua stdin
        con(thang_dir, sys.stdin.read().split(), a.con, a.vua)
        return

    from osxphotos.photokit import check_photokit_authorization, request_photokit_authorization

    if not check_photokit_authorization():
        request_photokit_authorization()
        if not check_photokit_authorization():
            sys.exit("Chưa có quyền truy cập Ảnh: Cài đặt hệ thống → Quyền riêng tư & Bảo mật → Ảnh → bật Terminal, rồi chạy lại.")
    os.makedirs(os.path.join(thang_dir, "vua"), exist_ok=True)
    ds = can_tai(tu, den, thang_dir, a.tai_het, a.vua)
    print(f"Cần tải {len(ds)} ảnh tháng {m:02d}/{y}, {a.luong} luồng...", flush=True)
    if not ds:
        return
    t0, xong, loi = time.time(), 0, 0
    procs = []
    for k in range(a.luong):
        phan = ds[k::a.luong]
        if not phan:
            continue
        p = subprocess.Popen([sys.executable, os.path.abspath(__file__), a.thang, "--con", str(k)] + (["--vua"] if a.vua else []),
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        p.stdin.write("\n".join(phan))
        p.stdin.close()
        procs.append(p)
    import selectors

    sel = selectors.DefaultSelector()
    for p in procs:
        sel.register(p.stdout, selectors.EVENT_READ)
    con_lai = len(procs)
    while con_lai:
        for key, _ in sel.select():
            dong = key.fileobj.readline()
            if not dong:
                sel.unregister(key.fileobj)
                con_lai -= 1
                continue
            if dong.startswith("ok"):
                xong += 1
            else:
                loi += 1
                print("  !", dong.strip(), flush=True)
            n = xong + loi
            if n % 10 == 0 or n == len(ds):
                phut = (time.time() - t0) / 60
                print(f"  {n}/{len(ds)} — tải được {xong}, lỗi {loi}, {xong / max(phut, 0.01):.1f} ảnh/phút", flush=True)
    for p in procs:
        p.wait()
    print(f"Xong: {xong} ảnh, lỗi {loi}. Giờ chạy: .venv/bin/python anhkhach.py quet {a.thang} --ocr"
          + ("" if a.vua else " --tai-goc"))


if __name__ == "__main__":
    main()
