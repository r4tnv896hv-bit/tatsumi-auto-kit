#!/usr/bin/env python3
"""台本（script.json）とナレーション（narration フォルダ）から、顔出しなしの動画（1920x1080）を作る。

使い方:
    python3 make_video.py --script /絶対パス/script.json --narration /絶対パス/narration --out /絶対パス/video/video.mp4

画面:
    visual.type = "text"  → 文字のスライド（heading を大きく、body を小さく）
    visual.type = "image" → 自分で用意した画像（16:9 でなくても、背景をぼかして収める）
    下の帯に字幕を焼き込む（narration の文を、声の長さに合わせて切り替える）

できるもの:
    video.mp4        動画（メタデータは消してある）
    subtitles.srt    字幕ファイル（YouTube に字幕としてアップロードしたいとき用）
    frames/          途中の画像（確認用。消してもよい）

最後に、動画の長さ（コンテナの Duration）とナレーションの長さを比べる。
0.25秒より大きくずれていたら NG（終了コード 1）。

必要なもの: Python 3.8+、ffmpeg、Pillow（pip install pillow）
"""
import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jp_linebreak import wrap as jp_wrap  # noqa: E402  言葉の途中で切らない折り返し

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
except ImportError:
    print("NG   Pillow が入っていません。次を実行してください: pip3 install pillow（Windows は pip install pillow）")
    sys.exit(2)

W, H = 1920, 1080
FPS = 30
SUB_H = 230  # 字幕の帯の高さ
TOLERANCE = 0.25

THEMES = {
    "light": {"bg": (250, 247, 240), "fg": (34, 34, 34), "sub": (90, 90, 90), "accent": (230, 120, 40)},
    "dark": {"bg": (24, 28, 36), "fg": (245, 245, 245), "sub": (190, 190, 190), "accent": (255, 196, 60)},
}

FONT_CANDIDATES = {
    "bold": [
        "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "C:/Windows/Fonts/YuGothB.ttc", "C:/Windows/Fonts/meiryob.ttc", "C:/Windows/Fonts/msgothic.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    ],
    "regular": [
        "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "C:/Windows/Fonts/YuGothM.ttc", "C:/Windows/Fonts/meiryo.ttc", "C:/Windows/Fonts/msgothic.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ],
}
def find_font(kind, override=None):
    if override:
        return override
    for p in FONT_CANDIDATES[kind]:
        if os.path.exists(p):
            return p
    print("NG   日本語のフォントが見つかりません。--font-bold / --font-regular でフォントファイルを指定してください")
    print("     （Linux は sudo apt-get install fonts-noto-cjk で入ります）")
    sys.exit(2)


def font(path, size):
    return ImageFont.truetype(path, size)


def wrap(draw, text, fnt, max_w, max_lines=None):
    """幅 max_w（ピクセル）に収まるよう、言葉の途中で切らずに折り返す（jp_linebreak.py）。"""
    lines = []
    for para in (text or "").split("\n"):
        ls, _ = jp_wrap(para, max_w, measure=lambda t: draw.textlength(t, font=fnt), max_lines=max_lines)
        lines += ls
    return lines


def draw_center(draw, lines, fnt, y, fill, line_gap=1.3):
    size = fnt.size
    # Noto Sans CJK（Linux）は字の上の余白が広く、そのままだと下の線に重なるので、その分だけ上げる
    dy = -int(size * 0.24) if "NotoSansCJK" in os.path.basename(str(getattr(fnt, "path", ""))) else 0
    for ln in lines:
        w = draw.textlength(ln, font=fnt)
        draw.text(((W - w) / 2, y + dy), ln, font=fnt, fill=fill)
        y += int(size * line_gap)
    return y


