"""Current public data permission, independent from historical quality approvals."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATASETS = ('data/v0.2', 'data/v0.2-ai-reviewed')
AUTHORIZATION = '那就公开，数据用 CC BY 4.0。把项目里这些自设限制和说明改一致，原始证据保留，双包解压的问题也一起修好，尽快弄成能提交的版本，别再让我填表。'
LICENSE_URL = 'https://creativecommons.org/licenses/by/4.0/'


def inventory(root, dataset):
    root = Path(root).resolve()
    relative = Path(dataset)
    if relative.as_posix() not in DATASETS:
        raise ValueError('public license dataset outside authorized scope')
    folder = root / relative
    if (not folder.is_dir() or not folder.resolve().is_relative_to(root)
            or any(p.is_symlink() for p in (folder, *folder.parents) if p.is_relative_to(root))):
        raise ValueError('public license dataset missing')
    files = {}
    for path in sorted(folder.rglob('*')):
        if any(p.is_symlink() for p in (path, *path.parents) if p.is_relative_to(root)):
            raise ValueError('linked licensed material refused')
        if path.is_file():
            files[path.relative_to(folder).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    if not files or 'sources.jsonl' not in files:
        raise ValueError('licensed data inventory incomplete')
    return files


def validate_public_license(root=ROOT, dataset=None):
    """Check the maintained authorization record and exact unchanged snapshots."""
    root = Path(root).resolve()
    path = root / 'data/PUBLIC_LICENSE.json'
    if any(p.is_symlink() for p in (path, *path.parents) if p.is_relative_to(root)):
        raise ValueError('linked public license record refused')
    raw = path.read_bytes()
    record = json.loads(raw)
    if (set(record) != {'schema_version', 'license_id', 'license_url', 'attribution', 'authorization', 'datasets'}
            or record['schema_version'] != 'public-data-license-1'
            or record['license_id'] != 'CC-BY-4.0' or record['license_url'] != LICENSE_URL
            or record['attribution'] != 'MemoBench contributors'
            or record['authorization'] != {'source': 'direct_user_message_current_thread',
                'authority': 'project_maintainer_user', 'statement': AUTHORIZATION}
            or set(record['datasets']) != set(DATASETS)):
        raise ValueError('public data authorization mismatch')
    for name in DATASETS:
        if record['datasets'][name] != inventory(root, name):
            raise ValueError('public data content hash mismatch')
    if dataset is not None:
        selected = Path(dataset).resolve()
        if selected not in {(root / name).resolve() for name in DATASETS}:
            raise ValueError('dataset is not covered by public permission')
    return {'status': 'accepted', 'license_id': record['license_id'],
            'license_url': record['license_url'], 'attribution': record['attribution'],
            'authorization_source': record['authorization']['source'],
            'record_sha256': hashlib.sha256(raw).hexdigest(), 'datasets': list(DATASETS),
            'quality_approval_changed': False}
