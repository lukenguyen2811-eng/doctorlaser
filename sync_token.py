"""Tự làm mới token TikTok bằng REFRESH TOKEN rồi đẩy lên Railway.

KHÁC bản cũ: bản cũ chỉ copy token có sẵn trong Keychain của Claude Code — mà
token đó ~24h phải được chính Claude Code refresh, nếu máy để không thì token
chết và không có gì để đẩy. Bản này TỰ gọi OAuth refresh_token grant (không cần
Claude Code), nên chạy độc lập.

Cơ chế:
- Refresh token lưu ở file .tiktok_refresh (JSON {refresh_token, client_id}).
- Mỗi lần chạy: gọi refresh -> nhận access_token MỚI + refresh_token MỚI (TikTok
  xoay vòng refresh token), LƯU LẠI refresh token mới, rồi đẩy access token lên
  Railway. Chạy launchd nhiều cữ/ngày -> token luôn tươi.
- Refresh token sống ~30 ngày và được gia hạn mỗi lần refresh -> chỉ cần chạy ít
  nhất 1 lần trong ~30 ngày là chuỗi không đứt. Nếu đứt (báo dưới), authorize lại:
      claude mcp logout tiktok-ads && claude mcp login tiktok-ads
  rồi chạy: python3 sync_token.py --bootstrap
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FLAT_URL = "https://business-api.tiktok.com/open_mcp/tt-ads-mcp-flat"
TOKEN_EP = FLAT_URL + "/oauth/token"
ADVERTISER_ID = "7139812447623446530"
RAILWAY_PROJECT = "eaea6f2e-fea0-4ef5-b789-63437560488a"
RAILWAY_SERVICE = "doctorlaser"
RT_FILE = ROOT / ".tiktok_refresh"  # {refresh_token, client_id} — ĐỪNG commit


def _load_rt() -> dict | None:
    if RT_FILE.exists():
        try:
            j = json.loads(RT_FILE.read_text())
            if j.get("refresh_token") and j.get("client_id"):
                return j
        except Exception:
            pass
    return None


def _bootstrap_from_keychain() -> dict | None:
    """Lần đầu: lấy refresh token TỐT NHẤT (server có quyền advertiser) từ Keychain."""
    try:
        raw = subprocess.check_output(
            ["security", "find-generic-password", "-s", "Claude Code-credentials", "-w"],
            stderr=subprocess.DEVNULL).decode()
    except Exception:
        return None
    d = json.loads(raw).get("mcpOAuth", {})
    cands = [v for k, v in d.items()
             if "tiktok" in k.lower() and isinstance(v, dict)
             and v.get("refreshToken") and v.get("clientId")
             and "tt-ads-mcp-flat" in (v.get("serverUrl") or "")]
    for v in cands:
        try:
            at, rt = _refresh(v["refreshToken"], v["clientId"])
        except Exception:
            continue
        if _token_ok(at):
            _save_rt(rt, v["clientId"])
            return {"refresh_token": rt, "client_id": v["clientId"]}
    return None


def _save_rt(refresh_token: str, client_id: str) -> None:
    RT_FILE.write_text(json.dumps({"refresh_token": refresh_token, "client_id": client_id}))


def _refresh(refresh_token: str, client_id: str) -> tuple[str, str]:
    """Đổi refresh_token -> (access_token mới, refresh_token mới)."""
    body = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
    }).encode()
    req = urllib.request.Request(TOKEN_EP, data=body, headers={
        "Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"})
    resp = json.loads(urllib.request.urlopen(req, timeout=30).read())
    return resp["access_token"], resp["refresh_token"]


def _token_ok(access_token: str) -> bool:
    """Access token phải gọi được tools/call với code 0 (có quyền advertiser)."""
    h = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json",
         "Accept": "application/json, text/event-stream"}
    payload = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
        "name": "report_integrated_get", "arguments": {
            "advertiser_id": ADVERTISER_ID, "report_type": "BASIC",
            "data_level": "AUCTION_CAMPAIGN", "dimensions": ["campaign_id"],
            "metrics": ["campaign_name", "spend"],
            "start_date": "2026-08-01", "end_date": "2026-08-01", "page_size": 1}}}
    for attempt in range(2):
        try:
            req = urllib.request.Request(FLAT_URL, data=json.dumps(payload).encode(), headers=h)
            s = urllib.request.urlopen(req, timeout=40).read().decode().strip()
            if s.startswith(("event:", "data:")):
                for line in s.splitlines():
                    if line.startswith("data:"):
                        s = line[5:].strip()
                        break
            code = json.loads(json.loads(s)["result"]["content"][0]["text"]).get("code")
            if code == 0:
                return True
        except Exception:
            pass
        time.sleep(4)  # token mới có thể cần vài giây để hiệu lực
    return False


def _push_railway(access_token: str) -> bool:
    for attempt in range(3):
        r = subprocess.run(
            ["railway", "variables", "--set", f"TIKTOK_MCP_TOKEN={access_token}",
             "-p", RAILWAY_PROJECT, "-e", "production", "-s", RAILWAY_SERVICE],
            capture_output=True, timeout=60)
        if r.returncode == 0:
            return True
        if attempt == 2:
            print("❌ push lỗi:", (r.stderr.decode() or r.stdout.decode())[:150])
    return False


def main() -> None:
    bootstrap = "--bootstrap" in sys.argv
    check_only = "--check" in sys.argv

    state = _load_rt()
    if state is None or bootstrap:
        print("… chưa có refresh token trong file, lấy từ Keychain (bootstrap)…")
        state = _bootstrap_from_keychain()
        if state is None:
            print("❌ Không bootstrap được. Authorize lại rồi chạy --bootstrap:")
            print("   claude mcp logout tiktok-ads && claude mcp login tiktok-ads")
            raise SystemExit(1)
        print("✅ Bootstrap xong, đã lưu refresh token.")

    # TikTok đôi khi cấp access token CHƯA gắn quyền advertiser (code 40001) dù
    # refresh thành công. Refresh lại vài lần tới khi được token code 0. Mỗi lần
    # refresh xoay refresh token -> LƯU LẠI ngay để không đứt chuỗi.
    rt = state["refresh_token"]
    cid = state["client_id"]
    good_token = None
    for attempt in range(5):
        try:
            access_token, rt = _refresh(rt, cid)
        except urllib.error.HTTPError as e:
            print(f"❌ Refresh thất bại (HTTP {e.code}): refresh token có thể đã hết hạn ~30 ngày.")
            print("   Authorize lại: claude mcp logout tiktok-ads && claude mcp login tiktok-ads")
            print("   rồi chạy: python3 sync_token.py --bootstrap")
            raise SystemExit(1)
        _save_rt(rt, cid)  # lưu refresh token mới NGAY (xoay vòng)
        if _token_ok(access_token):
            good_token = access_token
            break
        print(f"   … lần {attempt + 1}: token chưa có quyền (40001), refresh lại…")

    if not good_token:
        print("🔴 Sau 5 lần refresh vẫn chưa lấy được token có quyền advertiser. Thử lại sau.")
        raise SystemExit(1)
    print(f"✅ Có access token hợp lệ (len {len(good_token)}).")
    if check_only:
        return
    if _push_railway(good_token):
        print("🎉 Đã đẩy token lên Railway.")


if __name__ == "__main__":
    main()
