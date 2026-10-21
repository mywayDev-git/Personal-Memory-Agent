"""Explicit isolated latency experiments. Without --execute, print a plan only.

This is a performance experiment, not evaluation.main_suite or a model comparison.
It never downloads models, stops ordinary servers or edits application defaults.
"""

import argparse
import hashlib
import json
import math
import os
import statistics
import subprocess
import sys
from pathlib import Path

from evaluation.latency_variants import OPTIONS
from evaluation.response_latency import CASES

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / ".local" / "latency-recheck"
ANSWER_CASES = tuple(k for k, v in CASES.items() if not v.get("search"))


def output_path(name):
    if not name or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in name):
        raise ValueError("Use a new run name containing letters, numbers, - or _")
    expected = OUTPUT_ROOT / name
    if expected.resolve() != expected.absolute() or OUTPUT_ROOT.resolve() != OUTPUT_ROOT.absolute():
        raise ValueError("Linked evaluation directories are not allowed")
    return expected


def experiment_command(output, options, *, samples, cases, placement, port, threads=0, embedding_batch=8192):
    return [sys.executable, "-m", "evaluation.response_latency", "--output", str(output),
            "--variants", "current", "candidate", "--candidate-options", *options,
            "--samples", str(samples), "--cases", *cases, "--placement", placement,
            "--port", str(port), "--threads", str(threads), "--embedding-batch", str(embedding_batch),
            "--fixed-anchor", "--reset-prompt-cache"]


def assessment(document, *, required_samples):
    """Do not conflate component time, regex screens and final semantic acceptance."""
    rows = [r for r in document.get("runs", []) if not r.get("warmup")]
    requested = document.get("configuration", {}).get("cases", [])
    result = {"complete": False, "automatic_quality_passed": False,
              "semantic_review": "PENDING_REVIEW", "default_change_allowed": False,
              "per_case": {}, "answer_geometric_median_reduction": None}
    if not requested or not document.get("execution_completed"):
        return result
    complete = document.get("source_unchanged") is True and document.get("evaluator_unchanged") is True
    quality_ok, tails_ok, ratios = True, True, []
    for case in requested:
        groups = [[r for r in rows if r["case"] == case and r["variant"] == v]
                  for v in ("current", "candidate")]
        valid = all(len(g) == required_samples and len({r["sample"] for r in g}) == required_samples
                    and not any(r.get("error_code") for r in g)
                    and all(type(r.get("seconds")) in {int, float}
                            and math.isfinite(r["seconds"]) and r["seconds"] > 0 for r in g)
                    for g in groups)
        complete &= valid
        quality_ok &= valid and all(r.get("quality", {}).get("passed") is True for g in groups for r in g)
        if not valid:
            result["per_case"][case] = {"complete": False}
            continue
        medians = [statistics.median(r["seconds"] for r in g) for g in groups]
        p95s = [sorted(r["seconds"] for r in g)[math.ceil(.95 * len(g)) - 1] for g in groups]
        ratio = medians[1] / medians[0] if medians[0] > 0 else None
        tails_ok &= p95s[1] <= p95s[0]
        if case in ANSWER_CASES and ratio is not None:
            ratios.append(ratio)
        result["per_case"][case] = {"complete": True, "current_median_seconds": medians[0],
                                   "candidate_median_seconds": medians[1],
                                   "current_p95_seconds": p95s[0], "candidate_p95_seconds": p95s[1],
                                   "median_reduction": None if ratio is None else 1 - ratio}
    reduction = 1 - math.exp(statistics.mean(math.log(r) for r in ratios)) if ratios else None
    result.update(complete=bool(complete), automatic_quality_passed=bool(complete and quality_ok),
                  p95_non_regression=bool(complete and tails_ok),
                  answer_geometric_median_reduction=reduction,
                  timing_gate_passed=bool(required_samples >= 20 and complete and quality_ok
                                         and tails_ok and reduction is not None and reduction >= .2),
                  application_wide_claim=False)
    return result


