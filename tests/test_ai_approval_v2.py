"""Synthetic AI-review/usage artifacts; no human identity or real decision invented."""
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from memobench import approval_v2 as approval
from memobench.data_v2 import build_dataset, digest, encode, read_rows, validate_release
from memobench.schema_v2 import ContractError
from memobench.adapters_v2.factory import review_native_settings

class AIApprovalTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.source=self.root/'source';self.source.mkdir()
        stories=[]
        for index in range(2):
            stories.append({'story_id':'synthetic-ai-'+str(index),'template_id':'synthetic-ai-'+str(index),'split':'test',
                'source_type':'authored_synthetic_ai_assisted','official_capability':'memory_retrieval','technical_categories':['recall'],
                'utterances':[['测试颜色是蓝色。','记下测试颜色：蓝色。']],
                'events':[{'op':'set','key':'color','value':'蓝色','utterance':0}],
                'targets':[{'key':'color','type':'string'}],'queries':['测试颜色是什么？','先前测试颜色是？']})
        (self.source/'sources.jsonl').write_text(''.join(encode(row) for row in stories));(self.source/'generation-record.md').write_text('Synthetic fixture only; offline authored_synthetic_ai_assisted.')
        build_dataset(self.source);self.expected=approval.context(self.source)
        self.time='2026-01-01T00:00:00Z'
        common={'reviewed_at':self.time,'sources_sha256':self.expected['sources_sha256'],'is_human_review':False,
                'reviewer_exposed_story_ids':[s['story_id'] for s in stories],'unseen_holdout_claim':False,
                'records':[{'story_id':s['story_id'],'source_sha256':digest(s),'decision':'accepted' if index==0 else 'rejected',
                            'reason':'synthetic semantic decision '+str(index),'generated_gold_checked':True,'all_source_wordings_checked':True} for index,s in enumerate(stories)]}
        self.independent=dict(copy.deepcopy(common),reviewer_identity={'kind':'ai','id':'synthetic-independent','model':'fixture'},
            source_file_hashes={name:hashlib.sha256((self.source/name).read_bytes()).hexdigest() for name in
                ['sources.jsonl','candidates.jsonl','dev.jsonl','public.jsonl','paired-2048.jsonl','paired-8192.jsonl','paired-32768.jsonl']})
        self.independent_path=self.root/'independent.json';self.independent_path.write_text(encode(self.independent))
        self.primary=dict(copy.deepcopy(common),reviewer_identity={'kind':'ai','id':'synthetic-primary','model':'fixture'},
            independent_review_sha256=hashlib.sha256(self.independent_path.read_bytes()).hexdigest())
        self.primary_path=self.root/'primary.json';self.primary_path.write_text(encode(self.primary))
        self.source_check={'reviewer_identity':self.primary['reviewer_identity'],'reviewed_at':self.time,
            'sources_sha256':self.expected['sources_sha256'],'source_file_sha256':hashlib.sha256((self.source/'sources.jsonl').read_bytes()).hexdigest(),
            'generation_record_sha256':hashlib.sha256((self.source/'generation-record.md').read_bytes()).hexdigest(),
            'authorization':{'origin':'direct_user_message_current_thread','text':'SYNTHETIC user authorization fixture','scope':'internal fixture only'},
            'source_findings':{'source_types':['authored_synthetic_ai_assisted'],'generation_record_declares_offline_ai_assisted_synthetic':True,'observed_content':'synthetic source verification'},
            'allowed_use':'internal_evaluation_only','public_redistribution_authorized':False,'public_license_id':None,'is_human_license_signature':False}
        self.source_check_path=self.root/'source-check.json';self.source_check_path.write_text(encode(self.source_check))
        self.bundle=self.root/'bundle';approval.package_ai_review(self.source,self.bundle,self.independent_path,self.primary_path,self.source_check_path,
            development_exposed_story_ids=['synthetic-ai-0'])
        self.document=json.loads((self.bundle/'approval.json').read_text())
    def validate(self,document):return approval.validate_decisions(self.source,document,self.expected,evidence_root=self.bundle)
    def test_real_artifact_package_import_internal_only_reject_exclusion(self):
        self.validate(self.document)
        target=self.root/'reviewed'
        result=approval.import_approvals(self.source,target,self.bundle/'approval.json',usage_decision=self.bundle/'usage-approval.json')
        self.assertEqual(result['release_status'],'accepted_internal');self.assertEqual(result['license_status'],'pending_review')
        self.assertEqual(result['formal_test_n_query'],2);self.assertFalse(result['unseen_holdout_claim'])
        self.assertEqual({row['story_id'] for row in read_rows(target/'test.jsonl')},{'synthetic-ai-0'})
        self.assertEqual((target/'approval.json').read_bytes(),(self.bundle/'approval.json').read_bytes())
    def test_same_identity_digest_reference_and_decision_fail(self):
        for case in ['identity','digest','reference','decision','unseen']:
            document=copy.deepcopy(self.document)
            if case=='identity':document['primary_review']['reviewer_identity']=document['reviewer_identity']
            elif case=='digest':document['evidence']['primary_review']['sha256']='0'*64
            elif case=='reference':document['evidence']['independent_review']=document['evidence']['primary_review']
            elif case=='decision':document['records'][0]['status']='rejected'
            else:document['exposure']['unseen_holdout_claim']=True
            with self.subTest(case=case),self.assertRaises((ContractError,FileNotFoundError)):self.validate(document)
    def test_original_edit_missing_and_variant_change_fail(self):
        reference=self.document['evidence']['primary_review'];path=self.bundle/reference['path'];raw=path.read_bytes()
        path.write_bytes(raw+b' ')
        with self.assertRaisesRegex(ContractError,'digest'):self.validate(self.document)
        path.unlink()
        with self.assertRaises(FileNotFoundError):self.validate(self.document)
        path.write_bytes(raw)
        with (self.source/'paired-8192.jsonl').open('a') as stream:stream.write('\n')
        with self.assertRaisesRegex(ContractError,'material stale'):self.validate(self.document)
    def test_primary_unchecked_original_cannot_be_promoted_by_package_boolean(self):
        changed=copy.deepcopy(self.primary);changed['records'][0]['generated_gold_checked']=False
        raw=encode(changed).encode();sha=hashlib.sha256(raw).hexdigest();(self.bundle/'evidence'/ (sha+'.json')).write_bytes(raw)
        document=copy.deepcopy(self.document);document['evidence']['primary_review']={'path':'evidence/'+sha+'.json','sha256':sha}
        with self.assertRaisesRegex(ContractError,'agreement and checks'):self.validate(document)
    def test_primary_wrong_independent_reference_rejected(self):
        changed=copy.deepcopy(self.primary);changed['independent_review_sha256']='0'*64
        raw=encode(changed).encode();sha=hashlib.sha256(raw).hexdigest();(self.bundle/'evidence'/(sha+'.json')).write_bytes(raw)
        document=copy.deepcopy(self.document);document['evidence']['primary_review']={'path':'evidence/'+sha+'.json','sha256':sha}
        with self.assertRaisesRegex(ContractError,'bind independent'):self.validate(document)

    def test_internal_import_prepare_real_cli_mock_transport(self):
        import io
        from contextlib import redirect_stdout
        from memobench.native_preparation_v2 import prepare
        from memobench.cli_v2 import main
        from memobench.adapters_v2 import factory
        from memobench.schema_v2 import Prediction
        from test_native_preparation_v2 import NativePreparationTests
        target=self.root/'internal-reviewed'
        approval.import_approvals(self.source,target,self.bundle/'approval.json',usage_decision=self.bundle/'usage-approval.json')
        helper=NativePreparationTests();helper.root=self.root;helper.config=self.root/'ssh-config';helper.config.write_text('synthetic no-network config')
        probe=helper.make_probe()
        recipe={'schema_version':'native-run-recipe-1','dataset':'unused','split':'test','products':['openclaw'],'purpose':'internal_evaluation'}
        calls=[]
        class MockSSH:
            def __init__(self,*args,**kwargs):calls.append('transport')
            def request(self,method,operation,payload,home):
                calls.append(method)
                if method=='query':return Prediction(payload['episode_id'],payload['variant_id'],payload['session_id'],payload['probe_id'],'ok','synthetic native response','2026-01-01T00:00:00Z').to_dict()
                return {'operation_id':operation,'status':'ready','usage':None}
            def close(self):pass
        with patch.object(factory,'SSHVMTransport',MockSSH):
            plan=prepare(recipe,self.root/'internal-prepared',ssh_config=helper.config,acceptances={'openclaw':probe},dataset=target)
            self.assertEqual(calls,[]);self.assertEqual(plan['status'],'ready_for_scope_and_budget_review')
            output=io.StringIO()
            with redirect_stdout(output):code=main(['run','--config',plan['configs']['openclaw'],'--out',str(self.root/'internal-run'),'--live'])
        result=json.loads(output.getvalue());self.assertEqual(code,0);self.assertEqual(result['status'],'completed')
        self.assertEqual(result['dataset_validation']['review_method'],'independent_ai');self.assertFalse(result['publish_ranking'])
        self.assertEqual(calls.count('query'),2)
        html=(self.root/'internal-run/report.html').read_text()
        self.assertIn('内部评测集：独立 AI 审核，非未见留出',html);self.assertNotIn('人工签收测试集',html)

    def test_internal_status_cannot_run_public_purpose_or_grant_license(self):
        validation={'release_status':'accepted_internal','usage_scope':'internal_evaluation_only'}
        with self.assertRaisesRegex(ValueError,'approval_required'):
            review_native_settings('kylin',{'purpose':'frozen_evaluation'},validation)
        usage=json.loads((self.bundle/'usage-approval.json').read_text());usage['public_license_granted']=True
        with self.assertRaisesRegex(ContractError,'public license'):approval.validate_usage(usage,self.expected,self.source,self.bundle)
        with self.assertRaises(ContractError):approval.validate_license(usage,self.expected)
