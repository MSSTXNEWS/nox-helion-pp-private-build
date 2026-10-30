# NOX HELION · AI ENGINE ADMISSION & EXPRESS P0 PATH · 2026-10-30

This is the **implementation shortlist** distilled from [100 candidate engines](NOX_AI_ENGINE_PACK_100_20261030.md), [38 weight cards](NOX_MODEL_WEIGHTS_38_OFFICIAL_CANDIDATES_20261030.md), and approved NOX V16/Release 1 constraints. It is **not** an authorization to install or merge any repo. A P0 candidate may still be deferred if existing code already satisfies the feature. Never add a second model engine, RAG server, event bus or agent runtime by default. SourceLock, exact SHA preimages, ACL/consent, STOP, native Windows acceptance, immutable approved images and rollback prevail.

| Priority | Selected reuse | Source | NOX benefit | Avoid | Hard evidence needed |
|---|---|---|---|---|---|
| P0 | **Existing Ollama + OllamaSharp only if missing** | [Upstream](https://github.com/ollama/ollama) | Local chat/model list/pull | Use existing one provider process | NOX model tags/chat real stream; STOP and offline states |
| P0 | **sqlite-vec** | [Upstream](https://github.com/asg017/sqlite-vec) | RAG vectors in canonical SQLite | No new vector DB | Index->retrieve->cite->delete can be replayed |
| P0 | **whisper.cpp** | [Upstream](https://github.com/ggml-org/whisper.cpp) | Windows offline RU-ES voice | Prefer existing voice route | Mic PCM to transcript verified, STOP |
| P0 | **Silero VAD** | [Upstream](https://github.com/snakers4/silero-vad) | Voice activity segmentation | Optional compact audio adapter | Real audio on/off, latency measured |
| P0 | **Kokoro small TTS weight** | [Upstream](https://huggingface.co/hexgrad/Kokoro-82M) | Speech feedback | Test actual RU/ES quality and weight rights | Audio rendered with sample text, voice consent |
| P0 | **Ollama-compatible Qwen3.5 4B/9B quant** | [Upstream](https://huggingface.co/Qwen/Qwen3.5-9B) | Local writing/analysis | Choose one quantized file after device preflight | Measured VRAM/RAM and reasonable latency |
| P0 | **BGE-M3 or Qwen3-Embedding 0.6B** | [Upstream](https://huggingface.co/BAAI/bge-m3) | Multilingual embeddings | Choose one into RAG | RU↔ES retrieval quality/latency test |
| P0 | **PEFT + Accelerate** | [Upstream](https://github.com/huggingface/peft) | Real authorized LoRA training | Reuse existing FORGE and governor | Holdout gain, checkpoint, rollback, owner approval |
| P0 | **Aider sandbox code assistant** | [Upstream](https://github.com/Aider-AI/aider) | Fix/apply minimal patches from existing repository | Isolated branch, no MAIN auto-merge | Expected test PASS and readback, no approved artwork changes |
| P0 | **WebView2Browser behaviors + WPF Samples** | [Upstream](https://github.com/MicrosoftEdge/WebView2Samples) | Browser tabs, history, search in EXE | No new browser host | WPF Windows native screenshot + playback tested |
| P0 | **Video.js 10 and LibVLCSharp conditional** | [Upstream](https://videojs.org/) | Playable local/remote permitted cinema | Select Web/Native only where route needs it | Real media load/seek/subtitles/resume |
| P1 | **ComfyUI one job adapter** | [Upstream](https://github.com/Comfy-Org/ComfyUI) | Image/video graph execution | External worker with STOP and task receipts | Real one-image pilot and refusal to show fake completed render |
| P1 | **A specific image weight SDXL** | [Upstream](https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0) | RTX 3060 image pilot | Weight license and disk preflight | Real local image, checkpointed inputs and output hash |
| P1 | **Godot playable template and Dialogic** | [Upstream](https://github.com/godotengine/godot) | One R1 game and AI NPC | Separate Godot game runtime not replacing NOX host | save → quit → restart → reload + NPC quest logic |
| P1 | **Roblox Studio MCP and official templates** | [Upstream](https://create.roblox.com/docs/studio/mcp) | NOX builds Roblox games in Studio | Requires authorized Studio and user consent | Create playtest in private place, not published automatically |
| P1 | **PptxGenJS + Pandoc + PDF.js** | [Upstream](https://github.com/gitbrent/PptxGenJS) | Real PowerPoint, document conversion and preview | Reuse Work OS artifact routes | Editable PPTX with inspected slide and export |

## One-shared-backend execution sequence
1. Resolve native P01–P05 source wiring on frozen SHA; do not create fake PASS. 2. Reuse existing Ollama/SQLite/RAG/Voice; bring missing adapters only. 3. Collect model-card metadata/license/quantization/disk limits, never bulk download by default. 4. Prove one end-to-end local chat/RAG/voice flow. 5. Add one small approved creative workflow with measured VRAM/latency/cost; 6. separate Roblox/Godot work accepts true playtest; 7. patch code through supervised isolation, external QA and verified rollback; 8. only then promote dependency version to release manifest.

**Not for direct RTX 3060 12GB Windows:** HunyuanVideo 1.5 states Linux and minimum 14 GB VRAM with offload; vLLM/SGLang/TensorRT-LLM server or Apple MLX LM require separate compatible hosts. Keep them as P2/cloud-only candidates.
