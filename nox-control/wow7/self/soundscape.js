/* soundscape.js - генеративный ambient NOX на Web Audio. Без зависимостей и CDN. Браузер и Node (для тестов, с подменой ctx).
 * API:  const s = NoxSoundscape.create({ctx?, storage?, seed?});  await s.start();  s.setMood({...});  s.stop();
 *   setMood(json): tonic("D"|MIDI), mode(major|minor|dorian|lydian|phrygian|pentatonic), bpm 40-120, density 0..1,
 *                  brightness 0..1, warmth 0..1 (тембр: 0 - пила/резко, 1 - треугольник/мягко), intensity 0..1, quiet bool;
 *                  либо PAD {p,a,d} (-1..1) и/или music{bpm,mode,intensity} из EMO/mood_ui.py - всё нормализуется normalizeMood().
 *   composeScene({name?,mood,seed?}) -> сцена (воспроизводима по seed); loadScene(scene); addFavorite(scene, why); listFavorites(); removeFavorite(id)
 *   promptFromMood(mood) -> текст для MusicGen/Stable Audio Open (ПК по запросу); fetchGenerated(url, mood, seconds) -> слой поверх.
 *   getState() -> текущие параметры (для журнала/«почему играет так»).
 * Звук: пэд (2 детюнёных осциллятора x 4 голоса, плавная смена аккордов), дрон, воздух (фильтрованный шум), редкая мелодия
 *       в гамме с эхом, мягкий пульс при высокой интенсивности; реверберация - сгенерированный импульс (без файлов).
 * Тихие часы (quiet=true): без пульса и мелодии, громкость <= 0.35. Автозапуск звука браузер блокирует до жеста - start() вызывать из клика. */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.NoxSoundscape = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  var NOTE = { C: 0, "C#": 1, Db: 1, D: 2, "D#": 3, Eb: 3, E: 4, F: 5, "F#": 6, Gb: 6, G: 7, "G#": 8, Ab: 8, A: 9, "A#": 10, Bb: 10, B: 11 };
  var NOTE_NAMES_RU = ["до", "до-диез", "ре", "ми-бемоль", "ми", "фа", "фа-диез", "соль", "ля-бемоль", "ля", "си-бемоль", "си"];
  var MODES = {
    major: [0, 2, 4, 5, 7, 9, 11], minor: [0, 2, 3, 5, 7, 8, 10], dorian: [0, 2, 3, 5, 7, 9, 10],
    lydian: [0, 2, 4, 6, 7, 9, 11], phrygian: [0, 1, 3, 5, 7, 8, 10], pentatonic: [0, 2, 4, 7, 9]
  };
  var MODE_RU = { major: "мажор", minor: "минор", dorian: "дорийский лад", lydian: "лидийский лад", phrygian: "фригийский лад", pentatonic: "пентатоника" };

  function clamp(x, lo, hi) { x = +x; if (!isFinite(x)) return lo; return x < lo ? lo : x > hi ? hi : x; }
  function mulberry32(a) {
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      var t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  function midiToHz(m) { return 440 * Math.pow(2, (m - 69) / 12); }

  function normalizeMood(m) {
    m = m || {};
    var music = m.music || {};
    var p = m.p, a = m.a, d = m.d;
    if (m.pad && typeof m.pad === "object") { p = m.pad.p; a = m.pad.a; d = m.pad.d; }
    var hasPAD = isFinite(p) || isFinite(a);
    p = clamp(isFinite(p) ? p : 0, -1, 1); a = clamp(isFinite(a) ? a : 0, -1, 1); d = clamp(isFinite(d) ? d : 0, -1, 1);
    var mode = m.mode || music.mode || (hasPAD ? (p >= 0 ? (a > 0.4 ? "lydian" : "major") : (a > 0.3 ? "phrygian" : "minor")) : "minor");
    if (!MODES[mode]) mode = "minor";
    var tonic = m.tonic;
    if (typeof tonic === "string") tonic = NOTE.hasOwnProperty(tonic) ? NOTE[tonic] : 2;
    else if (isFinite(tonic)) tonic = ((Math.round(tonic) % 12) + 12) % 12;
    else tonic = hasPAD ? [2, 7, 9, 4, 0][Math.floor((p + 1) * 2.49)] : 2;
    var bpm = m.bpm != null ? m.bpm : music.bpm != null ? music.bpm : 52 + 40 * (a + 1) / 2;
    var intensity = m.intensity != null ? m.intensity : music.intensity != null ? music.intensity : 0.5 + 0.5 * a;
    return {
      tonic: tonic, mode: mode, bpm: clamp(bpm, 40, 120),
      density: clamp(m.density != null ? m.density : 0.25 + 0.4 * (a + 1) / 2, 0, 1),
      brightness: clamp(m.brightness != null ? m.brightness : 0.45 + 0.3 * p, 0, 1),
      warmth: clamp(m.warmth != null ? m.warmth : 0.6 - 0.2 * a + 0.2 * d, 0, 1),
      intensity: clamp(intensity, 0, 1), quiet: !!m.quiet
    };
  }

  function scaleMidi(mood, octaveBase, count) {
    var iv = MODES[mood.mode], out = [];
    for (var i = 0; i < count; i++) out.push(octaveBase + mood.tonic + iv[i % iv.length] + 12 * Math.floor(i / iv.length));
    return out;
  }

  /* аккорд из ступеней: триада (0,2,4) от ступени deg в гамме, плюс 7-я/9-я по яркости */
  function chordFor(mood, deg, rng) {
    var iv = MODES[mood.mode], n = iv.length, notes = [];
    var steps = n === 5 ? [0, 1, 2, 3] : [0, 2, 4, mood.brightness > 0.55 ? 6 : 1 + n];
    for (var i = 0; i < steps.length; i++) {
      var s = deg + steps[i];
      notes.push(48 + mood.tonic + iv[s % n] + 12 * Math.floor(s / n));
    }
    return notes;
  }

  function sceneName(mood, rng) {
    var time = mood.quiet ? "Ночной" : mood.intensity > 0.7 ? "Яркий" : mood.intensity < 0.35 ? "Тихий" : "Ровный";
    var nouns = mood.brightness > 0.6 ? ["рассвет", "ветер", "свет"] : mood.brightness < 0.4 ? ["туман", "прилив", "сумрак"] : ["дрейф", "горизонт", "поток"];
    return time + " " + nouns[Math.floor(rng() * nouns.length)] + ", " + NOTE_NAMES_RU[mood.tonic] + " " + MODE_RU[mood.mode];
  }

  function promptFromMood(mood) {
    mood = normalizeMood(mood);
    var feel = mood.intensity > 0.7 ? "energetic, driving" : mood.intensity < 0.35 ? "calm, spacious, slow" : "steady, flowing";
    var tone = mood.brightness > 0.6 ? "bright, airy" : mood.brightness < 0.4 ? "dark, deep" : "balanced";
    var tex = mood.warmth > 0.6 ? "warm analog pads" : "crisp glassy synths";
    return "instrumental ambient, " + feel + ", " + tone + ", " + tex + ", " + MODE_RU[mood.mode] + " feel in " +
      ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"][mood.tonic] + ", " + Math.round(mood.bpm) + " bpm, no vocals, seamless loop";
  }

  function create(opts) {
    opts = opts || {};
    var ctx = opts.ctx || null, started = false, mood = normalizeMood(opts.mood), seed = opts.seed != null ? opts.seed : (Date.now() & 0xffffff);
    var rng = mulberry32(seed), nodes = {}, timer = null, nextStep = 0, stepIdx = 0, chordIdx = 0, volume = 0.6, voices = [], genLayer = null;
    var storage = opts.storage || (typeof localStorage !== "undefined" ? localStorage : null), FAV_KEY = "nox.soundscape.favs";
    var logger = opts.onChange || function () {};

    function T(param, v, tc) { var t = ctx.currentTime; if (param.setTargetAtTime) param.setTargetAtTime(v, t, tc || 1.5); else param.value = v; }

    function makeImpulse(sec, decay) {
      var len = Math.floor(ctx.sampleRate * sec), buf = ctx.createBuffer(2, len, ctx.sampleRate), r = mulberry32(12345);
      for (var c = 0; c < 2; c++) { var ch = buf.getChannelData(c); for (var i = 0; i < len; i++) ch[i] = (r() * 2 - 1) * Math.pow(1 - i / len, decay); }
      return buf;
    }
    function makeNoise(sec) {
      var len = Math.floor(ctx.sampleRate * sec), buf = ctx.createBuffer(1, len, ctx.sampleRate), ch = buf.getChannelData(0), r = mulberry32(777), b0 = 0, b1 = 0, b2 = 0;
      for (var i = 0; i < len; i++) { var w = r() * 2 - 1; b0 = 0.99765 * b0 + w * 0.099046; b1 = 0.963 * b1 + w * 0.2965164; b2 = 0.57 * b2 + w * 1.0526913; ch[i] = (b0 + b1 + b2 + w * 0.1848) * 0.11; }
      return buf;
    }

    function build() {
      var master = ctx.createGain(); master.gain.value = 0;
      var comp = ctx.createDynamicsCompressor(); comp.threshold.value = -24; comp.ratio.value = 3;
      master.connect(comp); comp.connect(ctx.destination);
      var dry = ctx.createGain(); dry.gain.value = 0.75; dry.connect(master);
      var rev = ctx.createConvolver(); rev.buffer = makeImpulse(4.5, 2.6);
      var revSend = ctx.createGain(); revSend.gain.value = 0.35; revSend.connect(rev); rev.connect(master);
      var padF = ctx.createBiquadFilter(); padF.type = "lowpass"; padF.Q.value = 0.7; padF.frequency.value = 900;
      var padG = ctx.createGain(); padG.gain.value = 0.18; padF.connect(padG); padG.connect(dry); padG.connect(revSend);
      var lfo = ctx.createOscillator(), lfoG = ctx.createGain(); lfo.frequency.value = 0.07; lfoG.gain.value = 250; lfo.connect(lfoG); lfoG.connect(padF.frequency); lfo.start();
      var drone = ctx.createOscillator(), droneG = ctx.createGain(); drone.type = "sine"; droneG.gain.value = 0.0; drone.connect(droneG); droneG.connect(dry); drone.start();
      var noise = ctx.createBufferSource(); noise.buffer = makeNoise(6); noise.loop = true;
      var noiseF = ctx.createBiquadFilter(); noiseF.type = "bandpass"; noiseF.frequency.value = 1200; noiseF.Q.value = 0.5;
      var noiseG = ctx.createGain(); noiseG.gain.value = 0; noise.connect(noiseF); noiseF.connect(noiseG); noiseG.connect(dry); noiseG.connect(revSend); noise.start();
      var delay = ctx.createDelay(2.0), fb = ctx.createGain(), mel = ctx.createGain(); fb.gain.value = 0.38; mel.gain.value = 0.5;
      delay.delayTime.value = 0.5; mel.connect(dry); mel.connect(delay); delay.connect(fb); fb.connect(delay); delay.connect(revSend);
      for (var i = 0; i < 4; i++) {
        var o1 = ctx.createOscillator(), o2 = ctx.createOscillator(), g = ctx.createGain(); g.gain.value = 0.25;
        o1.detune.value = -7; o2.detune.value = 7; o1.connect(g); o2.connect(g); g.connect(padF); o1.start(); o2.start();
        voices.push({ o1: o1, o2: o2, g: g });
      }
      nodes = { master: master, dry: dry, revSend: revSend, padF: padF, padG: padG, drone: drone, droneG: droneG, noiseG: noiseG, noiseF: noiseF, delay: delay, mel: mel, lfo: lfo, noise: noise, comp: comp };
    }

    function applyMood(init) {
      var m = mood, tc = init ? 0.05 : 2.5, ceil = m.quiet ? 0.35 : 1;
      T(nodes.master.gain, Math.min(volume, ceil) * (0.35 + 0.65 * m.intensity), 2.0);
      T(nodes.padF.frequency, 350 + 2600 * m.brightness * (m.quiet ? 0.6 : 1), tc);
      T(nodes.padG.gain, 0.12 + 0.12 * m.intensity, tc);
      var chord = chordFor(m, [0, 3, 4, 5, 2, 6][chordIdx % 6] % MODES[m.mode].length, rng);
      voices.forEach(function (v, i) {
        v.o1.type = v.o2.type = m.warmth > 0.5 ? "triangle" : "sawtooth";
        var f = midiToHz(chord[i % chord.length] + (i === 3 ? 12 : 0));
        T(v.o1.frequency, f, init ? 0.05 : 1.2); T(v.o2.frequency, f, init ? 0.05 : 1.2);
        T(v.g.gain, m.warmth > 0.5 ? 0.25 : 0.12, tc);
      });
      T(nodes.drone.frequency, midiToHz(24 + m.tonic + 12), tc);
      T(nodes.droneG.gain, 0.10 + 0.1 * m.warmth, tc);
      T(nodes.noiseG.gain, (0.01 + 0.07 * m.density) * (m.quiet ? 0.7 : 1), tc);
      T(nodes.noiseF.frequency, 500 + 3500 * m.brightness, tc);
      T(nodes.delay.delayTime, clamp(60 / m.bpm * 0.75, 0.2, 1.2), 0.5);
      T(nodes.lfo.frequency, 0.03 + 0.1 * (m.bpm - 40) / 80, tc);
    }

    function note(time, midi, vel, dur) {
      var o = ctx.createOscillator(), g = ctx.createGain(); o.type = mood.warmth > 0.5 ? "sine" : "triangle"; o.frequency.value = midiToHz(midi);
      g.gain.setValueAtTime(0, time); g.gain.linearRampToValueAtTime(vel, time + 0.03); g.gain.exponentialRampToValueAtTime(0.0001, time + dur);
      o.connect(g); g.connect(nodes.mel); o.start(time); o.stop(time + dur + 0.05);
    }
    function pulse(time) {
      var o = ctx.createOscillator(), g = ctx.createGain(); o.type = "sine";
      o.frequency.setValueAtTime(70, time); o.frequency.exponentialRampToValueAtTime(38, time + 0.25);
      g.gain.setValueAtTime(0.0001, time); g.gain.linearRampToValueAtTime(0.28 * mood.intensity, time + 0.01); g.gain.exponentialRampToValueAtTime(0.0001, time + 0.45);
      o.connect(g); g.connect(nodes.dry); o.start(time); o.stop(time + 0.5);
    }

    /* один шаг сетки (восьмая); вызывается планировщиком; публично - для тестов. -> {melody:bool, pulse:bool, chord:bool} */
    function step(time) {
      var res = { melody: false, pulse: false, chord: false };
      var perBar = 8;
      if (stepIdx % (perBar * 4) === 0 && stepIdx > 0) { chordIdx++; applyMood(false); res.chord = true; }
      if (!mood.quiet) {
        if (stepIdx % 4 === 0 && mood.intensity > 0.6) { pulse(time); res.pulse = true; }
        if (rng() < mood.density * 0.35) {
          var sc = scaleMidi(mood, 60, 14), idx = Math.floor(rng() * sc.length);
          note(time, sc[idx], 0.05 + 0.09 * mood.brightness, 1.2 + 2.5 * (1 - mood.density));
          res.melody = true;
        }
      }
      stepIdx++;
      return res;
    }
    function scheduler() {
      var dur = 60 / mood.bpm / 2;
      while (nextStep < ctx.currentTime + 0.5) { step(nextStep); nextStep += dur; }
    }

    var api = {
      normalizeMood: normalizeMood, promptFromMood: promptFromMood,
      start: function () {
        if (started) return Promise.resolve(api.getState());
        if (!ctx) { var AC = (typeof AudioContext !== "undefined" && AudioContext) || (typeof webkitAudioContext !== "undefined" && webkitAudioContext); if (!AC) return Promise.reject(new Error("Web Audio недоступен")); ctx = new AC(); }
        var go = function () { build(); applyMood(true); started = true; nextStep = ctx.currentTime + 0.1; timer = setInterval(scheduler, 100); return api.getState(); };
        return Promise.resolve(ctx.state === "suspended" && ctx.resume ? ctx.resume() : null).then(go);
      },
      stop: function () {
        if (!started) return;
        T(nodes.master.gain, 0, 0.4); clearInterval(timer); timer = null; started = false;
        var c = ctx, v = voices, n = nodes;
        setTimeout(function () { try { v.forEach(function (x) { x.o1.stop(); x.o2.stop(); }); n.lfo.stop(); n.drone.stop(); n.noise.stop(); } catch (e) {} }, 1500);
        voices = []; nodes = {};
      },
      setMood: function (json) {
        var prev = mood; mood = normalizeMood(typeof json === "string" ? JSON.parse(json) : json);
        if (started) applyMood(false);
        logger({ from: prev, to: mood });
        return mood;
      },
      setVolume: function (v) { volume = clamp(v, 0, 1); if (started) applyMood(false); },
      getState: function () { return { started: started, mood: mood, seed: seed, chordIdx: chordIdx, stepIdx: stepIdx, volume: volume, generated: !!genLayer }; },
      step: step,
      composeScene: function (o) {
        o = o || {}; var m = normalizeMood(o.mood || mood), s = o.seed != null ? o.seed : (Math.floor(Math.random() * 0xffffff));
        return { v: 1, id: "sc-" + s.toString(36) + "-" + Math.round(m.bpm), name: o.name || sceneName(m, mulberry32(s)), seed: s, mood: m, created: Date.now() };
      },
      loadScene: function (sc) { seed = sc.seed; rng = mulberry32(seed); stepIdx = 0; chordIdx = 0; return api.setMood(sc.mood); },
      listFavorites: function () { try { return JSON.parse(storage.getItem(FAV_KEY) || "[]"); } catch (e) { return []; } },
      addFavorite: function (sc, why) {
        var list = api.listFavorites().filter(function (x) { return x.scene.id !== sc.id; });
        list.push({ scene: sc, why: String(why || ""), at: Date.now() }); if (storage) storage.setItem(FAV_KEY, JSON.stringify(list)); return list.length;
      },
      removeFavorite: function (id) { var list = api.listFavorites().filter(function (x) { return x.scene.id !== id; }); if (storage) storage.setItem(FAV_KEY, JSON.stringify(list)); return list.length; },
      /* опционально: аудио, сгенерированное на ПК (MusicGen / Stable Audio Open) по запросу; сервер принимает {prompt, seconds}, отдаёт wav */
      fetchGenerated: function (url, m, seconds) {
        var body = JSON.stringify({ prompt: promptFromMood(m || mood), seconds: seconds || 20 });
        return fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: body })
          .then(function (r) { if (!r.ok) throw new Error("генерация: HTTP " + r.status); return r.arrayBuffer(); })
          .then(function (ab) { return ctx.decodeAudioData(ab); })
          .then(function (buf) {
            if (genLayer) { try { genLayer.stop(); } catch (e) {} }
            var s = ctx.createBufferSource(), g = ctx.createGain(); s.buffer = buf; s.loop = true; g.gain.value = 0.0; s.connect(g); g.connect(nodes.dry); s.start();
            T(g.gain, 0.5, 3); genLayer = s; return buf.duration;
          });
      }
    };
    return api;
  }

  return { create: create, normalizeMood: normalizeMood, promptFromMood: promptFromMood, mulberry32: mulberry32, scaleMidi: scaleMidi, chordFor: chordFor, midiToHz: midiToHz, MODES: MODES };
});
