#!/bin/sh
# Chạy song song với tai_goc.py: mỗi CHU_KY giây, tháng nào có ảnh mới tải về (anh_goc/YYYY-MM)
# thì đọc nhãn lại (quet --ocr, KHÔNG tải gì từ iCloud) rồi ghép -> có ảnh nào làm ảnh đó, không đợi hết tháng.
#   nohup sh tu_dong_ghep.sh > ~/anh_thu/tu_dong.log 2>&1 &      (dừng: pkill -f tu_dong_ghep.sh)
# Phần đã duyệt không bị đụng (quet/ghep chỉ ghi cột gợi ý).
cd "$(dirname "$0")" || exit 1
MOC="${MOC:-$HOME/anh_thu/moc}"; CHU_KY="${CHU_KY:-600}"
mkdir -p "$MOC"
VONG=0
while true; do
  # Mỗi giờ (6 vòng x 10'): kéo hóa đơn KiotViet tháng này (+ tháng trước trong 3 ngày đầu tháng) để ảnh mới có HĐ mà ghép
  if [ $((VONG % 6)) -eq 0 ]; then
    for m in $(date +%Y-%m) $( [ "$(date +%d)" -le 3 ] && date -v-1m +%Y-%m ); do
      if .venv/bin/python anhkhach.py hoadon "$m" > /dev/null 2>&1; then rm -f "$MOC/$m"; else echo "  ! lỗi kéo hóa đơn $m"; fi
    done
  fi
  VONG=$((VONG + 1))
  for d in anh_goc/[0-9][0-9][0-9][0-9]-[0-9][0-9]; do
    [ -d "$d" ] || continue
    m=$(basename "$d"); moc="$MOC/$m"
    if [ ! -f "$moc" ] || [ -n "$(find "$d" -type f -newer "$moc" -name '*.*' 2>/dev/null | head -1)" ]; then
      touch "$moc.tam"   # ảnh về trong lúc đang quét sẽ được tính ở vòng sau
      echo "== $m $(date +%H:%M) có ảnh mới"
      if .venv/bin/python anhkhach.py quet "$m" --ocr | tail -1 && .venv/bin/python anhkhach.py ghep "$m" | grep -E "Chắc|Gợi|Chưa"; then
        mv "$moc.tam" "$moc"
      else
        echo "  ! lỗi tháng $m — thử lại vòng sau"
      fi
    fi
  done
  # Mỗi giờ (cùng vòng kéo hóa đơn): ghép lại tháng trước + tháng này rồi TỰ DUYỆT (CEO 16/10 lần 9). Tắt: TU_DUYET=0.
  # --lap 3: xét lại cả ảnh đã tự duyệt, ảnh đổi HĐ giữa các lượt thì bỏ; không bao giờ đụng ảnh người đã duyệt.
  if [ "${TU_DUYET:-1}" = "1" ] && [ $(((VONG - 1) % 6)) -eq 0 ]; then
    TRUOC=$(date -v-1m +%Y-%m); NAY=$(date +%Y-%m)
    for m in "$TRUOC" "$NAY"; do
      .venv/bin/python anhkhach.py ghep "$m" > /dev/null 2>&1 || echo "  ! lỗi ghép $m trước tự duyệt"
    done
    echo "== tự duyệt $TRUOC $NAY $(date +%H:%M)"
    .venv/bin/python anhkhach.py tu_duyet "$TRUOC" "$NAY" --lap 3 | tail -3 || echo "  ! lỗi tự duyệt"
  fi
  sleep "$CHU_KY"
done
