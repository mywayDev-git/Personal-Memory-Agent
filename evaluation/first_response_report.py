"""Conservative per-case adoption gates. This tool only reads saved results."""

import argparse
import json
from pathlib import Path

from .latency_bottlenecks import analyze


def compare(document):
    placement = document["configuration"]["placement"]
    target = 10 if placement == "gpu" else 60
    analyzed = analyze(document, target)
    decisions = {}
    for name in document["configuration"]["cases"]:
        baseline = analyzed["cases"].get("current/" + name)
        candidate = analyzed["cases"].get("candidate/" + name)
        if not baseline or not candidate:
            decisions[name] = {"status": "INCOMPLETE"}
            continue
        a, b = baseline["latency_seconds"], candidate["latency_seconds"]
        complete = document.get("execution_completed") and all(
            r["requested"] >= 5 and r["completed"] == r["requested"] and
            r["automatic_quality_passes"] == r["requested"] for r in (baseline, candidate))
        reduction = 1 - b["median"] / a["median"] if a["median"] and b["median"] else None
        memory_ok = all(baseline[field] and candidate[field] is not None and
                        candidate[field] <= baseline[field] * 1.05
                        for field in ("ram_peak_mb", "private_commit_peak_mb"))
        if placement == "gpu":
            memory_ok = bool(memory_ok and baseline["device_vram_peak_mb"] and
                             candidate["device_vram_peak_mb"] is not None and
                             candidate["device_vram_peak_mb"] <= baseline["device_vram_peak_mb"] * 1.05)
        tail_ok = a["maximum"] is not None and b["maximum"] is not None and b["maximum"] <= a["maximum"] * 1.1
        simple = name in {"simple_answer", "dev_fact", "final_fact", "dev_date", "final_date"}
        cold = document["configuration"].get("cold_interpretations", False)
        speed_ok = (b["median"] is not None and a["median"] is not None and
                    (b["median"] <= target if cold and simple else
                     reduction is not None and reduction >= .2 if cold else
                     b["median"] <= a["median"] + max(.1 * a["median"], .05)))
        status = ("SCREEN_PASS" if complete and memory_ok and tail_ok and speed_ok else
                  "PARTIAL_IMPROVEMENT" if complete and memory_ok and tail_ok and reduction is not None and reduction >= .2 else
                  "NOT_ADOPTED")
        decisions[name] = {"status": status, "baseline": baseline, "candidate": candidate,
                           "median_reduction": reduction, "memory_within_5_percent": bool(memory_ok),
                           "maximum_within_10_percent": bool(tail_ok), "target_seconds": target if simple else None}
    return {"placement": placement, "cold_interpretations": document["configuration"].get("cold_interpretations"),
            "prompt_reset": document["configuration"].get("reset_prompt_cache"), "cases": decisions,
            "adoption": "PENDING_FULL_QUALITY_AND_FINAL_VERIFICATION",
            "gpu_absent_environment_verified": document.get("gpu_absent_environment_verified", False),
            "device_vram_includes_other_apps": True,
            "sampling_cannot_prove_zero_short_memory_peaks": True}


def render(reports):
    lines = ["첫 질문 GPU 10초·CPU 60초 비교", "================================", "",
             "합성 DB와 실제 모델의 응답 완료 시간입니다. 모델 로딩·색인·준비 실행은 별도입니다.",
             "SCREEN_PASS는 해당 사례의 자동 선별 통과이며 전체 품질 검증이나 기본값 채택이 아닙니다.",
             "최종 독립 검증은 유지합니다. 5회 최댓값을 전체 요청의 P95 보장으로 해석하지 않습니다.", ""]
    for report in reports:
        lines += [f"가속: {report['placement']} / 첫 요청 조건: {report['cold_interpretations']}", ""]
        for case, row in report["cases"].items():
            if "baseline" not in row:
                lines.append(f"* {case}: INCOMPLETE")
                continue
            a, b = row["baseline"], row["candidate"]
            lines += [f"* {case}: {row['status']}",
                      f"  중앙값 {a['latency_seconds']['median']} → {b['latency_seconds']['median']}초; 최대 {a['latency_seconds']['maximum']} → {b['latency_seconds']['maximum']}초.",
                      f"  자동 품질 {a['automatic_quality_passes']}/{a['requested']} → {b['automatic_quality_passes']}/{b['requested']}; RAM {a['ram_peak_mb']} → {b['ram_peak_mb']} MiB.",
                      f"  Private commit {a['private_commit_peak_mb']} → {b['private_commit_peak_mb']} MiB; 장치 VRAM {a['device_vram_peak_mb']} → {b['device_vram_peak_mb']} MiB."]
        lines.append("")
    lines += ["CPU 강제 실행과 GPU 없는 PC의 검증은 구분합니다. 물리적 GPU 부재 환경은 별도 확인이 필요합니다.",
              "메모리는 표본 관측값이며 짧은 피크를 놓칠 수 있습니다. VRAM에는 다른 앱 사용량이 포함됩니다.",
              "원시 단계별 시간·호출 수·오류·시스템 여유 메모리는 동봉 JSON에서 확인할 수 있습니다.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a new output; previous reports are preserved")
    reports = [{"source": str(path), **compare(json.loads(path.read_text("utf-8")))} for path in args.results]
    args.output.write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
    text_path = args.output.with_suffix(".rst")
    if not text_path.exists():
        text_path.write_text(render(reports), encoding="utf-8")


if __name__ == "__main__":
    main()
