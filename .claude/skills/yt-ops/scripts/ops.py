#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
yt-channel-ops / ops.py
YouTube チャンネルの「毎週の段取り」を、ファイルだけで回すための道具。標準ライブラリだけで動く。
アップロード・投稿・送信は一切しない（それは人が YouTube Studio で行う）。

  python3 ops.py init   --dir <チャンネルフォルダ> --name "チャンネル名" --days 火,金
  python3 ops.py add    --dir <...> --title "仮タイトル" [--pillar 柱] [--publish 2026-11-20]
  python3 ops.py list   --dir <...>
  python3 ops.py move   --dir <...> --id V003 --stage script [--publish 2026-11-20]
  python3 ops.py week   --dir <...> [--date 2026-11-09]
  python3 ops.py checklist --dir <...> --id V003
  python3 ops.py review --dir <...> --csv <YouTube Studio から書き出した 表データ.csv>
"""
import argparse
import csv
import json
import os
import re
import statistics
import sys
from datetime import date, datetime, timedelta

STAGES = ["idea", "plan", "script", "record", "edit", "thumb", "ready", "published"]
STAGE_JA = {"idea": "ネタ", "plan": "企画OK", "script": "台本OK", "record": "収録済み", "edit": "編集済み",
            "thumb": "サムネOK", "ready": "公開準備OK", "published": "公開済み"}
# 公開日から逆算した「この段階を終えておく日」（公開日の何日前）
DUE = {"plan": 9, "script": 6, "record": 4, "edit": 2, "thumb": 2, "ready": 1}
WEEK_JA = ["月", "火", "水", "木", "金", "土", "日"]
FIELDS = ["id", "title", "pillar", "stage", "publish", "updated", "notes"]


def die(msg):
    print("エラー: " + msg, file=sys.stderr)
    sys.exit(1)


def paths(d):
    d = os.path.abspath(os.path.expanduser(d))
    return d, os.path.join(d, "channel.json"), os.path.join(d, "queue.csv")


def load(d):
    d, cj, qc = paths(d)
    if not os.path.exists(cj):
        die("チャンネルフォルダではありません（channel.json が無い）: %s\n先に init してください" % d)
    with open(cj, encoding="utf-8") as f:
        ch = json.load(f)
    rows = []
    if os.path.exists(qc):
        with open(qc, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
    return d, ch, rows


def save_rows(d, rows):
    _, _, qc = paths(d)
    tmp = qc + ".tmp"
    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})
    os.replace(tmp, qc)


def pdate(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date() if s else None
    except ValueError:
        die("日付は 2026-11-20 の形で書いてください: %s" % s)


def next_id(rows):
    n = max([int(re.sub(r"\D", "", r["id"]) or 0) for r in rows] + [0]) + 1
    return "V%03d" % n


def find(rows, vid):
    for r in rows:
        if r["id"].upper() == vid.upper():
            return r
    die("ID が見つかりません: %s（list で確認できます）" % vid)


def next_stage_due(r):
    """まだ終わっていない最初の段階と、その締め切り日"""
    pub = pdate(r.get("publish"))
    if not pub or r["stage"] == "published":
        return None, None
    idx = STAGES.index(r["stage"])
    for st in STAGES[idx + 1:]:
        if st in DUE:
            return st, pub - timedelta(days=DUE[st])
    return "published", pub


# ---------- コマンド ----------

def cmd_init(a):
    d, cj, qc = paths(a.dir)
    if os.path.exists(cj):
        die("すでに作られています: %s" % cj)
    for sub in ["weekly", "videos", "analytics"]:
        os.makedirs(os.path.join(d, sub), exist_ok=True)
    days = [x.strip() for x in a.days.split(",") if x.strip()]
    for x in days:
        if x not in WEEK_JA:
            die("--days は 月,火,水,木,金,土,日 から選んでください: %s" % x)
    ch = {"name": a.name, "audience": a.audience or "【誰に向けたチャンネルか】",
          "pillars": [p.strip() for p in (a.pillars or "【柱1】,【柱2】,【柱3】").split(",")],
          "publish_days": days, "created": date.today().isoformat()}
    with open(cj, "w", encoding="utf-8") as f:
        json.dump(ch, f, ensure_ascii=False, indent=2)
    save_rows(d, [])
    with open(os.path.join(d, "decisions.md"), "w", encoding="utf-8") as f:
        f.write("# 決めたことと理由\n\n| 日付 | 決めたこと | 理由 | 見直す日 |\n|---|---|---|---|\n")
    print("作りました: %s" % d)
    print("  channel.json（方針） / queue.csv（台本キュー） / weekly/ / videos/ / analytics/ / decisions.md")
    print("公開する曜日: %s" % "・".join(days))


def cmd_add(a):
    d, ch, rows = load(a.dir)
    r = {"id": next_id(rows), "title": a.title, "pillar": a.pillar or "", "stage": "idea",
         "publish": a.publish or "", "updated": date.today().isoformat(), "notes": a.notes or ""}
    if a.publish:
        pdate(a.publish)
    rows.append(r)
    save_rows(d, rows)
    print("足しました: %s %s" % (r["id"], r["title"]))


def cmd_list(a):
    d, ch, rows = load(a.dir)
    if not rows:
        print("キューは空です。add でネタを足してください")
        return
    print("| ID | 段階 | 公開予定 | 次の段階（締め切り） | 柱 | タイトル |")
    print("|---|---|---|---|---|---|")
    for r in sorted(rows, key=lambda r: (r["publish"] or "9999", r["id"])):
        st, due = next_stage_due(r)
        nxt = "%s（%s）" % (STAGE_JA.get(st, st), due.isoformat()) if st else "-"
        print("| %s | %s | %s | %s | %s | %s |" % (r["id"], STAGE_JA[r["stage"]], r["publish"] or "未定", nxt, r["pillar"], r["title"]))


def cmd_move(a):
    d, ch, rows = load(a.dir)
    if a.stage not in STAGES:
        die("段階は %s のどれかです" % " / ".join(STAGES))
    r = find(rows, a.id)
    old = r["stage"]
    r["stage"] = a.stage
    if a.publish:
        pdate(a.publish)
        r["publish"] = a.publish
    r["updated"] = date.today().isoformat()
    save_rows(d, rows)
    print("%s: %s → %s" % (r["id"], STAGE_JA[old], STAGE_JA[a.stage]))
    if a.stage == "ready":
        print("公開準備OKです。checklist --id %s でアップロード前の確認表を作ってください" % r["id"])


def cmd_week(a):
    d, ch, rows = load(a.dir)
    today = pdate(a.date) if a.date else date.today()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    iso = monday.isocalendar()
    out = os.path.join(d, "weekly", "%d-W%02d.md" % (iso[0], iso[1]))

    slots = [monday + timedelta(days=i) for i in range(14) if WEEK_JA[(monday + timedelta(days=i)).weekday()] in ch["publish_days"]]
    by_pub = {r["publish"]: r for r in rows if r["publish"] and r["stage"] != "published"}
    empty = [s for s in slots if s.isoformat() not in by_pub and s >= today]
    late, todo = [], {}
    for r in rows:
        pub = pdate(r.get("publish"))
        if not pub or r["stage"] == "published":
            continue
        idx = STAGES.index(r["stage"])
        first_late = True
        for st in STAGES[idx + 1:]:
            due = pub - timedelta(days=DUE[st]) if st in DUE else pub
            if due < today:
                if first_late:
                    late.append((r, st, due))
                    first_late = False
            elif due <= sunday:
                todo.setdefault(due, []).append((r, st))
    ideas = [r for r in rows if r["stage"] in ("idea", "plan") and not r["publish"]]

    L = ["# 週の段取り %s 〜 %s（%s）" % (monday.isoformat(), sunday.isoformat(), ch["name"]), "",
         "作った時刻: %s" % datetime.now().strftime("%Y-%m-%d %H:%M"), ""]
    L += ["## 今週と来週の公開枠", "", "| 公開日 | 曜日 | 動画 | いまの段階 |", "|---|---|---|---|"]
    for s in slots:
        r = by_pub.get(s.isoformat())
        L.append("| %s | %s | %s | %s |" % (s.isoformat(), WEEK_JA[s.weekday()], ("%s %s" % (r["id"], r["title"])) if r else "**空き**", STAGE_JA[r["stage"]] if r else "-"))
    L += ["", "## 遅れているもの（先に片づける）", ""]
    L += ["- [ ] %s %s：%s が %s 締め切り（%d 日遅れ）" % (r["id"], r["title"], STAGE_JA[st], due.isoformat(), (today - due).days) for r, st, due in late] or ["- なし"]
    L += ["", "## 曜日ごとのやること", ""]
    for i in range(7):
        day = monday + timedelta(days=i)
        items = todo.get(day, [])
        L.append("### %s（%s）" % (day.isoformat(), WEEK_JA[i]))
        L += [("- [ ] %s %s を公開する（アップロード・予約は自分で。前日までに checklist）" % (r["id"], r["title"])) if st == "published"
              else "- [ ] %s %s を「%s」まで進める" % (r["id"], r["title"], STAGE_JA[st]) for r, st in items] or ["- 締め切りなし（ネタ出し・分析の日にする）"]
        L.append("")
    L += ["## 空き枠をうめる候補（ネタ・企画OKの中から）", ""]
    if empty:
        L += ["- 空き枠: %s" % "、".join("%s(%s)" % (s.isoformat(), WEEK_JA[s.weekday()]) for s in empty)]
        L += ["- 候補: %s %s（柱: %s）" % (r["id"], r["title"], r["pillar"] or "-") for r in ideas[:5]] or ["- 候補がありません。ネタを3つ足してください"]
        L += ["", "決めたら：`ops.py move --id <ID> --stage plan --publish <日付>`"]
    else:
        L.append("- 空き枠はありません")
    L += ["", "## 今週の確認（人がやること）", "",
          "- [ ] 先週公開した動画の数字を YouTube Studio で見た（金曜に review）",
          "- [ ] アップロードは自分で行った（このキットは投稿しない）",
          "- [ ] 決めたことを decisions.md に書いた"]
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print("書きました: %s" % out)
    print("公開枠 %d / 空き %d / 遅れ %d / 今週の締め切り %d 件" % (len(slots), len(empty), len(late), sum(len(v) for v in todo.values())))


CHECKLIST = """# アップロード前チェック {id}「{title}」

