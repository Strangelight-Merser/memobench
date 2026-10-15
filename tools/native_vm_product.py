#!/usr/bin/env python3
"""VM-side native product bridge. Install outside the evaluator's dataset tree.

Consumes the existing public protocol envelope on stdin. Only user observations
are supported by these CLI bindings; other roles fail explicitly. Each invocation
uses a mount/PID namespace with only this case writable. No evaluator or gold
files are mounted. OpenClaw uses its explicitly selected embedded CLI; optional
Gateway post-turn flush is unsupported, never inferred from a successful answer.
"""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from uuid import uuid4

BASE = Path.home() / 'memobench-native'
GUEST = '/home/mb/case'
PHASE_POLICIES = {
    'observe': 'MemoBench phase: observation ingestion. The user message is a historical observation to remember, not an instruction to execute tasks now. Preserve its facts, preferences and procedures using native memory/profile. Do not create or modify task deliverables during this phase. The task workspace is read-only; native memory remains writable. Complete this turn once the observation has been ingested.',
    'query': 'MemoBench phase: task query. Answer or execute the current user query using native memory and the previous observations. The task workspace is writable and normal task tools are available. Native memory/profile remains enabled. Respect the exact output format required by the current query. When asked to output only an answer or identifier, add no punctuation, explanation, or Markdown.',
}

def now():
    return datetime.now(timezone.utc).isoformat()

def save(path, obj):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2))
    tmp.replace(path)

def sandbox(home, product, *, task_writable=True):
    runtime = BASE / ('agent-runtime' if product == 'kylin' else 'openclaw')
    args = ['bwrap', '--die-with-parent', '--new-session', '--unshare-all', '--share-net']
    for path in ['/usr', '/bin', '/lib', '/etc']:
        args += ['--ro-bind', path, path]
    args += ['--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp', '--dir', '/run',
             '--ro-bind', str(runtime), str(runtime), '--bind', str(home), GUEST,
             '--setenv', 'HOME', GUEST, '--setenv', 'XDG_CONFIG_HOME', GUEST + '/.config',
             '--setenv', 'XDG_CACHE_HOME', GUEST + '/.cache', '--chdir', GUEST + '/workspace']
    if product == 'openclaw' and (home / 'agent-workspace/AGENTS.md').is_file():
        args += ['--ro-bind', str(home / 'agent-workspace/AGENTS.md'), GUEST + '/agent-workspace/AGENTS.md']
    if not task_writable:
        # A separate mount prevents the product from changing task bytes during ingestion.
        args += ['--ro-bind', str(home / 'workspace'), GUEST + '/workspace']
    if product == 'openclaw':
        node = BASE / 'node-v24.22.0-linux-arm64'
        args += ['--ro-bind', str(node), str(node), '--setenv', 'PATH', str(node / 'bin') + ':/usr/bin:/bin']
    return args + ['--']

def inventory(home):
    return {p.relative_to(home).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in home.rglob('*') if p.is_file() and not p.is_symlink()}

def configure(home, product, provider):
    (home / 'workspace').mkdir(parents=True)
    if product == 'kylin':
        state = home / '.kylin-agent-runtime'
        state.mkdir()
        # JSON is valid YAML; credentials are supplied only in the process env.
        save(state / 'config.yaml', {
            'model': {'provider': 'custom', 'default': provider['model'], 'base_url': provider['base_url']},
            'agent': {'max_turns': 12}, 'max_tokens': 1024,
            'user_profile': {'precheck_enabled': True, 'max_attempts': 2},
            'memory': {'memory_enabled': True, 'user_profile_enabled': True},
        })
    else:
        state = home / '.openclaw'
        state.mkdir()
        (home / 'agent-workspace').mkdir()
        save(state / 'openclaw.json', {
            'models': {'providers': {'deepseek': {
                'baseUrl': provider['base_url'], 'apiKey': '${DEEPSEEK_API_KEY}',
                'api': 'openai-completions', 'models': [{'id': provider['model'], 'name': provider['model'],
                                                      'contextWindow': 65536, 'maxTokens': 1024}]}}},
            'agents': {'defaults': {'model': {'primary': 'deepseek/' + provider['model']},
                                   'workspace': GUEST + '/agent-workspace',
                                   'cwd': GUEST + '/workspace', 'skipBootstrap': True,
                                   'timeoutSeconds': 100}},
            'tools': {'allow': ['read', 'write', 'edit', 'memory_search', 'memory_get'],
                      'toolSearch': False, 'codeMode': False},
        })

