"""Build a manifest and ZIP; verify every archived byte without calling APIs."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
EXCLUDED_DIRS={'.git','.runtime','__pycache__','.venv','node_modules','dist'}
PATTERNS=[re.compile(rb'\bsk-[A-Za-z0-9_-]{32,}'),
          re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')]

def selected():
    for p in sorted(ROOT.rglob('*')):
        rel=p.relative_to(ROOT)
        if not p.is_file() or set(rel.parts)&EXCLUDED_DIRS:continue
        if p.suffix in ('.pyc','.pyo','.key','.pem','.tmp'):continue
        if p.name.startswith('.env') and p.name!='.env.example':continue
        if rel.as_posix()=='file-manifest.json':continue
        yield p

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
    target=args.out.resolve()
    if target.is_relative_to(ROOT):raise ValueError('压缩包应输出到项目目录以外，避免自包含。')
    if target.exists():raise FileExistsError('保留现有压缩包，请使用新的输出名称。')
    files=list(selected());suspects=[]
    for p in files:
        if p.suffix.lower() in ('.pdf','.png','.jpg','.jpeg','.zip'):continue
        data=p.read_bytes()
        if any(pattern.search(data) for pattern in PATTERNS):suspects.append(p.relative_to(ROOT).as_posix())
    if suspects:
        print(json.dumps({'secret_pattern_review_required':suspects,'matched_values_not_printed':True},ensure_ascii=False))
        return 2
    manifest={'created_at':datetime.now(timezone.utc).isoformat(),'skill_version':'1.0.0','web_version':'0.1.1',
              'files':{p.relative_to(ROOT).as_posix():{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in files},
              'scan_scope':'High-confidence API-key/private-key patterns and excluded local configuration; not an exhaustive content review.'}
    manifest_path=ROOT/'file-manifest.json';manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    target.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
        for p in files+[manifest_path]:archive.write(p,'condition-archaeologist-project/'+p.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(target) as archive:
        if archive.testzip() is not None:raise ValueError('ZIP CRC verification failed')
        for name,record in manifest['files'].items():
            data=archive.read('condition-archaeologist-project/'+name)
            if len(data)!=record['bytes'] or hashlib.sha256(data).hexdigest()!=record['sha256']:raise ValueError('Archive bytes differ: '+name)
        count=len(archive.namelist())
    report={'archive':str(target),'bytes':target.stat().st_size,'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
            'files':count,'crc_passed':True,'all_manifest_hashes_passed':True,'model_calls':0,
            'pattern_scan_passed':True,'fresh_directory_engineering_check':'pending'}
    report_path=target.with_suffix('.verification.json');report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False));return 0

if __name__=='__main__':sys.exit(main())
