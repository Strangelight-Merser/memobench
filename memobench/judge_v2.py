"""单答案裁判与盲标校准；网络传输由卡6注入，不在此实现。"""
import hashlib
import json
from pathlib import Path

from .protocol_v2 import adapter_payload
from .schema_v2 import (AdapterCapabilities, ContractError, Gold, Observation,
                        Prediction, Probe, validate_prediction)
from .scoring_v2 import METRICS, result, score, strict_json, validate_inputs

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts/judge-v0.2/system.txt"


def build_messages(gold, prediction, probe, observations, capabilities):
    validate_inputs(gold, prediction)
    validate_prediction(prediction, probe, capabilities, observations)
    evidence = []
    by_id = {o.observation_id: o for o in observations}
    if len(by_id) != len(observations):
        raise ContractError("证据 ID 重复")
    for location in gold.evidence:
        observation = by_id.get(location.observation_id)
        if observation is None:
            raise ContractError("缺少证据")
        # 复用协议的范围、时间和公开字段校验。
        reference = Prediction(probe.episode_id, probe.variant_id, probe.session_id,
                               probe.probe_id, "ok", "", prediction.answered_at,
                               retrieved_evidence=[location.observation_id])
        validate_prediction(reference, probe,
                            AdapterCapabilities(retrieved_evidence="supported"), [observation])
        if location.end is not None and location.end > len(observation.text):
            raise ContractError("证据字符位置越界")
        evidence.append({"observation_id": location.observation_id,
                         "role": observation.role,
                         "text": observation.text[location.start:location.end]})
    trusted = {"query": adapter_payload(probe)["query"],
               "slots": [s.to_dict() for s in gold.slots],
               "canonical_state_ledger": gold.canonical_state_ledger,
               "forget_policies": gold.forget_policies,
               "expected_actions": gold.expected_actions,
               "evidence": evidence}
    candidate = {"untrusted_candidate": prediction.text,
                 "slots": None if prediction.slots is None else
                 [s.to_dict() for s in prediction.slots]}
    return [{"role": "system", "content": PROMPT_PATH.read_text(encoding="utf-8")},
            {"role": "user", "content": json.dumps({"evaluation": trusted}, ensure_ascii=False)},
            {"role": "user", "content": json.dumps(candidate, ensure_ascii=False)}]


def parse_judgment(raw, gold):
    data = strict_json(raw)
    if (type(data) is not dict or set(data) != {"status", "metrics", "evidence_ids", "reason"}
            or data["status"] not in ("scored", "pending_review")
            or type(data["reason"]) is not str or not data["reason"].strip()
            or type(data["metrics"]) is not dict or set(data["metrics"]) != set(METRICS)
            or any(v is not None and type(v) is not bool for v in data["metrics"].values())
            or type(data["evidence_ids"]) is not list
            or any(type(v) is not str for v in data["evidence_ids"])):
        raise ValueError("裁判 JSON 格式错误")
    ids = data["evidence_ids"]
    if len(ids) != len(set(ids)) or not set(ids) <= {e.observation_id for e in gold.evidence}:
        raise ValueError("裁判证据引用错误")
    if data["metrics"]["evidence_supported"] is True and not ids:
        raise ValueError("缺少支持证据")
    if data["metrics"]["task_completed"] is not None:
        raise ValueError("裁判不能验证真实任务产物")
    return data


def judge(gold, prediction, probe, observations, capabilities, *, transport=None,
          task_checks=None):
    """transport(messages)->str；调用方负责卡6状态检查、预算和用量存盘。"""
    hard = score(gold, prediction, task_checks=task_checks)
    validate_prediction(prediction, probe, capabilities, observations)
    if prediction.status != "ok" or hard["status"] == "scored":
        return hard
    try:
        messages = build_messages(gold, prediction, probe, observations, capabilities)
    except ContractError:
        hard["review_reason"] = "insufficient_evidence_or_invalid_reference"
        return hard
    if transport is None:
        hard["review_reason"] = "blocked: judge_transport_unavailable"
        return hard
    try:
        raw = transport(messages)
    except Exception:
        # 不透传供应商异常，避免凭据或私有文本进入日志。
        hard["review_reason"] = "judge_transport_failed"
        return hard
    try:
        parsed = parse_judgment(raw, gold)
    except (ValueError, TypeError, OverflowError):
        hard["review_reason"] = "invalid_judge_json"
        return hard
    if parsed["status"] == "pending_review":
        hard["review_reason"] = "judge_requested_review"
        return hard
    values = hard["metrics"].copy()
    for name in METRICS:
        if name == "forgotten_disclosure" and gold.forget_policies and values[name] is None:
            # 未支持的删除政策不能靠裁判猜测含义。
            continue
        if values[name] is None and name != "task_completed":
            values[name] = parsed["metrics"][name]
    # 无证据支持的肯定答案不能自动放行。
    if (any(s.state == "answer" for s in gold.slots) and
            values["answer_correct"] is True and values["evidence_supported"] is not True):
        values["answer_correct"] = None
    output = result(gold, values, source="semantic_judge")
    output["evidence_ids"] = parsed["evidence_ids"]
    output["reason"] = parsed["reason"]
    return output


