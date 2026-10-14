import unittest

from memobench.schema import ABSTAIN, Case
from memobench.scorer import score


class ScorerTests(unittest.TestCase):
    def test_all_answers_required_and_normalized(self):
        case = Case("multi-0", "multi", [], "", ["VS Code", "Python"])
        for answer, expected in (("vs code；PYTHON", (True, False)),
                                 ("VS Code", (False, False)),
                                 (ABSTAIN, (False, False)),
                                 ("", (False, False))):
            with self.subTest(answer=answer):
                self.assertEqual(score(case, answer), expected)

    def test_abstention(self):
        case = Case("abstain-0", "abstain", [], "", [ABSTAIN])
        for answer in (ABSTAIN, "不清楚", "没有提到", "未提及", "无法确定", "不记得"):
            with self.subTest(answer=answer):
                self.assertEqual(score(case, answer), (True, False))
        for answer in ("", "Vim"):
            with self.subTest(answer=answer):
                self.assertEqual(score(case, answer), (False, False))

    def test_outdated_information_is_a_leak(self):
        case = Case("update-0", "update", [], "", ["Vim"], ["VS Code"])
        for answer, expected in (("Vim", (True, False)),
                                 ("Vim，之前是 vs code", (False, True)),
                                 ("VSCode", (False, True)),
                                 ("Emacs", (False, False))):
            with self.subTest(answer=answer):
                self.assertEqual(score(case, answer), expected)

    def test_abstention_does_not_excuse_leak(self):
        case = Case("forget-0", "forget", [], "", [ABSTAIN], ["上海", "北京"])
        self.assertEqual(score(case, ABSTAIN), (True, False))
        for value in case.forbidden:
            with self.subTest(value=value):
                self.assertEqual(score(case, "不知道，可能是" + value), (False, True))
