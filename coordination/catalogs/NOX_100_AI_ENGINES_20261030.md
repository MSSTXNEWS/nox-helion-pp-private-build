# NOX HELION · 100 AI Engines, Frameworks & Production Runtimes

Date: 2026-10-30. **Candidate technical pack, not 100 installed/benchmarked engines.** Separate weights from source code. License, maintenance, provider access and Windows/GPU requirements must be checked per pinned revision. P0 reuse existing Ollama/SQLite/FORGE/WebView2; do not install all alternatives. All external code in isolated staging, never silently modify PR162, source-lock assets, models or personas.

| # | AI class | Project | Upstream source | Integration disposition |
|---:|---|---|---|---|
| 1 | LLM inference | ollama | [source](https://github.com/ollama/ollama) | Compare to existing Ollama |
| 2 | LLM inference | llama.cpp | [source](https://github.com/ggml-org/llama.cpp) | Compare to existing Ollama |
| 3 | LLM inference | vllm | [source](https://github.com/vllm-project/vllm) | Compare to existing Ollama |
| 4 | LLM inference | sglang | [source](https://github.com/sgl-project/sglang) | Compare to existing Ollama |
| 5 | LLM inference | TensorRT-LLM | [source](https://github.com/NVIDIA/TensorRT-LLM) | Compare to existing Ollama |
| 6 | LLM inference | onnxruntime | [source](https://github.com/microsoft/onnxruntime) | Compare to existing Ollama |
| 7 | LLM inference | text-generation-inference | [source](https://github.com/huggingface/text-generation-inference) | Compare to existing Ollama |
| 8 | LLM inference | mlc-llm | [source](https://github.com/mlc-ai/mlc-llm) | Compare to existing Ollama |
| 9 | LLM inference | OpenLLM | [source](https://github.com/bentoml/OpenLLM) | Compare to existing Ollama |
| 10 | LLM inference | ktransformers | [source](https://github.com/kvcache-ai/ktransformers) | Compare to existing Ollama |
| 11 | AI model adapters | transformers | [source](https://github.com/huggingface/transformers) | Adapter/reference |
| 12 | AI model adapters | optimum | [source](https://github.com/huggingface/optimum) | Adapter/reference |
| 13 | AI model adapters | huggingface_hub | [source](https://github.com/huggingface/huggingface_hub) | Adapter/reference |
| 14 | AI model adapters | ggml | [source](https://github.com/ggml-org/ggml) | Adapter/reference |
| 15 | AI model adapters | pytorch | [source](https://github.com/pytorch/pytorch) | Adapter/reference |
| 16 | AI model adapters | onnxruntime-genai | [source](https://github.com/microsoft/onnxruntime-genai) | Adapter/reference |
| 17 | AI model adapters | openvino | [source](https://github.com/openvinotoolkit/openvino) | Adapter/reference |
| 18 | AI model adapters | neural-compressor | [source](https://github.com/intel/neural-compressor) | Adapter/reference |
| 19 | AI model adapters | semantic-kernel | [source](https://github.com/microsoft/semantic-kernel) | Adapter/reference |
| 20 | AI model adapters | litellm | [source](https://github.com/BerriAI/litellm) | Adapter/reference |
| 21 | Memory & RAG | mem0 | [source](https://github.com/mem0ai/mem0) | Adapter/reference |
| 22 | Memory & RAG | letta | [source](https://github.com/letta-ai/letta) | Adapter/reference |
| 23 | Memory & RAG | graphrag | [source](https://github.com/microsoft/graphrag) | Adapter/reference |
| 24 | Memory & RAG | llama_index | [source](https://github.com/run-llama/llama_index) | Adapter/reference |
| 25 | Memory & RAG | langchain | [source](https://github.com/langchain-ai/langchain) | Adapter/reference |
| 26 | Memory & RAG | sqlite-vec | [source](https://github.com/asg017/sqlite-vec) | Adapter/reference |
| 27 | Memory & RAG | faiss | [source](https://github.com/facebookresearch/faiss) | Adapter/reference |
| 28 | Memory & RAG | qdrant | [source](https://github.com/qdrant/qdrant) | Adapter/reference |
| 29 | Memory & RAG | chroma | [source](https://github.com/chroma-core/chroma) | Adapter/reference |
| 30 | Memory & RAG | weaviate | [source](https://github.com/weaviate/weaviate) | Adapter/reference |
| 31 | Autonomous agents & coding | OpenHands | [source](https://github.com/OpenHands/OpenHands) | Sandbox agent |
| 32 | Autonomous agents & coding | aider | [source](https://github.com/Aider-AI/aider) | Sandbox agent |
| 33 | Autonomous agents & coding | opencode | [source](https://github.com/anomalyco/opencode) | Sandbox agent |
| 34 | Autonomous agents & coding | cline | [source](https://github.com/cline/cline) | Sandbox agent |
| 35 | Autonomous agents & coding | goose | [source](https://github.com/block/goose) | Sandbox agent |
| 36 | Autonomous agents & coding | langgraph | [source](https://github.com/langchain-ai/langgraph) | Sandbox agent |
| 37 | Autonomous agents & coding | autogen | [source](https://github.com/microsoft/autogen) | Sandbox agent |
| 38 | Autonomous agents & coding | crewAI | [source](https://github.com/crewAIInc/crewAI) | Sandbox agent |
| 39 | Autonomous agents & coding | smolagents | [source](https://github.com/huggingface/smolagents) | Sandbox agent |
| 40 | Autonomous agents & coding | SWE-agent | [source](https://github.com/SWE-agent/SWE-agent) | Sandbox agent |
| 41 | Training and weights tooling | peft | [source](https://github.com/huggingface/peft) | FORGE evaluate |
| 42 | Training and weights tooling | trl | [source](https://github.com/huggingface/trl) | FORGE evaluate |
| 43 | Training and weights tooling | accelerate | [source](https://github.com/huggingface/accelerate) | FORGE evaluate |
| 44 | Training and weights tooling | unsloth | [source](https://github.com/unslothai/unsloth) | FORGE evaluate |
| 45 | Training and weights tooling | LLaMA-Factory | [source](https://github.com/hiyouga/LLaMA-Factory) | FORGE evaluate |
| 46 | Training and weights tooling | axolotl | [source](https://github.com/axolotl-ai-cloud/axolotl) | FORGE evaluate |
| 47 | Training and weights tooling | DeepSpeed | [source](https://github.com/microsoft/DeepSpeed) | FORGE evaluate |
| 48 | Training and weights tooling | pytorch-lightning | [source](https://github.com/Lightning-AI/pytorch-lightning) | FORGE evaluate |
| 49 | Training and weights tooling | bitsandbytes | [source](https://github.com/bitsandbytes-foundation/bitsandbytes) | FORGE evaluate |
| 50 | Training and weights tooling | datasets | [source](https://github.com/huggingface/datasets) | FORGE evaluate |
| 51 | ASR and translation | whisper.cpp | [source](https://github.com/ggml-org/whisper.cpp) | Adapter/reference |
| 52 | ASR and translation | faster-whisper | [source](https://github.com/SYSTRAN/faster-whisper) | Adapter/reference |
| 53 | ASR and translation | whisper | [source](https://github.com/openai/whisper) | Adapter/reference |
| 54 | ASR and translation | silero-vad | [source](https://github.com/snakers4/silero-vad) | Adapter/reference |
| 55 | ASR and translation | whisperX | [source](https://github.com/m-bain/whisperX) | Adapter/reference |
| 56 | ASR and translation | pyannote-audio | [source](https://github.com/pyannote/pyannote-audio) | Adapter/reference |
| 57 | ASR and translation | seamless_communication | [source](https://github.com/facebookresearch/seamless_communication) | Adapter/reference |
| 58 | ASR and translation | fairseq | [source](https://github.com/facebookresearch/fairseq) | Adapter/reference |
| 59 | ASR and translation | argos-translate | [source](https://github.com/argosopentech/argos-translate) | Adapter/reference |
| 60 | ASR and translation | marian | [source](https://github.com/marian-nmt/marian) | Adapter/reference |
| 61 | Voice & TTS | Qwen3-TTS | [source](https://github.com/QwenLM/Qwen3-TTS) | Adapter/reference |
| 62 | Voice & TTS | kokoro | [source](https://github.com/hexgrad/kokoro) | Adapter/reference |
| 63 | Voice & TTS | piper | [source](https://github.com/rhasspy/piper) | Adapter/reference |
| 64 | Voice & TTS | TTS | [source](https://github.com/coqui-ai/TTS) | Adapter/reference |
| 65 | Voice & TTS | piper1-gpl | [source](https://github.com/OHF-Voice/piper1-gpl) | Adapter/reference |
| 66 | Voice & TTS | StyleTTS2 | [source](https://github.com/yl4579/StyleTTS2) | Adapter/reference |
| 67 | Voice & TTS | OpenVoice | [source](https://github.com/myshell-ai/OpenVoice) | Adapter/reference |
| 68 | Voice & TTS | fish-speech | [source](https://github.com/fishaudio/fish-speech) | Adapter/reference |
| 69 | Voice & TTS | F5-TTS | [source](https://github.com/SWivid/F5-TTS) | Adapter/reference |
| 70 | Voice & TTS | chatterbox | [source](https://github.com/resemble-ai/chatterbox) | Adapter/reference |
| 71 | Image and video AI | ComfyUI | [source](https://github.com/Comfy-Org/ComfyUI) | Separate creative worker |
| 72 | Image and video AI | diffusers | [source](https://github.com/huggingface/diffusers) | Separate creative worker |
| 73 | Image and video AI | InvokeAI | [source](https://github.com/invoke-ai/InvokeAI) | Separate creative worker |
| 74 | Image and video AI | generative-models | [source](https://github.com/Stability-AI/generative-models) | Separate creative worker |
| 75 | Image and video AI | flux | [source](https://github.com/black-forest-labs/flux) | Separate creative worker |
| 76 | Image and video AI | LTX-Video | [source](https://github.com/Lightricks/LTX-Video) | Separate creative worker |
| 77 | Image and video AI | Wan2.2 | [source](https://github.com/Wan-Video/Wan2.2) | Separate creative worker |
| 78 | Image and video AI | HunyuanVideo | [source](https://github.com/Tencent/HunyuanVideo) | Separate creative worker |
| 79 | Image and video AI | CogVideo | [source](https://github.com/THUDM/CogVideo) | Separate creative worker |
| 80 | Image and video AI | InternVideo | [source](https://github.com/OpenGVLab/InternVideo) | Separate creative worker |
| 81 | Music and sound AI | ACE-Step-1.5 | [source](https://github.com/ace-step/ACE-Step-1.5) | Separate creative worker |
| 82 | Music and sound AI | audiocraft | [source](https://github.com/facebookresearch/audiocraft) | Separate creative worker |
| 83 | Music and sound AI | audiolm-pytorch | [source](https://github.com/lucidrains/audiolm-pytorch) | Separate creative worker |
| 84 | Music and sound AI | stable-audio-tools | [source](https://github.com/Stability-AI/stable-audio-tools) | Separate creative worker |
| 85 | Music and sound AI | bark | [source](https://github.com/suno-ai/bark) | Separate creative worker |
| 86 | Music and sound AI | Retrieval-based-Voice-Conversion-WebUI | [source](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) | Separate creative worker |
| 87 | Music and sound AI | spleeter | [source](https://github.com/deezer/spleeter) | Separate creative worker |
| 88 | Music and sound AI | demucs | [source](https://github.com/facebookresearch/demucs) | Separate creative worker |
| 89 | Music and sound AI | magenta | [source](https://github.com/magenta/magenta) | Separate creative worker |
| 90 | Music and sound AI | NeMo | [source](https://github.com/NVIDIA/NeMo) | Separate creative worker |
| 91 | AI evaluation and MCP | langfuse | [source](https://github.com/langfuse/langfuse) | Adapter/reference |
| 92 | AI evaluation and MCP | promptfoo | [source](https://github.com/promptfoo/promptfoo) | Adapter/reference |
| 93 | AI evaluation and MCP | inspect_ai | [source](https://github.com/UKGovernmentBEIS/inspect_ai) | Adapter/reference |
| 94 | AI evaluation and MCP | lm-evaluation-harness | [source](https://github.com/EleutherAI/lm-evaluation-harness) | Adapter/reference |
| 95 | AI evaluation and MCP | mlflow | [source](https://github.com/mlflow/mlflow) | Adapter/reference |
| 96 | AI evaluation and MCP | promptflow | [source](https://github.com/microsoft/promptflow) | Adapter/reference |
| 97 | AI evaluation and MCP | opentelemetry-python | [source](https://github.com/open-telemetry/opentelemetry-python) | Adapter/reference |
| 98 | AI evaluation and MCP | pydantic-ai | [source](https://github.com/pydantic/pydantic-ai) | Adapter/reference |
| 99 | AI evaluation and MCP | E2B | [source](https://github.com/e2b-dev/E2B) | Adapter/reference |
| 100 | AI evaluation and MCP | python-sdk | [source](https://github.com/modelcontextprotocol/python-sdk) | Adapter/reference |

## Gates
Exact tag/SHA; license+weight terms; CPU/RAM/VRAM; offline storage budget; authorized model download; isolated test; STOP/undo; frozen independent QA. **P0 candidate ≠ verified runtime**. Local vs Windows supported must be measured; existing approved OneHost remains authoritative.
