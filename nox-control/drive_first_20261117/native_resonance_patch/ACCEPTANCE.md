# Native Resonance acceptance

`native_acceptance.py` is a separate bounded canary, not an installer or server.
Only the existing authorized owner repair runner should invoke it. That runner
must keep its current actor / repository / issue checks and host pins. The
script requires its `NOX_OWNER_REQUEST_ID` numeric comment ID and exact
`NOX_OWNER_SOURCE_SHA` checkout SHA. It does not invent an actor environment
variable or claim that environment variables authenticate an owner.

Default invocation is offline readiness: source SHA, safe AST path resolution,
scoped stop proof, installed asset SHA and current idle priority. It does not
read the password, log in, create a dialog or contact a model.

Explicit native acceptance after patch installation:

```text
python3 native_acceptance.py --canary --expected-source-sha <exact checkout SHA> --maintenance-lock-fd <inherited owner lease FD>
```

Without the FD the script takes the same existing `owner_maintenance.lock`
nonblocking; when the parent holds it, the parent must pass the inherited FD.
No other lock, server, daemon or model is created. Existing `CHAT_ACTIVE=0`,
`MODE=IDLE` and all current 8098 slots idle are required before each synthetic
mutation. This lease serializes cooperating maintenance/background workers; it
is not a claim that browser owners cannot start a new chat concurrently.

The only hosts are 127.0.0.1:18775 (existing wrapper → 8080) and
127.0.0.1:8098 (`GET /slots` only). Redirects and proxy environment use are
disabled. The existing `_read_chat_password` is interpreted through a narrow
AST grammar including its actual `try/except OSError: return ''` fallback;
all top-level simple-name assignments are indexed, but only the dependency
chain of `CHAT_PASSWORD_PATH` is interpreted. Identifier spelling is unrestricted;
the supported path syntax, final root and symlink guards are unchanged. Calls to
environment readers or other functions, cycles and duplicate assignments in the
used chain HOLD. A failure may publish bounded ASCII dependency names, never
their values, source or paths. Unrelated assignments are never interpreted.
the native app is never imported. The secret is read privately
only for official `/chat/login`. All later requests use a new private cookie
jar, which is cleared on exit.

Acceptance hashes the authenticated `/nox-web-v29/pc/resonance.html`, its new
CSS and new JS. HTML accepts the exact source bytes or only the known existing
`_OwnerStatic` single injection of `/nox-web-v29/native-owner.js` immediately
after `<head>`; removing that one exact insertion must recover the pinned SHA.
Duplicate or other overlays fail. CSS/JS retain strict raw SHA checks.
It creates one uniquely named QA dialog, asks `17 + 25` once,
reads NDJSON meaningful deltas and terminal receipt, and reads only that own
dialog's last two messages. PASS requires exactly numerical 42, saved and
S03-integrated terminal receipt, and an exact persisted user/assistant pair.
The report publishes only 42 or WITHHELD plus a SHA; arbitrary model text,
response bodies, password, cookie and secret filename are never exported.

Global wall deadline is 56 seconds including setup, with up to 2 additional
seconds for a scoped stop. The same private cookie jar may POST `/api/nox/stop`
only after AST verification of the separately pinned bridge's nested
`register_native_v29_chat.stream_stop` handler: request scope
selects the active event and only that event is set. Missing/unknown scope
semantics HOLD before generation. There are no retries. The QA dialog is left
as evidence, not silently deleted. A failed history check may still leave a
completed own generation; the report does not claim rollback.

Local validation: three focused tests passed, covering rejected AST code/path
escape with nonleaking errors, scoped/global stop distinction, actual NDJSON
and missing terminal, exact own history and withheld unexpected model text.
No native HTTP request or deployment was executed by the author. Browser
geometry and external tunnel availability are separate acceptance checks;
loopback PASS alone does not certify a publicly working link.
