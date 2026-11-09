# -*- coding: utf-8 -*-
"""字幕(.srt)から「切り抜きの候補」を機械的に洗い出し、segments.json の下書きを作る。

ここで出るのは“下書き”です。最後に選ぶのは Claude（とご本人）です。
  - 30〜60秒におさまる
  - 文の頭から始まり、文の終わり（。！？）で終わる
  - 最初の字幕（＝最初の2秒）に「つかみ」の言葉がある
を点数にして、重ならない上位 N 本を出します。

使い方:  python3 find_segments.py 動画.mp4 字幕.srt  [--count 5] [--min 30] [--max 60] [--out segments.json]
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vidutil as vu  # noqa: E402

HOOK_WORDS = ["実は", "知らない", "見落と", "損", "やめ", "やってはいけない", "絶対", "たった", "九割", "9割",
              "一番", "なぜ", "本当", "意外", "失敗", "秘密", "結論", "危険", "注意", "まだ", "ほとんどの人",
              "最後は", "ポイント", "コツ", "裏技"]
WEAK_START = ["そして", "で、", "なので", "あと", "えー", "あの", "えっと", "それで", "でも", "だから", "次に",
              "まず", "それから"]
END_MARKS = "。！？!?」"


def score_window(cues, i, j):
    first = cues[i]["text"]
    s, why = 0.0, []
    hooks = [w for w in HOOK_WORDS if w in first]
    if hooks:
        s += 3 + len(hooks)
        why.append("つかみ語:" + "・".join(hooks))
    if re.search(r"[？?]|ませんか|でしょうか", first):
        s += 2
        why.append("問いかけで始まる")
    if re.search(r"[0-9０-９一二三四五六七八九十百千万]+(つ|個|割|円|選|か月|年|回)", first):
        s += 1.5
        why.append("数字で始まる")
    if any(first.startswith(w) for w in WEAK_START):
        s -= 3
        why.append("つなぎ言葉で始まる(減点)")
    if cues[i]["start"] - (cues[i - 1]["end"] if i else 0) > 0.2:
        s += 0.5  # 前に間がある＝話の区切り
    last = cues[j]["text"]
    if last and last[-1] in END_MARKS:
        s += 1
    else:
        s -= 2
        why.append("文の途中で終わる(減点)")
    dur = cues[j]["end"] - cues[i]["start"]
    chars = sum(len(c["text"]) for c in cues[i:j + 1])
    s += min(chars / dur, 9) / 3  # 話の密度
    return s, why


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("srt")
    ap.add_argument("--count", type=int, default=5)
    ap.add_argument("--min", type=float, default=30)
    ap.add_argument("--max", type=float, default=60)
    ap.add_argument("--mode", default="blur", choices=["blur", "crop"])
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    cues = vu.read_srt(a.srt)
    total = vu.container_duration(a.video)
    cands = []
    for i in range(len(cues)):
        for j in range(i, len(cues)):
            st = max(cues[i]["start"] - 0.15, 0)
            en = min(cues[j]["end"] + 0.35, total)
            d = en - st
            if d > a.max:
                break
            if d < a.min:
                continue
            s, why = score_window(cues, i, j)
            cands.append((s, st, en, i, j, why))
    cands.sort(key=lambda c: -c[0])
    chosen = []
    for c in cands:
        if all(c[2] <= o[1] or c[1] >= o[2] for o in chosen):
            chosen.append(c)
        if len(chosen) >= a.count:
            break
    chosen.sort(key=lambda c: c[1])

    clips = []
    for n, (s, st, en, i, j, why) in enumerate(chosen, 1):
        clips.append({
            "id": "clip%02d" % n,
            "title": "",  # 画面上部の見出し（Claude が 15文字以内で付ける）
            "parts": [[round(st, 2), round(en, 2)]],
            "hook": cues[i]["text"],
            "ends_with": cues[j]["text"],
            "score": round(s, 2),
            "reason": " / ".join(why) or "特徴なし",
        })
    out = a.out or os.path.join(os.path.dirname(os.path.abspath(a.video)), "segments.json")
    plan = {"source": os.path.abspath(a.video), "srt": os.path.abspath(a.srt), "mode": a.mode,
            "clips": clips}
    with open(out, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
    for c in clips:
        p = c["parts"][0]
        print("%s  %6.2f〜%6.2f秒 (%.1f秒)  点%.1f  つかみ「%s」  理由: %s"
              % (c["id"], p[0], p[1], p[1] - p[0], c["score"], c["hook"][:24], c["reason"]))
    print("下書きを保存:", out)
    if len(clips) < 3:
        print("※ 候補が3本未満です。--min を下げる・parts を2つつなぐ、などを検討してください。")


if __name__ == "__main__":
    main()
