#!/usr/bin/env python3
"""YouTube台本（script.json）を機械で点検し、人が読む用の script.md を作る。

使い方:
    python3 check_script.py /絶対パス/script.json
    python3 check_script.py /絶対パス/script.json --target-sec 45   # 30〜60秒の試し動画

結果の見方:
    NG   … 直してから、もう一度実行する
    注意 … 目で見て、問題なければそのままでよい
    情報 … 数えた結果
終了コード: NG が1つでもあれば 1、無ければ 0

標準ライブラリだけで動く（追加のインストールは不要）。
"""
import argparse
import json
import os
import re
import sys

CHARS_PER_MIN = 330  # 日本語ナレーションの目安（1分あたりの文字数）

BANNED = ["必ず稼", "確実に稼", "誰でも稼", "稼げます", "収入保証", "保証します",
          "絶対に儲", "100%", "１００％", "TODO", "いかがでしたか"]
CAUTION = ["必ず", "確実に", "誰でも", "絶対", "簡単に", "放置で", "不労所得",
           "と言われています", "でしょう", "最強", "神"]
NUM = re.compile(r"[0-9０-９]+(\.[0-9]+)?\s*(円|万|千|億|%|％|年|か月|ヶ月|日|件|人|倍|GB|分)")
PLACEHOLDER = re.compile(r"【ここにご自身の体験[^】]*】")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("script")
    ap.add_argument("--target-sec", type=float, default=None,
                    help="目標の長さ（秒）。省略時は script.json の target_minutes（無ければ9分）")
    a = ap.parse_args()

    path = os.path.abspath(a.script)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:  # noqa: BLE001
        print(f"NG   script.json が読めません: {e}")
        return 1

    ng, warn, info = [], [], []
    scenes = data.get("scenes") or []
    if not data.get("title"):
        ng.append("title（タイトル）が空です")
    if not scenes:
        ng.append("scenes（シーン）が1つもありません")

    target = a.target_sec if a.target_sec else float(data.get("target_minutes", 9)) * 60
    ids = set()
    total_chars = 0
    numbers = []
    placeholders = 0
    for i, s in enumerate(scenes, 1):
        sid = s.get("id") or f"(番号{i})"
        if not s.get("id"):
            ng.append(f"{sid}: id がありません（s01, s02…）")
        elif sid in ids:
            ng.append(f"{sid}: id が重複しています")
        ids.add(sid)
        nar = (s.get("narration") or "").strip()
        if not nar:
            ng.append(f"{sid}: narration（ナレーション）が空です")
            continue
        total_chars += len(nar)
        sec = len(nar) / CHARS_PER_MIN * 60
        if a.target_sec is None and not (8 <= sec <= 50):
            warn.append(f"{sid}: 約{sec:.0f}秒（1シーン15〜40秒が目安）")
        for sent in re.split(r"[。！？!?]", nar):
            if len(sent) > 40:
                warn.append(f"{sid}: 40文字を超える文があります「{sent[:20]}…」")
        text = nar + (s.get("yomi") or "")
        for w in BANNED:
            if w in text:
                ng.append(f"{sid}: 言ってはいけない言い方「{w}」")
        for w in CAUTION:
            if w in text:
                warn.append(f"{sid}: 言い方を目で確認「{w}」")
        for m in NUM.finditer(nar):
            numbers.append((sid, m.group(0)))
        placeholders += len(PLACEHOLDER.findall(nar))
        v = s.get("visual") or {}
        if v.get("type") not in ("text", "image"):
            ng.append(f"{sid}: visual.type は text か image にしてください")
        if not v.get("heading"):
            ng.append(f"{sid}: visual.heading（画面の大きな文字）が空です")
        elif len(v["heading"]) > 15:
            warn.append(f"{sid}: heading が15文字を超えています（画面で小さくなります）")
        if v.get("body") and len(v["body"]) > 30:
            warn.append(f"{sid}: body が30文字を超えています")
        if v.get("type") == "image":
            img = v.get("image", "")
            if not os.path.isabs(img):
                ng.append(f"{sid}: image は絶対パスで書いてください")
            elif not os.path.exists(img):
                warn.append(f"{sid}: 画像が見つかりません（文字スライドで代用されます）: {img}")

    est = total_chars / CHARS_PER_MIN * 60
    info.append(f"シーン数 {len(scenes)} / ナレーション合計 {total_chars}文字 / 推定 約{est:.0f}秒（目標 {target:.0f}秒）")
    if scenes and not (target * 0.8 <= est <= target * 1.2):
        warn.append(f"長さが目標から20%以上ずれています（推定{est:.0f}秒 / 目標{target:.0f}秒）")
    if numbers:
        info.append(f"数字の言い方 {len(numbers)}か所 → factcheck.md に全部載せてください: "
                    + "、".join(f"{sid}「{n}」" for sid, n in numbers))
    if placeholders:
        warn.append(f"【ここにご自身の体験】の穴埋めが {placeholders}か所 残っています（公開前にご本人が埋める）")

    # 人が読む用の script.md
    md = [f"# {data.get('title', '')}", "", f"チャンネル: {data.get('channel', '')}", ""]
    for s in scenes:
        v = s.get("visual") or {}
        md += [f"## {s.get('id', '')}", "",
               f"- ナレーション: {s.get('narration', '')}"]
        if s.get("yomi"):
            md.append(f"- 読み: {s['yomi']}")
        vis = v.get("heading", "") + (f" / {v['body']}" if v.get("body") else "")
        if v.get("type") == "image":
            vis = f"画像 {v.get('image', '')}（予備の文字: {vis}）"
        md += [f"- 画面: {vis}", ""]
    out_md = os.path.join(os.path.dirname(path), "script.md")
    with open(out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    info.append(f"人が読む用の台本を書きました: {out_md}")

    for x in ng:
        print("NG  ", x)
    for x in warn:
        print("注意", x)
    for x in info:
        print("情報", x)
    print("結果:", "NG あり（直してから再実行）" if ng else "OK")
    return 1 if ng else 0


if __name__ == "__main__":
    sys.exit(main())
