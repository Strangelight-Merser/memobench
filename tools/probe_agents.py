#!/usr/bin/env python3
"""只读安装探测；--live 才执行版本和帮助，不启动模型或用户服务。"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from memobench.adapters_v2.transports import TransportError, run_process
from memobench.schema_v2 import AdapterCapabilities


def _redact(raw):
    text = raw.decode("utf-8", errors="replace")
    text = re.sub(r"(?i)(bearer\s+|(?:api[_-]?key|token|password)\s*[=:]\s*)\S+", r"\1[REDACTED]", text)
    text = re.sub(r"\bsk-[A-Za-z0-9_-]+", "[REDACTED]", text)
    return text.replace(str(Path.home()), "$USER_HOME")


def probe(config, *, live=False):
    report = {"status": "blocked", "recorded_at": datetime.now(timezone.utc).isoformat(),
              "host": {"system": platform.system(), "machine": platform.machine(),
                       "python": platform.python_version()},
              "openkylin": "NOT_VERIFIED", "live": live, "agents": []}
    for spec in config["agents"]:
        item = {"adapter_id": spec["adapter_id"], "status": "blocked", "reasons": [],
                "capabilities": AdapterCapabilities().to_dict(), "commands": [],
                "execution_mode": spec["execution_mode"], "models": [],
                "model_configuration": "NOT_VERIFIED", "session": "NOT_VERIFIED",
                "cross_session_memory": "NOT_VERIFIED", "state_directory": "NOT_VERIFIED",
                "async_flush": "NOT_VERIFIED", "cleanup": "NOT_VERIFIED",
                "permission_isolation": "NOT_VERIFIED", "review": "pending_review",
                "comparison_scope": "整体系统比较"}
        report["agents"].append(item)
        if not live:
            item["reasons"].append("live_required：未执行外部命令")
            continue
        executable = next((path for name in spec["executables"]
                           if (path := shutil.which(name))), None)
        item["executable_found"] = executable is not None
        item["missing_credentials"] = [name for name in spec["required_env"] if not os.environ.get(name)]
        if not executable:
            item["reasons"].append("executable_not_found：PATH 未发现候选命令，不代表全盘未安装")
        else:
            with tempfile.TemporaryDirectory(prefix="memobench-probe-") as home:
                for args in [["--version"]] + spec["help_args"]:
                    # 探测配置只允许只读帮助与版本命令，不能变成任意执行器。
                    if args not in (["--version"], ["--help"], ["agent", "--help"]):
                        raise ValueError("非白名单探测命令")
                    entry = {"argv": [Path(executable).name] + args}
                    item["commands"].append(entry)
                    try:
                        code, out, err = run_process([executable] + args, home, timeout=15)
                        entry.update(returncode=code, stdout=_redact(out), stderr=_redact(err),
                                     stdout_sha256=hashlib.sha256(out).hexdigest(),
                                     stderr_sha256=hashlib.sha256(err).hexdigest())
                    except TransportError as exc:
                        entry["error"] = exc.code
        if item["missing_credentials"]:
            item["reasons"].append("credential_missing：未提供所选服务的环境变量")
        item["reasons"].append("native_binding_not_verified：尚无该安装版本的会话、响应、flush 和隔离证据")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args(argv)
    report = probe(json.loads(Path(args.config).read_text(encoding="utf-8")), live=args.live)
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("blocked：探测报告已写入；真实智能体生命周期未验收")
    return 2


if __name__ == "__main__":
    sys.exit(main())
