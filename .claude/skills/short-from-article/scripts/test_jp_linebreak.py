#!/usr/bin/env python3
"""字幕の折り返しが「言葉の途中で切らない」ことの確認。

実行: python3 test_jp_linebreak.py   （Windows は python）
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jp_linebreak import INF, bad_breaks, break_cost, wrap  # noqa: E402

CASES = [
    "固定費を見直す3つの順番",
    "お金の話は、専門家や公式の情報で確かめてください。",
    "Claude Codeで台本を作る",
    "スマホ代・保険・サブスクの順番",
    "2026年の5,000円と1.5倍の違い",
    "この1か月で使っていないものから、解約を考えます。",
    "食費を削るのがつらい人ほど、先に固定費を見直してください。",
]


class TestNoBreakInsideWord(unittest.TestCase):
    def test_cases_all_widths(self):
        for text in CASES:
            for limit in range(4, len(text) + 1):
                for max_lines in (None, 2):
                    lines, _ = wrap(text, limit, max_lines=max_lines)
                    with self.subTest(text=text, limit=limit, max_lines=max_lines, lines=lines):
                        self.assertEqual("".join(lines).replace(" ", ""), text.replace(" ", ""))
                        self.assertEqual(bad_breaks(lines), [])
                        if max_lines:
                            self.assertLessEqual(len(lines), max_lines)

    def test_reported_lines(self):
        # Rin の指摘: 「3／つ」「公／式」で切れていた
        for limit in range(4, 13):
            lines, _ = wrap("固定費を見直す3つの順番", limit, max_lines=2)
            self.assertNotIn("3", [l[-1] for l in lines[:-1]], lines)
            lines, _ = wrap("専門家や公式の情報", limit, max_lines=2)
            self.assertFalse(any(l.endswith("公") for l in lines), lines)

    def test_forbidden_points(self):
        must_not = [("固定費", 2), ("3つ", 1), ("2026年", 4), ("2026年", 2), ("公式", 1),
                    ("スマホ代", 3), ("サブスク", 2), ("Claude Code", 6), ("Claude Code", 7),
                    ("ください", 2), ("お金", 1), ("5,000円", 2), ("見直す", 1)]
        for word, i in must_not:
            with self.subTest(word=word, i=i):
                self.assertEqual(break_cost(word, i), INF)

    def test_natural_points(self):
        ok = [("固定費を見直す", 4), ("専門家や公式", 4), ("スマホ代・保険", 5), ("台本を作る", 3),
              ("確かめ、次へ", 4), ("Codeで台本", 5)]
        for text, i in ok:
            with self.subTest(text=text, i=i):
                self.assertLess(break_cost(text, i), INF)

    def test_overflow_flag(self):
        lines, over = wrap("サブスクリプションサービス", 6)
        self.assertEqual(lines, ["サブスクリプションサービス"])  # 切れないので1行のまま
        self.assertTrue(over)


if __name__ == "__main__":
    unittest.main(verbosity=1)
