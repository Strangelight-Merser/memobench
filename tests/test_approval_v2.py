"""All named signers here are synthetic fixtures, never real approvals."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from memobench import approval_v2 as approval
from memobench.data_v2 import build_dataset, read_rows, encode, validate_release
from memobench.schema_v2 import ContractError

DATA=Path(__file__).resolve().parents[1]/'data/v0.2'
class ApprovalTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'dataset';self.root.mkdir()
        story={'story_id':'synthetic-approval-story','template_id':'synthetic-approval-template','split':'test',
            'source_type':'authored_synthetic_ai_assisted','official_capability':'memory_retrieval','technical_categories':['recall'],
            'utterances':[['我的测试颜色是蓝色。','记下测试颜色：蓝色。']],
            'events':[{'op':'set','key':'color','value':'蓝色','utterance':0}],
            'targets':[{'key':'color','type':'string'}],'queries':['测试颜色是什么？','请说出先前的测试颜色。']}
        (self.root/'sources.jsonl').write_text(encode(story));build_dataset(self.root)
        self.package=Path(self.temp.name)/'unsigned';approval.templates(self.root,self.package)
        self.document=json.loads((self.package/'approval.json').read_text())
        self.license=json.loads((self.package/'license-approval.json').read_text())
    def signed(self):
        document=copy.deepcopy(self.document)
        document['records'][0].update(status='accepted',reviewer='synthetic-test-only',reviewed_at='2026-01-01T00:00:00Z',
            reason='synthetic fixture',ledger_query_checked=True,all_variants_checked=True,development_exposed=False)
        return document
    def test_pending_template_and_real_independent_license_gate(self):
        self.assertEqual(approval.state(self.root)['release_status'],'pending_review')
        (self.root/'approval.json').write_text(json.dumps(self.signed()));build_dataset(self.root)
        self.assertEqual(validate_release(self.root)['release_status'],'pending_license')
        self.license.update(status='accepted',license_id='CC-BY-4.0',reviewer='synthetic-test-only',reviewed_at='2026-01-01T00:00:00Z',reason='synthetic fixture')
        (self.root/'license-approval.json').write_text(json.dumps(self.license));build_dataset(self.root)
        self.assertEqual(validate_release(self.root)['release_status'],'accepted')
    def test_duplicate_missing_unknown_timestamp_stale_exposure(self):
        for change in ['duplicate','missing','unknown','timezone','stale','exposed']:
            doc=self.signed()
            if change=='duplicate':doc['records']*=2
            elif change=='missing':doc['records']=[]
            elif change=='unknown':doc['records'][0]['accepted_by_agent']=True
            elif change=='timezone':doc['records'][0]['reviewed_at']='2026-01-01T00:00:00'
            elif change=='stale':doc['context']['variants_sha256']='stale'
            elif change=='exposed':doc['records'][0].update(development_exposed=True,exposure_notes='used in development')
            with self.subTest(change=change),self.assertRaises(ContractError):approval.validate_decisions(self.root,doc,self.document['context'])
    def test_manifest_string_cannot_replace_human_approval(self):
        from memobench.runner_v2 import run
        manifest=json.loads((self.root/'manifest.json').read_text());manifest['status']='accepted';manifest['license']='accepted'
        (self.root/'manifest.json').write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ContractError,'status mismatch'):validate_release(self.root)
        with self.assertRaisesRegex(ContractError,'status mismatch'):
            run({'dataset':str(self.root),'split':'test','mode':'native_agent','execution':'online','adapter':'kylin'},
                    Path(self.temp.name)/'run',live=True)

    def test_rejected_or_pending_cannot_release_empty_test(self):
        document=self.signed();document['records'][0]['status']='rejected'
        (self.root/'approval.json').write_text(json.dumps(document));build_dataset(self.root)
        self.assertEqual(validate_release(self.root)['release_status'],'empty_reviewed_test')
        self.assertEqual(validate_release(self.root)['formal_test_n_query'],0)
    def test_pending_field_types_and_symlink_material_rejected(self):
        bad=copy.deepcopy(self.document);bad['records'][0]['exposure_notes']=None
        with self.assertRaises(ContractError):approval.validate_decisions(self.root,bad,self.document['context'])
        linked=Path(self.temp.name)/'decision-link.json';linked.symlink_to(self.package/'approval.json')
        with self.assertRaisesRegex(ContractError,'symlink'):approval.import_approvals(self.root,Path(self.temp.name)/'copy',linked)

    def test_rules_change_invalidates_approval(self):
        (self.root/'approval.json').write_text(json.dumps(self.signed()));build_dataset(self.root)
        with patch.object(approval,'RULE_FILES',approval.RULE_FILES+('memobench/runner_v2.py',)):
            with self.assertRaisesRegex(ContractError,'fingerprint stale'):validate_release(self.root)
    def test_import_only_new_copy_and_preserves_original_review(self):
        original=(self.root/'review.jsonl').read_bytes();test=(self.root/'test.jsonl').read_bytes()
        signed_bytes=(self.package/'approval.json').read_bytes()
        result=approval.import_approvals(self.root,Path(self.temp.name)/'copy',self.package/'approval.json')
        self.assertEqual(result['release_status'],'pending_review')
        self.assertEqual((Path(self.temp.name)/'copy/approval.json').read_bytes(),signed_bytes)
        self.assertEqual((self.root/'review.jsonl').read_bytes(),original);self.assertEqual((self.root/'test.jsonl').read_bytes(),test)
        with self.assertRaises(ContractError):approval.import_approvals(self.root,self.root,self.package/'approval.json')
