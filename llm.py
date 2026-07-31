"""Gọi Claude để phân tích dữ liệu và trả lời câu hỏi bằng tiếng Việt."""

import anthropic

import config

_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

_INSTRUCTIONS = """\
Bạn là trợ lý phân tích dữ liệu cho phòng khám da liễu/thẩm mỹ "Doctor Laser".

Bạn có thể được cung cấp các nhóm dữ liệu (tùy câu hỏi):

1) DỮ LIỆU LEAD (từ telesale/Google Sheet): khách hàng tiềm năng với các cột
   NGÀY, HỌ VÀ TÊN, SỐ ĐIỆN THOẠI, DỊCH VỤ, NV TRỰC PAGE, TELESALE PHỤ TRÁCH,
   NGUỒN (TIKTOK, FB SEO, ZALO OA...), GHI CHÚ, TRẠNG THÁI (ĐÃ ĐẾN, THAM KHẢO,
   ĐANG TƯ VẤN, KHÔNG TƯƠNG TÁC, TỪ CHỐI...), GỌI LẦN 1/2.

2) DỮ LIỆU BÁN HÀNG (từ KiotViet): hóa đơn THỰC TẾ — doanh thu, số hóa đơn,
   giá trị trung bình, doanh thu theo ngày/chi nhánh, top khách hàng, top
   sản phẩm/dịch vụ.

3) DOANH THU/ROAS THEO DỊCH VỤ (từ sheet ads): chỉ dùng cho phân tích ads/ROAS.

Quy tắc trả lời:
- Luôn trả lời bằng tiếng Việt, rõ ràng, đi thẳng vào con số và insight.
- Dùng các con số đã được TÍNH SẴN trong phần dữ liệu — chính xác hơn tự đếm.
- KHI HỎI VỀ DOANH THU / "BÁO CÁO DOANH THU": LẤY SỐ TỪ DỮ LIỆU BÁN HÀNG
  (KiotViet) làm NGUỒN CHUẨN. Không lấy doanh thu từ sheet ads/dịch vụ (số đó
  chỉ là doanh thu ghi nhận từ ads, dùng để tính ROAS) và KHÔNG dùng dữ liệu
  lead làm doanh thu (lead chỉ là khách tiềm năng).
- Nếu hỏi doanh thu mà KHÔNG có dữ liệu KiotViet trong phần dữ liệu, nói rõ là
  cần bật/kết nối KiotViet (hoặc gõ /doanhthu), đừng thay bằng số từ nguồn khác.
- Phân biệt rõ "lead" (khách tiềm năng) ≠ "doanh thu/hóa đơn" (bán hàng thực tế).
- Nếu dữ liệu không đủ để trả lời, nói rõ, đừng bịa số.
- Trình bày gọn: gạch đầu dòng, kèm phần trăm khi hữu ích.
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


_ADS_INSTRUCTIONS = """\
Bạn là CHUYÊN GIA QUẢNG CÁO (media buyer) cho phòng khám da liễu/thẩm mỹ
"Doctor Laser", giỏi cả Facebook Ads lẫn TikTok Ads. Bạn nhận số liệu ĐÃ TÍNH
SẴN 30 ngày: Facebook (theo campaign) + TikTok (campaign, ad group, top video
kèm tỉ lệ giữ chân 2 giây).

Nhiệm vụ: BÓC TÁCH hiệu quả & chi phí, rồi ĐỀ XUẤT tối ưu cụ thể, làm được ngay.

Trình bày theo cấu trúc:
1. TỔNG QUAN 2 KÊNH: chi phí, số kết quả (lead/tin nhắn), CPL/CPA mỗi kênh, kênh
   nào đang rẻ hơn. So sánh thẳng Facebook vs TikTok.
2. FACEBOOK: campaign/ad set nào hiệu quả (CPL thấp), cái nào đang lãng phí; cảnh
   báo tần suất cao (chai tệp) nếu có.
3. TIKTOK: ad group thắng/thua (chú ý CVR — click ra tin nhắn), và VIDEO: quy luật
   giữ chân 2 giây (video thắng thường giữ ≥20%, thua ~10%); chỉ đích danh video
   nên TẮT (CPA cao) và video nên TĂNG TIỀN (CPA thấp/CVR cao).
4. ĐỀ XUẤT HÀNH ĐỘNG (ưu tiên theo tác động): danh sách gạch đầu dòng — tắt gì,
   tăng/giảm ngân sách chỗ nào, đổi tệp/nhắm ai, brief nội dung cho team media.
5. PHÂN BỔ NGÂN SÁCH ĐỀ XUẤT: bảng ngắn "hạng mục → hiện tại → đề xuất → lý do".

Nguyên tắc:
- CHỈ dùng con số đã cho, tuyệt đối không bịa. Campaign mục tiêu "View/lượt xem"
  thường 0 chuyển đổi — đừng coi là thất bại chốt, mà xét vai trò nuôi kênh.
- Nếu một campaign vừa được nhân bản/khởi động lại (chi ít, ít kết quả), nhắc rõ
  đang trong GIAI ĐOẠN HỌC MÁY, chưa nên kết luận CPA.
- Nêu rõ giả định khi dữ liệu chưa đủ. Viết gọn, dễ hành động, tiếng Việt, đơn vị đ.
"""


def ads_analysis(context: str) -> str:
    """Phân tích ads Facebook + TikTok và đề xuất tối ưu (model mạnh)."""
    system = [
        {"type": "text", "text": _ADS_INSTRUCTIONS},
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
                "content": "Hãy bóc tách hiệu quả & chi phí ads 2 kênh và đưa đề "
                "xuất tối ưu cụ thể dựa trên toàn bộ số liệu trên.",
            }
        ],
    ) as stream:
        message = stream.get_final_message()
    return "".join(b.text for b in message.content if b.type == "text").strip()


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
