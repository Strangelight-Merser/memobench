"""Evaluator-side verification of bridge-owned workspace bytes and native trace."""
import base64
import hashlib
import json
from .schema_v2 import ContractError, ForgetPolicy
from .sandbox_v2 import validate_actions


def unpack(snapshot):
    if type(snapshot) is not dict:
        raise ContractError('artifact snapshot missing')
    files = {}
    for path, record in snapshot.items():
        if not isinstance(path, str) or path.startswith('/') or any(p in ('', '.', '..') for p in path.split('/')) or '\\' in path:
            raise ContractError('unsafe artifact path')
        data = base64.b64decode(record['content_base64'], validate=True)
        if len(data) != record['size'] or hashlib.sha256(data).hexdigest() != record['sha256']:
            raise ContractError('artifact bytes/hash mismatch')
        files[path] = data
    return files


def verify_remote_task(gold, prediction, checkpoint, evidence):
    validate_actions(gold)
    if checkpoint['binding'] != evidence.get('binding'):
        raise ContractError('artifact binding mismatch')
    if checkpoint['baseline'] != evidence.get('baseline'):
        raise ContractError('artifact baseline mismatch')
    before, after = unpack(checkpoint['baseline']), unpack(evidence['after'])
    audit = evidence.get('audit')
    if (evidence.get('complete') is not True or type(audit) is not dict or audit.get('complete') is not True
            or not audit.get('product_session') or audit.get('checkpoint') != checkpoint['transcript']):
        raise ContractError('native tool audit incomplete')
    changed = {p for p, data in after.items() if before.get(p) != data}
    deleted = set(before) - set(after)
    writes = [event for event in audit['events'] if event['operation'] == 'write']
    common = ['unsupported_native_file_deletion'] if deleted else []
    if prediction.status != 'ok': common.append('prediction_not_ok')
    for path in changed:
        if not any(event['path'] == path for event in writes): common.append('unsupported_native_tool_execution')
    texts = [prediction.text or ''] + [data.decode('utf-8') for path, data in after.items() if path in changed]
    if prediction.slots is not None: texts.append(json.dumps([slot.to_dict() for slot in prediction.slots], ensure_ascii=False))
    emissions = []
    for event in audit['events']:
        args = event['arguments']
        emissions += [str(args.get('content', '')), str(args.get('new_string', '')), event['path']]
    for raw in gold.forget_policies:
        policy = ForgetPolicy.from_dict(raw)
        if any(value in text for value in policy.values for text in texts + emissions): common.append('forgotten_disclosure')
        if policy.retained_text is not None and not any(policy.retained_text in text for text in texts): common.append('unrelated_preference_lost')
    checks = []
    for action in gold.expected_actions:
        faults = list(common)
        path = action['path']
        matches = [e for e in writes if e['path'] == path]
        if action['operation'] != 'create': faults.append('unsupported_native_render')
        if path not in after: faults.append('missing_file')
        elif hashlib.sha256(after[path]).hexdigest() != action['sha256']: faults.append('content_mismatch')
        if path not in changed or path in before or not matches: faults.append('action_trace_mismatch')
        if matches:
            event = matches[-1]
            if event['tool'] not in ('write', 'write_file'): faults.append('action_trace_mismatch')
            content = event['arguments'].get('content')
            if not isinstance(content, str) or content.encode('utf-8') != after.get(path): faults.append('action_trace_mismatch')
        if any(old in changed or any(event['path'] == old for event in writes) for old in action.get('old_paths', [])):
            faults.append('old_path_reuse')
        checks.append({'status': 'failed' if faults else 'passed', 'faults': sorted(set(faults))})
    unsupported = any(f.startswith('unsupported_') for check in checks for f in check['faults'])
    return {'status': 'unsupported' if unsupported else 'passed' if all(c['status'] == 'passed' for c in checks) else 'failed',
            'checks': checks, 'faults': sorted({f for check in checks for f in check['faults']}),
            'binding': evidence['binding'], 'artifacts': {p: hashlib.sha256(b).hexdigest() for p,b in after.items()},
            'deleted_paths': sorted(deleted), 'audit_coverage': 'direct_file_tools_only; exec and render unsupported',
            'source': 'bridge_workspace_bytes_and_native_tool_trace'}
