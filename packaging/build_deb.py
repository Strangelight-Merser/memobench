#!/usr/bin/env python3
"""标准库生成 Debian ar/tar.gz 包；不下载、不安装、不运行 maintainer scripts。"""
import argparse
import gzip
import io
from pathlib import Path
import tarfile


def archive(entries):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w', format=tarfile.USTAR_FORMAT) as tar:
        for name, payload, mode in sorted(entries):
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime = len(payload), mode, 0
            info.uid = info.gid = 0
            info.uname = info.gname = 'root'
            tar.addfile(info, io.BytesIO(payload))
    return gzip.compress(buffer.getvalue(), mtime=0)


def build(root, output):
    root = Path(root).resolve()
    entries = [('usr/bin/memobench-v2', (root / 'packaging/memobench-v2').read_bytes(), 0o755)]
    # 数据许可未签收，不把候选数据和私人gold打进可分发包。
    for directory, pattern in [('memobench', '*.py'), ('prompts', '*.txt')]:
        for path in sorted((root / directory).rglob(pattern)):
            if path.is_symlink():
                raise ValueError('symlink source refused')
            entries.append(('usr/share/memobench/' + path.relative_to(root).as_posix(), path.read_bytes(), 0o644))
    for name in ('LICENSE', 'README.md', 'SECURITY.md'):
        entries.append(('usr/share/doc/memobench/' + name, (root / name).read_bytes(), 0o644))
    members = [('debian-binary', b'2.0\n'),
               ('control.tar.gz', archive([('./control', (root / 'packaging/control').read_bytes(), 0o644)])),
               ('data.tar.gz', archive(entries))]
    data = bytearray(b'!<arch>\n')
    for name, payload in members:
        header = f'{name + "/":<16}{0:<12}{0:<6}{0:<6}{"100644":<8}{len(payload):<10}`\n'
        data.extend(header.encode('ascii'))
        data.extend(payload)
        if len(payload) % 2:
            data.extend(b'\n')
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(data)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    target = args.out or args.root / 'packaging/dist/memobench_0.2.0_all.deb'
    print(build(args.root, target))
    print('CANDIDATE ONLY: openKylin install/run/remove NOT_VERIFIED')


if __name__ == '__main__':
    main()
