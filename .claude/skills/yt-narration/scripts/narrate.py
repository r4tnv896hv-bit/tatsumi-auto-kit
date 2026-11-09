#!/usr/bin/env python3
"""台本（script.json）からナレーション音声を作る。

使い方:
    python3 narrate.py /絶対パス/script.json --out /絶対パス/narration          # 標準（パソコン内蔵の声）
    python3 narrate.py script.json --out narration --mp3                         # mp3 も作る
    python3 narrate.py script.json --out narration --engine gemini               # 声を良くしたいとき（任意）

声の種類（--engine）:
    os     … 標準。macOS は say（Kyoko）、Windows は標準の音声合成（Haruka など）。
             回数制限が無いので、長い動画でも一度で最後まで作れる
    gemini … 声を良くしたいときに使う（任意）。GEMINI_API_KEY が必要。
             無料枠は1日の回数が少ないので、長い動画は1日で作り切れないことがある。
             キーが無い・途中で上限に達したときは、声がちぐはぐにならないよう
             全シーンを内蔵の声で作り直して最後まで仕上げる（--strict なら止まる）

できるもの（--out のフォルダ）:
    s01.wav, s02.wav …   シーンごとの声
    narration.wav        全部をつないだ声（シーンの間に --gap 秒の無音）
    narration.mp3        --mp3 をつけたとき
    timing.json          各シーンの開始・終了秒（yt-video が字幕と画面の切り替えに使う）

すでに同じ文・同じ声で作ったシーンは作り直さない（Gemini の回数制限を節約）。
必要なもの: Python 3.8+ と ffmpeg。追加の pip は不要。
API キーは画面に出さない。
"""
import argparse
import base64
import hashlib
import json
import os
import platform
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import wave

RATE = 24000
API = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_MODELS = "gemini-2.5-flash-preview-tts,gemini-2.5-flash-tts"
CHUNK_CHARS = 1200  # 1回の読み上げに送る最大文字数（長いシーンは文の区切りで分ける）


class QuotaExhausted(Exception):
    """1日の上限など、待っても回復しない失敗。"""


class GeminiError(Exception):
    pass


def log(msg):
    print(msg, flush=True)


def need_ffmpeg():
    if not shutil.which("ffmpeg"):
        log("NG   ffmpeg が見つかりません。")
        log("     Mac: brew install ffmpeg / Windows: winget install Gyan.FFmpeg（入れたらターミナルを開き直す）")
        sys.exit(2)


def to_wav(src, dst, fmt_args=None):
    """どんな音声でも 24kHz・モノラル・16bit の wav にそろえる（メタデータは消す）。"""
    cmd = ["ffmpeg", "-y", "-loglevel", "error"] + (fmt_args or []) + [
        "-i", src, "-ar", str(RATE), "-ac", "1", "-c:a", "pcm_s16le",
        "-map_metadata", "-1", "-fflags", "+bitexact", "-flags:a", "+bitexact", dst]
    subprocess.run(cmd, check=True)


def wav_sec(path):
    with wave.open(path, "rb") as w:
        return w.getnframes() / float(w.getframerate())


def split_text(text, limit=CHUNK_CHARS):
    if len(text) <= limit:
        return [text]
    parts, cur = [], ""
    for sent in re.split(r"(?<=[。！？!?])", text):
        if len(cur) + len(sent) > limit and cur:
            parts.append(cur)
            cur = ""
        cur += sent
    if cur:
        parts.append(cur)
    return parts


# ---------------- Gemini ----------------

def _post(url, body, key, timeout=180):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "x-goog-api-key": key})
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def _retry_delay(err_json):
    for d in (err_json.get("error", {}).get("details") or []):
        if "retryDelay" in d:
            m = re.match(r"([\d.]+)s", str(d["retryDelay"]))
            if m:
                return float(m.group(1))
    return None


def _is_daily(err_json):
    s = json.dumps(err_json)
    return "PerDay" in s or "per day" in s.lower()


