"""Kết nối KiotViet Public API để lấy hóa đơn & khách hàng.

Cơ chế: OAuth2 client_credentials -> access token (1 giờ) -> gọi API kèm
header Retailer + Bearer. Tài liệu: KiotViet Public API v1.2.
"""

import calendar
import time
from datetime import datetime, timedelta

import requests

import config

_TOKEN_URL = "https://id.kiotviet.vn/connect/token"
_PAGE_SIZE = 100  # tối đa của KiotViet

# Một số WAF của KiotViet chặn request không có User-Agent giống trình duyệt.
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Cache token và dữ liệu trong bộ nhớ.
_token = {"value": None, "expires_at": 0.0}
_data_cache: dict[str, tuple[float, object]] = {}


def _get_token() -> str:
    now = time.time()
    if _token["value"] and now < _token["expires_at"] - 60:
        return _token["value"]

    resp = requests.post(
        _TOKEN_URL,
        data={
            "scopes": "PublicApi.Access",
            "grant_type": "client_credentials",
            "client_id": config.KIOTVIET_CLIENT_ID,
            "client_secret": config.KIOTVIET_CLIENT_SECRET,
        },
        headers={"User-Agent": _UA},
        timeout=30,
    )
    if resp.status_code != 200:
        # KiotViet trả lý do cụ thể trong body (invalid_client / invalid_scope...).
        raise RuntimeError(
            f"Xin token KiotViet thất bại ({resp.status_code}): {resp.text[:300]}"
        )
    body = resp.json()
    _token["value"] = body["access_token"]
    _token["expires_at"] = now + int(body.get("expires_in", 3600))
    return _token["value"]


def _headers() -> dict:
    return {
        "Retailer": config.KIOTVIET_RETAILER,
        "Authorization": f"Bearer {_get_token()}",
        "User-Agent": _UA,
        "Accept": "application/json",
    }


def _api_get(path: str, params: dict, attempts: int = 4) -> dict:
    """GET một endpoint KiotViet, tự thử lại khi gặp lỗi 5xx (server tạm trục trặc)."""
    last = None
    for i in range(attempts):
        resp = requests.get(
            f"{config.KIOTVIET_BASE_URL}{path}",
            headers=_headers(),
            params=params,
            timeout=60,
        )
        if resp.status_code == 200:
            return resp.json()
        last = resp
        if resp.status_code >= 500:
            time.sleep(2 * (i + 1))  # 2s, 4s, 6s...
            continue
        break  # lỗi 4xx -> không thử lại
    raise RuntimeError(
        f"KiotViet trả lỗi ({last.status_code}) tại {path}: {last.text[:300]}"
    )


def _get_all(path: str, params: dict, max_items: int = 5000) -> list[dict]:
    """Gọi 1 endpoint và gom toàn bộ trang (có phân trang)."""
    items: list[dict] = []
    current = 0
    while True:
        page_params = dict(params)
        page_params["pageSize"] = _PAGE_SIZE
        page_params["currentItem"] = current
        body = _api_get(path, page_params)
        data = body.get("data") or []
        items.extend(data)
        total = body.get("total", 0)
        current += _PAGE_SIZE
        if not data or current >= total or len(items) >= max_items:
            break
    return items


def _cached(key: str, ttl: int, loader):
    now = time.time()
    hit = _data_cache.get(key)
    if hit and (now - hit[0]) < ttl:
        return hit[1]
    value = loader()
    _data_cache[key] = (now, value)
    return value


def invoice_revenue(inv: dict) -> float:
    """Doanh thu 1 hóa đơn = TỔNG TIỀN HÀNG (trước VAT).

    Cộng 'subTotal' của chi tiết hóa đơn (giống cột 'Tổng tiền hàng' của KiotViet).
    Nếu không có chi tiết -> dùng 'total' (đã gồm VAT) làm phương án dự phòng.
    """
    details = inv.get("invoiceDetails") or []
    if details:
        return sum(float(d.get("subTotal") or 0) for d in details)
    return float(inv.get("total") or 0)


