#!/usr/bin/env python3
"""Isolated CPU-only browser acceptance for the existing authenticated NOX chat."""
import base64,hashlib,json,os,pwd,re,shutil,stat,subprocess,sys,tempfile,time
from pathlib import Path
try:BUNDLE=__NOX_BUNDLE_JSON__
except NameError:BUNDLE={}
ROOT=Path('/root/nox');AREA=ROOT/'browser_qa'
APT_AREA=Path('/var/lib/nox-browser-qa-apt')
LIBRARY_PACKAGES={'libXcomposite.so.1':'libxcomposite1','libXdamage.so.1':'libxdamage1',
 'libatk-1.0.so.0':'libatk1.0-0','libatk-bridge-2.0.so.0':'libatk-bridge2.0-0','libatspi.so.0':'libatspi2.0-0'}
RUNTIME_PACKAGES=set(LIBRARY_PACKAGES.values())|{'libx11-6','libxext6','libxfixes3','libxi6','libxtst6',
 'libxrender1','libxau6','libxdmcp6','libxcb1','libdbus-1-3','libglib2.0-0','libatk1.0-data'}
UBUNTU_SOURCES=('deb [arch=amd64 signed-by=/usr/share/keyrings/ubuntu-archive-keyring.gpg] '
 'http://archive.ubuntu.com/ubuntu jammy main\n'
 'deb [arch=amd64 signed-by=/usr/share/keyrings/ubuntu-archive-keyring.gpg] '
 'http://archive.ubuntu.com/ubuntu jammy-updates main\n'
 'deb [arch=amd64 signed-by=/usr/share/keyrings/ubuntu-archive-keyring.gpg] '
 'http://security.ubuntu.com/ubuntu jammy-security main\n')
# Full source hash is checked before any package operation.
PIN='b76198d8117c3912fb7e1a1ef19c01abc41aa3ac87f4ad919612342edf593587'
def emit(kind,data):print('NOX_MAINT_REPAIR='+json.dumps({'kind':kind,'data':data},separators=(',',':')),flush=True)
def run(argv,env,timeout,tag):
 proc=subprocess.run(argv,env=env,capture_output=True,timeout=timeout)
 if proc.returncode:
  path=AREA/('install_'+tag.lower()+'_'+os.environ.get('NOX_OWNER_REQUEST_ID','unknown')+'.log')
  fd=os.open(path,os.O_CREAT|os.O_WRONLY|os.O_TRUNC|os.O_NOFOLLOW,0o600)
  with os.fdopen(fd,'wb') as output:output.write((proc.stdout+b'\n'+proc.stderr)[-100000:])
  raise RuntimeError('HOLD_BROWSER_'+tag+'_EXIT_'+str(proc.returncode))
 return proc.stdout
def plain(path):
 path=Path(path)
 for item in (*reversed(path.parents),path):
  if item.is_symlink():raise RuntimeError('HOLD_BROWSER_SYSTEM_PATH')
 return path
def browser_binary():
 candidates=[]
 for pattern in ('chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell',
                 'chromium-*/chrome-linux64/chrome'):
  candidates.extend((AREA/'browsers').glob(pattern))
 if len(candidates)>4:raise RuntimeError('HOLD_BROWSER_BINARY_COUNT')
 if not candidates:return None
 candidates.sort(key=lambda p:('headless' not in str(p),str(p)))
 target=plain(candidates[0]);info=target.stat()
 if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.geteuid():raise RuntimeError('HOLD_BROWSER_BINARY_OWNER')
 with target.open('rb') as stream:
  if stream.read(4)!=b'\x7fELF':raise RuntimeError('HOLD_BROWSER_BINARY_FORMAT')
 return target
def missing_libraries(binary,env):
 raw=run(['/usr/bin/ldd',str(binary)],env,12,'LINKER')
 if len(raw)>100000:raise RuntimeError('HOLD_BROWSER_LINKER_BUDGET')
 return sorted(set(re.findall(r'^\s*([A-Za-z0-9_.+-]+)\s+=>\s+not found\s*$',raw.decode(errors='replace'),re.M)))
