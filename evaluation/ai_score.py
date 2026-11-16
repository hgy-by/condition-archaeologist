"""Aggregate explicitly authored AI mathematical reviews; never auto-prove math.

This scorer does NOT turn a matching reference string into a valid witness.
The reviewing AI must supply per-obligation findings and reasons. Source hashes
bind those findings to immutable responses. Internal results cannot enter the
independent-review RSI gate in lab.py.
"""
import argparse
import hashlib
import json
from pathlib import Path

import lab


def content_hashes(content):
    """Hash exact bytes and equivalent LF/CRLF text representations.

    Historical review records were produced on Windows while CI evaluates
    them on Linux.  CRLF versus LF is a transport detail, so it must not make
    an otherwise unchanged model response look edited.  All other bytes,
    including content changes, remain covered by the digest.
    """
    lf=content.replace(b'\r\n',b'\n').replace(b'\r',b'\n')
    variants={content,lf,lf.replace(b'\n',b'\r\n')}
    return {hashlib.sha256(value).hexdigest() for value in variants}


def file_hash_matches(path,expected):
    return expected in content_hashes(path.read_bytes())


def finding(value, name):
    if not isinstance(value, dict) or type(value.get('valid')) is not bool or not isinstance(value.get('reason'), str) or not value['reason'].strip():
        raise ValueError('Missing mathematical review: '+name)
    return value['valid']


def source_path(root, relative):
    candidate = (root/relative).resolve()
    if not candidate.is_relative_to(root.resolve()):
        raise ValueError('Source path escapes experiment')
    return candidate


