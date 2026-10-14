import argparse
import json
import os
import sys
from dataclasses import asdict

from . import memory
from .generator import generate
from .reader import LLMReader, RuleReader
from .report import render
from .runner import run, summarize
from .schema import Case, CATEGORIES
from .sweep import DEFAULT_DISTRACTS, sweep


def _table(summary):
    cats = list(CATEGORIES)
    print(f"{'system':<16}" + "".join(f"{c:>9}" for c in cats) + f"{'overall':>9}{'leak':>7}{'ctx':>8}")
    for s, r in sorted(summary.items(), key=lambda x: -x[1]["overall"]):
        print(f"{s:<16}" + "".join(f"{r.get(c,0)*100:>8.0f}%" for c in cats)
              + f"{r['overall']*100:>8.0f}%{r['leak_rate']*100:>6.0f}%{r['avg_ctx']:>8.0f}")


def main(argv=None):
    p = argparse.ArgumentParser("memobench", description="智能体长期记忆自动化评测")
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="生成评测数据集")
    g.add_argument("-n", type=int, default=20, help="每类用例数")
    g.add_argument("--sessions", type=int, default=6)
    g.add_argument("--turns", type=int, default=8, help="每会话用户消息数")
    g.add_argument("--seed", type=int, default=42)
    g.add_argument("--distract", type=int, default=3, help="每个相关属性的干扰句数")
    g.add_argument("-o", "--out", default="data/memobench.jsonl")

    r = sub.add_parser("run", help="运行评测")
    r.add_argument("--data", help="数据集 jsonl；缺省则按参数现场生成")
    r.add_argument("-n", type=int, default=20)
    r.add_argument("--sessions", type=int, default=6)
    r.add_argument("--turns", type=int, default=8)
    r.add_argument("--seed", type=int, default=42)
    r.add_argument("--distract", type=int, default=3)
    r.add_argument("--systems", default=",".join(getattr(memory, "DEFAULT_SYSTEMS", list(memory.REGISTRY))))
    r.add_argument("--reader", choices=["rule", "llm"], default="rule")
    r.add_argument("--out", default="results")

    s = sub.add_parser("sweep", help="扫描干扰句数，生成各系统难度曲线")
    s.add_argument("-n", type=int, default=20, help="每类用例数")
    s.add_argument("--sessions", type=int, default=6)
    s.add_argument("--turns", type=int, default=8)
    s.add_argument("--seed", type=int, default=42)
    s.add_argument("--distract", type=int, nargs="+", default=list(DEFAULT_DISTRACTS),
                   help="干扰句数列表，默认 0 1 2 4 6 8")
    s.add_argument("--systems", default=",".join(getattr(memory, "DEFAULT_SYSTEMS", list(memory.REGISTRY))))
    s.add_argument("--reader", choices=["rule", "llm"], default="rule")
    s.add_argument("--out", default="results")

    a = p.parse_args(argv)
    if a.cmd == "generate":
        cases = generate(a.n, a.sessions, a.turns, a.seed, a.distract)
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        with open(a.out, "w", encoding="utf-8") as f:
            for c in cases:
                f.write(json.dumps(c.to_dict(), ensure_ascii=False) + "\n")
        print(f"已生成 {len(cases)} 条用例 -> {a.out}")
        return 0

    systems = [name.strip() for name in a.systems.split(",")]
    if any(name not in memory.REGISTRY for name in systems):
        p.error(f"系统名称无效，可选: {', '.join(memory.REGISTRY)}")
    if a.cmd == "sweep":
        if a.n < 1 or a.sessions < 2 or not 0 <= a.turns <= 36 or any(d < 0 for d in a.distract):
            p.error("sweep 要求 n >= 1、sessions >= 2、0 <= turns <= 36、distract >= 0")
        reader = RuleReader() if a.reader == "rule" else LLMReader()
        data = sweep(systems, reader, a.out, a.distract, a.n, a.sessions, a.turns, a.seed)
        for level in data['levels']:
            print(f"\n干扰句数: {level['distract']}")
            _table(level['summary'])
        print(f"\n结果: {a.out}/sweep.json\n报告: {a.out}/sweep.html")
        return 0

    if a.data:
        with open(a.data, encoding="utf-8") as f:
            cases = [Case.from_dict(json.loads(l)) for l in f if l.strip()]
    else:
        cases = generate(a.n, a.sessions, a.turns, a.seed, a.distract)
    reader = RuleReader() if a.reader == "rule" else LLMReader()
    results = run(cases, systems, reader)
    summary = summarize(results)
    os.makedirs(a.out, exist_ok=True)
    with open(f"{a.out}/results.jsonl", "w", encoding="utf-8") as f:
        for x in results:
            f.write(json.dumps(asdict(x), ensure_ascii=False) + "\n")
    with open(f"{a.out}/summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    with open(f"{a.out}/report.html", "w", encoding="utf-8") as f:
        f.write(render(summary, {"reader": reader.name, "n_cases": len(cases), "seed": a.seed}, results, cases))
    _table(summary)
    print(f"\n报告: {a.out}/report.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
