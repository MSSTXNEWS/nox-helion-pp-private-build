r"""NOX HELION temperature sensors: observed readings only.

Priority:
  1) LibreHardwareMonitor WMI (root\LibreHardwareMonitor)
  2) OpenHardwareMonitor WMI (root\OpenHardwareMonitor)
  3) NVIDIA nvidia-smi, for NVIDIA cards only.

No fictional readings. PowerShell CIM sensors require the respective sensor
utility to be running; AMD Adrenalin UI reading is NOT automatically exported.
Temperature is unavailable if all live sources fail. Fail closed for GPU
training unless a trusted, fresh reading exists.
"""
from __future__ import annotations
import json
import os
import subprocess

MAX_AGE_SECONDS=15

def _cim_sensors(namespace):
    # Constrain PowerShell to read-only fixed namespace and no downloaded scripts.
    if namespace not in ("root\\LibreHardwareMonitor","root\\OpenHardwareMonitor"):
        return []
    script=(
        "$ErrorActionPreference='Stop';"
        "Get-CimInstance -Namespace '"+namespace+"' -ClassName Sensor | "
        "Where-Object {$_.SensorType -eq 'Temperature'} | "
        "Select-Object Name,Identifier,Value,SensorType | ConvertTo-Json -Compress"
    )
    cmd=subprocess.run(["powershell.exe","-NoProfile","-NonInteractive","-Command",script],
                       capture_output=True,text=True,timeout=7,check=True)
    raw=cmd.stdout.strip()
    if not raw:return []
    parsed=json.loads(raw)
    return parsed if isinstance(parsed,list) else [parsed]

def _classify(row):
    name=str(row.get("Name",""))
    ident=str(row.get("Identifier",""))
    field=(name+" "+ident).lower()
    try: val=float(row.get("Value"))
    except (ValueError,TypeError):return None
    if not 0<=val<=115:return None
    gpu=(
        (("gpu" in field or "radeon" in field or "geforce" in field)
         and ("core" in field or "hot spot" in field or "hotspot" in field
              or "temperature" in ident.lower() or "gpu" in name.lower()))
    )
    cpu=("cpu" in field or "/intelcpu/" in field or "/amdcpu/" in field)
    if gpu:return ("gpu",val,name,ident)
    if cpu:return ("cpu",val,name,ident)
    return None

def temperature():
    """Current hardware sensor data; never infer GPU temperature from CPU/VRAM."""
    if os.name=="nt":
        for namespace in ("root\\LibreHardwareMonitor","root\\OpenHardwareMonitor"):
            try:
                rows=_cim_sensors(namespace)
            except (OSError,ValueError,subprocess.SubprocessError,json.JSONDecodeError):
                continue
            gpu=[];cpu=[]
            for row in rows:
                if not isinstance(row,dict):continue
                parsed=_classify(row)
                if parsed is None:continue
                typ,v,name,ident=parsed
                if typ=="gpu":gpu.append((v,name,ident))
                else:cpu.append((v,name,ident))
            if gpu:
                # Prefer core temperature, not VRAM/hotspot when available.
                core=[x for x in gpu if "core" in x[1].lower()]
                winner=max(core or gpu,key=lambda x:x[0])
                return {"gpu_c":winner[0],"cpu_c":max((x[0] for x in cpu),default=None),
                        "source":namespace,"gpu_sensor":winner[1],
                        "gpu_identifier":winner[2],"verified_live":True}
    try:
        p=subprocess.run(["nvidia-smi","--query-gpu=temperature.gpu",
                          "--format=csv,noheader,nounits"],capture_output=True,
                         text=True,timeout=5,check=True)
        values=[int(x.strip()) for x in p.stdout.splitlines() if x.strip().isdigit()]
        values=[x for x in values if 0<=x<=110]
        if values:
            return {"gpu_c":max(values),"cpu_c":None,"source":"nvidia-smi",
                    "gpu_sensor":"GPU core","gpu_identifier":None,"verified_live":True}
    except (OSError,ValueError,subprocess.SubprocessError):pass
    return {"gpu_c":None,"cpu_c":None,"source":"UNAVAILABLE",
            "gpu_sensor":None,"gpu_identifier":None,"verified_live":False}

if __name__=="__main__":
    print(json.dumps(temperature(),ensure_ascii=False))
