"""Regressions found in the actual VM integration, without model calls."""
import json
from contextlib import closing
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

from tools import native_vm_product as bridge
from memobench.adapters_v2.ssh_vm import SSHVMTransport
from memobench.adapters_v2.transports import TransportError


class NativeVMBindingTests(unittest.TestCase):
    def test_kylin_reads_current_committed_answer_not_debug_stdout(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            state = home / '.kylin-agent-runtime'
            state.mkdir()
            with closing(sqlite3.connect(state / 'state.db')) as db, db:
                db.execute('CREATE TABLE messages(id INTEGER, session_id TEXT, role TEXT, '
                           'content TEXT, timestamp REAL, tool_calls TEXT)')
                db.execute('CREATE TABLE sessions(id TEXT, system_prompt TEXT)')
                db.execute('INSERT INTO sessions VALUES(?, ?)', ('s1', '<user_profile_data>native nickname</user_profile_data>'))
                db.executemany('INSERT INTO messages VALUES(?,?,?,?,?,?)', [
                    (1, 's1', 'assistant', 'stale', 1, None),
                    (2, 'other', 'assistant', 'wrong session', time.time()+100, None),
                    (3, 's1', 'assistant', 'native answer', time.time()+100, None),
                    (4, 's1', 'assistant', 'tool narration', time.time()+100, '[{}]')])
            completed = subprocess.CompletedProcess([], 0, 'debug\nFAKE ANSWER', 'session_id: s1\n')
            provider = {'api_key': 'test-secret', 'base_url': 'https://example.invalid/v1', 'model': 'fixture'}
            log = state / 'logs/agent.log'
            log.parent.mkdir()
            def run_completed(*args, **kwargs):
                with log.open('a') as stream:
                    stream.write('User-profile extraction LLM call completed: applied=1\n')
                    stream.write('Turn ended: reason=completion_review:completed model=fixture session=s1\n')
                return completed
            with patch.object(bridge.subprocess, 'run', side_effect=run_completed):
                result = bridge.invoke(home, 'kylin', provider, 'test', {})
            self.assertTrue(result['ok'])
            self.assertEqual(result['answer'], 'native answer')
            self.assertIn('native nickname', result['native_profile_prompt'])
            with patch.object(bridge.subprocess, 'run', return_value=completed):
                paused = bridge.invoke(home, 'kylin', provider, 'test', {})
            self.assertFalse(paused['ok'])
            self.assertEqual(paused['task_status'], 'unverified_or_incomplete')
            def run_without_profile(*args, **kwargs):
                with log.open('a') as stream:
                    stream.write('Turn ended: reason=completion_review:completed model=fixture session=s1\n')
                return completed
            with patch.object(bridge.subprocess, 'run', side_effect=run_without_profile):
                missing_profile = bridge.invoke(home, 'kylin', provider, 'test', {})
            self.assertEqual(missing_profile['task_status'], 'completed')
            self.assertFalse(missing_profile['profile_completed'])
            self.assertFalse(missing_profile['ok'])


    def test_failed_process_does_not_accept_old_answer(self):
        completed = subprocess.CompletedProcess([], 1, 'old answer', 'session_id: old\n')
        provider = {'api_key': 'test-secret', 'base_url': 'https://example.invalid/v1', 'model': 'fixture'}
        with patch.object(bridge.subprocess, 'run', return_value=completed):
            result = bridge.invoke(Path('/not-present'), 'kylin', provider, 'test', {})
        self.assertFalse(result['ok'])
        self.assertIsNone(result['answer'])

    def test_openclaw_has_no_openai_credential_alias(self):
        completed = subprocess.CompletedProcess([], 0, json.dumps({'payloads': [{'text': 'answer'}]}), '')
        provider = {'api_key': 'test-secret', 'base_url': 'https://example.invalid/v1', 'model': 'fixture'}
        with patch.object(bridge.subprocess, 'run', return_value=completed) as run:
            result = bridge.invoke(Path('/fixture'), 'openclaw', provider, 'test', {})
        self.assertTrue(result['ok'])
        env = run.call_args.kwargs['env']
        self.assertNotIn('OPENAI_API_KEY', env)
        self.assertNotIn('OPENAI_BASE_URL', env)
        self.assertEqual(env['DEEPSEEK_API_KEY'], 'test-secret')

    def test_timeout_preserves_diagnostics_without_key(self):
        provider = {'api_key': 'test-secret', 'base_url': 'https://example.invalid/v1', 'model': 'fixture'}
        failure = subprocess.TimeoutExpired([], 180, output=b'partial test-secret', stderr=b'error')
        with patch.object(bridge.subprocess, 'run', side_effect=failure):
            result = bridge.invoke(Path('/fixture'), 'openclaw', provider, 'test', {})
        self.assertFalse(result['ok'])
        self.assertTrue(result['timeout'])
        self.assertNotIn('test-secret', json.dumps(result))
        self.assertIn('partial', result['stdout'])

    def test_transport_requires_explicit_live(self):
        with self.assertRaises(TransportError):
            SSHVMTransport('/fixture', 'kylin')
