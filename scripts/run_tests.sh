#!/bin/bash
# キットの動作確認をまとめて行う。すべて一時フォルダの中で動き、キットのフォルダには何も書きません。
# ネットにはつなぎません。投稿・送信もしません。有料の API（Gemini など）は使いません。
#
# 使い方:
#   bash scripts/run_tests.sh          … 速い点検（約30秒。動画・音声は作らない）
#   bash scripts/run_tests.sh --full   … 動画・音声・サムネまで実際に作る（Mac か Linux。数分かかる）
#       Linux は先に: sudo apt-get install ffmpeg fonts-noto-cjk open-jtalk open-jtalk-mecab-naist-jdic hts-voice-nitech-jp-atr503-m001
#   bash scripts/run_tests.sh --full --keep   … 作ったものを消さずに残す（場所を最後に表示）
#
# 終了コード: 0 = 全部合格 / 1 = 不合格あり
set -u
KIT="$(cd "$(dirname "$0")/.." && pwd)"
SK="$KIT/.claude/skills"
PY="$(command -v python3 || command -v python)"
FULL=0; KEEP=0
for a in "$@"; do
  case "$a" in --full) FULL=1 ;; --keep) KEEP=1 ;; esac
done
W="$(mktemp -d "${TMPDIR:-/tmp}/kit-test-XXXXXX")"
PASS=0; FAIL=0; LOG="$W/test.log"
export PYTHONDONTWRITEBYTECODE=1

# step 名前 期待する終了コード（空白区切りで複数可） コマンド...
step() {
  local name="$1" want="$2"; shift 2
  "$@" >>"$LOG" 2>&1
  local rc=$?
  if [[ " $want " == *" $rc "* ]]; then
    PASS=$((PASS+1)); printf "PASS  rc=%-3s %s\n" "$rc" "$name"
  else
    FAIL=$((FAIL+1)); printf "FAIL  rc=%-3s %s （期待 %s）\n" "$rc" "$name" "$want"
    echo "      ↳ ログ: $LOG"
  fi
}

echo "== キットの点検  $(date '+%Y-%m-%d %H:%M:%S') =="
echo "キット: $KIT"
echo "作業場: $W"

# --- 0 キットの形 ---
step "kit_doctor（スキル・担当・秘密の混入）" "0" "$PY" "$KIT/scripts/kit_doctor.py"
step "selftest（全スキルの試し運転）" "0 2" "$PY" "$SK/kit-setup/scripts/selftest.py" --skills "$SK"
step "make_workspace（作業フォルダ）" "0" "$PY" "$SK/kit-setup/scripts/make_workspace.py" --base "$W/kit-work"
step "install_skills --dry-run（別フォルダへ）" "0" "$PY" "$SK/kit-setup/scripts/install_skills.py" --target project --project "$W/proj" --dry-run --with-agents
step "install_skills（別フォルダへ本番）" "0" "$PY" "$SK/kit-setup/scripts/install_skills.py" --target project --project "$W/proj" --with-agents
step "install_skills（2回目＝同じなので何もしない）" "0" "$PY" "$SK/kit-setup/scripts/install_skills.py" --target project --project "$W/proj" --with-agents
step "env_check（道具の点検）" "0 1" "$PY" "$SK/kit-setup/scripts/env_check.py"

# --- 1 リサーチ ---
step "yt-research new" "0" "$PY" "$SK/yt-research/scripts/research_board.py" new --theme "固定費の見直し" --out "$W/kit-work/research" --count 5
BOARD="$(ls "$W"/kit-work/research/*.md | head -1)"
step "yt-research check（空のボード → NG が出る）" "1" "$PY" "$SK/yt-research/scripts/research_board.py" check "$BOARD"
"$PY" - "$BOARD" <<'EOF'
import sys, re
p = sys.argv[1]; s = open(p, encoding="utf-8").read()
for i in range(1, 6):
    s = s.replace("### 候補%d\n- 仮タイトル: \n- 悩み: \n- 骨組み: \n- 出典: \n- 形: " % i,
        "### 候補%d\n- 仮タイトル: 固定費を見直す順番その%d\n- 悩み: 手取りが少なくお金が残らない\n- 骨組み: 書き出す → 印をつける → 1つやめる\n- 出典: https://www.example.com/%d\n- 形: YouTube" % (i, i, i))
s = s.replace("## おすすめの3つ\n1. \n2. \n3. ", "## おすすめの3つ\n1. 候補1 理由\n2. 候補2 理由\n3. 候補3 理由")
open(p, "w", encoding="utf-8").write(s)
EOF
step "yt-research check（埋めたボード → 合格）" "0" "$PY" "$SK/yt-research/scripts/research_board.py" check "$BOARD"

