"""Offline plan/budget checks with isolated synthetic transport, not math scores."""
import importlib.util
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import uuid

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'evaluation'))
import web_experiment as runner

class WebExperiment(unittest.TestCase):
    def fresh(self):return ROOT/'.runtime/tests'/uuid.uuid4().hex
    def test_prepare_never_calls_provider_and_freezes_eight_jobs(self):
        out=self.fresh()
        with patch.object(runner,'urlopen',side_effect=AssertionError('No live call')):
            result=runner.prepare(out)
        self.assertEqual(result['model_calls'],0)
        self.assertEqual(result['prepared_jobs'],8)
        plan=runner.read(out/'plan.json');claimed=plan.pop('plan_digest')
        self.assertEqual(claimed,runner.digest(plan))

    def test_pair_has_same_inputs_budgets_schema_but_no_skill_in_direct_arm(self):
        out=self.fresh();runner.prepare(out,'paired')
        jobs=runner.read(out/'plan.json')['jobs']
        self.assertEqual(len(jobs),16)
        a,b=jobs[:2]
        for key in ('max_tokens','response_format','model'):self.assertEqual(a['payload'][key],b['payload'][key])
        self.assertEqual(a['payload']['messages'][1],b['payload']['messages'][1])
        self.assertNotIn('FILE SKILL.md',a['payload']['messages'][0]['content'])
        self.assertIn('FILE SKILL.md',b['payload']['messages'][0]['content'])

    def test_cancellation_makes_no_attempt(self):
        out=self.fresh();runner.prepare(out)
        with patch('builtins.input',return_value='cancel'),patch.object(runner,'urlopen',side_effect=AssertionError()):
            result=runner.run(out,1)
        self.assertEqual(result['new_calls'],0)
        self.assertFalse((out/'raw').exists())

    def test_failure_counts_once_and_is_not_retried(self):
        out=self.fresh();runner.prepare(out)
        with patch('builtins.input',return_value='RUN 1'),patch.object(runner.getpass,'getpass',return_value='synthetic-token'),patch.object(runner,'urlopen',side_effect=TimeoutError()) as transport:
            result=runner.run(out,1)
        self.assertEqual(transport.call_count,1)
        self.assertEqual(result['attempted_calls'],1)
        self.assertIsNone(result['math_score'])
        self.assertEqual(runner.read(out/'raw/000.json')['status'],'transport_error')

    def test_plan_change_rejected_before_token_or_transport(self):
        out=self.fresh();runner.prepare(out)
        plan=runner.read(out/'plan.json');plan['model']='modified';runner.save(out/'plan.json',plan)
        with patch.object(runner,'urlopen',side_effect=AssertionError()),self.assertRaises(ValueError):runner.run(out,1)

if __name__=='__main__':unittest.main()