公開予定: {publish} ／ 作った日: {today}

## ファイル
- [ ] 動画ファイルの長さを測った（ffprobe か再生ソフトで。台本の想定と大きくずれていない）
- [ ] 冒頭3秒・つなぎ目・最後の5秒を目で見た
- [ ] 音量：声が聞き取れる／BGM が声より小さい
- [ ] 画面に個人情報（メール・通知・住所・他人の名前）が映っていない
- [ ] 他人の動画・画像・音楽を使っていない（使ったなら利用条件を確認済み）

## タイトル・サムネ
- [ ] タイトルは中身と合っている（言い切りすぎ・うその数字なし）
- [ ] 大事な言葉が前から30字以内に入っている
- [ ] サムネの文字はスマホの小さい表示でも読める
- [ ] サムネとタイトルで同じことを繰り返していない（役割を分ける）

## 説明欄・設定
- [ ] 説明欄の最初の2行に「誰の・何の悩みに答える動画か」
- [ ] 目次（0:00 から始める）
- [ ] 字幕（.srt）を登録した
- [ ] 「改変または合成されたコンテンツ」：本物そっくりの AI 人物・音声を使ったなら「はい」
- [ ] 子ども向けかどうかを正しく選んだ
- [ ] 公開日時を予約した（公開・予約は自分で行う）

