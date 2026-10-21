"""Resumable append-only evaluation orchestration; never imported by the app."""

import argparse
import itertools
import json
import os
import platform
import random
import subprocess
from contextlib import nullcontext
from functools import cmp_to_key
from pathlib import Path
from uuid import uuid4

from evaluation.repository import Repository
from evaluation.schema import Case, Dataset, Result, content_hash

from .catalog import DATA, PROFILES, VERSION, select_cases, validate
from .grading import grade, summary
from .runtime import cancel_point, checked_root, digest, execute, model_specs, servers

ROOT = Path(__file__).resolve().parents[2]
VERDICTS = {"PASS": "pass", "FAIL": "fail", "ERROR": "error", "PENDING_REVIEW": "pending_review",
            "SKIP": "not_applicable", "UNSUPPORTED": "not_applicable", "NOT_RUN": "not_applicable"}


def atomic_json(path, data):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False, default=str) + "\n", "utf-8")
    temporary.replace(path)


def snapshot():
    files = sorted(p for folder in ("pma", "scripts", "config", "schema", "prompts", "evaluation", "tests")
                   for p in (ROOT / folder).rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    return content_hash({p.relative_to(ROOT).as_posix(): digest(p) for p in files})


def trials(cases, repeats, seed):
    jobs = [{"case": case, "attempt": attempt, "id": f"{case['id']}.r{attempt}"}
            for case in cases for attempt in range(1, repeats + 1)]
    random.Random(seed).shuffle(jobs)
    return jobs


def read_rows(path):
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            rows.append(json.loads(line))
    ids = [r["trial_id"] for r in rows]
    if len(set(ids)) != len(ids):
        raise ValueError("DUPLICATE_COMPLETED_TRIAL")
    return rows


def review_result(case):
    return {"verdict": "PENDING_REVIEW", "actual_answer": None, "response_behavior": None,
            "error_type": None, "evaluation": {"review_checklist": case["review_checklist"],
            "review_reason": "이 항목은 원문·실제 동작 증거를 첨부한 사람 검토가 필요합니다.",
            "answer_correct": None, "retrieval_complete": False}}


def apply_reviews(directory, rows):
    path = directory / "adjudications.jsonl"
    indexed = {r["trial_id"]: dict(r) for r in rows}
    if path.exists():
        for line in path.read_text("utf-8").splitlines():
            review = json.loads(line)
            for relative, expected in review.get("evidence_hashes", {}).items():
                evidence = (directory / relative).resolve(strict=True)
                if not evidence.is_relative_to(directory.resolve()) or digest(evidence) != expected:
                    raise ValueError("REVIEW_EVIDENCE_CHANGED")
            row = indexed[review["trial_id"]]
            if row["observation_hash"] != review["observation_hash"]:
                raise ValueError("REVIEW_OBSERVATION_HASH_MISMATCH")
            if row["verdict"] != "PENDING_REVIEW":
                raise ValueError("REVIEW_CANNOT_OVERRIDE_PROVED_FAILURE_OR_COMPLETED_REVIEW")
            row.update(verdict=review["verdict"], review=review)
            row["evaluation"] = {**row["evaluation"], **review["evaluation"]}
    return list(indexed.values())


def import_reviews(directory, path):
    """Human decisions are a separate immutable audit stream, never a rewrite of raw trials."""
    manifest = json.loads((directory / "manifest.json").read_text("utf-8"))
    if manifest["config"].get("grading_version") != VERSION:
        raise ValueError("REVIEW_REQUIRES_MATCHING_GRADING_VERSION")
    reviews = json.loads(path.read_text("utf-8"))
    raw = read_rows(directory / "cases.jsonl")
    effective = {r["trial_id"]: r for r in apply_reviews(directory, raw)}
    validated = []
    for review in reviews:
        row = effective[review["trial_id"]]
        if row["verdict"] != "PENDING_REVIEW" or row["observation_hash"] != review["observation_hash"]:
            raise ValueError("REVIEW_REQUIRES_PENDING_TRIAL_AND_EXACT_OBSERVATION_HASH")
        if review["verdict"] not in {"PASS", "FAIL", "UNSUPPORTED"}:
            raise ValueError("INVALID_REVIEW_VERDICT")
        if not review.get("reviewer") or not review.get("reason") or not review.get("evidence"):
            raise ValueError("REVIEW_REQUIRES_REVIEWER_REASON_AND_EVIDENCE")
        evidence_hashes = {}
        for relative in review["evidence"]:
            evidence = (directory / relative).resolve(strict=True)
            if not evidence.is_relative_to(directory.resolve()) or not evidence.is_file():
                raise ValueError("REVIEW_EVIDENCE_MUST_BE_WITHIN_CANDIDATE_DIRECTORY")
            evidence_hashes[relative] = digest(evidence)
        if review["verdict"] == "UNSUPPORTED" and not review.get("product_scope_reference"):
            raise ValueError("UNSUPPORTED_REQUIRES_DOCUMENTED_PRODUCT_SCOPE")
        evaluation = review.get("evaluation", {})
        allowed = {"answer_correct", "final_evidence_complete", "claims_supported", "context_correct",
                   "security_exposures", "deleted_exposures", "invalid_citation_count"}
        if not set(evaluation) <= allowed:
            raise ValueError("INVALID_REVIEW_EVALUATION_KEY")
        for key, value in evaluation.items():
            if key.endswith("exposures") or key == "invalid_citation_count":
                if type(value) is not int or value < 0:
                    raise ValueError("INVALID_EXPOSURE_COUNT")
            elif type(value) is not bool:
                raise ValueError("REVIEW_GRADES_MUST_BE_BOOLEAN")
        if row["adapter"] == "review" and "answer_correct" in evaluation:
            raise ValueError("MANUAL_CATALOG_CHECK_IS_NOT_A_MODEL_ACCURACY_SAMPLE")
        if review["verdict"] == "PASS" and row["adapter"] == "product" and (
                evaluation.get("answer_correct") is not True or evaluation.get("claims_supported") is not True):
            raise ValueError("PRODUCT_PASS_REQUIRES_FACT_AND_CLAIM_VERIFICATION")
        if review["verdict"] == "FAIL" and row["adapter"] == "product" and evaluation.get("answer_correct") is not False:
            raise ValueError("PRODUCT_FAILURE_REQUIRES_FALSE_ANSWER_GRADE")
        validated.append({**review, "evidence_hashes": evidence_hashes})
        effective[review["trial_id"]] = {**row, "verdict": review["verdict"]}
    with (directory / "adjudications.jsonl").open("a", encoding="utf-8") as stream:
        for review in validated:
            stream.write(json.dumps(review, ensure_ascii=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    rows = apply_reviews(directory, raw)
    repo = Repository(directory / "evaluation.db")
    for row in rows:
        publish(repo, manifest["run_id"], row)
    result = report(directory, rows, len(repo.cases(repo.get_run(manifest["run_id"])["dataset_id"])), manifest["config"])
    repo.replace_run_metrics(manifest["run_id"], result["metrics"])
    return result


def publish(repo, run_id, row):
    evaluation = {**row["evaluation"], "suite_verdict": row["verdict"],
                  "measurement_type": "functional" if row["adapter"] != "product" else "model_question",
                  "observation_hash": row.get("observation_hash"), "reproduce": row["reproduce"],
                  "observation": row.get("observation"), "expected_behavior": row["expected_behavior"]}
    events = row.get("observation", {}).get("events", []) if row.get("observation") else []
    repo.save_case_result(run_id, Result(case_id=row["trial_id"], actual_answer=row.get("actual_answer"),
                          response_behavior=row.get("response_behavior"), verdict=VERDICTS[row["verdict"]],
                          latency_ms=row.get("latency_ms"), error_type=row.get("error_type"), evaluation=evaluation),
                          events=events)


def probe_answer(probe):
    """Owner checks are booleans; subprocess checks are result objects."""
    checks = probe.get("checks")
    if checks is None:
        return json.dumps(probe, ensure_ascii=False)
    def passed(check):
        return check is True or isinstance(check, dict) and check.get("outcome") == "passed"
    prefix = "지원 밖 기능 · 거절 검사 " if probe.get("unsupported") else "실제 제품 동작 검사 "
    return prefix + f"{sum(passed(c) for c in checks)}/{len(checks)}개 통과"


def report(directory, rows, total, config):
    result = summary(rows, total)
    result.update(candidate=config["candidate"], profile=config["profile"],
                  partial_selection=config.get("partial_selection", False),
                  stage=config.get("stage"), generation_id=config.get("generation_id"), embedding_id=config.get("embedding_id"),
                  threshold_status="미확정 · 기준값 수집" if not config.get("gates") else "고정 합격선 사용",
                  recommendation="미확정" if not config.get("gates") else "최종 비교 보고서 참조")
    atomic_json(directory / "summary.json", result)
    lines = ["# 메인 테스트 실행 보고서", "", f"모델 조합: {config['candidate']}",
             f"프로필: {config['profile']} · 채점: {config.get('grading_version', VERSION)}", result["threshold_status"],
             f"예정 {total} · 기록 {len(rows)} · 미실행 {total-len(rows)}", "",
             "## 판정", *[f"- {key}: {value}" for key, value in result["counts"].items()],
             "", "## 지표 (값 / 판정 가능한 표본 수)"]
    for name, metric in result["metrics"].items():
        lines.append(f"- {name}: {metric['value']} / {metric['denominator']}")
    lines += ["", "답변 정확도·검색률·인용률은 관측·판정 가능한 표본을 분모로 한 조건부 지표입니다.",
              "근거 충족 답변 성공률에는 기록된 모델 표본의 실행 오류·미확정도 포함하며 성공으로 계산하지 않습니다.",
              "", "## 필수 보안 검사", "미검사·오류·검토 대기는 통과가 아닙니다. 내부 owner 검사는 다중 사용자 인증 검증이 아닙니다."]
    for check, coverage in result["safety_coverage"].items():
        lines.append(f"- {check}: 실행 {coverage['executed']} / 통과 {coverage['passed']}")
    lines += ["", "## 실패·검토 대기", "검색·생성·근거를 별도로 판정하며 관측하지 않은 원인은 확정하지 않습니다."]
    for row in rows:
        if row["verdict"] != "PASS":
            lines.append(f"- {row['trial_id']}: {row['verdict']} · {row.get('error_type') or '원문·동작 검토 필요'}")
    lines += ["", "실행 오류와 미실행은 성공이 아닙니다. 사람 검토 항목은 모델 정확도 표본에 포함하지 않습니다.",
              "최종 모델이나 앱 기본 설정을 자동 변경하지 않습니다."]
    (directory / "report.md").write_text("\n".join(lines) + "\n", "utf-8")
    return result


def run_candidate(directory, config, jobs, settings_context, *, execute_fn=execute, resume=False,
                  seed_templates=None, dashboard=None, cancelled=None):
    directory.mkdir(parents=True, exist_ok=True)
    manifest_path, rows_path = directory / "manifest.json", directory / "cases.jsonl"
    repo = Repository(directory / "evaluation.db")
    dataset = Dataset(id="main-" + content_hash([j["case"] for j in jobs])[:24],
                      name="main-" + content_hash([j["case"] for j in jobs])[:24], version="6",
                      cases=[Case(id=j["id"], question=j["case"]["question"],
                                  question_type=j["case"]["variables"][0].split("-")[0],
                                  expected_behavior=j["case"]["expected_behavior"],
                                  expected_answer=j["case"].get("expected_answer") or json.dumps(j["case"].get("required_facts", []), ensure_ascii=False),
                                  metadata={"scenario": j["case"], "reference_time": "2026-10-20T10:00:00+09:00"})
                             for j in jobs])
    repo.create_dataset(dataset)
    if manifest_path.exists():
        previous = json.loads(manifest_path.read_text("utf-8"))
        if not resume or previous["config"] != config:
            raise ValueError("RESUME_REQUIRES_IDENTICAL_CONFIG_AND_SNAPSHOT")
        run_id = previous["run_id"]
    else:
        if rows_path.exists():
            raise ValueError("ORPHAN_RESULTS_REJECTED")
        run_id = repo.create_run(dataset.id, config=config, environment=config["environment"],
                                 commit_sha=config["commit"])
        atomic_json(manifest_path, {"run_id": run_id, "config": config})
    rows = apply_reviews(directory, read_rows(rows_path))
    expected = {j["id"] for j in jobs}
    if not {r["trial_id"] for r in rows} <= expected:
        raise ValueError("UNEXPECTED_RESUME_TRIAL")
    for row in rows:
        publish(repo, run_id, row)  # recover a DB transaction interrupted after JSONL fsync
    done = {row["trial_id"] for row in rows}
    repo.update_run_status(run_id, "running")
    if jobs:
        repo.update_progress(run_id, jobs[0]["id"], "model_start")
    mirror, mirror_id = None, None
    if dashboard:
        publish_run(directory, dashboard)
        mapping = json.loads((directory / "published.json").read_text("utf-8"))
        mirror, mirror_id = Repository(dashboard), mapping[str(dashboard.resolve()) + ":" + run_id]
        mirror.update_run_status(mirror_id, "running")
    try:
        cancel_point(cancelled)
        context = nullcontext(None) if len(done) == len(jobs) else settings_context
        with context as runtime:
            settings = runtime[0] if isinstance(runtime, tuple) else runtime
            processes = runtime[1] if isinstance(runtime, tuple) else []
            for job in jobs:
                cancel_point(cancelled)
                if job["id"] in done:
                    continue
                case = job["case"]
                repo.update_progress(run_id, job["id"], "review" if case["adapter"] == "review" else "execution")
                if mirror:
                    mirror.update_progress(mirror_id, job["id"], "review" if case["adapter"] == "review" else "execution")
                row = {"trial_id": job["id"], "case_id": case["id"], "family": case.get("evaluation_family", case["family"]),
                       "attempt": job["attempt"], "expected_behavior": case["expected_behavior"],
                       "adapter": case["adapter"], "reproduce": subprocess.list2cmdline([
                           "python", "-m", "evaluation.main_suite", "--execute", "--profile", config["profile"],
                           "--case", case["id"], "--output", str(directory.parent.with_name("repro-" + job["id"])),
                           "--models", config.get("models_manifest", str(DATA / "models.json"))])}
                row["safety_checks"] = case.get("safety_checks", [])
                try:
                    if case["adapter"] == "review":
                        row.update(review_result(case))
                        row["observation_hash"] = content_hash({"case": case, "snapshot": config["snapshot"]})
                    else:
                        from evaluation.performance_benchmark import MemorySampler
                        sampler = MemorySampler([os.getpid()] + [p.pid for p in processes]) if os.name == "nt" and processes else nullcontext()
                        with sampler as mem:
                            if config.get("extraction_policy") == "shared-baseline" and case["adapter"] == "product" and case["id"] not in (seed_templates or {}):
                                raise RuntimeError("F-INDEX:SHARED_EXTRACTION_SEED_UNAVAILABLE")
                            observation = execute_fn(case, settings, directory / "attempts" / (job["id"] + "." + uuid4().hex[:8]),
                                                     seed_template=(seed_templates or {}).get(case["id"]),
                                                     **({"cancelled": cancelled} if cancelled is not None else {}))
                        row["peak_ram_mb"] = max(mem.ram) if mem and mem.ram else None
                        # Normalize numpy diagnostic values before hashing/persisting.
                        observation = json.loads(json.dumps(observation, ensure_ascii=False, default=str))
                        row["observation"], row["observation_hash"] = observation, content_hash(observation)
                        row["latency_ms"] = observation.get("latency_ms")
                        if "probe" in observation:
                            passed = observation["probe"]["passed"]
                            probe = observation["probe"]
                            actual = probe_answer(probe)
                            row.update(verdict="UNSUPPORTED" if observation["probe"].get("unsupported") else "PASS" if passed else "FAIL", evaluation={"probe": observation["probe"],
                                       "security_exposures": observation["probe"].get("security_exposures", 0),
                                       "model_accuracy_sample": False,
                                       "answer_comparison": {"method": "product_contract", "status": "EXACT_MATCH" if passed else "MISMATCH",
                                           "coverage_gaps": case.get("coverage_gaps", []),
                                           "note": "실제 제품의 처리 결과와 기대 조건을 비교한 기능 검사입니다. 모델 정확도에는 포함하지 않습니다."}},
                                       actual_answer=actual,
                                       error_type=None if passed else "F-STATE")
                        else:
                            row.update(grade(case, observation))
                except Exception as exc:
                    from scripts.memory_agent.diagnostics import failure

                    from .answer_comparison import compare_answer

                    partial = getattr(exc, "evaluation_observation", None)
                    if partial is None:
                        partial = row.get("observation", {})
                    diagnostic = partial.get("failure") or failure(exc, "execution")[1]
                    row["observation"] = partial
                    row["observation_hash"] = content_hash(partial)

                    row.update(verdict="ERROR", error_type=str(exc).split(":", 1)[0] if str(exc).startswith("F-") else "F-EXECUTION",
                               evaluation={"error_class": type(exc).__name__, "failure": diagnostic, "answer_correct": None,
                                           "answer_comparison": {**compare_answer(case, ""), "status": "EXECUTION_ERROR"},
                                           "model_accuracy_sample": case.get("model_accuracy_sample", True)},
                               actual_answer=f"실행 오류 ({type(exc).__name__}): " +
                               (str(exc) if str(exc).startswith("F-") else "제품 동작을 완료하지 못했습니다. 처리 과정과 오류 유형을 확인하세요."))
                if case.get("gold_groups"):
                    row["evaluation"].setdefault("requested_retrieval_success", False)
                # Each completed attempt is immutable, including failures and pending reviews.
                with rows_path.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                rows.append(row)
                publish(repo, run_id, row)
                result = report(directory, rows, len(jobs), config)
                repo.replace_run_metrics(run_id, result["metrics"])
                if mirror:
                    publish(mirror, mirror_id, row)
                    mirror.replace_run_metrics(mirror_id, result["metrics"])
                print(f"{config['candidate']} {len(rows)}/{len(jobs)} {job['id']} {row['verdict']}", flush=True)
        cancel_point(cancelled)
        repo.update_run_status(run_id, "completed")
        if mirror:
            mirror.update_run_status(mirror_id, "completed")
    except KeyboardInterrupt:
        repo.update_run_status(run_id, "cancelled")
        if mirror:
            mirror.update_run_status(mirror_id, "cancelled")
        report(directory, rows, len(jobs), config)
        raise
    except BaseException as exc:
        repo.update_run_status(run_id, "failed", type(exc).__name__)
        if mirror:
            mirror.update_run_status(mirror_id, "failed", type(exc).__name__)
        report(directory, rows, len(jobs), config)
        raise
    return report(directory, rows, len(jobs), config), rows


def gates_config(path):
    if path is None:
        return None
    gates = json.loads(path.read_text("utf-8"))
    required = {"grounded_answer_success_rate", "answer_correct", "complete_evidence_recall"}
    if not isinstance(gates.get("version"), str) or not gates["version"].strip() or not isinstance(gates.get("approved_by"), str) or not gates["approved_by"].strip() or set(gates.get("minimums", {})) != required:
        raise ValueError("GATES_REQUIRE_VERSION_APPROVER_AND_ALL_QUALITY_MINIMUMS")
    if any(type(v) not in {int, float} or not 0 <= v <= 1 for v in gates["minimums"].values()):
        raise ValueError("INVALID_GATE_VALUE")
    return gates


def ranking(summaries, gates):
    order = ("grounded_answer_success_rate", "answer_correct", "complete_evidence_recall")
    def compare(a, b):
        for metric in order:
            interval = paired_interval(a, b, metric)
            if interval and interval[0] > 0:
                return -1
            if interval and interval[1] < 0:
                return 1
        for metric in ("p95_latency_ms", "peak_ram_mb"):
            av = a["metrics"].get(metric, {}).get("value")
            bv = b["metrics"].get(metric, {}).get("value")
            if av is not None and bv is not None and av != bv:
                return -1 if av < bv else 1
        return (a["candidate"] > b["candidate"]) - (a["candidate"] < b["candidate"])
    ranked = sorted(summaries, key=cmp_to_key(compare))
    eligible = []
    for result in ranked:
        if (gates and result["complete"] and not result.get("partial_selection") and result["counts"].get("UNSUPPORTED", 0) == 0
                and not result.get("critical_failures")
                and not result.get("functional_failures")
                and result.get("safety_verified", False)
                and not any(result[k] for k in ("security_exposures", "deleted_exposures", "invalid_citations"))
                and all(result["metrics"][k]["value"] is not None
                        and result["metrics"][k]["value"] >= limit for k, limit in gates["minimums"].items())):
            eligible.append(result)
    return {"status": "합격선 미확정" if not gates else "선택 보류" if not eligible else "추천 후보",
            "recommended": eligible[0]["candidate"] if eligible else None,
            "reference_ranking": [s["candidate"] for s in ranked],
            "gates": gates, "auto_applied": False,
            "note": "미완료·검토 대기·미지원이 있으면 공식 추천하지 않습니다."}


def paired_interval(a, b, metric):
    """95% paired family bootstrap: repeats and paraphrases are not independent cases."""
    import numpy as np
    families = sorted(a.get("families", {}).keys() & b.get("families", {}).keys())
    deltas = []
    for family in families:
        av = [r[metric] for r in a["families"][family] if r.get(metric) is not None]
        bv = [r[metric] for r in b["families"][family] if r.get(metric) is not None]
        if av and bv:
            deltas.append(sum(av)/len(av) - sum(bv)/len(bv))
    if len(deltas) < 2:
        return None
    rng = np.random.default_rng(42)
    samples = rng.choice(deltas, (2000, len(deltas))).mean(axis=1)
    return [float(v) for v in np.quantile(samples, [.025, .975])]


def parser():
    p = argparse.ArgumentParser(description="명시적 요청 전용 메인 평가. --execute 없이는 정적 실행 계획만 표시합니다.")
    p.add_argument("--execute", action="store_true")
    p.add_argument("--profile", choices=PROFILES, default="core")
    p.add_argument("--output", type=Path)
    p.add_argument("--models", type=Path, default=DATA / "models.json")
    p.add_argument("--server", type=Path, default=Path("C:/llama.cpp/llama-server.exe"))
    p.add_argument("--port", type=int, default=18481)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--resume", action="store_true")
    p.add_argument("--gates", type=Path)
    p.add_argument("--case", action="append", help="명시한 사례만 별도 실행 (부분 결과는 공식 추천 불가)")
    p.add_argument("--publish-to", type=Path, help="선택: 관제실 evaluation.db (기억 DB와 분리)")
    p.add_argument("--review-file", type=Path, help="실제 모델 호출 없이 사람 검토 결과를 가져옵니다.")
    p.add_argument("--cancel-file", type=Path, help="관제실 중단 요청 파일 (내부 실행 제어)")
    p.add_argument("--completion-file", type=Path, help="관제실 완료 상태 파일 (내부 실행 제어)")
    return p


def _main(args):
    validation = validate()
    if args.review_file:
        if args.execute or args.output is None:
            raise ValueError("REVIEWS_REQUIRE_CANDIDATE_OUTPUT_AND_NO_EXECUTE")
        directory = checked_root(args.output)
        result = import_reviews(directory, args.review_file)
        if args.publish_to:
            publish_run(directory, args.publish_to)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    cases = select_cases(args.profile)
    if args.case:
        requested = set(args.case)
        cases = [case for case in cases if requested & {case["id"], *case.get("source_case_ids", [])}]
        if not requested <= {alias for c in cases for alias in [c["id"], *c.get("source_case_ids", [])]}:
            raise ValueError("CASE_NOT_IN_SELECTED_PROFILE")
    jobs = trials(cases, PROFILES[args.profile]["repeats"], args.seed)
    if not args.execute:
        print(json.dumps({**validation, "profile": args.profile, "scheduled": len(jobs),
                          "executed": False, "threshold_status": "미확정",
                          "automated_trials": sum(j["case"]["adapter"] != "review" for j in jobs),
                          "review_trials": sum(j["case"]["adapter"] == "review" for j in jobs)}, ensure_ascii=False))
        return 0
    if args.output is None:
        raise ValueError("EXPLICIT_OUTPUT_REQUIRED")
    root = checked_root(args.output)
    cancelled = args.cancel_file.exists if args.cancel_file else None
    cancel_point(cancelled)
    if not args.server.is_file():
        raise ValueError("LOCAL_MODEL_SERVER_REQUIRED_NO_DOWNLOAD")
    manifest = json.loads(args.models.read_text("utf-8"))
    if args.profile in {"core", "extended"}:
        manifest = {role: {"baseline": manifest[role]["baseline"]} for role in ("generation", "embedding")}
    specs = model_specs(manifest, cancelled=cancelled)
    gates = gates_config(args.gates)
    root.mkdir(parents=True, exist_ok=True)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    environment = {"os": platform.platform(), "processor": platform.processor(),
                   "python": platform.python_version(), "cpu_count": os.cpu_count()}
    version = subprocess.run([str(args.server), "--version"], capture_output=True, text=True,
                             creationflags=0x08000000 if os.name == "nt" else 0, timeout=20)
    common = {"profile": args.profile, "seed": args.seed, "grading_version": VERSION,
              "snapshot": snapshot(), "commit": commit, "environment": environment, "gates": gates,
              "server_sha256": digest(args.server), "server_version": (version.stdout + version.stderr).strip(),
              "retrieval": {"product_defaults": True}, "repeats": PROFILES[args.profile]["repeats"]}
    common["models_manifest"] = str(args.models.resolve())
    common["partial_selection"] = bool(args.case)
    summaries = []
    # Controlled one-axis comparisons first. Cross combinations are revalidated below.
    seed_templates = {}
    def run_pair(g, e, *, shared=False, stage="generation"):
        cancel_point(cancelled)
        candidate = f"{g}--{e}" + ("--e2e" if stage == "confirmation" else "--embedding" if stage == "embedding" else "")
        directory = root / candidate
        directory.mkdir(exist_ok=True)
        config = {**common, "candidate": candidate, "model": specs["generation", g],
                  "embedding": specs["embedding", e], "extraction_policy": "shared-baseline" if shared else "real-end-to-end",
                  "stage": stage, "generation_id": g, "embedding_id": e}
        if shared:
            config["extraction_seed_manifest"] = {key: digest(value[0]) for key, value in seed_templates.items()}
        context = servers(args.server, specs["generation", g], specs["embedding", e], directory, port=args.port, cancelled=cancelled)
        result, rows = run_candidate(directory, config, jobs, context, resume=args.resume,
                                     seed_templates=seed_templates if shared else None, dashboard=args.publish_to, cancelled=cancelled)
        summaries.append(result)
        if (g, e) == ("baseline", "baseline") and stage == "generation":
            for row in rows:
                if row.get("observation", {}).get("seed"):
                    seed_templates.setdefault(row["case_id"], row["observation"]["seed"])
        if args.publish_to:
            publish_run(directory, args.publish_to)
        return result
    if args.profile == "final":
        for g, e in itertools.product(manifest["generation"], manifest["embedding"]):
            run_pair(g, e, stage="final")
    else:
        for g in manifest["generation"]:
            run_pair(g, "baseline")
    if args.profile == "compare":
        for e in manifest["embedding"]:
            run_pair("baseline", e, shared=True, stage="embedding")
        by_candidate = {s["candidate"]: s for s in summaries}
        ranked_g = ranking([s for s in summaries if s["stage"] == "generation"], None)["reference_ranking"]
        ranked_e = ranking([s for s in summaries if s["stage"] == "embedding"], None)["reference_ranking"]
        # Unknown quality must not silently turn an accuracy-first selection into
        # a speed-only shortlist. Resume after source-bound adjudications.
        quality_known = all(s["metrics"]["answer_correct"]["value"] is not None
                            and s["metrics"]["grounded_answer_success_rate"]["value"] is not None
                            and not s["counts"].get("PENDING_REVIEW", 0) for s in summaries)
        top_g = [by_candidate[n]["generation_id"] for n in ranked_g][:2] if quality_known else []
        top_e = [by_candidate[n]["embedding_id"] for n in ranked_e][:2] if quality_known else []
        for g, e in itertools.product(top_g, top_e):
            run_pair(g, e, stage="confirmation")
    selection_summaries = [s for s in summaries if s["candidate"].endswith("--e2e")] if args.profile == "compare" else summaries
    comparison = {"summaries": summaries, **ranking(selection_summaries, gates)}
    if args.profile == "compare" and not selection_summaries:
        comparison["status"] = "검토 대기 · 상위 조합 선정 보류"
    comparison["paired_95_intervals"] = [{"left": a["candidate"], "right": b["candidate"],
        "metrics": {metric: paired_interval(a, b, metric) for metric in (
            "grounded_answer_success_rate", "answer_correct", "complete_evidence_recall")}}
        for a, b in itertools.combinations(selection_summaries, 2)]
    atomic_json(root / "comparison.json", comparison)
    lines = ["# 모델 비교 보고서", "", comparison["status"],
             f"추천: {comparison['recommended'] or '미확정 / 선택 보류'}", "",
             "| 모델 조합 | 답변 정확도 | 근거 충족 답변 | 완전 근거 검색 | p95(ms) | 최대 RAM(MiB) | 확정 여부 |",
             "|---|---|---|---|---|---|---|"]
    for s in summaries:
        m = s["metrics"]
        values = [m[k]["value"] for k in ("answer_correct", "grounded_answer_success_rate", "complete_evidence_recall", "p95_latency_ms", "peak_ram_mb")]
        lines.append("| " + " | ".join([s["candidate"], *["미확인" if v is None else str(round(v, 4)) for v in values], "완료" if s["complete"] else "미완료·검토 필요"]) + " |")
    lines += ["", comparison["note"], "", "코드/모델/설정은 자동 변경하지 않았습니다."]
    (root / "comparison.md").write_text("\n".join(lines) + "\n", "utf-8")
    return 0


def main(argv=None):
    args = parser().parse_args(argv)
    marker = None
    if args.completion_file:
        if not args.execute or args.output is None:
            raise ValueError("COMPLETION_MARKER_REQUIRES_EXPLICIT_EXECUTION")
        root = checked_root(args.output)
        marker = args.completion_file.resolve()
        if marker != root / "execution-status.json":
            raise ValueError("COMPLETION_MARKER_MUST_BE_WITHIN_RUN")
        root.mkdir(parents=True, exist_ok=True)
        atomic_json(marker, {"status": "running"})
    try:
        result = _main(args)
    except KeyboardInterrupt:
        if marker:
            atomic_json(marker, {"status": "cancelled"})
        return 130
    except BaseException:
        if marker:
            atomic_json(marker, {"status": "failed"})
        raise
    if marker:
        atomic_json(marker, {"status": "completed" if result == 0 else "failed"})
    return result


def publish_run(directory, destination):
    """Copy evaluation records, never product data, into the read-only dashboard store."""
    if destination.name != "evaluation.db" or destination.parent.name != "evaluation":
        raise ValueError("PUBLISH_DESTINATION_MUST_BE_EVALUATION_DIRECTORY")
    source = Repository(directory / "evaluation.db")
    target = Repository(destination)
    for ds in source.datasets():
        dataset = Dataset(id=ds["id"], name=ds["name"], version=ds["version"], cases=source.cases(ds["id"]))
        target.create_dataset(dataset)
    mapping_path = directory / "published.json"
    mapping = json.loads(mapping_path.read_text("utf-8")) if mapping_path.exists() else {}
    destination_key = str(destination.resolve())
    for run in source.list_runs(limit=100)["items"]:
        key = destination_key + ":" + run["id"]
        rid = mapping.get(key)
        if not rid:
            rid = target.create_run(run["dataset_id"], config=run["config"], commit_sha=run["commit_sha"], environment=run["environment"])
            mapping[key] = rid
            atomic_json(mapping_path, mapping)
        for result in source.results(run["id"]):
            target.save_case_result(rid, result, source.get_case_trace(run["id"], result.case_id)["stages"])
        target.replace_run_metrics(rid, source.get_run_summary(run["id"])["metrics"])
        target.update_run_status(rid, run["status"])
