"""v2 数据合同；公开输入与评测器真值分开保存。"""
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime
import json
import math
import re
from typing import Any, Dict, List, Literal, Optional, Union, get_args, get_origin, get_type_hints

SCHEMA_VERSION = "0.2"
TECHNICAL_CATEGORIES = ("recall", "update", "multi", "temporal", "forget", "abstain")
OFFICIAL_CAPABILITIES = {
    "long_term_retention": "长期保持", "memory_retrieval": "记忆调用",
    "dynamic_update": "动态更新", "similarity_discrimination": "相近区分",
    "boundary_recognition": "边界识别", "task_reuse": "任务复用",
}
AnswerState = Literal["answer", "unknown", "forgotten", "conflict"]
Support = Literal["supported", "unsupported", "unknown"]
Mode = Literal["component", "native_agent"]


class ContractError(ValueError):
    """合同错误只报告字段，不回显私有值。"""


def _require(ok, name):
    if not ok:
        raise ContractError("无效字段: " + name)


def _text(value, name):
    _require(isinstance(value, str) and bool(value.strip()), name)


def _time(value, name):
    _text(value, name)
    _require(bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})", value)), name)
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ContractError("无效时间: " + name) from None
    _require(result.utcoffset() is not None, name)
    return result


def _json(value):
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float:
        _require(math.isfinite(value), "JSON.number")
    elif type(value) is list:
        for item in value:
            _json(item)
    elif type(value) is dict:
        for key, item in value.items():
            _require(type(key) is str, "JSON.key")
            _json(item)
    else:
        raise ContractError("非 JSON 值")


def _typed(value, annotation, name, decode=False):
    origin, args = get_origin(annotation), get_args(annotation)
    if annotation is Any:
        _json(value)
        return value
    if origin is Literal:
        _require(value in args and type(value) is str, name)
    elif origin is Union:
        for choice in args:
            try:
                return _typed(value, choice, name, decode)
            except ContractError:
                pass
        raise ContractError("无效字段: " + name)
    elif origin is list:
        _require(type(value) is list, name)
        return [_typed(v, args[0], name, decode) for v in value]
    elif origin is dict:
        _require(type(value) is dict, name)
        return {_typed(k, args[0], name, decode): _typed(v, args[1], name, decode)
                for k, v in value.items()}
    elif isinstance(annotation, type) and issubclass(annotation, Record):
        if decode:
            return annotation.from_dict(value)
        _require(type(value) is annotation, name)
        value.validate()
    else:
        _require(type(value) is annotation, name)
    return value


def _unique(values, name):
    for value in values:
        _text(value, name)
    _require(len(values) == len(set(values)), name + ".duplicate")


class Record:
    def __post_init__(self):
        self.validate()

    def validate(self):
        for name, annotation in get_type_hints(type(self)).items():
            _typed(getattr(self, name), annotation, name)
        for f in fields(self):
            if f.name.endswith("_id"):
                _text(getattr(self, f.name), f.name)

    def to_dict(self):
        """完整序列化；私有记录仅允许评测器存盘。"""
        self.validate()
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        _require(type(data) is dict, cls.__name__)
        names = {f.name for f in fields(cls)}
        _require(set(data) <= names, cls.__name__ + ".extra_fields")
        hints = get_type_hints(cls)
        try:
            return cls(**{k: _typed(v, hints[k], k, True) for k, v in data.items()})
        except TypeError:
            raise ContractError("缺少必填字段: " + cls.__name__) from None

    def to_json(self):
        return json.dumps(self.to_dict(), ensure_ascii=False, allow_nan=False, sort_keys=True)

    @classmethod
    def from_json(cls, text):
        def pairs(items):
            result = {}
            for key, value in items:
                _require(key not in result, "JSON.duplicate_key")
                result[key] = value
            return result
        try:
            return cls.from_dict(json.loads(text, object_pairs_hook=pairs))
        except (json.JSONDecodeError, TypeError):
            raise ContractError("无效 JSON") from None

    def to_public(self):
        raise ContractError("私有记录不能作为公开输入")


@dataclass
class SandboxReference(Record):
    reference_id: str
    path: str

    def validate(self):
        super().validate()
        _text(self.path, "path")
        _require(not self.path.startswith("/") and ".." not in self.path.split("/")
                 and "\\" not in self.path and "\x00" not in self.path, "path")


