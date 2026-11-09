#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
秘書エージェント用 タスク帳スクリプト（標準ライブラリだけで動きます）

できること
  intake   メモ（箇条書き）からタスクを取り込む
  add      タスクを1件足す
  list     タスク一覧を出す
  done     タスクを完了にする
  summary  今日のまとめ（日報の下書き）をファイルに書く
  remind   リマインドの文面を「下書きファイル」に書く（どこにも送りません）

データの置き場所
  --dir で指定 > 環境変数 SECRETARY_DIR > ~/secretary の順で決まります。
  定期実行（cron など）で使うときは、必ず --dir に絶対パスを書いてください。

メモの書き方（1行1タスク）
  - 請求書を送る 期限:11/10 優先:高 #経理
  - 動画の台本を見直す 期限:明日
  - 名刺を注文する
  期限は 2026-11-10 / 11/10 / 今日 / 明日 / 明後日 が使えます。
  優先は 高 / 中 / 低（書かなければ 中）。# のあとはタグです。
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import tempfile

PRIORITY_ORDER = {"高": 0, "中": 1, "低": 2}
WEEKDAYS = "月火水木金土日"


# ---------- 置き場所・読み書き ----------

def data_dir(arg_dir):
    d = arg_dir or os.environ.get("SECRETARY_DIR") or os.path.expanduser("~/secretary")
    d = os.path.abspath(os.path.expanduser(d))
    os.makedirs(d, exist_ok=True)
    return d


def tasks_path(d):
    return os.path.join(d, "tasks.json")


def load(d):
    p = tasks_path(d)
    if not os.path.exists(p):
        return {"next_id": 1, "tasks": []}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save(d, data):
    # 途中で止まっても壊れないよう、一時ファイルに書いてから置き換える
    p = tasks_path(d)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tasks.", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)


def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


# ---------- 日付 ----------

def today(arg_date=None):
    if arg_date:
        return dt.date.fromisoformat(arg_date)
    return dt.date.today()


def parse_due(s, base):
    try:
        return _parse_due(s, base)
    except ValueError:
        raise ValueError("期限の書き方が読めません: " + s.strip())


def _parse_due(s, base):
    s = s.strip()
    if s in ("今日", "きょう"):
        return base
    if s in ("明日", "あした"):
        return base + dt.timedelta(days=1)
    if s in ("明後日", "あさって"):
        return base + dt.timedelta(days=2)
    m = re.fullmatch(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", s)
    if m:
        return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})", s)
    if m:
        d = dt.date(base.year, int(m.group(1)), int(m.group(2)))
        # 1か月以上前の日付なら、来年のことだと考える（例：12月に「1/5」と書いた）
        if d < base - dt.timedelta(days=30):
            d = dt.date(base.year + 1, d.month, d.day)
        return d
    raise ValueError("期限の書き方が読めません: " + s)


def fmt_date(iso):
    if not iso:
        return "期限なし"
    d = dt.date.fromisoformat(iso)
    return "%d/%d(%s)" % (d.month, d.day, WEEKDAYS[d.weekday()])


# ---------- 1行をタスクに ----------

def parse_line(line, base):
    """メモの1行を {title, due, priority, tags} に。タスクでない行は None。"""
    s = line.strip()
    # 空行・見出し行（# 見出し）・引用行は読み飛ばす
    if not s or re.match(r"^#{1,6}\s", s) or s.startswith(">"):
        return None
    s = re.sub(r"^(\- \[ \]|\- \[x\]|[-*・●]|\d+[.)．])\s*", "", s)
    if not s:
        return None
    due = None
    priority = "中"
    tags = []
    m = re.search(r"期限[:：]\s*(\S+)", s)
    if m:
        due = parse_due(m.group(1), base).isoformat()
        s = s.replace(m.group(0), "")
    m = re.search(r"優先[:：]\s*(高|中|低)", s)
    if m:
        priority = m.group(1)
        s = s.replace(m.group(0), "")
    for t in re.findall(r"#(\S+)", s):
        tags.append(t)
    s = re.sub(r"#\S+", "", s)
    title = re.sub(r"\s+", " ", s).strip()
    if not title:
        return None
    return {"title": title, "due": due, "priority": priority, "tags": tags}


def add_task(data, item, base):
    # 同じ題名の未完了タスクがあれば足さない（同じメモを2回取り込んでも増えない）
    for t in data["tasks"]:
        if t["status"] == "open" and t["title"] == item["title"]:
            return None
    t = dict(item)
    t["id"] = data["next_id"]
    t["status"] = "open"
    t["created"] = base.isoformat()
    t["done_on"] = None
    data["next_id"] += 1
    data["tasks"].append(t)
    return t


