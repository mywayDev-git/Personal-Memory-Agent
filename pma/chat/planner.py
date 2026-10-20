"""Response policy and server-authored actions over independently reviewed answers."""

from .interpretation import explicit_completion_conflicts, intent
from .policy import memory_disabled

RESPONSE_TYPES = dict(
    enumerate(
        [
            "DIRECT",
            "CLARIFY",
            "MULTI_RESULT",
            "LATEST",
            "CONFLICT",
            "TIMELINE",
            "PARTIAL",
            "NO_EVIDENCE",
            "LOW_CONFIDENCE",
            "COMPARE",
            "SUMMARY",
            "GENERAL",
            "HYBRID",
            "SAVE_CONFIRM",
            "CORRECTION",
            "DELETE_CONFIRM",
            "ERROR",
            "ACCESS_DENIED",
            "FOLLOW_UP",
            "ACTION_CHOICES",
            "MEMORY_CONNECTED",
            "RESUME_ACTIVITY",
            "PAST_EXPERIENCE",
            "NEXT_STEP_SUGGESTION",
            "PROGRESS_REVIEW",
            "PLAN_RECONSIDERATION",
            "MEMORY_SUPPRESSED",
        ],
        1,
    )
)
ACTION_TYPES = {
    "CHOOSE_TARGET",
    "CHOOSE_DATE",
    "CONTINUE",
    "REVIEW",
    "RESUME_TASK",
    "COMPARE",
    "SHOW_HISTORY",
    "SHOW_EVIDENCE",
    "EXPLAIN",
    "PLAN_NEXT",
    "CONFIRM_PROGRESS",
    "SAVE_PROGRESS",
    "CORRECT_RECORD",
    "RETRY_SEARCH",
    "EXPAND_SCOPE",
    "DISMISS",
}
FOLLOWUPS = {
    "CONTINUE": "확인된 진도를 바탕으로 이어갈 방법을 제안해줘. 다음 과정은 근거가 있을 때만 특정해줘.",
    "REVIEW": "확인된 내용부터 복습해줘.",
    "RESUME_TASK": "확인된 작업 상태에서 이어갈 계획을 제안해줘.",
    "EXPLAIN": "확인된 내용을 자세히 설명해줘.",
    "PLAN_NEXT": "확인된 상태를 바탕으로 다음 단계를 제안해줘.",
}


def prepare(question, interpretation, mode="memory"):
    kind = interpretation.get("intent", intent(question))
    return {
        "intent": kind,
        "memory_usage": not memory_disabled(question, mode),
        "connect_memory": kind in {"resume", "progress", "experience", "reconsider", "next_step"},
        "constraints": [
            "완료 여부와 다음 과정은 근거로 확인한다",
            "과거 해결책의 현재 적용 가능성을 확인한다",
            "거절·실패한 추천을 반복하지 않는다",
            "민감한 기억은 현재 요청에 필요한 경우만 사용한다",
        ],
        "suggestions_optional": mode != "memory",
    }


