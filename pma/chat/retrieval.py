"""Access to the existing search core while the orchestrator owns its model slot."""

from .context import merge_filters


def retrieve(service, question, *, today=None, filters=None, state_filters=None,
             selection_question=None, correction_enabled=True):
    return service.search_in_model_slot(
        question, merge_filters(state_filters or {}, filters) or None, today,
        defer_limit=True, selection_question=selection_question,
        **({"correction_enabled": False} if not correction_enabled else {}),
    )
