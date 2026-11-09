# -*- coding: utf-8 -*-
"""台本ファイル(scripts.json)の形と長さを点検する。動画を作る前に必ず通す。

使い方:  python3 check_scripts.py scripts.json
終了コード: 0=合格 / 1=直すところあり

点検すること:
  - 台本が3本あるか / 各台本が hook・point1〜3・cta の5場面か
  - 画面の大きな文字(slide)が 16文字以内か（長いと読めない）
  - つかみ(hook)の読み上げが 2秒で言える長さ（目安 16文字以内）か
  - 読み上げ全体が 60秒以内に収まりそうか（1秒 ≒ 6.5文字で概算）
"""
import json
import sys

ROLES = ["hook", "point1", "point2", "point3", "cta"]
CHARS_PER_SEC = 6.5


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    with open(sys.argv[1], encoding="utf-8") as f:
        data = json.load(f)
    errs, warns = [], []
    scripts = data.get("scripts", [])
    if len(scripts) != 3:
        errs.append("台本は3本にしてください（いま %d本）" % len(scripts))
    for s in scripts:
        sid = s.get("id", "?")
        roles = [sc.get("role") for sc in s.get("scenes", [])]
        if roles != ROLES:
            errs.append("%s: 場面の並びは %s にしてください（いま %s）" % (sid, ROLES, roles))
        if not s.get("title"):
            errs.append("%s: title（画面上部の見出し）が空です" % sid)
        elif len(s["title"]) > 15:
            warns.append("%s: title が %d文字。15文字以内が読みやすいです" % (sid, len(s["title"])))
        total = 0
        for sc in s.get("scenes", []):
            slide, nar = sc.get("slide", ""), sc.get("narration", "")
            if not slide or not nar:
                errs.append("%s/%s: slide と narration の両方を書いてください" % (sid, sc.get("role")))
            if any(len(x) > 8 for x in slide.split("\n")):
                warns.append("%s/%s: slide の1行が8文字を超えるので自動で折り返します（\\n で自分で区切るときれい）"
                             % (sid, sc.get("role")))
            if len(slide.replace("\n", "")) > 16:
                errs.append("%s/%s: slide が %d文字。16文字以内に" % (sid, sc.get("role"), len(slide)))
            if sc.get("role") == "hook" and len(nar) > 16:
                warns.append("%s/hook: 読み上げ %d文字。最初の2秒で言い切るなら16文字以内が目安"
                             % (sid, len(nar)))
            total += len(nar) / CHARS_PER_SEC + 0.4
        if total > 58:
            errs.append("%s: 読み上げの見込みが約%.0f秒。60秒を超えそうなので削ってください" % (sid, total))
        elif total < 15:
            warns.append("%s: 見込み約%.0f秒。短すぎるかもしれません" % (sid, total))
        print("%s 「%s」 見込み 約%.0f秒" % (sid, s.get("title", ""), total))
    for w in warns:
        print("  注意:", w)
    for e in errs:
        print("  ★直す:", e)
    print("合格" if not errs else "不合格（★を直してください）")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
