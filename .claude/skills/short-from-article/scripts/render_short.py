# -*- coding: utf-8 -*-
"""台本(scripts.json)の1本を、文字スライドの縦長動画(1080x1920)にする。読み上げ＋字幕つき。

使い方:
  python3 render_short.py scripts.json --index 1 [--tts auto|say|gemini] [--outdir 出力フォルダ]

読み上げ(--tts):
  auto   … GEMINI_API_KEY があれば Gemini、なければ macOS の say（初期値）
  say    … macOS の say（Kyoko）。無料・回数制限なし
  gemini … Gemini の音声。1場面＝1回の呼び出し（1本で5回）。無料枠は回数が少ないので注意
  ※ Gemini が途中で失敗したら、声が混ざらないよう全場面を say で作り直します。
  ※ キーは環境変数から読むだけで、画面にもファイルにも書きません。
     キーを ~/.zshrc に書いている場合は  zsh -ic 'python3 render_short.py ...'  で動かす。

終了コード: 0=合格 / 3=長さなどの点検で不合格
"""
import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vidutil as vu  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

TAIL = 0.45  # 各場面の読み上げの後ろに足す「間」（秒）
THEMES = {  # 場面ごとの背景色・アクセント色
    "hook": ((24, 32, 48), (255, 214, 0)),
    "point1": ((250, 246, 236), (46, 125, 96)),
    "point2": ((250, 246, 236), (46, 125, 96)),
    "point3": ((250, 246, 236), (46, 125, 96)),
    "cta": ((46, 125, 96), (255, 255, 255)),
}
BADGE = {"hook": "", "point1": "POINT 1", "point2": "POINT 2", "point3": "POINT 3", "cta": "まとめ"}


# ---------------------------------------------------------------- 読み上げ
def tts_say(text, wav, voice, rate):
    """内蔵の声で読む。Mac は say、Windows は標準の音声合成、Linux は Open JTalk（どれも無料・回数制限なし）。"""
    vu.local_tts(text, wav, voice, rate, 48000)


