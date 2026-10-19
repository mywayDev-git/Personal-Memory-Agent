"""Read-only model boundary observations; no prompt or response content is saved."""

from contextvars import ContextVar
from functools import wraps
from time import perf_counter

from .diagnostics import Reason, Stage, current_trace

_CALL = ContextVar("pma_model_observation", default=None)
_BATCHES = ContextVar("pma_selection_batches", default=None)


def observe(**fields):
    """Called only at existing transport/parse boundaries."""
    state = _CALL.get()
    if state is not None:
        state.update(fields)


def observed_model(stage):
    def decorate(function):
        @wraps(function)
        def wrapped(self, question, *args, **kwargs):
            trace = current_trace()
            if trace is None:
                return function(self, question, *args, **kwargs)
            selection = stage == Stage.EVIDENCE_SELECTION_BATCH
            evidence = (
                args[0]
                if args and stage != Stage.MODEL_UNDERSTANDING
                else kwargs.get("evidence", [])
            )
            if selection and not evidence:
                return function(self, question, *args, **kwargs)
            batches = _BATCHES.get()
            root_token = None
            if selection and batches is None:
                batches = []
                root_token = _BATCHES.set(batches)
            merge = selection and len(evidence) > getattr(getattr(self, "settings", None), "selection_batch_size", 4)
            state = {"model_called": False}
            token = _CALL.set(state)
            started = perf_counter()
            result = None
            failed = False
            try:
                result = function(self, question, *args, **kwargs)
                return result
            except Exception:
                failed = True
                raise
            finally:
                try:
                    fields = dict(
                        state,
                        status="error" if failed else "completed",
                        duration_ms=(perf_counter() - started) * 1000,
                    )
                    if failed:
                        fields["reason"] = Reason.MODEL_ERROR
                    if stage != Stage.MODEL_UNDERSTANDING:
                        fields.update(
                            input_count=len(evidence),
                            evidence_refs=[trace.memory_ref(r["id"]) for r in evidence],
                        )
                    if selection:
                        returned = ([mid for mid, decision in result.items()
                                     if decision.get("category") not in {"irrelevant", "unverified_selection"}]
                                    if isinstance(result, dict) else (result or []))
                        selected = list(dict.fromkeys(returned))
                        fields.update(
                            batched=merge or root_token is None,
                            model_selected_refs=[trace.memory_ref(i) for i in selected],
                            output_count=None if failed else len(selected),
                        )
                        if not merge:
                            fields["batch_index"] = len(batches)
                            batches.append(list(selected))
                        else:
                            fields["evidence_refs"] = [trace.memory_ref(r["id"]) for r in evidence]
                        fields["candidates"] = [
                            {
                                "memory_ref": trace.memory_ref(i),
                                "rank": index + 1,
                                "status": "unknown"
                                if failed
                                else (
                                    "selected"
                                    if i in selected
                                    else "excluded"
                                ),
                                "reason": Reason.NOT_OBSERVED
                                if failed
                                else (
                                    Reason.MODEL_NOT_SELECTED
                                    if i not in selected
                                    else None
                                ),
                            }
                            for index, i in enumerate(
                                [r["id"] for r in evidence]
                            )
                        ]
                    elif not failed and stage == Stage.MODEL_UNDERSTANDING:
                        fields.update(
                            has_time_condition=bool(
                                result.get("date_from") or result.get("date_to")
                            ),
                            has_person_condition=bool(
                                result.get("actor") or result.get("recipient")
                            ),
                        )
                    elif not failed and stage == Stage.MODEL_ANSWER:
                        fields.update(
                            regenerated=kwargs.get("feedback") is not None,
                            output_count=len(result.get("items", [])),
                            citation_refs=[
                                trace.memory_ref(i)
                                for item in result.get("items", [])
                                for i in item.get("citations", [])
                            ],
                        )
                    elif not failed and stage == Stage.MODEL_VERIFY:
                        fields["supported"] = result
                    elif not failed and stage == Stage.MODEL_REVIEW:
                        from .answer_review import accepted

                        fields["supported"] = accepted(
                            result, args[1] if len(args) > 1 else kwargs["response"]
                        )
                    trace.record_event(Stage.EVIDENCE_SELECTION_MERGE if merge else stage, **fields)
                except Exception:
                    trace.recording_failed = True
                finally:
                    _CALL.reset(token)
                    parent = _CALL.get()
                    if parent is not None and state.get("model_called"):
                        parent["model_called"] = True
                    if root_token is not None:
                        _BATCHES.reset(root_token)

        return wrapped

    return decorate
