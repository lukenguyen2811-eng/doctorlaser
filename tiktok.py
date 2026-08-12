"""Báo cáo TikTok Ads qua endpoint MCP chính thức của TikTok (tt-ads-mcp-flat).

Bot gọi JSON-RPC (initialize + tools/call report_integrated_get) tới
https://business-api.tiktok.com/open_mcp/tt-ads-mcp-flat bằng token OAuth
cấp qua TikTok Agentic Hub (biến TIKTOK_MCP_TOKEN).

QUAN TRỌNG: token bị RÀNG BUỘC theo endpoint (OAuth resource indicator).
Token cấp cho tt-ads-mcp-flat gọi sang tt-ads-mcp-layer sẽ bị 401. Nếu đổi
endpoint khi authorize thì phải đổi _URL bên dưới cho khớp.

CƠ CHẾ TOKEN (đã kiểm chứng 12/08/2026):
- Access token sống ~24h, NHƯNG TikTok chỉ cho 1 access token sống/lượt cấp:
  bất kỳ ai refresh (Claude Code CLI, script khác) là token đang dùng BỊ THU HỒI
  ngay → không thể dựa vào access token tĩnh trong env.
- Refresh token KHÔNG xoay vòng (dùng lại được tới khi authorize hết hạn ~30
  ngày) → bot giữ TIKTOK_REFRESH_TOKEN + TIKTOK_CLIENT_ID và TỰ refresh khi
  gặp 401/40105 rồi thử lại. Tự lành, không cần cập nhật token thủ công.
- Khi refresh token hết hạn (~30 ngày): authorize lại
  (claude mcp logout tiktok-ads && claude mcp login tiktok-ads) và cập nhật
  TIKTOK_REFRESH_TOKEN trên Railway.
"""

import json
import threading
import time

import requests

import config

_URL = "https://business-api.tiktok.com/open_mcp/tt-ads-mcp-flat"
_TOKEN_EP = _URL + "/oauth/token"
_initialized = False
_cache: dict = {}
# Access token đang dùng (khởi tạo từ env, tự thay khi refresh).
_access_token: str = config.TIKTOK_MCP_TOKEN
_token_lock = threading.Lock()
# Hạn của refresh token (epoch giây) — cập nhật từ refresh_token_expires_in
# mỗi lần refresh, để báo cáo nhắc trước khi phải authorize lại (~30 ngày/lần).
_rt_expires_at: float = 0.0


def rt_days_left() -> float | None:
    """Số ngày còn lại của refresh token (None nếu chưa refresh lần nào)."""
    if not _rt_expires_at:
        return None
    return (_rt_expires_at - time.time()) / 86400


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }


def _can_refresh() -> bool:
    return bool(config.TIKTOK_REFRESH_TOKEN and config.TIKTOK_CLIENT_ID)


def _refresh_access_token() -> bool:
    """Đổi refresh token lấy access token mới. Trả True nếu thành công."""
    global _access_token, _rt_expires_at
    if not _can_refresh():
        return False
    with _token_lock:
        try:
            resp = requests.post(_TOKEN_EP, timeout=30, data={
                "grant_type": "refresh_token",
                "refresh_token": config.TIKTOK_REFRESH_TOKEN,
                "client_id": config.TIKTOK_CLIENT_ID,
            }, headers={"Accept": "application/json"})
            if resp.status_code != 200:
                return False
            body = resp.json()
            _access_token = body["access_token"]
            rt_exp = body.get("refresh_token_expires_in")
            if rt_exp:
                _rt_expires_at = time.time() + float(rt_exp)
            return True
        except Exception:  # noqa: BLE001
            return False


def _parse_body(text: str) -> dict:
    """Server có thể trả JSON thuần hoặc SSE (dòng 'data: {...}')."""
    text = (text or "").strip()
    if not text:
        return {}
    if text.startswith("{"):
        return json.loads(text)
    for line in text.splitlines():
        if line.startswith("data:"):
            return json.loads(line[5:].strip())
    raise RuntimeError(f"TikTok MCP trả dữ liệu lạ: {text[:200]}")


