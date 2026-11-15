"""Run local engineering/math computations only. Never calls a model provider."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,default=ROOT/'reports/current');a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=True)
    node=shutil.which('node')
    checks=[('web-tests',[sys.executable,'-X','utf8','-m','unittest','discover','-s','web/tests','-p','test_*.py','-v']),
            ('evaluation-tests',[sys.executable,'-X','utf8','-m','unittest','discover','-s','evaluation/tests','-p','test_*.py','-v']),
            ('skill-structure',[sys.executable,'-X','utf8','scripts/check_skill.py']),
            ('exact-computations',[sys.executable,'-X','utf8','evaluation/final_exact_checks.py','--out',str(a.out/'exact-computations.json')]),
            ('skill-environment',[sys.executable,'-X','utf8','skill/scripts/self_check.py','--out',str(a.out/'skill-environment.json')])]
    if node:
        checks.extend([('javascript-syntax-app',[node,'--check','web/static/app.js']),
                       ('javascript-syntax-utils',[node,'--check','web/static/report-utils.js']),
                       ('report-utils-tests',[node,'web/tests/test_report_utils.cjs'])])
    results=[]
    for name,command in checks:
        result=subprocess.run(command,cwd=ROOT,capture_output=True,encoding='utf-8',errors='replace')
        (a.out/(name+'.log')).write_text(result.stdout+'\n'+result.stderr,encoding='utf-8')
        results.append({'name':name,'exit_code':result.returncode,'passed':result.returncode==0,
                        'command':command,'log':name+'.log'})
        print(name,'PASS' if result.returncode==0 else 'FAIL',flush=True)
    canonical={str(f.relative_to(ROOT/'skill')).replace('\\','/'):hashlib.sha256(f.read_bytes()).hexdigest()
               for f in (ROOT/'skill').rglob('*') if f.is_file() and '__pycache__' not in f.parts and f.suffix!='.pyc'}
    bundled={str(f.relative_to(ROOT/'web/skill')).replace('\\','/'):hashlib.sha256(f.read_bytes()).hexdigest()
             for f in (ROOT/'web/skill').rglob('*') if f.is_file() and '__pycache__' not in f.parts and f.suffix!='.pyc'}
    match=canonical==bundled
    results.append({'name':'canonical-and-web-skill-match','passed':match,'runtime_files':len(canonical),'sha256':canonical})
    summary={'created_at':datetime.now(timezone.utc).isoformat(),'engineering_passed':all(x['passed'] for x in results),
             'checks':results,'node_available':bool(node),'live_model_calls':0,'live_model_score':None,
             'browser_interaction_verified':False,'mathematics_formally_verified':False,'RSI_improvement_proven':False,
             'scope':'Tests include explicitly isolated synthetic transport fixtures. Exact computations verify only six stated algebraic/calculus scopes.'}
    (a.out/'engineering-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return 0 if summary['engineering_passed'] else 1

if __name__=='__main__':sys.exit(main())
