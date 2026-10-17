"""Đổi NGÀY CHỤP trong app Ảnh cho ảnh đưa lên trễ (Lượng giao 17/10/2026, CEO chọn cách làm).

    .venv/bin/python doi_ngay.py                 # chạy khan: chỉ đếm + xuất danh sách, KHÔNG gọi app Ảnh
    .venv/bin/python doi_ngay.py --ghi           # đổi ngày trong app Ảnh (chạy trong Terminal của Mac Ảnh)
    .venv/bin/python doi_ngay.py --ghi --toi-da 1   # chạy thử 1 nhóm mới nhất (chạy lại làm tiếp nhóm kế)
    .venv/bin/python doi_ngay.py --go            # đặt lại NGÀY CŨ cho mọi ảnh đã đổi (bảng doi_ngay)

Chỉ đổi ảnh:
  - KHÔNG có ngày gốc EXIF (photos.ngay_goc = 0): ngày trong app Ảnh là ngày nhận/tải, không phải ngày chụp;
  - máy ghép CHẮC CHẮN hoặc người ĐÃ DUYỆT, chưa loại, từ app Ảnh, không phải biên lai / màn hình máy (may_loai);
  - ngày ảnh TRỄ 1–2 ngày so với ngày HĐ đang gắn;
  - nhãn trên ảnh (nếu có ghi ngày) ghi đúng ngày HĐ — nhãn ghi ngày khác thì ngày nhãn thắng: KHÔNG đổi;
  - ảnh của thư viện (PHAsset.sourceType = 1); ảnh album CHIA SẺ iCloud (2) không đổi được -> bỏ qua.
Ảnh có EXIF giữ nguyên (ngày máy chụp là thật; lệch HĐ = buổi theo gói). Ảnh không EXIF trễ > 2 ngày / trước HĐ:
chỉ liệt kê, không đổi.

Ngày mới = ngày HĐ + giờ HĐ cho ẢNH ĐẦU của mỗi nhóm (cùng ngày ảnh, cùng HĐ); các ảnh sau giữ đúng chênh lệch
giây so với ảnh đầu -> thứ tự và khoảng cách trong bộ chụp không đổi. HĐ không có giờ -> 12:00.

An toàn: trước khi đổi, mỗi ảnh được lưu vào bảng doi_ngay (id, ngày giờ cũ đầy đủ, ngày giờ mới, HĐ, lúc);
--go đặt lại đúng ngày giờ cũ. Sau khi đổi, photos.ngay / thoi_gian trong DB cập nhật theo (lần quét sau đọc lại
không lệch) rồi ghép lại ngày cũ + ngày mới; ảnh nào ghép ra HĐ khác HĐ ban đầu thì in ra để soát.

FILE GỐC: PhotoKit chỉ sửa siêu dữ liệu của app Ảnh (ngày, từ khoá, chú thích), KHÔNG sửa được file gốc trong
thư viện iCloud. Ngày mới, mã KH/SĐT/dịch vụ (từ khoá + chú thích do gan_chac ghi) nằm trong app Ảnh và đồng bộ
iCloud sang mọi máy. Muốn siêu dữ liệu đi theo file khi đưa ra ngoài: app Ảnh → chọn ảnh → Tệp → Xuất → "Xuất ảnh"
(KHÔNG chọn "Xuất bản gốc chưa sửa đổi"), bật "Tiêu đề, từ khoá và chú thích" + "Thông tin vị trí": file xuất ra
mang ngày đã đổi và từ khoá/chú thích trong IPTC/XMP. Việc này làm tay khi cần, script không làm.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import sqlite3
import sys

import anhkhach as A

TRE = (1, 2)  # ngày ảnh trễ so với ngày HĐ (ngày) thì đổi
LO = 50  # ảnh / lần performChanges
GIO_MAC_DINH = "12:00"


def _bang(conn) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS doi_ngay (id TEXT PRIMARY KEY, ngay_cu TEXT, thoi_gian_cu TEXT,"
                 " ngay_moi TEXT, thoi_gian_moi TEXT, hd TEXT, luc TEXT, trang_thai TEXT)")


def chon(conn) -> tuple[list[dict], list[dict]]:
    """(sẽ đổi, không đổi kèm lý do) — chỉ đọc DB."""
    cot = {r[1] for r in conn.execute("PRAGMA table_info(photos)")}
    da = set()
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name='doi_ngay'").fetchone():
        da = {r[0] for r in conn.execute("SELECT id FROM doi_ngay WHERE trang_thai='xong'")}
    rows = conn.execute(
        "SELECT p.id, p.ngay, p.thoi_gian, p.ocr, p.chu_thich, p.do_tin, p.xn_hd, "
        + ("p.may_loai, " if "may_loai" in cot else "NULL AS may_loai, ") +
        "v.code, v.ngay AS ngay_hd, v.gio AS gio_hd FROM photos p JOIN visits v ON v.code=COALESCE(p.xn_hd, p.goi_y_hd)"
        " WHERE p.bo_qua=0 AND p.nguon='photos' AND p.ngay_goc=0 AND (p.xn_hd IS NOT NULL OR p.do_tin='chac')"
        " ORDER BY p.ngay, p.thoi_gian, p.id").fetchall()
    doi, khong = [], []
    for r in rows:
        if r["id"] in da or not r["ngay_hd"]:
            continue
        tre = (dt.date.fromisoformat(r["ngay"]) - dt.date.fromisoformat(r["ngay_hd"])).days
        if tre == 0:
            continue
        d = dict(r, tre=tre)
        if r["may_loai"]:
            khong.append(dict(d, ly_do=f"may_loai {r['may_loai']}"))
            continue
        if tre not in TRE:
            khong.append(dict(d, ly_do="trễ > 2 ngày" if tre > 0 else "ngày ảnh TRƯỚC ngày HĐ"))
            continue
        ngay_nhan = {n["ngay"] for n in A.doc_nhan(f"{r['chu_thich'] or ''} {r['ocr'] or ''}", int(r["ngay"][:4]))
                     if n.get("ngay")}
        if ngay_nhan and r["ngay_hd"] not in ngay_nhan:
            khong.append(dict(d, ly_do=f"nhãn ghi ngày {sorted(ngay_nhan)[0]} khác ngày HĐ"))
            continue
        d["ly_do"] = (f"không EXIF, trễ {tre} ngày so với HĐ"
                      + (" — nhãn ghi đúng ngày HĐ" if ngay_nhan else ""))
        doi.append(d)
    # Ngày giờ mới: theo nhóm (ngày ảnh, HĐ) — ảnh đầu = giờ HĐ, ảnh sau + chênh lệch gốc
    nhom = collections.defaultdict(list)
    for d in doi:
        nhom[(d["ngay"], d["code"])].append(d)
    for ds in nhom.values():
        ds.sort(key=lambda d: (d["thoi_gian"], d["id"]))
        t0 = dt.datetime.fromisoformat(ds[0]["thoi_gian"])
        g = (ds[0]["gio_hd"] or GIO_MAC_DINH)[:5]
        moc = dt.datetime.fromisoformat(f"{ds[0]['ngay_hd']}T{g}:00")
        for d in ds:
            t = moc + (dt.datetime.fromisoformat(d["thoi_gian"]) - t0)
            d["thoi_gian_moi"] = t.isoformat(timespec="seconds")
            d["ngay_moi"] = t.date().isoformat()
    return doi, khong


def gioi_han(doi: list[dict], toi_da: int) -> list[dict]:
    """Chỉ giữ toi_da NHÓM (ngày ảnh, HĐ) mới nhất (theo ngày ảnh rồi giờ ảnh đầu nhóm); 0 = tất cả."""
    if not toi_da:
        return doi
    nhom: dict = {}
    for d in doi:
        k = (d["ngay"], d["code"])
        nhom[k] = min(nhom.get(k, d["thoi_gian"]), d["thoi_gian"])
    giu = set(sorted(nhom, key=lambda k: (k[0], nhom[k], k[1]), reverse=True)[:toi_da])
    return [d for d in doi if (d["ngay"], d["code"]) in giu]


def xuat_tsv(doi, khong, f_doi: str, f_khong: str) -> None:
    with open(f_doi, "w", encoding="utf-8") as f:
        f.write("uuid\tngay_cu\tthoi_gian_cu\tthoi_gian_moi\thd\tngay_hd\ttre\tly_do\n")
        for d in doi:
            f.write("\t".join(str(x) for x in (d["id"], d["ngay"], d["thoi_gian"], d["thoi_gian_moi"], d["code"],
                                               d["ngay_hd"], d["tre"], d["ly_do"])) + "\n")
    with open(f_khong, "w", encoding="utf-8") as f:
        f.write("uuid\tngay\tthoi_gian\thd\tngay_hd\ttre\tly_do\n")
        for d in khong:
            f.write("\t".join(str(x) for x in (d["id"], d["ngay"], d["thoi_gian"], d["code"], d["ngay_hd"], d["tre"],
                                               d["ly_do"])) + "\n")


# ---------------------------- app Ảnh (PhotoKit) ----------------------------
def _ns(t: dt.datetime):
    """datetime (giờ máy) -> NSDate."""
    import Foundation
    return Foundation.NSDate.dateWithTimeIntervalSince1970_(t.timestamp())


class DoiKit:
    """Đặt creationDate cho ảnh app Ảnh qua PhotoKit. P/lib/ns tiêm được để test."""

    def __init__(self, P=None, ns=None):
        if P is None:
            import album_anh
            album_anh._quyen()
            P = album_anh._photos()
        self.P, self.ns = P, ns or _ns
        self.lib = P.PHPhotoLibrary.sharedPhotoLibrary()

    def tim(self, ids: list[str]) -> dict:
        """uuid -> PHAsset (chỉ ảnh thư viện, sourceType 1)."""
        kq = self.P.PHAsset.fetchAssetsWithLocalIdentifiers_options_([f"{u}/L0/001" for u in ids], None)
        ra = {}
        for i in range(kq.count()):
            x = kq.objectAtIndex_(i)
            if getattr(x, "sourceType", lambda: 1)() == 1:
                ra[x.localIdentifier().split("/")[0]] = x
        return ra

    def dat(self, cap: list[tuple]) -> None:
        """cap: [(PHAsset, datetime)] -> đặt creationDate (1 lần performChanges)."""
        P, loi = self.P, []

        def khoi():
            try:
                for x, t in cap:
                    P.PHAssetChangeRequest.changeRequestForAsset_(x).setCreationDate_(self.ns(t))
            except Exception as e:  # noqa: BLE001
                loi.append(e)
        ok, err = self.lib.performChangesAndWait_error_(khoi, None)
        if loi:
            raise RuntimeError(f"PhotoKit: {loi[0]}")
        if not ok:
            raise RuntimeError(f"PhotoKit: {err.localizedDescription() if err is not None else 'không rõ lỗi'}"[:150])


def _ghep_lai(conn, ngays: set[str]) -> None:
    cum = A.cum_khach(conn)
    for n in sorted(ngays):
        A.ghep_ngay(conn, n, cum)
    conn.commit()


def ghi(conn, doi: list[dict], kit) -> tuple[int, int, list]:
    """Đổi ngày: lưu bảng doi_ngay TRƯỚC, đổi trong app Ảnh, cập nhật DB, ghép lại. Trả (đổi, bỏ qua, lệch HĐ)."""
    _bang(conn)
    luc = dt.datetime.now().isoformat(timespec="seconds")
    xong = bo = 0
    ngays = set()
    for k in range(0, len(doi), LO):
        lo = doi[k:k + LO]
        for d in lo:  # lưu ngày cũ TRƯỚC khi đổi
            conn.execute("INSERT OR REPLACE INTO doi_ngay VALUES (?,?,?,?,?,?,?,?)",
                         (d["id"], d["ngay"], d["thoi_gian"], d["ngay_moi"], d["thoi_gian_moi"], d["code"], luc, "cho"))
        conn.commit()
        tim = kit.tim([d["id"] for d in lo])
        cap = [(tim[d["id"]], dt.datetime.fromisoformat(d["thoi_gian_moi"])) for d in lo if d["id"] in tim]
        if cap:
            kit.dat(cap)
        for d in lo:
            if d["id"] in tim:
                conn.execute("UPDATE photos SET ngay=?, thoi_gian=? WHERE id=?", (d["ngay_moi"], d["thoi_gian_moi"], d["id"]))
                conn.execute("UPDATE doi_ngay SET trang_thai='xong' WHERE id=?", (d["id"],))
                ngays |= {d["ngay"], d["ngay_moi"]}
                xong += 1
            else:  # không thấy / ảnh album chia sẻ
                conn.execute("DELETE FROM doi_ngay WHERE id=?", (d["id"],))
                bo += 1
        conn.commit()
    _ghep_lai(conn, ngays)
    lech = []
    for d in doi:
        r = conn.execute("SELECT goi_y_hd, xn_hd, do_tin FROM photos WHERE id=?", (d["id"],)).fetchone()
        if r and (r["xn_hd"] or r["goi_y_hd"]) != d["code"]:
            lech.append((d["id"], d["code"], r["xn_hd"] or r["goi_y_hd"], r["do_tin"]))
    return xong, bo, lech


def go(conn, kit) -> int:
    """Đặt lại ngày giờ CŨ cho mọi ảnh đã đổi (trang_thai 'xong'), cập nhật DB, ghép lại."""
    _bang(conn)
    rows = conn.execute("SELECT * FROM doi_ngay WHERE trang_thai='xong'").fetchall()
    ngays, n = set(), 0
    for k in range(0, len(rows), LO):
        lo = rows[k:k + LO]
        tim = kit.tim([r["id"] for r in lo])
        cap = [(tim[r["id"]], dt.datetime.fromisoformat(r["thoi_gian_cu"])) for r in lo if r["id"] in tim]
        if cap:
            kit.dat(cap)
        for r in lo:
            if r["id"] in tim:
                conn.execute("UPDATE photos SET ngay=?, thoi_gian=? WHERE id=?", (r["ngay_cu"], r["thoi_gian_cu"], r["id"]))
                conn.execute("DELETE FROM doi_ngay WHERE id=?", (r["id"],))
                ngays |= {r["ngay_cu"], r["ngay_moi"]}
                n += 1
        conn.commit()
    _ghep_lai(conn, ngays)
    return n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ghi", action="store_true", help="đổi ngày trong app Ảnh (chạy trong Terminal của Mac Ảnh)")
    ap.add_argument("--go", action="store_true", help="đặt lại ngày cũ cho mọi ảnh đã đổi")
    ap.add_argument("--toi-da", type=int, default=0, metavar="N",
                    help="chỉ N NHÓM (ngày ảnh, HĐ) mới nhất — chạy thử 1 nhóm: --toi-da 1 (0 = tất cả)")
    ap.add_argument("--xuat", default="doi_ngay_khan.tsv", help="file danh sách sẽ đổi (chạy khan)")
    ap.add_argument("--xuat-khong", default="doi_ngay_khong.tsv", help="file danh sách không đổi")
    a = ap.parse_args()
    if a.ghi or a.go:
        conn = A.ket_noi()
    else:
        conn = sqlite3.connect(f"file:{A.DB_FILE}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
    if a.go:
        print(f"Đã đặt lại ngày cũ cho {go(conn, DoiKit())} ảnh.")
        return
    doi, khong = chon(conn)
    tong = len(doi)
    doi = gioi_han(doi, a.toi_da)
    if a.toi_da:
        print(f"--toi-da {a.toi_da}: lấy {len(doi)}/{tong} ảnh của {a.toi_da} nhóm mới nhất")
    dem = collections.Counter(d["ly_do"].split(" —")[0] if "trễ" in d["ly_do"] and "EXIF" not in d["ly_do"]
                              else d["ly_do"].split(" ")[0] for d in khong)
    print(f"Sẽ đổi ngày {len(doi)} ảnh (không EXIF, trễ 1–2 ngày so với HĐ) ở "
          f"{len({(d['ngay'], d['code']) for d in doi})} nhóm; không đổi (chỉ liệt kê) {len(khong)}: {dict(dem)}")
    if not a.ghi:
        xuat_tsv(doi, khong, a.xuat, a.xuat_khong)
        print(f"CHẠY KHAN — danh sách: {a.xuat}, {a.xuat_khong}. Thêm --ghi để đổi (chạy trong Terminal của Mac Ảnh).")
        return
    xong, bo, lech = ghi(conn, doi, DoiKit())
    print(f"Xong: đổi {xong} ảnh, bỏ qua {bo} (không thấy / album chia sẻ). Ghép lại: {len(lech)} ảnh ra HĐ khác:")
    for x in lech[:50]:
        print("  ", x)
    if lech:
        sys.exit(1)


if __name__ == "__main__":
    main()
