#!/usr/bin/env python3
"""SNS 投稿の下書き（posts.md）を点検する。投稿はしない。

posts.md の形:
    ## 投稿1｜X｜学び抜粋
    本文……

    ## 投稿2｜Threads｜告知
    本文……

使い方:
    python3 check_posts.py sns_week/posts.md

点検すること:
    - 長さ：X は重み付き 280 まで（日本語1字=2、URL=23）、Threads は 500 字まで
    - リンク：1投稿にURLは1つまで。告知・LINE案内以外の型にURLがあれば注意
    - 同じ本文の投稿が2つ以上ないか（重複投稿）
    - ハッシュタグは2個まで
    - 約束しすぎ・あおりの言葉
    - 本文が空（「（ここに本文）」のまま）
終了コード：NG があれば 1、無ければ 0。
"""
import re
import sys

URL = re.compile(r"https?://\S+")
HEAD = re.compile(r"^## 投稿(\d+)｜(X|Threads)｜(.+)$")
NG_WORDS = ["誰でも稼", "必ず稼", "確実に稼", "稼げます", "収入保証", "今だけ無料で稼"]
CAUTION_WORDS = ["絶対", "必ず", "100%", "放置で", "不労所得", "限定", "残りわずか"]
LINK_OK = ("告知", "LINE")


def x_weight(text):
    """X の文字数の数え方（概算）：URL=23、ラテン文字など=1、日本語など=2。"""
    w = 0
    for u in URL.findall(text):
        w += 23
    text = URL.sub("", text)
    for ch in text:
        c = ord(ch)
        if c <= 0x10FF or 0x2000 <= c <= 0x200D or 0x2010 <= c <= 0x201F or 0x2032 <= c <= 0x2037:
            w += 1
        else:
            w += 2
    return w


def parse(path):
    posts, cur = [], None
    with open(path, encoding="utf-8") as f:
        for line in f.read().splitlines():
            m = HEAD.match(line)
            if m:
                cur = {"no": int(m.group(1)), "pf": m.group(2), "kind": m.group(3).strip(), "body": []}
                posts.append(cur)
                continue
            if cur is None:
                continue
            if line.strip().startswith("<!--"):
                continue
            cur["body"].append(line)
    for p in posts:
        p["text"] = "\n".join(p["body"]).strip()
    return posts


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    posts = parse(sys.argv[1])
    ng, warn = [], []
    if not posts:
        ng.append("「## 投稿N｜X｜型」の見出しが1つもありません")

    seen = {}
    for p in posts:
        tag = f"投稿{p['no']}（{p['pf']}／{p['kind']}）"
        t = p["text"]
        if not t or "（ここに本文）" in t:
            ng.append(f"{tag}：本文がまだありません")
            continue
        if p["pf"] == "X":
            w = x_weight(t)
            if w > 280:
                ng.append(f"{tag}：X の長さ {w}/280。短くする（長文はスレッドにせず note へ誘導）")
            info = f"長さ {w}/280"
        else:
            n = len(t)
            if n > 500:
                ng.append(f"{tag}：Threads の長さ {n}/500")
            info = f"長さ {n}/500"
        urls = URL.findall(t) + re.findall(r"【[^】]*URL[^】]*】", t)
        if len(urls) > 1:
            ng.append(f"{tag}：リンクが {len(urls)} 個。1つにする")
        if urls and not any(k in p["kind"] for k in LINK_OK):
            warn.append(f"{tag}：「{p['kind']}」の型にリンクがあります。毎回リンクを貼ると宣伝ばかりに見えます")
        tags = re.findall(r"[#＃]\S+", t)
        if len(tags) > 2:
            warn.append(f"{tag}：ハッシュタグが {len(tags)} 個。2個までに")
        for wd in NG_WORDS:
            if wd in t:
                ng.append(f"{tag}：「{wd}」は約束しすぎ。言い換える")
        for wd in CAUTION_WORDS:
            if wd in t:
                warn.append(f"{tag}：「{wd}」→ あおりすぎでないか確認")
        key = re.sub(r"\s", "", URL.sub("", t))
        if key in seen:
            ng.append(f"{tag}：投稿{seen[key]} と同じ本文です（重複投稿は避ける）")
        else:
            seen[key] = p["no"]
        print(f"情報 {tag}：{info}")

    for x in ng:
        print("NG  ", x)
    for x in warn:
        print("注意", x)
    print(f"--- 結果：投稿 {len(posts)}件／NG {len(ng)}件／注意 {len(warn)}件")
    sys.exit(1 if ng else 0)


if __name__ == "__main__":
    main()
