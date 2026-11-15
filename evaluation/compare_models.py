"""Freeze answer-free jobs, run independent calls, and prepare digest-bound review."""
import argparse
import concurrent.futures
import copy
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit
import lab
import model_transport

RUNTIME = Path(__file__).resolve().parents[1] / 'skill'
sys.path.insert(0, str(RUNTIME / 'scripts'))
import validate_output

FILES = ('SKILL.md', 'references/judgment-protocol.md', 'references/strategies.md',
         'references/verification.md', 'references/output-schema.md')
SAFE_KEYS = {'task_id','subject','statement','ambient','hypotheses','intervention','conclusions','request'}


def safe_task(task):
    if not isinstance(task, dict) or set(task) - SAFE_KEYS:
        raise ValueError('Task contains unknown fields; reference answers must not be forwarded')
    if not re.fullmatch(r'[A-Za-z0-9_-]+', task.get('task_id', '')):
        raise ValueError('Invalid task ID')
    return copy.deepcopy(task)


def prepare(inputs, out, runtime=RUNTIME):
    if out.exists():
        raise FileExistsError('Choose a fresh run directory; existing evidence is preserved')
    rows = lab.read(inputs)
    # Reject duplicate jobs before any mutation or network call.
    jobs = []
    sources = {name: (runtime / name).read_text(encoding='utf-8') for name in FILES}
    schema = sources['references/output-schema.md']
    common = ('独立完成数学任务，中文回答，只输出一个JSON对象。不调用工具或读取外部文件。'
              '不要声称已人工或形式化核验。未知成本用null。以下是共同输出格式，示例值不是答案。\n'
              + schema.split('机器评测输出为单个 JSON 对象：',1)[1].split('示意字段不是默认答案',1)[0])
    common += ('\n两组共同的输出约定：judgment只取indispensable（单删后有反例）、'
               'removable（删后结论仍成立）、implied（保留条件推出被删条件）、'
               'joint（指定联合删除有反例）、type_constraint（需改写定义或对象类别）、'
               'unresolved（证据不足）、statement_issue（原命题有误）。'
               'removable/implied的witness与target_failure填null，argument写删后成立理由。'
               'retained_checks和replacement_checks均为id、argument对象数组，覆盖相应条件。'
               '未知成本填null。这些标签约定不代表本题答案。')
    seen = set()
    for row in rows:
        task = safe_task(row['task'])
        kind = row['kind']
        if kind not in ('intervention','uncertainty','full_theorem'):
            raise ValueError('Unknown task kind')
        for arm in row['arms']:
            if arm not in ('direct_model','full_skill'):
                raise ValueError('Unknown arm')
            identity = (task['task_id'], arm)
            if identity in seen:
                raise ValueError('Duplicate job')
            seen.add(identity)
            instructions = common
            if kind == 'full_theorem':
                instructions += ('\n本题必须自行提取假设。输出顶层task_id、theorem、interventions、'
                                 'dependency_map、remaining_work；interventions内使用上述单项格式。')
            elif kind == 'uncertainty':
                instructions += ('\n这是可能有歧义的请求。只输出task_id、interpretation、'
                                 'missing_information、conditional_analysis、questions、limitations。'
                                 '不要把歧义强行改成单一确定命题；可给明确限定后的版本。')
            if arm == 'full_skill':
                instructions += '\n\n运行以下冻结Skill文本，不读取其他资源：\n' + '\n\n'.join(
                    'FILE '+name+'\n'+text for name,text in sources.items())
            jobs.append({'task_id':task['task_id'],'arm':arm,'kind':kind,
                         'task':task,'task_digest':lab.digest(task),'instructions':instructions,
                         'reference_state':row.get('reference_state','not_provided')})
    config, endpoint, _ = model_transport.settings()
    out.mkdir(parents=True)
    lab.save(out/'jobs.json', jobs)
    lab.save(out/'configuration.json', {
        'model':config['model'],'provider_origin':urlsplit(endpoint).netloc,
        'reasoning_effort':config.get('model_reasoning_effort','high'),
        'max_output_tokens':8000,'timeout_seconds':180,'concurrency':2,
        'max_transport_retries':1,'expected_answers':len(jobs),
        'model_tools':False,'history':False,'reference_answers_sent':False,
        'mode':'text_loaded_skill_without_seeds','formal_score':None,
        'shared_output_contract_sha256':hashlib.sha256(common.encode()).hexdigest(),
        'skill_files_sha256':{k:hashlib.sha256(v.encode()).hexdigest() for k,v in sources.items()},
        'jobs_digest':lab.digest(jobs),'actual_cost_usd':None})
    print(json.dumps({'prepared':len(jobs),'out':str(out)},ensure_ascii=False))


def assess_response(result, job):
    result.update({'task_id':job['task_id'],'arm':job['arm'],'kind':job['kind'],
                   'prediction':None,'structure_errors':None})
    if not result.get('raw'):
        return result
    try:
        response, answer = model_transport.parse_response(result['raw'])
        if not isinstance(response, dict):
            raise ValueError('Provider returned a non-object response')
        provider_error = response.get('error')
        if isinstance(provider_error, dict) and not response.get('output'):
            # Keep arbitrary upstream text in the raw artifact only. It is not
            # an answer, mathematical failure, or permission to retry forever.
            error_type = provider_error.get('type')
            allowed = {'service_unavailable_error','server_error','overloaded_error'}
            result['provider_error_type'] = error_type if error_type in allowed else 'other_provider_error'
            result['parse_error'] = 'Provider error envelope; no model answer'
            return result
        result.update({'actual_model':response.get('model'),'usage':response.get('usage'),
                       'response_status':response.get('status'),'answer':answer,
                       'incomplete_details':response.get('incomplete_details')})
        clean = answer.strip()
        if clean.startswith('```') and clean.endswith('```'):
            clean = clean.split('\n',1)[1].rsplit('```',1)[0].strip()
        pred = json.loads(clean)
        if not isinstance(pred,dict) or pred.get('task_id')!=job['task_id']:
            raise ValueError('Task ID mismatch or non-object')
        if job['kind']=='uncertainty':
            errors = ['missing '+k for k in ('interpretation','missing_information','conditional_analysis','questions','limitations') if k not in pred]
        else:
            errors = validate_output.validate(pred)
        if response.get('status') != 'completed':
            errors.append('Response did not complete; never silently count a truncated answer as a pass')
        result['prediction'], result['structure_errors'] = pred, errors
    except (ValueError,KeyError,TypeError) as error:
        result['parse_error'] = str(error)
    return result


