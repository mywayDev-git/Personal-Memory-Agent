"""Rebuild only this dataset from its self-contained authored definition."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def build(root=ROOT):
    d=json.loads((root/'definition.json').read_text(encoding='utf-8'))
    assert d['version']=='pma-memory-v2.0.0'
    for n in ['inputs','annotations','sources','contexts','questions','coverage','cases','connections','sentence_inventory']:
        (root/(n+'.json')).write_text(json.dumps(d[n],ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    m=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    m['provenance']['definition_sha256']=hashlib.sha256((root/'definition.json').read_bytes()).hexdigest()
    m['integrity']=[dict(file=n,sha256=hashlib.sha256((root/n).read_bytes()).hexdigest()) for n in ['inputs.json','annotations.json','sources.json','contexts.json','questions.json','coverage.json','cases.json','connections.json','sentence_inventory.json','definition.json','lib.mjs','build.py','README.md','coverage_review.md']]
    (root/'manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    return dict(sources=len(d['sources']['records']),questions=len(d['questions']['questions']),model_calls=0)
if __name__=='__main__':print(json.dumps(build()))
