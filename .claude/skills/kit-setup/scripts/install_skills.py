# -*- coding: utf-8 -*-
"""キットのスキルを Claude Code のスキル置き場へコピーする。

使い方:
  python3 install_skills.py --target user                       → ホームの .claude/skills/ へ
  python3 install_skills.py --target project --project /絶対パス → そのフォルダの .claude/skills/ へ
  （どちらも --dry-run を付けると「何をコピーするか」だけ表示して何もしません）
  --kit /絶対パス  キットのフォルダ（省略時は、このファイルの4つ上 = tatsumi-auto-kit）
  --with-agents   .claude/agents/ の担当（サブエージェント）も一緒にコピーする

決まり:
  - 同じ名前のスキルがすでにあり、中身が違うときは、上書きせず「名前.bak-日時」に退避してからコピーします。
  - 中身がまったく同じなら、何もしません。
  - コピーのあと、全ファイルの中身（ハッシュ）が元と同じかを確かめます。
終了コード: 0 = 全部コピーできて中身も一致 / 1 = どこかで失敗
"""
import argparse
import datetime
import hashlib
import os
import shutil
import sys

EXPECTED = ["kit-setup", "yt-research", "yt-script", "yt-narration", "yt-video", "yt-thumbnail",
            "yt-ops", "short-clip", "short-from-article", "note-article", "sns-to-note", "sns-post",
            "weekly-report", "secretary"]
SKIP_NAMES = {"__pycache__", ".DS_Store", "Thumbs.db"}


def default_kit():
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(here, "..", "..", "..", ".."))


def find_skills(kit):
    found = {}
    sk = os.path.join(kit, ".claude", "skills")
    if os.path.isdir(sk):  # 今のキットの形: tatsumi-auto-kit/.claude/skills/<名前>/SKILL.md
        for name in sorted(os.listdir(sk)):
            if os.path.isfile(os.path.join(sk, name, "SKILL.md")):
                found[name] = os.path.join(sk, name)
        return found
    kit_depth = kit.rstrip(os.sep).count(os.sep)
    for root, dirs, files in os.walk(kit):
        dirs[:] = [d for d in dirs if d not in SKIP_NAMES and d != "samples" and not d.startswith(".")]
        if root.rstrip(os.sep).count(os.sep) - kit_depth > 3:
            dirs[:] = []
            continue
        if "SKILL.md" in files:
            name = os.path.basename(root)
            if name in found:
                print("注意: 同じ名前のスキルが2つあります: %s と %s（先の方を使います）" % (found[name], root))
                continue
            found[name] = root
    return found


def tree_hashes(d):
    out = {}
    for root, dirs, files in os.walk(d):
        dirs[:] = [x for x in dirs if x not in SKIP_NAMES]
        for f in files:
            if f in SKIP_NAMES:
                continue
            p = os.path.join(root, f)
            h = hashlib.sha256()
            with open(p, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(chunk)
            out[os.path.relpath(p, d).replace(os.sep, "/")] = h.hexdigest()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", choices=["user", "project"], required=True)
    ap.add_argument("--project", default=None, help="--target project のときのフォルダ（絶対パス）")
    ap.add_argument("--kit", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--with-agents", action="store_true")
    a = ap.parse_args()

    kit = os.path.abspath(a.kit) if a.kit else default_kit()
    if a.target == "user":
        dest_root = os.path.join(os.path.expanduser("~"), ".claude", "skills")
    else:
        if not a.project:
            print("--target project のときは --project にフォルダの絶対パスを入れてください")
            return 1
        dest_root = os.path.join(os.path.abspath(os.path.expanduser(a.project)), ".claude", "skills")

    skills = find_skills(kit)
    print("キットの場所: " + kit)
    print("コピー先    : " + dest_root)
    missing = [n for n in EXPECTED if n not in skills]
    if missing:
        print("キットの中に見つからないスキル: " + ", ".join(missing))
        print("→ キットのフォルダを丸ごと展開したか、--kit の場所が正しいかを確かめてください。")
        return 1

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    ok = True
    for name in EXPECTED:
        src = skills[name]
        dst = os.path.join(dest_root, name)
        src_h = tree_hashes(src)
        if os.path.isdir(dst):
            if tree_hashes(dst) == src_h:
                print("同じ    %-20s（もう入っています）" % name)
                continue
            bak = dst + ".bak-" + stamp
            if a.dry_run:
                print("入替予定 %-20s（今のものは %s に退避）" % (name, os.path.basename(bak)))
                continue
            shutil.move(dst, bak)
            print("退避    %-20s → %s" % (name, os.path.basename(bak)))
        elif a.dry_run:
            print("コピー予定 %-18s %d ファイル" % (name, len(src_h)))
            continue
        os.makedirs(dest_root, exist_ok=True)
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns(*SKIP_NAMES))
        same = tree_hashes(dst) == src_h
        ok = ok and same
        print("%s %-20s %d ファイル" % ("コピー  " if same else "不一致！", name, len(src_h)))

    if a.with_agents:
        src_ag = os.path.join(kit, ".claude", "agents")
        dst_ag = os.path.join(os.path.dirname(dest_root), "agents")
        for f in sorted(os.listdir(src_ag)) if os.path.isdir(src_ag) else []:
            if not f.endswith(".md"):
                continue
            s_p, d_p = os.path.join(src_ag, f), os.path.join(dst_ag, f)
            if os.path.isfile(d_p):
                with open(s_p, "rb") as x, open(d_p, "rb") as y:
                    if x.read() == y.read():
                        print("同じ    担当 %-16s（もう入っています）" % f)
                        continue
                if a.dry_run:
                    print("入替予定 担当 %s（今のものは退避）" % f)
                    continue
                shutil.move(d_p, d_p + ".bak-" + stamp)
            elif a.dry_run:
                print("コピー予定 担当 %s" % f)
                continue
            os.makedirs(dst_ag, exist_ok=True)
            shutil.copy2(s_p, d_p)
            print("コピー  担当 %s" % f)

    if a.dry_run:
        print("（--dry-run なので何もしていません）")
        return 0
    print("== 結果: %s ==" % ("全部コピーでき、中身も元と一致しました" if ok else "一致しないものがあります"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
