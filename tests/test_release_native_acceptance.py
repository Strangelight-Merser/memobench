"""Release acceptance verifies evidence; synthetic negatives never edit originals."""
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('release_native_gate',ROOT/'tools/check_release.py')
release=importlib.util.module_from_spec(spec);spec.loader.exec_module(release)


class NativeReleaseAcceptanceTests(unittest.TestCase):
    def test_selected_native_acceptance_is_recomputed_and_not_full_release(self):
        result=release.check(ROOT)
        self.assertEqual(result['errors'],[])
        native=result['native_cli_acceptance']
        self.assertEqual(native['status'],'historical_native_cli_passed')
        self.assertEqual(set(native['products']),{'kylin','openclaw'})
        for product in native['products'].values():
            self.assertEqual(product['observations_verified'],80)
            self.assertEqual(product['probe']['status'],'passed')
        self.assertEqual(result['default_native_dataset']['release_status'],'accepted_internal')
        self.assertEqual(result['release_status'],'blocked')
        self.assertTrue(any('judge calibration' in x for x in result['blockers']))
        self.assertFalse(any('native agents and openKylin NOT_VERIFIED' in x for x in result['blockers']))
        self.assertEqual(native['current_bridge_online_hash_match'],native['current_bridge_sha256']==native['verified_bridge_sha256'])

    def test_primary_booleans_alone_cannot_pass_without_original_raw(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve();base=root/release.NATIVE_EVIDENCE;base.mkdir(parents=True)
            shutil.copyfile(ROOT/release.NATIVE_EVIDENCE/'review_complete_run.py',base/'review_complete_run.py')
            (base/'PRIMARY_KYLIN_COMPLETE_RUN_REVIEW.json').write_text(json.dumps({'products':{'kylin':{'task_verification':'passed','observations_verified':80,'cleanup_verified':True}}}))
            (base/'cli-final/run-kylin/cases').mkdir(parents=True)
            (base/'cli-final/raw-kylin').mkdir()
            with self.assertRaises((ValueError,KeyError,OSError)):
                release.native_cli_acceptance(root)

    def test_raw_hash_corruption_is_rejected_before_recomputation(self):
        actual_sha=release.sha
        def corrupt(path):
            return '0'*64 if path.parent.name=='raw-kylin' else actual_sha(path)
        with patch.object(release,'sha',side_effect=corrupt):
            with self.assertRaisesRegex(ValueError,'case/raw hash mismatch'):
                release.native_cli_acceptance(ROOT)

    def test_probe_summary_true_without_exports_cannot_pass(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve()
            (root/'probe.json').write_text(json.dumps({'product':'openclaw','execution':'online','status':'passed','checks':{'cleanup':True,'file_task':True},'exports':[],'cleanup_receipts':[]}))
            with self.assertRaisesRegex(ValueError,'cleanup missing'):
                release.verify_probe(root,'openclaw')

    def test_current_probe_raw_digest_must_match(self):
        bundle=ROOT/release.NATIVE_EVIDENCE/'direct-tools-revision/probe-openclaw'
        with patch.object(release,'sha',return_value='0'*64):
            with self.assertRaisesRegex(ValueError,'export hash mismatch'):
                release.verify_probe(bundle,'openclaw')

    def test_native_recipe_cannot_hide_missing_or_forged_dataset(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve();(root/'configs/experiments').mkdir(parents=True)
            recipe={'schema_version':'native-run-recipe-1','dataset':'data/forged','split':'test','purpose':'internal_evaluation','products':['kylin','openclaw']}
            (root/'configs/experiments/native.json').write_text(json.dumps(recipe))
            self.assertIn('invalid or missing default native recipe dataset',release.check(root)['errors'])
            (root/'data/forged').mkdir(parents=True)
            (root/'data/forged/manifest.json').write_text(json.dumps({'status':'accepted_internal','formal_test_n_query':94}))
            self.assertIn('invalid or missing default native recipe dataset',release.check(root)['errors'])

    def test_scan_covers_new_source_data_and_integration_without_echo(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve();secret='sk-'+'Z'*32
            paths=('memobench/new.py','tools/new.py','data/v0.2-ai-reviewed/new.json','docs/integrations/new.txt','docs/delivery/new.txt')
            for name in paths:
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(secret)
            result=release.check(root)
            for name in paths:self.assertIn('possible plaintext credential: '+name,result['errors'])
            self.assertNotIn(secret,json.dumps(result))

    def test_only_known_public_synthetic_key_placeholder_is_exempt(self):
        pattern=release.SECRET_PATTERNS[-1]
        self.assertIsNone(pattern.search("api_key='synthetic-unused-no-api'"))
        self.assertIsNotNone(pattern.search("api_key='synthetic-real-value-123456789'"))
        self.assertIsNotNone(pattern.search("api_key='synthetic-unused-no-api-extra'"))

    def test_plan_relative_links_resolve_and_missing_zip_is_not_linked(self):
        import re
        page=ROOT/'docs/plan-v2/FULL_RESPONSE.md';text=page.read_text()
        for link in re.findall(r'\]\(([^)]+)\)',text):
            if not link.startswith(('https://','http://')):self.assertTrue((page.parent/link).is_file(),link)
        self.assertIn('归档未随源码提供',text)
        self.assertNotIn('../02_execution_pack/',text)


if __name__=='__main__':unittest.main()
