"""One real observe and one query per product; public synthetic development only."""
import json,sys,uuid,hashlib,subprocess,shlex
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from memobench.runner_v2 import execute_case
from memobench.adapters_v2.native import NativeAdapter
from memobench.adapters_v2.ssh_vm import SSHVMTransport
from memobench.adapters_v2.factory import native_capabilities
from memobench.schema_v2 import Episode,Observation,Probe,Gold
out=Path(__file__).resolve().parent
product=sys.argv[1];case='phase-smoke-'+uuid.uuid4().hex;content='PUBLIC-'+uuid.uuid4().hex;path='reports/'+uuid.uuid4().hex+'.txt'
text='请记住这项虚构开发约定：标记文件相对路径为 '+path+'，精确内容为 '+content+'，不加换行。现在请立即创建该文件；以后我会只说按约定创建标记。'
query='请按先前记住的约定创建标记文件，使用原生直接文件写入工具，不用shell。'
e=Episode(case,'v1',case,'dev',['s1'],[Observation(case,'v1','s1','o','user',text,'2026-10-15T00:00:00Z')],[Probe(case,'v1','s1','q',query,'2026-10-15T00:01:00Z')],[Gold('q',[],[],[],[{'operation':'create','path':path,'sha256':hashlib.sha256(content.encode()).hexdigest()}],[],['recall'],['task_reuse'])])
t=SSHVMTransport('/Users/huaiyi/Documents/oschina/.local-vm/ssh_config',product,live=True)
result=execute_case(e,lambda:NativeAdapter(t,native_capabilities()),mode='native_agent',execution='online',operation_prefix=case)
record={'product':product,'synthetic_development_only':True,'public_input':e.to_public(),'expected':{'path':path,'sha256':hashlib.sha256(content.encode()).hexdigest()},'result':result,'namespaces':list(t.namespaces.values())}
(out/('smoke-'+product+'.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2))
for ns in record['namespaces']:
 script="import pathlib,json;p=pathlib.Path.home()/'memobench-native/cases'/"+repr(ns)+";print(json.dumps({f.name:json.loads(f.read_text()) for f in p.glob('*.json')}))"
 r=subprocess.run(['ssh','-F','/Users/huaiyi/Documents/oschina/.local-vm/ssh_config','memobench-vm','python3 -c '+shlex.quote(script)],capture_output=True,text=True,check=True,timeout=30)
 (out/('smoke-'+product+'-raw-'+ns+'.json')).write_text(r.stdout)
print(json.dumps({'product':product,'error':result['error'],'cleanup_error':result['cleanup_error'],'task_status':result['results'][0].get('task_status') if result['results'] else None}))
