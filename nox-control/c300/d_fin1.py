import json,os,glob
V='/workspace/nox/web/site/vendor'
idx=json.load(open(V+'/INDEX.json')); mods={m['name']:m for m in idx['modules']}
if os.path.exists(V+'/INDEX.part.json'):
    for m in json.load(open(V+'/INDEX.part.json'))['modules']: mods[m['name']]=m
S='/workspace/nox/web/build/src'
def du(d):
    t=0
    for r,_,fs in os.walk(d):
        for f in fs:
            try:t+=os.path.getsize(os.path.join(r,f))
            except:pass
    return t//1024
man=[
('talkinghead','git met4citizen/TalkingHead','1.8.2','MIT','vendor/talkinghead/modules/talkinghead.mjs','import {TalkingHead} from "./vendor/talkinghead/modules/talkinghead.mjs" (нужен importmap three + three/addons, GLB-аватары в vendor/talkinghead/avatars)','чат, голос, ТВ'),
('foliate-js','git johnfactotum/foliate-js','git','MIT','vendor/foliate-js/epub.js','import "./vendor/foliate-js/view.js" ; <foliate-view>','читалка'),
('novnc','git novnc/noVNC','git','MPL-2.0','vendor/novnc/core/rfb.js','import RFB from "./vendor/novnc/core/rfb.js"','удалённый стол'),
('drawio','git jgraph/drawio (webapp)','git','Apache-2.0','vendor/drawio/index.html','<iframe src="./vendor/drawio/index.html?embed=1&proto=json&spin=1&ui=dark">','доска'),
('earth','git cambecc/earth (public)','git','MIT','vendor/earth/index.html','<iframe src="./vendor/earth/index.html"> (данные ветров нужно подкладывать в data/weather самим)','атлас'),
('jupyterlite','pip jupyterlite-core + pyodide-kernel (статика)','pip','BSD-3-Clause','vendor/jupyterlite/lab/index.html','<iframe src="./vendor/jupyterlite/lab/index.html"> или ./vendor/jupyterlite/repl/index.html?kernel=python','помощник, обучение'),
('planets','Solar System Scope textures','-','CC BY 4.0','vendor/planets/2k/','new THREE.TextureLoader().load("./vendor/planets/8k/8k_earth_daymap.jpg"); кольца Сатурна: 2k/2k_saturn_ring_alpha.png; облака/ночь: *_earth_clouds, *_earth_nightmap','фон (планеты); LICENSE и ATTRIBUTION.txt в папке'),
]
for n,p,v,l,main,ex,pg in man:
    d=V+'/'+n
    mods[n]={'name':n,'pkg':p,'version':v,'license':l,'dir':'vendor/'+n+'/','main':main,'example':ex,'page':pg,'status':'ok' if os.path.isdir(d) else 'FAIL','totalKB':du(d) if os.path.isdir(d) else 0,'files':[]}
mods['stellarium-web-engine']={'name':'stellarium-web-engine','pkg':'git Stellarium/stellarium-web-engine','license':'AGPL-3.0','status':'SKIP: нужна сборка emscripten (wasm), лицензия AGPL','dir':'','example':'','page':'атлас','files':[]}
L=sorted(mods.values(),key=lambda m:m['name'])
json.dump({'base':'site/vendor (URL: ./vendor/<имя>/ от корня сайта)','modules':L},open(V+'/INDEX.json','w'),ensure_ascii=False,indent=1)
ok=[m for m in L if str(m.get('status','')).startswith(('ok','уже'))]
o=['# VENDOR_INDEX: готовые модули в site/vendor (авто, исполнитель D)','Подключение: пути от корня сайта, ./vendor/<имя>/... Бандлы *.esm.js (ESM, minify) и *.iife.js (глобал NOX_<имя>). Полный JSON: site/vendor/INDEX.json.','',f'Всего: {len(L)}, готово: {len(ok)}','','| Модуль | Версия | Лицензия | Готовый файл | Пример | Страница | Статус |','|---|---|---|---|---|---|---|']
for m in L:
    ex=(m.get('example') or '').replace('|','\\|').replace('\n',' ')
    mn=m.get('main') or (m.get('files') or [''])[0]
    mn=str(mn).split(' ')[0]
    o.append(f"| {m['name']} | {m.get('version') or ''} | {m.get('license') or ''} | {mn} | {ex[:140]} | {m.get('page','')} | {str(m.get('status'))[:60]} |")
open(V+'/VENDOR_INDEX.md','w').write('\n'.join(o)+'\n')
print('MDBEGIN');print('\n'.join(o));print('MDEND')
