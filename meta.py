"""Kết nối Meta (Facebook) Marketing API — lấy chi phí & hiệu quả ads/campaign.

Dùng Graph API insights của Ad Account. Chỉ đọc (theo dõi), không sửa campaign.
"""

import json
import time

import requests

import config

_cache: dict = {}


def _base() -> str:
    return f"https://graph.facebook.com/{config.META_API_VERSION}"


def _account() -> str:
    acct = config.META_AD_ACCOUNT_ID.strip()
    return acct if acct.startswith("act_") else f"act_{acct}"


def _vnd(x: float) -> str:
    return f"{int(round(x)):,}".replace(",", ".") + "đ"


def _get_insights(since: str, until: str, level: str = "campaign") -> list[dict]:
    fields = (
        "campaign_name,spend,impressions,clicks,ctr,cpc,reach,"
        "actions,cost_per_action_type"
    )
    params = {
        "level": level,
        "fields": fields,
        "time_range": json.dumps({"since": since, "until": until}),
        "limit": 200,
        "access_token": config.META_ACCESS_TOKEN,
    }
    rows: list[dict] = []
    resp = requests.get(f"{_base()}/{_account()}/insights", params=params, timeout=60)
    if resp.status_code != 200:
        raise RuntimeError(f"Meta API lỗi ({resp.status_code}): {resp.text[:300]}")
    body = resp.json()
    rows += body.get("data", [])
    # Phân trang
    guard = 0
    while body.get("paging", {}).get("next") and guard < 50:
        guard += 1
        r = requests.get(body["paging"]["next"], timeout=60)
        if r.status_code != 200:
            break
        body = r.json()
        rows += body.get("data", [])
    return rows


def get_insights(since: str, until: str, force: bool = False) -> list[dict]:
    key = f"{since}:{until}"
    now = time.time()
    hit = _cache.get(key)
    if not force and hit and (now - hit[0]) < config.KIOTVIET_CACHE_TTL:
        return hit[1]
    data = _get_insights(since, until)
    _cache[key] = (now, data)
    return data


def _results(row: dict) -> int:
    """Đếm 'kết quả' chính: tin nhắn + lead (tùy mục tiêu campaign)."""
    total = 0.0
    for a in row.get("actions") or []:
        at = a.get("action_type", "")
        if "messaging_conversation_started" in at or at in (
            "lead",
            "onsite_conversion.lead_grouped",
        ):
            total += float(a.get("value") or 0)
    return int(total)


def build_summary(rows: list[dict], label: str) -> str:
    if not rows:
        return f"FACEBOOK ADS — {label}\nKhông có dữ liệu campaign trong kỳ."

    spend = sum(float(r.get("spend") or 0) for r in rows)
    impr = sum(float(r.get("impressions") or 0) for r in rows)
    clicks = sum(float(r.get("clicks") or 0) for r in rows)
    results = sum(_results(r) for r in rows)
    cpl = spend / results if results else 0

    parts = [
        f"FACEBOOK ADS — {label}",
        f"- Tổng chi: {_vnd(spend)}",
        f"- Hiển thị: {int(impr):,}".replace(",", ".") + f" | Click: {int(clicks)}",
        f"- Kết quả (tin nhắn/lead): {results}",
        f"- CPL (giá 1 kết quả): {_vnd(cpl) if results else 'n/a'}",
        "",
        "Theo campaign (chi | kết quả | CPL):",
    ]
    ranked = sorted(rows, key=lambda r: -float(r.get("spend") or 0))
    for r in ranked[:15]:
        s = float(r.get("spend") or 0)
        res = _results(r)
        c = (s / res) if res else 0
        name = (r.get("campaign_name") or "(không tên)")[:30]
        parts.append(
            f"  • {name}: {_vnd(s)} | {res} kết quả | "
            + (f"CPL {_vnd(c)}" if res else "CPL n/a")
        )
    return "\n".join(parts)
