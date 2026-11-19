#!/usr/bin/env python3
"""Read-only bounded listener census for serving NOX; no chat requests or secrets."""
import json,os,re,subprocess,sys,urllib.request,urllib.error
from pathlib import Path
SERVICES=("nox-proxy","nox-web29-18775","nox-ds41-8098","nox-dispatcher-t855u")
def emit(k,d):print("NOX_MAINT_INSPECT_"+k+"="+json.dumps(d,sort_keys=True,separators=(",",":")),flush=True)
def service(name):
    r=subprocess.run(["supervisorctl","status",name],capture_output=True,text=True,timeout=10)
    m=re.match(r"^"+re.escape(name)+r"\s+([A-Z]+)(?:\s+pid\s+(\d+))?",r.stdout.strip())
    return {"state":m[1] if m else "UNKNOWN","pid":int(m[2]) if m and m[2] else None}
def listens(pid):
    if not pid:return []
    sock=set()
    for fd in (Path("/proc")/str(pid)/"fd").iterdir():
        try:
            m=re.fullmatch(r"socket:\[(\d+)\]",os.readlink(fd))
            if m:sock.add(m[1])
        except (OSError,ValueError):pass
    ports=set()
    for table in ("/proc/net/tcp","/proc/net/tcp6"):
        for l in Path(table).read_text().splitlines()[1:]:
            p=l.split()
            if len(p)>9 and p[3]=="0A" and p[9] in sock:
                try:ports.add(int(p[1].split(":")[-1],16))
                except ValueError:pass
    return sorted(ports)[:20]
def get(url):
    req=urllib.request.Request(url,method="GET",headers={"User-Agent":"NOX-owner-readonly-port-check"})
    try:
        with urllib.request.urlopen(req,timeout=3) as r:return {"http":r.status}
    except urllib.error.HTTPError as e:return {"http":e.code}
    except Exception as e:return {"status":type(e).__name__}
def main():
    data={x:service(x) for x in SERVICES}
    for n,v in data.items():v["listeners"]=listens(v["pid"])
    emit("SERVICES",data)
    ports=sorted(set(x for p in data.values() for x in p["listeners"] if 1024<=x<=65535))
    ports=sorted(set(ports+[8081,8082,8098,18775,18877]))[:18]
    result={}
    for p in ports:
        result[str(p)]={"health":get(f"http://127.0.0.1:{p}/health"),
                        "status":get(f"http://127.0.0.1:{p}/api/nox/status")}
    result["web_chat"] = get("http://127.0.0.1:18775/nox-web-v29/chat.html")
    emit("HTTP",result)
    print("NOX_MAINT_INSPECT_COMPLETE=true",flush=True)
if __name__=="__main__":
    try:main()
    except Exception as exc:
        emit("HOLD",{"reason":type(exc).__name__});sys.exit(2)
