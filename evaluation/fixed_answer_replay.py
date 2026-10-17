"""Frozen, synthetic-only answer ablations with per-stage durable checkpoints.

No extraction, retrieval, query planning, production mutation, or automatic grading.
Run prepare, then diagnostic; source review is required before expansion.
"""
import argparse
import copy
import hashlib
import json
import time
from dataclasses import replace
from pathlib import Path

import requests

from evaluation.kiwi_compare import model_identity
from evaluation.kiwi_runtime import Meter
from evaluation.query_tree import digest
from pma.answer_review import accepted, validate_review
from pma.errors import AppError
from pma.grounding import claims_supported
from pma.legacy_answer import LegacyAnswerMethods
from pma.models import ANSWER_SCHEMA, LocalModels
from pma.settings import AppSettings
from scripts.memory_agent.validator import schema_errors

BASE = Path('output/memory-validation-v1/full-120')
DEFAULT = Path('output/fixed-answer-replay-v1')
BAD = {'wrong', 'excessive_abstention'}


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    # Windows scanners can briefly hold the destination after a read/write.
    for attempt in range(6):
        try:
            temporary.replace(path)
            break
        except PermissionError:
            if attempt == 5:
                raise
            time.sleep(0.05 * (attempt + 1))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def diagnostic_ids(cases):
    failures = [c['id'] for c in cases if any(a['judgment'] in BAD for a in c['arms'].values())]
    successes = []
    for category in sorted({c['category'] for c in cases}):
        groups = set()
        for c in sorted(cases, key=lambda c: c['id']):
            if c['category'] != category or c['id'] in failures:
                continue
            generated = [a for a in c['arms'].values() if a['generated']]
            if not generated or any(a['judgment'] not in {'correct', 'appropriate_abstention'} for a in generated):
                continue
            group = c['id'].rsplit('-q', 1)[0]
            if group not in groups:
                groups.add(group)
                successes.append(c['id'])
            if len(groups) == 2:
                break
        assert len(groups) == 2, category
    assert len(failures) == 21 and len(successes) == 12
    return dict(failures=sorted(failures), successes=successes,
                cases=sorted(failures + successes))


def prepare(out):
    if (out/'manifest.json').exists():
        verify_manifest(out)
        return
    cases = read(BASE/'case-comparisons.json')
    selection = diagnostic_ids(cases)
    sources = {str(BASE/'case-comparisons.json'): sha(BASE/'case-comparisons.json')}
    inputs = {}
    mappings = []
    baseline_manifest = None
    for c in cases:
        run = Path('output/query-tree-v1') / ('validation-reference-'+c['split']+'-full-1')
        manifest = read(run/'manifest.json')
        baseline_manifest = baseline_manifest or manifest
        assert manifest['models'] == baseline_manifest['models']
        assert manifest['settings'] == baseline_manifest['settings']
        for file, expected in manifest['files'].items():
            assert sha(file) == expected, file
        result_path = run/'results'/(c['id']+'--0.json')
        answer_path = run/'selective_answers'/result_path.name
        result, answers = read(result_path), read(answer_path)
        assert answers['result_sha256'] == sha(result_path)
        for p in (result_path, answer_path, run/'manifest.json', run/'validation-reviews.json'):
            sources[str(p)] = sha(p)
        for label, baseline in answers['arms'].items():
            assert not any(t['stage']=='error' for t in baseline['answer_trace'])
            nodes = result['arms'][label]['selected']
            # Include both actual gateway representations and raw nodes: no unsafe
            # merging merely because the legacy representation happens to match.
            payload = dict(question=result['question'], evidence=nodes,
                           old_evidence=LocalModels.compact_evidence(nodes),
                           new_evidence=LocalModels.answer_evidence(nodes))
            key = digest(payload)
            inputs.setdefault(key, payload)
            mappings.append(dict(case=c['id'], category=c['category'], split=c['split'],
                                 arm=label, input_id=key, diagnostic=c['id'] in selection['cases'],
                                 baseline=baseline, baseline_review=c['arms'][label]['judgment'],
                                 baseline_reason=c['arms'][label]['reason']))
    assert len(mappings) == 884
    code = {str(p):sha(p) for folder in ('pma','scripts','config','schema','prompts')
            for p in Path(folder).rglob('*') if p.is_file() and p.suffix in {'.py','.json','.txt'}}
    for p in (Path(__file__), Path('evaluation/kiwi_runtime.py'), Path('evaluation/kiwi_compare.py')):
        code[str(p)] = sha(p)
    manifest = dict(version=1, sources=sources, code=code, settings=baseline_manifest['settings'],
                    models=baseline_manifest['models'], selection=selection,
                    input_hash=digest(inputs), mapping_hash=digest(mappings),
                    policy='Frozen selected inputs only; no query plan or structured shortcut; no gold sent to models; B/C share draft; C/D share first review; one repair maximum.',
                    evaluator='Fixture-author source review; not independent',
                    legacy_unique_inputs=646, replay_unique_inputs=len(inputs))
    write(out/'inputs.json',inputs)
    write(out/'mappings.json',mappings)
    write(out/'manifest.json',manifest)
    print(json.dumps(dict(cases=len(selection['cases']), diagnostic_inputs=len({m['input_id'] for m in mappings if m['diagnostic']}), all_inputs=len(inputs)),ensure_ascii=False),flush=True)


