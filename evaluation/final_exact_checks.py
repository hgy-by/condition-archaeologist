"""Repeat six exact computations supporting actual final-run witnesses only."""
import argparse
from pathlib import Path
import sympy as s
import lab


def run():
    groups=[]
    x,y=s.symbols('x y',real=True)
    for k in (1,2):
        A=s.Matrix([[1,-k],[k,1]]);v=s.Matrix([x,y])
        assert s.expand((v.T*A*v)[0]-x*x-y*y)==0
        assert A.charpoly().all_coeffs()==[1,-2,1+k*k]
    groups.append({'id':'positive_nonsymmetric','scope':'k=1,2实二次型及特征多项式；未用数值近似。'})
    J=s.Matrix([[1,1],[0,1]]);N=s.Matrix([[0,1],[0,0]])
    assert len((J-s.eye(2)).nullspace())==1
    assert N*N==s.zeros(2) and N!=s.zeros(2)
    groups.append({'id':'Jordan','scope':'实际Jordan矩阵的特征空间和幂零性。'})
    x=s.symbols('x',real=True,nonzero=True)
    assert s.simplify(s.diff(x*x*s.sin(1/x**2),x)-(2*x*s.sin(1/x**2)-2*s.cos(1/x**2)/x))==0
    groups.append({'id':'derivative_formula','scope':'仅非零点导数公式；0点导数与极限序列另见数学论证。'})
    z=s.symbols('z')
    assert s.diff(1/(2-z),z,2).subs(z,0)==s.Rational(1,4)
    assert s.diff(z*z,z,2)==2
    groups.append({'id':'nonaffine','scope':'1/(2-z)和z²的二阶导数。'})
    a=s.symbols('a',positive=True)
    assert s.limit(s.integrate(1/x,(x,a,1)),a,0,dir='+')==s.oo
    groups.append({'id':'positive_divergent_integral','scope':'(0,1)上1/x的不正常积分为+∞；其可测非负性另作数学论证。'})
    assert s.exp(2*s.pi*s.I)==1
    groups.append({'id':'complex_period','scope':'exp(2πi)=1；整性、非零性未由此计算证明。'})
    return {'status':'pass','groups':groups,'formal_verification':False,
        'evidence_level':'local_exact_computation','universal_mathematical_verification':False,
        'sympy_version':s.__version__}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();result=run();lab.save(a.out,result)
    print('Exact computation groups passed:',len(result['groups']))
