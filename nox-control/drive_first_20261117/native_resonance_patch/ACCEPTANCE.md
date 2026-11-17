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
The observed native `from common import SECRETS` is the sole supported cross-file
binding: only the fixed sibling `/root/nox/scripts/common.py` is read as data.
Its owner/mode, regular-file type and stable inode/stat/path are checked, its SHA
is reported, and only the SECRETS path dependency chain is interpreted. That SHA
is checked again before login. No alias, relative import, wildcard, other module,
environment call or module execution is accepted. This records current source
identity; it does not claim inspection of the running process's cached module.
the native app is never imported. The secret is read privately
only for official `/chat/login`. All later requests use a new private cookie
jar, which is cleared on exit.

Acceptance hashes the authenticated `/nox-web-v29/pc/resonance.html`, its new
CSS and new JS. HTML accepts the exact source bytes or only the known existing
`_OwnerStatic` single injection of `/nox-web-v29/native-owner.js` immediately
after `<head>`; removing that one exact insertion must recover the pinned SHA.
Duplicate or other overlays fail. CSS/JS retain strict raw SHA checks.

Native v4 run `44147786817` subsequently established the additional exact HTML
composition: known owner-head script plus the existing `owner_chat_ui.decorate_html`
mount relocation, shell CSS marker and four owner scripts. The 14,519 served
bytes had SHA `e736c54022439cc2cddfaba17aeebf9844e2f6cf35a3b07c3837a8c0531b70cc`,
identical to the independently computed fixture. Its 28 reference fingerprints
and changed-span fingerprints also matched; the pinned bridge projection calls
`decorate_html`, while the wrapper projection has no HTML replacement. The
source `owner_chat_ui.py` was recovered from GitHub commit
`432b6195e7a8e3e56b32b9abcfd258dfc21465ec`: 4,854 bytes, SHA
`da2cea21d21d3c1129bcb6621cd5293469a085ad861924a8c5cc63981577a866`, identical
to the prior native export. Acceptance now also checks that exact installed
owner-UI source SHA and permits only the observed whole-response SHA/length.
It does not execute the decorator, strip scripts, or accept arbitrary overlays.

Version 4 separates two results: `ui_asset_acceptance_pass` proves those three
served assets; `native_chat_canary_pass` proves the authenticated chat, model
stream and exact own S03 history. `native_canary_pass` is their conjunction.
An unrecognized served HTML change remains `HOLD_SERVED_ASSET_HASH` overall
even when the chat works. Because this canary never executes HTML, that isolated
UI mismatch does not block the single independently guarded chat test. Source
identity, official authentication, owner runner binding, idle priority, free
model slots, maintenance lease and own-session STOP remain mandatory. A failed
guard still stops the run. Unknown HTML is never normalized or accepted.

The pinned `/root/nox/scripts/nox_web29_onehost_18775.py` wrapper is also checked
before HTTP: SHA `0a0165e5b061f88ec60009c49a3c12e9823a45b89044604186e307c81fb701e6`,
as reported by the parent from native binding identities. Asset diagnostics
contain only HTTP status, sanitized MIME/encoding, byte length/SHA, fixed marker
counts, static reference fingerprints and bounded changed-span fingerprints.
No HTML, arbitrary URL, response-header value, source literal or source body is
exported. On a UI mismatch, fixed-file bridge/wrapper AST projections identify
relevant functions and calls, replacement argument shapes and literal lengths
and SHA hashes, capped at 16 KB per source. No native source is imported or
executed. These projections diagnose a transform; they do not authorize a new
transform or claim that disk source equals process memory.

It creates one uniquely named QA dialog, asks `17 + 25` once,
reads NDJSON meaningful deltas and terminal receipt, and reads only that own
dialog's last two messages. PASS requires exactly numerical 42, saved and
S03-integrated terminal receipt, and an exact persisted user/assistant pair.
The report publishes only 42 or WITHHELD plus a SHA; arbitrary model text,
response bodies, password, cookie and secret filename are never exported.
Immediately after a terminal stream, the safe stream receipt is recorded before
close/history handling. A later failure includes a fixed phase and exception
class, never raw exception text. Own-history evidence includes HTTP status,
sanitized MIME, length/SHA and JSON decoding status without response contents.

## Read-only reconciliation after v4

V4 created one dialog and sent one model request, then reported a bounded failure
after returning from `read_stream`; the prior report did not preserve its stream
receipt fields. Absence of a scoped-STOP attempt supports a control-flow inference,
not a recovered terminal flag or latency measurement. Do not repeat generation
to reconcile that unknown outcome.

```text
python3 native_acceptance.py --reconcile-owned-dialog --expected-source-sha <exact checkout SHA>
python3 native_acceptance.py --assets-only --expected-source-sha <exact checkout SHA>
```

The first command permits only fixed own dialog
`5ce69137da0a4c42a0387917c8567d52`, created by run `44147786817` / job
`134267516216` / owner request `6957085526`. It uses a fresh official login,
the same source/owner/idle/free-slot/lease guards, three asset GETs and one
history GET with `limit=2`. Its read-only transport rejects dialog creation,
model POST, STOP and a different dialog ID even if a caller attempts them.
The prior session cookie is gone; it is neither reused nor impersonated.
The read-only deadline is 20 seconds, with no retry and no STOP on exit.

`reconciliation_pass` requires the pinned UI and exactly the fixed dialog's
synthetic QA question, numeric answer 42, user/assistant roles, and a common
nonempty exchange ID. Question/answer/exchange IDs are hashed, apart from 42.
`native_canary_pass` remains false: terminal saved/S03 flags and measured TTFA
from v4 are not recoverable merely by reading history. The separate positive
history result must not be relabeled as a new successful generation.

Global wall deadline is 56 seconds including setup, with up to 2 additional
seconds for a scoped stop. The same private cookie jar may POST `/api/nox/stop`
only after AST verification of the separately pinned bridge's nested
`register_native_v29_chat.stream_stop` handler: request scope
selects the active event and only that event is set. Missing/unknown scope
semantics HOLD before generation. There are no retries. The QA dialog is left
as evidence, not silently deleted. A failed history check may still leave a
completed own generation; the report does not claim rollback.

Local validation: six focused tests passed, covering rejected AST code/path
escape with nonleaking errors, scoped/global stop distinction, actual NDJSON
and missing terminal, exact own history and withheld unexpected model text;
unknown HTML fingerprints and AST literal withholding; and a complete local
fake transport run proving one own dialog/request, successful chat/S03, failed
UI and overall HOLD without leaking credential, cookie or HTML sentinels.
The updated fixtures also verify the exact observed owner-UI composition and
reject mutated bytes or an unverified owner-UI pin; a full read-only reconciliation
performs zero generation/dialog/STOP calls; direct transport attempts to mutate
or read another dialog fail before networking; malformed HTTP history exports
only safe metadata and an exception class.
No native HTTP request or deployment was executed by the author. Browser
geometry and external tunnel availability are separate acceptance checks;
loopback PASS alone does not certify a publicly working link.
