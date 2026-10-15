"""Explicit SSH transport for the reviewed openKylin VM product bridge."""
import hashlib
import json
from pathlib import Path
from uuid import uuid4

from .transports import TransportError, decode_response, run_process


class SSHVMTransport:
    def __init__(self, ssh_config, product, *, live=False, timeout=330,
                 bridge_path='/home/mb/memobench-native/native_vm_product.py'):
        if not live:
            raise TransportError('live_required')
        if product not in ('kylin', 'openclaw'):
            raise ValueError('unknown VM product')
        import re
        if not re.fullmatch(r'/[a-zA-Z0-9_./-]+', bridge_path) or '..' in Path(bridge_path).parts:
            raise ValueError('unsafe bridge path')
        self.argv = ['/usr/bin/ssh', '-F', str(Path(ssh_config).resolve()),
                     'memobench-vm', '/usr/bin/python3',
                     bridge_path, '--product', product]
        self.bridge_sha256 = hashlib.sha256((Path(__file__).resolve().parents[2] / 'tools/native_vm_product.py').read_bytes()).hexdigest()
        self.timeout = timeout
        self.namespaces = {}

    def request(self, method, operation_id, payload, home):
        namespace = self.namespaces.setdefault(str(home), uuid4().hex)
        body = json.dumps({'namespace': namespace, 'run_id': Path(home).parent.name, 'bridge_sha256': self.bridge_sha256, 'method': method,
                           'operation_id': operation_id, 'payload': payload},
                          ensure_ascii=False, allow_nan=False).encode()
        code, out, _ = run_process(self.argv, home, body, self.timeout)
        if code:
            raise TransportError('vm_product_failed')
        return decode_response(out)

    def task_checkpoint(self, operation_id, payload, home):
        checkpoint = self.request('artifact_checkpoint', operation_id + ':checkpoint',
                                  dict(payload, query_operation=operation_id), home)
        expected = {'run': home.parent.name, 'namespace': self.namespaces[str(home)],
                    'episode_id': payload['episode_id'], 'variant_id': payload['variant_id'],
                    'session_id': payload['session_id'], 'operation_id': operation_id,
                    'bridge_sha256': self.bridge_sha256}
        if checkpoint.get('binding') != expected:
            raise TransportError('artifact_checkpoint_binding_mismatch')
        return checkpoint

    def task_evidence(self, operation_id, payload, home):
        return self.request('artifact_evidence', operation_id + ':evidence',
                            dict(payload, query_operation=operation_id), home)

    def close(self):
        pass  # NativeAdapter sends one confirmed close per namespace first.
