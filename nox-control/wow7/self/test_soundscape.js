// node test_soundscape.js  - тесты чистой логики и графа Web Audio на подменённом контексте
const assert = require("assert");
const S = require("./soundscape.js");
function mockCtx() {
  const log = { osc: 0, gain: 0, started: 0, targets: [] };
  const param = (name) => ({ value: 0, setTargetAtTime(v) { log.targets.push([name, v]); this.value = v; }, setValueAtTime() {}, linearRampToValueAtTime() {}, exponentialRampToValueAtTime() {} });
  const node = (kind) => ({ kind, connect() {}, start() { log.started++; }, stop() {}, gain: param("gain"), frequency: param("freq"), detune: param("det"), delayTime: param("dt"), Q: param("Q"), threshold: {}, ratio: {}, buffer: null, loop: false, type: "" });
  const c = { currentTime: 0, sampleRate: 8000, state: "running", destination: {},
    createGain: () => { log.gain++; return node("gain"); }, createOscillator: () => { log.osc++; return node("osc"); },
    createBiquadFilter: () => node("bq"), createConvolver: () => node("conv"), createDynamicsCompressor: () => node("comp"),
    createDelay: () => node("delay"), createBufferSource: () => node("src"),
    createBuffer: (ch, len) => { const d = Array.from({ length: ch }, () => new Float32Array(len)); return { getChannelData: (i) => d[i] }; } };
  return { c, log };
}
const mem = () => { const m = {}; return { getItem: (k) => (k in m ? m[k] : null), setItem: (k, v) => { m[k] = String(v); } }; };

// 1 нормализация
let m = S.normalizeMood({ bpm: 999, density: -3, tonic: "Eb", mode: "nope" });
assert.strictEqual(m.bpm, 120); assert.strictEqual(m.density, 0); assert.strictEqual(m.tonic, 3); assert.strictEqual(m.mode, "minor");
m = S.normalizeMood({ p: 0.8, a: 0.1 }); assert.ok(["major", "lydian"].includes(m.mode));
m = S.normalizeMood({ music: { bpm: 70, mode: "major", intensity: 0.9 } }); assert.strictEqual(m.bpm, 70); assert.strictEqual(m.mode, "major"); assert.strictEqual(m.intensity, 0.9);
assert.deepStrictEqual(S.normalizeMood({ p: -0.9, a: -0.5 }).mode, "minor");
// 2 музыкальная теория
assert.strictEqual(Math.round(S.midiToHz(69)), 440);
const sc = S.scaleMidi({ tonic: 2, mode: "minor" }, 60, 8); assert.deepStrictEqual(sc.slice(0, 3), [62, 64, 65]); assert.strictEqual(sc[7], 74);
const ch = S.chordFor({ tonic: 0, mode: "major", brightness: 0.8 }, 0); assert.deepStrictEqual(ch.slice(0, 3), [48, 52, 55]);
// 3 детерминизм
const a = S.mulberry32(5), b = S.mulberry32(5); for (let i = 0; i < 20; i++) assert.strictEqual(a(), b());
// 4 граф и шаги
(async () => {
  const { c, log } = mockCtx(); const s = S.create({ ctx: c, seed: 42, storage: mem(), mood: { intensity: 0.9, density: 1, quiet: false } });
  await s.start(); assert.ok(log.osc >= 10); assert.ok(log.started > 8);
  let mel = 0, pul = 0, chords = 0; for (let i = 0; i < 200; i++) { const r = s.step(i * 0.3); mel += r.melody; pul += r.pulse; chords += r.chord; }
  assert.ok(mel > 20, "мелодия играет при density=1"); assert.ok(pul > 30, "пульс при intensity>0.6"); assert.ok(chords >= 5, "аккорды меняются");
  // тихие часы: нет мелодии и пульса, громкость <= 0.35
  s.setMood({ quiet: true, density: 1, intensity: 1 }); mel = 0; pul = 0; for (let i = 0; i < 100; i++) { const r = s.step(0); mel += r.melody; pul += r.pulse; }
  assert.strictEqual(mel + pul, 0, "quiet = тишина мелодии/пульса");
  const masterT = log.targets.filter((t) => t[0] === "gain").pop(); assert.ok(masterT[1] <= 0.35 + 1e-9, "громкость в тишину <= 0.35: " + masterT[1]);
  // JSON-строка
  assert.strictEqual(s.setMood('{"mode":"dorian","bpm":60}').mode, "dorian");
  // сцены: воспроизводимость и избранное
  const scn = s.composeScene({ mood: { p: 0.5, a: 0.2 }, seed: 7 }); const scn2 = s.composeScene({ mood: { p: 0.5, a: 0.2 }, seed: 7 });
  assert.strictEqual(scn.name, scn2.name); assert.strictEqual(scn.id, scn2.id); assert.ok(/[а-я]/i.test(scn.name));
  s.addFavorite(scn, "нравится светлый пэд"); s.addFavorite(scn, "повтор"); assert.strictEqual(s.listFavorites().length, 1); assert.strictEqual(s.listFavorites()[0].why, "повтор");
  s.loadScene(scn); assert.strictEqual(s.getState().seed, 7); assert.strictEqual(s.removeFavorite(scn.id), 0);
  // промпт для MusicGen
  const pr = S.promptFromMood({ tonic: "A", mode: "minor", bpm: 55, intensity: 0.2, brightness: 0.2 }); assert.ok(/calm/.test(pr) && /55 bpm/.test(pr) && /no vocals/.test(pr));
  s.stop();
  console.log("soundscape.js: все проверки OK");
})().catch((e) => { console.error(e); process.exit(1); });
