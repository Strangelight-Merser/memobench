"""One-off approved bridge deployment receipt and NO-MODEL lifecycle check."""
import base64
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from memobench.adapters_v2.ssh_vm import SSHVMTransport
from memobench.adapters_v2.native import NativeAdapter
from memobench.adapters_v2.factory import native_capabilities
from memobench.protocol_v2 import require_ready
from memobench.schema_v2 import Probe

SCRIPT = r'''
import base64,hashlib,json,os,pathlib,py_compile,stat,tempfile
value=json.load(__import__('sys').stdin)
path=pathlib.Path.home()/'memobench-native/native_vm_product.py'
if path.is_symlink():raise ValueError('linked bridge refused')
old=path.read_bytes();old_hash=hashlib.sha256(old).hexdigest()
backup=path.with_name(path.name+'.backup-'+old_hash)
if backup.exists():
 if backup.is_symlink() or backup.read_bytes()!=old:raise ValueError('backup conflict')
else:
 with backup.open('xb') as stream:stream.write(old)
new=base64.b64decode(value['source']);new_hash=hashlib.sha256(new).hexdigest()
if new_hash!=value['sha256']:raise ValueError('payload hash mismatch')
py_compile.compile(str(backup),doraise=True)
fd,tmp=tempfile.mkstemp(prefix='native-bridge-deploy-',dir=str(path.parent))
try:
 with os.fdopen(fd,'wb') as stream:stream.write(new);stream.flush();os.fsync(stream.fileno())
 os.chmod(tmp,stat.S_IMODE(path.stat().st_mode))
 os.replace(tmp,path)
finally:
 if os.path.exists(tmp):os.unlink(tmp)
py_compile.compile(str(path),doraise=True)
assert hashlib.sha256(path.read_bytes()).hexdigest()==new_hash
print(json.dumps({'path':str(path),'old_sha256':old_hash,'backup':str(backup),'new_sha256':new_hash,'py_compile':'passed','model_api_calls':0}))
'''

def main():
    repo=Path(__file__).resolve().parents[3];out=Path(__file__).parent
    source=(repo/'tools/native_vm_product.py').read_bytes()
    digest=hashlib.sha256(source).hexdigest()
    config=repo.parent/'.local-vm/ssh_config'
    result=subprocess.run(['/usr/bin/ssh','-F',str(config),'memobench-vm','python3 -c '+shlex.quote(SCRIPT)],
        input=json.dumps({'source':base64.b64encode(source).decode(),'sha256':digest}).encode(),capture_output=True,check=True,timeout=30)
    receipt=json.loads(result.stdout);receipt['local_sha256']=digest;receipt['checks']=[]
    (out/'deployment-receipt.json').write_text(json.dumps(receipt,indent=2))
    for product in ['kylin','openclaw']:
        transport=SSHVMTransport(config,product,live=True)
        adapter=NativeAdapter(transport,native_capabilities())
        record={'product':product,'model_api_calls':0,'calls':[],'default_bridge_path':True}
        try:
            for method,args,operation in [('reset_case',('deployment-synthetic-no-query','v1'),'reset'),('begin_session',('s1',),'begin')]:
                response=getattr(adapter,method)(*args,'no-api:'+product+':'+operation)
                record['calls'].append({'method':method,'receipt':response.to_dict()});require_ready(response)
            probe=Probe('deployment-synthetic-no-query','v1','s1','unused','NO QUERY IS SENT','2026-01-01T00:00:00Z')
            checkpoint=adapter.task_checkpoint(probe,'no-api:'+product+':unused-query')
            assert checkpoint['baseline']=={}
            record['checkpoint']=checkpoint
        finally:
            adapter.close();record['cleanup_receipts']=[r.to_dict() for r in adapter.cleanup_receipts]
        receipt['checks'].append(record)
        (out/'deployment-receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2))
    print(json.dumps({'deployed_sha256':digest,'backup':receipt['backup'],'default_transport_no_api_checks':len(receipt['checks']),'model_api_calls':0}))

if __name__=='__main__':main()
