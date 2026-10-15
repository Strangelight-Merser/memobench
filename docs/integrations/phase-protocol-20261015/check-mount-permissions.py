"""No model/provider access: test reviewed bridge mount policy in disposable homes."""
import base64,hashlib,json,shlex,subprocess
from pathlib import Path
bridge=Path('tools/native_vm_product.py').read_bytes()
remote=r'''
import base64,json,pathlib,tempfile,importlib.util,subprocess,shutil,sys
v=json.load(sys.stdin);root=pathlib.Path(tempfile.mkdtemp(prefix='memobench-phase-permission-'));module=root/'bridge.py';module.write_bytes(base64.b64decode(v['bridge']));spec=importlib.util.spec_from_file_location('reviewed_bridge',module);bridge=importlib.util.module_from_spec(spec);spec.loader.exec_module(bridge)
code=r"""
import pathlib,json,os,errno
h=pathlib.Path('/home/mb/case');out={}
def attempt(name,fn):
 try:fn();out[name]={'succeeded':True,'errno':None}
 except OSError as e:out[name]={'succeeded':False,'errno':e.errno,'errno_name':errno.errorcode.get(e.errno)}
attempt('relative_task_write',lambda:pathlib.Path('relative.txt').write_text('synthetic'))
attempt('absolute_task_write',lambda:(h/'workspace/absolute.txt').write_text('synthetic'))
attempt('parent_task_write',lambda:pathlib.Path('../workspace/parent.txt').write_text('synthetic'))
attempt('symlink_task_write',lambda:(h/'agent-workspace/task-link/symlink.txt').write_text('synthetic'))
attempt('rename_task_mount',lambda:(h/'workspace').rename(h/'replaced-workspace'))
attempt('replace_task_mount',lambda:(h/'workspace').rmdir())
attempt('phase_policy_write',lambda:(h/'agent-workspace/AGENTS.md').write_text('overwrite forbidden'))
attempt('native_memory_write',lambda:(h/'agent-workspace/MEMORY.md').write_text('synthetic memory'))
attempt('native_state_write',lambda:(h/'.native-state/state.txt').write_text('synthetic state'))
print(json.dumps(out))
"""
records=[]
try:
 for product in ('kylin','openclaw'):
  for phase in ('observe','query'):
   home=root/(product+'-'+phase);home.mkdir();(home/'workspace').mkdir();(home/'agent-workspace').mkdir();(home/'.native-state').mkdir();(home/'agent-workspace/AGENTS.md').write_text(bridge.PHASE_POLICIES[phase]+'\n');(home/'agent-workspace/task-link').symlink_to('/home/mb/case/workspace')
   # Do not attempt directory replacement in query: writable tasks are allowed,
   # but replacement of a mount is not the behaviour under test.
   effective=code if phase=='observe' else code.replace("attempt('rename_task_mount',lambda:(h/'workspace').rename(h/'replaced-workspace'))",'').replace("attempt('replace_task_mount',lambda:(h/'workspace').rmdir())",'')
   p=subprocess.run(bridge.sandbox(home,product,task_writable=phase=='query')+['/usr/bin/python3','-c',effective],capture_output=True,text=True,check=True,timeout=20)
   records.append({'product':product,'phase':phase,'results':json.loads(p.stdout)})
 print(json.dumps({'bridge_sha256':v['sha256'],'model_calls':0,'records':records},indent=2))
finally:shutil.rmtree(root)
'''
r=subprocess.run(['ssh','-F','/Users/huaiyi/Documents/oschina/.local-vm/ssh_config','memobench-vm','python3 -c '+shlex.quote(remote)],input=json.dumps({'bridge':base64.b64encode(bridge).decode(),'sha256':hashlib.sha256(bridge).hexdigest()}),capture_output=True,text=True,check=True,timeout=100)
Path(__file__).with_name('mount-permissions.json').write_text(r.stdout)
d=json.loads(r.stdout)
for row in d['records']:
 for name,result in row['results'].items():
  expected=(row['phase']=='query' or name in ('native_memory_write','native_state_write') or (row['product']=='kylin' and name=='phase_policy_write')) and not (row['product']=='openclaw' and name=='phase_policy_write')
  assert result['succeeded']==expected,(row['product'],row['phase'],name,result)
print(json.dumps({'model_calls':0,'cases':len(d['records']),'all_expected':True,'bridge_sha256':d['bridge_sha256']}))
