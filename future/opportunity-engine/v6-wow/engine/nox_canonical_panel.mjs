/* NOX OIE · canonical-shell-only panel. No HOME/MENU/WORK overrides, no invented asteroids/personas. */
export function mountOpportunityPanel(target, { apiBase = '', signal, onBack, onEvent, requestJob } = {}) {
  if (!(target instanceof HTMLElement)) throw new TypeError('CANONICAL_HOST_REQUIRED');
  if (target.dataset.noxScreen !== 'opportunity-engine') throw new Error('NOX_ROUTE_NOT_APPROVED');
  const abort = new AbortController();
  if (signal) signal.addEventListener('abort', () => abort.abort(), { once: true });
  if (target.shadowRoot) throw new Error('ALREADY_MOUNTED');
  const root = target.attachShadow({ mode: 'open' });
  const style = document.createElement('style');
  style.textContent = `
    :host{display:block}*{box-sizing:border-box}.panel{color:#eee0ce;font:14px/1.5 'Segoe UI',sans-serif}
    h2{font-size:clamp(19px,2.2vw,29px);margin:0}header{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:18px}
    .status{margin-left:auto;color:#e0bb87;font:11px monospace}.notice{color:#c4b4a3;font-size:12px}
    input,button{font:inherit;color:inherit;background:#111419;border:1px solid #92704e;border-radius:8px;padding:10px;min-height:44px}
    button{cursor:pointer}button:hover,button:focus-visible{border-color:#f0c38e}button:focus-visible,input:focus-visible{outline:2px solid #eac28c}
    .toolbar{display:flex;gap:10px;margin:12px 0 20px;flex-wrap:wrap}.toolbar input{flex:1;min-width:180px}
    .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,230px),1fr));gap:12px}
    .item{display:block;text-align:left;min-height:105px;padding:14px;background:linear-gradient(150deg,#221b18,#101319)}
    .item small{display:block;color:#d4b087;margin:6px 0}.actions{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 12px}.detail{white-space:pre-wrap;overflow-wrap:anywhere;margin:18px 0;background:#101319;padding:16px;border:1px solid #635243;border-radius:8px}
    [hidden]{display:none!important}@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
  `;
  root.append(style);
  const panel = document.createElement('section');panel.className='panel';panel.setAttribute('aria-label','Opportunity Engine');
  panel.innerHTML = '<header><button type="button" data-action="back" aria-label="Назад">← Назад</button><h2>Фабрика возможностей</h2><span class="status">LOCAL · PREVIEW · HOLD</span></header><p class="notice">Исследовательские гипотезы, не запущенные компании. Встроенный раздел NOX, без замены HOME/MENU/WORK.</p><div class="toolbar"><input type="search" aria-label="Поиск идей" placeholder="Найти идею"><button type="button" data-action="clear">Сбросить</button></div><div class="toolbar"><input type="text" maxlength="240" data-theme aria-label="Тема исследования" placeholder="Тема для исследования"><button type="button" data-action="generate">Создать 3 гипотезы</button><button type="button" data-action="megablock">МЕГА-БЛОК 1</button></div><p role="status" class="notice"></p><div class="grid" role="list"></div><button type="button" data-action="more" hidden>Показать ещё</button><div class="detail" hidden aria-live="polite"></div>';
  root.append(panel);
  const input=panel.querySelector('input'),grid=panel.querySelector('.grid'),status=panel.querySelector('[role=status]'),more=panel.querySelector('[data-action=more]'),detail=panel.querySelector('.detail');
  let data=[],limit=9,filtered=[],busy=false;
  const emit=(type,detail={})=>{ onEvent?.({contract:"nox.oie.ui.v1",type,...detail}); };
  const theme=panel.querySelector("[data-theme]");
  async function get(path) {
    const response=await fetch(apiBase+path,{signal:abort.signal,credentials:'omit',cache:'no-store'});
    if(!response.ok)throw Error('HTTP_'+response.status);
    const payload=await response.json();if(!payload.ok)throw Error(payload.error||'API_ERROR');return payload.result;
  }
  async function post(endpoint){
    if(busy)return;busy=true;status.textContent='Выполняется локальный расчёт…';
    try {
      if(typeof requestJob!=='function')throw Error('HOST_ACTION_NOT_CONNECTED');
      const payload=await requestJob(endpoint==='/api/megablock1'?'megablock1.preview':'mission.run',{theme:theme.value,count:3},abort.signal);
      if(!payload?.ok)throw Error(payload?.error||'HOST_ACTION_FAILED');
      detail.textContent=JSON.stringify(payload.result,null,2);detail.hidden=false;status.textContent='Локальный результат создан · коммерческая проверка HOLD';emit('job.done',{endpoint});
    } catch(err){if(!abort.signal.aborted){status.textContent='HOLD · '+err.message;emit('job.error',{endpoint,error:err.message});}}
    finally{busy=false;}
  }
  function render(){
    filtered=data.filter(x=>(x.name+' '+x.id+' '+(x.category||'')).toLocaleLowerCase().includes(input.value.trim().toLocaleLowerCase()));
    grid.replaceChildren();
    for(const item of filtered.slice(0,limit)){
      const button=document.createElement('button');button.type='button';button.className='item';button.setAttribute('role','listitem');button.dataset.ideaId=item.id;
      const name=document.createElement('strong');name.textContent=item.name;const meta=document.createElement('small');meta.textContent=item.id+' · '+(item.status||'HOLD');button.append(name,meta);grid.append(button);
    }
    more.hidden=limit>=filtered.length;status.textContent=filtered.length+' гипотез · показано '+Math.min(limit,filtered.length);
  }
  panel.addEventListener('click',async e=>{
    const action=e.target.closest('button');if(!action)return;
    if(action.dataset.action==='back'){onBack?.();emit('navigation.back');return;}
    if(action.dataset.action==='generate'){await post('/api/mission');return;}
    if(action.dataset.action==='megablock'){await post('/api/megablock1');return;}
    if(action.dataset.action==='clear'){input.value='';limit=9;detail.hidden=true;render();return;}
    if(action.dataset.action==='more'){limit+=9;render();return;}
    if(action.dataset.ideaId){try{const result=await get('/api/inspect?id='+encodeURIComponent(action.dataset.ideaId));detail.textContent=JSON.stringify(result.idea,null,2);detail.hidden=false;detail.focus();}catch(err){status.textContent='Инспектор: '+err.message;}}
  },{signal:abort.signal});
  input.addEventListener('input',()=>{limit=9;render();},{signal:abort.signal});
  get('/api/ideas').then(result=>{data=result.ideas||[];render();}).catch(err=>{if(!abort.signal.aborted)status.textContent='HOLD · '+err.message;});
  const keyboard=e=>{if(e.key==='Escape'&&detail.hidden===false){detail.hidden=true;emit('inspector.close');}else if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();input.focus();}};
  target.addEventListener('keydown',keyboard,{signal:abort.signal});
  return {dispose(){abort.abort();root.replaceChildren();emit('panel.dispose');},refresh:()=>get('/api/ideas').then(result=>{data=result.ideas||[];render();})};
}
