"""离线构建或验证固定数据，不调用生成 API。"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from memobench.data_v2 import build_dataset, validate_release


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset', default='data/v0.2')
    parser.add_argument('--validate-only', action='store_true')
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()
    try:
        if not args.validate_only:
            build_dataset(args.dataset, args.seed)
        result = validate_release(args.dataset)
    except (ValueError, KeyError, OSError) as exc:
        print(json.dumps({'validation': 'failed', 'error_type': type(exc).__name__}))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
