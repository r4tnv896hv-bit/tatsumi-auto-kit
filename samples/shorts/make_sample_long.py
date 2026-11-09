# -*- coding: utf-8 -*-
"""テスト用の「自分の長尺動画」を作る（架空チャンネル「ゆる家計ラボ」）。

文字スライド ＋ macOS の say の読み上げで、約2分の横長動画と、正確な字幕(.srt)を作ります。
わざと 23.976fps（ずれ事故が起きやすいコマ数）で作り、short-clip の点検を試します。

使い方:  python3 make_sample_long.py  [出力フォルダ]   （Mac 専用。say を使います）
"""
import os
import subprocess
import sys
import tempfile
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", ".claude", "skills", "short-clip", "scripts"))
import vidutil as vu  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

VOICE = "Kyoko"
SR = 48000
GAP = 0.35

SLIDES = [
    ("ゆる家計ラボ", "固定費を見直す3つの方法", [
        "こんにちは、ゆる家計ラボです。",
        "このチャンネルは、架空の家計研究所が、ゆるく節約を考える番組です。",
        "今日のテーマは、毎月の固定費を見直す方法です。"]),
    ("節約で一番効くのは？", "我慢ではなく「固定費」", [
        "実は、節約で一番効くのは、毎日の我慢ではありません。",
        "コンビニのコーヒーを我慢しても、月に数千円です。",
        "でも、固定費を一つ見直すだけで、その何倍も変わることがあります。",
        "まずは、毎月自動で出ていくお金を、全部書き出してみましょう。"]),
    ("書き出しのコツ", "明細を3か月分ならべる", [
        "書き出すときのコツは、通帳とカードの明細を、三か月分ならべることです。",
        "一か月だけだと、年に一回の支払いを見落とします。",
        "書き出したら、なくても困らないもの、に印をつけます。"]),
    ("眠っているサブスク", "無料期間のあと、払い続けていない？", [
        "九割の人が見落としているのが、使っていないサブスクです。",
        "無料期間のあと、そのまま払い続けているものはありませんか。",
        "ゆる家計ラボのスタッフも、書き出してみたら、三つも眠っていました。",
        "解約は、思い立ったその日にやるのがおすすめです。"]),
    ("スマホ料金", "使用量とプランを比べる", [
        "次に見るのは、スマホの料金です。",
        "使っているデータ量を、設定画面で確かめてみてください。",
        "毎月の使用量より、ずっと大きなプランに入っていることがよくあります。",
        "プランを変える前に、違約金や手数料がないかも確認しましょう。"]),
    ("保険", "年に1回だけ見直す", [
        "最後は、保険です。",
        "保険は、入っていること自体が、安心になりがちです。",
        "でも、いまの暮らしに合っているかは、年に一回、見直す価値があります。",
        "分からないところは、契約している会社に直接聞くのが一番確実です。"]),
    ("やってはいけないこと", "一度に全部変えない", [
        "やってはいけないのは、一度に全部変えようとすることです。",
        "疲れてしまって、結局なにも続きません。",
        "今週は一つだけ、と決めるのが、ゆる家計流です。"]),
    ("まとめ", "書き出す・止める・年1で見直す", [
        "まとめです。",
        "固定費を書き出す。眠っているサブスクを止める。スマホと保険を年に一回見直す。",
        "この三つだけで、家計はかなり軽くなります。",
        "この番組は、架空のチャンネルによるサンプル動画です。",
        "チャンネル登録で、次回のゆる家計ラボもお楽しみに。"]),
]


def tts(text, out_wav, tmp):
    aiff = os.path.join(tmp, "s.aiff")
    subprocess.run(["say", "-v", VOICE, "-o", aiff, text], check=True)
    vu.run(["-i", aiff, "-ac", "1", "-ar", str(SR), "-c:a", "pcm_s16le", out_wav])
    with wave.open(out_wav) as w:
        return w.readframes(w.getnframes())


def slide_png(path, head, sub, idx, n):
    img = Image.new("RGB", (1920, 1080), (250, 246, 236))
    d = ImageDraw.Draw(img)
    big = ImageFont.truetype(vu.jp_font("W8"), 110)
    mid = ImageFont.truetype(vu.jp_font("W6"), 64)
    small = ImageFont.truetype(vu.jp_font("W6"), 40)
    d.rectangle([0, 0, 1920, 120], fill=(46, 125, 96))
    d.text((60, 32), "ゆる家計ラボ（架空チャンネル）", font=small, fill=(255, 255, 255))
    d.text((1760, 32), "%d/%d" % (idx, n), font=small, fill=(255, 255, 255))
    d.text((960, 470), head, font=big, fill=(40, 40, 40), anchor="mm")
    d.text((960, 660), sub, font=mid, fill=(46, 125, 96), anchor="mm")
    d.rounded_rectangle([660, 760, 1260, 780], radius=10, fill=(242, 190, 80))
    img.save(path)


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else HERE
    os.makedirs(out_dir, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="yurukakei_")
    pcm, cues, t = b"", [], 0.0
    gap = b"\x00\x00" * int(SR * GAP)
    seg_files = []
    for i, (head, sub, lines) in enumerate(SLIDES, 1):
        slide_start = t
        for line in lines:
            data = tts(line, os.path.join(tmp, "line.wav"), tmp)
            d = len(data) / 2 / SR
            cues.append({"start": t, "end": t + d, "text": line})
            pcm += data + gap
            t += d + GAP
        dur = t - slide_start
        png = os.path.join(tmp, "slide%02d.png" % i)
        slide_png(png, head, sub, i, len(SLIDES))
        seg = os.path.join(tmp, "seg%02d.mp4" % i)
        # 23.976fps でスライドごとに映像だけ作る
        vu.run(["-loop", "1", "-framerate", "24000/1001", "-i", png, "-t", "%.3f" % dur,
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "24000/1001", seg])
        seg_files.append(seg)
    wav = os.path.join(tmp, "all.wav")
    with wave.open(wav, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm)
    lst = os.path.join(tmp, "list.txt")
    with open(lst, "w") as f:
        f.writelines("file '%s'\n" % s for s in seg_files)
    out = os.path.join(out_dir, "yurukakei_long_sample.mp4")
    vu.run(["-f", "concat", "-safe", "0", "-i", lst, "-i", wav, "-map", "0:v", "-map", "1:a",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", out])
    srt = os.path.join(out_dir, "yurukakei_long_sample.srt")
    vu.write_srt(cues, srt)
    print("作成: %s（%.2f秒）" % (out, vu.container_duration(out)))
    print("作成: %s（%d行）" % (srt, len(cues)))


if __name__ == "__main__":
    main()
