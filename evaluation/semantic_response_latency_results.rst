Person scope, event meaning, and request reuse
=============================================

Qwen3-8B-Q4_K_M and BGE-M3-Q8_0 remain unchanged. Synthetic DBs only.
All drafts still require independent source review and exact citation spans.

The baseline below includes the correctness fixes. Earlier wrong-person or
contradictory-stop answers are not valid speed baselines.

Request reuse stays opt-in (PMA_REQUEST_REUSE=1). These limited synthetic
measurements do not establish a general application-wide speed improvement.
Only the bounded, independently reviewed stop-source draft is enabled by default.
PMA_SOURCE_STOP_DRAFTS=0 and PMA_REQUEST_REUSE=0 restore stop-lookup generation/repair.

Targeted stop-record median reduction: 37.95% in 20 balanced repetitions per path; all 40 responses correct.

Final case coverage: 12 cases, five correct responses per case using the latest
verified result for each case. The earlier plan-only and compound-search
failures remain below and in raw data; their corrected reruns are separate.

Python: 431 passed, 0 failed. UI: four checks passed.
Mixed events: 10/10 exact source sets. Fresh multilingual questions: 90/90,
no errors or per-question regressions; positive Precision@8=0.925, Recall@8=0.800.
The multilingual metric is retrieval/fusion/top8 before optional relevance
review; final-answer quality is evaluated separately above. Original app and
both original model servers restored and healthy; no personal reindex.

semantic-stopped-final20
------------------------

Source commit: 4b77a52bb08a4b0aba11f8fa3bd66dc6948e7c1a
Preparation/warmups excluded; timer stops at validated response return.

* baseline/stopped: n=20, quality=20/20, failures=0, median=35.373s, P95=38.092s, chat calls median=7.0, selection cache hits=0.
  RAM working-set peak=4726.0 MiB; device VRAM sampled peak=7931.0 MiB.
* reuse/stopped: n=20, quality=20/20, failures=0, median=21.951s, P95=24.541s, chat calls median=5.0, selection cache hits=0.
  RAM working-set peak=4551.3 MiB; device VRAM sampled peak=7925.0 MiB.

semantic-default-quality5
-------------------------

Source commit: 75d91eab6847ec3be0a839ab9a30272b7ea2e2f8
Preparation/warmups excluded; timer stops at validated response return.

* source_first/additional_search: n=5, quality=5/5, failures=0, median=14.667s, P95=15.913s, chat calls median=8, selection cache hits=0.
  RAM working-set peak=4696.6 MiB; device VRAM sampled peak=7860.0 MiB.
* source_first/concurrent: n=5, quality=5/5, failures=0, median=19.888s, P95=21.071s, chat calls median=7, selection cache hits=0.
  RAM working-set peak=4066.9 MiB; device VRAM sampled peak=7918.0 MiB.
* source_first/followup: n=5, quality=5/5, failures=0, median=49.787s, P95=59.941s, chat calls median=12, selection cache hits=0.
  RAM working-set peak=6262.3 MiB; device VRAM sampled peak=7862.0 MiB.
* source_first/identity: n=5, quality=5/5, failures=0, median=38.592s, P95=41.467s, chat calls median=9, selection cache hits=0.
  RAM working-set peak=6339.3 MiB; device VRAM sampled peak=7869.0 MiB.
* source_first/identity_exclusion: n=5, quality=5/5, failures=0, median=33.556s, P95=35.088s, chat calls median=9, selection cache hits=0.
  RAM working-set peak=5847.8 MiB; device VRAM sampled peak=7878.0 MiB.
* source_first/long_evidence: n=5, quality=5/5, failures=0, median=78.058s, P95=79.784s, chat calls median=10, selection cache hits=0.
  RAM working-set peak=6056.8 MiB; device VRAM sampled peak=7925.0 MiB.
* source_first/multi_hop: n=5, quality=0/5, failures=0, median=14.971s, P95=15.382s, chat calls median=4, selection cache hits=0.
  RAM working-set peak=4823.6 MiB; device VRAM sampled peak=7860.0 MiB.
* source_first/negation: n=5, quality=5/5, failures=0, median=14.881s, P95=14.933s, chat calls median=7, selection cache hits=0.
  RAM working-set peak=4954.4 MiB; device VRAM sampled peak=7858.0 MiB.
* source_first/no_evidence: n=5, quality=5/5, failures=0, median=5.284s, P95=5.413s, chat calls median=3, selection cache hits=0.
  RAM working-set peak=4290.5 MiB; device VRAM sampled peak=7860.0 MiB.
* source_first/plan: n=5, quality=0/5, failures=0, median=37.724s, P95=41.691s, chat calls median=10, selection cache hits=0.
  RAM working-set peak=5029.7 MiB; device VRAM sampled peak=7860.0 MiB.
* source_first/stopped: n=5, quality=5/5, failures=0, median=21.766s, P95=23.093s, chat calls median=5, selection cache hits=0.
  RAM working-set peak=5295.1 MiB; device VRAM sampled peak=7837.0 MiB.
* source_first/stopped_date: n=5, quality=5/5, failures=0, median=26.017s, P95=31.284s, chat calls median=7, selection cache hits=0.
  RAM working-set peak=4866.8 MiB; device VRAM sampled peak=7858.0 MiB.

semantic-execution-compound-quality5
------------------------------------

Source commit: f8066256a2069bddcbeacbb4248c26d507bdcc08
Preparation/warmups excluded; timer stops at validated response return.

* source_first/multi_hop: n=5, quality=5/5, failures=0, median=44.774s, P95=45.732s, chat calls median=12, selection cache hits=0.
  RAM working-set peak=5681.5 MiB; device VRAM sampled peak=7907.0 MiB.
* source_first/plan: n=5, quality=5/5, failures=0, median=30.216s, P95=31.579s, chat calls median=8, selection cache hits=0.
  RAM working-set peak=6758.5 MiB; device VRAM sampled peak=7913.0 MiB.

Safety and interpretation
-------------------------

* Independent review and additional-search decisions are not cached or removed.
* Relevance reuse is limited to identical question, model configuration, full
  source revision, compact model inputs, correction inputs, and policy within
  one request. Cancellation/deadline checks still run on a hit.
* Explicit person resolution only skips interpretation for a complete narrow
  role-qualified identity/profession lookup with the label present in sources.
* Stop drafts preserve an entire bounded source sentence. Date constraints,
  recognized conditional/negated speech, multiple candidates and broader
  questions fall back to normal generation; instructions remain untrusted.
* RAM sums process working sets and can double-count shared pages. VRAM is
  the device total, including desktop usage, sampled once per second.
* Long-evidence replies remain brief; finite synthetic checks do not prove
  general answer completeness or universal person disambiguation.
* Five-sample P95 is the maximum; repeat a promising finalist twenty times
  before treating a speed change as robust. Do not pool separate cohorts.
