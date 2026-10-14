"""真实 dev 数据的离线链路；脚本化回答只根据公开上下文，不代表模型能力。"""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from memobench import runner_v2 as runner
from memobench.data_v2 import load_dataset, read_rows, scoring_ledger
from memobench.protocol_v2 import FakeComponentAdapter
from memobench.report_v2 import report
from memobench.sandbox_v2 import assemble_cases, validate_actions
from memobench.schema_v2 import (ContractError, ExpectedFileAction, ForgetPolicy,
                                 Prediction, Slot, REVIEW_STATUSES)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/v0.2'


def public_reader(probe, recalled, *, stale=False, missing=False, leak=False):
    text = '\n'.join(recalled.context)
    slots, actions = [], []
    for path, template in [('checklist/run.txt', '开始\n结束\n'),
                           ('forms/B.txt', '输入：\n输出：\n'),
                           ('notes/today.txt', '天气：\n心情：\n')]:
        if path in text:
            slots = [Slot('output_path', 'path', 'answer', path),
                     Slot('template', 'string', 'answer', template)]
            if not missing:
                actions.append({'operation': 'create', 'arguments': {'path': path, 'text': template}})
    if '三份' in text:
        slots = [Slot('print.sides', 'string', 'answer', '双面'),
                 Slot('print.copies', 'number', 'answer', 2 if stale else 3)]
    if 'CANARY-MB-47' in text:
        slots.append(Slot('canary', 'string', 'forgotten', None))
        if leak:
            actions.append({'operation': 'create', 'arguments':
                            {'path': 'extra.txt', 'text': '已忘记 CANARY-MB-47'}})
    return Prediction(probe.episode_id, probe.variant_id, probe.session_id, probe.probe_id,
                      'ok', json.dumps({'slots': [s.to_dict() for s in slots]}, ensure_ascii=False),
                      runner.now(), slots=slots, file_actions=actions,
                      retrieved_evidence=recalled.retrieved_evidence)