# --- 2 台本 ---
mkdir -p "$W/kit-work/youtube/sample"
cp "$KIT/samples/youtube/script.json" "$KIT/samples/youtube/concepts.json" "$W/kit-work/youtube/sample/"
step "yt-script check_script（見本の台本）" "0" "$PY" "$SK/yt-script/scripts/check_script.py" "$W/kit-work/youtube/sample/script.json" --target-sec 45

# --- 3 字幕の改行ルール（3スキル共通の部品） ---
for s in yt-video short-clip short-from-article; do
  step "$s test_jp_linebreak" "0" "$PY" "$SK/$s/scripts/test_jp_linebreak.py"
done

# --- 4 note・SNS・週報・秘書・運用 ---
cat > "$W/note.md" <<'EOF'
# 家計簿が続かない人のための3つの手順

## はじめに
家計簿が続かない理由は、記録が多すぎることです。

## 手順1 記録は1日1回だけにする
夜に1回だけ、レシートをまとめて入れます。

=== ここから有料 ===

## 手順2 項目は5つまで
EOF
step "note-article check_draft（短い見本 → 字数不足で NG）" "1" "$PY" "$SK/note-article/scripts/check_draft.py" "$W/note.md"
step "sns-to-note make_week_plan" "0" "$PY" "$SK/sns-to-note/scripts/make_week_plan.py" "$W/note.md" --start 2026-11-16 --out "$W/sns_week" --platform X
# 有料ラインの目印（note-article と sns-to-note で共通の「=== ここから有料 ===」。古い形も読めること）
paid_test() {  # $1 = 目印の行
  local d="$W/paid_$RANDOM"; mkdir -p "$d"
  printf '# 題名\n\n## 無料の見出しA\n本文\n\n%s\n\n## 有料の見出しZ\n秘密の手順\n' "$1" > "$d/a.md"
  "$PY" "$SK/sns-to-note/scripts/make_week_plan.py" "$d/a.md" --start 2026-11-16 --out "$d/out" --platform X || return 1
  grep -q "無料の見出しA" "$d/out/posts.md" "$d/out/plan.md" || return 1
  ! grep -q "有料の見出しZ" "$d/out/posts.md" || return 1
  ! grep -q "秘密の手順" "$d/out/posts.md" "$d/out/plan.md" || return 1
}
step "有料ライン（新しい目印）→ 有料の見出しが投稿に出ない" "0" paid_test "=== ここから有料 ==="
step "有料ライン（古い目印）→ 有料の見出しが投稿に出ない" "0" paid_test "――――― ここから有料（有料ライン） ―――――"
printf '# 題名\n\n## 無料\n本文\n\n=== ここから有料 ===\n\n## 有料\n' > "$W/paidmark.md"
step "note-article check_draft が目印を見つける" "0" bash -c "\"$PY\" \"$SK/note-article/scripts/check_draft.py\" \"$W/paidmark.md\" | grep -q '有料ラインの印：あり'"
step "note-article SKILL.md の目印が共通の形" "0" grep -q "^=== ここから有料 ===$" "$SK/note-article/SKILL.md"
step "sns-to-note check_posts（見本の下書き）" "0" "$PY" "$SK/sns-to-note/scripts/check_posts.py" "$KIT/samples/sns/sample_posts.md"
cp "$KIT/samples/sns/sample_posts.md" "$W/kit-work/sns/2026-11-10_sample.md"
step "sns-post check_drafts（見本 → 合格）" "0" "$PY" "$SK/sns-post/scripts/check_drafts.py" "$W/kit-work/sns/2026-11-10_sample.md"
cp "$KIT/samples/sns/sample_posts.md" "$W/kit-work/sns/2026-11-11_copy.md"
step "sns-post check_drafts --past（使い回し → NG）" "1" "$PY" "$SK/sns-post/scripts/check_drafts.py" "$W/kit-work/sns/2026-11-11_copy.md" --past "$W/kit-work/sns"
printf '## 投稿1｜X｜言い切り\nこの方法なら誰でも稼げます。必ず結果が出ます。#a #b #c\n' > "$W/bad.md"
step "sns-post check_drafts（言い過ぎ → NG）" "1" "$PY" "$SK/sns-post/scripts/check_drafts.py" "$W/bad.md"
step "sns-post review_posts（見本の数字）" "0" "$PY" "$SK/sns-post/scripts/review_posts.py" "$KIT/samples/sns/sample_metrics.csv" --out "$W/kit-work/reports"
step "secretary add" "0" "$PY" "$SK/secretary/scripts/secretary.py" --dir "$W/sec" --date 2026-11-10 add "請求書を送る 期限:11/12 優先:高"
step "secretary add（期限切れ）" "0" "$PY" "$SK/secretary/scripts/secretary.py" --dir "$W/sec" --date 2026-11-10 add "台本の確認 期限:11/08"
step "secretary summary" "0" "$PY" "$SK/secretary/scripts/secretary.py" --dir "$W/sec" --date 2026-11-10 summary
step "secretary remind" "0" "$PY" "$SK/secretary/scripts/secretary.py" --dir "$W/sec" --date 2026-11-10 remind --days 3
step "secretary run_daily.sh（相対パス → 断る）" "2" bash "$SK/secretary/scripts/run_daily.sh" "relative/path"
step "secretary run_daily.sh（絶対パス）" "0" bash "$SK/secretary/scripts/run_daily.sh" "$W/sec"
step "yt-ops init" "0" "$PY" "$SK/yt-ops/scripts/ops.py" init --dir "$W/ops" --name "ゆる家計ラボ" --days 火,金 --pillars "固定費,貯金,買い物" --audience "一人暮らしの会社員"
step "yt-ops add" "0" "$PY" "$SK/yt-ops/scripts/ops.py" add --dir "$W/ops" --title "固定費を見直す3つの方法"
step "yt-ops week" "0" "$PY" "$SK/yt-ops/scripts/ops.py" week --dir "$W/ops"
step "yt-ops review（見本の CSV）" "0" "$PY" "$SK/yt-ops/scripts/ops.py" review --dir "$W/ops" --csv "$SK/yt-ops/templates/sample_studio_export.csv"
step "weekly-report（CSV・タスクつき）" "0" "$PY" "$SK/weekly-report/scripts/weekly_report.py" --work "$W/kit-work" --yt-csv "$SK/yt-ops/templates/sample_studio_export.csv" --sns-csv "$KIT/samples/sns/sample_metrics.csv" --tasks "$W/sec"
step "short-clip transcribe（whisper 無し → 案内して rc=2）" "0 2" "$PY" "$SK/short-clip/scripts/transcribe.py" "$W/none.mp4"
step "short-from-article check_scripts（見本の台本3本）" "0" "$PY" "$SK/short-from-article/scripts/check_scripts.py" "$KIT/samples/shorts/scripts.json"

