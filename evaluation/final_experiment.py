"""Bounded, frozen five-arm release experiment. No reference answers sent.

prepare/run/recover are separate. Calls use independent requests without tools,
history, seeds, or controller reference files. At most one explicit recovery is
allowed per job with NO answer. Wrong or malformed answers are never retried.
"""
import argparse
import concurrent.futures
import copy
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

import lab
import model_transport
import compare_models
import rsi

BASE=Path(__file__).resolve().parents[1]
CURRENT=BASE/'skill'
OLD=BASE/'reports/history-v1.0.0/installed-runtime-backup-v0.2.1'
FILES=compare_models.FILES
ARMS=('direct_model','old_skill','full_skill','without_strategies','without_verification')


def freeze_text(arm):
    if arm=='direct_model':return '',{}
    root=OLD if arm=='old_skill' else CURRENT
    sources={n:(root/n).read_text(encoding='utf-8') for n in FILES}
    if arm=='without_strategies':
        sources.pop('references/strategies.md')
        sources['SKILL.md']='\n'.join('2. 自行构造候选对象；本配置不加载策略库。' if line.startswith('2. 按相关条件读取') else line for line in sources['SKILL.md'].splitlines())
    if arm=='without_verification':
        sources.pop('references/verification.md')
        sources['SKILL.md']='\n'.join('3. 形成候选判断；本配置不加载专门的验证流程文档。' if line.startswith('3. 阅读 [证据和工具]') else line for line in sources['SKILL.md'].splitlines())
    text='\n\n'.join('FILE '+n+'\n'+content for n,content in sources.items())
    return text,{n:hashlib.sha256(content.encode()).hexdigest() for n,content in sources.items()}


def prepare(out):
    if out.exists():raise FileExistsError('Use a fresh directory')
    control=BASE/'evaluation/final_acceptance'
    schema=(CURRENT/'references/output-schema.md').read_text(encoding='utf-8')
    example=schema.split('机器评测输出为单个 JSON 对象：',1)[1].split('示意字段不是默认答案',1)[0]
    common=('完成数学任务，中文，仅输出JSON。不得调用工具、读取文件或声称人工/形式化核验。'
        '共同分类：indispensable=单删反例，removable=删后仍成立，implied=其余条件推出被删条件，'
        'joint=指定联合干预反例，type_constraint=必须先重写类型或定义，unresolved=证据不足，'
        'statement_issue=原命题有误。原命题错误应保留原假设、removed=[]并反驳原结论。'
        'removable/implied的witness与target_failure用null。所有保留/替代条件分别核验。'
        '每段论证尽量≤120汉字；未知成本null。单项格式如下，示例不是答案：\n'+example)
    jobs=[]
    def add(task,kind,arms):
        for arm in arms:
            frozen,hashes=freeze_text(arm)
            instructions=common
            if kind=='full_theorem':
                instructions+='\n整条定理：输出task_id、theorem（背景/假设/结论）、interventions（上述单项格式数组）、dependency_map、remaining_work。'
            elif kind=='uncertainty':
                instructions+='\n可能有歧义的名称请求：输出task_id、interpretation、missing_information、conditional_analysis、questions、limitations，不强行固定唯一命题。'
            if frozen:instructions+='\n按以下冻结Skill文本执行，不加载其他资源：\n'+frozen
            jobs.append({'task_id':task['task_id'],'arm':arm,'kind':kind,
                'task':compare_models.safe_task(task),'task_digest':lab.digest(task),
                'instructions':instructions,'skill_files_sha256':hashes})
    for task in lab.read(control/'full-theorem-inputs.json'):add(task,'full_theorem',ARMS)
    for task in lab.read(control/'challenge-inputs.json'):add(task,'intervention',['full_skill'])
    add(lab.read(control/'uncertainty-input.json'),'uncertainty',['full_skill'])
    assert len(jobs)==29
    config,endpoint,_=model_transport.settings()
    plan=lab.read(control/'acceptance-plan.json')
    if plan['candidate_runtime_hash']!=rsi.tree_hash(CURRENT):raise ValueError('Candidate changed since plan freeze')
    configuration={**plan['resources'],'model':config['model'],'provider_origin':urlsplit(endpoint).netloc,
        'max_transport_retries':0,'jobs_digest':lab.digest(jobs),'plan_digest':lab.digest(plan),
        'candidate_runtime_hash':rsi.tree_hash(CURRENT),'old_runtime_hash':rsi.tree_hash(OLD),
        'reference_answers_sent':False,'seeds_sent':False,'tools':False,'history':False,
        'repeats':1,'sampling_settings':'provider default except explicit effort/token budget; hidden routing unknown',
        'common_contract_sha256':hashlib.sha256(common.encode()).hexdigest(),
        'max_calls':58,'actual_usd':None}
    out.mkdir(parents=True)
    lab.save(out/'jobs.json',jobs);lab.save(out/'configuration.json',configuration)
    summarize(out)


