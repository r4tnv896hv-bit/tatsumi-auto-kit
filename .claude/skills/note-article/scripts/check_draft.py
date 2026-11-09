#!/usr/bin/env python3
"""note記事の下書き（article.md）を機械で点検する。

使い方:
    python3 check_draft.py note_drafts/20261102_sample/article.md

結果の見方:
    NG   … 直してから、もう一度実行する
    注意 … 目で見て、問題なければそのままでよい
    情報 … 数えた結果
終了コード: NG が1つでもあれば 1、無ければ 0

標準ライブラリだけで動く（追加のインストールは不要）。
"""
import re
import sys

# 本文に出てきたら止める言い方（NG）
BANNED = [
    "出典", "参考：", "参考:", "によると", "いかがでしたか", "でしょう",
    "と言えます", "と考えられます", "必ず稼", "確実に稼", "誰でも稼",
    "稼げます", "稼げる方法", "保証します", "収入保証", "最短", "必見", "今すぐ",
    "衝撃", "完全保存版", "TODO", ".png", ".jpg",
]
# 見かけたら目で確かめる言い方（注意）
CAUTION = ["必ず", "確実に", "誰でも", "絶対", "簡単に", "放置で", "不労所得"]

FIG_LINE = re.compile(r"^\s*(［図\d+］|\[図\d+\]|図の題[：:]|図の説明[：:])")
URL = re.compile(r"https?://\S+")
MONEY = re.compile(r"[0-9０-９][0-9０-９,，.]*\s*(万|千|億)?\s*円")
PERCENT = re.compile(r"[0-9０-９]+(\.[0-9]+)?\s*(%|％|割)")
NUM_IN_TITLE = re.compile(r"[0-9０-９一二三四五六七八九十百]")
NON_COUNTED_H2 = ("はじめに", "まとめ", "おわりに", "さいごに", "最後に")


