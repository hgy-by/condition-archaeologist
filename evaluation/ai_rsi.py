"""Opt-in AI-reviewed internal RSI workflow. Never impersonates human acceptance.

Changes are staged from explicitly AI-reviewed development evidence. A candidate
must beat the frozen baseline on isolated tasks under the original numerical
thresholds before AI acceptance. Maintenance release decisions are separate.
"""
import argparse
import shutil
from pathlib import Path

import lab
import rsi


def ai_record(record):
    if record.get('reviewer_type')!='ai' or not record.get('reviewer') or not record.get('reviewed_at'):
        raise ValueError('Actual AI reviewer and date required')
    if not isinstance(record.get('reason'),str) or not record['reason'].strip():
        raise ValueError('Concrete mathematical review reason required')


def stage(proposal,source,destination,evidence):
    source=Path(source).resolve();destination=Path(destination).resolve()
    if destination.exists() or destination==source or source in destination.parents:
        raise ValueError('New isolated candidate directory required')
    if rsi.tree_hash(source)!=proposal.get('baseline_tree_hash'):
        raise ValueError('Baseline changed')
    for key in ('author','rationale','risk'):
        if not proposal.get(key):raise ValueError('Missing '+key)
    records=lab.unique(evidence,'task_id')
    ids=proposal.get('source_case_ids',[])
    if not ids:raise ValueError('Explicit reviewed development sources required')
    for tid in ids:
        record=records.get(tid,{})
        ai_record(record)
        if record.get('pool')!='development' or record.get('mathematical_review_passed') is not True:
            raise ValueError('RSI proposal source must be AI-reviewed development evidence: '+tid)
        artifact=Path(record.get('artifact',''))
        if not artifact.is_file():
            raise ValueError('Missing concrete evidence artifact')
        import hashlib
        if hashlib.sha256(artifact.read_bytes()).hexdigest()!=record.get('artifact_sha256'):
            raise ValueError('Evidence artifact changed')
    edits=proposal.get('edits',[])
    if not edits:raise ValueError('No candidate edits')
    for edit in edits:
        target=(destination/edit['path']).resolve()
        if not target.is_relative_to(destination) or target==destination or not isinstance(edit.get('content'),str) or not edit['content'].strip():
            raise ValueError('Invalid candidate edit')
    shutil.copytree(source,destination,ignore=shutil.ignore_patterns('__pycache__'))
    for edit in edits:
        path=destination/edit['path'];path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(edit['content'],encoding='utf-8')
    return {'status':'AI_candidate_staged_not_accepted','reviewer_type':'ai',
        'baseline_tree_hash':rsi.tree_hash(source),'candidate_tree_hash':rsi.tree_hash(destination),
        'candidate_path':str(destination),'source_case_ids':ids,'evidence_digest':lab.digest(evidence),
        'proposal':proposal,'automatic_installation':False}


def gate(base,candidate,policy):
    reasons=[]
    for report in (base,candidate):
        if report.get('status')!='ai_reviewed_internal':reasons.append('Requires explicitly AI-reviewed internal reports')
        if not report.get('config_digest'):reasons.append('Missing frozen resource configuration')
        if not report.get('skill_tree_hash'):reasons.append('Missing frozen Skill hash')
        if report.get('pool')!='isolated_validation':reasons.append('Requires isolated validation, never development or final heldout')
        if report.get('reference_exposure') is not False:reasons.append('Generator saw references or isolation not established')
        if report.get('candidate_rule_sources_disjoint') is not True:reasons.append('Tasks overlap rule-development sources')
    if base.get('config_digest')!=candidate.get('config_digest'):reasons.append('Unequal model/budget configuration')
    if base.get('skill_tree_hash')==candidate.get('skill_tree_hash'):reasons.append('Same Skill compared to itself')
    comparison=lab.compare(base,candidate,policy['min_bootstrap_samples'])
    if comparison['paired_success_gain']<policy['min_success_gain']:reasons.append('Insufficient improvement')
    if comparison['family_count']<policy['min_family_count']:reasons.append('Insufficient families')
    if policy['require_positive_ci'] and comparison['family_cluster_bootstrap95'][0]<=0:reasons.append('Improvement interval includes zero')
    bp=base.get('metrics',{}).get('witness_precision');cp=candidate.get('metrics',{}).get('witness_precision')
    if not isinstance(bp,(float,int)) or not isinstance(cp,(float,int)):reasons.append('Counterexample precision unmeasured')
    elif cp<bp-policy['max_precision_drop']:reasons.append('Counterexample precision regressed')
    if candidate.get('metrics',{}).get('evidence_honesty')!=1:reasons.append('Evidence honesty failed or unmeasured')
    return {'decision':'reject_or_collect_more_evidence' if reasons else 'eligible_for_AI_acceptance',
        'review_mode':'ai_internal','reasons':reasons,'comparison':comparison,
        'baseline_tree_hash':base.get('skill_tree_hash'),'candidate_tree_hash':candidate.get('skill_tree_hash'),
        'baseline_report_digest':lab.digest(base),'candidate_report_digest':lab.digest(candidate),
        'policy_digest':lab.digest(policy),'automatic_installation':False,
        'independent_human_validation':False}


