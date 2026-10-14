"""受控文件工具与私有产物验证；不提供进程权限隔离。"""
import copy
import hashlib
import json
import os
from pathlib import Path
import stat
from string import Template

from .protocol_v2 import WriteReceipt, adapter_payload
from .schema_v2 import (ContractError, Episode, Gold, Prediction, SandboxReference,
                        validate_dataset, ForgetPolicy, ExpectedFileAction, REVIEW_STATUSES)


def sha256(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _parts(path):
    SandboxReference('file', path).validate()
    parts = path.split('/')
    if any(p in ('', '.') for p in parts):
        raise ContractError('路径必须规范化')
    return parts


class FileSandbox:
    """仅允许通过此工具访问文件；宿主必须禁止并发重命名测试目录。"""

    def __init__(self, root):
        # 根目录由评测器创建，不能由模型选择；不接受已有用户目录。
        self.root = Path(root)
        self.root.mkdir(mode=0o700, parents=False, exist_ok=False)
        self._fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        self._events = []
        self._operations = {}
        self._emissions = {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    @property
    def audit(self):
        return copy.deepcopy(self._events)

    def _parent(self, path, create=False):
        parts = _parts(path)
        if self._fd is None:
            raise ContractError('文件工具已关闭')
        fd = os.dup(self._fd)
        try:
            for part in parts[:-1]:
                if create:
                    try:
                        os.mkdir(part, mode=0o700, dir_fd=fd)
                    except FileExistsError:
                        pass
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = child
            return fd, parts[-1]
        except BaseException:
            os.close(fd)
            raise

    def read(self, path):
        fd, name = self._parent(path)
        try:
            child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
            with os.fdopen(child, 'rb') as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise ContractError('拒绝特殊文件或硬链接')
                return stream.read().decode('utf-8')
        finally:
            os.close(fd)

    def _create(self, path, text):
        if type(text) is not str:
            raise ContractError('文件内容必须是文本')
        fd, name = self._parent(path, create=True)
        try:
            child = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                            0o600, dir_fd=fd)
            with os.fdopen(child, 'w', encoding='utf-8', newline='') as stream:
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
        finally:
            os.close(fd)

    def snapshot(self):
        """全部文件哈希；遇到链接/特殊文件拒绝验收，不跳过可疑产物。"""
        result = {}
        def walk(fd, prefix):
            for name in sorted(os.listdir(fd)):
                path = prefix + name
                info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                if stat.S_ISDIR(info.st_mode):
                    child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                    try:
                        walk(child, path + '/')
                    finally:
                        os.close(child)
                else:
                    result[path] = sha256(self.read(path))
        walk(self._fd, '')
        return result

    def execute(self, operation, operation_id, **arguments):
        """同 ID 同参数返回原结果；失败也不盲目重放写入。去重仅在当前实例有效。"""
        if type(operation) is not str:
            raise ContractError('操作类型无效')
        if not isinstance(operation_id, str) or not operation_id.strip():
            raise ContractError('操作 ID 无效')
        payload = copy.deepcopy([operation, arguments])
        if operation_id in self._operations:
            previous, result = self._operations[operation_id]
            if previous != payload:
                raise ContractError('操作 ID 重用')
            return copy.deepcopy(result)
        allowed = {'create': {'path', 'text'}, 'read': {'path'}, 'list': set(),
                   'render': {'path', 'template', 'values'}, 'audit': set()}
        event = {'sequence': len(self._events), 'operation_id': operation_id,
                 'operation': operation if operation in allowed else 'rejected', 'status': 'failed'}
        try:
            if operation not in allowed or set(arguments) != allowed[operation]:
                raise ContractError('操作或参数不在白名单')
            if 'path' in arguments:
                _parts(arguments['path'])
                event['path'] = arguments['path']
            if operation == 'create':
                self._create(arguments['path'], arguments['text'])
                event['sha256'] = sha256(arguments['text'])
                self._emissions[event['sequence']] = arguments['text']
                value = None
            elif operation == 'render':
                template = self.read(arguments['template'])
                values = arguments['values']
                if type(values) is not dict or any(type(k) is not str or type(v) is not str
                                                   for k, v in values.items()):
                    raise ContractError('模板参数必须是字符串映射')
                text = Template(template).substitute(values)
                self._create(arguments['path'], text)
                event.update(sha256=sha256(text), template_sha256=sha256(template))
                self._emissions[event['sequence']] = text
                value = None
            elif operation == 'read':
                value = self.read(arguments['path'])
                event['sha256'] = sha256(value)
                self._emissions[event['sequence']] = value
            elif operation == 'list':
                value = list(self.snapshot())
            else:
                value = self.audit
            event['status'] = 'ready'
            result = {'receipt': WriteReceipt(operation_id, 'ready').to_dict(), 'value': value}
        except (OSError, ValueError, KeyError, TypeError):
            # 不在公开错误中回显文本、模板变量或宿主路径。
            result = {'receipt': WriteReceipt(operation_id, 'failed').to_dict(),
                      'value': None, 'error': 'file_operation_rejected'}
        self._events.append(event)
        self._operations[operation_id] = (payload, copy.deepcopy(result))
        return result


def validate_actions(gold):
    """卡5在合同允许的 expected_actions 字典内定义文件验证语义。"""
    if type(gold) is not Gold:
        raise ContractError('需要 Gold')
    gold.validate()
    if not gold.expected_actions:
        raise ContractError('缺少文件预期动作')
    paths = set()
    for action in gold.expected_actions:
        ExpectedFileAction.from_dict(action)
        if action['path'] in paths:
            raise ContractError('重复产物')
        paths.add(action['path'])
    for policy in gold.forget_policies:
        ForgetPolicy.from_dict(policy)


def verify_task(sandbox, gold, prediction, *, baseline, audit_since):
    """评测器在任务/删除请求处取快照；只传入该请求之后的 Prediction。"""
    validate_actions(gold)
    if type(prediction) is not Prediction:
        raise ContractError('需要 Prediction')
    prediction.validate()
    if prediction.probe_id != gold.probe_id:
        raise ContractError('问题引用不匹配')
    if type(audit_since) is not int or not 0 <= audit_since <= len(sandbox.audit):
        raise ContractError('审计检查点无效')
    faults = []
    events = sandbox.audit[audit_since:]
    try:
        current = sandbox.snapshot()
    except (OSError, ValueError):
        return {'status': 'failed', 'faults': ['unsafe_artifact'], 'artifacts': None}
    changed = {p for p, digest in current.items() if baseline.get(p) != digest}
    if prediction.status != 'ok':
        faults.append('prediction_not_ok')
    for action in gold.expected_actions:
        path = action['path']
        writes = [e for e in events if e.get('path') == path and e['status'] == 'ready'
                  and e['operation'] in ('create', 'render')]
        if any(p in changed for p in action.get('old_paths', [])):
            faults.append('old_path_reuse')
        if path not in current:
            faults.append('missing_file')
        elif current[path] != action['sha256']:
            faults.append('content_mismatch')
        if path not in changed or not writes:
            faults.append('action_log_mismatch')
        elif writes[-1].get('sha256') != current.get(path):
            faults.append('action_log_mismatch')
        if writes and writes[-1]['operation'] != action['operation']:
            faults.append('action_log_mismatch')
        if action['operation'] == 'render' and writes:
            digest = writes[-1].get('template_sha256')
            if digest != action['template_sha256']:
                faults.append('stale_template' if digest == action.get('old_template_sha256')
                              else 'template_mismatch')
    for event in events:
        if event['status'] == 'ready' and event['operation'] in ('create', 'render'):
            if current.get(event['path']) != event.get('sha256'):
                faults.append('action_log_mismatch')
    for path in changed:
        writes = [e for e in events if e.get('path') == path and e['status'] == 'ready'
                  and e['operation'] in ('create', 'render')]
        if not writes or writes[-1].get('sha256') != current[path]:
            faults.append('action_log_mismatch')
    for raw_policy in gold.forget_policies:
        policy = ForgetPolicy.from_dict(raw_policy)
        final_texts = [prediction.text or ''] + [sandbox.read(p) for p in changed]
        if prediction.slots is not None:
            final_texts.append(json.dumps([s.to_dict() for s in prediction.slots], ensure_ascii=False))
        texts = final_texts + [text for sequence, text in sandbox._emissions.items()
                               if sequence >= audit_since]
        texts += list(changed) + [event.get('path', '') for event in events]
        if any(value in text for value in policy.values for text in texts):
            faults.append('forgotten_disclosure')
        if policy.retained_text is not None and not any(
                policy.retained_text in text for text in final_texts):
            faults.append('unrelated_preference_lost')
    return {'status': 'failed' if faults else 'passed',
            'faults': sorted(set(faults)), 'artifacts': current}


def assemble_cases(episodes, story_ids, review_status):
    """仅选择既有故事；不改写事实，不补样本，不把待审核数据提升为正式测试。"""
    episodes = list(episodes)
    validate_dataset(episodes)
    if len(story_ids) != 12 or len(set(story_ids)) != 12:
        raise ContractError('需要12个不同的既有故事 ID')
    selected = [e for e in episodes if e.story_id in story_ids]
    missing = set(story_ids) - {e.story_id for e in selected}
    if missing:
        return {'status': 'blocked', 'reason': 'missing_existing_stories', 'cases': []}
    for episode in selected:
        if episode.split != 'test' or len(episode.session_ids) < 2:
            raise ContractError('需要跨会话测试故事')
        for gold in episode.golds:
            validate_actions(gold)
    if any(status not in REVIEW_STATUSES for status in review_status.values()):
        raise ContractError('审阅状态错误')
    if any(review_status.get(e.story_id) != 'accepted' for e in selected):
        return {'status': 'pending_review', 'reason': 'human_review_required', 'cases': []}
    # 这里只返回类型化对象；统一 runner 按时间发送单条公开输入。
    return {'status': 'ready', 'cases': [Episode.from_dict(e.to_dict()) for e in selected]}


def public_task_input(value):
    return adapter_payload(value)


def native_isolation_status():
    """当前实现没有操作系统权限隔离后端，禁止据此启动不受限的 native agent。"""
    return {'status': 'blocked', 'reason': 'external_permission_isolation_NOT_VERIFIED'}
