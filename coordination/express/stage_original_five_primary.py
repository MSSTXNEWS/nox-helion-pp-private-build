"""Add five accessible EXPRESS primary actions to an immutable R11 HOME copy.

The original HOME, host, menu and backend are never rewritten. Caller stages
only a disposable NSIS payload and verifies the published digest separately.
No synthetic install/model/training ACKs or permission changes are permitted.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

ORIGINAL_BYTES = 94908
ORIGINAL_SHA256 = "b57d58bb001c9826feb3bf7ff19510d047c7ec2926ee8b703538dfca886a960b"
MARKER = 'id="nox-express-primary"'

# Original controls are invoked only by a real user click. Unknown routes HOLD.
# MODELS delegates to the already installed original WPF bridge, which enforces
# native SID/ACL/consent and may legitimately return HOLD if offline.
INSERT = r'''<!-- NOX EXPRESS 5 original-home primary actions; no additional host -->
<style id="nox-express-primary-style">
#nox-express-primary{position:fixed;left:50%;bottom:12px;transform:translateX(-50%);z-index:990;display:flex;gap:7px;max-width:calc(100vw - 20px);width:max-content;flex-wrap:wrap;justify-content:center;padding:9px;border:1px solid rgba(115,207,255,.4);border-radius:18px;background:rgba(5,11,25,.94);box-shadow:0 0 28px rgba(60,140,225,.25);color:#eaf6ff;font:600 12px/1.3 system-ui,sans-serif}
#nox-express-primary button{appearance:none;cursor:pointer;min-height:44px;min-width:92px;padding:10px 12px;border:1px solid #4484a5;border-radius:12px;background:linear-gradient(145deg,#162f51,#081320);color:#f0faff;font:inherit;letter-spacing:.04em}
#nox-express-primary button:hover,#nox-express-primary button:focus-visible{border-color:#9ce7ff;outline:2px solid #9ce7ff;outline-offset:2px}
#nox-express-primary [data-nox-state]{width:100%;font-size:11px;text-align:center;font-weight:400;min-height:14px}
@media(max-width:550px){#nox-express-primary{bottom:3px;gap:4px;padding:5px}#nox-express-primary button{min-width:67px;padding:8px 5px;font-size:10px}}
@media(prefers-reduced-motion:reduce){#nox-express-primary,#nox-express-primary *{animation:none!important;transition:none!important;scroll-behavior:auto!important}}
</style>
<nav id="nox-express-primary" aria-label="NOX HELION EXPRESS — основные действия">
<button type="button" data-nox-primary="CHAT" aria-label="CHAT">CHAT</button>
<button type="button" data-nox-primary="INSTALL" aria-label="INSTALL">INSTALL</button>
<button type="button" data-nox-primary="MODELS" aria-label="MODELS">MODELS</button>
<button type="button" data-nox-primary="LEARN" aria-label="LEARN">LEARN</button>
<button type="button" data-nox-primary="REPORTS" aria-label="REPORTS">REPORTS</button>
<span data-nox-state role="status" aria-live="polite"></span>
</nav>
<script id="nox-express-primary-bind">
(()=>{'use strict';
const nav=document.getElementById('nox-express-primary');if(!nav)return;
const state=nav.querySelector('[data-nox-state]');
const screenNames={CHAT:['ЧАТ','CHAT'],INSTALL:['УСТАНОВКА','INSTALL'],LEARN:['ОБУЧЕНИЕ','LEARN'],REPORTS:['ОТЧЁТЫ','ОТЧЕТЫ','REPORTS']};
function safeOriginalLink(a){
 // No external/privileged routes from a text-matched original anchor.
 const href=(a.getAttribute('href')||'').trim();
 if(!href || href.startsWith('//') || /\\/.test(href) ||
    /^[A-Za-z][A-Za-z0-9+.-]*:/.test(href))return false;
 try{
   const destination=new URL(href,document.baseURI);
   const original=new URL(document.baseURI);
   if(destination.origin!==original.origin)return false;
   if(original.protocol==='file:')return destination.pathname===original.pathname && destination.search===original.search;
   return (original.protocol==='http:'||original.protocol==='https:') &&
          destination.protocol===original.protocol;
 }catch{return false;}
}
function findOriginalScreen(name){
 const terms=screenNames[name]||[];
 // Resolve only a pre-existing safe original route; otherwise explicit HOLD.
 return Array.from(document.querySelectorAll('a[href]')).find(a=>!nav.contains(a)&&
   terms.includes((a.textContent||'').trim().toLocaleUpperCase('ru'))&&
   safeOriginalLink(a));
}
function findOriginalControl(name){
 // Bind to SOURCE-LOCKED R11 buttons, not invented anchor text or direct IPC.
 // Unknown, duplicated, replaced or disabled original controls must HOLD.
 const selectors={
   CHAT:'.nav button[data-screen="chat"]',
   INSTALL:'button#install-app',
   MODELS:'button#model-center',
   LEARN:'.nav button[data-screen="control"]',
   REPORTS:'button#native-report'
 };
 const selector=selectors[name];if(!selector)return null;
 const matches=document.querySelectorAll(selector);
 if(matches.length!==1)return null;
 const button=matches[0];
 return button.tagName==='BUTTON'&&button.isConnected&&!button.disabled&&
        !nav.contains(button)?button:null;
}
nav.addEventListener('click',event=>{
 const target=event.target.closest('button[data-nox-primary]');
 if(!target||!nav.contains(target)||!event.isTrusted)return;
 const name=target.getAttribute('data-nox-primary');
 state.textContent='';
 if(name==='MODELS' && (!window.chrome||!window.chrome.webview||
     typeof window.chrome.webview.postMessage!=='function')){
   state.textContent='MODELS: native WebView2 недоступен · HOLD';return;
 }
 // A SOURCE-LOCKED original button already has the real event listener and
 // native IPC wrapper (SID, consent, request identity). Never forge a receipt.
 const original=findOriginalControl(name)||findOriginalScreen(name);
 if(!original){state.textContent=name+': нет подтверждённого исходного экрана · HOLD';return;}
 original.click();
});
})();
</script>
'''


def publish(original: bytes) -> tuple[bytes, dict]:
    """Return a derived HTML payload and strict non-release source receipt."""
    if type(original) is not bytes or len(original) != ORIGINAL_BYTES:
        raise ValueError("U08_ORIGINAL_HOME_BYTES_HOLD")
    original_sha = hashlib.sha256(original).hexdigest()
    if original_sha != ORIGINAL_SHA256:
        raise ValueError("U08_ORIGINAL_HOME_SHA_HOLD")
    try:
        html = original.decode("utf-8-sig")
    except UnicodeError as exc:
        raise ValueError("U08_ORIGINAL_HOME_UTF8_HOLD") from exc
    if html.lower().count("</body>") != 1 or MARKER in html or "nox-express-primary-bind" in html:
        raise ValueError("U08_ORIGINAL_HOME_HTML_ANCHOR_HOLD")
    close = html.lower().rfind("</body>")
    derived = (html[:close] + INSERT + html[close:]).encode("utf-8")
    if derived.count(b'data-nox-primary=') != 5:
        raise ValueError("U08_FIVE_PRIMARY_COUNT_HOLD")
    return derived, {
        "source_sha256": original_sha,
        "published_sha256": hashlib.sha256(derived).hexdigest(),
        "published_bytes": len(derived),
        "visible_primary_buttons": ["CHAT", "INSTALL", "MODELS", "LEARN", "REPORTS"],
        "installed_ui_automation": "NOT_RUN",
        "release_accepted": False,
    }
