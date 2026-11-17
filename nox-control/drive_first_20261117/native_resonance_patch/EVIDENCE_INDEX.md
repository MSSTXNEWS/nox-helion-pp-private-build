# Evidence index

- NATIVE_UI_APPLY_PARENT_REPORT.json: prior native static UI apply, parent-reported.
- evidence/NATIVE_CANARY_V4_RESULT_20261117.json: actual run44147786817/job134267516216; one own model request, then bounded failure. It is not a successful canary receipt.
- evidence/HTML_TRANSFORM_MATCH.json: every predicted HTML fingerprint matched v4, using exact saved owner UI source.
- reviews/reconcile: independent review of core7b82ccbb…,3 focused tests passed without native calls. Author fixture source is in tests/test_acceptance.py; the independent report/log are preserved as evidence.
- reviews/RECONCILE_WRAPPER_REVIEW.json: exact wrapper f8e29f94… binds core7b82ccbb… to read-only fixed own-dialog reconciliation.

Native read-only reconciliation has not been observed by this package author. The current core does not infer lost v4 terminal flags or timing and cannot repeat generation through the read-only transport.

Exact owner UI source: https://github.com/MSSTXNEWS/nox-helion-pp-private-build/blob/432b6195e7a8e3e56b32b9abcfd258dfc21465ec/nox-control/owner_chat_ui.py
Native v4: https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/44147786817/job/134267516216