def total_revenue(invoices: list[dict]) -> float:
    return sum(invoice_revenue(i) for i in invoices)


def _counts_as_revenue(inv: dict) -> bool:
    """Tính vào doanh thu nếu KHÔNG phải hóa đơn hủy (giống KiotViet)."""
    sv = (inv.get("statusValue") or "").strip().lower()
    if "hủy" in sv or "huỷ" in sv:
        return False
    if inv.get("status") == 2:  # 2 = Đã hủy
        return False
    return True


def _fetch_invoices(from_date: str, to_date: str | None = None) -> list[dict]:
    params = {
        "fromPurchaseDate": from_date,
        "orderBy": "purchaseDate",
        "orderDirection": "Desc",
        "includePayment": "true",
        "includeInvoiceDelivery": "false",
    }
    if to_date:
        params["toPurchaseDate"] = to_date
    invoices = _get_all("/invoices", params)
    # Chỉ giữ hóa đơn hoàn thành để doanh thu khớp KiotViet.
    return [i for i in invoices if _counts_as_revenue(i)]


def _fetch_invoices_from(from_date: str) -> list[dict]:
    return _fetch_invoices(from_date)


def get_invoices_for_date(d, force: bool = False) -> list[dict]:
    """Lấy hóa đơn của đúng 1 ngày (d là datetime.date)."""
    from_date = f"{d:%Y-%m-%d} 00:00:00"
    to_date = f"{d:%Y-%m-%d} 23:59:59"
    key = f"invoices_day:{d.isoformat()}"
    if force:
        _data_cache.pop(key, None)
    return _cached(
        key, config.KIOTVIET_CACHE_TTL, lambda: _fetch_invoices(from_date, to_date)
    )


def get_invoices(days: int | None = None, force: bool = False) -> list[dict]:
    """Lấy hóa đơn trong N ngày gần nhất."""
    days = days or config.KIOTVIET_INVOICE_DAYS
    now = datetime.now()
    from_date = (now - timedelta(days=days)).strftime("%Y-%m-%d 00:00:00")
    to_date = now.strftime("%Y-%m-%d 23:59:59")
    key = f"invoices:{days}"
    if force:
        _data_cache.pop(key, None)
    return _cached(
        key, config.KIOTVIET_CACHE_TTL, lambda: _fetch_invoices(from_date, to_date)
    )


def get_current_month_invoices(force: bool = False) -> list[dict]:
    """Lấy hóa đơn của THÁNG HIỆN TẠI (từ ngày 1 đến hôm nay).

    Bắt buộc có cả ngày bắt đầu VÀ kết thúc, nếu không KiotViet trả về toàn bộ.
    """
    now = datetime.now()
    from_date = now.replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    ).strftime("%Y-%m-%d 00:00:00")
    to_date = now.strftime("%Y-%m-%d 23:59:59")
    key = f"invoices_month:{now.year}-{now.month:02d}"
    if force:
        _data_cache.pop(key, None)
    return _cached(
        key, config.KIOTVIET_CACHE_TTL, lambda: _fetch_invoices(from_date, to_date)
    )


def get_invoices_for_month(year: int, month: int, force: bool = False) -> list[dict]:
    """Lấy hóa đơn của một THÁNG bất kỳ (cả tháng)."""
    last_day = calendar.monthrange(year, month)[1]
    from_date = f"{year:04d}-{month:02d}-01 00:00:00"
    to_date = f"{year:04d}-{month:02d}-{last_day:02d} 23:59:59"
    key = f"invoices_m:{year}-{month:02d}"
    if force:
        _data_cache.pop(key, None)
    return _cached(
        key, config.KIOTVIET_CACHE_TTL, lambda: _fetch_invoices(from_date, to_date)
    )


def get_customer_total() -> int:
    """Đếm tổng số khách hàng (gọi nhẹ, chỉ đọc trường total)."""

    def loader():
        body = _api_get("/customers", {"pageSize": 1, "currentItem": 0})
        return body.get("total", 0)

    return _cached("customer_total", config.KIOTVIET_CACHE_TTL, loader)
