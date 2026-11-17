# A1 ↔ A6 actual source contract acceptance

Run `NOX-49-20261117`; supports 1A01 and the unchanged original packet. No card newly accepted at native level.

This is an actual loopback ASGI server using the full existing A6 bridge and durable ledger, real SQLite, the unchanged A1 client JavaScript, and an explicitly synthetic model transport. It does not use a captured response fixture to stand in for ASGI or SQLite. No OneHost files/processes are touched.

One test block has three compound scenarios:

1. Disconnect a real HTTP stream after the first durable delta, then invoke A1 resume. Only GET snapshot/events/history are used; one model invocation remains. Verify Unicode text, snapshot, S03 user/assistant pair and distinct stable exchange/S03 record IDs.
2. Run two producer requests with separate dialog/session scopes. A1 sends exact request-ID STOP. Verify acknowledged delivery, no saved partial pair, other producer remains live and completes, and no GPU-halt claim.
3. Kill only the test harness's own ASGI subprocess. Restart it against the same temporary SQLite file. A1 GET resume observes `STREAM_INTERRUPTED_RESTART`, no done/saved, and no additional model invocation.

Command from repository workspace:

```sh
node run_cross_contract.cjs /absolute/path/to/integration/owner_mini_source /absolute/path/to/site/nox-v135-resonance-owner-bridge.js /absolute/path/to/receipt.json
```

The Node runner locates `asgi_fixture.py` beside itself. It requires Python with FastAPI/uvicorn and Node with fetch. Optional `NOX_TEST_PYTHON` selects Python. It binds only a random 127.0.0.1 port, creates its own temp directory, owns/kills only its child process, and removes its temporary DB/log after the receipt is written. The harness endpoints are test controls and must never be installed on OneHost.

Result: 3/3 compound scenarios passed, four synthetic model invocations total. Backend SHA `03fbddf0f620cef9d972bf560dba7c0d631786e13cee2bf899eabc1109811cf0`; ledger `87fc5fb69eb24652ebe4b4d02e25d58177924255a2db07f9a0d914002f173d91`; client `7525c0aaca7fa0b0dfdf3446c56161a47a811442c3448172865d5608b738b062`. No implementation mismatch found, no client/backend edits needed. Existing source commits A1 `40585de06c350a6dc66c9c674daf34982fe022aa`, A6 `cb4bc6754bae99d76e4a90fe9bcbea1caae35c5b`.

The result proves source compatibility. Actual Maya/C01–C08/S03 behavior on OneHost, GPU STOP and performance remain subject to the native gates.
