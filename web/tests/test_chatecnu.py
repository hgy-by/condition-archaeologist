"""ChatECNU documented-protocol tests with explicit fixtures, zero live calls."""
import copy
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import server
import launch_chatecnu as launcher

EXAMPLE=json.loads((ROOT/'examples.json').read_text(encoding='utf-8'))['ma']

def response():return {'model':'ecnu-max','choices':[{'finish_reason':'stop','message':{
    'role':'assistant','content':json.dumps(EXAMPLE),'reasoning_content':'Fixture: not used as a final report.'}}],
    'usage':{'prompt_tokens':100,'completion_tokens':200,'total_tokens':300}}

class ChatECNUAdapter(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ,{'CA_WEB_BASE_URL':launcher.BASE_URL,'CA_WEB_API_MODE':'chat_completions',
            'CA_WEB_MODEL':'ecnu-max','CA_WEB_API_KEY':'fixture-secret','CA_WEB_MAX_OUTPUT_TOKENS':'12000'})
        self.env.start()
    def tearDown(self):self.env.stop()
    def test_ecnu_host_selects_documented_protocol_without_extra_setting(self):
        with patch.dict(os.environ,{'CA_WEB_API_MODE':''}):self.assertEqual(server.api_mode(launcher.BASE_URL),'chat_completions')
    def test_unknown_protocol_fails_before_model_call(self):
        with patch.dict(os.environ,{'CA_WEB_API_MODE':'wrong'}):
            with self.assertRaises(server.AppError):server.api_mode(launcher.BASE_URL)
    def test_chat_request_and_final_report_use_documented_fields(self):
        with patch.object(server,'urlopen',return_value=io.BytesIO(json.dumps(response()).encode())) as transport:
            value=server.analyze('连续函数在区间内部存在零点','数学分析')
        req=transport.call_args.args[0];payload=json.loads(req.data)
        self.assertEqual(req.full_url,launcher.BASE_URL+'/chat/completions')
        self.assertEqual(payload['model'],'ecnu-max');self.assertFalse(payload['stream'])
        self.assertEqual(payload['messages'][0]['role'],'system')
        self.assertIn('FILE SKILL.md',payload['messages'][0]['content'])
        self.assertEqual(payload['response_format']['json_schema']['schema'],server.REPORT_SCHEMA)
        self.assertEqual(payload['max_tokens'],12000)
        for k in ('instructions','input','store','max_output_tokens','text'):self.assertNotIn(k,payload)
        self.assertEqual(value['report'],EXAMPLE)
        self.assertEqual(value['meta']['api_mode'],'chat_completions')
        self.assertNotIn('fixture-secret',json.dumps(value));self.assertFalse(value['meta']['mathematics_certified'])
    def test_valid_chat_output(self):self.assertEqual(server.parse_chat_response(response()),EXAMPLE)
    def test_truncated_final_content_never_parsed_as_success(self):
        r=response();r['choices'][0]['finish_reason']='length'
        with self.assertRaisesRegex(server.AppError,'长度上限'):server.parse_chat_response(r)
    def test_reasoning_only_output_never_substituted_for_answer(self):
        r=response();r['choices'][0]['message']['content']=None
        with self.assertRaises(server.AppError):server.parse_chat_response(r)
    def test_non_json_and_code_fences_rejected_without_repair(self):
        r=response();r['choices'][0]['message']['content']='```json\n'+json.dumps(EXAMPLE)+'\n```'
        with self.assertRaises(server.AppError):server.parse_chat_response(r)
    def test_tool_request_not_claimed_as_execution(self):
        r=response();r['choices'][0]['message']['tool_calls']=[{'id':'fixture'}]
        with self.assertRaises(server.AppError):server.parse_chat_response(r)
    def test_content_filter_and_refusal_handled(self):
        r=response();r['choices'][0]['finish_reason']='content_filter'
        with self.assertRaises(server.AppError):server.parse_chat_response(r)
        r=response();r['choices'][0]['message']['refusal']='fixture'
        with self.assertRaises(server.AppError):server.parse_chat_response(r)
    def test_missing_or_multiple_choices_rejected(self):
        for r in ({'choices':[]},{'choices':[{},{}]},{'error':{'message':'secret'}}):
            with self.assertRaises(server.AppError):server.parse_chat_response(r)
    def test_chat_still_rejects_missing_retained_obligation(self):
        r=response();report=copy.deepcopy(EXAMPLE);report['interventions'][0]['retained_checks']=[]
        r['choices'][0]['message']['content']=json.dumps(report)
        with self.assertRaises(server.AppError):server.parse_chat_response(r)
    def test_bad_budget_rejected(self):
        with patch.dict(os.environ,{'CA_WEB_MAX_OUTPUT_TOKENS':'abc'}):
            with self.assertRaises(server.AppError):server.analyze('完整的测试定理','数学分析')
    def test_chat_network_failure_does_not_echo_secret(self):
        with patch.object(server,'urlopen',side_effect=URLError('fixture-secret')):
            with self.assertRaises(server.AppError) as caught:server.analyze('完整的测试定理','数学分析')
        self.assertEqual(caught.exception.status,504);self.assertNotIn('fixture-secret',str(caught.exception))

class TokenPreflight(unittest.TestCase):
    def test_copy_prefix_and_outer_whitespace_handled(self):self.assertEqual(launcher.normalize_token('  Bearer fixture-token  '),'fixture-token')
    def test_invalid_token_input_rejected(self):
        for t in ('','中文说明','token\nsecond','token\tvalue'):
            with self.assertRaises(ValueError):launcher.normalize_token(t)
    def test_models_read_only_request_checks_exact_requested_model(self):
        value={'data':[{'id':'ecnu-max'},{'id':'ecnu-plus'}]}
        with patch.object(launcher,'urlopen',return_value=io.BytesIO(json.dumps(value).encode())) as transport:
            self.assertTrue(launcher.check_models('fixture-secret','ecnu-max'))
        req=transport.call_args.args[0]
        self.assertEqual(req.get_method(),'GET');self.assertEqual(req.full_url,launcher.BASE_URL+'/models')
        self.assertIsNone(req.data)
    def test_no_silent_model_substitution(self):
        with patch.object(launcher,'urlopen',return_value=io.BytesIO(b'{"data":[{"id":"ecnu-plus"}]}')):
            with self.assertRaisesRegex(ValueError,'ecnu-max'):launcher.check_models('fixture-secret','ecnu-max')
    def test_auth_failure_is_actionable_and_redacted(self):
        with patch.object(launcher,'urlopen',side_effect=HTTPError('https://example.org',401,'fixture-secret',{},None)):
            with self.assertRaisesRegex(ValueError,'令牌验证未通过') as caught:launcher.check_models('fixture-secret','ecnu-max')
        self.assertNotIn('fixture-secret',str(caught.exception))
    def test_model_listing_parse_failure_rejected(self):
        for content in (b'not json',b'{"data":"wrong"}',b'{"error":{}}'):
            with patch.object(launcher,'urlopen',return_value=io.BytesIO(content)):
                with self.assertRaises(ValueError):launcher.check_models('fixture-secret','ecnu-max')

if __name__=='__main__':unittest.main()