@dataclass
class Observation(Record):
    episode_id: str
    variant_id: str
    session_id: str
    observation_id: str
    role: Literal["system", "user", "assistant", "tool"]
    text: str
    observed_at: str
    sandbox_references: List[SandboxReference] = field(default_factory=list)

    def validate(self):
        super().validate()
        _text(self.text, "text")
        _time(self.observed_at, "observed_at")
        _unique([r.reference_id for r in self.sandbox_references], "sandbox_references")

    def to_public(self):
        # 使用固定类型的字段白名单，额外属性永不进入传输。
        data = self.to_dict()
        return {f.name: data[f.name] for f in fields(Observation)}


@dataclass
class Probe(Record):
    episode_id: str
    variant_id: str
    session_id: str
    probe_id: str
    query: str
    observed_at: str
    sandbox_references: List[SandboxReference] = field(default_factory=list)

    def validate(self):
        super().validate()
        _text(self.query, "query")
        _time(self.observed_at, "observed_at")
        _unique([r.reference_id for r in self.sandbox_references], "sandbox_references")

    def to_public(self):
        data = self.to_dict()
        return {f.name: data[f.name] for f in fields(Probe)}


@dataclass
class Slot(Record):
    name: str
    value_type: Literal["string", "number", "boolean", "version", "path"]
    state: AnswerState
    value: Any
    aliases: List[Any] = field(default_factory=list)

    def validate(self):
        super().validate()
        _text(self.name, "name")
        if self.state in ("unknown", "forgotten", "conflict"):
            _require(self.value is None and not self.aliases, "slot.non_answer")
        else:
            for value in [self.value] + self.aliases:
                valid = (type(value) in (int, float) if self.value_type == "number"
                         else type(value) is bool if self.value_type == "boolean"
                         else type(value) is str)
                _require(valid, "slot.value")


@dataclass
class EvidenceLocation(Record):
    observation_id: str
    start: Optional[int] = None
    end: Optional[int] = None

    def validate(self):
        super().validate()
        _require((self.start is None and self.end is None) or
                 (self.start is not None and self.end is not None and
                  0 <= self.start < self.end), "evidence.span")


@dataclass(repr=False)
class Gold(Record):
    probe_id: str
    slots: List[Slot]
    evidence: List[EvidenceLocation]
    canonical_state_ledger: List[Dict[str, Any]]
    expected_actions: List[Dict[str, Any]]
    forget_policies: List[Dict[str, Any]]
    technical_categories: List[str]
    official_capabilities: List[str]

    def validate(self):
        super().validate()
        _require(bool(self.slots) or bool(self.expected_actions), "gold.targets")
        _unique([s.name for s in self.slots], "slots")
        for name, allowed in (("technical_categories", TECHNICAL_CATEGORIES),
                              ("official_capabilities", OFFICIAL_CAPABILITIES)):
            values = getattr(self, name)
            _unique(values, name)
            _require(bool(values) and all(v in allowed for v in values), name)

    def __repr__(self):
        return "Gold(<private>)"


@dataclass(repr=False)
class Episode(Record):
    episode_id: str
    variant_id: str
    story_id: str
    split: Literal["dev", "test"]
    session_ids: List[str]
    observations: List[Observation]
    probes: List[Probe]
    golds: List[Gold]

    def validate(self):
        super().validate()
        _require(bool(self.session_ids) and bool(self.probes), "episode.empty")
        _unique(self.session_ids, "session_ids")
        _unique([o.observation_id for o in self.observations], "observation_ids")
        _unique([p.probe_id for p in self.probes], "probe_ids")
        _unique([g.probe_id for g in self.golds], "gold.probe_ids")
        observations = {o.observation_id: o for o in self.observations}
        probes = {p.probe_id: p for p in self.probes}
        _require(set(probes) == {g.probe_id for g in self.golds}, "gold.references")
        previous = None
        for observation in self.observations:
            stamp = _time(observation.observed_at, "observed_at")
            _require(previous is None or stamp >= previous, "observation.order")
            previous = stamp
        for item in self.observations + self.probes:
            _require((item.episode_id, item.variant_id) == (self.episode_id, self.variant_id)
                     and item.session_id in self.session_ids, "episode.references")
        for gold in self.golds:
            probe = probes[gold.probe_id]
            for evidence in gold.evidence:
                _require(evidence.observation_id in observations, "evidence.reference")
                observation = observations[evidence.observation_id]
                _require(_time(observation.observed_at, "observed_at") <=
                         _time(probe.observed_at, "observed_at"), "evidence.future")
                _require(self.session_ids.index(observation.session_id) <=
                         self.session_ids.index(probe.session_id), "evidence.session")
                _require(evidence.end is None or evidence.end <= len(observation.text), "evidence.end")

    def to_public(self):
        self.validate()
        return {"episode_id": self.episode_id, "variant_id": self.variant_id,
                "session_ids": list(self.session_ids),
                "observations": [o.to_public() for o in self.observations],
                "probes": [p.to_public() for p in self.probes]}

    def __repr__(self):
        return "Episode(<private>)"


