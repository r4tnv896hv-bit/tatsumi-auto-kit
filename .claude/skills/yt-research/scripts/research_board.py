# -*- coding: utf-8 -*-
"""YouTube のネタ・競合リサーチの「調査ボード」を作る／点検する。ネットにはつなぎません。

使い方:
  python3 research_board.py new --theme "固定費の見直し" --out /絶対パス/research
      → /絶対パス/research/YYYY-MM-DD_<テーマ>.md （空欄つきのボード）を作る。同名があれば上書きしない
  python3 research_board.py check /絶対パス/research/2026-11-10_固定費の見直し.md
      → 候補ごとに「仮タイトル・悩み・骨組み・出典URL・形」がそろっているか、
         出典が http(s) で始まるか、同じ仮タイトルが無いか、おすすめ3つが書いてあるかを点検

ボードの形（候補1つ分）:
  ### 候補1
  - 仮タイトル: ……（32字以内）
  - 悩み: ……
  - 骨組み: ……
  - 出典: https://……（複数なら「 / 」で区切る。見つからなければ「出典なし」）
  - 形: YouTube / ショート / note / SNS

終了コード: 0 = NG なし / 1 = NG あり / 2 = 使い方の誤り
"""
import argparse
import datetime as dt
import os
import re
import sys

FIELDS = ["仮タイトル", "悩み", "骨組み", "出典", "形"]
FORMS = {"YouTube", "ショート", "note", "SNS"}
URL = re.compile(r"https?://[^\s/]+\.[^\s]+")
SAFE = re.compile(r"[\\/:*?\"<>|\s]+")


def board_text(theme, n):
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    out = ["# リサーチボード: %s" % theme, "",
           "- 調べた日時: %s" % now,
           "- テーマ: %s" % theme,
           "- 見てほしい人: 【誰の・どんな悩み】",
           "",
           "## 切り口（各3件以上、公式・本人の発信を優先）",
           "- よくある悩み:",
           "- よくある間違い:",
           "- 最近の変化:",
           "",
           "## 競合・参考チャンネル（文章や映像は写さない。見るのは「切り口」と「型」だけ）",
           "| チャンネル | URL | 伸びている動画の切り口 | 自分ならどう変えるか |",
           "|---|---|---|---|",
           "| 【】 | 【】 | 【】 | 【】 |",
           "",
           "## ネタ候補"]
    for i in range(1, n + 1):
        out += ["", "### 候補%d" % i] + ["- %s: " % f for f in FIELDS]
    out += ["", "## おすすめの3つ", "1. ", "2. ", "3. ", "",
            "## 確かめきれなかったこと", "- "]
    return "\n".join(out) + "\n"


def cmd_new(a):
    out = os.path.abspath(os.path.expanduser(a.out))
    os.makedirs(out, exist_ok=True)
    name = "%s_%s.md" % (dt.date.today().isoformat(), SAFE.sub("_", a.theme.strip())[:40])
    path = os.path.join(out, name)
    if os.path.exists(path):
        print("すでにあります（上書きしません）: " + path)
        return 1
    with open(path, "w", encoding="utf-8") as f:
        f.write(board_text(a.theme.strip(), a.count))
    print("作りました: " + path)
    return 0


def parse(text):
    cands, cur = [], None
    for line in text.splitlines():
        m = re.match(r"^###\s*候補\s*(\d+)", line)
        if m:
            cur = {"no": int(m.group(1))}
            cands.append(cur)
            continue
        if line.startswith("## "):
            cur = None
            continue
        if cur is not None:
            m = re.match(r"^-\s*([^:：]+)[:：]\s*(.*)$", line)
            if m and m.group(1).strip() in FIELDS:
                cur[m.group(1).strip()] = m.group(2).strip()
    return cands


def cmd_check(a):
    path = os.path.abspath(a.file)
    if not os.path.isfile(path):
        print("ファイルがありません: " + path)
        return 2
    with open(path, encoding="utf-8") as f:
        text = f.read()
    cands = parse(text)
    ng, warn, titles = [], [], {}
    if len(cands) < 5:
        ng.append("候補が %d 個しかありません（5個以上）" % len(cands))
    for c in cands:
        tag = "候補%d" % c["no"]
        for f in FIELDS:
            if not c.get(f) or c.get(f).startswith("【"):
                ng.append("%s: 「%s」が空です" % (tag, f))
        t = c.get("仮タイトル", "")
        if len(t) > 32:
            warn.append("%s: 仮タイトルが %d 字（32字以内が目安）" % (tag, len(t)))
        if t:
            if t in titles:
                ng.append("%s: 候補%d と同じ仮タイトルです" % (tag, titles[t]))
            titles.setdefault(t, c["no"])
        src = c.get("出典", "")
        if src and src != "出典なし" and not URL.search(src):
            ng.append("%s: 出典が URL になっていません（見つからなければ「出典なし」と書く）" % tag)
        if src == "出典なし":
            warn.append("%s: 出典なし → 台本にする前に、ご本人が確かめる" % tag)
        form = c.get("形", "")
        if form and not any(x in form for x in FORMS):
            warn.append("%s: 形「%s」は YouTube / ショート / note / SNS のどれかに" % (tag, form))
    rec = re.search(r"## おすすめの3つ\s*\n(.*?)(\n## |\Z)", text, re.S)
    filled = [l for l in (rec.group(1).splitlines() if rec else []) if re.match(r"^\d\.\s*\S", l)]
    if len(filled) < 3:
        ng.append("「おすすめの3つ」が %d 個しか書かれていません" % len(filled))
    for x in ng:
        print("NG   " + x)
    for x in warn:
        print("注意 " + x)
    print("== 結果: 候補 %d 個 / NG %d / 注意 %d ==" % (len(cands), len(ng), len(warn)))
    return 1 if ng else 0


def main():
    ap = argparse.ArgumentParser(description="YouTube リサーチボードを作る／点検する（使い方は先頭の説明を参照）")
    sub = ap.add_subparsers(dest="cmd")
    n = sub.add_parser("new", help="空のボードを作る")
    n.add_argument("--theme", required=True)
    n.add_argument("--out", required=True, help="保存先フォルダ（絶対パス）")
    n.add_argument("--count", type=int, default=10, help="候補の数（初期値 10）")
    c = sub.add_parser("check", help="ボードを点検する")
    c.add_argument("file")
    a = ap.parse_args()
    if a.cmd == "new":
        return cmd_new(a)
    if a.cmd == "check":
        return cmd_check(a)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
