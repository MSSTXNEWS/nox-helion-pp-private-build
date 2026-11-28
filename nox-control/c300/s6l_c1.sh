echo "K1: s6l_c1"
python3 -I - <<'PY'
import json,urllib.request,urllib.parse
def get(u): return json.loads(urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"nox-s6/1"}),timeout=40).read())
for ds in ["DataCreatorAI/Anti-Sycophancy-DPO","Hooshaai/aegis-anti-sycophancy","camgeodesic/sycophancy-anti-inoculation-data_03_16","swzzzzc/Anti-Sycophancy-RepE-384","limloop/characters_dialogs","IlyaGusev/gpt_roleplay_realm"]:
    try:
        info=get("https://huggingface.co/api/datasets/"+ds); lic=[t[8:] for t in info.get("tags",[]) if t.startswith("license:")]
        sp=get("https://datasets-server.huggingface.co/splits?dataset="+urllib.parse.quote(ds))["splits"][0]
        d=get("https://datasets-server.huggingface.co/rows?"+urllib.parse.urlencode({"dataset":ds,"config":sp["config"],"split":sp["split"],"offset":0,"length":2}))
        cols=[(f["name"],f["type"].get("dtype") if isinstance(f["type"],dict) else "?") for f in d["features"]]
        r=d["rows"][0]["row"]
        print(ds,lic,sp["split"],"rows",d.get("num_rows_total"),"cols",cols)
        print("   lens",{k:(len(v) if isinstance(v,(str,list)) else v) for k,v in r.items()})
    except Exception as e: print(ds,"err",repr(e)[:80])
PY
echo END
