import html
import json
import math
from datetime import datetime

from .schema import CATEGORIES

_CSS = """
:root{color-scheme:light dark;--bg:#fafafa;--fg:#1d1d1f;--muted:#6b7280;--card:#fff;--line:#e5e7eb;--accent:#4f46e5}
@media (prefers-color-scheme:dark){:root{--bg:#111318;--fg:#e5e7eb;--muted:#9ca3af;--card:#1a1d24;--line:#2a2e37;--accent:#818cf8}}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.6 -apple-system,"PingFang SC","Noto Sans CJK SC",sans-serif}
*{box-sizing:border-box}main{max-width:1000px;margin:0 auto;padding:32px 16px;overflow-wrap:anywhere}
h1{margin:0 0 4px}.muted{color:var(--muted)}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:20px;margin:20px 0;overflow-x:auto}
table{border-collapse:collapse;width:100%}th,td{padding:8px 10px;border-bottom:1px solid var(--line);text-align:center;white-space:nowrap}
th:first-child,td:first-child{text-align:left}
td.c{font-variant-numeric:tabular-nums}
.bar{height:8px;border-radius:4px;background:var(--accent);margin-top:4px}
.best{font-weight:700;color:var(--accent)}
.charts{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}
.charts .card{margin:0;min-width:0}h2{font-size:20px;margin:0 0 12px}
svg{display:block;width:100%;height:auto;color:var(--fg)}svg text{fill:currentColor;font-size:13px}
.grid{fill:none;stroke:var(--line)}.axis{stroke:var(--muted)}
.legend{display:flex;flex-wrap:wrap;gap:8px 20px;list-style:none;padding:0}
.legend li{display:flex;align-items:center;gap:8px;min-width:0;overflow-wrap:anywhere}
.swatch{width:12px;height:12px;border-radius:50%;flex-shrink:0}
summary{cursor:pointer;font-weight:600}details{padding:12px 0;border-bottom:1px solid var(--line)}
.failure{padding:12px 0;border-top:1px solid var(--line)}.failure p{margin:4px 0;white-space:pre-wrap}
@media(max-width:640px){main{padding:20px 12px}.card{padding:12px}.charts{grid-template-columns:1fr}}
"""


def _colors(systems):
    return {s: f"hsl({i * 137.508 % 360:.1f},65%,52%)" for i, s in enumerate(systems)}


def _legend(colors):
    return '<ul class="legend">' + ''.join(
        f'<li><span class="swatch" style="background:{color}"></span>{html.escape(s)}</li>'
        for s, color in colors.items()) + '</ul>'


def _svg(title, parts, width=480, height=360):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
            f'role="img" aria-label="{html.escape(title, quote=True)}">'
            f'<title>{html.escape(title)}</title>{"".join(parts)}</svg>')


def _radar(summary, colors):
    cats = list(CATEGORIES)

    def point(i, value):
        angle = -math.pi / 2 + i * 2 * math.pi / len(cats)
        return 240 + 120 * value * math.cos(angle), 180 + 120 * value * math.sin(angle)

    def points(values):
        return ' '.join(f'{x:.2f},{y:.2f}' for i, v in enumerate(values) for x, y in [point(i, v)])

    parts = []
    for level in (0.25, 0.5, 0.75, 1):
        parts.append(f'<polygon class="grid" points="{points([level] * len(cats))}"/>')
        parts.append(f'<text x="245" y="{180 - 120 * level:.2f}">{level:.0%}</text>')
    for i, c in enumerate(cats):
        x, y = point(i, 1)
        lx, ly = point(i, 1.25)
        parts.append(f'<line class="grid" x1="240" y1="180" x2="{x:.2f}" y2="{y:.2f}"/>')
        parts.append(f'<text x="{lx:.2f}" y="{ly + 5:.2f}" text-anchor="middle">{c}</text>')
    for s, color in colors.items():
        values = [summary[s].get(c, 0) for c in cats]
        label = s + '：' + '，'.join(f'{c} {v:.1%}' for c, v in zip(cats, values))
        parts.append(f'<polygon points="{points(values)}" fill="{color}" fill-opacity="0.08" '
                     f'stroke="{color}" stroke-width="2"><title>{html.escape(label)}</title></polygon>')
    return _svg('六维能力雷达图，刻度 0–100%', parts)


def _plot_axes(xmax, xlabel, ticks):
    # 散点图和难度曲线共用固定坐标范围，总分始终从 0% 到 100%。
    parts = []
    for value in (0, 0.25, 0.5, 0.75, 1):
        y = 290 - 240 * value
        parts.append(f'<line class="grid" x1="60" y1="{y}" x2="440" y2="{y}"/>')
        parts.append(f'<text x="52" y="{y + 5}" text-anchor="end">{value:.0%}</text>')
    parts.append('<path class="axis" fill="none" d="M60 50V290H440"/>')
    parts.append('<text x="60" y="25">总分</text>')
    for value in ticks:
        x = 60 + 380 * value / xmax
        parts.append(f'<text x="{x:.2f}" y="313" text-anchor="middle">{value:g}</text>')
    parts.append(f'<text x="250" y="345" text-anchor="middle">{html.escape(xlabel)}</text>')
    return parts


