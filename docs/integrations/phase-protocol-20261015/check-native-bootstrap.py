import subprocess,shlex,json
from pathlib import Path
script=r'''import pathlib,tempfile,subprocess,json,shutil
r=pathlib.Path.home()/"memobench-native"; d=pathlib.Path(tempfile.mkdtemp(prefix="phase-bootstrap-")); results=[]
js="const m=await import(process.argv[1]);const files=await m.c(process.argv[2]);process.stdout.write(JSON.stringify(files.filter(f=>f.name==='AGENTS.md')));"
try:
 for phase in ("observe","query"):
  text="PUBLIC PHASE "+phase; (d/"AGENTS.md").write_text(text)
  p=subprocess.run([str(r/"node-v24.22.0-linux-arm64/bin/node"),"--input-type=module","-e",js,"file://"+str(r/"openclaw/node_modules/openclaw/dist/workspace-ZTBSFGyP.mjs"),str(d)],capture_output=True,text=True,check=True,timeout=20)
  rows=json.loads(p.stdout);assert rows[0]["content"]==text;results.append({"phase":phase,"native_loaded_text":rows[0]["content"],"missing":rows[0]["missing"]})
 print(json.dumps({"model_calls":0,"actual_native_function":"loadWorkspaceBootstrapFiles","skipBootstrap_source_semantics":"ensureBootstrapFiles: !skipBootstrap controls seed creation; existing file load independent","results":results},indent=2))
finally:shutil.rmtree(d)
'''
r=subprocess.run(["ssh","-F","/Users/huaiyi/Documents/oschina/.local-vm/ssh_config","memobench-vm","python3 -c "+shlex.quote(script)],capture_output=True,text=True,check=True,timeout=60)
Path(__file__).with_name("native-bootstrap.json").write_text(r.stdout)
print(r.stdout)
