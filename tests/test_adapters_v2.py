"""卡4离线验收；假进程与 HTTP fixture 不代表真实产品。"""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

from memobench.adapters_v2 import NativeAdapter, SubprocessTransport, HTTPTransport, TransportError
from memobench.adapters_v2.transports import decode_response
from memobench.protocol_v2 import require_ready
from memobench.schema_v2 import AdapterCapabilities, ContractError, Observation, Probe
from tools.probe_agents import probe

STAMP = "2026-10-14T10:00:00Z"
# 磁盘状态只证明测试桥的行为，不能作为智能体记忆证据。
WORKER = r'''
import json, os, sys, time
from pathlib import Path
request = json.load(sys.stdin)
p = request['payload']
method = request['method']
root = Path.home()
f = root / 'state.json'
state = json.loads(f.read_text()) if f.exists() else {'observations': [], 'calls': []}
state['calls'].append(request)
if method == 'reset_case':
    state['observations'] = []
if method == 'observe':
    state['observations'].append(p)
f.write_text(json.dumps(state))
if method == 'observe' and p['text'] == 'slow':
    time.sleep(3)
if method == 'observe' and p['text'] == 'bad-json':
    print('oops'); sys.exit(0)
if method == 'observe' and p['text'] == 'crash':
    print('SECRET', file=sys.stderr); sys.exit(1)
if method == 'query':
    result = {k: p[k] for k in ('episode_id', 'variant_id', 'session_id', 'probe_id')}
    result.update(status='ok', text='native:' + '|'.join(o['text'] for o in state['observations']),
                  answered_at='2026-10-14T11:00:00Z')
else:
    result = dict(operation_id=request['operation_id'], status='ready')
    if method == 'observe' and p['text'] == 'async':
        result['status'] = 'unknown'
print(json.dumps(result))
'''


