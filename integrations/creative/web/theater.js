'use strict';
// E06: existing projector WebView2, local user-selected media only. No second server or media endpoint.
const bc = 'BroadcastChannel' in window ? new BroadcastChannel('nox-helion-theater') : null;
const $ = id => document.getElementById(id);
const video = $('video'), poster = $('poster'), status = $('media-status');
let mediaURL = null, subtitleURL = null, subtitleTrack = null;
let mediaEpoch = 0, subtitleEpoch = 0; // discard stale async subtitles
function notice(message) { status.textContent = String(message).slice(0, 300); }
function forgetSubtitles() {
  if (subtitleTrack) { subtitleTrack.remove(); subtitleTrack = null; }
  if (subtitleURL) { URL.revokeObjectURL(subtitleURL); subtitleURL = null; }
}
function subtitleToVtt(raw, ext) {
  const text = raw.replace(/^\uFEFF/, '').replace(/\r\n?/g, '\n');
  if (ext === '.vtt') {
    if (!/^WEBVTT(?:[ \t].*)?\n/.test(text)) throw new Error('Некорректный WEBVTT');
    return text;
  }
  if (ext !== '.srt' || !/\d{2}:\d{2}:\d{2},\d{3}\s+-->\s+\d{2}:\d{2}:\d{2},\d{3}/.test(text)) {
    throw new Error('Некорректный SRT');
  }
  return 'WEBVTT\n\n' + text.replace(/(\d{2}:\d{2}:\d{2}),(\d{3})/g, '$1.$2')
    .replace(/^\s*\d+\s*\n(?=\d{2}:\d{2}:\d{2}\.\d{3}\s+-->)/gm, '');
}
function command(d) {
  if (!d || typeof d !== 'object') return;
  if (d.action === 'play') play();
  if (d.action === 'pause') video.pause();
  if (d.action === 'title') $('title').textContent = String(d.value || 'NOX HELION').slice(0, 120);
  if (d.action === 'space') $('space').textContent = String(d.value || 'Кинозал').slice(0, 120);
  if (d.action === 'fullscreen') fullscreen();
}
function play() {
  if (!video.src) { notice('Сначала выберите локальный видеофайл.'); return; }
  video.play().catch(() => notice('Воспроизведение заблокировано или кодек не поддерживается.'));
}
function fullscreen() {
  Promise.resolve($('stage').requestFullscreen?.()).catch(() => notice('Полноэкранный режим недоступен.'));
}
if (bc) bc.onmessage = e => command(e.data);
const project = new URLSearchParams(location.search).get('project');
if (project && /^[a-z0-9_-]{1,48}$/i.test(project)) {
  notice('Проект ' + project + ': выберите готовый видеофайл на компьютере. Автоматический доступ к закрытым файлам проекта не предоставляется.');
}
$('file').onchange = e => {
  const file = e.target.files?.[0]; if (!file) return;
  if (!/\.(mp4|webm|mov|m4v)$/i.test(file.name) || file.size < 1) {
    notice('HOLD: выберите непустой MP4, WebM, MOV или M4V.'); return;
  }
  video.pause(); mediaEpoch++; subtitleEpoch++; forgetSubtitles();
  if (mediaURL) URL.revokeObjectURL(mediaURL);
  mediaURL = URL.createObjectURL(file);
  video.src = mediaURL;
  video.style.display = 'block'; poster.style.display = 'none';
  notice('Видео загружено локально: ' + file.name + '. Можно добавить .srt или .vtt.');
};
$('subtitle-file').onchange = async e => {
  const file = e.target.files?.[0]; if (!file) return;
  const ext = /\.(srt|vtt)$/i.exec(file.name)?.[0]?.toLowerCase();
  if (!video.src) { notice('Сначала выберите видео.'); return; }
  if (!ext || file.size < 1 || file.size > 5 * 1024 * 1024) {
    notice('HOLD: субтитры .srt/.vtt, размер до 5 МБ.'); return;
  }
  const subtitleChoice = ++subtitleEpoch, movieChoice = mediaEpoch;
  try {
    const vtt = subtitleToVtt(await file.text(), ext);
    if (subtitleChoice !== subtitleEpoch || movieChoice !== mediaEpoch || !mediaURL) return;
    const nextURL = URL.createObjectURL(new Blob([vtt], { type: 'text/vtt' }));
    const track = document.createElement('track');
    track.kind = 'subtitles'; track.label = 'Локальные субтитры';
    track.srclang = /\.(ru|es|en)\.(?:srt|vtt)$/i.exec(file.name)?.[1]?.toLowerCase() || 'und';
    track.src = nextURL; track.default = true;
    const enable = () => {
      if (subtitleTrack === track && video.textTracks?.length)
        video.textTracks[video.textTracks.length - 1].mode = 'showing';
    };
    track.addEventListener?.('load', enable);
    forgetSubtitles(); subtitleURL = nextURL; subtitleTrack = track;
    video.appendChild(track); enable();
    notice('Субтитры подключены: ' + file.name);
  } catch (error) {
    if (subtitleChoice === subtitleEpoch && movieChoice === mediaEpoch)
      notice('HOLD: файл субтитров не прочитан: ' + String(error?.message || error));
  }
};
$('play').onclick = play;
$('pause').onclick = () => video.pause();
$('full').onclick = fullscreen;
$('screens').onclick = async () => {
  try {
    if (!window.getScreenDetails) { notice('Перенесите окно на нужный монитор Windows, затем нажмите полный экран.'); return; }
    const d = await window.getScreenDetails(); notice('Экранов доступно: ' + d.screens.length + '. Перенесите окно на проектор.');
  } catch (_) { notice('Разрешение на экраны не получено. Используйте перенос окна.'); }
};
video.addEventListener('error', () => notice('HOLD: видео не открылось (формат или кодек).'));
window.addEventListener('beforeunload', () => {
  mediaEpoch++; subtitleEpoch++;
  video.pause(); forgetSubtitles();
  if (mediaURL) URL.revokeObjectURL(mediaURL);
  bc?.close();
});
