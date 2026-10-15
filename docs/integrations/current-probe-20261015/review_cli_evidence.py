"""Read-only independent checks of real CLI runs; does not overwrite scores."""
from collections import Counter
import hashlib
import json
from pathlib import Path
from memobench.data_v2 import load_dataset
from memobench.native_artifacts_v2 import unpack, verify_remote_task
from memobench.schema_v2 import Prediction, ContractError

ROOT = Path(__file__).resolve().parent
prepared = ROOT / 'cli-prepared'
episode = next(e for e in load_dataset('data/v0.2-ai-reviewed', 'test')
               if e.story_id == 'e6a7a9059f826b02f8edd920' and e.variant_id == 'd012611aa89b90909fcea7b9')
report = {'reviewer': 'primary_agent', 'review_method': 'independent_evidence_recomputation',
          'original_observations': len(episode.observations), 'products': {}}
for product in ('openclaw', 'kylin'):
    case_path, = (prepared / f'run-{product}' / 'cases').glob('*.json')
    raw_path, = (prepared / f'raw-{product}').glob('*.json')
    case = json.loads(case_path.read_text())
    raw = json.loads(raw_path.read_text())
    control = raw['control.json']
    attempt, = case['attempts']
    assert case['public_input'] == episode.to_public(), 'public input modified'
    assert control['closed'] is True
    operations = list(control['operations'].values())
    counts = Counter(op['method'] for op in operations)
    assert counts['observe'] == 80 and counts['query'] == 1
    assert counts['begin_session'] == 2
    assert counts['end_session'] == (2 if attempt['error'] is None else 1)
    assert all(op['status'] == 'completed' for op in operations)
    assert attempt['cleanup_error'] is None
    assert all(r['status'] == 'ready' for r in attempt['cleanup_receipts'])
    query_op, = [op for op in operations if op['method'] == 'query']
    query = raw[query_op['evidence']]
    result, = attempt['results']
    assert result['prediction']['text'] == query['answer']
    assert result['prediction']['status'] == 'ok'
    evidence, = attempt['operation_evidence']
    assert evidence['evidence'] == query['artifacts']
    before = unpack(evidence['checkpoint']['baseline'])
    after = unpack(evidence['evidence']['after'])
    try:
        verification = verify_remote_task(episode.golds[0], Prediction.from_dict(result['prediction']),
                                          evidence['checkpoint'], evidence['evidence'])
    except ContractError as exc:
        verification = {'status': 'blocked', 'reason': str(exc)}
    profile = [raw[op['evidence']].get('profile_completed') for op in operations
               if op['method'] in ('observe', 'query')] if product == 'kylin' else None
    if profile is not None:
        assert len(profile) == 81 and all(p is True for p in profile)
    report['products'][product] = {
        'case_sha256': hashlib.sha256(case_path.read_bytes()).hexdigest(),
        'raw_sha256': hashlib.sha256(raw_path.read_bytes()).hexdigest(),
        'bridge_sha256': control['bridge_sha256'],
        'public_input_exact_match': True, 'single_attempt': True,
        'operation_counts': dict(counts), 'all_operations_completed': True,
        'cleanup_verified': True, 'prediction_matches_raw_native_answer': True,
        'native_profile_completed_turns': len(profile) if profile is not None else None,
        'marker_before_exact_READY': before.get('markers/ready.txt') == b'READY',
        'marker_after_exact_READY': after.get('markers/ready.txt') == b'READY',
        'marker_changed_by_query': before.get('markers/ready.txt') != after.get('markers/ready.txt'),
        'independently_recomputed_verification': verification,
        'original_task_status': result['task_status'],
        'original_scoring_status': result['score']['status'],
        'original_attempt_status': attempt['status'],
    }
print(json.dumps(report, ensure_ascii=False, indent=2))