def find_tts_models(key):
    """ListModels から使える TTS モデル名を探す（指定のモデルが無いとき用）。"""
    try:
        req = urllib.request.Request(f"{API}/models?pageSize=200", headers={"x-goog-api-key": key})
        d = json.load(urllib.request.urlopen(req, timeout=60))
    except Exception:  # noqa: BLE001
        return []
    names = [m["name"].split("/", 1)[1] for m in d.get("models", [])
             if "tts" in m["name"] and "generateContent" in (m.get("supportedGenerationMethods") or [])]
    return sorted(names, key=lambda n: ("flash" not in n, n), reverse=False)


class Gemini:
    def __init__(self, key, models, voice, max_retries=6):
        self.key, self.voice, self.max_retries = key, voice, max_retries
        self.models = models
        self.model = None
        self.model_version = None

    def _call(self, model, text):
        body = {"contents": [{"parts": [{"text": text}]}],
                "generationConfig": {"responseModalities": ["AUDIO"],
                                     "speechConfig": {"voiceConfig": {
                                         "prebuiltVoiceConfig": {"voiceName": self.voice}}}}}
        url = f"{API}/models/{model}:generateContent"
        delay = 8.0
        for attempt in range(1, self.max_retries + 1):
            try:
                d = _post(url, body, self.key)
                part = d["candidates"][0]["content"]["parts"][0]["inlineData"]
                self.model_version = d.get("modelVersion", model)
                return base64.b64decode(part["data"]), part.get("mimeType", "")
            except urllib.error.HTTPError as e:
                raw = e.read().decode("utf-8", "replace")
                try:
                    ej = json.loads(raw)
                except ValueError:
                    ej = {}
                msg = ej.get("error", {}).get("message", raw)[:300]
                if e.code == 404:
                    raise LookupError(msg)
                if e.code == 429 and _is_daily(ej):
                    raise QuotaExhausted(f"1日の上限に達しました（{model}）: {msg}")
                if e.code in (429, 500, 502, 503, 504):
                    wait = _retry_delay(ej) or delay
                    wait = min(wait, 90) + random.uniform(0, 2)
                    log(f"     混雑/回数制限（HTTP {e.code}）。{wait:.0f}秒待って再試行 {attempt}/{self.max_retries}")
                    time.sleep(wait)
                    delay = min(delay * 2, 90)
                    continue
                raise GeminiError(f"HTTP {e.code}: {msg}")
            except (urllib.error.URLError, TimeoutError, KeyError, IndexError) as e:
                log(f"     通信または応答の形が想定外（{type(e).__name__}）。{delay:.0f}秒待って再試行 {attempt}/{self.max_retries}")
                time.sleep(delay)
                delay = min(delay * 2, 90)
        raise GeminiError(f"{self.max_retries}回試しても成功しませんでした")

    def synth(self, text, dst):
        candidates = [self.model] if self.model else list(self.models)
        tried = set()
        while True:
            for model in candidates:
                if model in tried:
                    continue
                tried.add(model)
                try:
                    data, mime = self._call(model, text)
                    self.model = model
                    break
                except LookupError:
                    log(f"     モデル {model} は使えません。次を試します")
            else:
                found = [m for m in find_tts_models(self.key) if m not in tried]
                if not found:
                    raise GeminiError("使える TTS モデルが見つかりません（GEMINI_TTS_MODEL で指定してください）")
                candidates = found
                continue
            break
        with tempfile.TemporaryDirectory() as td:
            raw = os.path.join(td, "raw")
            with open(raw, "wb") as f:
                f.write(data)
            if "wav" in mime.lower():
                to_wav(raw, dst)
            else:  # audio/L16;codec=pcm;rate=24000
                m = re.search(r"rate=(\d+)", mime)
                to_wav(raw, dst, ["-f", "s16le", "-ar", m.group(1) if m else "24000", "-ac", "1"])


# ---------------- パソコン内蔵の声 ----------------

