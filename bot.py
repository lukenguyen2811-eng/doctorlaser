"""Bot Telegram phân tích dữ liệu Google Sheet của Doctor Laser.

Người dùng nhắn câu hỏi bằng tiếng Việt, bot đọc Google Sheet, tính số liệu
và dùng Claude để trả lời.

Chạy:  python bot.py
"""

import asyncio
import logging

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import analytics
import config
import llm
import sheets

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO
)
log = logging.getLogger("doctorlaser-bot")

# Số cặp hỏi-đáp tối đa giữ lại cho mỗi cuộc trò chuyện.
MAX_HISTORY_TURNS = 6
TELEGRAM_LIMIT = 4096

WELCOME = (
    "Xin chào! Tôi là bot phân tích dữ liệu khách hàng của Doctor Laser.\n\n"
    "Bạn cứ hỏi tự nhiên bằng tiếng Việt, ví dụ:\n"
    "• Hôm nay có bao nhiêu lead?\n"
    "• Nguồn nào ra nhiều khách nhất?\n"
    "• Tỉ lệ khách ĐÃ ĐẾN trên tổng lead là bao nhiêu?\n"
    "• Telesale nào đang phụ trách nhiều khách nhất?\n"
    "• Dịch vụ nào được quan tâm nhất tuần này?\n\n"
    "Lệnh:\n"
    "/stats - xem nhanh số liệu tổng hợp\n"
    "/refresh - tải lại dữ liệu mới nhất từ Google Sheet\n"
    "/help - hướng dẫn"
)


def _allowed(update: Update) -> bool:
    if not config.ALLOWED_TELEGRAM_IDS:
        return True
    user = update.effective_user
    return bool(user and user.id in config.ALLOWED_TELEGRAM_IDS)


async def _reply_long(update: Update, text: str) -> None:
    """Gửi tin nhắn, tự chia nhỏ nếu vượt giới hạn của Telegram."""
    if not text:
        text = "(không có nội dung)"
    for i in range(0, len(text), TELEGRAM_LIMIT):
        await update.message.reply_text(text[i : i + TELEGRAM_LIMIT])


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        await update.message.reply_text("Xin lỗi, bạn không có quyền dùng bot này.")
        return
    await update.message.reply_text(WELCOME)


async def cmd_refresh(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return
    try:
        records = await asyncio.to_thread(sheets.get_records, True)
        await update.message.reply_text(
            f"Đã tải lại dữ liệu: {len(records)} lead."
        )
    except Exception as e:  # noqa: BLE001
        log.exception("refresh failed")
        await update.message.reply_text(f"Lỗi khi tải dữ liệu: {e}")


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return
    try:
        records = await asyncio.to_thread(sheets.get_records)
        summary = analytics.build_summary(records)
        await _reply_long(update, summary)
    except Exception as e:  # noqa: BLE001
        log.exception("stats failed")
        await update.message.reply_text(f"Lỗi: {e}")


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        await update.message.reply_text("Xin lỗi, bạn không có quyền dùng bot này.")
        return

    question = (update.message.text or "").strip()
    if not question:
        return

    await update.message.chat.send_action(ChatAction.TYPING)

    try:
        records = await asyncio.to_thread(sheets.get_records)
        if not records:
            await update.message.reply_text(
                "Chưa đọc được dữ liệu nào từ Google Sheet."
            )
            return

        data_tsv = sheets.to_tsv(records)
        summary = analytics.build_summary(records)

        # Lịch sử hội thoại lưu theo từng chat.
        history: list[dict] = context.chat_data.get("history", [])
        history.append({"role": "user", "content": question})

        reply = await asyncio.to_thread(llm.answer, history, data_tsv, summary)

        history.append({"role": "assistant", "content": reply})
        # Giữ lịch sử trong giới hạn.
        context.chat_data["history"] = history[-MAX_HISTORY_TURNS * 2 :]

        await _reply_long(update, reply)
    except Exception as e:  # noqa: BLE001
        log.exception("answer failed")
        await update.message.reply_text(f"Có lỗi xảy ra: {e}")


def main() -> None:
    errors = config.check()
    if errors:
        raise SystemExit("Cấu hình chưa đúng:\n - " + "\n - ".join(errors))

    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("refresh", cmd_refresh))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))

    log.info("Bot đang chạy. Nhấn Ctrl+C để dừng.")
    app.run_polling()


if __name__ == "__main__":
    main()