def call(job,out,config):
    folder = out/'raw'/job['arm']/job['task_id']
    folder.mkdir(parents=True,exist_ok=True)
    previous = sorted(folder.glob('attempt-*.json'))
    if previous:
        return lab.read(previous[-1])
    payload={'model':config['model'],'instructions':job['instructions'],
             'input':json.dumps(job['task'],ensure_ascii=False),'store':False,
             'reasoning':{'effort':config['reasoning_effort']},
             'max_output_tokens':config['max_output_tokens']}
    for attempt in range(1,config['max_transport_retries']+2):
        result=assess_response(model_transport.request_once(payload,config['timeout_seconds']),job)
        result['attempt']=attempt
        result['task_digest']=job['task_digest']
        lab.save(folder/f'attempt-{attempt}.json',result)
        # Retry only a transport failure with no HTTP response; never retry an
        # incorrect answer, refusal, truncation, parse failure, or authentication.
        if result['http_status'] is not None:
            break
    print(json.dumps({'task_id':job['task_id'],'arm':job['arm'],'attempts':attempt,
                      'http_status':result['http_status'],'parsed':result['prediction'] is not None,
                      'structure_pass':result['structure_errors']==[]},ensure_ascii=False),flush=True)
    return result


def execute(out):
    config=lab.read(out/'configuration.json'); jobs=lab.read(out/'jobs.json')
    if lab.digest(jobs)!=config['jobs_digest']:
        raise ValueError('Frozen jobs changed')
    current,endpoint,_=model_transport.settings()
    if current['model']!=config['model'] or urlsplit(endpoint).netloc!=config['provider_origin']:
        raise ValueError('Configured model/provider changed since preparation')
    with concurrent.futures.ThreadPoolExecutor(max_workers=config['concurrency']) as pool:
        futures=[pool.submit(call,j,out,config) for j in jobs]
        for future in concurrent.futures.as_completed(futures):
            future.result()
    from review_results import render
    render(out)


def recoverable(result):
    if result.get('answer') or result.get('prediction') is not None:
        return False
    return result.get('http_status') in (520,521,522,523,524) or (
        result.get('http_status')==200 and (not (result.get('raw') or '').strip() or
        result.get('provider_error_type') in {'service_unavailable_error','server_error','overloaded_error'}))


def recover(out):
    """One explicit recovery of gateway/empty-body failures; never choose answers."""
    config=lab.read(out/'configuration.json');jobs=lab.read(out/'jobs.json')
    if lab.digest(jobs)!=config['jobs_digest']:raise ValueError('Frozen jobs changed')
    current,endpoint,_=model_transport.settings()
    if current['model']!=config['model'] or urlsplit(endpoint).netloc!=config['provider_origin']:
        raise ValueError('Configured model/provider changed')
    selected=[]
    for job in jobs:
        folder=out/'raw'/job['arm']/job['task_id'];files=sorted(folder.glob('attempt-*.json'))
        if not files:continue
        result=lab.read(files[-1])
        if result.get('explicit_gateway_recovery') or not recoverable(result):continue
        selected.append((job,folder,len(files)+1))
    lab.save(out/'gateway-recovery-plan.json',{
        'reason':'Gateway 520-524, HTTP 200 whitespace, or explicit transient provider error envelope, with no model answer',
        'policy':'One explicit recovery per affected job, sequential, identical frozen payload; never retry any mathematical answer.',
        'jobs':[{'task_id':j['task_id'],'arm':j['arm'],'attempt':n} for j,_,n in selected]})
    for job,folder,number in selected:
        payload={'model':config['model'],'instructions':job['instructions'],
                 'input':json.dumps(job['task'],ensure_ascii=False),'store':False,
                 'reasoning':{'effort':config['reasoning_effort']},'max_output_tokens':config['max_output_tokens']}
        result=assess_response(model_transport.request_once(payload,config['timeout_seconds']),job)
        result.update({'attempt':number,'task_digest':job['task_digest'],'explicit_gateway_recovery':True})
        lab.save(folder/f'attempt-{number}.json',result)
        print(json.dumps({'recovery':job['task_id'],'arm':job['arm'],
                          'http_status':result['http_status'],'has_answer':bool(result.get('answer')),
                          'structure_pass':result['structure_errors']==[]},ensure_ascii=False),flush=True)
    from review_results import render
    render(out)


def main():
    parser=argparse.ArgumentParser(); sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare'); p.add_argument('--inputs',required=True,type=Path); p.add_argument('--outdir',required=True,type=Path)
    p=sub.add_parser('run'); p.add_argument('--outdir',required=True,type=Path)
    p=sub.add_parser('recover'); p.add_argument('--outdir',required=True,type=Path)
    args=parser.parse_args()
    if args.command=='prepare': prepare(args.inputs,args.outdir)
    elif args.command=='run':execute(args.outdir)
    else:recover(args.outdir)


if __name__=='__main__': main()
