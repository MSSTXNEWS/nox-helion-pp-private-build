echo "K1: l2_recon4"
D=/workspace/nox/svc/living; ls -la $D | head -30; wc -l $D/*.py
f=$D/living_svc.py
grep -n -i -E "mem0|^def |^class |sqlite|8082|s03|\.db|recall|embed|remember|forget|/pre|/post" $f | head -120
$D/../../venv_living/bin/python -m pip list 2>/dev/null | grep -i -E "mem0|sqlite|numpy|faiss|chroma|qdrant|openai|pydantic|torch|onnx|transformers|sentence|requests|httpx|posthog"
find /workspace/nox/state -maxdepth 2 -iname "*mem*" 2>/dev/null | head; ls /workspace/nox/state/living 2>/dev/null | head -30
