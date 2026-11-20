/* NOX Cinema Assist. Self-contained player control layer for a source-pinned NOX build. */
(() => {
  'use strict';

  const cfg = window.NOX_CINEMA_ASSIST_CONFIG || {};
  const SCRIPT_URL = document.currentScript && document.currentScript.src ? document.currentScript.src : location.href;
  const API = cfg.apiBase || (location.protocol === 'https:' ? new URL('/api/cinema', location.origin).href : 'http://' + location.hostname + ':18776/api/cinema');
  const TOKEN = cfg.apiToken || '';
  const MODES = ['off', 'es', 'ru', 'dub'];
  const state = { mode: 'off', video: null, ws: null, context: null, worklet: null, capture: null,
    silent: null, dubGain: null, run: 0, startPromise: null, seekTimer: null, dubEpoch: 0, pipelinePending: 0,
    pipeline: Promise.resolve(), audioSeconds: 0, map: [], cues: [], esTrack: null,
    ruTrack: null, profiles: {}, profileSpeaker: '0', originalVolume: 1, duckCount: 0, dubSources: new Set(), dubTimers: new Set(), finalSignatures: new Set(), host: null,
    controls: null, caption: null, status: null, controller: null };

  const authHeaders = extra => Object.assign({ 'X-NOX-Cinema-Token': TOKEN }, extra || {});
  const apiUrl = path => API.replace(/\/$/, '') + path;
  const status = value => { if (state.status) state.status.textContent = value; };
  const safeText = value => String(value || '').replace(/\s+/g, ' ').trim();

  function speakerSlot(speaker) {
    if (speaker == null || !Number.isFinite(Number(speaker))) return state.profileSpeaker;
    const id = Number(speaker);
    // WLK's Deepgram-compatible /v1/listen adapter emits zero-based speaker IDs.
    if (id < 0) return state.profileSpeaker;
    return String(Math.max(0, Math.min(3, Math.floor(id))));
  }

  function make(tag, className, text) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (text) el.textContent = text;
    return el;
  }

  function createButton(label, action, cls) {
    const b = make('button', cls || 'nox-ca-button', label);
    b.type = 'button';
    b.addEventListener('click', action);
    return b;
  }

  function mount(video) {
    if (!video || state.video === video) return;
    const selectedMode = state.mode;
    if (state.video) unmount();
    video.dataset.noxCinemaAssist = 'ready';
    const host = video.closest('[data-cinema-player],.cinema-player,.player-shell,.player-container,.video-container') || video.parentElement;
    if (!host) return;
    state.video = video;
    state.host = host;
    state.originalVolume = Number.isFinite(video.volume) ? video.volume : 1;
    state.controller = new AbortController();
    const listen = { signal: state.controller.signal };

    const panel = make('section', 'nox-ca-panel');
    panel.setAttribute('aria-label', 'Перевод и субтитры NOX');
    const heading = make('div', 'nox-ca-heading');
    heading.append(make('strong', '', 'КИНО · ПЕРЕВОД NOX'));
    state.status = make('span', 'nox-ca-status', 'Движки не подключены');
    state.status.setAttribute('role', 'status');
    state.status.setAttribute('aria-live', 'polite');
    heading.append(state.status);
    panel.append(heading);

    const modes = make('div', 'nox-ca-modes');
    const labels = [['off', 'Выкл.'], ['es', 'Субтитры ES'], ['ru', 'Перевод RU'], ['dub', 'Дубляж RU']];
    labels.forEach(([mode, label]) => {
      const b = createButton(label, () => activate(mode));
      b.dataset.mode = mode;
      b.setAttribute('aria-pressed', String(mode === 'off'));
      modes.append(b);
    });
    panel.append(modes);

    const controls = make('div', 'nox-ca-options');
    const phone = createButton('Как открыть на телефоне', showPhoneInstructions, 'nox-ca-button nox-ca-phone');
    phone.title = 'На телефоне откройте тот же NOX-плеер и выберите Bluetooth-наушники';
    controls.append(phone);

    const voiceLabel = make('label', 'nox-ca-file-label', 'Профиль голоса персонажа');
    const speakerSelect = make('select', 'nox-ca-speaker');
    speakerSelect.setAttribute('aria-label', 'Номер говорящего в распознанной дорожке');
    [['0', 'Говорящий 1'], ['1', 'Говорящий 2'], ['2', 'Говорящий 3'], ['3', 'Говорящий 4']].forEach(([value, label]) => {
      const option = make('option', '', label); option.value = value; speakerSelect.append(option);
    });
    speakerSelect.addEventListener('change', () => { state.profileSpeaker = speakerSelect.value; });
    voiceLabel.append(speakerSelect);
    const voiceFile = make('input', 'nox-ca-file');
    voiceFile.type = 'file';
    voiceFile.accept = 'audio/wav,.wav';
    voiceFile.setAttribute('aria-label', 'Выбрать WAV образец голоса персонажа');
    voiceFile.addEventListener('change', () => uploadVoice(voiceFile.files && voiceFile.files[0]));
    voiceLabel.append(voiceFile);
    controls.append(voiceLabel);

    const original = make('label', 'nox-ca-range-label', 'Оригинал');
    const originalRange = make('input', 'nox-ca-range');
    originalRange.type = 'range'; originalRange.min = '0'; originalRange.max = '100'; originalRange.value = String(Math.round(state.originalVolume * 100));
    originalRange.addEventListener('input', () => { state.originalVolume = Number(originalRange.value) / 100; applyDuck(); });
    original.append(originalRange); controls.append(original);

    const dub = make('label', 'nox-ca-range-label', 'Русская речь');
    const dubRange = make('input', 'nox-ca-range');
    dubRange.type = 'range'; dubRange.min = '0'; dubRange.max = '100'; dubRange.value = '100';
    dubRange.addEventListener('input', () => { if (state.dubGain) state.dubGain.gain.value = Number(dubRange.value) / 100; });
    dub.append(dubRange); controls.append(dub);
    panel.append(controls);

    const actions = make('div', 'nox-ca-actions');
    actions.append(createButton('Скачать субтитры VTT', exportVtt, 'nox-ca-button nox-ca-export'));
    panel.append(actions);
    state.caption = make('div', 'nox-ca-caption');
    state.caption.hidden = true;
    state.caption.setAttribute('aria-live', 'polite');
    host.append(panel, state.caption);
    state.controls = panel;

    video.addEventListener('volumechange', () => {
      if (state.duckCount) {
        const expected = state.originalVolume * 0.18;
        if (Math.abs(video.volume - expected) > 0.025) state.originalVolume = Math.min(1, Math.max(0, video.volume / 0.18));
      } else state.originalVolume = video.volume;
    }, listen);
    video.addEventListener('seeked', () => {
      if (state.mode === 'off') return;
      clearTimeout(state.seekTimer);
      state.seekTimer = setTimeout(() => { if (state.mode !== 'off') restartAtSeek(); }, 220);
    }, listen);
    video.addEventListener('pause', () => {
      if (state.ws && state.ws.readyState === WebSocket.OPEN) state.ws.send(JSON.stringify({ type: 'KeepAlive' }));
      stopDubAudio();
    }, listen);
    video.addEventListener('play', () => { if (state.mode !== 'off' && (!state.ws || state.ws.readyState !== WebSocket.OPEN)) restartAtSeek(); }, listen);
    checkServices(state.status);
    if (selectedMode !== 'off') {
      state.mode = selectedMode;
      setPressed();
      start().catch(err => status(errorLabel(err)));
    }
  }

  function unmount() {
    const oldVideo = state.video;
    if (!oldVideo) return;
    stop();
    if (state.controller) state.controller.abort();
    [state.esTrack, state.ruTrack].forEach(track => {
      if (!track) return;
      track.mode = 'disabled';
      if (track.cues) Array.from(track.cues).forEach(cue => { try { track.removeCue(cue); } catch (_) {} });
    });
    if (state.controls) state.controls.remove();
    if (state.caption) state.caption.remove();
    delete oldVideo.dataset.noxCinemaAssist;
    state.video = null; state.host = null; state.controls = null; state.caption = null; state.status = null;
    state.controller = null; state.esTrack = null; state.ruTrack = null; state.pipeline = Promise.resolve();
  }

  async function checkServices(statusTarget) {
    try {
      const r = await fetch(apiUrl('/health'), { headers: authHeaders(), cache: 'no-store' });
      const j = await r.json();
      if (statusTarget && statusTarget.isConnected) statusTarget.textContent = r.ok && j.translation_ready ? 'Переводчик готов · ASR проверяется при запуске' : 'Локальный переводчик не запущен';
    } catch (_) { if (statusTarget && statusTarget.isConnected) statusTarget.textContent = 'Запустите локальный движок NOX Cinema'; }
  }

  function asrUrl() {
    const host = cfg.asrHost || location.hostname || '127.0.0.1';
    const port = cfg.asrPort || '8000';
    const defaultUrl = location.protocol === 'https:'
      ? new URL('/v1/listen', location.origin.replace(/^https:/, 'wss:')).href
      : 'ws://' + host + ':' + port + '/v1/listen';
    const url = new URL(cfg.asrWsUrl || defaultUrl, location.href);
    const defaults = {
      language: 'es', encoding: 'linear16', sample_rate: '16000', channels: '1',
      interim_results: 'true', endpointing: '500', utterance_end_ms: '1000'
    };
    Object.keys(defaults).forEach(key => {
      if (!url.searchParams.has(key)) url.searchParams.set(key, defaults[key]);
    });
    if (cfg.asrToken) url.searchParams.set('token', cfg.asrToken);
    return url.href;
  }

  function waitOpen(ws) {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error('ASR_CONNECTION_TIMEOUT')), 8000);
      ws.addEventListener('open', () => { clearTimeout(timer); resolve(); }, { once: true });
      ws.addEventListener('error', () => { clearTimeout(timer); reject(new Error('ASR_CONNECTION_FAILED')); }, { once: true });
    });
  }

  async function activate(mode) {
    if (!MODES.includes(mode)) return;
    if (state.caption) state.caption.hidden = true;
    if (mode === 'off') { stop(); state.mode = 'off'; setTrackModes(); setPressed(); status('Перевод выключен'); return; }
    if (state.mode !== mode) stopDubAudio();
    state.mode = mode; setPressed();
    try { await start(); }
    catch (err) { state.mode = 'off'; setTrackModes(); setPressed(); stop(); status(errorLabel(err)); }
  }

  function setPressed() {
    if (!state.controls) return;
    state.controls.querySelectorAll('[data-mode]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.mode === state.mode)));
  }

  function start() {
    if (state.startPromise) return state.startPromise;
    const pending = startNow();
    state.startPromise = pending;
    pending.then(() => { if (state.startPromise === pending) state.startPromise = null; }, () => { if (state.startPromise === pending) state.startPromise = null; });
    return pending;
  }

  async function startNow() {
    if (!state.video) throw new Error('NO_VIDEO_ELEMENT');
    if (state.ws && state.ws.readyState === WebSocket.OPEN && state.context) { setTrackModes(); return; }
    const video = state.video;
    const capture = video.captureStream ? video.captureStream() : (video.mozCaptureStream ? video.mozCaptureStream() : null);
    if (!capture) throw new Error('VIDEO_CAPTURE_UNSUPPORTED');
    if (!capture.getAudioTracks().length) {
      capture.getTracks().forEach(track => track.stop());
      throw new Error('PLAYER_AUDIO_NOT_CAPTURED');
    }
    const run = ++state.run;
    const ws = new WebSocket(asrUrl());
    ws.binaryType = 'arraybuffer';
    state.capture = capture;
    state.ws = ws;
    ws.addEventListener('message', event => { if (run === state.run) onAsrMessage(event.data, run); });
    ws.addEventListener('close', () => { if (run === state.run && state.mode !== 'off') status('Поток распознавания остановлен'); });
    let context = null;
    let worklet = null;
    try {
      await waitOpen(ws);
      if (run !== state.run) return;
      const Ctx = window.AudioContext || window.webkitAudioContext;
      if (!Ctx || !window.AudioWorkletNode) throw new Error('AUDIO_WORKLET_UNSUPPORTED');
      context = new Ctx();
      await context.resume();
      if (run !== state.run) return;
      const workletUrl = new URL('cinema_assist_audio_worklet.js', SCRIPT_URL).href;
      await context.audioWorklet.addModule(workletUrl);
      if (run !== state.run) return;
      const audioOnly = new MediaStream(capture.getAudioTracks());
      const source = context.createMediaStreamSource(audioOnly);
      worklet = new AudioWorkletNode(context, 'nox-cinema-pcm16', { numberOfInputs: 1, numberOfOutputs: 1, outputChannelCount: [1] });
      const silent = context.createGain(); silent.gain.value = 0;
      source.connect(worklet).connect(silent).connect(context.destination);
      state.context = context; state.worklet = worklet; state.capture = capture; state.silent = silent;
      state.dubGain = context.createGain(); state.dubGain.gain.value = 1; state.dubGain.connect(context.destination);
      state.audioSeconds = 0; state.map = []; state.finalSignatures.clear();
      worklet.port.onmessage = e => {
        if (run !== state.run || state.mode === 'off' || video.paused || !state.ws || state.ws.readyState !== WebSocket.OPEN) return;
        const buffer = e.data && e.data.buffer;
        if (!(buffer instanceof ArrayBuffer) || !buffer.byteLength) return;
        const frameSeconds = buffer.byteLength / 2 / 16000;
        const chunkContextTime = Number(e.data && e.data.contextTimeStart);
        const processingLag = Number.isFinite(chunkContextTime) && state.context ? Math.max(0, state.context.currentTime - chunkContextTime) : 0;
        const mediaS = Math.max(0, (Number(video.currentTime) || 0) - processingLag * Math.max(0.5, video.playbackRate || 1));
        state.map.push({ audioS: state.audioSeconds, mediaS });
        state.audioSeconds += frameSeconds;
        if (state.map.length > 6000) state.map.splice(0, 3000);
        state.ws.send(buffer);
      };
      if (!state.esTrack) state.esTrack = video.addTextTrack('captions', 'Español · NOX', 'es');
      if (!state.ruTrack) state.ruTrack = video.addTextTrack('captions', 'Русский · NOX', 'ru');
      state.esTrack.mode = 'hidden'; state.ruTrack.mode = 'hidden';
      setTrackModes();
      status('Слышу дорожку фильма · испанский');
    } catch (err) {
      if (worklet) { worklet.port.onmessage = null; try { worklet.disconnect(); } catch (_) {} }
      if (context) context.close().catch(() => {});
      capture.getTracks().forEach(track => track.stop());
      if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) ws.close();
      if (state.ws === ws) state.ws = null;
      if (state.capture === capture) state.capture = null;
      if (state.context === context) { state.context = null; state.worklet = null; state.silent = null; state.dubGain = null; }
      throw err;
    } finally {
      if (run !== state.run) {
        if (worklet) { worklet.port.onmessage = null; try { worklet.disconnect(); } catch (_) {} }
        if (context) context.close().catch(() => {});
        capture.getTracks().forEach(track => track.stop());
        if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) ws.close();
        if (state.ws === ws) state.ws = null;
        if (state.capture === capture) state.capture = null;
      }
    }
  }

  function setTrackModes() {
    if (state.esTrack) state.esTrack.mode = state.mode === 'es' ? 'showing' : state.mode === 'off' ? 'disabled' : 'hidden';
    if (state.ruTrack) state.ruTrack.mode = state.mode === 'ru' ? 'showing' : state.mode === 'off' ? 'disabled' : 'hidden';
    if (state.caption) state.caption.hidden = state.mode === 'off' || state.mode === 'dub';
  }

  function mapTime(audioS) {
    const points = state.map;
    if (!points.length || !Number.isFinite(audioS)) return Number(state.video.currentTime) || 0;
    let left = points[0], right = points[points.length - 1];
    for (let i = 1; i < points.length; i++) { if (points[i].audioS >= audioS) { left = points[i - 1]; right = points[i]; break; } }
    if (right.audioS === left.audioS) return left.mediaS;
    const ratio = Math.max(0, Math.min(1, (audioS - left.audioS) / (right.audioS - left.audioS)));
    return left.mediaS + (right.mediaS - left.mediaS) * ratio;
  }

  async function onAsrMessage(raw, run) {
    if (run !== state.run) return;
    let msg; try { msg = JSON.parse(raw); } catch (_) { return; }
    if (msg.type === 'error') { status('Ошибка распознавания: ' + safeText(msg.error)); return; }
    if (msg.type !== 'Results') return;
    const alt = msg.channel && msg.channel.alternatives && msg.channel.alternatives[0];
    const text = safeText(alt && alt.transcript);
    if (!text) return;
    const words = alt && Array.isArray(alt.words) ? alt.words : [];
    const firstWord = words.length ? words[0] : null;
    const lastWord = words.length ? words[words.length - 1] : null;
    const start = Number(firstWord && firstWord.start != null ? firstWord.start : msg.start) || 0;
    const fallbackDuration = Number(msg.duration) || Math.max(1.5, text.length / 12);
    const end = Number(lastWord && lastWord.end != null ? lastWord.end : start + fallbackDuration) || start + fallbackDuration;
    const speakerOf = word => word && word.speaker != null && Number.isFinite(Number(word.speaker)) ? Number(word.speaker) : null;
    const finalGroups = [];
    if (msg.is_final && words.length) {
      words.forEach(word => {
        const wordText = safeText(word.punctuated_word || word.word);
        if (!wordText) return;
        const wordSpeaker = speakerOf(word);
        let group = finalGroups[finalGroups.length - 1];
        if (!group || group.speaker !== wordSpeaker) {
          group = { text: [], start: Number(word.start) || start, end: Number(word.end) || start, speaker: wordSpeaker };
          finalGroups.push(group);
        }
        group.text.push(wordText);
        group.end = Number(word.end) || group.end;
      });
    }
    if (finalGroups.length === 1) finalGroups[0].text = [text];
    const cues = finalGroups.length
      ? finalGroups.map(group => ({ text: group.text.join(' '), start: mapTime(group.start), end: mapTime(group.end), language: 'es', speaker: group.speaker }))
      : [{ text, start: mapTime(start), end: mapTime(end), language: 'es', speaker: speakerOf(firstWord) }];
    if (!msg.is_final) { if (state.mode === 'es') showCaption(text); return; }
    cues.forEach(cue => {
      const signature = Math.round(cue.start * 10) + ':' + cue.text;
      if (state.finalSignatures.has(signature)) return;
      state.finalSignatures.add(signature);
      if (state.finalSignatures.size > 1000) state.finalSignatures.delete(state.finalSignatures.values().next().value);
      const nativeEs = addCue(cue, 'es');
      if (state.mode === 'es') { renderCue(cue, nativeEs); return; }
      if (state.mode === 'dub' && state.pipelinePending >= 6) {
        state.dubEpoch += 1;
        state.pipeline = Promise.resolve();
        state.pipelinePending = 0;
        status('Дубляж отстаёт — сбрасываю просроченную очередь');
      }
      cue.dubEpoch = state.dubEpoch;
      const epoch = cue.dubEpoch;
      state.pipelinePending += 1;
      state.pipeline = state.pipeline.then(() => translateCue(cue, run)).catch(err => status(errorLabel(err))).finally(() => {
        if (epoch === state.dubEpoch) state.pipelinePending = Math.max(0, state.pipelinePending - 1);
      });
    });
  }

  function addCue(cue, lang) {
    let native = false;
    if (lang === 'es') {
      try { state.esTrack.addCue(new VTTCue(Math.max(0, cue.start), Math.max(cue.start + 0.25, cue.end), cue.text)); native = true; } catch (_) {}
    } else {
      try { state.ruTrack.addCue(new VTTCue(Math.max(0, cue.start), Math.max(cue.start + 0.25, cue.end), cue.text)); native = true; } catch (_) {}
    }
    state.cues.push({ ...cue, language: lang });
    if (state.cues.length > 1200) state.cues.splice(0, 300);
    [state.esTrack, state.ruTrack].forEach(track => {
      if (!track || !track.cues) return;
      while (track.cues.length > 1200) { try { track.removeCue(track.cues[0]); } catch (_) { break; } }
    });
    return native;
  }

  async function translateCue(cue, run) {
    if (run !== state.run || state.mode === 'off' || state.mode === 'es') return;
    if (state.mode === 'dub' && (state.video.paused || cue.dubEpoch !== state.dubEpoch || cue.end < state.video.currentTime - 0.75)) return;
    status('Перевожу реплику…');
    try {
      const r = await fetch(apiUrl('/translate'), { method: 'POST', headers: authHeaders({ 'Content-Type': 'application/json' }), body: JSON.stringify({ text: cue.text, source: 'es', target: 'ru' }) });
      if (!r.ok) throw new Error('TRANSLATION_HTTP_' + r.status);
      const data = await r.json();
      const ru = safeText(data.translation);
      if (!ru || run !== state.run || state.mode === 'off' || state.mode === 'es') return;
      if (state.mode === 'dub' && (state.video.paused || cue.dubEpoch !== state.dubEpoch || cue.end < state.video.currentTime - 0.75)) return;
      const translated = { text: ru, start: cue.start, end: cue.end, language: 'ru', speaker: cue.speaker };
      const nativeRu = addCue(translated, 'ru');
      if (state.mode === 'ru') renderCue(translated, nativeRu);
      if (state.mode === 'dub') await speak(translated, cue.speaker, run, cue.dubEpoch);
      status(state.mode === 'dub' ? 'Русский дубляж · локально' : 'Русский перевод · локально');
    } catch (err) { if (run === state.run) status(errorLabel(err)); }
  }

  async function speak(cue, speaker, run, dubEpoch) {
    const profileId = state.profiles[speakerSlot(speaker)] || '';
    if (!profileId) throw new Error('VOICE_PROFILE_REQUIRED_OR_EXPIRED');
    const r = await fetch(apiUrl('/tts'), { method: 'POST', headers: authHeaders({ 'Content-Type': 'application/json' }), body: JSON.stringify({ text: cue.text, language: 'ru', profile_id: profileId }) });
    if (!r.ok) throw new Error(r.status === 409 ? 'VOICE_PROFILE_REQUIRED_OR_EXPIRED' : 'TTS_HTTP_' + r.status);
    if (run !== state.run || state.mode !== 'dub' || state.video.paused || dubEpoch !== state.dubEpoch || cue.end < state.video.currentTime - 0.75) return;
    if (!state.context || !state.dubGain) return;
    const audio = await state.context.decodeAudioData(await r.arrayBuffer());
    if (run !== state.run || state.mode !== 'dub' || state.video.paused || dubEpoch !== state.dubEpoch || cue.end < state.video.currentTime - 0.75) return;
    const source = state.context.createBufferSource();
    source.buffer = audio; source.connect(state.dubGain);
    const remaining = (cue.start - state.video.currentTime) / Math.max(0.5, state.video.playbackRate || 1);
    const when = state.context.currentTime + Math.max(0, remaining);
    let duckTimer = null;
    const duck = () => { state.dubTimers.delete(duckTimer); if (run !== state.run || state.video.paused || dubEpoch !== state.dubEpoch) return; source._noxDucked = true; state.duckCount += 1; applyDuck(); };
    const waitMs = Math.max(0, (when - state.context.currentTime) * 1000);
    duckTimer = setTimeout(duck, waitMs);
    state.dubTimers.add(duckTimer);
    state.dubSources.add(source);
    source.onended = () => {
      if (duckTimer) { clearTimeout(duckTimer); state.dubTimers.delete(duckTimer); }
      state.dubSources.delete(source);
      if (source._noxDucked) { source._noxDucked = false; state.duckCount = Math.max(0, state.duckCount - 1); }
      applyDuck();
    };
    source.start(when);
  }

  function stopDubAudio() {
    ++state.dubEpoch;
    state.dubTimers.forEach(timer => clearTimeout(timer));
    state.dubTimers.clear();
    state.dubSources.forEach(source => { try { source.stop(); } catch (_) {} });
    state.dubSources.clear();
    state.duckCount = 0;
    applyDuck();
  }

  function applyDuck() {
    if (state.video) state.video.volume = state.originalVolume * (state.duckCount ? 0.18 : 1);
  }

  function renderCue(cue, nativeTrack) {
    if (nativeTrack && state.caption) state.caption.hidden = true;
    else showCaption(cue.text);
    if (state.controls) state.controls.dataset.currentCue = cue.language;
  }

  function showCaption(text) {
    if (!state.caption || state.mode === 'dub' || state.mode === 'off') return;
    state.caption.textContent = text;
    state.caption.hidden = false;
  }

  function exportVtt() {
    const rows = state.cues.filter(c => c.language === (state.mode === 'es' ? 'es' : 'ru'));
    if (!rows.length) { status('Сначала включите субтитры'); return; }
    const stamp = n => { const ms = Math.max(0, Math.round(n * 1000)); const h = String(Math.floor(ms / 3600000)).padStart(2, '0'); const m = String(Math.floor(ms / 60000) % 60).padStart(2, '0'); const s = String(Math.floor(ms / 1000) % 60).padStart(2, '0'); const x = String(ms % 1000).padStart(3, '0'); return h + ':' + m + ':' + s + '.' + x; };
    const body = 'WEBVTT\n\n' + rows.map((c,i) => (i + 1) + '\n' + stamp(c.start) + ' --> ' + stamp(Math.max(c.start + 0.25, c.end)) + '\n' + c.text + '\n').join('\n');
    const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([body], { type: 'text/vtt;charset=utf-8' })); a.download = 'nox-cinema-' + (state.mode === 'es' ? 'es' : 'ru') + '.vtt'; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  async function uploadVoice(file) {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.wav') || file.size > 20 * 1024 * 1024) { status('Нужен WAV-файл до 20 МБ'); return; }
    const form = new FormData(); form.append('file', file);
    try {
      const r = await fetch(apiUrl('/voice-profiles'), { method: 'POST', headers: authHeaders(), body: form });
      if (!r.ok) throw new Error('VOICE_PROFILE_HTTP_' + r.status);
      const data = await r.json(); state.profiles[state.profileSpeaker] = data.profile_id || ''; status('Профиль говорящего ' + (Number(state.profileSpeaker) + 1) + ' хранится только в памяти сеанса');
    } catch (err) { status(errorLabel(err)); }
  }

  async function showPhoneInstructions() {
    const localOnly = /^(localhost|127\.0\.0\.1|\[::1\])$/i.test(location.hostname);
    if (localOnly || location.protocol !== 'https:') {
      status('Для телефона нужен доступный в LAN адрес NOX по HTTPS; localhost и обычный HTTP не подходят');
      return;
    }
    const message = 'Откройте тот же NOX-плеер на телефоне и выберите наушники; звук ПК не передаётся';
    if (navigator.clipboard && window.isSecureContext) {
      try { await navigator.clipboard.writeText(location.href); status('Адрес плеера скопирован. ' + message); }
      catch (_) { status(message); }
    } else status(message);
  }

  function stop() {
    ++state.run;
    state.startPromise = null;
    state.pipelinePending = 0;
    clearTimeout(state.seekTimer);
    state.seekTimer = null;
    state.pipeline = Promise.resolve();
    stopDubAudio();
    if (state.worklet) { state.worklet.port.onmessage = null; try { state.worklet.disconnect(); } catch (_) {} }
    if (state.silent) try { state.silent.disconnect(); } catch (_) {}
    if (state.capture) state.capture.getTracks().forEach(t => t.stop());
    if (state.ws && (state.ws.readyState === WebSocket.OPEN || state.ws.readyState === WebSocket.CONNECTING)) {
      if (state.ws.readyState === WebSocket.OPEN) { try { state.ws.send(JSON.stringify({ type: 'CloseStream' })); } catch (_) {} }
      state.ws.close();
    }
    if (state.context) state.context.close().catch(() => {});
    state.worklet = null; state.capture = null; state.silent = null; state.context = null; state.ws = null; state.duckGain = null;
    state.duckCount = 0; applyDuck();
    if (state.caption) state.caption.hidden = true;
  }

  function clearTracks() {
    [state.esTrack, state.ruTrack].forEach(track => {
      if (!track || !track.cues) return;
      Array.from(track.cues).forEach(cue => { try { track.removeCue(cue); } catch (_) {} });
    });
    state.cues.length = 0;
    state.finalSignatures.clear();
  }

  function restartAtSeek() {
    const mode = state.mode;
    stop(); clearTracks(); state.mode = mode;
    state.seekTimer = setTimeout(() => {
      state.seekTimer = null;
      if (state.mode !== 'off') start().catch(e => status(errorLabel(e)));
    }, 150);
  }

  function errorLabel(err) {
    const code = String(err && err.message || err);
    const labels = { VIDEO_CAPTURE_UNSUPPORTED: 'Этот браузер не даёт захватить звук плеера', PLAYER_AUDIO_NOT_CAPTURED: 'Плеер не отдаёт звук для перевода', AUDIO_WORKLET_UNSUPPORTED: 'Нужен современный браузер с AudioWorklet', NO_VIDEO_ELEMENT: 'В кинотеатре не найден HTML-видеоплеер', ASR_CONNECTION_FAILED: 'Не запущен локальный ASR на порту 8000', ASR_CONNECTION_TIMEOUT: 'Не отвечает локальный ASR', TRANSLATION_HTTP_503: 'Локальная модель перевода не установлена', TTS_HTTP_503: 'Локальная модель озвучки не установлена', VOICE_PROFILE_REQUIRED_OR_EXPIRED: 'Загрузите WAV-образец для выбранного говорящего; профиль хранится 20 минут' };
    return labels[code] || code.replace(/_/g, ' ');
  }

  function chooseVideo() {
    const all = Array.from(document.querySelectorAll('video'));
    if (!all.length) return null;
    const visible = all.filter(video => {
      const rect = video.getBoundingClientRect();
      const style = window.getComputedStyle(video);
      return rect.width > 32 && rect.height > 32 && style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity || 1) > 0;
    });
    const candidates = visible.length ? visible : all;
    const explicit = candidates.find(video => video.matches('[data-nox-cinema-player],[data-cinema-player]') || video.closest('[data-cinema-player]'));
    if (explicit) return explicit;
    if (state.video && state.video.isConnected) {
      const current = state.video.getBoundingClientRect();
      const style = window.getComputedStyle(state.video);
      if (current.width > 32 && current.height > 32 && style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity || 1) > 0) return state.video;
    }
    const playing = candidates.filter(video => !video.paused && !video.ended);
    const pool = playing.length ? playing : candidates;
    return pool.sort((a, b) => {
      const ar = a.getBoundingClientRect(), br = b.getBoundingClientRect();
      return (br.width * br.height) - (ar.width * ar.height);
    })[0] || null;
  }

  function scan() {
    const selected = chooseVideo();
    if (selected) mount(selected);
    else if (state.video && !state.video.isConnected) unmount();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', scan, { once: true }); else scan();
  new MutationObserver(scan).observe(document.documentElement, { childList: true, subtree: true });
})();
