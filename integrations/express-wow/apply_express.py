"""One-shot NOX V16 Creative+WOW source integration against immutable R13 donor.

Copies the input first; NEVER modifies its files, Git main, or a built EXE.
Installed Windows binary / running models / E07 remain independent gates.
"""
from __future__ import annotations
import argparse,hashlib,json,os,shutil,sys,tempfile
from pathlib import Path

D02={
 'home.png':'382c1069afcaaaed11c319796f2c553d2bd977d7e46c68ecd7d55af26e132a4a',
 'menu.png':'4c73d137e6d25f496abb006dbb8af08b1fe272d2f935c5006f0f42b6fd9992b9',
 'core01.png':'343e5c73539358fe2c086706b4155cc0f9cd9702fcd40a98b4aab130585bec97',
 'menu_sections.png':'7d181604f913cf9956c173c14da3dc7fd0238c389322896588cec4407b4024a4',
}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def execute(input_r11:Path,repo:Path,output:Path):
 input_r11=input_r11.resolve(strict=True);repo=repo.resolve(strict=True)
 output=output.absolute()
 if output.exists() or output.is_symlink():raise ValueError('NOLOSS_OUTPUT_EXISTS')
 if not output.parent.is_dir():raise ValueError('NOLOSS_PARENT_MISSING')
 if str(output).startswith(str(input_r11)+os.sep):raise ValueError('OUTPUT_INSIDE_SOURCE_HOLD')
 if not (input_r11/'NOX.P01.Shell.csproj').is_file():raise ValueError('IMMUTABLE_R13_R11_REQUIRED')
 for n,expected in D02.items():
  p=input_r11/'Assets'/n
  if not p.is_file() or p.is_symlink() or sha(p)!=expected:raise ValueError('ORIGINAL_D02_SHA_HOLD:'+n)
 sys.path.insert(0,str(repo/'integrations/creative'))
 sys.path.insert(0,str(repo/'integrations/wow200'))
 import stage_creative,stage_wow200
 tmp=Path(tempfile.mkdtemp(prefix='NOX_EXPRESS_STAGE_',dir=output.parent))
 try:
  src=tmp/'R11'
  shutil.copytree(input_r11,src,symlinks=True)
  creative=stage_creative.stage(src,repo/'integrations/creative')
  wow=stage_wow200.stage(src,repo/'integrations/wow200')
  if wow['donor_file_count']!=56 or wow.get('active_d02_engine')!='OWNER1_PR144_PINNED' or wow.get('legacy_d02_runtime_imported') is not False:
   raise ValueError('WOW_OWNER_NOT_CONNECTED')
  html=(src/'Assets/index.html').read_text(encoding='utf-8-sig')
  studio=(src/'Assets/creative/studio.html').read_text(encoding='utf-8-sig')
  renderer=src/'Assets/creative/wow200/runtime/home-scene.mjs'
  owner=src/'Assets/creative/wow200/proposals/NOX-CINEMA-FX/nox-cinema.mjs'
  old=src/'Assets/creative/wow200/legacy/d02-pr30/nox-cinema.mjs'
  if (not owner.is_file() or not old.is_file() or
      renderer.read_text().count("from '../proposals/NOX-CINEMA-FX/nox-cinema.mjs'")!=1 or
      html.count('creative/wow200/runtime/home-scene.mjs')!=1 or
      html.count('creative/wow200/proposals/NOX-CINEMA-FX/nox-cinema.css')!=1 or
      'creative/wow200/canonical/nox-cinema.css' in html or
      studio.count('wow200/runtime/loader.mjs')!=1):
   raise ValueError('ONLY_ONE_ACTIVE_E01_D02_RENDERER_HOLD')
  for n,expected in D02.items():
   if sha(src/'Assets'/n)!=expected:raise ValueError('D02_POST_SHA_HOLD:'+n)
  proof={
   'schema':'NOX_V16_EXPRESS_CREATIVE_WOW_ONEHOST_SOURCE_V1',
   'source_root':'R13 exact user-supplied staged R11',
   'original_protected_d02_sha256':D02,
   'creative_src_files':len(creative.get('files',[])),
   'wow_donor_files':wow['donor_file_count'],
   'single_active_owner': 'E01',
   'active_owner_git_blob_sha1':wow['active_d02_git_blobs'],
   'home_legacy_renderer_preserved_but_inactive':True,
   'original_input_unchanged':True,
   'component_source_merged':True,
   'windows_install_accepted':False,
   'gpu_video_provider_accepted':False,
   'e07_same_exe_accepted':False,
   'files':[]}
  for p in [src/'MainWindow.xaml.cs',src/'Assets/index.html',src/'Assets/creative/studio.html',renderer,owner,
            src/'Assets/creative/wow200/proposals/NOX-CINEMA-FX/nox-cinema.css']:
   proof['files'].append({'path':p.relative_to(src).as_posix(),'sha256':sha(p),'bytes':p.stat().st_size})
  (tmp/'EXPRESS_RECEIPT.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
  os.replace(tmp,output)
  return proof
 except BaseException:
  shutil.rmtree(tmp,ignore_errors=True)
  raise

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--r13',type=Path,required=True);parser.add_argument('--repo',type=Path,required=True);parser.add_argument('--out',type=Path,required=True)
 args=parser.parse_args()
 try:print(json.dumps(execute(args.r13,args.repo,args.out),ensure_ascii=False,indent=2))
 except Exception as e:raise SystemExit('HOLD_NOLOSS: '+repr(e))