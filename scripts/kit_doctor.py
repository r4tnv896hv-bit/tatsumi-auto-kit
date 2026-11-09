# -*- coding: utf-8 -*-
"""キットの「健康診断」。ファイルを読むだけで、何も書き換えません。ネットにもつなぎません。

使い方:  python3 scripts/kit_doctor.py            （キットのフォルダのどこからでも）
         python3 scripts/kit_doctor.py --kit /絶対パス/tatsumi-auto-kit

見ること:
  1 スキル   .claude/skills/<名前>/SKILL.md があるか / name がフォルダ名と同じか / description があり 1024 字以内か /
             SKILL.md に書かれた scripts/〇〇.py・templates/〇〇 が本当にあるか
  2 担当     .claude/agents/<名前>.md の name・description があるか / name がファイル名と同じか
  3 部品     .py が文法として読めるか（実行はしない）
  4 設定     .claude/settings.json が JSON として読めるか
  5 秘密     APIキーらしき文字列・.env ファイルが入っていないか（.env.example は可）
  6 ライセンス  AGPL / GPL の文が、キットの部品（.py .sh .js）に入っていないか
終了コード: 0 = NG なし / 1 = NG あり
"""
import argparse
import json
import os
import re
import sys

EXPECTED_SKILLS = ["kit-setup", "yt-research", "yt-script", "yt-narration", "yt-video", "yt-thumbnail", "yt-ops",
                   "short-clip", "short-from-article", "note-article", "sns-to-note", "sns-post",
                   "weekly-report", "secretary"]
EXPECTED_AGENTS = ["researcher", "scriptwriter", "editor", "thumbnail-designer", "publisher-drafts", "analyst"]
SECRET = re.compile(r"(AIza[0-9A-Za-z_\-]{30,}|sk-ant-[0-9A-Za-z_\-]{20,}|sk-[0-9A-Za-z]{32,}|ghp_[0-9A-Za-z]{30,}|xox[bp]-[0-9A-Za-z\-]{20,})")
LICENSE_BAD = re.compile(r"GNU (AFFERO )?GENERAL PUBLIC LICENSE|SPDX-License-Identifier:\s*A?GPL", re.I)
SKIP_DIRS = {".git", "__pycache__", "node_modules"}


def front(path):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    if not m:
        return None, text
    fm = m.group(1)
    out = {}
    name = re.search(r"^name:\s*(.+)$", fm, re.M)
    out["name"] = name.group(1).strip() if name else ""
    d = re.search(r"^description:\s*(>-?|\|)?\s*(.*?)(?=^\S[\w-]*:|\Z)", fm, re.M | re.S)
    out["description"] = re.sub(r"\s+", " ", (d.group(2) if d else "")).strip()
    out["tools"] = (re.search(r"^tools:\s*(.+)$", fm, re.M) or [None, ""])[1] if re.search(r"^tools:", fm, re.M) else ""
    return out, text


def main():
    ap = argparse.ArgumentParser(description="キットの健康診断（読むだけ）")
    ap.add_argument("--kit", default=os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))
    a = ap.parse_args()
    kit = os.path.abspath(a.kit)
    ng, ok = [], 0

    sk = os.path.join(kit, ".claude", "skills")
    for name in EXPECTED_SKILLS:
        p = os.path.join(sk, name, "SKILL.md")
        if not os.path.isfile(p):
            ng.append("スキル %s: SKILL.md がありません" % name)
            continue
        fm, text = front(p)
        if not fm:
            ng.append("スキル %s: 先頭の --- が読めません" % name)
            continue
        if fm["name"] != name:
            ng.append("スキル %s: name が %r（フォルダ名と同じにする）" % (name, fm["name"]))
        if not fm["description"]:
            ng.append("スキル %s: description がありません" % name)
        elif len(fm["description"]) > 1024:
            ng.append("スキル %s: description が %d 字（1024 字以内）" % (name, len(fm["description"])))
        for ref in sorted(set(re.findall(r"(?<![\w/])((?:scripts|templates)/[\w\-.]+\.(?:py|sh|md|json|csv|html|txt))", text))):
            if not os.path.exists(os.path.join(sk, name, ref)):
                ng.append("スキル %s: SKILL.md に書かれた %s がありません" % (name, ref))
        ok += 1
    extra = sorted(set(os.listdir(sk)) - set(EXPECTED_SKILLS)) if os.path.isdir(sk) else []
    for e in extra:
        if os.path.isdir(os.path.join(sk, e)):
            print("情報 一覧に無いスキルがあります: %s（自分で足したものなら問題ありません）" % e)

    ag = os.path.join(kit, ".claude", "agents")
    for name in EXPECTED_AGENTS:
        p = os.path.join(ag, name + ".md")
        if not os.path.isfile(p):
            ng.append("担当 %s: %s.md がありません" % (name, name))
            continue
        fm, _ = front(p)
        if not fm or fm["name"] != name or not fm["description"]:
            ng.append("担当 %s: name / description を確かめる" % name)
        else:
            ok += 1

    for root, dirs, files in os.walk(kit):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            p = os.path.join(root, f)
            rel = os.path.relpath(p, kit)
            if f == ".env" or (f.startswith(".env.") and f != ".env.example"):
                ng.append("秘密: %s が入っています（配る前に消す）" % rel)
            if os.path.getsize(p) > 5_000_000 or f.endswith((".png", ".mp4", ".wav", ".mp3", ".jpg")):
                continue
            try:
                with open(p, encoding="utf-8") as fh:
                    text = fh.read()
            except (UnicodeDecodeError, OSError):
                continue
            if SECRET.search(text):
                ng.append("秘密: %s に APIキーらしき文字列があります" % rel)
            if f.endswith((".py", ".sh", ".js")) and LICENSE_BAD.search(text) and rel != os.path.join("scripts", "kit_doctor.py"):
                ng.append("ライセンス: %s に GPL / AGPL の文があります（キットには入れない）" % rel)
            if f.endswith(".py"):
                try:
                    compile(text, rel, "exec")
                except SyntaxError as e:
                    ng.append("部品: %s の文法エラー %s" % (rel, e))

    st = os.path.join(kit, ".claude", "settings.json")
    if os.path.isfile(st):
        try:
            with open(st, encoding="utf-8") as fh:
                json.load(fh)
        except ValueError as e:
            ng.append("設定: .claude/settings.json が JSON として読めません（%s）" % e)
    else:
        ng.append("設定: .claude/settings.json がありません")

    for x in ng:
        print("NG   " + x)
    print("== 健康診断: スキル %d / 担当 %d を確認、NG %d ==" % (
        sum(1 for n in EXPECTED_SKILLS if os.path.isfile(os.path.join(sk, n, "SKILL.md"))),
        sum(1 for n in EXPECTED_AGENTS if os.path.isfile(os.path.join(ag, n + ".md"))), len(ng)))
    return 1 if ng else 0


if __name__ == "__main__":
    sys.exit(main())
