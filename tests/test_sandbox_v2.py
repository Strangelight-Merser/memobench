"""卡5离线反例；这些 fixture 不属于正式故事或真实智能体结果。"""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from memobench.protocol_v2 import WriteReceipt, require_ready
from memobench.sandbox_v2 import (FileSandbox, assemble_cases, native_isolation_status,
                                public_task_input, sha256, verify_task)
from memobench.schema_v2 import (ContractError, Episode, Gold, Observation, Prediction,
                                Probe, SandboxReference)

SPEC = importlib.util.spec_from_file_location('probe_openkylin',
    Path(__file__).resolve().parents[1] / 'tools/probe_openkylin.py')
probe_env = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe_env)
STAMP = '2026-10-14T10:00:00Z'


class SandboxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.box = FileSandbox(Path(self.temp.name) / 'case')
        self.addCleanup(self.box.close)
        self.pred = Prediction('e', 'v', 's2', 'p', 'ok', '完成，偏好中文', STAMP)

    def create(self, path, text, op=None):
        result = self.box.execute('create', op or path, path=path, text=text)
        require_ready(WriteReceipt.from_dict(result['receipt']))
        return result

    def gold(self, **overrides):
        action = {'operation': 'create', 'path': 'current/note.txt', 'sha256': sha256('中文'),
                  'old_paths': ['old/note.txt']}
        action.update(overrides)
        return Gold('p', [], [], [], [action], [], ['update'], ['task_reuse'])

    def check(self, gold=None, baseline=None, since=0):
        return verify_task(self.box, gold or self.gold(), self.pred,
                           baseline=baseline or {}, audit_since=since)

    def test_create_read_list_audit_and_hash(self):
        self.create('current/note.txt', '中文')
        self.assertEqual(self.check()['status'], 'passed')
        self.assertEqual(self.box.execute('read', 'r', path='current/note.txt')['value'], '中文')
        self.assertEqual(self.box.execute('list', 'l')['value'], ['current/note.txt'])
        audit = self.box.execute('audit', 'a')['value']
        self.assertEqual(audit[0]['sha256'], sha256('中文'))
        audit[0]['status'] = 'tampered'
        self.assertEqual(self.box.audit[0]['status'], 'ready')

    def test_path_and_operation_rejections(self):
        for i, path in enumerate(['/tmp/escape', '../escape', 'a/../escape', 'a//b', '.',
                                  'a/./b', 'a\\b', 'a\x00b']):
            result = self.box.execute('create', str(i), path=path, text='secret')
            self.assertEqual(result['receipt']['status'], 'failed')
        self.assertEqual(self.box.execute('shell', 'shell', command='whoami')['receipt']['status'], 'failed')
        self.assertFalse((Path(self.temp.name) / 'escape').exists())
        self.assertNotIn('secret', repr(self.box.audit))

    def test_symlinks_and_hardlinks(self):
        outside = Path(self.temp.name) / 'outside'
        outside.mkdir()
        (outside / 'secret').write_text('untouched')
        (self.box.root / 'linked').symlink_to(outside, target_is_directory=True)
        (self.box.root / 'leaf').symlink_to(outside / 'secret')
        for i, path in enumerate(['linked/secret', 'leaf']):
            self.assertEqual(self.box.execute('read', 'r' + str(i), path=path)['receipt']['status'], 'failed')
            self.assertEqual(self.box.execute('create', 'w' + str(i), path=path, text='bad')['receipt']['status'], 'failed')
        os.link(outside / 'secret', self.box.root / 'hard')
        with self.assertRaises(ContractError):
            self.box.read('hard')
        self.assertEqual((outside / 'secret').read_text(), 'untouched')
        self.assertEqual(self.check()['faults'], ['unsafe_artifact'])

    def test_fifo_rejected_without_blocking(self):
        os.mkfifo(self.box.root / 'fifo')
        self.assertEqual(self.box.execute('read', 'fifo', path='fifo')['receipt']['status'], 'failed')

    def test_dedup_no_overwrite_and_failed_retry(self):
        first = self.create('a', 'one', 'op')
        self.assertEqual(first, self.box.execute('create', 'op', path='a', text='one'))
        self.assertEqual(len(self.box.audit), 1)
        with self.assertRaises(ContractError):
            self.box.execute('create', 'op', path='a', text='two')
        failure = self.box.execute('create', 'op2', path='a', text='two')
        self.assertEqual(failure['receipt']['status'], 'failed')
        self.assertEqual(self.box.execute('create', 'op2', path='a', text='two'), failure)
        self.assertEqual(self.box.read('a'), 'one')

    def test_template_and_stale_template(self):
        self.create('templates/old.txt', '旧版：$language')
        self.create('templates/current.txt', '新版：$language')
        baseline, since = self.box.snapshot(), len(self.box.audit)
        self.box.execute('render', 'render', path='current/note.txt',
                         template='templates/old.txt', values={'language': '中文'})
        gold = self.gold(operation='render', sha256=sha256('新版：中文'),
                         template_sha256=sha256('新版：$language'),
                         old_template_sha256=sha256('旧版：$language'))
        faults = self.check(gold, baseline, since)['faults']
        self.assertIn('stale_template', faults)
        self.assertIn('content_mismatch', faults)

    def test_render_success_and_missing_variable(self):
        self.create('template', '$language')
        baseline, since = self.box.snapshot(), len(self.box.audit)
        self.box.execute('render', 'ok', path='current/note.txt', template='template', values={'language': '中文'})
        gold = self.gold(operation='render', template_sha256=sha256('$language'))
        self.assertEqual(self.check(gold, baseline, since)['status'], 'passed')
        self.assertEqual(self.box.execute('render', 'bad', path='bad', template='template', values={})['receipt']['status'], 'failed')
        self.assertFalse((self.box.root / 'bad').exists())

    def test_false_success_old_path_and_external_tampering(self):
        self.assertIn('missing_file', self.check()['faults'])
        self.create('old/note.txt', '中文')
        self.assertIn('old_path_reuse', self.check()['faults'])
        self.create('current/note.txt', '中文')
        (self.box.root / 'current/note.txt').write_text('changed')
        self.assertIn('action_log_mismatch', self.check()['faults'])

    def test_existing_file_does_not_prove_new_action(self):
        self.create('current/note.txt', '中文')
        self.assertIn('action_log_mismatch', self.check(baseline=self.box.snapshot(), since=len(self.box.audit))['faults'])

    def test_forget_new_files_outputs_and_preserved_preference(self):
        canary = 'MEMOBENCH_FICTIONAL_CANARY_C5'
        self.create('before.txt', canary)
        baseline, since = self.box.snapshot(), len(self.box.audit)
        gold = self.gold()
        gold.forget_policies = [{'canary': canary, 'retained_text': '中文'}]
        self.create('current/note.txt', '中文')
        self.assertEqual(self.check(gold, baseline, since)['status'], 'passed')
        self.pred.text = '已忘记' + canary
        self.assertIn('forgotten_disclosure', self.check(gold, baseline, since)['faults'])
        self.pred.text = '完成'
        self.create('extra.txt', canary)
        self.assertIn('forgotten_disclosure', self.check(gold, baseline, since)['faults'])
        (self.box.root / 'current/note.txt').write_text('refuse')
        self.assertIn('unrelated_preference_lost', self.check(gold, baseline, since)['faults'])

    def test_forget_transient_file_and_tool_response(self):
        canary = 'MEMOBENCH_FICTIONAL_CANARY_C5'
        self.create('before.txt', canary)
        baseline, since = self.box.snapshot(), len(self.box.audit)
        gold = self.gold()
        gold.forget_policies = [{'canary': canary, 'retained_text': '中文'}]
        self.create('current/note.txt', '中文')
        self.box.execute('read', 'post-delete-read', path='before.txt')
        self.assertIn('forgotten_disclosure', self.check(gold, baseline, since)['faults'])
        self.create('transient.txt', canary)
        (self.box.root / 'transient.txt').unlink()
        faults = self.check(gold, baseline, since)['faults']
        self.assertIn('forgotten_disclosure', faults)
        self.assertIn('action_log_mismatch', faults)

    def test_scope_and_private_boundary(self):
        p = Probe('e', 'v', 's2', 'p', '创建文件', STAMP, [SandboxReference('r', 'template')])
        self.assertNotIn('expected_actions', public_task_input(p))
        with self.assertRaises(ContractError):
            public_task_input(self.gold())
        self.pred.probe_id = 'other'
        with self.assertRaises(ContractError):
            self.check()
        self.assertEqual(native_isolation_status()['status'], 'blocked')
        with FileSandbox(Path(self.temp.name) / 'variant2') as other:
            self.assertEqual(other.snapshot(), {})

    def test_existing_root_rejected(self):
        with self.assertRaises(FileExistsError):
            FileSandbox(self.box.root)

    def test_assembly_missing_review_and_existing_stories(self):
        ids = ['story' + str(i) for i in range(12)]
        self.assertEqual(assemble_cases([], ids, {})['status'], 'blocked')
        episodes = []
        for i, story in enumerate(ids):
            e = 'e' + str(i)
            episodes.append(Episode(e, 'v', story, 'test', ['s1', 's2'],
                [Observation(e, 'v', 's1', 'o', 'user', '离线合同样例', STAMP)],
                [Probe(e, 'v', 's2', 'p', '创建文件', STAMP)], [self.gold()]))
        self.assertEqual(assemble_cases(episodes, ids, {})['status'], 'pending_review')
        result = assemble_cases(episodes, ids, dict.fromkeys(ids, 'approved'))
        self.assertEqual(result['status'], 'ready')
        self.assertEqual(len(result['cases']), 12)
        self.assertIsNot(result['cases'][0], episodes[0])


