# -*- coding: utf-8 -*-
"""動画から日本語の文字起こし(.srt)を作る。whisper が入っていなければ、.srt をお願いする案内を出す。

使い方:  python3 transcribe.py 動画.mp4  [出力.srt]
終了コード: 0=できた / 2=whisper が無い（.srt を用意してもらう）/ 1=失敗
"""
import glob
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vidutil as vu  # noqa: E402

NO_WHISPER = """
文字起こしの道具（whisper）が、このパソコンに入っていません。
次のどれかで、字幕ファイル(.srt)を用意して、動画と同じフォルダに置いてください。

  1 YouTube に「自分で」上げた動画なら → YouTube Studio → 字幕 → 自動字幕を .srt でダウンロード
  2 Vrew / CapCut などの編集アプリで自動字幕を作り、.srt で書き出す
  3 whisper を入れる（少し上級）:  pip3 install -U openai-whisper
     → 入れたら、もう一度このスクリプトを動かすと自動で文字起こしします

.srt を置いたら「字幕を置いたよ」と教えてください。
"""


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    src = os.path.abspath(sys.argv[1])
    out = os.path.abspath(sys.argv[2]) if len(sys.argv) > 2 else os.path.splitext(src)[0] + ".srt"
    model = os.environ.get("WHISPER_MODEL", "small")
    tmp = tempfile.mkdtemp(prefix="whisper_")
    env = dict(os.environ, PATH=os.path.dirname(vu.FFMPEG) + os.pathsep + os.environ.get("PATH", ""))

    # 1) openai-whisper のコマンド
    if shutil.which("whisper"):
        subprocess.run(["whisper", src, "--language", "ja", "--model", model, "--output_format", "srt",
                        "--output_dir", tmp], check=True, env=env)
        got = glob.glob(os.path.join(tmp, "*.srt"))
        if got:
            shutil.move(got[0], out)
            print("文字起こし完了:", out)
            return 0
    # 2) faster-whisper（Python）
    try:
        from faster_whisper import WhisperModel  # type: ignore
        segs, _ = WhisperModel(model, compute_type="int8").transcribe(src, language="ja")
        vu.write_srt([{"start": s.start, "end": s.end, "text": s.text.strip()} for s in segs], out)
        print("文字起こし完了:", out)
        return 0
    except ImportError:
        pass
    # 3) whisper.cpp（モデルの場所を WHISPER_CPP_MODEL で指定したときだけ）
    cpp = shutil.which("whisper-cli") or shutil.which("whisper-cpp")
    if cpp and os.environ.get("WHISPER_CPP_MODEL"):
        wav = os.path.join(tmp, "a.wav")
        vu.run(["-i", src, "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", wav])
        subprocess.run([cpp, "-m", os.environ["WHISPER_CPP_MODEL"], "-l", "ja", "-osrt",
                        "-of", os.path.splitext(out)[0], wav], check=True)
        print("文字起こし完了:", out)
        return 0

    print(NO_WHISPER)
    return 2


if __name__ == "__main__":
    sys.exit(main())
