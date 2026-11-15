"""Auditable evaluation controller. No LLM dependency; no automatic general math grading."""
import argparse
import hashlib
import json
import math
import random
import statistics
from pathlib import Path

ROOT=Path(__file__).resolve().parent
SPLITS=('development','validation','heldout')
LABELS=('indispensable','removable','implied','joint','type_constraint','unresolved','statement_issue')

def read(path): return json.loads(Path(path).read_text(encoding='utf-8'))
def rows(path):
    return [json.loads(s) for s in Path(path).read_text(encoding='utf-8').splitlines() if s.strip()]
def save(path,obj):
    p=Path(path); p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def load(split): return rows(ROOT/split/'cases.jsonl')
def unique(items,key):
    result={}
    for x in items:
        if x[key] in result: raise ValueError('duplicate '+key+': '+str(x[key]))
        result[x[key]]=x
    return result
def digest(obj): return hashlib.sha256(json.dumps(obj,ensure_ascii=False,sort_keys=True).encode()).hexdigest()

def validate():
    allrows=sum((load(s) for s in SPLITS),[]); unique(allrows,'task_id'); families={}; errors=[]
    for r in allrows:
        old=families.setdefault(r['family_id'],r['split'])
        if old!=r['split']: errors.append('family leak '+r['family_id'])
        ids={h['id'] for h in r['hypotheses']}
        removed=set(r['intervention']['removed'])
        if not removed<=ids: errors.append('unknown removed hypothesis '+r['task_id'])
        if set(r['reference']['retained_checks'])!=ids-removed: errors.append('retained obligations mismatch '+r['task_id'])
        replacement=r['intervention'].get('replacement')
        if replacement and set(r['reference'].get('replacement_checks',{}))!={replacement['id']}: errors.append('replacement obligation mismatch '+r['task_id'])
        if r['reference']['judgment'] not in LABELS: errors.append('invalid label '+r['task_id'])
        if r['review']['status']!='approved' and r['gold_eligible']: errors.append('unreviewed gold '+r['task_id'])
    return {'status':'pass' if not errors else 'fail','tasks':len(allrows),'families':len(families),'splits':{s:len(load(s)) for s in SPLITS},'pending_review':sum(r['review']['status']!='approved' for r in allrows),'errors':errors,'scope':'data consistency only, not mathematical truth'}

def prompt(r,arm):
    base={k:r[k] for k in ['task_id','subject','statement','hypotheses','intervention','conclusions']}
    base['ambient']=r.get('ambient','按定理的明确对象约定')
    prefixes={
      'direct_model':'完成以下数学任务，输出一个JSON对象。',
      'fixed_prompt':'逐项核对保留假设与结论。找不到反例时说明未知，不宣称冗余。输出一个JSON对象。',
      'full_skill':'使用 $condition-archaeologist 完成以下任务，按Skill的机器输出规范输出一个JSON对象。',
      'retrieval_only':'参考控制者提供的已审阅开发案例完成任务，不使用Skill策略库。输出一个JSON对象。',
      'without_strategies':'使用控制者提供的无策略库Skill副本完成任务，输出一个JSON对象。',
      'without_verification':'使用控制者提供的移除验证流程Skill副本完成任务，输出一个JSON对象。',
      'cases_only_update':'使用仅扩充案例的冻结版本完成任务，输出一个JSON对象。',
      'strategy_update':'使用包含策略更新的冻结版本完成任务，输出一个JSON对象。'}
    return {'task_id':r['task_id'],'prompt':prefixes[arm]+'\n'+json.dumps(base,ensure_ascii=False),'task_digest':digest(base)}

def make_review_tasks(cases,predictions):
    pp=unique(predictions,'task_id'); out=[]
    for r in cases:
        pred=pp.get(r['task_id'])
        out.append({'task_id':r['task_id'],'prediction_digest':digest(pred),'reviewer':None,'reviewed_at':None,'independent':None,'judgment_correct':None,'witness_claimed':None,'witness_valid':None,'hypothesis_matches':None,'prediction_hypothesis_count':None,'all_retained_valid':None,'conclusion_refuted':None,'argument_valid':None,'intervention_valid':None,'evidence_honest':None,'dependency_correct':None,'notes':'请逐义务审阅；未提供预测记失败；替代反例按数学有效性判定，不按参考字面匹配。'})
    return out

