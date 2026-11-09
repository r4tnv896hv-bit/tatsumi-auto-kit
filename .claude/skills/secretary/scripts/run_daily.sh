#!/bin/bash
# 毎朝の自動実行用：メモの取り込み → 今日のまとめ → リマインド下書き
# 使い方: run_daily.sh /Users/あなた/secretary
# 定期実行（cron）はホームディレクトリで動くので、必ず絶対パスを渡してください。
# このスクリプトはファイルを書くだけです。どこにも送信しません。
set -u
DIR="${1:-}"
if [ -z "$DIR" ] || [ "${DIR#/}" = "$DIR" ]; then
  echo "データの置き場所を絶対パスで渡してください（例: run_daily.sh /Users/あなた/secretary）" >&2
  exit 2
fi
HERE="$(cd "$(dirname "$0")" && pwd)"
PY="$(command -v python3 || echo /usr/bin/python3)"
mkdir -p "$DIR/logs"
LOG="$DIR/logs/run_$(date +%Y-%m-%d).log"
{
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') 開始 ==="
  rc=0
  if [ -s "$DIR/inbox.md" ]; then
    "$PY" "$HERE/secretary.py" --dir "$DIR" intake "$DIR/inbox.md" --clear || rc=1
  else
    echo "inbox.md は空なので取り込みは飛ばします"
  fi
  "$PY" "$HERE/secretary.py" --dir "$DIR" summary || rc=1
  "$PY" "$HERE/secretary.py" --dir "$DIR" remind --days 1 || rc=1
  echo "=== 終了 rc=$rc ==="
} >> "$LOG" 2>&1
exit $rc
