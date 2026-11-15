"""Test mathematical review completeness and provenance, not mathematical truth."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'evaluation'))
import final_score
import lab


class ReviewIntegrity(unittest.TestCase):
    def setUp(self):
        self.run=ROOT/'reports/history-v1.0.0/final-confirmation-12000'
        self.reviews=lab.read(self.run/'AI-mathematical-reviews.json')

    def test_actual_four_subject_reviews_can_be_reaggregated(self):
        result=final_score.score(self.run,self.reviews)
        self.assertEqual(result['metrics']['full_skill']['full_theorem_math_success']['numerator'],4)
        self.assertFalse(result['independent_human'])

    def test_missing_task_review_rejected(self):
        with self.assertRaisesRegex(ValueError,'Every planned'):
            final_score.score(self.run,self.reviews[:-1])

    def test_changed_raw_response_rejected(self):
        self.reviews[0]['source_digest']='changed'
        with self.assertRaisesRegex(ValueError,'Source changed'):final_score.score(self.run,self.reviews)

    def test_changed_input_rejected(self):
        self.reviews[0]['task_digest']='changed'
        with self.assertRaisesRegex(ValueError,'Task changed'):final_score.score(self.run,self.reviews)

    def test_missing_retained_hypothesis_review_rejected(self):
        row=next(r for r in self.reviews if any(i['retained'] for i in r['interventions']))
        item=next(i for i in row['interventions'] if i['retained'])
        item['retained'].pop(next(iter(item['retained'])))
        with self.assertRaisesRegex(ValueError,'Missing retained'):final_score.score(self.run,self.reviews)

    def test_missing_redundancy_proof_review_rejected(self):
        item=next(i for r in self.reviews for i in r['interventions'] if 'preservation_proof' in i)
        del item['preservation_proof']
        with self.assertRaisesRegex(ValueError,'preservation proof'):final_score.score(self.run,self.reviews)

    def test_false_math_finding_lowers_score(self):
        item=next(i for r in self.reviews for i in r['interventions'] if 'target_falsity' in i)
        item['target_falsity']={'pass':False,'reason':'Synthetic mutation: target falsity not established.'}
        result=final_score.score(self.run,self.reviews)
        self.assertEqual(result['metrics']['full_skill']['full_theorem_math_success']['numerator'],3)
        self.assertLess(result['metrics']['full_skill']['witness_precision']['rate'],1)

    def test_text_true_is_not_boolean_review(self):
        self.reviews[0]['objects']['pass']='true'
        with self.assertRaisesRegex(ValueError,'Concrete review'):final_score.score(self.run,self.reviews)

    def test_ai_cannot_be_renamed_independent_human(self):
        self.reviews[0]['independent_human']=True
        with self.assertRaisesRegex(ValueError,'impersonate'):final_score.score(self.run,self.reviews)

    def test_reviewing_does_not_mutate_actual_sources(self):
        raw=list((self.run/'raw').rglob('*.json'))
        before={str(p):p.read_bytes() for p in raw}
        original=copy.deepcopy(self.reviews)
        final_score.score(self.run,self.reviews)
        self.assertEqual(self.reviews,original)
        self.assertEqual(before,{str(p):p.read_bytes() for p in raw})

    def test_truncated_answer_is_failure_and_honesty_unassessed(self):
        job={'task_id':'fixture','arm':'full_skill','kind':'full_theorem','task_digest':'frozen'}
        record={'answer':'{"truncated":','prediction':None}
        review={'task_id':'fixture','arm':'full_skill','family_id':'synthetic','reviewer_type':'ai',
            'reviewer':'test fixture','reviewed_at':'2026-11-05','independent_human':False,
            'source_digest':lab.digest(record),'task_digest':'frozen','status':'invalid_output',
            'runtime_reason':'Synthetic truncated output, not a model experiment.','hypothesis_expected':2}
        with patch.object(final_score.final_experiment,'records',return_value=iter([(job,record,[])])):
            result=final_score.score(self.run,[review])
        row=result['per_task'][0]
        self.assertTrue(row['answer']);self.assertTrue(row['output_failure'])
        self.assertFalse(row['math_success']);self.assertIsNone(row['uncertainty_honest'])

    def test_no_answer_cannot_be_misreported_as_success(self):
        job={'task_id':'fixture','arm':'full_skill','kind':'full_theorem','task_digest':'frozen'}
        review={'task_id':'fixture','arm':'full_skill','family_id':'synthetic','reviewer_type':'ai',
            'reviewer':'test fixture','reviewed_at':'2026-11-05','independent_human':False,
            'source_digest':lab.digest(None),'task_digest':'frozen','status':'no_answer',
            'runtime_reason':'Synthetic transport failure, not a real experiment.'}
        with patch.object(final_score.final_experiment,'records',return_value=iter([(job,None,[])])):
            result=final_score.score(self.run,[review])
        self.assertFalse(result['per_task'][0]['answer'])
        self.assertTrue(result['per_task'][0]['runtime_failure'])
        self.assertEqual(result['metrics']['full_skill']['full_theorem_math_success']['rate'],0)


if __name__=='__main__':unittest.main()