## 公開後（48時間以内）
- [ ] コメントに返信した
- [ ] 48時間後のインプレッションのクリック率・平均視聴率をメモした
- [ ] ops.py move --id {id} --stage published を実行した
"""


def cmd_checklist(a):
    d, ch, rows = load(a.dir)
    r = find(rows, a.id)
    out = os.path.join(d, "videos", "%s_upload_checklist.md" % r["id"])
    with open(out, "w", encoding="utf-8") as f:
        f.write(CHECKLIST.format(id=r["id"], title=r["title"], publish=r["publish"] or "未定", today=date.today().isoformat()))
    print("書きました: %s" % out)


# YouTube Studio の書き出し（日本語・英語）の列名を、ゆるく読み取る
COLS = {
    "title": ["動画のタイトル", "video title", "title"],
    "published": ["動画公開時刻", "video publish time", "公開"],
    "views": ["視聴回数", "views"],
    "hours": ["総再生時間", "watch time"],
    "subs": ["チャンネル登録者", "subscribers"],
    "impr": ["インプレッション数", "impressions"],
    "ctr": ["クリック率", "click-through rate"],
    "avd": ["平均視聴時間", "average view duration"],
    "apv": ["平均再生率", "average percentage viewed"],
}


def map_cols(header):
    m = {}
    for key, cands in COLS.items():
        for i, h in enumerate(header):
            hl = h.strip().lower()
            if any(c.lower() in hl for c in cands):
                if key == "impr" and ("クリック率" in h or "click" in hl):
                    continue
                m.setdefault(key, i)
    return m


def num(s):
    s = (s or "").replace(",", "").replace("%", "").strip()
    if re.match(r"^\d+:\d{2}(:\d{2})?$", s):
        p = [int(x) for x in s.split(":")]
        return p[0] * 60 + p[1] if len(p) == 2 else p[0] * 3600 + p[1] * 60 + p[2]
    try:
        return float(s)
    except ValueError:
        return None


def cmd_review(a):
    d, ch, rows = load(a.dir)
    if not os.path.exists(a.csv):
        die("CSV が見つかりません: %s" % a.csv)
    with open(a.csv, encoding="utf-8-sig", newline="") as f:
        data = list(csv.reader(f))
    if not data:
        die("CSV が空です")
    m = map_cols(data[0])
    if "title" not in m or "views" not in m:
        die("列が読めません。YouTube Studio →アナリティクス→詳細→（右上の）書き出し→「カンマ区切り値（.csv）」の「表データ.csv」を使ってください\n見つかった列: %s" % ", ".join(data[0]))
    vids = []
    for r in data[1:]:
        if len(r) <= m["title"] or not r[m["title"]].strip() or r[0].strip() in ("合計", "Total"):
            continue
        v = {k: (num(r[i]) if k != "title" and k != "published" else r[i].strip()) for k, i in m.items() if i < len(r)}
        vids.append(v)
    if not vids:
        die("動画の行がありませんでした")

    def med(k):
        xs = [v[k] for v in vids if isinstance(v.get(k), (int, float))]
        return statistics.median(xs) if xs else None

    mc, ma, mv = med("ctr"), med("apv"), med("views")
    L = ["# 数字の振り返り %s（%s）" % (date.today().isoformat(), ch["name"]), "",
         "- 測った時刻: %s" % datetime.now().strftime("%Y-%m-%d %H:%M"),
         "- 元データ: %s（%d 本）" % (os.path.basename(a.csv), len(vids)),
         "- 中央値: 視聴回数 %s / クリック率 %s%% / 平均再生率 %s%%" % (fmt(mv), fmt(mc), fmt(ma)), "",
         "## 動画ごとの判定", "",
         "| タイトル | 視聴回数 | インプレッション | クリック率% | 平均再生率% | 判定 | 次にやること |", "|---|---|---|---|---|---|---|"]
    keep, fix_thumb, fix_open = [], [], []
    for v in sorted(vids, key=lambda v: -(v.get("views") or 0)):
        ctr, apv = v.get("ctr"), v.get("apv")
        lo_c = mc is not None and ctr is not None and ctr < mc * 0.8
        lo_a = ma is not None and apv is not None and apv < ma * 0.8
        hi_c = mc is not None and ctr is not None and ctr >= mc * 1.2
        hi_a = ma is not None and apv is not None and apv >= ma * 1.2
        if lo_c and lo_a:
            j, nx = "要見直し", "企画そのものを見直す（誰の悩みかがズレていないか）"
        elif lo_c:
            j, nx = "入口が弱い", "タイトル・サムネを作り直す案を2つ"
            fix_thumb.append(v["title"])
        elif lo_a:
            j, nx = "途中で離脱", "冒頭30秒と構成を見直す（結論を先に）"
            fix_open.append(v["title"])
        elif hi_c and hi_a:
            j, nx = "当たり", "同じ『理由』で次の企画を1本"
            keep.append(v["title"])
        elif hi_c:
            j, nx = "入口は強い", "タイトル・サムネの型をメモして次にも使う。中身の冒頭を強化"
        elif hi_a:
            j, nx = "中身は強い", "見られれば最後まで見られる。タイトル・サムネを強くすれば伸びる余地"
        else:
            j, nx = "ふつう", "-"
        L.append("| %s | %s | %s | %s | %s | %s | %s |" % (v["title"].replace("|", "／"), fmt(v.get("views")), fmt(v.get("impr")), fmt(ctr), fmt(apv), j, nx))
    L += ["", "## 来週に向けて（最大3つ）", ""]
    acts = []
    if keep:
        acts.append("当たりの「なぜ」を1行で書き、同じ理由の企画を queue に1本足す（例: %s）" % keep[0])
    if fix_thumb:
        acts.append("クリック率が低い動画のサムネ・タイトルを差し替える案を作る（例: %s）" % fix_thumb[0])
    if fix_open:
        acts.append("次の台本は、冒頭15秒で結論と得られることを言い切る（例: %s）" % fix_open[0])
    if not acts:
        acts.append("大きな差はありません。公開ペースを守ることを優先")
    L += ["- [ ] " + x for x in acts[:3]]
    L += ["", "> 判定は中央値との比較です（±20%）。本数が5本未満のときは参考程度に。", ""]
    out = os.path.join(d, "analytics", "review_%s.md" % date.today().isoformat())
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print("書きました: %s（%d 本）" % (out, len(vids)))


def fmt(x):
    if x is None:
        return "-"
    if isinstance(x, float) and not x.is_integer():
        return "%.1f" % x
    return "{:,}".format(int(x))


def main():
    ap = argparse.ArgumentParser(description="YouTube チャンネル運用の段取り（投稿はしない）")
    sp = ap.add_subparsers(dest="cmd")
    p = sp.add_parser("init"); p.add_argument("--dir", required=True); p.add_argument("--name", required=True)
    p.add_argument("--days", default="火,金", help="公開する曜日（例: 火,金）"); p.add_argument("--audience"); p.add_argument("--pillars", help="発信の柱（カンマ区切り）")
    p = sp.add_parser("add"); p.add_argument("--dir", required=True); p.add_argument("--title", required=True)
    p.add_argument("--pillar"); p.add_argument("--publish"); p.add_argument("--notes")
    p = sp.add_parser("list"); p.add_argument("--dir", required=True)
    p = sp.add_parser("move"); p.add_argument("--dir", required=True); p.add_argument("--id", required=True)
    p.add_argument("--stage", required=True); p.add_argument("--publish")
    p = sp.add_parser("week"); p.add_argument("--dir", required=True); p.add_argument("--date")
    p = sp.add_parser("checklist"); p.add_argument("--dir", required=True); p.add_argument("--id", required=True)
    p = sp.add_parser("review"); p.add_argument("--dir", required=True); p.add_argument("--csv", required=True)
    a = ap.parse_args()
    f = {"init": cmd_init, "add": cmd_add, "list": cmd_list, "move": cmd_move, "week": cmd_week,
         "checklist": cmd_checklist, "review": cmd_review}.get(a.cmd)
    if not f:
        ap.print_help()
        sys.exit(1)
    f(a)


if __name__ == "__main__":
    main()