def sort_key(t):
    return (t["due"] or "9999-12-31", PRIORITY_ORDER.get(t["priority"], 1), t["id"])


def line_of(t):
    tags = " ".join("#" + x for x in t.get("tags", []))
    return "[%d] %s（%s・優先%s）%s" % (t["id"], t["title"], fmt_date(t["due"]), t["priority"],
                                     (" " + tags) if tags else "")


# ---------- コマンド ----------

def cmd_intake(a):
    d = data_dir(a.dir)
    base = today(a.date)
    data = load(d)
    if a.file == "-":
        lines = sys.stdin.read().splitlines()
    else:
        with open(a.file, encoding="utf-8") as f:
            lines = f.read().splitlines()
    added, skipped, errors = [], 0, []
    for ln in lines:
        try:
            item = parse_line(ln, base)
        except ValueError as e:
            errors.append("%s → %s" % (ln.strip(), e))
            continue
        if not item:
            continue
        t = add_task(data, item, base)
        if t:
            added.append(t)
        else:
            skipped += 1
    save(d, data)
    print("取り込み: %d件 / 重複で見送り: %d件 / 読めなかった行: %d件" % (len(added), skipped, len(errors)))
    for t in added:
        print("  + " + line_of(t))
    for e in errors:
        print("  ! " + e)
    if a.clear and a.file != "-" and not errors:
        write_text(os.path.abspath(a.file), "")
        print("メモを空にしました: " + os.path.abspath(a.file))
    return 1 if errors else 0


def cmd_add(a):
    d = data_dir(a.dir)
    base = today(a.date)
    data = load(d)
    try:
        item = parse_line(a.text, base)
    except ValueError as e:
        print(e)
        return 1
    if not item:
        print("タスクの文が空です")
        return 1
    t = add_task(data, item, base)
    save(d, data)
    print(("追加: " + line_of(t)) if t else "同じタスクがすでにあります")
    return 0


def cmd_list(a):
    d = data_dir(a.dir)
    data = load(d)
    ts = data["tasks"] if a.all else [t for t in data["tasks"] if t["status"] == "open"]
    if not ts:
        print("タスクはありません")
        return 0
    for t in sorted(ts, key=sort_key):
        mark = "済" if t["status"] == "done" else "未"
        print("%s %s" % (mark, line_of(t)))
    return 0


def cmd_done(a):
    d = data_dir(a.dir)
    base = today(a.date)
    data = load(d)
    hit = [t for t in data["tasks"] if t["id"] in a.ids]
    found = {t["id"] for t in hit}
    for t in hit:
        t["status"] = "done"
        t["done_on"] = base.isoformat()
        print("完了: " + line_of(t))
    save(d, data)
    missing = [i for i in a.ids if i not in found]
    for i in missing:
        print("番号 %d は見つかりません" % i)
    return 1 if missing else 0


def buckets(data, base):
    open_ts = sorted([t for t in data["tasks"] if t["status"] == "open"], key=sort_key)
    soon_limit = base + dt.timedelta(days=3)
    over, todays, soon, later, nodue = [], [], [], [], []
    for t in open_ts:
        if not t["due"]:
            nodue.append(t)
            continue
        due = dt.date.fromisoformat(t["due"])
        if due < base:
            over.append(t)
        elif due == base:
            todays.append(t)
        elif due <= soon_limit:
            soon.append(t)
        else:
            later.append(t)
    done_today = [t for t in data["tasks"] if t["status"] == "done" and t["done_on"] == base.isoformat()]
    return over, todays, soon, later, nodue, done_today


