"""受控进程与 JSON-over-HTTP 传输；不实现 MCP。"""
import json
import os
from pathlib import Path
import signal
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request

from ..schema_v2 import ContractError


class TransportError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def decode_response(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError()
            result[key] = value
        return result
    def invalid(value):
        raise ValueError()
    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)
        if not isinstance(value, dict):
            raise ValueError()
        return value
    except (ValueError, UnicodeError):
        raise TransportError("invalid_json") from None


def isolated_environment(home):
    """不继承凭据、代理、Python 注入或真实 HOME。"""
    home = Path(home)
    result = {"PATH": os.defpath, "LANG": "C.UTF-8", "HOME": str(home)}
    for key, name in (("XDG_CONFIG_HOME", "config"), ("XDG_DATA_HOME", "data"),
                      ("XDG_CACHE_HOME", "cache"), ("XDG_STATE_HOME", "state"),
                      ("TMPDIR", "tmp")):
        path = home / name
        path.mkdir(parents=True, exist_ok=True)
        result[key] = str(path)
    return result


def run_process(argv, home, stdin=b"", timeout=30, credential_env=()):
    """固定 argv；文本只走 stdin；超时终止本次进程组。"""
    env = isolated_environment(home)
    for name in credential_env:
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*_(?:API_KEY|TOKEN)", name):
            raise ContractError("仅允许显式命名的凭据环境变量")
        if not os.environ.get(name):
            raise TransportError("credential_missing")
        env[name] = os.environ[name]
    try:
        process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, cwd=home,
                                   env=env, start_new_session=True)
        try:
            out, err = process.communicate(stdin, timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
            raise TransportError("timeout") from None
    except OSError:
        raise TransportError("process_unavailable") from None
    if len(out) + len(err) > 4 * 1024 * 1024:
        raise TransportError("response_too_large")
    return process.returncode, out, err


class SubprocessTransport:
    """命令必须实现文档所列桥接协议，不可直接填普通 agent CLI。"""
    def __init__(self, argv, *, live=False, timeout=30, credential_env=()):
        if not live:
            raise TransportError("live_required")
        if (not isinstance(argv, (list, tuple)) or not argv or
                any(not isinstance(v, str) or not v or "\x00" in v for v in argv) or
                not Path(argv[0]).is_absolute()):
            raise ContractError("argv 必须是含绝对可执行路径的固定列表")
        if timeout <= 0:
            raise ContractError("timeout 必须为正数")
        self.argv, self.timeout = list(argv), timeout
        self.credential_env = tuple(credential_env)

    def request(self, method, operation_id, payload, home):
        body = json.dumps({"method": method, "operation_id": operation_id,
                           "payload": payload}, ensure_ascii=False, allow_nan=False).encode()
        code, out, _ = run_process(self.argv, home, body, self.timeout, self.credential_env)
        if code:
            raise TransportError("process_failed")
        return decode_response(out)

    def close(self):
        pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class HTTPTransport:
    """专用测试服务的桥接协议；服务端负责 namespace 权限隔离。"""
    def __init__(self, endpoint, *, live=False, key_env=None, timeout=30):
        if not live:
            raise TransportError("live_required")
        url = urllib.parse.urlsplit(endpoint)
        if (url.scheme not in ("http", "https") or not url.hostname or
                url.username or url.password or url.query or url.fragment or
                (url.scheme == "http" and url.hostname not in ("localhost", "127.0.0.1", "::1"))):
            raise ContractError("endpoint 必须为无凭据 HTTPS 或本机 HTTP 地址")
        if timeout <= 0:
            raise ContractError("timeout 必须为正数")
        if key_env and not os.environ.get(key_env):
            raise TransportError("credential_missing")
        self.endpoint, self.key_env, self.timeout = endpoint, key_env, timeout
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())

    def request(self, method, operation_id, payload, home):
        # 随机测试空间名只作路由，不代替服务端鉴权。
        body = json.dumps({"method": method, "operation_id": operation_id,
                           "payload": payload, "namespace": Path(home).name},
                          ensure_ascii=False, allow_nan=False).encode()
        headers = {"Content-Type": "application/json"}
        if self.key_env:
            key = os.environ.get(self.key_env)
            if not key:
                raise TransportError("credential_missing")
            headers["Authorization"] = "Bearer " + key
        req = urllib.request.Request(self.endpoint, data=body, headers=headers, method="POST")
        try:
            with self._opener.open(req, timeout=self.timeout) as response:
                raw = response.read(4 * 1024 * 1024 + 1)
                if len(raw) > 4 * 1024 * 1024:
                    raise TransportError("response_too_large")
                return decode_response(raw)
        except urllib.error.HTTPError as exc:
            exc.close()
            raise TransportError("http_error") from None
        except (TimeoutError, urllib.error.URLError, OSError):
            raise TransportError("transport_uncertain") from None

    def close(self):
        pass
