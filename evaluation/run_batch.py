"""Run an explicitly supplied model adapter; stdin prompt, JSON output file or stdout.
The external controller must enforce heldout filesystem isolation; this script is not a sandbox.
"""
import argparse
import json
import subprocess
import time
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument('--jobs',required=True); p.add_argument('--adapter',required=True); p.add_argument('--workdir',required=True); p.add_argument('--outdir',required=True); p.add_argument('--timeout',type=int,default=180)
    a=p.parse_args(); jobs=json.loads(Path(a.jobs).read_text(encoding='utf-8')); adapter=json.loads(Path(a.adapter).read_text(encoding='utf-8')); out=Path(a.outdir).resolve()
    if a.timeout<=0: raise ValueError('timeout must be positive')
    if out.exists(): raise ValueError('choose a fresh output directory; previous runs are preserved')
    out.mkdir(parents=True,exist_ok=False)
    if not isinstance(adapter,list) or not adapter or not all(isinstance(x,str) for x in adapter): raise ValueError('adapter must be nonempty argument list')
    predictions=[]; traces=[]
    for job in jobs:
        tid=job['task_id']
        if not tid.replace('-','').replace('_','').isalnum(): raise ValueError('invalid task ID')
        output_file=out/(tid+'.json'); cmd=[x.replace('{output_file}',str(output_file)) for x in adapter]; start=time.perf_counter()
        # Existing files must never masquerade as current model output.
        if output_file.exists(): raise ValueError('output exists; choose a fresh run directory')
        try:
            result=subprocess.run(cmd,input=job['prompt'],text=True,encoding='utf-8',capture_output=True,cwd=a.workdir,timeout=a.timeout,shell=False)
            pred=None; error=None
            if result.returncode==0:
                try:
                    pred=json.loads(output_file.read_text(encoding='utf-8') if output_file.exists() else result.stdout)
                    if not isinstance(pred,dict) or pred.get('task_id')!=tid: raise ValueError('task ID mismatch or non-object')
                    if not isinstance(pred.get('cost',{}),dict): raise ValueError('cost must be object')
                    pred.setdefault('cost',{}); pred['cost']['elapsed_seconds']=time.perf_counter()-start
                    pred['cost'].setdefault('model_calls',None)
                    predictions.append(pred)
                except (ValueError,OSError) as e: error=str(e)
            traces.append({'task_id':tid,'returncode':result.returncode,'adapter_process_calls':1,'error':error,'stderr':result.stderr,'stdout':result.stdout,'elapsed_seconds':time.perf_counter()-start,'task_digest':job['task_digest']})
        except (OSError,subprocess.TimeoutExpired) as e:
            traces.append({'task_id':tid,'returncode':None,'error':str(e),'elapsed_seconds':time.perf_counter()-start,'task_digest':job['task_digest']})
        (out/'predictions.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in predictions),encoding='utf-8')
        (out/'traces.json').write_text(json.dumps(traces,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'attempted':len(traces),'outputs':len(predictions),'mathematical_success':'not_graded'},ensure_ascii=False))
    return 0 if len(predictions)==len(jobs) else 2

if __name__=='__main__': raise SystemExit(main())
