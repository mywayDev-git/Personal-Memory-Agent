# Main evaluation policy

The official main evaluation (`python -m evaluation.main_suite`) runs only when
the user explicitly asks to run the main test, model comparison, extended test,
or final candidate verification. A request to implement or fix evaluation code
does not authorize a real evaluation run.

The user may also explicitly start an evaluation with the dashboard's Test Run
button. Only that authenticated button action may launch it; viewing, polling,
reloading the dashboard, and implementing the controls must never launch it.

Never attach it to pytest collection, app startup, CI, or ordinary validation.
Offline harness tests in `tests/test_main_suite.py` and `tests/test_main_suite_answers.py` may run normally; they must
not load real models. Read `docs/main_test_plan.md` before running the suite.
Keep personal databases and ordinary model servers untouched. Evaluation does
not authorize product fixes, model downloads, threshold changes, or a change to
the application's default models.
