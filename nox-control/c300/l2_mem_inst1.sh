echo "K1: l2_mem_inst1"
N=/workspace/nox; V=$N/venv_mem
df -h /workspace | tail -1
[ -x $V/bin/python ] || python3 -m venv $V
$V/bin/pip install -q --disable-pip-version-check mem0ai sqlite-vec requests 2>&1 | tail -3
$V/bin/pip list 2>/dev/null | grep -i -E "mem0|sqlite|qdrant|openai|pydantic|numpy|posthog"
$V/bin/python - <<'PY'
import importlib.metadata as m
md=m.metadata("mem0ai"); print("license:",md.get("License"), [c for c in md.get_all("Classifier") or [] if "License" in c])
print("version",m.version("mem0ai"))
PY
M=$($V/bin/python -c "import mem0,os;print(os.path.dirname(mem0.__file__))"); echo $M
echo "--- vs base"; grep -n -E "^\s+def |^class |abstractmethod" $M/vector_stores/base.py
echo "--- factory"; grep -n -E "class |provider_to_class|\"[a-z_]+\":" $M/utils/factory.py | head -90
echo "--- emb base"; sed -n 1,60p $M/embeddings/base.py
echo "--- llm base"; grep -n -E "def |class " $M/llms/base.py
echo "--- prompts"; grep -n -E "^[A-Z_]+ ?=|^def " $M/configs/prompts.py
echo "--- memory.add"; grep -n -E "def add|def search|def delete|def get_all|def _add_to_vector_store|def update" $M/memory/main.py | head