def apt_plan(raw,requested):
 if len(raw)>200000 or re.search(rb'^Remv\s',raw,re.M):raise RuntimeError('HOLD_BROWSER_APT_REMOVAL_OR_SIZE')
 result=[]
 for line in raw.decode(errors='replace').splitlines():
  if not line.startswith('Inst '):continue
  match=re.fullmatch(r'Inst ([A-Za-z0-9+_.:-]+)(?: \[([^\]]+)\])? \(([^ ]+) [^\r\n]+\)',line)
  if not match:raise RuntimeError('HOLD_BROWSER_APT_PLAN_FORMAT')
  name,old,version=match.groups();name=name.removesuffix(':amd64')
  if name not in RUNTIME_PACKAGES or old is not None or not re.fullmatch(r'[A-Za-z0-9.+:~_-]{1,100}',version):
   raise RuntimeError('HOLD_BROWSER_APT_PACKAGE_OR_UPGRADE')
  result.append((name,version))
 if not 1<=len(result)<=16 or len({name for name,_ in result})!=len(result):raise RuntimeError('HOLD_BROWSER_APT_PLAN_COUNT')
 if not set(requested)<=set(name for name,_ in result):raise RuntimeError('HOLD_BROWSER_APT_MISSING_TARGET')
 return result
def apt_context():
 # A separate metadata/cache directory and explicit signed Ubuntu sources.
 # No existing repositories, trust policy or global APT configuration changes.
 data=Path('/etc/os-release').read_text()
 distro=dict((key,value.strip('"')) for key,value in re.findall(r'^([A-Z_]+)=(.*)$',data,re.M))
 if distro.get('ID')!='ubuntu' or distro.get('VERSION_ID')!='22.04':raise RuntimeError('HOLD_BROWSER_UBUNTU_VERSION')
 keyring=plain('/usr/share/keyrings/ubuntu-archive-keyring.gpg')
 if not keyring.is_file():raise RuntimeError('HOLD_BROWSER_UBUNTU_KEYRING')
 base=plain(APT_AREA)
 if base.exists():
  info=base.stat()
  if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.geteuid() or info.st_mode&0o022:raise RuntimeError('HOLD_BROWSER_APT_DIRECTORY')
 else:base.mkdir(mode=0o755)
 sources=plain(base/'sources.list')
 if sources.exists():
  if sources.read_text()!=UBUNTU_SOURCES:raise RuntimeError('HOLD_BROWSER_APT_SOURCE_CHANGED')
 else:
  fd=os.open(sources,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o644)
  with os.fdopen(fd,'w') as stream:stream.write(UBUNTU_SOURCES)
 apt_uid=pwd.getpwnam('_apt').pw_uid
 for name in ('lists','archives'):
  folder=plain(base/name);folder.mkdir(mode=0o755,exist_ok=True)
  info=folder.stat()
  if info.st_uid!=os.geteuid() or info.st_mode&0o022:raise RuntimeError('HOLD_BROWSER_APT_DIRECTORY')
  partial=plain(folder/'partial');partial.mkdir(mode=0o700,exist_ok=True)
  if partial.stat().st_uid not in (os.geteuid(),apt_uid):raise RuntimeError('HOLD_BROWSER_APT_PARTIAL_OWNER')
  os.chown(partial,apt_uid,-1)
 options=['-o','Dir::Etc::sourcelist='+str(sources),'-o','Dir::Etc::sourceparts=-',
  '-o','Dir::State::lists='+str(base/'lists'),'-o','Dir::Cache::archives='+str(base/'archives'),
  '-o','Acquire::Languages=none','-o','Acquire::Retries=0','-o','Acquire::http::Timeout=20',
  '-o','Acquire::https::Timeout=20','-o','DPkg::Lock::Timeout=15','-o','Dpkg::Use-Pty=0']
 return options
