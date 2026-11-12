"""Source-locked in-place WEB fixes on the ORIGINAL pinned baseline, not a demo.
Safe to run exactly once after tools/restore-pinned-baseline.mjs; does not touch D02/14 PBR.
"""
from pathlib import Path
import hashlib, re
root = Path(__file__).resolve().parent.parent / 'dist'
locks = {
 'chat.html': 'a9abd5e5d855b72dc047898a65d622a152ca5c1009a7da1b78e2dd5892259b0b',
 'nox-ui.js': '294f6a9efb523735dbadd9ce6c35433fb9b2489f9c7e1df4d5d3d157286932bc',
 'nox-function-catalog.css': '80cb5fe3e77b638b9c21e12fe065672c09775dbda4f9961bfe60b2b2da97de05',
 'nox-chat.js': 'd598379aa8f4fbb1da43539ed39634d74efe3bc4a3d129f00721d6cf7bc95b4a',
 'nox-telemetry.js': 'c2eed8a1fd9b611e1f989f09269f06042a71d91291ce1226d768952cc784ec89',
 'nox-function-catalog.js': 'f5582dd797a3772b6c3e53a9bf7967e07b002810fd1b5ffe6a3a8f42b5d6675f',
 'nox-universe-v19.js': '6417847dc8a12a3d6356f82c2f6455cb6eb2b3dc55455fe48a49dd72d8b889f0',
}
sha=lambda text: hashlib.sha256(text.encode('utf-8')).hexdigest()
def once(text,old,new):
 if text.count(old)!=1: raise RuntimeError('WEB26_ANCHOR_DRIFT: '+old[:80])
 return text.replace(old,new,1)
def change(name,operation):
 p=root/name;s=p.read_text('utf-8')
 if sha(s)!=locks[name]:raise RuntimeError('WEB26_PREIMAGE_DRIFT: '+name+':'+sha(s))
 t=operation(s)
 if t==s:raise RuntimeError('WEB26_NO_CHANGE: '+name)
 p.write_text(t,'utf-8')
 print('WEB26_PATCHED',name,sha(t))
change('chat.html',lambda s:once(once(s,'data-action="dictate" aria-label="Микрофон"','id="chatDictate" data-action="dictate" aria-label="Микрофон"'),'<button class="graphic-button" data-action="translate">Перевести</button>','<button id="chatTranslate" class="graphic-button" data-action="translate">Перевести</button>'))
change('nox-universe-v19.js',lambda s:once(s,'function open(){panel.hidden=false;openBtn.hidden=true;show(state.active);close.focus()}',"function open(moduleName){panel.hidden=false;openBtn.hidden=true;show(typeof moduleName==='string'&&modules.includes(moduleName)?moduleName:state.active);close.focus()}"))
def catalog(s):
 s=once(s,"['voice','Голос NOX','mic','settings','native-push-panel'","['voice','Голос NOX','mic','chat','chatDictate'")
 s=once(s,"['diagnostics','Диагностика','terminal','dashboard','nox-widget-diagnostics'","['diagnostics','Диагностика','terminal','dashboard','dashboard-overview'")
 for item,anchor in [('training','trainer-queue'),('language','translation'),('monitoring','cpu-monitor')]:
  line=next((l for l in s.splitlines() if l.startswith(" ['"+item+"',")),None)
  if not line:raise RuntimeError('WEB26_CATALOG_ANCHOR:'+item)
  extra={
   'training':" ['trainer-queue','Очередь и STOP','list-todo','training','training-queue','Реальная очередь обучения; действия контролирует OneHost.'],\n ['trainer-checkpoints','Checkpoint и SHA','shield-check','training','training-checkpoints','Подтверждённые контрольные точки; отсутствие API — HOLD.'],\n ['trainer-quality','Оценка качества NOX','chart-line','training','training-quality','Loss и проверенные метрики без вымышленных значений.'],",
   'language':" ['translation','Перевод RU ↔ ES','languages','chat','chatTranslate','Перевод через существующий Резонанс; отсутствие локального ИИ — HOLD.'],\n ['resonance','Резонанс · чат NOX','message-circle','chat','chatForm','Один чат и STOP через существующий OneHost.'],",
   'monitoring':" ['cpu-monitor','Нагрузка CPU','cpu','dashboard','dashboard-cpu','Фактические показания CPU.'],\n ['gpu-monitor','Нагрузка GPU','circuit-board','dashboard','dashboard-gpu','GPU и VRAM, реальный источник измерения.'],\n ['temperature','SAFE70 · температура','thermometer','dashboard','dashboard-thermal','Температура и статус датчика из OneHost.'],"
  }[item]
  s=once(s,line,line+'\n'+extra)
 for item,module in [('notifications','Уведомления'),('calendar','Календарь'),('news','Новости'),('weather','Погода'),('fx','Валюта')]:
  line=next((l for l in s.splitlines() if l.startswith(" ['"+item+"',")),None)
  if not line or not line.endswith('],'):raise RuntimeError('WEB26_MODULE_ROW:'+item)
  s=once(s,line,line[:-2]+",'v19:"+module+"'],")
 needle="if(item.ui){event.preventDefault();const method=item.ui==='commands'?'open':'openInbox';"
 replacement="if(item.ui?.startsWith('v19:')&&!native){event.preventDefault();const module=item.ui.slice(4);if(window.NOX_UNIVERSE_V19?.modules?.includes(module)){dialog.close();window.NOX_UNIVERSE_V19.open(module);}else{status.textContent='Модуль '+module+' не загружен · HOLD';}return;}if(item.ui&&['commands','inbox'].includes(item.ui)){event.preventDefault();const method=item.ui==='commands'?'open':'openInbox';"
 s=once(s,needle,replacement)
 needle="window.NoxFunctionCatalog={open,entries:entries.map(n=>({...n})),diagnostics:()=>({entries:entries.length,open:dialog.open,search:search.value,networkRequestsOnOpen:0,automaticActions:false})};"
 replacement="""// The native owner has the real command center; public WEB gets only this
// existing read-only catalog without privileged actions or a second router.
if(!native&&document.body?.dataset.page!=='index'){
 const launch=make('button','nox-function-public-open');launch.id='noxPublicFunctionOpen';launch.type='button';launch.dataset.noxCatalogOpen='';
 launch.setAttribute('aria-label','Все функции NOX · Ctrl+K');launch.setAttribute('aria-keyshortcuts','Control+K');
 launch.append(glyph('grid-2x2'),make('span','','ВСЕ ФУНКЦИИ'));
 (document.querySelector('.nox-v19-root')||document.querySelector('.nox-app-header')||document.body).append(launch);
 document.addEventListener('keydown',event=>{if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='k'&&!event.repeat&&!event.isComposing){
  event.preventDefault();if(dialog.open)close();else open();
 }});
}
window.NoxFunctionCatalog={open,entries:entries.map(n=>({...n})),diagnostics:()=>({entries:entries.length,open:dialog.open,search:search.value,networkRequestsOnOpen:0,automaticActions:false})};"""
 return once(s,needle,replacement)