def tts_gemini(text, wav, voice):
    key = os.environ.get("GEMINI_API_KEY", "")
    model = os.environ.get("GEMINI_TTS_MODEL", "gemini-3.8-flash-tts")
    url = "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent" % model
    body = {"contents": [{"parts": [{"text": text}]}],  # 「元気に読んで」などの指示は書かない（読み上げられてしまう）
            "generationConfig": {"responseModalities": ["AUDIO"],
                                 "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}}}
    for attempt in range(4):
        req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json", "x-goog-api-key": key})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                res = json.load(r)
            break
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "replace")[:300]
            if e.code in (429, 500, 503) and attempt < 3:
                print("   Gemini が混んでいます(%d)。25秒待って再試行…" % e.code)
                time.sleep(25)
                continue
            raise RuntimeError("Gemini エラー %d: %s" % (e.code, msg))
    part = res["candidates"][0]["content"]["parts"][0]["inlineData"]
    data = base64.b64decode(part["data"])
    raw = wav + ".src.wav"
    if data[:4] == b"RIFF":  # すでに WAV
        open(raw, "wb").write(data)
    else:  # 生の PCM（24kHz・16bit・モノラル）
        rate = 24000
        mime = part.get("mimeType", "")
        if "rate=" in mime:
            rate = int(mime.split("rate=")[1].split(";")[0])
        with wave.open(raw, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(data)
    vu.run(["-i", raw, "-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le", wav])
    os.remove(raw)
    print("   Gemini 音声OK（モデル %s）" % res.get("modelVersion", model))


def wav_seconds(path):
    with wave.open(path) as w:
        return w.getnframes() / float(w.getframerate())


def caption(scene):
    """字幕に出す文。読み上げ用にひらがなで書いた所(さんかげつ等)は caption に漢字・数字で書いておく。"""
    return scene.get("caption") or scene["narration"]


# ---------------------------------------------------------------- スライド画像
def draw_slide(path, title, scene, idx, n):
    bg, accent = THEMES.get(scene["role"], THEMES["point1"])
    dark_bg = sum(bg) < 300 or scene["role"] == "cta"
    fg = (255, 255, 255) if dark_bg else (35, 35, 35)
    img = Image.new("RGB", (vu.W, vu.H), bg)
    d = ImageDraw.Draw(img)
    f_title = ImageFont.truetype(vu.jp_font("W7"), 58)
    f_badge = ImageFont.truetype(vu.jp_font("W7"), 48)
    # 上: 見出し（上 250px は端末の表示に隠れやすいので避ける）
    d.text((vu.W // 2, 330), title, font=f_title, fill=accent if dark_bg else (46, 125, 96), anchor="mm")
    # 進み具合の点
    for k in range(n):
        x = vu.W // 2 + (k - (n - 1) / 2) * 44
        r = 11 if k == idx else 7
        d.ellipse([x - r, 410 - r, x + r, 410 + r], fill=accent if k == idx else (150, 150, 150))
    # 真ん中: 大きな文字（1行 8文字まで・最大3行）
    lines = []  # 台本の改行(\n)はそのまま使い、8文字を超える行だけ折り返す
    for part in scene["slide"].split("\n"):
        lines += vu.wrap_jp(part, 8) if part.strip() else []
    size = 118 if len(lines) <= 2 else 100
    longest = max([vu.text_units(l) for l in lines] or [1])
    size = min(size, int((vu.W - 80) / longest))  # 言葉の途中で切らない分、長い行は文字を小さくして収める
    f_big = ImageFont.truetype(vu.jp_font("W8"), size)
    gap = int(size * 1.35)
    y0 = 900 - gap * (len(lines) - 1) / 2
    badge = BADGE.get(scene["role"], "")
    if badge:
        bw = d.textlength(badge, font=f_badge) + 60
        by = y0 - gap / 2 - 110
        d.rounded_rectangle([vu.W / 2 - bw / 2, by, vu.W / 2 + bw / 2, by + 80], radius=40, fill=accent)
        d.text((vu.W / 2, by + 40), badge, font=f_badge, fill=bg if not dark_bg else (35, 35, 35), anchor="mm")
    for k, line in enumerate(lines):
        d.text((vu.W / 2, y0 + gap * k), line, font=f_big, fill=fg, anchor="mm",
               stroke_width=3 if dark_bg else 0, stroke_fill=(0, 0, 0))
    img.save(path)  # PIL で新しく保存＝余計な情報は入らない


# ---------------------------------------------------------------- 本体
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scripts")
    ap.add_argument("--index", type=int, default=1, help="何本目を作るか（1〜3）")
    ap.add_argument("--tts", default="auto", choices=["auto", "say", "gemini"])
    ap.add_argument("--voice", default=None, help="say なら Kyoko、Gemini なら Puck など（Windows・Linux の内蔵の声では使わない）")
    ap.add_argument("--rate", type=int, default=0, help="内蔵の声の速さ（初期値のままが自然。Mac: 1分の語数 / Windows: -10〜10 / Linux: 百分率で 100 が標準）")
    ap.add_argument("--outdir", default=None)
    a = ap.parse_args()

    with open(a.scripts, encoding="utf-8") as f:
        data = json.load(f)
    s = data["scripts"][a.index - 1]
    outdir = a.outdir or os.path.join(os.path.dirname(os.path.abspath(a.scripts)), "shorts_out")
    os.makedirs(outdir, exist_ok=True)
    work = tempfile.mkdtemp(prefix="shortart_")
    vu.make_fontsdir(work)
    scenes = s["scenes"]

    engine = a.tts
    if engine == "auto":
        engine = "gemini" if os.environ.get("GEMINI_API_KEY") else "say"
    if engine == "gemini" and not os.environ.get("GEMINI_API_KEY"):
        sys.exit("GEMINI_API_KEY が読めません。Mac は zsh -ic 'python3 …' で動かすか、--tts say（内蔵の声）を使ってください。")

    wavs = [os.path.join(work, "n%d.wav" % i) for i in range(len(scenes))]
    if engine == "gemini":
        try:
            for i, sc in enumerate(scenes):
                if i:
                    time.sleep(21)  # 無料枠は1分3回ほど
                print("読み上げ(Gemini) %d/%d" % (i + 1, len(scenes)))
                tts_gemini(sc["narration"], wavs[i], a.voice or "Puck")
        except Exception as e:  # noqa: BLE001
            print("   Gemini で作れませんでした: %s\n   → 声をそろえるため、全場面を say で作り直します。" % e)
            engine = "say"
    if engine == "say":
        for i, sc in enumerate(scenes):
            tts_say(sc["narration"], wavs[i], a.voice, a.rate)

    parts, planned = [], 0.0
    for i, sc in enumerate(scenes):
        speech = wav_seconds(wavs[i])
        d = vu.frames(speech + TAIL)
        png = os.path.join(work, "s%d.png" % i)
        draw_slide(png, s["title"], sc, i, len(scenes))
        ass = os.path.join(work, "s%d.ass" % i)
        vu.write_ass(ass, vu.chunk_cue(0.05, speech, caption(sc)))
        part = os.path.join(work, "p%d.mp4" % i)
        vu.run(["-loop", "1", "-framerate", str(vu.FPS), "-i", png, "-i", wavs[i], "-t", "%.3f" % d,
                "-filter_complex", "[0:v]ass=%s:fontsdir=fonts,format=yuv420p[v]" % os.path.basename(ass),
                "-map", "[v]", "-map", "1:a", "-af", "apad,aresample=48000"]
               + vu.ENC_V + ["-tune", "stillimage"] + vu.ENC_A + [part], cwd=work)
        parts.append(part)
        planned += d
        print("場面 %d/%d %-6s %.2f秒" % (i + 1, len(scenes), sc["role"], d))

    out = os.path.join(outdir, "%s_vertical.mp4" % s.get("id", "short%02d" % a.index))
    vu.concat_and_strip(parts, out, work)
    srt = out.replace(".mp4", ".srt")  # 投稿先で字幕を別に付けたいとき用
    cues, t = [], 0.0
    for i, sc in enumerate(scenes):
        sp = wav_seconds(wavs[i])
        for (x, y, txt) in vu.chunk_cue(0.05, sp, caption(sc)):
            cues.append({"start": t + x, "end": t + y, "text": txt.replace("\\N", "")})
        t += vu.frames(sp + TAIL)
    vu.write_srt(cues, srt)
    shutil.rmtree(work, ignore_errors=True)
    print("読み上げ: %s" % engine)
    ok = vu.verify(out, planned)
    if not 15 <= planned <= 60.5:
        print("   ※ %.1f秒 は 15〜60秒 の外です。台本を削るか足してください。" % planned)
    if not ok:
        bad = out.replace(".mp4", "_NG.mp4")
        shutil.move(out, bad)
        print("   ★不合格: %s（渡さないでください）" % bad)
        return 3
    print("完成: %s（%.2f秒）\n字幕ファイル: %s" % (out, planned, srt))
    return 0


if __name__ == "__main__":
    sys.exit(main())
