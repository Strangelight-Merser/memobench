"""Phase restrictions preserve native memory and exact public inputs."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from tools import native_vm_product as bridge


class PhaseProtocolTests(unittest.TestCase):
    def test_query_policy_enforces_generic_format_without_case_values(self):
        policy=bridge.PHASE_POLICIES['query']
        self.assertIn('exact output format required by the current query',policy)
        self.assertIn('add no punctuation, explanation, or Markdown',policy)
        for forbidden in ('不知道','MB-','READY','markers/','notes/code.txt'):
            self.assertNotIn(forbidden,policy)

    def test_observe_mount_protects_tasks_but_keeps_native_home_writable(self):
        home = Path('/synthetic')
        observe = bridge.sandbox(home, 'openclaw', task_writable=False)
        self.assertIn(['--bind', str(home), bridge.GUEST], [observe[i:i+3] for i in range(len(observe)-2)])
        self.assertIn(['--ro-bind', str(home/'workspace'), bridge.GUEST+'/workspace'], [observe[i:i+3] for i in range(len(observe)-2)])
        query = bridge.sandbox(home, 'openclaw', task_writable=True)
        self.assertNotIn(str(home/'workspace'), query)

    def test_openclaw_native_directory_roles_are_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            bridge.configure(home, 'openclaw', {'model':'synthetic','base_url':'https://invalid.example'})
            cfg=json.loads((home/'.openclaw/openclaw.json').read_text())
            self.assertEqual(cfg['agents']['defaults']['cwd'],bridge.GUEST+'/workspace')
            self.assertEqual(cfg['agents']['defaults']['workspace'],bridge.GUEST+'/agent-workspace')
            self.assertTrue((home/'agent-workspace').is_dir())
            self.assertIn('write', cfg['tools']['allow'])
            self.assertIn('memory_search', cfg['tools']['allow'])

    def test_openclaw_uses_direct_native_tool_schemas_without_changing_allowlist(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp)
            bridge.configure(home,'openclaw',{'model':'synthetic','base_url':'https://invalid.example'})
            tools=json.loads((home/'.openclaw/openclaw.json').read_text())['tools']
            self.assertIs(tools['toolSearch'],False)
            self.assertIs(tools['codeMode'],False)
            self.assertEqual(tools['allow'],['read','write','edit','memory_search','memory_get'])

    def test_phase_does_not_rewrite_public_text_or_resume_id(self):
        provider={'api_key':'synthetic','base_url':'https://invalid.example','model':'synthetic'}
        text='原样观察：请创建 reports/ready.txt\n 不裁剪。'
        for product in ('kylin','openclaw'):
            session={'product_session':'existing-session'}
            for phase in ('observe','query'):
                completed=subprocess.CompletedProcess([],1,'','')
                with patch.object(bridge.subprocess,'run',return_value=completed) as run:
                    bridge.invoke(Path('/synthetic'),product,provider,text,session,phase)
                argv=run.call_args.args[0]
                self.assertIn(text,argv)
                self.assertIn('existing-session',argv)
                if product=='kylin':
                    self.assertEqual(run.call_args.kwargs['env']['HERMES_EPHEMERAL_SYSTEM_PROMPT'],bridge.PHASE_POLICIES[phase])
                    self.assertEqual(argv[argv.index('--toolsets')+1], 'memory' if phase=='observe' else 'memory,file')
                self.assertEqual(str(Path('/synthetic/workspace')) in argv, phase=='observe')

    def test_system_policy_refresh_preserves_native_memory_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp)
            bridge.configure(home,'kylin',{'model':'synthetic','base_url':'https://invalid.example'})
            for phase in ('observe','query'):
                policy=bridge.prepare_phase_policy(home,'kylin',phase)
                cfg=json.loads((home/'.kylin-agent-runtime/config.yaml').read_text())
                self.assertNotIn('system_prompt',cfg['agent'])
                self.assertEqual(policy['source'],'HERMES_EPHEMERAL_SYSTEM_PROMPT')
                self.assertTrue(cfg['memory']['memory_enabled'])
                self.assertTrue(cfg['memory']['user_profile_enabled'])
                self.assertEqual(policy['text'],bridge.PHASE_POLICIES[phase])
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp)
            bridge.configure(home,'openclaw',{'model':'synthetic','base_url':'https://invalid.example'})
            for phase in ('observe','query'):
                bridge.prepare_phase_policy(home,'openclaw',phase)
                self.assertEqual((home/'agent-workspace/AGENTS.md').read_text().strip(),bridge.PHASE_POLICIES[phase])
                argv=bridge.sandbox(home,'openclaw',task_writable=phase=='query')
                self.assertIn(['--ro-bind',str(home/'agent-workspace/AGENTS.md'),bridge.GUEST+'/agent-workspace/AGENTS.md'],[argv[i:i+3] for i in range(len(argv)-2)])

    def test_observe_workspace_change_blocks_ready_and_retains_native_answer(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);root=base/'cases'/('a'*32);home=root/'home';home.mkdir(parents=True)
            bridge.configure(home,'kylin',{'model':'synthetic','base_url':'https://invalid.example'})
            bridge.save(base/'provider.json',{})
            control={'product':'kylin','episode_id':'e','variant_id':'v','session':'s','sessions':{'s':{}},'operations':{},'uncertain':False,'bridge_sha256':'synthetic'}
            bridge.save(root/'control.json',control)
            text='原文观察：请稍后创建文件。'
            def changed(*args):
                self.assertEqual(args[3],text)
                (home/'workspace/early.txt').write_text('synthetic premature write')
                return {'ok':True,'answer':'native original answer'}
            req={'bridge_sha256':bridge.hashlib.sha256(Path(bridge.__file__).read_bytes()).hexdigest(),'namespace':'a'*32,'method':'observe','operation_id':'o','payload':{'episode_id':'e','variant_id':'v','session_id':'s','role':'user','text':text}}
            with patch.object(bridge,'BASE',base),patch.object(bridge,'invoke',side_effect=changed):
                receipt=bridge.dispatch(req,'kylin')
            self.assertEqual(receipt['status'],'unknown')
            evidence=json.loads((root/(bridge.hashlib.sha256(b'o').hexdigest()+'.json')).read_text())
            self.assertEqual(evidence['answer'],'native original answer')
            self.assertFalse(evidence['task_workspace_unchanged'])
            self.assertEqual(evidence['phase_policy']['public_text'],text)
            self.assertEqual(evidence['phase_error'],'observation_modified_task_workspace')

    def test_native_memory_events_never_count_as_task_events(self):
        rows=[]
        for i,path in enumerate((bridge.GUEST+'/agent-workspace/MEMORY.md','reports/ready.txt')):
            rows.extend([{'source':'synthetic','position':i*2,'session_id':'s','message':{'role':'assistant','content':[{'type':'toolCall','id':str(i),'name':'write','arguments':{'path':path}}]}}, {'source':'synthetic','position':i*2+1,'session_id':'s','message':{'role':'toolResult','toolCallId':str(i),'isError':False,'content':'{"ok":true}'}}])
        audit=bridge.native_file_audit(rows,bridge.transcript_checkpoint([]),'s')
        self.assertEqual([e['path'] for e in audit['events']],['reports/ready.txt'])
        self.assertEqual([e['path'] for e in audit['memory_events']],['MEMORY.md'])
        rows[0]['message']['content'][0]['arguments']['path']=bridge.GUEST+'/agent-workspace/../workspace/ready.txt'
        with self.assertRaises(ValueError):bridge.native_file_audit(rows,bridge.transcript_checkpoint([]),'s')

if __name__=='__main__':unittest.main()