def install_runtime_libraries(env):
 binary=browser_binary()
 if binary is None:
  emit('browser_runtime_libraries',{'state':'SYSTEM_BROWSER_SELECTED_NO_BUNDLED_LINKER_TARGET','changed':False});return
 missing=missing_libraries(binary,env)
 if not missing:
  emit('browser_runtime_libraries',{'state':'LINKER_VERIFIED','changed':False,'missing_libraries':[]});return
 if any(name not in LIBRARY_PACKAGES for name in missing):raise RuntimeError('HOLD_BROWSER_UNREVIEWED_SHARED_LIBRARY')
 packages=sorted({LIBRARY_PACKAGES[name] for name in missing})
 apt_env={**env,'DEBIAN_FRONTEND':'noninteractive','DEBIAN_PRIORITY':'critical','NEEDRESTART_MODE':'l','LC_ALL':'C'}
 options=apt_context()
 if run(['/usr/bin/dpkg','--print-architecture'],apt_env,10,'ARCH').strip()!=b'amd64':raise RuntimeError('HOLD_BROWSER_SYSTEM_ARCH')
 run(['/usr/bin/apt-get',*options,'update'],apt_env,100,'APT_UPDATE')
 common=['--no-install-recommends','--no-remove','--no-upgrade']
 proposed=run(['/usr/bin/apt-get',*options,'--simulate',*common,'install',*packages],apt_env,35,'APT_PLAN')
 plan=apt_plan(proposed,packages)
 emit('browser_runtime_libraries',{'state':'REVIEWED_RUNTIME_INSTALL_ADMITTED','packages':[{'package':n,'version':v} for n,v in plan],
  'missing_libraries':missing,'torch_or_cuda_packages_changed':False,'global_apt_sources_changed':False,'service_restart_requested':False})
 if any((ROOT/name).exists() for name in ('STOP','STOP.flag','stop.flag','.stop','state/STOP')):raise RuntimeError('HOLD_OWNER_STOP')
 if shutil.disk_usage(ROOT).free<7*1024**3:raise RuntimeError('HOLD_BROWSER_DISK_RESERVE')
 run(['/usr/bin/apt-get',*options,*common,'--yes','-o','Dpkg::Options::=--force-confold','install',
      *[name+'='+version for name,version in plan]],apt_env,150,'APT_RUNTIME')
 remaining=missing_libraries(binary,env)
 if remaining:raise RuntimeError('HOLD_BROWSER_LINKER_STILL_MISSING')
 versions=run(['/usr/bin/dpkg-query','-W','-f=${binary:Package}\t${Version}\t${db:Status-Status}\n',
               *[name for name,_ in plan]],apt_env,15,'APT_VERIFY').decode().splitlines()
 installed={}
 for line in versions:
  parts=line.split('\t')
  if len(parts)!=3 or parts[2]!='installed':raise RuntimeError('HOLD_BROWSER_RUNTIME_PACKAGE_STATE')
  installed[parts[0].removesuffix(':amd64')]=parts[1]
 if installed!=dict(plan):raise RuntimeError('HOLD_BROWSER_RUNTIME_VERSION_MISMATCH')
 marker=AREA/'owner-system-libraries.json'
 if marker.is_symlink():raise RuntimeError('HOLD_BROWSER_RUNTIME_MARKER_PATH')
 fd=os.open(marker,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'w') as stream:
  json.dump({'schema':'NOX_OWNER_BROWSER_RUNTIME_V1','packages':installed,'missing_libraries':[],
   'verified_at':time.time(),'torch_or_cuda_packages_changed':False},stream);stream.flush();os.fsync(stream.fileno())
 emit('browser_runtime_libraries',{'state':'LINKER_AND_PACKAGE_VERSIONS_VERIFIED','changed':True,
  'packages':installed,'missing_libraries':[],'browser_acceptance_pending':True})
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
 install_runtime_libraries(env)
 proc=subprocess.run([str(python),'-'],input=raw,env=env,capture_output=True,timeout=175)
 for line in proc.stdout.decode(errors='replace').splitlines():
  if line.startswith('NOX_MAINT_') and len(line)<100000:print(line,flush=True)
 if proc.returncode:raise RuntimeError('HOLD_BROWSER_NATIVE_ACCEPTANCE')
 print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
if __name__=='__main__':
 try:main()
 except Exception as exc:
  text=str(exc);emit('browser_entry_hold',{'reason':text if re.fullmatch('HOLD_[A-Z0-9_]+',text) else type(exc).__name__});raise SystemExit(2)
