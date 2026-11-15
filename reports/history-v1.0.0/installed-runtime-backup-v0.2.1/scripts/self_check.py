"""Check local runtime and a few exact witnesses, with explicit evidence limits."""
import argparse,importlib.util,json,platform,re,sys
from pathlib import Path

def run():
    root=Path(__file__).resolve().parents[1]; problems=[]
    required=['SKILL.md','references/judgment-protocol.md','references/strategies.md','references/output-schema.md','references/verification.md','references/rsi.md','references/seeds.json','scripts/check_witness.py','scripts/validate_output.py']
    for name in required:
        if not (root/name).is_file(): problems.append('missing '+name)
    for p in root.rglob('*.md'):
        for target in re.findall(r'\]\(([^)]+)\)',p.read_text(encoding='utf-8')):
            if not target.startswith(('http:','https:','#')) and not (p.parent/target).exists(): problems.append('broken reference '+target)
    sympy_available=importlib.util.find_spec('sympy') is not None; calculations=[]
    if sympy_available:
        from check_witness import check
        for item in [
            {'kind':'matrix','A':[[0,1],[0,0]],'claims':{'diagonalizable':False}},
            {'kind':'matrix','A':[[0,-1],[1,0]],'field':'real','claims':{'has_eigenvalue_in_field':False}},
            {'kind':'spike_integral','height':1,'p':1,'q':1,'claims':{'integral_power':0,'integral_coefficient':1}},
        ]:
            answer=check(item); calculations.append(answer)
            if answer['claims_pass'] is not True: problems.append('supported arithmetic self-check failed')
    return {'version':'0.2.1','skill_root':str(root),'python':sys.executable,'python_version':platform.python_version(),'core_files':'pass' if not problems else 'fail','sympy_available':sympy_available,'computation_checks':calculations,'issues':problems,'chat_workflow_ready':not problems,'local_computation_ready':not problems and sympy_available,'human_math_review':'not_performed_by_this_check','limitation':'Core reasoning runs in Codex chat. This is not a standalone theorem-solving program or a capability benchmark.'}

def main():
    p=argparse.ArgumentParser(); p.add_argument('--out',required=True); a=p.parse_args(); result=run()
    out=Path(a.out); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result['chat_workflow_ready'] else 1
if __name__=='__main__': raise SystemExit(main())
