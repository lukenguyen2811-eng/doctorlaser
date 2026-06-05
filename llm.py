"""Gọi Claude để phân tích dữ liệu và trả lời câu hỏi bằng tiếng Việt."""

import anthropic

import config

_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

_INSTRUCTIONS = """\
Bạn là trợ lý phân tích dữ liệu cho phòng khám da liễu/thẩm mỹ "Doctor Laser".

Dữ liệu là bảng theo dõi LEAD (khách hàng tiềm năng) với các cột:
- NGÀY: ngày phát sinh lead
- HỌ VÀ TÊN: tên khách (có thể là tên tài khoản mạng xã hội)
- SỐ ĐIỆN THOẠI
- DỊCH VỤ: dịch vụ khách quan tâm (SẸO RỖ, FILLER, BOTOX, ...)
- NV TRỰC PAGE: nhân viên trực page
- TELESALE PHỤ TRÁCH: nhân viên telesale
- NGUỒN: kênh đến (TIKTOK, FB SEO, ZALO OA, WEB, ...)
- GHI CHÚ
- TRẠNG THÁI: kết quả (ĐÃ ĐẾN, ĐÃ ĐẶT HẸN, THAM KHẢO, ĐANG TƯ VẤN,
  KHÔNG TƯƠNG TÁC, TỪ CHỐI ĐIỀU TRỊ, RÁC, NGOẠI TỈNH, ...)
- GỌI LẦN 1, GỌI LẦN 2

Quy tắc trả lời:
- Luôn trả lời bằng tiếng Việt, rõ ràng, đi thẳng vào con số và insight.
- Khi cần con số tổng hợp (đếm theo nguồn/trạng thái/dịch vụ/ngày/telesale),
  HÃY DÙNG phần "SỐ LIỆU TỔNG HỢP" đã tính sẵn bên dưới — chính xác hơn tự đếm.
- Khi câu hỏi cần lọc/tìm theo điều kiện cụ thể, dùng phần "DỮ LIỆU CHI TIẾT".
- Nếu dữ liệu không đủ để trả lời, nói rõ là không đủ dữ liệu, đừng bịa.
- Trình bày gọn: dùng gạch đầu dòng, số liệu kèm phần trăm khi hữu ích.
- Có thể chủ động gợi ý insight (ví dụ nguồn nào hiệu quả, tỉ lệ chốt) khi phù hợp.
"""


def _build_system(data_tsv: str, summary: str) -> list[dict]:
    """System prompt: phần hướng dẫn + dữ liệu (được cache để tiết kiệm chi phí)."""
    context = (
        f"=== SỐ LIỆU TỔNG HỢP (đã tính sẵn, chính xác) ===\n{summary}\n\n"
        f"=== DỮ LIỆU CHI TIẾT (bảng TSV) ===\n{data_tsv}"
    )
    return [
        {"type": "text", "text": _INSTRUCTIONS},
        # Khối dữ liệu lớn -> bật prompt caching để các câu hỏi sau rẻ và nhanh hơn.
        {"type": "text", "text": context, "cache_control": {"type": "ephemeral"}},
    ]


def answer(history: list[dict], data_tsv: str, summary: str) -> str:
    """Gọi Claude với lịch sử hội thoại và dữ liệu hiện tại, trả về câu trả lời."""
    system = _build_system(data_tsv, summary)

    # Dùng streaming để tránh timeout khi dữ liệu lớn / câu trả lời dài.
    with _client.messages.stream(
        model=config.CLAUDE_MODEL,
        max_tokens=8000,
        system=system,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        messages=history,
    ) as stream:
        message = stream.get_final_message()

    return "".join(b.text for b in message.content if b.type == "text").strip()
