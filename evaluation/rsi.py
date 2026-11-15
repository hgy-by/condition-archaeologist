"""Local candidate staging and auditable version records; never automatic installation."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path
import lab

ROOT=Path(__file__).resolve().parent.parent

def tree_hash(path):
    h=hashlib.sha256()
    for p in sorted(Path(path).rglob('*')):
        if p.is_file() and '__pycache__' not in p.parts:
            h.update(p.relative_to(path).as_posix().encode()); h.update(p.read_bytes())
    return h.hexdigest()

def stage(proposal,source,destination):
    if not proposal.get('author') or not proposal.get('rationale') or not proposal.get('risk'): raise ValueError('author, rationale and risk required')
    refs=lab.unique(lab.load('development'),'task_id'); ids=proposal.get('source_case_ids',[])
    if not ids: raise ValueError('reviewed development sources required')
    for tid in ids:
        if tid not in refs or refs[tid]['review']['status']!='approved' or not refs[tid]['gold_eligible']: raise ValueError('unreviewed or non-development RSI source: '+tid)
    src=Path(source).resolve(); dest=Path(destination).resolve()
    if dest.exists() or dest==src or src in dest.parents: raise ValueError('destination must be new and outside source')
    if tree_hash(src)!=proposal.get('baseline_tree_hash'): raise ValueError('baseline has changed')
    edits=proposal.get('edits',[])
    if not edits: raise ValueError('no candidate edits')
    for edit in edits:
        relative=Path(edit['path'])
        if relative.is_absolute() or not (dest in (dest/relative).resolve().parents): raise ValueError('edit escapes candidate')
        if not isinstance(edit.get('content'),str) or not edit['content'].strip(): raise ValueError('empty edit')
    shutil.copytree(src,dest,ignore=shutil.ignore_patterns('__pycache__'))
    for edit in edits:
        p=dest/edit['path']; p.parent.mkdir(parents=True,exist_ok=True); p.write_text(edit['content'],encoding='utf-8')
    record={'status':'staged_not_accepted','baseline_tree_hash':tree_hash(src),'candidate_tree_hash':tree_hash(dest),'source_case_ids':ids,'proposal':proposal,'candidate_path':str(dest)}
    lab.save(dest.parent/(dest.name+'-record.json'),record)
    return record

def main():
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest='cmd',required=True)
    q=sub.add_parser('hash'); q.add_argument('path')
    q=sub.add_parser('stage'); q.add_argument('--proposal',required=True); q.add_argument('--source',required=True); q.add_argument('--destination',required=True)
    q=sub.add_parser('accept'); q.add_argument('--gate',required=True); q.add_argument('--record',required=True); q.add_argument('--signature',required=True); q.add_argument('--out',required=True)
    q=sub.add_parser('rollback'); q.add_argument('--acceptance',required=True); q.add_argument('--reason',required=True); q.add_argument('--out',required=True)
    a=p.parse_args()
    try:
        if a.cmd=='hash': result={'tree_hash':tree_hash(a.path)}
        elif a.cmd=='stage': result=stage(lab.read(a.proposal),a.source,a.destination)
        elif a.cmd=='accept':
            g=lab.read(a.gate); rec=lab.read(a.record); sig=lab.read(a.signature)
            if g['decision']!='eligible_for_human_acceptance': raise ValueError('gate did not pass')
            if g.get('candidate_tree_hash')!=rec['candidate_tree_hash'] or g.get('baseline_tree_hash')!=rec['baseline_tree_hash']: raise ValueError('gate evaluated different skill versions')
            if not sig.get('reviewer') or not sig.get('reviewed_at') or sig.get('accept') is not True: raise ValueError('human acceptance missing')
            if sig.get('candidate_tree_hash')!=rec['candidate_tree_hash'] or tree_hash(rec['candidate_path'])!=rec['candidate_tree_hash']: raise ValueError('candidate changed')
            if sig.get('gate_digest')!=lab.digest(g): raise ValueError('signature must identify exact gate report')
            result={'status':'accepted_for_manual_installation','candidate_tree_hash':rec['candidate_tree_hash'],'rollback_tree_hash':rec['baseline_tree_hash'],'signature':sig,'automatic_installation':False}; lab.save(a.out,result)
        else:
            rec=lab.read(a.acceptance); result={'status':'rollback_requested','restore_tree_hash':rec['rollback_tree_hash'],'reason':a.reason,'instruction':'从保留的基线副本核对哈希后恢复，保留此次记录；不自动覆盖个人安装目录。'}; lab.save(a.out,result)
        print(json.dumps(result,ensure_ascii=False)); return 0
    except (ValueError,KeyError,OSError) as e:
        print(json.dumps({'status':'blocked','reason':str(e)},ensure_ascii=False)); return 2

if __name__=='__main__': raise SystemExit(main())
