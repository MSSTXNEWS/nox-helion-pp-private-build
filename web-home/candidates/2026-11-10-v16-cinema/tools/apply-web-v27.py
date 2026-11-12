"""V27: source-locked fix for static NOX WEB catalogue links and UI route favorites.
Runs AFTER the original V26 overlay in the same 10-page build.
Does not modify the original D02, PBR worlds, media or a native OneHost module.
"""
from pathlib import Path
import hashlib
ROOT=Path(__file__).resolve().parent.parent / 'dist'
sha=lambda s:hashlib.sha256(s.encode('utf8')).hexdigest()
js_file=ROOT/'nox-function-catalog.js'
css_file=ROOT/'nox-function-catalog.css'
orig_js=js_file.read_text('utf8')
orig_css=css_file.read_text('utf8')
preimages={
'nox-function-catalog.js':'67f6672da1ed87f5bd456ee3fb3d0b3ac578f15a2059abd563c87460c1293a53',
'nox-function-catalog.css':'8be0ca95b6713c30b94d27ac80390267498b255d3ec6aa16a149098a8cdeb82b'
}
assert sha(orig_js)==preimages['nox-function-catalog.js'],'NOX_WEB_V27_SOURCE_DRIFT_JS'
assert sha(orig_css)==preimages['nox-function-catalog.css'],'NOX_WEB_V27_SOURCE_DRIFT_CSS'
def once(s,old,new):
    if s.count(old)!=1:raise RuntimeError('NOX_WEB_V27_ANCHOR_DRIFT: '+old[:90])
    return s.replace(old,new,1)