class EnvironmentTests(unittest.TestCase):
    def test_ubuntu_and_macos_never_openkylin(self):
        for system, release in [('Darwin', 'ID=openkylin'), ('Linux', 'ID=ubuntu\nNAME=openKylin')]:
            with patch.object(probe_env.platform, 'system', return_value=system), \
                 patch.object(probe_env.Path, 'read_text', return_value=release), \
                 patch.object(probe_env, 'command', return_value={'status': 'blocked'}):
                result = probe_env.collect()
                self.assertEqual(result['status'], 'NOT_VERIFIED')
                self.assertIsNone(result['model_service_host']['host'])

    def test_detection_is_not_acceptance(self):
        with patch.object(probe_env.platform, 'system', return_value='Linux'), \
             patch.object(probe_env.Path, 'read_text', return_value='ID="openkylin"\nVERSION_ID="2.0"'), \
             patch.object(probe_env, 'command', return_value={'status': 'observed'}):
            result = probe_env.collect()
            self.assertTrue(result['openkylin_detected'])
            self.assertEqual(result['acceptance'], 'NOT_VERIFIED')

    def test_missing_tools_and_timeout(self):
        with patch.object(probe_env.shutil, 'which', return_value=None):
            self.assertEqual(probe_env.collect(['missing-tool'])['execution_host']['tools']['missing-tool']['status'], 'blocked')
        with patch.object(probe_env.subprocess, 'run', side_effect=probe_env.subprocess.TimeoutExpired('x', 10)):
            self.assertEqual(probe_env.command(['x'])['reason'], 'timeout')


if __name__ == '__main__':
    unittest.main()
