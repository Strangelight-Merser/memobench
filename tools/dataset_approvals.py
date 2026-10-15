"""Prepare human templates, package independent AI originals, or import supplied decisions into a NEW copy."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from memobench.approval_v2 import templates, import_approvals, package_ai_review
from memobench.data_v2 import build_review_page


def main():
    parser=argparse.ArgumentParser()
    sub=parser.add_subparsers(dest='action',required=True)
    prepare=sub.add_parser('prepare');prepare.add_argument('--dataset',required=True);prepare.add_argument('--out',required=True)
    load=sub.add_parser('import');load.add_argument('--dataset',required=True);load.add_argument('--out',required=True)
    load.add_argument('--decisions',required=True);load.add_argument('--license');load.add_argument('--usage')
    ai=sub.add_parser('package-ai');ai.add_argument('--dataset',required=True);ai.add_argument('--out',required=True)
    ai.add_argument('--independent',required=True);ai.add_argument('--primary',required=True);ai.add_argument('--source-check',required=True)
    ai.add_argument('--framework-development-exposed-story-id',action='append',default=[])
    args=parser.parse_args()
    if args.action=='prepare':
        seed=json.loads((Path(args.dataset)/'manifest.json').read_text())['seed']
        result=templates(args.dataset,args.out,seed)
        build_review_page(args.dataset,Path(args.out)/'review.html')
    elif args.action=='package-ai':
        result=package_ai_review(args.dataset,args.out,args.independent,args.primary,args.source_check,
            development_exposed_story_ids=args.framework_development_exposed_story_id)
    else: result=import_approvals(args.dataset,args.out,args.decisions,args.license,args.usage)
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__': main()
