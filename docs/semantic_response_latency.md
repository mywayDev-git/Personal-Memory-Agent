# Person scope and event meaning

This follow-up keeps Qwen3-8B-Q4_K_M and BGE-M3-Q8_0, the original
context limits, independent answer review, and exact original-source spans.
Personal databases are neither benchmark inputs nor reindexed.

## Correctness changes

An immediate person follow-up can inherit a unique role-qualified name from
the previous user question only when the completed answer has a checked
source span containing the same role-qualified referent (with whitespace and
ordinary possessive wording normalized). Assistant prose alone cannot establish
the referent. Ambiguous questions, failed turns, missing spans, and a current
explicit role do not trigger substitution. The current running turn is excluded
from the search for the immediately preceding turn. Only a complete identity
or profession lookup can anchor this shortcut; a question about that person's
friend can introduce a different referent and falls back to normal context
interpretation. Up to six consecutive checked identity/profession follow-ups
can retain the original user-specified role. Excluded roles such as
``회사 동료 민수 말고 ...`` are not treated as selected roles. Multiple requested
facts never use a single identity sentence as the entire draft.

Retrieval and answer validation receive the same scoped question. The context
model cannot replace an explicit role. A citation to a differently qualified
person with the same name fails a deterministic person check, even if the
independent model review approves it.

For explicit study-stop evidence, a denial that any stop record exists fails
the semantic check. An unknown stop date is still acceptable. A rejected
negation draft can be repaired using the existing exact-topic quotation draft;
for a narrow stop-record question this repair focuses on the stop sentence,
rather than unrelated start and note records. That repair must pass independent
review before it is returned. Temporal-scoped absence claims remain subject to
model review; a past stop does not by itself prove a present or year-specific
state. Physical folding of a study notebook and negated reports are not learning
stops.

These are conservative guards for explicit patterns, not a general proof of
semantic correctness. Other names, languages, implicit relationships, and
complex mixed events remain subject to retrieval and independent review.

## Execution limits and compound questions

The first full model regression run at `75d91ea` found two remaining failures:
the execution question repeated only a plan (5/5 incomplete responses), and a
profession-plus-cancellation-reason question returned no evidence (5/5).
Those failures remain in the raw measurements; they are not speed controls.

Commit `f806625` addresses these cases. A unique, short, explicit plan can supply
an exact quotation and the limited statement that this record cannot confirm
actual execution. A separate deterministic fulfillment check rejects plan-only
responses to an execution question even when model review approves them. The
draft is still independently reviewed; competing execution evidence or multiple
plans fall back to normal generation. Derived state tags do not override raw
source wording, and no stored facts or indexes are rewritten.

A narrowly recognized role-qualified profession question joined to an event
reason is searched as literal clauses. Each search keeps its own person and
relation conditions. The original full question remains authoritative for
generation and independent review, and the normal additional-search decision
still runs. Profession claims are not required to invent a cause merely because
another requested fact asks why. Coverage checks and model review still require
both requested facts; dependent or single questions are not split.

Only the two affected cases were rerun after this targeted fix, five times each.
Both passed 5/5. Other completed case results retain their original source
revision and cohort; their times are not pooled with the rerun.

## Measurement

Use isolated synthetic databases with the existing response-latency harness.
Warmups are separate; stop the timer when the validated response is returned,
before gold scoring and artifact output. Report refusals and wrong-person
answers as quality failures, never successful speed improvements.

The interrupted `semantic-quality-v1` preparation is excluded from statistics.
The initial `semantic-quality-v2` screen found a refused follow-up after correctly
rejecting merged people. It was stopped to fix answer completeness; its partial
results are diagnostic evidence, not the final latency control.
The first `semantic-reuse-paired5` preparation was stopped during warmups to
freeze a shared verified anchor for both variants. It is not a measured result.
The `--fixed-anchor` protocol prepares and verifies one synthetic previous turn
outside the timed interval, then clones that identical conversation DB for each
variant and repetition. Current-question understanding is still executed fresh.
The anchor SHA-256, quality check, and preparation time are recorded separately.
In the evaluator, `baseline` explicitly disables source-first drafts;
`source_first` matches the narrow production default with broad reuse disabled;
`reuse` enables the experimental context/cache bundle as well. Thus the baseline
remains an explicit guarded generation/repair control after the default changes.
RAM is summed process working sets and may double-count shared pages. VRAM is
the device total sampled once per second, including desktop usage; neither is
an exact instantaneous per-model peak. Report individual case medians and P95,
and do not pool warmups, interrupted screens, or different measurement cohorts.
Completed trials, source fingerprints, sample counts, and final decisions will
be recorded in the companion evaluation report.

## Opt-in request reuse

`PMA_REQUEST_REUSE=1` enables bounded relevance-result reuse within a single
request. Keys include the exact question, full immutable source and revision,
all compact model inputs, correction data, model configuration/revision, and
the selection implementation/type. Only successful verified selection results
are cached. The cache is bounded to 64 entries and disappears with the request.
Independent answer review, extra-search decisions, and display review are not
cached. Hits still check cancellation and the request deadline.

The same experimental option can avoid context interpretation for a complete,
explicit, source-backed person/profession lookup. This broad option remains
disabled. The five-case follow-up comparison reduced model calls from 12 to 11
and median latency from 49.310 to 42.300 seconds, but no relevance cache hits
were observed. That result came from a completed case group in an intentionally
interrupted trial and is preliminary, not an application-wide speed claim.

## Default source draft for narrow stop lookups

The independently reviewed source-first stop draft is enabled separately by
default (`PMA_SOURCE_STOP_DRAFTS=1`). It requires an explicit learning-stop
sentence, one unique candidate, and a sentence no longer than 300 characters.
It copies that complete sentence without paraphrasing or truncation. Physical
folding, conditional/negated reports, date/numeric or recent-state constraints,
negated actions, multiple requested records, and broader questions fall back to
normal generation. Every retained source still reaches independent review in full, and every final
citation remains tied to its exact original revision and span.

The balanced 20-repetition trial at commit `4b77a52` compared the focused-repair
correctness baseline against source-first drafts (then enabled by the broader
evaluation-only reuse option). Both returned the same exact stop quote in all
20 measured responses. Median latency was 35.373 vs 21.951 seconds (37.95%
lower); P95 was 38.092 vs 24.541 seconds. Calls fell from 7 to 5: one initial
generation and its rejected-draft review were removed, while the final
independent review and additional-search decision remained. There were no
selection-cache hits or context shortcuts in this stop case.

Commit `75d91ea` separates the narrow source-first default from the still-disabled
broad reuse option and adds conservative bounds for other wording and source
forms. The exact measured positive question/source are unchanged. The final
default-path quality run records this source transition separately; cohorts are
not pooled. The result applies to this explicit stop-record question, not to all
search or answer workloads. Model defaults remain unchanged.

To recover the generation/repair performance path for stop-presence lookups, set
`PMA_SOURCE_STOP_DRAFTS=0` and `PMA_REQUEST_REUSE=0`, then restart. Correctness
guards and independent review remain active. No database migration or reindex
is required for these changes.
