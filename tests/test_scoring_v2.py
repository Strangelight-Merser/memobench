import json
from pathlib import Path
import unittest

from memobench.schema_v2 import Gold, Prediction, Slot
from memobench.scoring_v2 import score, summarize, value_equal

STAMP = "2026-10-14T10:00:00Z"


def gold(slots, **kwargs):
    return Gold("p", slots, kwargs.get("evidence", []), kwargs.get("ledger", []),
                kwargs.get("actions", []), kwargs.get("policies", []),
                ["recall"], ["memory_retrieval"])


def prediction(slots=None, text=None, **kwargs):
    if text is None:
        text = json.dumps({"slots": [s.to_dict() for s in slots]}, ensure_ascii=False)
    return Prediction("e", "v", "s", "p", "ok", text, STAMP, slots=slots, **kwargs)


class ScoringTests(unittest.TestCase):
    def test_swapped_fields(self):
        g = gold([Slot("editor", "string", "answer", "Vim"),
                  Slot("browser", "string", "answer", "Firefox")])
        p = prediction([Slot("editor", "string", "answer", "Firefox"),
                        Slot("browser", "string", "answer", "Vim")])
        self.assertFalse(score(g, p)["metrics"]["answer_correct"])

    def test_natural_counterexamples_pending(self):
        for state, value, text in [("answer", "UKUI", "不是UKUI。"),
                                   ("unknown", None, "不知道，但你住在北京。")]:
            r = score(gold([Slot("x", "string", state, value)]), prediction(text=text))
            self.assertEqual(r["status"], "pending_review")
            self.assertIsNone(r["metrics"]["answer_correct"])

    def test_types_and_aliases(self):
        self.assertTrue(value_equal(Slot("n", "number", "answer", 2), 2.0))
        self.assertFalse(value_equal(Slot("n", "number", "answer", 1), True))
        self.assertFalse(value_equal(Slot("p", "path", "answer", "/Work/A"), "/work/a"))
        self.assertFalse(value_equal(Slot("v", "version", "answer", "2.0 SP1"), "2.0"))
        self.assertTrue(value_equal(Slot("s", "string", "answer", "Vim", ["vim"]), "vim"))

    def test_old_version_substring(self):
        s = Slot("os", "version", "answer", "openKylin 2.0 SP1")
        g = gold([s], ledger=[{"slot": "os", "scope": "current", "previous_values": ["openKylin 2.0"]}])
        r = score(g, prediction([s]))
        self.assertTrue(r["metrics"]["answer_correct"])
        self.assertFalse(r["metrics"]["current_value_misuse"])
        old = Slot("os", "version", "answer", "openKylin 2.0")
        self.assertTrue(score(g, prediction([old]))["metrics"]["current_value_misuse"])

    def test_negated_old_and_history(self):
        s = Slot("editor", "string", "answer", "Vim")
        g = gold([s], ledger=[{"slot": "editor", "scope": "current", "previous_values": ["Emacs"]}])
        r = score(g, prediction(text="现在是Vim，不再是Emacs。"))
        self.assertIsNone(r["metrics"]["current_value_misuse"])
        history = gold([Slot("editor", "string", "answer", "Emacs")],
                       ledger=[{"slot": "editor", "scope": "historical", "previous_values": ["Emacs"]}])
        r = score(history, prediction(history.slots))
        self.assertTrue(r["metrics"]["answer_correct"])
        self.assertIsNone(r["metrics"]["current_value_misuse"])

    def test_privacy_in_negation(self):
        g = gold([Slot("secret", "string", "forgotten", None)],
                 policies=[{"slot": "secret", "mode": "literal_disclosure", "values": ["虚构CANARY-27"]}])
        r = score(g, prediction(text="我不再记得虚构CANARY-27。"))
        self.assertTrue(r["metrics"]["forgotten_disclosure"])

    def test_states(self):
        for state in ("answer", "unknown", "forgotten", "conflict"):
            s = Slot("x", "string", state, "A" if state == "answer" else None)
            self.assertTrue(score(gold([s]), prediction([s]))["metrics"]["answer_correct"])
        g = gold([Slot("x", "string", "unknown", None)])
        p = prediction([Slot("x", "string", "answer", "北京")])
        self.assertTrue(score(g, p)["metrics"]["unknown_assertion"])

    def test_untrusted_side_slots(self):
        s = Slot("x", "string", "answer", "UKUI")
        r = score(gold([s]), prediction([s], text="不是UKUI"))
        self.assertIsNone(r["metrics"]["answer_correct"])

    def test_state_conflict_and_escaped_disclosure(self):
        s = Slot("x", "string", "answer", "UKUI")
        p = prediction([s], state="unknown")
        self.assertIsNone(score(gold([s]), p)["metrics"]["answer_correct"])
        g = gold([Slot("secret", "string", "forgotten", None)],
                 policies=[{"slot": "secret", "mode": "literal_disclosure", "values": ["虚构秘密"]}])
        text = json.dumps({"slots": [Slot("secret", "string", "answer", "虚构秘密").to_dict()]})
        self.assertTrue(score(g, prediction(text=text))["metrics"]["forgotten_disclosure"])

    def test_always_refuse_cannot_complete_task(self):
        g = gold([Slot("path", "path", "answer", "work/report.txt")], actions=[{"path": "work/report.txt"}])
        p = prediction([Slot("path", "path", "unknown", None)])
        r = score(g, p, task_checks=[False])
        self.assertFalse(r["metrics"]["answer_correct"])
        self.assertFalse(r["metrics"]["task_completed"])
        self.assertIsNone(score(g, p)["metrics"]["task_completed"])
        with self.assertRaises(ValueError):
            score(g, p, task_checks=[])

    def test_empty_denominators_and_pending(self):
        self.assertIsNone(summarize([])["metrics"]["answer_correct"]["rate"])
        r = score(gold([Slot("x", "string", "answer", "A")]), prediction(text="散文"))
        stats = summarize([r])["metrics"]["answer_correct"]
        self.assertEqual((stats["eligible"], stats["denominator"], stats["pending"]), (1, 0, 1))

    def test_development_fixtures(self):
        path = Path(__file__).resolve().parents[1] / "evaluation/calibration/development.jsonl"
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        self.assertGreaterEqual(len(rows), 20)
        for row in rows:
            with self.subTest(item=row["item_id"]):
                r = score(Gold.from_dict(row["gold"]), Prediction.from_dict(row["prediction"]))
                for metric, expected in row["expected_rule_metrics"].items():
                    self.assertEqual(r["metrics"][metric], expected)
