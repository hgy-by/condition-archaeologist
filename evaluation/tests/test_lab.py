"""Isolated synthetic fixtures only. These are software tests, never benchmark results."""
import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'evaluation'))
import lab
import rsi
spec=importlib.util.spec_from_file_location('witness',ROOT/'skill/scripts/check_witness.py')
w=importlib.util.module_from_spec(spec); spec.loader.exec_module(w)

def fixture():
    case={'task_id':'SYNTHETIC-1','subject':'isolated synthetic','family_id':'synthetic','split':'validation','hypotheses':[{'id':'H1'}],'intervention':{'removed':['H1']},'reference':{'judgment':'indispensable'},'review':{'status':'approved','reviewer':'synthetic_test_only','record':'fixture'},'gold_eligible':True}
    pred={'task_id':'SYNTHETIC-1','judgment':'indispensable','witness':'alternative mathematical object; reviewed by fixture','cost':{'elapsed_seconds':1}}
    review={'task_id':'SYNTHETIC-1','prediction_digest':lab.digest(pred),'reviewer':'synthetic_test_only','reviewed_at':'fixture','independent':True,'hypothesis_matches':1,'prediction_hypothesis_count':1}
    for k in ['judgment_correct','witness_claimed','witness_valid','all_retained_valid','conclusion_refuted','argument_valid','intervention_valid','evidence_honest','dependency_correct']: review[k]=True
    return case,pred,review

class MeaningfulChecks(unittest.TestCase):
    def test_data_obligations_and_family_isolation(self): self.assertEqual(lab.validate()['errors'],[])
    def test_nilpotent_rejects_diagonalization(self):
        self.assertTrue(w.check({'kind':'matrix','A':[[0,1],[0,0]],'claims':{'diagonalizable':False}})['claims_pass'])
    def test_incorrect_matrix_claim_rejected(self):
        self.assertFalse(w.check({'kind':'matrix','A':[[1,0],[0,2]],'claims':{'diagonalizable':False}})['claims_pass'])
    def test_real_complex_distinction(self):
        for field,answer in [('real',False),('complex',True)]:
            self.assertTrue(w.check({'kind':'matrix','A':[[0,-1],[1,0]],'field':field,'claims':{'diagonalizable':answer}})['claims_pass'])
    def test_empty_claims_never_prove(self): self.assertFalse(w.check({'kind':'matrix','A':[[1]],'claims':{}})['claims_pass'])
    def test_unsupported_is_unknown(self): self.assertIsNone(w.check({'kind':'general_topology'})['claims_pass'])
    def test_unknown_claim_is_unknown(self): self.assertIsNone(w.check({'kind':'matrix','A':[[1]],'claims':{'compact':True}})['claims_pass'])
    def test_untrusted_expression_rejected(self): self.assertEqual(w.check({'kind':'matrix','A':[["__import__('os')"]]})['status'],'input_error')
    def test_float_rejected(self): self.assertEqual(w.check({'kind':'matrix','A':[[0.1]]})['status'],'input_error')
    def test_polynomial_stationary(self): self.assertTrue(w.check({'kind':'polynomial_endpoints','coefficients':[1,0,-1],'a':-1,'b':1,'claims':{'equal_endpoints':True,'has_stationary_point':True}})['claims_pass'])
    def test_spike_exact_integral(self): self.assertTrue(w.check({'kind':'spike_integral','height':-1,'p':1,'q':1,'claims':{'integral_power':0,'integral_coefficient':-1}})['claims_pass'])
    def test_rational_denominator(self): self.assertTrue(w.check({'kind':'rational_values','numerator':[1],'denominator':[1,0],'points':[1,2],'claims':{'original_denominator_has_roots':True}})['claims_pass'])
    def test_pending_gold_blocks(self):
        c,p,a=fixture(); c['review']['status']='pending'
        with self.assertRaises(ValueError): lab.score([c],[p],[a])
    def test_alternative_witness_scored_by_obligations(self):
        c,p,a=fixture(); self.assertEqual(lab.score([c],[p],[a])['metrics']['success_rate'],1)
    def test_broken_retained_hypothesis_fails(self):
        c,p,a=fixture(); a['all_retained_valid']=False; a['witness_valid']=False
        r=lab.score([c],[p],[a]); self.assertEqual(r['metrics']['success_rate'],0); self.assertEqual(r['metrics']['witness_precision'],0)
    def test_modified_prediction_invalidates_review(self):
        c,p,a=fixture(); p['witness']='changed'
        with self.assertRaises(ValueError): lab.score([c],[p],[a])
    def test_abstention_not_perfect_precision(self):
        c,p,a=fixture(); p['judgment']='unresolved'; p['witness']=None; a['prediction_digest']=lab.digest(p)
        a['witness_claimed']=a['witness_valid']=a['judgment_correct']=False
        r=lab.score([c],[p],[a]); self.assertEqual(r['metrics']['coverage'],0); self.assertIsNone(r['metrics']['witness_precision'])
    def test_gate_refuses_unreviewed_small_sample(self):
        c,p,a=fixture(); r=lab.score([c],[p],[a],True); r['config_digest']='fixture'
        policy=lab.read(ROOT/'evaluation/rsi-policy.json'); g=lab.gate(r,r,policy)
        self.assertEqual(g['decision'],'reject_or_collect_more_evidence'); self.assertFalse(g['automatic_promotion'])
    def test_export_omits_references_and_sources(self):
        r=lab.load('heldout')[0]; exported=lab.prompt(r,'full_skill'); text=exported['prompt']
        self.assertNotIn('reference',text); self.assertNotIn('sources',text); self.assertNotIn('reviewer',text)
    def test_rsi_unreviewed_source_blocked(self):
        proposal={'author':'synthetic','rationale':'synthetic fixture','risk':'synthetic','source_case_ids':['MA01']}
        with self.assertRaisesRegex(ValueError,'unreviewed'): rsi.stage(proposal,ROOT/'skill',ROOT/'unused-synthetic-destination')
    def test_rsi_missing_source_blocked(self):
        with self.assertRaises(ValueError): rsi.stage({'author':'synthetic','rationale':'test','risk':'test','source_case_ids':[]},ROOT/'skill',ROOT/'unused-synthetic-destination')
    def test_conflicting_boolean_claim_rejected(self):
        self.assertEqual(w.check({'kind':'matrix','A':[[1]],'claims':{'square':1}})['status'],'input_error')

if __name__=='__main__': unittest.main(verbosity=2)
