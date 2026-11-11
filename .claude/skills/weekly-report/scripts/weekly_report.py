# -*- coding: utf-8 -*-
r"""1週間の「週報」を作る。作業フォルダの中のファイルと、ご本人が渡した CSV の数字だけを使います。
ネットにはつなぎません。どこにも送りません。

使い方:
  python3 weekly_report.py --work /絶対パス/kit-work
  python3 weekly_report.py --work /絶対パス/kit-work --days 7 \
      --yt-csv /絶対パス/表データ.csv \           ← YouTube Studio の書き出し（任意）
      --sns-csv /絶対パス/metrics.csv \           ← sns-post の数字表（任意）
      --tasks /絶対パス/secretary                  ← secretary スキルのデータ（任意）

できるもの:  <work>/reports/YYYY-MM-DD_weekly.md（同名があれば _2, _3 …）
中身:
  1 今週作ったもの   research / youtube / shorts / note / sns の中で、期間内に作った・直したファイルの数と一覧
  2 YouTube の数字   視聴回数の多い順に5本（CSV の数字だけ。合計の行は飛ばす）
  3 SNS の数字       媒体ごとの本数・表示の合計・反応率の中央値
  4 タスク           期限切れ・7日以内・今週終えたもの（secretary の tasks.json）
  5 来週の提案       空欄（Claude が 1〜4 を読んで最大3つ書く。決めるのはご本人）
終了コード: 0 = 作れた / 2 = 使い方の誤り
"""
import argparse
import csv
import datetime as dt
import json
import os
import re
import statistics
import sys

AREAS = [("research", "リサーチ"), ("youtube", "YouTube"), ("shorts", "ショート"), ("note", "note"), ("sns", "SNS")]
SKIP = {".DS_Store", "Thumbs.db"}


def recent_files(base, since):
    out = []
    if not os.path.isdir(base):
        return out
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
        for f in files:
            if f in SKIP or f.startswith("."):
                continue
            p = os.path.join(root, f)
            try:
                m = os.path.getmtime(p)
            except OSError:
                continue
            if m >= since:
                out.append((m, os.path.relpath(p, base)))
    return sorted(out, reverse=True)


