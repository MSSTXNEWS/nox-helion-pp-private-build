/* NOX Creative secondary WOW 001–200 entrypoint: originals PR44/PR38, one layered visual scene.
 * No host event spoofing; preview is explicitly marked DEMO, never LIVE/100%.
 * D02 HOME untouched; animation source supplied by owner-approved original donor files.
 */
import {mountUnifiedCinema,reviewWowScopes} from '../proposals/NOX-WOW-UNIFIED-1-150/gate.mjs';
import {CUES} from '../proposals/NOX-WOW51-100/catalog.mjs';
import {SHOTS} from '../proposals/NOX-WOW101-150/catalog.mjs';
import {COMPOSITIONS} from '../proposals/NOX-WOW151-200/catalog.mjs';
import {mountCinematic} from '../proposals/NOX-PACK01-50/cinema50.mjs';

const $=id=>document.getElementById(id);
const validModes=new Set(['ECO','BALANCED','MAX','REDUCED']);
const detail=new Map([...CUES,...SHOTS,...COMPOSITIONS].map(x=>[x.id,x.name||x.title]));
let scene=null,pack=null;
export const ownerAudit=()=>Object.freeze({
  first50:pack!==null?50:0,secondary51to100:CUES.length,
  secondary101to150:SHOTS.length,secondary151to200:COMPOSITIONS.length,
  noxApprovedHomeUnmodified:true,mode:scene?.current().active||'IDLE',
  releaseAccepted:false,sourceOnly:true
});
const mode=()=>document.body.classList.contains('mode-eco')?'ECO':document.body.classList.contains('mode-max')?'MAX':document.body.classList.contains('mode-reduce')?'REDUCED':'BALANCED';
// The OS Reduced Motion preference outranks user and preview animation modes.
const safeMode=(requested,motion)=>motion?.matches===true?'REDUCED':validModes.has(requested)?requested:'BALANCED';
const note=(x)=>{const e=$('nox-wow200-state');if(e)e.textContent=x};
function create(){
  const parent=$('screen-immersive');
  if(!parent || parent.id==='home' || parent.closest('[data-nox-page="home"]'))return;
  if($('nox-wow200-panel'))return;
  const card=document.createElement('div');card.id='nox-wow200-panel';card.className='nox-w200-ui';
  const head=document.createElement('h3');head.textContent='WOW 001–200 · кинематографические эффекты NOX';
  const expl=document.createElement('p');expl.textContent='Сохранены исходные эффекты и анимации. Предпросмотр — художественная сцена, а не обучение ИИ или подтверждение готового EXE.';
  const controls=document.createElement('div');controls.className='nox-w200-controls';
  // Original secondary WOW: graphic-only controls. Keep hidden scalar state so
  // existing R14 mode/preview consumers keep their exact semantics and IDs.
  const label=document.createElement('div');label.className='nox-w200-control-label';label.textContent='Эффекты 51–200';
  const select=document.createElement('input');select.type='hidden';select.id='nox-wow200-id';select.value='51';
  const effectGrid=document.createElement('div');effectGrid.id='nox-wow200-effects';effectGrid.className='nox-w200-effect-grid';
  effectGrid.setAttribute('role','group');effectGrid.setAttribute('aria-label','Кинематографические эффекты 51–200');
  const effectButtons=[];
  function selectEffect(id){
    if(!Number.isInteger(id)||id<51||id>200)return false;
    select.value=String(id);
    for(const button of effectButtons){
      const active=button.dataset.effectId===String(id);
      button.className=active?'nox-w200-effect-tile is-active':'nox-w200-effect-tile';
      button.setAttribute('aria-pressed',String(active));
    }
    return true;
  }
  for(let id=51;id<=200;id++){
    const button=document.createElement('button');button.type='button';
    button.dataset.effectId=String(id);
    button.className=id===51?'nox-w200-effect-tile is-active':'nox-w200-effect-tile';
    button.textContent=String(id);button.title=detail.get(id)||'WOW NOX';
    button.setAttribute('aria-label',`Эффект ${id} · ${detail.get(id)||'WOW NOX'}`);
    button.setAttribute('aria-pressed',String(id===51));
    button.onclick=()=>selectEffect(id);
    effectButtons.push(button);effectGrid.append(button);
  }
  label.append(select,effectGrid);
  const modLabel=document.createElement('div');modLabel.className='nox-w200-control-label';modLabel.textContent='Производительность';
  const mod=document.createElement('input');mod.type='hidden';mod.id='nox-wow200-mode';mod.value=mode();
  const modeGrid=document.createElement('div');modeGrid.id='nox-wow200-modes';modeGrid.className='nox-w200-mode-grid';
  modeGrid.setAttribute('role','group');modeGrid.setAttribute('aria-label','Режим анимации');
  const modeButtons=[];
  const syncModeButtons=()=>{for(const button of modeButtons){
    const active=button.dataset.mode===mod.value;
    button.className=active?'nox-w200-mode-chip is-active':'nox-w200-mode-chip';
    button.setAttribute('aria-pressed',String(active));
  }};
  for(const value of validModes){
    const button=document.createElement('button');button.type='button';button.textContent=value;
    button.dataset.mode=value;button.setAttribute('aria-label','Режим '+value);
    button.onclick=()=>{mod.value=value;mod.onchange?.()};
    modeButtons.push(button);modeGrid.append(button);
  }
  syncModeButtons();modLabel.append(mod,modeGrid);
  const btn=document.createElement('button');btn.type='button';btn.id='nox-wow200-preview';btn.textContent='Показать эффект';
  controls.append(label,modLabel,btn);
  const preview=document.createElement('div');preview.className='nox-w200-cinema';
  const root=document.createElement('div');root.id='nox-wow200-stage';root.dataset.noxWowSlot='secondary';root.className='nox-w200-stage';preview.append(root);
  const report=document.createElement('p');report.id='nox-wow200-state';report.className='nox-w200-note';report.textContent='SOURCE · готов к предпросмотру';
  const title=document.createElement('h3');title.textContent='WOW 001–050 · реальные маршруты / материалы';
  const routes=document.createElement('div');routes.id='nox-wow200-routes';routes.className='nox-w200-pack01 nox-pack01';routes.dataset.noxWowSlot='secondary';
  card.append(head,expl,controls,preview,report,title,routes);parent.append(card);
  const motion=window.matchMedia?.('(prefers-reduced-motion: reduce)')??null;
  const effective=()=>safeMode(mod.value,motion);
  const applyMode=()=>{const current=effective();scene?.setMode(current);pack?.setMode(current.toLowerCase());return current;};
  try{
    reviewWowScopes();
    scene=mountUnifiedCinema(root,{mode:effective(),reducedMotion:motion?.matches===true});
    btn.onclick=()=>{const id=Number(select.value);if(!Number.isInteger(id)||id<51||id>200)return;
      const current=applyMode();const cue=scene.preview(id);
      note('DEMO · '+id+' · '+(cue.name||cue.title||'киноэффект')+' · режим '+current+' · не подтверждение работы GPU');};
    mod.onchange=()=>{syncModeButtons();return applyMode()};
    if(typeof motion?.addEventListener==='function')motion.addEventListener('change',applyMode);
    else if(typeof motion?.addListener==='function')motion.addListener(applyMode);
  }catch(e){note('HOLD визуального движка: '+e.message)}
  // First 50 actual route presets are read from the original single P01 catalog.
  // We do not dispatch privileged routes on a visual preview click.
  fetch('wow200/pack01-catalog.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('P01 catalog unavailable');return r.json()}).then(catalog=>{
    if(catalog?.version!=='NOX-INTEGRATION-PACK-01'||!Array.isArray(catalog.actions)||catalog.actions.length!==50||
       new Set(catalog.actions.map(x=>x?.routeId)).size!==50||
       catalog.actions.some((x,i)=>!x||x.taskId!=='NIP01-'+String(i+1).padStart(2,'0')||
         !/^[a-z][a-z0-9]*(?:[._][a-z0-9]+)*$/.test(x.routeId)||
         !['chat','models','learning','voice','space'].includes(x.category)||
         !Number.isInteger(x.owner)||x.owner<1||x.owner>6))
      throw Error('P01 original catalog identity or routes incomplete');
    for(const action of catalog.actions){const button=document.createElement('button');button.className='nox-pack01__tile';button.type='button';button.dataset.routeId=action.routeId;button.dataset.state='HOLD';button.textContent=action.title||action.routeId;
      const description=document.createElement('span');description.textContent='FX preview / без вызова действия';button.append(description);
      button.onclick=()=>{
        // UI gesture opens the real existing P01 function panel. Never auto-execute
        // privileged actions or simulate a successful backend operation.
        if(window.parent===window){note('HOLD · основной NOX не подключён к маршруту '+action.routeId);return;}
        try{
          window.parent.postMessage({type:'nox.creative.navigate.v1',routeId:action.routeId},window.location.origin);
          note('REQUESTED · '+action.routeId+' · ожидается подтверждение основного NOX, действие ещё не выполнено');
        }catch{note('HOLD · нет доступного канала к основной функции '+action.routeId);}

      };
      routes.append(button)}
    pack=mountCinematic(routes,catalog);pack.decorate();pack.setMode(effective().toLowerCase());
  }).catch(e=>{routes.textContent='WOW 001–050: исходный маршрутный каталог недоступен · HOLD · '+e.message});
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',create,{once:true});else create();