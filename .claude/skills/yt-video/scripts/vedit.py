#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
video-edit-handoff / vedit.py
編集指示書（edit.json）どおりに、カット → 字幕 → つなぎ → BGM を ffmpeg で行い、最後に長さを確かめる。

サブコマンド:
  probe   <ファイル...>                     長さ・解像度・音の有無を一覧にする
  silence <素材> --out edit.json           無音を探して「残す区間」の下書き edit.json を作る（ジェットカット）
  check   <edit.json>                      書き出さずに指示書を点検（区間が素材の長さに収まるか等）
  render  <edit.json>                      書き出し → 長さ確認 → edit_report.md

必要なもの: Python 3.8+ / ffmpeg（drawtext・subtitles が使えるもの）。ffprobe は無くても動く。
外部への送信・投稿は一切しない。
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

FONT_CANDIDATES = [
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "C:/Windows/Fonts/YuGothB.ttc",
    "C:/Windows/Fonts/meiryob.ttc",
    "C:/Windows/Fonts/meiryo.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc",
]
TOL_CLIP = 0.10   # 1クリップあたりの許容誤差（秒）
TOL_TOTAL = 0.30  # 全体の許容誤差（秒）


def die(msg, code=1):
    print("エラー: " + msg, file=sys.stderr)
    sys.exit(code)


def run(cmd):
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if r.returncode != 0:
        print(" ".join(cmd), file=sys.stderr)
        print(r.stderr.decode("utf-8", "replace")[-2500:], file=sys.stderr)
        die("ffmpeg が失敗しました（上のエラー全文を、そのまま Claude Code に貼ってください）")
    return r