# --- 5 動画・音声・サムネ（--full のときだけ。Mac の say を使う） ---
if [ "$FULL" = 1 ]; then
  Y="$W/kit-work/youtube/sample"
  step "yt-narration（内蔵の声）" "0" "$PY" "$SK/yt-narration/scripts/narrate.py" "$Y/script.json" --out "$Y/narration" --mp3
  step "yt-video モードA（スライド動画＋長さ照合）" "0" "$PY" "$SK/yt-video/scripts/make_video.py" --script "$Y/script.json" --narration "$Y/narration" --out "$Y/video/video.mp4"
  step "yt-thumbnail（3案 → PNG）" "0" "$PY" "$SK/yt-thumbnail/scripts/render_thumbnail.py" "$Y/concepts.json" --out "$Y/thumbnail"
  step "yt-video モードB probe" "0" "$PY" "$SK/yt-video/scripts/vedit.py" probe "$Y/video/video.mp4"
  step "yt-video モードB silence（無音詰めの下書き）" "0" "$PY" "$SK/yt-video/scripts/vedit.py" silence "$Y/video/video.mp4" --out "$Y/edit/edit.json"
  step "yt-video モードB check" "0" "$PY" "$SK/yt-video/scripts/vedit.py" check "$Y/edit/edit.json"
  step "yt-video モードB render（実物の長さ照合）" "0" "$PY" "$SK/yt-video/scripts/vedit.py" render "$Y/edit/edit.json"
  S="$W/kit-work/shorts"
  step "見本の長尺動画を作る（23.976fps）" "0" "$PY" "$KIT/samples/shorts/make_sample_long.py" "$S/long"
  step "short-clip find_segments" "0" "$PY" "$SK/short-clip/scripts/find_segments.py" "$S/long/yurukakei_long_sample.mp4" "$S/long/yurukakei_long_sample.srt" --count 2 --out "$S/segments.json"
  step "short-clip make_clips（縦長・字幕・長さ照合）" "0" "$PY" "$SK/short-clip/scripts/make_clips.py" "$S/segments.json" --outdir "$S/clips"
  cp "$KIT/samples/shorts/scripts.json" "$S/scripts.json"
  step "short-from-article render_short（say）" "0" "$PY" "$SK/short-from-article/scripts/render_short.py" "$S/scripts.json" --index 1 --tts say --outdir "$S/from_article"
fi

echo "== 結果: PASS $PASS / FAIL $FAIL  $(date '+%Y-%m-%d %H:%M:%S') =="
if [ "$KEEP" = 1 ] || [ "$FAIL" != 0 ]; then
  echo "作ったもの・ログはここに残しました: ${W} （ログ: ${LOG}）"
else
  rm -rf "$W"
fi
[ "$FAIL" = 0 ]
