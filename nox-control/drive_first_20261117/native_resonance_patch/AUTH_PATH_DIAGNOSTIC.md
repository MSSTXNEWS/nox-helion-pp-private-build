# Narrow auth-path diagnostic, after the second static HOLD

Parent-provided native evidence: run `44141930938`, job `134246732037`,
checkout `05b7996e2be505d61d468f5845afdfab6f115efa`, canary SHA
`633c2d1afce41f5d3d99d4fb1b6a5baf5aa488e9f3196426d0317bfa56cbf63b`.
The canary stopped at `HOLD_PATH_NAME` with dependency identifiers
`CHAT_PASSWORD_PATH`, `SECRETS`, before login/HTTP/model generation. Existing
release staging and the separately reported legacy-policy patch are independent
outcomes, not undone by this canary HOLD.

The corrected resolver recognizes arbitrary simple assignment names, so a
second identical run is not useful. The origin of SECRETS must now be observed:
import, wildcard import, conditional/nested assignment, unpacking, or another
unsupported binding. None is assumed here.

The complete pinned repository tree at
`320dae4516bc0ea3225454aa7d0528463138a95a` had 1856 entries and was not truncated;
no chat_proxy/chat-proxy named source was found. The code search for
CHAT_PASSWORD_PATH also returned no result. A source matching the exact native
proxy SHA was therefore not obtained; the resolver remains unchanged.

`native_auth_path_diagnostic.py` reads only the fixed native chat_proxy.py,
requires exact SHA `a03119817d695b1dc7ca2681a60bc564a0aa891468582bbf11b70592e2b4dfd6`,
and emits AST names, node types, import origins and binding locations. All
literal values are withheld. It never imports the app, reads a credential file,
executes the reader, contacts HTTP, or starts a model. Run only this read-only
diagnostic through the already authorized owner audit entrypoint. Do not repeat
the combined release.

Local fixture passed for import, conditional assignment, tuple unpacking and
wildcard import, with sentinel values withheld and os.system execution forbidden.
After actual binding evidence arrives, implement only its supported static path
case with a fixture and new source SHA. Native canary acceptance is still pending.

## Observed follow-up and targeted fix

Parent reports successful AST audit run `44143234300`, job `134251356059`:
line 35 is exactly `from common import SECRETS` (absolute import, no alias),
line 207 builds CHAT_PASSWORD_PATH from SECRETS, and the reader shape is unchanged.
The canary now supports only this observed import, reading the fixed sibling
common.py as stable owner-controlled source data and interpreting its constant
path chain. Its fresh SHA is returned in readiness and checked again before login.
This did not require executing the common module or changing authentication.
Targeted fixtures passed for the observed import and rejected other/relative/
aliased imports, environment calls, cycles and paths outside the allowed root.
