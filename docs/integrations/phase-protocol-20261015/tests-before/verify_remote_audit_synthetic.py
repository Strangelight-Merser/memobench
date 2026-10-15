"""Explicit no-model SSH audit check. Temporary fake product persistence, REAL files/SSH.
Never installs/replaces the real product bridge or reads the real provider file.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from memobench.adapters_v2.ssh_vm import SSHVMTransport
from memobench.adapters_v2.native import NativeAdapter
from memobench.adapters_v2.factory import native_capabilities
from memobench.runner_v2 import execute_case
from memobench.schema_v2 import Episode, Observation, Probe, Gold
from memobench.sandbox_v2 import sha256

WRAPPER = r'''
import argparse,json,sqlite3,sys,time,uuid,subprocess
from pathlib import Path
from contextlib import closing
import native_vm_product as bridge
bridge.BASE=Path(__file__).parent/'fixture-state'
real_sandbox=bridge.sandbox
def sandbox(home,product):
    args=real_sandbox(home,product)
    return [arg.replace(str(bridge.BASE/'agent-runtime'),'/home/mb/memobench-native/agent-runtime')
            .replace(str(bridge.BASE/'openclaw'),'/home/mb/memobench-native/openclaw')
            .replace(str(bridge.BASE/'node-v24.22.0-linux-arm64'),'/home/mb/memobench-native/node-v24.22.0-linux-arm64') for arg in args]
bridge.sandbox=sandbox
real_run=subprocess.run
def run_without_profile(*args,**kwargs):
    if any('load_profile' in str(arg) for arg in args[0]):
        return subprocess.CompletedProcess(args[0],0,'{"entries":{}}','')
    return real_run(*args,**kwargs)
bridge.subprocess.run=run_without_profile
# Native transcript source is synthetic. Never execute a real product or API.
def invoke(home,product,provider,text,session):
    session.setdefault('product_session','synthetic-'+uuid.uuid4().hex)
    sid=session['product_session']
    try: task=json.loads(text)
    except ValueError: task={}
    if product=='kylin':
        dbpath=home/'.kylin-agent-runtime/state.db'
        with closing(sqlite3.connect(dbpath)) as db,db:
            db.execute('CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY,session_id TEXT,role TEXT,content TEXT,tool_call_id TEXT,tool_calls TEXT,tool_name TEXT)')
            if task:
                call={'id':uuid.uuid4().hex,'function':{'name':'write_file','arguments':json.dumps({'path':task['path'],'content':task['content']})}}
                db.execute('INSERT INTO messages(session_id,role,tool_calls)VALUES(?,?,?)',(sid,'assistant',json.dumps([call])))
                db.execute('INSERT INTO messages(session_id,role,content,tool_call_id,tool_name)VALUES(?,?,?,?,?)',(sid,'tool','{"success":true}',call['id'],'write_file'))
    else:
        dbpath=home/'.openclaw/agents/main/sessions/sessions.sqlite';dbpath.parent.mkdir(parents=True,exist_ok=True)
        with closing(sqlite3.connect(dbpath)) as db,db:
            db.execute('CREATE TABLE IF NOT EXISTS transcript_events(seq INTEGER PRIMARY KEY,session_id TEXT,event_json TEXT,event_zstd BLOB)')
            if task:
                cid=uuid.uuid4().hex
                events=[{'message':{'role':'assistant','content':[{'type':'toolCall','id':cid,'name':'write','arguments':{'path':task['path'],'content':task['content']}}]}},
                        {'message':{'role':'toolResult','toolCallId':cid,'isError':False,'content':[{'type':'text','text':'synthetic tool result'}]}}]
                for event in events:db.execute('INSERT INTO transcript_events(session_id,event_json)VALUES(?,?)',(sid,json.dumps(event)))
        # Exercise the actual pinned Node SQLite and zstd decoder with a compressed row.
        script="const{DatabaseSync}=require('node:sqlite');const z=require('node:zlib');let d=new DatabaseSync(process.argv[1]);for(const r of d.prepare('select seq,event_json from transcript_events where event_json is not null').all())d.prepare('update transcript_events set event_zstd=?,event_json=null where seq=?').run(z.zstdCompressSync(Buffer.from(r.event_json)),r.seq);d.close();"
        subprocess.run(['/home/mb/memobench-native/node-v24.22.0-linux-arm64/bin/node','-e',script,str(dbpath)],check=True,capture_output=True)
    if task:
        target=home/'workspace'/task['path'];target.parent.mkdir(parents=True,exist_ok=True);target.write_text(task['content'])
        if task.get('untraced_extra'):
            target=home/'workspace/extra.txt';target.write_text('untraced synthetic write')
    return {'ok':True,'answer':'synthetic fixture answer','product_session':sid,'profile_completed':True,'synthetic_transport_audit':True}
bridge.invoke=invoke
parser=argparse.ArgumentParser();parser.add_argument('--product',required=True);args=parser.parse_args()
try: print(json.dumps(bridge.dispatch(json.load(sys.stdin),args.product)))
except Exception as exc: print(type(exc).__name__,str(exc),file=sys.stderr);sys.exit(1)
'''
PROVISION = r'''
import base64,json,pathlib,tempfile
value=json.load(__import__('sys').stdin)
root=pathlib.Path(tempfile.mkdtemp(prefix='memobench-synthetic-audit-'))
(root/'native_vm_product.py').write_bytes(base64.b64decode(value['bridge']))
(root/'endpoint.py').write_text(value['wrapper'])
state=root/'fixture-state';state.mkdir();(state/'node-v24.22.0-linux-arm64').symlink_to('/home/mb/memobench-native/node-v24.22.0-linux-arm64');(state/'provider.json').write_text(json.dumps({'api_key':'synthetic-unused-no-api','base_url':'https://invalid.example','model':'synthetic'}))
print(root)
'''

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--ssh-config',required=True);parser.add_argument('--out',required=True)
    args=parser.parse_args();out=Path(args.out);out.mkdir(parents=True,exist_ok=False)
    ssh=['/usr/bin/ssh','-F',str(Path(args.ssh_config).resolve()),'memobench-vm']
    import shlex
    def remote(script,stdin=b''):
        return subprocess.run(ssh+['python3 -c '+shlex.quote(script)],input=stdin,capture_output=True,check=True,timeout=60)
    body=json.dumps({'bridge':base64.b64encode((Path(__file__).parent/'native_vm_product.py').read_bytes()).decode(),'wrapper':WRAPPER}).encode()
    root=remote(PROVISION,body).stdout.decode().strip()
    results=[]
    try:
        for product in ['kylin','openclaw']:
            for untraced in [False,True]:
                task={'path':'reports/synthetic.txt','content':'synthetic hello','untraced_extra':untraced}
                e=Episode('synthetic-audit','v','synthetic-audit','dev',['s1','s2'],
                    [Observation('synthetic-audit','v','s1','o1','user','synthetic observation','2026-01-01T00:00:00Z')],
                    [Probe('synthetic-audit','v','s2','p',json.dumps(task),'2026-01-02T00:00:00Z')],
                    [Gold('p',[],[],[],[{'operation':'create','path':'reports/synthetic.txt','sha256':sha256('synthetic hello')}],[],['recall'],['task_reuse'])])
                transport=SSHVMTransport(args.ssh_config,product,live=True,bridge_path=root+'/endpoint.py')
                result=execute_case(e,lambda:NativeAdapter(transport,native_capabilities()),mode='native_agent',execution='offline',operation_prefix=product+('-untraced' if untraced else '-positive'))
                results.append({'product':product,'synthetic_transport_audit':True,'untraced_extra':untraced,'result':result})
                (out/(product+('-untraced' if untraced else '-positive')+'.json')).write_text(json.dumps(results[-1],ensure_ascii=False,indent=2))
                expected='blocked: unsupported_native_tool_execution' if untraced else 'passed'
                if result['results'][0]['task_status']!=expected: raise AssertionError(json.dumps(result,ensure_ascii=False))
        summary={'synthetic_transport_audit':True,'model_api_calls':0,'cases':len(results),'all_expected':True,'real_product_invocation_verified':False}
        (out/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary))
    finally:
        remote("import shutil;shutil.rmtree("+repr(root)+")")

if __name__=='__main__':main()
