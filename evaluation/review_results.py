"""Render blinded cards; import actual human feedback without inventing math scores."""
import argparse
import hashlib
import html
import json
from pathlib import Path
import random
import lab

DECISIONS=('待审核','通过','部分正确','错误','待确认')


def records(out):
    result=[]
    for job in lab.read(out/'jobs.json'):
        files=sorted((out/'raw'/job['arm']/job['task_id']).glob('attempt-*.json'))
        row=lab.read(files[-1]) if files else None
        result.append((job,row,files))
    return result


def render(out):
    rows=records(out); rng=random.Random(20261105); grouped={}
    for job,result,attempts in rows:
        grouped.setdefault(job['task_id'],[]).append((job,result,attempts))
    cards=[]; mapping=[]; counts={}
    for tid,group in grouped.items():
        rng.shuffle(group)
        for index,(job,result,attempts) in enumerate(group):
            rid=tid+'-'+chr(65+index)
            digest=lab.digest(result)
            mapping.append({'review_id':rid,'task_id':tid,'arm':job['arm'],'kind':job['kind'],
                            'response_digest':digest,'has_response':bool(result and result.get('answer'))})
            counts[job['kind']]=counts.get(job['kind'],0)+1
            answer=(result or {}).get('answer') or '没有取得模型回答。属于运行缺口，不应伪造数学答案。'
            structure=(result or {}).get('structure_errors')
            status='结构检查通过（不等于数学正确）' if structure==[] else '需检查运行或输出格式：'+str(structure)
            cards.append('<article><h2>'+rid+'</h2><p>'+html.escape(job['kind'])+'；'+html.escape(status)
                +'</p><h3>输入</h3><pre>'+html.escape(json.dumps(job['task'],ensure_ascii=False,indent=2))
                +'</pre><h3>原始回答</h3><pre>'+html.escape(answer)+'</pre>'
                +'<label>审核结论 <select data-id="'+rid+'">'+''.join('<option>'+d+'</option>' for d in DECISIONS)
                +'</select></label><p>请记录数学错误、遗漏或需要进一步确认之处；完整定理还要检查条件与结论是否遗漏。</p>'
                +'<textarea data-id="'+rid+'" rows="5"></textarea></article>')
    lab.save(out/'controller-arm-mapping.json',mapping)
    fingerprint=lab.digest(mapping)
    review_template={'run_digest':fingerprint,'reviewer':'','reviewed_at':'',
                     'records':[{'review_id':r['review_id'],'response_digest':r['response_digest'],
                                 'decision':'待审核','notes':''} for r in mapping]}
    lab.save(out/'human-review-template.json',review_template)
    # Embed only digests and public review IDs; group labels remain in controller file.
    public=[{k:r[k] for k in ('review_id','response_digest')} for r in mapping]
    jsdata=json.dumps({'digest':fingerprint,'records':public},ensure_ascii=False).replace('<','\\u003c')
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>第二轮模型回答审核</title>
<style>body{font:17px/1.7 system-ui;max-width:1100px;margin:auto;padding:25px;background:#f6f7f8}article{background:white;margin:24px 0;padding:24px;border:1px solid #ccc}pre{font:16px/1.7 system-ui;white-space:pre-wrap;overflow-wrap:anywhere}textarea{width:97%}button{padding:12px}</style>
<h1>第二轮模型回答审核</h1><p>两组已按题打乱。不要先查看controller-arm-mapping.json。A/B只隐藏组别，不构成文件访问隔离。先独立审核，再参考AI意见。</p>
<p>通过＝关键数学任务完成；部分正确＝存在关键遗漏；错误＝有实质错误；待确认＝暂时无法判断。歧义任务看是否合理澄清、条件化分析和诚实报告；完整定理看解析、逐项干预、依赖与剩余工作。不同于参考答案的有效反例应认可。</p>
<p>审核人或代称 <input id="reviewer"> 日期 <input id="date" type="date"></p>
<button onclick="exportData()">导出审核记录</button> <input type="file" accept=".json" onchange="restore(this)">
<p>填写不会自动保存，请导出记录。可导入已导出的文件继续填写。尚未完成的条目保持“待审核”。</p>
'''+''.join(cards)+'''<script>const bound='''+jsdata+''';
function exportData(){const d={run_digest:bound.digest,reviewer:document.querySelector('#reviewer').value,reviewed_at:document.querySelector('#date').value,records:bound.records.map(r=>({...r,decision:document.querySelector('select[data-id="'+r.review_id+'"]').value,notes:document.querySelector('textarea[data-id="'+r.review_id+'"]').value}))};const u=URL.createObjectURL(new Blob([JSON.stringify(d,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=u;a.download='第二轮人工审核记录.json';a.click();setTimeout(()=>URL.revokeObjectURL(u),1000)}
async function restore(i){try{const d=JSON.parse(await i.files[0].text());if(d.run_digest!==bound.digest)throw Error('记录属于其他运行或回答已经变化');document.querySelector('#reviewer').value=d.reviewer||'';document.querySelector('#date').value=d.reviewed_at||'';for(const r of d.records){const expected=bound.records.find(e=>e.review_id===r.review_id);if(!expected||expected.response_digest!==r.response_digest)throw Error('回答摘要不匹配');document.querySelector('select[data-id="'+r.review_id+'"]').value=r.decision;document.querySelector('textarea[data-id="'+r.review_id+'"]').value=r.notes||''}}catch(e){alert(e.message)}}
</script></html>'''
    (out/'模型回答人工审核.html').write_text(page,encoding='utf-8')
    latest=[r for _,r,_ in rows if r]
    attempts=[lab.read(p) for _,_,paths in rows for p in paths]
    summary={'planned_answers':len(rows),'attempted_calls':len(attempts),
             'answers_received':sum(bool(r.get('answer')) for r in latest),
             'parsed_outputs':sum(r.get('prediction') is not None for r in latest),
             'structure_passes':sum(r.get('structure_errors')==[] for r in latest),
             'kinds':counts,'actual_models':sorted({r['actual_model'] for r in latest if r.get('actual_model')}),
             'usage':{k:sum((r.get('usage') or {}).get(k,0) or 0 for r in attempts) for k in ('input_tokens','output_tokens','total_tokens')},
             'usd':None,'human_math_review':'pending','formal_capability_score':None,'RSI_improvement_proven':False}
    lab.save(out/'run-summary.json',summary)
    print(json.dumps(summary,ensure_ascii=False),flush=True)
    return summary


def import_reviews(out,feedback):
    source=lab.read(feedback); mapping=lab.read(out/'controller-arm-mapping.json')
    if not source.get('reviewer') or not source.get('reviewed_at'):
        raise ValueError('Reviewer alias and date required; real identity or signature not required')
    if source.get('run_digest')!=lab.digest(mapping):
        raise ValueError('Review belongs to another run')
    expected=lab.unique(mapping,'review_id'); seen=set(); imported=[]
    current={(j['task_id'],j['arm']):lab.digest(r) for j,r,_ in records(out)}
    for row in source['records']:
        rid=row['review_id']
        if rid in seen or rid not in expected:
            raise ValueError('Duplicate or unknown review ID')
        seen.add(rid); match=expected[rid]
        if row.get('response_digest')!=match['response_digest'] or current[(match['task_id'],match['arm'])]!=match['response_digest']:
            raise ValueError('Response changed since review; do not reuse stale judgments')
        if row.get('decision') not in DECISIONS:
            raise ValueError('Unknown review decision')
        imported.append({**row,'task_id':match['task_id'],'arm':match['arm'],'kind':match['kind']})
    digest=lab.digest(source); folder=out/'imported-reviews'; folder.mkdir(parents=True,exist_ok=True)
    # Keep paths usable on Windows while retaining the full digest in the record.
    path=folder/(digest[:24]+'.json')
    if path.exists():
        raise FileExistsError('This review record was already imported')
    summary={'review_record_digest':digest,'reviewer':source['reviewer'],'reviewed_at':source['reviewed_at'],
             'source_file_sha256':hashlib.sha256(feedback.read_bytes()).hexdigest(),
             'run_digest':source['run_digest'],'records':imported,
             'decision_counts':{d:sum(r['decision']==d for r in imported) for d in DECISIONS},
             'unsubmitted':len(mapping)-len(imported),
             'numeric_rubric_score':None,'automatic_formal_adjudication':False,
             'note':'定性审核不自动转换为细项数学真值或百分制扣分；需检查理由、处理争议后接入lab.py。'}
    lab.save(path,summary)
    print(json.dumps({'imported':len(imported),'decisions':summary['decision_counts'],'path':str(path)},ensure_ascii=False))
    return summary


def main():
    parser=argparse.ArgumentParser(); sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('render');p.add_argument('--outdir',required=True,type=Path)
    p=sub.add_parser('import');p.add_argument('--outdir',required=True,type=Path);p.add_argument('--feedback',required=True,type=Path)
    args=parser.parse_args()
    if args.command=='render':render(args.outdir)
    else:import_reviews(args.outdir,args.feedback)


if __name__=='__main__':main()
