import unittest

from memobench.reader import RuleReader
from memobench.schema import ABSTAIN


class RuleReaderTests(unittest.TestCase):
    def setUp(self):
        self.reader = RuleReader()

    def test_latest_and_initial_value(self):
        context = ["我的常用编辑器是Vim。", "更正一下，我的常用编辑器现在改成Emacs了。",
                   "更正一下，我的常用编辑器现在改成Kate了。"]
        self.assertEqual(self.reader.answer("我的常用编辑器是什么？", context), "Kate")
        self.assertEqual(self.reader.answer("我最初说的常用编辑器是什么？", context), "Vim")

    def test_multiple_facts_follow_question_order(self):
        context = ["我的常用编辑器是Vim。", "我的所在城市是上海。"]
        self.assertEqual(self.reader.answer("我的所在城市和常用编辑器分别是什么？", context),
                         "上海；Vim")

    def test_missing_information(self):
        for question, context in (("我的所在城市是什么？", []),
                                  ("我的所在城市是什么？", ["我的常用编辑器是Vim。"]),
                                  ("我的姓名是什么？", ["我的所在城市是上海。"])):
            with self.subTest(question=question, context=context):
                self.assertEqual(self.reader.answer(question, context), ABSTAIN)
        self.assertEqual(self.reader.answer("我的所在城市和常用编辑器分别是什么？",
                                            ["我的所在城市是上海。"]), "上海；不知道")

    def test_forget_and_learn_again(self):
        context = ["我的所在城市是上海。", "请忘掉我的所在城市，不要再记住它。"]
        for question in ("我的所在城市是什么？", "我最初说的所在城市是什么？"):
            with self.subTest(question=question):
                self.assertEqual(self.reader.answer(question, context), ABSTAIN)
                self.assertEqual(self.reader.answer(question, context + ["我的所在城市是成都。"]),
                                 "成都")

    def test_distractors_do_not_replace_personal_fact(self):
        context = ["我的所在城市是上海。", "我的同事说他的所在城市是北京。",
                   "我的室友的所在城市是成都。", "我在考虑要不要把所在城市换成深圳，还没决定。",
                   "请忘掉我的常用编辑器，不要再记住它。"]
        self.assertEqual(self.reader.answer("我的所在城市是什么？", context), "上海")