def main(path):
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()

    ng, warn, info = [], [], []

    # 題名
    title = next((l[2:].strip() for l in lines if l.startswith("# ")), "")
    if not title:
        ng.append("題名（# で始まる行）が見つかりません")
    elif not NUM_IN_TITLE.search(title):
        warn.append("題名に数字がありません：" + title)

    # 本文（図の指示・見出し・区切り線を除く）
    body_lines = []
    for i, l in enumerate(lines, 1):
        if FIG_LINE.match(l) or l.startswith("#") or l.strip() in ("---", "***"):
            continue
        if l.strip().startswith(("<!--", "【要確認")):
            continue
        body_lines.append((i, l))

    body_text = "".join(l for _, l in body_lines)
    chars = len(re.sub(r"\s", "", body_text))
    info.append("字数（空白・見出し・図の指示・要確認の印を除く）：{:,}字".format(chars))
    if chars < 7000 or chars > 9000:
        ng.append("字数が 7,000〜9,000字 の外です（{:,}字）".format(chars))

    # 禁止の言い方（図の説明も含めて全行を見る）
    for i, l in enumerate(lines, 1):
        for w in BANNED:
            if w in l:
                ng.append("{}行目：使わない言い方「{}」→ {}".format(i, w, l.strip()[:40]))
        for w in CAUTION:
            if w in l:
                warn.append("{}行目：「{}」約束やあおりになっていないか → {}".format(i, w, l.strip()[:40]))

    # URL
    for i, l in enumerate(lines, 1):
        for u in URL.findall(l):
            warn.append("{}行目：URLがあります（使う人が指定したもの以外は消す）→ {}".format(i, u))

    # 表
    for i, l in enumerate(lines, 1):
        if l.count("|") >= 2:
            ng.append("{}行目：表の記号「|」があります。表は使わず箇条書きに".format(i))

    # お金・割合の数字
    for i, l in body_lines:
        if MONEY.search(l):
            warn.append("{}行目：お金の数字。本人の実績か・約束になっていないか → {}".format(i, l.strip()[:40]))
        if PERCENT.search(l):
            warn.append("{}行目：割合の数字。出どころが作業メモにあるか → {}".format(i, l.strip()[:40]))

    # 長い行（箇条書き・引用もふくむ。30字を超えたら注意）
    long_lines = [(i, l) for i, l in body_lines if len(l.strip()) > 30]
    if long_lines:
        warn.append("30字を超える行：{}行（例：{}行目）".format(len(long_lines), long_lines[0][0]))

    # 長い段落（空行で区切って4行以上）
    para, start, long_paras = [], None, []
    for i, l in enumerate(lines + [""], 1):
        is_text = l.strip() and not l.startswith("#") and not FIG_LINE.match(l) \
            and not l.strip().startswith(("【要確認", "<!--")) \
            and not l.lstrip().startswith(("・", "-", "*", ">", "　"))
        if is_text:
            if not para:
                start = i
            para.append(l)
        else:
            if len(para) > 3:
                long_paras.append(start)
            para = []
    if long_paras:
        warn.append("4行以上の段落：{}か所（{}行目 ほか）".format(len(long_paras), long_paras[0]))

    # 見出し
    h2 = [l[3:].strip() for l in lines if l.startswith("## ")]
    h2_counted = [h for h in h2 if not h.startswith(NON_COUNTED_H2)]
    info.append("大見出し（はじめに・まとめを除く）：{}個".format(len(h2_counted)))
    if not 5 <= len(h2_counted) <= 7:
        ng.append("大見出しは5〜7個にします（いま{}個）".format(len(h2_counted)))

    # 太字（大見出しごと）
    section, bold = "（冒頭）", {}
    for l in lines:
        if l.startswith("## "):
            section = l[3:].strip()
        bold[section] = bold.get(section, 0) + len(re.findall(r"\*\*[^*]+\*\*", l))
    for s, n in bold.items():
        if n > 2:
            warn.append("太字が多い（{}か所）：{}".format(n, s))

    # 図
    figs = [l for l in lines if re.match(r"^\s*(［図\d+］|\[図\d+\])", l)]
    fig_titles = [l for l in lines if re.match(r"^\s*図の題[：:]", l)]
    fig_descs = [l for l in lines if re.match(r"^\s*図の説明[：:]", l)]
    info.append("図の指示：{}枚".format(len(figs)))
    if not 4 <= len(figs) <= 7:
        ng.append("図は4〜7枚にします（いま{}枚）".format(len(figs)))
    if not (len(figs) == len(fig_titles) == len(fig_descs)):
        ng.append("図の番号・図の題・図の説明の数がそろっていません（{}/{}/{}）".format(
            len(figs), len(fig_titles), len(fig_descs)))

    # 要確認
    kakunin = sum(l.count("【要確認") for l in lines)
    info.append("【要確認】の数：{}（公開前にご自身で確かめて消す）".format(kakunin))

    # 有料ライン（目印は「=== ここから有料 ===」の1行。sns-to-note / sns-post と共通）
    paid = [i + 1 for i, l in enumerate(lines) if l.strip() == "=== ここから有料 ==="]
    old_mark = [i + 1 for i, l in enumerate(lines) if "ここから有料（有料ライン）" in l]
    if paid:
        info.append("有料ラインの印：あり（{}行目）".format(", ".join(map(str, paid))))
    if len(paid) > 1:
        warn.append("有料ラインの印が {} か所あります。1か所にする".format(len(paid)))
    if old_mark:
        warn.append("古い形の有料ラインの印（{}行目）→「=== ここから有料 ===」の1行に置きかえる".format(", ".join(map(str, old_mark))))

    print("== note記事 点検結果：{} ==".format(path))
    for x in info:
        print("情報  " + x)
    for x in warn:
        print("注意  " + x)
    for x in ng:
        print("NG    " + x)
    print("== NG {}件 / 注意 {}件 ==".format(len(ng), len(warn)))
    return 1 if ng else 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("使い方: python3 check_draft.py article.md")
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
