# NOX HELION · WEIGHT MODEL CARDS · 2026-10-30

**38 exact candidate model-card paths, not downloaded weights.** This is a model discovery register, separate from 100 AI engines. Model card availability verified by live public search for selected cards only (Qwen3.5-9B, Qwen3 Embedding 0.6B, FLUX.1-schnell, HunyuanVideo-1.5, Parler TTS mini, Nvidia Parakeet, XTTS-v2, SAM2 and ACE-Step 1.5); remaining URLs require per-card verification before install. No implicit license or weight redistribution rights. Quantized GGUF/ONNX variants are separate artifacts and MUST be pinned at actual revision and verified SHA. Existing NOX Model Center actions: SOURCE/LICENSE/DOWNLOAD/CHECK SHA/INSTALL/TEST/STOP/ROLLBACK. All untested entries marked CANDIDATE.

**12 GB NVIDIA GPU:** no guarantee all run, 9–14B generally need quant/offload; FLUX.1-schnell full model may be heavy; HunyuanVideo 1.5 model card states Linux + minimum 14GB GPU with offload, and is therefore HOLD on 12GB Windows. Some model cards are hundreds of GB including multiple variants and must not be bulk pulled. Heavy runs need optional external GPU and explicit spend consent. Weights used for speech or persons require voice/identity consent and rights. Download only requested files, not full git clone of model repos.

