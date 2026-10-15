"""Synthetic audit: real temporary bytes plus fixed-product transcript schemas."""
import base64
from contextlib import closing
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from tools import native_vm_product as bridge
from memobench.native_artifacts_v2 import verify_remote_task, unpack
from memobench.schema_v2 import Gold, Prediction, ContractError
from memobench.sandbox_v2 import sha256

class RemoteArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.home=Path(self.temp.name);(self.home/'workspace').mkdir()
        self.database=self.home/'.kylin-agent-runtime/state.db';self.database.parent.mkdir()
        with closing(sqlite3.connect(self.database)) as db,db:
            db.execute('CREATE TABLE messages(id INTEGER,session_id TEXT,role TEXT,content TEXT,tool_call_id TEXT,tool_calls TEXT,tool_name TEXT)')
        self.checkpoint={'binding':{'run':'r','namespace':'n','operation_id':'q','session_id':'s2'},'baseline':bridge.workspace_snapshot(self.home),
                         'transcript':bridge.transcript_checkpoint(bridge.native_records(self.home,'kylin'))}
    def evidence(self):
        path=self.home/'workspace/reports/week.txt';path.parent.mkdir();path.write_text('hello')
        call={'id':'c','function':{'name':'write_file','arguments':json.dumps({'path':'reports/week.txt','content':'hello'})}}
        with closing(sqlite3.connect(self.database)) as db,db:
            db.execute('INSERT INTO messages VALUES(?,?,?,?,?,?,?)',(1,'product-session','assistant',None,None,json.dumps([call]),None))
            db.execute('INSERT INTO messages VALUES(?,?,?,?,?,?,?)',(2,'product-session','tool',json.dumps({'success':True}),'c',None,'write_file'))
        audit=bridge.native_file_audit(bridge.native_records(self.home,'kylin'),self.checkpoint['transcript'],'product-session')
        return {'binding':self.checkpoint['binding'],'baseline':self.checkpoint['baseline'],'after':bridge.workspace_snapshot(self.home),'audit':audit,'complete':True}
    def verify(self,evidence):
        gold=Gold('p',[],[],[],[{'operation':'create','path':'reports/week.txt','sha256':sha256('hello'),'old_paths':['old/week.txt']}],[],['update'],['task_reuse'])
        prediction=Prediction('e','v','s2','p','ok','done','2026-01-01T00:00:00Z')
        return verify_remote_task(gold,prediction,self.checkpoint,evidence)
    def test_real_bytes_and_current_native_trace(self):
        evidence=self.evidence();self.assertEqual(self.verify(evidence)['status'],'passed')
        self.assertEqual(evidence['audit']['events'][0]['native_result']['position'],2)
    def test_tampered_bytes_scope_missing_trace(self):
        evidence=self.evidence()
        altered=copy.deepcopy(evidence);altered['after']['reports/week.txt']['content_base64']=base64.b64encode(b'wrong').decode()
        with self.assertRaises(ContractError):self.verify(altered)
        altered=copy.deepcopy(evidence);altered['binding']['session_id']='old'
        with self.assertRaises(ContractError):self.verify(altered)
        evidence['audit']['events']=[]
        self.assertEqual(self.verify(evidence)['status'],'unsupported')
    def test_missing_result_and_old_session_cannot_support_write(self):
        self.evidence()
        with closing(sqlite3.connect(self.database)) as db,db:db.execute('DELETE FROM messages WHERE id=2')
        records=bridge.native_records(self.home,'kylin')
        with self.assertRaisesRegex(ValueError,'result missing'):bridge.native_file_audit(records,self.checkpoint['transcript'],'product-session')
        self.assertEqual(bridge.native_file_audit(records,self.checkpoint['transcript'],'other-session')['events'],[])
    def test_transcript_prefix_replaced(self):
        self.evidence();records=bridge.native_records(self.home,'kylin');checkpoint=bridge.transcript_checkpoint(records)
        records[0]['session_id']='old'
        with self.assertRaisesRegex(ValueError,'replaced or truncated'):bridge.native_file_audit(records,checkpoint,'product-session')
    def test_duplicate_reordered_and_wrong_tool_results_fail(self):
        self.evidence();records=bridge.native_records(self.home,'kylin')
        for changed in [records+[copy.deepcopy(records[0])],records+[copy.deepcopy(records[1])],list(reversed(records))]:
            with self.assertRaises(ValueError):bridge.native_file_audit(changed,self.checkpoint['transcript'],'product-session')
        records[1]['message']['tool_name']='another_tool'
        with self.assertRaisesRegex(ValueError,'name mismatch'):bridge.native_file_audit(records,self.checkpoint['transcript'],'product-session')
    def test_parent_symlink_and_deletion_unsupported(self):
        outside=Path(self.temp.name)/'outside';outside.mkdir()
        (self.home/'.kylin-agent-runtime').rename(outside/'state')
        (self.home/'.kylin-agent-runtime').symlink_to(outside/'state',target_is_directory=True)
        with self.assertRaisesRegex(ValueError,'linked native'):bridge.native_records(self.home,'kylin')
    def test_deleted_baseline_is_not_silent_success(self):
        evidence=self.evidence()
        before={'old.txt':{'size':3,'sha256':sha256('old'),'content_base64':base64.b64encode(b'old').decode()}}
        self.checkpoint['baseline']=before;evidence['baseline']=before
        self.assertEqual(self.verify(evidence)['status'],'unsupported')
        self.assertIn('old.txt',self.verify(evidence)['deleted_paths'])
    def test_failed_verification_still_saves_raw_evidence(self):
        from memobench.adapters_v2.native import NativeAdapter
        from memobench.adapters_v2.factory import native_capabilities
        evidence=self.evidence();evidence['complete']=False
        class Transport:
            def task_evidence(self,*args):return evidence
            def close(self):pass
        adapter=NativeAdapter(Transport(),native_capabilities());self.addCleanup(adapter.close)
        gold=Gold('p',[],[],[],[{'operation':'create','path':'reports/week.txt','sha256':sha256('hello')}],[],['recall'],['task_reuse'])
        prediction=Prediction('e','v','s2','p','ok','done','2026-01-01T00:00:00Z')
        with self.assertRaises(ContractError):adapter.verify_task(gold,prediction,self.checkpoint,'q')
        self.assertEqual(adapter.evidence_index[0]['evidence'],evidence)
        self.assertEqual(adapter.evidence_index[0]['verification_error_type'],'ContractError')

    def test_workspace_links_rejected(self):
        (self.home/'workspace/linked').symlink_to(self.database)
        with self.assertRaisesRegex(ValueError,'unsafe workspace'):bridge.workspace_snapshot(self.home)
    def test_forbidden_path_even_when_native_write_same_bytes(self):
        evidence=self.evidence();event=copy.deepcopy(evidence['audit']['events'][0]);event['path']='old/week.txt'
        evidence['audit']['events'].append(event)
        self.assertIn('old_path_reuse',self.verify(evidence)['faults'])

