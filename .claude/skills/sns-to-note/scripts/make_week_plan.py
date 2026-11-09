#!/usr/bin/env python3
"""note の記事（Markdown）から、1週間分の「SNS投稿の予定表」と「下書きの枠」を作る。

使い方:
    python3 make_week_plan.py article.md --start 2026-11-09
    python3 make_week_plan.py article.md --start 2026-11-09 --out ./sns_week --platform X

- 記事の「無料部分」（=== ここから有料 === より上）の見出しだけを投稿ネタに使う。
  有料部分の中身を SNS に出さないため。
- 出力: <out>/plan.md（予定表） と <out>/posts.md（下書きの枠。check_posts.py の形式）
- 投稿はしない。ファイルを作るだけ。
標準ライブラリだけで動く。
"""
import argparse
import datetime
import os
import sys

PAID_LINE = "=== ここから有料 ==="
# 古い note-article が書いていた目印（2026-11-09 まで）。読み込みだけ受け付ける
OLD_PAID_MARKS = ("ここから有料（有料ライン）",)


def is_paid_line(line):
    t = line.strip()
    return t == PAID_LINE or any(m in t for m in OLD_PAID_MARKS)

# 曜日ごとの型（月=0）。告知（リンクあり）は週2回まで。
WEEK = [
    ("学び抜粋", False),
    ("問いかけ", False),
    ("失敗談・体験", False),
    ("学び抜粋", False),
    ("告知", True),
    ("一覧・まとめ", False),
    ("振り返り＋LINE案内", True),
]
WD = "月火水木金土日"


def read_article(path):
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    title = next((l[2:].strip() for l in lines if l.startswith("# ")), "（題名なし）")
    cut = next((i for i, l in enumerate(lines) if is_paid_line(l)), len(lines))
    free = lines[:cut]
    heads = [l[3:].strip() for l in free if l.startswith("## ")]
    paid_heads = [l[3:].strip() for l in lines[cut:] if l.startswith("## ")]
    return title, heads, paid_heads, cut < len(lines)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("article")
    p.add_argument("--start", default=None, help="週の初日 YYYY-MM-DD（既定: 次の月曜）")
    p.add_argument("--out", default="sns_week", help="出力フォルダ（既定 ./sns_week）")
    p.add_argument("--platform", default="X", choices=["X", "Threads"], help="主に使う媒体")
    a = p.parse_args()

    title, heads, paid_heads, has_paid = read_article(a.article)
    if not heads:
        print("止めました：無料部分に見出し（##）がありません。記事の構成を先に作ってください。")
        sys.exit(1)

    if a.start:
        start = datetime.date.fromisoformat(a.start)
    else:
        t = datetime.date.today()
        start = t + datetime.timedelta(days=(7 - t.weekday()) % 7 or 7)

    os.makedirs(a.out, exist_ok=True)
    plan = [f"# 1週間の投稿予定：{title}", "",
            f"- 媒体：{a.platform}",
            f"- 期間：{start} 〜 {start + datetime.timedelta(days=6)}",
            "- ネタに使う見出し（無料部分のみ）：" + "／".join(heads),
            ]
    if has_paid:
        plan.append("- 使わない見出し（有料部分。SNSに中身を出さない）：" + ("／".join(paid_heads) or "なし"))
    plan += ["", "| 日付 | 曜日 | 型 | ネタ（見出し） | リンク |", "|---|---|---|---|---|"]

    posts = [f"# 投稿の下書き：{title}", "",
             "各投稿の本文を書いたら、check_posts.py で点検する。リンクは【noteのURL】【LINEのURL】のまま残し、投稿の直前にご本人が差し替える。", ""]
    k = 0
    for d in range(7):
        day = start + datetime.timedelta(days=d)
        kind, link = WEEK[day.weekday()]
        head = heads[k % len(heads)]
        k += 1
        url = "【LINEのURL】" if "LINE" in kind else ("【noteのURL】" if link else "なし")
        plan.append(f"| {day} | {WD[day.weekday()]} | {kind} | {head} | {url} |")
        posts += [f"## 投稿{d + 1}｜{a.platform}｜{kind}", f"<!-- {day}（{WD[day.weekday()]}） ネタ：{head} -->", "",
                  "（ここに本文）", ""]
        if link:
            posts += [f"（リンクは本文の最後か、自分の返信欄に1つだけ：{url}）", ""]

    plan += ["", "## 週の終わりに記録する数字", "",
             "| 項目 | 今週 | 先週 |", "|---|---|---|",
             "| 投稿数 |  |  |", "| いちばん反応が多かった投稿の型 |  |  |",
             "| プロフィールを見た人の数 |  |  |", "| note の閲覧数（ダッシュボード） |  |  |",
             "| note の購入数 |  |  |", "| LINE の登録数 |  |  |"]

    with open(os.path.join(a.out, "plan.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(plan) + "\n")
    with open(os.path.join(a.out, "posts.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(posts) + "\n")
    print(f"作りました：{os.path.abspath(os.path.join(a.out, 'plan.md'))}")
    print(f"作りました：{os.path.abspath(os.path.join(a.out, 'posts.md'))}")
    print(f"ネタに使った見出し {len(heads)} 個／除外した有料部分の見出し {len(paid_heads)} 個")


if __name__ == "__main__":
    main()
