#!/usr/bin/env python3
"""Read-only versions inventory for existing NOX CUDA/Volta trainer. No pip, installs, or imports torch."""
import json, subprocess, importlib.metadata as md, sys, os
names=('torch','transformers','accelerate','peft','trl','bitsandbytes','deepspeed','unsloth','safetensors','numpy','psutil','watchdog')
versions={}
for name in names:
 try:versions[name]=md.version(name)
 except md.PackageNotFoundError:versions[name]='NOT_INSTALLED'
def run(cmd):
 try:
  p=subprocess.run(cmd,capture_output=True,text=True,timeout=7,check=False)
  return {'status':'OK' if p.returncode==0 else 'HOLD_NONZERO','out':p.stdout[:800] if p.returncode==0 else None}
 except (OSError,subprocess.TimeoutExpired):return {'status':'UNAVAILABLE'}
print(json.dumps({'schema':'NOX_V40_STACK_PREFLIGHT','python':sys.version.split()[0],
                  'packages':versions,'driver':run(['nvidia-smi','--query-gpu=name,compute_cap,driver_version','--format=csv,noheader']),
                  'nvcc':run(['nvcc','--version']),'install_executed':False,
                  'policy':'V100 SM70: keep compatible existing CUDA12 FP16 environment; do not upgrade drivers or restart trainer here.'},ensure_ascii=False,indent=2))
