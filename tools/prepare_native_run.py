"""Create reviewed native configs and dry plan without network or model calls."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from memobench.native_preparation_v2 import prepare
from memobench.runner_v2 import ROOT, read, encoded


def main():
    p=argparse.ArgumentParser(description='只读准备：缺审批或当前原始probe证据则blocked，不创建transport')
    p.add_argument('--recipe',default=str(ROOT/'configs/experiments/native.json'))
    p.add_argument('--dataset',help='审核后新数据目录；支持独立AI内部用途，不覆盖原始候选数据')
    p.add_argument('--ssh-config',required=True)
    p.add_argument('--acceptance',action='append',default=[],metavar='PRODUCT=PROBE_JSON')
    p.add_argument('--out',required=True)
    args=p.parse_args()
    acceptances={}
    for value in args.acceptance:
        product,separator,path=value.partition('=')
        if not separator or not product or not path or product in acceptances:p.error('每产品仅一个PRODUCT=PROBE_JSON')
        acceptances[product]=path
    result=prepare(read(args.recipe),args.out,ssh_config=args.ssh_config,acceptances=acceptances,dataset=args.dataset)
    print(encoded(result),end='')
    return 2 if result['status']=='blocked' else 0

if __name__=='__main__':sys.exit(main())