| # | Modality | Candidate model | Expected NOX use | Priority | Exact model card | Verified installation |
|---:|---|---|---|---|---|---|
| 1 | TEXT_GENERAL | **Qwen3.5 9B** | RU/multilingual writer chat; quantization & runtime check | P0 | [Qwen/Qwen3.5-9B](https://huggingface.co/Qwen/Qwen3.5-9B) | NOT_INSTALLED |
| 2 | TEXT_GENERAL | **Qwen3.5 4B** | Faster lightweight assistant variant | P0 | [Qwen/Qwen3.5-4B](https://huggingface.co/Qwen/Qwen3.5-4B) | NOT_INSTALLED |
| 3 | TEXT_GENERAL | **Qwen3 8B** | Fallback for chat/reasoning | P1 | [Qwen/Qwen3-8B](https://huggingface.co/Qwen/Qwen3-8B) | NOT_INSTALLED |
| 4 | TEXT_GENERAL | **Qwen3 14B** | Higher-quality critic; 12GB quantization/offload caution | P1 | [Qwen/Qwen3-14B](https://huggingface.co/Qwen/Qwen3-14B) | NOT_INSTALLED |
| 5 | TEXT_CODE | **Qwen2.5 Coder 7B** | Local code assistant | P0 | [Qwen/Qwen2.5-Coder-7B-Instruct](https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct) | NOT_INSTALLED |
| 6 | MULTIMODAL | **Qwen2.5 VL 7B** | Visual/screenshot analysis | P1 | [Qwen/Qwen2.5-VL-7B-Instruct](https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct) | NOT_INSTALLED |
| 7 | TEXT_GENERAL | **Phi-4 Mini Instruct** | Compact instruct | P1 | [microsoft/Phi-4-mini-instruct](https://huggingface.co/microsoft/Phi-4-mini-instruct) | NOT_INSTALLED |
| 8 | TEXT_GENERAL | **Gemma 3 4B** | Small multimodal model, special terms | P1 | [google/gemma-3-4b-it](https://huggingface.co/google/gemma-3-4b-it) | NOT_INSTALLED |
| 9 | TEXT_GENERAL | **Gemma 3 12B** | Larger critic, 12GB quantized/offload only | P1 | [google/gemma-3-12b-it](https://huggingface.co/google/gemma-3-12b-it) | NOT_INSTALLED |
| 10 | TEXT_REASONING | **DeepSeek R1 Qwen 7B Distill** | Reasoning comparison | P1 | [deepseek-ai/DeepSeek-R1-Distill-Qwen-7B](https://huggingface.co/deepseek-ai/DeepSeek-R1-Distill-Qwen-7B) | NOT_INSTALLED |
| 11 | TEXT_GENERAL | **SmolLM2 1.7B** | Low resource tests | P1 | [HuggingFaceTB/SmolLM2-1.7B-Instruct](https://huggingface.co/HuggingFaceTB/SmolLM2-1.7B-Instruct) | NOT_INSTALLED |
| 12 | TEXT_GENERAL | **Llama 3.2 3B Instruct** | Meta terms/gated access | P1 | [meta-llama/Llama-3.2-3B-Instruct](https://huggingface.co/meta-llama/Llama-3.2-3B-Instruct) | NOT_INSTALLED |
| 13 | TEXT_GENERAL | **Mistral 7B Instruct v0.3** | Second opinion candidate | P1 | [mistralai/Mistral-7B-Instruct-v0.3](https://huggingface.co/mistralai/Mistral-7B-Instruct-v0.3) | NOT_INSTALLED |
| 14 | EMBEDDING | **Qwen3 Embedding 0.6B** | Multilingual search vectors | P0 | [Qwen/Qwen3-Embedding-0.6B](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B) | NOT_INSTALLED |
| 15 | EMBEDDING | **BGE-M3** | Multilingual RAG | P0 | [BAAI/bge-m3](https://huggingface.co/BAAI/bge-m3) | NOT_INSTALLED |
| 16 | EMBEDDING | **multilingual-e5-large** | RAG embedding alternative | P1 | [intfloat/multilingual-e5-large](https://huggingface.co/intfloat/multilingual-e5-large) | NOT_INSTALLED |
| 17 | EMBEDDING | **MiniLM L6 v2** | Small embedding test baseline | P1 | [sentence-transformers/all-MiniLM-L6-v2](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2) | NOT_INSTALLED |
| 18 | RERANKER | **Qwen3 Reranker 0.6B** | Rerank retrieved passages | P1 | [Qwen/Qwen3-Reranker-0.6B](https://huggingface.co/Qwen/Qwen3-Reranker-0.6B) | NOT_INSTALLED |
| 19 | ASR | **Whisper Large v3 Turbo** | Transcription high quality | P1 | [openai/whisper-large-v3-turbo](https://huggingface.co/openai/whisper-large-v3-turbo) | NOT_INSTALLED |
| 20 | ASR | **Whisper Small** | Lower resource ASR | P0 | [openai/whisper-small](https://huggingface.co/openai/whisper-small) | NOT_INSTALLED |
| 21 | ASR | **Distil Whisper Large v3** | English ASR acceleration | P1 | [distil-whisper/distil-large-v3](https://huggingface.co/distil-whisper/distil-large-v3) | NOT_INSTALLED |
| 22 | ASR | **Parakeet TDT 0.6B v2** | English ASR; NeMo runtime | P1 | [nvidia/parakeet-tdt-0.6b-v2](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v2) | NOT_INSTALLED |
| 23 | TTS | **Kokoro 82M** | Expressive lightweight TTS | P0 | [hexgrad/Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) | NOT_INSTALLED |
| 24 | TTS | **F5 TTS** | Reference-guided speech; permissions | P1 | [SWivid/F5-TTS](https://huggingface.co/SWivid/F5-TTS) | NOT_INSTALLED |
| 25 | TTS | **Parler TTS Mini v1** | Voice description and style | P1 | [parler-tts/parler-tts-mini-v1](https://huggingface.co/parler-tts/parler-tts-mini-v1) | NOT_INSTALLED |
| 26 | TTS | **XTTS v2** | Special Coqui model license | P2 | [coqui/XTTS-v2](https://huggingface.co/coqui/XTTS-v2) | NOT_INSTALLED |
| 27 | IMAGE | **FLUX.1 Schnell** | Image diffusion; heavy 12B, likely offload/remote | P1 | [black-forest-labs/FLUX.1-schnell](https://huggingface.co/black-forest-labs/FLUX.1-schnell) | NOT_INSTALLED |
| 28 | IMAGE | **SDXL Base 1.0** | Local image workflow | P1 | [stabilityai/stable-diffusion-xl-base-1.0](https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0) | NOT_INSTALLED |
| 29 | IMAGE | **Stable Diffusion 3.5 Medium** | Check stability model license | P1 | [stabilityai/stable-diffusion-3.5-medium](https://huggingface.co/stabilityai/stable-diffusion-3.5-medium) | NOT_INSTALLED |
| 30 | IMAGE | **Stable Diffusion v1.5** | Legacy image workflows and terms | P1 | [runwayml/stable-diffusion-v1-5](https://huggingface.co/runwayml/stable-diffusion-v1-5) | NOT_INSTALLED |
| 31 | VIDEO | **Wan2.2 TI2V 5B** | Video with offload/quant; native acceptance needed | P1 | [Wan-AI/Wan2.2-TI2V-5B](https://huggingface.co/Wan-AI/Wan2.2-TI2V-5B) | NOT_INSTALLED |
| 32 | VIDEO | **HunyuanVideo 1.5** | Linux ≥14GB VRAM w offload per model card; 12GB HOLD | P2 | [tencent/HunyuanVideo-1.5](https://huggingface.co/tencent/HunyuanVideo-1.5) | NOT_INSTALLED |
| 33 | VIDEO | **CogVideoX 2B** | Short scene workflow; GPU preflight | P1 | [THUDM/CogVideoX-2b](https://huggingface.co/THUDM/CogVideoX-2b) | NOT_INSTALLED |
| 34 | VIDEO | **LTX Video** | Video-generation workflow | P1 | [Lightricks/LTX-Video](https://huggingface.co/Lightricks/LTX-Video) | NOT_INSTALLED |
| 35 | MUSIC | **ACE-Step 1.5** | Music pilot and original songs; model-use rights | P1 | [ACE-Step/Ace-Step1.5](https://huggingface.co/ACE-Step/Ace-Step1.5) | NOT_INSTALLED |
| 36 | VISION | **SAM2 Hiera Large** | Segment video/image objects | P1 | [facebook/sam2-hiera-large](https://huggingface.co/facebook/sam2-hiera-large) | NOT_INSTALLED |
| 37 | VISION | **CLIP ViT B32** | Image text search/zero-shot | P1 | [openai/clip-vit-base-patch32](https://huggingface.co/openai/clip-vit-base-patch32) | NOT_INSTALLED |
| 38 | MULTIMODAL | **Qwen2.5 Omni 7B** | Audio/video/text multimodal evaluation | P1 | [Qwen/Qwen2.5-Omni-7B](https://huggingface.co/Qwen/Qwen2.5-Omni-7B) | NOT_INSTALLED |

## Preflight workflow
1. Fetch card metadata and license via Hub; 2. list immutable available revisions and formats; 3. estimate RAM/VRAM/disks from **specific** quant/file, not params alone; 4. show license/size/permission; 5. download only authorized files to quarantine staging with checksum; 6. scanned/rights gate; 7. test model in existing Ollama/ComfyUI/FORGE where compatible; 8. collect benchmark latency, VRAM, quality; 9. attach native receipts; 10. promote via approval and record rollback. Model selection should never silently launch new services.
