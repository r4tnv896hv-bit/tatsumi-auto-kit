# -*- coding: utf-8 -*-
"""作業フォルダを作る（すでにあるフォルダ・ファイルには触りません）。

使い方:  python3 make_workspace.py                    → ホームの下に kit-work/ を作る
         python3 make_workspace.py --base /絶対パス   → 置き場所を変える
         python3 make_workspace.py --dry-run          → 作る予定だけ表示

できるもの:  kit-work/ の下に research youtube shorts note sns reports memory memo logs
            memory/MEMORY.md（目次。無いときだけ作る）
"""
import argparse
import os
import sys

SUBS = ["research", "youtube", "shorts", "note", "sns", "reports", "memory", "memo", "logs"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.path.join(os.path.expanduser("~"), "kit-work"))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    base = os.path.abspath(os.path.expanduser(a.base))
    for d in [base] + [os.path.join(base, s) for s in SUBS]:
        if os.path.isdir(d):
            print("あり    " + d)
        elif a.dry_run:
            print("作る予定 " + d)
        else:
            os.makedirs(d, exist_ok=True)
            print("作った  " + d)
    idx = os.path.join(base, "memory", "MEMORY.md")
    if not a.dry_run and not os.path.exists(idx):
        with open(idx, "w", encoding="utf-8") as f:
            f.write("# MEMORY.md（業務日誌の目次。1件1行）\n\n")
        print("作った  " + idx)
    if not a.dry_run:
        bad = [s for s in SUBS if not os.path.isdir(os.path.join(base, s))]
        if bad:
            print("作れなかったフォルダ: " + ", ".join(bad))
            return 1
    print("作業フォルダ: " + base)
    return 0


if __name__ == "__main__":
    sys.exit(main())