def wilson(success,n):
    if not n: return None
    z=1.95996398454; p=success/n; d=1+z*z/n
    center=(p+z*z/(2*n))/d; half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return [max(0,center-half),min(1,center+half)]

def score(cases,predictions,adjudications,provisional=False):
    if not provisional and any(r['review']['status']!='approved' or not r['gold_eligible'] or not r['review'].get('reviewer') or not r['review'].get('record') for r in cases):
        raise ValueError('正式评分拒绝：参考答案尚未逐题独立审阅。可用 --provisional 生成明确标注的内部诊断。')
    pp=unique(predictions,'task_id'); aa=unique(adjudications,'task_id'); validids={r['task_id'] for r in cases}
    if set(pp)-validids or set(aa)-validids: raise ValueError('unknown task IDs')
    per=[]
    required=('judgment_correct','witness_claimed','witness_valid','all_retained_valid','conclusion_refuted','argument_valid','intervention_valid','evidence_honest','dependency_correct')
    for r in cases:
        tid=r['task_id']; pred=pp.get(tid); a=aa.get(tid)
        if a is None or not a.get('reviewer') or not a.get('reviewed_at') or a.get('independent') is not True:
            raise ValueError('missing independent adjudication '+tid)
        if a.get('prediction_digest')!=digest(pred): raise ValueError('prediction changed after review '+tid)
        if any(type(a.get(k))!=bool for k in required): raise ValueError('incomplete adjudication '+tid)
        matches=a.get('hypothesis_matches'); predicted_count=a.get('prediction_hypothesis_count')
        if type(matches)!=int or type(predicted_count)!=int or not 0<=matches<=min(len(r['hypotheses']),predicted_count): raise ValueError('invalid hypothesis counts '+tid)
        label=pred.get('judgment','unresolved') if pred else 'unresolved'
        if label not in LABELS: raise ValueError('invalid predicted label '+tid)
        has_claim=a['witness_claimed']
        if pred is None and (has_claim or a['witness_valid'] or matches or predicted_count): raise ValueError('missing prediction cannot contain mathematical claims '+tid)
        if label in ('indispensable','joint') and pred and not has_claim: raise ValueError('counterexample judgment must count witness claim '+tid)
        if a['witness_valid'] and not (has_claim and a['all_retained_valid'] and a['conclusion_refuted'] and a['intervention_valid']): raise ValueError('inconsistent witness review '+tid)
        reference=r['reference']['judgment']; resolved=bool(pred) and label!='unresolved'
        correct=resolved and a['judgment_correct'] and label==reference and a['argument_valid'] and a['intervention_valid'] and a['evidence_honest']
        if label in ('indispensable','joint'): correct=correct and a['witness_valid']
        if len(r['intervention']['removed'])>1: correct=correct and a['dependency_correct']
        cost=pred.get('cost',{}) if pred else {}
        for k in ['elapsed_seconds','model_calls','tool_calls','usd']:
            value=cost.get(k)
            if value is not None and (type(value) not in (int,float) or not math.isfinite(value) or value<0): raise ValueError('invalid cost '+tid)
        per.append({'task_id':tid,'family_id':r['family_id'],'subject':r['subject'],'reference':reference,'predicted':label,'resolved':resolved,'success':bool(correct),'witness_claimed':has_claim,'witness_valid':a['witness_valid'],'reference_has_counterexample':reference in ('indispensable','joint'),'discovery':a['witness_valid'] and reference in ('indispensable','joint'),'joint_task':len(r['intervention']['removed'])>1,'evidence_honest':a['evidence_honest'],'matches':matches,'hypotheses':len(r['hypotheses']),'predicted_hypotheses':predicted_count,'cost':cost})
    n=len(per); claims=sum(x['witness_claimed'] for x in per); valids=sum(x['witness_valid'] for x in per); reference_ce=sum(x['reference_has_counterexample'] for x in per); successes=sum(x['success'] for x in per); resolved=sum(x['resolved'] for x in per)
    f1={}
    for label in sorted({x['reference'] for x in per if x['reference']!='unresolved'}):
        tp=sum(x['success'] and x['reference']==label and x['predicted']==label for x in per)
        fp=sum(x['predicted']==label and not (x['success'] and x['reference']==label) for x in per)
        fn=sum(x['reference']==label and not x['success'] for x in per)
        f1[label]=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None
    fam={}
    for x in per: fam.setdefault(x['family_id'],[]).append(x['success'])
    def ratio(a,b): return a/b if b else None
    metrics={'tasks':n,'success_rate':ratio(successes,n),'witness_precision':ratio(valids,claims),'witness_precision_n':claims,'witness_precision_wilson95':wilson(valids,claims),'discovery_rate':ratio(sum(x['discovery'] for x in per),reference_ce),'discovery_n':reference_ce,'coverage':ratio(resolved,n),'selective_risk':ratio(sum(x['resolved'] and not x['success'] for x in per),resolved),'evidence_honesty':ratio(sum(x['evidence_honest'] for x in per),n),'hypothesis_precision':ratio(sum(x['matches'] for x in per),sum(x['predicted_hypotheses'] for x in per)),'hypothesis_recall':ratio(sum(x['matches'] for x in per),sum(x['hypotheses'] for x in per)),'verified_macro_f1':statistics.mean(f1.values()) if f1 else None,'per_class_f1':f1,'family_complete_success':ratio(sum(all(v) for v in fam.values()),len(fam)),'joint_success':ratio(sum(x['success'] for x in per if x['joint_task']),sum(x['joint_task'] for x in per)),'subjects':{sub:{'tasks':sum(x['subject']==sub for x in per),'success_rate':statistics.mean(x['success'] for x in per if x['subject']==sub)} for sub in sorted({x['subject'] for x in per})},'heldout_success':None,'cost':{k:{'observed_n':sum(x['cost'].get(k) is not None for x in per),'mean':statistics.mean(x['cost'][k] for x in per if x['cost'].get(k) is not None) if any(x['cost'].get(k) is not None for x in per) else None} for k in ['elapsed_seconds','model_calls','tool_calls','usd']}}
    splits={r['split'] for r in cases}
    if splits=={'heldout'}: metrics['heldout_success']=metrics['success_rate']
    return {'status':'provisional_internal' if provisional else 'reviewed_score','dataset_digest':digest(cases),'prediction_digest':digest(predictions),'splits':sorted(splits),'metrics':metrics,'per_task':per,'uncertainty_note':'Wilson only descriptive for claim counts; dependent tasks require family clustered comparison. No claim of statistical sufficiency.'}

