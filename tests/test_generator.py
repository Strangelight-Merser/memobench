import unittest
from collections import Counter

from memobench.generator import generate


class GeneratorTests(unittest.TestCase):
    def test_same_seed_is_deterministic(self):
        options = dict(n_per_category=3, n_sessions=4,
                       turns_per_session=6, seed=17, n_distract=2)
        first = [c.to_dict() for c in generate(**options)]
        generate(seed=99, n_per_category=1)
        self.assertEqual(first, [c.to_dict() for c in generate(**options)])

    def test_different_seeds_change_dataset(self):
        self.assertNotEqual(generate(n_per_category=2, seed=17),
                            generate(n_per_category=2, seed=18))

    def test_six_categories_and_unique_ids(self):
        categories = ("recall", "update", "multi", "temporal", "forget", "abstain")
        for n in (1, 3):
            with self.subTest(n=n):
                cases = generate(n_per_category=n)
                self.assertEqual(len(cases), 6 * n)
                self.assertEqual(Counter(c.category for c in cases),
                                 {category: n for category in categories})
                self.assertEqual(len({c.id for c in cases}), len(cases))

    def test_zero_cases(self):
        self.assertEqual(generate(n_per_category=0), [])
