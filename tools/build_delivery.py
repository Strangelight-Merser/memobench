"""Build source and untouched evidence archives from a clean, fixed Git commit."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import zipfile


def build(root, out):
    root, out = Path(root).resolve(), Path(out).resolve()
    def git(*args):
        return subprocess.check_output(['git', '-C', str(root), *args])
    if git('status', '--porcelain').strip():
        raise ValueError('Commit the reviewed files first; refusing a dirty working tree')
    commit = git('rev-parse', 'HEAD').decode().strip()
    archive = git('archive', '--format=zip', 'HEAD')
    out.mkdir(parents=True, exist_ok=False)
    inventory = {}
    with zipfile.ZipFile(io.BytesIO(archive)) as original, \
         zipfile.ZipFile(out / 'memobench-source.zip', 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as source, \
         zipfile.ZipFile(out / 'memobench-evidence-original.zip', 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as evidence:
        for entry in original.infolist():
            if entry.is_dir():
                continue
            name = entry.filename
            data = original.read(name)
            is_evidence = (name.startswith('docs/integrations/') and name != 'docs/integrations/README.md') or name in (
                'docs/openkylin/VM_ACCESS.md', 'docs/delivery/verified-native-bridge.py')
            target = evidence if is_evidence else source
            info = zipfile.ZipInfo('memobench/' + name, entry.date_time)
            info.external_attr = entry.external_attr
            info.compress_type = zipfile.ZIP_DEFLATED
            target.writestr(info, data)
            inventory[name] = {'sha256': hashlib.sha256(data).hexdigest(),
                               'archive': 'evidence' if is_evidence else 'source'}
    manifest = {'commit': commit, 'data_usage': 'internal_evaluation_only',
                'raw_evidence_unchanged': True, 'files': inventory,
                'archives': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in sorted(out.glob('*.zip'))}}
    (out / 'MANIFEST.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    (out / 'README.txt').write_text(
        'MemoBench 工程交付候选\n提交：' + commit + '\n\n'
        '将两个 ZIP 解压到同一目录，得到完整 memobench/ 提交快照。\n'
        '先阅读 memobench/docs/delivery/README.md。\n'
        '源码包可离线运行；完整历史验收检查需要同时解压原始证据包。\n'
        '证据包保留历史机器路径与私网地址，不包含私钥或模型凭据。\n'
        '数据仅有内部使用批准，未授予公开再分发许可。\n'
        '本包不是正式 PDF/视频提交，也不是全基准排名。\n')
    return {'commit': commit, 'files': len(inventory), 'output': str(out),
            'archives': manifest['archives']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.root, args.out), ensure_ascii=False, indent=2))
