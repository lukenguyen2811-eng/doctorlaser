#!/bin/sh
# Chạy song song với tai_goc.py: mỗi CHU_KY giây, tháng nào có ảnh mới tải về (anh_goc/YYYY-MM)
# thì đọc nhãn lại (quet --ocr, KHÔNG tải gì từ iCloud) rồi ghép -> có ảnh nào làm ảnh đó, không đợi hết tháng.
#   nohup sh tu_dong_ghep.sh > ~/anh_thu/tu_dong.log 2>&1 &      (dừng: pkill -f tu_dong_ghep.sh)
# Phần đã duyệt không bị đụng (quet/ghep chỉ ghi cột gợi ý).
cd "$(dirname "$0")" || exit 1
MOC="${MOC:-$HOME/anh_thu/moc}"; CHU_KY="${CHU_KY:-600}"
mkdir -p "$MOC"
while true; do
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
  sleep "$CHU_KY"
done
