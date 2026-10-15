"""Bounded native acceptance uses complete approved cases, never sliced turns."""
import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from memobench.runner_v2 import select_cases, run
from memobench.native_preparation_v2 import prepare
from memobench.data_v2 import load_dataset
from memobench.adapters_v2 import factory
from memobench.schema_v2 import Prediction


class NativeSelectionTests(TestCase):
    def setUp(self):
        from test_native_preparation_v2 import NativePreparationTests
        self.fixture = NativePreparationTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.dataset = self.fixture.review_via_actual_html_export()
        self.episodes = load_dataset(self.dataset, 'test')
        first = self.episodes[0]
        self.selection = [{'story_id': first.story_id, 'variant_id': first.variant_id}]

    def test_exact_scope_preserves_all_turns_and_rejects_unknown_or_duplicate(self):
        selected = select_cases(self.episodes, self.selection)
        self.assertEqual(len(selected), 1)
        self.assertIs(selected[0], self.episodes[0])
        self.assertEqual(len(selected[0].observations), 80)
        for invalid in ([], None, self.selection * 2, [{'story_id': 'missing', 'variant_id': 'missing'}],
                        [{'story_id': self.episodes[0].story_id}], [{'story_id': 7, 'variant_id': 'x'}]):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                select_cases(self.episodes, invalid)

    def test_prepare_and_runner_use_same_single_complete_case(self):
        recipe = {'schema_version': 'native-run-recipe-1', 'dataset': 'unused', 'split': 'test',
                  'products': ['openclaw'], 'purpose': 'frozen_evaluation', 'case_selection': self.selection}
        plan = prepare(recipe, self.fixture.root / 'selected-plan', ssh_config=self.fixture.config,
                       acceptances={'openclaw': self.fixture.evidence}, dataset=self.dataset)
        self.assertEqual(plan['n_case'], 1)
        self.assertEqual(plan['product_calls'], 81)
        config = json.loads(Path(plan['configs']['openclaw']).read_text())
        calls = []
        class Transport:
            def __init__(self, *args, **kwargs): pass
            def request(self, method, operation, payload, home):
                calls.append(method)
                if method == 'query':
                    return Prediction(payload['episode_id'], payload['variant_id'], payload['session_id'],
                                      payload['probe_id'], 'ok', '蓝色', '2026-01-01T00:00:00Z').to_dict()
                return {'operation_id': operation, 'status': 'ready', 'usage': None}
            def close(self): pass
        with patch.object(factory, 'SSHVMTransport', Transport):
            result = run(config, self.fixture.root / 'selected-run', live=True)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['n_case'], 1)
        self.assertEqual(calls.count('observe'), 80)
        self.assertEqual(calls.count('query'), 1)
