// EV-B06 R03: source-level rollback retry guard, NOT WebView2/Windows E07.
'use strict';
const fs=require('node:fs'),assert=require('node:assert/strict'),path=require('node:path');
const source=fs.readFileSync(process.argv[2] || path.resolve(__dirname,'../../stage/proposals/P01/C09/Bridge/P01WebView2NavigationBridge.cs'),'utf8');
const match=source.match(/internal bool ReturnToTrustedShell\(\)[\s\S]*?\n    \}/);
assert.ok(match, 'native return must exist on existing bridge');
const body=match[0];
assert.match(body, /_externalNavigationActive/, 'must check external active state');
assert.match(body, /_returnToShellPending\s*=\s*true/, 'must begin return pending');
assert.match(body, /AdvanceDocumentEpoch\(newDocument:\s*false\)/, 'must revoke prior native work');
assert.match(body, /_webView\.Navigate\(_trustedVirtualOrigin\.AbsoluteUri\)/, 'must return to original shell');
assert.match(body,/catch\s*\(Exception\)\s*\{[\s\S]*?_returnToShellPending\s*=\s*false;[\s\S]*?return false;[\s\S]*?\}/,
 'failed synchronous shell navigation must permit owner retry');
assert.doesNotMatch(body, /_externalNavigationActive\s*=\s*false/, 'failed navigation must not re-enable native IPC');
assert.match(source, /if \(_externalNavigationActive\)/, 'external mode must remain isolated');
assert.match(source, /if \(_returnToShellPending && IsTrustedSource\(args\.Uri\)\) return;/,
 'return must be permitted only for owner-initiated trusted navigation');
console.log('EV_B06_R03_RETRY_SOURCE_GATE 9/9 PASS; Windows/WebView2 NOT_RUN');
