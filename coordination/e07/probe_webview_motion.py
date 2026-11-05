"""Read-only physical reduced-motion evidence from installed WebView2 on Windows E07.

The temporary CDP endpoint is enabled ONLY by the independent Windows workflow,
bound to loopback in the disposable runner. No user or page data is emitted;
no DOM mutations, simulated media settings, or permission grants occur.
"""
from __future__ import annotations

import base64
import binascii
import json
import os
import re
import subprocess
import sys

import independent_setup_e07 as e07

SCHEMA = "NOX-E07-WEBVIEW2-REDUCED-MOTION-v2"


def validate(observation: object) -> dict:
    """Require direct live WebView2 media and actual rendered-style evidence."""
    e07.require(type(observation) is dict and
                set(observation) == {"schema", "media_reduced", "home_active",
                                      "primary_controls", "visible_nodes",
                                      "css_animated", "css_transitions",
                                      "waapi_running", "d02_scope_count",
                                      "d02_visible_nodes"} and
                observation["schema"] == SCHEMA and
                observation["media_reduced"] is True and
                observation["home_active"] is True and
                type(observation["primary_controls"]) is int and
                observation["primary_controls"] == 5 and
                type(observation["d02_scope_count"]) is int and
                observation["d02_scope_count"] == 1 and
                type(observation["d02_visible_nodes"]) is int and
                5 <= observation["d02_visible_nodes"] <= 4096 and
                type(observation["visible_nodes"]) is int and
                5 <= observation["visible_nodes"] <= 4096 and
                all(type(observation[k]) is int and observation[k] == 0
                    for k in ("css_animated", "css_transitions", "waapi_running")),
                "E07_WEBVIEW2_REDUCED_MOTION_PHYSICAL_HOLD")
    return {"status": "PASS",
            "scope": "INSTALLED_WEBVIEW2_MEDIA_CSS_WAAPI_NOT_OS_SETTING_ALONE",
            "media_reduced": True,
            "visible_nodes": observation["visible_nodes"],
            "d02_visible_nodes": observation["d02_visible_nodes"],
            "d02_scope_count": 1,
            "css_animated": 0, "css_transitions": 0,
            "waapi_running": 0}


def select_unique_home_observation(observations: object) -> dict:
    """Choose one physically observed active HOME, not the first matching CDP tab."""
    e07.require(type(observations) is list and 1 <= len(observations) <= 4
                and all(type(item) is dict for item in observations),
                "E07_WEBVIEW2_CDP_PAGE_NOT_UNIQUE_HOLD")
    homes = [item for item in observations if item.get("home_active") is True]
    e07.require(len(homes) == 1, "E07_WEBVIEW2_CDP_PAGE_NOT_UNIQUE_HOLD")
    return validate(homes[0])


CDP_WIRE_PREFIX = "NOX_E07_CDP_V3:"


def decode_observation_wire(stdout: str) -> dict:
    """Parse a bounded ASCII frame from live CDP, never promote noisy stdout."""
    e07.require(type(stdout) is str and 0 < len(stdout) <= 16384,
                "E07_WEBVIEW2_CDP_READONLY_HOLD")
    wire = stdout.strip()
    e07.require(re.fullmatch(r"NOX_E07_CDP_V3:[A-Za-z0-9+/]+={0,2}", wire) is not None,
                "E07_WEBVIEW2_CDP_JSON_HOLD")
    try:
        decoded = base64.b64decode(wire[len(CDP_WIRE_PREFIX):], validate=True)
        if not 0 < len(decoded) <= 8192:
            raise ValueError("bounded CDP JSON required")
        observations = json.loads(decoded.decode("utf-8", errors="strict"))
    except (ValueError, UnicodeError, binascii.Error):
        raise e07.Hold("E07_WEBVIEW2_CDP_JSON_HOLD") from None
    return select_unique_home_observation(observations)