@dataclass
class AdapterCapabilities(Record):
    native_answer: Support = "unknown"
    retrieved_evidence: Support = "unknown"
    write_usage: Support = "unknown"
    flush: Support = "unknown"
    restart: Support = "unknown"
    storage_inspection: Support = "unknown"


@dataclass
class Prediction(Record):
    episode_id: str
    variant_id: str
    session_id: str
    probe_id: str
    status: Literal["ok", "unsupported", "error", "timeout"]
    text: Optional[str]
    answered_at: str
    state: Optional[AnswerState] = None
    slots: Optional[List[Slot]] = None
    retrieved_evidence: Optional[List[str]] = None
    usage: Optional[Dict[str, Any]] = None

    def validate(self):
        super().validate()
        _time(self.answered_at, "answered_at")
        _require(self.status != "ok" or self.text is not None, "prediction.text")
        if self.slots is not None:
            _unique([s.name for s in self.slots], "prediction.slots")


@dataclass
class ModelRecord(Record):
    provider: str
    endpoint_id: str
    requested_model: str
    returned_model: Optional[str]
    parameters: Dict[str, Any]
    version: Optional[str]
    digest: Optional[str]
    recorded_at: str

    def validate(self):
        super().validate()
        for name in ("provider", "requested_model"):
            _text(getattr(self, name), name)
        _time(self.recorded_at, "recorded_at")
        for name in ("returned_model", "version", "digest"):
            if getattr(self, name) is not None:
                _text(getattr(self, name), name)


@dataclass
class RunManifest(Record):
    run_id: str
    mode: Mode
    execution: Literal["offline", "online", "replay"]
    adapter_id: str
    adapter_version: str
    capabilities: AdapterCapabilities
    models: List[ModelRecord]
    started_at: str
    finished_at: Optional[str]
    code_hash: str
    data_hash: str
    scorer_hash: str
    schema_version: str = SCHEMA_VERSION

    def validate(self):
        super().validate()
        _text(self.adapter_version, "adapter_version")
        start = _time(self.started_at, "started_at")
        if self.finished_at is not None:
            _require(_time(self.finished_at, "finished_at") >= start, "finished_at")
        for name in ("code_hash", "data_hash", "scorer_hash"):
            _require(bool(re.fullmatch(r"[0-9a-f]{64}", getattr(self, name))), name)
        _require(self.schema_version == SCHEMA_VERSION, "schema_version")
        if self.mode == "native_agent":
            _require(self.capabilities.native_answer == "supported", "native_answer")


def validate_dataset(episodes):
    """variant 内局部 ID 唯一；故事不得跨开发和测试集。"""
    seen, splits = set(), {}
    for episode in episodes:
        _require(type(episode) is Episode, "episode")
        episode.validate()
        key = (episode.episode_id, episode.variant_id)
        _require(key not in seen, "episode.duplicate")
        seen.add(key)
        _require(splits.get(episode.story_id, episode.split) == episode.split, "story.split")
        splits[episode.story_id] = episode.split


def validate_prediction(prediction, probe, capabilities, observations):
    """验证输出归属与可观察证据；证据 ID 仅表示引用，不证明支持答案。"""
    _require(type(prediction) is Prediction and type(probe) is Probe, "prediction.type")
    prediction.validate()
    probe.validate()
    capabilities.validate()
    _require(all(getattr(prediction, name) == getattr(probe, name)
                 for name in ("episode_id", "variant_id", "session_id", "probe_id")),
             "prediction.references")
    if capabilities.retrieved_evidence != "supported":
        _require(prediction.retrieved_evidence is None, "prediction.evidence.unsupported")
    if prediction.retrieved_evidence is not None:
        available = set()
        for observation in observations:
            observation.validate()
            if ((observation.episode_id, observation.variant_id) == (probe.episode_id, probe.variant_id)
                    and _time(observation.observed_at, "observed_at") <=
                    _time(probe.observed_at, "observed_at")):
                available.add(observation.observation_id)
        _unique(prediction.retrieved_evidence, "prediction.evidence")
        _require(set(prediction.retrieved_evidence) <= available, "prediction.evidence.references")
