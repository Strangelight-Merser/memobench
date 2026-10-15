"""Content-bound human or independent-AI review; internal use and public license are separate."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
from .schema_v2 import ContractError

ROOT = Path(__file__).resolve().parents[1]
RULE_FILES = ('memobench/data_v2.py', 'memobench/approval_v2.py', 'memobench/schema_v2.py',
              'memobench/scoring_v2.py', 'memobench/judge_v2.py', 'memobench/sandbox_v2.py',
              'memobench/native_artifacts_v2.py', 'prompts/judge-v0.2/system.txt')


def context(root, seed=42):
    from .data_v2 import read_rows, generate, digest
    stories = read_rows(Path(root) / 'sources.jsonl')
    variants = generate(stories, seed)
    selected = [story for story in stories if story['split'] == 'test'][:12]
    value = {'seed': seed, 'sources_sha256': digest(stories),
             'variants_sha256': digest([e.to_dict() for e in variants]),
             'paired_sha256': {str(size): digest([e.to_dict() for e in generate(selected, seed, size)])
                               for size in (2048, 8192, 32768)},
             'rules': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in RULE_FILES}}
    return dict(value, fingerprint=digest(value))


def checked_time(value):
    if not isinstance(value, str): raise ContractError('review timestamp required')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise ContractError('invalid review timestamp') from None
    if parsed.tzinfo is None or parsed > datetime.now(timezone.utc):
        raise ContractError('review timestamp requires timezone and cannot be future')


def validate_human_decisions(root, document, expected):
    from .data_v2 import read_rows, digest, opaque
    if set(document) != {'schema_version', 'context', 'records'} or document['schema_version'] != '0.2':
        raise ContractError('unknown human decision fields')
    if document['context'] != expected:
        raise ContractError('human review fingerprint stale')
    stories = {row['story_id']: row for row in read_rows(Path(root) / 'sources.jsonl')}
    records = document['records']
    if type(records) is not list or len(records) != len(stories) or {r['story_id'] for r in records} != set(stories):
        raise ContractError('human review missing or duplicate stories')
    fields = {'story_id','source_sha256','source_type','evidence_ids','status','reviewer','reviewed_at',
              'ledger_query_checked','all_variants_checked','reason','development_exposed','exposure_notes'}
    for row in records:
        source = stories[row['story_id']]
        if set(row) != fields or row['status'] not in ('pending_review','accepted','rejected'):
            raise ContractError('unknown human review record fields')
        if (row['source_sha256'] != digest(source) or row['source_type'] != source['source_type']
                or row['evidence_ids'] != [opaque(source['story_id'], 'observation', i) for i in range(len(source['utterances']))]):
            raise ContractError('human review source stale')
        if (type(row['ledger_query_checked']) is not bool or type(row['all_variants_checked']) is not bool
                or not isinstance(row['reason'], str) or not isinstance(row['exposure_notes'], str)
                or (row['development_exposed'] is not None and type(row['development_exposed']) is not bool)):
            raise ContractError('invalid human decision field types')
        if row['status'] == 'pending_review':
            if row['reviewer'] is not None or row['reviewed_at'] is not None:
                raise ContractError('pending decision cannot have a signer')
            continue
        if not isinstance(row['reviewer'], str) or not row['reviewer'].strip() or not isinstance(row['reason'], str) or not row['reason'].strip():
            raise ContractError('human signer and reason required')
        checked_time(row['reviewed_at'])
        if type(row['development_exposed']) is not bool or (row['development_exposed'] and not row['exposure_notes'].strip()):
            raise ContractError('development exposure review required')
        if row['status'] == 'accepted' and (row['ledger_query_checked'] is not True or row['all_variants_checked'] is not True
                or (source['split'] == 'test' and row['development_exposed'])):
            raise ContractError('accepted decision lacks checks or is exposed holdout')
    return records


def identity(value):
    if (type(value) is not dict or set(value) != {'kind', 'id', 'model'}
            or value['kind'] not in ('ai', 'human') or not isinstance(value['id'], str) or not value['id'].strip()
            or (value['kind'] == 'ai' and (not isinstance(value['model'], str) or not value['model'].strip()))
            or (value['kind'] == 'human' and value['model'] is not None)):
        raise ContractError('reviewer identity must explicitly identify AI or human')
    return value


def evidence_file(base, reference):
    if type(reference) is not dict or set(reference) != {'path', 'sha256'}:
        raise ContractError('review evidence reference required')
    relative = Path(reference['path'])
    if (relative.parts != ('evidence', reference['sha256'] + '.json')
            or len(reference['sha256']) != 64 or any(c not in '0123456789abcdef' for c in reference['sha256'])):
        raise ContractError('review evidence must use content-addressed relative path')
    path = Path(base) / relative
    if any(part.is_symlink() for part in (path, path.parent)) or not path.resolve().is_relative_to(Path(base).resolve()):
        raise ContractError('linked review evidence refused')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != reference['sha256']:
        raise ContractError('review evidence digest mismatch')
    return json.loads(raw), path


def review_artifact(value, expected, stories):
    actor = identity(value['reviewer_identity'])
    if value.get('is_human_review') is not (actor['kind'] == 'human'):
        raise ContractError('review original must honestly declare AI or human')
    checked_time(value['reviewed_at'])
    if value['sources_sha256'] != expected['sources_sha256']:
        raise ContractError('AI review original source stale')
    rows = value['records']
    if (type(rows) is not list or len(rows) != len(stories)
            or {row['story_id'] for row in rows} != set(stories)):
        raise ContractError('AI review original missing or duplicate stories')
    result = {}
    for row in rows:
        from .data_v2 import digest
        if (row['source_sha256'] != digest(stories[row['story_id']])
                or row['decision'] not in ('accepted', 'rejected', 'needs_repair', 'pending_review')
                or not isinstance(row['reason'], str) or not row['reason'].strip()):
            raise ContractError('AI review original verdict incomplete or stale')
        result[row['story_id']] = row
    return result


def validate_ai_decisions(root, document, expected, evidence_root):
    from .data_v2 import read_rows, digest, opaque
    fields = {'schema_version', 'context', 'review_method', 'reviewer_identity', 'primary_review', 'evidence', 'exposure', 'records'}
    if set(document) != fields or document['schema_version'] != '0.3' or document['review_method'] != 'independent_ai':
        raise ContractError('independent AI review protocol required')
    if document['context'] != expected:
        raise ContractError('AI review fingerprint stale')
    reviewer = identity(document['reviewer_identity'])
    primary = document['primary_review']
    if type(primary) is not dict or set(primary) != {'reviewer_identity', 'reviewed_at'}:
        raise ContractError('primary review identity and time required')
    primary_identity = identity(primary['reviewer_identity'])
    checked_time(primary['reviewed_at'])
    if reviewer['kind'] != 'ai' or primary_identity['id'] == reviewer['id']:
        raise ContractError('independent AI and distinct primary reviewer required')
    if set(document['evidence']) != {'independent_review', 'primary_review'}:
        raise ContractError('two original review artifacts required')
    independent, _ = evidence_file(evidence_root, document['evidence']['independent_review'])
    main, _ = evidence_file(evidence_root, document['evidence']['primary_review'])
    if (independent['reviewer_identity'] != reviewer or main['reviewer_identity'] != primary_identity
            or main['reviewed_at'] != primary['reviewed_at']
            or main['independent_review_sha256'] != document['evidence']['independent_review']['sha256']):
        raise ContractError('primary review does not bind independent original')
    stories = {row['story_id']: row for row in read_rows(Path(root) / 'sources.jsonl')}
    material_files = {'sources.jsonl', 'candidates.jsonl', 'dev.jsonl', 'public.jsonl', 'paired-2048.jsonl', 'paired-8192.jsonl', 'paired-32768.jsonl'}
    if set(independent.get('source_file_hashes', {})) != material_files:
        raise ContractError('AI review must bind all reviewed variant files')
    for name, sha in independent['source_file_hashes'].items():
        if hashlib.sha256((Path(root)/name).read_bytes()).hexdigest() != sha:
            raise ContractError('AI reviewed variant material stale')
    independent_rows = review_artifact(independent, expected, stories)
    main_rows = review_artifact(main, expected, stories)
    exposure = document['exposure']
    if type(exposure) is not dict or set(exposure) != {'reviewer_exposed_story_ids', 'framework_development_exposed_story_ids', 'unseen_holdout_claim'}:
        raise ContractError('AI review exposure declaration required')
    reviewed_ids = exposure['reviewer_exposed_story_ids']
    developed = exposure['framework_development_exposed_story_ids']
    if (not isinstance(reviewed_ids, list) or len(reviewed_ids) != len(stories) or set(reviewed_ids) != set(stories)
            or not isinstance(developed, list) or len(set(developed)) != len(developed) or set(developed) - set(stories)
            or exposure['unseen_holdout_claim'] is not False):
        raise ContractError('AI review cannot claim an unseen holdout')
    if independent.get('unseen_holdout_claim') is not False or main.get('unseen_holdout_claim') is not False:
        raise ContractError('review originals must disclose reviewed exposure')
    for artifact in (independent, main):
        if set(artifact.get('reviewer_exposed_story_ids', [])) != set(stories):
            raise ContractError('review original exposure scope incomplete')
    rows = document['records']
    if type(rows) is not list or len(rows) != len(stories) or {row['story_id'] for row in rows} != set(stories):
        raise ContractError('AI approval missing or duplicate stories')
    row_fields = {'story_id','source_sha256','source_type','evidence_ids','status','reviewer','reviewed_at',
                  'ledger_query_checked','all_variants_checked','reason','development_exposed','exposure_notes'}
    for row in rows:
        source = stories[row['story_id']]
        original = main_rows[row['story_id']]
        if (set(row) != row_fields or row['status'] not in ('accepted','rejected','pending_review')
                or row['source_sha256'] != digest(source) or row['source_type'] != source['source_type']
                or row['evidence_ids'] != [opaque(source['story_id'], 'observation', i) for i in range(len(source['utterances']))]
                or row['reviewer'] != primary_identity['id'] or row['reviewed_at'] != primary['reviewed_at']
                or row['status'] != original['decision'] or row['reason'] != original['reason']
                or type(row['development_exposed']) is not bool
                or row['development_exposed'] != (row['story_id'] in developed)
                or not isinstance(row['exposure_notes'], str) or not row['exposure_notes'].strip()):
            raise ContractError('AI approval must preserve primary per-story decision and exposure')
        if row['status'] == 'accepted' and (independent_rows[row['story_id']]['decision'] != 'accepted'
                or original.get('generated_gold_checked') is not True or original.get('all_source_wordings_checked') is not True
                or row['ledger_query_checked'] is not True or row['all_variants_checked'] is not True):
            raise ContractError('accepted AI story needs independent agreement and checks')
        if type(row['ledger_query_checked']) is not bool or type(row['all_variants_checked']) is not bool:
            raise ContractError('AI decision checks must be booleans')
    return rows


def validate_decisions(root, document, expected, evidence_root=None):
    # These are two current review types, not an adapter that upgrades old signatures.
    if document.get('schema_version') == '0.2':
        return validate_human_decisions(root, document, expected)
    return validate_ai_decisions(root, document, expected, evidence_root or root)


def validate_usage(document, expected, root, evidence_root=None):
    from .data_v2 import read_rows
    fields = {'schema_version','context_fingerprint','sources_sha256','usage','status','authorization',
              'source_verification','public_license_granted','unseen_holdout_claim'}
    if set(document) != fields or document['schema_version'] != 'internal-usage-1':
        raise ContractError('internal usage evidence protocol required')
    if (document['context_fingerprint'] != expected['fingerprint'] or document['sources_sha256'] != expected['sources_sha256']
            or document['usage'] != 'internal_evaluation_only' or document['public_license_granted'] is not False
            or document['unseen_holdout_claim'] is not False):
        raise ContractError('internal usage cannot grant public license or unseen ranking')
    if document['status'] == 'pending_review': return False
    if document['status'] != 'accepted': raise ContractError('invalid internal usage status')
    authorization = document['authorization']
    if (type(authorization) is not dict or set(authorization) != {'origin','text','scope'}
            or authorization['origin'] != 'direct_user_message_current_thread'
            or any(not isinstance(authorization[key], str) or not authorization[key].strip() for key in ('origin','text','scope'))):
        raise ContractError('actual user authorization reference required')
    verification = document['source_verification']
    if type(verification) is not dict or set(verification) != {'reviewer_identity','reviewed_at','reason','evidence'}:
        raise ContractError('source verification evidence required')
    identity(verification['reviewer_identity']);checked_time(verification['reviewed_at'])
    if not isinstance(verification['reason'], str) or not verification['reason'].strip():
        raise ContractError('source verification reason required')
    if any(row['source_type'] != 'authored_synthetic_ai_assisted' for row in read_rows(Path(root)/'sources.jsonl')):
        raise ContractError('internal permission limited to verified authored synthetic sources')
    source_evidence, _ = evidence_file(evidence_root or root, verification['evidence'])
    if (source_evidence['sources_sha256'] != expected['sources_sha256']
            or source_evidence.get('allowed_use') != 'internal_evaluation_only'
            or source_evidence.get('public_redistribution_authorized') is not False
            or source_evidence.get('public_license_id') is not None
            or source_evidence.get('is_human_license_signature') is not False
            or source_evidence.get('authorization') != authorization
            or source_evidence.get('reviewer_identity') != verification['reviewer_identity']
            or source_evidence.get('reviewed_at') != verification['reviewed_at']
            or source_evidence.get('source_file_sha256') != hashlib.sha256((Path(root)/'sources.jsonl').read_bytes()).hexdigest()
            or source_evidence.get('generation_record_sha256') != hashlib.sha256((Path(root)/'generation-record.md').read_bytes()).hexdigest()
            or source_evidence.get('source_findings', {}).get('source_types') != ['authored_synthetic_ai_assisted']
            or source_evidence.get('source_findings', {}).get('generation_record_declares_offline_ai_assisted_synthetic') is not True):
        raise ContractError('internal source evidence incomplete')
    return True


def validate_license(document, expected):
    fields = {'schema_version','context_fingerprint','sources_sha256','status','license_id','reviewer','reviewed_at','reason'}
    if set(document) != fields or document['schema_version'] != '0.2':
        raise ContractError('unknown license fields')
    if document['context_fingerprint'] != expected['fingerprint'] or document['sources_sha256'] != expected['sources_sha256']:
        raise ContractError('license approval stale')
    if not isinstance(document['reason'], str) or (document['license_id'] is not None and not isinstance(document['license_id'], str)):
        raise ContractError('invalid license field types')
    if document['status'] == 'pending_review':
        if document['reviewer'] is not None or document['reviewed_at'] is not None: raise ContractError('pending license signer')
        return False
    if document['status'] != 'accepted' or any(not isinstance(document[key], str) or not document[key].strip() for key in ('license_id','reviewer','reason')):
        raise ContractError('license signoff incomplete')
    checked_time(document['reviewed_at'])
    return True


def state(root, seed=42):
    from .data_v2 import read_rows
    root = Path(root)
    expected = context(root, seed)
    approval = root / 'approval.json'
    license_path = root / 'license-approval.json'
    records = read_rows(root / 'review.jsonl')
    signed = approval.exists()
    document = json.loads(approval.read_text()) if signed else None
    if signed: records = validate_decisions(root, document, expected)
    method = 'independent_ai' if document and document.get('review_method') == 'independent_ai' else 'human' if signed else None
    licensed = validate_license(json.loads(license_path.read_text()), expected) if license_path.exists() else False
    usage_path = root / 'usage-approval.json'
    internal = validate_usage(json.loads(usage_path.read_text()), expected, root) if usage_path.exists() else False
    pending = sum(row['status'] == 'pending_review' for row in records)
    rejected = sum(row['status'] == 'rejected' for row in records)
    stories = {s['story_id']: s for s in read_rows(root / 'sources.jsonl')}
    accepted_test = sum(row['status'] == 'accepted' and stories[row['story_id']]['split'] == 'test' for row in records)
    status = ('pending_review' if not signed or pending else 'empty_reviewed_test' if not accepted_test
              else 'accepted_internal' if internal else 'pending_internal_usage' if method == 'independent_ai'
              else 'pending_license' if not licensed else 'accepted')
    return {'context': expected, 'records': records, 'release_status': status,
            'review_method': method, 'usage_scope': 'internal_evaluation_only' if internal else None,
            'unseen_holdout_claim': False, 'internal_usage_status': 'accepted' if internal else 'pending_review',
            'license_status': 'accepted' if licensed else 'pending_review',
            'pending_n_story': pending, 'rejected_n_story': rejected, 'accepted_test_n_story': accepted_test}


def templates(root, destination, seed=42):
    from .data_v2 import read_rows, encode
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    expected = context(root, seed)
    rows = [dict(row, status='pending_review', reviewer=None, reviewed_at=None,
                 ledger_query_checked=False, all_variants_checked=False,
                 development_exposed=None, exposure_notes='', reason='')
            for row in read_rows(Path(root)/'review.jsonl')]
    (destination/'approval.json').write_text(encode({'schema_version':'0.2','context':expected,'records':rows}))
    (destination/'license-approval.json').write_text(encode({'schema_version':'0.2',
        'context_fingerprint':expected['fingerprint'],'sources_sha256':expected['sources_sha256'],
        'status':'pending_review','license_id':None,'reviewer':None,'reviewed_at':None,'reason':''}))
    return expected


def import_approvals(source, destination, decisions, license_decision=None, usage_decision=None):
    from .data_v2 import build_dataset, validate_release
    materials = [Path(source), Path(decisions)] + ([Path(license_decision)] if license_decision else []) + ([Path(usage_decision)] if usage_decision else [])
    def linked(path):
        absolute = path.absolute()
        return any(part.is_symlink() and str(part) not in ('/tmp', '/var') for part in (absolute, *absolute.parents))
    if any(linked(path) for path in materials) or linked(Path(destination)):
        raise ContractError('symlink approval material refused')
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if any(path.is_symlink() for path in source.rglob('*')):
        raise ContractError('symlink dataset material refused')
    if destination.exists() or destination.is_relative_to(source):
        raise ContractError('approval import requires a new separate dataset directory')
    manifest = json.loads((source/'manifest.json').read_text())
    expected = context(source, manifest['seed'])
    document = json.loads(Path(decisions).read_text())
    bundle_root = Path(decisions).resolve().parent
    validate_decisions(source, document, expected, evidence_root=bundle_root)
    license_document = json.loads(Path(license_decision).read_text()) if license_decision else None
    if license_document is not None: validate_license(license_document, expected)
    usage_document = json.loads(Path(usage_decision).read_text()) if usage_decision else None
    if usage_document is not None: validate_usage(usage_document, expected, source, Path(usage_decision).resolve().parent)
    shutil.copytree(source, destination)
    shutil.copyfile(decisions, destination/'approval.json')
    if license_document is not None:
        shutil.copyfile(license_decision, destination/'license-approval.json')
    if usage_document is not None:
        shutil.copyfile(usage_decision, destination/'usage-approval.json')
    evidence_references = list(document.get('evidence', {}).values())
    if usage_document is not None: evidence_references.append(usage_document['source_verification']['evidence'])
    for reference in evidence_references:
        base = Path(usage_decision).resolve().parent if usage_document and reference == usage_document['source_verification']['evidence'] else bundle_root
        _, original = evidence_file(base, reference)
        target = destination/reference['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if target.read_bytes() != original.read_bytes(): raise ContractError('evidence archive collision')
        else: shutil.copyfile(original, target)
    build_dataset(destination, manifest['seed'])
    return validate_release(destination)


def package_ai_review(root, destination, independent_path, primary_path, source_check_path, *, development_exposed_story_ids):
    """Package actual AI decisions and authorized usage; never invent human signatures."""
    from .data_v2 import read_rows, digest, opaque, encode, validate_release
    validate_release(root)
    root, destination = Path(root), Path(destination)
    if destination.exists(): raise ContractError('AI review package needs a new directory')
    expected = context(root, json.loads((root/'manifest.json').read_text())['seed'])
    independent = json.loads(Path(independent_path).read_text())
    primary = json.loads(Path(primary_path).read_text())
    source_check = json.loads(Path(source_check_path).read_text())
    stories = {row['story_id']:row for row in read_rows(root/'sources.jsonl')}
    independent_rows = review_artifact(independent, expected, stories)
    primary_rows = review_artifact(primary, expected, stories)
    destination.mkdir(parents=True)
    references = {}
    for key, path in [('independent_review', independent_path), ('primary_review', primary_path), ('source_check', source_check_path)]:
        raw = Path(path).read_bytes();sha = hashlib.sha256(raw).hexdigest()
        relative = 'evidence/'+sha+'.json';target=destination/relative;target.parent.mkdir(exist_ok=True)
        target.write_bytes(raw);references[key]={'path':relative,'sha256':sha}
    rows = []
    for story_id, source in stories.items():
        verdict=primary_rows[story_id]
        rows.append({'story_id':story_id,'source_sha256':digest(source),'source_type':source['source_type'],
            'evidence_ids':[opaque(story_id,'observation',i) for i in range(len(source['utterances']))],
            'status':verdict['decision'],'reviewer':primary['reviewer_identity']['id'],'reviewed_at':primary['reviewed_at'],
            'ledger_query_checked':verdict.get('generated_gold_checked', False),
            'all_variants_checked':verdict.get('all_source_wordings_checked', False),
            'reason':verdict['reason'],'development_exposed':story_id in development_exposed_story_ids,
            'exposure_notes':'Both AI reviewers inspected this story. The development flag records known framework/developer exposure, not tested-model tuning. No model training invocation occurred in this audit; earlier history is not asserted.'})
    document={'schema_version':'0.3','context':expected,'review_method':'independent_ai',
        'reviewer_identity':independent['reviewer_identity'],
        'primary_review':{'reviewer_identity':primary['reviewer_identity'],'reviewed_at':primary['reviewed_at']},
        'evidence':{key:references[key] for key in ('independent_review','primary_review')},
        'exposure':{'reviewer_exposed_story_ids':list(stories),
                    'framework_development_exposed_story_ids':list(development_exposed_story_ids),'unseen_holdout_claim':False},
        'records':rows}
    usage={'schema_version':'internal-usage-1','context_fingerprint':expected['fingerprint'],
        'sources_sha256':expected['sources_sha256'],'usage':'internal_evaluation_only','status':'accepted',
        'authorization':source_check['authorization'],
        'source_verification':{'reviewer_identity':source_check['reviewer_identity'],'reviewed_at':source_check['reviewed_at'],
            'reason':source_check['source_findings']['observed_content'],'evidence':references['source_check']},
        'public_license_granted':False,'unseen_holdout_claim':False}
    validate_decisions(root,document,expected,evidence_root=destination)
    validate_usage(usage,expected,root,evidence_root=destination)
    (destination/'approval.json').write_text(encode(document))
    (destination/'usage-approval.json').write_text(encode(usage))
    return {'review_method':'independent_ai','package':str(destination),'context_fingerprint':expected['fingerprint'],
            'accepted':sum(row['status']=='accepted' for row in rows),'rejected':sum(row['status']=='rejected' for row in rows),
            'usage':'internal_evaluation_only','public_license_granted':False}
