"""Regression/integration tests. Synthetic adapters are not model capability results."""
import importlib.util,json,subprocess,sys,unittest,uuid
from contextlib import contextmanager
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'evaluation'))
sys.path.insert(0,str(ROOT/'skill/scripts'))
import lab,check_witness,validate_output
TEMP_ROOT=ROOT/'.runtime/tests'/'test-runtime-v020'
TEMP_ROOT.mkdir(parents=True,exist_ok=True)
@contextmanager
def scratch_directory():
    # Ordinary inherited permissions work in restricted Windows sessions; mkdtemp
    # may create a private ACL that excludes the execution identity.
    path=TEMP_ROOT/uuid.uuid4().hex; path.mkdir()
    yield path

def output():
    return {'task_id':'SYNTHETIC','hypotheses':[{'id':'H1','text':'target'},{'id':'H2','text':'retained'}], 'intervention':{'removed':['H1'],'replacement':None},'judgment':'indispensable','witness':'explicit synthetic witness','retained_checks':[{'id':'H2','argument':'synthetic argument'}],'replacement_checks':[],'target_failure':{'id':'C1','argument':'synthetic failure'},'argument':'synthetic whole argument','evidence':[{'kind':'mathematical_argument','artifact':None,'scope':'synthetic'}],'dependencies':[],'uncertainties':[],'next_steps':[],'cost':{'elapsed_seconds':None,'model_calls':None,'tool_calls':None,'usd':None}}

class RuntimeRegression(unittest.TestCase):
    def test_false_dominates_unknown(self):
        r=check_witness.check({'kind':'matrix','A':[[1]],'claims':{'square':False,'unknown_property':True}})
        self.assertIs(r['claims_pass'],False)
    def test_original_hole_not_filled(self):
        r=check_witness.check({'kind':'rational_values','numerator':[1,0],'denominator':[1,0],'points':[0,1],'claims':{'original_denominator_has_roots':True}})
        self.assertEqual(r['details']['values']['0'],'undefined_in_original_domain'); self.assertEqual(r['details']['values']['1'],'1')
    def test_real_eigenvalue_distinct_from_diagonalization(self):
        r=check_witness.check({'kind':'matrix','A':[[1,1],[0,1]],'field':'real','claims':{'diagonalizable':False,'has_eigenvalue_in_field':True}})
        self.assertIs(r['claims_pass'],True)
    def test_rotation_has_no_real_eigenvalue(self):
        self.assertTrue(check_witness.check({'kind':'matrix','A':[[0,-1],[1,0]],'field':'real','claims':{'has_eigenvalue_in_field':False}})['claims_pass'])
    def test_unknown_claim_cli_is_not_success(self):
        with scratch_directory() as d:
            inp=Path(d)/'in.json'; out=Path(d)/'nested/out.json'; inp.write_text(json.dumps({'kind':'matrix','A':[[1]],'claims':{'unrecognized':True}}),encoding='utf-8')
            r=subprocess.run([sys.executable,str(ROOT/'skill/scripts/check_witness.py'),str(inp),'--out',str(out)],capture_output=True)
            self.assertNotEqual(r.returncode,0); self.assertIsNone(json.loads(out.read_text(encoding='utf-8'))['claims_pass'])
    def test_output_structure_accepts_complete_obligations(self): self.assertEqual(validate_output.validate(output()),[])
    def test_output_structure_rejects_missing_retained(self):
        r=output(); r['retained_checks']=[]; self.assertTrue(validate_output.validate(r))
    def test_output_structure_requires_replacement(self):
        r=output(); r['intervention']['replacement']={'id':'H1w','text':'weaker'}; self.assertTrue(validate_output.validate(r))
        r['replacement_checks']=[{'id':'H1w','argument':'verified'}]; self.assertEqual(validate_output.validate(r),[])
    def test_unresolved_needs_explanation(self):
        r=output(); r['judgment']='unresolved'; r['witness']=None; r['target_failure']=None; self.assertTrue(validate_output.validate(r))
        r['uncertainties']=['remaining mathematical question']; self.assertEqual(validate_output.validate(r),[])
    def test_claimed_review_needs_artifact(self):
        r=output(); r['evidence'][0]['kind']='human_reviewed'; self.assertTrue(validate_output.validate(r))
    def test_batch_duplicate_ids_rejected(self):
        r={'theorem':{},'interventions':[output(),output()],'dependency_map':[],'remaining_work':[]}; self.assertTrue(validate_output.validate(r))
    def test_export_includes_object_conventions(self):
        r=next(x for x in lab.load('development') if x['task_id']=='AL02'); self.assertIn(r['ambient'],lab.prompt(r,'full_skill')['prompt'])
    def test_ma04_replacement_preserved(self):
        r=next(x for x in lab.load('development') if x['task_id']=='MA04'); self.assertEqual(r['intervention']['replacement']['id'],'H2w')
    def test_ai_review_alone_cannot_qualify_as_human_gold(self):
        for s in lab.SPLITS:
            for r in lab.load(s):
                if r['gold_eligible']:
                    self.assertEqual(r['review']['status'],'approved'); self.assertTrue(r['review'].get('reviewer')); self.assertTrue(r['review'].get('record'))
                elif r.get('ai_review'): self.assertNotEqual(r['review'].get('status'),'approved')
    def test_adapter_flow_preserves_unknown_model_cost_and_old_runs(self):
        with scratch_directory() as d:
            temp=Path(d); jobs=temp/'jobs.json'; adapter=temp/'adapter.json'; script=temp/'synthetic_adapter.py'; out=temp/'run'
            jobs.write_text(json.dumps([{'task_id':'SYNTHETIC','prompt':'fixture','task_digest':'fixture'}]),encoding='utf-8')
            script.write_text('import json,sys\nsys.stdin.read()\nprint(json.dumps({"task_id":"SYNTHETIC","judgment":"unresolved","cost":{}}))\n',encoding='utf-8')
            adapter.write_text(json.dumps([sys.executable,str(script)]),encoding='utf-8')
            cmd=[sys.executable,str(ROOT/'evaluation/run_batch.py'),'--jobs',str(jobs),'--adapter',str(adapter),'--workdir',str(temp),'--outdir',str(out)]
            result=subprocess.run(cmd,capture_output=True); self.assertEqual(result.returncode,0,result.stderr)
            predictions=(out/'predictions.jsonl').read_bytes(); pred=json.loads(predictions.decode('utf-8')); self.assertIsNone(pred['cost']['model_calls'])
            result=subprocess.run(cmd,capture_output=True); self.assertNotEqual(result.returncode,0); self.assertEqual((out/'predictions.jsonl').read_bytes(),predictions)

if __name__=='__main__': unittest.main(verbosity=2)
