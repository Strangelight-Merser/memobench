#!/usr/bin/env python3
"""离线工程检查；--strict 额外要求正式发布缺口清零。不会修改数据或调用网络。"""
import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path
import re
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REQUIRED = (
    'README.md', 'CONTRIBUTING.md', 'SECURITY.md', 'CITATION.cff', 'LICENSE',
    '.github/workflows/ci.yml', 'packaging/control', 'packaging/README.md',
    'packaging/build_deb.py', 'packaging/memobench-v2',
    'tools/build_deb.sh', 'tools/check_release.py', 'tests/test_release_v2.py',
    'docs/作品介绍.md', 'docs/submission/CHECKLIST.md', 'docs/submission/VIDEO.md',
    'docs/submission/ROADSHOW.md', 'docs/submission/VALIDATION.md',
    'docs/submission/evidence-sha256.json', 'data/v0.2/manifest.json',
    'memobench/cli_v2.py', 'configs/experiments/offline.json',
    'configs/experiments/native.json',
)
CONTROLLED = ('README.md', 'CONTRIBUTING.md', 'SECURITY.md', 'CITATION.cff',
              '.github', 'packaging', 'configs', 'data/v0.2', 'artifacts',
              'docs/submission', 'docs/作品介绍.md', 'memobench', 'tools', 'patches',
              'data/v0.2-ai-reviewed', 'docs/integrations', 'docs/delivery')
