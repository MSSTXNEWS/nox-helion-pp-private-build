"""Fail-closed and reversible NOX R13 Creative Studio staging.

This runs only on an isolated, pre-authorized R13 build tree.  It does not
modify the preserved owner-approved D02 art or original source archive.
"""
from __future__ import annotations
import hashlib
import json
import shutil
import sys
from pathlib import Path

D02 = {
    'home.png':'382c1069afcaaaed11c319796f2c553d2bd977d7e46c68ecd7d55af26e132a4a',
    'menu.png':'4c73d137e6d25f496abb006dbb8af08b1fe272d2f935c5006f0f42b6fd9992b9',
    'core01.png':'343e5c73539358fe2c086706b4155cc0f9cd9702fcd40a98b4aab130585bec97',
    'menu_sections.png':'7d181604f913cf9956c173c14da3dc7fd0238c389322896588cec4407b4024a4',
}
ANCHOR = 'case "packInvoke": _ = DispatchPack01Async(json.RootElement.Clone()); break;'
LIFECYCLE = 'Closing += (_, _) => { _openAiProvider.Dispose(); _trainingMonitorCts?.Cancel(); };'

def sha(p:Path)->str:
    return hashlib.sha256(p.read_bytes()).hexdigest()

def safe_source_file(p:Path)->None:
    if not p.is_file() or p.is_symlink():
        raise ValueError('CREATIVE_SOURCE_MISSING_OR_SYMLINK:'+str(p.name))

def stage(root:Path, source:Path)->dict:
    root=root.resolve();source=source.resolve()
    main=root/'MainWindow.xaml.cs';html=root/'Assets/index.html';project=root/'NOX.P01.Shell.csproj'
    bridge=root/'Integration/CreativeHostBridge.cs';asset_dir=root/'Assets/creative'
    if not all(x.is_file() and not x.is_symlink() for x in (main,html,project)):
        raise ValueError('R13_SOURCE_ROOT_HOLD')
    if bridge.exists() or bridge.is_symlink() or asset_dir.exists() or asset_dir.is_symlink():
        raise ValueError('CREATIVE_ALREADY_STAGED_OR_CONFLICT')
    # The previous patch mutated MainWindow and index BEFORE this check. A corrupt D02
    # could therefore leave a half-applied tree. Validate all art before ANY write.
    for name,expected in D02.items():
        f=root/'Assets'/name
        safe_source_file(f)
        if sha(f)!=expected:raise ValueError('CANONICAL_D02_SHA_HOLD:'+name)
    main_raw=main.read_bytes();html_raw=html.read_bytes()
    native=main_raw.decode('utf-8-sig'); page=html_raw.decode('utf-8-sig')
    if native.count(ANCHOR)!=1 or native.count(LIFECYCLE)!=1:
        raise ValueError('R13_ROUTER_OR_LIFECYCLE_DRIFT')
    if page.count('</body>')!=1 or 'creative/entry.js' in page:
        raise ValueError('R13_HTML_PREIMAGE_DRIFT')
    web=source/'web';sidecar=source/'bridge/CreativeHostBridge.cs'
    safe_source_file(sidecar)
    required={'entry.js','studio.js','studio.html','studio.css','theater.html','theater.js','manifest.webmanifest'}
    found={p.name for p in web.iterdir() if p.is_file() and not p.is_symlink()}
    if not required.issubset(found) or any(not (web/name).is_file() or (web/name).is_symlink() for name in required):
        raise ValueError('CREATIVE_WEB_ASSETS_INCOMPLETE_HOLD')
    for name in found:
        safe_source_file(web/name)
    patched=native.replace(ANCHOR,ANCHOR+'\n                case "creativeInvoke": _ = DispatchCreativeAsync(json.RootElement.Clone()); break;\n                case "creativeProjector": _ = OpenCreativeProjectorAsync(GetString(json.RootElement,"projectId")); break;')
    patched=patched.replace(LIFECYCLE,LIFECYCLE+'\n        Closing += (_, _) => StopCreativeWorker();')
    patched_html=page.replace('</body>','<script src="creative/entry.js"></script></body>')
    # No original D02, R13 owner archive, installer, P03/P04/P05 source is overwritten.
    receipt={'schema':'NOX_R13_CREATIVE_STAGE_V2_FAILCLOSED','canonical_d02_sha256':dict(D02),
             'files':[],'release_accepted':False}
    def record(path:Path,pre:bytes|None=None):
        v={'path':str(path.relative_to(root)).replace('\\','/'),'sha256':sha(path),'bytes':path.stat().st_size}
        if pre is not None:v['pre_sha256']=hashlib.sha256(pre).hexdigest()
        receipt['files'].append(v)
    try:
        # Changes can be rolled back if any copy/IO step fails.
        bridge.parent.mkdir(exist_ok=True,parents=True)
        bridge.write_bytes(sidecar.read_bytes());record(bridge)
        asset_dir.mkdir()
        for p in sorted(web.iterdir()):
            if not p.is_file():continue
            d=asset_dir/p.name;d.write_bytes(p.read_bytes());record(d)
        main.write_text(patched,encoding='utf-8');record(main,main_raw)
        html.write_text(patched_html,encoding='utf-8');record(html,html_raw)
        for name,expected in D02.items():
            if sha(root/'Assets'/name)!=expected:raise ValueError('D02_POST_SHA_DRIFT')
        receipt_path=root.parent/'CREATIVE_STAGE_RECEIPT.json'
        if receipt_path.exists():raise ValueError('CREATIVE_RECEIPT_CONFLICT')
        receipt_path.write_text(json.dumps(receipt,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    except BaseException:
        # Restore source preimages even for interrupted staging on this disposable tree.
        main.write_bytes(main_raw);html.write_bytes(html_raw)
        if bridge.is_file():bridge.unlink()
        if asset_dir.is_dir():shutil.rmtree(asset_dir)
        raise
    return receipt

if __name__=='__main__':
    if len(sys.argv)!=3:raise SystemExit('USAGE: stage_creative.py STAGED_R13_R11 CREATIVE_SOURCE')
    try:print('CREATIVE_R13_NOLOSS_STAGED',len(stage(Path(sys.argv[1]),Path(sys.argv[2]))['files']))
    except ValueError as ex:raise SystemExit('HOLD: '+str(ex))