"""Freeze public test inputs without API calls; run only with local confirmation.

Every actual attempt is counted before transport. No automatic retries, scoring,
RSI acceptance, provider substitution or reading of reference answers.
"""
import argparse
import getpass
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('ca_web_adapter',BASE/'web/server.py')
app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app)
API_BASE='https://chat.ecnu.edu.cn/open/api/v1'

def digest(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def save(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');tmp.replace(path)

def tree_hash(root):
    root=Path(root);h=hashlib.sha256()
    for p in sorted(root.rglob('*')):
        if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc':
            h.update(p.relative_to(root).as_posix().encode());h.update(p.read_bytes())
    return h.hexdigest()

def arm_text(arm,baseline=None):
    if arm=='direct_model':return ''
    root=Path(baseline) if arm=='old_skill' else BASE/'skill'
    files=[p for p in app.FILES if not (arm=='without_strategies' and p=='references/strategies.md')
           and not (arm=='without_verification' and p=='references/verification.md')]
    content={p:(root/p).read_text(encoding='utf-8') for p in files}
    if arm=='without_strategies':
        content['SKILL.md']='\n'.join('2. 本配置不提供策略库，请自行搜索。' if line.startswith('2. 按相关条件读取') else line for line in content['SKILL.md'].splitlines())
    if arm=='without_verification':
        content['SKILL.md']='\n'.join('3. 本配置不提供专门验证文档。' if line.startswith('3. 阅读 [证据和工具]') else line for line in content['SKILL.md'].splitlines())
    return '\n\n'.join('FILE '+p+'\n'+t for p,t in content.items())

def prepare(out,suite='smoke',model='ecnu-max',baseline=None):
    if out.exists():raise ValueError('输出目录已存在，请选择一个新目录以保留旧记录。')
    arms={'smoke':['full_skill'],'paired':['direct_model','full_skill'],
          'ablation':['direct_model','full_skill','without_strategies','without_verification'],
          'rsi':['old_skill','full_skill']}[suite]
    if suite=='rsi' and not baseline:raise ValueError('RSI比较须显式指定冻结旧版 --baseline-skill。')
    source=read(Path(__file__).with_name('web_tasks.json'))
    jobs=[]
    for task in source['tasks']:
        for arm in arms:
            payload=app.build_payload(task['theorem'],task['subject'],task['id'],model,'chat_completions')
            payload['messages'][0]['content']=app.WEB_INSTRUCTIONS+'\n\n'+arm_text(arm,baseline)
            jobs.append({'task':task,'arm':arm,'payload':payload})
    plan={'schema_version':1,'suite':suite,'provider':API_BASE,'model':model,
          'web_version':app.WEB_VERSION,'skill_version':app.SKILL_VERSION,'jobs':jobs,
          'candidate_skill_tree_sha256':tree_hash(BASE/'skill'),
          'baseline_skill_tree_sha256':tree_hash(baseline) if suite=='rsi' else None,
          'planned_calls':len(jobs),'max_transport_retries':0,'source_digest':digest(source),
          'reference_answers_sent':False,'strict_blind':False,'math_score':None,
          'limitation':'公开输入；尚待模型输出及逐项数学审阅。提示词和用量上限相同不保证实际用量相同。'}
    plan['plan_digest']=digest(plan)
    save(out/'plan.json',plan)
    return {'prepared_jobs':len(jobs),'model_calls':0,'out':str(out)}

def run(out,max_calls):
    plan=read(out/'plan.json');claimed=plan.pop('plan_digest')
    if digest(plan)!=claimed:raise ValueError('冻结计划已变动，请重新准备。')
    if plan['provider']!=API_BASE:raise ValueError('本入口仅运行已冻结的ChatECNU地址。')
    if plan['candidate_skill_tree_sha256']!=tree_hash(BASE/'skill'):raise ValueError('当前Skill已变动；为防止混合版本，请重新冻结测试计划。')
    records=sorted((out/'raw').glob('*.json')) if (out/'raw').exists() else []
    if not 1<=max_calls<=len(plan['jobs']):raise ValueError('次数上限须在1与计划总数之间。')
    print(f"本次最多累计发起 {max_calls} 次ChatECNU请求，已经记录 {len(records)} 次。价格未知。")
    if input(f'确认额度授权后输入 RUN {max_calls}：').strip()!=f'RUN {max_calls}':return {'cancelled':True,'new_calls':0}
    token=getpass.getpass('在本机粘贴学校API令牌（隐藏输入）：').strip()
    if not token or any(c.isspace() for c in token):raise ValueError('令牌应为一行完整内容。')
    for index,job in enumerate(plan['jobs']):
        path=out/'raw'/f'{index:03d}.json'
        if path.exists():continue
        count=len(list((out/'raw').glob('*.json'))) if (out/'raw').exists() else 0
        if count>=max_calls:break
        record={'task_id':job['task']['id'],'arm':job['arm'],'plan_digest':claimed,
                'status':'attempt_recorded_before_transport','usage':None,'usd':None,
                'mathematical_review':'pending','math_score':None}
        save(path,record)
        started=time.monotonic()
        try:
            request=Request(API_BASE+'/chat/completions',data=json.dumps(job['payload']).encode(),
                headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'},method='POST')
            with urlopen(request,timeout=180) as response:
                raw=response.read(4_000_001)
                if len(raw)>4_000_000:raise ValueError('oversized response')
                value=json.loads(raw)
            record.update(raw_response=value,usage=value.get('usage'),returned_model=value.get('model'))
            try:record.update(report=app.parse_chat_response(value),status='structure_pass_math_pending')
            except app.AppError as error:record.update(status='invalid_report',error=str(error))
        except HTTPError as error:record.update(status='transport_error',error='HTTP '+str(error.code))
        except Exception as error:record.update(status='transport_error',error=type(error).__name__)
        record['elapsed_seconds']=round(time.monotonic()-started,2);save(path,record)
        print(job['task']['id'],job['arm'],record['status'])
    actual=[read(p) for p in sorted((out/'raw').glob('*.json'))]
    summary={'attempted_calls':len(actual),'planned_calls':len(plan['jobs']),
             'structure_passes':sum(r['status']=='structure_pass_math_pending' for r in actual),
             'actual_usd':None,'math_score':None,'mathematical_review':'pending',
             'RSI_improvement_proven':False,'strict_blind':False}
    save(out/'summary.json',summary)
    return summary

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');p.add_argument('--out',type=Path,required=True)
    p.add_argument('--suite',choices=['smoke','paired','ablation','rsi'],default='smoke')
    p.add_argument('--model',default='ecnu-max');p.add_argument('--baseline-skill',type=Path)
    p=sub.add_parser('run');p.add_argument('--out',type=Path,required=True);p.add_argument('--max-calls',type=int,required=True)
    args=parser.parse_args()
    result=prepare(args.out,args.suite,args.model,args.baseline_skill) if args.command=='prepare' else run(args.out,args.max_calls)
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