class OSVoice:
    def __init__(self, voice=None, rate=None):
        self.sys = platform.system()
        self.voice, self.rate = voice, rate
        if self.sys == "Darwin":
            if not self.voice:
                listing = subprocess.run(["say", "-v", "?"], capture_output=True, text=True).stdout
                self.voice = "Kyoko" if re.search(r"^Kyoko\s", listing, re.M) else None
                if not self.voice:
                    jp = [l.split("  ")[0].strip() for l in listing.splitlines() if "ja_JP" in l]
                    self.voice = jp[0] if jp else None
                if not self.voice:
                    log("注意 日本語の声が見つかりません。システム設定 > アクセシビリティ > 読み上げコンテンツ で日本語の声を追加してください")
        elif self.sys != "Windows":
            raise RuntimeError("この OS の内蔵の声には対応していません（Gemini を使ってください）")
        self.name = f"os:{self.sys}:{self.voice or 'default'}"

    def synth(self, text, dst):
        with tempfile.TemporaryDirectory() as td:
            txt = os.path.join(td, "in.txt")
            with open(txt, "w", encoding="utf-8") as f:
                f.write(text)
            if self.sys == "Darwin":
                aiff = os.path.join(td, "out.aiff")
                cmd = ["say", "-f", txt, "-o", aiff]
                if self.voice:
                    cmd[1:1] = ["-v", self.voice]
                if self.rate:
                    cmd[1:1] = ["-r", str(self.rate)]
                subprocess.run(cmd, check=True)
                to_wav(aiff, dst)
            else:
                out = os.path.join(td, "out.wav")
                ps = (
                    "Add-Type -AssemblyName System.Speech;"
                    "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
                    "$v=$s.GetInstalledVoices()|Where-Object{$_.VoiceInfo.Culture.Name -eq 'ja-JP'}|Select-Object -First 1;"
                    "if($v){$s.SelectVoice($v.VoiceInfo.Name)};"
                    + (f"$s.Rate={int(self.rate)};" if self.rate else "")
                    + f"$s.SetOutputToWaveFile('{out}');"
                    f"$s.Speak([IO.File]::ReadAllText('{txt}',[Text.Encoding]::UTF8));$s.Dispose()")
                subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)
                to_wav(out, dst)


# ---------------- 本体 ----------------

def synth_scene(engine, text, dst):
    chunks = split_text(text)
    if len(chunks) == 1:
        engine.synth(text, dst)
        return
    with tempfile.TemporaryDirectory() as td:
        parts = []
        for i, c in enumerate(chunks):
            p = os.path.join(td, f"p{i}.wav")
            engine.synth(c, p)
            parts.append(p)
        concat_wavs(parts, dst, gap=0.15)


