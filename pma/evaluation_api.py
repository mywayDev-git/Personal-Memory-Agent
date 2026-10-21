"""Evaluation viewing and explicit execution actions under session/CSRF protection."""

import json
import sqlite3
from collections import Counter
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from evaluation.comparison import compare, compare_models
from evaluation.repository import Repository

from .evaluation_execution import EvaluationExecutor, ExecutionError


class StartEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    request_id: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9._-]+$")
    profile: Literal["core", "compare", "extended", "final"] = "core"
    generation: list[str] = Field(default_factory=lambda: ["baseline"], min_length=1, max_length=30)
    embedding: list[str] = Field(default_factory=lambda: ["baseline"], min_length=1, max_length=30)


class CancelEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class EvaluationDisplay(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    show_originals: bool


def install(app, settings, static):
    if not settings.evaluation_enabled:
        return
    repo = Repository(settings.data_dir / "evaluation" / "evaluation.db")
    executor = EvaluationExecutor(settings)
    app.state.evaluation_executor = executor
    app.state.evaluation_show_originals = settings.evaluation_details
    router = APIRouter(prefix="/api/eval")

    def details_allowed():
        return app.state.evaluation_show_originals

    @router.get("/display")
    def display():
        return {"show_originals": details_allowed(), "scope": "app_session"}

    @router.put("/display")
    def set_display(data: EvaluationDisplay):
        # Explicit authenticated/CSRF-protected user preference, reset on app restart.
        app.state.evaluation_show_originals = data.show_originals
        return display()

    def execution_action(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ExecutionError as exc:
            raise HTTPException(exc.status, {"code": exc.code, "message": str(exc)}) from None

    @router.get("/execution/options")
    def execution_options():
        return execution_action(executor.options)

    @router.get("/execution")
    def execution_status():
        return execution_action(executor.status)

    @router.post("/execution", status_code=202)
    def start_evaluation(data: StartEvaluation):
        return execution_action(executor.start, **data.model_dump())

    @router.post("/execution/{job_id}/cancel", status_code=202)
    def cancel_evaluation(job_id: str, data: CancelEvaluation):
        return execution_action(executor.cancel, job_id)

    @router.get("/plan")
    def main_plan():
        from evaluation.main_suite.catalog import plan
        return plan()

    @router.get("/plan/memories")
    def planned_memories(request: Request):
        from evaluation.main_suite.sources import source_dataset
        page = paging(request)
        sources = source_dataset()["records"]
        query = request.query_params.get("q", "").strip().casefold()
        selected = [s for s in sources if not query or query in json.dumps(s, ensure_ascii=False).casefold()]
        return {"total": len(selected), "inventory_total": len(sources), **page,
                "items": [{"id": s["id"], "preview": s["text"][:140], "version": s["version"],
                           "kinds": s["kinds"], "case_count": len(s["cases"])}
                          for s in selected[page["offset"]:page["offset"] + page["limit"]]],
                "synthetic_only": True, "read_only": True, "executed": False}

    @router.get("/plan/memories/export")
    def export_planned_memories():
        from evaluation.main_suite.sources import source_dataset
        return JSONResponse(source_dataset(), headers={"Content-Disposition": 'attachment; filename="main-test-source-records.json"'})

    @router.get("/plan/memories/{source_id}")
    def planned_memory(source_id: str):
        from evaluation.main_suite.sources import source_dataset
        for source in source_dataset()["records"]:
            if source["id"] == source_id:
                return {"source": source, "synthetic_only": True, "read_only": True, "executed": False}
        raise HTTPException(404, {"code": "NOT_FOUND"})

    @router.get("/plan/dataset")
    def planned_dataset(request: Request):
        from evaluation.main_suite.catalog import PROFILES, VERSION, read, select_cases
        page = paging(request)
        profile = request.query_params.get("profile", "")
        if profile and profile not in PROFILES:
            raise HTTPException(400, {"code": "INVALID_PROFILE"})
        cases = select_cases(profile) if profile else read("scenarios.json")
        category = request.query_params.get("category", "")
        split = request.query_params.get("split", "")
        query = request.query_params.get("q", "").strip().casefold()
        selected = [c for c in cases if (not category or any(v.startswith(category + "-") for v in c["variables"]))
                    and (not split or c["split"] == split)
                    and (not query or query in json.dumps(c, ensure_ascii=False).casefold())]
        keys = ("id", "question", "expected_answer", "priority", "split", "variables", "variant")
        if request.query_params.get("view") == "questions":
            from evaluation.main_suite.presentation import question_groups
            grouped = question_groups(selected)
            inventory = read("scenarios.json")
            items = []
            for group in grouped[page["offset"]:page["offset"] + page["limit"]]:
                items.append({key: value for key, value in group.items() if key != "conditions"} | {
                    "condition_count": len(group["conditions"]), "case_ids": [c["id"] for c in group["conditions"]]})
            return {"version": VERSION, "total": len(grouped), "condition_total": len(selected),
                    "inventory_total": len(inventory), "inventory_question_total": len(question_groups(inventory)),
                    **page, "items": items, "synthetic_only": True, "executed": False}
        return {"version": VERSION, "total": len(selected), "inventory_total": len(read("scenarios.json")),
                **page, "items": [{key: c.get(key) for key in keys}
                                  for c in selected[page["offset"]:page["offset"] + page["limit"]]],
                "synthetic_only": True, "executed": False}

    @router.get("/plan/dataset/export")
    def export_planned_dataset():
        from evaluation.main_suite.catalog import VERSION, read
        from evaluation.main_suite.sources import source_dataset
        return JSONResponse({"version": VERSION, "variables": read("catalog.json"),
                             "cases": read("scenarios.json"), "source_dataset": source_dataset(), "synthetic_only": True, "executed": False},
                            headers={"Content-Disposition": 'attachment; filename="main-test-dataset.json"'})

    @router.get("/plan/dataset/{case_id}")
    def planned_case(case_id: str):
        from evaluation.main_suite.catalog import read
        from evaluation.main_suite.deduplication import question_key
        cases = read("scenarios.json")
        for case in cases:
            if case_id == case["id"]:
                return {"case": case, "conditions": [c for c in cases if question_key(c["question"]) == question_key(case["question"])],
                        "synthetic_only": True, "executed": False}
        raise HTTPException(404, {"code": "NOT_FOUND"})

    @router.get("/plan/cases/{variable_id}")
    def planned_cases(variable_id: str):
        # Static synthetic fixtures only. No personal DB, results or model calls.
        from evaluation.main_suite.catalog import read
        variables = {v["variable_id"]: v for v in read("catalog.json")}
        if variable_id not in variables:
            raise HTTPException(404, {"code": "NOT_FOUND"})
        items = [{key: c.get(key) for key in ("id", "split", "variant", "question", "expected_answer",
                 "required_facts", "forbidden_facts", "coverage_scope", "coverage_gaps", "steps", "variables", "variable_variants")}
                 for c in read("scenarios.json") if c["id"] in variables[variable_id]["cases"]]
        from evaluation.main_suite.presentation import question_groups
        return {"items": items, "question_groups": question_groups(items), "synthetic_only": True, "executed": False}

    def guarded(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except KeyError:
            raise HTTPException(404, {"code": "NOT_FOUND"}) from None
        except sqlite3.Error:
            raise HTTPException(500, {"code": "EVALUATION_STORAGE_ERROR"}) from None

    def paging(request):
        try:
            limit = int(request.query_params.get("limit", 20))
            offset = int(request.query_params.get("offset", 0))
            if not 1 <= limit <= 100 or offset < 0:
                raise ValueError()
            return dict(limit=limit, offset=offset)
        except ValueError:
            raise HTTPException(400, {"code": "INVALID_PAGINATION"}) from None

    def mask(row):
        row = dict(row)
        if row.get("evaluation", {}).get("suite_verdict"):
            row["suite_verdict"] = row["evaluation"]["suite_verdict"]
        # Evaluation viewing does not grant access to text from personal memories.
        if not details_allowed():
            for key in ("question", "expected_answer", "actual_answer"):
                row[key] = None
            row.pop("metadata", None)
            row.pop("claims", None)
            row.pop("evaluation", None)
            row["text_masked"] = True
        return row

    def compact_case(row):
        # Preview-only list responses never include raw observations, sources or traces.
        result = {key: row.get(key) for key in (
            "case_id", "verdict", "suite_verdict", "expected_behavior", "response_behavior",
            "latency_ms", "error_type", "question_type", "ambiguity_class", "text_masked")}
        result["measurement_type"] = row.get("evaluation", {}).get("measurement_type")
        def preview(value):
            if value is None:
                return None
            value = " ".join(str(value).split())
            return value[:88] + "…" if len(value) > 88 else value
        expected = row.get("expected_answer")
        if expected:
            try:
                parsed = json.loads(expected)
                if isinstance(parsed, list):
                    expected = " · ".join(str(item) for item in parsed) or None
            except (ValueError, TypeError):
                pass
        result.update(question_preview=preview(row.get("question")),
                      expected_preview=preview(expected), actual_preview=preview(row.get("actual_answer")))
        return result

    @router.get("/datasets")
    def datasets():
        return {"items": repo.datasets()}

    @router.get("/runs")
    def runs(request: Request):
        value = guarded(repo.list_runs, request.query_params.get("dataset_id"), **paging(request))
        value["items"] = [run(item["id"]) for item in value["items"]]
        return value

    @router.get("/runs/{run_id}")
    def run(run_id: str):
        value = guarded(repo.get_run, run_id)
        if value["config"].get("grading_version") in {"main-suite-v1", "main-suite-v2", "main-suite-v3", "main-suite-v4", "main-suite-v5", "main-suite-v6"}:
            value["candidate_label"] = value["config"].get("candidate")
        if not details_allowed():
            value.pop("config", None)
            value.pop("environment", None)
            value["error_message"] = "실행 오류" if value["error_message"] else None
        return value

    @router.get("/runs/{run_id}/summary")
    def summary(run_id: str):
        value = guarded(repo.get_run_summary, run_id)
        configuration = guarded(repo.get_run, run_id)["config"]
        if configuration.get("grading_version") in {"main-suite-v1", "main-suite-v2", "main-suite-v3", "main-suite-v4", "main-suite-v5", "main-suite-v6"}:
            value["suite"] = {"candidate": configuration.get("candidate"), "profile": configuration.get("profile"),
                              "threshold_status": "고정 합격선 " + configuration["gates"]["version"] if configuration.get("gates") else "합격선 미확정 · 기준값 수집",
                              "auto_applied": False}
            value["suite"]["grading_version"] = configuration["grading_version"]
            value["suite"]["metric_note"] = "답변·검색·인용 지표는 판정 가능한 표본의 조건부 비율입니다. 보안 검사를 하지 않은 실행의 노출 0건은 통과를 뜻하지 않습니다."
            value["suite"]["safety"] = value.get("metrics", {}).get("safety_checks", {}).get("details", {}).get("checks")
        return value

    @router.get("/runs/{run_id}/cases")
    def cases(run_id: str, request: Request):
        filters = {
            k: request.query_params[k]
            for k in ("verdict", "error_type", "question_type", "ambiguity_class", "q")
            if k in request.query_params
        }
        if filters.get("q") and not details_allowed():
            raise HTTPException(403, {"code": "DETAIL_ACCESS_REQUIRED"})
        compact = request.query_params.get("view") == "compact"
        value = guarded(repo.list_case_results, run_id, compact=compact, **paging(request), **filters)
        value["items"] = [mask(r) for r in value["items"]]
        if compact:
            value["items"] = [compact_case(row) for row in value["items"]]
        return value

    @router.get("/runs/{run_id}/cases/{case_id}")
    def detail(run_id: str, case_id: str):
        return mask(guarded(repo.get_case_result, run_id, case_id))

    @router.get("/runs/{run_id}/cases/{case_id}/trace")
    def trace(run_id: str, case_id: str):
        guarded(repo.get_case_result, run_id, case_id)
        if not details_allowed():
            raise HTTPException(403, {"code": "DETAIL_ACCESS_REQUIRED"})
        return guarded(repo.get_case_trace, run_id, case_id)

    @router.get("/runs/{run_id}/failures")
    def failures(run_id: str):
        rows = guarded(repo.list_case_results, run_id, limit=2147483647)["items"]
        return {
            "items": [
                {"error_type": k, "count": v}
                for k, v in Counter(
                    r["error_type"] or "unknown" for r in rows if r["verdict"] in {"fail", "error"}
                ).most_common()
            ]
        }

    @router.get("/runs/{run_id}/scenarios")
    def scenarios(run_id: str):
        rows = guarded(repo.list_case_results, run_id, limit=2147483647)["items"]
        groups = {}
        for row in rows:
            group = groups.setdefault(
                row["question_type"],
                dict(
                    question_type=row["question_type"],
                    total=0,
                    pass_count=0,
                    fail=0,
                    pending_review=0,
                    error=0,
                    not_applicable=0,
                ),
            )
            group["total"] += 1
            group["pass_count" if row["verdict"] == "pass" else row["verdict"]] += 1
        for group in groups.values():
            group["pass"] = group.pop("pass_count")
        return {"items": list(groups.values())}

    @router.get("/compare")
    def comparison(request: Request):
        left, right = (request.query_params.get(k) for k in ("left_run_id", "right_run_id"))
        if not left or not right:
            raise HTTPException(400, {"code": "RUN_IDS_REQUIRED"})
        mode = request.query_params.get("mode", "regression")
        if mode not in {"regression", "models"}:
            raise HTTPException(400, {"code": "INVALID_COMPARISON_MODE"})
        value = guarded(compare_models if mode == "models" else compare, repo, left, right)
        if not value["comparable"] and request.query_params.get("strict") == "1":
            raise HTTPException(409, {"code": "INCOMPARABLE", "reasons": value["reasons"]})
        value["left"], value["right"] = run(left), run(right)
        return value

    app.include_router(router)

    @app.get("/evaluation")
    @app.get("/evaluation/{page:path}")
    def dashboard(page: str = ""):
        return FileResponse(static / ("evaluation-datasets.html" if page == "datasets" else "evaluation.html"))
