"""Structural/obligation validation. Does not determine mathematical truth."""
import argparse,json
from pathlib import Path

LABELS={'indispensable','removable','implied','joint','type_constraint','unresolved','statement_issue'}
EVIDENCE={'candidate','mathematical_argument','partial_computation','ai_reviewed','human_reviewed','formal_checked','unresolved'}
def validate(result):
    errors=[]
    if not isinstance(result,dict): return ['output must be a JSON object']
    if 'interventions' in result:
        for key in ('theorem','interventions','dependency_map','remaining_work'):
            if key not in result: errors.append('missing '+key)
        if not isinstance(result.get('interventions'),list) or not result['interventions']: errors.append('interventions must be nonempty array')
        else:
            seen=set()
            for i,r in enumerate(result['interventions']):
                errors.extend(f'intervention {i}: '+e for e in validate(r))
                if isinstance(r,dict):
                    tid=r.get('task_id')
                    if isinstance(tid,str):
                        if tid in seen: errors.append('duplicate task_id '+tid)
                        seen.add(tid)
        return errors
    required=('task_id','hypotheses','intervention','judgment','witness','retained_checks','replacement_checks','target_failure','argument','evidence','dependencies','uncertainties','next_steps','cost')
    for key in required:
        if key not in result: errors.append('missing '+key)
    if not isinstance(result.get('task_id'),str) or not result['task_id'].strip(): errors.append('task_id must be nonempty string')
    label=result.get('judgment')
    if label not in LABELS: errors.append('unknown judgment')
    hypotheses=result.get('hypotheses',[]); ids=[]
    if not isinstance(hypotheses,list): errors.append('hypotheses must be array')
    else:
        for h in hypotheses:
            if not isinstance(h,dict) or not isinstance(h.get('id'),str) or not isinstance(h.get('text'),str): errors.append('invalid hypothesis')
            else: ids.append(h['id'])
        if len(set(ids))!=len(ids): errors.append('duplicate hypothesis IDs')
    intervention=result.get('intervention',{})
    if not isinstance(intervention,dict): errors.append('intervention must be object'); intervention={}
    removed=intervention.get('removed',[])
    if not isinstance(removed,list) or not all(isinstance(x,str) for x in removed): errors.append('removed must be string array'); removed=[]
    if len(set(removed))!=len(removed) or not set(removed)<=set(ids): errors.append('invalid removed IDs')
    checks=result.get('retained_checks',[])
    if not isinstance(checks,list): errors.append('retained_checks must be array'); checks=[]
    checked=[]
    for c in checks:
        if not isinstance(c,dict) or not isinstance(c.get('id'),str) or not isinstance(c.get('argument'),str) or not c['argument'].strip(): errors.append('invalid retained check')
        else: checked.append(c['id'])
    if len(set(checked))!=len(checked): errors.append('duplicate retained checks')
    if label in {'indispensable','joint','removable','implied'} and set(checked)!=set(ids)-set(removed): errors.append('retained checks must cover every retained hypothesis exactly')
    replacement=intervention.get('replacement'); replchecks=result.get('replacement_checks',[])
    if not isinstance(replchecks,list): errors.append('replacement_checks must be array'); replchecks=[]
    if replacement is not None:
        if not isinstance(replacement,dict) or not isinstance(replacement.get('id'),str) or not isinstance(replacement.get('text'),str): errors.append('invalid replacement')
        elif label in {'indispensable','joint','removable','implied'}:
            if len(replchecks)!=1 or not isinstance(replchecks[0],dict) or replchecks[0].get('id')!=replacement['id'] or not replchecks[0].get('argument'): errors.append('missing replacement obligation')
    elif replchecks: errors.append('replacement checks supplied without replacement')
    if label in {'indispensable','joint','statement_issue'}:
        if not isinstance(result.get('witness'),str) or not result['witness'].strip(): errors.append('counterexample requires explicit witness')
        target=result.get('target_failure')
        if not isinstance(target,dict) or not target.get('id') or not target.get('argument'): errors.append('counterexample requires target_failure argument')
    if not isinstance(result.get('argument'),str) or not result['argument'].strip(): errors.append('argument must be nonempty')
    for field in ('evidence','dependencies','uncertainties','next_steps'):
        if not isinstance(result.get(field),list): errors.append(field+' must be array')
    if label=='unresolved' and not result.get('uncertainties'): errors.append('unresolved requires uncertainty explanation')
    if isinstance(result.get('evidence'),list):
        for e in result['evidence']:
            if not isinstance(e,dict) or e.get('kind') not in EVIDENCE or not e.get('scope'): errors.append('invalid evidence entry')
            elif e['kind'] in {'ai_reviewed','human_reviewed','formal_checked'} and not e.get('artifact'): errors.append('review or proof artifact required')
    cost=result.get('cost')
    if not isinstance(cost,dict): errors.append('cost must be object')
    else:
        import math
        for k in ('elapsed_seconds','model_calls','tool_calls','usd'):
            v=cost.get(k)
            if v is not None and (type(v) not in (int,float) or not math.isfinite(v) or v<0): errors.append('invalid cost '+k)
    return errors

def main():
    p=argparse.ArgumentParser(); p.add_argument('input'); p.add_argument('--out',required=True); a=p.parse_args()
    try: errors=validate(json.loads(Path(a.input).read_text(encoding='utf-8')))
    except (OSError,ValueError) as e: errors=[str(e)]
    result={'status':'pass' if not errors else 'fail','errors':errors,'scope':'Output structure and obligation completeness only, not mathematical truth.'}
    out=Path(a.out); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False)); return 1 if errors else 0
if __name__=='__main__': raise SystemExit(main())
