"""扫描同主题干扰句数量，比较各记忆系统的难度曲线。"""
import html
import json
import os

from .generator import generate
from .report import _CSS, _colors, _legend, _plot_axes, _svg
from .runner import run, summarize

DEFAULT_DISTRACTS = (0, 1, 2, 4, 6, 8)


def render(data):
    levels = data['levels']
    colors = _colors(data['meta']['systems'])
    xmax = max(1, max(row['distract'] for row in levels))
    parts = _plot_axes(xmax, '每个相关属性的干扰句数', [row['distract'] for row in levels])
    rows = []
    for s, color in colors.items():
        points = [(60 + 380 * row['distract'] / xmax, 290 - 240 * row['summary'][s]['overall'])
                  for row in levels]
        coords = ' '.join(f'{x:.2f},{y:.2f}' for x, y in points)
        parts.append(f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="2">'
                     f'<title>{html.escape(s)}</title></polyline>')
        for row, (x, y) in zip(levels, points):
            score = row['summary'][s]['overall']
            label = f"{s}：干扰句数 {row['distract']}，总分 {score:.1%}"
            parts.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="4" fill="{color}">'
                         f'<title>{html.escape(label)}</title></circle>')
        cells = ''.join(f"<td>{row['summary'][s]['overall']:.1%}</td>" for row in levels)
        rows.append(f'<tr><td>{html.escape(s)}</td>{cells}</tr>')
    head = ''.join(f"<th>{row['distract']}</th>" for row in levels)
    meta = data['meta']
    return f'''<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MemoBench 难度曲线</title><style>{_CSS}</style></head><body><main>
<h1>MemoBench 难度曲线</h1>
<p class="muted">读取器 {html.escape(meta['reader'])} · 每档用例 {levels[0]['n_cases']} · 种子 {meta['seed']}
 · 会话数 {meta['sessions']} · 每会话用户消息数 {meta['turns']}</p>
<section class="card"><h2>干扰句数与总分</h2>{_svg('各系统随干扰句数变化的总分', parts)}{_legend(colors)}</section>
<section class="card"><table><thead><tr><th>系统 / 干扰句数</th>{head}</tr></thead>
<tbody>{''.join(rows)}</tbody></table></section>
<p class="muted">各档使用相同生成参数与种子；干扰数量会改变随机采样过程，各档并非逐题配对数据。</p>
</main></body></html>'''


def sweep(systems, reader, out='results', distracts=DEFAULT_DISTRACTS,
          n=20, sessions=6, turns=8, seed=42):
    distracts = sorted(set(distracts))
    if not distracts or any(d < 0 for d in distracts):
        raise ValueError('干扰句数必须是非空的非负整数列表')
    systems = list(systems)
    data = {'meta': {'reader': reader.name, 'systems': systems, 'n': n,
                     'sessions': sessions, 'turns': turns, 'seed': seed}, 'levels': []}
    for distract in distracts:
        cases = generate(n, sessions, turns, seed, distract)
        summary = summarize(run(cases, systems, reader))
        data['levels'].append({'distract': distract, 'n_cases': len(cases), 'summary': summary})
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, 'sweep.json'), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    with open(os.path.join(out, 'sweep.html'), 'w', encoding='utf-8') as f:
        f.write(render(data))
    return data
