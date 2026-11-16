"""NOX 3A V06: exact-SHA source-only 3A+3D recovery overlay.
Requires accepted 3D ZIP, original WEB29 ZIP, and the previous 3A retry patch.
No server, credentials, S03 or weight writes. Run from an isolated directory.
"""
import argparse, copy, hashlib, json, subprocess, tempfile, zipfile
from pathlib import Path

BASE_SHA='18faa0b933d72f7be3668b541036fab513f69cdbd10e6427fe7a4e2866f734dc'
PRIMARY_SHA='611a3cf21b37ff79dbaece57f4c65c5efb70e0c302b5fc4b4f64dbfa060f15bc'
RETRY_SHA='deab7398e666599a0dded8ee1b45710607deab15a524946832513e95bdbbb8ef'
FINAL_SHA='17964a1316ef321b3d5b776f254e17730865e1657bffbecd1f1897b19f4f4167'
JS='site/pc/v25/nox-shell-v25.js'

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()

def one(s,old,new):
 if s.count(old)!=1:raise ValueError('HOLD_UNEXPECTED_JS_PREIMAGE')
 return s.replace(old,new)

def run(base,primary,retry,out):
 if (sha(base),sha(primary),sha(retry)) != (BASE_SHA,PRIMARY_SHA,RETRY_SHA):
  raise ValueError('HOLD_ARTIFACT_SHA_MISMATCH')
 with zipfile.ZipFile(base) as b, zipfile.ZipFile(primary) as p:
  if b.testzip() or p.testzip() or not set(p.namelist()).issubset(b.namelist()):
   raise ValueError('HOLD_ZIP_INTEGRITY')
  old=b.read(JS)
  if hashlib.sha256(old).hexdigest()!='c12a85540ae0f715f0e6669771d6331ff49f58e4c61331c9df7ab348afb6dadc':
   raise ValueError('HOLD_JS_PREIMAGE_SHA')
  with tempfile.TemporaryDirectory() as d:
   fp=Path(d)/JS;fp.parent.mkdir(parents=True);fp.write_bytes(old)
   for extra in ('--check',None):
    cmd=['git','apply','--unidiff-zero'] + ([extra] if extra else []) + [str(Path(retry).resolve())]
    subprocess.run(cmd,cwd=d,check=True,stdout=subprocess.DEVNULL)
   s=fp.read_text()
  s=one(s,"        const response = await fetch(IA_URL, { cache: 'no-store' });\n        if (!response.ok) throw new Error('IA HTTP ' + response.status);\n        const data = await response.json();", """        // A stalled catalog request must not block the original owner menu indefinitely.
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 2800);
        let data;
        try {
          const response = await fetch(IA_URL, { cache: 'no-store', signal: controller.signal });
          if (!response.ok) throw new Error('IA HTTP ' + response.status);
          data = await response.json();
        } finally {
          clearTimeout(timeout);
        }""")
  s=one(s,'<p>Закройте и откройте меню, чтобы повторить загрузку.</p>','<p><button type="button" class="n25-btn" data-n25-retry>Повторить загрузку</button></p>')
  s=one(s,"    el.querySelector('[data-n25-close]')?.addEventListener('click', closeMenu);", """    el.querySelector('[data-n25-close]')?.addEventListener('click', closeMenu);
    el.querySelector('[data-n25-retry]')?.addEventListener('click', async e => {
      const btn = e.currentTarget;
      btn.disabled = true;
      const tiles = await loadIA();
      if (!tiles.length) { btn.disabled = false; return; }
      const next = buildOverlay(standalone);
      next.dataset.catalogueState = 'loaded';
      next.dataset.open = el.dataset.open || 'true';
      el.replaceWith(next);
      if (ov === el) ov = next;
      next.querySelector('.n25-q')?.focus();
    });""")
  new=s.encode()
  if hashlib.sha256(new).hexdigest()!='710a5af39c7ce7326b6593a8e85fd5710f29f33465021250ee7fe610782a438e':
   raise ValueError('HOLD_POSTIMAGE_UNEXPECTED')
  media_ext={'.png','.jpg','.jpeg','.webp','.gif','.svg','.glb','.gltf','.frag','.vert','.glsl','.wgsl','.mp4','.webm','.woff','.woff2','.ttf','.otf','.hdr','.ktx2'}
  media=[n for n in p.namelist() if Path(n).suffix.lower() in media_ext]
  if len(media)<150 or any(p.read(n)!=b.read(n) for n in media):raise ValueError('HOLD_CINEMATIC_ASSETS_CHANGED')
  if set(b.namelist())-set(p.namelist()) != {'site/nox-cinematic-accessibility-3d.css','site/nox-motion-idle-loader.js'}:
   raise ValueError('HOLD_UNEXPECTED_ADDITIONS')
  with zipfile.ZipFile(out,'w') as z:
   for info in b.infolist():z.writestr(copy.copy(info),new if info.filename==JS else b.read(info.filename))
  if sha(out)!=FINAL_SHA:raise ValueError('HOLD_ZIP_OUTPUT_SHA')
  return {'status':'SOURCE_ONLY','file':str(out),'sha256':FINAL_SHA,'members':1214,'original_members':1212,'media_identical':len(media)}

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('accepted_3d_zip');ap.add_argument('original_web29_zip');ap.add_argument('previous_3a_retry_patch');ap.add_argument('output_zip')
 args=ap.parse_args();print(json.dumps(run(args.accepted_3d_zip,args.original_web29_zip,args.previous_3a_retry_patch,args.output_zip)))
