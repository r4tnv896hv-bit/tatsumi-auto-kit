# -*- coding: utf-8 -*-
"""ショート動画スキル共通の小道具（ffmpeg の場所探し・長さの測定・字幕ファイル・メタデータ確認）。

short-clip と short-from-article の両方に同じファイルを置いています。
片方を直したら、もう片方にもコピーしてください（字幕の折り返しは jp_linebreak.py。これも両方に同じものを置く）。
"""
import os
import re
import shutil
import subprocess
import sys

FPS = 30
W, H = 1080, 1920


# ---------------------------------------------------------------- ffmpeg
def find_ffmpeg():
    cands = [os.environ.get("FFMPEG"), shutil.which("ffmpeg"),
             os.path.expanduser("~/.npm-global/bin/ffmpeg"),
             "/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"]
    for c in cands:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    sys.exit("ffmpeg が見つかりません。README の「準備」を見て入れてください（brew install ffmpeg など）。")


FFMPEG = find_ffmpeg()


def run(args, cwd=None):
    """ffmpeg を実行。失敗したらエラー全文を出して止まる（要約しない）。"""
    p = subprocess.run([FFMPEG, "-hide_banner", "-y"] + args, cwd=cwd,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        sys.stderr.write(p.stderr)
        raise SystemExit("ffmpeg が失敗しました（上がエラー全文です）。終了コード %d" % p.returncode)
    return p


def _info(path):
    p = subprocess.run([FFMPEG, "-hide_banner", "-i", path], stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, text=True)
    return p.stderr


# ---------------------------------------------------------------- 長さの測定
def container_duration(path):
    """ファイル全体（コンテナ）の長さ。プレイヤーに表示される長さ。"""
    m = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", _info(path))
    if not m:
        raise SystemExit("長さが読めません: %s" % path)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def stream_duration(path, kind):
    """映像(kind='v')・音声(kind='a')を実際に最後まで読み、最後の位置を返す。
    「音声は終わったのに映像だけ止まった絵が何分も続く」事故を見つけるため。"""
    p = subprocess.run([FFMPEG, "-hide_banner", "-v", "error", "-i", path, "-map", "0:%s:0" % kind,
                        "-f", "null", "-", "-progress", "pipe:1", "-nostats"],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    vals = re.findall(r"out_time_us=(\d+)", p.stdout)
    return int(vals[-1]) / 1e6 if vals else 0.0


def video_size(path):
    m = re.search(r"Video: .*?, (\d{2,5})x(\d{2,5})", _info(path))
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def leftover_metadata(path):
    """消し忘れの情報（作成日時・エンコーダ名・位置情報・AIラベルなど）を探す。空なら合格。"""
    found = []
    txt = _info(path)
    for key in ("creation_time", "encoder", "comment", "title", "artist", "location",
                "com.apple", "date", "description", "copyright"):
        if re.search(r"^\s+%s\s*:" % re.escape(key), txt, re.M):
            found.append("タグ:" + key)
    with open(path, "rb") as f:
        data = f.read()
    for needle in (b"c2pa", b"jumb", b"caBX", b"x264 - core", b"Lavf", b"Lavc"):
        if needle in data:
            found.append("中身:" + needle.decode())
    return found


def verify(path, planned, tol=0.5, size=(W, H)):
    """完成ファイルを点検。planned は予定の長さ（秒）。結果を表示し、合否(bool)を返す。"""
    c = container_duration(path)
    v = stream_duration(path, "v")
    a = stream_duration(path, "a")
    wh = video_size(path)
    meta = leftover_metadata(path)
    ok = (abs(c - planned) <= tol and abs(v - planned) <= tol and abs(a - planned) <= tol
          and (size is None or wh == tuple(size)) and not meta)
    print("[点検] %s" % os.path.basename(path))
    print("   予定 %.2f秒 / 全体 %.2f秒 / 映像 %.2f秒 / 音声 %.2f秒 / 画面 %dx%d / 残った情報 %s → %s"
          % (planned, c, v, a, wh[0], wh[1], ",".join(meta) or "なし", "合格" if ok else "★不合格"))
    return ok


# ---------------------------------------------------------------- 仕上げ（つなぐ＋情報を消す）
def concat_and_strip(parts, out, workdir):
    """同じ設定で作った部品 mp4 を「concat demuxer」で無劣化につなぎ、情報を消して out に書く。
    ※ 1本でも必ずここを通す（メタデータ消しと x264 の署名消しを兼ねる）。"""
    lst = os.path.join(workdir, "_list.txt")
    with open(lst, "w", encoding="utf-8") as f:
        for p in parts:
            f.write("file '%s'\n" % os.path.abspath(p).replace("'", "'\\''"))
    run(["-f", "concat", "-safe", "0", "-i", lst, "-map", "0:v:0", "-map", "0:a:0", "-c", "copy",
         "-map_metadata:s:v", "-1", "-map_metadata:s:a", "-1",
         "-bsf:v", "filter_units=remove_types=6",          # x264 の署名(SEI)を消す
         "-map_metadata", "-1", "-map_chapters", "-1",
         "-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact",
         "-movflags", "+faststart", out])


def frames(sec):
    """秒数を 30fps のコマ数ちょうどに丸める（部品の長さのズレをためないため）。"""
    return round(sec * FPS) / FPS


ENC_V = ["-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact",
         "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
         "-r", str(FPS), "-video_track_timescale", "15360"]
ENC_A = ["-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2"]


# ---------------------------------------------------------------- フォント
_NOTO_DIRS = ("/usr/share/fonts/opentype/noto", "/usr/share/fonts/noto-cjk", "/usr/share/fonts/google-noto-cjk")


def jp_font(weight="W6"):
    # Mac（ヒラギノ）→ Linux（Noto Sans CJK。細い字は Regular、それ以外は Bold）の順に探す
    noto = ("Regular", "Bold") if weight in ("W0", "W1", "W2", "W3") else ("Bold", "Regular")
    cands = ["/System/Library/Fonts/ヒラギノ角ゴシック %s.ttc" % weight,
             "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
             "/System/Library/Fonts/Hiragino Sans GB.ttc",
             "/Library/Fonts/Arial Unicode.ttf"]
    cands += [os.path.join(d, "NotoSansCJK-%s.ttc" % k) for k in noto for d in _NOTO_DIRS]
    for p in cands:
        if os.path.exists(p):
            return p
    sys.exit("日本語フォントが見つかりません。Linux は次で入ります: sudo apt-get install fonts-noto-cjk")


def ass_font(weight="W7"):
    """字幕（ASS）に書くフォントの名前と太字の印。Mac はヒラギノ、Linux は Noto Sans CJK JP の太字。"""
    if "NotoSansCJK" in os.path.basename(jp_font(weight)):
        return "Noto Sans CJK JP", -1
    return "Hiragino Sans", 0


# ---------------------------------------------------------------- 内蔵の読み上げ
_OJ_DICS = ("/var/lib/mecab/dic/open-jtalk/naist-jdic", "/usr/share/open-jtalk/dic",
            "/usr/local/share/open_jtalk/dic", "/usr/share/open_jtalk/dic")
_OJ_VOICES = ("/usr/share/hts-voice/mei/mei_normal.htsvoice",
              "/usr/share/hts-voice/nitech-jp-atr503-m001/nitech_jp_atr503_m001.htsvoice",
              "/usr/share/open-jtalk/voices/nitech_jp_atr503_m001.htsvoice")
OJ_HINT = ("Linux の読み上げ（Open JTalk）が見つかりません。次で入ります:\n"
           "  sudo apt-get install open-jtalk open-jtalk-mecab-naist-jdic hts-voice-nitech-jp-atr503-m001")


def find_open_jtalk():
    """Linux の読み上げ Open JTalk の（コマンド, 辞書, 声）。そろっていなければ None。
    声を変えるときは環境変数 OPEN_JTALK_VOICE に .htsvoice の絶対パスを入れる。"""
    exe = shutil.which("open_jtalk")
    dic = next((d for d in (os.environ.get("OPEN_JTALK_DIC", ""),) + _OJ_DICS if d and os.path.isdir(d)), None)
    voice = next((v for v in (os.environ.get("OPEN_JTALK_VOICE", ""),) + _OJ_VOICES if v and os.path.isfile(v)), None)
    return (exe, dic, voice) if exe and dic and voice else None


def local_tts_name():
    """このパソコンで使う内蔵の読み上げの名前（say / open_jtalk）。無ければ None。"""
    if shutil.which("say"):
        return "say"
    return "open_jtalk" if find_open_jtalk() else None


def local_tts(text, wav, voice=None, rate=None, sr=48000):
    """内蔵の声で text を読み、モノラルの wav にする。Mac は say、Linux は Open JTalk。
    rate: Mac は1分の語数（例 180）。Linux は百分率（100 が標準の速さ）。"""
    tmp = wav + ".tmp"
    if shutil.which("say"):
        tmp += ".aiff"
        cmd = ["say", "-v", voice or "Kyoko", "-o", tmp]
        if rate:
            cmd += ["-r", str(rate)]
        subprocess.run(cmd + [text], check=True)
    else:
        oj = find_open_jtalk()
        if not oj:
            sys.exit(OJ_HINT)
        tmp += ".wav"
        cmd = [oj[0], "-x", oj[1], "-m", oj[2], "-ow", tmp]
        if rate:
            cmd += ["-r", "%.2f" % (float(rate) / 100.0)]
        line = " ".join(text.split()) + "\n"  # Open JTalk は1行ずつ読むので、改行をまとめる
        subprocess.run(cmd, input=line.encode("utf-8"), check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    run(["-i", tmp, "-ac", "1", "-ar", str(sr), "-c:a", "pcm_s16le", wav])
    os.remove(tmp)


def make_fontsdir(workdir, weight="W7"):
    """字幕用フォントだけを入れたフォルダを作る（libass に確実に太字の日本語フォントを使わせる）。"""
    d = os.path.join(workdir, "fonts")
    os.makedirs(d, exist_ok=True)
    src = jp_font(weight)
    dst = os.path.join(d, "jp" + os.path.splitext(src)[1])
    if not os.path.exists(dst):
        os.symlink(src, dst)
    return d


# ---------------------------------------------------------------- 字幕（SRT 読み・ASS 書き）
def _t(s):
    h, m, rest = s.strip().replace(",", ".").split(":")
    return int(h) * 3600 + int(m) * 60 + float(rest)


def read_srt(path):
    with open(path, encoding="utf-8-sig") as f:
        blocks = re.split(r"\n\s*\n", f.read().strip())
    cues = []
    for b in blocks:
        lines = [l for l in b.strip().splitlines() if l.strip()]
        for i, l in enumerate(lines):
            if "-->" in l:
                a, z = l.split("-->")
                text = "".join(lines[i + 1:]).strip()
                text = re.sub(r"<[^>]+>", "", text)
                if text:
                    cues.append({"start": _t(a), "end": _t(z.split()[0]), "text": text})
                break
    return cues


def srt_time(t):
    ms = int(round(t * 1000))
    return "%02d:%02d:%02d,%03d" % (ms // 3600000, ms // 60000 % 60, ms // 1000 % 60, ms % 1000)


def write_srt(cues, path):
    with open(path, "w", encoding="utf-8") as f:
        for i, c in enumerate(cues, 1):
            f.write("%d\n%s --> %s\n%s\n\n" % (i, srt_time(c["start"]), srt_time(c["end"]), c["text"]))


def ass_time(t):
    cs = int(round(max(t, 0) * 100))
    return "%d:%02d:%02d.%02d" % (cs // 360000, cs // 6000 % 60, cs // 100 % 60, cs % 100)


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jp_linebreak import wrap as _jp_wrap  # noqa: E402  言葉の途中で切らない折り返し（同じフォルダ）


def text_units(s):
    """画面上の幅の目安（全角=1、半角=0.55）。"""
    return sum(0.55 if ord(ch) < 0x2000 else 1.0 for ch in s)


def _split_max(text, limit):
    """どのかたまりもなるべく limit 文字以内で、言葉の途中では切らずに分ける。
    収まらないときは +4文字まではみ出し、それでも無理ならその長さのまま（表示側で文字を小さくする）。"""
    lines, _ = _jp_wrap(text, limit, measure=text_units, slack=4)
    return lines


def wrap_jp(text, width=12):
    """日本語を1行 width 文字以内で、行の長さをそろえて折り返す。"""
    return _split_max(text.strip(), width)


def split_for_screen(text, width=12, max_lines=2):
    """長い字幕を「1画面2行まで」のかたまりに分ける。
    まず文の終わり（。！？）で区切り、1画面に入る分だけ文をまとめる。長すぎる文だけ途中で分ける。"""
    per = width * max_lines
    sentences = [x for x in re.split(r"(?<=[。！？!?])", text.strip()) if x]
    chunks, cur = [], ""
    for sen in sentences:
        if len(sen) > per:
            if cur:
                chunks.append(cur)
                cur = ""
            chunks += _split_max(sen, per)
        elif not cur:
            cur = sen
        elif len(cur) <= width and len(sen) <= width:
            cur += sen  # 短い文どうしは「1文1行」で同じ画面に並べる
            chunks.append(cur)
            cur = ""
        else:
            chunks.append(cur)
            cur = sen
    if cur:
        chunks.append(cur)
    # 1画面は2行まで。言葉の途中では切らない（長い行は write_ass が文字を小さくする）
    return ["\\N".join(_jp_wrap(c.strip(), width, measure=text_units, slack=4, max_lines=2)[0]) for c in chunks]


ASS_HEAD = """[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,{font},{sub_size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,{bold},0,0,0,100,100,0,0,1,7,2,2,90,90,{sub_margin},1
Style: Title,{font},{title_size},&H0000E6FF,&H0000E6FF,&H00000000,&H64000000,{bold},0,0,0,100,100,0,0,1,7,2,8,80,80,{title_margin},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def fit_size(text, base_size, avail_px):
    """いちばん長い行が avail_px に収まる文字の大きさ（収まるなら base_size のまま）。"""
    longest = max([text_units(l) for l in text.split("\\N")] or [1])
    need = longest * base_size
    return base_size if need <= avail_px else max(int(base_size * avail_px / need), int(base_size * 0.6))


def write_ass(path, subs, title=None, title_end=None, sub_size=72, title_size=84,
              sub_margin=420, title_margin=250):
    """subs = [(start, end, text)]（その部品の頭を0秒とした時間）。
    画面の安全な範囲: 下は 420px 空ける（いいね・説明文のボタンに隠れない）、上は 250px 空ける。
    自動の折り返しは切ってある（WrapStyle 2）。行が長いときは、その字幕だけ文字を小さくする（{\\fs}）。"""
    with open(path, "w", encoding="utf-8") as f:
        font, bold = ass_font()
        f.write(ASS_HEAD.format(w=W, h=H, sub_size=sub_size, title_size=title_size,
                                sub_margin=sub_margin, title_margin=title_margin, font=font, bold=bold))
        if title:
            t = "\\N".join(wrap_jp(title, 11))
            fs = fit_size(t, title_size, W - 160)
            t = ("{\\fs%d}" % fs if fs != title_size else "") + t
            f.write("Dialogue: 1,%s,%s,Title,,0,0,0,,%s\n" % (ass_time(0), ass_time(title_end), t))
        for a, z, text in subs:
            if z - a < 0.05:
                continue
            fs = fit_size(text, sub_size, W - 180)
            text = ("{\\fs%d}" % fs if fs != sub_size else "") + text
            f.write("Dialogue: 0,%s,%s,Sub,,0,0,0,,%s\n" % (ass_time(a), ass_time(z), text))


def chunk_cue(start, end, text, width=12):
    """1つの字幕が長いとき、文字数の割合で時間を分けて「2行ずつ」表示する。"""
    chunks = split_for_screen(text, width)
    total = sum(len(c.replace("\\N", "")) for c in chunks) or 1
    out, t = [], start
    for c in chunks:
        d = (end - start) * len(c.replace("\\N", "")) / total
        out.append((t, t + d, c))
        t += d
    return out