def capabilities(**kw):
    return AdapterCapabilities(native_answer="supported", **kw)


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        worker = self.root / "worker.py"
        worker.write_text(WORKER)
        self.transport = SubprocessTransport([sys.executable, str(worker)], live=True, timeout=1)
        self.adapter = NativeAdapter(self.transport, capabilities(), run_directory=self.root / "run")
        self.addCleanup(self.adapter.close)
        require_ready(self.adapter.reset_case("e", "v", "reset"))
        require_ready(self.adapter.begin_session("s1", "begin"))

    def observation(self, text="fictional canary", **kw):
        fields = dict(episode_id="e", variant_id="v", session_id="s1", observation_id="o",
                      role="user", text=text, observed_at=STAMP)
        fields.update(kw)
        return Observation(**fields)

    def question(self, session="s1", variant="v"):
        return Probe("e", variant, session, "p", "记住了什么？", STAMP)

    def state(self):
        return json.loads((self.adapter._home / "state.json").read_text())

    def test_sessions_preserve_memory_and_native_response(self):
        self.adapter.observe(self.observation(), "write")
        home = self.adapter._home
        require_ready(self.adapter.end_session("s1", "end"))
        require_ready(self.adapter.begin_session("s2", "begin2"))
        result = self.adapter.query(self.question("s2"), "query")
        self.assertEqual(result.text, "native:fictional canary")
        self.assertEqual(home, self.adapter._home)
        self.assertIsNone(result.usage)
        self.assertIsNone(result.retrieved_evidence)

    def test_variant_and_episode_isolation(self):
        self.adapter.observe(self.observation(), "write")
        old = self.adapter._home
        self.adapter.end_session("s1", "end")
        self.adapter.reset_case("e", "v2", "reset2")
        self.adapter.begin_session("s1", "begin2")
        self.assertNotEqual(old, self.adapter._home)
        self.assertEqual(self.adapter.query(self.question(variant="v2"), "q2").text, "native:")
        self.adapter.end_session("s1", "end2")
        self.adapter.reset_case("e2", "v", "reset3")
        self.assertEqual(self.state()['observations'], [])

    def test_write_and_query_deduplication(self):
        obs = self.observation()
        first = self.adapter.observe(obs, "write")
        self.assertEqual(first, self.adapter.observe(obs, "write"))
        result = self.adapter.query(self.question(), "query")
        result.text = "changed copy"
        self.assertEqual(self.adapter.query(self.question(), "query").text, "native:fictional canary")
        calls = self.state()['calls']
        self.assertEqual(sum(c['method'] == 'observe' for c in calls), 1)
        self.assertEqual(sum(c['method'] == 'query' for c in calls), 1)
        with self.assertRaises(ContractError):
            self.adapter.observe(self.observation("changed"), "write")

    def test_unknown_blocks_query_and_does_not_repeat(self):
        obs = self.observation("async")
        receipt = self.adapter.observe(obs, "write")
        with self.assertRaises(ContractError):
            require_ready(receipt)
        self.assertEqual(self.adapter.observe(obs, "write").status, "unknown")
        with self.assertRaises(ContractError):
            self.adapter.query(self.question(), "query")
        self.assertEqual(len(self.state()['observations']), 1)

    def test_bad_json_or_failed_process_never_ready(self):
        for text in ("bad-json", "crash"):
            with self.subTest(text=text):
                with tempfile.TemporaryDirectory() as tmp:
                    a = NativeAdapter(self.transport, capabilities(), run_directory=Path(tmp) / "run")
                    try:
                        a.reset_case("e", "v", "r")
                        a.begin_session("s1", "b")
                        self.assertEqual(a.observe(self.observation(text), "w").status, "unknown")
                    finally:
                        a.close()

    def test_timeout_after_write_no_retry(self):
        obs = self.observation("slow")
        self.assertEqual(self.adapter.observe(obs, "write").status, "unknown")
        self.adapter.observe(obs, "write")
        self.assertEqual(len(self.state()['observations']), 1)

    def test_public_boundary_and_all_roles(self):
        for index, role in enumerate(("system", "user", "assistant", "tool")):
            obs = self.observation(role=role, observation_id=str(index))
            obs.gold = "PRIVATE_SENTINEL"
            self.adapter.observe(obs, "w" + str(index))
        sent = json.dumps(self.state())
        self.assertNotIn("PRIVATE_SENTINEL", sent)
        self.assertEqual([o['role'] for o in self.state()['observations']],
                         ['system', 'user', 'assistant', 'tool'])
        with self.assertRaises(ContractError):
            self.adapter.observe({"gold": "secret"}, "invalid")

    def test_scope_and_reset_rejected_before_send(self):
        count = len(self.state()['calls'])
        with self.assertRaises(ContractError):
            self.adapter.observe(self.observation(variant_id="other"), "w")
        with self.assertRaises(ContractError):
            self.adapter.reset_case("e", "v", "r2")
        self.assertEqual(len(self.state()['calls']), count)

    def test_duplicate_observation_id(self):
        self.adapter.observe(self.observation(), "write")
        with self.assertRaises(ContractError):
            self.adapter.observe(self.observation(), "write2")

    def test_shell_text_is_data_and_env_isolated(self):
        marker = self.root / 'injected'
        text = '$(touch ' + str(marker) + '); echo hello'
        with patch.dict(os.environ, {"SHOULD_NOT_INHERIT": "secret"}):
            self.adapter.observe(self.observation(text), "write")
        self.assertEqual(self.state()['observations'][0]['text'], text)
        self.assertFalse(marker.exists())
        from memobench.adapters_v2.transports import isolated_environment
        env = isolated_environment(self.adapter._home)
        self.assertNotIn("SHOULD_NOT_INHERIT", env)
        self.assertNotEqual(env['HOME'], os.environ.get('HOME'))

    def test_close_only_owned_data_and_reject_restart(self):
        outside = self.root / 'user-config'
        outside.write_text('keep')
        (self.adapter._home / 'linked').symlink_to(outside)
        home = self.adapter._home
        self.adapter.close()
        self.adapter.close()
        self.assertFalse(home.exists())
        self.assertEqual(outside.read_text(), 'keep')
        with self.assertRaises(ContractError):
            NativeAdapter(self.transport, capabilities(), run_directory=self.adapter.run_directory)

    def test_cleanup_failure_reported_without_retry(self):
        with patch.object(self.transport, 'request', side_effect=TransportError('http_error')) as call:
            with self.assertRaisesRegex(TransportError, 'cleanup_not_verified'):
                self.adapter.close()
            self.adapter.close()
            self.assertEqual(call.call_count, 1)
        self.assertEqual(self.adapter.cleanup_receipts[0].status, 'unknown')

    def test_query_timeout_and_failed_end_session(self):
        with patch.object(self.transport, 'request', side_effect=TransportError('timeout')) as call:
            result = self.adapter.query(self.question(), 'q-timeout')
            self.assertEqual(result.status, 'timeout')
            self.assertEqual(result, self.adapter.query(self.question(), 'q-timeout'))
            self.assertEqual(call.call_count, 1)
        with self.assertRaises(ContractError):
            self.adapter.end_session('s1', 'end')

    def test_end_session_must_wait_for_flush(self):
        with patch.object(self.transport, 'request', return_value={'operation_id': 'end', 'status': 'unknown'}):
            self.assertEqual(self.adapter.end_session('s1', 'end').status, 'unknown')
        with self.assertRaises(ContractError):
            self.adapter.begin_session('s2', 'begin2')

    def test_invalid_response_scope_and_evidence(self):
        for extra in ({'episode_id': 'wrong'}, {'retrieved_evidence': ['o']}):
            with self.subTest(extra=extra):
                response = dict(episode_id='e', variant_id='v', session_id='s1', probe_id='p',
                                status='ok', text='answer', answered_at=STAMP, **{})
                response.update(extra)
                with patch.object(self.transport, 'request', return_value=response):
                    result = self.adapter.query(self.question(), 'invalid')
                self.assertEqual(result.status, 'error')
                # 每个子例独立恢复测试对象的状态；不会重试外部操作。
                self.adapter._uncertain = False
                self.adapter._operations.clear()


