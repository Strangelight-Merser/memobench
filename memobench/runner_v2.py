"""唯一 v2 编排器。离线 fixture 验证链路，不构成真实系统成绩。"""
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from uuid import uuid4

from .data_v2 import load_dataset, validate_release
from .protocol_v2 import FakeComponentAdapter, require_ready, adapter_payload
from .schema_v2 import (Prediction, Observation, Probe, RunManifest,
                        validate_dataset, validate_prediction)
from .judge_v2 import judge, overall_label
from .scoring_v2 import summarize as summarize_scores, strict_json
from .stats_v2 import Sample, summarize as summarize_stats
from .llm_v2 import CostLedger, LLMClient, Limits
from .sandbox_v2 import native_isolation_status, validate_actions, FileSandbox, verify_task

ROOT = Path(__file__).resolve().parent.parent


def now():
    return datetime.now(timezone.utc).isoformat()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False) + '\n'


def digest(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def safe_output(root, relative):
    """产物名由程序决定，ID 只参与摘要；拒绝符号链接和目录穿越。"""
    root = Path(root).absolute()
    path = root / relative
    if Path(relative).is_absolute() or any(p in ('..', '.') for p in relative.split('/')):
        raise ValueError('unsafe output path')
    part = path
    while True:
        if part.is_symlink():
            raise ValueError('symlink output refused')
        if part == root:
            break
        part = part.parent
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('unsafe output path')
    return path


def atomic_write(path, text):
    path = Path(path).absolute()
    safe_output(path.parent, path.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                     delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
            stream.close()
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def save(root, name, value):
    atomic_write(safe_output(root, name), encoded(value))


def read(path):
    return strict_json(Path(path).read_text(encoding='utf-8'))


def hash_inventory(root, paths):
    root = Path(root).resolve()
    rows = [{'path': p.relative_to(root).as_posix(),
             'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
            for p in sorted(paths)]
    return {'sha256': digest(rows), 'files': rows,
            'serialization': 'UTF-8 JSON ensure_ascii=False sort_keys=True separators=(comma,colon), trailing LF'}


def fixture_reader(probe, recalled):
    """透明回显，仅检查全历史输送；不声称是 LLM Reader。"""
    return Prediction(probe.episode_id, probe.variant_id, probe.session_id, probe.probe_id,
                      recalled.status, '\n'.join(recalled.context), now(),
                      retrieved_evidence=recalled.retrieved_evidence)


def offline_file_checks(gold, prediction):
    """只执行假适配器显式返回的工具请求；不从 gold 生成操作或内容。"""
    with tempfile.TemporaryDirectory(prefix='memobench-files-') as directory:
        with FileSandbox(Path(directory) / 'case') as sandbox:
            for index, action in enumerate(prediction.file_actions):
                if (set(action) != {'operation', 'arguments'} or
                        type(action['arguments']) is not dict):
                    raise ValueError('invalid file action request')
                sandbox.execute(action['operation'], 'file:' + str(index), **action['arguments'])
            checks, results = [], []
            for action in gold.expected_actions:
                checked = verify_task(sandbox, replace(gold, expected_actions=[action]), prediction,
                                      baseline={}, audit_since=0)
                checks.append(checked['status'] == 'passed')
                results.append(checked)
            return checks, {'audit': sandbox.audit, 'checks': results,
                            'artifacts': sandbox.snapshot()}


def execute_case(episode, factory, *, mode, reader=fixture_reader, operation_prefix,
                 execution='offline', judge_transport=None):
    """factory 无私有参数；一个完整 episode/variant 一个全新实例。"""
    adapter = None
    rows, events, seen = [], [], []
    ledger = CostLedger()
    error = None
    stage = 'create_adapter'
    caps = None
    def op(name):
        return operation_prefix + ':' + name
    def write(method, *args, name):
        receipt = getattr(adapter, method)(*args, op(name))
        ledger.record_adapter('write', receipt, execution=execution)
        events.append({'method': method, 'receipt': receipt.to_dict()})
        if receipt.operation_id != op(name):
            raise ValueError('receipt operation mismatch')
        require_ready(receipt)
    try:
        adapter = factory()
        caps = adapter.capabilities
        caps.validate()
        if mode == 'native_agent':
            stage = 'reset_case'
            write('reset_case', episode.episode_id, episode.variant_id, name='reset')
        golds = {g.probe_id: g for g in episode.golds}
        for session in episode.session_ids:
            if mode == 'native_agent':
                stage = 'begin_session'
                write('begin_session', session, name='begin:' + session)
            timeline = [x for x in episode.observations + episode.probes if x.session_id == session]
            timeline.sort(key=lambda x: (datetime.fromisoformat(x.observed_at.replace('Z', '+00:00')),
                                         0 if type(x) is Observation else 1))
            for item in timeline:
                public = adapter_payload(item)
                stage = 'observe' if type(item) is Observation else 'query'
                # 独立副本：被测方不能修改评测器持有的观察或问题。
                if type(item) is Observation:
                    write('observe', Observation.from_dict(public), name='observe:' + item.observation_id)
                    seen.append(item)
                    continue
                raw = None
                if mode == 'native_agent':
                    prediction = adapter.query(Probe.from_dict(public), op('query:' + item.probe_id))
                    ledger.record_adapter('read', prediction, execution=execution)
                    actual_execution = execution
                else:
                    recalled = adapter.recall(Probe.from_dict(public))
                    recalled.validate()
                    ledger.record_adapter('retrieval', recalled, execution=execution)
                    if recalled.status == 'ok':
                        answer = reader(Probe.from_dict(public), recalled)
                        if isinstance(answer, Prediction):
                            prediction, actual_execution = answer, execution
                            ledger.record_adapter('read', prediction, execution=execution)
                        else:
                            raw = answer.to_dict()
                            prediction, actual_execution = answer.to_prediction(item), answer.execution
                    else:
                        prediction = Prediction(item.episode_id, item.variant_id, item.session_id,
                                                item.probe_id, recalled.status, None, now())
                        actual_execution = execution
                validate_prediction(prediction, item, caps, seen)
                gold = golds[item.probe_id]
                task_status, task_checks, task_verification = None, None, None
                if gold.expected_actions:
                    validate_actions(gold)
                    task_status = 'blocked: trusted_tool_execution_unavailable'
                    if execution == 'offline' and prediction.file_actions is not None:
                        task_checks, task_verification = offline_file_checks(gold, prediction)
                        task_status = 'passed' if all(task_checks) else 'failed'
                scored = judge(gold, prediction, item, seen, caps, transport=judge_transport,
                               task_checks=task_checks)
                if task_verification and any('forgotten_disclosure' in check['faults']
                                              for check in task_verification['checks']):
                    from .scoring_v2 import result as scoring_result
                    scored['metrics']['forgotten_disclosure'] = True
                    scored = scoring_result(gold, scored['metrics'], scored.get('review_reason'),
                                            source=scored['source'])
                rows.append({'prediction': prediction.to_dict(), 'execution': actual_execution,
                             'score': scored, 'raw_reader': raw, 'task_status': task_status,
                             'task_verification': task_verification,
                             'evidence_locations': [e.to_dict() for e in gold.evidence]})
                if prediction.status != 'ok':
                    raise RuntimeError('prediction_failed')
            stage = 'end_session'
            write('end_session', session, name='end:' + session)
    except Exception as exc:
        # 异常正文可能包含私有值或供应商密钥，只留类型与阶段。
        error = {'stage': stage, 'type': type(exc).__name__}
    finally:
        if adapter is not None and hasattr(adapter, 'close'):
            try:
                adapter.close()
            except Exception as exc:
                error = {'stage': 'close', 'type': type(exc).__name__}
    completed = {r['prediction']['probe_id'] for r in rows}
    for probe, gold in zip(episode.probes, [next(g for g in episode.golds if g.probe_id == p.probe_id)
                                          for p in episode.probes]):
        if probe.probe_id not in completed:
            status = 'timeout' if error and error['type'] == 'TimeoutError' else 'error'
            prediction = Prediction(probe.episode_id, probe.variant_id, probe.session_id,
                                    probe.probe_id, status, None, now())
            from .scoring_v2 import score
            rows.append({'prediction': prediction.to_dict(), 'execution': execution,
                         'score': score(gold, prediction), 'raw_reader': None,
                         'task_status': None,
                         'evidence_locations': [e.to_dict() for e in gold.evidence]})
    return {'status': 'failed' if error else 'completed', 'error': error, 'results': rows,
            'events': events, 'cost_records': ledger.records, 'finished_at': now()}


def summarize(episodes, cases, mode, execution):
    rows = [r for c in cases for r in c['results']]
    partitions = {}
    for partition in ('offline', 'online', 'replay'):
        samples = [Sample(Prediction.from_dict(r['prediction']),
                          None if overall_label(r['score']) is None else float(overall_label(r['score'])),
                          '1', r['execution']) for r in rows]
        if partition == execution or any(r['execution'] == partition for r in rows):
            selected = [r for r in rows if r['execution'] == partition]
            partitions[partition] = {'statistics': summarize_stats(episodes, samples,
                execution=partition, expected_repeats=['1']),
                'scoring': summarize_scores(r['score'] for r in selected)}
    return {'mode': mode, 'partitions': partitions, 'n_case': len(cases),
            'failed_cases': sum(c['status'] != 'completed' for c in cases),
            'publish_ranking': False}


def run(config, out, *, live=False, resume=False):
    allowed = {'dataset', 'split', 'mode', 'execution', 'adapter', 'reader', 'llm', 'binding_status'}
    if type(config) is not dict or set(config) - allowed:
        raise ValueError('unknown experiment configuration')
    mode, execution = config.get('mode'), config.get('execution')
    if mode not in ('component', 'native_agent') or execution not in ('offline', 'online', 'replay'):
        raise ValueError('invalid mode/execution')
    root = Path(out).absolute()
    marker = safe_output(root, 'manifest.json')
    if root.exists() and any(root.iterdir()) and not resume:
        raise ValueError('output exists; use --resume or a new directory')
    dataset = Path(config['dataset']).resolve()
    validation = validate_release(dataset)
    episodes = load_dataset(dataset, config.get('split', 'dev'))
    validate_dataset(episodes)
    notice = '候选数据，未签收' if validation['release_status'] != 'accepted' or config.get('split') != 'test' else '人工签收测试集'
    blocked = None
    if mode == 'native_agent':
        blocked = native_isolation_status()['reason']
        if not live:
            blocked = 'live_required; ' + blocked
    elif execution == 'online' and not live:
        blocked = 'live_required'
    if blocked:
        if resume and marker.exists():
            raise ValueError('cannot replace an existing run with blocked status')
        summary = {'status': 'blocked', 'reason': blocked, 'mode': mode, 'partitions': {},
                   'data_notice': notice, 'dataset_validation': validation,
                   'publish_ranking': False, 'n_case': 0, 'failed_cases': 0}
        save(root, 'summary.json', summary)
        return summary
    if config.get('adapter') != 'full-history-fixture':
        raise ValueError('no reviewed component adapter configured')
    reader_kind = config.get('reader')
    if reader_kind not in ('echo-fixture', 'llm'):
        raise ValueError('explicit reader required')
    if reader_kind == 'echo-fixture' and execution != 'offline':
        raise ValueError('fixture is offline only')
    if reader_kind == 'llm' and execution == 'offline':
        raise ValueError('LLM requires online or replay execution')
    inventory = {
        'code': hash_inventory(ROOT, list((ROOT / 'memobench').rglob('*.py'))),
        'data': hash_inventory(dataset, [p for p in dataset.iterdir() if p.is_file()]),
        'scorer': hash_inventory(ROOT, [ROOT / 'memobench/scoring_v2.py', ROOT / 'memobench/judge_v2.py',
                                       ROOT / 'prompts/judge-v0.2/system.txt'])}
    identity = digest({'config': config, 'hashes': inventory})
    if resume and marker.exists():
        previous = read(safe_output(root, 'run.json'))
        if previous['identity'] != identity:
            raise ValueError('resume config/code/data/scorer mismatch')
        manifest = RunManifest.from_dict(read(marker))
        if reader_kind == 'llm':
            raise ValueError('LLM resume blocked: cumulative budget restoration unavailable; use new run')
    else:
        if resume and root.exists() and any(root.iterdir()):
            raise ValueError('missing resume manifest')
        manifest = RunManifest(uuid4().hex, mode, execution, config['adapter'], 'contract-0.2',
            FakeComponentAdapter().capabilities, [], now(), None,
            inventory['code']['sha256'], inventory['data']['sha256'], inventory['scorer']['sha256'])
        save(root, 'hashes.json', inventory)
        save(root, 'run.json', {'identity': identity, 'config': config, 'data_notice': notice,
                              'dataset_validation': validation, 'fixture': True})
        save(root, 'manifest.json', manifest.to_dict())
    manifest.finished_at = None
    save(root, 'manifest.json', manifest.to_dict())
    client = None
    reader = fixture_reader
    if reader_kind == 'llm':
        settings = dict(config.get('llm', {}))
        bound = settings.pop('input_token_bound')
        settings['limits'] = Limits(**settings.get('limits', {}))
        client = LLMClient.from_env(**settings)
        def reader(probe, recalled):
            answer = client.answer(probe, recalled, live=live and execution == 'online',
                                   input_token_bound=bound)
            manifest.models.append(answer.model)
            save(root, 'manifest.json', manifest.to_dict())
            return answer
    cases = []
    prior_failed_attempts = 0
    interrupted_attempts = 0
    for episode in episodes:
        key = digest([episode.episode_id, episode.variant_id])
        name = 'cases/' + key + '.json'
        path = safe_output(root, name)
        attempts = read(path)['attempts'] if path.exists() else []
        for attempt in attempts:
            if attempt['status'] == 'running':
                attempt.update(status='interrupted', detected_at=now())
        prior_failed_attempts += sum(a['status'] == 'failed' for a in attempts)
        interrupted_attempts += sum(a['status'] == 'interrupted' for a in attempts)
        if attempts and attempts[-1]['status'] == 'completed':
            cases.append(attempts[-1])
            continue
        attempt_id = uuid4().hex
        attempts.append({'status': 'running', 'attempt_id': attempt_id, 'started_at': now()})
        case_record = {'episode_id': episode.episode_id, 'variant_id': episode.variant_id,
                       'story_id': episode.story_id, 'public_input': episode.to_public(), 'attempts': attempts}
        save(root, name, case_record)
        result = execute_case(episode, FakeComponentAdapter, mode=mode, reader=reader,
                              operation_prefix=manifest.run_id + ':' + attempt_id, execution=execution)
        attempts[-1].update(result)
        save(root, name, case_record)
        cases.append(attempts[-1])
        save(root, 'summary.json', dict(summarize(episodes, cases, mode, execution),
             status='running', data_notice=notice, dataset_validation=validation, fixture=True))
    total_ledger = CostLedger()
    total_ledger.records = [r for c in cases for r in c['cost_records']]
    if client:
        total_ledger.records.extend(client.ledger.records)
    summary = dict(summarize(episodes, cases, mode, execution),
        status='completed_with_errors' if any(c['status'] != 'completed' for c in cases) else 'completed',
        data_notice=notice, dataset_validation=validation, fixture=True,
        reader=reader_kind, cost=total_ledger.summary(),
        prior_failed_attempts=prior_failed_attempts, interrupted_attempts=interrupted_attempts,
        integration_gaps=[
            'echo-fixture 不发起文件操作；文件任务需显式工具请求及可信产物验证',
            'native 产品桥与外部权限隔离未验证；不支持中断 native 原地续跑',
            '离线 echo-fixture 非 LLM Reader；语义裁判与人工校准未执行'])
    if client:
        save(root, 'llm-costs.json', client.ledger.records)
    manifest.finished_at = now()
    save(root, 'manifest.json', manifest.to_dict())
    save(root, 'summary.json', summary)
    atomic_write(safe_output(root, 'results.jsonl'), ''.join(encoded(dict(r,
        attempt_id=c['attempt_id'])) for c in cases for r in c['results']))
    return summary
