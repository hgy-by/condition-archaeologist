"""Score explicit, source-bound AI reviews of full theorems and edge tasks.

The script validates review completeness and aggregates the reviewing AI's
mathematical findings. It cannot decide arbitrary mathematical truth itself.
"""
import argparse
import hashlib
from pathlib import Path

import lab
import final_experiment


def finding(value,name):
    if not isinstance(value,dict) or type(value.get('pass')) is not bool or not value.get('reason'):
        raise ValueError('Concrete review finding required: '+name)
    return value['pass']


def score(run,reviews):
    actual={(j['task_id'],j['arm']):(j,r,paths) for j,r,paths in final_experiment.records(run)}
    supplied={}
    for review in reviews:
        key=(review['task_id'],review['arm'])
        if key in supplied or key not in actual:raise ValueError('Duplicate or unknown review')
        supplied[key]=review
    if set(supplied)!=set(actual):raise ValueError('Every planned task needs review or a no-answer finding')
    rows=[]
    for key,(job,record,paths) in actual.items():
        review=supplied[key]
        if review.get('reviewer_type')!='ai' or not review.get('reviewer') or not review.get('reviewed_at'):
            raise ValueError('AI reviewer provenance required')
        if review.get('independent_human') is not False:raise ValueError('Cannot impersonate independent human review')
        if review.get('source_digest')!=lab.digest(record):raise ValueError('Source changed since review')
        if review.get('task_digest')!=job['task_digest']:raise ValueError('Task changed since review')
        pred=(record or {}).get('prediction')
        if pred is None:
            has_text=bool(record and record.get('answer'))
            expected='invalid_output' if has_text else 'no_answer'
            if review.get('status')!=expected or not review.get('runtime_reason'):
                raise ValueError('Unusable answer needs an explicit runtime/format finding')
            rows.append({'task_id':key[0],'arm':key[1],'kind':job['kind'],'family_id':review['family_id'],
                'answer':has_text,'math_success':False,'protocol_success':False,'interventions':[],
                'hypothesis_matches':0,'hypothesis_expected':review.get('hypothesis_expected',0),
                'hypothesis_reported':0,'uncertainty_honest':None,'runtime_failure':not has_text,
                'output_failure':has_text})
            continue
        if review.get('prediction_digest')!=lab.digest(pred):raise ValueError('Prediction changed since review')
        if review.get('status')!='reviewed':raise ValueError('Answer has not been reviewed')
        common=('objects','mathematical_correctness','uncertainty_honesty')
        checks={name:finding(review.get(name),name) for name in common}
        interventions=[]
        if job['kind']=='uncertainty':
            checks['ambiguity_handling']=finding(review.get('ambiguity_handling'),'ambiguity handling')
            if review.get('interventions'):raise ValueError('Uncertainty request has no forced intervention rubric')
        else:
            outputs=pred.get('interventions',[]) if job['kind']=='full_theorem' else [pred]
            ir=review.get('interventions')
            if not isinstance(ir,list) or len(ir)!=len(outputs):raise ValueError('Every actual intervention must be mathematically reviewed')
            if job['kind']=='full_theorem':
                for name in ('hypothesis_extraction','conclusion_extraction','single_condition_coverage','dependency_reporting','remaining_work'):
                    checks[name]=finding(review.get(name),name)
                for name in ('hypothesis_expected','hypothesis_matches','hypothesis_reported'):
                    if type(review.get(name)) is not int or review[name]<0:raise ValueError('Raw-text hypothesis counts required')
                if review['hypothesis_matches']>min(review['hypothesis_expected'],review['hypothesis_reported']):raise ValueError('Invalid extraction counts')
            for index,(output,item) in enumerate(zip(outputs,ir)):
                if item.get('index')!=index or item.get('output_digest')!=lab.digest(output):raise ValueError('Intervention identity changed')
                ids={h['id'] for h in output['hypotheses']}
                removed=set(output['intervention']['removed'])
                if set(item.get('retained',{}))!=ids-removed:raise ValueError('Missing retained mathematical review')
                replacement=output['intervention'].get('replacement')
                rid={replacement['id']} if replacement else set()
                if set(item.get('replacement',{}))!=rid:raise ValueError('Missing replacement mathematical review')
                valid=[finding(v,'retained '+k) for k,v in item['retained'].items()]
                valid += [finding(v,'replacement '+k) for k,v in item['replacement'].items()]
                valid += [finding(item.get(k),k) for k in ('judgment','argument','intervention')]
                label=output.get('judgment');claim=label in ('indispensable','joint','statement_issue')
                if claim:
                    valid.append(finding(item.get('target_falsity'),'target falsity'))
                    if set(item.get('deleted',{}))!=removed:raise ValueError('Missing deleted-condition review')
                    valid += [finding(v,'deleted '+k) for k,v in item['deleted'].items()]
                elif label in ('implied','removable'):
                    valid.append(finding(item.get('preservation_proof'),'preservation proof'))
                elif label in ('type_constraint','unresolved'):
                    valid.append(finding(item.get('definition_or_gap'),'definition or genuine gap'))
                else:raise ValueError('Invalid judgment')
                interventions.append({'index':index,'task_id':output.get('task_id'),'label':label,'removed_count':len(removed),
                    'success':all(valid),'witness_claimed':claim,'witness_valid':claim and all(valid)})
        math_success=all(checks.values()) and all(i['success'] for i in interventions)
        rows.append({'task_id':key[0],'arm':key[1],'kind':job['kind'],'family_id':review['family_id'],
            'answer':True,'math_success':math_success,'protocol_success':math_success and record.get('structure_errors')==[],
            'interventions':interventions,'hypothesis_matches':review.get('hypothesis_matches',0),
            'hypothesis_expected':review.get('hypothesis_expected',0),'hypothesis_reported':review.get('hypothesis_reported',0),
            'uncertainty_honest':checks['uncertainty_honesty'],'runtime_failure':False,
            'component_findings':checks,'limitations':review.get('limitations',[])})
    def frac(a,b):return {'numerator':a,'denominator':b,'rate':a/b if b else None}
    metrics={}
    for arm in final_experiment.ARMS:
        group=[r for r in rows if r['arm']==arm]
        full=[r for r in group if r['kind']=='full_theorem']
        ints=[i for r in group for i in r['interventions']]
        full_ints=[i for r in full for i in r['interventions']]
        judged_honesty=[r for r in group if r['uncertainty_honest'] is not None]
        metrics[arm]={'planned':len(group),'answers':sum(r['answer'] for r in group),
            'full_theorem_math_success':frac(sum(r['math_success'] for r in full),len(full)),
            'full_theorem_protocol_success':frac(sum(r['protocol_success'] for r in full),len(full)),
            'raw_text_hypothesis_recall':frac(sum(r['hypothesis_matches'] for r in full),sum(r['hypothesis_expected'] for r in full)),
            'raw_text_hypothesis_precision':frac(sum(r['hypothesis_matches'] for r in full),sum(r['hypothesis_reported'] for r in full)),
            'witness_precision':frac(sum(i['witness_valid'] for i in ints),sum(i['witness_claimed'] for i in ints)),
            'full_theorem_witness_precision':frac(sum(i['witness_valid'] for i in full_ints),sum(i['witness_claimed'] for i in full_ints)),
            'intervention_math_success':frac(sum(i['success'] for i in ints),len(ints)),
            'evidence_honesty':frac(sum(r['uncertainty_honest'] for r in judged_honesty),len(judged_honesty)),
            'by_judgment':{label:frac(sum(i['success'] for i in ints if i['label']==label),sum(i['label']==label for i in ints))
                for label in ('indispensable','implied','removable','joint','type_constraint','unresolved','statement_issue')}}
    return {'status':'ai_reviewed_internal','review_mode':'controller_AI_source_bound_review',
        'reviewer_blinded_to_arms':False,'independent_human':False,'run_config_digest':lab.digest(lab.read(run/'configuration.json')),
        'reviews_digest':lab.digest(reviews),'metrics':metrics,'per_task':rows,
        'scope':'Small internal release-acceptance tasks; not strict independent blind testing, a universal theorem solver, or automatic mathematical proof.'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True);p.add_argument('--reviews',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    try:
        result=score(a.run,lab.read(a.reviews));lab.save(a.out,result)
        print(__import__('json').dumps({'status':result['status'],'metrics':result['metrics']},ensure_ascii=False))
    except (ValueError,KeyError,TypeError,OSError) as error:
        print(__import__('json').dumps({'status':'blocked','reason':str(error)},ensure_ascii=False));return 2
    return 0


if __name__=='__main__':raise SystemExit(main())
