"""Guard evidence boundaries and transport recovery; fixtures are not capability results."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'evaluation'))
import ai_score
import compare_models as runner
import lab
import model_transport as transport


class AIReviewBoundary(unittest.TestCase):
    def setUp(self):
        self.report=ROOT/'reports/history-v1.0.0/ai-review-v0.2.2'
        self.run=ROOT/'reports/history-v1.0.0/validation-balanced-v0.2.1-2026-11-05'
        self.cases=lab.read(self.report/'cases.json')
        self.reviews=lab.read(self.report/'full_skill-reviews.json')

    def evaluate(self):
        return ai_score.evaluate(self.cases,self.reviews,self.run)

    def test_authored_ai_reviews_remain_internal(self):
        score=self.evaluate()
        self.assertEqual(score['status'],'ai_reviewed_internal')
        self.assertFalse(score['reference_gold_promoted'])
        self.assertFalse(score['independent'])

    def test_human_impersonation_rejected(self):
        self.reviews[0]['reviewer_type']='human'
        with self.assertRaisesRegex(ValueError,'AI reviewer'):self.evaluate()

    def test_independence_impersonation_rejected(self):
        self.reviews[0]['independent']=True
        with self.assertRaisesRegex(ValueError,'independent human'):self.evaluate()

    def test_edited_source_invalidates_review(self):
        self.reviews[0]['source_sha256']='changed'
        with self.assertRaisesRegex(ValueError,'Response changed'):self.evaluate()

    def test_source_hash_ignores_platform_line_endings_but_detects_content_changes(self):
        lf=b'{"answer":"same"}\n'
        crlf=b'{"answer":"same"}\r\n'
        changed=b'{"answer":"changed"}\r\n'
        windows_digest=hashlib.sha256(crlf).hexdigest()
        self.assertIn(windows_digest,ai_score.content_hashes(lf))
        self.assertIn(windows_digest,ai_score.content_hashes(crlf))
        self.assertNotIn(windows_digest,ai_score.content_hashes(changed))

    def test_edited_reference_invalidates_review(self):
        self.cases[0]['statement']+=' changed'
        with self.assertRaisesRegex(ValueError,'Reference changed'):self.evaluate()

    def test_changed_prediction_digest_rejected(self):
        self.reviews[0]['prediction_digest']='changed'
        with self.assertRaisesRegex(ValueError,'Prediction changed'):self.evaluate()

    def test_missing_retained_obligation_rejected(self):
        self.reviews[0]['retained'].pop(next(iter(self.reviews[0]['retained'])))
        with self.assertRaisesRegex(ValueError,'Every retained'):self.evaluate()

    def test_missing_replacement_obligation_rejected(self):
        r=next(r for r in self.reviews if r['task_id']=='CA09');r['replacement']={}
        with self.assertRaisesRegex(ValueError,'Replacement review'):self.evaluate()

    def test_unexplained_boolean_is_not_math_review(self):
        self.reviews[0]['argument']={'valid':True,'reason':''}
        with self.assertRaisesRegex(ValueError,'Missing mathematical review'):self.evaluate()

    def test_invalid_retained_condition_fails_score(self):
        r=self.reviews[0];r['retained'][next(iter(r['retained']))]={'valid':False,'reason':'Deliberate failing obligation fixture'}
        score=self.evaluate()
        self.assertFalse(score['per_task'][0]['success'])

    def test_alternative_valid_witnesses_not_string_matched(self):
        # Actual recorded RA07 answers use different spaces and both were reviewed.
        direct=lab.read(self.report/'direct_model-reviews.json')
        self.reviews=direct
        score=self.evaluate()
        row=next(r for r in score['per_task'] if r['task_id']=='RA07')
        self.assertTrue(row['witness_valid'])

    def test_missing_task_cannot_disappear_from_denominator(self):
        self.reviews.pop()
        with self.assertRaisesRegex(ValueError,'Every task'):self.evaluate()

    def test_path_escape_rejected(self):
        self.reviews[0]['source_file']='../../../../outside.json'
        with self.assertRaisesRegex(ValueError,'escapes'):self.evaluate()

    def test_ai_score_never_enters_formal_rsi_gate(self):
        score=self.evaluate()
        decision=lab.gate(score,score,{})
        self.assertEqual(decision['decision'],'reject_or_collect_more_evidence')
        self.assertFalse(decision['automatic_promotion'])


class ResponseFailures(unittest.TestCase):
    def job(self):return {'task_id':'SYN','arm':'full_skill','kind':'full_theorem'}

    def result(self,typ):
        return {'http_status':200,'raw':json.dumps({'error':{'type':typ,'message':'fixture'}})}

    def test_transient_error_envelope_is_not_math_answer(self):
        result=runner.assess_response(self.result('service_unavailable_error'),self.job())
        self.assertIsNone(result['prediction'])
        self.assertTrue(runner.recoverable(result))

    def test_auth_envelope_not_recoverable(self):
        result=runner.assess_response(self.result('authentication_error'),self.job())
        self.assertFalse(runner.recoverable(result))

    def test_arbitrary_error_not_recoverable(self):
        result=runner.assess_response(self.result('made_up_error'),self.job())
        self.assertFalse(runner.recoverable(result))

    def test_actual_answer_never_retried_for_error_tag(self):
        result={'http_status':200,'provider_error_type':'server_error','answer':'Some answer','prediction':None}
        self.assertFalse(runner.recoverable(result))

    def test_non_object_provider_json_cleanly_rejected(self):
        result=runner.assess_response({'http_status':200,'raw':'[]'},self.job())
        self.assertIsNone(result['prediction'])
        self.assertIn('JSON object',result['parse_error'])

    def test_ai_evidence_requires_traceable_artifact(self):
        pred=lab.read(ROOT/'reports/history-v1.0.0/ai-review-v0.2.2/../validation-balanced-v0.2.1-2026-11-05/raw/full_skill/MA08/attempt-1.json')['prediction']
        pred['evidence']=[{'kind':'ai_reviewed','artifact':None,'scope':'fixture'}]
        self.assertTrue(any('artifact required' in e for e in runner.validate_output.validate(pred)))
        pred['evidence'][0]['artifact']='real-review.json'
        self.assertEqual(runner.validate_output.validate(pred),[])


if __name__=='__main__':unittest.main()