def text_slide(v, theme, fb, fr, channel):
    img = Image.new("RGB", (W, H), theme["bg"])
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 14], fill=theme["accent"])
    if channel:
        d.text((60, 44), channel, font=font(fr, 40), fill=theme["sub"])
    area_h = H - SUB_H
    head = v.get("heading", "")
    body = v.get("body", "")
    size = 130
    while size > 60:
        hf = font(fb, size)
        hl = wrap(d, head, hf, W - 240)
        if len(hl) <= 2:
            break
        size -= 10
    bf = font(fr, 56)
    bl = wrap(d, body, bf, W - 320) if body else []
    total = len(hl) * int(size * 1.3) + (40 + len(bl) * int(56 * 1.4) if bl else 0)
    y = max(120, (area_h - total) // 2)
    y = draw_center(d, hl, hf, y, theme["fg"])
    if bl:
        lw = 160
        d.rectangle([(W - lw) / 2, y + 4, (W + lw) / 2, y + 12], fill=theme["accent"])
        draw_center(d, bl, bf, y + 40, theme["sub"], 1.4)
    return img


def image_slide(path, theme):
    src = Image.open(path).convert("RGB")
    bg = src.copy()
    s = max(W / bg.width, H / bg.height)
    bg = bg.resize((int(bg.width * s) + 1, int(bg.height * s) + 1))
    bg = bg.crop(((bg.width - W) // 2, (bg.height - H) // 2, (bg.width - W) // 2 + W, (bg.height - H) // 2 + H))
    bg = bg.filter(ImageFilter.GaussianBlur(40))
    bg = Image.blend(bg, Image.new("RGB", (W, H), theme["bg"]), 0.35)
    area_h = H - SUB_H - 40
    s = min((W - 120) / src.width, area_h / src.height)
    fg = src.resize((max(1, int(src.width * s)), max(1, int(src.height * s))))
    bg.paste(fg, ((W - fg.width) // 2, 20 + (area_h - fg.height) // 2))
    return bg


def subtitle_lines(draw, text, fnt, max_w, hard_w):
    """字幕を2行までに、言葉の途中で切らずに分ける。
    ぴったり収まらないときは +4文字分（ただし hard_w まで）のはみ出しを許す。
    戻り値 (lines, fits): fits=False なら、この大きさでは収まらない（呼び出し側で文字を小さくする）。"""
    measure = lambda t: draw.textlength(t, font=fnt)  # noqa: E731
    slack = max(0, min(4 * measure("あ"), hard_w - max_w))
    lines, _ = jp_wrap(text, max_w, measure=measure, slack=slack, max_lines=2)
    fits = len(lines) <= 2 and all(measure(l) <= hard_w for l in lines)
    return lines, fits


def add_subtitle(base, text, fb):
    img = base.copy()
    if not text:
        return img
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rectangle([0, H - SUB_H, W, H], fill=(0, 0, 0, 175))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    d = ImageDraw.Draw(img)
    # 字幕の帯の幅は左右 100px 空け（はみ出しを許しても左右 20px は残す）。
    # それでも収まらないときだけ、文字を小さくする（言葉の途中では切らない）
    size = 64
    while True:
        f = font(fb, size)
        lines, fits = subtitle_lines(d, text, f, W - 200, W - 40)
        if fits or size <= 36:
            break
        size -= 4
    lh = int(size * 1.35)
    y = H - SUB_H + (SUB_H - lh * len(lines)) // 2
    for ln in lines:
        w = d.textlength(ln, font=f)
        d.text(((W - w) / 2, y), ln, font=f, fill=(255, 255, 255), stroke_width=3, stroke_fill=(0, 0, 0))
        y += lh
    return img


def subtitle_chunks(text, max_chars=46):
    """ナレーションを字幕1枚分（2行・約46文字まで）に区切る。長い文は、言葉の途中で切らずに分ける。"""
    out = []
    for sent in [s for s in re.split(r"(?<=[。！？!?])", text.strip()) if s.strip()]:
        if len(sent) <= max_chars:
            out.append(sent)
        else:
            parts, _ = jp_wrap(sent, max_chars)
            out += parts
    return out or [""]


def container_duration(path):
    """ffmpeg -i の表示から、コンテナの Duration を読む（ffprobe が無くても動く）。"""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", path], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", r.stderr)
    if not m:
        return None
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def stream_durations(path):
    """映像・音声それぞれを最後まで読んで、実際の長さを測る。"""
    res = {}
    for kind, sel in (("video", "0:v:0"), ("audio", "0:a:0")):
        r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-progress", "pipe:1", "-i", path,
                            "-map", sel, "-f", "null", "-"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        ts = re.findall(r"out_time_us=(\d+)", r.stdout)
        res[kind] = int(ts[-1]) / 1e6 if ts else None
    return res


def srt_time(t):
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", required=True)
    ap.add_argument("--narration", required=True, help="yt-narration の出力フォルダ（narration.wav と timing.json）")
    ap.add_argument("--out", required=True, help="作る mp4 のパス")
    ap.add_argument("--theme", choices=list(THEMES), default="light")
    ap.add_argument("--font-bold", default=None)
    ap.add_argument("--font-regular", default=None)
    ap.add_argument("--no-subtitles", action="store_true", help="字幕を焼き込まない")
    a = ap.parse_args()

    if not shutil.which("ffmpeg"):
        print("NG   ffmpeg が見つかりません（Mac: brew install ffmpeg / Windows: winget install Gyan.FFmpeg）")
        return 2
    with open(a.script, encoding="utf-8") as f:
        data = json.load(f)
    nar_dir = os.path.abspath(a.narration)
    with open(os.path.join(nar_dir, "timing.json"), encoding="utf-8") as f:
        timing = json.load(f)
    nar_wav = os.path.join(nar_dir, "narration.wav")
    with wave.open(nar_wav, "rb") as w:
        nar_sec = w.getnframes() / float(w.getframerate())

    scenes = {s["id"]: s for s in data["scenes"]}
    tids = [t["id"] for t in timing["scenes"]]
    if set(tids) != set(scenes):
        print("NG   台本とナレーションのシーンが合いません。台本を直したら、ナレーションを作り直してください")
        return 1

    theme = THEMES[a.theme]
    fb, fr = find_font("bold", a.font_bold), find_font("regular", a.font_regular)
    out = os.path.abspath(a.out)
    out_dir = os.path.dirname(out)
    frames = os.path.join(out_dir, "frames")
    os.makedirs(frames, exist_ok=True)
    for old in os.listdir(frames):
        if old.endswith(".png"):
            os.remove(os.path.join(frames, old))

    # 1) シーンごとの画像と、字幕の切り替え時刻を決める
    segs = []  # (画像パス, 開始秒, 終了秒)
    srt = []
    for t in timing["scenes"]:
        s = scenes[t["id"]]
        v = s.get("visual") or {}
        img_path = v.get("image")
        if v.get("type") == "image" and img_path and os.path.exists(img_path):
            base = image_slide(img_path, theme)
        else:
            if v.get("type") == "image":
                print(f"注意 {t['id']}: 画像が無いので文字スライドで代用します")
            base = text_slide(v, theme, fb, fr, data.get("channel", ""))
        chunks = [""] if a.no_subtitles else subtitle_chunks(s.get("narration", ""))
        total_chars = sum(max(1, len(c)) for c in chunks)
        st, sp_end, end = t["start"], t["speech_end"], t["end"]
        cur = st
        for i, c in enumerate(chunks):
            c_end = end if i == len(chunks) - 1 else cur + (sp_end - st) * max(1, len(c)) / total_chars
            p = os.path.join(frames, f"{t['id']}_{i:02d}.png")
            add_subtitle(base, c, fb).save(p)
            segs.append((p, cur, c_end))
            if c:
                srt.append((cur, min(c_end, sp_end + 0.3) if i == len(chunks) - 1 else c_end, c))
            cur = c_end
    segs[-1] = (segs[-1][0], segs[-1][1], nar_sec)

    # 2) 切り替え時刻をフレーム単位にそろえ、ずれがたまらないようにする
    lst = os.path.join(frames, "list.txt")
    with open(lst, "w", encoding="utf-8") as f:
        prev = 0
        for p, _, e in segs:
            fe = round(e * FPS)
            dur = max(1, fe - prev) / FPS
            prev = max(prev + 1, fe)
            f.write(f"file '{p.replace(os.sep, '/')}'\nduration {dur:.6f}\n")
        f.write(f"file '{segs[-1][0].replace(os.sep, '/')}'\n")

    with open(os.path.join(out_dir, "subtitles.srt"), "w", encoding="utf-8") as f:
        for i, (b, e, c) in enumerate(srt, 1):
            f.write(f"{i}\n{srt_time(b)} --> {srt_time(e)}\n{c}\n\n")

    # 3) ffmpeg で動画にする（メタデータは消す）
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
           "-f", "concat", "-safe", "0", "-i", lst, "-i", nar_wav,
           "-map", "0:v:0", "-map", "1:a:0",
           "-vf", f"fps={FPS},format=yuv420p", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
           "-tune", "stillimage", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
           "-t", f"{nar_sec:.3f}",
           "-map_metadata", "-1", "-map_chapters", "-1",
           "-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact",
           "-movflags", "+faststart", out]
    print("情報 動画を書き出し中…")
    r = subprocess.run(cmd)
    if r.returncode != 0 or not os.path.exists(out):
        print("NG   ffmpeg が失敗しました（上のエラー全文を、そのまま相談に貼ってください）")
        return 1

    # 4) 長さの確認（コンテナの Duration と、映像・音声それぞれ）
    cd = container_duration(out)
    sd = stream_durations(out)
    print(f"情報 ナレーション {nar_sec:.3f}秒 / 動画コンテナ {cd if cd is None else f'{cd:.3f}'}秒 / "
          f"映像 {sd['video'] if sd['video'] is None else round(sd['video'], 3)}秒 / "
          f"音声 {sd['audio'] if sd['audio'] is None else round(sd['audio'], 3)}秒")
    bad = [k for k, v in (("コンテナ", cd), ("映像", sd["video"]), ("音声", sd["audio"]))
           if v is None or abs(v - nar_sec) > TOLERANCE]
    if bad:
        print(f"NG   長さがナレーションと {TOLERANCE}秒以上ずれています: {'、'.join(bad)}")
        return 1
    print(f"OK   {out}")
    print(f"     字幕ファイル: {os.path.join(out_dir, 'subtitles.srt')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