def probe() -> dict:
    """Read WebView2's real matchMedia/computed styles without emulation."""
    e07.require(sys.platform == "win32" and
                os.environ.get("GITHUB_ACTIONS") == "true" and
                os.environ.get("RUNNER_OS") == "Windows" and
                os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted" and
                os.environ.get("GITHUB_REPOSITORY") ==
                    "MSSTXNEWS/nox-helion-pp-private-build" and
                os.environ.get("NOX_E07_DEVTOOLS_PORT") == "9222" and
                os.environ.get("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS") ==
                    "--remote-debugging-address=127.0.0.1 --remote-debugging-port=9222",
                "E07_WEBVIEW2_CDP_CI_ONLY_HOLD")
    # A fixed expression reads booleans/counters only. It cannot write DOM,
    # change media preferences, enumerate files, or access private model data.
    script = r"""
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.Encoding]::UTF8
try {
 $port=9222
 try {
  $targets=@(Invoke-RestMethod -Uri 'http://127.0.0.1:9222/json/list' -TimeoutSec 5)
 } catch { throw 'ENDPOINT_UNREACHABLE' }
 $pages=@($targets | Where-Object {
  $_.type -eq 'page' -and
  ($_.url+'') -cin @('https://nox.local/','https://nox.local/index.html')
 })
 # All candidates are REAL trusted-origin WebView2 targets on the runner.
 # Never select by tab order; reject multiple live HOME pages after CDP probing.
 if($pages.Count -lt 1 -or $pages.Count -gt 4){throw 'PAGE_NOT_UNIQUE'}
 $observations=[System.Collections.Generic.List[object]]::new()
 foreach($page in $pages){
  $uri=[uri]$page.webSocketDebuggerUrl
  if($uri.Scheme -ne 'ws' -or $uri.Host -notin @('127.0.0.1','localhost') -or
     $uri.Port -ne $port -or -not $uri.AbsolutePath.StartsWith('/devtools/page/')){
     throw 'NON_LOOPBACK_CDP'
  }
 $expression=@'
(() => {
 // /json/list is a pre-evaluation snapshot. A live WebView2 may navigate;
 // bind the physical DOM evidence to CURRENT trusted origin, fail closed.
 if(location.origin!=='https://nox.local' ||
    !['/','/index.html'].includes(location.pathname)) {
   throw new Error('NOX_CDP_ORIGIN_DRIFT');
 }
 const home=document.getElementById('home');
 const dock=document.getElementById('nox-express-primary');
 const buttons=dock?[...dock.querySelectorAll('button[data-nox-primary]')]:[];
 // Enumerate the installed ORIGINAL D02 scene first, then the five primary
 // controls. Never silently truncate: an unobserved tail could still animate.
 const scopes=[...document.querySelectorAll('.nox-cinema-scope')];
 const d02Nodes=scopes.length===1?[...scopes[0].querySelectorAll('*')]:[];
 const candidates=[...new Set([...scopes,...d02Nodes,
   ...document.querySelectorAll('#home, #home *, #nox-express-primary, #nox-express-primary *')])];
 const tooMany=candidates.length>4096;
 const nodes=tooMany?[]:candidates;
 const d02Set=new Set(d02Nodes);
 let visible=0,d02Visible=0,cssAnimated=0,cssTransitions=0;
 const activeTime=(value)=>String(value||'').split(',').some(x=>Number.parseFloat(x)>0);
 for(const el of nodes){
   const rect=el.getBoundingClientRect();
   // Visibility counts remain geometric. Real CSS/WAAPI motion checks inspect
   // ALL original D02/primary nodes, including small and offscreen particles.
   if(rect.width>=5&&rect.height>=5){
     visible++;
     if(d02Set.has(el))d02Visible++;
   }
   for(const pseudo of [null,'::before','::after']){
     const st=getComputedStyle(el,pseudo);
     if(st.animationName!=='none'&&activeTime(st.animationDuration))cssAnimated++;
     if(activeTime(st.transitionDuration))cssTransitions++;
   }
 }
 const running=document.getAnimations({subtree:true}).filter(x=>x.playState==='running').length;
 return {schema:'NOX-E07-WEBVIEW2-REDUCED-MOTION-v2',
   media_reduced:matchMedia('(prefers-reduced-motion: reduce)').matches,
   home_active:!!home&&home.classList.contains('active'),
   primary_controls:buttons.length,d02_scope_count:scopes.length,
   d02_visible_nodes:d02Visible,visible_nodes:tooMany?4097:visible,
   css_animated:cssAnimated,css_transitions:cssTransitions,waapi_running:running};
})()
'@
 $message=@{id=401;method='Runtime.evaluate';params=@{
   expression=$expression;returnByValue=$true;awaitPromise=$false}} |
   ConvertTo-Json -Compress -Depth 5
 $ws=[Net.WebSockets.ClientWebSocket]::new()
 $cancel=[Threading.CancellationTokenSource]::new()
 $cancel.CancelAfter(5000)
 try {
  $ws.ConnectAsync($uri,$cancel.Token).GetAwaiter().GetResult()
  $bytes=[Text.Encoding]::UTF8.GetBytes($message)
  $ws.SendAsync([ArraySegment[byte]]::new($bytes),
   [Net.WebSockets.WebSocketMessageType]::Text,$true,$cancel.Token
  ).GetAwaiter().GetResult()
  $observed=$null
  for($turn=0;$turn -lt 12;$turn++){
   $buffer=New-Object byte[] 65536
   $builder=[Text.StringBuilder]::new()
   do {
    $part=$ws.ReceiveAsync([ArraySegment[byte]]::new($buffer),$cancel.Token).GetAwaiter().GetResult()
    if($part.MessageType -ne [Net.WebSockets.WebSocketMessageType]::Text){
     throw 'CDP_NOT_TEXT'
    }
    [void]$builder.Append([Text.Encoding]::UTF8.GetString($buffer,0,$part.Count))
    if($builder.Length -gt 131072){throw 'CDP_REPLY_TOO_LARGE'}
   }while(-not $part.EndOfMessage)
   $reply=$builder.ToString() | ConvertFrom-Json
   if($reply.id -eq 401){
    if($null -ne $reply.error -or $null -ne $reply.result.exceptionDetails){
     throw 'CDP_RUNTIME_ERROR'
    }
    $observed=$reply.result.result.value
    break
   }
  }
  if($null -eq $observed){throw 'CDP_NO_EVALUATION'}
  [void]$observations.Add($observed)
 } finally {
  $ws.Dispose()
  $cancel.Dispose()
 }
 } # each trusted WebView2 target
 # Send one bounded ASCII envelope; PowerShell host stdout codepages must not
 # corrupt actual read-only CDP media/CSS/WAAPI evidence on Windows.
 $receiptJson=ConvertTo-Json -InputObject @($observations.ToArray()) -Compress -Depth 6
 if([string]::IsNullOrWhiteSpace($receiptJson) -or $receiptJson.Length -gt 8192){
    throw 'CDP_REPLY_TOO_LARGE'
 }
 [Console]::Out.WriteLine('NOX_E07_CDP_V3:'+
    [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($receiptJson)))
} catch {
 $reason=$_.Exception.Message+''
 $allowed=@('ENDPOINT_UNREACHABLE','PAGE_NOT_UNIQUE','NON_LOOPBACK_CDP',
   'CDP_NOT_TEXT','CDP_REPLY_TOO_LARGE','CDP_RUNTIME_ERROR','CDP_NO_EVALUATION')
 if($allowed -notcontains $reason){$reason='READONLY'}
 Write-Output ('E07_WEBVIEW2_CDP_'+$reason+'_HOLD')
 exit 2
}
"""
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    try:
        result = subprocess.run(
            ["pwsh", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
            capture_output=True, timeout=32, check=False, encoding="utf-8",
            errors="replace")
    except (OSError, subprocess.TimeoutExpired):
        raise e07.Hold("E07_WEBVIEW2_CDP_PROCESS_HOLD") from None
    if result.returncode != 0:
        reason=result.stdout.strip()
        if re.fullmatch(
            r"E07_WEBVIEW2_CDP_(?:ENDPOINT_UNREACHABLE|PAGE_NOT_UNIQUE|"
            r"NON_LOOPBACK_CDP|CDP_NOT_TEXT|CDP_REPLY_TOO_LARGE|"
            r"CDP_RUNTIME_ERROR|CDP_NO_EVALUATION|READONLY)_HOLD", reason
        ):
            raise e07.Hold(reason)
        raise e07.Hold("E07_WEBVIEW2_CDP_READONLY_HOLD")
    return decode_observation_wire(result.stdout)
