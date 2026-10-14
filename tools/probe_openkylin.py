#!/usr/bin/env python3
"""离线、只读环境诊断；不安装软件，不访问模型服务。"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import shlex
import shutil
import subprocess
import sys


def command(argv):
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=10,
                                stdin=subprocess.DEVNULL, shell=False)
        return {'status': 'observed' if result.returncode == 0 else 'error',
                'returncode': result.returncode, 'stdout': result.stdout.strip(),
                'stderr': result.stderr.strip()}
    except FileNotFoundError:
        return {'status': 'blocked', 'reason': 'executable_not_found', 'returncode': None}
    except subprocess.TimeoutExpired:
        return {'status': 'blocked', 'reason': 'timeout', 'returncode': None}
    except (OSError, UnicodeError):
        return {'status': 'blocked', 'reason': 'probe_failed', 'returncode': None}


def parse_os_release(text):
    values = {}
    for line in text.splitlines():
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        try:
            words = shlex.split(value, comments=True)
        except ValueError:
            continue
        if len(words) == 1:
            values[key] = words[0]
    return values


def collect(tools=()):
    try:
        raw = Path('/etc/os-release').read_text(encoding='utf-8')
        release = {'status': 'observed', 'raw': raw, 'fields': parse_os_release(raw)}
    except (OSError, UnicodeError):
        release = {'status': 'NOT_VERIFIED', 'raw': None, 'fields': {}}
    system = platform.system()
    detected = system == 'Linux' and release['fields'].get('ID', '').lower() == 'openkylin'
    versions = {}
    for tool in tools:
        executable = shutil.which(tool)
        versions[tool] = command([executable, '--version']) if executable else {
            'status': 'blocked', 'reason': 'executable_not_found', 'returncode': None}
    return {
        'recorded_at': datetime.now(timezone.utc).isoformat(),
        'status': 'detected' if detected else 'NOT_VERIFIED',
        'openkylin_detected': detected,
        'acceptance': 'NOT_VERIFIED',
        'reason': 'requires_real_agent_and_manual_acceptance' if detected else 'not_openkylin',
        'execution_host': {
            'os_release': release, 'uname': dict(platform.uname()._asdict()),
            'python': {'version': platform.python_version(), 'executable': sys.executable},
            'dpkg_architecture': command(['dpkg', '--print-architecture']),
            'tools': versions, 'tool_versions_status': 'observed' if versions else 'NOT_VERIFIED'},
        'model_service_host': {'status': 'NOT_VERIFIED', 'reason': 'not_probed', 'host': None},
        'permission_isolation': {'status': 'NOT_VERIFIED'},
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True)
    parser.add_argument('--tool', action='append', default=[],
                        help='已确认的工具可执行文件，仅读取 --version，可重复')
    args = parser.parse_args(argv)
    result = collect(args.tool)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('openKylin: ' + result['status'] + '; acceptance: NOT_VERIFIED')
    # 0仅表示诊断文件生成成功，不代表平台签收。
    return 0


if __name__ == '__main__':
    sys.exit(main())
