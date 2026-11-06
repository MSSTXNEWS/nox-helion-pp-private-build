# NOX LOCAL · Functional Mega 31–34 + Push

Scope: read-only integration shell for existing NOX, no new model or S03 database. Based on original NOX WEB V7_FIXED without deletion. The 31/32 trainer controls remain HOLD until the original trainer is verified. Checkpoints and observed `loss` are read from existing logs only. Actual Web Push is optional: requires pywebpush, VAPID keys, user subscription and running sender; client notification permission requires clicking the bell. Do not infer `PASS` from source-only build.

This stage includes: separate local port 18773; 12 quick chat tags from original, explicit server-side chat STOP, local metrics and ECharts where locally available, training log/checkpoint viewer, original S03 read-only schema probe, browser notifications, service worker and opt-in Push endpoint, automated tests.

Set paths only inside C:\NOX_HELION using `nox_connections.json` copied from `nox_connections.example.json` if actual source paths are verified. Never store sensitive keys in repo. Without that file all optional integration is `HOLD`.