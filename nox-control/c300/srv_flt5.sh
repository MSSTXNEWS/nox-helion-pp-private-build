#!/bin/bash
cat > /tmp/srv_flt_patch.py <<'PYEOF'
import sys,shutil,time,py_compile
F="/workspace/nox/distill_v2/code/distill_v2.py"
s=open(F,encoding="utf-8").read()
if "P3_FILTER" in s: print("already"); sys.exit(0)
shutil.copy(F,F+".bak_p3filter_%d"%int(time.time()))
helper='''
# P3_FILTER (26.11): выходы Claude и данные с некоммерческой лицензией (NC) в обучение не идут. Список: state/p3/train_blocklist.json (необязательный),
# лицензии HF: state/p3/hf_licenses.json. Откат: убрать вызов _p3_blocked в cmd_prep.
_P3_CLAUDE_RX = re.compile(r"(?i)claude|anthropic|\\bopus[-\\s]?\\d|\\bsonnet\\b|\\bhaiku[-\\s]?\\d")
_P3_SELFID_RX = re.compile(r"(?i)\\bI(?:'m| am) Claude\\b|\\bmade by Anthropic\\b|\\bcreated by Anthropic\\b|я\\s+(?:—\\s*)?Claude\\b|создан\\w*\\s+(?:компани\\w+\\s+)?Anthropic")
_P3_NC_RX = re.compile(r"(?i)-nc\\b|-nc-|noncomm|non-comm")
_P3_CACHE = {}
def _p3_lists():
    if not _P3_CACHE:
        bl = load_json("/workspace/nox/state/p3/train_blocklist.json", {}) or {}
        lic = load_json("/workspace/nox/state/p3/hf_licenses.json", {}) or {}
        nc = {k for k, v in lic.items() if _P3_NC_RX.search(json.dumps(v))} | set(bl.get("nc_datasets", []))
        _P3_CACHE.update(nc=nc, extra=[x.lower() for x in bl.get("deny_substrings", [])])
    return _P3_CACHE
def _p3_blocked(d):
    """Причина блокировки строки или None."""
    L = _p3_lists()
    meta = " ".join(str(d.get(k) or "") for k in ("origin", "teacher", "source", "model", "typ", "license", "lic", "id"))
    if _P3_CLAUDE_RX.search(meta): return "claude_meta"
    low = meta.lower()
    if any(x in low for x in L["extra"]): return "deny_list"
    ds = re.sub(r"^https?://huggingface\\.co/datasets/", "", str(d.get("origin") or "")).strip("/")
    if ds and ds in L["nc"]: return "nc_dataset"
    if _P3_NC_RX.search(str(d.get("license") or d.get("lic") or "")): return "nc_license"
    for k, v in d.items():
        if k in ("prompt", "user") or not isinstance(v, str): continue
        if _P3_SELFID_RX.search(v[:20000]): return "claude_selfid"
    return None
'''
a="def cmd_prep(a):"
assert s.count(a)==1
s=s.replace(a,helper+"\n"+a,1)
old='''        if d["key"] in excluded_keys:
            stats["verified_language_excluded"] += 1
            continue
'''
assert s.count(old)==1
new=old+'''        _pb = _p3_blocked(d)  # P3_FILTER
        if _pb:
            stats["p3_excluded_" + _pb] += 1
            continue
'''
s=s.replace(old,new,1)
open(F,"w",encoding="utf-8").write(s); py_compile.compile(F,doraise=True); print("patched")
PYEOF
cd /workspace/nox/distill_v2/code
grep -n -E "^import|^from" distill_v2.py | head -12 | tr '\n' ' '; echo
python3 -I /tmp/srv_flt_patch.py || exit 1
cp /workspace/nox/distill_v2/code/distill_v2.py /tmp/dv2_test.py
python3 -I - <<'PY'
import re,json,sys,types
src=open("/workspace/nox/distill_v2/code/distill_v2.py",encoding="utf-8").read()
i=src.index("# P3_FILTER (26.11)"); j=src.index("def cmd_prep(a):")
def load_json(p,d=None):
    try: return json.load(open(p))
    except Exception: return d
ns={"re":re,"json":json,"load_json":load_json}
exec(src[i:j],ns)
b=ns["_p3_blocked"]
tests=[({"origin":"https://huggingface.co/datasets/nvidia/Nemotron-Agentic-v1","answer":"ok"},None),
({"teacher":"claude-opus-4.5","answer":"x"},"claude_meta"),({"source":"ready:Crownelius/Opus-4.5-Reasoning"},"claude_meta"),
({"answer":"I'm Claude, made by Anthropic."},"claude_selfid"),({"license":"cc-by-nc-4.0"},"nc_license"),
({"prompt":"что такое Claude?","answer":"модель"},None),({"teacher":"ready:empathy__x","answer":"привет"},None)]
for d,exp in tests: print(b(d),exp,"OK" if b(d)==exp else "FAIL")
print("nc list size",len(ns["_p3_lists"]()["nc"]))
PY
