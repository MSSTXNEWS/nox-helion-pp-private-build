"""Bounded additive staging for E06 R13's verified disposable WPF/WebView2 tree.
No modifications to frozen source archive, canonical UI art, or actual production branch.
"""
from pathlib import Path
import hashlib
import json
import shutil
import sys


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    if len(sys.argv)!=3:raise SystemExit('Usage: stage_creative.py STAGED_R11 CREATIVE_SOURCE')
    stage=Path(sys.argv[1]).resolve();source=Path(sys.argv[2]).resolve()
    main=stage/'MainWindow.xaml.cs';html=stage/'Assets/index.html';integration=stage/'Integration/CreativeHostBridge.cs'
    if not all(x.is_file() for x in (main,html,stage/'NOX.P01.Shell.csproj')):
        raise SystemExit('HOLD: R13 WPF source is missing')
    if integration.exists() or (stage/'Assets/creative').exists():raise SystemExit('HOLD: creative files already in stage')
    original=main.read_text(encoding='utf-8-sig')
    anchor='case "packInvoke": _ = DispatchPack01Async(json.RootElement.Clone()); break;'
    if original.count(anchor)!=1:raise SystemExit('HOLD: original R13 message router drift')
    patched=original.replace(anchor,anchor+'\n                case "creativeInvoke": _ = DispatchCreativeAsync(json.RootElement.Clone()); break;\n                case "creativeProjector": _ = OpenCreativeProjectorAsync(); break;')
    close='Closing += (_, _) => { _openAiProvider.Dispose(); _trainingMonitorCts?.Cancel(); };'
    if patched.count(close)!=1:raise SystemExit('HOLD: original lifecycle contract drift')
    patched=patched.replace(close,close+'\n        Closing += (_, _) => StopCreativeWorker();')
    original_html=html.read_text(encoding='utf-8-sig')
    if original_html.count('</body>')!=1:raise SystemExit('HOLD: R13 HTML contract drift')
    if 'creative/entry.js' in original_html:raise SystemExit('HOLD: existing creative navigation conflict')
    patched_html=original_html.replace('</body>','<script src="creative/entry.js"></script></body>')
    receipt={'schema':'NOX_R13_CREATIVE_STAGE_V1','canonical_art_untouched':True,'files':[]}
    def record(path,pre=None):receipt['files'].append({'path':str(path.relative_to(stage)).replace('\\','/'),'pre_sha256':pre,'post_sha256':sha(path)})
    pre=sha(main);main.write_text(patched,encoding='utf-8');record(main,pre)
    pre=sha(html);html.write_text(patched_html,encoding='utf-8');record(html,pre)
    shutil.copyfile(source/'bridge/CreativeHostBridge.cs',integration);record(integration)
    target=stage/'Assets/creative';target.mkdir(parents=True)
    for file in sorted((source/'web').glob('*')):
        if not file.is_file():continue
        dest=target/file.name;shutil.copyfile(file,dest);record(dest)
    # NO-LOSS hard gate: canonical D02 artwork must remain byte-identical before and after.
    approved={
        'home.png':'382c1069afcaaaed11c319796f2c553d2bd977d7e46c68ecd7d55af26e132a4a',
        'menu.png':'4c73d137e6d25f496abb006dbb8af08b1fe272d2f935c5006f0f42b6fd9992b9',
        'core01.png':'343e5c73539358fe2c086706b4155cc0f9cd9702fcd40a98b4aab130585bec97',
        'menu_sections.png':'7d181604f913cf9956c173c14da3dc7fd0238c389322896588cec4407b4024a4'
    }
    for canonical, expected in approved.items():
        file=stage/'Assets'/canonical
        if not file.is_file() or sha(file)!=expected:
            raise SystemExit('HOLD: original D02 resource missing or altered: '+canonical)
    receipt['canonical_d02_sha256']=approved

    (stage.parent/'CREATIVE_STAGE_RECEIPT.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    print('CREATIVE_R13_STAGED_NOLOSS',len(receipt['files']))

if __name__=='__main__':main()
