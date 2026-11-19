#!/usr/bin/env python3
"""NOX 3A WEB29 mount-safe menu/hub/world patch, SOURCE only.
Pinned input archive SHA256: b91d2a5c11ef7365fee6d76396c619611c0d2f1bf4399fb7ab388484b2659b7f.
Expected output SHA256: 48fa3a189b100242a3ff965e15da3ef83e426c443e275df03bdaae76dfaf413a.
Never calls a server, overwrites an input file, or edits original D02/14 worlds, chat, S03 or weights.
"""
import argparse, hashlib, zipfile
from pathlib import Path
SHA='b91d2a5c11ef7365fee6d76396c619611c0d2f1bf4399fb7ab388484b2659b7f'
OUT='48fa3a189b100242a3ff965e15da3ef83e426c443e275df03bdaae76dfaf413a'
PRE={
'site/pc/menu.html':'51d556d213773783dd3ad4b0a9f20e937e8e1bb5786c69ca02092ac719da657f',
'site/pc/hub.html':'e1e9ef4da981b8cc0755c95b19691d1e274530cf3202e8e3f6a950b169067da1',
'site/pc/world.html':'a1ee5e70d2860a468f078fa17af009f1fe7d09a4c2856920b6fde013b97fe429',
}
STATIC={
'href="/favicon.svg"':'href="../favicon.svg"',
'href="/pc/vendor/fonts/tektur/tektur.css"':'href="./vendor/fonts/tektur/tektur.css"',
'href="/pc/v25/nox-shell-v25.css"':'href="./v25/nox-shell-v25.css"',
'src="/pc/v25/nox-shell-v25.js"':'src="./v25/nox-shell-v25.js"',
'href="/index.html"':'href="../index.html"',
'href="/pc/menu.html"':'href="./menu.html"',
'href="/resonance.html"':'href="./resonance.html"',
'href="/pc/hub.html?s=world"':'href="./hub.html?s=world"',
}
HUB={
'href="/pc/hub.html?s=${x.id}"':'href="./hub.html?s=${S.esc(x.id)}"',
"const hold = x.availability === 'HOLD';":"const hold = x.availability === 'HOLD';\n      const route = S.hrefOf(t, x);",
'href="${S.esc(x.href)}"':'href="${S.esc(route)}"',
"if (location.hash) document.querySelector(location.hash)?.scrollIntoView({ block: 'center' });":"if (location.hash) {\n      // routeIds contain dots: querySelector('#intellect.01') misparses them as classes.\n      let target = location.hash.slice(1);\n      try { target = decodeURIComponent(target); } catch {}\n      document.getElementById(target)?.scrollIntoView({ block: 'center' });\n    }",
}
def sha(b):return hashlib.sha256(b).hexdigest()
def main(source,dest):
 if source.resolve()==dest.resolve():raise ValueError('Refusing in-place overwrite')
 if sha(source.read_bytes())!=SHA:raise ValueError('HOLD_INPUT_ARCHIVE_SHA')
 with zipfile.ZipFile(source) as src:
  if src.testzip() or len(src.namelist())!=1212:raise ValueError('HOLD_ARCHIVE_INTEGRITY')
  changes={}
  for path,old_hash in PRE.items():
   data=src.read(path)
   if sha(data)!=old_hash:raise ValueError('HOLD_PREIMAGE_SHA:'+path)
   s=data.decode('utf8')
   rules={'site/pc/menu.html':{'href="/favicon.svg"':'href="../favicon.svg"'},'site/pc/hub.html':{**STATIC,**HUB},'site/pc/world.html':STATIC}[path]
   for old,new in rules.items():
    if old not in s and not (path.endswith('hub.html') and old=='href="/pc/hub.html?s=world"'):raise ValueError('HOLD_MISSING_PATTERN:'+old)
    s=s.replace(old,new)
   changes[path]=s.encode('utf8')
  with zipfile.ZipFile(dest,'w') as out:
   for info in src.infolist():out.writestr(info,changes.get(info.filename,src.read(info.filename)))
 if sha(dest.read_bytes())!=OUT:raise ValueError('HOLD_OUTPUT_SHA')
 with zipfile.ZipFile(dest) as z:
  if z.testzip() or len(z.namelist())!=1212:raise ValueError('HOLD_OUTPUT_CRC')
 print('SOURCE_PASS',OUT,'3 files changed; 1209/1212 byte-identical')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('input',type=Path);p.add_argument('output',type=Path);a=p.parse_args();main(a.input,a.output)