s=orig_js
s=once(s,"const native=window.NOX_NATIVE_OWNER===true,files={home:'index',dashboard:'system'};", """const native=window.NOX_NATIVE_OWNER===true,files={home:'index',dashboard:'system'};
// Public preview: never show native-only S03/session actions as working.
// Store only catalog route IDs, never messages, user records or credentials.
const nativeOnlyPublic=new Set(['session','events']);
const favoritesKey='nox.web.ui.favorite.ids.v1',recentKey='nox.web.ui.recent.ids.v1';
const validIds=new Set(entries.map(e=>e.id));
function readIds(key){if(native)return [];try{const rows=JSON.parse(localStorage.getItem(key)||'[]');return Array.isArray(rows)?rows.filter(v=>typeof v==='string'&&validIds.has(v)&&!nativeOnlyPublic.has(v)).slice(0,36):[]}catch{return []}}
let favorites=new Set(readIds(favoritesKey)),recent=readIds(recentKey),catalogView='all';
const storeIds=(key,value)=>{try{localStorage.setItem(key,JSON.stringify(value));return true}catch{return false}};
function recordRecent(id){if(native||!validIds.has(id))return;recent=[id,...recent.filter(v=>v!==id)].slice(0,12);storeIds(recentKey,recent);}
""")
s=once(s,"const grid=make('div','nox-function-grid');dialog.append(head,note,search,status,grid);document.body.append(dialog);let returnFocus=null;", """const grid=make('div','nox-function-grid');
const allButton=make('button','nox-function-filter','ВСЕ ФУНКЦИИ');allButton.type='button';
allButton.addEventListener('click',()=>{catalogView='all';search.value='';render();search.focus()});
dialog.append(head,note,search,allButton,status,grid);document.body.append(dialog);let returnFocus=null;""")
s=once(s,"for(const item of entries){if(q&&!", "for(const item of entries){if(!native&&catalogView==='saved'&&!favorites.has(item.id)&&!recent.includes(item.id))continue;if(q&&!")
s=once(s,"const a=make('a','nox-function-card');a.href=path(item.page)+'#'+item.anchor;", """const unavailable=!native&&nativeOnlyPublic.has(item.id);
const a=make(unavailable?'button':'a','nox-function-card');if(unavailable){a.type='button';a.disabled=true;a.title='HOLD · Требуется действующий локальный OneHost';a.dataset.availability='HOLD_NATIVE_ONLY';}else a.href=path(item.page)+'#'+item.anchor;""")
s=once(s,"a.addEventListener('click',event=>{if(event.ctrlKey||event.metaKey||event.shiftKey||event.altKey)return;", """a.addEventListener('click',event=>{if(event.ctrlKey||event.metaKey||event.shiftKey||event.altKey)return;
if(!native&&item.id==='commands'){event.preventDefault();catalogView='all';search.value='';render();search.focus();return;}
if(!native&&item.id==='favorites'){event.preventDefault();catalogView='saved';search.value='';render();search.focus();return;}
""")
s=once(s,"if(window.NOX_UNIVERSE_V19?.modules?.includes(module)){dialog.close();window.NOX_UNIVERSE_V19.open(module);}","if(window.NOX_UNIVERSE_V19?.modules?.includes(module)){recordRecent(item.id);dialog.close();window.NOX_UNIVERSE_V19.open(module);}")
s=once(s,"event.preventDefault();dialog.close();history.replaceState(null,'',target.hash);reveal(item.anchor);", "event.preventDefault();recordRecent(item.id);dialog.close();history.replaceState(null,'',target.hash);reveal(item.anchor);")
s=once(s,"}else dialog.close();});grid.append(a);}", """}else{recordRecent(item.id);dialog.close();}});
if(native){grid.append(a);continue;}
const tile=make('div','nox-function-item');tile.append(a);
if(!unavailable){const star=make('button','nox-function-favorite',favorites.has(item.id)?'★':'☆');star.type='button';star.dataset.favoriteId=item.id;
star.setAttribute('aria-label',(favorites.has(item.id)?'Убрать из избранного: ':'Добавить в избранное: ')+item.label);
star.setAttribute('aria-pressed',String(favorites.has(item.id)));
star.addEventListener('click',()=>{if(favorites.has(item.id))favorites.delete(item.id);else favorites.add(item.id);
const saved=storeIds(favoritesKey,[...favorites]);render();if(!saved)status.textContent='Избранное изменено только для этого окна · сохранение недоступно';});tile.append(star);}
grid.append(tile);}
""")
s=once(s,"status.textContent=count?'Найдено функций: '+count:'Совпадений нет. Измените запрос.';", "status.textContent=count?'Найдено функций: '+count:catalogView==='saved'?'Избранное и недавние пусты. Добавьте функцию кнопкой ☆.':'Совпадений нет. Измените запрос.';")
s=once(s,"function open(query=''){returnFocus=document.activeElement;search.value=typeof query==='string'?query.slice(0,160):'';render();", "function open(query=''){returnFocus=document.activeElement;catalogView='all';search.value=typeof query==='string'?query.slice(0,160):'';render();")
s=once(s,"diagnostics:()=>({entries:entries.length,open:dialog.open,search:search.value,networkRequestsOnOpen:0,automaticActions:false})", "diagnostics:()=>({entries:entries.length,open:dialog.open,search:search.value,mode:catalogView,favorites:favorites.size,recent:recent.length,nativeOnlyUnavailable:native?0:nativeOnlyPublic.size,networkRequestsOnOpen:0,automaticActions:false})")
css=orig_css+'''
/* V27 existing graphical catalog: truthful local-only actions and route-ID favorites. */
.nox-function-filter{min-height:44px;padding:9px 14px;margin-top:12px;background:#192129;border:1px solid #9386738c;border-radius:9px;color:#ecce94;font:600 12px/1.4 inherit;cursor:pointer}
.nox-function-item{min-width:0;position:relative;display:grid;grid-template-columns:minmax(0,1fr)}
.nox-function-item>.nox-function-card{width:100%;min-width:0;height:100%;padding-right:58px;text-align:left}
.nox-function-favorite{position:absolute;top:9px;right:8px;z-index:2;min-width:44px;min-height:44px;background:#151b20ee;color:#ecc58d;border:1px solid #aa906456;border-radius:10px;cursor:pointer;font-size:23px}
.nox-function-favorite[aria-pressed=true]{background:#42321ded;color:#f6dca5}
.nox-function-card[disabled]{opacity:.62;cursor:not-allowed}
.nox-function-dialog .nox-function-favorite:focus-visible,.nox-function-dialog .nox-function-filter:focus-visible{outline:2px solid #dfc497;outline-offset:3px}
@media(max-width:480px){.nox-function-item>.nox-function-card{padding-right:56px}}
@media(prefers-reduced-motion:reduce){.nox-function-item *{animation:none!important;transition:none!important}}
'''
postimages={'nox-function-catalog.js':'c509870d8fc664bb7c60cd53d3daf21280aa410832d978d3fedbd0543730f661','nox-function-catalog.css':'c2059ad63829f82b171d2f2e776ee0137b1402fc2f26b96d02b3e3c9eff37605'}
assert sha(s)==postimages['nox-function-catalog.js'],'NOX_WEB_V27_POSTIMAGE_JS_UNEXPECTED'
assert sha(css)==postimages['nox-function-catalog.css'],'NOX_WEB_V27_POSTIMAGE_CSS_UNEXPECTED'
js_file.write_text(s,'utf8');css_file.write_text(css,'utf8')
print('NOX_WEB_V27_SHA_LOCK_PASS',postimages)
