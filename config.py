"""Đọc cấu hình từ biến môi trường / file .env."""

import os

from dotenv import load_dotenv

load_dotenv()


def _get(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


# Telegram
TELEGRAM_BOT_TOKEN = _get("TELEGRAM_BOT_TOKEN")
ALLOWED_TELEGRAM_IDS = {
    int(x) for x in _get("ALLOWED_TELEGRAM_IDS").replace(" ", "").split(",") if x
}

# Claude
ANTHROPIC_API_KEY = _get("ANTHROPIC_API_KEY")
CLAUDE_MODEL = _get("CLAUDE_MODEL", "claude-haiku-4-5")

# Google Sheet
GOOGLE_SHEET_ID = _get("GOOGLE_SHEET_ID")
GOOGLE_SHEET_GID = _get("GOOGLE_SHEET_GID")
# Cách 1 (Railway/cloud): dán toàn bộ nội dung JSON vào biến môi trường này.
GOOGLE_SERVICE_ACCOUNT_JSON = _get("GOOGLE_SERVICE_ACCOUNT_JSON")
# Cách 2 (chạy máy cá nhân): đường dẫn tới file JSON.
GOOGLE_SERVICE_ACCOUNT_FILE = _get("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json")
SHEET_CACHE_TTL = int(_get("SHEET_CACHE_TTL", "120") or "120")

# KiotViet (tùy chọn) - dữ liệu hóa đơn & khách hàng
KIOTVIET_CLIENT_ID = _get("KIOTVIET_CLIENT_ID")
KIOTVIET_CLIENT_SECRET = _get("KIOTVIET_CLIENT_SECRET")
KIOTVIET_RETAILER = _get("KIOTVIET_RETAILER")
# Số ngày hóa đơn lấy về (KiotViet có thể rất nhiều dữ liệu). Mặc định 30 ngày.
KIOTVIET_INVOICE_DAYS = int(_get("KIOTVIET_INVOICE_DAYS", "30") or "30")
KIOTVIET_CACHE_TTL = int(_get("KIOTVIET_CACHE_TTL", "300") or "300")
# Base URL API: bán lẻ = public.kiotapi.com ; F&B = publicfnb.kiotapi.com
KIOTVIET_BASE_URL = _get("KIOTVIET_BASE_URL", "https://public.kiotapi.com")


def kiotviet_enabled() -> bool:
    return bool(
        KIOTVIET_CLIENT_ID and KIOTVIET_CLIENT_SECRET and KIOTVIET_RETAILER
    )


# Sheet doanh thu/ads theo dịch vụ (bảng giao dịch + ROAS theo dịch vụ)
ADS_SERVICE_SHEET_ID = _get(
    "ADS_SERVICE_SHEET_ID", "1OD5UXzOQ1ukZ0LQlcZZ806QdC_FZrlDbbWR1sdTer3g"
)
ADS_SERVICE_GID = _get("ADS_SERVICE_GID", "1272703772")

# Model dùng cho phân tích chiến lược (/chienluoc) - mạnh hơn model trả lời thường.
STRATEGY_MODEL = _get("STRATEGY_MODEL", "claude-sonnet-4-6")

# Sheet chi phí ads theo THÁNG (mỗi tab là 1 tháng, có Facebook/Tiktok/Youtube).
ADS_MONTHLY_SHEET_ID = _get(
    "ADS_MONTHLY_SHEET_ID", "18pxTeTp8jGUkztD-CaHh6zmgBkvGCzNyxl979Au29L0"
)


def strategy_enabled() -> bool:
    return bool(ADS_SERVICE_SHEET_ID)


def adspend_enabled() -> bool:
    return bool(ADS_MONTHLY_SHEET_ID)


# Báo cáo tự động hằng ngày
TIMEZONE = _get("TIMEZONE", "Asia/Ho_Chi_Minh")
DAILY_REPORT_HOUR = int(_get("DAILY_REPORT_HOUR", "8") or "8")
# Chat ID nơi gửi báo cáo tự động. Lấy bằng cách gõ /chatid trong nhóm.
DAILY_REPORT_CHAT_ID = _get("DAILY_REPORT_CHAT_ID")

# Sheet nhân viên điền chi phí ads & doanh thu theo nguồn/kênh.
CHANNEL_SHEET_ID = _get("CHANNEL_SHEET_ID", "18DCX4in2XkgIlcnmxxqYhMvb2GoWMCqMdnquTtFwgZ0")
CHANNEL_GID = _get("CHANNEL_GID", "")


def channel_enabled() -> bool:
    return bool(CHANNEL_SHEET_ID)


def check() -> list[str]:
    """Trả về danh sách lỗi cấu hình (rỗng nghĩa là OK)."""
    errors = []
    if not TELEGRAM_BOT_TOKEN:
        errors.append("Thiếu TELEGRAM_BOT_TOKEN")
    if not ANTHROPIC_API_KEY:
        errors.append("Thiếu ANTHROPIC_API_KEY")
    if not GOOGLE_SHEET_ID:
        errors.append("Thiếu GOOGLE_SHEET_ID")
    # Cần MỘT trong hai: nội dung JSON qua biến môi trường, hoặc file JSON.
    if not GOOGLE_SERVICE_ACCOUNT_JSON and not os.path.exists(
        GOOGLE_SERVICE_ACCOUNT_FILE
    ):
        errors.append(
            "Thiếu thông tin Google Service Account: đặt GOOGLE_SERVICE_ACCOUNT_JSON "
            f"(nội dung JSON) hoặc để file {GOOGLE_SERVICE_ACCOUNT_FILE}"
        )
    return errors
