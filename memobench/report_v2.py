"""静态、无脚本报告；缺失值不绘制成零分雷达。"""
from html import escape
from pathlib import Path
from .schema_v2 import OFFICIAL_CAPABILITIES
from .runner_v2 import read, safe_output, atomic_write


def display(value):
    return '未测' if value is None else escape(str(value), quote=True)


def rate(value):
    return '未测' if value is None else f'{value:.1%}'


def render(summary, records=()):
    parts = ['<!doctype html><html lang="zh-CN"><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'">',
        '<title>MemoBench v2 运行报告</title><style>body{font:16px/1.6 system-ui;max-width:1100px;margin:32px auto;padding:0 20px;color:#172033}table{border-collapse:collapse;width:100%;margin:16px 0}th,td{border:1px solid #ccd3df;padding:8px;text-align:left}pre{white-space:pre-wrap;overflow-wrap:anywhere}.notice{background:#fff0c2;padding:16px;font-weight:bold}section{border-top:2px solid #ccd3df;margin-top:28px}</style>',
        '<h1>MemoBench v2 运行报告</h1>',
        '<p class="notice">' + display(summary.get('data_notice')) + '</p>',
        '<p>运行状态：' + display(summary.get('status')) + '；正式 test 题数：' +
        display(summary.get('dataset_validation', {}).get('formal_test_n_query')) + '</p>',
        '<p>不发布排行榜。正确性、风险与任务完成分别统计；未判定不计为零分。</p>',
        '<section><h2>v1 legacy 诊断</h2><p>未测（本报告未载入 v1；旧版产物独立保存，不混榜）。</p></section>']
    for mode, title in [('component', 'component 记忆组件'), ('native_agent', 'native 真实智能体')]:
        parts.append('<section><h2>' + title + '</h2>')
        if summary.get('mode') != mode or not summary.get('partitions'):
            parts.append('<p>未测</p>')
            if summary.get('mode') == mode and summary.get('reason'):
                parts.append('<p>blocked：' + display(summary['reason']) + '</p>')
        else:
            if summary.get('fixture'):
                fixture_notice = ('离线 native transport fixture，仅验证协议与工具链，不代表真实产品接入。'
                                  if summary.get('mode') == 'native_agent' else
                                  '协议 fixture / smoke，非真实智能体；回显读取器不代表公共 LLM 能力。')
                parts.append('<p class="notice">' + fixture_notice + '</p>')
            parts.append('<p>case：' + display(summary.get('n_case')) + '；失败 case：' + display(summary.get('failed_cases')) + '</p>')
            for execution in ('offline', 'online', 'replay'):
                parts.append('<h3>' + execution + '</h3>')
                block = summary['partitions'].get(execution)
                if not block:
                    parts.append('<p>未测</p>')
                    continue
                stats = block['statistics']
                parts.append('<p>完整判定微平均：' + rate(stats['micro_mean']) +
                    '；按故事宏平均：' + rate(stats['story_macro_mean']) +
                    '；评分分母：' + display(stats['denominator']) + '</p>')
                parts.append('<table><tr><th>计数</th><th>值</th></tr>')
                for key in ('n_story', 'n_query', 'n_repeat', 'n_repeat_planned', 'n_expected',
                            'n_received', 'missing', 'unscored', 'error', 'timeout', 'unsupported',
                            'error_rate', 'timeout_rate'):
                    parts.append('<tr><td>' + key + '</td><td>' + display(stats[key]) + '</td></tr>')
                parts.append('</table><table><tr><th>官方能力（缺失不绘制为0）</th><th>分数</th><th>已评分/计划</th></tr>')
                for key, label in OFFICIAL_CAPABILITIES.items():
                    cap = stats['capabilities'][key]
                    parts.append(f'<tr><td>{label}</td><td>{rate(cap["mean"])}</td><td>{cap["denominator"]}/{cap["n_expected"]}</td></tr>')
                parts.append('</table><table><tr><th>指标</th><th>比例</th><th>分子/分母</th><th>适用</th><th>待复核</th></tr>')
                for key, metric in block['scoring']['metrics'].items():
                    parts.append(f'<tr><td>{escape(key)}</td><td>{rate(metric["rate"])}</td><td>{metric["numerator"]}/{metric["denominator"]}</td><td>{metric["eligible"]}</td><td>{metric["pending"]}</td></tr>')
                parts.append('</table><p>current_value_misuse、forgotten_disclosure、unknown_assertion 的 true 表示风险发生；其余表示成功。宏平均按故事等权，仅统计完整判定项。</p>')
        parts.append('</section>')
    parts.append('<section><h2>运行限制与成本</h2><p>历史失败尝试：' + display(summary.get('prior_failed_attempts')) +
                 '；中断尝试：' + display(summary.get('interrupted_attempts')) +
                 '；完整在线费用：' + display(summary.get('cost', {}).get('total_cost')) + '</p>')
    for gap in summary.get('integration_gaps', []):
        parts.append('<p>' + display(gap) + '</p>')
    parts.append('</section><section><h2>原始输出与评分依据</h2>')
    for record in records:
        prediction = record['prediction']
        parts.append('<details><summary>' + display(prediction['episode_id']) + ' / ' +
                     display(prediction['variant_id']) + ' / ' + display(prediction['probe_id']) + '</summary>')
        parts.append('<pre>' + display(prediction.get('text')) + '</pre><p>状态：' + display(prediction['status']) +
                     '；评分理由：' + display(record['score'].get('review_reason') or record['score'].get('reason')) +
                     '；文件任务：' + display(record.get('task_status')) + '</p><pre>' +
                     display(record.get('evidence_locations')) + '</pre></details>')
    if summary.get('mode') == 'native_agent':
        if summary.get('fixture') or 'offline' in summary.get('partitions', {}):
            footer = '离线 native fixture 不构成真实产品接入或成绩；未知费用/用量保持 null。'
        elif summary.get('status') == 'blocked' and not summary.get('partitions'):
            footer = 'native 尚未执行，请查看阻断原因与准备配置；未知费用/用量保持 null。'
        else:
            footer = 'native 原生运行：产品版本与接入证据见运行配置；语义裁判的校准与最终裁决状态单独报告。未知费用/用量保持 null。'
    else:
        footer = 'openKylin、两款真实智能体、人工校准：未测。未知费用/用量保持 null。'
    parts.append('</section><p>' + footer + '</p></html>')
    return ''.join(parts)


def report(run_directory, out):
    root = Path(run_directory)
    summary = read(safe_output(root, 'summary.json'))
    records = []
    directory = safe_output(root, 'cases')
    if directory.exists():
        for path in sorted(directory.glob('*.json')):
            case = read(safe_output(root, 'cases/' + path.name))
            if case['attempts']:
                records.extend(case['attempts'][-1].get('results', []))
    atomic_write(out, render(summary, records))
    return summary
