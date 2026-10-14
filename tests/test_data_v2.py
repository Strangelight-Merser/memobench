"""卡2离线验收；不访问 API，不冒充人工签收。"""
import copy
from collections import Counter
import json
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from memobench.data_v2 import (build_dataset, encode, generate, load_dataset,
                               build_review_page, digest, read_rows, safe_path, truth,
                               validate_release, validate_sources)
from memobench.protocol_v2 import adapter_payload
from memobench.schema_v2 import ContractError, Episode, validate_dataset

ROOT = Path(__file__).resolve().parents[1] / 'data/v0.2'


class DataV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stories = read_rows(ROOT / 'sources.jsonl')
        cls.episodes = generate(cls.stories)

    def test_frozen_schema_roundtrip(self):
        for e in self.episodes:
            self.assertEqual(Episode.from_json(e.to_json()).to_dict(), e.to_dict())

    def test_seed_bytes_and_stream_isolation(self):
        first = ''.join(e.to_json() for e in self.episodes)
        self.assertEqual(first, ''.join(e.to_json() for e in generate(self.stories)))
        larger = generate(self.stories, context_chars=8192)
        for a, b in zip(self.episodes, larger):
            self.assertEqual(a.golds, b.golds)
            self.assertEqual(a.probes, b.probes)
            ids = {v.observation_id for v in a.golds[0].evidence}
            self.assertEqual([o for o in a.observations if o.observation_id in ids],
                             [o for o in b.observations if o.observation_id in ids])

    def test_forty_turns_and_character_scale(self):
        for size in (2048, 8192, 32768):
            for e in generate(self.stories[:1], context_chars=size):
                self.assertEqual(sum(len(o.text) for o in e.observations), size)
                for session in e.session_ids:
                    self.assertEqual(sum(o.session_id == session for o in e.observations), 40)
        self.assertTrue(generate(self.stories[:1], context_chars=32768, turns_per_session=100))
        with self.assertRaises(ValueError):
            generate(self.stories[:1], context_chars=2)

    def test_story_template_split(self):
        validate_sources(self.stories)
        validate_dataset(self.episodes)
        dev = {s['template_id'] for s in self.stories if s['split'] == 'dev'}
        test = {s['template_id'] for s in self.stories if s['split'] == 'test'}
        self.assertFalse(dev & test)
        bad = copy.deepcopy(self.stories)
        other = next(s for s in bad if s['split'] != bad[0]['split'])
        other['template_id'] = bad[0]['template_id']
        with self.assertRaises(ContractError):
            validate_sources(bad)

    def test_two_variants_share_truth(self):
        for a, b in zip(self.episodes[::2], self.episodes[1::2]):
            self.assertEqual(a.story_id, b.story_id)
            self.assertEqual(a.golds, b.golds)
            self.assertNotEqual(a.probes[0].query, b.probes[0].query)

    def test_ledger_is_independent_from_wording(self):
        story = copy.deepcopy(self.stories[4])
        expected = truth(story['events'], story['targets'])
        story['utterances'] = [['无关文本。', '其他文本。'] for _ in story['utterances']]
        self.assertEqual(generate([story])[0].golds[0].slots, expected)
        self.assertEqual(expected[0].value, 'kitty')

    def test_architecture_requires_evidence(self):
        by_template = {s['template_id']: s for s in self.stories}
        unknown = by_template['dragon_brand_unknown_arch']
        self.assertEqual(truth(unknown['events'], unknown['targets'])[0].state, 'unknown')
        known = by_template['two_device_arch_evidence']
        self.assertEqual(truth(known['events'], known['targets'])[0].value, 'aarch64')

    def test_conflict_forget_and_inference(self):
        values = {s['template_id']: truth(s['events'], s['targets']) for s in self.stories}
        self.assertEqual(values['conflicting_delivery_locations'][0].state, 'conflict')
        slots = values['forget_canary_keep_template']
        self.assertEqual(slots[0].state, 'forgotten')
        self.assertEqual(slots[1].value, 'notes/today.txt')
        self.assertEqual(values['folder_filename_inference'][0].value, 'reports/May/summary.txt')
        with self.assertRaises(ContractError):
            truth([{'op':'bad','key':'x'}], [])

    def test_private_fields_never_exported(self):
        forbidden = {'golds','canonical_state_ledger','expected_actions','forget_policies',
                     'technical_categories','official_capabilities','story_id','split','targets'}
        def walk(value):
            if isinstance(value, dict):
                self.assertFalse(set(value) & forbidden)
                for v in value.values(): walk(v)
            elif isinstance(value, list):
                for v in value: walk(v)
        for e in self.episodes:
            walk(e.to_public())
            for item in e.observations + e.probes:
                walk(adapter_payload(item))
            with self.assertRaises(ContractError):
                adapter_payload(e)

    def test_paths_reject_escape_and_symlink(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            root = Path(directory)
            (root / 'link').symlink_to(outside, target_is_directory=True)
            for path in ('../escape', '/tmp/escape', 'a/../../escape', 'link/file', 'a\\b'):
                with self.subTest(path=path), self.assertRaises(ContractError):
                    safe_path(root, path)
            self.assertEqual(safe_path(root, 'reports/Result.txt'), root.resolve() / 'reports/Result.txt')
        bad = copy.deepcopy(next(s for s in self.stories if s.get('file_task')))
        for event in bad['events']:
            if event['key'] == 'output_path': event['value'] = '../escape'
        with self.assertRaises(ContractError):
            generate([bad])

    def test_static_release_is_offline_and_pending(self):
        with patch('urllib.request.urlopen', side_effect=AssertionError('禁止联网')):
            result = validate_release(ROOT)
            self.assertEqual(result['validation'], 'ok')
            self.assertEqual(result['formal_test_n_query'], 0)
            self.assertEqual(load_dataset(ROOT, 'test'), [])

    def test_build_deterministic_and_review_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            # 小集合足以覆盖构建/签收逻辑，不重建全部发布文件。
            (root / 'sources.jsonl').write_text(encode(self.stories[0]), encoding='utf-8')
            build_dataset(root)
            first = {p.name: p.read_bytes() for p in root.iterdir()}
            build_dataset(root)
            self.assertEqual(first, {p.name: p.read_bytes() for p in root.iterdir()})
            self.assertEqual(validate_release(root)['formal_test_n_query'], 0)
            review = read_rows(root / 'review.jsonl')[0]
            review.update(status='accepted', reviewer='fixture-reviewer',
                          reviewed_at='2026-10-14T00:00:00Z',
                          ledger_query_checked=True, all_variants_checked=True)
            (root / 'review.jsonl').write_text(encode(review), encoding='utf-8')
            build_dataset(root)
            self.assertEqual(validate_release(root)['formal_test_n_query'], 2)
            review['source_sha256'] = '0' * 64
            (root / 'review.jsonl').write_text(encode(review), encoding='utf-8')
            build_dataset(root)
            with self.assertRaises(ContractError): validate_release(root)

    def test_tampered_public_and_unsigned_test_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'sources.jsonl').write_text(encode(self.stories[0]), encoding='utf-8')
            build_dataset(root)
            (root / 'test.jsonl').write_bytes((root / 'candidates.jsonl').read_bytes())
            with self.assertRaises(ContractError): validate_release(root)

    def test_evidence_and_actions(self):
        for e in self.episodes:
            ids = {o.observation_id for o in e.observations}
            self.assertTrue({v.observation_id for v in e.golds[0].evidence} <= ids)
            for action in e.golds[0].expected_actions:
                self.assertEqual(action['operation'], 'write_file')
                self.assertFalse(action['path'].startswith('/'))

    def test_sixty_story_budget_and_pending_review(self):
        self.assertEqual(len(self.stories), 60)
        self.assertEqual(len(self.episodes), 120)
        self.assertEqual(Counter(s['split'] for s in self.stories), {'dev': 12, 'test': 48})
        counts = Counter((s['official_capability'], s['split']) for s in self.stories)
        self.assertEqual(len(counts), 12)
        for (_, split), count in counts.items():
            self.assertEqual(count, 2 if split == 'dev' else 8)
        reviews = read_rows(ROOT / 'review.jsonl')
        self.assertEqual(len(reviews), 60)
        self.assertTrue(all(r['status'] == 'pending_review' and r['reviewer'] is None
                            and r['reviewed_at'] is None for r in reviews))

    def test_expanded_truth_regressions(self):
        slots = {s['template_id']: {v.name: v for v in truth(s['events'], s['targets'])}
                 for s in self.stories}
        for name, key in [('device_replacement_unknown_arch', 'new.arch'),
                          ('unknown_package_tool_from_runtime', 'package_manager'),
                          ('missing_filename_blocks_path', 'output_path'),
                          ('sample_identity_not_self', 'self.occupation'),
                          ('dev_unseen_task_completion', 'backup.completed')]:
            self.assertEqual(slots[name][key].state, 'unknown')
            self.assertIsNone(slots[name][key].value)
        self.assertEqual(slots['runtime_vs_package_tool']['package.tool'].value, 'apt')
        self.assertEqual(slots['runtime_vs_package_tool']['kare.name'].value, 'Kylin Agent Runtime')
        self.assertEqual(slots['correction_of_measurement_transcription']['device_a.arch'].value, 'aarch64')
        self.assertEqual(slots['device_owner_not_operator']['self.desktop.arch'].value, 'x86_64')
        self.assertEqual(slots['case_sensitive_paths_distinct']['a.path'].value, 'work/Map')
        self.assertEqual(slots['authoritative_conflict_resolution']['board.location'].value, '西厅')
        self.assertEqual(slots['unresolved_equal_authority']['meeting.time'].state, 'conflict')
        self.assertEqual(slots['forget_contact_keep_preference']['contact'].state, 'forgotten')
        self.assertEqual(slots['forget_contact_keep_preference']['language'].value, '中文')

    def test_expansion_preserves_existing_review(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'sources.jsonl'
            source.write_text(encode(self.stories[0]), encoding='utf-8')
            build_dataset(root)
            review = read_rows(root / 'review.jsonl')[0]
            review.update(status='rejected', reason='fixture: 需要补充证据')
            previous = encode(review)
            (root / 'review.jsonl').write_text(previous, encoding='utf-8')
            source.write_text(''.join(encode(s) for s in self.stories[:2]), encoding='utf-8')
            build_dataset(root)
            self.assertTrue((root / 'review.jsonl').read_text(encoding='utf-8').startswith(previous))
            rows = read_rows(root / 'review.jsonl')
            self.assertEqual(rows[1]['status'], 'pending_review')
            self.assertEqual(rows[1]['source_sha256'], digest(self.stories[1]))
            self.assertEqual(validate_release(root)['formal_test_n_query'], 0)

    def test_source_pair_and_order_validation(self):
        for field, value in [('queries', ['相同', '相同']), ('split', 'formal'),
                             ('official_capability', 'invented')]:
            bad = copy.deepcopy(self.stories[:1])
            bad[0][field] = value
            with self.assertRaises(ContractError):
                validate_sources(bad)
        bad = copy.deepcopy(next(s for s in self.stories if s['template_id'] == 'version_upgrade_observation'))
        bad['events'].reverse()
        with self.assertRaises(ContractError):
            validate_sources([bad])

    def test_review_page_frozen_payload_and_safe_embedding(self):
        page = (ROOT.parents[1] / 'docs/review/data-review.html').read_text(encoding='utf-8')
        raw = page.split('<script type="application/json" id="dataset">', 1)[1].split('</script>', 1)[0]
        payload = json.loads(raw)
        self.assertEqual([r['source'] for r in payload['stories']], self.stories)
        self.assertEqual(payload['source_sha256'], hashlib.sha256((ROOT / 'sources.jsonl').read_bytes()).hexdigest())
        self.assertEqual(sum(len(r['episodes']) == 3 for r in payload['stories']), 12)
        self.assertNotIn('src=', page)
        self.assertNotIn('innerHTML', page)
        self.assertNotIn('fetch(', page)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            story = copy.deepcopy(self.stories[0])
            story['queries'][0] = '</script><script>alert(1)</script>'
            (root / 'sources.jsonl').write_text(encode(story), encoding='utf-8')
            build_dataset(root)
            build_review_page(root, root / 'review.html')
            rendered = (root / 'review.html').read_text(encoding='utf-8')
            self.assertNotIn('</script><script>alert(1)', rendered)
            self.assertIn('\\u003c/script\\u003e', rendered)


if __name__ == '__main__':
    unittest.main()
