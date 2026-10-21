"""Orthogonal switches for the current product baseline, not the old repair control."""

from dataclasses import asdict, replace

OPTIONS = {
    "compact_ids": {"compact_model_ids": True},
    "token_cache": {"request_token_cache": True},
    "prefix_off": {"prompt_cache": False},
    "prefix_on": {"prompt_cache": True},
    "batch8": {"selection_batch_size": 8},
    "context_shortcut": {"explicit_context_shortcut": True},
    "selection_cache": {"selection_reuse": True},
    "planning_compact": {"compact_search_planning": True},
    "plain": {"chat_presentation": "plain"},
    "fair_scheduling": {"fair_model_scheduling": True},
}


def configured(settings, options=()):
    """Ignore process optimization env overrides; keep model and context settings."""
    if len(set(options)) != len(options) or set(options) - OPTIONS.keys():
        raise ValueError("INVALID_LATENCY_OPTIONS")
    if {"prefix_off", "prefix_on"} <= set(options):
        raise ValueError("CONFLICTING_PREFIX_OPTIONS")
    changes = dict(request_token_cache=False, request_reuse=False, selection_reuse=False,
                   explicit_context_shortcut=False, prompt_cache=None,
                   source_stop_drafts=True, selection_batch_size=4,
                   chat_presentation="reviewed", compact_search_planning=False,
                   fair_model_scheduling=False, compact_model_ids=False)
    for option in options:
        changes.update(OPTIONS[option])
    return replace(settings, **changes)


def parameters(settings):
    return {name: asdict(settings)[name] for name in (
        "request_token_cache", "request_reuse", "selection_reuse", "explicit_context_shortcut",
        "prompt_cache", "source_stop_drafts", "selection_batch_size", "chat_presentation",
        "compact_search_planning", "fair_model_scheduling", "compact_model_ids")}
