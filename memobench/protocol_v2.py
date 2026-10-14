"""适配器合同与内存假实现；不负责评测编排或评分。"""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Protocol

from .schema_v2 import (
    AdapterCapabilities, ContractError, Observation, Prediction, Probe, Record,
    _require, _text,
)


class UnsupportedCapability(ContractError):
    pass


def require_capability(capabilities, name):
    capabilities.validate()
    _require(name in AdapterCapabilities.__dataclass_fields__, "capability.name")
    if getattr(capabilities, name) != "supported":
        raise UnsupportedCapability("能力未支持: " + name)


@dataclass
class WriteReceipt(Record):
    operation_id: str
    status: Literal["ready", "durable", "unknown", "failed"]
    usage: Optional[Dict[str, Any]] = None


def require_ready(receipt):
    """异步适配器须先等待；unknown/failed 不能当作写入成功。"""
    receipt.validate()
    _require(receipt.status in ("ready", "durable"), "write.not_ready")


@dataclass
class RecallResult(Record):
    status: Literal["ok", "unsupported", "error", "timeout"]
    context: List[str]
    retrieved_evidence: Optional[List[str]] = None
    usage: Optional[Dict[str, Any]] = None


def adapter_payload(value):
    """只接收确定的公开类型，不接受字典或整份 Episode。"""
    _require(type(value) in (Observation, Probe), "payload.type")
    return value.to_public()


def public_log_record(value):
    """默认运行日志仅留公开定位字段，不透传原对象和文本。"""
    payload = adapter_payload(value)
    return {k: v for k, v in payload.items()
            if k in ("episode_id", "variant_id", "session_id", "observation_id",
                     "probe_id", "role", "observed_at")}


class ComponentAdapter(Protocol):
    capabilities: AdapterCapabilities

    def observe(self, observation: Observation, operation_id: str) -> WriteReceipt: ...
    def end_session(self, session_id: str, operation_id: str) -> WriteReceipt: ...
    def recall(self, probe: Probe) -> RecallResult: ...


class NativeAgentAdapter(Protocol):
    capabilities: AdapterCapabilities

    def reset_case(self, episode_id: str, variant_id: str, operation_id: str) -> WriteReceipt: ...
    def begin_session(self, session_id: str, operation_id: str) -> WriteReceipt: ...
    def observe(self, observation: Observation, operation_id: str) -> WriteReceipt: ...
    def end_session(self, session_id: str, operation_id: str) -> WriteReceipt: ...
    def query(self, probe: Probe, operation_id: str) -> Prediction: ...
    def close(self) -> None: ...


