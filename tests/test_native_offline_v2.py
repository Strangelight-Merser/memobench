"""Synthetic regression exposures: no released stories, remote calls or credentials."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from memobench import runner_v2 as runner
from memobench.schema_v2 import Episode, Gold, Observation, Probe, Prediction
from memobench.sandbox_v2 import FileSandbox, sha256
from tools.probe_native_vm import acceptance_passed, operation_evidence

STAMP = '2026-01-01T00:00:00Z'

def episode():
    return Episode('synthetic', 'v1', 'synthetic-regression', 'dev', ['s1', 's2'],
        [Observation('synthetic', 'v1', 's1', 'o1', 'user', 'Write hello to reports/Qinghe/week.txt. Do not use old/Qinghe/week.txt.', STAMP)],
        [Probe('synthetic', 'v1', 's2', 'p', 'Perform the remembered task.', '2026-01-02T00:00:00Z')],
        [Gold('p', [], [], [], [{'operation': 'create', 'path': 'reports/Qinghe/week.txt',
          'sha256': sha256('hello'), 'old_paths': ['old/Qinghe/week.txt']}], [], ['update'], ['task_reuse'])])

class Transport:
    def __init__(self, root, *, old=False, preexisting=False, unknown=False, timeout=False, cleanup=False):
        self.box = None
        self.preexisting = preexisting
        self.old, self.unknown, self.timeout, self.cleanup = old, unknown, timeout, cleanup
        self.calls = []
    def task_checkpoint(self, operation_id, payload, home):
        return {'sandbox': self.box, 'binding': {'run': home.parent.name, 'namespace': home.name} | {k: payload[k] for k in ('episode_id', 'variant_id', 'session_id')} | {'operation_id': operation_id}}
    def request(self, method, operation_id, payload, home):
        self.calls.append((method, operation_id, payload))
        assert 'expected_actions' not in json.dumps(payload)
        if method == 'reset_case':
            self.box = FileSandbox(home / 'files')
            if self.preexisting:
                self.box.execute('create', 'preexisting', path='reports/Qinghe/week.txt', text='hello')
        if method == 'query':
            if not self.timeout:
                self.box.execute('create', operation_id, path='reports/Qinghe/week.txt', text='hello')
                if self.old:
                    self.box.execute('create', operation_id+':old', path='old/Qinghe/week.txt', text='hello')
            return Prediction(payload['episode_id'], payload['variant_id'], payload['session_id'], payload['probe_id'],
                              'timeout' if self.timeout else 'ok', None if self.timeout else 'native full answer', STAMP).to_dict()
        return {'operation_id': operation_id, 'status': 'unknown' if (method == 'observe' and self.unknown) or (method == 'close' and self.cleanup) else 'ready', 'usage': None}
    def close(self):
        self.box.close()

class OfflineNativeTests(unittest.TestCase):
    def run_case(self, **settings):
        with tempfile.TemporaryDirectory() as tmp:
            transport = Transport(tmp, **settings)
            with patch.object(runner, 'load_dataset', return_value=[episode()]), patch.object(runner, 'validate_release', return_value={'release_status': 'pending_review'}), patch.object(runner, 'FakeComponentAdapter', side_effect=AssertionError('component forbidden')), patch.object(runner, 'fixture_reader', side_effect=AssertionError('reader forbidden')):
                result = runner.run({'dataset': str(Path(tmp)), 'split': 'dev', 'mode': 'native_agent', 'execution': 'offline', 'adapter': 'kylin'}, Path(tmp)/'out', native_transport_factory=lambda product: transport)
            case = json.loads(next((Path(tmp)/'out/cases').glob('*.json')).read_text())['attempts'][0]
            return result, case, transport.calls
    def test_formal_run_native_and_actual_files(self):
        summary, case, calls = self.run_case()
        self.assertEqual(summary['status'], 'completed')
        self.assertTrue(summary['fixture'])
        self.assertEqual(case['results'][0]['prediction']['text'], 'native full answer')
        self.assertEqual(case['results'][0]['task_status'], 'passed')
        self.assertEqual([p['session_id'] for m, _, p in calls if m == 'begin_session'], ['s1', 's2'])
        self.assertTrue(case['operation_evidence'][0]['audit'])
    def test_forbidden_old_path(self):
        _, case, _ = self.run_case(old=True)
        self.assertIn('old_path_reuse', case['results'][0]['task_verification']['faults'])
    def test_preexisting_file_cannot_pass(self):
        _, case, _ = self.run_case(preexisting=True)
        self.assertEqual(case['results'][0]['task_status'], 'failed')
    def test_timeout_and_dual_failure(self):
        _, case, _ = self.run_case(timeout=True, cleanup=True)
        self.assertEqual(case['results'][0]['prediction']['status'], 'timeout')
        self.assertEqual(case['error']['stage'], 'query')
        self.assertEqual(case['cleanup_error']['stage'], 'close')
    def test_unknown_observe_not_queried(self):
        _, case, calls = self.run_case(unknown=True, cleanup=True)
        self.assertEqual(case['blocked_write']['status'], 'unknown')
        self.assertFalse(any(m == 'query' for m, _, _ in calls))
        self.assertFalse(case['results'][0]['query_executed'])
        self.assertEqual(case['results'][0]['not_executed_reason'], 'prior_write_unknown')
    def test_export_error_and_missing_check(self):
        keys = ['same_session','cross_session','cross_case_no_canary','cross_case_unknown','file_task','cleanup']
        report = {'product': 'openclaw', 'checks': dict.fromkeys(keys, True)}
        self.assertTrue(acceptance_passed(report))
        self.assertFalse(acceptance_passed(report | {'evidence_export_error': True}))
        del report['checks']['cleanup']
        self.assertFalse(acceptance_passed(report))
    def test_multiple_actions_keep_verification_cardinality(self):
        from memobench.adapters_v2.factory import native_factory
        e = episode()
        e.golds[0].expected_actions.append({'operation':'create','path':'reports/second.txt','sha256':sha256('second')})
        with tempfile.TemporaryDirectory() as tmp:
            transport=Transport(tmp)
            result=runner.execute_case(e,native_factory('openclaw', execution='offline', transport_factory=lambda _:transport),
                                       mode='native_agent', operation_prefix='multi')
        checks=result['results'][0]['task_verification']['checks']
        self.assertEqual(len(checks),2)
        self.assertEqual(checks[0]['status'],'passed')
        self.assertEqual(checks[1]['status'],'failed')
        self.assertIsNone(result['error'])

    def test_gate_precedes_transport(self):
        from memobench.adapters_v2.factory import native_factory
        with patch('memobench.adapters_v2.factory.SSHVMTransport', side_effect=AssertionError('transport constructed')):
            with self.assertRaisesRegex(ValueError, 'live_required'):
                native_factory('kylin', execution='online')
            with self.assertRaisesRegex(ValueError, 'approval_required'):
                native_factory('kylin', execution='online', live=True)

    def test_reviewed_online_factory_reachable_only_after_hash_checks(self):
        from memobench.adapters_v2 import factory
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); config=root/'ssh-config'; config.write_text('fixture, no real host')
            bridge=Path(factory.__file__).resolve().parents[2]/'tools/native_vm_product.py'
            settings={'ssh_config':str(config), 'purpose':'development_acceptance', 'acceptance':str(root/'acceptance.json'),
                      'bridge_sha256':hashlib.sha256(bridge.read_bytes()).hexdigest(),
                      'config_sha256':hashlib.sha256(config.read_bytes()).hexdigest(), 'dataset_sha256':'fixture-data'}
            evidence={'product':'openclaw','execution':'online','status':'passed','checks':dict.fromkeys(factory.REQUIRED_CHECKS,True),
                      **{k:settings[k] for k in ('bridge_sha256','config_sha256','dataset_sha256')}}
            evidence.update(canary='fixture-canary', events=[], exports=[])
            for case, queries in [('memory',[('q1','s1','fixture-canary'),('q2','s2','fixture-canary'),('q3','s2','done')]),('isolation',[('q4','s1','不知道')])]:
                namespace='fixture-'+case
                reset='reset-'+case
                binding={'namespace':namespace,'operation_id':reset,'session_id':None,'method':'reset_case','bridge_sha256':settings['bridge_sha256']}
                exported={'control.json':{'episode_id':case,'variant_id':'v','bridge_sha256':settings['bridge_sha256'],'closed':True,
                    'operations':{reset:{'method':'reset_case','status':'completed','session_id':None,'evidence':'reset.json'}}},
                    'reset.json':{'binding':binding,'mount_isolation':'passed','private_sentinel_present_outside':True,'private_sentinel_visible_inside':False}}
                evidence['events'].append({'method':'reset_case','episode_id':case,'variant_id':'v','receipt':{'operation_id':reset}})
                for probe,session,answer in queries:
                    exported['control.json']['operations'][probe]={'method':'query','status':'completed','session_id':session,'evidence':probe+'.json'}
                    exported[probe+'.json']={'binding':binding | {'operation_id':probe,'session_id':session,'method':'query'},'answer':answer,
                        'files_before':{},'files_after':{'workspace/notes/code.txt':hashlib.sha256(b'fixture-canary\n').hexdigest()}}
                    evidence['events'].append({'method':'query','operation_id':probe,'input':{'episode_id':case,'variant_id':'v','session_id':session,'probe_id':probe},
                                               'prediction':{'status':'ok','text':answer}})
                export_raw=json.dumps(exported).encode(); export_path=root/(case+'.json'); export_path.write_bytes(export_raw)
                evidence['exports'].append({'namespace':namespace,'path':str(export_path),'sha256':hashlib.sha256(export_raw).hexdigest()})
            raw=json.dumps(evidence).encode(); (root/'acceptance.json').write_bytes(raw)
            settings['acceptance_sha256']=hashlib.sha256(raw).hexdigest()
            validation={'release_status':'accepted','content_sha256':'fixture-data'}
            with patch.object(factory,'SSHVMTransport') as ssh, patch.object(factory,'NativeAdapter') as adapter:
                make=factory.native_factory('openclaw',execution='online',live=True,settings=settings,validation=validation)
                ssh.assert_not_called()
                make(); ssh.assert_called_once_with(str(config),'openclaw',live=True)
                config.write_text('changed')
                with self.assertRaisesRegex(ValueError,'configuration_hash_mismatch'):
                    factory.native_factory('openclaw',execution='online',live=True,settings=settings,validation=validation)
                self.assertEqual(ssh.call_count,1)
                config.write_text('fixture, no real host')
                entry=evidence['exports'][0]
                raw_export=json.loads(Path(entry['path']).read_bytes())
                raw_export['reset.json']['private_sentinel_visible_inside']=True
                changed=json.dumps(raw_export).encode(); Path(entry['path']).write_bytes(changed)
                entry['sha256']=hashlib.sha256(changed).hexdigest()
                changed_acceptance=json.dumps(evidence).encode(); (root/'acceptance.json').write_bytes(changed_acceptance)
                settings['acceptance_sha256']=hashlib.sha256(changed_acceptance).hexdigest()
                with self.assertRaisesRegex(ValueError,'mount_isolation_NOT_VERIFIED'):
                    factory.native_factory('openclaw',execution='online',live=True,settings=settings,validation=validation)
                self.assertEqual(ssh.call_count,1)


    def test_missing_profile_terminal_cannot_pass(self):
        keys = ['same_session','cross_session','cross_case_no_canary','cross_case_unknown','file_task','cleanup',
                'profile_cross_session','profile_persisted','profile_prompt_injected','profile_turns_completed']
        report = {'product':'kylin','checks':dict.fromkeys(keys, True)}
        self.assertTrue(acceptance_passed(report))
        del report['checks']['profile_turns_completed']
        self.assertFalse(acceptance_passed(report))

    def test_component_file_disclosure_preserved(self):
        from memobench.protocol_v2 import FakeComponentAdapter
        e = episode()
        e.golds[0].forget_policies = [{'slot': 'secret', 'mode': 'literal_disclosure', 'values': ['hello']}]
        def reader(probe, recalled):
            return Prediction('synthetic','v1','s2','p','ok','done',STAMP,
                file_actions=[{'operation':'create','arguments': {'path':'reports/Qinghe/week.txt','text':'hello'}}])
        result = runner.execute_case(e, FakeComponentAdapter, mode='component', operation_prefix='privacy', reader=reader)
        self.assertTrue(result['results'][0]['score']['metrics']['forgotten_disclosure'])

    def test_bridge_dispatch_query_timeout(self):
        from tools import native_vm_product as bridge
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            namespace = 'a' * 32
            root = base / 'cases' / namespace
            root.mkdir(parents=True)
            (base / 'provider.json').write_text('{}')
            control = {'product':'kylin', 'episode_id':'synthetic', 'variant_id':'v1', 'session':'s2',
                       'sessions':{'s2':{}}, 'operations':{}, 'uncertain':False, 'bridge_sha256':'fixture'}
            (root/'control.json').write_text(json.dumps(control))
            request = {'bridge_sha256':hashlib.sha256(Path(bridge.__file__).read_bytes()).hexdigest(), 'namespace':namespace, 'method':'query', 'operation_id':'timeout-query',
                       'payload':episode().probes[0].to_public()}
            with patch.object(bridge, 'BASE', base), patch.object(bridge, 'invoke', return_value={'ok':False,'timeout':True}):
                response = bridge.dispatch(request, 'kylin')
            self.assertEqual(response['status'], 'timeout')
            self.assertTrue(json.loads((root/'control.json').read_text())['uncertain'])

    def test_operation_evidence_binding(self):
        binding = {'namespace':'n', 'operation_id':'o', 'session_id':'s2', 'method':'query', 'bridge_sha256':'v'}
        export = {'control.json': {'bridge_sha256':'v', 'operations': {'o': {'status':'completed', 'method':'query', 'session_id':'s2', 'evidence':'e.json'}}}, 'e.json': {'binding':binding}}
        self.assertEqual(operation_evidence(export, 'n','o','s2','query','v')['binding'], binding)
        for key, value in [('session_id','old'), ('operation_id','old'), ('bridge_sha256','old')]:
            changed=copy.deepcopy(export); changed['e.json']['binding'][key]=value
            with self.assertRaises(ValueError): operation_evidence(changed, 'n','o','s2','query','v')

class ProbeExportTests(unittest.TestCase):
    def fixture(self, episode_id='profile'):
        from tools.probe_native_vm import inspect_export
        report={'product':'kylin','checks':{},'events':[]}
        control={'episode_id':episode_id,'variant_id':'v','bridge_sha256':'v','operations':{}}
        export={'control.json':control}
        for index, sid in enumerate(['p1','p2'] if episode_id=='profile' else ['s2']):
            op='op'+str(index)
            report['events'].append({'method':'query','operation_id':op,'input':{'episode_id':episode_id,'variant_id':'v','session_id':sid,'probe_id':'q3'}})
            control['operations'][op]={'method':'query','session_id':sid,'status':'completed','evidence':op+'.json'}
            export[op+'.json']={'binding':{'namespace':'n','operation_id':op,'session_id':sid,'method':'query','bridge_sha256':'v'},'profile_completed':True,'native_profile_prompt':'nick','files_before':{},'files_after':{'workspace/notes/code.txt':hashlib.sha256(b'code\n').hexdigest()}}
        return report, export, inspect_export
    def test_raw_profile_missing_one_terminal(self):
        report,export,inspect=self.fixture()
        good,_=inspect(report,export,'n','code','nick','v')
        self.assertTrue(good['checks']['profile_turns_completed'])
        del export['op0.json']['profile_completed']
        bad,_=inspect(report,export,'n','code','nick','v')
        self.assertFalse(bad['checks']['profile_turns_completed'])
    def test_q3_preexisting_file(self):
        report,export,inspect=self.fixture('memory')
        good,_=inspect(report,export,'n','code','nick','v')
        self.assertTrue(good['checks']['file_task'])
        export['op0.json']['files_before']=export['op0.json']['files_after']
        bad,_=inspect(report,export,'n','code','nick','v')
        self.assertFalse(bad['checks']['file_task'])
    def test_complete_old_session_and_version_fail(self):
        for mismatch in ['session','version']:
            report,export,inspect=self.fixture()
            if mismatch=='session':
                export['control.json']['operations']['op1']['session_id']='old'
                export['op1.json']['binding']['session_id']='old'
            else:
                export['control.json']['bridge_sha256']='old'
                for item in ['op0.json','op1.json']: export[item]['binding']['bridge_sha256']='old'
            bad,_=inspect(report,export,'n','code','nick','v')
            self.assertTrue(bad['evidence_export_error'])
