#!/usr/bin/env python3
"""Small live integration acceptance, never a benchmark or ranking."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from memobench.adapters_v2 import NativeAdapter
from memobench.adapters_v2.ssh_vm import SSHVMTransport
from memobench.protocol_v2 import require_ready
from memobench.schema_v2 import AdapterCapabilities, Observation, Probe


def now():
    return datetime.now(timezone.utc).isoformat()


def operation_evidence(export, namespace, operation_id, session_id, method, bridge_sha256):
    """Resolve one completed operation; arbitrary export entries never count."""
    control = export['control.json']
    if control['bridge_sha256'] != bridge_sha256:
        raise ValueError('bridge version mismatch')
    operation = control['operations'][operation_id]
    if (operation['status'] != 'completed' or operation['method'] != method
            or operation.get('session_id') != session_id):
        raise ValueError('operation mismatch or incomplete')
    evidence = export[operation['evidence']]
    expected = {'namespace': namespace, 'operation_id': operation_id,
                'session_id': session_id, 'method': method, 'bridge_sha256': bridge_sha256}
    if evidence.get('binding') != expected:
        raise ValueError('evidence binding mismatch')
    return evidence


def acceptance_passed(report):
    required = {'same_session', 'cross_session', 'cross_case_no_canary',
                'cross_case_unknown', 'file_task', 'cleanup'}
    if report['product'] == 'kylin':
        required |= {'profile_cross_session', 'profile_persisted',
                     'profile_prompt_injected', 'profile_turns_completed'}
    return (not report.get('error') and not report.get('evidence_export_error')
            and set(report['checks']) == required
            and all(report['checks'][key] is True for key in required))


def inspect_export(report, evidence, namespace, code, nickname, bridge_hash):
    """Pure offline check of one namespace export against locally recorded events."""
    import copy
    report = copy.deepcopy(report)
    exported_operations = set()
    try:
        control = evidence['control.json']
        resolved = []
        for operation_id, operation in control['operations'].items():
            if operation['method'] in ('observe', 'query', 'end_session'):
                event = next(event for event in report['events']
                    if (event.get('operation_id') or event.get('receipt', {}).get('operation_id')) == operation_id)
                public = event.get('input', event)
                event_session = public.get('session_id')
                if (control['episode_id'], control['variant_id']) != (public.get('episode_id'), public.get('variant_id')):
                    raise ValueError('event case mismatch')
                item = operation_evidence(evidence, namespace, operation_id,
                    event_session, event['method'], bridge_hash)
                if event_session != operation.get('session_id'):
                    raise ValueError('event session mismatch')
                exported_operations.add(operation_id)
                resolved.append((operation, item))
        expected = hashlib.sha256((code + '\n').encode()).hexdigest()
        for operation, item in resolved:
            sid = operation.get('session_id')
            if control['episode_id'] == 'memory' and sid == 's1' and operation['method'] == 'end_session':
                report['file_baseline_absent'] = 'workspace/notes/code.txt' not in item.get('files', {})
            if control['episode_id'] == 'memory' and sid == 's2' and operation['method'] == 'query':
                matching = next(event for event in report['events'] if event.get('operation_id') == item['binding']['operation_id'])
                if matching['input']['probe_id'] == 'q3':
                    report['checks']['file_task'] = ('workspace/notes/code.txt' not in item.get('files_before', {}) and
                        'files_before' in item and item.get('files_after', {}).get('workspace/notes/code.txt') == expected)
            if control['episode_id'] == 'profile' and sid == 'p1' and operation['method'] == 'end_session':
                entry = item.get('profile', {}).get('entries', {}).get('basic.preferred_name', {})
                report['checks']['profile_persisted'] = entry.get('value') == nickname
            if control['episode_id'] == 'profile' and sid == 'p2' and operation['method'] == 'query':
                report['checks']['profile_prompt_injected'] = nickname in (item.get('native_profile_prompt') or '')
        if report['product'] == 'kylin':
            turns = [item for operation, item in resolved if operation['method'] in ('observe', 'query')]
            report['checks']['profile_turns_completed'] = (report['checks'].get('profile_turns_completed', True)
                and bool(turns) and all(item.get('profile_completed') is True for item in turns))
    except (KeyError, ValueError, TypeError, StopIteration):
        report['evidence_export_error'] = True
    return report, exported_operations


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--ssh-config', required=True)
    p.add_argument('--product', choices=['kylin', 'openclaw'], required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--live', action='store_true')
    args = p.parse_args()
    if not args.live:
        p.error('--live required; this invokes the configured model API')
    args.out.mkdir(parents=True, exist_ok=False)
    transport = SSHVMTransport(args.ssh_config, args.product, live=True)
    caps = AdapterCapabilities(native_answer='supported', retrieved_evidence='unsupported',
                               write_usage='unsupported', flush='unsupported', restart='unsupported',
                               storage_inspection='supported')
    adapter = NativeAdapter(transport, caps)
    code = 'MB-' + uuid4().hex[:12].upper()
    report = {'product': args.product, 'started_at': now(), 'scope': 'synthetic integration acceptance only',
              'bridge_sha256': hashlib.sha256((Path(__file__).parent / 'native_vm_product.py').read_bytes()).hexdigest(),
              'config_sha256': hashlib.sha256(Path(args.ssh_config).read_bytes()).hexdigest(),
              'capabilities': caps.to_dict(), 'canary': code, 'events': [], 'checks': {}, 'exports': [],
              'publish_ranking': False, 'execution': 'online', 'model': 'deepseek-flash',
              'openclaw_mode': 'embedded_explicit; optional Gateway flush unsupported'}
    def persist():
        (args.out / 'probe.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    current_case = {}
    def write(method, *values):
        if method == 'reset_case':
            current_case.update(episode_id=values[0], variant_id=values[1])
        receipt = getattr(adapter, method)(*values, uuid4().hex)
        report['events'].append({'method': method, 'receipt': receipt.to_dict(),
            'episode_id': current_case.get('episode_id'), 'variant_id': current_case.get('variant_id'),
            'session_id': values[0].session_id if method == 'observe' else values[0] if method in ('begin_session', 'end_session') else None})
        persist()
        require_ready(receipt)
    def query(episode, session, probe_id, text):
        value = Probe(episode, 'v1', session, probe_id, text, now())
        operation_id = uuid4().hex
        result = adapter.query(value, operation_id)
        report['events'].append({'method': 'query', 'operation_id': operation_id, 'input': value.to_public(), 'prediction': result.to_dict()})
        persist()
        if result.status != 'ok':
            raise RuntimeError('native query failed')
        return result.text
    nickname = '青竹' + uuid4().hex[:6].upper()
    report['profile_canary'] = nickname if args.product == 'kylin' else None
    try:
        write('reset_case', 'memory', 'v1')
        write('begin_session', 's1')
        value = Observation('memory', 'v1', 's1', 'o1', 'user',
                            '请记住：我的虚构测试项目“蓝帆”的代号是 ' + code + '。后面的新会话会询问，请保存到你的长期记忆。', now())
        report['events'].append({'method': 'public_observation', 'input': value.to_public()})
        write('observe', value)
        answer = query('memory', 's1', 'q1', '蓝帆项目的代号是什么？只回答代号；不知道就回答不知道。')
        report['checks']['same_session'] = answer.strip() == code
        write('end_session', 's1')
        write('begin_session', 's2')
        answer = query('memory', 's2', 'q2', '我以前告诉过你的蓝帆项目代号是什么？只回答代号；不知道就回答不知道。')
        report['checks']['cross_session'] = answer.strip() == code
        query('memory', 's2', 'q3', '请把蓝帆项目代号写到当前工作目录的 notes/code.txt，文件只含代号和一个换行。如果不知道就不要写。')
        write('end_session', 's2')
        write('reset_case', 'isolation', 'v1')
        write('begin_session', 's1')
        answer = query('isolation', 's1', 'q4', '我以前告诉过你的蓝帆项目代号是什么？只回答代号；不知道就回答不知道。')
        report['checks']['cross_case_no_canary'] = code not in answer
        report['checks']['cross_case_unknown'] = answer.strip() == '不知道'
        write('end_session', 's1')
        if args.product == 'kylin':
            write('reset_case', 'profile', 'v1')
            write('begin_session', 'p1')
            value = Observation('profile', 'v1', 'p1', 'profile-o1', 'user',
                                '以后请称呼我为' + nickname + '，这是我希望你记住的昵称。', now())
            report['events'].append({'method': 'public_observation', 'input': value.to_public()})
            write('observe', value)
            write('end_session', 'p1')
            write('begin_session', 'p2')
            answer = query('profile', 'p2', 'profile-q1', '我希望你如何称呼我？只回答昵称，不知道就回答不知道。')
            report['checks']['profile_cross_session'] = answer.strip() == nickname
            write('end_session', 'p2')
    except Exception as exc:
        report['error'] = type(exc).__name__ + ': ' + str(exc)
    finally:
        try:
            adapter.close()
            report['checks']['cleanup'] = True
        except Exception as exc:
            report['checks']['cleanup'] = False
            report['cleanup_error'] = str(exc)
        report['namespaces'] = list(transport.namespaces.values())
        exported_operations = set()
        report['cleanup_receipts'] = [r.to_dict() for r in adapter.cleanup_receipts]
        for namespace in report['namespaces']:
            # Only bridge-owned JSON evidence; private agent homes are never exported.
            command = "python3 -c " + __import__('shlex').quote(
                "import pathlib,json; p=pathlib.Path.home()/'memobench-native/cases'/" + repr(namespace) +
                "; print(json.dumps({f.name:json.loads(f.read_text()) for f in p.glob('*.json')}))")
            try:
                r = subprocess.run(['/usr/bin/ssh', '-F', str(Path(args.ssh_config).resolve()),
                                    'memobench-vm', command], capture_output=True, text=True, timeout=30)
                if r.returncode:
                    raise ValueError('export process failed')
                evidence = json.loads(r.stdout)
                (args.out / (namespace + '.json')).write_text(json.dumps(evidence, ensure_ascii=False, indent=2))
                exported_path = args.out / (namespace + '.json')
                report['exports'].append({'namespace': namespace, 'path': exported_path.name,
                    'sha256': hashlib.sha256(exported_path.read_bytes()).hexdigest()})
                bridge_hash = hashlib.sha256((Path(__file__).parent / 'native_vm_product.py').read_bytes()).hexdigest()
                report, resolved_operations = inspect_export(report, evidence, namespace, code, nickname, bridge_hash)
                exported_operations.update(resolved_operations)
            except (subprocess.TimeoutExpired, OSError, ValueError, TypeError):
                report['evidence_export_error'] = True
        required_operations = {event.get('operation_id') or event.get('receipt', {}).get('operation_id')
            for event in report['events'] if event['method'] in ('observe', 'query', 'end_session')}
        if exported_operations != required_operations:
            report['evidence_export_error'] = True
        report['checks'].setdefault('file_task', False)
        report['finished_at'] = now()
        report['status'] = 'passed' if acceptance_passed(report) else 'incomplete'
        persist()
    print(json.dumps({k: report[k] for k in ['product', 'status', 'checks', 'namespaces']}, ensure_ascii=False))
    return 0 if report['status'] == 'passed' else 2

if __name__ == '__main__':
    raise SystemExit(main())
