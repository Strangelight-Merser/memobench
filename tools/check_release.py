#!/usr/bin/env python3
"""离线工程检查；--strict 额外要求正式发布缺口清零。不会修改数据或调用网络。"""
import argparse
import hashlib
import json
from pathlib import Path
import re

REQUIRED = (
    'README.md', 'CONTRIBUTING.md', 'SECURITY.md', 'CITATION.cff', 'LICENSE',
    '.github/workflows/ci.yml', 'packaging/control', 'packaging/README.md',
    'packaging/build_deb.py', 'packaging/memobench-v2',
    'tools/build_deb.sh', 'tools/check_release.py', 'tests/test_release_v2.py',
    'docs/作品介绍.md', 'docs/submission/CHECKLIST.md', 'docs/submission/VIDEO.md',
    'docs/submission/ROADSHOW.md', 'docs/submission/VALIDATION.md',
    'docs/submission/evidence-sha256.json', 'data/v0.2/manifest.json',
    'memobench/cli_v2.py', 'configs/experiments/offline.json',
)
CONTROLLED = ('README.md', 'CONTRIBUTING.md', 'SECURITY.md', 'CITATION.cff',
              '.github', 'packaging', 'configs', 'data/v0.2', 'artifacts',
              'docs/submission', 'docs/作品介绍.md')
SECRET_PATTERNS = (
    re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    re.compile(r'\b(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{30,}|AKIA[A-Z0-9]{16})\b'),
    re.compile(r'''(?i)["']?(?:api_key|access_token|password)["']?\s*[:=]\s*["'](?!\$|<|YOUR_|your_|pending|placeholder|test|fake|dummy)[A-Za-z0-9_+/=-]{16,}["']'''),
)
PLACEHOLDER = re.compile(r'【待补|\bTODO\b|\bTBD\b|PLACEHOLDER', re.I)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def confined(root, name):
    rel = Path(name)
    if rel.is_absolute() or '..' in rel.parts or not rel.parts:
        raise ValueError('unsafe inventory path')
    path = root / rel
    if any(p.is_symlink() for p in (path, *path.parents) if p != root.parent):
        raise ValueError('symlink inventory path')
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('unsafe inventory path')
    return path


def check(root):
    root = Path(root).resolve()
    errors, blockers = [], []
    for name in REQUIRED:
        if not (root / name).is_file():
            errors.append('missing: ' + name)
    try:
        manifest = json.loads((root / 'data/v0.2/manifest.json').read_text())
        if not manifest['files']:
            raise ValueError('empty data inventory')
        for name, expected in manifest['files'].items():
            if sha(confined(root / 'data/v0.2', name)) != expected:
                errors.append('data hash mismatch: ' + name)
        if manifest.get('status') != 'accepted':
            blockers.append('data pending_review: human signoff required')
        if manifest.get('license') in (None, '', 'pending_maintainer_signoff'):
            blockers.append('data license pending_maintainer_signoff')
        if not manifest.get('formal_test_n_query'):
            blockers.append('formal test set empty')
    except (OSError, ValueError, KeyError, TypeError):
        errors.append('invalid data manifest or inventory')
    try:
        inventory = json.loads((root / 'docs/submission/evidence-sha256.json').read_text())
        must = {'data/v0.2/manifest.json', 'docs/experiments/distract-6/summary.json',
                'docs/experiments/distract-6/results.jsonl', 'docs/experiments/distract-6/report.html'}
        if not must.issubset(inventory):
            errors.append('missing data/report evidence hashes')
        for name, expected in inventory.items():
            if not re.fullmatch('[0-9a-f]{64}', expected) or sha(confined(root, name)) != expected:
                errors.append('evidence hash mismatch: ' + name)
    except (OSError, ValueError, KeyError, TypeError):
        errors.append('invalid evidence inventory')
    scanned = set()
    for name in CONTROLLED:
        path = root / name
        paths = path.rglob('*') if path.is_dir() else [path]
        for item in paths:
            if not item.is_file() or item.is_symlink() or '__pycache__' in item.parts or item.suffix in ('.deb', '.pyc'):
                continue
            relative = item.relative_to(root).as_posix()
            if relative in scanned:
                continue
            scanned.add(relative)
            try:
                text = item.read_text(encoding='utf-8')
            except UnicodeDecodeError:
                continue
            if any(p.search(text) for p in SECRET_PATTERNS):
                errors.append('possible plaintext credential: ' + relative)
            # 草稿中的占位是诚实披露；结果文件中的占位是错误。
            if item.name in ('summary.json', 'results.jsonl', 'report.html') and PLACEHOLDER.search(text):
                errors.append('placeholder in result: ' + relative)
    # 当前交付仍未具备这些外部证据；不能从workflow或fixture推导PASS。
    blockers.extend([
        'native agents and openKylin NOT_VERIFIED',
        'LLM results and judge calibration pending',
        'remote CI logs and clean-clone/anonymous access not verified',
        'final PDF/video and submission consistency require human review',
    ])
    return {'offline_checks': 'failed' if errors else 'passed',
            'release_status': 'blocked' if errors or blockers else 'ready',
            'errors': errors, 'blockers': blockers, 'scanned_files': len(scanned),
            'scan_scope': 'controlled working-tree files only; not git history or proof of no secrets'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default='.')
    parser.add_argument('--strict', action='store_true', help='正式发布阻塞项也返回非零')
    args = parser.parse_args(argv)
    result = check(args.root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result['errors'] else (2 if args.strict and result['blockers'] else 0)


if __name__ == '__main__':
    raise SystemExit(main())