def probe(path):
    """長さ・解像度・音の有無。ffprobe が無ければ ffmpeg -i の表示から読む。"""
    info = {"path": path, "duration": None, "width": None, "height": None, "audio": False}
    ffprobe = os.environ.get("FFPROBE") or shutil.which("ffprobe")
    if ffprobe:
        r = subprocess.run([ffprobe, "-v", "error", "-show_entries",
                            "format=duration:stream=codec_type,width,height", "-of", "json", path],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            j = json.loads(r.stdout.decode())
            info["duration"] = float(j["format"]["duration"])
            for s in j.get("streams", []):
                if s.get("codec_type") == "video" and not info["width"]:
                    info["width"], info["height"] = s.get("width"), s.get("height")
                if s.get("codec_type") == "audio":
                    info["audio"] = True
            return info
        except Exception:
            pass
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", path], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    t = r.stderr.decode("utf-8", "replace")
    m = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", t)
    if not m:
        die("長さを読めませんでした（ファイルが壊れているか、動画ではありません）: " + path)
    h, mi, s = m.groups()
    info["duration"] = int(h) * 3600 + int(mi) * 60 + float(s)
    m = re.search(r"Video: .*?(\d{2,5})x(\d{2,5})", t)
    if m:
        info["width"], info["height"] = int(m.group(1)), int(m.group(2))
    info["audio"] = "Audio:" in t
    return info


def esc(value):
    v = str(value).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    return "'" + v + "'"


def find_font(arg):
    if arg and os.path.exists(arg):
        return arg
    for f in FONT_CANDIDATES:
        if os.path.exists(f):
            return f
    die("日本語フォントが見つかりません。edit.json の font にフォントファイルを指定してください"
        "（Linux は sudo apt-get install fonts-noto-cjk で入ります）")


def resolve(base, p):
    return p if os.path.isabs(p) else os.path.normpath(os.path.join(base, p))


def wrap(text, n):
    out = []
    for para in str(text).split("\n"):
        while len(para) > n + 2:
            out.append(para[:n])
            para = para[n:]
        if para:
            out.append(para)
    return out


# ---------- 指示書の読み込み・点検 ----------

def load_spec(path):
    try:
        with open(path, encoding="utf-8") as f:
            spec = json.load(f)
    except Exception as e:
        die("edit.json を読めません: %s" % e)
    spec["_base"] = os.path.dirname(os.path.abspath(path))
    return spec


def check_spec(spec, quiet=False):
    """問題の一覧と、クリップごとの予定の長さを返す。"""
    errs, warns, plan = [], [], []
    base = spec["_base"]
    clips = spec.get("clips") or []
    if not clips:
        errs.append("clips が空です")
    cache = {}
    for i, c in enumerate(clips, 1):
        src = c.get("src")
        if not src:
            errs.append("clip %d: src がありません" % i)
            continue
        p = resolve(base, src)
        if not os.path.exists(p):
            errs.append("clip %d: 素材が見つかりません: %s" % (i, p))
            continue
        if p not in cache:
            cache[p] = probe(p)
        d = cache[p]["duration"]
        a = float(c.get("in", 0))
        b = float(c.get("out", d))
        if b > d + 0.05:
            errs.append("clip %d: out=%.2f が素材の長さ %.2f を超えています" % (i, b, d))
        if a < 0 or b - a <= 0.2:
            errs.append("clip %d: in=%.2f / out=%.2f の区間が短すぎるか逆です" % (i, a, b))
        if b - a > 0:
            plan.append({"no": i, "src": p, "in": a, "out": min(b, d), "dur": round(min(b, d) - a, 3),
                         "caption": c.get("caption", ""), "has_audio": cache[p]["audio"]})
    for key in ("srt", "bgm"):
        v = spec.get(key)
        if isinstance(v, dict):
            v = v.get("src")
        if v and not os.path.exists(resolve(base, v)):
            errs.append("%s が見つかりません: %s" % (key, resolve(base, v)))
    if spec.get("srt") and any(c.get("caption") for c in clips):
        warns.append("srt と clip ごとの caption が両方あります。字幕が二重になるので、どちらか一方にしてください")
    total = sum(x["dur"] for x in plan)
    if not quiet:
        print("クリップ数: %d / 予定の長さ: %.2f 秒" % (len(plan), total))
        for x in plan:
            print("  %2d. %-28s %7.2f → %7.2f (%5.2f秒)%s" % (x["no"], os.path.basename(x["src"])[:28], x["in"], x["out"], x["dur"],
                                                          "" if x["has_audio"] else "  ※音なし素材（無音を足します）"))
        for w in warns:
            print("注意: " + w)
        for e in errs:
            print("NG: " + e)
    return errs, plan, total


# ---------- 書き出し ----------

def cut_clip(x, i, spec, W, H, fps, font, work):
    d = x["dur"]
    vf = ["scale=%d:%d:force_original_aspect_ratio=decrease" % (W, H),
          "pad=%d:%d:(ow-iw)/2:(oh-ih)/2:color=black" % (W, H), "setsar=1", "fps=%d" % fps]
    if spec.get("fade_video"):
        vf.append("fade=t=in:st=0:d=0.15,fade=t=out:st=%.3f:d=0.15" % max(0, d - 0.15))
    if x["caption"]:
        size = int(H * (0.045 if W >= H else 0.032))
        lines = wrap(x["caption"], 24 if W >= H else 14)[:2]
        band_y = int(H * (0.80 if W >= H else 0.74))
        vf.append("drawbox=x=0:y=%d:w=iw:h=%d:color=black@0.55:t=fill" % (band_y, int(size * 3.2)))
        for j, line in enumerate(lines):
            tf = os.path.join(work, "cap%03d_%d.txt" % (i, j))
            with open(tf, "w", encoding="utf-8") as f:
                f.write(line)
            y = band_y + int(size * 0.35) + j * int(size * 1.3) + (int(size * 0.65) if len(lines) == 1 else 0)
            vf.append("drawtext=fontfile=%s:textfile=%s:expansion=none:fontsize=%d:fontcolor=white:x=(w-text_w)/2:y=%d"
                      % (esc(font), esc(tf), size, y))
    fs = os.path.join(work, "vf%03d.txt" % i)
    with open(fs, "w", encoding="utf-8") as f:
        f.write(",\n".join(vf))
    out = os.path.join(work, "part%03d.mp4" % i)
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", "%.3f" % x["in"], "-i", x["src"]]
    if not x["has_audio"]:
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
    af = "afade=t=in:d=0.04,afade=t=out:st=%.3f:d=0.12,aresample=44100" % max(0, d - 0.12)
    cmd += ["-t", "%.3f" % d, "-filter_script:v", fs, "-af", af,
            "-map", "0:v:0", "-map", ("1:a:0" if not x["has_audio"] else "0:a:0"),
            "-c:v", "libx264", "-preset", "medium", "-crf", str(spec.get("crf", 21)), "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "160k", "-ac", "2", "-ar", "44100", out]
    run(cmd)
    return out


def render(spec_path):
    spec = load_spec(spec_path)
    errs, plan, total = check_spec(spec)
    if errs:
        die("指示書に問題があります（上の NG を直してから、もう一度 render してください）")
    W, H = [int(v) for v in str(spec.get("size", "1920x1080")).lower().split("x")]
    fps = int(spec.get("fps", 30))
    font = find_font(spec.get("font"))
    base = spec["_base"]
    out = resolve(base, spec.get("output", "final.mp4"))
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    work = tempfile.mkdtemp(prefix="vedit_")
    rows = []
    try:
        parts = []
        for i, x in enumerate(plan, 1):
            print("カット %d/%d ..." % (i, len(plan)), flush=True)
            p = cut_clip(x, i, spec, W, H, fps, font, work)
            real = probe(p)["duration"]
            ok = abs(real - x["dur"]) <= TOL_CLIP
            rows.append((x, real, ok))
            parts.append(p)
        lst = os.path.join(work, "list.txt")
        with open(lst, "w", encoding="utf-8") as f:
            for p in parts:
                f.write("file '%s'\n" % p.replace("'", "'\\''"))
        joined = os.path.join(work, "joined.mp4")
        run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", joined])
        cur = joined
        jd = probe(joined)["duration"]

        # 字幕ファイル（.srt）を焼き込む
        if spec.get("srt"):
            srt = resolve(base, spec["srt"])
            tmp_srt = os.path.join(work, "subs.srt")
            shutil.copy(srt, tmp_srt)
            # Mac・Windows はこれまでどおり。Linux（Noto）のときだけ、入っているフォントの名前にする
            fname = "Noto Sans CJK JP" if "NotoSansCJK" in os.path.basename(font) else "Hiragino Sans"
            style = "FontName=%s,FontSize=%d,Outline=2,MarginV=40" % (fname, 22 if W >= H else 14)
            nxt = os.path.join(work, "subbed.mp4")
            run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", cur,
                 "-vf", "subtitles=%s:force_style=%s" % (esc(tmp_srt), esc(style)),
                 "-c:v", "libx264", "-preset", "medium", "-crf", str(spec.get("crf", 21)), "-pix_fmt", "yuv420p",
                 "-c:a", "copy", nxt])
            cur = nxt

        # BGM を敷く（元の音は残し、BGM は小さく・最後はフェードアウト）
        bgm = spec.get("bgm")
        if bgm:
            if isinstance(bgm, str):
                bgm = {"src": bgm}
            vol = float(bgm.get("volume", 0.12))
            fo = float(bgm.get("fade_out", 2.0))
            fc = ("[1:a]volume=%.3f,afade=t=in:d=1,afade=t=out:st=%.3f:d=%.2f,aresample=44100[b];"
                  "[0:a][b]amix=inputs=2:duration=first:normalize=0[m]" % (vol, max(0, jd - fo), fo))
            if bgm.get("loudnorm", True):
                fc += ";[m]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo[a]"
            else:
                fc += ";[m]aformat=sample_fmts=fltp:channel_layouts=stereo[a]"
            nxt = os.path.join(work, "bgm.mp4")
            run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", cur, "-stream_loop", "-1",
                 "-i", resolve(base, bgm["src"]), "-filter_complex", fc, "-map", "0:v", "-map", "[a]",
                 "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-t", "%.3f" % jd, nxt])
            cur = nxt

        run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", cur, "-c", "copy",
             "-map_metadata", "-1", "-movflags", "+faststart", out])
    finally:
        shutil.rmtree(work, ignore_errors=True)

    fin = probe(out)
    diff = abs(fin["duration"] - total)
    all_ok = diff <= TOL_TOTAL and all(ok for _, _, ok in rows)
    report = os.path.join(os.path.dirname(out), "edit_report.md")
    with open(report, "w", encoding="utf-8") as f:
        f.write("# 編集レポート\n\n")
        f.write("- 測った時刻: %s\n" % datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        f.write("- 指示書: %s\n- 書き出し: %s\n" % (os.path.abspath(spec_path), out))
        f.write("- 解像度: %sx%s / 音: %s\n" % (fin["width"], fin["height"], "あり" if fin["audio"] else "なし"))
        f.write("- 予定の長さ: %.2f 秒 / 実物: %.2f 秒 / 差: %.2f 秒 → **%s**\n\n" % (total, fin["duration"], diff, "OK" if all_ok else "NG"))
        f.write("| No | 素材 | in | out | 予定(秒) | 実物(秒) | 判定 |\n|---|---|---|---|---|---|---|\n")
        for x, real, ok in rows:
            f.write("| %d | %s | %.2f | %.2f | %.2f | %.2f | %s |\n" % (x["no"], os.path.basename(x["src"]), x["in"], x["out"], x["dur"], real, "OK" if ok else "NG"))
        f.write("\n## 人の目で見ること\n\n- [ ] 冒頭3秒で何の動画か分かるか\n- [ ] つなぎ目で声や音がブツッと切れていないか\n"
                "- [ ] 字幕の誤字・固有名詞\n- [ ] BGM が声より大きくないか\n- [ ] 他人の素材・音楽が入っていないか（利用条件を確認したか）\n")
    print("書き出し: %s" % out)
    print("レポート: %s" % report)
    print("長さの確認: 予定 %.2f 秒 / 実物 %.2f 秒 / 差 %.2f 秒 -> %s" % (total, fin["duration"], diff, "OK" if all_ok else "NG"))
    if not all_ok:
        sys.exit(2)


# ---------- 無音カットの下書き ----------

def silence(src, out_json, noise, min_sil, pad):
    info = probe(src)
    if not info["audio"]:
        die("この素材には音がありません。無音カットは使えません")
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", src, "-af", "silencedetect=n=%s:d=%s" % (noise, min_sil), "-f", "null", "-"],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    t = r.stderr.decode("utf-8", "replace")
    starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", t)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", t)]
    dur = info["duration"]
    sil = []
    for k, s in enumerate(starts):
        e = ends[k] if k < len(ends) else dur
        sil.append((max(0.0, s), e))
    keep, cur = [], 0.0
    for s, e in sil:
        if s - cur > 0.3:
            keep.append((max(0.0, cur - pad if cur > 0 else 0.0), min(dur, s + pad)))
        cur = e
    if dur - cur > 0.3:
        keep.append((max(0.0, cur - pad), dur))
    spec = {
        "output": "out/final.mp4", "size": "%dx%d" % (info["width"] or 1920, info["height"] or 1080), "fps": 30,
        "clips": [{"src": os.path.relpath(src, os.path.dirname(os.path.abspath(out_json))), "in": round(a, 2), "out": round(b, 2), "caption": ""} for a, b in keep],
        "bgm": None, "srt": None,
    }
    os.makedirs(os.path.dirname(os.path.abspath(out_json)), exist_ok=True)  # 2026-11-09 修正: 出力先フォルダが無いと止まっていた
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False, indent=2)
    kept = sum(b - a for a, b in keep)
    print("素材の長さ: %.2f 秒 / 無音の区間: %d か所 / 残す区間: %d 個（合計 %.2f 秒、%.0f%% に短縮）"
          % (dur, len(sil), len(keep), kept, 100 * kept / dur if dur else 0))
    print("下書き: %s（中身を確認してから render してください）" % out_json)


