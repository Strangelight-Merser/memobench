"""故事聚类、配对、缺失与缓存重复的离线反例。"""
import unittest

from memobench.schema_v2 import Episode, Probe, Gold, Slot, Prediction
from memobench.stats_v2 import Sample, paired_bootstrap, summarize, wilson_interval

STAMP = "2026-10-14T10:00:00Z"


def episode(story, variant="v", count=1):
    probes = [Probe(story, variant, "s", str(i), "问题", STAMP) for i in range(count)]
    golds = [Gold(p.probe_id, [Slot("editor", "string", "answer", "Vim")], [], [], [], [],
                  ["recall"], ["long_term_retention"]) for p in probes]
    return Episode(story, variant, story, "dev", ["s"], [], probes, golds)


def sample(ep, score=1, index=0, repeat="r1", execution="online", status="ok"):
    p = ep.probes[index]
    pred = Prediction(p.episode_id, p.variant_id, p.session_id, p.probe_id, status,
                      "Vim" if status == "ok" else None, STAMP)
    return Sample(pred, score, repeat, execution)


class StatisticsTests(unittest.TestCase):
    def test_cluster_not_probe_weight(self):
        a, b = episode("a", count=10), episode("b")
        left = [sample(a, 1, i) for i in range(10)] + [sample(b, 0)]
        right = [sample(a, 0, i) for i in range(10)] + [sample(b, 1)]
        result = paired_bootstrap([a, b], left, right, execution="online")
        self.assertEqual(result["difference"], 0)
        self.assertEqual(result["n_story"], 2)
        self.assertEqual(result["n_pairs"], 11)
        self.assertEqual(result["ci95"], [-1, 1])
        self.assertEqual(result, paired_bootstrap([a, b], left, right, execution="online"))

    def test_variants_share_story(self):
        a, av, b = episode("a"), episode("a", "v2"), episode("b")
        data = [a, av, b]
        result = paired_bootstrap(data, [sample(e) for e in data], [sample(e, 0) for e in data], execution="online")
        self.assertEqual(result["n_story"], 2)
        self.assertEqual(result["n_query"], 3)
        self.assertEqual(result["ci95"], [1, 1])

    def test_replay_never_increases_repeat(self):
        ep = episode("a")
        live = sample(ep)
        replay = sample(ep, execution="replay", repeat="r2")
        result = summarize([ep], [live, replay, replay], execution="online", expected_repeats=["r1", "r2"])
        self.assertEqual(result["n_repeat"], 1)
        self.assertEqual(result["n_received"], 1)
        self.assertEqual(result["missing"], 1)
        self.assertEqual(result["n_replay"], 2)
        result = summarize([ep], [replay, replay], execution="replay", expected_repeats=["r2"])
        self.assertEqual(result["n_repeat"], 0)
        self.assertEqual(result["n_received"], 1)
        with self.assertRaises(ValueError):
            paired_bootstrap([ep], [replay], [replay], execution="replay")

    def test_missing_timeout_error_denominators(self):
        ep = episode("a", count=5)
        rows = [sample(ep), sample(ep, None, 1, status="timeout"),
                sample(ep, None, 2, status="error"), sample(ep, None, 3, status="unsupported")]
        out = summarize([ep], rows, execution="online", expected_repeats=["r1"])
        self.assertEqual(out["missing"], 1)
        self.assertEqual(out["timeout_rate"], 0.2)
        self.assertEqual(out["error_rate"], 0.4)
        self.assertEqual(out["denominator"], 1)
        self.assertEqual(out["capabilities"]["long_term_retention"]["n_expected"], 5)
        self.assertIsNone(out["capabilities"]["task_reuse"]["mean"])

    def test_empty_denominators(self):
        out = summarize([], [], execution="online", expected_repeats=["r1"])
        for name in ("error_rate", "timeout_rate", "micro_mean", "story_macro_mean"):
            self.assertIsNone(out[name])
        result = paired_bootstrap([], [], [], execution="online")
        self.assertIsNone(result["difference"])
        self.assertIsNone(result["ci95"])
        self.assertIsNone(wilson_interval(0, 0))

    def test_wilson(self):
        low, high = wilson_interval(5, 10)
        self.assertAlmostEqual(low, 0.236593, places=5)
        self.assertAlmostEqual(high, 0.763407, places=5)
        self.assertAlmostEqual(wilson_interval(0, 10)[0], 0)
        self.assertAlmostEqual(wilson_interval(10, 10)[1], 1)
        with self.assertRaises(ValueError):
            wilson_interval(2, 1)

    def test_incomplete_pairs_and_one_story(self):
        ep = episode("a", count=2)
        out = paired_bootstrap([ep], [sample(ep), sample(ep, 0, 1)], [sample(ep, 0)], execution="online")
        self.assertEqual(out["difference"], 1)
        self.assertEqual(out["missing_or_unscored_pairs"], 1)
        self.assertIsNone(out["ci95"])

    def test_duplicate_and_invalid_score_rejected(self):
        ep = episode("a")
        row = sample(ep)
        with self.assertRaises(ValueError):
            summarize([ep], [row, row], execution="online", expected_repeats=["r1"])
        with self.assertRaises(ValueError):
            sample(ep, float("nan"))
        with self.assertRaises(ValueError):
            sample(ep, 1, status="timeout")
        with self.assertRaises(ValueError):
            summarize([], [row], execution="online", expected_repeats=["r1"])

    def test_offline_online_separate(self):
        ep = episode("a")
        out = summarize([ep], [sample(ep, 1, execution="offline"), sample(ep, 0)],
                        execution="online", expected_repeats=["r1"])
        self.assertEqual(out["micro_mean"], 0)
        self.assertEqual(out["n_received"], 1)


if __name__ == "__main__":
    unittest.main()
