"""Auto-sync TikTok MCP token: macOS Keychain → Railway.

Token MCP sống ~24h; Claude Code CLI tự refresh trong Keychain. Script này
(launchd 07:00 + 19:00 trên Mac mini) đọc token mới nhất, push lên Railway nếu
token đổi. Authorization sống ~30 ngày → mỗi tháng re-auth:
    claude mcp logout tiktok-ads && claude mcp login tiktok-ads

QUAN TRỌNG — chọn token theo QUYỀN THẬT, không theo hạn:
Keychain có thể chứa NHIỀU mục "tiktok" (mỗi MCP server 1 mục, vd tiktok-ads +
tiktok-ads-2). Có mục xác thực được (initialize 200) nhưng KHÔNG có quyền thao
tác advertiser (tools/call trả code 40001). Vì vậy phải kiểm tra tận
tools/call report_integrated_get (phải trả code 0) rồi mới push.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
MCP_URL = "https://business-api.tiktok.com/open_mcp/tt-ads-mcp-flat"
ADVERTISER_ID = "7139812447623446530"
RAILWAY_PROJECT = "eaea6f2e-fea0-4ef5-b789-63437560488a"  # project DOCTORLASER
RAILWAY_SERVICE = "doctorlaser"
STATE = ROOT / ".token_synced"  # nhớ token đã push (đừng commit — thêm .gitignore)


def _all_tokens_from_keychain() -> list[str]:
    """Mọi accessToken 'tiktok' trong Keychain (chưa lọc quyền)."""
    try:
        raw = subprocess.check_output(
            ["security", "find-generic-password", "-s", "Claude Code-credentials", "-w"],
            stderr=subprocess.DEVNULL).decode()
    except Exception:
        return []
    d = json.loads(raw).get("mcpOAuth", {})
    return [v["accessToken"] for k, v in d.items()
            if "tiktok" in k.lower() and isinstance(v, dict) and v.get("accessToken")]


def token_has_permission(tok: str) -> bool:
    """Token phải gọi được tools/call report_integrated_get với code 0.

    Chỉ check initialize là KHÔNG đủ: token thiếu quyền vẫn init 200 nhưng
    tools/call trả 40001 (No permission to operate advertiser).
    """
    try:
        r = requests.post(MCP_URL, headers={
            "Authorization": f"Bearer {tok}", "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"}, timeout=30,
            data=json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
                "name": "report_integrated_get", "arguments": {
                    "advertiser_id": ADVERTISER_ID, "report_type": "BASIC",
                    "data_level": "AUCTION_CAMPAIGN", "dimensions": ["campaign_id"],
                    "metrics": ["campaign_name", "spend"],
                    "start_date": "2026-07-28", "end_date": "2026-07-28", "page_size": 1}}}))
        if r.status_code != 200:
            return False
        body = r.text.strip()
        if body.startswith(("event:", "data:")):
            for line in body.splitlines():
                if line.startswith("data:"):
                    body = line[5:].strip()
                    break
        inner = json.loads(json.loads(body)["result"]["content"][0]["text"])
        return inner.get("code") == 0
    except Exception:
        return False


def pick_valid_token() -> str | None:
    """Trả token ĐẦU TIÊN có quyền advertiser thật (code 0)."""
    for tok in _all_tokens_from_keychain():
        if token_has_permission(tok):
            return tok
    return None


def push_railway(tok: str) -> bool:
    # Truyền -p/-e/-s trực tiếp, KHÔNG dùng `railway link`.
    # `railway link` ghi lại ~/.railway/config.json; chạy chồng nhau (launchd +
    # tay) từng làm hỏng config → CLI mất đăng nhập. Dạng cờ không đụng config.
    for attempt in range(3):
        r = subprocess.run(
            ["railway", "variables", "--set", f"TIKTOK_MCP_TOKEN={tok}",
             "-p", RAILWAY_PROJECT, "-e", "production", "-s", RAILWAY_SERVICE],
            capture_output=True, timeout=60)
        if r.returncode == 0:
            return True
        if attempt == 2:
            err = (r.stderr.decode() or r.stdout.decode())[:150]
            print(f"❌ push lỗi: {err}")
    return False


def main() -> None:
    check_only = "--check" in sys.argv
    toks = _all_tokens_from_keychain()
    if not toks:
        print("❌ Không đọc được token Keychain. Chạy: claude mcp login tiktok-ads")
        raise SystemExit(1)
    tok = pick_valid_token()
    n_ok = sum(1 for t in toks if t == tok)  # tok đã được test, đếm cho rõ log
    print(f"Keychain: {len(toks)} token tiktok | có quyền advertiser: "
          f"{'✅ có' if tok else '🔴 KHÔNG có cái nào'}")
    if not tok:
        print("⚠️ Không token nào thao tác được advertiser — re-auth ĐÚNG server:")
        print("   claude mcp logout tiktok-ads && claude mcp login tiktok-ads")
        raise SystemExit(1)
    if check_only:
        return
    prev = STATE.read_text().strip() if STATE.exists() else ""
    if tok == prev:
        print("↔️ Token không đổi, bỏ qua.")
        return
    print("📤 Push token (đã xác minh quyền) lên Railway...")
    if push_railway(tok):
        STATE.write_text(tok)
        print("🎉 Xong.")


if __name__ == "__main__":
    main()