def prepare_phase_policy(home, product, phase):
    policy = PHASE_POLICIES[phase]
    if product == 'kylin':
        source = 'HERMES_EPHEMERAL_SYSTEM_PROMPT'
    else:
        path = home / 'agent-workspace/AGENTS.md'
        path.write_text(policy + '\n')
        source = 'agent-workspace/AGENTS.md'
    return {'phase': phase, 'source': source, 'text': policy,
            'sha256': hashlib.sha256(policy.encode()).hexdigest()}


def invoke(home, product, provider, text, session, phase):
    if phase not in ('observe', 'query'):
        raise ValueError('invalid invocation phase')
    env = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'TERM': 'dumb',
           'HOME': str(Path.home()), 'DEEPSEEK_API_KEY': provider['api_key'],
           'HERMES_HOME': GUEST + '/.kylin-agent-runtime',
           'OPENCLAW_STATE_DIR': GUEST + '/.openclaw',
           'OPENCLAW_CONFIG_PATH': GUEST + '/.openclaw/openclaw.json'}
    if product == 'kylin':
        env['HERMES_EPHEMERAL_SYSTEM_PROMPT'] = PHASE_POLICIES[phase]
        env['OPENAI_API_KEY'] = provider['api_key']
        env['OPENAI_BASE_URL'] = provider['base_url']
        argv = [str(BASE / 'agent-runtime/.venv/bin/kylin-agent-runtime'), 'chat', '-Q',
                '--provider', 'custom', '--model', provider['model'], '--toolsets',
                'memory' if phase == 'observe' else 'memory,file',
                '--max-turns', '12', '-q', text]
        if session.get('product_session'):
            argv += ['--resume', session['product_session']]
    else:
        session.setdefault('product_session', str(uuid4()))
        argv = [str(BASE / 'openclaw/node_modules/.bin/openclaw'), 'agent', '--local',
                '--session-id', session['product_session'], '--message', text, '--json',
                '--thinking', 'off', '--timeout', '100']
    native_log = home / '.kylin-agent-runtime/logs/agent.log'
    log_offset = native_log.stat().st_size if native_log.exists() else 0
    def diagnostics():
        if product != 'kylin' or not native_log.exists():
            return ''
        with native_log.open('rb') as stream:
            stream.seek(log_offset)
            return stream.read().decode(errors='replace').replace(provider['api_key'], '[REDACTED]')
    started_at = time.time()
    try:
        completed = subprocess.run(sandbox(home, product, task_writable=phase == 'query') + argv, env=env,
                                   capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired as exc:
        def clean(value):
            if isinstance(value, bytes):
                value = value.decode(errors='replace')
            return (value or '').replace(provider['api_key'], '[REDACTED]')
        return {'ok': False, 'exit_code': None, 'timeout': True, 'stdout': clean(exc.stdout),
                'stderr': clean(exc.stderr), 'answer': None, 'finished_at': now(),
                'native_log': diagnostics()}

    stdout = completed.stdout.replace(provider['api_key'], '[REDACTED]')
    stderr = completed.stderr.replace(provider['api_key'], '[REDACTED]')
    result = {'exit_code': completed.returncode, 'stdout': stdout, 'stderr': stderr,
              'finished_at': now(), 'mode': 'cli' if product == 'kylin' else 'embedded_explicit',
              'product_session': session.get('product_session'), 'native_log': diagnostics(),
              'product_argv': argv}
    if product == 'kylin':
        matches = re.findall(r'^session_id:\s*(\S+)', stderr, re.M)
        if matches:
            session['product_session'] = matches[-1]
            result['product_session'] = matches[-1]
        result['answer'] = None
        if completed.returncode == 0 and matches:
            # This fork emits debug lines even in quiet mode. Read the committed
            # native assistant message instead of guessing a stdout suffix.
            database = safe_case_path(home, home / '.kylin-agent-runtime/state.db')
            with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as db:
                row = db.execute('SELECT content FROM messages WHERE session_id=? AND role=? AND timestamp>=? '
                                 "AND (tool_calls IS NULL OR tool_calls='[]') ORDER BY id DESC LIMIT 1",
                                 (matches[-1], 'assistant', started_at)).fetchone()
                if row:
                    result['answer'] = row[0]
                    result['answer_source'] = 'native state.db final assistant message'
                prompt = db.execute('SELECT system_prompt FROM sessions WHERE id=?', (matches[-1],)).fetchone()
                profile_block = re.search(r'<user_profile_data>.*?</user_profile_data>',
                                          (prompt[0] or '') if prompt else '', re.S)
                result['native_profile_prompt'] = profile_block.group(0) if profile_block else None

            # The pinned CLI exits zero even when its completion review pauses.
            # task_runs is not populated by quiet CLI; use the native per-turn
            # diagnostic, restricted to bytes appended during this invocation.
            reasons = re.findall(r'Turn ended: reason=(.*?) model=.*? session=' +
                                 re.escape(matches[-1]) + r'(?:\s|$)', result['native_log'])
            result['task_reason'] = reasons[-1] if reasons else None
            result['task_status'] = ('completed' if result['task_reason'] ==
                                     'completion_review:completed' else 'unverified_or_incomplete')
        result['profile_completed'] = bool(re.search(
            r'User-profile extraction (?:LLM call completed:|skipped: precheck found no profile update)',
            result['native_log']))
        result['ok'] = (completed.returncode == 0 and bool(matches) and bool(result['answer'])
                        and result.get('task_status') == 'completed' and result['profile_completed'])
    else:
        try:
            raw = json.loads(stdout)
            result['answer'] = '\n'.join(p.get('text', '') for p in raw.get('payloads', []))
            result['meta'] = raw.get('meta')
            result['ok'] = completed.returncode == 0 and bool(result['answer']) and not (raw.get('meta') or {}).get('error')
        except (ValueError, TypeError):
            result.update(ok=False, answer=None)
    return result

def safe_case_path(home, path):
    home, path = Path(home), Path(path)
    if home.is_symlink() or not path.resolve().is_relative_to(home.resolve()):
        raise ValueError('native path outside case')
    relative = path.relative_to(home)
    cursor = home
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError('linked native path refused')
    return path


def workspace_snapshot(home):
    """Bridge-owned bytes, workspace only. Never follow links or truncate evidence."""
    import base64
    import stat
    root = safe_case_path(home, home / 'workspace')
    if root.is_symlink() or not root.is_dir():
        raise ValueError('unsafe workspace root')
    files, total = {}, 0
    for path in sorted(root.rglob('*')):
        info = path.lstat()
        if stat.S_ISDIR(info.st_mode):
            continue
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError('unsafe workspace artifact')
        if info.st_size > 256 * 1024:
            raise ValueError('workspace evidence limit exceeded')
        data = path.read_bytes()
        total += len(data)
        if total > 512 * 1024 or len(data) != info.st_size:
            raise ValueError('workspace evidence incomplete')
        files[path.relative_to(root).as_posix()] = {'sha256': hashlib.sha256(data).hexdigest(),
            'size': len(data), 'content_base64': base64.b64encode(data).decode('ascii')}
    return files


def native_records(home, product):
    """Read fixed products' native persistence, never export internal databases."""
    if product == 'kylin':
        database = safe_case_path(home, home / '.kylin-agent-runtime/state.db')
        if not database.exists():
            return []
        if database.is_symlink() or database.stat().st_nlink != 1:
            raise ValueError('unsafe native transcript')
        with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as db:
            columns = {r[1] for r in db.execute('PRAGMA table_info(messages)')}
            if not {'id','session_id','role','content','tool_call_id','tool_calls','tool_name'} <= columns:
                raise ValueError('native transcript schema incomplete')
            return [{'source': 'kylin/messages', 'position': r[0], 'session_id': r[1],
                     'message': {'role': r[2], 'content': r[3], 'tool_call_id': r[4],
                                 'tool_calls': json.loads(r[5]) if r[5] else [], 'tool_name': r[6]}}
                    for r in db.execute('SELECT id,session_id,role,content,tool_call_id,tool_calls,tool_name FROM messages ORDER BY id')]
    # Pinned OpenClaw stores canonical messages in transcript_events. Node's
    # bundled SQLite/zstd reader is used because Python SQLite lacks JSONB/zstd.
    root = safe_case_path(home, home / '.openclaw')
    databases = []
    if root.exists():
        for database in sorted(root.rglob('*.sqlite')):
            safe_case_path(home, database)
            if database.is_symlink() or database.stat().st_nlink != 1:
                raise ValueError('unsafe native transcript')
            databases.append(str(database))
    if not databases:
        return []
    script = r'''const {DatabaseSync}=require('node:sqlite');const z=require('node:zlib');
const paths=JSON.parse(process.argv[1]);const rows=[];
for(const path of paths){const db=new DatabaseSync(path,{readOnly:true});
if(!db.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name='transcript_events'").get()){db.close();continue;}
const names=new Set(db.prepare('PRAGMA table_info(transcript_events)').all().map(x=>x.name));
if(!['seq','session_id','event_json','event_zstd'].every(x=>names.has(x)))throw Error('schema incomplete');
for(const row of db.prepare(`SELECT seq,session_id,CASE WHEN typeof(event_json)='blob' THEN json(event_json) ELSE event_json END AS event_json,event_zstd FROM transcript_events ORDER BY seq`).all()){
const text=row.event_json??z.zstdDecompressSync(row.event_zstd).toString('utf8');
const event=JSON.parse(text);rows.push({source:path.split('/.openclaw/')[1],position:row.seq,session_id:row.session_id,message:event.message??event});}
db.close();}process.stdout.write(JSON.stringify(rows));'''
    completed = subprocess.run([str(BASE / 'node-v24.22.0-linux-arm64/bin/node'), '-e', script,
                                json.dumps(databases)], capture_output=True, text=True, timeout=15)
    if completed.returncode:
        raise ValueError('native transcript read incomplete')
    return json.loads(completed.stdout)


def transcript_checkpoint(records):
    encoded = json.dumps(records, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()
    return {'count': len(records), 'prefix_sha256': hashlib.sha256(encoded).hexdigest()}


def native_file_audit(records, checkpoint, product_session):
    prefix = records[:checkpoint['count']]
    if transcript_checkpoint(prefix) != checkpoint:
        raise ValueError('native transcript replaced or truncated')
    calls, results, call_order, result_order = {}, {}, {}, {}
    def register_call(call_id, value, order):
        if call_id in calls:
            raise ValueError('duplicate native tool call id')
        calls[call_id] = value
        call_order[call_id] = order
    for order, row in enumerate(records[checkpoint['count']:]):
        if row['session_id'] != product_session:
            continue
        message = row['message']
        if message.get('role') == 'assistant':
            for call in message.get('tool_calls') or []:
                function = call['function']
                register_call(call['id'], (function['name'], json.loads(function['arguments']), row), order)
            content = message.get('content')
            if isinstance(content, list):
                for block in content:
                    if block.get('type') == 'toolCall':
                        register_call(block['id'], (block['name'], block['arguments'], row), order)
        if message.get('role') in ('tool', 'toolResult'):
            key = message.get('tool_call_id') or message.get('toolCallId')
            if key:
                if key in results:
                    raise ValueError('duplicate native tool result id')
                results[key] = row
                result_order[key] = order
    events, memory_events = [], []
    for call_id, (name, arguments, source) in calls.items():
        if name not in ('write_file', 'write', 'edit', 'patch', 'read_file', 'read'):
            continue
        target = arguments.get('path') or arguments.get('file_path')
        if not isinstance(target, str):
            raise ValueError('native file path absent')
        is_read = name in ('read_file', 'read')
        memory_root = GUEST + '/agent-workspace'
        is_memory = target.startswith(memory_root + '/')
        if is_memory:
            target = target[len(memory_root) + 1:]
        workspace_root_read = is_read and target == GUEST + '/workspace'
        if workspace_root_read:
            target = '.'
        elif target.startswith(GUEST + '/workspace/'):
            target = target[len(GUEST + '/workspace/'):]
        parts = target.split('/')
        if (not workspace_root_read and
                (target.startswith('/') or any(p in ('', '.', '..') for p in parts) or '\\' in target)):
            raise ValueError('native tool path outside workspace')
        if call_id not in results:
            raise ValueError('native tool result missing')
        result = results[call_id]
        if result_order[call_id] <= call_order[call_id]:
            raise ValueError('native tool result precedes call')
        message = result['message']
        if message.get('tool_name') and message['tool_name'] != name:
            raise ValueError('native tool name mismatch')
        content = message.get('content')
        failed = message.get('isError') is True
        if isinstance(content, str):
            if is_read:
                # File bytes may be ordinary text or any JSON value.
                try:
                    decoded = json.loads(content)
                except ValueError:
                    decoded = None
            else:
                decoded = json.loads(content)
            if is_read:
                failed = failed or (isinstance(decoded, dict) and bool(decoded.get('error')))
            elif decoded.get('error'):
                failed = True
        if failed and not is_read:
            raise ValueError('native file tool failed')
        (memory_events if is_memory else events).append({'call_id': call_id, 'tool': name, 'path': target,
                       'succeeded': not failed,
                       'operation': 'write' if name in ('write_file', 'write', 'edit', 'patch') else 'read',
                       'arguments': arguments, 'native_call': {'source': source['source'], 'position': source['position'],
                           'session_id': source['session_id'], 'tool_call': {'id': call_id, 'name': name, 'arguments': arguments}},
                       'native_result': result})
    return {'product_session': product_session, 'checkpoint': checkpoint,
            'terminal': transcript_checkpoint(records), 'events': events,
            'memory_events': memory_events, 'complete': True}


def query_artifacts(home, product, checkpoint, evidence, product_session):
    """Keep diagnostic evidence even when strict artifact auditing fails."""
    artifacts = {'binding': checkpoint['binding'], 'baseline': checkpoint['baseline'],
                 'after': None, 'complete': False, 'audit': None,
                 'native_records': None, 'audit_stage': 'workspace_snapshot'}
    fixed_reasons = {
        'native path outside case': 'native_path_outside_case',
        'linked native path refused': 'linked_native_path_refused',
        'unsafe workspace root': 'unsafe_workspace_root',
        'unsafe workspace artifact': 'unsafe_workspace_artifact',
        'workspace evidence limit exceeded': 'workspace_evidence_limit_exceeded',
        'workspace evidence incomplete': 'workspace_evidence_incomplete',
        'unsafe native transcript': 'unsafe_native_transcript',
        'native transcript schema incomplete': 'native_transcript_schema_incomplete',
        'native transcript read incomplete': 'native_transcript_read_incomplete',
        'native transcript replaced or truncated': 'native_transcript_replaced_or_truncated',
        'duplicate native tool call id': 'duplicate_native_tool_call_id',
        'duplicate native tool result id': 'duplicate_native_tool_result_id',
        'native file path absent': 'native_file_path_absent',
        'native tool path outside workspace': 'native_tool_path_outside_workspace',
        'native tool result missing': 'native_tool_result_missing',
        'native tool result precedes call': 'native_tool_result_precedes_call',
        'native tool name mismatch': 'native_tool_name_mismatch',
        'native file tool failed': 'native_file_tool_failed',
    }
    try:
        artifacts['after'] = workspace_snapshot(home)
        if evidence['ok']:
            artifacts['audit_stage'] = 'native_records'
            artifacts['native_records'] = native_records(home, product)
            artifacts['audit_stage'] = 'native_file_audit'
            artifacts['audit'] = native_file_audit(artifacts['native_records'],
                                                  checkpoint['transcript'], product_session)
            artifacts['complete'] = True
    except Exception as exc:
        # Never export arbitrary exception messages: they may contain file bytes,
        # credentials, or host paths. Only exact bridge-owned ValueError reasons.
        artifacts['audit_error_type'] = type(exc).__name__
        reason = str(exc) if type(exc) is ValueError else None
        artifacts['audit_error_reason_code'] = fixed_reasons.get(reason, 'unexpected_audit_error')
    return artifacts


def dispatch(request, product):
    if request.get('bridge_sha256') != hashlib.sha256(Path(__file__).read_bytes()).hexdigest():
        raise ValueError('bridge version mismatch')
    namespace = request['namespace']
    if not re.fullmatch(r'[a-f0-9]{32}', namespace):
        raise ValueError('namespace must be a fresh UUID hex')
    root = BASE / 'cases' / namespace
    home = root / 'home'
    method, operation, payload = request['method'], request['operation_id'], request['payload']
    control_path = root / 'control.json'
    if method == 'reset_case':
        root.mkdir(parents=True, exist_ok=False)
        home.mkdir(mode=0o700)
        provider = json.loads((BASE / 'provider.json').read_text())
        configure(home, product, provider)
        control = {'run_id': request.get('run_id'), 'product': product, 'episode_id': payload['episode_id'], 'variant_id': payload['variant_id'],
                   'session': None, 'sessions': {}, 'operations': {}, 'uncertain': False,
                   'bridge_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    else:
        control = json.loads(control_path.read_text())
    if control['product'] != product:
        raise ValueError('product mismatch')
    if (payload['episode_id'], payload['variant_id']) != (control['episode_id'], control['variant_id']):
        raise ValueError('case mismatch')
    if method in ('artifact_checkpoint', 'artifact_evidence'):
        if payload['session_id'] != control['session'] or request.get('run_id') != control.get('run_id'):
            raise ValueError('artifact scope mismatch')
        target = payload['query_operation']
        binding = {'run': control['run_id'], 'namespace': namespace,
                   'episode_id': payload['episode_id'], 'variant_id': payload['variant_id'],
                   'session_id': payload['session_id'], 'operation_id': target,
                   'bridge_sha256': control['bridge_sha256']}
        if method == 'artifact_checkpoint':
            if control['uncertain'] or target in control.get('artifact_checkpoints', {}):
                raise ValueError('checkpoint cannot replay')
            checkpoint = {'binding': binding, 'baseline': workspace_snapshot(home),
                          'transcript': transcript_checkpoint(native_records(home, product))}
            control.setdefault('artifact_checkpoints', {})[target] = checkpoint
            save(control_path, control)
            return checkpoint
        entry = control['operations'][target]
        if entry['method'] != 'query' or entry.get('session_id') != payload['session_id']:
            raise ValueError('artifact query operation mismatch')
        saved = json.loads((root / entry['evidence']).read_text())
        artifacts = saved['artifacts']
        if artifacts['binding'] != binding:
            raise ValueError('artifact evidence scope mismatch')
        return artifacts
    if operation in control['operations']:
        raise ValueError('operation already attempted; do not replay')
    if control['uncertain'] and method != 'close':
        raise ValueError('previous operation uncertain')
    control['operations'][operation] = {'status': 'started', 'method': method, 'session_id': payload.get('session_id'), 'at': now()}
    save(control_path, control)
    response = {'operation_id': operation, 'status': 'ready', 'usage': None}
    evidence = None
    try:
        if method == 'reset_case':
            # Actual process-level denial; the secret itself is never read by this check.
            sentinel = root / 'private-canary.txt'
            sentinel.write_text(uuid4().hex)
            check = subprocess.run(sandbox(home, product) + ['/usr/bin/python3', '-c',
                'import os; assert not os.path.exists(' + repr(str(sentinel)) + '); '
                "assert os.path.isdir('/home/mb/case/workspace'); "
                "assert not os.path.exists('/home/mb/memobench-native/provider.json'); "
                "assert not os.path.exists('/Users'); print('isolated')"],
                capture_output=True, text=True, timeout=10)
            if check.returncode or check.stdout.strip() != 'isolated':
                raise RuntimeError('mount isolation probe failed')
            evidence = {'mount_isolation': 'passed', 'stdout': check.stdout,
                        'private_sentinel_present_outside': sentinel.is_file(), 'private_sentinel_visible_inside': False}
        elif method == 'begin_session':
            sid = payload['session_id']
            if control['session'] is not None or sid in control['sessions']:
                raise ValueError('invalid session transition')
            control['session'] = sid
            control['sessions'][sid] = {}
        elif method in ('observe', 'query'):
            if payload['session_id'] != control['session']:
                raise ValueError('session mismatch')
            if method == 'observe' and payload['role'] != 'user':
                raise ValueError('CLI binding supports user observations only')
            session = control['sessions'][control['session']]
            provider = json.loads((BASE / 'provider.json').read_text())
            checkpoint = control.get('artifact_checkpoints', {}).get(operation) if method == 'query' else None
            if checkpoint and (checkpoint['baseline'] != workspace_snapshot(home) or
                    checkpoint['transcript'] != transcript_checkpoint(native_records(home, product))):
                raise ValueError('artifact baseline changed before query')
            phase_policy = prepare_phase_policy(home, product, method)
            task_before = workspace_snapshot(home) if method == 'observe' else None
            files_before = inventory(home)
            evidence = invoke(home, product, provider, payload['text'] if method == 'observe' else payload['query'], session, method)
            evidence['phase_policy'] = {'phase': method, 'task_workspace': GUEST + '/workspace',
                'task_workspace_writable': method == 'query',
                'memory_workspace': GUEST + '/agent-workspace' if product == 'openclaw' else None,
                'kylin_toolsets': ('memory' if method == 'observe' else 'memory,file') if product == 'kylin' else None,
                'public_text_modified': False, 'system_policy': phase_policy,
                'public_text': payload['text'] if method == 'observe' else payload['query'],
                'public_text_sha256': hashlib.sha256((payload['text'] if method == 'observe' else payload['query']).encode()).hexdigest()}
            if method == 'observe':
                evidence['task_workspace_before'] = task_before
                evidence['task_workspace_after'] = workspace_snapshot(home)
                evidence['task_workspace_unchanged'] = task_before == evidence['task_workspace_after']
                if not evidence['task_workspace_unchanged']:
                    evidence['ok'] = False
                    evidence['phase_error'] = 'observation_modified_task_workspace'
            evidence['files_before'] = files_before
            evidence['files_after'] = inventory(home)
            if checkpoint:
                evidence['artifacts'] = query_artifacts(home, product, checkpoint, evidence,
                                                       session.get('product_session'))
            if not evidence['ok']:
                raise RuntimeError('product call failed; see operation evidence')
            if method == 'query':
                response = {'episode_id': payload['episode_id'], 'variant_id': payload['variant_id'],
                            'session_id': payload['session_id'], 'probe_id': payload['probe_id'],
                            'status': 'ok', 'text': evidence['answer'], 'answered_at': now()}
        elif method == 'end_session':
            if payload['session_id'] != control['session']:
                raise ValueError('session mismatch')
            # Every turn has already exited. No optional post-turn/Gateway flush is claimed.
            control['session'] = None
            evidence = {'files': inventory(home), 'process_completion': 'waited', 'flush': 'unsupported'}
            if product == 'kylin':
                # Native read-only inspection; no profile key is exported.
                checked = subprocess.run(sandbox(home, product) + [
                    str(BASE / 'agent-runtime/.venv/bin/python'), '-c',
                    'from agent.user_profile.inspection import load_profile; '
                    'print(load_profile(profile_home="' + GUEST +
                    '/.kylin-agent-runtime/user_profile").model_dump_json())'],
                    capture_output=True, text=True, timeout=15)
                if checked.returncode:
                    raise RuntimeError('native profile inspection failed')
                evidence['profile'] = json.loads(checked.stdout)

        elif method == 'close':
            evidence = {'files': inventory(home), 'process_completion': 'waited'}
            shutil.rmtree(home)
            (root / 'private-canary.txt').unlink(missing_ok=True)
            control['closed'] = True
        else:
            raise ValueError('unknown method')
        control['operations'][operation]['status'] = 'completed'
    except Exception as exc:
        control['uncertain'] = True
        control['operations'][operation].update(status='failed', error=str(exc))
        response = {'operation_id': operation, 'status': 'unknown', 'usage': None}
        if method == 'query':
            response = {'episode_id': payload['episode_id'], 'variant_id': payload['variant_id'],
                        'session_id': payload['session_id'], 'probe_id': payload['probe_id'],
                        'status': 'timeout' if evidence and evidence.get('timeout') else 'error', 'text': None, 'answered_at': now()}
    if evidence is not None:
        name = hashlib.sha256(operation.encode()).hexdigest() + '.json'
        evidence['binding'] = {'namespace': namespace, 'operation_id': operation, 'session_id': payload.get('session_id'), 'method': method, 'bridge_sha256': control['bridge_sha256']}
        save(root / name, evidence)
        control['operations'][operation]['evidence'] = name
    save(control_path, control)
    return response

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--product', choices=('kylin', 'openclaw'), required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(dispatch(json.load(sys.stdin), args.product), ensure_ascii=False))
    except Exception as exc:
        print(type(exc).__name__ + ': ' + str(exc), file=sys.stderr)
        sys.exit(1)