def concat_wavs(paths, dst, gap=0.5, tail=0.0):
    silence = b"\x00\x00" * int(RATE * gap)
    with wave.open(dst, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        for i, p in enumerate(paths):
            with wave.open(p, "rb") as w:
                out.writeframes(w.readframes(w.getnframes()))
            if i < len(paths) - 1:
                out.writeframes(silence)
        out.writeframes(b"\x00\x00" * int(RATE * tail))


def build(scenes, out, engine, label):
    """全シーンを作る。作り済み（同じ文・同じ声）は飛ばす。"""
    for s in scenes:
        text = (s.get("yomi") or s.get("narration") or "").strip()
        sid = s["id"]
        dst = os.path.join(out, f"{sid}.wav")
        stamp = os.path.join(out, f"{sid}.stamp")
        sig = hashlib.sha256(f"{label}\n{text}".encode()).hexdigest()
        if os.path.exists(dst) and os.path.exists(stamp) and open(stamp).read() == sig:
            log(f"     {sid} 作成済み（スキップ）")
            continue
        log(f"     {sid} 作成中（{len(text)}文字）")
        synth_scene(engine, text, dst)
        with open(stamp, "w") as f:
            f.write(sig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("script")
    ap.add_argument("--out", required=True, help="音声を書き出すフォルダ（絶対パスがおすすめ）")
    ap.add_argument("--engine", choices=["os", "gemini"], default="os",
                    help="os（標準・内蔵の声）/ gemini（任意・声を良くしたいとき）")
    ap.add_argument("--voice", default=None, help="Gemini の声（初期値 Kore）。--engine gemini のときだけ使う")
    ap.add_argument("--os-voice", default=None, help="内蔵の声の名前（Mac 例: Kyoko。省略時は日本語の声を自動で選ぶ）")
    ap.add_argument("--strict", action="store_true", help="--engine gemini が失敗したら、内蔵の声に切り替えず止める")
    ap.add_argument("--rate", type=int, default=None, help="OS の声の速さ（Mac: 1分の語数 例 180 / Windows: -10〜10）")
    ap.add_argument("--gap", type=float, default=0.5, help="シーンの間の無音（秒）")
    ap.add_argument("--tail", type=float, default=0.8, help="最後に足す無音（秒）")
    ap.add_argument("--mp3", action="store_true", help="narration.mp3 も作る")
    ap.add_argument("--only", default=None, help="このシーンだけ作り直す（例 s03,s05）")
    a = ap.parse_args()

    need_ffmpeg()
    with open(a.script, encoding="utf-8") as f:
        data = json.load(f)
    scenes = data.get("scenes") or []
    if not scenes:
        log("NG   script.json にシーンがありません")
        return 1
    out = os.path.abspath(a.out)
    os.makedirs(out, exist_ok=True)
    if a.only:
        keep = set(a.only.split(","))
        for s in scenes:
            if s["id"] in keep:
                for ext in (".wav", ".stamp"):
                    p = os.path.join(out, s["id"] + ext)
                    if os.path.exists(p):
                        os.remove(p)

    used = None
    if a.engine == "gemini":
        key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not key:
            log("注意 GEMINI_API_KEY が設定されていません")
            if a.strict:
                log("NG   --strict なので止めます")
                return 1
            log("情報 標準の内蔵の声で作ります")
        else:
            models = [m.strip() for m in os.environ.get("GEMINI_TTS_MODEL", DEFAULT_MODELS).split(",") if m.strip()]
            g = Gemini(key, models, a.voice or "Kore")
            log(f"情報 Gemini TTS で作ります（声: {g.voice}）")
            try:
                build(scenes, out, g, f"gemini:{g.voice}")
                used = f"gemini:{g.model_version or g.model}:{g.voice}"
            except (QuotaExhausted, GeminiError) as e:
                log(f"注意 Gemini で作れませんでした: {e}")
                if a.strict:
                    log("NG   --strict なので止めます。時間をおいて同じコマンドを実行すると、続きから作ります")
                    return 1
                log("情報 声をそろえるため、全シーンを標準の内蔵の声で作り直します")

    if used is None:
        v = OSVoice(a.os_voice, a.rate)
        log(f"情報 内蔵の声: {v.name}")
        build(scenes, out, v, v.name)
        used = v.name

    paths = [os.path.join(out, f"{s['id']}.wav") for s in scenes]
    nar = os.path.join(out, "narration.wav")
    concat_wavs(paths, nar, gap=a.gap, tail=a.tail)

    t, timing = 0.0, []
    for i, (s, p) in enumerate(zip(scenes, paths)):
        sp = wav_sec(p)
        end = t + sp + (a.gap if i < len(scenes) - 1 else a.tail)
        timing.append({"id": s["id"], "start": round(t, 3), "speech_end": round(t + sp, 3),
                       "end": round(end, 3), "speech_sec": round(sp, 3)})
        t = end
    total = wav_sec(nar)
    timing[-1]["end"] = round(total, 3)
    with open(os.path.join(out, "timing.json"), "w", encoding="utf-8") as f:
        json.dump({"engine": used, "total_sec": round(total, 3), "gap": a.gap, "scenes": timing},
                  f, ensure_ascii=False, indent=2)

    if a.mp3:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", nar, "-c:a", "libmp3lame", "-b:a", "192k",
                        "-map_metadata", "-1", "-fflags", "+bitexact", os.path.join(out, "narration.mp3")], check=True)

    log(f"情報 声: {used}")
    for x in timing:
        log(f"     {x['id']}  {x['start']:7.2f}s → {x['end']:7.2f}s（声 {x['speech_sec']:.2f}s）")
    log(f"OK   narration.wav 合計 {total:.2f}秒: {nar}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
