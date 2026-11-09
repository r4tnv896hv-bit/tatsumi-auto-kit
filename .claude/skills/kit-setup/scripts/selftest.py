# -*- coding: utf-8 -*-
"""入れたスキルの「試し運転」（dry-run）。動画・音声・画像は作らず、ネットにもつなぎません。

使い方:  python3 selftest.py --skills /絶対パス/.claude/skills

やること（スキルごと）:
  1 SKILL.md に name と description があるか（name がフォルダ名と同じか）
  2 scripts/ の .py が文法として読めるか（実行はしない）
  3 部品の起動確認: 使い方表示（--help）や、見本ファイルの点検を「一時フォルダの中のコピー」で走らせる
  4 最後に、スキルのフォルダの中身が1つも変わっていないかを確かめる
結果:  OK / 準備不足（ffmpeg や Pillow が無いだけ。env_check.py の案内で直る）/ NG（壊れている）
終了コード: 0 = NG なし / 1 = NG あり / 2 = 準備不足あり（NG なし）
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

SKIP = {"__pycache__", ".DS_Store", "Thumbs.db"}

SAMPLE_POSTS = """## 投稿1｜X｜学び抜粋
固定費は我慢より先に見直す。

## 投稿2｜Threads｜問いかけ
毎月いちばん迷う出費はどれですか？
"""

SAMPLE_NOTE = """# 家計簿が続かない人のための3つの手順

## はじめに
家計簿が続かない理由は、記録が多すぎることです。

