"""Two explicitly authorized real synthetic queries; no dataset loaded."""
import json,sys,uuid,hashlib,subprocess,shlex
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from memobench.runner_v2 import execute_case
from memobench.adapters_v2.native import NativeAdapter
from memobench.adapters_v2.ssh_vm import SSHVMTransport
from memobench.adapters_v2.factory import native_capabilities
from memobench.schema_v2 import Episode,Probe,Gold
out=Path(__file__).resolve().parent
product=sys.argv[1]
case='audit-fix-synthetic-'+uuid.uuid4().hex
content='PUBLIC-SYNTHETIC-'+uuid.uuid4().hex
path='reports/'+uuid.uuid4().hex+'.txt'
query='这是公开合成开发任务。请先用原生 read 工具读取 /home/mb/case/workspace 根目录本身（目录不是文件，预期工具会返回错误；不要把该错误当任务终止）。随后继续用原生直接文件写入工具创建 '+path+'，内容精确为 '+content+'，不加换行，不用exec或shell。最后简述读目录失败和文件写入结果。'
e=Episode(case,'v1',case,'dev',['s1'],[],[Probe(case,'v1','s1','q',query,'2026-10-15T00:00:00Z')],[Gold('q',[],[],[],[{'operation':'create','path':path,'sha256':hashlib.sha256(content.encode()).hexdigest()}],[],['recall'],['task_reuse'])])
transport=SSHVMTransport('/Users/huaiyi/Documents/oschina/.local-vm/ssh_config',product,live=True)
result=execute_case(e,lambda:NativeAdapter(transport,native_capabilities()),mode='native_agent',execution='online',operation_prefix=case)
record={'product':product,'synthetic_development_only':True,'model_product_queries':1,'expected':{'path':path,'sha256':hashlib.sha256(content.encode()).hexdigest()},'public_input':e.to_public(),'result':result,'namespaces':list(transport.namespaces.values())}
(out/(product+'-file-regression.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2))
for namespace in record['namespaces']:
 script="import pathlib,json;p=pathlib.Path.home()/'memobench-native/cases'/"+repr(namespace)+";print(json.dumps({f.name:json.loads(f.read_text()) for f in p.glob('*.json')}))"
 r=subprocess.run(['ssh','-F','/Users/huaiyi/Documents/oschina/.local-vm/ssh_config','memobench-vm','python3 -c '+shlex.quote(script)],capture_output=True,text=True,check=True,timeout=30)
 (out/(product+'-file-raw-'+namespace+'.json')).write_text(r.stdout)
print(json.dumps({'product':product,'error':result['error'],'cleanup_error':result['cleanup_error'],'task_status':result['results'][0].get('task_status') if result['results'] else None}))
