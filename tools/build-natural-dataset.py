"""Compile authored context cases + pinned v1 controls. No models or DB writes."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
from natural_cases import CASES

VERSION="pma-long-v2.0.0"
STAMP="2026-11-03T12:00:00+09:00"

def sha(value):
    return hashlib.sha256(value if isinstance(value,bytes) else value.encode("utf-8")).hexdigest()

def u16(text,offset):
    return len(text[:offset].encode("utf-16-le"))//2

def build(root):
    base=root/"datasets"/"pma-long-v1.0.1"
    dest=root/"datasets"/VERSION
    dest.mkdir(parents=True,exist_ok=True)
    read=lambda p:json.loads(p.read_text(encoding="utf-8"))
    previous={k:read(base/(k+".json")) for k in ["manifest","sources","contexts","questions","inputs","annotations","import_plans"]}
    for item in previous["manifest"]["integrity"]:
        assert sha((base/item["file"]).read_bytes())==item["sha256"],item["file"]
    sources=copy.deepcopy(previous["sources"]["records"])
    contexts=copy.deepcopy(previous["contexts"]["contexts"])
    questions=copy.deepcopy(previous["questions"]["questions"])
    inputs=copy.deepcopy(previous["inputs"])
    sentence_rows=[]
    connections=[]
    annotations=[dict(id=a["id"],profile=a["profile"],family_id=a["family"],case_kind="legacy_control",
        record_ids=[a["id"]],question_ids=[a["id"]+":Q1"],gold_status="AUTHOR_DRAFT",
        upstream_annotation=a) for a in previous["annotations"]]
    cases=[]
    family_rows=copy.deepcopy(previous["manifest"]["families"])

    def new_context(cid,family,owner,refs,profile):
        return dict(id=cid,family_id=family,split="development",now=STAMP,actor_id=owner,
            setup=dict(initial_sources=refs,steps=[],history_visibility="active_only"),
            expected_state=dict(active_sources=refs,accessible_sources=refs),conversation=[],
            input_policy=dict(auto_save=False,search_scope="actor_accessible_active_sources_only",input_path="raw_original_v1"),
            required_observations=["retrieved_source_revisions","answer_claims","citation_spans"])

    for case in CASES:
        case_id=case["id"]
        profile="natural_single" if len(case["records"])==1 else "natural_multi"
        family_rows.append(dict(id=case_id,title=case["title"],split="development",variables=[],review_status="AUTHOR_DRAFT"))
        owner="fixture-"+sha(case_id)[:16]
        context_id="NIC-"+sha(case_id)[:16]
        refs=[];spans={};fact_ids={};record_sentences=[];case_sources=[];input_ids=[]
        for record_index,record in enumerate(case["records"],1):
            input_id=f"{case_id}-R{record_index}"
            sid="NIS-"+sha(input_id)[:16]
            ref=dict(source_id=sid,revision=1)
            refs.append(ref);input_ids.append(input_id)
            text="";rows=[]
            for paragraph_index,paragraph in enumerate(record["paragraphs"],1):
                if text:text+="\n\n"
                for sentence_index,s in enumerate(paragraph):
                    if sentence_index:text+=" "
                    assert s["key"] not in spans,(case_id,s["key"])
                    start=len(text);text+=s["text"]
                    spans[s["key"]]={**ref,"start":u16(text,start),"end":u16(text,len(text)),"quote":s["text"]}
                    fact_ids[s["key"]]=f"{case_id}-F-{s['key']}"
                    rows.append(dict(key=s["key"],paragraph=paragraph_index,spec=s))
            inputs.append(dict(id=input_id,text=text,reference_time=STAMP,entry_mode="record",
                metadata=dict(recorded_at=record["recorded_at"],synthetic_timestamp=True)))
            source=dict(id=sid,revision=1,family_id=case_id,split="development",text=text,
                metadata=dict(owner_id=owner,owner_is_author=True,created_at=record["recorded_at"],
                    synthetic_timestamp=True,document_reference_time=STAMP,time_zone="+09:00",channel="synthetic_fixture"),
                provenance=dict(upstream_case_id=input_id,case_id=case_id,title=record["title"],
                    profile=profile,pair_group=case_id,domain=case["domain"],synthetic_only=True,model_tokens=None),
                gold=dict(review_status="AUTHOR_DRAFT",coverage_scope="authored sentence-meaning inventory; semantic completeness pending independent review",
                    annotation_kind="sentence_meaning_bundles",facts=[],highlights=[],forbidden_inferences=[],sentence_inventory=[]))
            case_sources.append(source);record_sentences.append(rows)
        for source,rows in zip(case_sources,record_sentences):
            for row in rows:
                s=row["spec"];evidence=[spans[key] for key in s["refs"]]
                assert all(e["source_id"]==source["id"] for e in evidence),(case_id,s["key"],"cross-record resolution must be a case connection, not an unavailable extraction input")
                fid=fact_ids[s["key"]]
                source["gold"]["facts"].append(dict(id=fid,kind="sentence_meaning_bundle_draft",statement=s["meaning"],
                    evidence=evidence,qualifiers=s["qualifiers"],review_status="AUTHOR_DRAFT"))
                source["gold"]["sentence_inventory"].append(dict(id=f"{case_id}:{s['key']}",paragraph=row["paragraph"],
                    evidence=spans[s["key"]],fact_ids=[fid]))
                sentence_rows.append(dict(case_id=case_id,source_id=source["id"],sentence_key=s["key"],
                    paragraph=row["paragraph"],evidence=spans[s["key"]],fact_ids=[fid]))
            sources.append(source)
        contexts.append(new_context(context_id,case_id,owner,refs,profile))
        qids=[]
        for i,q in enumerate(case["questions"],1):
            qid=f"{case_id}-Q{i}"
            groups=[dict(id=f"{qid}-G{n}",any_of_fact_ids=[fact_ids[key]]) for n,key in enumerate(q["refs"],1)]
            questions.append(dict(id=qid,revision=1,display_case_id=case_id,family_id=case_id,split="development",
                context_id=context_id,text=q["text"],question_type=q["kind"],profile=profile,pair_group=case_id,position=None,
                variables=[],variant=None,required_observations=["citation_spans","answer_claims"],
                gold=dict(review_status="AUTHOR_DRAFT",label_status="author_draft_requires_independent_review",
                    expected_action=q["action"],reference_answer=q["answer"],required_claims=q["required"],forbidden_claims=q["forbidden"],
                    evidence_groups=groups,structured_expectations=q["expected"],
                    annotation_status=dict(reference_answer="AUTHOR_DRAFT",expected_action="AUTHOR_DRAFT"),
                    answer_policy="semantic review required; use all required evidence groups, preserve uncertainty, source attribution and scope",
                    citation_policy="Every evidence group is required; each group lists alternative sufficient fact annotations.",
                    judging="semantic review with exact source provenance; no keyword PASS",
                    coverage="question target meanings; source inventory is a separate author draft")))
            qids.append(qid)
        case_edges=[]
        for i,(kind,from_key,to_key,statement) in enumerate(case["connections"],1):
            edge=dict(id=f"{case_id}-E{i}",case_id=case_id,context_id=context_id,type=kind,
                from_fact_id=fact_ids[from_key],to_fact_id=fact_ids[to_key],statement=statement,
                evidence=[spans[from_key],spans[to_key]],review_status="AUTHOR_DRAFT")
            connections.append(edge);case_edges.append(edge["id"])
        annotations.append(dict(id=case_id,profile=profile,family_id=case_id,case_kind="natural_narrative",
            record_ids=input_ids,question_ids=qids,connection_ids=case_edges,gold_status="AUTHOR_DRAFT",
            authored_sentence_keys=list(spans),coverage="sentence-meaning inventory draft; not independently certified complete"))
        cases.append(dict(id=case_id,title=case["title"],domain=case["domain"],profile=profile,
            record_ids=input_ids,source_refs=refs,context_id=context_id,question_ids=qids,connection_ids=case_edges,
            characters=sum(len(source["text"]) for source in case_sources),review_status="AUTHOR_DRAFT"))

        # One target-preserving short counterpart per narrative, in a separate scope.
        # This variant controls ambiguity/distance, rather than being another independent story.
        control_case=case_id+"-CONTROL"
        control_input=control_case+"-R1"
        control_sid="NIS-"+sha(control_input)[:16]
        control_owner="fixture-"+sha(control_case)[:16]
        control_context="NIC-"+sha(control_case)[:16]
        control_ref=dict(source_id=control_sid,revision=1)
        control_span={**control_ref,"start":0,"end":u16(case["control"],len(case["control"])),"quote":case["control"]}
        control_fid=control_case+"-F1"
        source=dict(id=control_sid,revision=1,family_id=case_id,split="development",text=case["control"],
            metadata=dict(owner_id=control_owner,owner_is_author=True,created_at=case["records"][-1]["recorded_at"],
                synthetic_timestamp=True,document_reference_time=STAMP,time_zone="+09:00",channel="synthetic_fixture"),
            provenance=dict(upstream_case_id=control_input,case_id=control_case,title=case["title"]+" · 짧은 대조",
                profile="natural_control",pair_group=case_id,domain=case["domain"],synthetic_only=True,model_tokens=None),
            gold=dict(review_status="AUTHOR_DRAFT",coverage_scope="paired question target only; not full narrative preservation",
                facts=[dict(id=control_fid,kind="target_meaning_control_draft",statement=case["control"],evidence=[control_span],qualifiers={})],
                highlights=[],forbidden_inferences=case["questions"][0]["forbidden"]))
        sources.append(source)
        inputs.append(dict(id=control_input,text=case["control"],reference_time=STAMP,entry_mode="record",
            metadata=dict(recorded_at=case["records"][-1]["recorded_at"],synthetic_timestamp=True)))
        contexts.append(new_context(control_context,case_id,control_owner,[control_ref],"natural_control"))
        q=copy.deepcopy(questions[-len(case["questions"])]);assert q["id"]==qids[0]
        q.update(id=control_case+"-Q1",context_id=control_context,profile="natural_control",display_case_id=control_case,
            question_type="paired_short_control",variant=dict(type="target_preserving_short_control",paired_question_id=qids[0],parent_case_id=case_id))
        q["gold"]["evidence_groups"]=[dict(id=q["id"]+"-G1",any_of_fact_ids=[control_fid])]
        questions.append(q)
        annotations.append(dict(id=control_case,profile="natural_control",family_id=case_id,case_kind="paired_short_control",
            record_ids=[control_input],question_ids=[q["id"]],paired_question_id=qids[0],
            target_source_sentence_keys=case["control_refs"],gold_status="AUTHOR_DRAFT",coverage="paired question target meanings only"))

    profile_specs=[
        ("smoke",8,8,"기존 짧은 통제","v1의 짧은 통제 8개를 그대로 보존"),
        ("core",24,24,"기존 길이·위치 통제","반복형 3000자 앞·중간·끝; 문맥 연결 성능과 별도 집계"),
        ("sentence",8,8,"기존 긴 단일 문장","반복 절이 포함된 단일 문장 통제"),
        ("boundary",6,6,"기존 가져오기 경계","길이 경계 자료; 실제 가져오기 실행이 아닌 원문 전체 경로"),
        ("dependency",4,4,"기존 원거리 근거 통제","반복형 방해 문장 사이의 원거리 정정·역할·원인·충돌"),
        ("stress",6,6,"기존 장문 부하 통제","12000·24000자 조건부 계획 부하 자료"),
        ("natural_single",48,8,"자연 문맥 · 한 원문","서로 다른 8개 이야기 × 질문 6개. 지시어·역할·시간·조건·범위 연결"),
        ("natural_multi",24,4,"자연 문맥 · 원문 간 연결","서로 다른 4개 이야기의 원문 2개씩 × 질문 6개"),
        ("natural_control",12,12,"자연 문맥 · 짧은 대조","새 이야기마다 첫 연결 질문의 타깃 의미를 보존한 짧은 대조. 독립 이야기 아님"),
    ]
    facts_count=sum(len(s["gold"]["facts"]) for s in sources)
    manifest=dict(schema_version="pma-context-dataset-2",dataset_version=VERSION,title="장문·문맥 연결 개발셋 v2.0.0",
        synthetic_only=True,model_execution=False,independent_gold=False,execution_input_path="raw_original_v1",default_profile="natural_single",
        counts=dict(sources=len(sources),contexts=len(contexts),questions=len(questions),families=len(family_rows),
            source_facts=facts_count,legacy_target_regions=60,new_sentence_meaning_bundles=len(sentence_rows),
            short_control_bundles=12,natural_base_cases=12,new_natural_questions=72,paired_control_questions=12,natural_single_cases=8,natural_multi_cases=4,
            source_relations=len(connections),upstream_variables=0,draft_linked_variables=0),
        profiles={key:count for key,count,_,_,_ in profile_specs},families=family_rows,
        partition=dict(development=[q["id"] for q in questions],final=[]),
        provenance=dict(pinned_control_dataset="pma-long-v1.0.1",pinned_manifest_sha256=sha((base/"manifest.json").read_bytes()),
            authoring_sha256=sha((root/"tools"/"natural_cases.py").read_bytes()),builder_sha256=sha(Path(__file__).read_bytes()),
            source="authored synthetic data; v1 control records copied unchanged"),
        limits=["전체가 개발용 합성 데이터이며 정답·연결 관계는 작성자 초안",
            "새 기본 이야기는 12개; 질문 72개와 짧은 대조 12개를 독립 이야기 84개로 집계하지 않음",
            "기존 반복형 통제 56개와 자연 문맥 결과를 하나의 평균 점수로 합치지 않음",
            "문장 연결 주석은 자동 위치 검사만 완료 가능; 의미·완전성의 독립 검토는 미완료",
            "문장별 의미 묶음은 원자 사실 수가 아님; 전체 의미 Fact Recall로 표기하지 않음",
            "짧은 대조는 연결 질문 하나의 타깃 의미만 보존하며 원문 전체의 축약 보존을 주장하지 않음",
            "같은 사례 안의 원문만 함께 검색하며 다른 사례·짧은 대조의 정답 원문은 검색 범위에서 제외",
            "원문 전체 입력 경로; 실제 4000자 가져오기 분할·전역 개체 병합을 구현한 것이 아님",
            "모델 토큰수·실제 모델 성능·합격률 미측정; 489개 공식 변수의 포괄셋이 아님"],
        integrity=[])
    def write(name,value):
        target=dest/name
        target.write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding="utf-8",newline="\n")
    outputs={
        "inputs.json":inputs,"annotations.json":annotations,
        "sources.json":dict(schema_version="pma-source-1",dataset_version=VERSION,offset_convention="UTF-16 zero-based half-open [start,end)",records=sources,relations=connections),
        "contexts.json":dict(schema_version="pma-context-1",dataset_version=VERSION,contexts=contexts),
        "questions.json":dict(schema_version="pma-question-1",dataset_version=VERSION,questions=questions),
        "coverage.json":dict(variables=[],mapping_status="NOT_MAPPED_TO_MAIN_SUITE_489_VARIABLES",
            profiles=[dict(id=key,count=count,case_count=cases,label=label,description=desc) for key,count,cases,label,desc in profile_specs]),
        "cases.json":dict(schema_version="pma-natural-cases-1",cases=cases),
        "connections.json":dict(schema_version="pma-case-connections-1",relations=connections,review_status="AUTHOR_DRAFT"),
        "sentence_inventory.json":dict(schema_version="pma-sentence-inventory-1",records=sentence_rows,
            coverage="all authored sentence lines have draft meanings; no independent semantic completeness claim"),
        "import_plans.json":copy.deepcopy(previous["import_plans"]),
    }
    for name,value in outputs.items():write(name,value)
    for name in [*outputs,"lib.mjs","README.md"]:
        manifest["integrity"].append(dict(file=name,sha256=sha((dest/name).read_bytes())))
    write("manifest.json",manifest)
    print(json.dumps(dict(dataset=VERSION,counts=manifest["counts"],narrative_lengths=[dict(id=c["id"],characters=c["characters"]) for c in cases],model_calls=0),ensure_ascii=False))

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--root",type=Path,default=Path(__file__).resolve().parents[1]);args=parser.parse_args();build(args.root)
