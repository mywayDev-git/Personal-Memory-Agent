"""Summarize observed CPU/GPU experiments without running tests or models."""

import argparse
import json
from pathlib import Path

from evaluation.latency_bottlenecks import analyze


def render(experiments):
    lines = ["10초 응답 목표 비교", "===================", "",
             "Qwen3-8B Q4_K_M / BGE-M3 Q8_0, 합성 DB만 사용.",
             "준비 실행·색인·모델 로딩은 응답 시간에서 제외. 각 요청 전 실험 슬롯을 비웁니다.",
             "품질 통과 수는 자동 선별 검사입니다. 공식 메인 평가나 전 범위 의미 검증이 아닙니다.",
             "RAM은 Python·실험 모델 서버 작업 집합 합계, VRAM은 장치 전체 관측 최댓값입니다.",
             "검증·원문·인용 검사를 생략하지 않습니다. 성능 보고서에 기록 원문을 넣지 않습니다.", ""]
    for name, document in experiments:
        result = analyze(document)
        lines += [name, "-" * len(name), "",
                  f"실행 완료: {result['execution_completed']} / 가속: {result['placement']}",
                  f"제품 소스 고정: {document.get('source_unchanged')} / 측정 코드 고정: {document.get('evaluator_unchanged')}", ""]
        for key, row in sorted(result["cases"].items()):
            timing = row["latency_seconds"]
            latency = (f"중앙값 {timing['median']:.3f}초, 최대 {timing['maximum']:.3f}초"
                       if timing["median"] is not None else "완료된 시간 표본 없음")
            lines += [f"* {key}: {latency}; 완료 {row['completed']}/{row['requested']}; "
                      f"자동 품질 {row['automatic_quality_passes']}/{row['requested']}; "
                      f"10초 이내·품질 충족 {row['target_successes']}/{row['requested']}.",
                      f"  RAM 최대 {row['ram_peak_mb']} MiB / 장치 VRAM 최대 {row['device_vram_peak_mb']} MiB."]
            stages = sorted(row["exclusive_stages_seconds"].items(),
                            key=lambda item: item[1]["median"] or 0, reverse=True)[:4]
            lines.append("  단계별 중앙값(배타 시간): " + ", ".join(
                f"{stage} {values['median']:.3f}초" for stage, values in stages if values["median"] is not None))
        lines += [""]
    lines += ["판정 주의", "---------", "",
              "* 같은 조건의 current/candidate만 직접 비교합니다. 서로 다른 실행의 숫자는 참고 비교입니다.",
              "* 5회 반복의 최댓값은 긴 꼬리를 추정하는 데 부족합니다. 전체 앱의 95% 보장으로 해석하지 않습니다.",
              "* 빨리 실패한 요청은 목표 달성으로 계산하지 않습니다. 오류·미완료·검토 대기는 통과가 아닙니다.",
              "* 조건부 선별 검사의 통과만으로 모델 품질의 일반적 동등성이나 제품 기본값 변경을 승인하지 않습니다.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Use a new output path; earlier reports are preserved")
    experiments = [(str(path.parent), json.loads(path.read_text("utf-8"))) for path in args.results]
    args.output.write_text(render(experiments), "utf-8")


if __name__ == "__main__":
    main()