## 手順1 記録は1日1回だけにする
夜に1回だけ、レシートをまとめて入れます。
"""

# スキル名 → 試し運転の中身
#   ("help", スクリプト)                     … --help で使い方が出るか（exit 0）
#   ("noargs", スクリプト, [許す終了コード])   … 引数なしで使い方が出るか
#   ("check", スクリプト, 見本, [許す終了コード], 出力に含まれるはずの文字)
PLAN = {
    "note-article": [("check", "check_draft.py", "@note", [0, 1], "== NG")],
    "yt-script": [("check", "check_script.py", "templates/script_template.json", [0, 1], "結果")],
    "yt-narration": [("help", "narrate.py")],
    "yt-video": [("help", "make_video.py"), ("help", "vedit.py")],
    "yt-thumbnail": [("help", "render_thumbnail.py")],
    "short-clip": [("help", "find_segments.py"), ("help", "make_clips.py"),
                   ("noargs", "transcribe.py", [1, 2])],
    "short-from-article": [("check", "check_scripts.py", "templates/scripts_template.json", [0, 1], "合格"),
                           ("help", "render_short.py")],
    "yt-research": [("help", "research_board.py")],
    "yt-ops": [("help", "ops.py")],
    "sns-to-note": [("check", "check_posts.py", "@posts", [0, 1], "結果")],
    "sns-post": [("check", "check_drafts.py", "@posts", [0, 1], "結果"), ("help", "review_posts.py")],
    "weekly-report": [("help", "weekly_report.py")],
    "secretary": [("help", "secretary.py")],
    "kit-setup": [("help", "env_check.py"), ("help", "make_workspace.py"), ("help", "install_skills.py"),
                  ("help", "selftest.py")],
}


def tree_hashes(d):
    out = {}
    for root, dirs, files in os.walk(d):
        dirs[:] = [x for x in dirs if x not in SKIP]
        for f in files:
            if f in SKIP:
                continue
            p = os.path.join(root, f)
            with open(p, "rb") as fh:
                out[os.path.relpath(p, d)] = hashlib.sha256(fh.read()).hexdigest()
    return out


def frontmatter(path):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    if not m:
        return None
    fm = m.group(1)
    name = re.search(r"^name:\s*(.+)$", fm, re.M)
    desc = re.search(r"^description:\s*(.*)$", fm, re.M)
    return {"name": name.group(1).strip() if name else "", "has_desc": bool(desc)}


def classify(out):
    if "ffmpeg が見つかりません" in out or "ffmpeg not found" in out.lower():
        return "準備不足", "ffmpeg が無いため止まりました（env_check.py の案内で入れてください）"
    if re.search(r"No module named '?PIL", out) or "Pillow が入っていません" in out:
        return "準備不足", "Pillow が無いため止まりました（pip install pillow）"
    return None, None


def run(cmd, cwd):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    try:
        p = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           text=True, encoding="utf-8", errors="replace", timeout=90, env=env)
        return p.returncode, p.stdout
    except subprocess.TimeoutExpired:
        return -1, "90秒たっても終わりませんでした"


def test_skill(name, sdir, work):
    results = []  # (状態, 項目, 説明)
    skill_md = os.path.join(sdir, "SKILL.md")
    fm = frontmatter(skill_md) if os.path.isfile(skill_md) else None
    if not fm:
        results.append(("NG", "SKILL.md", "SKILL.md が無いか、先頭の --- の決まりが読めません"))
    elif fm["name"] != name or not fm["has_desc"]:
        results.append(("NG", "SKILL.md", "name（%s）か description がおかしい" % fm["name"]))
    else:
        results.append(("OK", "SKILL.md", "name と description あり"))

    sc = os.path.join(sdir, "scripts")
    for f in sorted(os.listdir(sc)) if os.path.isdir(sc) else []:
        if f.endswith(".py"):
            try:
                with open(os.path.join(sc, f), encoding="utf-8") as fh:
                    compile(fh.read(), f, "exec")
                results.append(("OK", "文法 " + f, "読めました"))
            except SyntaxError as e:
                results.append(("NG", "文法 " + f, str(e)))

    for step in PLAN.get(name, []):
        kind, script = step[0], step[1]
        spath = os.path.join(sc, script)
        if not os.path.isfile(spath):
            results.append(("NG", script, "ファイルがありません"))
            continue
        if kind == "help":
            code, out = run([sys.executable, spath, "--help"], work)
            label, ok = script + " --help", code == 0 and ("usage" in out.lower() or "使い方" in out)
        elif kind == "noargs":
            code, out = run([sys.executable, spath], work)
            label, ok = script + "（引数なし）", code in step[2] and "使い方" in out
        else:  # check: 見本を一時フォルダにコピーしてから点検（スキルのフォルダに何も書かない）
            sample = step[2]
            dst = os.path.join(work, "%s_%s" % (name, os.path.basename(sample) if not sample.startswith("@") else "sample.md"))
            if sample.startswith("@"):
                with open(dst, "w", encoding="utf-8") as fh:
                    fh.write(SAMPLE_NOTE if sample == "@note" else SAMPLE_POSTS)
            else:
                shutil.copy(os.path.join(sdir, sample), dst)
            code, out = run([sys.executable, spath, dst], work)
            label = "%s で見本を点検" % script
            ok = code in step[3] and step[4] in out and "Traceback" not in out
        if ok:
            results.append(("OK", label, "動きました（終了コード %d）" % code))
            continue
        st, why = classify(out)
        if st:
            results.append((st, label, why))
        else:
            tail = "\n".join(out.strip().splitlines()[-6:])
            results.append(("NG", label, "終了コード %d。出力の最後:\n%s" % (code, tail)))
    return results


def main():
    ap = argparse.ArgumentParser(description="入れたスキルの試し運転（dry-run）")
    ap.add_argument("--skills", required=True, help="スキル置き場（…/.claude/skills）の絶対パス")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    root = os.path.abspath(os.path.expanduser(a.skills))
    work = tempfile.mkdtemp(prefix="kit-selftest-")
    report = {}
    try:
        for name in PLAN:
            sdir = os.path.join(root, name)
            if not os.path.isdir(sdir):
                report[name] = [("NG", "フォルダ", "見つかりません: " + sdir)]
                continue
            before = tree_hashes(sdir)
            res = test_skill(name, sdir, work)
            after = tree_hashes(sdir)
            res.append(("OK", "フォルダ不変", "スキルの中身は変わっていません") if before == after
                       else ("NG", "フォルダ不変", "試し運転でスキルの中のファイルが変わりました"))
            report[name] = res
    finally:
        shutil.rmtree(work, ignore_errors=True)

    flat = [r[0] for v in report.values() for r in v]
    n_ng, n_need = flat.count("NG"), flat.count("準備不足")
    if a.json:
        print(json.dumps({k: [list(x) for x in v] for k, v in report.items()}, ensure_ascii=False, indent=2))
    else:
        for name, res in report.items():
            worst = "NG" if any(r[0] == "NG" for r in res) else ("準備不足" if any(r[0] == "準備不足" for r in res) else "OK")
            print("[%s] %s" % (worst, name))
            for st, label, msg in res:
                if st != "OK" or label.startswith(("SKILL", "フォルダ")) or "--help" in label or "点検" in label or "引数" in label:
                    first, *rest = msg.splitlines() or [""]
                    print("    %-6s %s … %s" % (st, label, first))
                    for line in rest:
                        print("           " + line)
        print("== 試し運転: OK %d / 準備不足 %d / NG %d ==" % (flat.count("OK"), n_need, n_ng))
    return 1 if n_ng else (2 if n_need else 0)


if __name__ == "__main__":
    sys.exit(main())
