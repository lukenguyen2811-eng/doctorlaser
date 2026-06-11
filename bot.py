"""Bot Telegram phân tích dữ liệu Google Sheet của Doctor Laser.

Người dùng nhắn câu hỏi bằng tiếng Việt, bot đọc Google Sheet, tính số liệu
và dùng Claude để trả lời.

Chạy:  python bot.py
"""

import asyncio
import logging
import re

import anthropic
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import adspend
import analytics
import config
import kiotviet
import llm
import sales
import sheets
import strategy

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO
)
log = logging.getLogger("doctorlaser-bot")

# Số cặp hỏi-đáp tối đa giữ lại cho mỗi cuộc trò chuyện.
MAX_HISTORY_TURNS = 6
TELEGRAM_LIMIT = 4096

# Câu hỏi chứa các từ này thường cần dữ liệu chi tiết từng khách (gửi cả bảng TSV).
# Mặc định chỉ gửi số liệu tổng hợp để tiết kiệm chi phí.
DETAIL_KEYWORDS = (
    "liệt kê", "danh sách", "tìm", "tên", "số điện thoại", "sđt", "sdt",
    "khách nào", "ai ", "ghi chú", "liên hệ", "gọi cho", "chi tiết",
)


def _needs_detail(question: str) -> bool:
    q = question.lower()
    return any(kw in q for kw in DETAIL_KEYWORDS)


# Câu hỏi liên quan bán hàng/doanh thu -> kèm dữ liệu KiotViet.
SALES_KEYWORDS = (
    "doanh thu", "doanh số", "hóa đơn", "hoá đơn", "bill", "bán", "mua",
    "chi tiêu", "khách mua", "sản phẩm", "dịch vụ bán", "đơn hàng",
    "revenue", "tiền", "thu", "chốt đơn", "kiotviet", "kiot",
)


def _is_sales_question(question: str) -> bool:
    q = question.lower()
    return any(kw in q for kw in SALES_KEYWORDS)


# Câu hỏi về hiệu quả ads/dịch vụ/nhân viên -> kèm dữ liệu ROAS theo dịch vụ.
STRATEGY_KEYWORDS = (
    "roas", "ads", "quảng cáo", "chi phí", "dịch vụ", "nhân viên", "saler",
    "sale", "hiệu quả", "kênh", "nguồn nào", "lời", "lãi", "ngân sách",
    "quý", "tăng trưởng", "phát triển", "xu hướng", "so sánh",
)


def _is_strategy_question(question: str) -> bool:
    q = question.lower()
    return any(kw in q for kw in STRATEGY_KEYWORDS)


