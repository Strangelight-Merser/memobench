"""冻结合同的 native 生命周期、隔离目录和至多一次投递。"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import threading
from uuid import uuid4

from ..protocol_v2 import WriteReceipt, adapter_payload, require_capability
from ..schema_v2 import (AdapterCapabilities, ContractError, Observation, Prediction,
                         Probe, validate_prediction)
from .transports import TransportError


def _check(condition, message):
    if not condition:
        raise ContractError(message)


class NativeAdapter:
    """串行调用；重启后禁止恢复既有目录，不能盲重放可能已写入的操作。"""
    def __init__(self, transport, capabilities, *, run_directory=None):
        capabilities.validate()
        _check(capabilities.restart != "supported", "restart unsupported")
        self.capabilities = AdapterCapabilities.from_dict(capabilities.to_dict())
        self.transport = transport
        if run_directory is None:
            self.run_directory = Path(tempfile.mkdtemp(prefix="memobench-native-"))
        else:
            self.run_directory = Path(run_directory).absolute()
            # 只能创建新的临时目录，既有目录（含软链接）一律拒绝恢复。
            _check(self.run_directory.parent.resolve().is_relative_to(
                Path(tempfile.gettempdir()).resolve()), "run_directory 必须在临时目录中")
            try:
                self.run_directory.mkdir(mode=0o700)
            except FileExistsError:
                raise ContractError("restart unsupported：禁止恢复或重试既有运行") from None
        self._case = None
        self._session = None
        self._cases, self._sessions, self._observations = set(), set(), []
        self._operations = {}
        self._home = None
        self._homes = []
        self.cleanup_receipts = []
        self.evidence_index = []
        self._closed = False
        self._uncertain = False
        self._lock = threading.Lock()
        (self.run_directory / "NO_RESUME").write_text("restart unsupported\n", encoding="utf-8")

    def _call(self, method, operation_id, payload, prepare, accept):
        _check(isinstance(operation_id, str) and bool(operation_id.strip()), "operation_id 无效")
        signature = json.dumps([method, payload], sort_keys=True, ensure_ascii=False, allow_nan=False)
        with self._lock:
            _check(not self._closed, "adapter.closed")
            if operation_id in self._operations:
                old, result = self._operations[operation_id]
                _check(old == signature, "operation_id.reused")
                if result is None:
                    raise TransportError("operation_uncertain_no_retry")
                return type(result).from_dict(result.to_dict())
            _check(not self._uncertain, "写入状态未确认，禁止后续调用")
            prepare()
            self._operations[operation_id] = (signature, None)
            # 写前留标记；即使发送后崩溃，也不允许重新打开目录重试。
            journal = self.run_directory / "operations.jsonl"
            with journal.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({"operation_sha256": hashlib.sha256(operation_id.encode()).hexdigest(),
                                         "request_sha256": hashlib.sha256(signature.encode()).hexdigest()}) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            try:
                raw = self.transport.request(method, operation_id, payload, self._home)
                if method == "query":
                    result = Prediction.from_dict(raw)
                    validate_prediction(result, Probe.from_dict(payload), self.capabilities, self._observations)
                    if result.status != "ok":
                        self._uncertain = True
                else:
                    result = WriteReceipt.from_dict(raw)
                    _check(result.operation_id == operation_id, "receipt.operation_id")
                    _check(self.capabilities.write_usage == "supported" or result.usage is None,
                           "write_usage.unsupported")
                    if result.status in ("unknown", "failed"):
                        self._uncertain = True
                if not self._uncertain:
                    accept()
            except (TransportError, ContractError) as exc:
                self._uncertain = True
                if method == "query":
                    result = Prediction(payload["episode_id"], payload["variant_id"],
                                        payload["session_id"], payload["probe_id"],
                                        "timeout" if isinstance(exc, TransportError) and exc.code == "timeout" else "error", None,
                                        datetime.now(timezone.utc).isoformat())
                else:
                    result = WriteReceipt(operation_id, "unknown")
            except Exception:
                self._uncertain = True
                raise TransportError("operation_uncertain_no_retry") from None
            self._operations[operation_id] = (signature, result)
            return type(result).from_dict(result.to_dict())

    def reset_case(self, episode_id, variant_id, operation_id):
        _check(all(isinstance(v, str) and v.strip() for v in (episode_id, variant_id)), "case ID 无效")
        key = (episode_id, variant_id)
        def prepare():
            _check(self._session is None and key not in self._cases, "reset_case.scope")
            self._home = Path(tempfile.mkdtemp(prefix="case-", dir=self.run_directory))
            self._homes.append((self._home, key))
        def accept():
            self._case = key
            self._cases.add(key)
            self._sessions.clear()
            self._observations.clear()
        return self._call("reset_case", operation_id,
                          {"episode_id": episode_id, "variant_id": variant_id}, prepare, accept)

    def begin_session(self, session_id, operation_id):
        _check(isinstance(session_id, str) and session_id.strip(), "session_id 无效")
        def prepare():
            _check(self._case is not None and self._session is None and
                   session_id not in self._sessions, "begin_session.scope")
        def accept():
            self._session = session_id
            self._sessions.add(session_id)
        return self._call("begin_session", operation_id,
                          {"episode_id": self._case[0], "variant_id": self._case[1], "session_id": session_id}
                          if self._case else {"session_id": session_id}, prepare, accept)

    def _scope(self, value):
        _check(self._case == (value.episode_id, value.variant_id) and
               self._session == value.session_id, "input.scope")

    def observe(self, observation, operation_id):
        _check(type(observation) is Observation, "observe.type")
        payload = adapter_payload(observation)
        def prepare():
            self._scope(observation)
            _check(observation.observation_id not in {o.observation_id for o in self._observations},
                   "observation.duplicate")
        return self._call("observe", operation_id, payload, prepare,
                          lambda: self._observations.append(Observation.from_dict(payload)))

    def end_session(self, session_id, operation_id):
        def prepare():
            _check(self._session is not None and self._session == session_id, "end_session.scope")
        return self._call("end_session", operation_id,
                          {"episode_id": self._case[0], "variant_id": self._case[1], "session_id": session_id}
                          if self._case else {"session_id": session_id}, prepare,
                          lambda: setattr(self, "_session", None))

    def query(self, probe, operation_id):
        require_capability(self.capabilities, "native_answer")
        _check(type(probe) is Probe, "query.type")
        return self._call("query", operation_id, adapter_payload(probe),
                          lambda: self._scope(probe), lambda: None)

    def task_checkpoint(self, probe, operation_id):
        """Evaluator-only local artifact handle; never sent to the product with gold."""
        if not hasattr(self.transport, 'task_checkpoint'):
            return None
        self._scope(probe)
        checkpoint = self.transport.task_checkpoint(operation_id, adapter_payload(probe), self._home)
        if hasattr(self.transport, 'task_evidence'):
            from ..native_artifacts_v2 import unpack
            expected = {'run': self.run_directory.name, 'namespace': self.transport.namespaces[str(self._home)],
                        'episode_id': probe.episode_id, 'variant_id': probe.variant_id,
                        'session_id': probe.session_id, 'operation_id': operation_id,
                        'bridge_sha256': self.transport.bridge_sha256}
            _check(checkpoint['binding'] == expected, 'remote artifact scope mismatch')
            unpack(checkpoint['baseline'])
            return checkpoint
        from ..sandbox_v2 import FileSandbox
        sandbox = checkpoint['sandbox']
        _check(type(sandbox) is FileSandbox, 'untrusted artifact handle')
        _check(sandbox.root.resolve().is_relative_to(self._home.resolve()), 'artifact home mismatch')
        binding = {'run': self.run_directory.name, 'namespace': self._home.name, 'operation_id': operation_id, 'session_id': probe.session_id,
                   'episode_id': probe.episode_id, 'variant_id': probe.variant_id}
        _check(checkpoint['binding'] == binding, 'artifact scope mismatch')
        return {'sandbox': sandbox, 'binding': binding, 'baseline': sandbox.snapshot(),
                'audit_since': len(sandbox.audit)}

    def verify_task(self, gold, prediction, checkpoint, operation_id):
        if hasattr(self.transport, 'task_evidence'):
            from ..native_artifacts_v2 import verify_remote_task
            payload = {'episode_id': prediction.episode_id, 'variant_id': prediction.variant_id,
                       'session_id': prediction.session_id}
            evidence = self.transport.task_evidence(operation_id, payload, self._home)
            record = {'binding': checkpoint['binding'], 'checkpoint': checkpoint, 'evidence': evidence}
            self.evidence_index.append(record)
            try:
                checked = verify_remote_task(gold, prediction, checkpoint, evidence)
            except Exception as exc:
                record['verification_error_type'] = type(exc).__name__
                raise
            record['verification'] = checked
            return checked
        from ..sandbox_v2 import verify_task
        _check(checkpoint['binding']['operation_id'] == operation_id, 'artifact operation mismatch')
        # A handle exists only for an evaluator-controlled local tool transport.
        from dataclasses import replace
        checks = [verify_task(checkpoint['sandbox'], replace(gold, expected_actions=[action]), prediction,
                              baseline=checkpoint['baseline'], audit_since=checkpoint['audit_since'])
                  for action in gold.expected_actions]
        checked = {'status': 'passed' if all(c['status'] == 'passed' for c in checks) else 'failed',
                   'checks': checks, 'faults': sorted({f for c in checks for f in c['faults']}),
                   'artifacts': checkpoint['sandbox'].snapshot()}
        checked['binding'] = checkpoint['binding']
        self.evidence_index.append({'binding': checkpoint['binding'],
                                    'baseline': checkpoint['baseline'],
                                    'audit': checkpoint['sandbox'].audit[checkpoint['audit_since']:],
                                    'verification': checked})
        return checked

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
            failed = False
            try:
                for home, key in self._homes:
                    operation_id = uuid4().hex
                    try:
                        raw = self.transport.request("close", operation_id,
                                                     {"episode_id": key[0], "variant_id": key[1]}, home)
                        receipt = WriteReceipt.from_dict(raw)
                        _check(receipt.operation_id == operation_id, "close.operation_id")
                    except Exception:
                        receipt = WriteReceipt(operation_id, "unknown")
                    self.cleanup_receipts.append(receipt)
                    failed = failed or receipt.status not in ("ready", "durable")
                self.transport.close()
            finally:
                # 仅清理由本实例新建的目录；不触碰实际 agent HOME。
                for home, _ in self._homes:
                    if home.is_symlink():
                        home.unlink()
                    elif home.exists():
                        shutil.rmtree(home)
                self._observations.clear()
                self._operations.clear()
            if failed:
                raise TransportError("cleanup_not_verified")
