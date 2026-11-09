# -*- coding: utf-8 -*-
"""キットを使う前の「道具そろっているか」点検（読むだけ。何もインストールしません）。

使い方:  python3 env_check.py            （Windows は python env_check.py）
         python3 env_check.py --json     （機械で読む用）

終了コード: 0 = 必須の道具がそろっている / 1 = 足りない必須の道具がある
鍵（GEMINI_API_KEY）は「入っているか」だけを見ます。中身は絶対に表示しません。
"""
import argparse
import json
import os
import platform
import shutil
import subprocess
import sys

LINKS = {
    "python": "https://www.python.org/downloads/",
    "ffmpeg": "https://ffmpeg.org/download.html",
    "homebrew": "https://brew.sh/",
    "pillow": "https://pillow.readthedocs.io/en/stable/installation/basic-installation.html",
    "chrome": "https://www.google.com/chrome/",
    "edge": "https://www.microsoft.com/edge",
    "whisper": "https://github.com/openai/whisper",
    "aistudio": "https://aistudio.google.com/",
}


def os_name():
    s = platform.system()
    return {"Darwin": "Mac", "Windows": "Windows"}.get(s, s or "不明")


def find_ffmpeg():
    cands = [os.environ.get("FFMPEG"), shutil.which("ffmpeg"),
             os.path.expanduser("~/.npm-global/bin/ffmpeg"),
             "/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"]
    for c in cands:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return None


def ffmpeg_version(path):
    try:
        p = subprocess.run([path, "-version"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           text=True, timeout=20)
        return (p.stdout.splitlines() or [""])[0].strip()
    except Exception as e:  # noqa: BLE001
        return "版を読めませんでした: %s" % e


def find_browser():
    sysname = platform.system()
    if sysname == "Darwin":
        cands = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                 "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                 "/Applications/Chromium.app/Contents/MacOS/Chromium",
                 "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
                 os.path.expanduser("~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")]
    elif sysname == "Windows":
        cands = []
        for base in (os.environ.get("PROGRAMFILES", r"C:\Program Files"),
                     os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
                     os.environ.get("LOCALAPPDATA", "")):
            cands += [os.path.join(base, r"Google\Chrome\Application\chrome.exe"),
                      os.path.join(base, r"Microsoft\Edge\Application\msedge.exe")]
    else:
        cands = [shutil.which(n) or "" for n in ("google-chrome", "chromium", "chromium-browser", "microsoft-edge")]
    for p in cands:
        if p and os.path.exists(p):
            return p
    return None


def has_module(name):
    try:
        __import__(name)
        return True
    except Exception:  # noqa: BLE001
        return False


def check():
    win = platform.system() == "Windows"
    mac = platform.system() == "Darwin"
    py = "python" if win else "python3"
    pip = "pip" if win else "pip3"
    items = []

    def add(key, label, ok, required, detail, fix):
        items.append({"key": key, "label": label, "ok": bool(ok), "required": required,
                      "detail": detail, "fix": fix if not ok else ""})

    v = sys.version_info
    add("python", "Python 3.8 以上", v >= (3, 8), True,
        "Python %d.%d.%d" % (v.major, v.minor, v.micro),
        "公式ページから入れてください: %s" % LINKS["python"])

    ff = find_ffmpeg()
    add("ffmpeg", "ffmpeg（動画・音声を作る道具）", ff, True,
        ffmpeg_version(ff) if ff else "見つかりません",
        ("Mac: Homebrew（%s）を入れてから  brew install ffmpeg\n" % LINKS["homebrew"]
         if mac else
         "Windows: PowerShell で  winget install Gyan.FFmpeg  （入れたらターミナルを開き直す）\n")
        + "公式の案内: %s" % LINKS["ffmpeg"])

    add("pillow", "Pillow（画像を作る Python の部品）", has_module("PIL"), True,
        "入っています" if has_module("PIL") else "入っていません",
        "ターミナルで  %s install pillow   公式の案内: %s" % (pip, LINKS["pillow"]))

    br = find_browser()
    add("browser", "Google Chrome か Microsoft Edge（サムネ画像を写す）", br, True,
        br or "見つかりません",
        "どちらか1つを公式ページから入れてください: Chrome %s / Edge %s" % (LINKS["chrome"], LINKS["edge"]))

    # ここから下は任意
    wh = shutil.which("whisper") or shutil.which("whisper-cli") or shutil.which("whisper-cpp")
    add("whisper", "（任意）whisper（長い動画の文字起こし）", wh, False,
        wh or "入っていません（字幕ファイル .srt を自分で用意すれば不要）",
        "使いたいときだけ:  %s install -U openai-whisper   案内: %s" % (pip, LINKS["whisper"]))

    if mac:
        say = shutil.which("say")
        add("voice", "内蔵の読み上げ（Mac の say）", say, False, say or "見つかりません",
            "Mac の「システム設定 > アクセシビリティ > 読み上げコンテンツ」で日本語の声を確認")
    elif win:
        add("voice", "内蔵の読み上げ（Windows の音声）", True, False,
            "Windows 標準の音声を使います（日本語の声が無い場合は 設定 > 時刻と言語 > 音声 で追加）", "")

    key_set = bool(os.environ.get("GEMINI_API_KEY"))
    add("gemini", "（任意）GEMINI_API_KEY（声を良くしたいときだけ）", key_set, False,
        "入っています（中身は表示しません）" if key_set else "入っていません（無くても最後まで作れます）",
        "使いたいときだけ。Google AI Studio（%s）でキーを作り、環境変数に入れます。"
        "キーを文章やファイルに書いて人に渡さないでください。" % LINKS["aistudio"])

    return {"os": os_name(), "os_detail": platform.platform(), "python_cmd": py, "items": items}


def main():
    ap = argparse.ArgumentParser(description="キットの道具点検（読むだけ）")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    r = check()
    missing = [i for i in r["items"] if i["required"] and not i["ok"]]
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        print("== 道具の点検（%s） ==" % r["os"])
        for i in r["items"]:
            mark = "OK  " if i["ok"] else ("足りない" if i["required"] else "なし（任意）")
            print("[%s] %s … %s" % (mark, i["label"], i["detail"]))
            if i["fix"] and (i["required"] or not i["ok"]):
                for line in i["fix"].splitlines():
                    print("        → " + line)
        print("== 必須で足りないもの: %d件 ==" % len(missing))
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