change('nox-function-catalog.js',catalog)
def telemetry(s):
 needle="if(capability)actions[ui]={...capability,enabled:capability.enabled===true&&(ui==='checkpoint'||binding),reason:capability.reason||(ui!=='checkpoint'&&!binding?'NOX_TRAINING_BINDING_REQUIRED':null)};"
 replacement="""if(capability){
        const extended=['compare','evaluate','rollback'].includes(ui);
        const routeOK=!extended||(capability.endpoint==='/api/nox/training/'+ui&&capability.method==='POST');
        const checkpointOK=ui!=='rollback'||(/^step-[0-9]+$/.test(capability.checkpoint||'')&&/^[a-f0-9]{64}$/i.test(capability.expected_sha256||''));
        actions[ui]={...capability,enabled:capability.enabled===true&&(ui==='checkpoint'||binding)&&routeOK&&checkpointOK,
          reason:!routeOK?'HOLD · OneHost не подтвердил маршрут и POST':!checkpointOK?'HOLD · checkpoint/SHA не проверены':capability.reason||null};
      }"""
 s=once(s,needle,replacement)
 needle="if(!['start','resume','pause','checkpoint','stop'].includes(action)||nativeActions[action]?.enabled!==true)throw Error(nativeActions[action]?.reason||nativeGate);"
 replacement="""if(['compare','evaluate','rollback'].includes(action)){
          const cap=nativeActions[action];
          if(cap?.enabled!==true||cap.endpoint!=='/api/nox/training/'+action||cap.method!=='POST')throw Error(cap?.reason||nativeGate);
          let payload={};
          if(action==='rollback'){
            if(!/^step-[0-9]+$/.test(cap.checkpoint||'')||!/^[a-f0-9]{64}$/i.test(cap.expected_sha256||''))throw Error('HOLD · checkpoint SHA не подтверждён');
            if(!window.confirm('Откатить к '+cap.checkpoint+' · SHA '+cap.expected_sha256.slice(0,16)+'…?')){show('action-output','Откат отменён');return;}
            payload={checkpoint:cap.checkpoint,expected_sha256:cap.expected_sha256,confirmed:true};
          }
          const response=await get(cap.endpoint,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
          show('action-output','OneHost: '+String(response.status||'UNKNOWN')+' · проверка по отдельной квитанции; не PASS обучения');
          void refresh();return;
        }
        if(!['start','resume','pause','checkpoint','stop'].includes(action)||nativeActions[action]?.enabled!==true)throw Error(nativeActions[action]?.reason||nativeGate);"""
 return once(s,needle,replacement)
