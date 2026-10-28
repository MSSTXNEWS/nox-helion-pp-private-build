'use strict';
const bc = 'BroadcastChannel' in window ? new BroadcastChannel('nox-helion-theater') : null;
const video=document.getElementById('video'), poster=document.getElementById('poster');
let objectURL=null;
// The native projector is a separate, non-privileged WebView2. The original
// /api/media route never existed on nox.local's static Assets mapping.
// Only native WPF may opt this page into a private read-only project mapping.
const query=new URLSearchParams(location.search);
const project=query.get('project');
const nativeMedia=query.get('local_project_media')==='1';
if(nativeMedia && project && /^[a-z0-9_-]{1,48}$/i.test(project)){
 video.src='https://nox-projects.invalid/'+encodeURIComponent(project)+'/NOX_MOVIE_FINAL.mp4';
 video.style.display='block';poster.style.display='none';
 video.addEventListener('error',()=>{
   video.style.display='none';poster.style.display='block';
   document.getElementById('space').textContent='Фильм пока недоступен. Выбери локальный MP4.';
 },{once:true});
}
function command(d){if(!d || typeof d!=='object')return;
 if(d.action==='play' && video.src)video.play().catch(()=>{});
 if(d.action==='pause')video.pause();
 if(d.action==='title')document.getElementById('title').textContent=String(d.value||'NOX HELION').slice(0,120);
 if(d.action==='space')document.getElementById('space').textContent=String(d.value||'Кинозал').slice(0,120);
 if(d.action==='fullscreen')document.getElementById('stage').requestFullscreen?.().catch(()=>{});
}
if(bc)bc.onmessage=e=>command(e.data);
document.getElementById('file').onchange=e=>{const f=e.target.files[0];if(!f)return;if(objectURL)URL.revokeObjectURL(objectURL);objectURL=URL.createObjectURL(f);video.src=objectURL;video.style.display='block';poster.style.display='none';};
document.getElementById('play').onclick=()=>video.play().catch(()=>{});
document.getElementById('pause').onclick=()=>video.pause();
document.getElementById('full').onclick=()=>document.getElementById('stage').requestFullscreen?.().catch(()=>{});
document.getElementById('screens').onclick=async()=>{try{if(!window.getScreenDetails){alert('Выбери монитор или проектор в настройках Windows и перетащи окно на него.');return;}const d=await window.getScreenDetails();alert('Обнаружено экранов: '+d.screens.length+'. Перемести окно на нужный экран, затем нажми полный экран.');}catch(e){alert('Разрешение на экраны не выдано. Используй перетаскивание окна.')}};
window.addEventListener('beforeunload',()=>{if(objectURL)URL.revokeObjectURL(objectURL);bc?.close()});