"""Portable structural check of this Skill package and its local references."""
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]/'skill'
def check():
    errors=[];required=['SKILL.md','agents/openai.yaml','references/judgment-protocol.md',
        'references/output-schema.md','references/review-status.json','references/rsi.md',
        'references/seeds.json','references/strategies.md','references/verification.md',
        'references/riemann-composition.md',
        'scripts/check_witness.py','scripts/self_check.py','scripts/validate_output.py']
    for item in required:
        if not (ROOT/item).is_file():errors.append('missing required file: '+item)
    text=(ROOT/'SKILL.md').read_text(encoding='utf-8') if (ROOT/'SKILL.md').exists() else ''
    if not re.match(r'^---\s*\nname:\s*condition-archaeologist\s*\ndescription:\s*.+?\n---\s*\n',text,re.S):errors.append('invalid Skill frontmatter or name')
    release=json.loads((ROOT/'references/review-status.json').read_text(encoding='utf-8'))
    version=release.get('release_version')
    if not version or f'当前版本：{version}' not in text:errors.append('Skill version disagrees with review record')
    for file in ROOT.rglob('*.md'):
        for ref in re.findall(r'\]\(([^)]+)\)',file.read_text(encoding='utf-8')):
            if not ref.startswith(('https://','http://','#')) and not (file.parent/ref).exists():errors.append(f'{file.relative_to(ROOT)}: broken reference {ref}')
    seeds=json.loads((ROOT/'references/seeds.json').read_text(encoding='utf-8'))
    result={'status':'fail' if errors else 'pass','version':version,'required_files':len(required),
            'reference_tasks':len(seeds) if isinstance(seeds,list) else None,'issues':errors,
            'scope':'File structure, metadata and links only; does not verify mathematics.'}
    return result
def main():
    value=check();print(json.dumps(value,ensure_ascii=False,indent=2));return 0 if value['status']=='pass' else 1
if __name__=='__main__':sys.exit(main())
