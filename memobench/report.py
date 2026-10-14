import html
import json
from datetime import datetime

from .schema import CATEGORIES

_CSS = """
:root{--bg:#fafafa;--fg:#1d1d1f;--muted:#6b7280;--card:#fff;--line:#e5e7eb;--accent:#4f46e5}
@media (prefers-color-scheme:dark){:root{--bg:#111318;--fg:#e5e7eb;--muted:#9ca3af;--card:#1a1d24;--line:#2a2e37;--accent:#818cf8}}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.6 -apple-system,"PingFang SC","Noto Sans CJK SC",sans-serif}
main{max-width:1000px;margin:0 auto;padding:32px 16px}
h1{margin:0 0 4px}.muted{color:var(--muted)}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:20px;margin:20px 0;overflow-x:auto}
table{border-collapse:collapse;width:100%}th,td{padding:8px 10px;border-bottom:1px solid var(--line);text-align:center;white-space:nowrap}
th:first-child,td:first-child{text-align:left}
td.c{font-variant-numeric:tabular-nums}
.bar{height:8px;border-radius:4px;background:var(--accent);margin-top:4px}
.best{font-weight:700;color:var(--accent)}
"""


def _cell(v, best):
    pct = f"{v*100:.0f}%"
    cls = "c best" if best else "c"
    return f'<td class="{cls}">{pct}<div class="bar" style="width:{v*100:.0f}%;opacity:{0.25+0.75*v:.2f}"></div></td>'


def render(summary, meta) -> str:
    systems = sorted(summary, key=lambda s: -summary[s]["overall"])
    cats = [c for c in CATEGORIES if any(c in summary[s] for s in systems)]
    best = {c: max(summary[s].get(c, 0) for s in systems) for c in cats + ["overall"]}
    head = "".join(f"<th title='{html.escape(CATEGORIES[c])}'>{c}</th>" for c in cats)
    rows = []
    for s in systems:
        r = summary[s]
        cells = "".join(_cell(r.get(c, 0), r.get(c, 0) == best[c]) for c in cats)
        rows.append(f"<tr><td>{html.escape(s)}</td>{cells}{_cell(r['overall'], r['overall']==best['overall'])}"
                    f"<td class='c'>{r['leak_rate']*100:.0f}%</td><td class='c'>{r['avg_ctx']:.0f}</td></tr>")
    legend = "".join(f"<li><b>{c}</b>：{html.escape(d)}</li>" for c, d in CATEGORIES.items() if c in cats)
    return f"""<!doctype html><html lang="zh"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MemoBench 评测报告</title><style>{_CSS}</style></head><body><main>
<h1>MemoBench 评测报告</h1>
<p class="muted">读取器 {html.escape(meta['reader'])} · 用例 {meta['n_cases']} · 种子 {meta['seed']} · {datetime.now():%Y-%m-%d %H:%M}</p>
<div class="card"><table><thead><tr><th>记忆系统</th>{head}<th>总分</th><th>泄露率 ↓</th><th>平均上下文字符 ↓</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>
<div class="card"><h3>维度说明</h3><ul>{legend}<li><b>泄露率</b>：回答中出现已遗忘或已过期信息的比例</li></ul></div>
<script type="application/json" id="data">{html.escape(json.dumps(summary, ensure_ascii=False))}</script>
</main></body></html>"""