def cmd_summary(a):
    d = data_dir(a.dir)
    base = today(a.date)
    data = load(d)
    over, todays, soon, later, nodue, done_today = buckets(data, base)

    def sec(title, ts, empty="なし"):
        out = ["## " + title, ""]
        out += ["- [ ] " + line_of(t) for t in ts] if ts else ["- " + empty]
        out.append("")
        return out

    lines = ["# 今日のまとめ %s" % fmt_date(base.isoformat()), "",
             "> 自動作成：%s（このファイルは下書きです。どこにも送っていません）" %
             dt.datetime.now().strftime("%Y-%m-%d %H:%M"), "",
             "| 期限切れ | 今日まで | 3日以内 | それ以降 | 期限なし | 今日終えた |",
             "|---|---|---|---|---|---|",
             "| %d | %d | %d | %d | %d | %d |" % (len(over), len(todays), len(soon), len(later), len(nodue), len(done_today)),
             ""]
    lines += sec("期限切れ（最優先で相談）", over)
    lines += sec("今日まで", todays)
    lines += sec("3日以内", soon)
    lines += sec("4日以上先", later)
    lines += sec("期限なし（期限を決めるか、やめるか）", nodue)
    lines.append("## 今日終えたこと")
    lines.append("")
    lines += (["- [x] " + t["title"] for t in done_today] or ["- なし"])
    lines.append("")
    top = (over + todays + soon)[:3]
    lines.append("## 次にやる3つ（案）")
    lines.append("")
    lines += (["%d. %s" % (i + 1, t["title"]) for i, t in enumerate(top)] or ["1. 期限のあるタスクはありません。期限なしの中から1つ選びましょう"])
    lines.append("")
    path = os.path.join(d, "daily", base.isoformat() + ".md")
    write_text(path, "\n".join(lines))
    print("書きました: " + path)
    print("期限切れ %d / 今日 %d / 3日以内 %d / 期限なし %d / 今日完了 %d" %
          (len(over), len(todays), len(soon), len(nodue), len(done_today)))
    return 0


def cmd_remind(a):
    d = data_dir(a.dir)
    base = today(a.date)
    data = load(d)
    limit = base + dt.timedelta(days=a.days)
    targets = [t for t in sorted(data["tasks"], key=sort_key)
               if t["status"] == "open" and t["due"] and dt.date.fromisoformat(t["due"]) <= limit]
    lines = ["# リマインド下書き %s" % fmt_date(base.isoformat()), "",
             "> これは下書きです。送信はしていません。送るかどうか・誰に送るかは、ご本人が決めて手で送ってください。", ""]
    if not targets:
        lines.append("対象のタスクはありません（期限が %d 日以内のもの）。" % a.days)
    for t in targets:
        due = dt.date.fromisoformat(t["due"])
        diff = (due - base).days
        when = "期限を%d日過ぎています" % (-diff) if diff < 0 else ("今日が期限です" if diff == 0 else "期限まであと%d日です" % diff)
        lines += ["## [%d] %s" % (t["id"], t["title"]), "",
                  "- 期限：%s（%s）" % (fmt_date(t["due"]), when),
                  "- 優先：%s" % t["priority"], "",
                  "自分あての文面（案）", "",
                  "```",
                  "【リマインド】%s" % t["title"],
                  "%s。今日のうちに、最初の5分だけ手をつけましょう。" % when,
                  "終わったら「%d番 完了」と秘書に伝えてください。" % t["id"],
                  "```", ""]
    path = os.path.join(d, "drafts", "remind_%s.md" % base.isoformat())
    write_text(path, "\n".join(lines))
    print("書きました: %s（%d件・未送信）" % (path, len(targets)))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description="秘書エージェント用タスク帳（下書き専用・外部送信なし）")
    p.add_argument("--dir", help="データの置き場所（絶対パス推奨）")
    p.add_argument("--date", help="今日の日付を指定（YYYY-MM-DD。テスト用）")
    sub = p.add_subparsers(dest="cmd")
    s = sub.add_parser("intake", help="メモからタスクを取り込む")
    s.add_argument("file", help="メモのファイル（- で標準入力）")
    s.add_argument("--clear", action="store_true", help="取り込み後にメモを空にする")
    s = sub.add_parser("add", help="タスクを1件足す")
    s.add_argument("text")
    s = sub.add_parser("list", help="一覧")
    s.add_argument("--all", action="store_true", help="完了したものも出す")
    s = sub.add_parser("done", help="完了にする")
    s.add_argument("ids", type=int, nargs="+")
    sub.add_parser("summary", help="今日のまとめを書く")
    s = sub.add_parser("remind", help="リマインドの下書きを書く")
    s.add_argument("--days", type=int, default=1, help="何日先の期限までを対象にするか（標準1）")
    a = p.parse_args(argv)
    fn = {"intake": cmd_intake, "add": cmd_add, "list": cmd_list, "done": cmd_done,
          "summary": cmd_summary, "remind": cmd_remind}.get(a.cmd)
    if not fn:
        p.print_help()
        return 2
    return fn(a)


if __name__ == "__main__":
    sys.exit(main())
