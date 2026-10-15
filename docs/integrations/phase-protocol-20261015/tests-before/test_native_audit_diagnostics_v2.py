"""Offline synthetic diagnostics; no native CLI, provider, or original fixture."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tools import native_vm_product as bridge


class NativeAuditDiagnosticsTests(unittest.TestCase):
    def checkpoint(self):
        return {'binding': {}, 'baseline': {}, 'transcript': bridge.transcript_checkpoint([])}

    def test_failed_audit_keeps_records_and_fixed_reason(self):
        records = [{'source': 'synthetic', 'position': 1, 'session_id': 's',
                    'message': {'role': 'assistant', 'content': [{'type': 'toolCall',
                        'id': 'r', 'name': 'write', 'arguments': {'path': 'missing.txt'}}]}},
                   {'source': 'synthetic', 'position': 2, 'session_id': 's',
                    'message': {'role': 'toolResult', 'toolCallId': 'r', 'isError': True,
                                'content': [{'type': 'text', 'text': 'synthetic failure'}]}}]
        with patch.object(bridge, 'workspace_snapshot', return_value={}), \
             patch.object(bridge, 'native_records', return_value=records):
            result = bridge.query_artifacts(Path('/synthetic'), 'openclaw', self.checkpoint(), {'ok': True}, 's')
        self.assertEqual(result['native_records'], records)
        self.assertEqual(result['audit_stage'], 'native_file_audit')
        self.assertEqual(result['audit_error_reason_code'], 'native_file_tool_failed')
        self.assertFalse(result['complete'])
        self.assertIsNone(result['audit'])

    def test_unknown_errors_do_not_export_messages(self):
        for error in (ValueError('SECRET/path/content'), RuntimeError('SECRET/path/content')):
            with self.subTest(error=type(error).__name__), \
                 patch.object(bridge, 'workspace_snapshot', return_value={}), \
                 patch.object(bridge, 'native_records', side_effect=error):
                result = bridge.query_artifacts(Path('/synthetic'), 'openclaw', self.checkpoint(), {'ok': True}, 's')
            self.assertEqual(result['audit_stage'], 'native_records')
            self.assertEqual(result['audit_error_reason_code'], 'unexpected_audit_error')
            self.assertNotIn('SECRET', json.dumps(result))
            self.assertFalse(result['complete'])

    def test_query_prediction_survives_audit_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            namespace = 'a' * 32
            root = base / 'cases' / namespace
            home = root / 'home'
            home.mkdir(parents=True)
            checkpoint = self.checkpoint()
            control = {'product': 'openclaw', 'episode_id': 'e', 'variant_id': 'v',
                       'session': 's', 'sessions': {'s': {'product_session': 'native-s'}},
                       'operations': {}, 'uncertain': False, 'bridge_sha256': 'synthetic',
                       'artifact_checkpoints': {'q': checkpoint}}
            bridge.save(root / 'control.json', control)
            bridge.save(base / 'provider.json', {})
            request = {'bridge_sha256': bridge.hashlib.sha256(Path(bridge.__file__).read_bytes()).hexdigest(),
                       'namespace': namespace, 'method': 'query', 'operation_id': 'q',
                       'payload': {'episode_id': 'e', 'variant_id': 'v', 'session_id': 's',
                                   'probe_id': 'p', 'query': 'synthetic'}}
            with patch.object(bridge, 'BASE', base), \
                 patch.object(bridge, 'workspace_snapshot', return_value={}), \
                 patch.object(bridge, 'native_records', return_value=[]), \
                 patch.object(bridge, 'inventory', return_value={}), \
                 patch.object(bridge, 'invoke', return_value={'ok': True, 'answer': 'native prediction'}), \
                 patch.object(bridge, 'native_file_audit', side_effect=ValueError('native tool result missing')):
                response = bridge.dispatch(request, 'openclaw')
            self.assertEqual(response['status'], 'ok')
            self.assertEqual(response['text'], 'native prediction')
            saved = json.loads((root / (bridge.hashlib.sha256(b'q').hexdigest() + '.json')).read_text())
            self.assertEqual(saved['answer'], 'native prediction')
            self.assertEqual(saved['artifacts']['native_records'], [])
            self.assertFalse(saved['artifacts']['complete'])
            self.assertEqual(saved['artifacts']['audit_error_reason_code'], 'native_tool_result_missing')


    def audit(self, name, path, content, failed=False):
        return bridge.native_file_audit(self.rows(name, path, content, failed),
                                       bridge.transcript_checkpoint([]), 's')

    def rows(self, name, path, content, failed=False, call_id='c', start=1):
        return [{'source': 'synthetic', 'position': start, 'session_id': 's',
                 'message': {'role': 'assistant', 'content': [{'type': 'toolCall',
                     'id': call_id, 'name': name, 'arguments': {'path': path}}]}},
                {'source': 'synthetic', 'position': start + 1, 'session_id': 's',
                 'message': {'role': 'toolResult', 'toolCallId': call_id,
                             'isError': failed, 'content': content}}]

    def test_plain_text_and_json_scalar_reads(self):
        for name in ('read', 'read_file'):
            for content in ('READY\n', '"READY"', '7', 'true', 'null', '[]'):
                with self.subTest(name=name, content=content):
                    result = self.audit(name, 'ready.txt', content)
                    self.assertTrue(result['complete'])
                    self.assertTrue(result['events'][0]['succeeded'])
                    self.assertEqual(result['events'][0]['native_result']['message']['content'], content)

    def test_failed_root_read_and_successful_write_are_audited(self):
        rows = self.rows('read', bridge.GUEST + '/workspace', 'EISDIR', True)
        rows += self.rows('write', 'markers/ready.txt', '{"ok":true}', call_id='w', start=3)
        result = bridge.native_file_audit(rows, bridge.transcript_checkpoint([]), 's')
        self.assertTrue(result['complete'])
        read, write = result['events']
        self.assertEqual((read['operation'], read['path'], read['succeeded']), ('read', '.', False))
        self.assertEqual(read['arguments']['path'], bridge.GUEST + '/workspace')
        self.assertEqual((write['operation'], write['succeeded']), ('write', True))

    def test_failed_and_outside_writes_stay_rejected(self):
        with self.assertRaisesRegex(ValueError, 'native file tool failed'):
            self.audit('write', 'ready.txt', '{"error":"failed"}', True)
        for path in (bridge.GUEST + '/workspace', '/outside.txt', '../outside.txt'):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'outside workspace'):
                self.audit('write', path, '{"ok":true}')

    def test_transcript_integrity_checks_stay_rejected(self):
        rows = self.rows('read', 'ready.txt', 'READY')
        cp = bridge.transcript_checkpoint([])
        for bad in (rows[:1], rows + [rows[1]], rows + [rows[0]], list(reversed(rows))):
            with self.subTest(rows=bad), self.assertRaises(ValueError):
                bridge.native_file_audit(bad, cp, 's')
        with self.assertRaisesRegex(ValueError, 'replaced or truncated'):
            bridge.native_file_audit(rows, bridge.transcript_checkpoint([{'prior': 'synthetic'}]), 's')

if __name__ == '__main__':
    unittest.main()
