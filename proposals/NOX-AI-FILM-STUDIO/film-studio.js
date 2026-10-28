/* NOX HELION Film Studio. Native host is the only entity that can save/render/export.
   The editor can plan a movie offline. It NEVER fabricates GPU work or rendered clips.
   D02 HOME lock: mount only this approved secondary film page. */
(function(){'use strict';
const $=id=>document.getElementById(id);
const STYLES=[
 ["photoreal","Фотореалистичный фильм"],["anime","Аниме"],["cartoon_2d","2D-мультфильм"],
 ["cartoon_3d","3D-мультфильм"],["stop_motion","Стоп-моушен"],["manga_motion","Ожившая манга"],
 ["noir","Нуар"],["fantasy","Фэнтези"],["sci_fi","Научная фантастика"],
 ["documentary","Документальное кино"],["cinematic_3d","3D-кино"],
 ["adult_anime_18","Аниме 18+ · только взрослые"]];
const PROVIDERS=[
 ["wan21-t2v-1.3b","Wan 2.1 · T2V 1.3B",["t2v"]],
 ["wan21-vace-1.3b","Wan 2.1 · VACE",["i2v","v2v"]],
 ["wan22-ti2v-5b","Wan 2.2 · 5B",["t2v","i2v"]],
 ["wan22-i2v-a14b","Wan 2.2 · I2V A14B",["i2v"]],
 ["hunyuan15-t2v","HunyuanVideo 1.5 · T2V",["t2v"]],
 ["hunyuan15-i2v","HunyuanVideo 1.5 · I2V",["i2v"]],
 ["mochi1-preview","Mochi 1",["t2v"]],
 ["ltxv-2b-distilled","LTX-Video 2B",["t2v","i2v"]],
 ["ltx25-fast","LTX 2.5 Fast",["t2v","i2v"]],
 ["skyreels-v2-i2v-14b","SkyReels V2 I2V",["i2v"]],
 ["skyreels-v2-df-14b","SkyReels V2 Long",["t2v"]],
 ["cogvideox-5b","CogVideoX 5B",["t2v","i2v"]]];
const elements=Object.freeze({title:$("filmTitle"),style:$("filmStyle"),rating:$("filmRating"),
 resolution:$("filmResolution"),rights:$("filmRights"),adult:$("adultConfirmed"),
 sceneTitle:$("sceneTitle"),prompt:$("scenePrompt"),seconds:$("sceneSeconds"),
 provider:$("sceneProvider"),operation:$("sceneMethod"),dialogue:$("sceneDialog"),
 list:$("scenes"),sceneCount:$("sceneCount"),time:$("totalTime"),status:$("actionStatus"),
 headline:$("sceneHeadline"),detail:$("sceneDetail"),timecode:$("sceneTimecode"),
 save:$("saveFilm"),queue:$("queueFilm"),export:$("exportFilm"),projector:$("openProjector")});
const ui={scenes:[],selected:null,hostReady:false,caps:{},pending:new Map(),
  nativeSceneStatuses:new Map(),nativeProjectId:null,offlinePlan:true};
const text=(tag,value,cls)=>{const n=document.createElement(tag);if(cls)n.className=cls;n.textContent=value;return n};
function verifyAgreement(){
 if(!elements.rights.checked)return "Подтверди права на исходные материалы.";
 if(elements.style.value==="adult_anime_18"&&(elements.rating.value!=="ADULT_18"||!elements.adult.checked))
  return "Для аниме 18+ выбери категорию 18+ и подтверди совершеннолетие.";
 if(elements.rating.value==="ADULT_18"&&!elements.adult.checked)
  return "Для категории 18+ подтвердите совершеннолетие.";
 return null;
}
function updateProviders(){
 const previous=elements.provider.value;
 elements.provider.replaceChildren();
 const available=PROVIDERS.filter(p=>p[2].includes(elements.operation.value));
 for(const [id,name] of available){const option=document.createElement("option");option.value=id;option.textContent=name;elements.provider.append(option)}
 if(available.some(x=>x[0]===previous))elements.provider.value=previous;
}
function asProject(){
 return {schema:"NOX_FILM_PROJECT_V1",projectId:ui.nativeProjectId||"local-studio-draft",
  title:elements.title.value.trim(),style:elements.style.value,rating:elements.rating.value,
  userIsAdult:elements.adult.checked,sourceRightsApproved:elements.rights.checked,
  width:Number(elements.resolution.value.split("x")[0]),height:Number(elements.resolution.value.split("x")[1]),
  fps:24,locale:"ru",scenes:ui.scenes.map(s=>({...s,
    status:ui.nativeSceneStatuses.get(s.id)||"PLANNED"}))};
}
function duration(secs){return String(Math.floor(secs/60))+":"+String(secs%60).padStart(2,"0")}
function refresh(){
 elements.list.replaceChildren();const count=ui.scenes.length;
 elements.sceneCount.textContent=count+" сцен";const total=ui.scenes.reduce((s,x)=>s+x.seconds,0);
 elements.time.textContent=duration(total);
 let start=0;
 for(const s of ui.scenes){
  const timeStart=start;
  const card=text("article","","scene-card"+(ui.selected===s.id?" selected":""));
  const meta=text("div","","scene-meta");
  meta.append(text("strong",s.title),text("small",duration(start)+" – "+duration(start+s.seconds)));
  const info=text("small",s.operation.toUpperCase()+" · "+s.providerId+" · "+(ui.nativeSceneStatuses.get(s.id)||"PLANNED"));
  const detail=text("p",s.prompt.slice(0,150));
  const button=text("button","Выбрать сцену");button.type="button";
  button.addEventListener("click",()=>{ui.selected=s.id;elements.headline.textContent=s.title;
    elements.detail.textContent=s.prompt;elements.timecode.textContent=duration(timeStart);
    refresh()});
  card.append(meta,info,detail,button);elements.list.append(card);
  start+=s.seconds;
 }
 if(!count){elements.list.append(text("p","Нет сцен. Начните со сценария.", "scene-empty"));
  elements.headline.textContent="Storyboard";elements.detail.textContent="Добавьте первую сцену.";elements.timecode.textContent="00:00";}
 $("aiScreenwriter").disabled=!(ui.hostReady&&ui.caps.script===true&&count===0&&!verifyAgreement());
 elements.save.disabled=!(ui.hostReady&&ui.caps.save===true&&count>0);
 elements.queue.disabled=!(ui.hostReady&&ui.caps.queue===true&&count>0&&!verifyAgreement());
 elements.export.disabled=!(ui.hostReady&&ui.caps.export===true&&count>0&&
   ui.scenes.every(s=>ui.nativeSceneStatuses.get(s.id)==="RENDERED"));
 elements.projector.disabled=!(ui.hostReady&&ui.caps.projector===true&&ui.caps.projectRendered===true);
 $("studioStatus").textContent=ui.hostReady?"WINDOWS HOST · "+(ui.caps.queue?"ГОТОВ К ОЧЕРЕДИ":"ВЕСА НЕ ПОДКЛЮЧЕНЫ"):
  "ДЕМО-РЕЖИМ · НЕТ ПОДКЛЮЧЕНИЯ К GPU";
}
function draftScene(){
 const err=verifyAgreement();if(err){elements.status.textContent=err;return}
 if(ui.scenes.length>=250){elements.status.textContent="Ограничение: 250 сцен в одной главе.";return}
 const title=elements.sceneTitle.value.trim(),prompt=elements.prompt.value.trim();
 if(!title||!prompt){elements.status.textContent="Напишите название и описание сцены.";return}
 if(elements.operation.value!=="t2v"){elements.status.textContent=
  "Для фото/видео → видео сначала добавьте подтверждённый референс через Windows host. Пока доступно планирование текста → видео.";return}
 const seconds=Number(elements.seconds.value),total=ui.scenes.reduce((x,s)=>x+s.seconds,0);
 if(total+seconds>3600){elements.status.textContent="Глава ограничена 60 минутами; создайте следующую главу.";return}
 const id="s-"+(ui.scenes.length+1).toString(36)+"-"+Date.now().toString(36);
 const scene={id,title,prompt,seconds,operation:elements.operation.value,
  providerId:elements.provider.value,characterIds:[],referenceSha256:null,
  dialogue:elements.dialogue.value.trim(),narration:"",camera:"cinematic"};
 ui.scenes.push(scene);ui.selected=id;ui.nativeProjectId=null;
 elements.headline.textContent=title;elements.detail.textContent=prompt;
 elements.status.textContent="Сцена добавлена в раскадровку. Ещё не сгенерирована.";
 elements.sceneTitle.value="";elements.prompt.value="";elements.dialogue.value="";
 refresh();
}
function send(action){
 if(!ui.hostReady||!ui.caps[action]||ui.pending.has(action)){elements.status.textContent=
  "Нет подтверждённой функции Windows host для "+action;return}
 const err=verifyAgreement();if(err){elements.status.textContent=err;return}
 if((action==="queue"||action==="export")&&!ui.scenes.length){elements.status.textContent="Сначала создайте сцены.";return}
 const request={type:"nox.film.command.v1",action,commandId:"noxfilm-"+Date.now().toString(36),
   project:asProject(),idea:action==="script"?$("filmIdea").value.trim():null,explicitUserAction:true};
 ui.pending.set(action,true);
 try{window.chrome.webview.postMessage(request);elements.status.textContent=
   "Команда отправлена host · это не подтверждение готового фильма.";}
 catch{ui.pending.delete(action);elements.status.textContent="Windows host недоступен. Запрос не выполнен."}
 refresh();
}
function receive(msg){
 if(!msg||typeof msg!=="object")return;
 if(msg.type==="nox.film.snapshot.v1"){
   ui.hostReady=true;ui.caps=typeof msg.capabilities==="object"&&msg.capabilities||{};
   if(typeof msg.projectId==="string"&&/^([a-z][a-z0-9-]{2,63})$/.test(msg.projectId))
     ui.nativeProjectId=msg.projectId;
   if(Array.isArray(msg.scenes)&&msg.scenes.length<=250){
    ui.nativeSceneStatuses=new Map(msg.scenes.filter(s=>s&&typeof s.id==="string"&&
      ["PLANNED","QUEUED","RUNNING","RENDERED","HOLD","FAILED"].includes(s.status)).map(s=>[s.id,s.status]));
   }
   refresh();
 } else if(msg.type==="nox.film.screenplay.v1"&&ui.pending.has("script")){
   if(!Array.isArray(msg.scenes)||msg.scenes.length<1||msg.scenes.length>24)return;
   const next=[];let total=0;const ids=new Set();
   for(const scene of msg.scenes){
     if(!scene||typeof scene.id!=="string"||!/^s-[a-z0-9-]{2,60}$/.test(scene.id)||
      ids.has(scene.id)||typeof scene.title!=="string"||!scene.title.trim()||
      scene.title.length>120||typeof scene.prompt!=="string"||!scene.prompt.trim()||
      scene.prompt.length>3000||!Number.isInteger(scene.seconds)||
      scene.seconds<1||scene.seconds>20||scene.status!=="PLANNED")return;
     total+=scene.seconds;if(total>1200)return;ids.add(scene.id);
     next.push({id:scene.id,title:scene.title,prompt:scene.prompt,
      seconds:scene.seconds,operation:"t2v",
      providerId:"wan21-t2v-1.3b",characterIds:[],
      referenceSha256:null,dialogue:typeof scene.dialogue==="string"?scene.dialogue.slice(0,3000):"",
      narration:"",camera:typeof scene.camera==="string"?scene.camera.slice(0,100):"cinematic"});
   }
   ui.scenes=next;ui.selected=null;ui.nativeSceneStatuses.clear();
   ui.pending.delete("script");
   elements.status.textContent="ИИ-сценарий получен через Windows host. Видеокадры ещё не созданы.";
   refresh();
 } else if(msg.type==="nox.film.ack.v1"&&["script","save","queue","export","projector"].includes(msg.action)){
   ui.pending.delete(msg.action);
   elements.status.textContent=msg.accepted===true?
    "Host принял команду · результат ожидается в реальных событиях.":"Отказ host: "+String(msg.reason||"нет разрешения").slice(0,130);
   refresh();
 }
}
for(const [key,label] of STYLES){const o=document.createElement("option");o.value=key;o.textContent=label;elements.style.append(o)}
for(const [id,name] of PROVIDERS){const o=document.createElement("option");o.value=id;o.textContent=name;elements.provider.append(o)}
elements.style.value="anime";elements.operation.addEventListener("change",updateProviders);updateProviders();
elements.style.addEventListener("change",refresh);
for(const x of [elements.rights,elements.adult,elements.rating])x.addEventListener("change",refresh);
$("addScene").addEventListener("click",draftScene);
$("newFilm").addEventListener("click",()=>{
 ui.scenes=[];ui.selected=null;ui.nativeProjectId=null;ui.nativeSceneStatuses.clear();
 elements.status.textContent="Новая раскадровка. Несохранённые сцены предыдущего проекта очищены.";
 refresh();
});
$("aiScreenwriter").addEventListener("click",()=>{
 if(ui.scenes.length){elements.status.textContent="Для нового сценария создайте новую раскадровку.";return}
 const idea=$("filmIdea").value.trim();
 if(!idea||idea.length>2500){elements.status.textContent="Опишите идею фильма.";return}
 send("script");
});
elements.save.addEventListener("click",()=>send("save"));
elements.queue.addEventListener("click",()=>send("queue"));
elements.export.addEventListener("click",()=>send("export"));
elements.projector.addEventListener("click",()=>send("projector"));
if(window.chrome?.webview?.addEventListener)window.chrome.webview.addEventListener("message",e=>receive(e.data));
refresh();
})();
