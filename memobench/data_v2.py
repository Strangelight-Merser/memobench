"""离线候选数据：先回放事件账本，再渲染公开观察。"""
import hashlib
import json
from pathlib import Path
import random
from datetime import datetime, timedelta, timezone

from .schema_v2 import (Episode, Observation, Probe, Gold, Slot, EvidenceLocation,
                        SandboxReference, ContractError, validate_dataset,
                        OFFICIAL_CAPABILITIES, TECHNICAL_CATEGORIES, REVIEW_STATUSES, ForgetPolicy)
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


def scoring_ledger(events, targets):
    """保留事件依据，另附各目标的作用域与曾经成立的值；不混入其他实体。"""
    rows = [dict(event) for event in events]
    final = {s.name: s for s in truth(events, targets)}
    for target in targets:
        key = target['key']
        previous = []
        for end in range(1, len(events) + 1):
            slot = truth(events[:end], [target])[0]
            if slot.state == 'answer' and slot.value not in previous:
                previous.append(slot.value)
        current = final[key]
        previous = [v for v in previous if current.state != 'answer' or v != current.value]
        rows.append({'slot': key, 'scope': target.get('scope', 'current' if current.state == 'answer' else current.state),
                     'previous_values': previous})
    return rows


def forget_policies(story, slots):
    # sources 是原始创作记录，发布 Gold 只生成统一协议，消费者不做旧格式兼容。
    policies = []
    for source in story.get('forget_policies', []):
        retained = next((s.value for s in slots if s.state == 'answer'
                         and s.name in ('template', 'language')), None)
        policies.append(ForgetPolicy(source['key'], 'literal_disclosure',
                                     [source['value']], retained).to_dict())
    return policies


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
                actions = [{'operation': 'create', 'path': path,
                            'sha256': hashlib.sha256(content.encode()).hexdigest()}]
            gold = Gold(probe.probe_id, slots, evidence, scoring_ledger(story['events'], story['targets']), actions,
                        forget_policies(story, slots), story['technical_categories'],
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
        if s['split'] not in ('dev', 'test') or s['official_capability'] not in OFFICIAL_CAPABILITIES:
            raise ContractError('故事分区或能力错误')
        if not s['technical_categories'] or set(s['technical_categories']) - set(TECHNICAL_CATEGORIES):
            raise ContractError('技术分类错误')
        template, split = s['template_id'], s['split']
        if templates.get(template, split) != split:
            raise ContractError('情节模板跨集合')
        templates[template] = split
        if s['source_type'] != 'authored_synthetic_ai_assisted':
            raise ContractError('来源类型未声明')
        groups = set(range(len(s['utterances'])))
        if any(e['utterance'] not in groups for e in s['events']):
            raise ContractError('事件缺少观察依据')
        if not s['utterances'] or any(len(u) != 2 or not all(isinstance(t, str) and t.strip() for t in u)
                                     or u[0] == u[1] for u in s['utterances']):
            raise ContractError('需要两种措辞')
        if len(s['queries']) != 2 or not all(s['queries']) or s['queries'][0] == s['queries'][1]:
            raise ContractError('需要两种问题措辞')
        if [e['utterance'] for e in s['events']] != sorted(e['utterance'] for e in s['events']):
            raise ContractError('事件与观察顺序不一致')
        keys = [t['key'] for t in s['targets']]
        if not keys or len(keys) != len(set(keys)):
            raise ContractError('目标为空或重复')
        truth(s['events'], s['targets'])


def build_dataset(root, seed=42):
    """构建固定候选文件；不自动签收，不覆盖人工审阅记录。"""
    stories = read_rows(safe_path(root, 'sources.jsonl'))
    validate_sources(stories)
    reviews = safe_path(root, 'review.jsonl')
    existing = read_rows(reviews) if reviews.exists() else []
    known = {r['story_id'] for r in existing}
    if len(known) != len(existing) or known - {s['story_id'] for s in stories}:
        raise ContractError('审阅清单重复或包含未知故事')
    additions = [{'story_id': s['story_id'],
            'source_sha256': digest(s), 'source_type': s['source_type'],
            'evidence_ids': [opaque(s['story_id'], 'observation', i)
                             for i in range(len(s['utterances']))],
            'status': 'pending_review', 'reviewer': None,
            'reviewed_at': None, 'ledger_query_checked': False,
            'all_variants_checked': False, 'reason': '等待人工逐条核对账本、证据和问题'}
            for s in stories if s['story_id'] not in known]
    if additions or not reviews.exists():
        # 已有行原样保留，仅补上新故事，绝不自动签收。
        with reviews.open('a', encoding='utf-8') as handle:
            if reviews.stat().st_size and not reviews.read_bytes().endswith(b'\n'):
                handle.write('\n')
            handle.write(''.join(encode(r) for r in additions))
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
        'generation': 'offline_authored_synthetic_ai_assisted', 'llm_api': 'not_used: offline_only',
        'openkylin': 'NOT_VERIFIED', 'license': 'pending_maintainer_signoff',
        'n_story': len(stories), 'n_query': len(episodes),
        'target_n_story': 60, 'paired_n_story': len(selected),
        'split_counts': {part: sum(s['split'] == part for s in stories) for part in ('dev', 'test')},
        'capability_counts': {cap: {part: sum(s['official_capability'] == cap and s['split'] == part
                                            for s in stories) for part in ('dev', 'test')}
                              for cap in OFFICIAL_CAPABILITIES},
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
        if (r['source_sha256'] != digest(s) or r['source_type'] != s['source_type']
                or r['evidence_ids'] != [opaque(s['story_id'], 'observation', i)
                                        for i in range(len(s['utterances']))]):
            raise ContractError('审阅来源或证据已过期')
        if r['status'] not in REVIEW_STATUSES:
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
    counts = {part: sum(s['split'] == part for s in stories) for part in ('dev', 'test')}
    capability_counts = {cap: {part: sum(s['official_capability'] == cap and s['split'] == part
                                        for s in stories) for part in ('dev', 'test')}
                         for cap in OFFICIAL_CAPABILITIES}
    if (manifest['n_story'] != len(stories) or manifest['n_query'] != len(actual)
            or manifest['split_counts'] != counts or manifest['capability_counts'] != capability_counts
            or manifest['paired_n_story'] != len(selected)
            or manifest['formal_test_n_query'] != len(read_rows(safe_path(root, 'test.jsonl')))):
        raise ContractError('清单数量不一致')
    return {'validation': 'ok', 'release_status': 'pending_review',
            'n_story': len(stories), 'formal_test_n_query': len(read_rows(safe_path(root, 'test.jsonl')))}


def build_review_page(root, destination):
    """生成包含私有真值的本地人工审核页；只导出意见，不修改签收清单。"""
    validate_release(root)
    stories = read_rows(safe_path(root, 'sources.jsonl'))
    reviews = {r['story_id']: r for r in read_rows(safe_path(root, 'review.jsonl'))}
    grouped = {s['story_id']: {} for s in stories}
    for size, filename in ((2048, 'candidates.jsonl'), (8192, 'paired-8192.jsonl'),
                           (32768, 'paired-32768.jsonl')):
        for episode in read_rows(safe_path(root, filename)):
            grouped[episode['story_id']].setdefault(str(size), []).append(episode)
    payload = {'capabilities': OFFICIAL_CAPABILITIES,
               'source_sha256': hashlib.sha256(safe_path(root, 'sources.jsonl').read_bytes()).hexdigest(),
               'stories': [{'source': s, 'review': reviews[s['story_id']],
                            'episodes': grouped[s['story_id']]} for s in stories]}
    # JSON 进入 script 数据块前转义 HTML 分隔符；界面数据一律 textContent。
    data = encode(payload).replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e')
    page = REVIEW_HTML.replace('__REVIEW_DATA__', data)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(page, encoding='utf-8')


REVIEW_HTML = r'''<!doctype html>
<html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MemoBench · 候选数据人工审核</title>
<style>
*{box-sizing:border-box}body{margin:0;height:100dvh;display:grid;grid-template-rows:auto auto minmax(0,1fr) auto;background:#f2f4f7;color:#172537;font:14px/1.6 system-ui,sans-serif}
header{padding:12px 24px;background:#152c42;color:white}h1{font-size:20px;margin:0}header p{margin:3px 0;color:#ccd9e5}
nav{display:flex;gap:12px;align-items:center;flex-wrap:wrap;padding:12px 24px;background:white;border-bottom:1px solid #cbd5df}
button,select,input,textarea{font:inherit}button,select{padding:6px 10px}button{cursor:pointer}button:disabled{cursor:default}
main{min-height:0;display:grid;grid-template-columns:1fr 1.25fr 1fr;gap:12px;padding:12px 24px}
section{background:white;border:1px solid #d3dce5;border-radius:8px;padding:14px;overflow:auto}h2{font-size:16px;margin:0 0 10px}h3{font-size:14px;margin:12px 0 4px}
pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f5f7fa;padding:9px;margin:6px 0;font:12px/1.55 ui-monospace,monospace}
.observation{padding:9px;border-left:3px solid #44829a;margin:8px 0;background:#f1f7fa;white-space:pre-wrap;overflow-wrap:anywhere}
small{display:block;color:#536779;overflow-wrap:anywhere}footer{padding:10px 24px;background:white;border-top:1px solid #cbd5df}
.reviewline{display:flex;align-items:center;gap:14px;flex-wrap:wrap}textarea{width:100%;height:50px;margin-top:6px;padding:6px}#notice{color:#9b321f;min-height:23px}label{cursor:pointer}
@media(max-width:850px){body{height:auto;display:block}main{height:auto;grid-template-columns:1fr}section{max-height:60vh}header,nav,footer{padding:12px}main{padding:12px}}
</style>
<header><h1>MemoBench · 候选数据人工审核</h1><p>60 个故事 · 12 开发 / 48 测试候选 · 含私有真值，仅供审阅。导出不会改写数据或批准正式发布。</p></header>
<nav><button id="prev">上一故事</button><select id="story" aria-label="选择故事"></select><button id="next">下一故事</button>
<span id="progress"></span><label>审阅者 <input id="reviewer" placeholder="实际审阅者" size="12"></label><button id="export">导出审核 JSON</button></nav>
<main>
<section><h2>事件账本与来源</h2><div id="meta"></div><h3>按时间排列的事件</h3><div id="ledger"></div><h3>目标槽位</h3><pre id="targets"></pre></section>
<section><h2>会话与两种等义表达</h2><label>字符规模 <select id="size" aria-label="字符规模"></select></label><div id="sessions"></div></section>
<section><h2>问题、真值与证据</h2><div id="questions"></div><h3>账本计算真值</h3><pre id="gold"></pre><h3>证据位置</h3><pre id="evidence"></pre><h3>文件动作与遗忘策略</h3><pre id="actions"></pre></section>
</main>
<footer><div class="reviewline">
<label><input type="radio" name="decision" value="pending_review"> 待审</label><label><input type="radio" name="decision" value="accepted"> 通过</label><label><input type="radio" name="decision" value="rejected"> 拒收</label>
<label><input type="checkbox" id="ledgerChecked"> 账本与问题一致</label><label><input type="checkbox" id="variantsChecked"> 两种表述及适用配对负载已检查</label>
</div><textarea id="reason" aria-label="审核原因" placeholder="通过或拒收原因（必填）；拒收应指出具体事件、措辞或真值问题，不能因模型答错而拒收。"></textarea><div id="notice" role="status">修改仅保存在当前页面内存中，关闭前请导出。三档负载仅适用于选定的 12 个测试故事。</div></footer>
<script type="application/json" id="dataset">__REVIEW_DATA__</script>
<script>
'use strict';
const dataset=JSON.parse(document.getElementById('dataset').textContent);
const $=id=>document.getElementById(id);
const records=dataset.stories.map(s=>({...s.review}));
let current=0;
const json=x=>JSON.stringify(x,null,2);
function text(parent,tag,content,className){const e=document.createElement(tag);e.textContent=content;if(className)e.className=className;parent.append(e);return e;}
function count(){ $('progress').textContent=`${current+1} / ${records.length} · 通过 ${records.filter(r=>r.status==='accepted').length} · 拒收 ${records.filter(r=>r.status==='rejected').length}`; }
function save(){
 const r=records[current];
 const status=document.querySelector('input[name="decision"]:checked').value;
 const checked=$('ledgerChecked').checked, variants=$('variantsChecked').checked, reason=$('reason').value;
 if(r.status!==status || r.ledger_query_checked!==checked || r.all_variants_checked!==variants || r.reason!==reason){
  Object.assign(r,{status,ledger_query_checked:checked,all_variants_checked:variants,reason,
    reviewer:status==='pending_review'?null:$('reviewer').value.trim(),reviewed_at:status==='pending_review'?null:new Date().toISOString()});
 }
 count();
}
function renderSessions(){
 const item=dataset.stories[current], episodes=item.episodes[$('size').value];
 $('sessions').replaceChildren();$('questions').replaceChildren();
 episodes.forEach((e,i)=>{
  text($('sessions'),'h3',`表达 ${i+1} · ${e.variant_id}`);
  const ids=new Set(e.golds[0].evidence.map(v=>v.observation_id));
  e.session_ids.forEach((sid,j)=>{
   text($('sessions'),'h3',`会话 ${j+1} · ${sid}`);
   const observations=e.observations.filter(o=>o.session_id===sid);
   observations.filter(o=>ids.has(o.observation_id)).forEach(o=>{
    text($('sessions'),'small',`${o.observation_id} · ${o.role} · ${o.observed_at}`);
    text($('sessions'),'div',o.text,'observation');
   });
   const details=document.createElement('details');
   text(details,'summary',`完整会话（${observations.length} 条，含填充噪声，按时间顺序）`);
   observations.forEach(o=>text(details,'pre',`${o.observation_id} · ${o.observed_at}\n${o.text}`));
   $('sessions').append(details);
  });
  text($('questions'),'h3',`表达 ${i+1} 的问题`);text($('questions'),'div',e.probes[0].query);
 });
 const gold=episodes[0].golds[0];
 $('gold').textContent=json(gold.slots);$('evidence').textContent=json(gold.evidence);
 $('actions').textContent=json({expected_actions:gold.expected_actions,forget_policies:gold.forget_policies});
}
function render(){
 const item=dataset.stories[current],s=item.source,r=records[current];$('story').value=String(current);
 $('meta').replaceChildren();
 text($('meta'),'div',`${dataset.capabilities[s.official_capability]} · ${s.split==='dev'?'开发':'测试候选'} · 原始状态 ${item.review.status}`);
 text($('meta'),'small',`故事 ${s.story_id}\n情节模板 ${s.template_id}`);
 text($('meta'),'pre',json({source_type:s.source_type,source_sha256:r.source_sha256,technical_categories:s.technical_categories}));
 $('ledger').replaceChildren();
 s.events.forEach((e,i)=>text($('ledger'),'pre',json({event:i+1,...e,evidence_id:r.evidence_ids[e.utterance]})));
 $('targets').textContent=json(s.targets);
 $('size').replaceChildren();Object.keys(item.episodes).forEach(n=>{const o=text($('size'),'option',`${n} 字符`);o.value=n;});
 document.querySelectorAll('input[name="decision"]').forEach(el=>el.checked=el.value===r.status);
 $('ledgerChecked').checked=r.ledger_query_checked;$('variantsChecked').checked=r.all_variants_checked;$('reason').value=r.reason;
 $('prev').disabled=current===0;$('next').disabled=current===records.length-1;
 renderSessions();count();document.querySelectorAll('section').forEach(s=>s.scrollTop=0);
}
dataset.stories.forEach((item,i)=>{const s=item.source;const o=text($('story'),'option',`${i+1}. ${dataset.capabilities[s.official_capability]} · ${s.template_id}`);o.value=i;});
$('prev').onclick=()=>{save();current--;render();};$('next').onclick=()=>{save();current++;render();};
$('story').onchange=()=>{save();current=Number($('story').value);render();};$('size').onchange=renderSessions;
document.querySelectorAll('input[name="decision"],#ledgerChecked,#variantsChecked').forEach(e=>e.onchange=save);
$('reason').oninput=save;
$('export').onclick=()=>{
 save();const reviewer=$('reviewer').value.trim();
 for(let i=0;i<records.length;i++){
  const r=records[i];if(r.status==='pending_review')continue;
  if(!reviewer||!r.reason.trim()||r.reason===dataset.stories[i].review.reason||
     (r.status==='accepted'&&(!r.ledger_query_checked||!r.all_variants_checked))){
   $('notice').textContent=`第 ${i+1} 个故事：请填写审阅者、具体原因；通过时须勾选两项核对。`;return;
  }
 }
 const output={schema_version:'0.2',source_sha256:dataset.source_sha256,exported_at:new Date().toISOString(),
  records:records.map(r=>r.status==='pending_review'?r:{...r,reviewer})};
 const url=URL.createObjectURL(new Blob([json(output)+'\n'],{type:'application/json;charset=utf-8'}));
 const a=document.createElement('a');a.href=url;a.download='memobench-human-review.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
 $('notice').textContent='审核 JSON 已生成本地下载；仓库数据未改变。维护者核对源摘要后再合入 review.jsonl 并重建。';
};
render();
</script></html>
'''