def _scatter(summary, colors):
    xmax = max(1, max((r['avg_ctx'] for r in summary.values()), default=0) * 1.1)
    parts = _plot_axes(xmax, '平均上下文字符 ↓', [xmax * i / 4 for i in range(5)])
    for s, color in colors.items():
        r = summary[s]
        x, y = 60 + 380 * r['avg_ctx'] / xmax, 290 - 240 * r['overall']
        label = f"{s}：平均上下文 {r['avg_ctx']:.1f} 字符，总分 {r['overall']:.1%}"
        parts.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="6" fill="{color}" '
                     f'fill-opacity="0.7" stroke="var(--fg)"><title>{html.escape(label)}</title></circle>')
    return _svg('平均上下文字符 vs 总分', parts)


def _failures(systems, results, cases):
    if results is None or cases is None:
        return '<p class="muted">未提供逐题结果与用例。</p>'
    by_id = {c.id: c for c in cases}
    groups = {s: [] for s in systems}
    for r in results:
        if not r.correct:
            groups.setdefault(r.system, []).append(r)
    sections = []
    for s, failed in groups.items():
        items = []
        for r in failed:
            case = by_id.get(r.case_id)
            question = case.question if case else '未提供对应用例'
            expected = '；'.join(case.answers) if case else '未提供对应用例'
            forbidden = ('<p><b>禁止出现：</b>' + html.escape('；'.join(case.forbidden)) + '</p>'
                         if case and case.forbidden else '')
            items.append(f'<article class="failure"><p class="muted">{html.escape(r.case_id)} · '
                         f'{html.escape(r.category)}{" · 泄露" if r.leaked else ""}</p>'
                         f'<p><b>问题：</b>{html.escape(question)}</p>'
                         f'<p><b>期望：</b>{html.escape(expected)}</p>{forbidden}'
                         f'<p><b>实际回答：</b>{html.escape(r.answer)}</p></article>')
        sections.append(f'<details><summary>{html.escape(s)} · {len(failed)} 个失败用例</summary>'
                        + (''.join(items) or '<p>全部通过。</p>') + '</details>')
    return ''.join(sections) or '<p>暂无评测结果。</p>'


def _cell(v, best):
    pct = f"{v*100:.0f}%"
    cls = "c best" if best else "c"
    return f'<td class="{cls}">{pct}<div class="bar" style="width:{v*100:.0f}%;opacity:{0.25+0.75*v:.2f}"></div></td>'


def render(summary, meta, results=None, cases=None) -> str:
    systems = sorted(summary, key=lambda s: -summary[s]["overall"])
    cats = [c for c in CATEGORIES if any(c in summary[s] for s in systems)]
    best = {c: max((summary[s].get(c, 0) for s in systems), default=0) for c in cats + ["overall"]}
    colors = _colors(systems)
    head = "".join(f"<th title='{html.escape(CATEGORIES[c])}'>{c}</th>" for c in cats)
    rows = []
    for s in systems:
        r = summary[s]
        cells = "".join(_cell(r.get(c, 0), r.get(c, 0) == best[c]) for c in cats)
        rows.append(f"<tr><td>{html.escape(s)}</td>{cells}{_cell(r['overall'], r['overall']==best['overall'])}"
                    f"<td class='c'>{r['leak_rate']*100:.0f}%</td><td class='c'>{r['avg_ctx']:.0f}</td></tr>")
    legend = "".join(f"<li><b>{c}</b>：{html.escape(d)}</li>" for c, d in CATEGORIES.items() if c in cats)
    data = json.dumps(summary, ensure_ascii=False).replace('<', '\\u003c')
    return f"""<!doctype html><html lang="zh"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MemoBench 评测报告</title><style>{_CSS}</style></head><body><main>
<h1>MemoBench 评测报告</h1>
<p class="muted">读取器 {html.escape(meta['reader'])} · 用例 {meta['n_cases']} · 种子 {meta['seed']} · {datetime.now():%Y-%m-%d %H:%M}</p>
<div class="card"><table><thead><tr><th>记忆系统</th>{head}<th>总分</th><th>泄露率 ↓</th><th>平均上下文字符 ↓</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>
<div class="charts"><section class="card"><h2>六维能力</h2>{_radar(summary, colors)}{_legend(colors)}
<p class="muted">各维度为准确率；未评测的维度按 0 绘制，以表格为准。</p></section>
<section class="card"><h2>上下文成本与总分</h2>{_scatter(summary, colors)}{_legend(colors)}</section></div>
<section class="card"><h2>失败用例</h2>{_failures(systems, results, cases)}</section>
<div class="card"><h3>维度说明</h3><ul>{legend}<li><b>泄露率</b>：回答中出现已遗忘或已过期信息的比例</li></ul></div>
<script type="application/json" id="data">{data}</script>
</main></body></html>"""