WELCOME = (
    "Xin chào! Tôi là bot phân tích dữ liệu của Doctor Laser.\n\n"
    "Tôi nắm 2 nguồn dữ liệu:\n"
    "• LEAD (telesale) từ Google Sheet\n"
    "• BÁN HÀNG (hóa đơn, doanh thu, khách hàng) từ KiotViet\n\n"
    "Bạn cứ hỏi tự nhiên bằng tiếng Việt, ví dụ:\n"
    "• Hôm nay có bao nhiêu lead? Nguồn nào hiệu quả nhất?\n"
    "• Doanh thu hôm nay/tuần này bao nhiêu?\n"
    "• Sản phẩm/dịch vụ nào bán chạy nhất?\n"
    "• Top khách hàng chi tiêu nhiều nhất?\n\n"
    "Lệnh:\n"
    "/stats - số liệu lead tổng hợp\n"
    "/doanhthu - số liệu bán hàng (KiotViet)\n"
    "/chienluoc - phân tích chiến lược (hỏi khoảng tháng, kế hoạch theo tuần & tháng)\n"
    "/refresh - tải lại dữ liệu mới nhất\n"
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


def _is_group(update: Update) -> bool:
    chat = update.effective_chat
    return bool(chat and chat.type in ("group", "supergroup"))


def _addressed_in_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> tuple[bool, str]:
    """Trong nhóm: chỉ coi là gọi bot khi @nhắc tên hoặc reply vào tin của bot.

    Trả về (có_gọi_bot, câu_hỏi_đã_bỏ_phần_@nhắc).
    """
    message = update.message
    text = (message.text or "").strip()

    # Reply vào một tin nhắn của chính bot.
    reply = message.reply_to_message
    if reply and reply.from_user and reply.from_user.id == context.bot.id:
        return True, text

    # Có @nhắc tên bot.
    username = context.bot.username
    if username and f"@{username}".lower() in text.lower():
        cleaned = text.replace(f"@{username}", "").replace(f"@{username}".lower(), "")
        return True, cleaned.strip()

    return False, text


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        if not _is_group(update):
            await update.message.reply_text("Xin lỗi, bạn không có quyền dùng bot này.")
        return
    await update.message.reply_text(WELCOME)


async def cmd_refresh(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return
    try:
        records = await asyncio.to_thread(sheets.get_records, True)
        msg = f"Đã tải lại dữ liệu: {len(records)} lead."
        if config.kiotviet_enabled():
            invoices = await asyncio.to_thread(kiotviet.get_invoices, None, True)
            msg += f"\nKiotViet: {len(invoices)} hóa đơn ({config.KIOTVIET_INVOICE_DAYS} ngày gần nhất)."
        await update.message.reply_text(msg)
    except Exception as e:  # noqa: BLE001
        log.exception("refresh failed")
        await update.message.reply_text(f"Lỗi khi tải dữ liệu: {e}")


async def cmd_doanhthu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return
    if not config.kiotviet_enabled():
        await update.message.reply_text(
            "Chưa kết nối KiotViet. Cần đặt KIOTVIET_CLIENT_ID, "
            "KIOTVIET_CLIENT_SECRET, KIOTVIET_RETAILER trong cấu hình."
        )
        return
    status = await update.message.reply_text("⏳ Đang lấy doanh thu tháng này...")
    try:
        import datetime as _dt

        label = f"tháng {_dt.date.today().month}"
        invoices = await asyncio.to_thread(kiotviet.get_current_month_invoices)
        customer_total = await asyncio.to_thread(kiotviet.get_customer_total)
        summary = sales.build_summary(invoices, customer_total, label)
        await status.edit_text(summary[:TELEGRAM_LIMIT])
    except Exception as e:  # noqa: BLE001
        log.exception("doanhthu failed")
        await status.edit_text(f"Lỗi khi lấy dữ liệu KiotViet: {e}")


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


def _parse_month_range(text: str) -> tuple[int, int] | None:
    """Tách khoảng tháng từ câu trả lời, vd '4-6', '5', 'tháng 4 đến 6'."""
    nums = [int(x) for x in re.findall(r"\d+", text) if 1 <= int(x) <= 12]
    if not nums:
        return None
    return (min(nums), max(nums))


async def cmd_chienluoc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return
    # Cho phép truyền sẵn khoảng tháng: /chienluoc 4-6
    rng = _parse_month_range(" ".join(context.args)) if context.args else None
    if rng:
        await _run_strategy(update, context, rng)
        return
    # Hỏi khoảng tháng, chờ câu trả lời tiếp theo của chính người này.
    context.chat_data["awaiting_range"] = update.effective_user.id if update.effective_user else 0
    await update.message.reply_text(
        "Bạn muốn phân tích chiến lược từ THÁNG mấy tới THÁNG mấy?\n"
        "Trả lời ví dụ:\n"
        "• 4-6  (từ tháng 4 đến tháng 6)\n"
        "• 5    (chỉ tháng 5)"
    )


async def _run_strategy(
    update: Update, context: ContextTypes.DEFAULT_TYPE, rng: tuple[int, int]
) -> None:
    from_m, to_m = rng
    status = await update.message.reply_text(
        f"⏳ Đang phân tích chiến lược tháng {from_m}–{to_m} (theo tuần & tháng)... "
        "(~30-60 giây)"
    )
    try:
        parts: list[str] = []

        data = None
        if config.strategy_enabled():
            data = await asyncio.to_thread(strategy.get_data)
            parts.append(
                f"# DOANH THU THEO THỜI GIAN (tháng {from_m}–{to_m})\n"
                + strategy.build_time_summary(data, from_m, to_m)
            )

        # Chi phí ads theo tháng -> ROAS theo tháng (sheet ads tháng).
        if config.adspend_enabled() and data is not None:
            try:
                wanted = set(range(from_m, to_m + 1))
                spend = await asyncio.to_thread(adspend.get_data, wanted)
                rev_m = strategy.revenue_by_month(data, from_m, to_m)
                parts.append(
                    "# CHI PHÍ ADS & ROAS THEO THÁNG\n"
                    + adspend.build_roas(spend, rev_m, from_m, to_m)
                )
            except Exception as e:  # noqa: BLE001
                log.warning("adspend failed: %s", e)
                parts.append(
                    "# CHI PHÍ ADS THEO THÁNG\n(Chưa đọc được sheet chi phí ads "
                    f"tháng — kiểm tra đã share cho service account chưa. Lỗi: {e})"
                )

        records = await asyncio.to_thread(sheets.get_records)
        if records:
            parts.append(
                "# DỮ LIỆU LEAD (tổng thể, tham khảo về tỉ lệ chốt/nguồn)\n"
                + analytics.build_summary(records)
            )

        if not parts:
            await status.edit_text("Chưa có dữ liệu để phân tích.")
            return

        reply = await asyncio.to_thread(llm.strategy, "\n\n".join(parts))
        if not reply:
            await status.edit_text(
                "Mình chưa tạo được nội dung (có thể do giới hạn token). Thử lại sau ít phút nhé."
            )
            return
        await status.delete()
        await _reply_long(update, reply)
    except anthropic.RateLimitError:
        await status.edit_text(
            "⚠️ Bị giới hạn tốc độ. Thử lại sau ~1 phút (phân tích chiến lược "
            "tốn nhiều token hơn)."
        )
    except Exception as e:  # noqa: BLE001
        log.exception("chienluoc failed")
        await status.edit_text(f"Có lỗi xảy ra: {e}")


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Đang chờ người này nhập khoảng tháng cho /chienluoc?
    pending = context.chat_data.get("awaiting_range")
    uid = update.effective_user.id if update.effective_user else None
    if pending is not None and uid == pending:
        context.chat_data.pop("awaiting_range", None)
        rng = _parse_month_range(update.message.text or "")
        if not rng:
            await update.message.reply_text(
                "Mình chưa hiểu khoảng tháng. Gõ lại /chienluoc rồi nhập ví dụ: 4-6"
            )
            return
        await _run_strategy(update, context, rng)
        return

    # Trong nhóm: chỉ phản hồi khi được @nhắc tên hoặc reply vào tin của bot,
    # để bot không trả lời mọi tin nhắn trong nhóm.
    if _is_group(update):
        addressed, question = _addressed_in_group(update, context)
        if not addressed:
            return
    else:
        question = (update.message.text or "").strip()

    if not _allowed(update):
        if not _is_group(update):
            await update.message.reply_text("Xin lỗi, bạn không có quyền dùng bot này.")
        return

    question = question.strip()
    if not question:
        return

    await update.message.chat.send_action(ChatAction.TYPING)
    # Báo ngay là đã nhận câu hỏi (câu đầu tiên có thể mất vài chục giây).
    status = await update.message.reply_text("⏳ Đang phân tích dữ liệu...")

    try:
        parts: list[str] = []

        # --- Dữ liệu LEAD (Google Sheet) ---
        records = await asyncio.to_thread(sheets.get_records)
        if records:
            parts.append(
                "# DỮ LIỆU LEAD (telesale)\n"
                + "## SỐ LIỆU TỔNG HỢP (đã tính sẵn, chính xác)\n"
                + analytics.build_summary(records)
            )
            # Chỉ gửi dữ liệu chi tiết khi câu hỏi thực sự cần (tiết kiệm token).
            if _needs_detail(question):
                parts.append("## LEAD CHI TIẾT (bảng TSV)\n" + sheets.to_tsv(records))

        # --- Doanh thu & ROAS theo dịch vụ — khi câu hỏi liên quan ads/dịch vụ ---
        if config.strategy_enabled() and _is_strategy_question(question):
            data = await asyncio.to_thread(strategy.get_data)
            parts.append(
                "# DOANH THU & ROAS THEO DỊCH VỤ/KÊNH/NHÂN VIÊN\n"
                + strategy.build_summary(data)
            )

        # --- Doanh thu (KiotViet) — mặc định lấy THÁNG NÀY khi hỏi doanh thu ---
        if config.kiotviet_enabled() and _is_sales_question(question):
            import datetime as _dt

            label = f"tháng {_dt.date.today().month}"
            invoices = await asyncio.to_thread(kiotviet.get_current_month_invoices)
            customer_total = await asyncio.to_thread(kiotviet.get_customer_total)
            parts.append(
                f"# DOANH THU (KiotViet, {label})\n"
                + sales.build_summary(invoices, customer_total, label)
            )

        if not parts:
            await status.edit_text("Chưa đọc được dữ liệu nào.")
            return

        context_text = "\n\n".join(parts)

        # Lịch sử hội thoại lưu theo từng chat.
        history: list[dict] = context.chat_data.get("history", [])
        history.append({"role": "user", "content": question})

        reply = await asyncio.to_thread(llm.answer, history, context_text)

        history.append({"role": "assistant", "content": reply})
        # Giữ lịch sử trong giới hạn.
        context.chat_data["history"] = history[-MAX_HISTORY_TURNS * 2 :]

        if not reply:
            await status.edit_text(
                "Mình chưa tạo được câu trả lời. Bạn thử hỏi lại nhé."
            )
            return
        # Ngắn -> sửa tin "Đang phân tích"; dài -> xoá rồi gửi nhiều phần.
        if len(reply) <= TELEGRAM_LIMIT:
            await status.edit_text(reply)
        else:
            await status.delete()
            await _reply_long(update, reply)
    except anthropic.RateLimitError:
        log.warning("rate limited")
        await status.edit_text(
            "⚠️ Bot đang bị giới hạn tốc độ (gửi quá nhiều yêu cầu/dữ liệu lớn "
            "trong 1 phút). Bạn thử lại sau khoảng 1 phút nhé."
        )
    except anthropic.APIStatusError as e:
        log.exception("anthropic error")
        if "credit balance is too low" in str(e):
            await status.edit_text(
                "⚠️ Tài khoản Claude đã hết credit. Vui lòng nạp thêm tại "
                "console.anthropic.com (Plans & Billing)."
            )
        else:
            await status.edit_text(f"Có lỗi từ Claude: {e}")
    except Exception as e:  # noqa: BLE001
        log.exception("answer failed")
        await status.edit_text(f"Có lỗi xảy ra: {e}")


def main() -> None:
    errors = config.check()
    if errors:
        raise SystemExit("Cấu hình chưa đúng:\n - " + "\n - ".join(errors))

    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("refresh", cmd_refresh))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("doanhthu", cmd_doanhthu))
    app.add_handler(CommandHandler("chienluoc", cmd_chienluoc))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))

    log.info("Bot đang chạy. Nhấn Ctrl+C để dừng.")
    app.run_polling()


if __name__ == "__main__":
    main()
