# Ordinary-context acceptance

One new question in the existing owned QA dialog, using the completed 442117 proxy generation and 442147 history anchors. The accepted single-login idle wait, one durable intent, one POST, full SSE/M1 verification and no-replay journal remain in place. History is checked from six messages to eight.

The existing proxy.log is read only through a held inode and a bounded fresh append window. One exact synthetic-prefix timing marker supports SOURCE_INFERRED_CONTEXT_HELPER_RETURNED; it does not expose tokenizer rounds, cache hits, an input trace, or measured speedup. Missing timing evidence never causes a repeated question. No source edit, proxy reload, model reload or queue change occurs.

Build: `python build_payload.py`. Focused check: `python test_ordinary_log_binding.py -v`. Root owns native dispatch; runtime wrapper is not executed by the build.