def _rpc(payload: dict) -> dict:
    resp = requests.post(_URL, data=json.dumps(payload), headers=_headers(), timeout=60)
    if resp.status_code == 401 and _refresh_access_token():
        # Token bị thu hồi (bên khác vừa refresh) -> tự refresh và thử lại 1 lần.
        resp = requests.post(
            _URL, data=json.dumps(payload), headers=_headers(), timeout=60
        )
    if resp.status_code == 401:
        raise RuntimeError(
            "Token TikTok hết hạn và không tự refresh được — authorize lại "
            "Agentic Hub, cập nhật TIKTOK_REFRESH_TOKEN trên Railway."
        )
    if resp.status_code != 200:
        raise RuntimeError(f"TikTok MCP lỗi HTTP {resp.status_code}: {resp.text[:200]}")
    return _parse_body(resp.text)


def _ensure_init() -> None:
    global _initialized
    if _initialized:
        return
    _rpc({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26", "capabilities": {},
            "clientInfo": {"name": "doctorlaser-bot", "version": "1.0"},
        },
    })
    _initialized = True


def _call_tool(name: str, arguments: dict) -> dict:
    """Gọi 1 tool MCP, trả về JSON đã parse từ TikTok API.

    Tự refresh + thử lại khi token hết hạn (40105) hoặc TikTok cấp token thiếu
    quyền advertiser (40001 — thi thoảng xảy ra, refresh lại là được).
    """
    _ensure_init()
    body: dict = {}
    for attempt in range(3):
        res = _rpc({
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        })
        if "error" in res:
            raise RuntimeError(f"TikTok MCP lỗi: {res['error']}")
        content = (res.get("result") or {}).get("content") or []
        body = json.loads(content[0]["text"]) if content else {}
        code = body.get("code")
        if code == 0:
            return body.get("data") or {}
        if code in (40105, 40001) and attempt < 2 and _refresh_access_token():
            continue  # token mới -> thử lại
        break
    code = body.get("code")
    if code in (40105, 40001):
        raise RuntimeError(
            "Token TikTok hết hạn/thiếu quyền và không tự refresh được — "
            "authorize lại Agentic Hub, cập nhật TIKTOK_REFRESH_TOKEN trên Railway."
        )
    raise RuntimeError(f"TikTok API lỗi ({code}): {body.get('message', '')[:200]}")


def get_campaign_report(start_date: str, end_date: str, force: bool = False) -> list[dict]:
    """Số liệu theo campaign trong khoảng ngày (YYYY-MM-DD), đã lọc campaign chi 0đ."""
    key = f"{start_date}:{end_date}"
    now = time.time()
    hit = _cache.get(key)
    if not force and hit and (now - hit[0]) < config.KIOTVIET_CACHE_TTL:
        return hit[1]

    data = _call_tool("report_integrated_get", {
        "advertiser_id": config.TIKTOK_ADVERTISER_ID,
        "report_type": "BASIC",
        "data_level": "AUCTION_CAMPAIGN",
        "dimensions": ["campaign_id"],
        "metrics": [
            "campaign_name", "spend", "impressions", "clicks",
            "conversion", "cost_per_conversion",
        ],
        "start_date": start_date,
        "end_date": end_date,
        "page_size": 100,
    })
    rows = []
    for item in data.get("list") or []:
        m = item.get("metrics") or {}
        spend = float(m.get("spend") or 0)
        if spend <= 0:
            continue
        rows.append({
            "name": (m.get("campaign_name") or "(không tên)").strip(),
            "spend": spend,
            "impressions": int(float(m.get("impressions") or 0)),
            "clicks": int(float(m.get("clicks") or 0)),
            "conversion": int(float(m.get("conversion") or 0)),
            "cpa": float(m.get("cost_per_conversion") or 0),
        })
    rows.sort(key=lambda r: -r["spend"])
    _cache[key] = (now, rows)
    return rows


def totals(rows: list[dict]) -> dict:
    spend = sum(r["spend"] for r in rows)
    conv = sum(r["conversion"] for r in rows)
    return {
        "spend": spend,
        "conversion": conv,
        "cpa": (spend / conv) if conv else 0.0,
        "impressions": sum(r["impressions"] for r in rows),
        "clicks": sum(r["clicks"] for r in rows),
    }


# ---------------------------------------------------------------------------
# Dữ liệu đa tầng cho lệnh phân tích ads (/phantichads)
# ---------------------------------------------------------------------------

