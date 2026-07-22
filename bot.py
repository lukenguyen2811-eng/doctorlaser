"""Bot Telegram phân tích dữ liệu Google Sheet của Doctor Laser.

Người dùng nhắn câu hỏi bằng tiếng Việt, bot đọc Google Sheet, tính số liệu
và dùng Claude để trả lời.

Chạy:  python bot.py
"""

import asyncio
import html as _html
import logging
import re

import anthropic
from telegram import Update
from telegram.constants import ChatAction, ParseMode
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
import crm
import kiotviet
import llm
import meta
import report
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
    "/baocaongay - báo cáo ngày (doanh thu + ads + lead hôm qua)\n"
    "/baocaoads - báo cáo ads hôm qua theo campaign + lũy kế tháng\n"
    "/adsnow - ads HÔM NAY realtime (đến thời điểm hiện tại)\n"
    "/stats - tổng data CRM (rác/quan tâm/lead) + trạng thái\n"
    "/doanhthu - doanh thu tháng này (KiotViet)\n"
    "/chienluoc - phân tích chiến lược (hỏi khoảng tháng, kế hoạch theo tuần & tháng)\n"
    "/refresh - tải lại dữ liệu mới nhất\n"
    "/help - hướng dẫn"
)


def _allowed(update: Update) -> bool:
    if not config.ALLOWED_TELEGRAM_IDS:
        return True
    user = update.effective_user
    return bool(user and user.id in config.ALLOWED_TELEGRAM_IDS)


def _mono_chunks(text: str) -> list[str]:
    """Chia text và bọc mỗi phần trong <pre> (monospace, canh cột thẳng hàng)."""
    text = text or "(trống)"
    limit = TELEGRAM_LIMIT - 20
    return [
        f"<pre>{_html.escape(text[i : i + limit])}</pre>"
        for i in range(0, len(text), limit)
    ]


async def _reply_mono(update: Update, text: str) -> None:
    for chunk in _mono_chunks(text):
        await update.message.reply_text(chunk, parse_mode=ParseMode.HTML)


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
    import datetime as _dt

    today = _dt.date.today()
    m = re.search(r"\d{1,2}", " ".join(context.args))
    if m and 1 <= int(m.group()) <= 12 and int(m.group()) != today.month:
        mon = int(m.group())
        label = f"tháng {mon}/{today.year}"
        fetch = lambda: kiotviet.get_invoices_for_month(today.year, mon)  # noqa: E731
    else:
        label = f"tháng {today.month}"
        fetch = kiotviet.get_current_month_invoices
    status = await update.message.reply_text(f"⏳ Đang lấy doanh thu {label}...")
    try:
        invoices = await asyncio.to_thread(fetch)
        customer_total = await asyncio.to_thread(kiotviet.get_customer_total)
        summary = sales.build_summary(invoices, customer_total, label)
        await status.delete()
        await _reply_mono(update, summary)
    except Exception as e:  # noqa: BLE001
        log.exception("doanhthu failed")
        await status.edit_text(f"Lỗi khi lấy dữ liệu KiotViet: {e}")


async def cmd_chatid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Trả về Chat ID hiện tại (để đặt DAILY_REPORT_CHAT_ID)."""
    chat = update.effective_chat
    await update.message.reply_text(
        f"Chat ID của nơi này là: {chat.id}\n"
        "Đặt giá trị này vào biến DAILY_REPORT_CHAT_ID trên Railway để nhận "
        "báo cáo tự động mỗi sáng."
    )


async def cmd_baocaongay(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return
    import datetime as _dt

    # Cho phép chỉ định ngày: /baocaongay 4/7 hoặc /baocaongay 4/7/2026.
    as_of = None
    arg = " ".join(context.args).strip()
    if arg:
        m = re.match(r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?", arg)
        if not m:
            await update.message.reply_text(
                "Không hiểu ngày. Dùng dạng: /baocaongay 4/7 hoặc /baocaongay 4/7/2026"
            )
            return
        d, mo, y = m.groups()
        year = int(y) if y else _dt.date.today().year
        if year < 100:
            year += 2000
        try:
            as_of = _dt.date(year, int(mo), int(d))
        except ValueError:
            await update.message.reply_text("Ngày không hợp lệ. Ví dụ đúng: /baocaongay 4/7/2026")
            return

    status = await update.message.reply_text("⏳ Đang lập báo cáo ngày...")
    try:
        text = await asyncio.to_thread(report.build_daily, as_of)
        await status.delete()
        await _reply_mono(update, text)
    except Exception as e:  # noqa: BLE001
        log.exception("baocaongay failed")
        await status.edit_text(f"Lỗi khi lập báo cáo: {e}")


async def _send_daily_report(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Job tự động: gửi báo cáo ngày vào chat đã cấu hình."""
    chat_id = config.DAILY_REPORT_CHAT_ID
    if not chat_id:
        return
    try:
        text = await asyncio.to_thread(report.build_daily)
        for chunk in _mono_chunks(text):
            await context.bot.send_message(chat_id, chunk, parse_mode=ParseMode.HTML)
    except Exception:  # noqa: BLE001
        log.exception("daily report job failed")


