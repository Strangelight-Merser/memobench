import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from memobench import runner_v2 as runner
from memobench.protocol_v2 import FakeComponentAdapter, FakeNativeAdapter, WriteReceipt
from memobench.schema_v2 import Episode, Observation, Probe, Gold, Slot, EvidenceLocation
from memobench.report_v2 import render


def episode():
    observations = [Observation('e', 'v', 's1', 'o' + str(i), role, role + ' text',
                    f'2026-01-01T00:00:0{i}Z') for i, role in enumerate(('system', 'user', 'assistant', 'tool'))]
    probes = [Probe('e', 'v', 's2', 'p', 'question', '2026-01-02T00:00:00Z')]
    gold = Gold('p', [Slot('private_slot', 'string', 'answer', 'PRIVATE_GOLD')],
                [EvidenceLocation('o1')], [], [], [], ['recall'], ['memory_retrieval'])
    return Episode('e', 'v', 'story', 'dev', ['s1', 's2'], observations, probes, [gold])


class RunnerTests(unittest.TestCase):
    def execute(self, factory=FakeComponentAdapter, **kwargs):
        return runner.execute_case(episode(), factory, mode=kwargs.pop('mode', 'component'),
                                   operation_prefix='test', **kwargs)

    def test_all_roles_and_no_gold(self):
        seen = []
        def reader(probe, recalled):
            seen.append(json.dumps([probe.to_public(), recalled.to_dict()]))
            return runner.fixture_reader(probe, recalled)
        result = self.execute(reader=reader)
        self.assertEqual(result['status'], 'completed')
        for role in ('system', 'user', 'assistant', 'tool'):
            self.assertIn(role + ' text', seen[0])
        self.assertNotIn('PRIVATE_GOLD', seen[0])
        self.assertNotIn('private_slot', seen[0])
        self.assertIsNone(result['results'][0]['score']['metrics']['answer_correct'])

    def test_native_never_uses_reader_and_preserves_sessions(self):
        result = self.execute(FakeNativeAdapter, mode='native_agent',
                              reader=lambda *_: self.fail('native used Reader'))
        self.assertEqual(result['status'], 'completed')
        methods = [e['method'] for e in result['events']]
        self.assertEqual(methods.count('reset_case'), 1)
        self.assertEqual(methods.count('begin_session'), 2)
        self.assertIn('assistant text', result['results'][0]['prediction']['text'])

    def test_future_observation_not_sent_before_probe(self):
        e = episode()
        e.observations.append(Observation('e', 'v', 's2', 'future', 'user', 'FUTURE', '2026-01-03T00:00:00Z'))
        result = runner.execute_case(e, FakeComponentAdapter, mode='component', operation_prefix='t')
        self.assertNotIn('FUTURE', result['results'][0]['prediction']['text'])

    def test_unknown_write_blocks_query_and_counts_error(self):
        class Unknown(FakeComponentAdapter):
            def observe(self, observation, operation_id):
                return WriteReceipt(operation_id, 'unknown')
            def recall(self, probe):
                raise AssertionError('must not query')
        result = self.execute(Unknown)
        summary = runner.summarize([episode()], [result], 'component', 'offline')
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(summary['partitions']['offline']['statistics']['error'], 1)
        self.assertEqual(summary['failed_cases'], 1)
        self.assertIsNone(summary['partitions']['offline']['statistics']['micro_mean'])

    def test_exception_text_is_not_logged(self):
        def factory():
            raise ValueError('SECRET')
        result = self.execute(factory)
        self.assertNotIn('SECRET', json.dumps(result))
        self.assertEqual(result['error']['stage'], 'create_adapter')

    def test_cleanup_failure_is_case_failure(self):
        class BrokenClose(FakeNativeAdapter):
            def close(self):
                raise RuntimeError('private')
        result = self.execute(BrokenClose, mode='native_agent')
        self.assertEqual(result['error']['stage'], 'close')
        self.assertEqual(result['status'], 'failed')

    def test_html_escape_and_missing(self):
        result = self.execute()
        result['results'][0]['prediction']['text'] = '<script>alert(1)</script>'
        summary = runner.summarize([episode()], [result], 'component', 'offline')
        summary.update(data_notice='候选数据，未签收', fixture=True)
        html = render(summary, result['results'])
        self.assertNotIn('<script>', html)
        self.assertIn('&lt;script&gt;', html)
        self.assertIn('未测', html)
        for text in ('v1 legacy', 'component', 'native', 'online', 'replay', '按故事宏平均'):
            self.assertIn(text, html)

    def test_safe_paths_and_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'run'
            root.mkdir()
            with self.assertRaises(ValueError):
                runner.save(root, '../escape.json', {})
            (root / 'cases').symlink_to(Path(tmp), target_is_directory=True)
            with self.assertRaises(ValueError):
                runner.save(root, 'cases/escape.json', {})

    def test_resume_skips_success_retries_failure_and_preserves_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = {'dataset': tmp, 'split': 'dev', 'mode': 'component', 'execution': 'offline',
                      'adapter': 'full-history-fixture', 'reader': 'echo-fixture'}
            # 输出不放在 dataset 中，避免恢复时真实数据哈希发生变化。
            with tempfile.TemporaryDirectory() as out, patch.object(runner, 'load_dataset', return_value=[episode()]), patch.object(runner, 'validate_release', return_value={'release_status': 'pending_review', 'formal_test_n_query': 0}):
                original = runner.execute_case
                failed = self.execute(lambda: (_ for _ in ()).throw(ValueError()))
                with patch.object(runner, 'execute_case', return_value=failed):
                    first = runner.run(config, out)
                self.assertEqual(first['status'], 'completed_with_errors')
                second = runner.run(config, out, resume=True)
                self.assertEqual(second['status'], 'completed')
                case = runner.read(next((Path(out) / 'cases').glob('*.json')))
                self.assertEqual([a['status'] for a in case['attempts']], ['failed', 'completed'])
                with patch.object(runner, 'execute_case', side_effect=AssertionError('repeated success')):
                    runner.run(config, out, resume=True)
                with self.assertRaises(ValueError):
                    runner.run(dict(config, split='candidates'), out, resume=True)

    def test_interruption_leaves_running_record_then_restarts_episode(self):
        with tempfile.TemporaryDirectory() as data, tempfile.TemporaryDirectory() as out:
            config = {'dataset': data, 'split': 'dev', 'mode': 'component', 'execution': 'offline',
                      'adapter': 'full-history-fixture', 'reader': 'echo-fixture'}
            with patch.object(runner, 'load_dataset', return_value=[episode()]), patch.object(runner, 'validate_release', return_value={'release_status': 'pending_review', 'formal_test_n_query': 0}):
                with patch.object(runner, 'execute_case', side_effect=KeyboardInterrupt):
                    with self.assertRaises(KeyboardInterrupt):
                        runner.run(config, out)
                path = next((Path(out) / 'cases').glob('*.json'))
                self.assertEqual(runner.read(path)['attempts'][0]['status'], 'running')
                runner.run(config, out, resume=True)
                self.assertEqual(len(runner.read(path)['attempts']), 2)
                self.assertEqual(runner.read(path)['attempts'][-1]['status'], 'completed')

    def test_execution_partitions_are_separate(self):
        result = self.execute()
        result['results'][0]['execution'] = 'replay'
        summary = runner.summarize([episode()], [result], 'component', 'online')
        self.assertEqual(summary['partitions']['online']['statistics']['n_received'], 0)
        self.assertEqual(summary['partitions']['replay']['statistics']['n_repeat'], 0)


if __name__ == '__main__':
    unittest.main()
