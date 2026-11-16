#!/usr/bin/env python3
"""Isolated CPU-only browser acceptance for the existing authenticated NOX chat."""
import base64,hashlib,json,os,re,shutil,subprocess,sys,tempfile,time
from pathlib import Path
try:BUNDLE=__NOX_BUNDLE_JSON__
except NameError:BUNDLE={}
ROOT=Path('/root/nox');AREA=ROOT/'browser_qa'
# Full source hash is checked before any package operation.
PIN='2033a533268c06f4f0ff25a44f6e635db704fc20e6bbc6ba7f077a8265cc0bad'
def emit(kind,data):print('NOX_MAINT_REPAIR='+json.dumps({'kind':kind,'data':data},separators=(',',':')),flush=True)
def run(argv,env,timeout,tag):
 proc=subprocess.run(argv,env=env,capture_output=True,timeout=timeout)
 if proc.returncode:
  path=AREA/('install_'+tag.lower()+'_'+os.environ.get('NOX_OWNER_REQUEST_ID','unknown')+'.log')
  fd=os.open(path,os.O_CREAT|os.O_WRONLY|os.O_TRUNC|os.O_NOFOLLOW,0o600)
  with os.fdopen(fd,'wb') as output:output.write((proc.stdout+b'\n'+proc.stderr)[-100000:])
  raise RuntimeError('HOLD_BROWSER_'+tag+'_EXIT_'+str(proc.returncode))
 return proc.stdout
def main():
 request=os.environ.get('NOX_OWNER_REQUEST_ID','');source=os.environ.get('NOX_OWNER_SOURCE_SHA','')
 if not request.isdigit() or not re.fullmatch('[a-f0-9]{40}',source):raise RuntimeError('HOLD_OWNER_CONTEXT')
 raw=base64.b64decode(BUNDLE.get('owner_chat_browser_qa.py',''),validate=True)
 if hashlib.sha256(raw).hexdigest()!=PIN:raise RuntimeError('HOLD_BROWSER_SOURCE_PIN')
 compile(raw,'owner_chat_browser_qa.py','exec')
 if any((ROOT/name).exists() for name in ('STOP','STOP.flag','stop.flag','.stop','state/STOP')):raise RuntimeError('HOLD_OWNER_STOP')
 if shutil.disk_usage(ROOT).free<7*1024**3:raise RuntimeError('HOLD_BROWSER_DISK_RESERVE')
 if int(Path('/sys/fs/cgroup/memory.max').read_text())-int(Path('/sys/fs/cgroup/memory.current').read_text())<4*1024**3:raise RuntimeError('HOLD_BROWSER_RAM_RESERVE')
 if AREA.is_symlink():raise RuntimeError('HOLD_BROWSER_PATH')
 AREA.mkdir(mode=0o700,exist_ok=True)
 marker=AREA/'owner-environment.json';venv=AREA/'venv';python=venv/'bin/python'
 spec={'schema':'NOX_OWNER_BROWSER_ENV_V1','playwright':'1.65.2','base_python':'/root/nox/venv/bin/python','torch_modified':False}
 if marker.exists():
  if marker.is_symlink() or json.loads(marker.read_text())!=spec:raise RuntimeError('HOLD_BROWSER_ENV_SCOPE')
 elif venv.exists():raise RuntimeError('HOLD_BROWSER_UNKNOWN_VENV')
 env={**os.environ,'CUDA_VISIBLE_DEVICES':'','PIP_DISABLE_PIP_VERSION_CHECK':'1','PIP_NO_CACHE_DIR':'1',
      'PYTHONNOUSERSITE':'1','PLAYWRIGHT_BROWSERS_PATH':str(AREA/'browsers'),'PYTHONDONTWRITEBYTECODE':'1'}
 if not python.exists():
  run([spec['base_python'],'-m','venv',str(venv)],env,90,'VENV')
  marker.write_text(json.dumps(spec));marker.chmod(0o600)
 purelib=run([str(python),'-c','import sysconfig;print(sysconfig.get_path("purelib"))'],env,15,'PURELIB').decode().strip()
 if not Path(purelib).is_relative_to(venv):raise RuntimeError('HOLD_BROWSER_PURELIB_SCOPE')
 shared=run([spec['base_python'],'-c','import sysconfig;print(sysconfig.get_path("purelib"))'],env,15,'SHARED').decode().strip()
 if not shared.startswith('/root/nox/venv/lib/'):raise RuntimeError('HOLD_BROWSER_SHARED_SCOPE')
 pth=Path(purelib)/'nox_existing_proxy.pth'
 if pth.is_symlink():raise RuntimeError('HOLD_BROWSER_PTH_PATH')
 pth.write_text(shared+'\n')
 emit('browser_preparation',{'state':'INSTALLING_ISOLATED_BROWSER','cuda_visible_devices':'','training_environment_modified':False})
 env['PIP_REQUIRE_VIRTUALENV']='1'
 run([str(python),'-m','pip','install','--index-url','https://pypi.org/simple','--only-binary=:all:','playwright==1.65.2'],env,180,'PACKAGE')
 if not any(shutil.which(name) for name in ('chromium','chromium-browser','google-chrome','google-chrome-stable')):
  run([str(python),'-m','playwright','install','--only-shell','chromium'],env,240,'CHROMIUM')
 proc=subprocess.run([str(python),'-'],input=raw,env=env,capture_output=True,timeout=175)
 for line in proc.stdout.decode(errors='replace').splitlines():
  if line.startswith('NOX_MAINT_') and len(line)<100000:print(line,flush=True)
 if proc.returncode:raise RuntimeError('HOLD_BROWSER_NATIVE_ACCEPTANCE')
 print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
if __name__=='__main__':
 try:main()
 except Exception as exc:
  text=str(exc);emit('browser_entry_hold',{'reason':text if re.fullmatch('HOLD_[A-Z0-9_]+',text) else type(exc).__name__});raise SystemExit(2)