def verify_manifest(out):
    manifest = read(out/'manifest.json')
    for p, expected in {**manifest['sources'],**manifest['code']}.items():
        assert sha(p)==expected, ('FROZEN_FILE_CHANGED',p)
    assert digest(read(out/'inputs.json'))==manifest['input_hash']
    assert digest(read(out/'mappings.json'))==manifest['mapping_hash']
    return manifest


class TransportStop(RuntimeError):
    pass


class StageFailure(RuntimeError):
    pass


class Journal:
    def __init__(self, path, identity, models):
        self.path, self.models = path, models
        self.data = read(path) if path.exists() else dict(identity=identity, stages={}, attempts=[])
        assert self.data['identity']==identity, 'STAGE_CACHE_IDENTITY_MISMATCH'

    def call(self, name, payload, fn):
        key = digest(payload)
        prior = self.data['stages'].get(name)
        if prior:
            assert prior['input_hash']==key, 'STAGE_INPUT_CHANGED'
            if prior['status']=='ok':
                return copy.deepcopy(prior['value'])
            raise StageFailure(prior['error'])
        meter = Meter(self.models)
        meter.stage = name
        started = time.perf_counter()
        row = dict(stage=name,input_hash=key,status='running')
        # Durable start marker distinguishes an interrupted call from a measured 0s call.
        self.data['in_flight'] = row
        write(self.path,self.data)
        try:
            with meter:
                value = fn()
            row.update(status='ok',value=value)
        except requests.RequestException as exc:
            row.update(status='transport_error',error=type(exc).__name__)
        except (ValueError, AppError) as exc:
            row.update(status='protocol_error',error=str(exc),error_type=type(exc).__name__)
        finally:
            row.update(seconds=time.perf_counter()-started,calls=meter.calls)
            self.data.pop('in_flight',None)
            self.data['attempts'].append(row)
            if row['status'] in {'ok','protocol_error'}:
                self.data['stages'][name]=row
            write(self.path,self.data)
        if row['status']=='transport_error':
            raise TransportStop(name)
        if row['status']!='ok':
            raise StageFailure(row.get('error','UNEXPECTED_STAGE_FAILURE'))
        return copy.deepcopy(value)


def checked_response(response, nodes):
    if schema_errors(response,ANSWER_SCHEMA):
        raise ValueError('INVALID_ANSWER_SCHEMA')
    if (response['status']=='answered') != bool(response['items']):
        raise ValueError('INVALID_ANSWER_STATE')
    ids={n['id'] for n in nodes}
    if any(cid not in ids for i in response['items'] for cid in i['citations']):
        raise ValueError('INVALID_CITATION')
    return response


