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
#nox-express-primary button{--nox-planet:#4ba3f1;--nox-planet-light:#a7edff;appearance:none;cursor:pointer;min-height:70px;min-width:92px;display:flex;flex-direction:column;justify-content:center;align-items:center;gap:4px;padding:7px 11px;border:1px solid rgba(115,207,255,.45);border-radius:15px;background:linear-gradient(160deg,rgba(24,53,85,.94),rgba(6,15,33,.98));color:#f0faff;font:inherit;letter-spacing:.04em;text-shadow:0 1px 3px #020714}
#nox-express-primary button::before{content:"";display:block;width:30px;height:30px;flex:none;border-radius:50%;background:radial-gradient(circle at 29% 23%,#fff 0%,var(--nox-planet-light) 14%,var(--nox-planet) 43%,#08172d 86%);box-shadow:inset -4px -5px 8px rgba(1,5,17,.85),inset 2px 2px 5px rgba(255,255,255,.55),0 0 13px var(--nox-planet);animation:noxPrimaryFloat 5.6s ease-in-out infinite}
#nox-express-primary button[data-nox-primary = "CHAT"]{--nox-planet:#55b6f8;--nox-planet-light:#c3f2ff}
#nox-express-primary button[data-nox-primary = "INSTALL"]{--nox-planet:#e39863;--nox-planet-light:#ffe4b7}
#nox-express-primary button[data-nox-primary = "MODELS"]{--nox-planet:#a481ee;--nox-planet-light:#f4d8ff}
#nox-express-primary button[data-nox-primary = "LEARN"]{--nox-planet:#58c9ae;--nox-planet-light:#c7ffe5}
#nox-express-primary button[data-nox-primary = "SETTINGS"]{--nox-planet:#e3bc58;--nox-planet-light:#fff4bc}
#nox-express-primary button:nth-of-type(even)::before{animation-delay:-2.8s}
#nox-express-primary button:focus-visible::before{box-shadow:0 0 0 3px #e6fcff,0 0 17px var(--nox-planet)}
@keyframes noxPrimaryFloat{0%,100%{transform:translateY(0)}50%{transform:translateY(-3px)}}

