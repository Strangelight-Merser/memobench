"""卡1合同验收；全部离线，不调用真实智能体。"""
import copy
import json
import unittest
from dataclasses import replace

from memobench.schema_v2 import (
    AdapterCapabilities, ContractError, Episode, EvidenceLocation, Gold,
    ModelRecord, Observation, Prediction, Probe, RunManifest, SandboxReference,
    Slot, validate_dataset, validate_prediction,
)
from memobench.protocol_v2 import (
    FakeComponentAdapter, FakeNativeAdapter, RecallResult, UnsupportedCapability,
    WriteReceipt, adapter_payload, public_log_record, require_capability, require_ready,
)

T0 = "2026-10-14T10:00:00Z"
T1 = "2026-10-14T11:00:00+00:00"
PRIVATE = "private-canary-17"


def episode():
    observation = Observation("e1", "v1", "s1", "o1", "user", "编辑器用 Vim。", T0)
    probe = Probe("e1", "v1", "s2", "p1", "编辑器用什么？", T1)
    gold = Gold("p1", [Slot("editor", "string", "answer", PRIVATE)],
                [EvidenceLocation("o1", 0, 3)], [{"state": PRIVATE}],
                [{"expected": PRIVATE}], [{"policy": PRIVATE}],
                ["recall"], ["long_term_retention"])
    return Episode("e1", "v1", "story1", "dev", ["s1", "s2"], [observation], [probe], [gold])


def manifest():
    return RunManifest("run1", "native_agent", "offline", "fake", "contract-0.2",
                       AdapterCapabilities(native_answer="supported"),
                       [ModelRecord("fixture", "endpoint1", "requested", "returned",
                                    {"temperature": 0, "nested": [None, True]}, None, None, T0)],
                       T0, T1, "a" * 64, "b" * 64, "c" * 64)


