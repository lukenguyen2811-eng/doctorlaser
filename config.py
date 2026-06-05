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
CLAUDE_MODEL = _get("CLAUDE_MODEL", "claude-opus-4-8")

# Google Sheet
GOOGLE_SHEET_ID = _get("GOOGLE_SHEET_ID")
GOOGLE_SHEET_GID = _get("GOOGLE_SHEET_GID")
GOOGLE_SERVICE_ACCOUNT_FILE = _get("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json")
SHEET_CACHE_TTL = int(_get("SHEET_CACHE_TTL", "120") or "120")


def check() -> list[str]:
    """Trả về danh sách lỗi cấu hình (rỗng nghĩa là OK)."""
    errors = []
    if not TELEGRAM_BOT_TOKEN:
        errors.append("Thiếu TELEGRAM_BOT_TOKEN")
    if not ANTHROPIC_API_KEY:
        errors.append("Thiếu ANTHROPIC_API_KEY")
    if not GOOGLE_SHEET_ID:
        errors.append("Thiếu GOOGLE_SHEET_ID")
    if not os.path.exists(GOOGLE_SERVICE_ACCOUNT_FILE):
        errors.append(
            f"Không tìm thấy file service account: {GOOGLE_SERVICE_ACCOUNT_FILE}"
        )
    return errors
