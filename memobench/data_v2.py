"""离线候选数据：先回放事件账本，再渲染公开观察。"""
import hashlib
import json
from pathlib import Path
import random
from datetime import datetime, timedelta, timezone

from .schema_v2 import (Episode, Observation, Probe, Gold, Slot, EvidenceLocation,
                        SandboxReference, ContractError, validate_dataset)
from .protocol_v2 import adapter_payload


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False,
                      separators=(',', ':')) + '\n'


def digest(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


def rng(seed, stream, story):
    return random.Random(int(digest([seed, stream, story]), 16))


def opaque(*parts):
    return digest(list(parts))[:24]


def safe_path(root, relative):
    """只定位指定目录内的文件；拒绝符号链接逃逸。"""
    SandboxReference('path-check', relative)
    root = Path(root).resolve()
    path = root / relative
    if not path.resolve().is_relative_to(root):
        raise ContractError('数据文件路径越界')
    return path


def read_rows(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines()
            if line.strip()]


def truth(events, targets):
    """只读结构化事件，不读取表面措辞或模型答案。"""
    state = {}
    for event in events:
        key, op = event['key'], event['op']
        if op == 'set':
            state[key] = ('answer', event['value'])
        elif op in ('forgotten', 'conflict'):
            state[key] = (op, None)
        elif op == 'copy':
            state[key] = state[event['from']]
        elif op == 'join':
            values = [state[k] for k in event['from']]
            if any(s != 'answer' for s, _ in values):
                raise ContractError('推断缺少依据')
            state[key] = ('answer', '/'.join(v.rstrip('/') for _, v in values))
        else:
            raise ContractError('未知账本操作')
    return [Slot(t['key'], t['type'], *state.get(t['key'], ('unknown', None)))
            for t in targets]


def generate(stories, seed=42, context_chars=2048, turns_per_session=40):
    """字符预算仅计 observation.text；两会话各至少指定条数。"""
    if type(turns_per_session) is not int or turns_per_session < 1:
        raise ValueError('轮数必须为正整数')
    episodes = []
    for story in stories:
        sid = story['story_id']
        # 事件流只决定故事时间，措辞和噪声不能消耗此随机源。
        day = rng(seed, 'events', sid).randrange(1, 20)
        origin = datetime(2026, 1, day, tzinfo=timezone.utc)
        slots = truth(story['events'], story['targets'])
        for variant in range(2):
            vid, eid = opaque('variant', variant), opaque('episode', sid)
            sessions = [opaque(sid, 'session', i) for i in range(2)]
            wording = rng(seed, 'wording', sid).randrange(2) ^ variant
            noise = rng(seed, 'noise', sid)
            observations, evidence = [], []
            for group, alternatives in enumerate(story['utterances']):
                oid = opaque(sid, 'observation', group)
                session = sessions[0 if group == 0 else 1]
                observations.append(Observation(eid, vid, session, oid, 'user',
                    alternatives[wording], (origin + timedelta(days=0 if group == 0 else 30, seconds=group)).isoformat()))
                evidence.append(EvidenceLocation(oid))
            # 补齐轮数采用有放回抽样，不受有限素材容量影响。
            fillers = ['讨论区今天有一条读书交流帖。', '窗外的树影慢慢移动。',
                       '休息时可以看看远处。', '这是一条与工作配置无关的闲聊。']
            counts = [sum(o.session_id == s for o in observations) for s in sessions]
            for session_index, session in enumerate(sessions):
                for i in range(max(0, turns_per_session - counts[session_index])):
                    observations.append(Observation(eid, vid, session,
                        opaque(sid, 'noise', session_index, i), 'user', noise.choice(fillers),
                        (origin + timedelta(days=session_index * 30, seconds=100+i)).isoformat()))
            # 核心证据 ID 和时间不随噪声改变。
            observations.sort(key=lambda o: o.observed_at)
            total = sum(len(o.text) for o in observations)
            if context_chars < total:
                raise ValueError('字符预算小于核心观察与轮数所需长度')
            remaining = context_chars - total
            padding = []
            while remaining:
                sentence = noise.choice(fillers)[:remaining]
                padding.append(sentence)
                remaining -= len(sentence)
            observations[-1].text += ''.join(padding)
            probe = Probe(eid, vid, sessions[1], opaque(sid, 'probe'), story['queries'][wording],
                          (origin + timedelta(days=60)).isoformat(),
                          [SandboxReference(opaque(sid, 'ref', i), p)
                           for i, p in enumerate(story.get('references', []))])
            actions = []
            if story.get('file_task'):
                values = {s.name: s.value for s in slots if s.state == 'answer'}
                path, content = values['output_path'], values['template']
                SandboxReference('output', path)
                actions = [{'operation': 'write_file', 'path': path, 'content': content,
                            'sha256': hashlib.sha256(content.encode()).hexdigest()}]
            gold = Gold(probe.probe_id, slots, evidence, story['events'], actions,
                        story.get('forget_policies', []), story['technical_categories'],
                        [story['official_capability']])
            episodes.append(Episode(eid, vid, sid, story['split'], sessions,
                                    observations, [probe], [gold]))
    validate_dataset(episodes)
    return episodes


def validate_sources(stories):
    ids, templates = set(), {}
    for s in stories:
        if s['story_id'] in ids:
            raise ContractError('重复故事')
        ids.add(s['story_id'])
        template, split = s['template_id'], s['split']
        if templates.get(template, split) != split:
            raise ContractError('情节模板跨集合')
        templates[template] = split
        if s['source_type'] != 'authored_synthetic_ai_assisted':
            raise ContractError('来源类型未声明')
        groups = set(range(len(s['utterances'])))
        if any(e['utterance'] not in groups for e in s['events']):
            raise ContractError('事件缺少观察依据')
        if any(len(u) != 2 or not all(u) for u in s['utterances']):
            raise ContractError('需要两种措辞')
        truth(s['events'], s['targets'])


def build_dataset(root, seed=42):
    """构建固定候选文件；不自动签收，不覆盖人工审阅记录。"""
    stories = read_rows(safe_path(root, 'sources.jsonl'))
    validate_sources(stories)
    reviews = safe_path(root, 'review.jsonl')
    if not reviews.exists():
        reviews.write_text(''.join(encode({'story_id': s['story_id'],
            'source_sha256': digest(s), 'source_type': s['source_type'],
            'evidence_ids': [opaque(s['story_id'], 'observation', i)
                             for i in range(len(s['utterances']))],
            'status': 'pending_review', 'reviewer': None,
            'reviewed_at': None, 'ledger_query_checked': False,
            'all_variants_checked': False, 'reason': '等待人工逐条核对账本、证据和问题'})
            for s in stories), encoding='utf-8')
    files = {}
    def save(name, rows):
        content = ''.join(encode(r) for r in rows)
        safe_path(root, name).write_text(content, encoding='utf-8')
        files[name] = hashlib.sha256(content.encode()).hexdigest()
    episodes = generate(stories, seed)
    save('candidates.jsonl', [e.to_dict() for e in episodes])
    save('public.jsonl', [e.to_public() for e in episodes])
    selected = [s for s in stories if s['split'] == 'test'][:12]
    for size in (2048, 8192, 32768):
        save(f'paired-{size}.jsonl', [e.to_dict() for e in generate(selected, seed, size)])
    review = {r['story_id']: r for r in read_rows(reviews)}
    accepted = set()
    for s in stories:
        r = review.get(s['story_id'], {})
        if (r.get('status') == 'accepted' and r.get('source_sha256') == digest(s)
                and r.get('reviewer') and r.get('reviewed_at')
                and r.get('ledger_query_checked') is True
                and r.get('all_variants_checked') is True):
            accepted.add(s['story_id'])
    save('test.jsonl', [e.to_dict() for e in episodes if e.split == 'test' and e.story_id in accepted])
    save('dev.jsonl', [e.to_dict() for e in episodes if e.split == 'dev'])
    for name in ('sources.jsonl', 'review.jsonl'):
        files[name] = hashlib.sha256(safe_path(root, name).read_bytes()).hexdigest()
    manifest = {'schema_version': '0.2', 'seed': seed, 'status': 'pending_review',
        'generation': 'offline_authored_synthetic_ai_assisted', 'llm_api': 'blocked: no credentials',
        'openkylin': 'NOT_VERIFIED', 'license': 'pending_maintainer_signoff',
        'n_story': len(stories), 'n_query': len(episodes),
        'target_n_story': 60, 'paired_n_story': len(selected),
        'formal_test_n_query': sum(e.split == 'test' and e.story_id in accepted for e in episodes),
        'context_unit': 'Unicode code points in observation.text; not tokens',
        'files': files}
    safe_path(root, 'manifest.json').write_text(encode(manifest), encoding='utf-8')
    return manifest


def load_dataset(root, split='dev'):
    """正式测试只读取通过人工签收门禁的 test.jsonl。"""
    if split not in ('dev', 'test', 'candidates'):
        raise ValueError('未知数据分区')
    validate_release(root)
    return [Episode.from_dict(r) for r in read_rows(safe_path(root, split + '.jsonl'))]


def validate_release(root):
    manifest = json.loads(safe_path(root, 'manifest.json').read_text(encoding='utf-8'))
    for name, expected in manifest['files'].items():
        if hashlib.sha256(safe_path(root, name).read_bytes()).hexdigest() != expected:
            raise ContractError('文件摘要不匹配')
    stories = read_rows(safe_path(root, 'sources.jsonl'))
    validate_sources(stories)
    expected = generate(stories, manifest['seed'])
    actual = [Episode.from_dict(r) for r in read_rows(safe_path(root, 'candidates.jsonl'))]
    if [e.to_dict() for e in actual] != [e.to_dict() for e in expected]:
        raise ContractError('候选数据与账本不一致')
    public = read_rows(safe_path(root, 'public.jsonl'))
    if public != [e.to_public() for e in actual]:
        raise ContractError('公开数据边界不一致')
    for e in actual:
        for item in e.observations + e.probes:
            adapter_payload(item)
    reviews = read_rows(safe_path(root, 'review.jsonl'))
    if len(reviews) != len(stories) or {r['story_id'] for r in reviews} != {s['story_id'] for s in stories}:
        raise ContractError('审阅清单不完整')
    reviewed = {r['story_id']: r for r in reviews}
    accepted = set()
    for s in stories:
        r = reviewed[s['story_id']]
        if r['status'] not in ('pending_review', 'accepted', 'rejected'):
            raise ContractError('审阅状态错误')
        if r['status'] == 'accepted':
            if not (r['source_sha256'] == digest(s) and r['reviewer'] and r['reviewed_at']
                    and r['ledger_query_checked'] is True and r['all_variants_checked'] is True):
                raise ContractError('人工签收不完整或已过期')
            accepted.add(s['story_id'])
        if r['status'] == 'rejected' and not r['reason']:
            raise ContractError('拒收缺少原因')
    for split in ('dev', 'test'):
        rows = read_rows(safe_path(root, split + '.jsonl'))
        wanted = [e.to_dict() for e in actual if e.split == split and
                  (split == 'dev' or e.story_id in accepted)]
        if rows != wanted:
            raise ContractError('分区或人工签收门禁失败')
    selected = [s for s in stories if s['split'] == 'test'][:12]
    for size in (2048, 8192, 32768):
        rows = read_rows(safe_path(root, f'paired-{size}.jsonl'))
        if rows != [e.to_dict() for e in generate(selected, manifest['seed'], size)]:
            raise ContractError('配对数据不一致')
    return {'validation': 'ok', 'release_status': 'pending_review',
            'n_story': len(stories), 'formal_test_n_query': len(read_rows(safe_path(root, 'test.jsonl')))}
