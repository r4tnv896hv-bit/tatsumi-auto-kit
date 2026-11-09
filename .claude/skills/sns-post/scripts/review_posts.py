# -*- coding: utf-8 -*-
"""SNS 投稿の数字（CSV）から、週の振り返りを作る。数字は CSV にあるものだけを使い、作りません。

CSV の形（templates/metrics_template.csv。1行 = 1投稿）:
    日付,媒体,型,書き出し,表示,反応,プロフィール,リンク
    2026-11-10,X,言い切り,固定費は我慢より先に,1200,36,8,2

  - 表示 = インプレッション（見られた回数）
  - 反応 = いいね＋返信＋リポスト（再投稿）＋保存 など、その媒体で数えられるものの合計
  - プロフィール・リンク は分かる媒体だけ（空でよい）
  - 各SNSの分析画面から書き写すか、書き出した CSV の列名を下の「別名」に合わせれば、そのまま読めます

使い方:
    python3 review_posts.py /絶対パス/metrics.csv --out /絶対パス/reports
    → reports/YYYY-MM-DD_sns_review.md を作る（同名があれば _2, _3 … を付ける）

判定（媒体ごとの中央値と比べて ±20%）:
    当たり     表示も反応率も高い     → 同じ型で来週もう1本
    届いたが弱い 表示だけ高い         → 書き出しは残し、中身を1つの気づきに絞る
    刺さったが狭い 反応率だけ高い      → 書き出しを作り直す案を2つ
    要見直し   両方低い              → 型を変える
    ふつう     それ以外
本数が媒体ごとに5本未満のときは「参考程度」と書きます。
終了コード: 0 = 作れた / 1 = 読める行が無い / 2 = 使い方の誤り
"""
import argparse
import csv
import datetime as dt
import os
import statistics
import sys

ALIAS = {
    "日付": ["日付", "date", "Date", "投稿日", "Post date", "time"],
    "媒体": ["媒体", "platform", "Platform", "SNS"],
    "型": ["型", "type", "Type", "投稿の型"],
    "書き出し": ["書き出し", "本文", "text", "Post text", "Tweet text", "投稿"],
    "表示": ["表示", "インプレッション", "impressions", "Impressions", "閲覧数", "Views", "views"],
    "反応": ["反応", "エンゲージメント", "engagements", "Engagements", "反応数"],
    "プロフィール": ["プロフィール", "プロフィールへのアクセス", "Profile visits", "user profile clicks"],
    "リンク": ["リンク", "リンクのクリック数", "URL clicks", "url clicks", "Link clicks"],
}


def num(s):
    try:
        return float(str(s).replace(",", "").strip())
    except ValueError:
        return None


def load(path, default_pf):
    with open(path, encoding="utf-8-sig", newline="") as f:
        rd = csv.DictReader(f)
        cols = {}
        for key, names in ALIAS.items():
            for n in names:
                if n in (rd.fieldnames or []):
                    cols[key] = n
                    break
        rows, skipped = [], 0
        for r in rd:
            imp = num(r.get(cols.get("表示", ""), ""))
            eng = num(r.get(cols.get("反応", ""), ""))
            if imp is None or eng is None or imp <= 0:
                skipped += 1
                continue
            rows.append({
                "日付": (r.get(cols.get("日付", ""), "") or "")[:10],
                "媒体": (r.get(cols.get("媒体", ""), "") or default_pf).strip() or default_pf,
                "型": (r.get(cols.get("型", ""), "") or "未分類").strip() or "未分類",
                "書き出し": (r.get(cols.get("書き出し", ""), "") or "").replace("\n", " ")[:24],
                "表示": imp, "反応": eng, "率": eng / imp,
                "プロフィール": num(r.get(cols.get("プロフィール", ""), "")),
                "リンク": num(r.get(cols.get("リンク", ""), "")),
            })
    return rows, skipped, cols