class TransportTests(unittest.TestCase):
    def test_live_required(self):
        with self.assertRaises(TransportError):
            SubprocessTransport([sys.executable])
        with self.assertRaises(TransportError):
            HTTPTransport('https://example.invalid')

    def test_fixed_argv_and_endpoint_validation(self):
        for argv in ('echo hi', ['relative'], []):
            with self.assertRaises(ContractError):
                SubprocessTransport(argv, live=True)
        for endpoint in ('http://example.invalid', 'https://u:p@example.invalid',
                         'https://example.invalid?key=secret', 'file:///tmp/a'):
            with self.assertRaises(ContractError):
                HTTPTransport(endpoint, live=True)

    def test_http_fixture_no_socket(self):
        t = HTTPTransport('https://example.invalid/bridge', live=True, key_env='TEST_AGENT_KEY')
        with patch.object(t._opener, 'open', return_value=io.BytesIO(b'{"operation_id":"w","status":"ready"}')) as call:
            result = t.request('end_session', 'w', {'session_id': 's'}, Path('/tmp/case-fixture'))
        self.assertEqual(result['status'], 'ready')
        request = call.call_args.args[0]
        body = json.loads(request.data)
        self.assertEqual(body['namespace'], 'case-fixture')
        self.assertNotIn('test-secret', request.data.decode())
        self.assertEqual(request.get_header('Authorization'), 'Bearer test-secret')

    def test_http_error_no_retry_no_secret(self):
        t = HTTPTransport('https://example.invalid', live=True)
        failure = urllib.error.HTTPError(t.endpoint, 503, 'SECRET', {}, None)
        with patch.object(t._opener, 'open', side_effect=failure) as call:
            with self.assertRaisesRegex(TransportError, '^http_error$'):
                t.request('observe', 'w', {}, Path('/tmp/case'))
            self.assertEqual(call.call_count, 1)

    def test_strict_json(self):
        for raw in (b'{"a":1,"a":2}', b'{"a":NaN}', b'[]', b'bad'):
            with self.assertRaises(TransportError):
                decode_response(raw)

    def test_redirect_refused(self):
        from memobench.adapters_v2.transports import _NoRedirect
        self.assertIsNone(_NoRedirect().redirect_request(None, None, 302, '', {}, 'https://other.invalid'))

    def setUp(self):
        patcher = patch.dict(os.environ, {'TEST_AGENT_KEY': 'test-secret'})
        patcher.start()
        self.addCleanup(patcher.stop)


class ProbeTests(unittest.TestCase):
    def config(self):
        return json.loads(Path('configs/adapters/native.json').read_text())

    def test_no_live_executes_nothing(self):
        with patch('tools.probe_agents.run_process', side_effect=AssertionError('must not execute')):
            report = probe(self.config())
        self.assertEqual(report['status'], 'blocked')
        self.assertTrue(all(not a['commands'] for a in report['agents']))

    def test_missing_install_and_credentials_blocked(self):
        with patch('tools.probe_agents.shutil.which', return_value=None), patch.dict(os.environ, {}, clear=True):
            report = probe(self.config(), live=True)
        self.assertEqual(report['status'], 'blocked')
        for agent in report['agents']:
            self.assertFalse(agent['executable_found'])
            self.assertEqual(agent['missing_credentials'], ['DEEPSEEK_API_KEY'])
            self.assertEqual(agent['cross_session_memory'], 'NOT_VERIFIED')

    def test_version_help_success_not_lifecycle_pass(self):
        with patch('tools.probe_agents.shutil.which', return_value='/test/bin/agent'), \
             patch('tools.probe_agents.run_process', return_value=(0, b'fixture version', b'')) as run:
            report = probe(self.config(), live=True)
        self.assertEqual(run.call_count, 5)
        self.assertEqual(report['status'], 'blocked')
        self.assertTrue(all(a['review'] == 'pending_review' for a in report['agents']))

    def test_cli_exit_two_without_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run([sys.executable, 'tools/probe_agents.py', '--config',
                                     'configs/adapters/native.json', '--out', str(Path(tmp) / 'probe.json')],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn('blocked', result.stdout)


if __name__ == '__main__':
    unittest.main()