#nox-express-primary button:hover,#nox-express-primary button:focus-visible{border-color:#9ce7ff;outline:2px solid #9ce7ff;outline-offset:2px}
#nox-express-primary [data-nox-state]{width:100%;font-size:11px;text-align:center;font-weight:400;min-height:14px}
@media(max-width:550px){#nox-express-primary{bottom:max(3px,env(safe-area-inset-bottom,0px));width:calc(100vw - 12px);max-width:calc(100vw - 12px);display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:3px;padding:5px;box-sizing:border-box}#nox-express-primary button{width:100%;min-width:0;min-height:56px;padding:6px 1px;font-size:9px;letter-spacing:0;line-height:1.2;white-space:nowrap}#nox-express-primary button::before{width:22px;height:22px}#nox-express-primary [data-nox-state]{grid-column:1 / -1;min-width:0;overflow-wrap:anywhere}}
@media(prefers-reduced-motion:reduce){#nox-express-primary,#nox-express-primary *,#nox-express-primary button::before{animation:none!important;transition:none!important;transform:none!important;scroll-behavior:auto!important}}
</style>
<nav id="nox-express-primary" aria-label="NOX HELION EXPRESS — основные действия">
<button type="button" data-nox-primary="CHAT" aria-label="CHAT">CHAT</button>
<button type="button" data-nox-primary="INSTALL" aria-label="INSTALL">INSTALL</button>
<button type="button" data-nox-primary="MODELS" aria-label="MODELS">MODELS</button>
<button type="button" data-nox-primary="LEARN" aria-label="LEARN">LEARN</button>
<button type="button" data-nox-primary="SETTINGS" aria-label="SETTINGS">SETTINGS</button>
<span data-nox-state role="status" aria-live="polite"></span>
</nav>
<script id="nox-express-primary-bind">
(()=>{'use strict';
const nav=document.getElementById('nox-express-primary');if(!nav)return;
const state=nav.querySelector('[data-nox-state]');
// Render only an exact unique *existing* text-only original MENU label as a
// graphical symbol. Do not replace its element, listeners, route, or siblings.
// Unknown/multiple labels are left untouched for physical visual E07 HOLD.
function renderOriginalMenuGlyph(){
 const labels=Array.from(new Set(document.querySelectorAll('aside *, nav *, header *, .sidebar *')))
  .filter(el=>!nav.contains(el)&&el.children.length===0&&
     (el.textContent||'').trim()==='MENU');
 if(labels.length!==1)return;
 const label=labels[0];
 const nodes=Array.from(label.childNodes).filter(n=>n.nodeType===3&&
     (n.textContent||'').trim()==='MENU');
 if(nodes.length!==1)return;
 if(!label.hasAttribute('aria-label'))
   label.setAttribute('aria-label','Направления HELION');
 nodes[0].textContent='✦';
 label.dataset.noxOriginalMenuGlyph='true';
}
if(document.readyState==='loading')
 document.addEventListener('DOMContentLoaded',renderOriginalMenuGlyph,{once:true});
else renderOriginalMenuGlyph();

const screenNames={CHAT:['ЧАТ','CHAT'],INSTALL:['УСТАНОВКА','INSTALL'],LEARN:['ОБУЧЕНИЕ','LEARN'],SETTINGS:['НАСТРОЙКИ','SETTINGS']};
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
   SETTINGS:'button.tile[data-menu-index="7"]'
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
 // Main actions navigate to SOURCE-LOCKED real controls, never run
 // install, model downloads or training merely because their top-level
 // navigation button was clicked. The user still chooses the original action
 // inside its own panel, under existing native ACL and consent.
 const destinations={
   INSTALL:['home','button#install-app'],
   MODELS:['control','button#model-center'],
   LEARN:['control','button#training-start']
 };
 if(Object.prototype.hasOwnProperty.call(destinations,name)){
   const [screen,selector]=destinations[name];
   const navControl=document.querySelector('.nav button[data-screen="'+screen+'"]');
   const matches=document.querySelectorAll(selector);
   if(!navControl||navControl.disabled||matches.length!==1||
      !matches[0].isConnected||matches[0].disabled){
     state.textContent=name+': исходный элемент недоступен · HOLD';return;
   }
   navControl.click(); // Reuse original showScreen/navigation, not a second UI.
   if(!document.getElementById(screen)?.classList.contains('active')){
     state.textContent=name+': исходный экран не открылся · HOLD';return;
   }
   const target=matches[0];
   if(target.getClientRects().length===0){
     state.textContent=name+': целевой элемент не виден · HOLD';return;
   }
   target.focus({preventScroll:false});
   if(document.activeElement!==target){
     state.textContent=name+': фокус оригинального элемента не подтверждён · HOLD';
     return;
   }
   // MODELS is a read-only catalog. Forward this trusted user click to the
   // existing native-backed control, never trigger a model pull or install.
   // INSTALL and LEARN remain focus-only for explicit owner consent.
   if(name==='MODELS')target.click();
   return;
 }
 // SETTINGS enters the original MENU first, then uses its ORIGINAL system tile.
 // No hidden-tile click can silently count as verified user navigation.
 if(name==='SETTINGS'){
   const menuEntries=document.querySelectorAll('.nav button[data-screen="menu"]');
   const systemTiles=document.querySelectorAll('button.tile[data-menu-index="7"]');
   if(menuEntries.length!==1||systemTiles.length!==1||
      menuEntries[0].disabled||!systemTiles[0].isConnected||systemTiles[0].disabled){
     state.textContent='SETTINGS: исходное направление недоступно · HOLD';return;
   }
   menuEntries[0].click();
   const tile=systemTiles[0];
   if(!document.getElementById('menu')?.classList.contains('active')||
      tile.getClientRects().length===0){
     state.textContent='SETTINGS: исходное MENU не открылось · HOLD';return;
   }
   tile.focus({preventScroll:false});
   if(document.activeElement!==tile){
     state.textContent='SETTINGS: системная кнопка не получила фокус · HOLD';return;
   }
   tile.click();
   if(!document.getElementById('menu-detail')?.classList.contains('active'))
     state.textContent='SETTINGS: исходная СИСТЕМА не открылась · HOLD';
   return;
 }
 // CHAT reuses its original source-bound screen, not a second router.
 // A clicked top-level action never fabricates a model reply or install ACK.
 const original=findOriginalControl(name)||findOriginalScreen(name);
 if(!original){state.textContent=name+': нет подтверждённого исходного экрана · HOLD';return;}
 original.click();
 if(name==='CHAT'&&!document.getElementById('chat')?.classList.contains('active'))
   state.textContent='CHAT: исходный экран не открылся · HOLD';
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
    # R11 original has a chatLog TDZ: a wheel listener is installed before
    # the later const declaration. Repair ONLY this integrity-pinned staged
    # copy so the remaining existing native HOME callbacks can initialize.
    # Original donors, host, permission gates and NSIS payload owners stay put.
    tdz_decl = "chatLog=document.getElementById('chat-log'),"
    tdz_anchor = "let chatScrollFrame=0;"
    if (html.count(tdz_decl) != 1 or html.count(tdz_anchor) != 1
            or html.index(tdz_anchor) >= html.index(tdz_decl)):
        raise ValueError("U07_ORIGINAL_CHATLOG_TDZ_PREIMAGE_HOLD")
    html = html.replace(tdz_decl, "", 1)
    html = html.replace(tdz_anchor,
                        "const chatLog=document.getElementById('chat-log');" + tdz_anchor, 1)

    close = html.lower().rfind("</body>")
    derived = (html[:close] + INSERT + html[close:]).encode("utf-8")
    if derived.count(b'data-nox-primary=') != 5:
        raise ValueError("U08_FIVE_PRIMARY_COUNT_HOLD")
    return derived, {
        "source_sha256": original_sha,
        "published_sha256": hashlib.sha256(derived).hexdigest(),
        "published_bytes": len(derived),
        "visible_primary_buttons": ["CHAT", "INSTALL", "MODELS", "LEARN", "SETTINGS"],
        "installed_ui_automation": "NOT_RUN",
        "release_accepted": False,
    }
