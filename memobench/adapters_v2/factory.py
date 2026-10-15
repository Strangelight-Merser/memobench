"""Explicit product factories. Online evidence is checked before SSH construction."""
import hashlib
import json
from pathlib import Path
from .native import NativeAdapter
from .ssh_vm import SSHVMTransport
from ..schema_v2 import AdapterCapabilities

PRODUCTS = ('kylin', 'openclaw')
REQUIRED_CHECKS = {'same_session', 'cross_session', 'cross_case_no_canary', 'cross_case_unknown', 'file_task', 'cleanup'}


def native_capabilities():
    return AdapterCapabilities(native_answer='supported', retrieved_evidence='unsupported',
        write_usage='unsupported', flush='unsupported', restart='unsupported', storage_inspection='supported')


def online_preflight(product, settings, validation, *, live, execution):
    if not live:
        raise ValueError('live_required')
    if execution != 'online' or product not in PRODUCTS:
        raise ValueError('native_online_only')
    return review_native_settings(product, settings, validation)


def review_native_settings(product, settings, validation):
    """Read-only evidence/data validation; does not authorize or create transport."""
    if product not in PRODUCTS:
        raise ValueError('unknown native product')
    internal = (validation.get('release_status') == 'accepted_internal'
                and validation.get('usage_scope') == 'internal_evaluation_only'
                and isinstance(settings, dict) and settings.get('purpose') == 'internal_evaluation')
    if validation.get('release_status') != 'accepted' and not internal:
        raise ValueError('native_data_approval_required')
    required = {'ssh_config', 'purpose', 'acceptance', 'acceptance_sha256', 'bridge_sha256', 'config_sha256', 'dataset_sha256'}
    if type(settings) is not dict or set(settings) != required or settings['purpose'] not in ('development_acceptance', 'frozen_evaluation', 'internal_evaluation'):
        raise ValueError('native_explicit_purpose_and_evidence_required')
    if settings['dataset_sha256'] != validation.get('content_sha256'):
        raise ValueError('native_dataset_hash_mismatch')
    config_bytes = Path(settings['ssh_config']).read_bytes()
    if hashlib.sha256(config_bytes).hexdigest() != settings['config_sha256']:
        raise ValueError('native_configuration_hash_mismatch')
    bridge = Path(__file__).resolve().parents[2] / 'tools/native_vm_product.py'
    if hashlib.sha256(bridge.read_bytes()).hexdigest() != settings['bridge_sha256']:
        raise ValueError('native_bridge_hash_mismatch')
    raw = Path(settings['acceptance']).read_bytes()
    if hashlib.sha256(raw).hexdigest() != settings['acceptance_sha256']:
        raise ValueError('native_acceptance_hash_mismatch')
    evidence = json.loads(raw)
    checks = REQUIRED_CHECKS | ({'profile_cross_session', 'profile_persisted', 'profile_prompt_injected', 'profile_turns_completed'} if product == 'kylin' else set())
    if (evidence.get('product') != product or evidence.get('execution') != 'online'
        or evidence.get('status') != 'passed' or evidence.get('error') or evidence.get('evidence_export_error')
        or set(evidence.get('checks', {})) != checks or not all(evidence['checks'][key] is True for key in checks)
        or evidence.get('bridge_sha256') != settings['bridge_sha256']
        or evidence.get('config_sha256') != settings['config_sha256']):
        raise ValueError('native_isolation_integration_evidence_NOT_VERIFIED')
    from tools.probe_native_vm import operation_evidence, inspect_export, acceptance_passed
    exports = evidence.get('exports')
    if not isinstance(exports, list) or not exports:
        raise ValueError('native_raw_isolation_evidence_required')
    checked = dict(evidence, checks={'cleanup': True})
    operations = set()
    for entry in exports:
        export_path = (Path(settings['acceptance']).resolve().parent / entry['path']).resolve()
        if not export_path.is_relative_to(Path(settings['acceptance']).resolve().parent):
            raise ValueError('native_raw_evidence_path_outside_bundle')
        raw_export = export_path.read_bytes()
        if hashlib.sha256(raw_export).hexdigest() != entry['sha256']:
            raise ValueError('native_raw_evidence_hash_mismatch')
        exported = json.loads(raw_export)
        control = exported['control.json']
        resets = [(op, item) for op, item in control['operations'].items() if item['method'] == 'reset_case']
        if len(resets) != 1 or control.get('closed') is not True:
            raise ValueError('native_namespace_lifecycle_NOT_VERIFIED')
        op, item = resets[0]
        isolation = operation_evidence(exported, entry['namespace'], op, None, 'reset_case', settings['bridge_sha256'])
        if (isolation.get('mount_isolation') != 'passed' or isolation.get('private_sentinel_present_outside') is not True
                or isolation.get('private_sentinel_visible_inside') is not False):
            raise ValueError('native_mount_isolation_NOT_VERIFIED')
        local_reset = next((event for event in evidence.get('events', [])
                            if event.get('method') == 'reset_case' and event.get('receipt', {}).get('operation_id') == op), None)
        if local_reset is None or (local_reset.get('episode_id'), local_reset.get('variant_id')) != (control['episode_id'], control['variant_id']):
            raise ValueError('native_reset_event_mismatch')
        for event in evidence.get('events', []):
            if event.get('method') != 'query' or event.get('operation_id') not in control['operations']:
                continue
            public = event['input']
            turn = operation_evidence(exported, entry['namespace'], event['operation_id'], public['session_id'], 'query', settings['bridge_sha256'])
            prediction = event['prediction']
            if prediction.get('status') != 'ok' or prediction.get('text') != turn.get('answer'):
                raise ValueError('native_prediction_evidence_mismatch')
            answer = prediction['text'].strip()
            probe_id = public['probe_id']
            if probe_id == 'q1': checked['checks']['same_session'] = answer == evidence['canary']
            elif probe_id == 'q2': checked['checks']['cross_session'] = answer == evidence['canary']
            elif probe_id == 'q4':
                checked['checks']['cross_case_no_canary'] = evidence['canary'] not in answer
                checked['checks']['cross_case_unknown'] = answer == '不知道'
            elif probe_id == 'profile-q1': checked['checks']['profile_cross_session'] = answer == evidence['profile_canary']
        checked, resolved = inspect_export(checked, exported, entry['namespace'], evidence['canary'],
                                          evidence.get('profile_canary'), settings['bridge_sha256'])
        operations.update(resolved)
    expected_operations = {event.get('operation_id') or event.get('receipt', {}).get('operation_id')
        for event in evidence.get('events', []) if event['method'] in ('observe', 'query', 'end_session')}
    if operations != expected_operations or not acceptance_passed(checked):
        raise ValueError('native_raw_integration_evidence_NOT_VERIFIED')
    # Hash-bound acceptance is a prerequisite, never a request to sign off data.
    return dict(settings)


def native_factory(product, *, execution, transport_factory=None, live=False,
                   settings=None, validation=None):
    if product not in PRODUCTS:
        raise ValueError('unknown native product')
    if execution == 'offline' and transport_factory is not None and not live:
        return lambda: NativeAdapter(transport_factory(product), native_capabilities())
    frozen = online_preflight(product, settings, validation or {}, live=live, execution=execution)
    return lambda: NativeAdapter(SSHVMTransport(frozen['ssh_config'], product, live=True), native_capabilities())