def check_run(out):
    config=lab.read(out/'configuration.json');jobs=lab.read(out/'jobs.json')
    if config['jobs_digest']!=lab.digest(jobs):raise ValueError('Frozen jobs changed')
    current,endpoint,_=model_transport.settings()
    if current['model']!=config['model'] or urlsplit(endpoint).netloc!=config['provider_origin']:
        raise ValueError('Model/provider changed')
    if rsi.tree_hash(CURRENT)!=config['candidate_runtime_hash']:raise ValueError('Candidate changed during experiment')
    return config,jobs


def records(out):
    for job in lab.read(out/'jobs.json'):
        paths=sorted((out/'raw'/job['arm']/job['task_id']).glob('attempt-*.json'))
        yield job,lab.read(paths[-1]) if paths else None,paths


def summarize(out):
    rows=list(records(out));attempts=[lab.read(p) for _,_,files in rows for p in files]
    result={'planned':len(rows),'attempts':len(attempts),'answers':sum(bool(r and r.get('answer')) for _,r,_ in rows),
        'parsed':sum(r is not None and r.get('prediction') is not None for _,r,_ in rows),
        'structure_passes':sum(r is not None and r.get('structure_errors')==[] for _,r,_ in rows),
        'per_arm':{arm:{'planned':sum(j['arm']==arm for j,_,_ in rows),
            'answers':sum(j['arm']==arm and bool(r and r.get('answer')) for j,r,_ in rows),
            'structure_passes':sum(j['arm']==arm and bool(r is not None and r.get('structure_errors')==[]) for j,r,_ in rows)} for arm in ARMS},
        'usage_reported':{k:sum((r.get('usage') or {}).get(k,0) or 0 for r in attempts) for k in ('input_tokens','output_tokens','total_tokens')},
        'usd':None,'math_review':'AI review required, not inferred from structure',
        'actual_models':sorted({r['actual_model'] for r in attempts if r.get('actual_model')})}
    lab.save(out/'run-summary.json',result)
    return result


def run(out,only=None):
    config,jobs=check_run(out)
    if only is not None:jobs=[j for j in jobs if (j['task_id']+':'+j['arm'])==only]
    with concurrent.futures.ThreadPoolExecutor(max_workers=config['concurrency']) as pool:
        futures=[pool.submit(compare_models.call,j,out,config) for j in jobs]
        for future in concurrent.futures.as_completed(futures):future.result()
    print(json.dumps(summarize(out),ensure_ascii=False),flush=True)


def recover(out):
    config,_=check_run(out);selected=[]
    for job,record,paths in records(out):
        if record is None or len(paths)!=1 or record.get('answer') or record.get('prediction') is not None:continue
        if compare_models.recoverable(record) or record.get('http_status') is None:
            selected.append(job)
    lab.save(out/'explicit-no-answer-recovery.json',{'policy':'One identical-payload recovery for NO answer only; not answer repair or score selection.',
        'jobs':[{'task_id':j['task_id'],'arm':j['arm']} for j in selected]})
    def one(job):
        payload={'model':config['model'],'instructions':job['instructions'],
            'input':json.dumps(job['task'],ensure_ascii=False),'store':False,
            'reasoning':{'effort':config['reasoning_effort']},'max_output_tokens':config['max_output_tokens']}
        result=compare_models.assess_response(model_transport.request_once(payload,config['timeout_seconds']),job)
        result.update(attempt=2,task_digest=job['task_digest'],explicit_no_answer_recovery=True)
        lab.save(out/'raw'/job['arm']/job['task_id']/'attempt-2.json',result)
        print(json.dumps({'recovery':job['task_id'],'arm':job['arm'],'http_status':result.get('http_status'),
            'answer':bool(result.get('answer')),'structure_pass':result.get('structure_errors')==[]},ensure_ascii=False),flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=config['concurrency']) as pool:
        for _ in pool.map(one,selected):pass
    summary=summarize(out)
    if summary['attempts']>config['max_calls']:raise ValueError('Call cap exceeded')
    print(json.dumps(summary,ensure_ascii=False),flush=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['prepare','run','recover','summary'])
    p.add_argument('--outdir',type=Path,required=True);p.add_argument('--only')
    args=p.parse_args()
    if args.command=='prepare':prepare(args.outdir)
    elif args.command=='run':run(args.outdir,args.only)
    elif args.command=='recover':recover(args.outdir)
    else:print(json.dumps(summarize(args.outdir),ensure_ascii=False))


if __name__=='__main__':main()
