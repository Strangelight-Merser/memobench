import unittest

from memobench.memory.baselines import BM25Retrieval, FullContext, ProfileStore, SlidingWindow
from memobench.reader import RuleReader
from memobench.schema import ABSTAIN, Turn


def observe(memory, texts, session=0):
    for index, text in enumerate(texts):
        memory.observe(Turn(session, 2 * index, "user", text))
        memory.observe(Turn(session, 2 * index + 1, "assistant", "好的，我记下了。"))
    memory.end_session(session)


class MemoryTests(unittest.TestCase):
    def test_empty_memories(self):
        for cls in (FullContext, SlidingWindow, BM25Retrieval, ProfileStore):
            with self.subTest(system=cls.name):
                self.assertEqual(cls().recall("我的所在城市是什么？"), [])

    def test_full_context_preserves_user_history_across_sessions(self):
        memory = FullContext()
        first = "我的所在城市是上海。"
        latest = "更正一下，我的所在城市现在改成北京了。"
        observe(memory, [first])
        observe(memory, [latest], session=1)
        context = memory.recall("我的所在城市是什么？")
        self.assertEqual(context, [first, latest])
        self.assertEqual(RuleReader().answer("我最初说的所在城市是什么？", context), "上海")

    def test_sliding_window_forgets_early_fact(self):
        memory = SlidingWindow(size=2)
        observe(memory, ["我的所在城市是上海。", "今天风扇有点吵。"])
        question = "我的所在城市是什么？"
        self.assertEqual(RuleReader().answer(question, memory.recall(question)), "上海")
        observe(memory, ["怎么查看内核版本？"], session=1)
        self.assertEqual(memory.recall(question), ["今天风扇有点吵。", "怎么查看内核版本？"])
        self.assertEqual(RuleReader().answer(question, memory.recall(question)), ABSTAIN)

    def test_bm25_selects_relevant_facts_in_chronological_order(self):
        memory = BM25Retrieval(k=2)
        first = "我的所在城市是上海。"
        latest = "更正一下，我的所在城市现在改成北京了。"
        observe(memory, [first, "abcdefgh", latest, "ijklmnop"])
        question = "我的所在城市是什么？"
        self.assertEqual(memory.recall(question), [first, latest])
        self.assertEqual(RuleReader().answer(question, memory.recall(question)), "北京")
        self.assertEqual(memory.recall("XYZ"), [])

    def test_bm25_top_k_ignores_assistant_messages(self):
        memory = BM25Retrieval(k=1)
        observe(memory, ["abcdefgh", "我的所在城市是上海。"])
        memory.observe(Turn(0, 4, "assistant", "我的所在城市是什么？"))
        self.assertEqual(memory.recall("我的所在城市是什么？"), ["我的所在城市是上海。"])

    def test_profile_updates_but_loses_temporal_history(self):
        memory = ProfileStore()
        observe(memory, ["我的所在城市是上海。", "更正一下，我的所在城市现在改成北京了。"])
        context = memory.recall("我的所在城市是什么？")
        self.assertEqual(context, ["我的所在城市是北京。"])
        self.assertEqual(RuleReader().answer("我的所在城市是什么？", context), "北京")
        # 画像仅保存最新值，无法恢复最初的上海。
        self.assertEqual(RuleReader().answer("我最初说的所在城市是什么？", context), "北京")

    def test_profile_forgets_only_requested_fact(self):
        memory = ProfileStore()
        observe(memory, ["我的所在城市是上海。", "我的常用编辑器是Vim。",
                         "请忘掉我的所在城市，不要再记住它。"])
        context = memory.recall("我的所在城市是什么？")
        self.assertEqual(context, ["我的常用编辑器是Vim。"])
        self.assertEqual(RuleReader().answer("我的所在城市是什么？", context), ABSTAIN)
        observe(memory, ["我的所在城市是成都。"], session=1)
        self.assertEqual(RuleReader().answer("我的所在城市是什么？", memory.recall("")), "成都")

    def test_profile_ignores_assistant_facts(self):
        memory = ProfileStore()
        observe(memory, ["我的所在城市是上海。"])
        memory.observe(Turn(0, 2, "assistant", "我的所在城市是北京。"))
        memory.observe(Turn(0, 3, "assistant", "请忘掉我的所在城市，不要再记住它。"))
        self.assertEqual(memory.recall(""), ["我的所在城市是上海。"])