def overall_label(scored):
    """完整结果才导出校准标签；未判定项不隐式视为成功。"""
    if scored["status"] != "scored":
        return None
    return not bool(scored["errors"])


def agreement(pairs):
    """配对标签为bool/null；错误放行率分母为人工判错数。"""
    pairs = list(pairs)
    if any(type(p) not in (tuple, list) or len(p) != 2 or
           any(v is not None and type(v) is not bool for v in p) for p in pairs):
        raise ValueError("标签须为 bool/null 对")
    matrix = {"human_false": {"model_false": 0, "model_true": 0},
              "human_true": {"model_false": 0, "model_true": 0}}
    valid = [(h, m) for h, m in pairs if h is not None and m is not None]
    for h, m in valid:
        matrix["human_" + str(h).lower()]["model_" + str(m).lower()] += 1
    n = len(valid)
    po = sum(h == m for h, m in valid) / n if n else None
    ph = sum(h for h, _ in valid) / n if n else 0
    pm = sum(m for _, m in valid) / n if n else 0
    pe = ph * pm + (1 - ph) * (1 - pm)
    negative = sum(not h for h, _ in valid)
    false_accept = sum(not h and m for h, m in valid)
    return {"n": n, "pending": len(pairs) - n, "agreement": po,
            "cohen_kappa": (po - pe) / (1 - pe) if n and pe != 1 else None,
            "confusion_matrix": matrix, "false_accept_count": false_accept,
            "false_accept_denominator": negative,
            "false_accept_rate": false_accept / negative if negative else None}


def prepare_blind(records, development):
    """生成无模型身份/裁判标签的盲标包；禁止故事或情节模板交叉。"""
    records, development = list(records), list(development)
    if len(development) < 20 or len(records) < 60:
        raise ValueError("需要至少20开发输出和60留出输出")
    for field in ("story_id", "template_id"):
        if {r[field] for r in records} & {r[field] for r in development}:
            raise ValueError("开发和留出泄漏")
    if len({r["story_id"] for r in records}) != len(records):
        raise ValueError("留出输出必须来自独立故事")
    blind, seen = [], set()
    for record in records:
        content = {k: record[k] for k in ("probe", "gold", "prediction", "observations")}
        # 通过协议重建，移除任意系统身份元数据。
        content = {"probe": Probe.from_dict(content["probe"]).to_dict(),
                   "gold": Gold.from_dict(content["gold"]).to_dict(),
                   "prediction": Prediction.from_dict(content["prediction"]).to_dict(),
                   "observations": [Observation.from_dict(o).to_dict() for o in content["observations"]]}
        content["prediction"]["usage"] = None
        identifier = hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        if identifier in seen:
            raise ValueError("重复留出输出")
        seen.add(identifier)
        blind.append({"item_id": identifier, "split": "holdout", **content,
                      "human_label": None, "review_status": "pending_review"})
    return sorted(blind, key=lambda row: row["item_id"])


def calibrate(annotations, judgments):
    """按 opaque item_id 对齐，保留逐条人工标签和模型标签。"""
    annotations, judgments = list(annotations), list(judgments)
    for rows in (annotations, judgments):
        if len({r["item_id"] for r in rows}) != len(rows):
            raise ValueError("校准 ID 重复")
    indexed = {r["item_id"]: r for r in judgments}
    if set(indexed) - {r["item_id"] for r in annotations}:
        raise ValueError("裁判结果含未知 ID")
    rows = []
    for a in annotations:
        if a.get("split") != "holdout":
            raise ValueError("校准只能使用留出集")
        h = a.get("human_label") if a.get("review_status") == "reviewed" else None
        m = indexed.get(a["item_id"], {}).get("model_label")
        rows.append({"item_id": a["item_id"], "human_label": h, "model_label": m})
    metrics = agreement([(r["human_label"], r["model_label"]) for r in rows])
    passed = (metrics["n"] >= 60 and metrics["pending"] == 0 and
              metrics["agreement"] >= .9 and metrics["cohen_kappa"] is not None and
              metrics["cohen_kappa"] >= .7)
    return {"status": "passed" if passed else "pending_review",
            "publish_judge_ranking": passed, "fallback": None if passed else "manual_adjudication",
            "metrics": metrics, "items": rows}


def main(argv=None):
    """独立校准入口；卡7可直接调用 calibrate，不重复实现 runner。"""
    import argparse
    parser = argparse.ArgumentParser(description="MemoBench 留出盲标校准（离线）")
    parser.add_argument("--annotations", required=True)
    parser.add_argument("--judgments", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    def read(path):
        return [strict_json(line) for line in Path(path).read_text(encoding="utf-8").splitlines()
                if line.strip()]
    output = calibrate(read(args.annotations), read(args.judgments))
    Path(args.out).write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
