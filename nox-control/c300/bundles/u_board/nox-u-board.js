/* U: виджет канбана «В работе / Нужен ты / Готово» (GET /svc/agentsb/board, карточки: стадия, стопор, %, ETA). API NOXboard */
(function(){ if(window.NOXboard)return;
 const COLS=['В работе','Нужен ты','Готово'],CLS={'В работе':'running','Нужен ты':'blocked','Готово':'done'};
 let box,ctl=null,data={};
 const esc=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
 const eta=s=>!s?'':(s>=3600?Math.round(s/3600)+' ч':s>=60?Math.round(s/60)+' мин':s+' с');
 function card(c){return '<div class="ub-c"><div class="ub-t">'+esc(c.title)+'</div><div class="ub-m">'+esc(c.stage||'')+(c.pct!=null?' · '+c.pct+'%':'')+(c.eta_sec?' · ETA '+eta(c.eta_sec):'')+'</div>'+(c.blocker?'<div class="ub-b">Стопор: '+esc(c.blocker)+'</div>':'')+'<div class="ub-bar"><i style="width:'+Math.max(0,Math.min(100,+c.pct||0))+'%"></i></div></div>'}
 function render(){ if(!box)return;box.querySelector('.ub-body').innerHTML=COLS.map(function(k){const a=data[k]||[];return '<details'+(k!=='Готово'?' open':'')+'><summary class="k8-s '+CLS[k]+'">'+k+' · '+a.length+'</summary>'+a.slice(0,8).map(card).join('')+'</details>'}).join('')}
 async function load(){ if(document.hidden)return;try{ctl&&ctl.abort();ctl=new AbortController();const r=await fetch('/svc/agentsb/board',{signal:ctl.signal,cache:'no-store'});if(!r.ok)return;data=await r.json();render()}catch(e){}}
 let tries=0;function mount(){ if(box||!document.body)return;const host=document.querySelector('.cx-right')||document.getElementById('tgWid');if(!host&&/chat/.test(location.pathname)&&++tries<30)return setTimeout(mount,500);
  box=document.createElement('section');box.id='nox-u-board';box.setAttribute('aria-label','Задачи агентов');
  box.innerHTML='<style>@media(max-width:768px){#nox-u-board.fl{display:none}}#nox-u-board{font-size:14px;color:inherit;max-width:100%;box-sizing:border-box}#nox-u-board.fl{position:fixed;left:12px;bottom:120px;width:300px;max-height:60vh;overflow:auto;z-index:40;background:rgba(20,15,15,.88);border:1px solid rgba(255,255,255,.15);border-radius:14px;padding:8px}#nox-u-board summary{min-height:44px;display:flex;align-items:center;cursor:pointer;font-size:14px}#nox-u-board .ub-c{padding:6px 8px;margin:4px 0;border-radius:10px;background:rgba(255,255,255,.07)}#nox-u-board .ub-t{font-weight:600}#nox-u-board .ub-m,#nox-u-board .ub-b{font-size:14px;opacity:.85}#nox-u-board .ub-b{color:#ff9b9b}#nox-u-board .ub-bar{height:4px;border-radius:2px;background:rgba(255,255,255,.12);margin-top:4px}#nox-u-board .ub-bar i{display:block;height:100%;border-radius:2px;background:var(--k8-running,#e9b465)}</style><div class="ub-body"></div>';
  if(host){box.classList.add('in');host.appendChild(box)}else{box.classList.add('fl');document.body.appendChild(box)}
  load();setInterval(load,15000);document.addEventListener('visibilitychange',load)}
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount);else mount();
 window.NOXboard={load:load,render:render,data:function(){return data}};
})();
