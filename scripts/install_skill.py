"""Compare or install the complete runtime with a recoverable backup.

Default is read-only comparison. An existing target is preserved as a sibling
backup; installation does not alter the project source or web runtime.
"""
import argparse
from datetime import datetime,timezone
import hashlib
from pathlib import Path
import shutil
import sys
import uuid

SOURCE=Path(__file__).resolve().parents[1]/'skill'
def files(root):
    return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'} if root.is_dir() else {}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target',type=Path,default=Path.home()/'.codex/skills/condition-archaeologist')
    parser.add_argument('--install',action='store_true');args=parser.parse_args()
    target=args.target.resolve()
    if target==SOURCE.resolve() or target.is_relative_to(SOURCE.resolve()):raise ValueError('安装位置不能覆盖项目源码。')
    before=files(target);source=files(SOURCE)
    changed=sorted(k for k in source.keys()|before.keys() if source.get(k)!=before.get(k))
    print('目标：',target);print('存在差异的文件：',len(changed))
    for name in changed:print(' ',name)
    if not args.install:return 0
    if not changed:print('与完整运行目录一致，无需重装。');return 0
    target.parent.mkdir(parents=True,exist_ok=True)
    stage=target.with_name(target.name+'.staging-'+uuid.uuid4().hex[:8])
    shutil.copytree(SOURCE,stage,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    if files(stage)!=source:raise ValueError('安装副本校验失败，原目录未改动。')
    backup=None
    if target.exists():
        if not target.is_dir():raise ValueError('目标已存在且不是目录。')
        backup=target.with_name(target.name+'.backup-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:6])
        target.rename(backup)
    try:stage.rename(target)
    except Exception:
        if backup is not None and not target.exists():backup.rename(target)
        raise
    print('完整运行目录已安装。备份：',backup or '原位置为空，无旧版')
    print('如客户端未识别新版本，请刷新技能列表或重启客户端。其他Agent可读取整个skill目录。')
    return 0

if __name__=='__main__':sys.exit(main())