def write_report(output, manifest):
    path = output / "verification.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", "utf-8")
    lines = ["# 응답 속도 재검증 기록", "", f"상태: **{manifest['status']}**", "",
             "기존 모델·개인 DB·운영 서버·제품 기본값을 유지합니다. 공식 메인 평가는 실행하지 않습니다.",
             "자동 품질 검사는 선별 검사이며 의미 검토를 대신하지 않습니다. 미실행은 통과가 아닙니다.", "",
             "캐시는 각 요청 전 실험 슬롯을 비워 이전 후보의 상태를 제거합니다. 요청 내부 재사용 효과를 측정하며,",
             "여러 요청에 걸친 운영 캐시 적중률을 입증하지 않습니다.", "",
             "| 후보/사례 | 현재 중앙값(초) | 후보 중앙값(초) | 현재 P95 | 후보 P95 |", "|---|---:|---:|---:|---:|"]
    for trial in manifest["trials"]:
        for case, row in trial.get("assessment", {}).get("per_case", {}).items():
            if row.get("complete"):
                vals = [row[k] for k in ("current_median_seconds", "candidate_median_seconds", "current_p95_seconds", "candidate_p95_seconds")]
                lines.append(f"| {trial['name']}/{case} | " + " | ".join(f"{v:.3f}" for v in vals) + " |")
    lines += ["", "## 재현 명령", "", "각 명령은 새로운 출력 폴더를 사용해야 합니다. 기존 결과를 덮어쓰지 않습니다."]
    for trial in manifest["trials"]:
        lines += ["", "```powershell", subprocess.list2cmdline(trial["command"]), "```"]
    lines += ["", "원문·답변·인용은 각 실험의 `quality/`에서 대조하고, `results.json`의 단계·호출·토큰·실패 기록을 확인합니다.",
              "관제실의 메인 테스트와 별도 실험입니다. 최종 채택에는 새 다국어 평가, 의미 검토 및 전체 회귀 검사도 필요합니다."]
    (output / "report.md").write_text("\n".join(lines) + "\n", "utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--stage", choices=["screen", "final"], default="screen")
    parser.add_argument("--candidates", nargs="+", choices=list(OPTIONS), default=list(OPTIONS))
    parser.add_argument("--combine", action="store_true", help="Compare only the explicitly chosen combination")
    parser.add_argument("--cases", nargs="+", choices=list(CASES), default=list(CASES))
    parser.add_argument("--placement", choices=["cpu", "gpu"], default="cpu")
    parser.add_argument("--port", type=int, default=18581)
    parser.add_argument("--threads", type=int)
    parser.add_argument("--embedding-batch", type=int, choices=[512, 2048, 4096, 8192])
    parser.add_argument("--name", default="screen-001")
    args = parser.parse_args(argv)
    if args.threads is None:
        args.threads = 4 if args.placement == "cpu" else 0
    if args.embedding_batch is None:
        args.embedding_batch = 4096 if args.placement == "cpu" else 8192
    try:
        output = output_path(args.name)
        if args.port < 18000 or args.port >= 65535:
            raise ValueError("Use dedicated ports >=18000; ordinary servers are never reused")
        if args.threads < 0:
            raise ValueError("Threads must be nonnegative")
        if len(set(args.candidates)) != len(args.candidates):
            raise ValueError("Duplicate candidates")
        if args.combine and {"prefix_on", "prefix_off"} <= set(args.candidates):
            raise ValueError("Choose only one prefix cache policy")
    except ValueError as exc:
        parser.error(str(exc))
    samples = 5 if args.stage == "screen" else 20
    options = [args.candidates] if args.combine else [[c] for c in args.candidates]
    trials = [{"name": "+".join(o), "status": "NOT_RUN", "command": experiment_command(
        output / ("combined" if args.combine else o[0]), o, samples=samples,
        cases=args.cases, placement=args.placement, port=args.port,
        threads=args.threads, embedding_batch=args.embedding_batch)} for o in options]
    manifest = {"schema_version": 1, "status": "PLANNED", "stage": args.stage,
                "samples": samples, "cases": args.cases, "placement": args.placement,
                "threads": args.threads, "embedding_batch": args.embedding_batch,
                "main_evaluation": "NOT_RUN", "personal_database_used": False,
                "default_models_changed": False, "ordinary_servers_stopped": False,
                "source_draft_expansion": "ALREADY_IMPLEMENTED_IN_CURRENT_BASELINE",
                "trials": trials}
    if not args.execute:
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 0
    if output.exists():
        parser.error("Use a new output name; previous records are immutable")
    if args.placement == "gpu":
        try:
            free = subprocess.check_output(["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"], text=True)
            if int(free.strip().splitlines()[0]) < 7800:
                parser.error("Insufficient free VRAM; ordinary model servers must remain untouched. Use CPU or run later.")
        except (OSError, ValueError, subprocess.CalledProcessError):
            parser.error("Cannot verify free VRAM")
    output.mkdir(parents=True)
    manifest["status"] = "RUNNING"
    write_report(output, manifest)
    try:
        for trial in trials:
            trial["status"] = "RUNNING"
            write_report(output, manifest)
            completed = subprocess.run(trial["command"], cwd=ROOT, env=os.environ.copy(), check=False)
            result_path = Path(trial["command"][trial["command"].index("--output") + 1]) / "results.json"
            trial["returncode"] = completed.returncode
            if result_path.exists():
                raw = result_path.read_bytes()
                trial["results_sha256"] = hashlib.sha256(raw).hexdigest()
                trial["assessment"] = assessment(json.loads(raw), required_samples=samples)
            trial["status"] = "COMPLETED" if completed.returncode == 0 and trial.get("assessment", {}).get("complete") else "ERROR"
            write_report(output, manifest)
        manifest["status"] = "COMPLETED" if all(t["status"] == "COMPLETED" for t in trials) else "ERROR"
    except BaseException as exc:
        manifest["status"] = "INTERRUPTED" if isinstance(exc, KeyboardInterrupt) else "ERROR"
        manifest["error_type"] = type(exc).__name__
        for trial in trials:
            if trial["status"] == "RUNNING":
                trial["status"] = manifest["status"]
        raise
    finally:
        write_report(output, manifest)
    return 0 if manifest["status"] == "COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
