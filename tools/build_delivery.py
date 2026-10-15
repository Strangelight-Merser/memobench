"""Build one complete source and untouched evidence archive from a clean, fixed Git commit."""
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
         zipfile.ZipFile(out / 'memobench-complete.zip', 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as source:
        for entry in original.infolist():
            if entry.is_dir():
                continue
            name = entry.filename
            data = original.read(name)
            info = zipfile.ZipInfo('memobench/' + name, entry.date_time)
            info.external_attr = entry.external_attr
            info.compress_type = zipfile.ZIP_DEFLATED
            source.writestr(info, data)
            inventory[name] = {'sha256': hashlib.sha256(data).hexdigest(),
                               'archive': 'memobench-complete.zip'}
    manifest = {'commit': commit, 'data_license': 'CC-BY-4.0',
                'raw_evidence_unchanged': True, 'files': inventory,
                'archives': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in sorted(out.glob('*.zip'))}}
    (out / 'MANIFEST.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    (out / 'README.txt').write_text(
        'MemoBench 工程交付候选\n提交：' + commit + '\n\n'
        '只需解压 memobench-complete.zip，得到包含源码、数据和原始证据的完整 memobench/ 提交快照。\n'
        '先阅读 memobench/docs/delivery/README.md。\n'
        '此单包可独立运行全部离线测试与历史证据检查，无需第二个包。\n'
        '原始证据保留历史机器路径与私网地址；不得将其用作本机运行配置。\n'
        '自建合成数据按 CC BY 4.0 公开，详见 memobench/data/LICENSE.md。\n'
        '本包不是正式 PDF/视频提交，也不是全基准排名。\n')
    return {'commit': commit, 'files': len(inventory), 'output': str(out),
            'archives': manifest['archives']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.root, args.out), ensure_ascii=False, indent=2))
