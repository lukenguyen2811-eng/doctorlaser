"""Đọc và làm sạch dữ liệu lead từ Google Sheet.

Dùng Google Service Account để đọc sheet (an toàn cho dữ liệu có số điện thoại).
Có cache trong bộ nhớ để tránh gọi Google liên tục.
"""

import json
import re
import time

import gspread
from google.oauth2.service_account import Credentials

import config

# Các cột chuẩn của bảng theo dõi lead (đúng theo tiêu đề trong sheet).
COLUMNS = [
    "ngay",          # NGÀY
    "ho_ten",        # HỌ VÀ TÊN
    "sdt",           # SỐ ĐIỆN THOẠI
    "dich_vu",       # DỊCH VỤ
    "nv_truc_page",  # NV TRỰC PAGE
    "telesale",      # TELESALE PHỤ TRÁCH
    "nguon",         # NGUỒN
    "ghi_chu",       # GHI CHÚ
    "trang_thai",    # TRẠNG THÁI
    "goi_lan_1",     # GỌI LẦN 1
    "goi_lan_2",     # GỌI LẦN 2
]

# Nhãn tiếng Việt để hiển thị / đưa vào prompt cho Claude.
COLUMN_LABELS = {
    "ngay": "NGÀY",
    "ho_ten": "HỌ VÀ TÊN",
    "sdt": "SỐ ĐIỆN THOẠI",
    "dich_vu": "DỊCH VỤ",
    "nv_truc_page": "NV TRỰC PAGE",
    "telesale": "TELESALE PHỤ TRÁCH",
    "nguon": "NGUỒN",
    "ghi_chu": "GHI CHÚ",
    "trang_thai": "TRẠNG THÁI",
    "goi_lan_1": "GỌI LẦN 1",
    "goi_lan_2": "GỌI LẦN 2",
}

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

# Cache: (timestamp, danh sách bản ghi)
_cache: tuple[float, list[dict]] | None = None


def _load_credentials() -> Credentials:
    """Lấy credentials từ biến môi trường (Railway) hoặc từ file (máy cá nhân)."""
    if config.GOOGLE_SERVICE_ACCOUNT_JSON:
        info = json.loads(config.GOOGLE_SERVICE_ACCOUNT_JSON)
        return Credentials.from_service_account_info(info, scopes=_SCOPES)
    return Credentials.from_service_account_file(
        config.GOOGLE_SERVICE_ACCOUNT_FILE, scopes=_SCOPES
    )


def open_spreadsheet(sheet_id: str):
    """Mở cả spreadsheet (để duyệt nhiều tab)."""
    creds = _load_credentials()
    client = gspread.authorize(creds)
    return client.open_by_key(sheet_id)


def open_worksheet(sheet_id: str, gid: str | None = None):
    """Mở 1 worksheet bất kỳ theo sheet_id + gid (dùng chung cho các module khác)."""
    spreadsheet = open_spreadsheet(sheet_id)
    if gid:
        return spreadsheet.get_worksheet_by_id(int(gid))
    return spreadsheet.get_worksheet(0)


def _open_worksheet():
    return open_worksheet(config.GOOGLE_SHEET_ID, config.GOOGLE_SHEET_GID)


def _is_empty_row(values: list[str]) -> bool:
    return not any(v.strip() for v in values)


def _fetch_rows() -> list[dict]:
    """Lấy toàn bộ dòng từ sheet và chuẩn hoá thành list các dict."""
    worksheet = _open_worksheet()
    raw = worksheet.get_all_values()

    records: list[dict] = []
    last_date = ""
    for row in raw[1:]:  # bỏ dòng tiêu đề
        # Đệm cho đủ số cột
        values = (row + [""] * len(COLUMNS))[: len(COLUMNS)]
        values = [v.strip() for v in values]

        if _is_empty_row(values):
            continue

        record = dict(zip(COLUMNS, values))

        # Ô NGÀY: chỉ coi là ngày thật nếu đúng dạng d/m/yyyy. Các giá trị khác
        # (trống, "sau 22h"...) -> kế thừa ngày thực của dòng trước.
        if re.match(r"^\d{1,2}/\d{1,2}/\d{4}", record["ngay"]):
            last_date = record["ngay"]
        else:
            record["ngay"] = last_date

        # Bỏ các dòng rác không có cả tên lẫn trạng thái lẫn dịch vụ.
        if not (record["ho_ten"] or record["trang_thai"] or record["dich_vu"]):
            continue

        records.append(record)

    return records


def get_records(force_refresh: bool = False) -> list[dict]:
    """Trả về dữ liệu lead, dùng cache theo SHEET_CACHE_TTL."""
    global _cache
    now = time.time()
    if (
        not force_refresh
        and _cache is not None
        and (now - _cache[0]) < config.SHEET_CACHE_TTL
    ):
        return _cache[1]

    records = _fetch_rows()
    _cache = (now, records)
    return records


def to_tsv(records: list[dict]) -> str:
    """Chuyển dữ liệu thành bảng TSV gọn để đưa vào prompt cho Claude."""
    header = "\t".join(COLUMN_LABELS[c] for c in COLUMNS)
    lines = [header]
    for r in records:
        lines.append("\t".join(r.get(c, "") for c in COLUMNS))
    return "\n".join(lines)