class BridgeAuditFailureTests(unittest.TestCase):
    def test_audit_failure_preserves_native_prediction_and_blocks_task(self):
        from memobench.protocol_v2 import FakeNativeAdapter
        from memobench.runner_v2 import execute_case
        from memobench.schema_v2 import Episode, Probe
        for unsafe in [False,True]:
            with self.subTest(unsafe=unsafe),tempfile.TemporaryDirectory() as tmp:
                base=Path(tmp);namespace='b'*32;root=base/'cases'/namespace;home=root/'home';(home/'workspace').mkdir(parents=True)
                (base/'provider.json').write_text('{}')
                binding={'run':'r','namespace':namespace,'episode_id':'e','variant_id':'v','session_id':'s','operation_id':'q','bridge_sha256':'fixture'}
                checkpoint={'binding':binding,'baseline':{},'transcript':bridge.transcript_checkpoint([])}
                control={'run_id':'r','product':'kylin','episode_id':'e','variant_id':'v','session':'s','sessions':{'s':{'product_session':'native-s'}},
                         'operations':{},'uncertain':False,'bridge_sha256':'fixture','artifact_checkpoints':{'q':checkpoint}}
                (root/'control.json').write_text(json.dumps(control))
                def invoke(*args):
                    target=home/'workspace/a.txt'
                    if unsafe:target.symlink_to(base/'provider.json')
                    else:target.write_text('hello')
                    return {'ok':True,'answer':'complete original native answer'}
                request={'bridge_sha256':hashlib.sha256(Path(bridge.__file__).read_bytes()).hexdigest(),'run_id':'r','namespace':namespace,
                         'method':'query','operation_id':'q','payload':{'episode_id':'e','variant_id':'v','session_id':'s','probe_id':'p','query':'public task'}}
                with patch.object(bridge,'BASE',base),patch.object(bridge,'invoke',side_effect=invoke),patch.object(bridge,'prepare_phase_policy',return_value={'phase':'query'}),patch.object(bridge,'native_file_audit',side_effect=ValueError('native tool result missing')):
                    response=bridge.dispatch(request,'kylin')
                self.assertEqual(response['status'],'ok');self.assertEqual(response['text'],'complete original native answer')
                saved=json.loads((root/(hashlib.sha256(b'q').hexdigest()+'.json')).read_text())['artifacts']
                self.assertFalse(saved['complete']);self.assertIn('audit_error_type',saved)
                class Adapter(FakeNativeAdapter):
                    def task_checkpoint(self,*args):return checkpoint
                    def query(self,*args):return Prediction.from_dict(response)
                    def verify_task(self,gold,prediction,*args):return verify_remote_task(gold,prediction,checkpoint,saved)
                gold=Gold('p',[],[],[],[{'operation':'create','path':'a.txt','sha256':sha256('hello')}],[],['recall'],['task_reuse'])
                episode=Episode('e','v','story','dev',['s'],[],[Probe('e','v','s','p','public task','2026-01-01T00:00:00Z')],[gold])
                result=execute_case(episode,Adapter,mode='native_agent',operation_prefix='r')
                self.assertEqual(result['results'][0]['prediction']['status'],'ok')
                self.assertEqual(result['results'][0]['prediction']['text'],'complete original native answer')
                self.assertEqual(result['results'][0]['task_status'],'blocked: artifact_evidence_not_verified')
