/* NOX V16 WOW-5. Local controlled secondary screens ONLY. Do not mount on HOME.
 * This component is UI-only; live states and allowlisted commands come from NOX host.
 */
(function(g) {
  'use strict';
  const validId = /^[a-z0-9_.:-]{1,96}$/i;
  const statuses = new Set(['idle','running','paused','error','offline','success']);
  const keys = ['cpu','gpu','vram'];
  function el(tag, cls, value) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (value !== undefined) e.textContent = String(value);
    return e;
  }
  function mount(target, {send, isHome=false}={}) {
    if (!target || typeof send !== 'function' || isHome) throw new Error('Requires trusted secondary NOX host');
    if (!document.getElementById('nox-wow5-style')) {
      const style = el('style'); style.id='nox-wow5-style';
      style.textContent =
       '.nox-w5{--edge:rgba(127,224,230,.35);--fg:#edf9fb;--soft:#aac6d1;color:var(--fg);'+
       'position:relative;overflow:hidden;padding:16px;border:1px solid var(--edge);border-radius:18px;'+
       'background:linear-gradient(140deg,rgba(48,78,89,.22),rgba(8,21,33,.76));'+
       'box-shadow:0 10px 40px #0004,inset 0 1px #edffff18;backdrop-filter:blur(12px);font:13px Segoe UI,sans-serif}'+
       '.nox-w5:before{content:"";pointer-events:none;position:absolute;inset:0;border-radius:inherit;'+
       'background:linear-gradient(110deg,transparent 20%,#9afaff0f 48%,transparent 72%);'+
       'background-size:250% 100%;animation:nox-w5-sheen 12s linear infinite}'+
       '@keyframes nox-w5-sheen{from{background-position:150% 0}to{background-position:-150% 0}}'+
       '.nox-w5[data-state=running]{border-color:#76e4e8aa;box-shadow:0 0 22px #40c4ca22}'+
       '.nox-w5[data-state=error]{border-color:#f2a19c}.nox-w5[data-state=paused]{border-color:#e9bc7e}'+
       '.nox-w5-head,.nox-w5-actions{display:flex;gap:8px;align-items:center;flex-wrap:wrap}'+
       '.nox-w5-head strong{flex:1}.nox-w5-lamp{display:inline-block;width:8px;height:8px;border-radius:50%;background:#526874}'+
       '.nox-w5[data-state=running] .nox-w5-lamp{background:#7df4e5;box-shadow:0 0 12px #7df4e5}'+
       '.nox-w5-stats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:13px 0}'+
       '.nox-w5-stats div{border:1px solid var(--edge);background:#091d2880;border-radius:10px;padding:10px;display:grid;gap:5px}'+
       '.nox-w5-stats span{color:var(--soft);font-size:10px}.nox-w5-stats b{font-variant-numeric:tabular-nums;font-size:17px}'+
       '.nox-w5 button{border:1px solid var(--edge);border-radius:999px;padding:7px 11px;background:#113b4a99;color:var(--fg);cursor:pointer}'+
       '.nox-w5 button:disabled{opacity:.4;cursor:not-allowed}.nox-w5 button:focus-visible{outline:2px solid #91f1ee}'+
       '.nox-w5-events{display:flex;list-style:none;gap:6px;flex-wrap:wrap;padding:0;margin:10px 0 0}'+
       '.nox-w5-events li{border:1px solid var(--edge);padding:4px 7px;border-radius:999px;font-size:10px}'+
       '.nox-w5.is-focused .nox-w5-stats,.nox-w5.is-focused .nox-w5-events{opacity:.25}'+
       '@media(prefers-reduced-motion:reduce){.nox-w5:before{animation:none}}';
      document.head.appendChild(style);
    }
    const root=el('section','nox-w5');root.dataset.state='idle';root.setAttribute('aria-label','NOX: системный статус');
    const head=el('div','nox-w5-head');
    const lamp=el('span','nox-w5-lamp');lamp.setAttribute('aria-hidden','true');
    const heading=el('strong','', 'NOX · Н/Д');heading.setAttribute('aria-live','polite');
    const focus=el('button','','Фокус');focus.type='button';
    focus.onclick=()=>{const yes=root.classList.toggle('is-focused');focus.textContent=yes?'Фокус включён':'Фокус';focus.setAttribute('aria-pressed',String(yes));};
    head.append(lamp,heading,focus);focus.setAttribute('aria-pressed','false');
    const stats=el('div','nox-w5-stats'), fields={};
    for (const k of keys) { const c=el('div');c.append(el('span','',k.toUpperCase()));fields[k]=el('b','','Н/Д');c.append(fields[k]);stats.append(c); }
    const actions=el('div','nox-w5-actions'), events=el('ol','nox-w5-events');
    events.setAttribute('aria-label','Последние реальные события');
    root.append(head,stats,actions,events);target.append(root);
    const allowed=new Set();
    return Object.freeze({
      setState(s){if(!statuses.has(s))return;root.dataset.state=s;heading.textContent='NOX · '+s;},
      setTelemetry(data){if(!data||typeof data!=='object')return;for(const k of keys){const n=data[k];fields[k].textContent=typeof n==='number'&&Number.isFinite(n)&&n>=0&&n<=100?Math.round(n)+'%':'Н/Д';}},
      setCommands(items){actions.replaceChildren();allowed.clear();if(!Array.isArray(items))return;for(const it of items.slice(0,8)){if(!it||typeof it.id!=='string'||!validId.test(it.id))continue;const b=el('button','',String(it.label||it.id).slice(0,48));b.type='button';b.disabled=it.enabled!==true;if(!b.disabled)allowed.add(it.id);b.onclick=()=>{if(allowed.has(it.id))send('nox.open.route',{routeId:it.id});};actions.append(b);}},
      addEvent(e){if(!e||!statuses.has(e.state)||typeof e.runId!=='string'||!validId.test(e.runId))return;const li=el('li','',e.state);li.title=String(e.timeUtc||'').slice(0,30);li.dataset.runId=e.runId;events.prepend(li);while(events.children.length>6)events.lastElementChild.remove();},
      destroy(){root.remove();}
    });
  }
  g.NoxWowFive=Object.freeze({mount});
})(typeof window!=='undefined'?window:globalThis);