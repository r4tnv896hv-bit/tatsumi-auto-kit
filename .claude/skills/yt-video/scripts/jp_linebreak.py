#!/usr/bin/env python3
"""日本語の字幕を「言葉の途中で切らずに」折り返す（標準ライブラリだけ）。

折ってよい場所（小さい数ほど自然）:
    0  句読点・閉じかっこの後（、。！？」』）… など）
    1  助詞の後（は が を に で と も の へ や から まで より）
    1  「・」の後、開きかっこ（「『（）の前
    3  ひらがな → 漢字・カタカナ・英字・数字 に変わる所（「見直す|固定費」）
折らない場所:
    漢字どうし（「固定|費」）、カタカナどうし（「サブ|スク」）、英字どうし（「Claude Code」の空白も）、
    漢字とカタカナの境目（「スマホ|代」）、ひらがなどうし（「くだ|さい」）、漢字→ひらがな（「見|直す」）、
    数字の途中と、数字と単位の間（「3|つ」「2026|年」「5,000|円」）、
    行頭に来てはいけない文字の前（、。ー っ ゃ など）、開きかっこの後、お/ご の後（「お|金」）

使い方:
    lines, over = wrap("固定費を見直す3つの順番", 8)
    # over が True なら、どうしても limit に収まらず少し長い行（最大 +slack）か、それ以上になった
    # → 呼び出す側で文字を小さくする
"""

BREAK_AFTER = set("、。，．！？!?」』）)】〉》…‥")
OPEN = set("「『（(【〈《")
NO_LINE_START = set("、。，．・：；！？!?」』）)】〉》…‥ーっゃゅょゎぁぃぅぇぉッャュョヮァィゥェォヵヶ々ゝゞヽヾ")
PARTICLES_1 = set("はがをにでともへやの")
PARTICLES_2 = ("から", "まで", "より")
PREFIX = set("おご")
INF = float("inf")


def _hira(c):
    return "ぁ" <= c <= "ゟ"


def _kata(c):
    return ("ァ" <= c <= "ヿ") or c == "ー"


def _kanji(c):
    return ("一" <= c <= "鿿") or ("㐀" <= c <= "䶿") or c in "々〆ヶ"


def _digit(c):
    return c.isdigit() or c in "０１２３４５６７８９"


def _latin(c):
    return ("a" <= c.lower() <= "z") or ("ａ" <= c <= "ｚ") or ("Ａ" <= c <= "Ｚ")


def _word_start(c):
    return _kanji(c) or _kata(c) or _latin(c) or _digit(c) or c in OPEN


def break_cost(text, i):
    """text[i-1] と text[i] の間で折るときのコスト。INF は「折ってはいけない」。"""
    if i <= 0 or i >= len(text):
        return INF
    a, b = text[i - 1], text[i]
    if b in NO_LINE_START or a in OPEN:
        return INF
    # 数字の途中・数字と単位（「3つ」「2026年」「5,000円」「1.5倍」）
    if _digit(a) or (a in ",.，．" and i >= 2 and _digit(text[i - 2]) and _digit(b)):
        return INF
    if a in BREAK_AFTER:
        return 0.0
    if b in OPEN:
        return 1.0
    if a == "・":
        return 1.0
    if a == " " or b == " ":
        x = text[i - 2] if a == " " and i >= 2 else a
        y = text[i + 1] if b == " " and i + 1 < len(text) else b
        if _latin(x) and _latin(y):
            return INF  # 「Claude Code」のような英語の名前は1つのかたまり
        return 1.0
    # 助詞の後
    before = text[i - 2] if i >= 2 else ""
    if a in PARTICLES_1 and b not in PARTICLES_1:
        if (before and not _hira(before)) or _word_start(b):
            return 1.0
    for p in PARTICLES_2:
        if text[max(0, i - 2):i] == p and b not in PARTICLES_1:
            pre = text[i - 3] if i >= 3 else ""
            if (pre and not _hira(pre)) or _word_start(b):
                return 1.0
    # ひらがな → 次の言葉の頭（漢字・カタカナ・英字・数字）
    if _hira(a) and _word_start(b):
        if a in PREFIX and (i < 2 or not _hira(text[i - 2]) or text[i - 2] in PARTICLES_1):
            return INF  # 「お金」「ご確認」
        return 3.0
    return INF


def _dp(text, limit, measure, unit, max_lines):
    """折ってよい場所だけを使い、どの行も limit 以内・行数が最少・コストが最小の分け方。無ければ None。"""
    L = len(text)
    pos = [0] + [i for i in range(1, L) if break_cost(text, i) < INF] + [L]
    cost_at = {i: break_cost(text, i) for i in pos[1:-1]}
    width = {}

    def w(j, i):
        if (j, i) not in width:
            width[(j, i)] = measure(text[j:i].strip())
        return width[(j, i)]

    total = measure(text)
    for n in range(1, (max_lines or len(pos)) + 1):
        avg = total / n
        best = {(0, 0): (0.0, None)}
        for k in range(1, n + 1):
            for i in pos[1:]:
                if (k < n and i == L) or (k == n and i != L):
                    continue
                cand = None
                for j in pos:
                    if j >= i:
                        break
                    prev = best.get((k - 1, j))
                    if prev is None or w(j, i) > limit:
                        continue
                    c = prev[0] + 0.08 * ((w(j, i) - avg) / unit) ** 2 + (cost_at.get(i, 0.0) if i < L else 0.0)
                    if cand is None or c < cand[0]:
                        cand = (c, j)
                if cand:
                    best[(k, i)] = cand
        if (n, L) in best:
            cuts, i, k = [L], L, n
            while k > 0:
                i = best[(k, i)][1]
                cuts.append(i)
                k -= 1
            cuts = cuts[::-1]
            return [text[x:y].strip() for x, y in zip(cuts, cuts[1:])]
    return None


def wrap(text, limit, measure=len, slack=None, max_lines=None):
    """text を、言葉の途中で切らずに limit 以内の行に分ける。

    measure: 長さの測り方（初期値は文字数。ピクセルで測るなら draw.textlength を包んだ関数）
    slack:   ぴったり収まらないとき、許す はみ出し（初期値は「4文字分」）
    max_lines: 行数の上限（例: 字幕は 2）
    戻り値: (lines, over)  over=True は limit を超えた行がある（呼び出し側で文字を小さくする合図）
    """
    text = (text or "").strip()
    if not text:
        return [], False
    unit = measure("あ") or 1
    if slack is None:
        slack = 4 * unit
    for lim, over in ((limit, False), (limit + slack, True)):
        lines = _dp(text, lim, measure, unit, max_lines)
        if lines:
            return lines, over
    # どうしても収まらない: 行数の上限の中で、いちばん長い行が短くなる分け方（言葉の途中では切らない）
    lo, hi = limit + slack, measure(text)
    best = [text]
    while hi - lo > unit / 4:
        mid = (lo + hi) / 2
        lines = _dp(text, mid, measure, unit, max_lines)
        if lines:
            best, hi = lines, mid
        else:
            lo = mid
    return best, True


def bad_breaks(lines):
    """テスト用: 行の境目のうち、折ってはいけない場所で折っているものを返す。"""
    joined, out, pos = "", [], []
    for ln in lines:
        if joined:
            pos.append(len(joined))
        joined += ln
    for p in pos:
        if break_cost(joined, p) == INF:
            out.append(joined[max(0, p - 3):p] + "／" + joined[p:p + 3])
    return out
