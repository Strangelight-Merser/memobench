"""No model/provider access: construct actual installed native tool definitions."""
import subprocess,shlex
from pathlib import Path
script=r'''
import pathlib,tempfile,json,subprocess,os,shutil
base=pathlib.Path.home()/'memobench-native';root=pathlib.Path(tempfile.mkdtemp(prefix='memobench-native-catalog-'));agent=root/'agent';task=root/'task';agent.mkdir();task.mkdir();config={'agents':{'defaults':{'workspace':str(agent),'cwd':str(task),'skipBootstrap':True}},'tools':{'allow':['read','write','edit','memory_search','memory_get'],'toolSearch':False,'codeMode':False}};(root/'config.json').write_text(json.dumps(config))
js=r"""const p=process.argv[1],cfg=JSON.parse(process.argv[2]);const {t:create}=await import('file://'+p+'/dist/agent-tools-BZa_AaY-.mjs');const {c:resolve,t:catalog,m:ref}=await import('file://'+p+'/dist/tool-search-Bw0pvXCm.mjs');const tools=create({config:cfg,workspaceDir:cfg.agents.defaults.workspace,cwd:cfg.agents.defaults.cwd,agentId:'main',modelProvider:'deepseek',modelId:'deepseek-flash',includeToolSearchControls:true});const result=catalog({config:cfg,tools,catalogRef:ref()});const expected=cfg.tools.allow;const names=tools.map(t=>t.name);for(const n of expected)if(!names.includes(n))throw Error('missing native tool '+n);if(names.includes('tool_call')||names.includes('tool_search'))throw Error('deferred wrapper present');if(resolve(cfg).enabled!==false||result.compacted!==false||result.tools!==tools)throw Error('disabled compaction contract failed');const schemas=Object.fromEntries(tools.filter(t=>expected.includes(t.name)).map(t=>[t.name,t.parameters]));if(!schemas.write.required.includes('content')||!schemas.write.required.includes('path'))throw Error('write schema incomplete');process.stdout.write(JSON.stringify({model_calls:0,tool_names:names,compacted:result.compacted,tools_same_reference:result.tools===tools,tool_search_enabled:resolve(cfg).enabled,schemas},null,2));"""
try:
 env=dict(os.environ,HOME=str(root),OPENCLAW_STATE_DIR=str(root/'state'),OPENCLAW_CONFIG_PATH=str(root/'config.json'))
 p=subprocess.run([str(base/'node-v24.22.0-linux-arm64/bin/node'),'--input-type=module','-e',js,str(base/'openclaw/node_modules/openclaw'),json.dumps(config)],cwd=task,env=env,capture_output=True,text=True,timeout=45)
 if p.returncode:raise RuntimeError(p.stderr)
 print(p.stdout)
finally:shutil.rmtree(root)
'''
r=subprocess.run(['ssh','-F','/Users/huaiyi/Documents/oschina/.local-vm/ssh_config','memobench-vm','python3 -c '+shlex.quote(script)],capture_output=True,text=True,timeout=60)
Path(__file__).with_name('native-catalog-stderr.log').write_text(r.stderr)
if r.returncode:raise RuntimeError(r.stderr)
Path(__file__).with_name('native-catalog.json').write_text(r.stdout)
print('Native catalog evidence saved; no tool execution or model calls.')