def evaluate(payload, models, legacy, journal, conditions=('B','C','D')):
    question,nodes=payload['question'],payload['evidence']
    empty=dict(status='insufficient_evidence',items=[])
    result={}
    args=dict(question=question,evidence=nodes)
    try:
        draft=journal.call('draft',args,lambda:checked_response(models.answer(question,copy.deepcopy(nodes)),nodes))
    except StageFailure as exc:
        return {c:dict(status='processing_error',error=str(exc),response=None) for c in conditions}
    attributes=claims_supported(draft['items'],nodes)
    if 'B' in conditions:
        try:
            ok=not draft['items'] or (attributes and journal.call('legacy_verify',dict(**args,draft=draft),lambda:legacy.verify(question,copy.deepcopy(nodes),copy.deepcopy(draft['items']))))
            result['B']=dict(status='complete',response=draft if ok else empty,
                             decision='accepted' if ok else 'verifier_rejected',draft=draft)
        except StageFailure as exc:
            result['B']=dict(status='processing_error',error=str(exc),response=None,draft=draft)
    if not set(conditions)&{'C','D'}:
        return result
    try:
        review=journal.call('review',dict(**args,draft=draft),lambda:validate_review(models.review(question,copy.deepcopy(nodes),copy.deepcopy(draft)),draft,nodes))
        passed=attributes and accepted(review,draft)
    except StageFailure as exc:
        for c in set(conditions)&{'C','D'}:
            result[c]=dict(status='processing_error',error=str(exc),response=None,draft=draft)
        return result
    if 'C' in conditions:
        result['C']=dict(status='complete',response=draft if passed else empty,
                         decision='accepted' if passed else 'verifier_rejected',draft=draft,review=review)
    if 'D' in conditions:
        if passed:
            result['D']=dict(status='complete',response=draft,decision='accepted',draft=draft,review=review)
        else:
            feedback=dict(previous_answer=draft,review=review,attributes_supported=attributes)
            try:
                repaired=journal.call('repair',dict(**args,feedback=feedback),lambda:checked_response(models.answer(question,copy.deepcopy(nodes),feedback=copy.deepcopy(feedback)),nodes))
                repaired_attributes=claims_supported(repaired['items'],nodes)
                second=journal.call('repair_review',dict(**args,draft=repaired),lambda:validate_review(models.review(question,copy.deepcopy(nodes),copy.deepcopy(repaired)),repaired,nodes))
                ok=repaired_attributes and accepted(second,repaired)
                result['D']=dict(status='complete',response=repaired if ok else empty,
                                 decision='repaired' if ok else 'repair_rejected',draft=draft,review=review,
                                 repaired=repaired,repair_review=second)
            except StageFailure as exc:
                result['D']=dict(status='processing_error',error=str(exc),response=None,draft=draft,review=review)
    return result


def run(out, phase):
    manifest=verify_manifest(out)
    settings=AppSettings.from_env()
    settings=replace(settings,answer_validation=True,
                     embedding_revision=manifest['settings']['embedding'].split(':')[1],
                     llm=replace(settings.llm,**manifest['settings']['llm']))
    assert model_identity(settings)==manifest['models'], 'MODEL_IDENTITY_CHANGED'
    models=LocalModels(settings)
    legacy=LocalModels(replace(settings,answer_validation=False))
    mappings=read(out/'mappings.json')
    conditions=('B','C','D')
    if phase=='regression':
        decision=read(out/'diagnostic-decision.json')
        assert decision['eligible'] and decision['selected'] in conditions
        conditions=(decision['selected'],)
    selected=[m for m in mappings if phase=='regression' or m['diagnostic']]
    inputs=read(out/'inputs.json')
    ids=list(dict.fromkeys(m['input_id'] for m in selected))
    for i,key in enumerate(ids):
        journal=Journal(out/'stages'/(key+'.json'),dict(manifest=digest(manifest),input_id=key),models)
        # Preserve an interrupted call marker before retry; its cost is unknown.
        if journal.data.get('in_flight'):
            journal.data.setdefault('interrupted',[]).append(journal.data.pop('in_flight'))
            write(journal.path,journal.data)
        result=evaluate(inputs[key],models,legacy,journal,conditions)
        dest=out/'results'/(key+'.json')
        prior=read(dest) if dest.exists() else dict(input_id=key,conditions={})
        for c,value in result.items():
            if c in prior['conditions']:
                assert prior['conditions'][c]==value, 'COMPLETED_RESULT_CHANGED'
            prior['conditions'][c]=value
        write(dest,prior)
        names=sorted({m['case'] for m in selected if m['input_id']==key})
        print(i+1,'/',len(ids),','.join(names),key[:10],{c:v['status'] for c,v in result.items()},flush=True)
    write(out/(phase+'-completion.json'),dict(inputs=len(ids),arm_results=len(selected),conditions=conditions,status='awaiting_source_review'))


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('phase',choices=['prepare','diagnostic','regression'])
    p.add_argument('--output',type=Path,default=DEFAULT)
    a=p.parse_args()
    personal=AppSettings.from_env().data_dir.resolve()
    output=a.output.resolve()
    assert not (output==personal or output.is_relative_to(personal) or personal.is_relative_to(output)), 'PERSONAL_DATA_OVERLAP'
    if a.phase=='prepare':
        prepare(a.output)
    else:
        run(a.output,a.phase)


if __name__=='__main__':
    main()