def judge(r, mi, mr):
    hi_i, lo_i = r["表示"] >= mi * 1.2, r["表示"] <= mi * 0.8
    hi_r, lo_r = r["率"] >= mr * 1.2, r["率"] <= mr * 0.8
    if hi_i and hi_r:
        return "当たり", "同じ型で来週もう1本"
    if hi_i and not hi_r:
        return "届いたが弱い", "書き出しは残し、中身を1つの気づきに絞る"
    if hi_r and not hi_i:
        return "刺さったが狭い", "書き出しを作り直す案を2つ"
    if lo_i and lo_r:
        return "要見直し", "型を変える"
    return "ふつう", "そのまま"


def main():
    ap = argparse.ArgumentParser(description="SNS 投稿の数字から週の振り返りを作る")
    ap.add_argument("csv")
    ap.add_argument("--out", required=True, help="振り返りの保存先フォルダ（絶対パス）")
    ap.add_argument("--platform", default="X", help="CSV に媒体の列が無いときの媒体名")
    a = ap.parse_args()
    src = os.path.abspath(a.csv)
    if not os.path.isfile(src):
        print("CSV がありません: " + src)
        return 2
    rows, skipped, cols = load(src, a.platform)
    if not rows:
        print("読める行がありません。列名（表示・反応）を確かめてください。読めた列: %s" % (", ".join(cols) or "なし"))
        return 1
    now = dt.datetime.now()
    lines = ["# SNS 週の振り返り（%s 作成）" % now.strftime("%Y-%m-%d %H:%M"), "",
             "- 元の数字: %s" % src, "- 読めた投稿: %d 本（読めなかった行: %d）" % (len(rows), skipped),
             "- 数字は CSV のものだけを使っています。測った時刻は、CSV を書き出した時刻です", ""]
    by_pf = {}
    for r in rows:
        by_pf.setdefault(r["媒体"], []).append(r)
    for pf, rs in by_pf.items():
        mi = statistics.median([r["表示"] for r in rs])
        mr = statistics.median([r["率"] for r in rs])
        lines += ["## %s（%d 本%s）" % (pf, len(rs), "・参考程度" if len(rs) < 5 else ""), "",
                  "- 表示の中央値: %d ／ 反応率の中央値: %.1f%%" % (mi, mr * 100), "",
                  "| 日付 | 型 | 書き出し | 表示 | 反応率 | 判定 | 次の一手 |", "|---|---|---|---|---|---|---|"]
        for r in sorted(rs, key=lambda x: x["日付"]):
            j, nxt = judge(r, mi, mr)
            r["判定"] = j
            lines.append("| %s | %s | %s | %d | %.1f%% | %s | %s |" % (r["日付"], r["型"], r["書き出し"], r["表示"], r["率"] * 100, j, nxt))
        types = {}
        for r in rs:
            types.setdefault(r["型"], []).append(r["率"])
        lines += ["", "### 型ごとの反応率（中央値）", ""]
        ranked = sorted(types.items(), key=lambda kv: -statistics.median(kv[1]))
        for t, v in ranked:
            lines.append("- %s：%.1f%%（%d 本）" % (t, statistics.median(v) * 100, len(v)))
        if len(ranked) >= 2:
            lines += ["", "来週の配分の案：「%s」を1本増やし、「%s」を1本減らす（決めるのはご本人）" % (ranked[0][0], ranked[-1][0])]
        lines.append("")
    lines += ["## ご本人が決めること", "", "- 来週の型の配分（上の案を使うか）",
              "- 「当たり」の投稿の、なぜ当たったかを1行（AI の推測ではなく、ご本人の感覚で）", ""]
    out = os.path.abspath(os.path.expanduser(a.out))
    os.makedirs(out, exist_ok=True)
    base = os.path.join(out, "%s_sns_review" % now.strftime("%Y-%m-%d"))
    path, i = base + ".md", 2
    while os.path.exists(path):
        path, i = "%s_%d.md" % (base, i), i + 1
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("作りました: " + path)
    print("投稿 %d 本 / 媒体 %s" % (len(rows), ", ".join("%s %d本" % (k, len(v)) for k, v in by_pf.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
