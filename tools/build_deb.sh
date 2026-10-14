#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
# 核心P0未验收时只允许明确的本地候选构建，不暗示适配通过。
if [ "${1:-}" != "--candidate" ]; then
    python3 "$ROOT/tools/check_release.py" --root "$ROOT" --strict
fi
if [ "${1:-}" = "--candidate" ]; then shift; fi
python3 "$ROOT/packaging/build_deb.py" --root "$ROOT" "$@"
