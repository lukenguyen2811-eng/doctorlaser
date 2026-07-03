"""Đồng bộ dữ liệu nguồn về MÁY CỦA BẠN (SQLite + CSV) — chạy trên máy Mac.

Kéo dữ liệu từ KiotViet, Meta (Facebook ads), Google Sheet (lead) về 1 file
database ngay trên máy bạn -> bạn tự kiểm soát, tích lũy lịch sử.

Chạy:  python local_sync.py           (đồng bộ 6 tháng gần nhất)
       python local_sync.py 12        (đồng bộ 12 tháng gần nhất)

KHÔNG cần Telegram/Anthropic. Chỉ cần credentials các nguồn trong .env.
"""

import csv
import datetime as dt
import os
import sqlite3
import sys

import config

DB_FILE = os.environ.get("LOCAL_DB", "doctorlaser.db")
EXPORT_DIR = os.environ.get("LOCAL_EXPORT_DIR", "export")


def _last_months(n: int) -> list[tuple[int, int]]:
    today = dt.date.today()
    y, m = today.year, today.month
    out = []
    for _ in range(n):
        out.append((y, m))
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    return out


def _export_csv(conn: sqlite3.Connection, table: str) -> None:
    os.makedirs(EXPORT_DIR, exist_ok=True)
    cur = conn.execute(f"SELECT * FROM {table}")
    cols = [d[0] for d in cur.description]
    path = os.path.join(EXPORT_DIR, f"{table}.csv")
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(cols)
        w.writerows(cur.fetchall())
    print(f"  -> xuất {path}")


# ----------------- LEAD (Google Sheet) -----------------
def sync_leads(conn: sqlite3.Connection) -> int:
    import sheets

    records = sheets.get_records(force_refresh=True)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS leads ("
        + ", ".join(f"{c} TEXT" for c in sheets.COLUMNS)
        + ")"
    )
    conn.execute("DELETE FROM leads")  # snapshot toàn bộ (lead không có ID ổn định)
    conn.executemany(
        f"INSERT INTO leads VALUES ({','.join('?' * len(sheets.COLUMNS))})",
        [tuple(r.get(c, "") for c in sheets.COLUMNS) for r in records],
    )
    conn.commit()
    return len(records)


# ----------------- HÓA ĐƠN (KiotViet) -----------------
def sync_invoices(conn: sqlite3.Connection, months: list[tuple[int, int]]) -> int:
    import kiotviet

    conn.execute(
        "CREATE TABLE IF NOT EXISTS invoices ("
        "code TEXT PRIMARY KEY, purchaseDate TEXT, thang TEXT, "
        "doanh_thu_truoc_vat REAL, tong_co_vat REAL, "
        "customerName TEXT, customerCode TEXT, branchName TEXT, statusValue TEXT)"
    )
    total = 0
    for y, m in months:
        try:
            invs = kiotviet.get_invoices_for_month(y, m, force=True)
        except Exception as e:  # noqa: BLE001
            print(f"  ! hóa đơn {m}/{y} lỗi: {e}")
            continue
        for i in invs:
            conn.execute(
                "INSERT OR REPLACE INTO invoices VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    str(i.get("code") or i.get("id")),
                    (i.get("purchaseDate") or "")[:19],
                    f"{y}-{m:02d}",
                    kiotviet.invoice_revenue(i),
                    float(i.get("total") or 0),
                    i.get("customerName") or "",
                    i.get("customerCode") or "",
                    i.get("branchName") or "",
                    i.get("statusValue") or "",
                ),
            )
        total += len(invs)
        print(f"  hóa đơn {m}/{y}: {len(invs)}")
    conn.commit()
    return total


# ----------------- ADS (Meta / Facebook) -----------------
def sync_ads(conn: sqlite3.Connection, months: list[tuple[int, int]]) -> int:
    import calendar

    import meta

    conn.execute(
        "CREATE TABLE IF NOT EXISTS ads ("
        "thang TEXT, campaign TEXT, chi_phi REAL, hien_thi REAL, click REAL, "
        "ket_qua INTEGER, cpl REAL, PRIMARY KEY (thang, campaign))"
    )
    total = 0
    for y, m in months:
        since = f"{y}-{m:02d}-01"
        until = f"{y}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}"
        try:
            rows = meta.get_insights(since, until, force=True)
        except Exception as e:  # noqa: BLE001
            print(f"  ! ads {m}/{y} lỗi: {e}")
            continue
        for r in rows:
            spend = float(r.get("spend") or 0)
            res = meta._results(r)
            conn.execute(
                "INSERT OR REPLACE INTO ads VALUES (?,?,?,?,?,?,?)",
                (
                    f"{y}-{m:02d}",
                    r.get("campaign_name") or "(không tên)",
                    spend,
                    float(r.get("impressions") or 0),
                    float(r.get("clicks") or 0),
                    res,
                    (spend / res) if res else 0,
                ),
            )
        total += len(rows)
        print(f"  ads {m}/{y}: {len(rows)} campaign")
    conn.commit()
    return total


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    months = _last_months(n)
    conn = sqlite3.connect(DB_FILE)
    print(f"== Đồng bộ {n} tháng gần nhất vào {DB_FILE} ==")

    print("LEAD (Google Sheet):")
    try:
        print(f"  tổng {sync_leads(conn)} lead")
        _export_csv(conn, "leads")
    except Exception as e:  # noqa: BLE001
        print(f"  ! lỗi lead: {e}")

    if config.kiotviet_enabled():
        print("HÓA ĐƠN (KiotViet):")
        sync_invoices(conn, months)
        _export_csv(conn, "invoices")
    else:
        print("HÓA ĐƠN: (chưa cấu hình KiotViet, bỏ qua)")

    if config.meta_enabled():
        print("ADS (Facebook/Meta):")
        sync_ads(conn, months)
        _export_csv(conn, "ads")
    else:
        print("ADS: (chưa cấu hình Meta, bỏ qua)")

    conn.close()
    print(f"\nXong. Dữ liệu ở: {os.path.abspath(DB_FILE)}")
    print(f"File CSV mở bằng Excel/Numbers ở thư mục: {os.path.abspath(EXPORT_DIR)}")


if __name__ == "__main__":
    main()
