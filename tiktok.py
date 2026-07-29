"""Báo cáo TikTok Ads qua endpoint MCP chính thức của TikTok (tt-ads-mcp-layer).

Bot gọi JSON-RPC (initialize + tools/call report_integrated_get) tới
https://business-api.tiktok.com/open_mcp/tt-ads-mcp-layer bằng token OAuth
cấp qua TikTok Agentic Hub (biến TIKTOK_MCP_TOKEN).

LƯU Ý: token Agentic Hub có hiệu lực ~30 ngày. Khi hết hạn, bot sẽ báo rõ
trong báo cáo — cần authorize lại và cập nhật TIKTOK_MCP_TOKEN trên Railway.
"""

import json
import time

import requests

import config

_URL = "https://business-api.tiktok.com/open_mcp/tt-ads-mcp-flat"
_initialized = False
_cache: dict = {}


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {config.TIKTOK_MCP_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }


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
    if resp.status_code == 401:
        raise RuntimeError(
            "Token TikTok hết hạn/không hợp lệ — authorize lại Agentic Hub và "
            "cập nhật TIKTOK_MCP_TOKEN trên Railway."
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
    """Gọi 1 tool MCP, trả về JSON đã parse từ TikTok API."""
    _ensure_init()
    res = _rpc({
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    })
    if "error" in res:
        raise RuntimeError(f"TikTok MCP lỗi: {res['error']}")
    content = (res.get("result") or {}).get("content") or []
    body = json.loads(content[0]["text"]) if content else {}
    code = body.get("code")
    if code == 40105:
        raise RuntimeError(
            "Token TikTok hết hạn — authorize lại Agentic Hub và cập nhật "
            "TIKTOK_MCP_TOKEN trên Railway."
        )
    if code != 0:
        raise RuntimeError(f"TikTok API lỗi ({code}): {body.get('message', '')[:200]}")
    return body.get("data") or {}


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