class FakeNativeAdapter:
    """仅用于合同测试：回显全部观察，不代表真实智能体或持久存储。"""

    def __init__(self):
        self.capabilities = AdapterCapabilities(
            native_answer="supported", retrieved_evidence="supported",
            write_usage="unsupported", flush="unsupported", restart="unsupported",
            storage_inspection="unsupported")
        self._case = None
        self._session = None
        self._sessions = set()
        self._cases = set()
        self._observations = []
        self._operations = {}
        self._closed = False

    def _operation(self, operation_id, payload, action):
        _text(operation_id, "operation_id")
        _require(not self._closed, "adapter.closed")
        if operation_id in self._operations:
            previous, result = self._operations[operation_id]
            _require(previous == payload, "operation_id.reused")
            return type(result).from_dict(result.to_dict())
        result = action()
        self._operations[operation_id] = (payload, result)
        return type(result).from_dict(result.to_dict())

    def reset_case(self, episode_id, variant_id, operation_id):
        _text(episode_id, "episode_id")
        _text(variant_id, "variant_id")
        def action():
            key = (episode_id, variant_id)
            _require(self._session is None and key not in self._cases, "reset_case.scope")
            self._case = key
            self._cases.add(key)
            self._sessions.clear()
            self._observations.clear()
            return WriteReceipt(operation_id, "ready")
        return self._operation(operation_id, ["reset_case", episode_id, variant_id], action)

    def begin_session(self, session_id, operation_id):
        _text(session_id, "session_id")
        def action():
            _require(self._case is not None and self._session is None and
                     session_id not in self._sessions, "begin_session.scope")
            self._session = session_id
            self._sessions.add(session_id)
            return WriteReceipt(operation_id, "ready")
        return self._operation(operation_id, ["begin_session", self._case, session_id], action)

    def _check_input(self, value):
        _require(self._case == (value.episode_id, value.variant_id) and
                 self._session == value.session_id, "input.scope")

    def observe(self, observation, operation_id):
        _require(type(observation) is Observation, "observe.type")
        payload = adapter_payload(observation)
        def action():
            self._check_input(observation)
            _require(observation.observation_id not in
                     {o.observation_id for o in self._observations}, "observation.duplicate")
            self._observations.append(Observation.from_dict(payload))
            return WriteReceipt(operation_id, "ready")
        return self._operation(operation_id, ["observe", payload], action)

    def end_session(self, session_id, operation_id):
        def action():
            _require(self._session is not None and self._session == session_id, "end_session.scope")
            self._session = None
            return WriteReceipt(operation_id, "ready")
        return self._operation(operation_id, ["end_session", self._case, session_id], action)

    def query(self, probe, operation_id):
        require_capability(self.capabilities, "native_answer")
        _require(type(probe) is Probe, "query.type")
        payload = adapter_payload(probe)
        def action():
            self._check_input(probe)
            return Prediction(
                probe.episode_id, probe.variant_id, probe.session_id, probe.probe_id,
                "ok", "\n".join(o.text for o in self._observations),
                datetime.now(timezone.utc).isoformat(),
                retrieved_evidence=[o.observation_id for o in self._observations])
        return self._operation(operation_id, ["query", payload], action)

    def close(self):
        self._closed = True
        self._observations.clear()
        self._operations.clear()


class FakeComponentAdapter:
    """每个 episode/variant 创建新实例；输出交给公共 Reader。"""

    def __init__(self):
        self.capabilities = AdapterCapabilities(
            native_answer="unsupported", retrieved_evidence="supported",
            write_usage="unsupported", flush="unsupported", restart="unsupported",
            storage_inspection="unsupported")
        self._observations = []
        self._case = None
        self._ended = set()
        self._operations = {}
        self._active_session = None

    def observe(self, observation, operation_id):
        _require(type(observation) is Observation, "observe.type")
        payload = adapter_payload(observation)
        _text(operation_id, "operation_id")
        if operation_id in self._operations:
            _require(self._operations[operation_id] == ["observe", payload], "operation_id.reused")
            return WriteReceipt(operation_id, "ready")
        key = (observation.episode_id, observation.variant_id)
        _require(self._case in (None, key) and observation.session_id not in self._ended
                 and self._active_session in (None, observation.session_id), "observe.scope")
        _require(observation.observation_id not in
                 {o.observation_id for o in self._observations}, "observation.duplicate")
        self._case = key
        self._active_session = observation.session_id
        self._observations.append(Observation.from_dict(payload))
        self._operations[operation_id] = ["observe", payload]
        return WriteReceipt(operation_id, "ready")

    def end_session(self, session_id, operation_id):
        _text(session_id, "session_id")
        _text(operation_id, "operation_id")
        payload = ["end_session", session_id]
        if operation_id in self._operations:
            _require(self._operations[operation_id] == payload, "operation_id.reused")
            return WriteReceipt(operation_id, "ready")
        _require(session_id not in self._ended and
                 self._active_session in (None, session_id), "end_session.scope")
        self._ended.add(session_id)
        self._active_session = None
        self._operations[operation_id] = payload
        return WriteReceipt(operation_id, "ready")

    def recall(self, probe):
        _require(type(probe) is Probe, "recall.type")
        adapter_payload(probe)
        _require(self._case in (None, (probe.episode_id, probe.variant_id)), "recall.scope")
        return RecallResult("ok", [o.text for o in self._observations],
                            [o.observation_id for o in self._observations])
