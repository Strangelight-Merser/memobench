"""Recompute phase and file acceptance from original complete real CLI evidence."""
from collections import Counter
import argparse
import hashlib
import json
from pathlib import Path
from memobench.data_v2 import load_dataset
from memobench.native_artifacts_v2 import unpack, verify_remote_task
from memobench.schema_v2 import Prediction
from tools.native_vm_product import native_file_audit, PHASE_POLICIES

root = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--run-root', type=Path, default=root / 'cli-final')
parser.add_argument('--bridge-source', type=Path, default=Path('tools/native_vm_product.py'))
parser.add_argument('--product', action='append', choices=('kylin', 'openclaw'))
args = parser.parse_args()
prepared = args.run_root
episode = next(e for e in load_dataset('data/v0.2-ai-reviewed', 'test')
               if (e.story_id, e.variant_id) == ('e6a7a9059f826b02f8edd920', 'd012611aa89b90909fcea7b9'))
bridge_hash = hashlib.sha256(args.bridge_source.read_bytes()).hexdigest()
report = {'reviewer': 'primary_agent', 'bridge_sha256': bridge_hash,
          'scope': 'selected products; original complete case; no full benchmark ranking', 'products': {}}
for product in args.product or ('openclaw', 'kylin'):
    case_path, = (prepared / f'run-{product}' / 'cases').glob('*.json')
    raw_path, = (prepared / f'raw-{product}').glob('*.json')
    case = json.loads(case_path.read_text())
    raw = json.loads(raw_path.read_text())
    control = raw['control.json']
    attempt, = case['attempts']
    assert case['public_input'] == episode.to_public()
    assert control['bridge_sha256'] == bridge_hash and control['closed'] is True
    operations = list(control['operations'].values())
    counts = Counter(op['method'] for op in operations)
    assert counts['observe'] == 80 and counts['query'] == 1
    assert counts['begin_session'] == counts['end_session'] == 2
    assert all(op['status'] == 'completed' for op in operations)
    assert attempt['error'] is None and attempt['cleanup_error'] is None
    assert all(r['status'] == 'ready' for r in attempt['cleanup_receipts'])
    observes = [raw[op['evidence']] for op in operations if op['method'] == 'observe']
    for obs, native in zip(episode.observations, observes):
        policy = native['phase_policy']
        assert policy['phase'] == 'observe' and policy['task_workspace_writable'] is False
        assert policy['public_text'] == obs.text
        assert policy['public_text_sha256'] == hashlib.sha256(obs.text.encode()).hexdigest()
        assert policy['system_policy']['text'] == PHASE_POLICIES['observe']
        assert policy['system_policy']['sha256'] == hashlib.sha256(PHASE_POLICIES['observe'].encode()).hexdigest()
        argv = native['product_argv']; text_flag = '-q' if product == 'kylin' else '--message'
        assert argv[argv.index(text_flag)+1] == obs.text
        assert native['task_workspace_before'] == native['task_workspace_after'] == {}
        assert native['task_workspace_unchanged'] is True
        if product == 'kylin':
            assert native['profile_completed'] is True
            assert argv[argv.index('--toolsets')+1] == 'memory'
    query_op, = [op for op in operations if op['method'] == 'query']
    native = raw[query_op['evidence']]
    policy = native['phase_policy']
    assert policy['phase'] == 'query' and policy['task_workspace_writable'] is True
    assert policy['public_text'] == episode.probes[0].query
    assert policy['public_text_sha256'] == hashlib.sha256(episode.probes[0].query.encode()).hexdigest()
    argv = native['product_argv']; text_flag = '-q' if product == 'kylin' else '--message'
    assert argv[argv.index(text_flag)+1] == episode.probes[0].query
    assert policy['system_policy']['text'] == PHASE_POLICIES['query']
    assert policy['system_policy']['sha256'] == hashlib.sha256(PHASE_POLICIES['query'].encode()).hexdigest()
    result, = attempt['results']; evidence, = attempt['operation_evidence']
    assert result['prediction']['text'] == native['answer']
    assert result['prediction']['status'] == 'ok'
    assert evidence['evidence'] == native['artifacts']
    artifacts, checkpoint = evidence['evidence'], evidence['checkpoint']
    assert native_file_audit(artifacts['native_records'], checkpoint['transcript'],
                             artifacts['audit']['product_session']) == artifacts['audit']
    checked = verify_remote_task(episode.golds[0], Prediction.from_dict(result['prediction']), checkpoint, artifacts)
    assert checked['status'] == result['task_status'] == 'passed'
    before, after = unpack(checkpoint['baseline']), unpack(artifacts['after'])
    assert 'markers/ready.txt' not in before and after['markers/ready.txt'] == b'READY'
    if product == 'kylin':
        assert native['profile_completed'] is True
        assert native['product_argv'][native['product_argv'].index('--toolsets')+1] == 'memory,file'
    report['products'][product] = {
        'public_input_exact_match': True, 'observations_verified': len(observes),
        'empty_task_workspace_throughout_observe': True, 'phase_policy_separate_from_user_text': True,
        'original_query_unchanged': True, 'single_attempt': True,
        'operation_counts': dict(counts), 'cleanup_verified': True,
        'native_profile_completed_turns': 81 if product == 'kylin' else None,
        'final_file_newly_created': True, 'exact_file_bytes': 'READY', 'file_size': 5,
        'file_sha256': hashlib.sha256(after['markers/ready.txt']).hexdigest(),
        'native_trace_independently_recomputed': True, 'task_verification': checked['status'],
        'original_scoring_status': result['score']['status'],
        'raw_sha256': hashlib.sha256(raw_path.read_bytes()).hexdigest(),
        'case_sha256': hashlib.sha256(case_path.read_bytes()).hexdigest(),
    }
print(json.dumps(report, ensure_ascii=False, indent=2))
