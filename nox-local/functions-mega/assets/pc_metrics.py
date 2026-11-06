"""Read-only local Windows telemetry, including AMD GPU if Windows perf counters exist.
No invented values. No external network calls. Does not control training or hardware.
"""
from __future__ import annotations
import ctypes, json, subprocess, time, shutil, os, re
from ctypes import wintypes

class MEMORYSTATUSEX(ctypes.Structure):
    _fields_=[('dwLength',wintypes.DWORD),('dwMemoryLoad',wintypes.DWORD),('ullTotalPhys',ctypes.c_ulonglong),('ullAvailPhys',ctypes.c_ulonglong),('ullTotalPageFile',ctypes.c_ulonglong),('ullAvailPageFile',ctypes.c_ulonglong),('ullTotalVirtual',ctypes.c_ulonglong),('ullAvailVirtual',ctypes.c_ulonglong),('ullAvailExtendedVirtual',ctypes.c_ulonglong)]

_last=(0,{})
def _powershell(script, timeout=4):
    flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
    r=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,encoding='utf-8',errors='replace',creationflags=flags,timeout=timeout)
    return r.stdout.strip() if r.returncode==0 else ''

def read():
    global _last
    now=time.monotonic()
    if now-_last[0]<5:return _last[1]
    data={'cpu_percent':None,'ram_percent':None,'gpu_percent':None,'gpu_source':None,'vram_used_gb':None,'vram_total_gb':None,'gpu_temperature_c':None,'gpu_power_w':None,'cpu_temperature_c':None,'ram_total_gb':None,'ram_used_gb':None,'source':'Windows local; no simulated readings','timestamp':time.time()}
    try:
        m=MEMORYSTATUSEX();m.dwLength=ctypes.sizeof(m)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
            data['ram_percent']=int(m.dwMemoryLoad)
            data['ram_total_gb']=round(m.ullTotalPhys/1073741824,2)
            data['ram_used_gb']=round((m.ullTotalPhys-m.ullAvailPhys)/1073741824,2)
    except Exception: pass
    try:
        val=_powershell('(Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average')
        if val:data['cpu_percent']=round(float(val.replace(',','.')),1)
    except Exception:pass
    # NVIDIA metrics if nvidia-smi is available. Never assume discrete NVIDIA present.
    exe=shutil.which('nvidia-smi')
    if not exe:
        path=r'C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe'
        if os.path.isfile(path):exe=path
    if exe:
        try:
            flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
            r=subprocess.run([exe,'--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=3,creationflags=flags)
            if r.returncode==0:
                vals=r.stdout.strip().splitlines()[0].split(',')
                def num(s):
                    try:return float(s.strip())
                    except Exception:return None
                numbers=list(map(num,vals[:5]));gpu,used,total,temp,power=numbers
                data.update(gpu_percent=gpu,vram_used_gb=round(used/1024,2) if used is not None else None,vram_total_gb=round(total/1024,2) if total is not None else None,gpu_temperature_c=temp,gpu_power_w=power,gpu_source='nvidia-smi')
        except Exception:pass
    # Windows GPU Engine performance counters include AMD Radeon 660M; they represent engine busy time, not exact total GPU utility.
    if data['gpu_percent'] is None:
        try:
            script=("$c=Get-Counter -Counter '\\GPU Engine(*)\\Utilization Percentage' -ErrorAction Stop; "
                    "$s=$c.CounterSamples | Where-Object {$_.InstanceName -match 'engtype_3D'}; "
                    "if($s){($s|Measure-Object -Property CookedValue -Sum).Sum}else{''}")
            val=_powershell(script,4)
            if val:
                n=float(val.replace(',','.'))
                if 0<=n<=100:
                    data['gpu_percent']=round(n,1)
                    data['gpu_source']='Windows GPU Engine 3D counter (estimate)'
        except Exception:pass
    _last=(now,data)
    return data