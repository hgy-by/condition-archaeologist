"""Maintenance regressions: presentation metadata is not a math certificate."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import server as app

class Maintenance(unittest.TestCase):
    def setUp(self):self.report=json.loads((ROOT/'examples.json').read_text(encoding='utf-8'))['ma']

    def test_joint_only_does_not_count_as_each_single(self):
        i=copy.deepcopy(self.report['interventions'][0])
        i['intervention']['removed']=['H1','H2'];i['judgment']='joint'
        self.report['interventions']=[i]
        c=app.coverage(self.report)
        self.assertEqual(c['analyzed'],0)
        self.assertEqual(c['not_analyzed'],c['total'])

    def test_unresolved_and_missing_are_distinct(self):
        self.report['interventions']=self.report['interventions'][:1]
        self.report['interventions'][0]['judgment']='unresolved'
        c=app.coverage(self.report)
        self.assertEqual((c['analyzed'],c['unresolved'],c['not_analyzed']),(0,1,2))

    def test_statement_issue_does_not_count_all_conditions(self):
        i=self.report['interventions'][0]
        i['judgment']='statement_issue';i['intervention']['removed']=[]
        self.report['interventions']=[i]
        self.assertEqual(app.coverage(self.report)['analyzed'],0)

    def test_empty_evidence_is_rejected(self):
        self.report['interventions'][0]['evidence']=[]
        with self.assertRaises(app.AppError):app.validate_report(self.report)

    def test_whitespace_summary_and_scope_are_rejected(self):
        self.report['summary']=' '
        with self.assertRaises(app.AppError):app.validate_report(self.report)
        self.report['summary']='说明'
        self.report['interventions'][0]['evidence'][0]['scope']=' '
        with self.assertRaises(app.AppError):app.validate_report(self.report)

    def test_budget_selection_is_explicit_in_both_protocols(self):
        for protocol in ('responses','chat_completions'):
            standard=app.build_payload('某定理完整表述','数学分析','ID','model',protocol)
            extended=app.build_payload('某定理完整表述','数学分析','ID','model',protocol,'extended')
            def budget(p):return json.loads(p['input'] if protocol=='responses' else p['messages'][1]['content'])['analysis_budget']
            self.assertEqual(budget(standard)['joint'],1)
            self.assertEqual(budget(extended)['joint'],3)

    def test_unknown_depth_rejected_before_transport(self):
        with self.assertRaises(app.AppError):app.build_payload('定理','数学分析','ID','model','responses','unknown')

if __name__=='__main__':unittest.main()
