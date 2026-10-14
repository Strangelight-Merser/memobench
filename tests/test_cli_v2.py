from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from memobench.cli_v2 import main
from memobench import runner_v2 as runner
from test_runner_v2 import episode


class CLITests(unittest.TestCase):
    def invoke(self, args):
        stream = io.StringIO()
        with redirect_stdout(stream):
            code = main(args)
        return code, json.loads(stream.getvalue())

    def test_validate_current_candidates(self):
        code, result = self.invoke(['validate', '--dataset', 'data/v0.2'])
        self.assertEqual(code, 0)
        self.assertEqual(result['formal_test_n_query'], 0)
        self.assertEqual(result['release_status'], 'pending_review')

    def test_run_report_and_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = str(Path(tmp) / 'run')
            args = ['run', '--config', 'configs/experiments/offline.json', '--out', out]
            with patch.object(runner, 'load_dataset', return_value=[episode()]):
                code, result = self.invoke(args)
                self.assertEqual(code, 0)
                self.assertEqual(result['data_notice'], '候选数据，未签收')
                self.assertTrue((Path(out) / 'manifest.json').is_file())
                self.assertEqual(self.invoke(args)[0], 2)
                self.assertEqual(self.invoke(args + ['--resume'])[0], 0)
            html = Path(tmp) / 'another.html'
            self.assertEqual(self.invoke(['report', '--run', out, '--out', str(html)])[0], 0)
            self.assertIn('候选数据，未签收', html.read_text())

    def test_native_blocked_even_with_live_no_transport(self):
        for live in ([], ['--live']):
            with tempfile.TemporaryDirectory() as tmp, patch('memobench.adapters_v2.SubprocessTransport', side_effect=AssertionError('must not start')):
                code, result = self.invoke(['run', '--config', 'configs/experiments/native.json', '--out', tmp] + live)
                self.assertEqual(code, 2)
                self.assertEqual(result['status'], 'blocked')
                self.assertEqual(result['n_case'], 0)

    def test_empty_calibration_is_not_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / 'empty.jsonl'
            empty.write_text('')
            code, result = self.invoke(['calibrate', '--annotations', str(empty), '--judgments', str(empty), '--out', str(Path(tmp) / 'calibration.json')])
            self.assertEqual(code, 0)
            self.assertFalse(result['publish_judge_ranking'])
            self.assertIsNone(result['metrics']['cohen_kappa'])

    def test_invalid_config_no_secret_echo(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / 'config.json'
            config.write_text('{"api_key":"SECRET"}')
            code, result = self.invoke(['run', '--config', str(config), '--out', str(Path(tmp) / 'out')])
            self.assertEqual(code, 2)
            self.assertNotIn('SECRET', str(result))

    def test_matrix_help(self):
        result = subprocess.run([sys.executable, 'tools/run_matrix.py', '--help'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn('--configs', result.stdout)


if __name__ == '__main__':
    unittest.main()
