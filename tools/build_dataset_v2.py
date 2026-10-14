"""离线构建或验证固定数据，不调用生成 API。"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from memobench.data_v2 import build_dataset, validate_release, build_review_page


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset', default='data/v0.2')
    parser.add_argument('--validate-only', action='store_true')
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--review-page', help='生成仅供人工使用的内联 HTML 审核页')
    args = parser.parse_args()
    if args.validate_only and args.review_page:
        parser.error('--validate-only 不可与 --review-page 同用')
    try:
        if not args.validate_only:
            build_dataset(args.dataset, args.seed)
        result = validate_release(args.dataset)
        if args.review_page:
            build_review_page(args.dataset, args.review_page)
    except (ValueError, KeyError, OSError) as exc:
        print(json.dumps({'validation': 'failed', 'error_type': type(exc).__name__}))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