def _report_list(data_level: str, dimensions: list, metrics: list,
                 start: str, end: str, page_size: int = 50) -> list[dict]:
    data = _call_tool("report_integrated_get", {
        "advertiser_id": config.TIKTOK_ADVERTISER_ID,
        "report_type": "BASIC", "data_level": data_level,
        "dimensions": dimensions, "metrics": metrics,
        "start_date": start, "end_date": end, "page_size": page_size,
        "order_field": "spend", "order_type": "DESC",
    })
    return data.get("list") or []


def _f(m: dict, k: str) -> float:
    try:
        return float(m.get(k) or 0)
    except (TypeError, ValueError):
        return 0.0


def build_analysis_text(start: str, end: str) -> str:
    """Khối dữ liệu TikTok (campaign + ad group + top video) để đưa cho Claude.

    Số liệu thô, đã tính CPA và tỉ lệ giữ chân 2 giây — để model phân tích, không
    tự bịa. Trả chuỗi tiếng Việt gọn.
    """
    lines: list[str] = [f"## TIKTOK ADS ({start} → {end}) — tài khoản Doctor Laser Clinic0905"]

    # 1) Campaign (chỉ cái có chi tiêu)
    camp = _report_list("AUCTION_CAMPAIGN", ["campaign_id"],
                        ["campaign_name", "spend", "impressions", "clicks", "ctr",
                         "conversion", "cost_per_conversion", "conversion_rate", "frequency"],
                        start, end)
    lines.append("\n### Theo CAMPAIGN")
    for it in camp:
        m = it.get("metrics") or {}
        if _f(m, "spend") <= 0:
            continue
        conv = int(_f(m, "conversion"))
        lines.append(
            f"- {m.get('campaign_name','?')}: chi {_f(m,'spend'):,.0f}đ | KQ {conv}"
            + (f" | CPA {_f(m,'cost_per_conversion'):,.0f}đ" if conv else " | (không có chuyển đổi)")
            + f" | CTR {_f(m,'ctr'):.2f}% | CVR {_f(m,'conversion_rate'):.2f}%"
            + f" | tần suất {_f(m,'frequency'):.2f}"
        )

    # 2) Ad group (top theo chi tiêu)
    ag = _report_list("AUCTION_ADGROUP", ["adgroup_id"],
                     ["campaign_name", "adgroup_name", "spend", "conversion",
                      "cost_per_conversion", "conversion_rate", "frequency"],
                     start, end)
    ag = [x for x in ag if _f((x.get("metrics") or {}), "spend") > 0][:8]
    lines.append("\n### Theo AD GROUP (top chi tiêu)")
    for it in ag:
        m = it["metrics"]
        conv = int(_f(m, "conversion"))
        lines.append(
            f"- [{m.get('campaign_name','?')}] {m.get('adgroup_name','?')}: "
            f"chi {_f(m,'spend'):,.0f}đ | KQ {conv}"
            + (f" | CPA {_f(m,'cost_per_conversion'):,.0f}đ" if conv else "")
            + f" | CVR {_f(m,'conversion_rate'):.2f}% | tần suất {_f(m,'frequency'):.2f}"
        )

    # 3) Top video/ad theo chi tiêu (kèm giữ chân 2s = xem>=2s / lượt phát)
    ads = _report_list("AUCTION_AD", ["ad_id"],
                      ["adgroup_name", "ad_name", "spend", "conversion",
                       "cost_per_conversion", "conversion_rate",
                       "video_play_actions", "video_watched_2s"],
                      start, end, page_size=20)
    ads = [x for x in ads if _f((x.get("metrics") or {}), "spend") > 0][:15]
    lines.append("\n### TOP VIDEO/AD (theo chi tiêu) — giữ 2s = xem≥2s / lượt phát")
    for it in ads:
        m = it["metrics"]
        conv = int(_f(m, "conversion"))
        plays = _f(m, "video_play_actions")
        hold2 = (_f(m, "video_watched_2s") / plays * 100) if plays else 0.0
        lines.append(
            f"- {m.get('ad_name','?')} [{m.get('adgroup_name','?')}]: "
            f"chi {_f(m,'spend'):,.0f}đ | KQ {conv}"
            + (f" | CPA {_f(m,'cost_per_conversion'):,.0f}đ" if conv else "")
            + f" | CVR {_f(m,'conversion_rate'):.2f}%"
            + (f" | giữ 2s {hold2:.1f}%" if plays else " | (ảnh/không phải video)")
        )
    return "\n".join(lines)
