"""Finite exact computations, never a general counterexample verifier. SymPy required."""
import argparse
import json
import time
from pathlib import Path
import sympy as s

VERSION = '0.1.0'

def rational(x):
    if isinstance(x, bool) or not isinstance(x, (int, str)):
        raise ValueError('use integer or rational string, never floating point')
    if isinstance(x, str):
        import re
        if not re.fullmatch(r'-?\d+(?:/[1-9]\d*)?', x):
            raise ValueError('only exact rational strings allowed')
    return s.Rational(x)

def polynomial(coeffs, x):
    if not isinstance(coeffs, list) or not coeffs or len(coeffs)>30:
        raise ValueError('1..30 coefficients required')
    return sum(rational(a)*x**(len(coeffs)-1-i) for i,a in enumerate(coeffs))

def check(data):
    start=time.perf_counter()
    try:
        kind=data['kind']; claims=data.get('claims',{})
        if not isinstance(claims,dict): raise ValueError('claims must be object')
        if kind=='matrix':
            rows=data['A']
            if not rows or len(rows)>8 or not rows[0] or len(rows[0])>8: raise ValueError('matrix size 1..8')
            A=s.Matrix([[rational(x) for x in row] for row in rows]); square=A.rows==A.cols
            field=data.get('field','complex')
            if field not in ['real','complex']: raise ValueError('field must be real or complex')
            actual={'square':square,'symmetric':square and A==A.T}
            if square:
                actual.update(invertible=A.det()!=0,diagonalizable=bool(A.is_diagonalizable(reals_only=field=='real')))
            details={'matrix':str(A),'determinant':str(A.det()) if square else None,'field':field}
        elif kind=='polynomial_endpoints':
            x=s.Symbol('x',real=True); f=polynomial(data['coefficients'],x)
            a,b=rational(data['a']),rational(data['b'])
            if not a<b: raise ValueError('a must be less than b')
            roots=s.solveset(s.diff(f,x),x,domain=s.Interval.open(a,b))
            actual={'equal_endpoints':bool(f.subs(x,a)==f.subs(x,b)),'has_stationary_point':None if roots.is_empty is None else not roots.is_empty}
            details={'f':str(f),'f_a':str(f.subs(x,a)),'f_b':str(f.subs(x,b)),'internal_stationary_points':str(roots)}
        elif kind=='spike_integral':
            p,q=data['p'],data['q']; h=rational(data['height'])
            if type(p)!=int or type(q)!=int or q<=0: raise ValueError('integer p, positive integer q required')
            if h==0: raise ValueError('zero height not supported')
            actual={'integral_power':p-q,'integral_coefficient':str(h)}
            details={'integral':f'{h}*n**({p-q})','scope':'arithmetic identity only; measurable support and convergence require argument'}
        elif kind=='rational_values':
            z=s.Symbol('z'); num=polynomial(data['numerator'],z); den=polynomial(data['denominator'],z)
            if den==0: raise ValueError('zero denominator')
            vals={str(v):str(s.cancel(num/den).subs(z,rational(v))) for v in data.get('points',[])}
            actual={'original_denominator_has_roots':bool(s.degree(den,z)>0)}
            details={'original_denominator_roots':str(s.solveset(den,z,domain=s.S.Complexes)),'values':vals,'reduced_expression':str(s.cancel(num/den))}
        else:
            return {'version':VERSION,'status':'unsupported','claims_pass':None,'reason':'unsupported kind'}
        checks={}
        for key,expected in claims.items():
            if key not in actual or actual[key] is None: checks[key]=None
            elif key=='integral_coefficient': checks[key]=rational(expected)==rational(actual[key])
            else:
                if type(actual[key]) is not type(expected): raise ValueError(f'claim {key} has wrong type')
                checks[key]=actual[key]==expected
        passed=bool(checks) and all(v is True for v in checks.values())
        return {'version':VERSION,'status':'partial_computation','claims_pass':passed if all(v is not None for v in checks.values()) else None,'checks':checks,'actual':actual,'details':details,'elapsed_seconds':time.perf_counter()-start,'limitation':'Does not establish all retained hypotheses or whole counterexample validity.'}
    except (ValueError,KeyError,TypeError,s.SympifyError) as e:
        return {'version':VERSION,'status':'input_error','claims_pass':None,'reason':str(e)}

def main():
    p=argparse.ArgumentParser(); p.add_argument('input'); p.add_argument('--out',required=True); a=p.parse_args()
    r=check(json.loads(Path(a.input).read_text(encoding='utf-8')))
    output=Path(a.out); output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(r,ensure_ascii=False))
    return 0 if r['status']=='partial_computation' and r['claims_pass'] is not False else 2

if __name__=='__main__': raise SystemExit(main())
