/** NOX V37 live Server/Training panel, mount inside EXISTING NOX UI only.
 * No fake samples or independent backend. Native host owns OneHost authorization,
 * STOP, telemetry, approvals, receipts and action dispatch. No dropdown controls.
 */
const ACTIONS = [
  ['server.status','Обновить показатели',false],
  ['server.jobs','Работающие задачи',false],
  ['server.logs','Журнал ошибок',false],
  ['server.checkpoints','Чекпоинты',false],
  ['checkpoint.backup','Сделать бэкап',true],
  ['training.pause','Пауза обучения',true],
  ['training.resume','Продолжить обучение',true],
  ['teacher.start','Запустить учителя',true],
  ['model.download','Загрузить модель',true]
];
const txt=(el,val)=>{el.textContent=String(val ?? 'Н/Д');return el};
const mk=(tag,cls,content='')=>{const el=document.createElement(tag);if(cls)el.className=cls;el.textContent=content;return el};
const safeNumber=(v,suffix='')=>typeof v==='number'&&Number.isFinite(v)?`${v}${suffix}`:'Н/Д';
export function mountNoxV37ServerPanel(root,host){
  if(!root || !host || typeof host.inspect!=='function') throw new TypeError('NATIVE_ONEHOST_INSPECT_REQUIRED');
  root.replaceChildren();root.classList.add('nox-v37');
  const header=mk('header','nv-head');
  header.append(mk('div','nv-kicker','NOX HELION · СЕРВЕР / NEURAL FORGE'),mk('h2','nv-title','Управление интеллектом'));
  const status=mk('div','nv-state','Получение проверенных данных…');header.append(status);root.append(header);
  const cards=mk('div','nv-grid');const gpuCards=[0,1].map(i=>{
    const el=mk('section','nv-card');el.append(mk('div','nv-kicker',`GPU ${i} · TESLA V100`));
    const util=mk('strong','nv-value','Н/Д');el.append(util);
    const vram=mk('div','nv-text','VRAM: Н/Д');el.append(vram);
    const temp=mk('div','nv-text','Температура: Н/Д');el.append(temp);
    cards.append(el);return {el,util,vram,temp};
  });root.append(cards);
  const actions=mk('section','nv-actions');actions.append(mk('h3','nv-subtitle','Действия NOX'));
  const consoleOut=mk('output','nv-output','Нет действий.');
  const announce=async(name)=>{status.textContent=`Запрос: ${name}`;const data=await host.inspect(name);
      consoleOut.textContent=JSON.stringify(data,null,2);return data;};
  for(const [action,title,isWrite] of ACTIONS){
    // No decorative/dead buttons: capability absent means no button at all.
    if(!host.capabilities?.includes(action))continue;
    if(isWrite && (typeof host.preview!=='function'||typeof host.confirm!=='function'))continue;
    const b=mk('button','nv-button'+(isWrite?' nv-sensitive':''),title);
    b.type='button';b.addEventListener('click',async()=>{
      b.disabled=true;
      try{
        if(!isWrite)await announce(action);
        else{
          // Native host owns exact target, signed grant, SHA and STOP. No web JS executes mutation.
          const preview=await host.preview(action);
          if(preview?.state!=='OWNER_CONFIRMATION_REQUIRED'||!preview?.plan?.request_sha256){
            consoleOut.textContent='HOLD: нет подтверждённого плана OneHost';return;}
          consoleOut.textContent=JSON.stringify(preview.plan,null,2);
          // Distinct user confirmation. Approval token must be verified by host, not by UI.
          if(window.confirm('Подтвердить операцию: '+title+'?\nЦель: '+preview.plan.target_id+'\nSHA: '+preview.plan.request_sha256)){
            const result=await host.confirm(preview.plan.request_sha256);
            consoleOut.textContent=JSON.stringify(result,null,2);
          }
        }
      }catch(err){consoleOut.textContent='HOLD: '+(err?.message??'native failure');}
      finally{b.disabled=false;}
    });actions.append(b);
  }
  actions.append(consoleOut);root.append(actions);
  async function refresh(){
    const data=await host.inspect('server.status');
    // Accept only explicit measured host telemetry; no inferred GPU percentages.
    status.textContent=data?.state??'НЕ ПОДКЛЮЧЕНО';
    for(let i=0;i<2;i++){
      const g=data?.gpus?.find?.(x=>x.index===i);const c=gpuCards[i];
      txt(c.util,safeNumber(g?.compute_util_pct,'%'));
      txt(c.vram,`VRAM: ${safeNumber(g?.vram_used_mib,' MiB')} / ${safeNumber(g?.vram_total_mib,' MiB')}`);
      txt(c.temp,`Температура: ${safeNumber(g?.temp_core_c,' °C')}`);
    }
    return data;
  }
  refresh().catch(()=>{status.textContent='HOLD · OneHost недоступен';});
  return {refresh,destroy(){root.replaceChildren();}};
}
