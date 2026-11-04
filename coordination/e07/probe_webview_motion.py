"""Read-only physical reduced-motion evidence from installed WebView2 on Windows E07.

The temporary CDP endpoint is enabled ONLY by the independent Windows workflow,
bound to loopback in the disposable runner. No user or page data is emitted;
no DOM mutations, simulated media settings, or permission grants occur.
"""
from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys

import independent_setup_e07 as e07

SCHEMA = "NOX-E07-WEBVIEW2-REDUCED-MOTION-v1"


def validate(observation: object) -> dict:
    """Require direct live WebView2 media and actual rendered-style evidence."""
    e07.require(type(observation) is dict and
                set(observation) == {"schema", "media_reduced", "home_active",
                                      "primary_controls", "visible_nodes",
                                      "css_animated", "css_transitions",
                                      "waapi_running"} and
                observation["schema"] == SCHEMA and
                observation["media_reduced"] is True and
                observation["home_active"] is True and
                type(observation["primary_controls"]) is int and
                observation["primary_controls"] == 5 and
                type(observation["visible_nodes"]) is int and
                5 <= observation["visible_nodes"] <= 4096 and
                all(type(observation[k]) is int and observation[k] == 0
                    for k in ("css_animated", "css_transitions", "waapi_running")),
                "E07_WEBVIEW2_REDUCED_MOTION_PHYSICAL_HOLD")
    return {"status": "PASS",
            "scope": "INSTALLED_WEBVIEW2_MEDIA_CSS_WAAPI_NOT_OS_SETTING_ALONE",
            "media_reduced": True,
            "visible_nodes": observation["visible_nodes"],
            "css_animated": 0, "css_transitions": 0,
            "waapi_running": 0}


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
  ($_.url+'') -ceq 'https://nox.local/'
 })
 if($pages.Count -ne 1){throw 'PAGE_NOT_UNIQUE'}
 $uri=[uri]$pages[0].webSocketDebuggerUrl
 if($uri.Scheme -ne 'ws' -or $uri.Host -notin @('127.0.0.1','localhost') -or
    $uri.Port -ne $port -or -not $uri.AbsolutePath.StartsWith('/devtools/page/')){
    throw 'NON_LOOPBACK_CDP'
 }
 $expression=@'
(() => {
 const home=document.getElementById('home');
 const dock=document.getElementById('nox-express-primary');
 const buttons=dock?[...dock.querySelectorAll('button[data-nox-primary]')]:[];
 const nodes=[...document.querySelectorAll('#home, #home *, #nox-express-primary, #nox-express-primary *')].slice(0,4096);
 let visible=0,cssAnimated=0,cssTransitions=0;
 const activeTime=(value)=>String(value||'').split(',').some(x=>Number.parseFloat(x)>0);
 for(const el of nodes){
   const rect=el.getBoundingClientRect();
   if(rect.width<5||rect.height<5)continue;
   visible++;
   for(const pseudo of [null,'::before','::after']){
     const st=getComputedStyle(el,pseudo);
     if(st.animationName!=='none'&&activeTime(st.animationDuration))cssAnimated++;
     if(activeTime(st.transitionDuration))cssTransitions++;
   }
 }
 const running=document.getAnimations({subtree:true}).filter(x=>x.playState==='running').length;
 return {schema:'NOX-E07-WEBVIEW2-REDUCED-MOTION-v1',
   media_reduced:matchMedia('(prefers-reduced-motion: reduce)').matches,
   home_active:!!home&&home.classList.contains('active'),
   primary_controls:buttons.length,visible_nodes:visible,
   css_animated:cssAnimated,css_transitions:cssTransitions,waapi_running:running};
})()
'@
 $message=@{id=401;method='Runtime.evaluate';params=@{
   expression=$expression;returnByValue=$true;awaitPromise=$false}} |
   ConvertTo-Json -Compress -Depth 5
 $ws=[Net.WebSockets.ClientWebSocket]::new()
 $cancel=[Threading.CancellationTokenSource]::new()
 $cancel.CancelAfter(15000)
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
  $observed | ConvertTo-Json -Compress -Depth 4
 } finally {
  $ws.Dispose()
  $cancel.Dispose()
 }
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
    e07.require(0 < len(result.stdout) <= 16384,
                "E07_WEBVIEW2_CDP_READONLY_HOLD")
    try:
        observation = json.loads(result.stdout.strip())
    except (UnicodeError, ValueError):
        raise e07.Hold("E07_WEBVIEW2_CDP_JSON_HOLD") from None
    return validate(observation)
