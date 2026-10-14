#!/usr/bin/env python3
"""顺序执行独立配置；各运行单独保存，不合并排行榜。"""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from memobench.cli_v2 import main as run_cli


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--configs', nargs='+', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args(argv)
    status = 0
    for index, config in enumerate(args.configs):
        command = ['run', '--config', config, '--out', str(Path(args.out) / f'run-{index:03d}')]
        if args.live:
            command.append('--live')
        if args.resume:
            command.append('--resume')
        status = max(status, run_cli(command))
    return status


if __name__ == '__main__':
    raise SystemExit(main())
