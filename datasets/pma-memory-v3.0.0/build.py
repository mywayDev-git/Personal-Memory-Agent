"""Rebuild JSON from this dataset's own definition; no model or sibling dependency."""
import hashlib,json
from pathlib import Path
def build(root=Path(__file__).resolve().parent):
    d=json.loads((root/'definition.json').read_text(encoding='utf-8'));assert d['version']=='pma-memory-v3.0.0'
    for n in ['sources','contexts','questions','coverage','cases','connections']:(root/(n+'.json')).write_text(json.dumps(d[n],ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    m=json.loads((root/'manifest.json').read_text(encoding='utf-8'));m['provenance']['definition_sha256']=hashlib.sha256((root/'definition.json').read_bytes()).hexdigest()
    names=['sources.json','contexts.json','questions.json','coverage.json','cases.json','connections.json','definition.json','lib.mjs','build.py','README.md','editorial_review.json','token_measurements.json']
    m['integrity']=[dict(file=n,sha256=hashlib.sha256((root/n).read_bytes()).hexdigest()) for n in names];(root/'manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n');return m['counts']
if __name__=='__main__':print(json.dumps(build()))
