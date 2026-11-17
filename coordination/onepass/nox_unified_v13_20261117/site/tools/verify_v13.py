#!/usr/bin/env python3
"""Offline structural check for NOX WOW V13. Never claims live OneHost acceptance.
Usage: python tools/verify_v13.py (from inside `site`) or python site/tools/verify_v13.py
"""
from pathlib import Path
from html.parser import HTMLParser
import hashlib,json,re,sys
root=Path(__file__).resolve().parents[1]
verified={'nox-home.mjs':'8066bc0a0f8ef5bb5f0fb1f58ad3f6ee29dc8506385c09d77d38d4235c7e42e9',
'nox-orbit-14.js':'3aced1774354b6212b665ef40514e78fb7660a3319fd346c4b12bbf277a39d38',
'nox-engines/nox-world-shaders.mjs':'124a5d341059eb1070adcf58640657aa471ea4888e4409101503ecaa9337f952',
'eclipse-materials.mjs':'0fb0ccf03b997a08e4bbbe854da0c3ce3e538d2652cbac21cc136ab3f68bebec',
'assets13-loader.js':'a9f306ac4886cd3d91b96e2872c4d90024f83cad654fa441e6fa39553d1f3b3a'}
class Links(HTMLParser):
 def __init__(self):super().__init__();self.local=[]
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if tag in ('script','img','source','link'):
   url=a.get('src') if tag!='link' else a.get('href')
   if url and not url.startswith(('https:','http:','//','data:','blob:','#','/api/')):
    self.local.append(url.split('?')[0].split('#')[0])
issues=[];active=[]
for f in root.rglob('*.html'):
 html=f.read_text(errors='replace')
 if 'data-nox-header-v12' not in html:continue
 active.append(str(f.relative_to(root)))
 if html.count('nox-world-controls-v13.css')!=1:issues.append([str(f),'world controls missing/duplicated'])
 if html.count('nox-connection-v13.js')!=1:issues.append([str(f),'connection JS missing/duplicated'])
 if html.count('nox-connection-v13.css')!=1:issues.append([str(f),'connection CSS missing/duplicated'])
 parser=Links();parser.feed(html)
 for u in parser.local:
  if u.startswith('/nox-web-v29/'):u=u[len('/nox-web-v29'):]
  p=(root/u.lstrip('/')) if u.startswith('/') else f.parent/u
  if not p.resolve().is_file():issues.append([str(f.relative_to(root)),f'missing {u}'])
for name,sha in verified.items():
 p=root/name
 if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=sha:issues.append([name,'protected original changed'])
required_routes=['chat.html', 'cinema.html', 'dispatcher.html', 'downloads.html', 'index.html', 'install.html', 'memory.html', 'models.html', 'motion100/gallery.html', 'pc/chat.html', 'pc/cinema.html', 'pc/dispatcher.html', 'pc/downloads.html', 'pc/help.html', 'pc/home-v18.html', 'pc/hub.html', 'pc/install.html', 'pc/memory.html', 'pc/menu.html', 'pc/models.html', 'pc/pages/canvas/index.html', 'pc/pages/cinema/index.html', 'pc/pages/code/index.html', 'pc/pages/games/index.html', 'pc/pages/graph/index.html', 'pc/pages/image/index.html', 'pc/pages/music/index.html', 'pc/pages/observatory/index.html', 'pc/pages/reader/index.html', 'pc/pages/voice/index.html', 'pc/personas.html', 'pc/projects.html', 'pc/resonance.html', 'pc/settings.html', 'pc/studio.html', 'pc/system.html', 'pc/training.html', 'pc/world.html', 'projects.html', 'settings.html', 'studio.html', 'system.html', 'training.html']
for route in required_routes:
 if route not in active:issues.append([route,'V13 original active route missing'])
result={'source_root':str(root),'active_routes':len(active),'protected_core_files':len(verified),'missing_local_deps':sum('missing ' in x[1] for x in issues),'errors':issues,'verdict':'SOURCE_PASS' if not issues else 'SOURCE_FAIL','production':'HOLD — no authenticated OneHost E2E'}
print(json.dumps(result,ensure_ascii=False,indent=2));sys.exit(bool(issues))
