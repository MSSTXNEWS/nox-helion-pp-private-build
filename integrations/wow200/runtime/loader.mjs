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
const note=(x)=>{const e=$('nox-wow200-state');if(e)e.textContent=x};
function create(){
  const parent=$('screen-immersive');
  if(!parent || parent.id==='home' || parent.closest('[data-nox-page="home"]'))return;
  if($('nox-wow200-panel'))return;
  const card=document.createElement('div');card.id='nox-wow200-panel';card.className='nox-w200-ui';
  const head=document.createElement('h3');head.textContent='WOW 001–200 · кинематографические эффекты NOX';
  const expl=document.createElement('p');expl.textContent='Сохранены исходные эффекты и анимации. Предпросмотр — художественная сцена, а не обучение ИИ или подтверждение готового EXE.';
  const controls=document.createElement('div');controls.className='nox-w200-controls';
  const label=document.createElement('label');label.textContent='Выбрать эффект 51–200';
  const select=document.createElement('select');select.id='nox-wow200-id';
  for(let id=51;id<=200;id++){const o=document.createElement('option');o.value=String(id);o.textContent=`${id} · ${detail.get(id)||'WOW NOX'}`;select.append(o)}
  label.append(select);
  const modLabel=document.createElement('label');modLabel.textContent='Производительность';
  const mod=document.createElement('select');mod.id='nox-wow200-mode';
  for(const v of validModes){const o=document.createElement('option');o.value=v;o.textContent=v;mod.append(o)}mod.value=mode();modLabel.append(mod);
  const btn=document.createElement('button');btn.type='button';btn.id='nox-wow200-preview';btn.textContent='Показать эффект';
  controls.append(label,modLabel,btn);
  const preview=document.createElement('div');preview.className='nox-w200-cinema';
  const root=document.createElement('div');root.id='nox-wow200-stage';root.dataset.noxWowSlot='secondary';root.className='nox-w200-stage';preview.append(root);
  const report=document.createElement('p');report.id='nox-wow200-state';report.className='nox-w200-note';report.textContent='SOURCE · готов к предпросмотру';
  const title=document.createElement('h3');title.textContent='WOW 001–050 · реальные маршруты / материалы';
  const routes=document.createElement('div');routes.id='nox-wow200-routes';routes.className='nox-w200-pack01 nox-pack01';routes.dataset.noxWowSlot='secondary';
  card.append(head,expl,controls,preview,report,title,routes);parent.append(card);
  try{
    reviewWowScopes();
    scene=mountUnifiedCinema(root,{mode:mod.value,reducedMotion:window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches||false});
    btn.onclick=()=>{const id=Number(select.value);if(!Number.isInteger(id)||id<51||id>200)return;
      scene.setMode(mod.value);const cue=scene.preview(id);
      note('DEMO · '+id+' · '+(cue.name||cue.title||'киноэффект')+' · режим '+mod.value+' · не подтверждение работы GPU');};
    mod.onchange=()=>scene?.setMode(mod.value);
    const mr=window.matchMedia?.('(prefers-reduced-motion: reduce)');
    mr?.addEventListener?.('change',e=>{if(e.matches)scene?.setMode('REDUCED');else scene?.setMode(mod.value)});
  }catch(e){note('HOLD визуального движка: '+e.message)}
  // First 50 actual route presets are read from the original single P01 catalog.
  // We do not dispatch privileged routes on a visual preview click.
  fetch('../pack01-catalog.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('P01 catalog unavailable');return r.json()}).then(catalog=>{
    if(!Array.isArray(catalog.actions)||catalog.actions.length!==50)throw Error('P01 original routes incomplete');
    for(const action of catalog.actions){const button=document.createElement('button');button.className='nox-pack01__tile';button.type='button';button.dataset.routeId=action.routeId;button.dataset.state='HOLD';button.textContent=action.title||action.routeId;
      const description=document.createElement('span');description.textContent='FX preview / без вызова действия';button.append(description);
      button.onclick=()=>{note('WOW 001–050 · '+action.routeId+' · визуальный пресет. Работа функции проверяется в основном NOX, не здесь.')};
      routes.append(button)}
    pack=mountCinematic(routes,catalog);pack.decorate();pack.setMode(mod.value.toLowerCase());
  }).catch(e=>{routes.textContent='WOW 001–050: исходный маршрутный каталог недоступен · HOLD · '+e.message});
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',create,{once:true});else create();