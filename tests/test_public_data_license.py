"""Current public permission never rewrites original quality/approval evidence."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from memobench import data_license as license
from memobench.cli_v2 import main


class PublicDataLicenseTests(unittest.TestCase):
    def fixture(self,root):
        for name in license.DATASETS:
            p=root/name;p.mkdir(parents=True)
            (p/'sources.jsonl').write_text('{"synthetic":"original fixture"}\n')
        record={'schema_version':'public-data-license-1','license_id':'CC-BY-4.0','license_url':license.LICENSE_URL,'attribution':'MemoBench contributors','authorization':{'source':'direct_user_message_current_thread','authority':'project_maintainer_user','statement':license.AUTHORIZATION},'datasets':{name:license.inventory(root,name) for name in license.DATASETS}}
        (root/'data/PUBLIC_LICENSE.json').write_text(json.dumps(record))
        return record

    def test_actual_public_license_and_cli_keep_historical_quality_state(self):
        permission=license.validate_public_license()
        self.assertEqual(permission['status'],'accepted')
        self.assertEqual(permission['license_id'],'CC-BY-4.0')
        for name,quality in zip(license.DATASETS,('pending_review','accepted_internal')):
            output=io.StringIO()
            with contextlib.redirect_stdout(output):code=main(['validate','--dataset',str(license.ROOT/name)])
            self.assertEqual(code,0)
            result=json.loads(output.getvalue())
            self.assertEqual(result['license_status'],'accepted')
            self.assertEqual(result['public_license']['status'],'accepted')
            self.assertNotEqual(result['historical_snapshot_license_status'],'accepted')
            self.assertEqual(result['release_status'],quality)
        self.assertFalse(permission['quality_approval_changed'])

    def test_changed_data_is_not_covered_by_snapshot_hashes(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve();self.fixture(root)
            self.assertEqual(license.validate_public_license(root)['status'],'accepted')
            (root/license.DATASETS[0]/'sources.jsonl').write_text('changed synthetic fixture')
            with self.assertRaisesRegex(ValueError,'content hash mismatch'):license.validate_public_license(root)

    def test_authorization_source_and_license_cannot_be_self_asserted(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve();record=self.fixture(root);path=root/'data/PUBLIC_LICENSE.json'
            for key,value in (('source','agent_inference'),('authority','unknown_signer'),('statement','approve')):
                changed=json.loads(json.dumps(record));changed['authorization'][key]=value;path.write_text(json.dumps(changed))
                with self.assertRaisesRegex(ValueError,'authorization mismatch'):license.validate_public_license(root)
            changed=json.loads(json.dumps(record));changed['license_id']='other';path.write_text(json.dumps(changed))
            with self.assertRaises(ValueError):license.validate_public_license(root)

    def test_unknown_material_and_links_are_not_in_authorized_scope(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve();self.fixture(root)
            with self.assertRaisesRegex(ValueError,'not covered'):license.validate_public_license(root,root/'other')
            p=root/license.DATASETS[0]/'linked';p.symlink_to(root/'data/PUBLIC_LICENSE.json')
            with self.assertRaisesRegex(ValueError,'linked'):license.validate_public_license(root)

if __name__=='__main__':unittest.main()
