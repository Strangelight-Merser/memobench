"""交付完整性、拒绝伪结果、凭据扫描与deb真实归档测试；全部离线。"""
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


release = load('check_release_v2', 'tools/check_release.py')
builder = load('build_deb_v2', 'packaging/build_deb.py')


class ReleaseTests(unittest.TestCase):
    def test_worktree_checks_and_honest_blockers(self):
        result = release.check(ROOT)
        self.assertEqual(result['errors'], [])
        self.assertEqual(result['release_status'], 'blocked')
        self.assertTrue(any('pending_review' in x for x in result['blockers']))

    def test_missing_and_tampered_hashes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'data/v0.2').mkdir(parents=True)
            (root / 'data/v0.2/x').write_text('changed')
            (root / 'data/v0.2/manifest.json').write_text(json.dumps({'files': {'x': '0' * 64}}))
            result = release.check(root)
            self.assertTrue(any('missing:' in x for x in result['errors']))
            self.assertIn('data hash mismatch: x', result['errors'])

    def test_unsafe_inventory_path(self):
        with tempfile.TemporaryDirectory() as folder:
            for path in ('../secret', '/etc/passwd'):
                with self.assertRaises(ValueError):
                    release.confined(Path(folder), path)

    def test_result_placeholder_and_secret_are_errors_without_echo(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'artifacts').mkdir()
            (root / 'artifacts/summary.json').write_text('{"result":"【待补：真实结果】"}')
            secret = 'sk-' + 'Q' * 32
            (root / 'artifacts/token.txt').write_text(secret)
            result = release.check(root)
            self.assertIn('placeholder in result: artifacts/summary.json', result['errors'])
            self.assertIn('possible plaintext credential: artifacts/token.txt', result['errors'])
            self.assertNotIn(secret, json.dumps(result))

    def test_deb_archive_control_payload_and_cli(self):
        with tempfile.TemporaryDirectory() as folder:
            output = builder.build(ROOT, Path(folder) / 'candidate.deb')
            raw = output.read_bytes()
            self.assertTrue(raw.startswith(b'!<arch>\n'))
            pos, members = 8, {}
            while pos < len(raw):
                header = raw[pos:pos + 60]
                self.assertEqual(header[-2:], b'`\n')
                size = int(header[48:58])
                name = header[:16].decode().strip().rstrip('/')
                members[name] = raw[pos + 60:pos + 60 + size]
                pos += 60 + size + size % 2
            self.assertEqual(members['debian-binary'], b'2.0\n')
            with tarfile.open(fileobj=io.BytesIO(members['control.tar.gz'])) as tar:
                control = tar.extractfile('./control').read().decode()
                self.assertIn('Architecture: all', control)
                self.assertIn('Depends: python3 (>= 3.9)', control)
                self.assertEqual(tar.getnames(), ['./control'])
            with tarfile.open(fileobj=io.BytesIO(members['data.tar.gz'])) as tar:
                names = tar.getnames()
                self.assertIn('usr/share/memobench/memobench/cli_v2.py', names)
                self.assertFalse(any('/data/' in n or '/home/' in n or 'systemd' in n for n in names))
                entry = tar.extractfile('usr/bin/memobench-v2').read().decode()
                self.assertIn('from memobench.cli_v2 import main', entry)
                self.assertEqual(tar.getmember('usr/bin/memobench-v2').mode, 0o755)
                # 仅提取明确受控普通文件，不依赖宿主dpkg或root安装。
                for member in tar.getmembers():
                    self.assertTrue(member.isfile())
                    path = Path(folder) / member.name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(tar.extractfile(member).read())
            package_root = Path(folder) / 'usr/share/memobench'
            entry = entry.replace("'/usr/share/memobench'", repr(str(package_root)))
            script = Path(folder) / 'entry.py'
            script.write_text(entry)
            proc = subprocess.run([sys.executable, str(script), '--help'], cwd=folder,
                                  capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn('validate', proc.stdout)

    def test_ci_has_no_live_secrets_or_privileged_pr(self):
        text = (ROOT / '.github/workflows/ci.yml').read_text()
        for forbidden in ('secrets.', 'pull_request_target', 'self-hosted', '--live', '--reader llm'):
            self.assertNotIn(forbidden, text)
        self.assertIn('persist-credentials: false', text)
        self.assertIn('actions/upload-artifact', text)


if __name__ == '__main__':
    unittest.main()