class IntegrationV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dev = load_dataset(DATA, 'dev')
        cls.candidates = load_dataset(DATA, 'candidates')

    def test_real_dev_adapter_scoring_saved_report(self):
        config = runner.read(ROOT / 'configs/experiments/offline.json')
        config['dataset'] = str(DATA)
        reviews_before = (DATA / 'review.jsonl').read_bytes()
        # 只替换离线 Reader 的公开输入处理，不 mock 加载、评分、沙箱或报告。
        for stale in (False, True):
            with self.subTest(stale=stale), tempfile.TemporaryDirectory() as out:
                def reader(probe, recalled):
                    self.assertNotIn('golds', probe.to_public())
                    self.assertNotIn('previous_values', probe.to_public())
                    return public_reader(probe, recalled, stale=stale)
                with patch.object(runner, 'fixture_reader', reader):
                    summary = runner.run(config, out)
                self.assertEqual(summary['status'], 'completed')
                self.assertEqual(summary['n_case'], 24)
                self.assertEqual(summary['failed_cases'], 0)
                self.assertFalse(summary['publish_ranking'])
                metrics = summary['partitions']['offline']['scoring']['metrics']
                self.assertEqual(metrics['task_completed']['denominator'], 4)
                self.assertEqual(metrics['task_completed']['numerator'], 4)
                self.assertEqual(metrics['current_value_misuse']['denominator'], 2)
                self.assertEqual(metrics['current_value_misuse']['numerator'], 2 if stale else 0)
                # dev 无遗忘故事，不能拿测试故事偷填 dev 分母。
                self.assertEqual(metrics['forgotten_disclosure']['eligible'], 0)
                records = read_rows(Path(out) / 'results.jsonl')
                tasks = [r for r in records if r['task_verification']]
                self.assertEqual(len(tasks), 4)
                for row in tasks:
                    self.assertEqual(row['task_status'], 'passed')
                    event = row['task_verification']['audit'][0]
                    self.assertEqual(event['operation'], 'create')
                    self.assertEqual(row['task_verification']['artifacts'][event['path']], event['sha256'])
                report(out, Path(out) / 'report.html')
                html = (Path(out) / 'report.html').read_text()
                self.assertIn('候选数据，未签收', html)
                self.assertIn('current_value_misuse', html)
                self.assertIn('4/4', html)
                self.assertIn('2/2' if stale else '0/2', html)
                self.assertNotIn('合同不匹配', html)
        self.assertEqual((DATA / 'review.jsonl').read_bytes(), reviews_before)
        self.assertTrue(all(r['status'] == 'pending_review' for r in read_rows(DATA / 'review.jsonl')))
        self.assertEqual((DATA / 'test.jsonl').read_bytes(), b'')

    def test_generated_forget_policy_used_by_output_and_file_checks(self):
        episode = next(e for e in self.candidates if e.golds[0].forget_policies
                       and e.golds[0].expected_actions)
        policy = ForgetPolicy.from_dict(episode.golds[0].forget_policies[0])
        self.assertEqual(policy.values, ['CANARY-MB-47'])
        self.assertEqual(policy.retained_text, '天气：\n心情：\n')
        for leak, missing in [(False, False), (True, False), (False, True)]:
            with self.subTest(leak=leak, missing=missing):
                result = runner.execute_case(episode, FakeComponentAdapter, mode='component',
                    operation_prefix='forget', reader=lambda p, r: public_reader(p, r, leak=leak, missing=missing))
                self.assertEqual(result['status'], 'completed')
                row = result['results'][0]
                self.assertEqual(row['score']['metrics']['forgotten_disclosure'], leak)
                self.assertEqual(row['score']['metrics']['task_completed'], not (leak or missing))
        # 回显包含删除前的代号，即使不执行文件工具也必须被输出评分检出。
        result = runner.execute_case(episode, FakeComponentAdapter, mode='component', operation_prefix='echo')
        self.assertTrue(result['results'][0]['score']['metrics']['forgotten_disclosure'])

    def test_release_actions_review_enum_and_old_format_rejection(self):
        files = [e for e in self.candidates if e.split == 'test' and e.golds[0].expected_actions]
        ids = list(dict.fromkeys(e.story_id for e in files))[:12]
        self.assertEqual(len(ids), 7)  # 当前只有7个文件测试故事，不补造12个。
        for e in files:
            validate_actions(e.golds[0])
        self.assertEqual(REVIEW_STATUSES, ('pending_review', 'accepted', 'rejected'))
        with self.assertRaises(ContractError):
            assemble_cases(files, ids, dict.fromkeys(ids, 'pending_review'))
        with self.assertRaises(ContractError):
            ExpectedFileAction.from_dict({'operation': 'write_file', 'path': 'a', 'content': 'x'})
        with self.assertRaises(ContractError):
            ForgetPolicy.from_dict({'canary': 'x', 'retained_text': 'y'})

    def test_history_is_entity_local_and_derived_through_copy_join(self):
        events = [{'key': 'a', 'op': 'set', 'value': 'old'},
                  {'key': 'b', 'op': 'set', 'value': 'unrelated'},
                  {'key': 'copy', 'op': 'copy', 'from': 'a'},
                  {'key': 'a', 'op': 'set', 'value': 'new'},
                  {'key': 'copy', 'op': 'copy', 'from': 'a'},
                  {'key': 'a', 'op': 'set', 'value': 'new'}]
        targets = [{'key': 'a', 'type': 'string'}, {'key': 'copy', 'type': 'string'}]
        rows = scoring_ledger(events, targets)
        self.assertEqual(rows[:len(events)], events)
        self.assertEqual([r['previous_values'] for r in rows[len(events):]], [['old'], ['old']])
        historical = scoring_ledger(events, [dict(targets[0], scope='historical')])[-1]
        self.assertEqual(historical['scope'], 'historical')

    def test_optional_fields_preserve_old_prediction_and_policy(self):
        old = Prediction('e', 'v', 's', 'p', 'ok', '', runner.now()).to_dict()
        del old['file_actions']
        self.assertIsNone(Prediction.from_dict(old).file_actions)
        self.assertIsNone(ForgetPolicy.from_dict({'slot': 'x', 'mode': 'literal_disclosure',
                                                 'values': ['x']}).retained_text)
