# R29 A02 PASS09 — native SIP quote/consent lifecycle

Parent c0e77ce005da64ea3bf18a5f9f328d34a787b5d1. A02 9/10 real approaches; maps to R29 matrix A02 approach09 / V16 §26.4.9, not a canonical accepted product TaskID.

Reused exact ConsentGatedSip section and math import from A05 p02_capabilities.py donor d721cd9608d62052060ae2c7ff6db240b281802f. Quote freshness/type/finite expiry is checked before and after blocking native provider verification/approval and before dial. STOP during verification prevents even prompting; STOP during consent prevents dial and quote consumption. Fresh verified/approved quote remains one-use. No provider, tariffs, new store or outgoing call was created.

RED: donor four tests produced five failed subcases; two additional STOP callback tests both failed against prior source. GREEN:32 selected tests covering donor SIP expiry/voice-output, new STOP callbacks and all20 consent/request/result/lifecycle donor checks. Offline provider callbacks only; no physical SIP or Windows claim.

Command: PYTHONPATH=Packages/P02/worker-python python -m unittest test_p02_voice_sip_r27.SipExpiryTests test_p02_voice_sip_r27.VoiceOutputTests test_p02_sip_stop_r29.SipStopBoundaries test_p02_voice_consent_r27.ConsentTests test_p02_voice_request_r27.RequestTests test_p02_voice_result_r27.ResultTests test_p02_voice_lifecycle_r27.LifecycleTests -v

An append-only PASS08 handoff correction replaces the stale runtime donor reference with its authenticated current blob dde0caf8fe8d0a56a9ec7d0b985a95ba2aec05fd; reused local bytes exactly match the remote donor. No code correction was needed for that metadata mistake.

Remaining ready same-owner source: A04 SQLite global-key/storage-unique and native origin/boolean proof admission. Remaining composition: actual SIP provider quote verification, current native approval and cancellation authority, already-existing host callbacks. Native same-SHA acceptance is distinct and not performed. VoiceSession/timeout/history/registration originals and approved graphics remain unchanged; no final integration/build/CI.

Lesson: validate quote/STOP again after each blocking callback, before taking an irreversible action; do not consume permission merely because a cancelled native dialog returned true.
