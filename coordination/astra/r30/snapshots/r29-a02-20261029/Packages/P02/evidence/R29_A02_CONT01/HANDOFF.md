# R29 A02 continuation01 — original preview/playback contract adapter

Parent220c95cd3e705c819c89d82d53baa52e22c69153. Previous A02 queue10/10 retained; continuation1/10 is separate and counts a tested source component, not product readiness. Source scope R29 A02 approach08 / V16 §26.4.8. No full product TaskID denominator or acceptance invented.

## Concrete contract defect and source fix

Original WindowsSapiTTS.speak executes preview-approved native playback and returns {state:TTS_SUBPROCESS_COMPLETED,language,evidence:requires_independent_physical_audio_confirmation}. Current P02 byte-audio pipeline correctly requires bytes and an output_audio_id; feeding the original receipt into it fails TTS_INVALID_RESULT. Making that pipeline accept arbitrary dictionaries or inventing stored audio would be false.

New p02_original_voice_port.py is a scoped adapter to the ORIGINAL VoiceService/LocalWhisperASR/LocalOllamaTranslator/WindowsSapiTTS; no new ASR/model/TTS engine, audio store, router, capture implementation or host. An explicit original_voice_port optional argument on the existing three-port registration selects this alternate chat.voice provider contract; the default byte-audio/MAESTRO path is unchanged and still rejects dictionaries. Canonical50 routes are not expanded.

Original-provider request schema is exactly capture_id,source,target,optional speak(bool). RU↔ES only; no page approval/identity/audio/path fields. Default output PREVIEW_ONLY contains the original challenge and review flags. speak=True expresses intent only: the real native UI must return NativePreviewDecision bound to the original request ID and text SHA. Original VoiceService.speak_preview independently validates the digest and safety. Only the exact original playback receipt is returned as NATIVE_TTS_SUBPROCESS_COMPLETED with audio_stored=False and physical_audio_confirmed=False; no output_audio_id or audible-success assertion is created.

This wrapper reuses the active ORIGINAL VoiceSession from enabled NativeIngress, so authorized real chat.stop cancels preview/ASR/translation/TTS rather than a separate token. It delegates original transcribe→translate→speak_preview methods separately, checking native scope, configured model identity/port/ASR settings, provider objects, native hooks and current model rights between stages. Native authorization itself is followed by revalidation before the next callback. Missing consent/UI/provider, changed scope/model/provider/hook, revoked model rights, invalid request/digest, or STOP fails closed before later work. Scope/capture/mic authorization and native review remain actual host obligations; no callback is replaced with production True.

## Reproduction and precise limitations

RED: existing registration cannot bind the original-service contract (nine initial tests fail with unsupported original_voice_port). Original playback-dict-vs-byte contract remains explicitly tested: the byte pipeline rejects the original SAPI receipt, proving it was not loosened.

GREEN:19 selected tests, including13 new original-service contract cases and6 pre-existing registration/STOP cases. The exact original package is imported from verified original729 ZIP SHA256 ff8e2848c7c7ab776b90cbd8ac28e41e3815e96373c3c5f635d7587284629e9a. Original VoiceService and original ASR/translator/SAPI adapter methods run; test fixtures replace ASR/translation subprocess boundary, installed-model diagnosis, platform detection and the SAPI process runner. No real model, microphone, PowerShell, audible playback or Windows acceptance is claimed. Tests cover preview/no-autoplay, exact native receipt, missing/forged/mismatched consent, STOP during native review, model revocation/identity change after ASR, scope/callback changes and preservation of the existing byte contract. Existing66-test voice suite was not pointlessly rerun.

```
NOX_ORIGINAL_SOURCE_ZIP=/path/to/verified-original-729.zip PYTHONPATH=Packages/P02/worker-python python -m unittest test_p02_original_voice_port_r29.OriginalVoiceContract test_p02_loader_existing_pack_r29.ExistingPackContract test_p02_loader_voice_stop_r29.VoiceStopWiring -v
```

Original source byte hashes are recorded in original_sources.json. Original729/three source parts, donor manifests and stager remain untouched. Existing TIMEOUT, stream/history/SIP safeguards and VoiceSession lifecycle retained.

## Exact remaining native composition and dependency

1. Existing host prepares the actual original VoiceService and NativeIngress(enable_voice_stop=True), passes the same authenticated scope resolver to both registration and OriginalVoicePort, then explicitly supplies original_voice_port=that_port. This source task does not mount it. Original playback uses installed language-default SAPI voices; it does not claim support for a selected voice identity or MAESTRO. Those existing byte-provider flows remain separate and intact.
2. Existing native owner supplies capture-specific microphone/OS consent and one-use capture via OwnerTwoPorts, live model permission callback and physical preview UI returning NativePreviewDecision. No original authenticated capture-ID registry exists in inspected729 code; original PushToTalk.release returns WAV bytes and has its own live-consent checks. A real host must bind those existing captured bytes to its one-use capture handle rather than invent a second capture backend/store.
3. Before final host composition reconcile E06 shared-host snapshot correction cbfe853500c781bfeac6419ccc581843ea1bedce (native_bridge.py805ade55→ed2bc0f1). The P02 port can reject mutations during its callbacks; it cannot retrospectively prove session immutability before port admission. That other-owner patch is not merged here. Tests use the original host fixture honestly.
4. Native Windows mic/model/SAPI/physical review and same-SHA acceptance remain NOT_RUN. Original VoiceSession is retired at request end; this candidate deliberately keeps native review within the one active request and does not create a detached multi-request preview store.

Lesson: adapt the actual original result/approval lifecycle instead of weakening a different provider's output contract; a subprocess completion receipt is not stored PCM or proof of audible speech. Revalidate authority and configured provider identity at each actual stage boundary.
