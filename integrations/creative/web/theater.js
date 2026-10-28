'use strict';
// E06: Keep the existing WPF WebView2 projector; no HTTP media API or second host.
const $=id=>document.getElementById(id);
const video=$('video'),poster=$('poster'),stage=$('stage'),status=$('status');
const bc=typeof BroadcastChannel==='function'?new BroadcastChannel('nox-helion-theater'):null;
let videoUrl=null,subtitleUrl=null,track=null;
const note=t=>{status.textContent=t};
const query=new URLSearchParams(window.location.search);
const project=query.get('project');
const nativeMedia=query.get('local_project_media')==='1';
// Only WPF's scoped virtual host may enable this media mapping.
if(nativeMedia && project && /^[a-z0-9_-]{1,48}$/i.test(project)){
 video.src='https://nox-projects.invalid/'+encodeURIComponent(project)+'/NOX_MOVIE_FINAL.mp4';
 video.style.display='block';poster.style.display='none';
 note('NOX · локальный фильм '+project+' · нажмите ▶');
 video.addEventListener('error',()=>{video.removeAttribute('src');video.load();video.style.display='none';poster.style.display='block';note('Фильм ещё не готов — выберите локальный MP4');},{once:true});
}else if(project&&/^[a-z0-9_-]{1,48}$/i.test(project)){
 note('Проект '+project+': выберите MP4/WebM через кнопку файла');
}
function releaseVideo(){if(videoUrl){URL.revokeObjectURL(videoUrl);videoUrl=null}}
function releaseSubtitle(){if(track){track.remove();track=null}if(subtitleUrl){URL.revokeObjectURL(subtitleUrl);subtitleUrl=null}}
function chooseVideo(file){
 if(!file)return;
 releaseVideo();videoUrl=URL.createObjectURL(file);video.src=videoUrl;
 video.style.display='block';poster.style.display='none';video.load();
 note('Видео выбрано: '+file.name+' — нажмите ▶');
}
function toWebVtt(text,name){
 const body=text.replace(/^\uFEFF/,'').replace(/\r\n?/g,'\n').trim();
 if(/\.vtt$/i.test(name)){if(!/^WEBVTT(?:\s|$)/.test(body))throw Error('Неверный заголовок VTT');return body+'\n'}
 if(!/\.srt$/i.test(name)||!/\d{1,2}:\d{2}:\d{2},\d{1,3}\s*-->/.test(body))throw Error('Неверный формат SRT');
 return 'WEBVTT\n\n'+body.replace(/(\d{1,2}:\d{2}:\d{2}),(\d{1,3})/g,(_,h,ms)=>h+'.'+ms.padEnd(3,'0'))+'\n';
}
async function chooseSubtitle(file){
 if(!file)return;
 if(file.size>2*1024*1024){note('Субтитры больше 2 МиБ — HOLD');return}
 try{
  const source=await file.text();const vtt=toWebVtt(source,file.name);
  releaseSubtitle();subtitleUrl=URL.createObjectURL(new Blob([vtt],{type:'text/vtt'}));
  track=document.createElement('track');track.kind='subtitles';track.label=file.name;track.srclang='ru';track.default=true;track.src=subtitleUrl;video.appendChild(track);
  track.addEventListener('load',()=>{if(track&&track.track)track.track.mode='showing'});
  note('Субтитры загружены: '+file.name);
 }catch(error){note('Субтитры не подключены: '+String(error.message||error))}
}
async function toggleFullscreen(){
 try{if(document.fullscreenElement){await document.exitFullscreen();note('Обычный режим')}
 else{if(typeof stage.requestFullscreen!=='function')throw Error('Недоступен в WebView2');await stage.requestFullscreen();note('Полный экран')}}
 catch(error){note('Полный экран отклонён: '+String(error.message||error)+'; используйте кнопку окна')}
}
async function play(){if(!video.src){note('Сначала выберите видео');return}try{await video.play();note('Воспроизведение')}catch(error){note('Не удалось запустить видео: '+String(error.message||error))}}
function pause(){video.pause();note('Пауза')}
function command(data){
 if(!data||typeof data!=='object')return;
 if(data.action==='play')void play();
 if(data.action==='pause')pause();
 if(data.action==='title')$('title').textContent=String(data.value||'NOX HELION').slice(0,120);
 if(data.action==='space')$('space').textContent=String(data.value||'Кинозал').slice(0,120);
 if(data.action==='fullscreen')void toggleFullscreen();
}
if(bc)bc.onmessage=e=>command(e.data);
$('file').onchange=e=>chooseVideo(e.target.files?.[0]);
$('subtitles').onchange=e=>void chooseSubtitle(e.target.files?.[0]);
$('play').onclick=()=>void play();
$('pause').onclick=pause;
$('full').onclick=()=>void toggleFullscreen();
$('screens').onclick=async()=>{
 try{
  if(typeof window.getScreenDetails!=='function'){note('Для проектора перенесите окно на нужный монитор Windows');return}
  const details=await window.getScreenDetails();
  note('Экранов обнаружено: '+details.screens.length+'. Перенесите окно и нажмите ⛶');
 }catch(error){note('Доступ к списку экранов не выдан; переносите окно средствами Windows')}
};
window.addEventListener('keydown',event=>{
 if(event.key==='F11'&&!event.repeat){event.preventDefault();void toggleFullscreen()}
 if(event.key==='Escape'&&document.fullscreenElement){event.preventDefault();void document.exitFullscreen().catch(()=>{})}
});
window.addEventListener('beforeunload',()=>{releaseSubtitle();releaseVideo();bc?.close()});
