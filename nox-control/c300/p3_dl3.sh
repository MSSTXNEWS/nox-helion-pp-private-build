t(){ echo -n "$1 : "; curl -L -s -r 0-30000000 -o /dev/null --max-time 12 -w "%{http_code} %{size_download}B %{speed_download}B/s\n" "$2"; }
t hf https://huggingface.co/leejet/FLUX.1-schnell-gguf/resolve/main/flux1-schnell-q4_0.gguf
t hf-mirror https://hf-mirror.com/leejet/FLUX.1-schnell-gguf/resolve/main/flux1-schnell-q4_0.gguf
t hf-clip https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors
t modelscope "https://modelscope.cn/api/v1/models/AI-ModelScope/FLUX.1-schnell-gguf/repo?Revision=master&FilePath=flux1-schnell-q4_0.gguf"
t github-speed https://github.com/ggml-org/llama.cpp/archive/refs/heads/master.zip
ls -la /workspace/nox/models/flux | cut -c25-120; cat /workspace/nox/models/flux/dl2.log
