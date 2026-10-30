# NOX HELION · AI ENGINE PACK 100 · 2026-10-30

**100 distinct AI engines, runtimes, frameworks and toolchains, not 100 independent LLM inference backends.** Curated upstream repository candidates for actual NOX functions; includes 10 categories × 10 and exact integration use. **Candidate != installed/QA-passed, commercially reusable, compatible with Windows/RTX 3060, or downloaded weights.** Upstream revision, code/weights licenses, threat scan, dependency lock and realistic GPU test pending. Not all engines should be installed: choose ONE primary per function, others are alternates/reference. Maintain existing WPF/WebView2/NSIS/Ollama/SQLite/RAG/FORGE/STOP/ACL/events.v3 and frozen HOME/MENU/WORK/Persona media. RTX 3060 12GB is a preflight reference, not a guaranteed supported device for all 100. Linux/cloud-only and Apple-only frameworks marked P2. 

## Integration gating
P0 = closely reusable with existing NOX, **not automatically installed**. P1 = adapter/pilot after compatibility. P2 = optional/alternative/heavy/research. For models use separate weight pack with exact revision and model license. Do not clone all candidates or start 100 backend processes.

| # | Category | Engine/toolchain | Role for NOX | Priority | Upstream source |
|---:|---|---|---|---|---|
| 1 | 01_LOCAL_LLM_RUNTIME | **Ollama** | Windows local LLM service; existing NOX backend | P0 | [Official code](https://github.com/ollama/ollama) |
| 2 | 01_LOCAL_LLM_RUNTIME | **llama.cpp** | GGUF runtime/quantization alternative | P1 | [Official code](https://github.com/ggml-org/llama.cpp) |
| 3 | 01_LOCAL_LLM_RUNTIME | **vLLM** | Linux GPU serving; not second default local runtime | P2 | [Official code](https://github.com/vllm-project/vllm) |
| 4 | 01_LOCAL_LLM_RUNTIME | **SGLang** | High-throughput Linux serving | P2 | [Official code](https://github.com/sgl-project/sglang) |
| 5 | 01_LOCAL_LLM_RUNTIME | **LMDeploy** | Optimized model serving; compatibility review | P2 | [Official code](https://github.com/InternLM/lmdeploy) |
| 6 | 01_LOCAL_LLM_RUNTIME | **MLX LM** | Apple Silicon only | P2 | [Official code](https://github.com/ml-explore/mlx-lm) |
| 7 | 01_LOCAL_LLM_RUNTIME | **MLC LLM** | Cross-platform compilation and deployment | P2 | [Official code](https://github.com/mlc-ai/mlc-llm) |
| 8 | 01_LOCAL_LLM_RUNTIME | **TensorRT-LLM** | NVIDIA inference build toolchain | P2 | [Official code](https://github.com/NVIDIA/TensorRT-LLM) |
| 9 | 01_LOCAL_LLM_RUNTIME | **ExLlamaV2** | GPU quantized inference alternative | P1 | [Official code](https://github.com/turboderp/exllamav2) |
| 10 | 01_LOCAL_LLM_RUNTIME | **LocalAI** | Local OpenAI-compatible API; optional, no second server | P2 | [Official code](https://github.com/mudler/LocalAI) |
| 11 | 02_SERVING_OPTIMIZATION | **ONNX Runtime** | Lightweight CPU/GPU execution and model formats | P1 | [Official code](https://github.com/microsoft/onnxruntime) |
| 12 | 02_SERVING_OPTIMIZATION | **OpenVINO** | Intel optimization | P2 | [Official code](https://github.com/openvinotoolkit/openvino) |
| 13 | 02_SERVING_OPTIMIZATION | **CTranslate2** | Optimized Whisper/translation inference | P1 | [Official code](https://github.com/OpenNMT/CTranslate2) |
| 14 | 02_SERVING_OPTIMIZATION | **TensorRT** | NVIDIA compilation/inference | P2 | [Official code](https://github.com/NVIDIA/TensorRT) |
| 15 | 02_SERVING_OPTIMIZATION | **NVIDIA Triton Server** | Multi-model GPU server for cloud | P2 | [Official code](https://github.com/triton-inference-server/server) |
| 16 | 02_SERVING_OPTIMIZATION | **Ray Serve** | Distributed model serving | P2 | [Official code](https://github.com/ray-project/ray) |
| 17 | 02_SERVING_OPTIMIZATION | **KServe** | Kubernetes serving | P2 | [Official code](https://github.com/kserve/kserve) |
| 18 | 02_SERVING_OPTIMIZATION | **BentoML** | Packaged service deployment | P2 | [Official code](https://github.com/bentoml/BentoML) |
| 19 | 02_SERVING_OPTIMIZATION | **llama-cpp-python** | Python bindings for GGUF inference | P1 | [Official code](https://github.com/abetlen/llama-cpp-python) |
| 20 | 02_SERVING_OPTIMIZATION | **Candle** | Rust tensor and inference framework | P2 | [Official code](https://github.com/huggingface/candle) |
| 21 | 03_AGENT_TOOLS_SKILLS | **LangGraph** | Stateful bounded agent workflows | P1 | [Official code](https://github.com/langchain-ai/langgraph) |
| 22 | 03_AGENT_TOOLS_SKILLS | **AutoGen** | Multi-agent framework | P2 | [Official code](https://github.com/microsoft/autogen) |
| 23 | 03_AGENT_TOOLS_SKILLS | **CrewAI** | Agent orchestration | P2 | [Official code](https://github.com/crewAIInc/crewAI) |
| 24 | 03_AGENT_TOOLS_SKILLS | **smolagents** | Small tool agents | P1 | [Official code](https://github.com/huggingface/smolagents) |
| 25 | 03_AGENT_TOOLS_SKILLS | **PydanticAI** | Typed agent controls | P1 | [Official code](https://github.com/pydantic/pydantic-ai) |
| 26 | 03_AGENT_TOOLS_SKILLS | **Haystack** | Search/agent pipelines | P2 | [Official code](https://github.com/deepset-ai/haystack) |
| 27 | 03_AGENT_TOOLS_SKILLS | **Letta** | Memory-aware agents | P1 | [Official code](https://github.com/letta-ai/letta) |
| 28 | 03_AGENT_TOOLS_SKILLS | **OpenHands** | Code agent in isolated sandbox | P1 | [Official code](https://github.com/OpenHands/OpenHands) |
| 29 | 03_AGENT_TOOLS_SKILLS | **Aider** | Patch-oriented coding; supervised | P0 | [Official code](https://github.com/Aider-AI/aider) |
| 30 | 03_AGENT_TOOLS_SKILLS | **OpenCode** | Terminal coding agent candidate | P1 | [Official code](https://github.com/anomalyco/opencode) |
| 31 | 04_MEMORY_RAG_SEARCH | **Mem0** | Extracted personal memory with revocation | P1 | [Official code](https://github.com/mem0ai/mem0) |
| 32 | 04_MEMORY_RAG_SEARCH | **LlamaIndex** | Document loaders and retrieval | P1 | [Official code](https://github.com/run-llama/llama_index) |
| 33 | 04_MEMORY_RAG_SEARCH | **LangChain** | Selective tools rather than duplicate graph | P2 | [Official code](https://github.com/langchain-ai/langchain) |
| 34 | 04_MEMORY_RAG_SEARCH | **Microsoft GraphRAG** | Relationship extraction/graph retrieval | P1 | [Official code](https://github.com/microsoft/graphrag) |
| 35 | 04_MEMORY_RAG_SEARCH | **sqlite-vec** | Vectors in existing SQLite | P0 | [Official code](https://github.com/asg017/sqlite-vec) |
| 36 | 04_MEMORY_RAG_SEARCH | **FAISS** | Separate vector index alternative | P2 | [Official code](https://github.com/facebookresearch/faiss) |
| 37 | 04_MEMORY_RAG_SEARCH | **Qdrant** | Server vector database alternative | P2 | [Official code](https://github.com/qdrant/qdrant) |
| 38 | 04_MEMORY_RAG_SEARCH | **Milvus** | Heavy vector server alternative | P2 | [Official code](https://github.com/milvus-io/milvus) |
| 39 | 04_MEMORY_RAG_SEARCH | **Chroma** | Vector store for isolated prototype | P2 | [Official code](https://github.com/chroma-core/chroma) |
| 40 | 04_MEMORY_RAG_SEARCH | **LanceDB** | Embedded vector/columnar alternative | P2 | [Official code](https://github.com/lancedb/lancedb) |
| 41 | 05_TRAINING_EVALUATION | **Transformers** | Model weights/tokenizer and training API | P1 | [Official code](https://github.com/huggingface/transformers) |
| 42 | 05_TRAINING_EVALUATION | **PEFT** | LoRA/QLoRA adapters | P0 | [Official code](https://github.com/huggingface/peft) |
| 43 | 05_TRAINING_EVALUATION | **TRL** | Preference/fine-tuning trainers | P1 | [Official code](https://github.com/huggingface/trl) |
| 44 | 05_TRAINING_EVALUATION | **Accelerate** | GPU training orchestration | P0 | [Official code](https://github.com/huggingface/accelerate) |
| 45 | 05_TRAINING_EVALUATION | **Unsloth** | Consumer GPU LoRA if supported | P1 | [Official code](https://github.com/unslothai/unsloth) |
| 46 | 05_TRAINING_EVALUATION | **Axolotl** | Config-driven tuning | P2 | [Official code](https://github.com/axolotl-ai-cloud/axolotl) |
| 47 | 05_TRAINING_EVALUATION | **LLaMA-Factory** | Training UI/trainer candidate | P1 | [Official code](https://github.com/hiyouga/LLaMA-Factory) |
| 48 | 05_TRAINING_EVALUATION | **DeepSpeed** | Large GPU distributed training | P2 | [Official code](https://github.com/deepspeedai/DeepSpeed) |
| 49 | 05_TRAINING_EVALUATION | **MLflow** | Experiment tracking/receipts | P1 | [Official code](https://github.com/mlflow/mlflow) |
| 50 | 05_TRAINING_EVALUATION | **lm-evaluation-harness** | Frozen holdout benchmark | P1 | [Official code](https://github.com/EleutherAI/lm-evaluation-harness) |
| 51 | 06_SPEECH_ASR_AUDIO | **whisper.cpp** | Offline ASR on Windows | P0 | [Official code](https://github.com/ggml-org/whisper.cpp) |
| 52 | 06_SPEECH_ASR_AUDIO | **faster-whisper** | ASR faster GPU path | P1 | [Official code](https://github.com/SYSTRAN/faster-whisper) |
| 53 | 06_SPEECH_ASR_AUDIO | **WhisperX** | Diarization/timing of transcripts | P1 | [Official code](https://github.com/m-bain/whisperX) |
| 54 | 06_SPEECH_ASR_AUDIO | **Silero VAD** | Voice activity detection | P0 | [Official code](https://github.com/snakers4/silero-vad) |
| 55 | 06_SPEECH_ASR_AUDIO | **SpeechBrain** | Voice classification/emotion research | P1 | [Official code](https://github.com/speechbrain/speechbrain) |
| 56 | 06_SPEECH_ASR_AUDIO | **NVIDIA NeMo** | Speech models training/inference | P2 | [Official code](https://github.com/NVIDIA/NeMo) |
| 57 | 06_SPEECH_ASR_AUDIO | **pyannote.audio** | Speaker separation | P1 | [Official code](https://github.com/pyannote/pyannote-audio) |
| 58 | 06_SPEECH_ASR_AUDIO | **Vosk** | Small offline ASR alternative | P1 | [Official code](https://github.com/alphacep/vosk-api) |
| 59 | 06_SPEECH_ASR_AUDIO | **WeNet** | Production ASR engine | P2 | [Official code](https://github.com/wenet-e2e/wenet) |
| 60 | 06_SPEECH_ASR_AUDIO | **ESPnet** | Speech research and training | P2 | [Official code](https://github.com/espnet/espnet) |
| 61 | 07_TTS_DUBBING | **Kokoro** | Lightweight voice TTS | P0 | [Official code](https://github.com/hexgrad/kokoro) |
| 62 | 07_TTS_DUBBING | **Piper TTS** | Offline TTS and GPL gate | P1 | [Official code](https://github.com/OHF-Voice/piper1-gpl) |
| 63 | 07_TTS_DUBBING | **Coqui TTS** | Speech synthesis reference; maintenance/license gate | P2 | [Official code](https://github.com/coqui-ai/TTS) |
| 64 | 07_TTS_DUBBING | **Chatterbox** | Expressive neural TTS candidate | P1 | [Official code](https://github.com/resemble-ai/chatterbox) |
| 65 | 07_TTS_DUBBING | **OpenVoice** | Voice style transfer with consent | P1 | [Official code](https://github.com/myshell-ai/OpenVoice) |
| 66 | 07_TTS_DUBBING | **F5-TTS** | Speech synthesis with reference audio consent | P1 | [Official code](https://github.com/SWivid/F5-TTS) |
| 67 | 07_TTS_DUBBING | **Fish Speech** | Multilingual TTS candidate | P1 | [Official code](https://github.com/fishaudio/fish-speech) |
| 68 | 07_TTS_DUBBING | **CosyVoice** | Multilingual voice | P1 | [Official code](https://github.com/FunAudioLLM/CosyVoice) |
| 69 | 07_TTS_DUBBING | **Bark** | Audio generation, model usage rights | P2 | [Official code](https://github.com/suno-ai/bark) |
| 70 | 07_TTS_DUBBING | **MeloTTS** | Multilingual speech | P1 | [Official code](https://github.com/myshell-ai/MeloTTS) |
| 71 | 08_IMAGE_GENERATION | **ComfyUI** | Reusable generation graph runner | P0 | [Official code](https://github.com/Comfy-Org/ComfyUI) |
| 72 | 08_IMAGE_GENERATION | **Diffusers** | Modular image/video diffusion inference | P0 | [Official code](https://github.com/huggingface/diffusers) |
| 73 | 08_IMAGE_GENERATION | **InvokeAI** | Image workflow studio | P1 | [Official code](https://github.com/invoke-ai/InvokeAI) |
| 74 | 08_IMAGE_GENERATION | **AUTOMATIC1111 WebUI** | UI/reference; avoid duplicate server | P2 | [Official code](https://github.com/AUTOMATIC1111/stable-diffusion-webui) |
| 75 | 08_IMAGE_GENERATION | **Forge WebUI** | Optimized WebUI alternative | P2 | [Official code](https://github.com/lllyasviel/stable-diffusion-webui-forge) |
| 76 | 08_IMAGE_GENERATION | **SD.Next** | Diffusion UI alternative | P2 | [Official code](https://github.com/vladmandic/sdnext) |
| 77 | 08_IMAGE_GENERATION | **Fooocus** | Reference for streamlined image jobs | P2 | [Official code](https://github.com/lllyasviel/Fooocus) |
| 78 | 08_IMAGE_GENERATION | **ControlNet** | Controlled scene composition | P1 | [Official code](https://github.com/lllyasviel/ControlNet) |
| 79 | 08_IMAGE_GENERATION | **InstantID** | Identity-consistent original assets with rights | P1 | [Official code](https://github.com/InstantID/InstantID) |
| 80 | 08_IMAGE_GENERATION | **IP-Adapter** | Image prompt consistency | P1 | [Official code](https://github.com/tencent-ailab/IP-Adapter) |
| 81 | 09_VIDEO_AVATAR_3D | **Wan2.2** | Short video generation; 12 GB offload testing required | P1 | [Official code](https://github.com/Wan-Video/Wan2.2) |
| 82 | 09_VIDEO_AVATAR_3D | **HunyuanVideo** | Large video model; cloud GPU possible | P2 | [Official code](https://github.com/Tencent/HunyuanVideo) |
| 83 | 09_VIDEO_AVATAR_3D | **CogVideoX** | Video-generation research/workflow | P2 | [Official code](https://github.com/zai-org/CogVideo) |
| 84 | 09_VIDEO_AVATAR_3D | **LTX-Video** | Video diffusion candidate | P1 | [Official code](https://github.com/Lightricks/LTX-Video) |
| 85 | 09_VIDEO_AVATAR_3D | **AnimateDiff** | Animating image sequences | P1 | [Official code](https://github.com/guoyww/AnimateDiff) |
| 86 | 09_VIDEO_AVATAR_3D | **LivePortrait** | Facial motion with rights and consent | P1 | [Official code](https://github.com/KwaiVGI/LivePortrait) |
| 87 | 09_VIDEO_AVATAR_3D | **SadTalker** | Talking avatar video | P2 | [Official code](https://github.com/OpenTalker/SadTalker) |
| 88 | 09_VIDEO_AVATAR_3D | **Wav2Lip** | Lip sync; non-commercial terms review | P2 | [Official code](https://github.com/Rudrabha/Wav2Lip) |
| 89 | 09_VIDEO_AVATAR_3D | **TRELLIS** | 3D asset generation candidate | P1 | [Official code](https://github.com/microsoft/TRELLIS) |
| 90 | 09_VIDEO_AVATAR_3D | **Hunyuan3D** | 3D reconstruction/asset generation | P1 | [Official code](https://github.com/Tencent-Hunyuan/Hunyuan3D-2) |
| 91 | 10_VISION_OCR_MULTIMODAL | **OpenCV** | Video frames and image processing | P0 | [Official code](https://github.com/opencv/opencv) |
| 92 | 10_VISION_OCR_MULTIMODAL | **PaddleOCR** | Multilingual document OCR | P1 | [Official code](https://github.com/PaddlePaddle/PaddleOCR) |
| 93 | 10_VISION_OCR_MULTIMODAL | **Tesseract** | Offline OCR baseline | P1 | [Official code](https://github.com/tesseract-ocr/tesseract) |
| 94 | 10_VISION_OCR_MULTIMODAL | **docTR** | Document deep-learning OCR | P1 | [Official code](https://github.com/mindee/doctr) |
| 95 | 10_VISION_OCR_MULTIMODAL | **Unstructured** | Document parsing | P1 | [Official code](https://github.com/Unstructured-IO/unstructured) |
| 96 | 10_VISION_OCR_MULTIMODAL | **PyMuPDF** | PDF parsing; AGPL/commercial license review | P2 | [Official code](https://github.com/pymupdf/PyMuPDF) |
| 97 | 10_VISION_OCR_MULTIMODAL | **Segment Anything 2** | Video/image segmentation | P1 | [Official code](https://github.com/facebookresearch/sam2) |
| 98 | 10_VISION_OCR_MULTIMODAL | **Detectron2** | Computer vision research | P2 | [Official code](https://github.com/facebookresearch/detectron2) |
| 99 | 10_VISION_OCR_MULTIMODAL | **Ultralytics YOLO** | Object detection; AGPL commercial review | P1 | [Official code](https://github.com/ultralytics/ultralytics) |
| 100 | 10_VISION_OCR_MULTIMODAL | **OpenCLIP** | Image-text embeddings | P1 | [Official code](https://github.com/mlfoundations/open_clip) |

## Recommended production choices
- Local LLM: **existing Ollama** primary; llama.cpp/ExLlamaV2 are research alternatives, not new auto-launched servers.
- Memory: existing SQLite+RAG, add sqlite-vec adapter and scoped loaders; GraphRAG only if actual feature requires a graph.
- Learning: PEFT + Accelerate + holdout/evaluation via existing Evolution/FORGE, not a second training backend.
- Voice: whisper.cpp + Silero VAD + Kokoro if license and language support validated.
- Images/video: one ComfyUI job adapter + controlled Diffusers workflows; video weights fit only if verified.
- Dev: Aider/OpenHands as isolated patch assistants (human-approved), not unattended edits to the product branch.

## Sources and scope
NOX Drive: FULL OWNER FUNCTION + WISHLIST MASTER; SOUL LIVING PERSONAS V2; Creative Studio V5; Release 1 REV5; FIN ZAGR V16. This AI pack is catalog-only, not modifications to canonical product source or the active PR. Item identities are source repository names, not model cards or weight artifacts.
