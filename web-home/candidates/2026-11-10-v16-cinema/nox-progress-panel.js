/* Existing SYSTEM / TRAINING instrumentation: read-only NOX progress surface.
 * No training start, no pretend 0%, no secrets, no added backend.
 */
(()=>{'use strict';
 if(!/(?:^|\/)(?:system|training)\.html$/i.test(location.pathname))return;
 const ready=()=>{
  if(document.getElementById('nox-evidence-progress'))return;
  const main=document.querySelector('main')||document.body;
  const make=(tag,className,text)=>{const n=document.createElement(tag);n.className=className;if(text)n.textContent=text;return n};
  const section=make('section','nox-evidence-progress');section.id='nox-evidence-progress';
  section.setAttribute('aria-label','Подтверждённый прогресс дистилляции NOX');
  const header=make('div','nox-evidence-header');
  const h=make('h2','','ДИСТИЛЛЯЦИЯ NOX · ДОКАЗАТЕЛЬСТВА');
  const status=make('strong','nox-evidence-status','HOLD · НЕТ ПРОВЕРЕННОГО ОТЧЁТА');
  header.append(h,status);
  const description=make('p','nox-evidence-desc','GPU % — загрузка оборудования, не процент поглощения знаний. Шаги доступны только при подтверждённых SHA-256 контрольной точки и trainer_state.json.');
  const data=make('div','nox-evidence-metrics');
  const details=make('p','nox-evidence-details','Подключите проверенный локальный отчёт NOX. Пока оценка недоступна.');
  const controls=make('div','nox-evidence-actions');
  const update=make('button','','ОБНОВИТЬ ДОКАЗАТЕЛЬСТВА');
  update.type='button';const exportBtn=make('button','','СОХРАНИТЬ ОТЧЁТ JSON');exportBtn.type='button';exportBtn.disabled=true;
  controls.append(update,exportBtn);
  section.append(header,description,data,details,controls);
  main.prepend(section);
  let last=null;
  const metric=(name,value)=>{const p=make('div','nox-evidence-metric'),k=make('span','',name),v=make('strong','',value);p.append(k,v);return p};
  const visible=(r)=>{
   last=r;data.replaceChildren();
   const verified=r?.schema==='nox-progress-receipt-v1'&&
    ['VERIFIED_CHECKPOINT_STEPS','VERIFIED_COMPLETE'].includes(r.status)&&
    r.weightUpdateVerified===true&&r.attestation==='LOCAL_WEIGHT_AND_TRAINER_STATE_SHA256_CHECKED'&&
    Number.isFinite(r.stepPercent)&&r.stepPercent>=0&&r.stepPercent<=100&&
    typeof r.studentWeightsSha256==='string'&&/^[a-f0-9]{64}$/i.test(r.studentWeightsSha256);
   if(!verified){
    status.textContent='HOLD · ПРОГРЕСС НЕ ДОКАЗАН';
    details.textContent='Источник: '+String(r?.reason||'NO_READABLE_ATTESTATION').slice(0,180)+
      '. Одна только загрузка A40 не подтверждает обновление весов.';
    exportBtn.disabled=true;return;
   }
   status.textContent=r.complete?'ПОДТВЕРЖДЁННЫЕ ЭТАПЫ ЗАВЕРШЕНЫ':'ПРОВЕРЕНЫ ШАГИ · ФИНАЛЬНАЯ ПРИЁМКА HOLD';
   data.append(metric('Подтверждённые шаги',r.completedSteps+' / '+r.targetSteps),
    metric('Прогресс этапа',r.stepPercent.toFixed(2)+'%'),
    metric('Обновление полных весов',r.weightUpdateVerified?'SHA-256 PASS':'HOLD'),
    metric('Учителя с доказательствами',String(r.teacherEvidenceCount??0)),
    metric('Проверка качества',r.qualityGainVerified?'PASS':'HOLD'),
    metric('Windows checkpoint',r.windowsSyncVerified?'PASS':'HOLD'));
   details.textContent='Контрольная точка: '+r.studentWeightsSha256.slice(0,16)+'… · дата: '+
       String(r.generatedAt||r.observedAt||'не указана')+
       '. Это прогресс шагов дистилляции, не процент общего интеллекта.';
   exportBtn.disabled=false;
  };
  const fetchEvidence=async()=>{
   update.disabled=true;status.textContent='ПРОВЕРКА ИСТОЧНИКА…';
   let proof=null;
   for(const url of ['./api/nox/progress','./nox-progress-receipt.json']){
    try{const response=await fetch(url,{cache:'no-store',credentials:'same-origin',headers:{Accept:'application/json'}});
      if(!response.ok)continue;
      const type=response.headers.get('content-type')||'';if(!type.includes('json'))continue;
      proof=await response.json();break;
    }catch{}
   }
   visible(proof);update.disabled=false;
  };
  update.addEventListener('click',fetchEvidence);
  exportBtn.addEventListener('click',()=>{
   if(!last||exportBtn.disabled)return;
   const blob=new Blob([JSON.stringify(last,null,2)],{type:'application/json'});
   const href=URL.createObjectURL(blob);const a=document.createElement('a');
   a.href=href;a.download='NOX_VERIFIED_DISTILLATION_PROGRESS.json';a.click();
   setTimeout(()=>URL.revokeObjectURL(href),1000);
  });
  window.NOX_PROGRESS_PANEL=Object.freeze({refresh:fetchEvidence,status:()=>status.textContent,source:'READ_ONLY_VERIFIED_PROOF'});
  fetchEvidence();
 };
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',ready,{once:true});else ready();
})();
