"""Chỉ mục ẢNH ĐIỀU TRỊ trên app KIOT (/api/ingest/anh-khach).

Ảnh KHÔNG rời máy Mac / Google Drive — KIOT chỉ giữ chỉ mục theo hóa đơn
(ngày, dịch vụ, số ảnh trước/sau, link mở ảnh) để nhân viên mở hóa đơn hoặc
hồ sơ khách trên KIOT là thấy "buổi này có ảnh" và bấm mở.

- anhkhach.py (Mac mini) đẩy chỉ mục lên:   day_chi_muc(items)
- bot Telegram (/anh) tra cứu:               tra_cuu(chuoi)
"""

from __future__ import annotations

import os
import re

import requests

KIOT_URL = os.environ.get("KIOT_URL", "https://kiot-production.up.railway.app")
_DUONG = "/api/ingest/anh-khach"
_TOI_DA = 500  # KIOT nhận tối đa 500 dòng / lần


def _token() -> str:
    tok = os.environ.get("KIOT_INGEST_TOKEN") or os.environ.get("INGEST_TOKEN") or ""
    if not tok:
        raise RuntimeError(
            "Thiếu KIOT_INGEST_TOKEN (copy INGEST_TOKEN từ service kiot trên Railway vào .env)"
        )
    return tok


def day_chi_muc(items: list[dict]) -> dict:
    """Đẩy chỉ mục ảnh lên KIOT (ghi đè theo mã hóa đơn). Trả tổng kết."""
    tong = {"them": 0, "cap_nhat": 0, "loi": []}
    for i in range(0, len(items), _TOI_DA):
        r = requests.post(
            KIOT_URL + _DUONG,
            headers={"x-ingest-token": _token(), "Content-Type": "application/json"},
            json={"items": items[i : i + _TOI_DA]},
            timeout=60,
        )
        if r.status_code != 200:
            raise RuntimeError(f"KIOT lỗi {r.status_code}: {r.text[:200]}")
        body = r.json()
        tong["them"] += int(body.get("them") or 0)
        tong["cap_nhat"] += int(body.get("cap_nhat") or 0)
        tong["loi"] += body.get("loi") or []
    return tong


def phan_loai(chuoi: str) -> tuple[str, str]:
    """'0909 123 456' -> ('sdt', '0909123456'); 'HD012345' -> ('hoa_don', ...); còn lại mã KH."""
    s = (chuoi or "").strip()
    so = re.sub(r"\D", "", s)
    chi_so = len(so) == len(re.sub(r"[\s.\-+]", "", s))  # toàn chữ số (cho phép cách/chấm/+)
    if so.startswith("84") and len(so) == 11:
        so = "0" + so[2:]
    elif len(so) == 9 and not so.startswith("0"):  # Excel hay mất số 0 đầu
        so = "0" + so
    if chi_so and len(so) >= 9:
        return "sdt", so
    if s.upper().startswith("HD"):
        return "hoa_don", s.upper()
    return "ma_kh", s.upper()


def tra_cuu(chuoi: str) -> list[dict]:
    """Các buổi có ảnh của 1 khách / 1 hóa đơn, mới nhất trước."""
    khoa, gia_tri = phan_loai(chuoi)
    r = requests.get(
        KIOT_URL + _DUONG,
        headers={"x-ingest-token": _token()},
        params={khoa: gia_tri},
        timeout=30,
    )
    if r.status_code != 200:
        raise RuntimeError(f"KIOT lỗi {r.status_code}: {r.text[:200]}")
    return r.json().get("items") or []


def dinh_dang(items: list[dict]) -> str:
    """Tin nhắn Telegram (HTML) liệt kê các buổi có ảnh."""
    import html

    if not items:
        return "Chưa có ảnh nào được gắn cho khách / hóa đơn này."
    dau = items[0]
    dong = [f"📷 <b>{html.escape(dau.get('ten_kh') or '')}</b> · {html.escape(dau.get('ma_kh') or '')}"
            f" · {html.escape(dau.get('sdt') or '')}", f"{len(items)} buổi có ảnh:"]
    for it in items[:30]:
        loai = it.get("loai") or {}
        chi_tiet = " / ".join(f"{ten} {loai[k]}" for k, ten in
                              (("truoc", "trước"), ("trong", "trong"), ("sau", "sau")) if loai.get(k))
        dong.append(
            f"• {html.escape(it.get('ngay') or '')} · {html.escape((it.get('dich_vu') or '')[:40])}"
            f" · {int(it.get('so_anh') or 0)} ảnh{f' ({chi_tiet})' if chi_tiet else ''}"
            f" · HĐ {html.escape(it.get('hoa_don') or '')}"
            + (f' · <a href="{html.escape(it["link_xem"])}">Mở ảnh</a>' if it.get("link_xem") else "")
        )
    if len(items) > 30:
        dong.append(f"… và {len(items) - 30} buổi cũ hơn (xem đủ trên KIOT).")
    return "\n".join(dong)