def compare(base,candidate,samples=2000):
    if base['dataset_digest']!=candidate['dataset_digest']: raise ValueError('different datasets')
    b=unique(base['per_task'],'task_id'); c=unique(candidate['per_task'],'task_id')
    if set(b)!=set(c): raise ValueError('different tasks')
    groups={}
    for tid,x in b.items():
        if x['family_id']!=c[tid]['family_id']: raise ValueError('family mismatch')
        groups.setdefault(x['family_id'],[]).append(int(c[tid]['success'])-int(x['success']))
    if not groups: raise ValueError('empty comparison')
    if samples<100: raise ValueError('at least 100 bootstrap samples required')
    rng=random.Random(20261102); families=list(groups.values()); boot=[]
    for _ in range(samples):
        values=sum((rng.choice(families) for i in families),[]); boot.append(statistics.mean(values))
    boot.sort(); interval=[boot[int(.025*(samples-1))],boot[int(.975*(samples-1))]]
    return {'paired_success_gain':statistics.mean(v for g in families for v in g),'family_count':len(groups),'bootstrap_samples':samples,'family_cluster_bootstrap95':interval,'seed':20261102}

def gate(base,candidate,policy):
    if any(r.get('status')=='ai_reviewed_internal' for r in (base,candidate)):
        return {'decision':'reject_or_collect_more_evidence',
                'reasons':['AI internal scores cannot satisfy the independent-review RSI gate'],
                'comparison':None,'automatic_promotion':False}
    comparison=compare(base,candidate,policy['min_bootstrap_samples']); reasons=[]
    for r in (base,candidate):
        if r['status']!='reviewed_score': reasons.append('scores not independently reviewed')
        if r['splits']!=['validation']: reasons.append('requires validation split, never heldout')
        if not r.get('config_digest'): reasons.append('missing configuration digest')
    if base.get('config_digest')!=candidate.get('config_digest'): reasons.append('unequal model/resources configuration')
    if comparison['paired_success_gain']<policy['min_success_gain']: reasons.append('insufficient gain')
    if comparison['family_count']<policy['min_family_count']: reasons.append('insufficient independent families')
    if policy['require_positive_ci'] and comparison['family_cluster_bootstrap95'][0]<=0: reasons.append('gain interval not positive')
    bp=base['metrics']['witness_precision']; cp=candidate['metrics']['witness_precision']
    if bp is None or cp is None: reasons.append('counterexample precision unmeasured')
    elif cp<bp-policy['max_precision_drop']: reasons.append('counterexample precision regressed')
    if candidate['metrics']['evidence_honesty']!=1: reasons.append('evidence overclaim detected')
    if not base.get('skill_tree_hash') or not candidate.get('skill_tree_hash'): reasons.append('missing frozen skill hashes')
    return {'decision':'reject_or_collect_more_evidence' if reasons else 'eligible_for_human_acceptance','reasons':reasons,'comparison':comparison,'baseline_tree_hash':base.get('skill_tree_hash'),'candidate_tree_hash':candidate.get('skill_tree_hash'),'automatic_promotion':False}

