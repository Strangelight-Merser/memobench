"""离线 fixture；所有传输均注入假 opener，不访问网络。"""
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from memobench.llm_v2 import LLMClient, Limits, CostLedger
from memobench.protocol_v2 import RecallResult, WriteReceipt
from memobench.schema_v2 import Probe, ModelRecord, Prediction

MESSAGES = [{"role": "user", "content": "你好"}]
PROBE = Probe("e", "v", "s", "p", "编辑器？", "2026-10-14T10:00:00Z")


def response(content="Vim", finish="stop", usage=True):
    obj = {"model": "returned-alias", "choices": [{"message": {"content": content}, "finish_reason": finish}]}
    if usage:
        obj["usage"] = {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7}
    return json.dumps(obj).encode()


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"TEST_LLM_KEY": "fixture-secret-not-real"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.calls = []
        self.sleeps = []

    def client(self, outputs=None, **kwargs):
        queue = list(outputs or [response()])
        def opener(req, timeout):
            self.calls.append(req)
            item = queue.pop(0)
            if isinstance(item, Exception):
                raise item
            return io.BytesIO(item)
        return LLMClient(endpoint=kwargs.pop("endpoint", "https://fixture.invalid/chat/completions"),
                         model="snapshot", key_env="TEST_LLM_KEY", provider="fixture",
                         opener=opener, sleep=self.sleeps.append, **kwargs)

    def call(self, client, **kwargs):
        return client.complete(MESSAGES, live=True, input_token_bound=20, **kwargs)

    def test_contract_and_raw(self):
        result = self.call(self.client())
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.model.returned_model, "returned-alias")
        self.assertIsNone(result.model.version)
        self.assertEqual(ModelRecord.from_json(result.model.to_json()), result.model)
        self.assertIsInstance(result.to_prediction(PROBE), Prediction)
        self.assertEqual(result.usage["total_tokens"], 7)
        self.assertIsNotNone(result.online_latency_ms)
        self.assertNotIn("fixture-secret", json.dumps(result.to_dict()))

    def test_endpoint_and_full_parameters_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            a = self.client(cache_dir=directory)
            b = self.client(endpoint="https://other.invalid/chat/completions", cache_dir=directory)
            self.call(a)
            self.call(b)
            self.assertEqual(len(self.calls), 2)
            replay = self.call(a)
            self.assertEqual(replay.execution, "replay")
            self.assertIsNone(replay.online_latency_ms)
            self.assertIsNotNone(replay.replay_latency_ms)
            self.assertEqual(replay.attempts, 0)
            self.assertEqual(len(self.calls), 2)
            for path in Path(directory).iterdir():
                cache = path.read_text()
                self.assertNotIn("fixture-secret", cache)
                for key in ("raw_response", "usage", "finish_reason", "recorded_at", "model"):
                    self.assertIn(key, json.loads(cache))
            c = self.client(parameters={"temperature": 0.7})
            self.assertNotEqual(a.cache_key(MESSAGES), c.cache_key(MESSAGES))
            self.assertNotEqual(a.cache_key(MESSAGES), a.cache_key(MESSAGES + [{"role": "assistant", "content": "a"}]))
            with patch("memobench.llm_v2.PARSER_VERSION", "next"):
                self.assertFalse((Path(directory) / (a.cache_key(MESSAGES) + ".json")).exists())
            self.assertEqual(a.ledger.summary()["stages"]["read"]["n_calls"], 1)

    def test_repeat_requires_no_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            client = self.client(cache_dir=directory)
            self.call(client)
            result = self.call(client, repeat=True)
            self.assertEqual(result.reason, "repeat_requires_cache_disabled")
            self.assertEqual(len(self.calls), 1)
        client = self.client([response(), response()])
        self.call(client, repeat=True)
        self.call(client, repeat=True)
        self.assertEqual(client.requests, 2)

    def test_live_key_and_bound_gates(self):
        client = self.client()
        self.assertEqual(client.complete(MESSAGES).reason, "live_required")
        self.assertEqual(client.complete(MESSAGES, live=True).reason, "input_token_bound_required")
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(self.call(client).reason, "missing_key")
        self.assertEqual(self.calls, [])

    def test_retry_after_and_request_budget(self):
        error = HTTPError("fixture", 429, "rate", {"Retry-After": "3"}, None)
        client = self.client([error, response()], limits=Limits(max_requests=2))
        self.assertEqual(self.call(client).status, "ok")
        self.assertEqual(self.sleeps, [3])
        self.assertEqual(client.requests, 2)
        self.assertEqual(self.call(client).reason, "budget_exhausted")
        self.assertIsNone(client.ledger.summary()["total_cost"])
        self.assertIsNone(client.ledger.records[0]["usage"])

    def test_retry_budget_counts_failed_attempt(self):
        client = self.client([HTTPError("x", 503, "x", {}, None)], limits=Limits(max_requests=1))
        result = self.call(client)
        self.assertEqual(result.reason, "budget_exhausted")
        self.assertEqual(result.attempts, 1)
        self.assertEqual(len(self.calls), 1)

    def test_retry_after_http_date_and_limit(self):
        client = self.client([HTTPError("x", 503, "x", {"Retry-After": "Wed, 01 Jan 2020 00:00:00 GMT"}, None), response()])
        self.assertEqual(self.call(client).status, "ok")
        self.assertEqual(self.sleeps, [0])
        client = self.client([HTTPError("x", 429, "x", {"Retry-After": "1000"}, None)])
        self.assertEqual(self.call(client).reason, "retry_after_exceeds_limit")

    def test_token_and_cost_limits(self):
        client = self.client(limits=Limits(max_total_tokens=10))
        self.assertEqual(self.call(client).reason, "budget_exhausted")
        client = self.client(limits=Limits(max_cost=0.01))
        self.assertEqual(self.call(client).reason, "prices_required")
        client = self.client(limits=Limits(max_cost=0.000001), prices={"input_per_million": 1, "output_per_million": 2})
        self.assertEqual(self.call(client).reason, "budget_exhausted")
        self.assertEqual(self.calls, [])
        client = self.client(prices={"input_per_million": 1, "output_per_million": 2})
        self.call(client)
        self.assertAlmostEqual(client.ledger.summary()["total_cost"], 9 / 1000000)

    def test_unknown_usage_stops_next_request(self):
        client = self.client([response(usage=False)])
        result = self.call(client)
        self.assertEqual(result.status, "ok")
        self.assertIsNone(result.usage)
        self.assertEqual(self.call(client).reason, "budget_unknown")
        self.assertIsNone(client.ledger.summary()["total_cost"])

    def test_timeout_and_no_blind_retry(self):
        for error in (TimeoutError(), URLError(TimeoutError())):
            client = self.client([error])
            result = self.call(client)
            self.assertEqual(result.status, "timeout")
            self.assertEqual(client.requests, 1)
            self.assertEqual(self.call(client).reason, "budget_unknown")

    def test_malformed_empty_truncated(self):
        fixtures = [(b'{', "invalid_json"), (b'{"x":1,"x":2}', "invalid_json"),
                    (response(""), "empty_content"), (response("partial", "length"), "truncated"),
                    (response("tool", "tool_calls"), "unsupported_finish_reason"),
                    (b'{"usage":NaN}', "invalid_json"), (b'{"usage":1e999}', "invalid_json"), (b'\xff', "invalid_encoding")]
        for raw, reason in fixtures:
            with self.subTest(reason=reason):
                result = self.call(self.client([raw]))
                self.assertEqual(result.status, "error")
                self.assertEqual(result.reason, reason)
                self.assertIsNone(result.text)

    def test_credential_echo_not_saved(self):
        result = self.call(self.client([response("fixture-secret-not-real")]))
        self.assertEqual(result.reason, "credential_in_response")
        self.assertIsNone(result.raw_response)

    def test_nonretry_http_and_safe_configuration(self):
        result = self.call(self.client([HTTPError("x", 401, "secret", {}, None)]))
        self.assertEqual(result.reason, "http_401")
        self.assertEqual(len(self.calls), 1)
        for endpoint in ("https://key@host/path", "https://host/path?key=x"):
            with self.assertRaises(ValueError):
                self.client(endpoint=endpoint)
        with self.assertRaises(ValueError):
            self.client(parameters={"api_key": "x"})
        with self.assertRaises(ValueError):
            self.client(parameters={"max_tokens": 513})
        with self.assertRaises(ValueError):
            self.client(parameters={"user": "fixture-secret-not-real"})

    def test_component_reader_public_only(self):
        result = self.client().answer(PROBE, RecallResult("ok", ["编辑器是 Vim"]), live=True, input_token_bound=40)
        self.assertEqual(result.status, "ok")
        body = json.loads(self.calls[0].data)
        self.assertIn("probe", body["messages"][1]["content"])
        self.assertNotIn("gold", self.calls[0].data.decode())
        blocked = self.client().answer(PROBE, RecallResult("unsupported", []))
        self.assertEqual(blocked.reason, "recall_unavailable")

    def test_key_rotation_does_not_change_cache_key(self):
        client = self.client()
        original = client.cache_key(MESSAGES)
        with patch.dict(os.environ, {"TEST_LLM_KEY": "different-fixture-secret"}):
            self.assertEqual(client.cache_key(MESSAGES), original)
        result = client.complete([{"role": "user", "content": "fixture-secret-not-real"}])
        self.assertEqual(result.reason, "invalid_or_sensitive_payload")
        self.assertFalse(self.calls)

    def test_stage_ledger(self):
        ledger = CostLedger()
        ledger.record_adapter("write", WriteReceipt("op", "ready"))
        ledger.record_adapter("retrieval", RecallResult("ok", [], usage={"calls": 1}))
        ledger.record("embedding", usage={"tokens": 3})
        summary = ledger.summary()
        self.assertIsNone(summary["total_cost"])
        self.assertIsNone(summary["stages"]["judge"]["usage"])
        self.assertEqual(summary["stages"]["write"]["n_calls"], 1)

    def test_invalid_cache_is_not_network_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            client = self.client(cache_dir=directory)
            (Path(directory) / (client.cache_key(MESSAGES) + ".json")).write_text("{")
            self.assertEqual(self.call(client).reason, "invalid_cache")
            self.assertFalse(self.calls)


if __name__ == "__main__":
    unittest.main()
