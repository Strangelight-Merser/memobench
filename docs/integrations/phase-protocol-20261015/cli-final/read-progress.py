"""Read-only operation counts for the two fixed local attempts; no model calls."""
from pathlib import Path
import json,subprocess,shlex,datetime
root=Path(__file__).resolve().parent
attempts={product:json.loads(next((root/('run-'+product)/'cases').glob('*.json')).read_text())['attempts'][-1]['attempt_id'] for product in ('kylin','openclaw')}
script=r'''
import pathlib,json,sys,collections
ids=json.load(sys.stdin);root=pathlib.Path.home()/'memobench-native/cases';rows=[]
for p in root.glob('*/control.json'):
 d=json.loads(p.read_text());matches=[product for product,attempt in ids.items() if any(attempt in key for key in d.get('operations',{}))]
 if not matches:continue
 counts=collections.Counter(v['method']+':'+v['status'] for v in d['operations'].values());profiles=collections.Counter();unchanged=collections.Counter()
 for v in d['operations'].values():
  if v['method'] in ('observe','query') and v.get('evidence'):
   e=json.loads((p.parent/v['evidence']).read_text());profiles[str(e.get('profile_completed'))]+=1
   if v['method']=='observe':unchanged[str(e.get('task_workspace_unchanged'))]+=1
 rows.append({'product':d['product'],'namespace':p.parent.name,'counts':dict(counts),'profile_completed':dict(profiles),'observe_task_unchanged':dict(unchanged),'closed':d.get('closed',False)})
print(json.dumps(rows))
'''
r=subprocess.run(['ssh','-F','/Users/huaiyi/Documents/oschina/.local-vm/ssh_config','memobench-vm','python3 -c '+shlex.quote(script)],input=json.dumps(attempts),capture_output=True,text=True,check=True,timeout=30)
record={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'products':json.loads(r.stdout)}
with (root/'progress.jsonl').open('a') as stream:stream.write(json.dumps(record)+'\n')
print(json.dumps(record))
