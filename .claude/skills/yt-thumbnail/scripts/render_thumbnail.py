#!/usr/bin/env python3
"""サムネイル案（concepts.json）を、HTML → PNG（1280x720）にする。

使い方:
    python3 render_thumbnail.py /絶対パス/concepts.json --out /絶対パス/thumbnail

concepts.json の形（templates/concepts_example.json を参照）:
    {"concepts": [
      {"id": "A", "layout": "center", "lines": ["[[固定費]]は", "この順で見直す"],
       "badge": "3ステップ", "small": "通信費→保険→サブスク",
       "bg": "#ffffff", "fg": "#222222", "accent": "#e8772e"}
    ]}
    layout: center（中央に大きな文字）/ split（左に数字のブロック。"number" と "unit" を使う）/ band（上下の帯。"top" と "bottom" を使う）
    [[ ]] で囲んだ文字は accent の色になる。

PNG にする方法（上から順に、使えるものを使う）:
    1. Google Chrome / Microsoft Edge / Chromium をヘッドレスで動かす（追加インストール不要）
    2. Python の playwright（pip install playwright && python -m playwright install chromium）

できるもの: thumb_A.html / thumb_A.png …（PNG は 1280x720 か確かめる。メタデータなし）
顔の画像や AI で作った人物は使わない（文字だけで作る）。
"""
import argparse
import html
import json
import os
import platform
import re
import shutil
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "..", "templates", "thumbnail.html")
W, H = 1280, 720


def esc(s):
    """[[ ]] を強調に変え、それ以外は HTML として安全にする。"""
    out, pos = [], 0
    for m in re.finditer(r"\[\[(.+?)\]\]", s or ""):
        out.append(html.escape(s[pos:m.start()]))
        out.append(f'<span class="hl">{html.escape(m.group(1))}</span>')
        pos = m.end()
    out.append(html.escape((s or "")[pos:]))
    return "".join(out)


def plain_len(s):
    return len(re.sub(r"\[\[|\]\]", "", s or ""))


def auto_size(lines, width):
    longest = max([plain_len(l) for l in lines] or [1])
    size = int(width / max(longest, 1) * 0.95)
    cap = 170 if len(lines) <= 2 else 130
    return max(60, min(cap, size))


def body_html(c):
    lines = c.get("lines") or []
    lay = c.get("layout", "center")
    small = f'<div class="small">{esc(c["small"])}</div>' if c.get("small") else ""
    if lay == "split":
        size = auto_size(lines, 1280 - 430 - 112)
        ls = "".join(f'<div class="line">{esc(l)}</div>' for l in lines)
        return size, (f'<div class="split"><div class="left"><div class="big">{esc(c.get("number", ""))}</div>'
                      f'<div class="unit">{esc(c.get("unit", ""))}</div></div>'
                      f'<div class="right">{ls}{small}</div></div>')
    if lay == "band":
        size = auto_size(lines, 1280 - 120)
        ls = "".join(f'<div class="line">{esc(l)}</div>' for l in lines)
        top = f'<div class="top">{esc(c["top"])}</div>' if c.get("top") else ""
        bottom = f'<div class="bottom">{esc(c["bottom"])}</div>' if c.get("bottom") else ""
        return size, f'<div class="band">{top}{ls}{small}{bottom}</div>'
    size = auto_size(lines, 1280 - 120)
    ls = "".join(f'<div class="line">{esc(l)}</div>' for l in lines)
    badge = f'<div class="badge">{esc(c["badge"])}</div>' if c.get("badge") else ""
    return size, f'<div class="center">{badge}{ls}<div class="bar"></div>{small}</div>'


def find_browser():
    sysname = platform.system()
    cands = []
    if sysname == "Darwin":
        cands = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                 "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                 "/Applications/Chromium.app/Contents/MacOS/Chromium",
                 "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"]
    elif sysname == "Windows":
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


def png_size(path):
    with open(path, "rb") as f:
        head = f.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", head[16:24])


