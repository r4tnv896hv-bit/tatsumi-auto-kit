# -*- coding: utf-8 -*-
"""segments.json のとおりに切り抜き、縦長 1080x1920 ＋ 日本語字幕焼き付け ＋ 情報消し ＋ 長さ点検 まで行う。

使い方:  python3 make_clips.py segments.json  [--outdir 出力フォルダ] [--only clip01,clip03]
終了コード: 0=全部合格 / 3=どれかが点検で不合格（そのファイルは渡さない）

長さがずれないための作り方（大事）:
  1 parts の1つずつを「-ss で頭出し → -t で長さ指定 → 作り直し」で別ファイルにする
    （長さは 30fps のコマ数ちょうどに丸める）
  2 それらを concat demuxer で“無劣化で”つなぐ
  ※ 1本のフィルタの中で trim と concat を組み合わせる方法は使わない。
    元動画のコマ数によっては、音声が終わったあとも止まった映像が何分も続くファイルができる。
  3 できたファイルを「全体・映像・音声」の3つの長さで測り、予定と ±0.5秒 以内か確かめる
"""
import argparse
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vidutil as vu  # noqa: E402

FILTERS = {
    # 横長の動画を縦長に: 背景＝同じ映像を拡大してぼかす / 手前＝元の映像を全部見せる
    "blur": ("[0:v]split=2[a][b];"
             "[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
             "boxblur=luma_radius=30:luma_power=2,eq=brightness=-0.10[bg];"
             "[b]scale=1080:1920:force_original_aspect_ratio=decrease[fg];"
             "[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1,fps=30,format=yuv420p"),
    # 真ん中を切り抜き: 人が中央にいる動画向け（左右は切れる）
    "crop": ("[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
             "setsar=1,fps=30,format=yuv420p"),
}


def subs_for(cues, a, d):
    """元動画の a 秒から d 秒ぶんにかかる字幕を、部品の頭=0秒 に直して返す。"""
    out = []
    for c in cues:
        s, e = max(c["start"], a) - a, min(c["end"], a + d) - a
        if e - s > 0.1:
            out += vu.chunk_cue(s, e, c["text"])
    return out


def make_clip(plan, clip, cues, outdir, work):
    src = plan["source"]
    vf = FILTERS[plan.get("mode", "blur")]
    fonts = vu.make_fontsdir(work)
    parts, planned = [], 0.0
    for k, (a, b) in enumerate(clip["parts"]):
        d = vu.frames(b - a)
        if d <= 0:
            raise SystemExit("%s の parts[%d] の長さが0以下です" % (clip["id"], k))
        ass = os.path.join(work, "%s_p%d.ass" % (clip["id"], k))
        vu.write_ass(ass, subs_for(cues, a, d), title=clip.get("title") or None, title_end=d)
        part = os.path.join(work, "%s_p%d.mp4" % (clip["id"], k))
        fade_out = max(d - 0.12, 0)
        vu.run(["-ss", "%.3f" % a, "-i", src, "-t", "%.3f" % d,
                "-filter_complex", vf + ",ass=%s:fontsdir=fonts[v]" % os.path.basename(ass),
                "-map", "[v]", "-map", "0:a:0",
                "-af", "aresample=48000,afade=t=in:d=0.04,afade=t=out:st=%.3f:d=0.12" % fade_out]
               + vu.ENC_V + vu.ENC_A + [part], cwd=work)
        parts.append(part)
        planned += d
    out = os.path.join(outdir, "%s_vertical.mp4" % clip["id"])
    vu.concat_and_strip(parts, out, work)
    ok = vu.verify(out, planned)
    if not 30 - 0.5 <= planned <= 60 + 0.5:
        print("   ※ 予定の長さ %.1f秒 が 30〜60秒 の外です（ショートの目安から外れています）" % planned)
    a0 = clip["parts"][0][0]
    first2 = [c["text"] for c in cues if c["end"] > a0 + 0.1 and c["start"] < a0 + 2.0]
    print("   最初の2秒に話している言葉: %s" % (" / ".join(first2) or "（なし＝つかみが弱い）"))
    if not ok:
        bad = out.replace(".mp4", "_NG.mp4")
        shutil.move(out, bad)
        print("   ★不合格のため名前を変えました: %s（渡さないでください）" % bad)
        return None, planned
    return out, planned


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("segments")
    ap.add_argument("--outdir", default=None)
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    with open(a.segments, encoding="utf-8") as f:
        plan = json.load(f)
    outdir = a.outdir or os.path.join(os.path.dirname(os.path.abspath(a.segments)), "shorts_out")
    os.makedirs(outdir, exist_ok=True)
    cues = vu.read_srt(plan["srt"])
    only = [x for x in a.only.split(",") if x]
    work = tempfile.mkdtemp(prefix="shortclip_")
    results, ng = [], 0
    for clip in plan["clips"]:
        if only and clip["id"] not in only:
            continue
        out, planned = make_clip(plan, clip, cues, outdir, work)
        if out:
            results.append((out, planned))
        else:
            ng += 1
    shutil.rmtree(work, ignore_errors=True)
    print("\n完成 %d本 / 不合格 %d本" % (len(results), ng))
    for out, planned in results:
        print("  %s  (%.2f秒)" % (out, planned))
    return 3 if ng else 0


if __name__ == "__main__":
    sys.exit(main())
