# NOX V16 · Voice Lab / MAESTRO / Calls

**Isolated candidate; not installed into NOX runtime, not a verified voice system.**

## What is physically included
- `voice-lab.js`: real consent-triggered browser microphone recording through HTTPS-secure `getUserMedia` and `MediaRecorder`; audio Blob passed to approved host callback `onAudio`, never uploaded by this UI module.
- Mode switch: RU↔ES translator, CEFR A1–C2 Spanish tutor, and call dial panel.
- Device mic permission and STOP, 30-second/16 MiB cap, stop when tab goes hidden, safe explicit permissions.
- Selection restricted to host-declared `installed:true` voice IDs.
- Calls require provider ready + displayed price + number/purpose + explicit consent; requests still require native host allowlist/validation and provider.
- `voice-lab.css`: responsive obsidian glass, accessible focus and Reduced Motion. Only secondary screens, not HOME D02.

## Native host contract — MUST be implemented by owner 2 + integrator 6
```js
const widget = NoxVoiceLab.mount(document.querySelector('#voiceLab'), {
  // Host applies authenticated permissions and allowlist for every operation:
  dispatch: (action, args) => trustedHost.dispatch(action, args),
  // Host takes Blob (local only), validates MIME/size/duration, streams to approved local ASR:
  onAudio: ({audio,mode,direction,level,voiceId}) =>
    trustedHost.submitAudio({audio,mode,direction,level,voiceId})
});
widget.setVoices([{id:'es-available-voice-id',name:'Installed Spanish voice',installed:true}]);
widget.setCallProvider({ready:false});
widget.setResponse({status:'Ready',text:''});
```

Allowed action requests: `nox.translate.text`, `nox.maestro.text`, `nox.voice.speak`, `nox.voice.stop`, `nox.calls.dial.request`.
They are client-side proposals, **NOT existing host handlers**. Do not blindly forward them to Windows commands, Ollama or SIP. Host must authorize origin, session, consent, permissions and backpressure. Call permission, destination, price and disclosure must be rechecked natively.

## Existing shared engine to reuse; no second chat backend
- ASR candidate: Qwen3-ASR 0.6B, user-authorized/downloaded local weights.
- Translation / teacher dialog via **existing** Ollama Qwen3 model and one chat history system.
- TTS candidate: Qwen3-TTS 0.6B voices actually installed, separate license checks.
- Optional word aligner for practice; word timestamps are NOT a reliable pronunciation scoring algorithm.
- Existing GPU training stays available for authorized future teaching LoRA, but teacher UX uses prompt/RAG/profile initially.
- SIP/PSTN calling needs a user-connected provider. Recording off by default.

## Acceptance gates
1. Integrator #6 binds exact source tree and shared host bridge (no duplicate renderer/database/LLM), final build only after #1–#5 component-ready.
2. Owner #2 proves microphone capture, RU/ES ASR, TTS, STOP, one real translated utterance, one tutor response, correct output-device selection.
3. Owner #3 pins/downloads actual ASR/TTS and LLM weights and proves local operation; do not treat model-card URLs as installed weights.
4. Owner #7 validates secure-context/permissions, sensitive microphone indicator, short-lived audio, failure/reconnect/STOP and same-SHA Windows QA.
5. Calls tested only when a permitted SIP provider is configured and separately consented; otherwise the button must be clearly unavailable.

Models are sourced from their official publishers; exact model revisions/licenses/VRAM must be pinned for production. A successful source PR is not a trained model or working SIP connection.