change('nox-telemetry.js',telemetry)
def chat(s):
 s=once(s,"streamMode='NATIVE_BUFFERED';","streamMode='NATIVE_BUFFERED',submitted=false;")
 s=once(s,"      const response=await fetch('/api/nox/chat/stream'","      submitted=true; // This request may commit even if the connection drops.\n      const response=await fetch('/api/nox/chat/stream'")
 s=once(s,"if(!line.trim())return;const frame=JSON.parse(line);","if(!line.trim())return;if(line.length>262144)throw Error('Кадр NOX слишком велик');const frame=JSON.parse(line);if(!frame||typeof frame!=='object'||Array.isArray(frame))throw Error('Неверный кадр OneHost');")
 s=once(s,"if(frame.type==='delta'){if(run.stopping)return;result+=frame.text||'';","if(frame.type==='delta'){if(run.stopping)return;if(typeof frame.text!=='string'||result.length+frame.text.length>2000000)throw Error('Неверный или слишком большой ответ NOX');result+=frame.text;")
 s=once(s,"buffer+=decoder.decode(chunk.value,{stream:true});let end;","buffer+=decoder.decode(chunk.value,{stream:true});if(buffer.length>300000)throw Error('Поток NOX превысил лимит кадра');let end;")
 s=once(s,"    }catch(error){if(!run.stopping){core('error');status('HOLD');hold(error);}if(!draft())draft(text);render();}","""    }catch(error){
      if(submitted){state.nativeReplayHold=true;state.lastTry=null;
        if(!run.stopping){core('error');status('HOLD · ответ S03 не подтверждён');say('HOLD · запрос мог быть сохранён. Обновите историю S03 перед повторной отправкой. '+String(error?.message||error));}
      }else{if(!run.stopping){core('error');status('HOLD');hold(error);}if(!draft())draft(text);}
      render();
    }""")
 s=once(s,"    run.stopping=true;\n    try {\n      const r=nativeOwner?await api('/api/nox/stop',{}):", "    run.stopping=true;\n    if(nativeOwner)state.nativeReplayHold=true;\n    run.controller.abort(); // No new UI tokens after STOP; native STOP call below is separate.\n    try {\n      const r=nativeOwner?await api('/api/nox/stop',{}):")
 return s
change('nox-chat.js',chat)

def ui_public(s):
 return once(s,"  const nativeOwner=window.NOX_NATIVE_OWNER===true;","""  const nativeOwner=window.NOX_NATIVE_OWNER===true;
  // Keep native owner-only extensions protected, while restoring the existing
  // read-only function catalog on public secondary pages (no new backend).
  if(!nativeOwner&&document.body?.dataset.page!=='index'){
    const publicCatalog=()=>void import('./nox-function-catalog.js').catch(error=>console.warn('NOX function catalog HOLD:',String(error?.message||error)));
    if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',publicCatalog,{once:true});else publicCatalog();
  }""")
change('nox-ui.js',ui_public)
public_css="""
/* Public secondary WEB pages: one discoverable graphical entry, native owner
   remains on the original trusted command center. HOME has no added controls. */
.nox-function-public-open{position:fixed;bottom:19px;left:230px;z-index:2147481001;display:inline-flex;align-items:center;justify-content:center;gap:9px;min-height:48px;min-width:150px;padding:9px 14px;border:1px solid rgba(225,178,114,.38);border-radius:14px;color:#f0c58e;background:linear-gradient(145deg,#24252b,#0c0d12);box-shadow:inset 0 1px rgba(255,255,255,.17),0 9px 28px #000b;font:600 12px/1.2 inherit;cursor:pointer}
.nox-function-public-open svg{width:18px;height:18px;flex:none}
.nox-function-public-open:focus-visible{outline:2px solid #dfc497;outline-offset:3px}
body.helion-home .nox-function-public-open{display:none!important}
@media(max-width:600px){.nox-function-public-open{left:auto;right:8px;bottom:8px;min-width:48px;padding:8px 12px}.nox-function-public-open span{display:none}}
@media(prefers-reduced-motion:reduce){.nox-function-public-open{animation:none!important;transition:none!important}}
"""
change('nox-function-catalog.css',lambda s:s+public_css)
