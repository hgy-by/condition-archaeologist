"""Meaningful AI staging/gating and experiment isolation tests; not math grades."""
import copy
from pathlib import Path
import sys
import unittest
import uuid

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'evaluation'))
import ai_rsi
import final_experiment as experiment
import lab
import rsi


def pair():
    a={'status':'ai_reviewed_internal','config_digest':'resources','skill_tree_hash':'baseline',
       'pool':'isolated_validation','reference_exposure':False,'candidate_rule_sources_disjoint':True,
       'dataset_digest':'synthetic-identical','per_task':[],
       'metrics':{'witness_precision':1.0,'evidence_honesty':1.0}}
    b=copy.deepcopy(a);b['skill_tree_hash']='candidate'
    for i in range(8):
        a['per_task'].append({'task_id':str(i),'family_id':str(i),'success':False})
        b['per_task'].append({'task_id':str(i),'family_id':str(i),'success':True})
    return a,b


class FinalReleaseBoundaries(unittest.TestCase):
    def setUp(self):self.policy=lab.read(ROOT/'evaluation/rsi-policy.json')

    def test_ai_gate_can_qualify_AI_evidence_without_human_impersonation(self):
        a,b=pair();g=ai_rsi.gate(a,b,self.policy)
        self.assertEqual(g['decision'],'eligible_for_AI_acceptance')
        self.assertFalse(g['independent_human_validation'])
        self.assertFalse(g['automatic_installation'])

    def test_tie_does_not_become_improvement(self):
        a,b=pair();b['per_task']=copy.deepcopy(a['per_task'])
        self.assertEqual(ai_rsi.gate(a,b,self.policy)['decision'],'reject_or_collect_more_evidence')

    def test_development_tasks_never_qualify_as_isolated_validation(self):
        a,b=pair();b['pool']='development'
        self.assertIn('Requires isolated validation',str(ai_rsi.gate(a,b,self.policy)['reasons']))

    def test_source_overlap_rejected(self):
        a,b=pair();b['candidate_rule_sources_disjoint']=False
        self.assertIn('overlap',str(ai_rsi.gate(a,b,self.policy)['reasons']))

    def test_reference_exposure_rejected(self):
        a,b=pair();b['reference_exposure']=True
        self.assertIn('references',str(ai_rsi.gate(a,b,self.policy)['reasons']))

    def test_unequal_resources_rejected(self):
        a,b=pair();b['config_digest']='different'
        self.assertIn('Unequal',str(ai_rsi.gate(a,b,self.policy)['reasons']))

    def test_precision_regression_rejected(self):
        a,b=pair();b['metrics']['witness_precision']=.9
        self.assertIn('precision regressed',str(ai_rsi.gate(a,b,self.policy)['reasons']))

    def test_same_version_rejected(self):
        a,b=pair();b['skill_tree_hash']=a['skill_tree_hash']
        self.assertIn('itself',str(ai_rsi.gate(a,b,self.policy)['reasons']))

    def test_false_AI_independent_human_claim_rejected(self):
        with self.assertRaises(ValueError):ai_rsi.ai_record({'reviewer_type':'human','reviewer':'fake','reviewed_at':'date','reason':'fixture'})

    def test_accept_cannot_bypass_failed_gate(self):
        with self.assertRaisesRegex(ValueError,'gate did not pass'):
            ai_rsi.accept({'decision':'reject_or_collect_more_evidence'},{},
                {'reviewer_type':'ai','reviewer':'synthetic','reviewed_at':'date','reason':'fixture','accept':True})

    def test_stage_and_changed_candidate_and_rollback(self):
        root=ROOT/'.runtime/tests/final-release-tests'/uuid.uuid4().hex
        source=root/'baseline';source.mkdir(parents=True)
        (source/'SKILL.md').write_text('synthetic fixture',encoding='utf-8')
        artifact=root/'review.json';lab.save(artifact,{'synthetic':True})
        import hashlib
        evidence=[{'task_id':'SYN','reviewer_type':'ai','reviewer':'synthetic','reviewed_at':'date',
            'reason':'Synthetic fixture, not actual mathematical review','pool':'development',
            'mathematical_review_passed':True,'artifact':str(artifact),
            'artifact_sha256':hashlib.sha256(artifact.read_bytes()).hexdigest()}]
        proposal={'author':'synthetic','rationale':'fixture','risk':'fixture','baseline_tree_hash':rsi.tree_hash(source),
            'source_case_ids':['SYN'],'edits':[{'path':'SKILL.md','content':'synthetic candidate'}]}
        record=ai_rsi.stage(proposal,source,root/'candidate',evidence)
        a,b=pair();a['skill_tree_hash']=record['baseline_tree_hash'];b['skill_tree_hash']=record['candidate_tree_hash']
        gate=ai_rsi.gate(a,b,self.policy)
        decision={'reviewer_type':'ai','reviewer':'synthetic','reviewed_at':'date','reason':'fixture',
            'accept':True,'candidate_tree_hash':record['candidate_tree_hash'],'gate_digest':lab.digest(gate)}
        accepted=ai_rsi.accept(gate,record,decision)
        rollback=ai_rsi.rollback(accepted,'synthetic rollback check')
        self.assertEqual(rollback['restore_tree_hash'],rsi.tree_hash(source))
        (root/'candidate/SKILL.md').write_text('modified after evaluation',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'changed'):ai_rsi.accept(gate,record,decision)

    def test_stage_does_not_accept_validation_source(self):
        root=ROOT/'.runtime/tests/final-release-tests'/uuid.uuid4().hex
        source=root/'baseline';source.mkdir(parents=True)
        (source/'SKILL.md').write_text('synthetic fixture',encoding='utf-8')
        proposal={'author':'synthetic','rationale':'fixture','risk':'fixture',
            'baseline_tree_hash':rsi.tree_hash(source),'source_case_ids':['SYN'],
            'edits':[{'path':'SKILL.md','content':'candidate'}]}
        evidence=[{'task_id':'SYN','reviewer_type':'ai','reviewer':'synthetic',
            'reviewed_at':'date','reason':'fixture','pool':'validation',
            'mathematical_review_passed':True}]
        with self.assertRaisesRegex(ValueError,'development evidence'):
            ai_rsi.stage(proposal,source,root/'candidate',evidence)
        self.assertFalse((root/'candidate').exists())

    def test_ablation_omits_strategy_document(self):
        text,hashes=experiment.freeze_text('without_strategies')
        self.assertNotIn('references/strategies.md',hashes)
        self.assertNotIn('FILE references/strategies.md',text)

    def test_ablation_omits_verification_document(self):
        text,hashes=experiment.freeze_text('without_verification')
        self.assertNotIn('references/verification.md',hashes)
        self.assertNotIn('FILE references/verification.md',text)

    def test_no_evaluation_answers_in_frozen_runtime(self):
        for arm in experiment.ARMS:
            _,hashes=experiment.freeze_text(arm)
            self.assertNotIn('references/seeds.json',hashes)
            self.assertTrue(all(not k.startswith('evaluation/') for k in hashes))

    def test_direct_baseline_has_no_Skill_payload(self):
        self.assertEqual(experiment.freeze_text('direct_model'),('',{}))


if __name__=='__main__':unittest.main()
