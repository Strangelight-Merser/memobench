"""Actual frozen review JS export -> copy import -> prepare -> official run.
All data, signatures and product evidence here are SYNTHETIC TEST FIXTURES.
"""
import copy
import io
from contextlib import redirect_stdout
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from memobench.approval_v2 import import_approvals, templates
from memobench.data_v2 import build_dataset, build_review_page, encode, validate_release
from memobench.native_preparation_v2 import prepare
from memobench.runner_v2 import run
from memobench.adapters_v2 import factory
from memobench.schema_v2 import Prediction

RECIPE={'schema_version':'native-run-recipe-1','dataset':'unused','split':'test','products':['openclaw'],'purpose':'frozen_evaluation'}

class NativePreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.data=self.root/'source';self.data.mkdir()
        story={'story_id':'synthetic-prepare','template_id':'synthetic-prepare','split':'test',
            'source_type':'authored_synthetic_ai_assisted','official_capability':'memory_retrieval','technical_categories':['recall'],
            'utterances':[['测试颜色是蓝色。','记下测试颜色：蓝色。']],
            'events':[{'op':'set','key':'color','value':'蓝色','utterance':0}],
            'targets':[{'key':'color','type':'string'}],'queries':['测试颜色是什么？','先前的测试颜色是？']}
        (self.data/'sources.jsonl').write_text(encode(story));build_dataset(self.data)
        self.config=self.root/'ssh-config';self.config.write_text('synthetic config; no network')
        self.evidence=self.make_probe()
    def make_probe(self):
        # Same documented fields and relative exports that actual probe emits.
        evidence={'product':'openclaw','execution':'online','status':'passed','checks':dict.fromkeys(factory.REQUIRED_CHECKS,True),
            'canary':'SYNTHETIC-CODE','bridge_sha256':hashlib.sha256((Path(factory.__file__).resolve().parents[2]/'tools/native_vm_product.py').read_bytes()).hexdigest(),
            'config_sha256':hashlib.sha256(self.config.read_bytes()).hexdigest(),'events':[],'exports':[]}
        for case,queries in [('memory',[('q1','s1','SYNTHETIC-CODE'),('q2','s2','SYNTHETIC-CODE'),('q3','s2','done')]),('isolation',[('q4','s1','不知道')])]:
            reset='reset-'+case;namespace='synthetic-'+case
            binding={'namespace':namespace,'operation_id':reset,'session_id':None,'method':'reset_case','bridge_sha256':evidence['bridge_sha256']}
            export={'control.json':{'episode_id':case,'variant_id':'v1','bridge_sha256':evidence['bridge_sha256'],'closed':True,
                'operations':{reset:{'method':'reset_case','status':'completed','session_id':None,'evidence':'reset.json'}}},
                'reset.json':{'binding':binding,'mount_isolation':'passed','private_sentinel_present_outside':True,'private_sentinel_visible_inside':False}}
            evidence['events'].append({'method':'reset_case','episode_id':case,'variant_id':'v1','receipt':{'operation_id':reset}})
            for probe,session,answer in queries:
                export['control.json']['operations'][probe]={'method':'query','status':'completed','session_id':session,'evidence':probe+'.json'}
                export[probe+'.json']={'binding':binding|{'operation_id':probe,'session_id':session,'method':'query'},'answer':answer,
                    'files_before':{},'files_after':{'workspace/notes/code.txt':hashlib.sha256(b'SYNTHETIC-CODE\n').hexdigest()}}
                evidence['events'].append({'method':'query','operation_id':probe,'input':{'episode_id':case,'variant_id':'v1','session_id':session,'probe_id':probe},
                    'prediction':{'status':'ok','text':answer}})
            path=self.root/(namespace+'.json');raw=json.dumps(export).encode();path.write_bytes(raw)
            evidence['exports'].append({'namespace':namespace,'path':path.name,'sha256':hashlib.sha256(raw).hexdigest()})
        path=self.root/'probe.json';path.write_text(json.dumps(evidence));return path
    def review_via_actual_html_export(self):
        package=self.root/'review';templates(self.data,package);build_review_page(self.data,package/'review.html')
        page=(package/'review.html').read_text()
        dataset=json.loads(re.search(r'<script type="application/json" id="dataset">(.*?)</script>',page,re.S).group(1))
        script=page.split("'use strict';",1)[1].split('</script>',1)[0]
        save=script[script.index('function save(){'):script.index('function renderSessions')]
        export=script[script.index("$('export').onclick=()=>{"):script.index('\nrender();',script.index("$('export').onclick=()=>{"))]
        harness="""const dataset=INPUT;const records=dataset.stories.map(s=>({...s.review,development_exposed:null,exposure_notes:''}));let current=0;
const nodes={reviewer:{value:'SYNTHETIC-TEST-SIGNER'},ledgerChecked:{checked:true},variantsChecked:{checked:true},exposed:{value:'false'},exposureNotes:{value:''},reason:{value:'synthetic review fixture'},export:{},notice:{}};
const $=id=>nodes[id];const count=()=>{};const json=x=>JSON.stringify(x,null,2);
const document={querySelector:()=>({value:'accepted'}),createElement:()=>({click(){}})};
const URL={createObjectURL:blob=>{blob.text().then(text=>process.stdout.write(text));return 'synthetic-download';},revokeObjectURL(){}};
SAVE
EXPORT
$('export').onclick();
""".replace('INPUT',json.dumps(dataset,ensure_ascii=False)).replace('SAVE',save).replace('EXPORT',export)
        completed=subprocess.run(['node','-e',harness],capture_output=True,text=True,check=True)
        decisions=self.root/'downloaded-review.json';decisions.write_text(completed.stdout)
        license=json.loads((package/'license-approval.json').read_text())
        license.update(status='accepted',license_id='CC-BY-4.0',reviewer='SYNTHETIC-TEST-SIGNER',reviewed_at='2026-01-01T00:00:00Z',reason='synthetic fixture')
        path=self.root/'signed-license.json';path.write_text(json.dumps(license))
        approved=self.root/'approved';result=import_approvals(self.data,approved,decisions,path)
        self.assertEqual(result['release_status'],'accepted');self.assertEqual(result['formal_test_n_query'],2)
        return approved
    def test_complete_human_export_prepare_official_run_without_network(self):
        approved=self.review_via_actual_html_export()
        calls=[]
        class MockSSH:
            def __init__(self,*args,**kwargs):calls.append(('transport',None))
            def request(self,method,operation,payload,home):
                calls.append((method,payload.get('session_id')))
                if method=='query':return Prediction(payload['episode_id'],payload['variant_id'],payload['session_id'],payload['probe_id'],'ok','原生完整回答：蓝色','2026-01-01T00:00:00Z').to_dict()
                return {'operation_id':operation,'status':'ready','usage':None}
            def close(self):pass
        with patch.object(factory,'SSHVMTransport',MockSSH):
            plan=prepare(RECIPE,self.root/'prepared',ssh_config=self.config,acceptances={'openclaw':self.evidence},dataset=approved)
            self.assertEqual(calls,[]);self.assertEqual(plan['status'],'ready_for_scope_and_budget_review')
            self.assertEqual(plan['product_calls'],162);self.assertEqual(plan['lifecycle_calls'],12)
            self.assertIsNone(plan['provider_requests']);self.assertIsNone(plan['estimated_cost'])
            config=json.loads(Path(plan['configs']['openclaw']).read_text())
            from memobench.cli_v2 import main
            output=io.StringIO()
            with redirect_stdout(output):
                code=main(['run','--config',plan['configs']['openclaw'],'--out',str(self.root/'actual-run'),'--live'])
            self.assertEqual(code,0)
            result=json.loads(output.getvalue())
        self.assertTrue((self.root/'actual-run/report.html').is_file())
        self.assertIn('native 原生运行',(self.root/'actual-run/report.html').read_text())
        from memobench.report_v2 import render
        self.assertIn('离线 native fixture 不构成真实产品接入',render(dict(result,fixture=True),[]))
        self.assertEqual(result['status'],'completed');self.assertEqual(sum(method=='query' for method,_ in calls),2)
        self.assertFalse(any('echo' in notice for notice in result['integration_gaps']))
        rows=[json.loads(line) for line in (self.root/'actual-run/results.jsonl').read_text().splitlines()]
        self.assertTrue(all(row['prediction']['text']=='原生完整回答：蓝色' for row in rows))
    def test_pending_and_missing_probe_never_emit_runnable_config(self):
        with patch.object(factory,'SSHVMTransport',side_effect=AssertionError('network forbidden')):
            plan=prepare(RECIPE,self.root/'blocked',ssh_config=self.config,acceptances={},dataset=self.data)
        self.assertEqual(plan['status'],'blocked');self.assertEqual(plan['configs'],{})
        self.assertTrue(any(row['code']=='data_approval_required' for row in plan['blockers']))
        self.assertFalse((self.root/'blocked/openclaw.json').exists())
    def test_moved_probe_bundle_relative_exports_and_stale_config(self):
        approved=self.review_via_actual_html_export()
        import shutil
        moved=self.root/'moved';moved.mkdir()
        for path in [self.evidence,*self.root.glob('synthetic-*.json')]:shutil.copyfile(path,moved/path.name)
        plan=prepare(RECIPE,self.root/'moved-plan',ssh_config=self.config,acceptances={'openclaw':moved/'probe.json'},dataset=approved)
        self.assertEqual(plan['status'],'ready_for_scope_and_budget_review')
        self.config.write_text('changed config')
        blocked=prepare(RECIPE,self.root/'stale-plan',ssh_config=self.config,acceptances={'openclaw':moved/'probe.json'},dataset=approved)
        self.assertEqual(blocked['status'],'blocked');self.assertEqual(blocked['configs'],{})

    def test_prepared_dataset_change_is_blocked_before_transport(self):
        approved=self.review_via_actual_html_export()
        plan=prepare(RECIPE,self.root/'prepared',ssh_config=self.config,acceptances={'openclaw':self.evidence},dataset=approved)
        config=json.loads(Path(plan['configs']['openclaw']).read_text())
        (approved/'unapproved-extra.txt').write_text('unapproved change')
        with patch.object(factory,'SSHVMTransport',side_effect=AssertionError('must block before network')):
            result=run(config,self.root/'blocked-run',live=True)
        self.assertEqual(result['status'],'blocked')