def evaluate(cases, reviews, run):
    cc = lab.unique(cases, 'task_id')
    rr = lab.unique(reviews, 'task_id')
    if not cc or set(cc) != set(rr):
        raise ValueError('Every task needs exactly one explicit AI review')
    per = []
    for tid, case in cc.items():
        review = rr[tid]
        if review.get('reviewer_type') != 'ai' or not review.get('reviewer') or not review.get('reviewed_at'):
            raise ValueError('AI reviewer provenance required')
        if review.get('independent') is not False:
            raise ValueError('This controller review cannot claim independent human review')
        if review.get('case_digest') != lab.digest(case):
            raise ValueError('Reference changed since review: '+tid)
        path = source_path(run, review['source_file'])
        if not file_hash_matches(path,review.get('source_sha256')):
            raise ValueError('Response changed since review: '+tid)
        record = lab.read(path)
        pred = record.get('prediction')
        if not pred or pred.get('task_id') != tid or record.get('arm') != review.get('arm'):
            raise ValueError('Missing or mismatched prediction: '+tid)
        if review.get('prediction_digest') != lab.digest(pred):
            raise ValueError('Prediction changed since review: '+tid)
        expected_ids = {h['id'] for h in case['hypotheses']}
        removed = set(case['intervention']['removed'])
        retained = expected_ids-removed
        if set(review.get('retained', {})) != retained:
            raise ValueError('Every retained hypothesis needs mathematical review: '+tid)
        replacement = case['intervention'].get('replacement')
        replacement_ids = {replacement['id']} if replacement else set()
        if set(review.get('replacement', {})) != replacement_ids:
            raise ValueError('Replacement review incomplete: '+tid)
        checks = [finding(review[k], k) for k in ('objects', 'intervention', 'argument', 'evidence_honesty', 'hypothesis_alignment')]
        checks += [finding(v, 'retained '+k) for k,v in review['retained'].items()]
        checks += [finding(v, 'replacement '+k) for k,v in review['replacement'].items()]
        label = pred.get('judgment')
        if label not in lab.LABELS:
            raise ValueError('Invalid output label: '+tid)
        ce = label in ('indispensable', 'joint', 'statement_issue')
        if type(review.get('witness_claimed')) is not bool or review['witness_claimed'] != ce:
            raise ValueError('Witness accounting inconsistent: '+tid)
        if ce:
            if set(review.get('deleted', {})) != removed:
                raise ValueError('Deleted condition checks incomplete: '+tid)
            checks += [finding(v, 'deleted '+k) for k,v in review['deleted'].items()]
            checks.append(finding(review.get('target'), 'target falsity'))
        elif review.get('deleted') or review.get('target') is not None:
            raise ValueError('Non-counterexample must not claim a target failure')
        else:
            checks.append(finding(review.get('preservation_proof'), 'conclusion preservation'))
        dependency = review.get('dependency_report')
        if not isinstance(dependency, dict) or type(dependency.get('complete')) is not bool or not dependency.get('reason'):
            raise ValueError('Dependency reporting review required')
        math_valid = all(checks)
        classification_valid = label == case['reference']['judgment']
        per.append({'task_id':tid,'family_id':case['family_id'],'subject':case['subject'],
                    'predicted':label,'reference':case['reference']['judgment'],
                    'mathematical_validity':math_valid,
                    'success':math_valid and classification_valid,
                    'classification_valid':classification_valid,
                    'witness_claimed':ce,'witness_valid':ce and math_valid,
                    'reference_has_counterexample':case['reference']['judgment'] in ('indispensable','joint'),
                    'dependency_report_complete':dependency['complete'],
                    'structure_pass':record.get('structure_errors') == [],
                    'notes':review.get('notes',[])})
    def fraction(a,b): return {'numerator':a,'denominator':b,'rate':a/b if b else None}
    n=len(per)
    claims=sum(p['witness_claimed'] for p in per)
    valid=sum(p['witness_valid'] for p in per)
    available=sum(p['reference_has_counterexample'] for p in per)
    return {'status':'ai_reviewed_internal','reviewer_type':'ai','independent':False,
            'reference_gold_promoted':False,'dataset_digest':lab.digest(cases),
            'review_digest':lab.digest(reviews),'splits':sorted({c['split'] for c in cases}),
            'metrics':{'tasks':n,
                'mathematical_validity':fraction(sum(p['mathematical_validity'] for p in per),n),
                'strict_intervention_success':fraction(sum(p['success'] for p in per),n),
                'witness_precision':fraction(valid,claims),
                'counterexample_discovery':fraction(sum(p['witness_valid'] and p['reference_has_counterexample'] for p in per),available),
                'joint_intervention_success':fraction(sum(p['success'] for p in per if p['reference']=='joint'),sum(p['reference']=='joint' for p in per)),
                'removable_class_success':fraction(sum(p['success'] for p in per if p['reference']=='removable'),sum(p['reference']=='removable' for p in per)),
                'implied_class_success':fraction(sum(p['success'] for p in per if p['reference']=='implied'),sum(p['reference']=='implied' for p in per)),
                'hypothesis_extraction_from_raw_text':None,
                'strict_blind_transfer':None,'full_theorem_success':None,'usd':None},
            'per_task':per,
            'limitations':['Controller AI sees references and group identity; not an independent human or blind judge.',
                'Input hypotheses were supplied; alignment is not end-to-end extraction accuracy.',
                'Single interventions do not validate a complete dependency map or complete-theorem workflow.',
                'Per-task mathematical reasons are AI judgments, not formal proofs. No automatic RSI promotion.']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases',required=True,type=Path)
    parser.add_argument('--reviews',required=True,type=Path)
    parser.add_argument('--run',required=True,type=Path)
    parser.add_argument('--out',required=True,type=Path)
    args=parser.parse_args()
    try:
        result=evaluate(lab.rows(args.cases),lab.read(args.reviews),args.run)
        lab.save(args.out,result)
        print(json.dumps({'status':result['status'],'output':str(args.out),'metrics':result['metrics']},ensure_ascii=False))
    except (OSError,ValueError,KeyError,TypeError) as error:
        print(json.dumps({'status':'blocked','reason':str(error)},ensure_ascii=False))
        return 2
    return 0


if __name__=='__main__':
    raise SystemExit(main())