class ContractTests(unittest.TestCase):
    def test_json_roundtrip(self):
        e = episode()
        objects = [e, e.observations[0], e.probes[0], e.golds[0], manifest(),
                   AdapterCapabilities(), SandboxReference("r1", "work/a.txt"),
                   Prediction("e1", "v1", "s2", "p1", "ok", "Vim", T1),
                   WriteReceipt("op1", "unknown"), RecallResult("unsupported", [])]
        for obj in objects:
            with self.subTest(type=type(obj).__name__):
                self.assertEqual(type(obj).from_json(obj.to_json()), obj)
                self.assertEqual(type(obj).from_dict(json.loads(obj.to_json())), obj)

    def test_missing_required_fields(self):
        for obj in [episode(), episode().observations[0], episode().probes[0],
                    episode().golds[0], manifest()]:
            data = obj.to_dict()
            data.pop(next(iter(data)))
            with self.assertRaises(ContractError):
                type(obj).from_dict(data)

    def test_unknown_fields_and_json_duplicate_keys(self):
        data = episode().observations[0].to_dict()
        data["gold"] = PRIVATE
        with self.assertRaises(ContractError):
            Observation.from_dict(data)
        with self.assertRaises(ContractError):
            AdapterCapabilities.from_json('{"flush":"unknown","flush":"supported"}')

    def test_invalid_enums_and_types(self):
        for patch in [{"role": "human"}, {"text": 123}, {"episode_id": ""},
                      {"sandbox_references": {}}]:
            with self.subTest(patch=patch), self.assertRaises(ContractError):
                Observation.from_dict({**episode().observations[0].to_dict(), **patch})
        with self.assertRaises(ContractError):
            AdapterCapabilities(flush=True)
        with self.assertRaises(ContractError):
            replace(manifest(), mode="legacy")

    def test_time_validation(self):
        for value in ["2026-10-14", "2026-10-14T10:00:00", "2026-02-30T10:00:00Z", "bad"]:
            with self.subTest(value=value), self.assertRaises(ContractError):
                replace(episode().observations[0], observed_at=value)
        with self.assertRaises(ContractError):
            replace(manifest(), finished_at="2025-01-01T00:00:00Z")

    def test_duplicate_ids(self):
        e = episode()
        for patch in [{"session_ids": ["s1", "s1"]},
                      {"observations": e.observations * 2}, {"probes": e.probes * 2},
                      {"golds": e.golds * 2}]:
            with self.subTest(patch=list(patch)), self.assertRaises(ContractError):
                replace(e, **patch)
        with self.assertRaises(ContractError):
            validate_dataset([e, e])

    def test_wrong_references(self):
        e = episode()
        patches = [{"golds": [replace(e.golds[0], probe_id="missing")]},
                   {"probes": [replace(e.probes[0], session_id="missing")]},
                   {"observations": [replace(e.observations[0], variant_id="other")]},
                   {"golds": [replace(e.golds[0], evidence=[EvidenceLocation("missing")])]}]
        for patch in patches:
            with self.subTest(patch=list(patch)), self.assertRaises(ContractError):
                replace(e, **patch)

    def test_evidence_span_and_future(self):
        with self.assertRaises(ContractError):
            EvidenceLocation("o1", 2, 1)
        e = episode()
        with self.assertRaises(ContractError):
            replace(e, golds=[replace(e.golds[0], evidence=[EvidenceLocation("o1", 0, 100)])])
        with self.assertRaises(ContractError):
            replace(e, observations=[replace(e.observations[0], observed_at="2027-01-01T00:00:00Z")])

    def test_split_isolation(self):
        e = episode()
        other = copy.deepcopy(e.to_dict())
        other["variant_id"] = "v2"
        for item in other["observations"] + other["probes"]:
            item["variant_id"] = "v2"
        second = Episode.from_dict(other)
        validate_dataset([e, second])
        with self.assertRaises(ContractError):
            validate_dataset([e, replace(second, split="test")])

    def test_gold_stripping_and_logs(self):
        e = episode()
        e.observations[0].gold = PRIVATE
        public = e.to_public()
        self.assertNotIn(PRIVATE, json.dumps(public))
        for key in ["golds", "story_id", "split", "technical_categories", "official_capabilities"]:
            self.assertNotIn(key, public)
        self.assertNotIn(PRIVATE, repr(e))
        self.assertNotIn(PRIVATE, repr(e.golds[0]))
        for obj in (e.observations[0], e.probes[0]):
            self.assertNotIn(PRIVATE, json.dumps(adapter_payload(obj)))
            self.assertNotIn(PRIVATE, json.dumps(public_log_record(obj)))
        for obj in (e, e.golds[0], e.to_dict()):
            with self.assertRaises(ContractError):
                adapter_payload(obj)
            with self.assertRaises(ContractError):
                public_log_record(obj)
        with self.assertRaises(ContractError):
            e.golds[0].to_public()
        public["observations"][0]["text"] = "修改副本"
        self.assertNotEqual(e.observations[0].text, "修改副本")

    def test_errors_do_not_echo_private_values(self):
        data = episode().golds[0].to_dict()
        data["technical_categories"] = [PRIVATE]
        try:
            Gold.from_dict(data)
        except ContractError as error:
            self.assertNotIn(PRIVATE, str(error))
        else:
            self.fail("应拒绝非法分类")

    def test_two_taxonomies_not_renamed(self):
        gold = episode().golds[0]
        self.assertEqual(gold.technical_categories, ["recall"])
        self.assertEqual(gold.official_capabilities, ["long_term_retention"])
        with self.assertRaises(ContractError):
            replace(gold, official_capabilities=["recall"])
        with self.assertRaises(ContractError):
            replace(gold, technical_categories=["task_reuse"])

    def test_typed_slots(self):
        for args in [("editor", "string", "answer", 3), ("n", "number", "answer", True),
                     ("x", "string", "forgotten", PRIVATE)]:
            with self.assertRaises(ContractError):
                Slot(*args)
        self.assertEqual(Slot("path", "path", "answer", "/Work/A").value, "/Work/A")
        with self.assertRaises(ContractError):
            replace(episode().golds[0], slots=[Slot("n", "number", "answer", float("nan"))])

    def test_manifest_hash_and_unknown_model(self):
        m = manifest()
        self.assertIsNone(m.models[0].version)
        self.assertIsNone(m.models[0].digest)
        with self.assertRaises(ContractError):
            replace(m, code_hash="unknown")
        with self.assertRaises(ContractError):
            replace(m, capabilities=AdapterCapabilities())

    def test_unsupported_capabilities(self):
        for status in ("unknown", "unsupported"):
            with self.assertRaises(UnsupportedCapability):
                require_capability(AdapterCapabilities(flush=status), "flush")
        require_capability(AdapterCapabilities(flush="supported"), "flush")
        with self.assertRaises(ContractError):
            require_capability(AdapterCapabilities(), "typo")
        self.assertIsNone(WriteReceipt("op1", "ready").usage)
        self.assertIsNone(RecallResult("unsupported", []).retrieved_evidence)

    def test_write_readiness(self):
        for status in ("ready", "durable"):
            require_ready(WriteReceipt("op1", status))
        for status in ("unknown", "failed"):
            with self.assertRaises(ContractError):
                require_ready(WriteReceipt("op1", status))

    def test_native_session_end_does_not_reset(self):
        e, adapter = episode(), FakeNativeAdapter()
        adapter.reset_case("e1", "v1", "reset")
        adapter.begin_session("s1", "begin1")
        adapter.observe(e.observations[0], "write")
        adapter.end_session("s1", "end1")
        with self.assertRaises(ContractError):
            adapter.reset_case("e1", "v1", "bad-reset")
        adapter.begin_session("s2", "begin2")
        result = adapter.query(e.probes[0], "query")
        self.assertIn("Vim", result.text)
        self.assertEqual(result.retrieved_evidence, ["o1"])
        adapter.end_session("s2", "end2")
        adapter.reset_case("e2", "v1", "reset2")
        adapter.begin_session("s2", "begin3")
        result = adapter.query(replace(e.probes[0], episode_id="e2"), "query2")
        self.assertEqual(result.text, "")
        adapter.close()
        with self.assertRaises(ContractError):
            adapter.begin_session("s3", "begin4")

    def test_variant_isolation(self):
        e, adapter = episode(), FakeNativeAdapter()
        adapter.reset_case("e1", "v1", "reset")
        adapter.begin_session("s1", "begin")
        adapter.observe(e.observations[0], "write")
        adapter.end_session("s1", "end")
        adapter.reset_case("e1", "v2", "reset2")
        adapter.begin_session("s2", "begin2")
        self.assertEqual(adapter.query(replace(e.probes[0], variant_id="v2"), "q").text, "")

    def test_native_retry_and_wrong_scope(self):
        e, adapter = episode(), FakeNativeAdapter()
        adapter.reset_case("e1", "v1", "r")
        adapter.reset_case("e1", "v1", "r")
        adapter.begin_session("s1", "b")
        adapter.observe(e.observations[0], "w")
        adapter.observe(e.observations[0], "w")
        with self.assertRaises(ContractError):
            adapter.observe(replace(e.observations[0], text="改变"), "w")
        with self.assertRaises(ContractError):
            adapter.observe(e.observations[0], "w2")
        with self.assertRaises(ContractError):
            adapter.query(e.probes[0], "q")
        adapter.end_session("s1", "end")
        adapter.end_session("s1", "end")
        adapter.begin_session("s2", "b2")
        first = adapter.query(e.probes[0], "q")
        first.retrieved_evidence.append("外部修改")
        second = adapter.query(e.probes[0], "q")
        self.assertEqual(second.retrieved_evidence, ["o1"])
        self.assertEqual(second.text.count("Vim"), 1)

    def test_component_contract(self):
        e, adapter = episode(), FakeComponentAdapter()
        adapter.observe(e.observations[0], "w")
        adapter.observe(e.observations[0], "w")
        adapter.end_session("s1", "end")
        adapter.end_session("s1", "end")
        recalled = adapter.recall(e.probes[0])
        self.assertEqual(recalled.context, [e.observations[0].text])
        self.assertIsNone(recalled.usage)
        with self.assertRaises(UnsupportedCapability):
            require_capability(adapter.capabilities, "native_answer")
        with self.assertRaises(ContractError):
            adapter.observe(replace(e.observations[0], episode_id="e2"), "w2")

    def test_prediction_references_and_capabilities(self):
        e = episode()
        p = Prediction("e1", "v1", "s2", "p1", "ok", "Vim", T1,
                       retrieved_evidence=["o1"])
        caps = AdapterCapabilities(retrieved_evidence="supported")
        validate_prediction(p, e.probes[0], caps, e.observations)
        for bad in [replace(p, probe_id="other"),
                    replace(p, retrieved_evidence=["missing"]),
                    replace(p, retrieved_evidence=["o1", "o1"])]:
            with self.assertRaises(ContractError):
                validate_prediction(bad, e.probes[0], caps, e.observations)
        with self.assertRaises(ContractError):
            validate_prediction(p, e.probes[0], AdapterCapabilities(), e.observations)
        validate_prediction(replace(p, retrieved_evidence=None), e.probes[0],
                            AdapterCapabilities(), e.observations)

    def test_all_roles_are_retained(self):
        e, adapter = episode(), FakeComponentAdapter()
        for index, role in enumerate(("system", "user", "assistant", "tool")):
            adapter.observe(replace(e.observations[0], observation_id="o" + str(index),
                                    role=role, text=role), "w" + str(index))
        adapter.end_session("s1", "end")
        self.assertEqual(adapter.recall(e.probes[0]).context,
                         ["system", "user", "assistant", "tool"])

    def test_sandbox_reference(self):
        for path in ("/private/gold.json", "../gold.json", "work/../../gold", "work\\gold"):
            with self.assertRaises(ContractError):
                SandboxReference("r1", path)


if __name__ == "__main__":
    unittest.main()
