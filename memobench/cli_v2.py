"""v2 显式入口；旧 cli 保持原样。"""
import argparse
from pathlib import Path
from .data_v2 import validate_release
from .judge_v2 import calibrate
from .runner_v2 import run, read, encoded, atomic_write
from .report_v2 import report
from .scoring_v2 import strict_json


def main(argv=None):
    parser = argparse.ArgumentParser(description='MemoBench v2：候选数据与正式结果分开')
    sub = parser.add_subparsers(dest='command', required=True)
    validate = sub.add_parser('validate')
    validate.add_argument('--dataset', required=True)
    execute = sub.add_parser('run')
    execute.add_argument('--config', required=True)
    execute.add_argument('--out', required=True)
    execute.add_argument('--live', action='store_true')
    execute.add_argument('--resume', action='store_true')
    reporting = sub.add_parser('report')
    reporting.add_argument('--run', required=True)
    reporting.add_argument('--out', required=True)
    calibration = sub.add_parser('calibrate')
    calibration.add_argument('--annotations', required=True)
    calibration.add_argument('--judgments', required=True)
    calibration.add_argument('--out', required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'validate':
            result = validate_release(args.dataset)
            from .data_license import ROOT, DATASETS, validate_public_license
            if Path(args.dataset).resolve() in {(ROOT / name).resolve() for name in DATASETS}:
                permission = validate_public_license(dataset=args.dataset)
                result = dict(result, historical_snapshot_license_status=result['license_status'],
                              license_status=permission['status'], public_license=permission)
        elif args.command == 'run':
            result = run(read(args.config), args.out, live=args.live, resume=args.resume)
            report(args.out, Path(args.out) / 'report.html')
        elif args.command == 'report':
            result = report(args.run, args.out)
        else:
            def rows(path):
                return [strict_json(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]
            result = calibrate(rows(args.annotations), rows(args.judgments))
            atomic_write(args.out, encoded(result))
        print(encoded(result), end='')
        return 2 if result.get('status') in ('blocked', 'completed_with_errors') else 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        # 不向终端回显可能携带私有 payload/凭据的异常正文。
        print(encoded({'status': 'error', 'type': type(exc).__name__,
                       'reason': '检查输入配置、路径、续跑身份与文件合同'}), end='')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
