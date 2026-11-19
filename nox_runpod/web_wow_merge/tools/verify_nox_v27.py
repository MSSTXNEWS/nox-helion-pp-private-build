#!/usr/bin/env python3
"""Independent read-only source acceptance. No claim about Windows/Ollama/GPU.

Usage: python verify_nox_v27.py /path/to/NOX_HELION_WEB_WOW_V27...zip [--web original.zip]
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path


def sha(data:bytes)->str:return hashlib.sha256(data).hexdigest()

def check(artifact:Path,original:Path|None=None):
  with zipfile.ZipFile(artifact) as z:
    names=[n for n in z.namelist() if not n.endswith('/')]
    if len(names)!=len(set(n.casefold() for n in names)):
      raise ValueError('NOX_WINDOWS_FILENAME_COLLISION')
    for name in names:
      if name.startswith('/') or '\\' in name or '..' in name.split('/') or ':' in name:
        raise ValueError('NOX_INVALID_ARCHIVE_PATH '+name)
    damaged=z.testzip()
    if damaged:raise ValueError('NOX_ZIP_CRC_FAIL '+damaged)
    manifest=json.loads(z.read('NOX_V27_SOURCE_LOCK.json'))
    receipt=json.loads(z.read('NOX_V27_BUILD_RECEIPT.json'))
    assert manifest['schema']=='NOX-UNIFIED-WEB-SOURCE-LOCK-v27'
    assert len(manifest['site'])==1046
    assert len(manifest['qa_onepass'])==10
    for file, expected in manifest['site'].items():
      if sha(z.read('site/'+file))!=expected:
        raise ValueError('NOX_SITE_SHA_MISMATCH '+file)
    for file, expected in manifest['qa_onepass'].items():
      if sha(z.read(file))!=expected:
        raise ValueError('NOX_ORIGINAL_QA_SHA_MISMATCH '+file)
    assert not receipt['release_accepted'] and not receipt['production_modified']
    assert not receipt['windows_onehost_live_tested'] and not receipt['gpu_weights_trained']
    assert not receipt['onepass_original_qa_executed_on_merged_site']
    root_index=z.read('site/index.html')
    assert sha(root_index)==receipt['original_d02_sha256']==receipt['merged_d02_sha256']
    assert z.read('site/original_web_v25_1/chat.html')
    assert z.read('site/original_web_v25_1/memory.html')
    assert b'pc/resonance.html' in z.read('site/chat.html')
    assert b'pc/memory.html' in z.read('site/memory.html')
    assert b'pc/resonance.html' in z.read('site/resonance.html')
    for page in ('site/training.html','site/pc/resonance.html',
                 'site/pc/memory.html','site/pc/chat.html'):
      html=z.read(page)
      assert html.count(b'nox_genesis_live_panel.mjs')==1,page
    assert sha(z.read('site/nox_genesis_live_panel.mjs'))=='7fa46af4ffe60390ebbbfb13e1accb83bb24f510b36e327abcb69b39c4548c66'
    assert not re.search(rb'AIza[0-9A-Za-z_-]{30,}',z.read('site/pc/pages/_vendor/excalidraw/excalidraw.production.min.js'))
    for route in ('index.html','chat.html','memory.html','resonance.html','training.html',
                  'models.html','system.html','settings.html','projects.html','cinema.html','install.html'):
      assert 'site/'+route in names,route
    if original is not None:
      with zipfile.ZipFile(original) as base:
        old={n:base.read(n) for n in base.namelist() if not n.endswith('/')}
      assert len(old)==292
      assert all(z.read('site/'+name)==body for name,body in old.items()
                 if name not in ('chat.html','memory.html','training.html'))
      assert z.read('site/original_web_v25_1/chat.html')==old['chat.html']
      assert z.read('site/original_web_v25_1/memory.html')==old['memory.html']
    return {'source_lock':'PASS','zip_crc':'PASS','site_sha256':len(manifest['site']),
            'onepass_qa_sha256':len(manifest['qa_onepass']),
            'original_web_without_target_changes':289 if original else 'not_checked',
            'original_web_archive_preserved':original is not None,
            'genesis_widget_integrity':'PASS','windows_onehost_e07':'HOLD_NOT_RUN',
            'zip_members':len(names)}

if __name__=='__main__':
  ap=argparse.ArgumentParser()
  ap.add_argument('archive',type=Path)
  ap.add_argument('--web',type=Path)
  a=ap.parse_args()
  try:print(json.dumps(check(a.archive,a.web),ensure_ascii=False,indent=2))
  except Exception as e:
    print('NOX_VERIFY_FAIL',str(e),file=sys.stderr)
    raise SystemExit(2)