async def cmd_testbaocao(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Kiểm tra báo cáo tự động: gửi thử tới DAILY_REPORT_CHAT_ID đã cấu hình."""
    if not _allowed(update):
        return
    chat_id = config.DAILY_REPORT_CHAT_ID
    if not chat_id:
        await update.message.reply_text(
            "Chưa đặt DAILY_REPORT_CHAT_ID nên lịch 8h sáng KHÔNG chạy.\n"
            "Cách sửa: gõ /chatid trong nhóm để lấy Chat ID, rồi thêm biến "
            "DAILY_REPORT_CHAT_ID trên Railway = giá trị đó."
        )
        return
    has_queue = bool(context.application.job_queue)
    await update.message.reply_text(
        f"Cấu hình lịch tự động:\n"
        f"• DAILY_REPORT_CHAT_ID = {chat_id}\n"
        f"• Giờ gửi = {config.DAILY_REPORT_HOUR}h ({config.TIMEZONE})\n"
        f"• JobQueue khả dụng: {'CÓ' if has_queue else 'KHÔNG'}\n"
        f"Đang gửi thử báo cáo tới chat đó..."
    )
    try:
        text = await asyncio.to_thread(report.build_daily)
        for chunk in _mono_chunks(text):
            await context.bot.send_message(chat_id, chunk, parse_mode=ParseMode.HTML)
        await update.message.reply_text("✅ Gửi thử THÀNH CÔNG tới chat đã cấu hình.")
    except Exception as e:  # noqa: BLE001
        log.exception("testbaocao failed")
        await update.message.reply_text(
            f"❌ Gửi thử THẤT BẠI: {e}\n"
            "Thường do Chat ID sai. Gõ /chatid TRONG NHÓM cần nhận để lấy đúng ID "
            "rồi cập nhật biến DAILY_REPORT_CHAT_ID trên Railway."
        )


async def cmd_kvdebug(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """So sánh các trường tiền của KiotViet cho 1 ngày: /kvdebug 12/06"""
    if not _allowed(update):
        return
    if not config.kiotviet_enabled():
        await update.message.reply_text("Chưa kết nối KiotViet.")
        return
    import datetime as _dt

    arg = " ".join(context.args).strip()
    m = re.match(r"(\d{1,2})/(\d{1,2})(?:/(\d{4}))?", arg)
    if m:
        dd, mm, yy = m.groups()
        d = _dt.date(int(yy) if yy else _dt.date.today().year, int(mm), int(dd))
    else:
        d = _dt.date.today() - _dt.timedelta(days=1)

    status = await update.message.reply_text(f"⏳ Đang kiểm tra ngày {d:%d/%m}...")
    try:
        inv = await asyncio.to_thread(kiotviet.get_invoices_for_date, d)

        def s(field: str) -> float:
            return sum(float(i.get(field) or 0) for i in inv)

        def f(x: float) -> str:
            return f"{int(round(x)):,}".replace(",", ".") + "đ"

        total, pay, disc = s("total"), s("totalPayment"), s("discount")
        pre_vat = kiotviet.total_revenue(inv)
        text = (
            f"KiotViet ngày {d:%d/%m/%Y} — {len(inv)} hóa đơn (đã loại hủy)\n"
            f"• tổng tiền hàng (trước VAT, đang dùng): {f(pre_vat)}\n"
            f"• total (có VAT): {f(total)}\n"
            f"• totalPayment: {f(pay)}\n"
            f"• discount: {f(disc)}"
        )
        await status.edit_text(text)
    except Exception as e:  # noqa: BLE001
        log.exception("kvdebug failed")
        await status.edit_text(f"Lỗi: {e}")


def _lead_date(r: dict):
    """Parse ô NGÀY (d/m/yyyy) của 1 lead -> datetime.date, hoặc None."""
    import datetime as _dt

    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", (r.get("ngay") or "").strip())
    if not m:
        return None
    try:
        return _dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


async def cmd_ads(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Chi phí & hiệu quả Facebook ads. /ads = tháng này, /ads 4 = tháng 4."""
    if not _allowed(update):
        return
    if not config.meta_enabled():
        await update.message.reply_text(
            "Chưa kết nối Meta. Cần đặt META_ACCESS_TOKEN, META_AD_ACCOUNT_ID."
        )
        return
    import calendar
    import datetime as _dt

    today = _dt.date.today()
    m = re.search(r"\d{1,2}", " ".join(context.args))
    if m and 1 <= int(m.group()) <= 12 and int(m.group()) != today.month:
        mon = int(m.group())
        since = f"{today.year}-{mon:02d}-01"
        until = f"{today.year}-{mon:02d}-{calendar.monthrange(today.year, mon)[1]:02d}"
        label = f"tháng {mon}/{today.year}"
    else:
        since = f"{today.year}-{today.month:02d}-01"
        until = today.strftime("%Y-%m-%d")
        label = f"tháng {today.month} (đến {today:%d/%m})"
    status = await update.message.reply_text(f"⏳ Đang lấy Facebook ads {label}...")
    try:
        rows = await asyncio.to_thread(meta.get_insights, since, until)
        await status.delete()
        await _reply_mono(update, meta.build_summary(rows, label))
    except Exception as e:  # noqa: BLE001
        log.exception("ads failed")
        await status.edit_text(f"Lỗi khi lấy Meta ads: {e}")


async def cmd_baocaoads(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Báo cáo ads hằng ngày: chi tiết campaign HÔM QUA + lũy kế tháng."""
    if not _allowed(update):
        return
    if not config.meta_enabled():
        await update.message.reply_text(
            "Chưa kết nối Meta ads. Cần đặt META_ACCESS_TOKEN, META_AD_ACCOUNT_ID."
        )
        return
    import datetime as _dt

    today = _dt.date.today()
    yesterday = today - _dt.timedelta(days=1)
    ds = yesterday.strftime("%Y-%m-%d")
    status = await update.message.reply_text("⏳ Đang lấy báo cáo ads...")
    try:
        rows = await asyncio.to_thread(meta.get_insights, ds, ds)
        text = meta.build_summary(rows, f"HÔM QUA {yesterday:%d/%m}")

        first = today.replace(day=1)
        if first <= yesterday:
            rows_m = await asyncio.to_thread(
                meta.get_insights, first.strftime("%Y-%m-%d"), ds
            )
            tm = meta.totals(rows_m)
            text += (
                f"\n\n— LŨY KẾ THÁNG {today.month} (đến {yesterday:%d/%m}) —\n"
                f"Chi: {meta._vnd(tm['spend'])} | Kết quả: {tm['results']} | "
                f"CPL: {meta._vnd(tm['cpl']) if tm['results'] else 'n/a'} | "
                f"CTR: {tm['ctr']:.2f}%"
            )
        await status.delete()
        await _reply_mono(update, text)
    except Exception as e:  # noqa: BLE001
        log.exception("baocaoads failed")
        await status.edit_text(f"Lỗi khi lấy báo cáo ads: {e}")


async def cmd_adsnow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ads REALTIME: số liệu HÔM NAY tính đến thời điểm hiện tại (theo campaign)."""
    if not _allowed(update):
        return
    if not config.meta_enabled():
        await update.message.reply_text(
            "Chưa kết nối Meta ads. Cần đặt META_ACCESS_TOKEN, META_AD_ACCOUNT_ID."
        )
        return
    import datetime as _dt

    now_vn = _dt.datetime.now(report.tzinfo())
    ds = now_vn.strftime("%Y-%m-%d")
    status = await update.message.reply_text("⏳ Đang lấy ads HÔM NAY (realtime)...")
    try:
        # force=True: bỏ cache để lấy số mới nhất từ Meta (gần realtime, trễ vài phút).
        rows = await asyncio.to_thread(meta.get_insights, ds, ds, True)
        label = f"HÔM NAY (đến {now_vn:%H:%M} {now_vn:%d/%m})"
        text = meta.build_summary(rows, label)
        text += "\n\n(Số liệu Meta cập nhật gần realtime, có thể trễ vài phút.)"
        await status.delete()
        await _reply_mono(update, text)
    except Exception as e:  # noqa: BLE001
        log.exception("adsnow failed")
        await status.edit_text(f"Lỗi khi lấy ads realtime: {e}")


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return
    import datetime as _dt

    mon = None
    m = re.search(r"\d{1,2}", " ".join(context.args))
    if m and 1 <= int(m.group()) <= 12:
        mon = int(m.group())
    try:
        leads, quan_tam, rac = await asyncio.to_thread(
            lambda: (crm.get_leads(), crm.get_quan_tam(), crm.get_rac())
        )
        if mon:
            year = _dt.date.today().year
            leads = crm.in_month(leads, year, mon)
            quan_tam = crm.in_month(quan_tam, year, mon)
            rac = crm.in_month(rac, year, mon)
            header = f"TỔNG HỢP DATA THÁNG {mon}/{year} (CRM chatbot)\n\n"
        else:
            header = "TỔNG HỢP DATA (CRM chatbot, tất cả)\n\n"
        summary = header + crm.build_summary(leads, quan_tam, rac)
        await _reply_mono(update, summary)
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

        # --- Doanh thu (KiotViet) — nhận "tháng N", mặc định THÁNG NÀY ---
        if config.kiotviet_enabled() and _is_sales_question(question):
            import datetime as _dt

            today = _dt.date.today()
            mq = re.search(r"tháng\s*(\d{1,2})", question.lower())
            if mq and 1 <= int(mq.group(1)) <= 12 and int(mq.group(1)) != today.month:
                mon = int(mq.group(1))
                label = f"tháng {mon}/{today.year}"
                invoices = await asyncio.to_thread(
                    kiotviet.get_invoices_for_month, today.year, mon
                )
            else:
                label = f"tháng {today.month}"
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
    app.add_handler(CommandHandler("ads", cmd_ads))
    app.add_handler(CommandHandler("baocaoads", cmd_baocaoads))
    app.add_handler(CommandHandler("adsnow", cmd_adsnow))
    app.add_handler(CommandHandler("kvdebug", cmd_kvdebug))
    app.add_handler(CommandHandler("chienluoc", cmd_chienluoc))
    app.add_handler(CommandHandler("baocaongay", cmd_baocaongay))
    app.add_handler(CommandHandler("testbaocao", cmd_testbaocao))
    app.add_handler(CommandHandler("chatid", cmd_chatid))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))

    # Lịch gửi báo cáo tự động mỗi sáng (giờ VN).
    if not config.DAILY_REPORT_CHAT_ID:
        log.warning(
            "KHÔNG lên lịch báo cáo ngày: thiếu biến DAILY_REPORT_CHAT_ID. "
            "Gõ /chatid trong nhóm để lấy Chat ID rồi đặt biến này trên Railway."
        )
    elif not app.job_queue:
        log.warning(
            "KHÔNG lên lịch báo cáo ngày: JobQueue không khả dụng. "
            "Cần cài 'python-telegram-bot[job-queue]' (đã có trong requirements.txt)."
        )
    else:
        import datetime as _dt

        app.job_queue.run_daily(
            _send_daily_report,
            time=_dt.time(hour=config.DAILY_REPORT_HOUR, tzinfo=report.tzinfo()),
            name="daily_report",
        )
        log.info(
            "Đã lên lịch báo cáo ngày lúc %sh (%s) gửi tới chat %s",
            config.DAILY_REPORT_HOUR,
            config.TIMEZONE,
            config.DAILY_REPORT_CHAT_ID,
        )

    log.info("Bot đang chạy. Nhấn Ctrl+C để dừng.")
    app.run_polling()


if __name__ == "__main__":
    main()
