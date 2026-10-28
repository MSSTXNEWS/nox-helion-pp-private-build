/* NOX V16 · SUPER MODEL CENTER / E03.
 * 109+ separate weight variant download actions in 20+ categories.
 * Shared mounts for P03 Model Center, Creative/3D, Video, Photo, Persona, Memory and more.
 * All transfers are performed ONLY by native E06 after exact manifest/source rights approval.
 */
(function(global){'use strict';
const VARIANTS=Object.freeze([{"category":"3d","modelId":"hunyuan3d-mini","variantId":"hunyuan3d-mini-shape","name":"Hunyuan3D 2 Mini","variant":"Геометрия · Shape 0.6B","source":"https://huggingface.co/tencent/Hunyuan3D-2mini"},{"category":"3d","modelId":"hunyuan3d-21","variantId":"hunyuan3d-21-shape","name":"Hunyuan3D 2.1","variant":"Геометрия · Shape","source":"https://huggingface.co/tencent/Hunyuan3D-2.1"},{"category":"3d","modelId":"hunyuan3d-21","variantId":"hunyuan3d-21-pbr","name":"Hunyuan3D 2.1","variant":"Текстуры · PBR","source":"https://huggingface.co/tencent/Hunyuan3D-2.1"},{"category":"3d","modelId":"trellis","variantId":"trellis-image-large","name":"TRELLIS Image Large","variant":"Полная 3D-модель","source":"https://huggingface.co/microsoft/TRELLIS-image-large"},{"category":"3d","modelId":"trellis2","variantId":"trellis2-pbr-4b","name":"TRELLIS.2 4B","variant":"PBR · 4B","source":"https://huggingface.co/microsoft/TRELLIS.2-4B"},{"category":"video","modelId":"wan21","variantId":"wan21-t2v-13b","name":"Wan 2.1","variant":"Text → Video · 1.3B","source":"https://huggingface.co/Wan-AI/Wan2.1-T2V-1.3B"},{"category":"video","modelId":"wan21","variantId":"wan21-vace-13b","name":"Wan 2.1","variant":"VACE · видеообработка","source":"https://huggingface.co/Wan-AI/Wan2.1-VACE-1.3B"},{"category":"video","modelId":"wan22","variantId":"wan22-ti2v-5b","name":"Wan 2.2","variant":"TI2V · 5B","source":"https://huggingface.co/Wan-AI/Wan2.2-TI2V-5B"},{"category":"video","modelId":"wan22","variantId":"wan22-i2v-a14b","name":"Wan 2.2","variant":"Image → Video · A14B","source":"https://huggingface.co/Wan-AI/Wan2.2-I2V-A14B"},{"category":"video","modelId":"wan22","variantId":"wan22-t2v-a14b","name":"Wan 2.2","variant":"Text → Video · A14B","source":"https://huggingface.co/Wan-AI/Wan2.2-T2V-A14B"},{"category":"video","modelId":"hunyuanvideo15","variantId":"hunyuan15-t2v","name":"HunyuanVideo 1.5","variant":"Текст → видео","source":"https://huggingface.co/tencent/HunyuanVideo-1.5"},{"category":"video","modelId":"hunyuanvideo15","variantId":"hunyuan15-i2v","name":"HunyuanVideo 1.5","variant":"Фото → видео","source":"https://huggingface.co/tencent/HunyuanVideo-1.5"},{"category":"video","modelId":"mochi","variantId":"mochi1-preview","name":"Mochi 1","variant":"Preview","source":"https://huggingface.co/genmo/mochi-1-preview"},{"category":"video","modelId":"ltx","variantId":"ltx-video2b","name":"LTX-Video","variant":"2B · Distilled","source":"https://huggingface.co/Lightricks/LTX-Video"},{"category":"video","modelId":"ltx","variantId":"ltx25-fast","name":"LTX 2.5","variant":"Fast","source":"https://huggingface.co/Lightricks/LTX-2.5"},{"category":"video","modelId":"skyreels","variantId":"skyreels2-i2v","name":"SkyReels V2","variant":"Фото → видео","source":"https://huggingface.co/Skywork/SkyReels-V2"},{"category":"video","modelId":"skyreels","variantId":"skyreels2-df","name":"SkyReels V2","variant":"Diffusion Forcing","source":"https://huggingface.co/Skywork/SkyReels-V2"},{"category":"video","modelId":"cogvideo","variantId":"cogvideox-5b","name":"CogVideoX","variant":"5B","source":"https://huggingface.co/THUDM/CogVideoX-5b"},{"category":"photo","modelId":"flux2","variantId":"flux2-klein4b-bf16","name":"FLUX.2 Klein 4B","variant":"Стандартные BF16","source":"https://huggingface.co/black-forest-labs/FLUX.2-klein-4B"},{"category":"photo","modelId":"flux2","variantId":"flux2-klein4b-fp8","name":"FLUX.2 Klein 4B","variant":"Оптимизированные FP8","source":"https://huggingface.co/black-forest-labs/FLUX.2-klein-4b-fp8"},{"category":"photo","modelId":"flux2","variantId":"flux2-dev","name":"FLUX.2 Dev","variant":"Высокое качество · Dev","source":"https://huggingface.co/black-forest-labs/FLUX.2-dev"},{"category":"photo","modelId":"qwen","variantId":"qwen-image-2512","name":"Qwen Image","variant":"2512 · полные веса","source":"https://huggingface.co/Qwen/Qwen-Image-2512"},{"category":"photo","modelId":"sd35","variantId":"stable-diffusion35-medium","name":"Stable Diffusion 3.5","variant":"Medium","source":"https://huggingface.co/stabilityai/stable-diffusion-3.5-medium"},{"category":"persona","modelId":"qwen3-persona","variantId":"qwen3-persona-06b","name":"Qwen3 · Характер и диалог","variant":"0.6B · лёгкая","source":"https://huggingface.co/Qwen/Qwen3-0.6B"},{"category":"persona","modelId":"qwen3-persona","variantId":"qwen3-persona-17b","name":"Qwen3 · Характер и диалог","variant":"1.7B · лёгкая","source":"https://huggingface.co/Qwen/Qwen3-1.7B"},{"category":"persona","modelId":"qwen3-persona","variantId":"qwen3-persona-4b","name":"Qwen3 · Характер и диалог","variant":"4B · баланс","source":"https://huggingface.co/Qwen/Qwen3-4B"},{"category":"persona","modelId":"qwen3-persona","variantId":"qwen3-persona-8b","name":"Qwen3 · Характер и диалог","variant":"8B · глубокие диалоги","source":"https://huggingface.co/Qwen/Qwen3-8B"},{"category":"persona","modelId":"qwen3-persona","variantId":"qwen3-persona-4b-instruct","name":"Qwen3 · Характер и диалог","variant":"4B Instruct 2507","source":"https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507"},{"category":"persona","modelId":"qwen3-persona","variantId":"qwen3-persona-4b-gguf","name":"Qwen3 · Характер и диалог","variant":"4B GGUF","source":"https://huggingface.co/Qwen/Qwen3-4B-GGUF"},{"category":"persona","modelId":"qwen3-persona","variantId":"qwen3-persona-8b-gguf","name":"Qwen3 · Характер и диалог","variant":"8B GGUF","source":"https://huggingface.co/Qwen/Qwen3-8B-GGUF"},{"category":"persona","modelId":"gemma-persona","variantId":"gemma-persona-4b-it","name":"Gemma 3 · Персона","variant":"4B It","source":"https://huggingface.co/google/gemma-3-4b-it"},{"category":"persona","modelId":"gemma-persona","variantId":"gemma-persona-12b-it","name":"Gemma 3 · Персона","variant":"12B It","source":"https://huggingface.co/google/gemma-3-12b-it"},{"category":"emotions","modelId":"emotion","variantId":"emotion-distilroberta","name":"Emotion Recognition · эмоции","variant":"7 эмоций · DistilRoBERTa","source":"https://huggingface.co/j-hartmann/emotion-english-distilroberta-base"},{"category":"emotions","modelId":"emotion","variantId":"emotion-go-emotions","name":"Emotion Recognition · эмоции","variant":"GoEmotions · многометочный","source":"https://huggingface.co/SamLowe/roberta-base-go_emotions"},{"category":"emotions","modelId":"emotion","variantId":"emotion-tweet-multilabel","name":"Emotion Recognition · эмоции","variant":"Эмоции текста · multilabel","source":"https://huggingface.co/cardiffnlp/twitter-roberta-base-emotion-multilabel-latest"},{"category":"emotions","modelId":"emotion","variantId":"emotion-xlm-sentiment","name":"Emotion Recognition · эмоции","variant":"Мультиязычная тональность","source":"https://huggingface.co/cardiffnlp/twitter-xlm-roberta-base-sentiment"},{"category":"emotions","modelId":"emotion","variantId":"emotion-roberta-sentiment","name":"Emotion Recognition · эмоции","variant":"Тональность текста EN","source":"https://huggingface.co/cardiffnlp/twitter-roberta-base-sentiment-latest"},{"category":"memory","modelId":"qwen3-emb","variantId":"qwen3-emb-06b","name":"Qwen3 Embedding · память","variant":"0.6B · 32K","source":"https://huggingface.co/Qwen/Qwen3-Embedding-0.6B"},{"category":"memory","modelId":"qwen3-emb","variantId":"qwen3-emb-4b","name":"Qwen3 Embedding · память","variant":"4B · 32K","source":"https://huggingface.co/Qwen/Qwen3-Embedding-4B"},{"category":"memory","modelId":"qwen3-emb","variantId":"qwen3-emb-8b","name":"Qwen3 Embedding · память","variant":"8B · 32K","source":"https://huggingface.co/Qwen/Qwen3-Embedding-8B"},{"category":"memory","modelId":"bge","variantId":"bge-m3","name":"BGE · мультиязычная память","variant":"BGE-M3 · 100+ языков","source":"https://huggingface.co/BAAI/bge-m3"},{"category":"memory","modelId":"bge","variantId":"bge-reranker-v2-m3","name":"BGE · мультиязычная память","variant":"Reranker V2 M3","source":"https://huggingface.co/BAAI/bge-reranker-v2-m3"},{"category":"memory","modelId":"e5","variantId":"e5-small","name":"Multilingual E5","variant":"Small · быстрый индекс","source":"https://huggingface.co/intfloat/multilingual-e5-small"},{"category":"memory","modelId":"e5","variantId":"e5-base","name":"Multilingual E5","variant":"Base · баланс","source":"https://huggingface.co/intfloat/multilingual-e5-base"},{"category":"memory","modelId":"e5","variantId":"e5-large","name":"Multilingual E5","variant":"Large · качество","source":"https://huggingface.co/intfloat/multilingual-e5-large"},{"category":"memory","modelId":"minilm","variantId":"minilm-multilingual-l12","name":"MiniLM · лёгкая память","variant":"Multilingual MiniLM L12","source":"https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"},{"category":"thread","modelId":"qwen-rerank","variantId":"qwen-rerank-06b","name":"Qwen3 · восстановление контекста","variant":"Reranker 0.6B","source":"https://huggingface.co/Qwen/Qwen3-Reranker-0.6B"},{"category":"thread","modelId":"qwen-rerank","variantId":"qwen-rerank-4b","name":"Qwen3 · восстановление контекста","variant":"Reranker 4B","source":"https://huggingface.co/Qwen/Qwen3-Reranker-4B"},{"category":"thread","modelId":"qwen-rerank","variantId":"qwen-rerank-8b","name":"Qwen3 · восстановление контекста","variant":"Reranker 8B","source":"https://huggingface.co/Qwen/Qwen3-Reranker-8B"},{"category":"thread","modelId":"thread-llm","variantId":"thread-llm-4b","name":"Длинный диалог · Qwen3","variant":"4B · контекст","source":"https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507"},{"category":"thread","modelId":"thread-llm","variantId":"thread-llm-8b","name":"Длинный диалог · Qwen3","variant":"8B · контекст","source":"https://huggingface.co/Qwen/Qwen3-8B"},{"category":"thread","modelId":"thread-llm","variantId":"thread-llm-30b-moe","name":"Длинный диалог · Qwen3","variant":"30B-A3B Instruct","source":"https://huggingface.co/Qwen/Qwen3-30B-A3B-Instruct-2507"},{"category":"voice","modelId":"qwen-tts","variantId":"qwen-tts-06b-base","name":"Qwen3 TTS · голоса","variant":"0.6B Base","source":"https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-Base"},{"category":"voice","modelId":"qwen-tts","variantId":"qwen-tts-06b-custom","name":"Qwen3 TTS · голоса","variant":"0.6B CustomVoice","source":"https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"},{"category":"voice","modelId":"qwen-tts","variantId":"qwen-tts-17b-custom","name":"Qwen3 TTS · голоса","variant":"1.7B CustomVoice","source":"https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"},{"category":"voice","modelId":"qwen-tts","variantId":"qwen-tts-17b-design","name":"Qwen3 TTS · голоса","variant":"1.7B VoiceDesign","source":"https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign"},{"category":"voice","modelId":"whisper","variantId":"whisper-tiny","name":"Whisper · распознавание речи","variant":"Tiny","source":"https://huggingface.co/openai/whisper-tiny"},{"category":"voice","modelId":"whisper","variantId":"whisper-base","name":"Whisper · распознавание речи","variant":"Base","source":"https://huggingface.co/openai/whisper-base"},{"category":"voice","modelId":"whisper","variantId":"whisper-small","name":"Whisper · распознавание речи","variant":"Small","source":"https://huggingface.co/openai/whisper-small"},{"category":"voice","modelId":"whisper","variantId":"whisper-medium","name":"Whisper · распознавание речи","variant":"Medium","source":"https://huggingface.co/openai/whisper-medium"},{"category":"voice","modelId":"diarization","variantId":"diarization-community1","name":"Разделение говорящих","variant":"Community 1 · требуется принятие условий","source":"https://huggingface.co/pyannote/speaker-diarization-community-1"},{"category":"vision","modelId":"qwen-vl","variantId":"qwen-vl-3b","name":"Qwen2.5-VL · зрение","variant":"3B Instruct","source":"https://huggingface.co/Qwen/Qwen2.5-VL-3B-Instruct"},{"category":"vision","modelId":"qwen-vl","variantId":"qwen-vl-7b","name":"Qwen2.5-VL · зрение","variant":"7B Instruct","source":"https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct"},{"category":"vision","modelId":"qwen3-vl","variantId":"qwen3-vl-4b","name":"Qwen3-VL · зрение","variant":"4B Instruct","source":"https://huggingface.co/Qwen/Qwen3-VL-4B-Instruct"},{"category":"vision","modelId":"qwen3-vl","variantId":"qwen3-vl-8b","name":"Qwen3-VL · зрение","variant":"8B Instruct","source":"https://huggingface.co/Qwen/Qwen3-VL-8B-Instruct"},{"category":"slides","modelId":"slides-llm","variantId":"slides-llm-qwen4b","name":"Презентации · структура и тексты","variant":"Qwen3 4B Instruct","source":"https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507"},{"category":"slides","modelId":"slides-llm","variantId":"slides-llm-qwen8b","name":"Презентации · структура и тексты","variant":"Qwen3 8B","source":"https://huggingface.co/Qwen/Qwen3-8B"},{"category":"slides","modelId":"layout","variantId":"layout-layoutlmv3","name":"Презентации · визуальная разметка","variant":"LayoutLMv3 base · NC-лицензия","source":"https://huggingface.co/microsoft/layoutlmv3-base"},{"category":"slides","modelId":"layout","variantId":"layout-qwen-vl-3b","name":"Презентации · визуальная разметка","variant":"Qwen2.5-VL 3B","source":"https://huggingface.co/Qwen/Qwen2.5-VL-3B-Instruct"},{"category":"websites","modelId":"web-coder","variantId":"web-coder-qwen15b","name":"Сайты · программирование","variant":"Qwen2.5 Coder 1.5B","source":"https://huggingface.co/Qwen/Qwen2.5-Coder-1.5B-Instruct"},{"category":"websites","modelId":"web-coder","variantId":"web-coder-qwen7b","name":"Сайты · программирование","variant":"Qwen2.5 Coder 7B","source":"https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct"},{"category":"websites","modelId":"web-coder","variantId":"web-coder-qwen14b","name":"Сайты · программирование","variant":"Qwen2.5 Coder 14B","source":"https://huggingface.co/Qwen/Qwen2.5-Coder-14B-Instruct"},{"category":"websites","modelId":"web-coder","variantId":"web-coder-qwen30moe","name":"Сайты · программирование","variant":"Qwen3 Coder 30B-A3B","source":"https://huggingface.co/Qwen/Qwen3-Coder-30B-A3B-Instruct"},{"category":"coding","modelId":"qwen-coder","variantId":"qwen-coder-qwen25-7b","name":"Код / самоулучшение NOX","variant":"Qwen2.5 Coder 7B","source":"https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct"},{"category":"coding","modelId":"qwen-coder","variantId":"qwen-coder-qwen25-32b","name":"Код / самоулучшение NOX","variant":"Qwen2.5 Coder 32B","source":"https://huggingface.co/Qwen/Qwen2.5-Coder-32B-Instruct"},{"category":"coding","modelId":"qwen-coder","variantId":"qwen-coder-qwen3-30b","name":"Код / самоулучшение NOX","variant":"Qwen3 Coder 30B-A3B","source":"https://huggingface.co/Qwen/Qwen3-Coder-30B-A3B-Instruct"},{"category":"coding","modelId":"qwen-coder","variantId":"qwen-coder-qwen3-next","name":"Код / самоулучшение NOX","variant":"Qwen3 Coder Next","source":"https://huggingface.co/Qwen/Qwen3-Coder-Next"},{"category":"coding","modelId":"deepseek-code","variantId":"deepseek-code-lite","name":"DeepSeek · код","variant":"Coder V2 Lite","source":"https://huggingface.co/deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct"},{"category":"coding","modelId":"deepseek-code","variantId":"deepseek-code-r1-7b","name":"DeepSeek · код","variant":"R1 Distill Qwen 7B","source":"https://huggingface.co/deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"},{"category":"agents","modelId":"agent-llm","variantId":"agent-llm-qwen4b","name":"Агенты · планирование и инструменты","variant":"Qwen3 4B Instruct","source":"https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507"},{"category":"agents","modelId":"agent-llm","variantId":"agent-llm-qwen30a3b","name":"Агенты · планирование и инструменты","variant":"Qwen3 30B-A3B Instruct","source":"https://huggingface.co/Qwen/Qwen3-30B-A3B-Instruct-2507"},{"category":"agents","modelId":"agent-llm","variantId":"agent-llm-gemma4b","name":"Агенты · планирование и инструменты","variant":"Gemma 3 4B It","source":"https://huggingface.co/google/gemma-3-4b-it"},{"category":"learning","modelId":"teacher","variantId":"teacher-qwen4b","name":"Локальное обучение · наставник","variant":"Qwen3 4B Instruct","source":"https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507"},{"category":"learning","modelId":"teacher","variantId":"teacher-qwen8b","name":"Локальное обучение · наставник","variant":"Qwen3 8B","source":"https://huggingface.co/Qwen/Qwen3-8B"},{"category":"learning","modelId":"teacher","variantId":"teacher-deepseek7b","name":"Локальное обучение · наставник","variant":"DeepSeek-R1 Distill Qwen 7B","source":"https://huggingface.co/deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"},{"category":"translate","modelId":"nllb","variantId":"nllb-600m","name":"Перевод · NLLB","variant":"NLLB 200 · 600M","source":"https://huggingface.co/facebook/nllb-200-distilled-600M"},{"category":"translate","modelId":"nllb","variantId":"nllb-13b","name":"Перевод · NLLB","variant":"NLLB 200 · 1.3B","source":"https://huggingface.co/facebook/nllb-200-distilled-1.3B"},{"category":"translate","modelId":"whisper-translate","variantId":"whisper-translate-small","name":"Речь → текст/перевод","variant":"Whisper Small","source":"https://huggingface.co/openai/whisper-small"},{"category":"translate","modelId":"whisper-translate","variantId":"whisper-translate-medium","name":"Речь → текст/перевод","variant":"Whisper Medium","source":"https://huggingface.co/openai/whisper-medium"},{"category":"research","modelId":"research-rag","variantId":"research-rag-bge-m3","name":"Исследования · RAG","variant":"BGE M3","source":"https://huggingface.co/BAAI/bge-m3"},{"category":"research","modelId":"research-rag","variantId":"research-rag-qwen-embed","name":"Исследования · RAG","variant":"Qwen3 Embedding 0.6B","source":"https://huggingface.co/Qwen/Qwen3-Embedding-0.6B"},{"category":"research","modelId":"research-rag","variantId":"research-rag-rerank","name":"Исследования · RAG","variant":"Qwen3 Reranker 0.6B","source":"https://huggingface.co/Qwen/Qwen3-Reranker-0.6B"},{"category":"tools","modelId":"utility","variantId":"utility-layout","name":"Инструменты ИИ · анализ документов","variant":"LayoutLMv3 Base","source":"https://huggingface.co/microsoft/layoutlmv3-base"},{"category":"tools","modelId":"utility","variantId":"utility-vl3b","name":"Инструменты ИИ · анализ документов","variant":"Qwen 2.5 VL 3B","source":"https://huggingface.co/Qwen/Qwen2.5-VL-3B-Instruct"},{"category":"behavior","modelId":"behavior-minilm","variantId":"multilingual-nli-fast","name":"MiniLM · контекст речи и намерения","variant":"Многоязычная NLI · лёгкая","source":"https://huggingface.co/MoritzLaurer/multilingual-MiniLMv2-L6-mnli-xnli"},{"category":"behavior","modelId":"behavior-deberta","variantId":"multilingual-nli-deberta","name":"mDeBERTa · смысл фраз","variant":"Многоязычная NLI · качество","source":"https://huggingface.co/MoritzLaurer/mDeBERTa-v3-base-mnli-xnli"},{"category":"behavior","modelId":"behavior-irony","variantId":"irony-roberta","name":"RoBERTa · ирония","variant":"Анализ иронии текста EN","source":"https://huggingface.co/cardiffnlp/twitter-roberta-base-irony"},{"category":"behavior","modelId":"behavior-toxicity","variantId":"detoxify-toxic-bert","name":"Detoxify · токсичность","variant":"Токсичная лексика","source":"https://huggingface.co/unitary/toxic-bert"},{"category":"emotions","modelId":"emotion-hartmann","variantId":"distilroberta-7","name":"Emotion RoBERTa · 7 эмоций","variant":"Английский текст","source":"https://huggingface.co/j-hartmann/emotion-english-distilroberta-base"},{"category":"emotions","modelId":"emotion-wav2vec","variantId":"superb-er","name":"SUPERB Wav2Vec2 · речь","variant":"4 эмоции по голосовому фрагменту","source":"https://huggingface.co/superb/wav2vec2-base-superb-er"},{"category":"emotions","modelId":"emotion-speechbrain","variantId":"iemocap-wav2vec","name":"SpeechBrain · эмоции речи","variant":"IEMOCAP, английский","source":"https://huggingface.co/speechbrain/emotion-recognition-wav2vec2-IEMOCAP"},{"category":"politics","modelId":"political-stance","variantId":"xstance-mdeberta","name":"Stance XStance · отношение к тезису","variant":"Многоязычные favor/against","source":"https://huggingface.co/MatteoFasulo/mdeberta-v3-xstance"},{"category":"politics","modelId":"political-stance","variantId":"xstance-xlmr","name":"Stance XStance · XLM-R","variant":"Сравнение аргументов","source":"https://huggingface.co/MatteoFasulo/xlm-roberta-xstance"},{"category":"politics","modelId":"political-stance","variantId":"newsbias-roberta","name":"EchoCheck · новостные материалы","variant":"Заявленная политическая окраска статей","source":"https://huggingface.co/alxdev/echocheck-political-stance"},{"category":"politics","modelId":"political-analysis","variantId":"politics-pretrain","name":"POLITICS · тематические статьи","variant":"Предобучение, требует fine-tuning","source":"https://huggingface.co/launch/POLITICS"},{"category":"politics","modelId":"political-analysis","variantId":"news-bias-distilbert","name":"News Bias DistilBERT","variant":"Классификация текстов СМИ","source":"https://huggingface.co/rijulpaul/news-political-bias"},{"category":"orientation","modelId":"preference-nli","variantId":"preferences-mini","name":"Личные настройки · быстрая NLI","variant":"Намерения/предпочтения из предоставленного текста","source":"https://huggingface.co/MoritzLaurer/multilingual-MiniLMv2-L6-mnli-xnli"},{"category":"orientation","modelId":"preference-nli","variantId":"preferences-large","name":"Личные настройки · mDeBERTa","variant":"Самоописание и контекст","source":"https://huggingface.co/MoritzLaurer/mDeBERTa-v3-base-mnli-xnli"},{"category":"orientation","modelId":"preference-llm","variantId":"preferences-qwen3","name":"Личные настройки · Qwen3","variant":"Диалог с управляемыми предпочтениями","source":"https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507"}].map(x=>Object.freeze(x)));
const TABS=Object.freeze([{"id":"3d","title":"3D / Миры"},{"id":"video","title":"Видео / Кино"},{"id":"photo","title":"Фото / Изображения"},{"id":"persona","title":"Личность ИИ"},{"id":"emotions","title":"Эмоции"},{"id":"memory","title":"Память / RAG"},{"id":"thread","title":"Нить разговора"},{"id":"voice","title":"Голос / Речь"},{"id":"vision","title":"Зрение"},{"id":"slides","title":"Презентации"},{"id":"websites","title":"Создание сайтов"},{"id":"coding","title":"Программирование"},{"id":"agents","title":"Агенты"},{"id":"learning","title":"Саморазвитие"},{"id":"translate","title":"Перевод"},{"id":"research","title":"Исследования"},{"id":"tools","title":"Документы / Инструменты"},{"id":"behavior","title":"Поведение / Общение"},{"id":"politics","title":"Политика / Аргументы"},{"id":"orientation","title":"Предпочтения / Ориентиры"}].map(x=>Object.freeze(x)));
const byVariant=new Map(VARIANTS.map(x=>[x.variantId,x]));
const byCategory=new Map(TABS.map(x=>[x.id,x]));
const HASH=/^[a-f0-9]{64}$/i,COMMIT=/^[a-f0-9]{40}$/i;
const state={approved:new Map(),jobs:new Map(),capabilities:{},pending:new Map(),hostReady:false,lastError:null};
const mounts=new Set();
const el=(tag,cls,label)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(label!==undefined)n.textContent=String(label);return n;};
const fmt=n=>typeof n==="number"&&Number.isFinite(n)&&n>=0?(n/1073741824).toLocaleString("ru-RU",{maximumFractionDigits:2})+" ГБ":"Н/Д";
function verified(meta,variant){
 return !!meta&&meta.variantId===variant.variantId&&meta.modelId===variant.modelId&&
 meta.installable===true&&meta.licenseVerified===true&&
 typeof meta.immutableRevision==="string"&&COMMIT.test(meta.immutableRevision)&&
 HASH.test(meta.manifestSha256||"")&&typeof meta.expectedBytes==="number"&&meta.expectedBytes>0;
}
function jobFor(key){return state.jobs.get(key)||null;}
function makeLink(entry){
 const a=el("a","p03-media-source","Источник / веса");
 a.href=entry.source;a.target="_blank";a.rel="noopener noreferrer";return a;
}
function available(kind){return VARIANTS.filter(x=>x.category===kind);}
function canSend(action,v,rights){
 if(!state.hostReady||!v||state.pending.has(v.variantId))return false;
 if(action==="prepare")return state.capabilities.prepare===true;
 if(action==="download")return state.capabilities.download===true&&rights&&verified(state.approved.get(v.variantId),v);
 if(action==="cancel")return state.capabilities.cancel===true&&!!jobFor(v.variantId)?.jobId;
 return false;
}
function send(action,v,rights){
 if(!canSend(action,v,rights))return false;
 const job=jobFor(v.variantId);
 const cid="p03m"+Date.now().toString(36)+Math.random().toString(36).slice(2,8);
 const command={type:"p03.media.command.v1",commandId:cid,action,
  modelId:v.modelId,variantId:v.variantId,licenseAcknowledged:rights,jobId:action==="cancel"?job.jobId:null};
 state.pending.set(v.variantId,action);
 renderAll();
 try{
  global.chrome.webview.postMessage(command);
  return true;
 }catch{
  state.pending.delete(v.variantId);state.lastError="HOST_NOT_CONNECTED";renderAll();return false;
 }
}
function renderVariant(v,rights){
 const j=jobFor(v.variantId),meta=state.approved.get(v.variantId);
 const card=el("article","p03-media-card");
 card.dataset.variantId=v.variantId;
 const heading=el("div","p03-media-card-head");
 heading.append(el("strong","",v.name),el("small","",v.category.toUpperCase()));
 card.append(heading,el("p","p03-media-variant",v.variant));
 const confirmed=verified(meta,v),inProgress=j&&["Queued","Downloading","Running"].includes(j.state);
 let status="ТРЕБУЕТСЯ ПРОВЕРКА ВЕСОВ";
 if(inProgress)status="ЗАГРУЗКА · "+(j.state||"Н/Д");
 else if(j?.state==="Completed"&&j.installedVerified===true)status="УСТАНОВЛЕНО · SHA ПРОВЕРЕН";
 else if(confirmed)status="ВЕСА ПРОВЕРЕНЫ · ГОТОВО";
 const s=el("p","p03-media-state",status);
 card.append(s,el("small","p03-media-size","Размер: "+fmt(meta?.expectedBytes)));
 if(inProgress&&typeof j.completedBytes==="number"&&typeof j.totalBytes==="number"&&j.totalBytes>0){
  const bar=el("progress","p03-media-progress");
  bar.max=j.totalBytes;bar.value=Math.min(Math.max(0,j.completedBytes),j.totalBytes);card.append(bar);
  card.append(el("small","p03-media-progress-text",fmt(j.completedBytes)+" / "+fmt(j.totalBytes)));
 }
 const actions=el("div","p03-media-ops");
 const download=el("button","p03-media-get","Скачать "+v.variant);
 download.type="button";download.dataset.variant=v.variantId;
 download.disabled=!canSend("download",v,rights)||!!inProgress;
 download.title=download.disabled?"Host должен подтвердить ревизию, SHA, права и место на диске":"Начать отдельную загрузку "+v.variantId;
 download.addEventListener("click",()=>send("download",v,rights));
 actions.append(download);
 if(!confirmed){
  const prepare=el("button","p03-media-prepare","Проверить веса");
  prepare.type="button";prepare.dataset.variant=v.variantId;
  prepare.disabled=!canSend("prepare",v,rights);
  prepare.addEventListener("click",()=>send("prepare",v,rights));
  actions.append(prepare);
 }
 if(inProgress){
  const stop=el("button","p03-media-stop","Отменить");
  stop.type="button";stop.dataset.variant=v.variantId;stop.disabled=!canSend("cancel",v,rights);
  stop.addEventListener("click",()=>send("cancel",v,rights));actions.append(stop);
 }
 card.append(actions,makeLink(v));
 return card;
}
function renderMount(view){
 if(!view.root?.isConnected&&view.root!==document.getElementById("mediaWeightsMount"))return;
 const q=(view.query.value||"").trim().toLocaleLowerCase();
 const tabs=view.tabRoot;tabs.replaceChildren();
 for(const c of TABS){
  const count=available(c.id).length;
  const btn=el("button","p03-media-tab",c.title+" · "+count);
  btn.type="button";btn.dataset.category=c.id;btn.setAttribute("aria-pressed",String(c.id===view.category));
  btn.addEventListener("click",()=>{view.category=c.id;view.query.value="";renderMount(view)});
  tabs.append(btn);
 }
 view.grid.replaceChildren();
 const chosen=available(view.category).filter(v=>!q||
  [v.name,v.variant,v.variantId,v.source].some(x=>x.toLocaleLowerCase().includes(q)));
 view.count.textContent=chosen.length+" вариантов весов";
 const groups=new Map();
 for(const v of chosen){if(!groups.has(v.modelId))groups.set(v.modelId,[]);groups.get(v.modelId).push(v)}
 for(const [modelId,variants] of groups){
  const group=el("section","p03-media-family");group.dataset.model=modelId;
  group.append(el("h4","p03-media-family-title",variants[0].name));
  const list=el("div","p03-media-grid");
  for(const v of variants)list.append(renderVariant(v,view.checkbox.checked));
  group.append(list);view.grid.append(group);
 }
 if(!chosen.length)view.grid.append(el("p","p03-media-empty","Нет моделей по запросу."));
 view.status.textContent=state.hostReady?
  "Подключён Windows host. Каждая загрузка имеет свой идентификатор и прогресс.":
  "Каталог готов. Реальное скачивание ждёт подключения Model Center к Windows host.";
 if(state.lastError)view.status.textContent+=" · "+state.lastError;
}
function renderAll(){for(const v of mounts)renderMount(v)}
function mount(root,{category="3d",showAllTabs=true}={}){
 if(!root||root.nodeType!==1||(typeof root.closest==="function"&&root.closest('[data-nox-page="home"]')))
  throw Error("D02_HOME_LOCK");
 if(root.dataset.noxMediaWeightsMounted==="true")throw Error("MEDIA_WEIGHTS_ALREADY_MOUNTED");
 if(!byCategory.has(category))throw Error("UNKNOWN_WEIGHT_CATEGORY");
 root.dataset.noxMediaWeightsMounted="true";
 root.classList.add("p03-media-section");
 const header=el("div","p03-media-heading");
 const titles=el("div");
 titles.append(el("div","eyebrow","NOX MODEL CENTER / WEIGHTS"),el("h3","","БИБЛИОТЕКА МОДЕЛЕЙ И ВЕСОВ"));
 const description=el("p","p03-media-hint","Разные модели и варианты весов: фото, видео, 3D, эмоции, личность, память, код и другое. Скачивание только в существующий Windows host с проверкой файлов.");
 header.append(titles,description);
 const control=el("div","p03-media-control");
 const input=el("input","p03-media-search");input.type="search";input.placeholder="Поиск по моделям и весам";input.setAttribute("aria-label","Поиск весов");
 control.append(input);
 const count=el("span","p03-media-count");
 control.append(count);
 const tabRoot=el("nav","p03-media-tabs");tabRoot.setAttribute("aria-label","Разделы библиотеки");
 if(!showAllTabs)tabRoot.hidden=true;
 const right=el("label","p03-media-rights");const check=el("input");check.type="checkbox";right.append(check,document.createTextNode(" Подтверждаю право скачивать и использовать выбранные веса"));
 const grid=el("div","p03-media-families");
 const status=el("output","p03-media-status");status.setAttribute("aria-live","polite");
 root.append(header,control,tabRoot,right,grid,status);
 const view={root,category,tabRoot,grid,status,checkbox:check,query:input,count};
 const onChange=()=>renderMount(view);
 input.addEventListener("input",onChange);check.addEventListener("change",onChange);
 mounts.add(view);renderMount(view);
 return Object.freeze({select(next){if(!byCategory.has(next))throw Error("UNKNOWN_WEIGHT_CATEGORY");view.category=next;renderMount(view)},
  current(){return view.category},count(){return available(view.category).length},
  destroy(){mounts.delete(view);input.removeEventListener("input",onChange);check.removeEventListener("change",onChange);
   root.replaceChildren();delete root.dataset.noxMediaWeightsMounted;root.classList.remove("p03-media-section")}})
}
function onHostMessage(data){
 if(!data||typeof data!=="object")return;
 if(data.type==="p03.media.snapshot.v1"){
  if(!Array.isArray(data.models)||data.models.length>300)return;
  state.approved=new Map(data.models.filter(m=>m&&byVariant.has(m.variantId)).map(m=>[m.variantId,m]));
  state.jobs=new Map((Array.isArray(data.jobs)?data.jobs:[]).filter(j=>j&&byVariant.has(j.variantId)).map(j=>[j.variantId,j]));
  state.hostReady=true;state.capabilities=data.capabilities&&typeof data.capabilities==="object"?data.capabilities:{};
  renderAll();
 }else if(data.type==="p03.media.progress.v1"&&data.job&&byVariant.has(data.job.variantId)){
  state.jobs.set(data.job.variantId,data.job);renderAll();
 }else if(data.type==="p03.media.ack.v1"&&byVariant.has(data.variantId)){
  state.pending.delete(data.variantId);state.lastError=data.accepted===true?null:"Host: "+String(data.reason||"отказано").slice(0,70);renderAll();
 }
}
if(global.chrome?.webview?.addEventListener)global.chrome.webview.addEventListener("message",e=>onHostMessage(e.data));
global.NoxMediaWeights=Object.freeze({mount,models:VARIANTS,categories:TABS.map(x=>x.id)});
document.addEventListener("DOMContentLoaded",()=>{
 const root=document.getElementById("mediaWeightsMount");
 if(root&&root.dataset.noxMediaWeightsMounted!=="true")mount(root);
});
})(window);
