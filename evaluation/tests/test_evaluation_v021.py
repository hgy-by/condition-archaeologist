"""Synthetic transport/review fixtures; never model capability scores."""
import copy
from contextlib import contextmanager
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import uuid

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'evaluation'))
import compare_models as runner
import model_transport as transport
import review_results as review
import lab


@contextmanager
def scratch():
    path=ROOT/'.runtime/tests/test-evaluation-v021'/uuid.uuid4().hex
    path.mkdir(parents=True)
    yield path


def job():
    return {'task_id':'SYN-1','arm':'full_skill','kind':'uncertainty',
            'task':{'task_id':'SYN-1','request':'synthetic fixture'},'task_digest':'fixture'}


def response(status='completed'):
    pred={'task_id':'SYN-1','interpretation':'synthetic','missing_information':[],
          'conditional_analysis':[],'questions':[],'limitations':[]}
    return {'http_status':200,'elapsed_seconds':1,'error':None,
            'raw':json.dumps({'status':status,'model':'synthetic',
                'output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(pred)}]}]})}


class EvaluationReliability(unittest.TestCase):
    def test_reference_field_rejected(self):
        with self.assertRaises(ValueError):runner.safe_task({'task_id':'SYN','reference':{'answer':'secret'}})

    def test_path_traversal_rejected(self):
        with self.assertRaises(ValueError):runner.safe_task({'task_id':'../SYN'})

    def test_truncation_not_structural_success(self):
        result=runner.assess_response(response('incomplete'),job())
        self.assertIn('Response did not complete',result['structure_errors'][0])

    def test_sse_complete_response(self):
        event={'type':'response.completed','response':json.loads(response()['raw'])}
        data,answer=transport.parse_response('data: '+json.dumps(event)+'\n\n')
        self.assertEqual(data['status'],'completed');self.assertEqual(json.loads(answer)['task_id'],'SYN-1')

    def test_mismatched_output_task_rejected(self):
        j=job();j['task_id']='SYN-OTHER'
        result=runner.assess_response(response(),j)
        self.assertIsNone(result['prediction']);self.assertIn('Task ID',result['parse_error'])

    def test_gateway_failure_recoverable(self):
        self.assertTrue(runner.recoverable({'http_status':522,'raw':None,'answer':None,'prediction':None}))

    def test_empty_200_recoverable(self):
        self.assertTrue(runner.recoverable({'http_status':200,'raw':'\n','answer':None,'prediction':None}))

    def test_bad_math_or_invalid_json_answer_never_recovered(self):
        self.assertFalse(runner.recoverable({'http_status':200,'raw':'body','answer':'incorrect math','prediction':None}))
        self.assertFalse(runner.recoverable({'http_status':401,'raw':None,'answer':None,'prediction':None}))

    def test_duplicate_jobs_fail_before_creating_run(self):
        with scratch() as root:
            task={'kind':'uncertainty','task':{'task_id':'SYN-1','request':'fixture'},'arms':['full_skill']}
            lab.save(root/'in.json',[task,task])
            with self.assertRaisesRegex(ValueError,'Duplicate'):runner.prepare(root/'in.json',root/'run')
            self.assertFalse((root/'run').exists())

    def test_existing_output_not_called_again(self):
        with scratch() as root:
            path=root/'raw/full_skill/SYN-1/attempt-1.json';lab.save(path,{'fixture':'existing'})
            with patch.object(transport,'request_once') as call:
                self.assertEqual(runner.call(job(),root,{}),{'fixture':'existing'});call.assert_not_called()

    def test_changed_frozen_jobs_block_execution(self):
        with scratch() as root:
            lab.save(root/'jobs.json',[]);lab.save(root/'configuration.json',{'jobs_digest':'wrong'})
            with self.assertRaisesRegex(ValueError,'Frozen'):runner.execute(root)

    def test_both_arms_receive_same_label_contract(self):
        with scratch() as root:
            task={'kind':'intervention','task':{'task_id':'SYN-1','statement':'synthetic'},'arms':['direct_model','full_skill']}
            lab.save(root/'in.json',[task])
            with patch.object(transport,'settings',return_value=({'model':'synthetic'},'https://example.invalid/v1/responses','fixture')):
                runner.prepare(root/'in.json',root/'run')
            jobs=lab.read(root/'run/jobs.json')
            self.assertTrue(jobs[1]['instructions'].startswith(jobs[0]['instructions']))
            for label in lab.LABELS:self.assertIn(label,jobs[0]['instructions'])

    def review_fixture(self,root):
        j=job();lab.save(root/'jobs.json',[j])
        result=runner.assess_response(response(),j);result['attempt']=1
        lab.save(root/'raw/full_skill/SYN-1/attempt-1.json',result)
        review.render(root)
        template=lab.read(root/'human-review-template.json')
        template['reviewer']='synthetic_fixture';template['reviewed_at']='fixture'
        return template

    def test_pending_review_not_promoted(self):
        with scratch() as root:
            template=self.review_fixture(root);lab.save(root/'review.json',template)
            result=review.import_reviews(root,root/'review.json')
            self.assertEqual(result['decision_counts']['待审核'],1)
            self.assertFalse(result['automatic_formal_adjudication']);self.assertIsNone(result['numeric_rubric_score'])

    def test_changed_response_invalidates_review(self):
        with scratch() as root:
            template=self.review_fixture(root);lab.save(root/'review.json',template)
            lab.save(root/'raw/full_skill/SYN-1/attempt-1.json',{'modified':True})
            with self.assertRaisesRegex(ValueError,'Response changed'):review.import_reviews(root,root/'review.json')

    def test_unknown_review_id_rejected(self):
        with scratch() as root:
            template=self.review_fixture(root);template['records'][0]['review_id']='OTHER'
            lab.save(root/'review.json',template)
            with self.assertRaisesRegex(ValueError,'unknown'):review.import_reviews(root,root/'review.json')

    def test_duplicate_review_import_preserves_evidence(self):
        with scratch() as root:
            template=self.review_fixture(root);lab.save(root/'review.json',template)
            review.import_reviews(root,root/'review.json')
            with self.assertRaises(FileExistsError):review.import_reviews(root,root/'review.json')


if __name__=='__main__':unittest.main()
