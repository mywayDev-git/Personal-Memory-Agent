"""Read-only evaluation routes protected by the existing session middleware."""

import sqlite3
from collections import Counter

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from evaluation.comparison import compare
from evaluation.repository import Repository


def install(app, settings, static):
    if not settings.evaluation_enabled:
        return
    repo = Repository(settings.data_dir / "evaluation" / "evaluation.db")
    router = APIRouter(prefix="/api/eval")

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
        # Evaluation viewing does not grant access to text from personal memories.
        if not settings.evaluation_details:
            for key in ("question", "expected_answer", "actual_answer"):
                row[key] = None
            row.pop("metadata", None)
            row.pop("claims", None)
            row.pop("evaluation", None)
            row["text_masked"] = True
        return row

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
        if not settings.evaluation_details:
            value.pop("config", None)
            value.pop("environment", None)
            value["error_message"] = "실행 오류" if value["error_message"] else None
        return value

    @router.get("/runs/{run_id}/summary")
    def summary(run_id: str):
        return guarded(repo.get_run_summary, run_id)

    @router.get("/runs/{run_id}/cases")
    def cases(run_id: str, request: Request):
        filters = {
            k: request.query_params[k]
            for k in ("verdict", "error_type", "question_type", "ambiguity_class", "q")
            if k in request.query_params
        }
        if filters.get("q") and not settings.evaluation_details:
            raise HTTPException(403, {"code": "DETAIL_ACCESS_REQUIRED"})
        value = guarded(repo.list_case_results, run_id, **paging(request), **filters)
        value["items"] = [mask(r) for r in value["items"]]
        return value

    @router.get("/runs/{run_id}/cases/{case_id}")
    def detail(run_id: str, case_id: str):
        return mask(guarded(repo.get_case_result, run_id, case_id))

    @router.get("/runs/{run_id}/cases/{case_id}/trace")
    def trace(run_id: str, case_id: str):
        guarded(repo.get_case_result, run_id, case_id)
        if not settings.evaluation_details:
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
        value = guarded(compare, repo, left, right)
        if not value["comparable"] and request.query_params.get("strict") == "1":
            raise HTTPException(409, {"code": "INCOMPARABLE", "reasons": value["reasons"]})
        value["left"], value["right"] = run(left), run(right)
        return value

    app.include_router(router)

    @app.get("/evaluation")
    @app.get("/evaluation/{page:path}")
    def dashboard(page: str = ""):
        return FileResponse(static / "evaluation.html")
