"""Gọi Claude để phân tích dữ liệu và trả lời câu hỏi bằng tiếng Việt."""

import anthropic

import config

_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

_INSTRUCTIONS = """\
Bạn là trợ lý phân tích dữ liệu cho phòng khám da liễu/thẩm mỹ "Doctor Laser".

Bạn có thể được cung cấp 2 nhóm dữ liệu (tùy câu hỏi):

1) DỮ LIỆU LEAD (từ telesale/Google Sheet): khách hàng tiềm năng với các cột
   NGÀY, HỌ VÀ TÊN, SỐ ĐIỆN THOẠI, DỊCH VỤ, NV TRỰC PAGE, TELESALE PHỤ TRÁCH,
   NGUỒN (TIKTOK, FB SEO, ZALO OA...), GHI CHÚ, TRẠNG THÁI (ĐÃ ĐẾN, THAM KHẢO,
   ĐANG TƯ VẤN, KHÔNG TƯƠNG TÁC, TỪ CHỐI...), GỌI LẦN 1/2.

2) DỮ LIỆU BÁN HÀNG (từ KiotViet): hóa đơn thực tế — doanh thu, số hóa đơn,
   giá trị trung bình, doanh thu theo ngày/chi nhánh, top khách hàng, top
   sản phẩm/dịch vụ.

Quy tắc trả lời:
- Luôn trả lời bằng tiếng Việt, rõ ràng, đi thẳng vào con số và insight.
- Dùng các con số đã được TÍNH SẴN trong phần dữ liệu — chính xác hơn tự đếm.
- Phân biệt rõ "lead" (khách tiềm năng từ marketing) và "doanh thu/hóa đơn"
  (bán hàng thực tế). Nếu câu hỏi về doanh thu mà không có dữ liệu bán hàng,
  nói rõ là chưa có/đưa dữ liệu KiotViet.
- Nếu dữ liệu không đủ để trả lời, nói rõ, đừng bịa số.
- Trình bày gọn: gạch đầu dòng, kèm phần trăm khi hữu ích.
- Chủ động gợi ý insight khi phù hợp (nguồn hiệu quả, tỉ lệ chốt, xu hướng
  doanh thu...).
"""


_STRATEGY_INSTRUCTIONS = """\
Bạn là CỐ VẤN CHIẾN LƯỢC marketing & kinh doanh cho phòng khám da liễu/thẩm mỹ
"Doctor Laser". Bạn được cung cấp số liệu đã tính sẵn: lead/telesale, doanh thu
bán hàng, và chi phí ads + ROAS theo dịch vụ/kênh/nhân viên.

Nhiệm vụ: đưa ra PHÂN TÍCH CHIẾN LƯỢC sắc bén và KẾ HOẠCH HÀNH ĐỘNG cụ thể.

Hãy trình bày theo cấu trúc:
1. BỨC TRANH TỔNG QUAN: vài chỉ số quan trọng nhất của kỳ được chọn (doanh thu,
   chi phí ads, ROAS, tỉ lệ chốt), kèm xu hướng tăng/giảm giữa các tháng.
2. PHÁT HIỆN CHÍNH: 3-5 insight — kênh/dịch vụ nào hiệu quả (ROAS cao) hay đang
   lãng phí, điểm rò rỉ ở phễu (lấy SĐT, tỉ lệ chốt), chênh lệch hiệu suất nhân
   viên, biến động theo tuần/tháng.
3. KẾ HOẠCH THEO THÁNG: cho từng tháng (hoặc tháng tới), mục tiêu doanh thu/ngân
   sách ads theo dịch vụ-kênh, trọng tâm cần làm.
4. KẾ HOẠCH THEO TUẦN: chia nhỏ thành việc làm hằng tuần (Tuần 1→4): chỉ tiêu
   số đo được (số lead, tỉ lệ lấy SĐT, tỉ lệ chốt, doanh thu), ai phụ trách.

Khi dữ liệu được lọc theo khoảng tháng, hãy bám sát đúng khoảng đó. Lưu ý: bảng
ROAS là số LŨY KẾ toàn bộ (không lọc tháng) — dùng để tham chiếu mức hiệu quả
tương đối giữa các dịch vụ, đừng coi là số của riêng kỳ.

Nguyên tắc: dùng đúng con số đã cho (đừng bịa); nêu rõ giả định nếu dữ liệu chưa
đủ; ưu tiên đề xuất có tác động doanh thu/lợi nhuận lớn; viết gọn, dễ hành động,
bằng tiếng Việt; dùng đơn vị tiền Việt (đ).
"""


def strategy(context: str) -> str:
    """Phân tích chiến lược chuyên sâu (dùng model mạnh + suy luận)."""
    system = [
        {"type": "text", "text": _STRATEGY_INSTRUCTIONS},
        {"type": "text", "text": context, "cache_control": {"type": "ephemeral"}},
    ]
    with _client.messages.stream(
        model=config.STRATEGY_MODEL,
        max_tokens=6000,
        system=system,
        thinking={"type": "adaptive"},
        output_config={"effort": "medium"},
        messages=[
            {
                "role": "user",
                "content": "Hãy phân tích chiến lược toàn diện và lập kế hoạch "
                "hành động dựa trên toàn bộ số liệu trên.",
            }
        ],
    ) as stream:
        message = stream.get_final_message()
    return "".join(b.text for b in message.content if b.type == "text").strip()


def answer(history: list[dict], context: str) -> str:
    """Trả lời câu hỏi dựa trên phần dữ liệu (context) đã được lắp sẵn.

    Tắt thinking + max_tokens nhỏ để tiết kiệm chi phí (số liệu đã tính sẵn).
    """
    system = [
        {"type": "text", "text": _INSTRUCTIONS},
        # Bật prompt caching cho khối dữ liệu để câu hỏi sau rẻ & nhanh hơn.
        {"type": "text", "text": context, "cache_control": {"type": "ephemeral"}},
    ]

    with _client.messages.stream(
        model=config.CLAUDE_MODEL,
        max_tokens=4000,
        system=system,
        messages=history,
    ) as stream:
        message = stream.get_final_message()

    return "".join(b.text for b in message.content if b.type == "text").strip()
