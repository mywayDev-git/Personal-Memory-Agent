"""Read-only HTML review of saved synthetic answers; never starts models."""

import argparse
import hashlib
import html
import json
from pathlib import Path

from .first_response_cases import DEVELOPMENT, HOLDOUT, manifest


def escaped(value):
    return html.escape("없음" if value is None else str(value), quote=True)


def render(results, artifacts):
    document = json.loads(results.read_text(encoding="utf-8"))
    config = document["configuration"]
    cases = {"development": DEVELOPMENT, "holdout": HOLDOUT}.get(config.get("fixture_split"))
    expected_hash = manifest()["sha256"]
    if config.get("fixture_split") == "identity_confirmation":
        from .identity_followup_cases import CASES, manifest as identity_manifest
        cases, expected_hash = CASES, identity_manifest()["sha256"]
    if config.get('fixture_split') == 'identity_search_confirmation':
        from .identity_search_cases import CASES, manifest as search_manifest
        cases, expected_hash = CASES, search_manifest()['sha256']
    if cases is None or config.get("fixture_manifest_sha256") != expected_hash:
        raise ValueError("UNKNOWN_OR_CHANGED_SYNTHETIC_FIXTURE")
    root = artifacts.resolve()
    scope_violations = {variant: sum(
        not row.get("warmup") and row.get("variant") == variant
        and (row.get("quality") or {}).get("validation") == "model_checked"
        and (row.get("quality") or {}).get("source_scope_valid") is False
        for row in document.get("runs", [])) for variant in ("current", "candidate")}
    parts = ["<!doctype html><html lang='ko'><meta charset='utf-8'>",
             "<meta name='viewport' content='width=device-width,initial-scale=1'>",
             "<title>첫 응답 합성 답변 검토표</title><style>",
             "body{font:16px/1.6 'Segoe UI',sans-serif;margin:auto;padding:24px;max-width:1100px;background:#f4f6f8;color:#182230}",
             "article{background:white;border:1px solid #ccd5df;border-radius:10px;padding:20px;margin:20px 0}",
             "pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f6f8;padding:12px}",
             "summary{cursor:pointer;font-weight:600}small{color:#526074}h2{font-size:20px}li{margin:8px 0}",
             ".pass{color:#176441}.fail{color:#a12626}.label{font-weight:600}</style>",
             "<h1>첫 응답 합성 답변 검토표</h1>",
             "<p>저장된 합성 자료만 읽는 검토표입니다. 모델 실행·DB 수정·자동 채택을 하지 않습니다. "
             "자동 채점 통과와 원문에 비춘 의미 검토는 별개입니다. 동일한 기준 오류도 정답으로 취급하지 않습니다.</p>",
             f"<p>환경: {escaped(config.get('placement'))} / 자료: {escaped(config.get('fixture_split'))} / "
             f"실행 완료: {escaped(document.get('execution_completed'))}</p>",
             f"<small>원시 결과 SHA256: {hashlib.sha256(results.read_bytes()).hexdigest()}<br>"
             f"검토 도구 SHA256: {hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}</small>"]
    if any(scope_violations.values()):
        parts.append(f"<p class='fail'>독립 검증 후에도 고정된 근거 범위를 벗어난 답변: "
                     f"기준 {scope_violations['current']}건, 후보 {scope_violations['candidate']}건. "
                     "기준도 실패했다는 이유로 정답으로 처리하지 않습니다. 해당 사례의 원문과 인물을 확인하세요.</p>")
    for row in document.get("runs", []):
        if row.get("warmup"):
            continue
        name, variant, sample = row["case"], row["variant"], row["sample"]
        if name not in cases or variant not in {"current", "candidate"} or type(sample) is not int or sample < 1:
            raise ValueError("INVALID_SYNTHETIC_OBSERVATION")
        path = (root / f"{name}-{sample}-{variant}.json").resolve()
        if not path.is_relative_to(root):
            raise ValueError("INVALID_ARTIFACT_PATH")
        artifact = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        response = artifact.get("response", {})
        passed = (row.get("quality") or {}).get("passed") is True
        label = "기준" if variant == "current" else "후보"
        seconds = row.get("seconds")
        duration = f"{seconds:.3f}초" if type(seconds) in (int, float) else "미측정"
        parts += [f"<article><h2>{escaped(name)} · {label} · {sample}회</h2>",
                  f"<p class='label'>{escaped(cases[name]['question'])}</p>",
                  f"<p>{duration} / 상태: {escaped(response.get('status', row.get('status')))} / "
                  f"독립 검증: {escaped(response.get('validation'))} / 오류: {escaped(row.get('error_code'))}</p>",
                  f"<p class='{'pass' if passed else 'fail'}'>자동 채점: {'통과' if passed else '실패 또는 측정 오류'}</p>",
                  "<h3>실제 답변</h3><ul>"]
        for item in response.get("items", []):
            parts.append(f"<li>{escaped(item['text'])}<br><small>인용 ID: {escaped(item.get('citations', []))}</small></li>")
        if not response.get("items"):
            parts.append("<li>답변 항목 없음</li>")
        parts += ["</ul>", f"<p>{escaped(response.get('clarification', ''))}</p>",
                  "<details><summary>정답 조건과 자동 채점 세부</summary>",
                  f"<pre>{escaped(json.dumps(cases[name], ensure_ascii=False, indent=2))}</pre>",
                  f"<pre>{escaped(json.dumps(row.get('quality'), ensure_ascii=False, indent=2))}</pre></details>",
                  "<details><summary>답변이 인용한 정확한 원문 구간</summary>"]
        for ref in response.get("citation_details", []):
            parts.append(f"<pre>{escaped(json.dumps(ref, ensure_ascii=False, indent=2))}</pre>")
        parts += ["</details><details><summary>조회된 모든 근거의 전체 원문</summary>"]
        for source in artifact.get("evidence", []):
            parts += [f"<p>ID: {escaped(source['id'])} / 기록: {escaped(source.get('record_id'))}</p>",
                      f"<pre>{escaped(source['source_text'])}</pre>"]
        if not artifact:
            parts.append("<p>답변 아티팩트 없음. 오류 사례를 빠른 정답으로 집계하지 않습니다.</p>")
        parts.append("</details></article>")
    parts.append("</html>")
    return "\n".join(parts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a new output; existing reports are preserved")
    content = render(args.results, args.artifacts or args.results.parent / "quality")
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(content)
    print(args.output)


if __name__ == "__main__":
    main()