def accept(gate_record,stage_record,decision):
    ai_record(decision)
    if gate_record.get('decision')!='eligible_for_AI_acceptance':raise ValueError('AI evidence gate did not pass')
    if decision.get('accept') is not True:raise ValueError('AI reviewer has not accepted')
    if decision.get('gate_digest')!=lab.digest(gate_record):raise ValueError('Decision refers to another gate')
    for key in ('baseline_tree_hash','candidate_tree_hash'):
        if gate_record.get(key)!=stage_record.get(key):raise ValueError('Gate evaluated different versions')
    if decision.get('candidate_tree_hash')!=stage_record['candidate_tree_hash'] or rsi.tree_hash(Path(stage_record['candidate_path']))!=stage_record['candidate_tree_hash']:
        raise ValueError('Candidate changed since evaluation')
    return {'status':'AI_internal_candidate_accepted','reviewer_type':'ai',
        'candidate_tree_hash':stage_record['candidate_tree_hash'],
        'rollback_tree_hash':stage_record['baseline_tree_hash'],
        'decision':decision,'gate_digest':lab.digest(gate_record),'automatic_installation':False,
        'claim_scope':'Internal isolated AI-reviewed comparison; not independent human certification or multi-round RSI.'}


def rollback(acceptance,reason):
    if not reason or not acceptance.get('rollback_tree_hash'):raise ValueError('Rollback baseline and reason required')
    return {'status':'rollback_requested','restore_tree_hash':acceptance['rollback_tree_hash'],
        'reason':reason,'automatic_installation':False,
        'instruction':'核对保留基线摘要，再恢复运行文件；保留候选与失败记录。'}


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    q=sub.add_parser('stage')
    for k in ('proposal','source','destination','evidence','out'):q.add_argument('--'+k,required=True,type=Path)
    q=sub.add_parser('gate')
    for k in ('baseline','candidate','policy','out'):q.add_argument('--'+k,required=True,type=Path)
    q=sub.add_parser('accept')
    for k in ('gate','stage','decision','out'):q.add_argument('--'+k,required=True,type=Path)
    q=sub.add_parser('rollback')
    q.add_argument('--acceptance',required=True,type=Path);q.add_argument('--reason',required=True);q.add_argument('--out',required=True,type=Path)
    a=p.parse_args()
    try:
        if a.command=='stage':result=stage(lab.read(a.proposal),a.source,a.destination,lab.read(a.evidence))
        elif a.command=='gate':result=gate(lab.read(a.baseline),lab.read(a.candidate),lab.read(a.policy))
        elif a.command=='accept':result=accept(lab.read(a.gate),lab.read(a.stage),lab.read(a.decision))
        else:result=rollback(lab.read(a.acceptance),a.reason)
        lab.save(a.out,result)
        print(__import__('json').dumps({'status':'written','out':str(a.out),'decision':result.get('decision',result.get('status'))},ensure_ascii=False))
    except (OSError,ValueError,KeyError,TypeError) as error:
        print(__import__('json').dumps({'status':'blocked','reason':str(error)},ensure_ascii=False));return 2
    return 0


if __name__=='__main__':raise SystemExit(main())
