# -*- coding: utf-8 -*-
"""SNS 投稿の下書き（X / Threads / Instagram）を点検する。投稿はしません。ネットにもつなぎません。

下書きファイルの形（sns-to-note の posts.md と同じ見出し。Instagram も書ける）:
    ## 投稿1｜X｜言い切り
    本文……

    ## 投稿2｜Threads｜手順
    本文……

    ## 投稿3｜Instagram｜保存用まとめ
    キャプション……

使い方:
    python3 check_drafts.py /絶対パス/sns/2026-11-10_元の題名.md
    python3 check_drafts.py <下書き> --past /絶対パス/sns       ← 過去の下書きと似すぎていないかも見る
    python3 check_drafts.py <下書き> --voice /絶対パス/voice_profile.md   ← 「使わない言葉」も見る

点検すること:
    長さ      X は重み付き 280 まで（日本語1字=2、URL=23 の概算）／Threads は 500 字まで／
              Instagram のキャプションは 2,200 字まで
    リンク    1投稿に1つまで。Instagram の本文の URL は押せないので注意
    ハッシュタグ  X・Threads は2個まで（注意）、Instagram は5個を超えたら注意・30個を超えたら NG
    重複      同じファイルの中で同じ本文／過去の下書きと 85% 以上同じ（--past）
    言葉      約束しすぎ（NG）・あおり（注意）・voice_profile.md の「使わない言葉」（NG）
    空欄      本文が空・「（ここに本文）」のまま（NG）。【】の残りは数えて知らせる
終了コード: 0 = NG なし / 1 = NG あり / 2 = 使い方の誤り
"""
import argparse
import difflib
import glob
import os
import re
import sys

URL = re.compile(r"https?://\S+")
HEAD = re.compile(r"^## 投稿(\d+)｜(X|Threads|Instagram)｜(.+)$")
LIMIT = {"X": 280, "Threads": 500, "Instagram": 2200}
NG_WORDS = ["誰でも稼", "必ず稼", "確実に稼", "稼げます", "収入保証", "絶対に儲", "元本保証", "今だけ無料で稼"]
CAUTION_WORDS = ["絶対", "必ず", "100%", "放置で", "不労所得", "限定", "残りわずか", "今すぐ"]


def x_weight(text):
    """X の文字数の数え方（概算）：URL=23、ラテン文字など=1、日本語など=2。"""
    w = 23 * len(URL.findall(text))
    for ch in URL.sub("", text):
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
            m = HEAD.match(line.strip())
            if m:
                cur = {"no": int(m.group(1)), "pf": m.group(2), "kind": m.group(3).strip(), "body": []}
                posts.append(cur)
                continue
            if line.startswith("## ") or line.startswith("# "):
                cur = None  # 投稿以外の見出し（メモ欄など）は本文に入れない
                continue
            if cur is None or line.strip().startswith("<!--"):
                continue
            cur["body"].append(line)
    for p in posts:
        p["text"] = "\n".join(p["body"]).strip()
    return posts


def norm(t):
    return re.sub(r"\s", "", URL.sub("", t))


def voice_ng_words(path):
    words = []
    if not path or not os.path.isfile(path):
        return words
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = re.match(r"^-?\s*使わない言葉[:：]\s*(.+)$", line.strip())
            if m:
                words += [w.strip() for w in re.split(r"[、,／/]", m.group(1)) if w.strip() and "【" not in w]
    return words


def main():
    ap = argparse.ArgumentParser(description="SNS 投稿の下書きを点検する（投稿はしない）")
    ap.add_argument("file")
    ap.add_argument("--past", default=None, help="過去の下書きフォルダ（似すぎチェック）")
    ap.add_argument("--voice", default=None, help="voice_profile.md（使わない言葉）")
    ap.add_argument("--similar", type=float, default=0.85, help="似すぎと判定する割合（初期値 0.85）")
    a = ap.parse_args()
    path = os.path.abspath(a.file)
    if not os.path.isfile(path):
        print("ファイルがありません: " + path)
        return 2
    posts = parse(path)
    ng, warn = [], []
    if not posts:
        ng.append("「## 投稿N｜X｜型」（X / Threads / Instagram）の見出しが1つもありません")

    past = []
    if a.past:
        for p in sorted(glob.glob(os.path.join(os.path.abspath(a.past), "**", "*.md"), recursive=True)):
            if os.path.abspath(p) == path:
                continue
            for q in parse(p):
                if q["text"]:
                    past.append((os.path.basename(p), q["no"], norm(q["text"])))
    vwords = voice_ng_words(a.voice)

    seen, holes = {}, 0
    for p in posts:
        tag = "投稿%d（%s／%s）" % (p["no"], p["pf"], p["kind"])
        t = p["text"]
        if not t or "（ここに本文）" in t:
            ng.append(tag + "：本文がまだありません")
            continue
        holes += len(re.findall(r"【[^】]*】", t))
        n = x_weight(t) if p["pf"] == "X" else len(t)
        lim = LIMIT[p["pf"]]
        if n > lim:
            ng.append("%s：長さ %d/%d。短くする（長い話は note や YouTube へ）" % (tag, n, lim))
        urls = URL.findall(t) + re.findall(r"【[^】]*URL[^】]*】", t)
        if len(urls) > 1:
            ng.append("%s：リンクが %d 個。1つにする" % (tag, len(urls)))
        if urls and p["pf"] == "Instagram":
            warn.append(tag + "：Instagram の本文の URL は押せません。「プロフィールのリンクから」に")
        if urls and not any(k in p["kind"] for k in ("告知", "LINE", "案内")):
            warn.append("%s：「%s」の型にリンクがあります。毎回リンクだと宣伝ばかりに見えます" % (tag, p["kind"]))
        tags = re.findall(r"[#＃][^\s#＃]+", t)
        if p["pf"] == "Instagram":
            if len(tags) > 30:
                ng.append("%s：ハッシュタグ %d 個（Instagram は30個まで）" % (tag, len(tags)))
            elif len(tags) > 5:
                warn.append("%s：ハッシュタグ %d 個。3〜5個に絞る（上限は変わることがあるので最新のルールを確認）" % (tag, len(tags)))
        elif len(tags) > 2:
            warn.append("%s：ハッシュタグ %d 個。2個までに" % (tag, len(tags)))
        for wd in NG_WORDS + vwords:
            if wd in t:
                ng.append("%s：「%s」は使わない言葉です。言い換える" % (tag, wd))
        for wd in CAUTION_WORDS:
            if wd in t and wd not in vwords:
                warn.append("%s：「%s」→ あおりすぎでないか確認" % (tag, wd))
        k = norm(t)
        if k in seen:
            ng.append("%s：投稿%d と同じ本文です（重複投稿は避ける）" % (tag, seen[k]))
        else:
            seen[k] = p["no"]
        for fname, no, pk in past:
            r = difflib.SequenceMatcher(None, k, pk).ratio()
            if r >= a.similar:
                ng.append("%s：過去の下書き %s の投稿%d と %d%% 同じです。切り口を変える" % (tag, fname, no, round(r * 100)))
                break
        print("情報 %s：長さ %d/%d" % (tag, n, lim))

    for x in ng:
        print("NG   " + x)
    for x in warn:
        print("注意 " + x)
    if holes:
        print("情報 【】の空欄が %d か所あります（ご本人が埋める所）" % holes)
    print("== 結果：投稿 %d 件／NG %d 件／注意 %d 件（過去の下書き %d 本と比べました）==" % (len(posts), len(ng), len(warn), len(past)))
    return 1 if ng else 0


if __name__ == "__main__":
    sys.exit(main())