def enrich(question, response, evidence, sid, mid, context_version, *, mode="auto", metadata=None):
    """No new factual prose: all public facts come from the reviewed response."""
    metadata = metadata or {}
    disabled = memory_disabled(question, mode)
    kind = intent(question)
    items = response.get("items", [])
    personal = [i for i in items if i.get("citations")]
    cited = {cid for i in personal for cid in i["citations"]}
    sources = [row for row in evidence if row["id"] in cited]
    if response.get("status") != "needs_clarification" and explicit_completion_conflicts(sources):
        response["display"] = {
            "kind": "conflict",
            "verified": True,
            "verification": "exact_dated_opposite_completion",
            "items": [
                {"index": i, "state": "confirmed", "event": "", "event_date": ""}
                for i in range(len(items))
            ],
        }
        response["notice"] = (
            "같은 시점의 완료 여부가 충돌해 상태를 확정할 수 없습니다. 두 원문을 비교해 주세요."
        )
        from .presentation import presentation

        response["presentation"] = presentation(response)
    display = response.get("display", {}) if response.get("display", {}).get("verified") else {}
    features = []
    primary = "DIRECT"
    if disabled:
        primary = "MEMORY_SUPPRESSED"
    elif response.get("conversation_type") == "general":
        primary = "GENERAL"
    elif response.get("status") == "needs_clarification":
        primary = "CLARIFY"
    elif response.get("status") == "insufficient_evidence":
        primary = "LOW_CONFIDENCE" if evidence else "NO_EVIDENCE"
    elif display.get("kind") in {"conflict", "partial"}:
        primary = {"conflict": "CONFLICT", "partial": "PARTIAL", "events": "MULTI_RESULT"}[
            display["kind"]
        ]
    elif personal:
        primary = {
            "resume": "RESUME_ACTIVITY",
            "progress": "PROGRESS_REVIEW",
            "experience": "PAST_EXPERIENCE",
            "reconsider": "PLAN_RECONSIDERATION",
            "next_step": "NEXT_STEP_SUGGESTION",
            "latest": "LATEST",
            "timeline": "TIMELINE",
            "compare": "COMPARE",
            "summary": "SUMMARY",
        }.get(kind, "MULTI_RESULT" if display.get("kind") == "events" else "DIRECT")
    if (
        personal
        and kind in {"resume", "progress", "experience", "reconsider", "next_step"}
        and display.get("kind") not in {"conflict", "partial"}
    ):
        response["presentation"] = [{"type": "text", "item_indices": list(range(len(items)))}]
    if kind in {"save", "correction", "delete"}:
        primary = {"save": "SAVE_CONFIRM", "correction": "CORRECTION", "delete": "DELETE_CONFIRM"}[
            kind
        ]
    if personal and not disabled:
        features.append("MEMORY_CONNECTED")
        if response.get("conversation_type") == "mixed":
            features.append("HYBRID")
        if any(i.get("source_type") == "inference" for i in items):
            features.append("NEXT_STEP_SUGGESTION")
        if metadata.get("route", {}).get("reason_code") == "MEMORY_FOLLOWUP":
            features.append("FOLLOW_UP")
    facts = [{"claim": i["text"], "evidence_ids": i["citations"]} for i in personal]
    uncertainties = [
        {"claim": items[r["index"]]["text"], "evidence_ids": items[r["index"]].get("citations", [])}
        for r in display.get("items", [])
        if r.get("state") == "unknown"
    ]
    # A clarification label is an option, not an assertion that the event happened.
    if primary == "CLARIFY":
        facts = []
    suggestions = [
        {"claim": i["text"], "basis_ids": sorted(cited)}
        for i in items
        if i.get("source_type") == "inference"
    ]
    interpretation = {
        **metadata.get("memory_interpretation", {}),
        "facts": facts,
        "inferences": [],
        "suggestions": suggestions,
        "uncertainties": uncertainties,
    }
    interpretation["observations"] = [
        o for o in interpretation.get("observations", []) if set(o.get("evidence_ids", [])) <= cited
    ]
    interpretation["relations"] = [
        r
        for r in interpretation.get("relations", [])
        if set(r.get("left_ids", []) + r.get("right_ids", [])) <= cited
    ]
    actions = []

    def add(action_type, label, *, target_ids=None, query=None):
        index = len(actions)
        actions.append(
            {
                "action_id": f"{mid}:{index}",
                "type": action_type,
                "label": label,
                "target_id": (target_ids or [mid])[0],
                "target_ids": target_ids or [],
                "pending_query_id": mid if primary == "CLARIFY" else None,
                "session_id": sid,
                "message_id": mid,
                "required_permissions": ["memory_write"]
                if action_type in {"SAVE_PROGRESS", "CORRECT_RECORD", "CONFIRM_PROGRESS"}
                else ["chat_read"],
                "state": "ACTIVE",
                "context_version": context_version,
                "expiration_policy": "context_and_source_version",
                "query": query,
                "source_versions": {r["record_id"]: r["version"] for r in sources},
            }
        )

    if not disabled and primary == "CLARIFY":
        for item in items:
            if item.get("citations"):
                add("CHOOSE_TARGET", item["text"], target_ids=item["citations"], query=item["text"])
    elif not disabled and personal:
        if primary == "CONFLICT":
            add("COMPARE", "기록 비교")
            add("SHOW_HISTORY", "변경 이력")
        elif kind == "resume":
            add(
                "RESUME_TASK" if "프로젝트" in question or "작업" in question else "CONTINUE",
                "이어서 진행",
            )
            add("REVIEW", "이전 내용 복습")
        elif kind == "progress":
            add("SHOW_HISTORY", "진행 이력")
            add("CONFIRM_PROGRESS", "진도 확인·정정")
        elif kind == "experience":
            add("SHOW_EVIDENCE", "이전 해결 기록")
            add("PLAN_NEXT", "현재 상황에 적용 검토")
        elif kind == "reconsider" or primary == "CONFLICT":
            add("COMPARE", "기록 비교")
            add("SHOW_HISTORY", "변경 이력")
        elif kind == "timeline" or kind == "latest":
            add("SHOW_HISTORY", "변경 이력")
        elif kind == "compare":
            add("COMPARE", "근거 비교")
        elif kind == "next_step":
            add("PLAN_NEXT", "다음 단계 계획")
        elif kind == "correction":
            add("CORRECT_RECORD", "수정할 기록 확인")
        elif kind == "delete":
            add("SHOW_EVIDENCE", "삭제할 기록 확인")
    if kind == "save":
        add("SAVE_PROGRESS", "저장할 내용 확인")
    if primary in {"NO_EVIDENCE", "LOW_CONFIDENCE"} and not disabled:
        add("RETRY_SEARCH", "다시 검색", query=question)
        if metadata.get("searches") and any(s.get("filters") for s in metadata["searches"]):
            add("EXPAND_SCOPE", "전체 기간에서 검색", query=question)
    if suggestions and actions and len(actions) < 3:
        add("DISMISS", "나중에")
    if len(actions) > 1 and primary != "CLARIFY":
        features.append("ACTION_CHOICES")
    refs = [
        {
            "memory_id": r["id"],
            "record_id": r["record_id"],
            "record_version": r["version"],
            "source_type": "imported_document" if r.get("source_location") else "personal_memory",
            "source_location": r.get("source_location") or r.get("revision_id"),
            "event_time": r.get("time"),
            "created_at": r.get("recorded_at"),
            "updated_at": r.get("updated_at"),
            "relevance": r.get("score"),
            "support_type": "cited",
            "spans": [c for c in response.get("citation_details", []) if c["memory_id"] == r["id"]],
        }
        for r in sources
    ]
    response.update(
        response_id=mid,
        conversation_id=sid,
        response_version=1,
        primary_response_type=primary,
        response_features=features,
        answer_text="\n\n".join(
            ([response["notice"]] if primary == "CONFLICT" and response.get("notice") else [])
            + [i["text"] for i in items]
        ),
        grounding_status="suppressed"
        if disabled
        else "verified"
        if personal
        else "not_applicable"
        if primary == "GENERAL"
        else "unconfirmed",
        evidence_refs=refs,
        uncertainty=uncertainties,
        interpretation=interpretation,
        memory_context={
            "enabled": not disabled,
            "source_ids": sorted(cited),
            "status_as_of": [
                o.get("event_time")
                for o in interpretation.get("observations", [])
                if o.get("event_time")
            ],
        },
        ui_actions=actions,
        context_update={"version": context_version},
        error_state=None,
    )
    return response
