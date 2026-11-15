"""Adapter/HTTP regression tests, NOT mathematical ability scores or live calls."""
import copy
import io
import json
import os
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import server as app

EXAMPLES=json.loads((ROOT/'examples.json').read_text(encoding='utf-8'))

class ReportValidation(unittest.TestCase):
    def setUp(self):self.report=copy.deepcopy(EXAMPLES['ma'])
    def test_four_authored_examples_cover_retained_obligations(self):
        for report in EXAMPLES.values():app.validate_report(report)
    def test_missing_retained_check_is_not_accepted(self):
        self.report['interventions'][0]['retained_checks'].pop()
        with self.assertRaises(app.AppError):app.validate_report(self.report)
    def test_changed_assumption_text_is_not_accepted(self):
        self.report['interventions'][0]['hypotheses'][0]['text']='different'
        with self.assertRaises(app.AppError):app.validate_report(self.report)
    def test_duplicate_intervention_ids_are_not_accepted(self):
        self.report['interventions'][1]['task_id']=self.report['interventions'][0]['task_id']
        with self.assertRaises(app.AppError):app.validate_report(self.report)
    def test_fake_independent_review_is_not_accepted(self):
        self.report['interventions'][0]['evidence'][0].update(kind='ai_reviewed',artifact='invented')
        with self.assertRaises(app.AppError):app.validate_report(self.report)
    def test_removable_cannot_claim_counterexample(self):
        self.report['interventions'][0]['judgment']='removable'
        with self.assertRaises(app.AppError):app.validate_report(self.report)
    def test_statement_issue_cannot_delete_hypothesis(self):
        self.report['interventions'][0]['judgment']='statement_issue'
        with self.assertRaises(app.AppError):app.validate_report(self.report)
    def test_dependency_requires_actual_intervention_id(self):
        self.report['dependency_map'][0]['intervention_ids']=['missing']
        with self.assertRaises(app.AppError):app.validate_report(self.report)
    def test_clarification_must_ask_a_question(self):
        self.report.update(status='clarification',interventions=[],dependency_map=[],questions=[])
        with self.assertRaises(app.AppError):app.validate_report(self.report)
    def test_valid_clarification_does_not_claim_completed_report(self):
        self.report.update(status='clarification',interventions=[],dependency_map=[],questions=['你指控制收敛还是单调收敛？'])
        app.validate_report(self.report)
    def test_incomplete_response_never_becomes_success(self):
        with self.assertRaisesRegex(app.AppError,'未完成'):app.parse_response({'status':'incomplete','output':[]})
    def test_refusal_is_reported(self):
        with self.assertRaisesRegex(app.AppError,'未提供'):app.parse_response({'output':[{'type':'message','content':[{'type':'refusal'}]}]})
    def test_provider_error_is_not_an_answer(self):
        with self.assertRaises(app.AppError):app.parse_response({'error':{'message':'provider error'}})
    def test_valid_response_parsing_uses_actual_report(self):
        value=app.parse_response({'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(self.report)}]}]})
        self.assertEqual(value,self.report)
    def test_malformed_provider_json_is_rejected(self):
        with self.assertRaises(app.AppError):app.parse_response({'output':[{'type':'message','content':[{'type':'output_text','text':'{"truncated":'}]}]})
    def test_invalid_field_types_rejected(self):
        self.report['interventions'][0]['retained_checks']='not an array'
        with self.assertRaises(app.AppError):app.validate_report(self.report)
    def test_real_adapter_wiring_with_explicit_transport_fixture(self):
        """Mock HTTP only; verifies payload and parsing, not live model quality."""
        response={'status':'completed','model':'fixture-model','usage':{'total_tokens':10},
            'output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(self.report)}]}]}
        with patch.dict(os.environ,{'CA_WEB_API_KEY':'fixture-secret','CA_WEB_MODEL':'fixture-model','CA_WEB_API_MODE':'responses'}):
            with patch.object(app,'urlopen',return_value=io.BytesIO(json.dumps(response).encode())) as transport:
                result=app.analyze('完整定理测试内容','数学分析')
        request=transport.call_args.args[0];payload=json.loads(request.data)
        self.assertEqual(payload['text']['format']['schema'],app.REPORT_SCHEMA)
        self.assertFalse(payload['store']);self.assertEqual(payload['max_output_tokens'],12000)
        self.assertIn('FILE SKILL.md',payload['instructions'])
        self.assertNotIn('seeds.json\n',payload['instructions'])
        self.assertEqual(result['meta']['input_theorem'],'完整定理测试内容')
        self.assertFalse(result['meta']['mathematics_certified'])
        self.assertNotIn('fixture-secret',json.dumps(result))
    def test_http_auth_failure_never_echoes_upstream_error_or_key(self):
        with patch.dict(os.environ,{'CA_WEB_API_KEY':'fixture-secret','CA_WEB_MODEL':'fixture-model'}):
            with patch.object(app,'urlopen',side_effect=HTTPError('https://example.org',401,'Unauthorized',{},None)):
                with self.assertRaises(app.AppError) as caught:app.analyze('完整定理测试内容','数学分析')
        self.assertEqual(caught.exception.status,503)
        self.assertNotIn('fixture-secret',str(caught.exception))
    def test_unresolved_requires_real_gap(self):
        i=self.report['interventions'][0];i.update(judgment='unresolved',witness=None,target_failure=None,uncertainties=[])
        with self.assertRaises(app.AppError):app.validate_report(self.report)

class HttpBoundaries(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ,{'CA_WEB_ACCESS_CODE':'test-access','CA_WEB_API_KEY':'','CA_WEB_MODEL':''})
        self.env.start();self.httpd=app.make_server(port=0)
        self.thread=threading.Thread(target=self.httpd.serve_forever,daemon=True);self.thread.start()
        self.base='http://127.0.0.1:'+str(self.httpd.server_port)
        with app.RATE_LOCK:app.RATE.clear()
    def tearDown(self):self.httpd.shutdown();self.httpd.server_close();self.thread.join();self.env.stop()
    def call(self,path,body=None,headers=None):
        req=Request(self.base+path,data=json.dumps(body).encode() if body is not None else None,
            headers={'Content-Type':'application/json',**(headers or {})})
        try:
            with urlopen(req) as r:return r.status,r.read(),r.headers
        except HTTPError as r:return r.code,r.read(),r.headers
    def test_config_exposes_no_credentials(self):
        code,data,_=self.call('/api/config');value=json.loads(data)
        self.assertEqual(code,200);self.assertFalse(value['live_ready']);self.assertTrue(value['access_code_required'])
        self.assertNotIn(b'test-access',data);self.assertNotIn('api_key',value)
    def test_example_explicitly_labeled(self):
        code,data,_=self.call('/api/example?id=ca')
        self.assertEqual(code,200);self.assertEqual(json.loads(data)['mode'],'example')
    def test_input_not_forwarded_without_access_code(self):
        with patch.object(app,'analyze') as analyze:
            code,_,_=self.call('/api/analyze',{'theorem':'some theorem','subject':'数学分析'})
            self.assertEqual(code,401);analyze.assert_not_called()
    def test_cross_origin_request_rejected(self):
        code,_,_=self.call('/api/analyze',{'theorem':'some theorem','subject':'数学分析'},
            {'Origin':'https://unrelated.example','X-Access-Code':'test-access'})
        self.assertEqual(code,403)
    def test_host_header_rejected(self):
        code,_,_=self.call('/api/config',headers={'Host':'unrelated.example'})
        self.assertEqual(code,403)
    def test_server_never_serves_skill_or_settings(self):
        for path in ('/server.py','/.env','/skill/SKILL.md','/../server.py'):
            code,_,_=self.call(path);self.assertEqual(code,404)
    def test_model_unconfigured_is_not_success(self):
        code,data,_=self.call('/api/analyze',{'theorem':'完整的数学定理用于测试','subject':'数学分析'}, {'X-Access-Code':'test-access'})
        self.assertEqual(code,503);self.assertIn('error',json.loads(data))
    def test_rate_limit_prevents_extra_model_calls(self):
        with app.RATE_LOCK:
            import time
            app.RATE['127.0.0.1'].extend([time.monotonic()]*8)
        with patch.object(app,'analyze') as analyze:
            code,_,_=self.call('/api/analyze',{'theorem':'完整的数学定理用于测试','subject':'数学分析'},{'X-Access-Code':'test-access'})
            self.assertEqual(code,429);analyze.assert_not_called()
    def test_invalid_subject_rejected(self):
        code,_,_=self.call('/api/analyze',{'theorem':'完整的数学定理用于测试','subject':'几何'}, {'X-Access-Code':'test-access'})
        self.assertEqual(code,400)
    def test_static_has_csp_and_correct_types(self):
        code,data,headers=self.call('/')
        self.assertEqual(code,200);self.assertIn('frame-ancestors',headers['Content-Security-Policy']);self.assertIn(b'<html',data)
    def test_lan_requires_access_code(self):
        with patch.dict(os.environ,{'CA_WEB_ACCESS_CODE':''}):
            with self.assertRaises(ValueError):app.make_server(host='0.0.0.0',port=0)

if __name__=='__main__':unittest.main()
