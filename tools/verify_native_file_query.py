"""Authorized tiny real development acceptance: ONE query per product, no retry.
Public synthetic task only. Does not open candidate/test data or sign approvals.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from memobench.adapters_v2.ssh_vm import SSHVMTransport
from memobench.adapters_v2.native import NativeAdapter
from memobench.adapters_v2.factory import native_capabilities
from memobench.runner_v2 import execute_case
from memobench.schema_v2 import Episode, Probe, Gold
from memobench.sandbox_v2 import sha256

PROVISION = r'''
import base64,json,pathlib,tempfile
value=json.load(__import__('sys').stdin)
root=pathlib.Path(tempfile.mkdtemp(prefix='memobench-real-audit-dev-'))
(root/'native_vm_product.py').write_bytes(base64.b64decode(value['bridge']))
print(root)
'''

def main():
    p=argparse.ArgumentParser();p.add_argument('--ssh-config',required=True);p.add_argument('--out',required=True);p.add_argument('--live',action='store_true');args=p.parse_args()
    if not args.live:p.error('--live required: at most one real query for each product')
    out=Path(args.out);out.mkdir(parents=True,exist_ok=False)
    ssh=['/usr/bin/ssh','-F',str(Path(args.ssh_config).resolve()),'memobench-vm']
    def remote(script,body=b''):
        return subprocess.run(ssh+['python3 -c '+shlex.quote(script)],input=body,capture_output=True,timeout=30,check=True)
    source=(Path(__file__).parent/'native_vm_product.py').read_bytes()
    root=remote(PROVISION,json.dumps({'bridge':base64.b64encode(source).decode()}).encode()).stdout.decode().strip()
    results=[]
    try:
        for product in ['kylin','openclaw']:
            nonce=uuid4().hex
            text='MemoBench synthetic developer audit '+nonce+'\n'
            path='reports/audit-'+nonce+'.txt'
            prompt=('请使用原生文件写入工具，在当前工作目录下新建 '+path+'。文件完整内容是以下JSON字符串解码后的文本，含结尾一个换行：'+json.dumps(text,ensure_ascii=False)+'。完成后回答完成。')
            episode=Episode('synthetic-real-audit-'+nonce,'v1','synthetic-real-audit-'+nonce,'dev',['s1'],[],
                [Probe('synthetic-real-audit-'+nonce,'v1','s1','p',prompt,'2026-01-01T00:00:00Z')],
                [Gold('p',[],[],[],[{'operation':'create','path':path,'sha256':sha256(text)}],[],['recall'],['task_reuse'])])
            transport=SSHVMTransport(args.ssh_config,product,live=True,bridge_path=root+'/native_vm_product.py')
            result=execute_case(episode,lambda:NativeAdapter(transport,native_capabilities()),mode='native_agent',execution='online',operation_prefix=product+':'+nonce)
            # Export bridge-owned JSON only; never product HOME, DB or provider.
            exports=[]
            for namespace in transport.namespaces.values():
                script="import json,pathlib;p=pathlib.Path('/home/mb/memobench-native/cases')/"+repr(namespace)+";print(json.dumps({f.name:json.loads(f.read_text()) for f in p.glob('*.json')}))"
                try:
                    raw=remote(script).stdout
                    filename=namespace+'.json';(out/filename).write_bytes(raw)
                    exports.append({'namespace':namespace,'path':filename,'sha256':hashlib.sha256(raw).hexdigest()})
                except Exception as exc:exports.append({'namespace':namespace,'export_error':type(exc).__name__})
            record={'real_product_query':True,'scope':'synthetic developer file audit only; NOT benchmark scores',
                'execution':'online','product':product,'planned_query_count':1,'attempted_query_count':sum(e.get('method')=='query' for e in result.get('events',[])),
                'bridge_sha256':hashlib.sha256(source).hexdigest(),'public_input':episode.to_public(),'exports':exports,'result':result,'api_cost':None}
            # query predictions are in results; lifecycle events do not add query receipts.
            record['attempted_query_count']=sum(r.get('query_executed',True) for r in result['results'])
            (out/(product+'.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2))
            results.append({'product':product,'status':result['status'],'task_status':result['results'][0].get('task_status'),'error':result['error'],'cleanup_error':result['cleanup_error']})
        (out/'summary.json').write_text(json.dumps({'planned_product_queries':2,'automatic_retries':0,'api_cost':None,'results':results},ensure_ascii=False,indent=2));print(json.dumps(results,ensure_ascii=False))
    finally:
        remote('import shutil;shutil.rmtree('+repr(root)+')')

if __name__=='__main__':main()