def main():
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest='cmd',required=True)
    q=sub.add_parser('validate'); q.add_argument('--out',required=True)
    q=sub.add_parser('export'); q.add_argument('--split',choices=SPLITS,required=True); q.add_argument('--arm',default='full_skill',choices=['direct_model','fixed_prompt','retrieval_only','full_skill','without_strategies','without_verification','cases_only_update','strategy_update']); q.add_argument('--out',required=True)
    q=sub.add_parser('prepare-review'); q.add_argument('--split',choices=SPLITS,required=True); q.add_argument('--predictions',required=True); q.add_argument('--out',required=True)
    q=sub.add_parser('score'); q.add_argument('--split',choices=SPLITS,required=True); q.add_argument('--predictions',required=True); q.add_argument('--reviews',required=True); q.add_argument('--config',required=True); q.add_argument('--skill-tree'); q.add_argument('--provisional',action='store_true'); q.add_argument('--out',required=True)
    for name in ('compare','gate'):
        q=sub.add_parser(name); q.add_argument('--baseline',required=True); q.add_argument('--candidate',required=True); q.add_argument('--out',required=True)
    a=p.parse_args()
    try:
        if a.cmd=='validate': result=validate()
        elif a.cmd=='export': result=[prompt(r,a.arm) for r in load(a.split)]
        elif a.cmd=='prepare-review': result=make_review_tasks(load(a.split),rows(a.predictions))
        elif a.cmd=='score':
            config=read(a.config)
            if any(config.get(k) is None for k in ('model','model_version','permissions','per_task_budget','retrieval_corpus_hash','sampling_settings')): raise ValueError('incomplete actual run configuration')
            result=score(load(a.split),rows(a.predictions),read(a.reviews),a.provisional)
            result['config_digest']=digest(config)
            if a.skill_tree:
                from rsi import tree_hash
                result['skill_tree_hash']=tree_hash(Path(a.skill_tree).resolve())
        elif a.cmd=='compare': result=compare(read(a.baseline),read(a.candidate))
        else: result=gate(read(a.baseline),read(a.candidate),read(ROOT/'rsi-policy.json'))
        save(a.out,result); print(json.dumps({'status':'written','output':a.out},ensure_ascii=False)); return 0
    except (ValueError,KeyError,TypeError,OSError) as e:
        print(json.dumps({'status':'blocked','reason':str(e)},ensure_ascii=False)); return 2

if __name__=='__main__': raise SystemExit(main())
