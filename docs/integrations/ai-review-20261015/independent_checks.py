"""Independent review checks: expected answers authored from both source wordings, not truth()/generate()."""
import json, hashlib, re
from pathlib import Path
from datetime import datetime, timezone
ROOT=Path(__file__).resolve().parents[3]
D=ROOT/'data/v0.2'
rows=lambda p:[json.loads(x) for x in p.read_text().splitlines() if x.strip()]
sources=rows(D/'sources.jsonl')
# Ordered to original sources lines; null entries are explicit unknown/conflict/forgotten below.
answers=[
['archive/Spring'],['纯文本','日期'],['Vim','Firefox'],['reports/May/summary.txt'],['kitty'],['2.0.1','2.0'],['Kate','Emacs'],['aarch64'],[None],[None],['reports/Qinghe/week.txt','本周完成：\n下周计划：\n'],[None,'notes/today.txt','天气：\n心情：\n'],
['Ctrl+Alt+S'],['入门索引'],['每周一次'],['Rust'],[None],['开始\n结束\n','checklist/run.txt'],['小字容易看串行'],['离线'],['保留，不自动删除'],['周三下午'],['毫米','摄氏度'],['断网时也能展示'],['蓝色收纳袋','灰色盒子'],['权限不足'],['柜子第二层'],['inbox/He'],['核对摘要'],['LAB-09'],['共享目录','exchange'],['秒'],['双面',3],['浅色'],['晚上'],['西厅'],['aarch64'],['稳定通道'],['青林','P-17'],['Xfce'],['Inkscape'],['work/Map'],['x86_64'],[2],['SVG','PNG'],['Kylin Agent Runtime','apt'],[None],[None],[None],[None,'中文'],[None],[None],[None],['forms/B.txt','输入：\n输出：\n'],['保留原文件，另存错误记录，不覆盖原文件'],['tickets/current.txt','现象：\n复现：\n'],['handoff/status.txt','状态：待核验\n'],['batches/B7/result.txt','样本：\n结果：\n'],['inspections/today.txt','设备：\n异常：\n'],['markers/ready.txt','READY']]
reasons=[
'春季项目归档目录直接给出且未更新。','纯文本格式与日期标题两项都直接给出。','编辑器 Vim 与浏览器 Firefox 的实体绑定一致。','目录和文件名明确，按目录连接得到完整相对路径。','同轮口误被明确撤回，kitty 为最终值。','最后实测 2.0.1 和最初 2.0 是不同时间目标，均有证据。','我与小林分别绑定 Kate 和 Emacs；他指小林不改变归属。','问题仅指设备甲，aarch64 来自明确的命令结果。','昵称不足确定架构，未知状态正确。','两条等效且未决说明无优先级，冲突而非采用最新值。','目标新路径和模板正确，但禁写旧位置/同事位置未编译为动作限制；两种表述对此强度不一。','代号请求删除且否定句也不得披露；日记位置和模板明确保留。',
'自定义截图组合键明确，假期后未变。','离线手册对应入门索引书签，无其他竞争实体。','每日备份只是撤销的提议，实际仍每周一次。','山谷 Rust 与海风 Python 区分清楚。','阅读北京攻略不能推出居住城市，明确未给出。','两行清单及末尾换行明确，复用至指定路径。','小字易串行是大字号的原因，两种表述等义。','同一地下实验室不能联网，离线步骤约束延续。','长期保留原片且不得自动删除明确。','周三下午为固定安排，不把其他时间推断为可用。','距离毫米、温度摄氏度的配对明确。','本地数据的原因是断网可展示，数据量被明确排除。','遥控器归蓝色收纳袋、转接头归灰盒；蓝色袋子是同一物的自然简称。','仅取第二次实验，权限不足不与首次空输入混淆。','旧资料显式等同青箱，其位置柜子第二层。','小周接任且明示沿用小何目录，复制有明确依据。','第二步在大小与记录之间，为核对摘要。','它被明确绑定绿的实验记录本，编号 LAB-09。','12MB 符合共享目录条件且后文已确认 exchange。','仅问封存第一版秒，不错误采用第二版毫秒。','只改份数至三，双面未变。','深色试用后恢复初始浅色基线，最终状态明确。','临时中午例外已经结束，晚上恢复；文字今天为叙事用语，不要求计算日历日期。','负责人裁定西厅并撤销东厅，冲突已解除。','同一输出截图纠正抄录，aarch64 不是更换设备推断。','预览通道只是未来待批提议，当前稳定通道明确保留。','显示名连续更新至青林，P-17 保持不变。','客体桌面 Xfce 与宿主 UKUI 清晰区分。','两位小陈以岗位消歧，设计岗 Inkscape。','区分大小写的路径甲为 work/Map，不能折叠为 work/map。','同一操作者不等同归属，我的台式机 x86_64。','松林项目配置两空格明确优先于全局四空格。','SVG 是可编辑源稿，PNG 是预览，两个目标均有依据。','KARE 全名和 apt 包管理用途均在原文，不需外部事实。','只有备份计划且没有执行证据，完成状态未知而不是 false。','新机器未测架构，不沿用旧设备 loongarch64。','只知 KARE 安装，不能推出包管理器。','联系人代号明确删除，中文偏好明确保留。','同级负责人上午/下午未裁决，无后到消息优先。','目录已知但文件名未知且无默认名，完整路径不可确定。','样例医生不代表用户职业，未知状态正确。','B 显式复用 A 的逐字模板，B 路径独立明确。','仅复述失败处理流程、不实际操作文件，gold 不要求动作正确。','按问题单类型选择现象/复现模板，不能拿会议模板。','固定待核验标记与末尾换行明确，不能宣称完成。','批次目录和文件名组合，逐字空模板且不得填结果。','只更新模板加入异常行，原位置保留且每行末尾换行。','READY 精确五字节，不加换行、引号或解释。']
assert len(answers)==len(reasons)==len(sources)==60
all_files=['candidates.jsonl','dev.jsonl','public.jsonl','paired-2048.jsonl','paired-8192.jsonl','paired-32768.jsonl']
loaded={f:rows(D/f) for f in all_files}
canon={(e['episode_id'],e['variant_id']):e for e in loaded['candidates.jsonl']}
reports=[]
for i,s in enumerate(sources):
 failures=[]; variants=[]
 selected=[(f,n,e) for f,es in loaded.items() if f!='public.jsonl' for n,e in enumerate(es,1) if e['story_id']==s['story_id']]
 for f,n,e in selected:
  g=e['golds'][0]; obs={o['observation_id']:o for o in e['observations']}; ev=[obs[v['observation_id']] for v in g['evidence']]
  state='conflict' if i in [9,50] else 'forgotten' if i in [11,49] else 'unknown'
  expect=[(t['key'],'answer' if v is not None else state,v) for t,v in zip(s['targets'],answers[i])]
  checks={
   'gold_matches_independent_reading':[(v['name'],v['state'],v['value']) for v in g['slots']]==expect,
   'query_is_same_source_wording':any(e['probes'][0]['query']==s['queries'][w] and [o['text'] for o in ev]==[u[w] for u in s['utterances']] for w in [0,1]),
   'noise_only_non_task_filler':all(re.fullmatch(r'(?:讨论区今天有一条读书交流帖。|窗外的树影慢慢移动。|休息时可以看看远处。|这是一条与工作配置无关的闲聊。)*(?:讨论区今天有一条读书交流帖。|窗外的树影慢慢移动。|休息时可以看看远处。|这是一条与工作配置无关的闲聊。)?',o['text']) is not None or any(o['text'].endswith(t[:n]) and re.fullmatch(r'(?:讨论区今天有一条读书交流帖。|窗外的树影慢慢移动。|休息时可以看看远处。|这是一条与工作配置无关的闲聊。)*',o['text'][:-n]) is not None for t in ['讨论区今天有一条读书交流帖。','窗外的树影慢慢移动。','休息时可以看看远处。','这是一条与工作配置无关的闲聊。'] for n in range(1,len(t))) for o in e['observations'] if o['observation_id'] not in {v['observation_id'] for v in g['evidence']}),
   'core_evidence_matches_one_whole_variant':any([o['text'] for o in ev]==[u[w] for u in s['utterances']] for w in [0,1]),
   'probe_after_all_observations':all(o['observed_at']<e['probes'][0]['observed_at'] for o in e['observations']),
   'two_sessions_and_80_observations':len(e['session_ids'])==2 and len(e['observations'])==80,
  }
  if s.get('file_task'):
   values=dict(zip([t['key'] for t in s['targets']],answers[i])); a=g['expected_actions']
   checks['file_path_and_exact_content_hash']=len(a)==1 and a[0]['path']==values['output_path'] and a[0]['sha256']==hashlib.sha256(values['template'].encode()).hexdigest() and a[0]['operation']=='create'
  else: checks['no_unrequested_file_action']=not g['expected_actions']
  if i in [11,49]:
   policies=g['forget_policies'];checks['literal_forget_and_retained_preference']=len(policies)==1 and policies[0]['values']==[s['forget_policies'][0]['value']] and policies[0]['retained_text']==answers[i][-1]
  if f.startswith('paired-'):checks['paired_gold_invariant']=g==canon[(e['episode_id'],e['variant_id'])]['golds'][0]
  for name,ok in checks.items():
   if not ok:failures.append({'file':f,'line':n,'check':name})
  variants.append({'file':f,'line':n,'variant_id':e['variant_id'],'checks':checks,'evidence':[{'observation_id':o['observation_id'],'text':o['text']} for o in ev]})
 main_variants=[v for v in variants if v['file']=='candidates.jsonl'];assert len(main_variants)==2
 reports.append({'story_id':s['story_id'],'source_line':i+1,'source_file':'data/v0.2/sources.jsonl','template_id':s['template_id'],'split':s['split'],'decision':'rejected' if i==10 or failures else 'accepted','repair_required':i==10 or bool(failures),'reason':reasons[i],'source_sha256':hashlib.sha256((json.dumps(s,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()).hexdigest(),'reviewer_type':'independent_ai','reviewer':'/root/independent_dataset_review','source_wordings_reviewed':[0,1],'expected_answers_from_reading':answers[i],'generated_checks':variants,'automatic_failures':failures,'review_exposure':{'reviewed_candidate_content':True,'kind':'dataset_semantic_audit','no_model_benchmark_or_training_run':True}})
public_ok=all({k:v for k,v in canon[(p['episode_id'],p['variant_id'])].items() if k in ('episode_id','observations','probes','session_ids','variant_id')}==p for p in loaded['public.jsonl'])
out={'schema_version':'independent-ai-review-1','reviewed_at':datetime.now(timezone.utc).isoformat(),'reviewer_type':'independent_ai','reviewer':'/root/independent_dataset_review','is_human_review':False,'scope':'60 original sources, both wordings, 120 candidate variants, 24 dev copies, 72 paired variants; public projection consistency','method':'Independent semantic reading plus hand-authored expected values; no use of data_v2.truth or generate for expected answers. Automated checks complement and do not replace semantic reading.','source_file_hashes':{f:hashlib.sha256((D/f).read_bytes()).hexdigest() for f in ['sources.jsonl']+all_files},'public_projection_matches':public_ok,'summary':{'stories':60,'accepted':sum(r['decision']=='accepted' for r in reports),'needs_repair':sum(r['decision']=='rejected' for r in reports),'automatic_failures':sum(len(r['automatic_failures']) for r in reports)},'limitations':['AI audit is not human review and makes no copyright/license signature.','All candidate stories exposed to this reviewer for audit; no unseen independent holdout or ranking claim.','Gold completeness of Qinghe is rejected; original source is untouched.','Simple synthetic statements and repetitive filler limit ecological validity; nominal one-month timestamps do not prove real elapsed-time memory.','Natural-language paraphrases require semantic adjudication; exact structured string scoring alone cannot establish correctness.','No benchmark model calls, remote execution, training, or tuning were performed.','Both AI reviewers have inspected private candidate content; do not send gold or review files to tested products.','dev_cancel_proposal and future_proposal_not_applied share proposal-versus-active logic; dev_reusable_checklist and test file-template tasks share exact template reuse. Different template_id does not prove independent generalization.'],'records':reports,'reviewer_identity':{'id':'/root/independent_dataset_review','model':'unreported','kind':'ai'},'sources_sha256':hashlib.sha256((json.dumps(sources,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()).hexdigest(),'reviewer_exposed_story_ids':[s['story_id'] for s in sources],'unseen_holdout_claim':False}
(ROOT/'docs/integrations/ai-review-20261015/independent-review.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(out['summary']));print('public projection:',public_ok)
