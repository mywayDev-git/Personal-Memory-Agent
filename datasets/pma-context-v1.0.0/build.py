"""Rebuild this standalone dataset from its own natural-only definition.json.

No sibling dataset, application DB, model, package or network is read.
"""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
VERSION="pma-context-v1.0.0"

def sha(data):
    return hashlib.sha256(data).hexdigest()

def build(root=ROOT):
    data=json.loads((root/"definition.json").read_text(encoding="utf-8"))
    assert data["version"]==VERSION
    write=lambda name,value:(root/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding="utf-8",newline="\n")
    names=["inputs","annotations","sources","contexts","questions","coverage","cases","connections","sentence_inventory"]
    for name in names:write(name+".json",data[name])
    sources=data["sources"]["records"];questions=data["questions"]["questions"]
    assert len(sources)==28 and len(questions)==84
    manifest=dict(schema_version="pma-context-standalone-1",dataset_version=VERSION,title="자연 문맥 독립셋 v1.0.0",
        synthetic_only=True,model_execution=False,independent_gold=False,execution_input_path="raw_original_v1",default_profile="natural_single",
        composition="natural_only_no_legacy_questions",
        counts=dict(sources=28,contexts=24,questions=84,families=12,source_facts=sum(len(s["gold"]["facts"]) for s in sources),
            new_sentence_meaning_bundles=264,short_control_bundles=12,natural_base_cases=12,new_natural_questions=72,
            paired_control_questions=12,natural_single_cases=8,natural_multi_cases=4,source_relations=59,
            legacy_questions=0,upstream_variables=0,draft_linked_variables=0),
        profiles={p["id"]:p["count"] for p in data["coverage"]["profiles"]},
        families=[dict(id=c["id"],title=c["title"],split="development",variables=[],review_status="AUTHOR_DRAFT") for c in data["cases"]["cases"]],
        partition=dict(development=[q["id"] for q in questions],final=[]),
        provenance=dict(creation_method="independent_natural_only_snapshot",runtime_dependency_on_other_datasets=False,
            definition_sha256=sha((root/"definition.json").read_bytes())),
        limits=["기존 56개 통제 질문과 원문은 포함하지 않는 별도 데이터셋",
            "자연 문맥 이야기 12개와 질문 72개; 짧은 대조 12개는 그중 첫 질문의 별도 입력 변형",
            "원문 28개 중 자연 원문 16개와 짧은 대조 원문 12개; 맥락 24개는 독립 이야기 24개가 아님",
            "작성자 정답 초안이며 의미 정확성·완전성의 독립 검토는 미완료",
            "문장 의미 묶음 264개와 대조 주석 12개는 원자 사실 276개라는 뜻이 아님",
            "모델 토큰수·실제 모델 성능·합격률 미측정; 전부 개발용 합성 자료",
            "원문 전체 입력 경로; 실제 가져오기 분할·전역 개체 병합·실사용 인증의 구현 검증이 아님",
            "사례당 검색 원문 1~2개: 원문 순위 성능으로 일반화하지 않음",
            "질문·프로필·원문을 고정해서 비교하고 짧은 대조를 독립 이야기로 합산하지 않음"],
        integrity=[])
    for name in [*(n+".json" for n in names),"definition.json","lib.mjs","build.py","README.md"]:
        manifest["integrity"].append(dict(file=name,sha256=sha((root/name).read_bytes())))
    write("manifest.json",manifest)
    print(json.dumps(dict(dataset=VERSION,sources=28,questions=84,legacy_questions=0,model_calls=0)))

if __name__=="__main__":build()
