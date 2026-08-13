#!/usr/bin/env sh
# Xem trang thai cua ca 2 repo: doctorlaser + kiot.
# Cach dung: ./scripts/team.sh
#
# Script doc STATUS.md tu thu muc anh em (2 repo clone canh nhau).
# Neu repo kia chua co trong may, script in cach lay ve.

set -eu

REPOS="doctorlaser kiot"
OWNER="lukenguyen2811-eng"

here=$(cd "$(dirname "$0")/.." && pwd)
parent=$(dirname "$here")
missing=0

for name in $REPOS; do
    dir="$parent/$name"
    printf '\n========================= %s =========================\n' "$name"

    if [ -f "$dir/STATUS.md" ]; then
        if [ -d "$dir/.git" ]; then
            branch=$(git -C "$dir" rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?')
            head=$(git -C "$dir" log -1 --format='%h %s' 2>/dev/null || echo '?')
            printf '[git] nhanh: %s | HEAD: %s\n' "$branch" "$head"
            if [ -n "$(git -C "$dir" status --porcelain 2>/dev/null)" ]; then
                printf '[git] CANH BAO: dang co thay doi chua commit\n'
            fi
            printf -- '---\n'
        fi
        cat "$dir/STATUS.md"
    else
        missing=1
        printf 'Khong tim thay %s/STATUS.md\n' "$dir"
        printf 'Lay repo nay ve de xem trang thai:\n'
        printf '  git clone https://github.com/%s/%s %s\n' "$OWNER" "$name" "$dir"
    fi
done

printf '\n'
exit $missing
