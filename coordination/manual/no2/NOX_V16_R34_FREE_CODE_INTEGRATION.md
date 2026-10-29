# NOX V16 · R34 · FREE REUSE FIRST · Real code, zero paid APIs

This is an isolated, opt-in source integration package for owner review, **not** a new Windows host or a second local LLM. It has no auto-download and does not claim native Windows acceptance. Free code ≠ free GPU/hardware/hosting ≠ redistribution rights for every model/voice.

## Reuse existing working NOX modules before upstream packages

| Existing code in PR162 | Native task / benefit |
| --- | --- |
| \`Packages/P02/worker-python/p02_capabilities.py:LocalVoicePipeline\` | Existing native-selected RU↔ES ASR/chat/TTS contract, STOP and consent |
| \`Packages/P02/worker-python/p02_runtime.py:OllamaClient\` | Loopback model runtime and existing cancellation |
| \`proposals/NOX-PACK02-50/ops.mjs\` | Existing 50 offline functions, including SRT/VTT/subtitle helpers |
| \`Packages/P04/train_qlora.py\` | Original QLoRA rights/GPU/holdout/checkpoint implementation |
| \`Packages/P02/worker-chat/SpaceBrowserBoundary.cs\` | Existing WPF/WebView2 origin boundary |

## Source code provided

- \`free_local_backends_r34.py\`: **actual callable adapters** for an already loaded faster-whisper model (\`asr(scope, audio, language, stop)\`) and an owner-selected, already installed Argos translation package (\`chat(scope,text,source,target,directive,stop)\`). These match the existing \`LocalVoicePipeline\` callback signatures. No model is constructed, downloaded or installed; native user/model consent guards are mandatory at every call, STOP is checked before and during lazy ASR and after translation, audio never goes to disk.
- \`test_free_local_backends_r34.py\`: 12 Python unittest cases, locally executed and passed on 2026-10-30 without optional packages, using fake vendor engines. This is **contract/source unit QA only**.
- \`free_upstream_catalog_r34.json\`: 12 upstream libraries/repositories with project-owned source references, exact official links, claimed licenses and current admission states. Do not infer approval from the catalog.

## How owner #1/#2 would integrate after exact HEAD/CAS

The **owner-selected** P02 host loads the model from a previously SHA-256 checked local path (or reuses the already initialized, owner-approved instance), obtains authenticated \`native_authorize(scope, "chat.voice")\` and \`snapshot_approved(scope, source, target)\` callables. Then configure existing \`LocalVoicePipeline(asr=bind_faster_whisper_asr(loaded_model,...), chat=existing_host_chat, tts=existing_host_tts, approved_models=real_rights_accepted, permitted_voices=frozenset(real_voice_ids))\`. Do not replace either the singleton host or the user's existing P02 runtime.

Argos \`bind_installed_argos_translation\` is an **optional** single host-selected translation mode only when a previously accepted offline RU↔ES model package is present; the default chat LLM and MAESTRO mode remain unchanged. Its callback can replace the \`chat\` callback only with explicit native approval. Never silently substitute an unlicensed model or call an online API.

\`\`\`bash
# Optional developer test (no model downloads; standard library only):
python -m unittest discover -s coordination/manual/no2 -p test_free_local_backends_r34.py -v

# Optional dependencies in an isolated pre-approved environment:
python -m pip install pysubs2
python -m pip install faster-whisper
python -m pip install argostranslate
# Owner must pin audited package versions, hashes, and accepted model licenses.
\`\`\`

## Useful free upstream modules (not blanket approval)

| Priority | Project / license | Actual use, owner |
| --- | --- | --- |
| P0 | [faster-whisper](https://github.com/SYSTRAN/faster-whisper), MIT | Local ASR RU/ES, P02; owner-loaded engine only |
| P0 | [Argos Translate](https://github.com/argosopentech/argos-translate), MIT or CC0 | Optional offline RU/ES machine translation, owner-approved packages |
| P0 | [pysubs2](https://github.com/tkarabela/pysubs2), MIT | Additional subtitle formats *only when PACK02 is insufficient* |
| P0 | [Ollama](https://github.com/ollama/ollama), MIT | **Already in NOX P02**; no second Ollama |
| P1 | [Silero VAD](https://github.com/snakers4/silero-vad), MIT | Optional VAD in approved ASR pipeline |
| P1 | [CTranslate2](https://github.com/OpenNMT/CTranslate2), MIT | Vendor inference dependency, not a parallel engine |
| P1 | [llama.cpp](https://github.com/ggml-org/llama.cpp), MIT | Optional GGUF ModelCenter backend, require separate model rights |
| P1 | [diffusers](https://github.com/huggingface/diffusers), Apache-2.0 | Images owner P04, approved local GPU/model weights only |
| P2 | [whisper.cpp](https://github.com/ggml-org/whisper.cpp), MIT | Alternative to faster-whisper, do not run two engines by default |
| P2 | [Vosk](https://github.com/alphacep/vosk-api), Apache-2.0 | Lightweight alternative offline ASR |
| HOLD | [ComfyUI](https://github.com/Comfy-Org/ComfyUI), GPL-3.0 | License/repackaging and second-server concerns; not default |
| HOLD | [OHF Piper](https://github.com/OHF-Voice/piper1-gpl), GPL-3.0 | Current maintained TTS; voice cards are separately licensed. Archived rhasspy/piper used MIT. |

## Host50 relevance: no fake bindings

The current Host50 owner map has **40/50 source-bound**, **10 unbound** (training.start/evaluate, media.player/subtitles, browser.open/bookmarks, images.generate, system.update/backup/pc_control), and 14 separately native pending. These adapters can reduce P02 voice work and supply ready subtitle/ASR/translation components; they do **not** complete Host50. P04 training must reuse original QLoRA; WebView2 must reuse actual WPF native boundary; backup/PC control must use approved Windows APIs and explicit consent. The remaining 10 need real owner-native callbacks with binding receipts and E2E.

## Release gates remain unchanged

SOURCE_PREPARED ≠ SOURCE_INTEGRATED ≠ QA_ACCEPTED ≠ BUILT ≠ E07. Manual #1/T06 owns PR162 writes; #3 P04/P05; #2 independent QA; T02 alone updates Master/E06/Lessons/Errors with CAS/readback. Do not start GitLab CI/EXE/NSIS before T09 frozen source, T10 SOURCE_READY, source archive 729/3 NO-LOSS and explicit owner approval. Use same EXE BuildID for E07 10/10. No re-training of LLM weights was performed.
