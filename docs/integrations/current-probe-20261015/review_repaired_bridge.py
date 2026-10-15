"""Independent review of the bounded real audit regression, no model calls."""
import hashlib
import json
from pathlib import Path
from memobench.native_artifacts_v2 import unpack, verify_remote_task
from memobench.schema_v2 import Gold, Prediction
from tools.native_vm_product import native_file_audit

root = Path(__file__).resolve().parent / 'audit-fix-acceptance'
bridge_hash = hashlib.sha256(Path('tools/native_vm_product.py').read_bytes()).hexdigest()
output = {'reviewer': 'primary_agent', 'scope': 'real synthetic integration regression, not benchmark',
          'bridge_sha256': bridge_hash, 'products': {}}
for product in ('openclaw', 'kylin'):
    path = root / f'{product}-file-regression.json'
    row = json.loads(path.read_text())
    attempt = row['result']
    evidence, = attempt['operation_evidence']
    checkpoint, artifacts = evidence['checkpoint'], evidence['evidence']
    assert artifacts['binding']['bridge_sha256'] == bridge_hash
    assert artifacts['complete'] is True
    assert native_file_audit(artifacts['native_records'], checkpoint['transcript'],
                             artifacts['audit']['product_session']) == artifacts['audit']
    result, = attempt['results']
    expected = row['expected']
    pred = Prediction.from_dict(result['prediction'])
    gold = Gold(pred.probe_id, [], [], [], [{'operation': 'create', **expected}], [], ['recall'], ['task_reuse'])
    checked = verify_remote_task(gold, pred, checkpoint, artifacts)
    assert checked['status'] == result['task_status'] == 'passed'
    before, after = unpack(checkpoint['baseline']), unpack(artifacts['after'])
    assert expected['path'] not in before
    assert hashlib.sha256(after[expected['path']]).hexdigest() == expected['sha256']
    assert attempt['error'] is None and attempt['cleanup_error'] is None
    assert all(r['status'] == 'ready' for r in attempt['cleanup_receipts'])
    raw_path, = root.glob(f'{product}-file-raw-*.json')
    raw = json.loads(raw_path.read_text())
    assert raw['control.json']['closed'] is True
    query, = [o for o in raw['control.json']['operations'].values() if o['method'] == 'query']
    native = raw[query['evidence']]
    assert native['artifacts'] == artifacts and native['answer'] == pred.text
    if product == 'kylin': assert native['profile_completed'] is True
    failed_reads = [e for e in artifacts['audit']['events']
                    if e['operation'] == 'read' and e['succeeded'] is False]
    assert any(e['arguments'].get('path') == '/home/mb/case/workspace' for e in failed_reads)
    output['products'][product] = {
        'task_verification': checked['status'], 'complete_native_trace_recomputed': True,
        'initial_file_absent': True, 'final_bytes_sha256': expected['sha256'],
        'failed_root_read_retained': True, 'cleanup_verified': True,
        'original_prediction_preserved': True,
        'native_profile_completed': native.get('profile_completed'),
        'raw_sha256': hashlib.sha256(raw_path.read_bytes()).hexdigest(),
        'record_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
    }
print(json.dumps(output, ensure_ascii=False, indent=2))