SECRET_PATTERNS = (
    re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    re.compile(r'\b(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{30,}|AKIA[A-Z0-9]{16})\b'),
    re.compile(r'''(?i)["']?(?:api_key|access_token|password)["']?\s*[:=]\s*["'](?!\$|<|YOUR_|your_|pending|placeholder|test|fake|dummy|synthetic-unused-no-api(?=["']))[A-Za-z0-9_+/=-]{16,}["']'''),
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


NATIVE_EVIDENCE = 'docs/integrations/phase-protocol-20261015'
NATIVE_REVIEWER_SHA256 = '2aa1ad634b640b692967e8d6e307563e8d6513ca201fab81c6d07142d130f16e'


def verify_probe(bundle, product):
    """Recompute lifecycle, isolation and answers from the current archived probe."""
    from tools.probe_native_vm import operation_evidence, inspect_export, acceptance_passed
    report = json.loads(confined(bundle, 'probe.json').read_text())
    if report['product'] != product or report.get('execution') != 'online':
        raise ValueError('probe identity mismatch')
    checked = dict(report, checks={'cleanup': True})
    operations = set()
    exports = report['exports']
    receipts = report['cleanup_receipts']
    if (not exports or len(receipts) != len(exports) or any(r['status'] != 'ready' for r in receipts)
            or len({e['namespace'] for e in exports}) != len(exports)
            or set(report['namespaces']) != {e['namespace'] for e in exports}):
        raise ValueError('probe cleanup missing')
    for entry in exports:
        path = confined(bundle, entry['path'])
        if sha(path) != entry['sha256']:
            raise ValueError('probe export hash mismatch')
        raw = json.loads(path.read_text())
        control = raw['control.json']
        closes = [(key, op) for key, op in control['operations'].items() if op['method'] == 'close']
        if (control.get('closed') is not True or control['product'] != product or len(closes) != 1
                or closes[0][1]['status'] != 'completed'
                or closes[0][0] not in {r['operation_id'] for r in receipts}):
            raise ValueError('probe namespace incomplete')
        operation_evidence(raw, entry['namespace'], closes[0][0], None, 'close', report['bridge_sha256'])
        resets = [(key, op) for key, op in control['operations'].items() if op['method'] == 'reset_case']
        if len(resets) != 1:
            raise ValueError('probe reset missing')
        key, _ = resets[0]
        reset = operation_evidence(raw, entry['namespace'], key, None, 'reset_case', report['bridge_sha256'])
        event = next(e for e in report['events'] if e['method'] == 'reset_case' and e['receipt']['operation_id'] == key)
        if ((event['episode_id'], event['variant_id']) != (control['episode_id'], control['variant_id'])
                or reset.get('mount_isolation') != 'passed'
                or reset.get('private_sentinel_present_outside') is not True
                or reset.get('private_sentinel_visible_inside') is not False):
            raise ValueError('probe isolation mismatch')
        for event in report['events']:
            if event['method'] != 'query' or event['operation_id'] not in control['operations']:
                continue
            public = event['input']
            turn = operation_evidence(raw, entry['namespace'], event['operation_id'], public['session_id'], 'query', report['bridge_sha256'])
            prediction = event['prediction']
            if prediction['status'] != 'ok' or prediction['text'] != turn['answer']:
                raise ValueError('probe answer mismatch')
            answer = prediction['text'].strip()
            key = public['probe_id']
            if key == 'q1': checked['checks']['same_session'] = answer == report['canary']
            elif key == 'q2': checked['checks']['cross_session'] = answer == report['canary']
            elif key == 'q4':
                checked['checks']['cross_case_no_canary'] = report['canary'] not in answer
                checked['checks']['cross_case_unknown'] = answer == '不知道'
            elif key == 'profile-q1': checked['checks']['profile_cross_session'] = answer == report['profile_canary']
        checked, resolved = inspect_export(checked, raw, entry['namespace'], report['canary'], report.get('profile_canary'), report['bridge_sha256'])
        operations.update(resolved)
    expected = {e.get('operation_id') or e.get('receipt', {}).get('operation_id') for e in report['events'] if e['method'] in ('observe', 'query', 'end_session')}
    if operations != expected or not acceptance_passed(checked):
        raise ValueError('probe raw verification failed')
    return {'status': 'passed', 'bridge_sha256': report['bridge_sha256'], 'probe_sha256': sha(bundle/'probe.json'), 'exports_verified': len(exports)}


def native_cli_acceptance(root):
    """Verify fixed historical CLI scope; this is not semantic benchmark release."""
    base = confined(root, NATIVE_EVIDENCE)
    reviewer = confined(base, 'review_complete_run.py')
    if sha(reviewer) != NATIVE_REVIEWER_SHA256:
        raise ValueError('native verifier source mismatch')
    products = {}
    for product, run_name, primary_name, bridge_name in (
        ('kylin', 'cli-final', 'PRIMARY_KYLIN_COMPLETE_RUN_REVIEW.json', NATIVE_EVIDENCE+'/cli-final/bridge-source.py'),
        ('openclaw', 'cli-openclaw-direct-schema', 'PRIMARY_OPENCLAW_COMPLETE_RUN_REVIEW.json', 'docs/delivery/verified-native-bridge.py')):
        run = confined(base, run_name)
        primary_path = confined(base, primary_name)
        primary = json.loads(primary_path.read_text())
        record = primary['products'][product]
        case, = (run/('run-'+product)/'cases').glob('*.json')
        raw, = (run/('raw-'+product)).glob('*.json')
        if sha(confined(root, case.relative_to(root))) != record['case_sha256'] or sha(confined(root, raw.relative_to(root))) != record['raw_sha256']:
            raise ValueError('native case/raw hash mismatch')
        source = confined(root, bridge_name)
        if sha(source) != primary['bridge_sha256']:
            raise ValueError('native verified bridge mismatch')
        proc = subprocess.run([sys.executable, str(reviewer), '--run-root', str(run), '--bridge-source', str(source), '--product', product],
                              cwd=root, env=dict(os.environ, PYTHONPATH=str(root)), capture_output=True, text=True, timeout=45)
        if proc.returncode or json.loads(proc.stdout) != primary:
            raise ValueError('native complete case recomputation failed')
        probe = verify_probe(confined(base, 'direct-tools-revision/probe-'+product), product)
        verified_source = confined(root, 'docs/delivery/verified-native-bridge.py')
        if probe['bridge_sha256'] != sha(verified_source):
            raise ValueError('native current probe source mismatch')
        products[product] = {'status': 'selected_complete_task_passed', 'observations_verified': record['observations_verified'],
                             'raw_sha256': record['raw_sha256'], 'case_sha256': record['case_sha256'],
                             'primary_sha256': sha(primary_path), 'run_bridge_sha256': primary['bridge_sha256'], 'probe': probe,
                             'original_scoring_status': record['original_scoring_status']}
    current = sha(confined(root, 'tools/native_vm_product.py'))
    verified = sha(confined(root, 'docs/delivery/verified-native-bridge.py'))
    return {'status': 'historical_native_cli_passed', 'scope': 'two products, one selected complete file task each; no benchmark ranking',
            'products': products, 'current_bridge_sha256': current, 'verified_bridge_sha256': verified,
            'current_bridge_online_hash_match': current == verified,
            'current_source_online_status': 'matches_verified_probe_bytes' if current == verified else 'not_inferred_from_historical_runs; portability revision is offline-only'}


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
        from memobench.data_v2 import validate_release
        data_validation = validate_release(root / 'data/v0.2')
        if data_validation['release_status'] != 'accepted':
            blockers.append('public data pending_review: original dataset public release is unapproved; internal AI-reviewed use is separate')
        if data_validation['license_status'] != 'accepted':
            blockers.append('public data license pending_maintainer_signoff; internal use grants no redistribution license')
        if not manifest.get('formal_test_n_query'):
            blockers.append('original public dataset formal test set empty; approved internal set is separate')
    except (OSError, ValueError, KeyError, TypeError):
        errors.append('invalid data manifest or inventory')
    default_native = None
    try:
        recipe = json.loads(confined(root, 'configs/experiments/native.json').read_text())
        if recipe['schema_version'] != 'native-run-recipe-1' or recipe['split'] != 'test':
            raise ValueError('invalid native recipe')
        dataset = confined(root, recipe['dataset'])
        from memobench.data_v2 import validate_release
        default_native = validate_release(dataset)
        approved = default_native['release_status'] == 'accepted' or (default_native['release_status'] == 'accepted_internal' and recipe['purpose'] == 'internal_evaluation' and default_native.get('usage_scope') == 'internal_evaluation_only')
        if not approved or not default_native.get('formal_test_n_query'):
            blockers.append('default native dataset is not approved for its declared purpose')
    except (OSError, ValueError, KeyError, TypeError):
        errors.append('invalid or missing default native recipe dataset')
    try:
        native = native_cli_acceptance(root)
    except (OSError, ValueError, KeyError, TypeError, StopIteration, subprocess.TimeoutExpired):
        native = {'status': 'not_verified', 'scope': 'selected complete CLI tasks'}
        errors.append('native CLI acceptance evidence invalid or missing')
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
        'semantic LLM scoring and judge calibration pending; selected native file-task acceptance is separate',
        'remote CI logs and anonymous remote access not verified',
        'openKylin desktop recording, final PDF/video and submission consistency pending',
    ])
    return {'offline_checks': 'failed' if errors else 'passed',
            'release_status': 'blocked' if errors or blockers else 'ready',
            'native_cli_acceptance': native, 'default_native_dataset': default_native,
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
