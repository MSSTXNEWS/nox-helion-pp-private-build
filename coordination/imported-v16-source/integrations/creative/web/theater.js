'use strict';
// E06: Keep the existing WPF WebView2 projector; no HTTP media API or second host.
const $=id=>document.getElementById(id);
const video=$('video'),poster=$('poster'),stage=$('stage'),status=$('status');
const bc=typeof BroadcastChannel==='function'?new BroadcastChannel('nox-helion-theater'):null;
let videoUrl=null,subtitleUrl=null,track=null,subtitleGeneration=0,nativeErrorHandler=null;
let playbackGeneration=0; // suppress old play() settlements after pause/media change/navigation
const note=t=>{status.textContent=t};
const query=new URLSearchParams(window.location.search);
const project=query.get('project');
const nativeMedia=query.get('local_project_media')==='1';
// WPF owns the physical projector; WebView2 theater has no native privileges.
const nativeViewer=query.get('nox_native_viewer')==='1';
// Only WPF's scoped virtual host may enable this media mapping.
if(nativeMedia && project && /^[a-z0-9_-]{1,48}$/i.test(project)){
 video.src='https://nox-projects.invalid/'+encodeURIComponent(project)+'/NOX_MOVIE_FINAL.mp4';
 video.style.display='block';poster.style.display='none';
 note('NOX · локальный фильм '+project+' · нажмите ▶');
 nativeErrorHandler=()=>{nativeErrorHandler=null;invalidatePlayback();video.removeAttribute('src');video.load();video.style.display='none';poster.style.display='block';note('Фильм ещё не готов — выберите локальный MP4');};
 video.addEventListener('error',nativeErrorHandler,{once:true});
}else if(project&&/^[a-z0-9_-]{1,48}$/i.test(project)){
 note('Проект '+project+': выберите MP4/WebM через кнопку файла');
}
function invalidatePlayback(){playbackGeneration++;video.pause()}
function releaseVideo(){if(videoUrl){URL.revokeObjectURL(videoUrl);videoUrl=null}}
function releaseSubtitle(){if(track){track.remove();track=null}if(subtitleUrl){URL.revokeObjectURL(subtitleUrl);subtitleUrl=null}}
function chooseVideo(file){
 if(!file)return;
 if(!/\.(mp4|webm|mov)$/i.test(file.name||'') || !(file.size>0) || file.size>16*1024*1024*1024){note('MEDIA_HOLD: выберите непустой MP4/WebM/MOV');return;}
 // Switching to a user-selected file must disarm the old project's error listener.
 if(nativeErrorHandler){video.removeEventListener('error',nativeErrorHandler);nativeErrorHandler=null;}
 // A new film invalidates previous pending play(), captions and file reads.
 invalidatePlayback();subtitleGeneration++;releaseSubtitle();
 releaseVideo();videoUrl=URL.createObjectURL(file);video.src=videoUrl;
 video.style.display='block';poster.style.display='none';video.load();
 note('Видео выбрано: '+file.name+' — нажмите ▶');
}
// A selected local movie may fail *after* the file picker succeeds. Restore a usable poster.
video.addEventListener('error',()=>{
 if(!videoUrl)return;
 invalidatePlayback();subtitleGeneration++;releaseSubtitle();releaseVideo();
 video.removeAttribute('src');video.load();
 video.style.display='none';poster.style.display='block';
 note('Локальное видео повреждено или формат не поддерживается — выберите MP4/WebM');
});
function toWebVtt(text,name){
 const body=text.replace(/^\uFEFF/,'').replace(/\r\n?/g,'\n').trim();
 if(/\.vtt$/i.test(name)){if(!/^WEBVTT(?:\s|$)/.test(body))throw Error('Неверный заголовок VTT');return body+'\n'}
 if(!/\.srt$/i.test(name)||!/\d{1,2}:\d{2}:\d{2},\d{1,3}\s*-->/.test(body))throw Error('Неверный формат SRT');
 return 'WEBVTT\n\n'+body.replace(/(\d{1,2}:\d{2}:\d{2}),(\d{1,3})/g,(_,h,ms)=>h+'.'+ms.padEnd(3,'0'))+'\n';
}
async function chooseSubtitle(file){
 if(!file)return;
 // Last selected subtitle wins even when file.text() resolves out of order.
 const selectedGeneration=++subtitleGeneration;
 // Keep the last valid track while parsing a replacement; invalid input does not discard it.
 if(file.size>2*1024*1024){note('Субтитры больше 2 МиБ — HOLD');return}
 try{
  const source=await file.text();
  if(selectedGeneration!==subtitleGeneration)return;
  const vtt=toWebVtt(source,file.name);
  releaseSubtitle();
  subtitleUrl=URL.createObjectURL(new Blob([vtt],{type:'text/vtt'}));
  track=document.createElement('track');track.kind='subtitles';track.label=file.name;
  const lang=/(?:^|[._ -])(es|ru|en|fr|de|it|pt|uk|pl)(?=[._ -]|\.(?:srt|vtt)$)/i.exec(file.name);
  track.srclang=(lang?.[1]||document.documentElement?.lang||'ru').toLowerCase();track.default=true;track.src=subtitleUrl;video.appendChild(track);
  const loadedTrack=track;
  loadedTrack.addEventListener('load',()=>{if(track===loadedTrack&&loadedTrack.track)loadedTrack.track.mode='showing'});
  note('Субтитры загружены: '+file.name);
 }catch(error){if(selectedGeneration===subtitleGeneration)note('HOLD: Субтитры не подключены: '+String(error.message||error))}
}
async function toggleFullscreen(){
 if(nativeViewer){note('Полный экран управляется панелью Windows NOX или F11');return}
 try{if(document.fullscreenElement){await document.exitFullscreen();note('Обычный режим')}
 else{if(typeof stage.requestFullscreen!=='function')throw Error('Недоступен в WebView2');await stage.requestFullscreen();note('Полный экран')}}
 catch(error){note('Полный экран отклонён: '+String(error.message||error)+'; используйте кнопку окна')}
}
async function play(){
 const source=video.currentSrc||video.src;
 if(!source){note('Сначала выберите видео');return}
 const generation=++playbackGeneration;
 try{
  await video.play();
  if(generation===playbackGeneration&&source===(video.currentSrc||video.src))note('Воспроизведение');
 }catch(error){
  if(generation===playbackGeneration&&source===(video.currentSrc||video.src))note('Не удалось запустить видео: '+String(error.message||error));
 }
}
function pause(){invalidatePlayback();note('Пауза')}
// Back stays in the existing scoped /creative/ virtual host; never history.back()
// to a potentially unrelated page, window.open(), or a second WPF host.
function backToStudio(){
 if(document.fullscreenElement){note('Сначала выйдите из полноэкранного режима');return}
 cleanup();
 window.location.assign('studio.html');
}
function command(data){
 if(!data||typeof data!=='object')return;
 // BroadcastChannel has no native user gesture and cannot authorize media playback.
 if(data.action==='play')note('MEDIA_HOLD: нажмите ▶ в окне кинозала');
 if(data.action==='pause')pause();
 if(data.action==='title')$('title').textContent=String(data.value||'NOX HELION').slice(0,120);
 if(data.action==='space')$('space').textContent=String(data.value||'Кинозал').slice(0,120);
 if(data.action==='fullscreen')void toggleFullscreen();
}
if(bc)bc.onmessage=e=>command(e.data);
// A single fullscreen owner: native WPF for the projector, DOM for browser preview.
if(nativeViewer){$('full').hidden=true;$('full').disabled=true;}
$('file').onchange=e=>{const input=e.target,file=input.files?.[0];input.value='';chooseVideo(file)};
$('subtitles').onchange=e=>{const input=e.target,file=input.files?.[0];input.value='';void chooseSubtitle(file)};
$('play').onclick=()=>void play();
$('pause').onclick=pause;
$('back').onclick=backToStudio;
$('full').onclick=()=>void toggleFullscreen();
$('screens').onclick=()=>{
 note('Выбор физического проектора/монитора выполняется через нативную панель NOX Windows.');
};
window.addEventListener('keydown',event=>{
 if(nativeViewer)return;
 if(event.key==='F11'&&!event.repeat){event.preventDefault();void toggleFullscreen()}
 if(event.key==='Escape'&&document.fullscreenElement){event.preventDefault();void document.exitFullscreen().catch(()=>{})}
});
function cleanup(){invalidatePlayback();subtitleGeneration++;releaseSubtitle();releaseVideo();bc?.close()}
window.addEventListener('pagehide',cleanup);
window.addEventListener('beforeunload',cleanup);