def num(s):
    s = (s or "").replace(",", "").replace("%", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def yt_section(path):
    lines = ["## 2 YouTube の数字", ""]
    if not path:
        return lines + ["- CSV を渡されていません（YouTube Studio → アナリティクス → 詳細 → 書き出し → 表データ.csv）", ""]
    if not os.path.isfile(path):
        return lines + ["- CSV が見つかりません: " + path, ""]
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    if not rows:
        return lines + ["- CSV が空です", ""]
    head = rows[0]

    def col(*names):
        for i, h in enumerate(head):
            hl = h.lower()
            if any(n.lower() in hl for n in names):
                return i
        return None
    ti, vi = col("動画のタイトル", "video title"), col("視聴回数", "views")
    ci, ai = col("クリック率", "click-through"), col("平均再生率", "average percentage viewed")
    if ti is None or vi is None:
        return lines + ["- 列が読めません（「表データ.csv」を渡してください）", ""]
    vids = []
    for r in rows[1:]:
        if len(r) <= max(ti, vi) or not r[ti].strip() or r[0].strip() in ("合計", "Total"):
            continue
        v = num(r[vi])
        if v is None:
            continue
        vids.append((v, r[ti].strip(), num(r[ci]) if ci is not None and ci < len(r) else None,
                     num(r[ai]) if ai is not None and ai < len(r) else None))
    vids.sort(reverse=True)
    mt = dt.datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M")
    lines += ["- 元の数字: %s（ファイルの更新 %s）" % (path, mt), "- 動画 %d 本%s" % (len(vids), "（5本未満は参考程度）" if len(vids) < 5 else ""), "",
              "| 順 | タイトル | 視聴回数 | クリック率 | 平均再生率 |", "|---|---|---|---|---|"]
    for i, (v, t, c, a) in enumerate(vids[:5], 1):
        lines.append("| %d | %s | %d | %s | %s |" % (i, t, v, "-" if c is None else "%.1f%%" % c, "-" if a is None else "%.1f%%" % a))
    return lines + [""]


def sns_section(path):
    lines = ["## 3 SNS の数字", ""]
    if not path:
        return lines + ["- 数字表を渡されていません（sns-post の templates/metrics_template.csv の形）", ""]
    if not os.path.isfile(path):
        return lines + ["- CSV が見つかりません: " + path, ""]
    by = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            imp, eng = num(r.get("表示")), num(r.get("反応"))
            if not imp or eng is None:
                continue
            by.setdefault((r.get("媒体") or "不明").strip(), []).append((imp, eng / imp))
    if not by:
        return lines + ["- 読める行がありません（列名「表示」「反応」を確かめる）", ""]
    lines += ["| 媒体 | 本数 | 表示の合計 | 反応率の中央値 |", "|---|---|---|---|"]
    for pf, v in by.items():
        lines.append("| %s | %d | %d | %.1f%% |" % (pf, len(v), sum(x[0] for x in v), statistics.median([x[1] for x in v]) * 100))
    return lines + ["", "- くわしい判定は sns-post の review_posts.py で作る", ""]


def task_section(d, today):
    lines = ["## 4 タスク", ""]
    if not d:
        return lines + ["- secretary のデータを渡されていません", ""]
    p = os.path.join(d, "tasks.json")
    if not os.path.isfile(p):
        return lines + ["- tasks.json がありません: " + p, ""]
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    ts = data.get("tasks", [])
    week_ago, soon = (today - dt.timedelta(days=7)).isoformat(), (today + dt.timedelta(days=7)).isoformat()
    over = [t for t in ts if t.get("status") == "open" and t.get("due") and t["due"] < today.isoformat()]
    near = [t for t in ts if t.get("status") == "open" and t.get("due") and today.isoformat() <= t["due"] <= soon]
    done = [t for t in ts if t.get("status") == "done" and (t.get("done_on") or "") >= week_ago]
    for title, group in (("期限切れ", over), ("7日以内", near), ("今週終えた", done)):
        lines.append("### %s（%d件）" % (title, len(group)))
        lines += ["- [%s] %s（期限 %s）" % (t.get("id"), t.get("title"), t.get("due") or "なし") for t in group] or ["- なし"]
        lines.append("")
    return lines


def main():
    ap = argparse.ArgumentParser(description="1週間の週報を作る（ファイルと CSV の数字だけを使う）")
    ap.add_argument("--work", required=True, help="作業フォルダ（kit-work）の絶対パス")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--yt-csv", default=None)
    ap.add_argument("--sns-csv", default=None)
    ap.add_argument("--tasks", default=None, help="secretary のデータフォルダ")
    a = ap.parse_args()
    work = os.path.abspath(os.path.expanduser(a.work))
    if not os.path.isdir(work):
        print("作業フォルダがありません: " + work)
        return 2
    now = dt.datetime.now()
    since = (now - dt.timedelta(days=a.days)).timestamp()
    L = ["# 週報 %s（直近 %d 日）" % (now.strftime("%Y-%m-%d"), a.days), "",
         "- 作成: %s" % now.strftime("%Y-%m-%d %H:%M"), "- 作業フォルダ: %s" % work,
         "- この週報は、ファイルの日付と渡された CSV の数字だけで作っています。数字は作っていません", "",
         "## 1 今週作ったもの", "", "| 置き場 | ファイル数 |", "|---|---|"]
    detail = []
    for sub, label in AREAS:
        fs = recent_files(os.path.join(work, sub), since)
        L.append("| %s（%s/） | %d |" % (label, sub, len(fs)))
        if fs:
            detail.append("### %s" % label)
            detail += ["- %s（%s）" % (rel, dt.datetime.fromtimestamp(m).strftime("%m/%d %H:%M")) for m, rel in fs[:15]]
            if len(fs) > 15:
                detail.append("- ほか %d 件" % (len(fs) - 15))
            detail.append("")
    L += [""] + detail
    L += yt_section(os.path.abspath(a.yt_csv) if a.yt_csv else None)
    L += sns_section(os.path.abspath(a.sns_csv) if a.sns_csv else None)
    L += task_section(os.path.abspath(a.tasks) if a.tasks else None, now.date())
    L += ["## 5 来週の提案（最大3つ。決めるのはご本人）", "", "1. 【】", "2. 【】", "3. 【】", "",
          "## ご本人が決めること", "", "- 【】", ""]
    out = os.path.join(work, "reports")
    os.makedirs(out, exist_ok=True)
    base = os.path.join(out, "%s_weekly" % now.strftime("%Y-%m-%d"))
    path, i = base + ".md", 2
    while os.path.exists(path):
        path, i = "%s_%d.md" % (base, i), i + 1
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print("作りました: " + path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
