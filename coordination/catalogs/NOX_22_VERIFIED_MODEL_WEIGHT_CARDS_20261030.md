# NOX HELION · VERIFIED MODEL WEIGHT CARDS · 2026-10-30

22 distinct exact Hugging Face model card URLs successfully opened using public search. This confirms model card URL existence, NOT successful weight download, safe inference, exact pinned revision, Windows compatibility, or commercial use. Some releases are gated or noncommercial, heavy or GPU-unsafe. Record immutable commit, SHA, exact files, format, disk/VRAM requirements, license/acceptable use terms and authorized data before actual downloading. Reuse existing Model Center and FORGE; no automatic pulls.

| # | Task | Model | Exact model card | Evaluation priority | Special warning |
|---:|---|---|---|---|---|
| 1 | Text LLM | Qwen3.5 9B | [Qwen/Qwen3.5-9B](https://huggingface.co/Qwen/Qwen3.5-9B) | P1 | VRAM+quantization check |
| 2 | Text LLM | Qwen3 8B | [Qwen/Qwen3-8B](https://huggingface.co/Qwen/Qwen3-8B) | P1 | GPU quantization check |
| 3 | Code LLM | Qwen2.5 Coder 7B | [Qwen/Qwen2.5-Coder-7B-Instruct](https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct) | P1 | Code skill evaluation |
| 4 | Text LLM | Gemma 3 4B | [google/gemma-3-4b-it](https://huggingface.co/google/gemma-3-4b-it) | P1 | Gemma custom conditions |
| 5 | Text LLM | Mistral 7B | [mistralai/Mistral-7B-Instruct-v0.3](https://huggingface.co/mistralai/Mistral-7B-Instruct-v0.3) | P1 | Resource/license review |
| 6 | Text+vision LLM | Gemma 3 12B | [google/gemma-3-12b-it](https://huggingface.co/google/gemma-3-12b-it) | P2 | Likely memory-intensive; terms |
| 7 | Text LLM | Llama 3.2 3B | [meta-llama/Llama-3.2-3B-Instruct](https://huggingface.co/meta-llama/Llama-3.2-3B-Instruct) | P1 | Llama license/access gate |
| 8 | Embedding | Qwen3 Embedding 0.6B | [Qwen/Qwen3-Embedding-0.6B](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B) | P0 | SQLite/RAG adapter candidate |
| 9 | Embedding | BGE-M3 | [BAAI/bge-m3](https://huggingface.co/BAAI/bge-m3) | P0 | Multilingual retrieval candidate |
| 10 | Reranking | Qwen3 Reranker 0.6B | [Qwen/Qwen3-Reranker-0.6B](https://huggingface.co/Qwen/Qwen3-Reranker-0.6B) | P1 | RAG rerank stage |
| 11 | Embedding | multilingual E5 large instruct | [intfloat/multilingual-e5-large-instruct](https://huggingface.co/intfloat/multilingual-e5-large-instruct) | P1 | Vector length/index compatibility |
| 12 | ASR | Whisper large-v3 turbo | [openai/whisper-large-v3-turbo](https://huggingface.co/openai/whisper-large-v3-turbo) | P1 | GPU/CPU cost |
| 13 | ASR | Parakeet TDT 0.6b v3 | [nvidia/parakeet-tdt-0.6b-v3](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3) | P2 | Language/support preflight |
| 14 | TTS | Kokoro 82M | [hexgrad/Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) | P0 | Voice language availability |
| 15 | TTS | Qwen3 TTS 0.6B Base | [Qwen/Qwen3-TTS-12Hz-0.6B-Base](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-Base) | P1 | Speech consent / GPU |
| 16 | TTS | Qwen3 TTS 1.7B VoiceDesign | [Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign) | P2 | GPU/voice rights |
| 17 | Image | FLUX.1 schnell | [black-forest-labs/FLUX.1-schnell](https://huggingface.co/black-forest-labs/FLUX.1-schnell) | P1 | GPU/quantization |
| 18 | Image | Stable Diffusion XL base | [stabilityai/stable-diffusion-xl-base-1.0](https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0) | P1 | Model license + memory |
| 19 | Video | Wan 2.2 TI2V 5B | [Wan-AI/Wan2.2-TI2V-5B](https://huggingface.co/Wan-AI/Wan2.2-TI2V-5B) | P2 | Huge download + GPU offloading |
| 20 | Music | ACE-Step 1.5 | [ACE-Step/Ace-Step1.5](https://huggingface.co/ACE-Step/Ace-Step1.5) | P1 | Pilot with selected exact files; license |
| 21 | Music | MusicGen small | [facebook/musicgen-small](https://huggingface.co/facebook/musicgen-small) | P2 | NONCOMMERCIAL CC-BY-NC-4.0 |
| 22 | Vision | Qwen2.5 VL 3B | [Qwen/Qwen2.5-VL-3B-Instruct](https://huggingface.co/Qwen/Qwen2.5-VL-3B-Instruct) | P1 | Vision worker preflight |

## Operator policy
Prefer one language model plus one embedding and one voice model for first local smoke test. Weights are NOT software engines. Use staging/allowlist, version-pinned HF download, file hashes, consent, STOP/resume, resource governor and rollback. No promises of all 22 fitting 12GB VRAM simultaneously; no commercial use of MusicGen-small without appropriate permission.