def main():
    ap = argparse.ArgumentParser(description="編集指示書どおりに ffmpeg で編集する")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("probe"); p.add_argument("files", nargs="+")
    p = sub.add_parser("silence"); p.add_argument("src"); p.add_argument("--out", required=True)
    p.add_argument("--noise", default="-35dB", help="これより小さい音を無音とみなす（既定 -35dB）")
    p.add_argument("--min", type=float, default=0.6, help="この秒数以上続く無音を切る（既定 0.6）")
    p.add_argument("--pad", type=float, default=0.12, help="話し始め・終わりに残す余白（既定 0.12秒）")
    p = sub.add_parser("check"); p.add_argument("spec")
    p = sub.add_parser("render"); p.add_argument("spec")
    a = ap.parse_args()
    if not shutil.which("ffmpeg"):
        die("ffmpeg が見つかりません。Mac: brew install ffmpeg / Windows: winget install Gyan.FFmpeg")
    if a.cmd == "probe":
        print("| ファイル | 長さ(秒) | 解像度 | 音 |\n|---|---|---|---|")
        for f in a.files:
            i = probe(f)
            print("| %s | %.2f | %s | %s |" % (os.path.basename(f), i["duration"], ("%sx%s" % (i["width"], i["height"])) if i["width"] else "-", "あり" if i["audio"] else "なし"))
    elif a.cmd == "silence":
        silence(a.src, a.out, a.noise, a.min, a.pad)
    elif a.cmd == "check":
        errs, _, _ = check_spec(load_spec(a.spec))
        print("判定: %s" % ("OK（render できます）" if not errs else "NG"))
        sys.exit(1 if errs else 0)
    elif a.cmd == "render":
        render(a.spec)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