def shot_browser(browser, html_path, png_path):
    url = "file:///" + os.path.abspath(html_path).replace(os.sep, "/").lstrip("/")
    with tempfile.TemporaryDirectory() as prof:
        cmd = [browser, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
               "--no-default-browser-check", f"--user-data-dir={prof}", "--force-device-scale-factor=1",
               f"--window-size={W},{H}", f"--screenshot={png_path}", "--virtual-time-budget=1500", url]
        try:
            subprocess.run(cmd, capture_output=True, timeout=90)
        except (subprocess.TimeoutExpired, OSError):
            # ブラウザが固まった・起動できなかったときは、次の方法（playwright）に任せる
            return False
    return os.path.exists(png_path)


def shot_playwright(html_path, png_path):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
        pg.goto("file:///" + os.path.abspath(html_path).replace(os.sep, "/").lstrip("/"))
        pg.wait_for_timeout(500)
        pg.screenshot(path=png_path)
        b.close()
    return os.path.exists(png_path)
    return os.path.exists(png_path)


def fix_size(png_path):
    """ブラウザによって数ピクセルずれることがあるので、1280x720 にそろえる（Pillow があれば）。"""
    sz = png_size(png_path)
    if sz == (W, H):
        return True
    try:
        from PIL import Image
    except ImportError:
        return False
    im = Image.open(png_path).convert("RGB")
    if im.width >= W and im.height >= H:
        im = im.crop((0, 0, W, H))
    else:
        im = im.resize((W, H))
    im.save(png_path)
    return png_size(png_path) == (W, H)


def strip_png_meta(png_path):
    """PNG から文字情報（tEXt/iTXt/zTXt/eXIf/caBX など）を取り除く。画素はそのまま。"""
    keep = {b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tRNS", b"gAMA", b"sRGB", b"cHRM", b"pHYs"}
    with open(png_path, "rb") as f:
        data = f.read()
    out, pos = [data[:8]], 8
    while pos < len(data):
        ln = struct.unpack(">I", data[pos:pos + 4])[0]
        typ = data[pos + 4:pos + 8]
        chunk = data[pos:pos + 12 + ln]
        if typ in keep:
            out.append(chunk)
        pos += 12 + ln
    with open(png_path, "wb") as f:
        f.write(b"".join(out))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("concepts")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    with open(a.concepts, encoding="utf-8") as f:
        concepts = json.load(f)["concepts"]
    with open(TEMPLATE, encoding="utf-8") as f:
        tpl = f.read()
    out = os.path.abspath(a.out)
    os.makedirs(out, exist_ok=True)
    browser = find_browser()
    ok_all = True
    for c in concepts:
        cid = c.get("id", "X")
        size, body = body_html(c)
        page = (tpl.replace("{{BG}}", c.get("bg", "#ffffff")).replace("{{FG}}", c.get("fg", "#222222"))
                .replace("{{ACCENT}}", c.get("accent", "#e8772e")).replace("{{SUB}}", c.get("sub", "#555555"))
                .replace("{{SIZE}}", str(c.get("size", size))).replace("{{BODY}}", body))
        hp = os.path.join(out, f"thumb_{cid}.html")
        pp = os.path.join(out, f"thumb_{cid}.png")
        with open(hp, "w", encoding="utf-8") as f:
            f.write(page)
        if os.path.exists(pp):
            os.remove(pp)
        done = bool(browser) and shot_browser(browser, hp, pp)
        if not done:
            browser = None  # 写せなかったブラウザは、次の案でもう待たない
            done = shot_playwright(hp, pp)
        if not done:
            print("NG   PNG にできませんでした。Google Chrome か Microsoft Edge を入れるか、")
            print("     pip install playwright && python -m playwright install chromium を実行してください")
            print(f"     （HTML はできています。ブラウザで開いてスクリーンショットでも代用できます: {hp}）")
            return 1
        fixed = fix_size(pp)
        strip_png_meta(pp)
        sz = png_size(pp)
        if not fixed or sz != (W, H):
            ok_all = False
            print(f"NG   {pp} の大きさが {sz}（1280x720 ではありません）")
        else:
            print(f"OK   {pp}（{sz[0]}x{sz[1]}）")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
