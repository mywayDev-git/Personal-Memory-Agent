"""Re-review frozen diagnostic drafts. Previous outputs are never overwritten."""
import argparse
import copy
from dataclasses import replace
from pathlib import Path

from evaluation.fixed_answer_replay import read,write,sha,digest,verify_manifest,Journal,evaluate
from evaluation.kiwi_compare import model_identity
from evaluation.review_semantic_candidate import SemanticReviewModels
from pma.models import LocalModels
from pma.settings import AppSettings

SOURCE=Path('output/fixed-answer-replay-v1/run-1')
OUTPUT=Path('output/fixed-answer-replay-v1/semantic-review-1')


def prepare(source,out):
    if (out/'manifest.json').exists():
        return verify_manifest(out)
    old=verify_manifest(source)
    assert read(source/'diagnostic-completion.json')['inputs']==195
    inputs,mappings=read(source/'inputs.json'),read(source/'mappings.json')
    manifest=copy.deepcopy(old)
    manifest['version']=2
    manifest['comparison_source']=str(source)
    manifest['changed_stage']='review and repair_review only; original draft and legacy verification imported exactly'
    manifest['sources'].update({str(p):sha(p) for p in (source/'manifest.json',source/'reviews.json',source/'diagnostic-decision.json')})
    for folder in ('stages','results'):
        manifest['sources'].update({str(p):sha(p) for p in (source/folder).glob('*.json')})
    for p in (Path(__file__),Path('evaluation/review_semantic_candidate.py')):
        manifest['code'][str(p)]=sha(p)
    write(out/'inputs.json',inputs)
    write(out/'mappings.json',mappings)
    write(out/'manifest.json',manifest)
    # Existing exact-response source reviews remain valid; no new answers are inferred.
    write(out/'reviews.json',read(source/'reviews.json'))
    return manifest


def run(source,out):
    manifest=verify_manifest(out)
    assert Path(manifest['comparison_source']).resolve()==source.resolve()
    settings=AppSettings.from_env()
    settings=replace(settings,answer_validation=True,
        embedding_revision=manifest['settings']['embedding'].split(':')[1],
        llm=replace(settings.llm,**manifest['settings']['llm']))
    assert model_identity(settings)==manifest['models']
    models=SemanticReviewModels(settings)
    legacy=LocalModels(replace(settings,answer_validation=False))
    inputs=read(out/'inputs.json')
    mappings=[m for m in read(out/'mappings.json') if m['diagnostic']]
    ids=list(dict.fromkeys(m['input_id'] for m in mappings))
    for i,key in enumerate(ids):
        journal=Journal(out/'stages'/(key+'.json'),dict(manifest=digest(manifest),input_id=key),models)
        if not journal.path.exists():
            old=read(source/'stages'/(key+'.json'))
            journal.data['stages']={name:copy.deepcopy(old['stages'][name]) for name in ('draft','legacy_verify') if name in old['stages']}
            journal.data['imported_stages']=list(journal.data['stages'])
            journal.data['imported_from']=dict(path=str(source/'stages'/(key+'.json')),sha256=sha(source/'stages'/(key+'.json')))
            write(journal.path,journal.data)
        if journal.data.get('in_flight'):
            journal.data.setdefault('interrupted',[]).append(journal.data.pop('in_flight'))
            write(journal.path,journal.data)
        result=evaluate(inputs[key],models,legacy,journal)
        assert result['B']==read(source/'results'/(key+'.json'))['conditions']['B']
        for condition in 'BCD':
            assert result[condition]['draft']==read(source/'results'/(key+'.json'))['conditions'][condition]['draft']
        dest=out/'results'/(key+'.json')
        value=dict(input_id=key,conditions=result)
        if dest.exists():assert read(dest)==value
        else:write(dest,value)
        print(i+1,'/',len(ids),next(m['case'] for m in mappings if m['input_id']==key),{c:v['status'] for c,v in result.items()},flush=True)
    write(out/'diagnostic-completion.json',dict(inputs=len(ids),arm_results=len(mappings),conditions=['B','C','D'],status='awaiting_source_review'))


if __name__=='__main__':
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('phase',choices=['prepare','run'])
    p.add_argument('--source',type=Path,default=SOURCE)
    p.add_argument('--output',type=Path,default=OUTPUT)
    a=p.parse_args()
    assert a.output.resolve()!=a.source.resolve()
    personal=AppSettings.from_env().data_dir.resolve()
    assert not(a.output.resolve().is_relative_to(personal) or personal.is_relative_to(a.output.resolve()))
    if a.phase=='prepare':prepare(a.source,a.output)
    else:run(a.source,a.output)
