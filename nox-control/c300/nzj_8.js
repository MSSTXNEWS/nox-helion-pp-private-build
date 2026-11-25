/* NOX DZ: редактор-дизайнер. Fabric 7 + Shoelace. ИИ: /vision/describe (Qwen3.6 vision), результат = редактируемые слои. */
(function(){
'use strict';
var root=document.getElementById('dz');if(!root||!window.fabric)return;
var F=window.fabric,$=function(s,r){return(r||document).querySelector(s)},$$=function(s,r){return Array.prototype.slice.call((r||document).querySelectorAll(s))};
var esc=function(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})};
var IMG=F.FabricImage||F.Image;
var S={tool:'select',W:1280,H:800,fill:'#e9b465',stroke:'#1a1a1a',sw:2,op:100,bsize:6,bcol:'#222222',bop:100,snap:false,grid:false,pgrid:true,pix:false,hist:[],hi:-1,busy:false,loading:false,clip:null,gen:null,ctl:null,mask:[],mode:'sel',zoomPct:100};
var FONTS=['Inter','Montserrat','Playfair Display','Roboto Mono','Arial','Georgia','Verdana','Courier New','Impact','Times New Roman'];
var TOOLS=[['select','cursor','Выбор','V'],['hand','hand-index','Рука (пробел)','H'],['rect','square','Прямоугольник','R'],['ellipse','circle','Эллипс','O'],['line','slash-lg','Линия','L'],['arrow','arrow-up-right','Стрелка','A'],['poly','pentagon','Многоугольник','Y'],['pen','vector-pen','Перо (клики, Enter/двойной клик = конец)','P'],['brush','brush','Кисть','B'],['doodle','pencil','Каракули (тонкий карандаш)','K'],['eraser','eraser','Ластик объектов','E'],['text','type','Текст','T'],['fill','paint-bucket','Заливка объекта','G'],['pick','eyedropper','Пипетка','I'],['mask','bullseye','Маска кистью (для ИИ)','M'],['lasso','bezier2','Лассо-маска (для ИИ)','Q'],['zoom','zoom-in','Лупа (клик +, Alt -)','Z']];
var $top=$('#dzTop'),$tools=$('#dzTools'),$stage=$('#dzStage'),$side=$('#dzSide'),$bot=$('#dzBot');

/* ---------- UI ---------- */
function ib(name,tip,act,extra){return '<sl-tooltip content="'+esc(tip)+'" placement="bottom"><sl-icon-button name="'+name+'" label="'+esc(tip)+'" data-act="'+act+'" '+(extra||'')+'></sl-icon-button></sl-tooltip>'}
function btn(txt,act,tip,extra){return '<sl-tooltip content="'+esc(tip||txt)+'"><sl-button size="medium" class="sm" data-act="'+act+'" '+(extra||'')+'>'+txt+'</sl-button></sl-tooltip>'}
$tools.innerHTML=TOOLS.map(function(t){return '<sl-tooltip content="'+esc(t[2]+' ('+t[3]+')')+'" placement="right"><sl-icon-button name="'+t[1]+'" label="'+esc(t[2])+'" data-tool="'+t[0]+'"></sl-icon-button></sl-tooltip>'}).join('');
$top.innerHTML=
 ib('arrow-counterclockwise','Отменить (Ctrl+Z)','undo')+ib('arrow-clockwise','Повторить (Ctrl+Shift+Z)','redo')+'<span class="dz-sep"></span>'+
 '<span id="dzOpts" style="display:flex;gap:8px;align-items:center"></span><span class="dz-sep"></span>'+
 ib('align-start','Выровнять по левому краю','al-l')+ib('align-center','По центру по горизонтали','al-c')+ib('align-end','По правому краю','al-r')+ib('align-top','По верху','al-t')+ib('align-middle','По центру по вертикали','al-m')+ib('align-bottom','По низу','al-b')+ib('distribute-horizontal','Распределить по горизонтали','dist-h')+ib('distribute-vertical','Распределить по вертикали','dist-v')+'<span class="dz-sep"></span>'+
 ib('collection','Группировать (Ctrl+G)','group')+ib('box-arrow-up-right','Разгруппировать (Ctrl+Shift+G)','ungroup')+ib('copy','Дублировать (Ctrl+D)','dup')+ib('trash','Удалить (Del)','del')+'<span class="dz-sep"></span>'+
 ib('upload','Открыть изображение или проект','open')+ib('save','Сохранить проект JSON (Ctrl+S)','savej')+ib('download','Экспорт (Ctrl+E)','export')+ib('clipboard','Копировать PNG в буфер','copypng')+ib('keyboard','Горячие клавиши (?)','keys')+
 '<sl-tooltip content="Панель ИИ и слоёв"><sl-button id="dzSheet" class="sm" data-act="sheet">Панель</sl-button></sl-tooltip>';
$stage.innerHTML='<canvas id="dzCv"></canvas><input type="file" id="dzFile" accept="image/*,.json" hidden>';
$side.className='dz-g';$top.className='dz-g';$tools.className='dz-g';$bot.className='dz-g';
$side.innerHTML='<sl-tab-group><sl-tab slot="nav" panel="lay">Слои</sl-tab><sl-tab slot="nav" panel="prop">Свойства</sl-tab><sl-tab slot="nav" panel="ai">ИИ</sl-tab>'+
 '<sl-tab-panel name="lay"><div class="dz-row">'+ib('plus-square','Новый пустой слой-группа','newlay')+ib('arrow-up','Слой выше ([)','up')+ib('arrow-down','Слой ниже (])','down')+ib('pencil-square','Переименовать слой','rename')+ib('lock','Блок/разблок','lockSel')+'</div><div id="dzLayers"></div></sl-tab-panel>'+
 '<sl-tab-panel name="prop"><div id="dzProps"></div></sl-tab-panel>'+
 '<sl-tab-panel name="ai"><div id="dzAI"></div></sl-tab-panel></sl-tab-group>';
$bot.innerHTML=ib('zoom-out','Уменьшить (-)','zout')+'<sl-select id="dzZoom" size="small" value="100" style="width:104px" hoist>'+[10,25,50,100,200,400,800,1600,3200].map(function(z){return'<sl-option value="'+z+'">'+z+'%</sl-option>'}).join('')+'</sl-select>'+ib('zoom-in','Увеличить (+)','zin')+ib('fullscreen','Вписать (Ctrl+0)','fit')+ib('1-square','100% (Ctrl+1)','z100')+'<span class="dz-sep"></span>'+
 '<sl-tooltip content="Привязка к сетке и объектам"><sl-switch id="dzSnap">Привязка</sl-switch></sl-tooltip><sl-tooltip content="Сетка"><sl-switch id="dzGrid">Сетка</sl-switch></sl-tooltip><sl-tooltip content="Без сглаживания (пиксели)"><sl-switch id="dzPix">Пиксели</sl-switch></sl-tooltip><span class="dz-sep"></span><span id="dzCoord">x 0 y 0</span><span class="dz-sep"></span><span class="l" style="font:500 12px var(--mono);color:var(--mu)">История</span><div id="dzHist"></div>';

/* ---------- canvas ---------- */
var cv=new F.Canvas($('#dzCv'),{preserveObjectStacking:true,selection:true,backgroundColor:'',fireRightClick:true,stopContextMenu:true,enableRetinaScaling:true,uniformScaling:false});
F.Object.prototype.transparentCorners=false;F.Object.prototype.cornerColor='#e9b465';F.Object.prototype.cornerStrokeColor='#111';F.Object.prototype.borderColor='#e9b465';F.Object.prototype.cornerSize=10;F.Object.prototype.touchCornerSize=34;
var EXTRA=['name','dzArt','dzMask','dzId'];
var art;
function mkArt(){art=new F.Rect({left:0,top:0,width:S.W,height:S.H,fill:'#ffffff',selectable:false,evented:false,objectCaching:false,hoverCursor:'default',name:'Холст',dzArt:true,shadow:new F.Shadow({color:'rgba(0,0,0,.6)',blur:40})});cv.add(art);cv.sendObjectToBack(art)}
function layout(){var top=root.getBoundingClientRect().top+window.scrollY,dock=document.querySelector('.nox-dock,#nox-dock,[class*="nox-dock"]'),dh=72;if(dock){var d=dock.getBoundingClientRect();if(d.height>0&&d.top>innerHeight/2)dh=innerHeight-d.top}root.style.height=Math.max(480,innerHeight-top-dh-10)+'px'}
function size(){layout();var r=$stage.getBoundingClientRect();cv.setDimensions({width:Math.max(100,r.width),height:Math.max(100,r.height)});cv.requestRenderAll()}
function fit(){var r=$stage.getBoundingClientRect(),z=Math.min((r.width-60)/S.W,(r.height-60)/S.H);z=Math.max(.02,z);cv.setViewportTransform([z,0,0,z,(r.width-S.W*z)/2,(r.height-S.H*z)/2]);zoomed()}
function zoomed(){S.zoomPct=Math.round(cv.getZoom()*100);var z=$('#dzZoom');if(z){var v=String(S.zoomPct);z.dataset.cur=v}cv.requestRenderAll();setPix()}
function setZoom(z,pt){z=Math.min(32,Math.max(.01,z));var r=$stage.getBoundingClientRect();cv.zoomToPoint(pt||new F.Point(r.width/2,r.height/2),z);zoomed()}
function setPix(){var on=S.pix||cv.getZoom()>=8;cv.imageSmoothingEnabled=!on;$$('canvas',$stage).forEach(function(c){c.style.imageRendering=on?'pixelated':'auto'});cv.requestRenderAll()}
function vis(o){return!o.dzArt&&!o.dzMask}
function userObjs(){return cv.getObjects().filter(vis)}
function nameOf(o){return o.name||({rect:'Прямоугольник',ellipse:'Эллипс',line:'Линия',path:'Контур',group:'Группа',textbox:'Текст',image:'Изображение',polygon:'Многоугольник',circle:'Круг'}[(o.type||'').toLowerCase()])||o.type}
var nameCnt={};function autoName(o){if(o.name)return;var n=nameOf(o);nameCnt[n]=(nameCnt[n]||0)+1;o.set('name',n+' '+nameCnt[n])}

/* сетка и пиксельная сетка поверх */
cv.on('after:render',function(){
 var ctx=cv.getContext(),z=cv.getZoom(),vt=cv.viewportTransform,rs=cv.getRetinaScaling?cv.getRetinaScaling():1;
 var W=cv.getWidth(),H=cv.getHeight();ctx.save();ctx.setTransform(rs,0,0,rs,0,0);
 if(S.grid&&z>=.25){var st=z<1?100:(z<4?20:10);ctx.strokeStyle='rgba(233,180,101,.16)';ctx.lineWidth=1;ctx.beginPath();for(var x=Math.floor((-vt[4]/z)/st)*st;x*z+vt[4]<W;x+=st){var X=x*z+vt[4];ctx.moveTo(X,0);ctx.lineTo(X,H)}for(var y=Math.floor((-vt[5]/z)/st)*st;y*z+vt[5]<H;y+=st){var Y=y*z+vt[5];ctx.moveTo(0,Y);ctx.lineTo(W,Y)}ctx.stroke()}
 if(S.pgrid&&z>=8){ctx.strokeStyle='rgba(255,255,255,.22)';ctx.lineWidth=1;ctx.beginPath();for(var x2=Math.floor(-vt[4]/z);x2*z+vt[4]<W;x2++){var X2=x2*z+vt[4];ctx.moveTo(X2,0);ctx.lineTo(X2,H)}for(var y2=Math.floor(-vt[5]/z);y2*z+vt[5]<H;y2++){var Y2=y2*z+vt[5];ctx.moveTo(0,Y2);ctx.lineTo(W,Y2)}ctx.stroke()}
 ctx.restore()});

/* ---------- история ---------- */
var hT=0;
function snap(){return JSON.stringify(cv.toObject(EXTRA))}
function pushH(lbl){if(S.loading)return;clearTimeout(hT);hT=setTimeout(function(){var s=snap();if(S.hist[S.hi]&&S.hist[S.hi].s===s)return;S.hist=S.hist.slice(0,S.hi+1);S.hist.push({s:s,l:lbl||'Правка'});if(S.hist.length>60)S.hist.shift();S.hi=S.hist.length-1;renderHist();try{localStorage.setItem('nox_dz_proj',s)}catch(e){}},120)}
function loadSnap(s){S.loading=true;return cv.loadFromJSON(JSON.parse(s)).then(function(){art=cv.getObjects().filter(function(o){return o.dzArt})[0]||(mkArt(),art);S.W=art.width;S.H=art.height;S.loading=false;cv.requestRenderAll();layers();props()})}
function undo(){if(S.hi>0){S.hi--;loadSnap(S.hist[S.hi].s).then(renderHist)}}
function redo(){if(S.hi<S.hist.length-1){S.hi++;loadSnap(S.hist[S.hi].s).then(renderHist)}}
function renderHist(){var h=$('#dzHist');h.innerHTML=S.hist.map(function(x,i){return'<sl-button size="small" class="sm'+(i===S.hi?' cur':'')+'" data-hi="'+i+'">'+(i+1)+'</sl-button>'}).join('');var c=$('.cur',h);if(c)c.scrollIntoView({block:'nearest',inline:'nearest'})}
['object:added','object:removed','object:modified'].forEach(function(e){cv.on(e,function(o){if(o.target&&!o.target.dzArt)autoName(o.target);pushH(e);layers()})});
cv.on('selection:created',sel);cv.on('selection:updated',sel);cv.on('selection:cleared',sel);
function sel(){layers();props();opts()}

/* ---------- инструменты ---------- */
var drag=null,penPts=null,penPrev=null;
function sp(o){return o.scenePoint||cv.getScenePoint(o.e)}
function setTool(t){
 if(S.tool==='pen')finishPen();
 S.tool=t;$$('[data-tool]').forEach(function(b){b.classList.toggle('on',b.dataset.tool===t)});
 var draw=(t==='brush'||t==='doodle'||t==='mask'||t==='lasso');cv.isDrawingMode=draw;cv.selection=(t==='select');
 cv.skipTargetFind=!(t==='select'||t==='eraser'||t==='fill'||t==='pick'||t==='text');
 cv.defaultCursor=({select:'default',hand:'grab',zoom:'zoom-in',pick:'crosshair',fill:'crosshair',eraser:'not-allowed',text:'text'})[t]||'crosshair';
 if(draw){var b=new F.PencilBrush(cv);
  if(t==='brush'){b.color=rgba(S.bcol,S.bop/100);b.width=S.bsize}
  else if(t==='doodle'){b.color='#111111';b.width=Math.max(1,Math.min(3,S.bsize/2))}
  else{b.color='rgba(255,0,200,.45)';b.width=t==='mask'?Math.max(S.bsize*3,12):2}
  cv.freeDrawingBrush=b}
 cv.forEachObject(function(o){if(!o.dzArt)o.selectable=(t==='select')&&!o.lockMovementX;o.evented=(t==='select'||t==='eraser'||t==='fill'||t==='pick'||t==='text')&&!o.dzArt});
 opts();cv.requestRenderAll()}
function rgba(h,a){if(/^#/.test(h)&&h.length>=7){var n=parseInt(h.slice(1,7),16);return'rgba('+(n>>16)+','+(n>>8&255)+','+(n&255)+','+a+')'}return h}
cv.on('path:created',function(e){var p=e.path;if(!p)return;if(S.tool==='mask'||S.tool==='lasso'){p.set({dzMask:true,name:'Маска',selectable:false,evented:false});if(S.tool==='lasso'){p.set({fill:'rgba(255,0,200,.35)',stroke:'rgba(255,0,200,.9)',strokeWidth:2})}S.mask.push(p);pushH('mask');maskInfo()}else{p.set({name:S.tool==='doodle'?'Каракули':'Мазок'});S.loading=false}});
function shapeStyle(){return{fill:S.fill,stroke:S.stroke,strokeWidth:S.sw,opacity:S.op/100,strokeUniform:true}}
cv.on('mouse:down',function(o){
 var p=sp(o),t=S.tool,e=o.e;
 if(t==='hand'||(e&&e.button===1)||S._space){drag={pan:true,x:e.clientX,y:e.clientY};cv.defaultCursor='grabbing';cv.selection=false;return}
 if(t==='zoom'){setZoom(cv.getZoom()*(e.altKey?.5:2),new F.Point(p.x*cv.getZoom()+cv.viewportTransform[4],p.y*cv.getZoom()+cv.viewportTransform[5]));return}
 if(t==='pick'){pickAt(e);return}
 if(t==='fill'&&o.target&&vis(o.target)){o.target.set('fill',S.fill);cv.requestRenderAll();pushH('fill');props();return}
 if(t==='eraser'&&o.target&&vis(o.target)){cv.remove(o.target);return}
 if(t==='text'){if(o.target&&o.target.type==='textbox')return;var tb=new F.Textbox('Текст',{left:p.x,top:p.y,width:240,fontFamily:'Inter',fontSize:36,fill:S.fill==='#e9b465'?'#111111':S.fill,name:'Текст'});cv.add(tb);cv.setActiveObject(tb);tb.enterEditing();tb.selectAll();return}
 if(t==='pen'){addPenPt(p);return}
 if(['rect','ellipse','line','arrow','poly'].indexOf(t)>=0){var q=snapPt(p);drag={x0:q.x,y0:q.y,shape:null};}
});
function snapPt(p){if(!S.snap)return{x:p.x,y:p.y};var g=S.zoomPct>=400?10:20;return{x:Math.round(p.x/g)*g,y:Math.round(p.y/g)*g}}
cv.on('mouse:move',function(o){
 var p=sp(o);$('#dzCoord').textContent='x '+Math.round(p.x)+'  y '+Math.round(p.y)+'  '+S.zoomPct+'%';
 if(!drag){if(S.tool==='pen'&&penPts)penPreview(p);return}
 if(drag.pan){var e=o.e,vt=cv.viewportTransform.slice();vt[4]+=e.clientX-drag.x;vt[5]+=e.clientY-drag.y;drag.x=e.clientX;drag.y=e.clientY;cv.setViewportTransform(vt);return}
 var q=snapPt(p),x0=drag.x0,y0=drag.y0,x=q.x,y=q.y,shift=o.e.shiftKey,t=S.tool;
 if(shift&&t!=='line'&&t!=='arrow'){var d=Math.max(Math.abs(x-x0),Math.abs(y-y0));x=x0+(x<x0?-d:d);y=y0+(y<y0?-d:d)}
 if(drag.shape)cv.remove(drag.shape);var sh;var L=Math.min(x0,x),T=Math.min(y0,y),W=Math.abs(x-x0),H=Math.abs(y-y0),st=shapeStyle();
 if(t==='rect')sh=new F.Rect(Object.assign({left:L,top:T,width:W,height:H,rx:S.rx||0,ry:S.rx||0},st));
 else if(t==='ellipse')sh=new F.Ellipse(Object.assign({left:L,top:T,rx:W/2,ry:H/2},st));
 else if(t==='line'||t==='arrow')sh=new F.Line([x0,y0,x,y],{stroke:S.stroke,strokeWidth:Math.max(1,S.sw),strokeLineCap:'round',opacity:S.op/100});
 else if(t==='poly'){var n=S.sides||5,pts=[],cx=(x0+x)/2,cy=(y0+y)/2,rx=W/2,ry=H/2;for(var i=0;i<n;i++){var a=-Math.PI/2+i*2*Math.PI/n;pts.push({x:cx+rx*Math.cos(a),y:cy+ry*Math.sin(a)})}sh=new F.Polygon(pts,st)}
 if(sh){sh.set({evented:false,selectable:false});drag.shape=sh;cv.add(sh);S.loading=true}cv.requestRenderAll()});
cv.on('mouse:up',function(o){
 if(!drag)return;var d=drag;drag=null;S.loading=false;
 if(d.pan){setTool(S.tool);return}
 if(d.shape){var sh=d.shape;cv.remove(sh);if(sh.width>1||sh.height>1||sh.x1!==sh.x2){
   if(S.tool==='arrow'&&sh.type==='line'){var x1=sh.x1,y1=sh.y1,x2=sh.x2,y2=sh.y2,ang=Math.atan2(y2-y1,x2-x1)*180/Math.PI,hd=new F.Triangle({left:x2,top:y2,width:14+S.sw*2,height:16+S.sw*2,fill:S.stroke,angle:ang+90,originX:'center',originY:'center'});var g=new F.Group([sh,hd],{name:'Стрелка'});cv.add(g)}
   else cv.add(sh);sh.set({evented:true,selectable:true});cv.setActiveObject(sh===undefined?null:(S.tool==='arrow'?cv.getObjects().slice(-1)[0]:sh))}
  setTool('select');$$('[data-tool]').forEach(function(b){b.classList.toggle('on',b.dataset.tool==='select')})}
});
cv.on('mouse:wheel',function(o){var e=o.e;e.preventDefault();e.stopPropagation();
 if(e.ctrlKey||e.metaKey||e.altKey){var z=cv.getZoom()*Math.pow(.999,e.deltaY);setZoom(z,new F.Point(e.offsetX,e.offsetY))}
 else{var vt=cv.viewportTransform.slice();vt[4]-=e.shiftKey?e.deltaY:e.deltaX;vt[5]-=e.shiftKey?0:e.deltaY;cv.setViewportTransform(vt)}});
cv.on('mouse:dblclick',function(){if(S.tool==='pen')finishPen()});
/* перо: клики -> Path (полилиния, закрыть двойным кликом рядом с началом) */
function addPenPt(p){var q=snapPt(p);penPts=penPts||[];penPts.push(q);penPreview(q)}
function penPreview(p){if(penPrev)cv.remove(penPrev);if(!penPts||!penPts.length)return;var d='M '+penPts.map(function(a){return a.x+' '+a.y}).join(' L ')+' L '+p.x+' '+p.y;S.loading=true;penPrev=new F.Path(d,{fill:'',stroke:S.stroke,strokeWidth:S.sw,evented:false,selectable:false,objectCaching:false});cv.add(penPrev);S.loading=false;cv.requestRenderAll()}
function finishPen(){if(penPrev){cv.remove(penPrev);penPrev=null}if(penPts&&penPts.length>1){var pts=penPts,cl=Math.hypot(pts[0].x-pts[pts.length-1].x,pts[0].y-pts[pts.length-1].y)<12/cv.getZoom();var d='M '+pts.map(function(a){return a.x+' '+a.y}).join(' L ')+(cl?' Z':'');var pa=new F.Path(d,{fill:cl?S.fill:'',stroke:S.stroke,strokeWidth:S.sw,strokeLineJoin:'round',name:'Контур'});cv.add(pa);cv.setActiveObject(pa)}penPts=null}
/* пипетка */
function pickAt(e){var el=cv.upperCanvasEl.getBoundingClientRect(),rs=cv.getRetinaScaling(),x=Math.floor((e.clientX-el.left)*rs),y=Math.floor((e.clientY-el.top)*rs);try{var d=cv.getElement().getContext('2d').getImageData(x,y,1,1).data;var hx='#'+[d[0],d[1],d[2]].map(function(v){return('0'+v.toString(16)).slice(-2)}).join('');S.fill=hx;if(e.shiftKey)S.stroke=hx;toast('Цвет '+hx+(e.shiftKey?' (обводка)':' (заливка)'));opts();props()}catch(er){toast('Пипетка недоступна: '+er.message)}}
function openD(d){customElements.whenDefined('sl-dialog').then(function(){d.show()})}
function toast(m){var t=document.createElement('sl-alert');t.setAttribute('variant','primary');t.setAttribute('open','');t.setAttribute('duration','3200');t.style.cssText='position:fixed;left:50%;bottom:150px;transform:translateX(-50%);z-index:1300;max-width:92vw';t.innerHTML=esc(m);document.body.appendChild(t);t.addEventListener('sl-after-hide',function(){t.remove()})}

/* ---------- верхняя контекстная панель ---------- */
function cp(id,val,tip){return'<sl-tooltip content="'+tip+'"><sl-color-picker id="'+id+'" size="medium" value="'+val+'" hoist opacity swatches="#000000;#ffffff;#e9b465;#d9534f;#5bc0de;#5cb85c;#f0ad4e;#9b59b6;#1a1a1a;#888888"></sl-color-picker></sl-tooltip>'}
function rg(id,min,max,val,tip,step){return'<sl-tooltip content="'+tip+'"><sl-range id="'+id+'" min="'+min+'" max="'+max+'" step="'+(step||1)+'" value="'+val+'" style="width:130px"></sl-range></sl-tooltip>'}
function opts(){var o=$('#dzOpts'),t=S.tool,a=cv.getActiveObject(),h='';
 if(t==='brush'||t==='doodle'||t==='mask'||t==='lasso'){h=(t==='brush'?cp('oBc',S.bcol,'Цвет кисти'):'')+'<label class="l">Размер'+rg('oBs',1,120,S.bsize,'Размер кисти')+'</label>'+(t==='brush'?'<label class="l">Непрозр.'+rg('oBo',5,100,S.bop,'Прозрачность кисти')+'</label>':'')+(t==='mask'||t==='lasso'?btn('Очистить маску','clrmask','Удалить все маски')+btn('Инверсия (весь холст минус маска)','maskinv','Инвертировать маску: выделить всё, кроме нарисованного'):'')}
 else if(['rect','ellipse','poly','pen','fill','select','line','arrow'].indexOf(t)>=0||a){h='<label class="l">Заливка'+cp('oF',S.fill,'Цвет заливки (клик по объекту с инструментом Заливка)')+'</label><label class="l">Обводка'+cp('oS',S.stroke,'Цвет обводки')+'</label><label class="l">Толщина'+rg('oW',0,60,S.sw,'Толщина обводки')+'</label><label class="l">Непрозр.'+rg('oO',0,100,S.op,'Непрозрачность')+'</label>'+(t==='rect'?'<label class="l">Радиус'+rg('oR',0,200,S.rx||0,'Скругление углов')+'</label>':'')+(t==='poly'?'<label class="l">Углов'+rg('oN',3,12,S.sides||5,'Число углов')+'</label>':'')}
 else if(t==='text'){h=cp('oF',S.fill,'Цвет текста')}
 else h='<span style="color:var(--mu);font-size:12px">'+esc((TOOLS.filter(function(x){return x[0]===t})[0]||[0,0,''])[2])+'</span>';
 o.innerHTML=h;wireOpts()}
function wireOpts(){
 var on=function(id,fn){var e=$('#'+id);if(e)e.addEventListener('sl-input',function(){fn(e.value)})};
 on('oBc',function(v){S.bcol=v;if(cv.freeDrawingBrush)cv.freeDrawingBrush.color=rgba(v,S.bop/100)});on('oBs',function(v){S.bsize=+v;if(cv.freeDrawingBrush)cv.freeDrawingBrush.width=S.tool==='mask'?Math.max(v*3,12):+v});on('oBo',function(v){S.bop=+v;if(cv.freeDrawingBrush)cv.freeDrawingBrush.color=rgba(S.bcol,v/100)});
 on('oF',function(v){S.fill=v;applyActive({fill:v})});on('oS',function(v){S.stroke=v;applyActive({stroke:v})});on('oW',function(v){S.sw=+v;applyActive({strokeWidth:+v})});on('oO',function(v){S.op=+v;applyActive({opacity:v/100})});on('oR',function(v){S.rx=+v;applyActive({rx:+v,ry:+v})});on('oN',function(v){S.sides=+v})}
function applyActive(p){var a=cv.getActiveObjects().filter(vis);if(!a.length)return;a.forEach(function(o){var q=Object.assign({},p);if(o.type==='group'||o.type==='textbox'&&('stroke' in q)&&false)return o.set(q);if(('rx' in q)&&o.type!=='rect')delete q.rx,delete q.ry;o.set(q)});cv.requestRenderAll();clearTimeout(applyActive.t);applyActive.t=setTimeout(function(){pushH('props')},250)}

/* ---------- слои ---------- */
var layT=0;
function layers(){clearTimeout(layT);layT=setTimeout(layers2,30)}
function layers2(){var L=$('#dzLayers');if(!L)return;var act=cv.getActiveObjects(),objs=userObjs().slice().reverse();
 if(!objs.length){L.innerHTML='<div class="dz-out">Слоёв нет. Нарисуйте фигуру, каракули, вставьте изображение, или попросите ИИ.</div>';return}
 L.innerHTML=objs.map(function(o,i){var idx=cv.getObjects().indexOf(o);return'<div class="dz-lay'+(act.indexOf(o)>=0?' sel':'')+'" data-idx="'+idx+'"><sl-icon-button name="'+(o.visible===false?'eye-slash':'eye')+'" label="Показать/скрыть" data-lact="vis"></sl-icon-button><span class="nm" title="'+esc(o.name||nameOf(o))+'">'+esc(o.name||nameOf(o))+'</span><sl-icon-button name="'+(o.lockMovementX?'lock':'unlock')+'" label="Блокировка" data-lact="lock"></sl-icon-button><sl-icon-button name="trash" label="Удалить слой" data-lact="del"></sl-icon-button></div>'}).join('');
 var tg=L.parentElement;if(window.Sortable&&!L._sort){L._sort=Sortable.create(L,{animation:120,handle:'.nm',onEnd:function(ev){var objsAll=cv.getObjects();var rows=$$('.dz-lay',L).map(function(r){return objsAll[+r.dataset.idx]}).reverse();var base=cv.getObjects().filter(function(o){return!vis(o)});S.loading=true;rows.forEach(function(o,i){cv.moveObjectTo(o,base.length?i+base.filter(function(b){return b.dzArt}).length:i)});S.loading=false;pushH('order');layers()}})}}
$side.addEventListener('click',function(e){var row=e.target.closest('.dz-lay');if(!row)return;var o=cv.getObjects()[+row.dataset.idx];if(!o)return;var a=e.target.closest('[data-lact]');
 if(a){var k=a.dataset.lact;if(k==='vis'){o.visible=o.visible===false;if(!o.visible)cv.discardActiveObject()}else if(k==='lock'){var l=!o.lockMovementX;o.set({lockMovementX:l,lockMovementY:l,lockRotation:l,lockScalingX:l,lockScalingY:l,hasControls:!l});}else if(k==='del'){cv.remove(o)}cv.requestRenderAll();pushH('layer');layers();return}
 if(S.tool!=='select')setTool('select');if(o.selectable!==false||true){o.set({selectable:true,evented:true});cv.setActiveObject(o);cv.requestRenderAll()}});

/* ---------- свойства ---------- */
function nin(id,lbl,val){return'<label class="l">'+lbl+'<sl-input id="'+id+'" type="number" size="small" value="'+Math.round(val*100)/100+'"></sl-input></label>'}
function props(){var P=$('#dzProps');if(!P)return;var o=cv.getActiveObject();
 if(!o||o.dzArt){P.innerHTML='<div class="dz-h">Холст</div><div class="dz-row">'+nin('pW','Ширина',S.W)+nin('pH','Высота',S.H)+'</div><div class="dz-row"><label class="l">Фон'+cp('pBg',art&&art.fill&&art.fill!=='transparent'?art.fill:'#ffffff','Цвет фона холста')+'</label><sl-switch id="pTr" '+(art&&art.fill==='transparent'?'checked':'')+'>Прозрачный</sl-switch></div><div class="dz-row">'+btn('1920x1080','cs-1920x1080','Размер 1920x1080')+btn('1080x1080','cs-1080x1080','Квадрат')+btn('1080x1920','cs-1080x1920','Сторис')+btn('512x512','cs-512x512','Иконка 512')+'</div><div class="dz-row" style="color:var(--mu);font-size:12px">Выберите объект: появятся X, Y, W, H, угол, цвета, тень, текст.</div>';
  var f=function(){var w=+$('#pW').value,h=+$('#pH').value;if(w>0&&h>0)canvasSize(w,h)};$('#pW').addEventListener('sl-change',f);$('#pH').addEventListener('sl-change',f);$('#pBg').addEventListener('sl-input',function(e){art.set('fill',e.target.value);cv.requestRenderAll();pushH('bg')});$('#pTr').addEventListener('sl-change',function(e){art.set('fill',e.target.checked?'transparent':'#ffffff');cv.requestRenderAll();pushH('bg')});return}
 var b=o.getBoundingRect?o:o,w=o.getScaledWidth(),h=o.getScaledHeight(),t=o.type,H='<div class="dz-h">'+esc(o.name||nameOf(o))+'</div><div class="dz-row">'+nin('pX','X',o.left)+nin('pY','Y',o.top)+nin('pWd','W',w)+nin('pHd','H',h)+nin('pA','Угол',o.angle||0)+'</div>'+
 '<div class="dz-row"><label class="l">Непрозр.'+rg('pOp',0,100,Math.round((o.opacity==null?1:o.opacity)*100),'Непрозрачность')+'</label></div>'+
 '<div class="dz-row">'+btn('Отразить Г','flipx','Отразить по горизонтали')+btn('Отразить В','flipy','Отразить по вертикали')+btn('+90','rot90','Повернуть на 90')+btn('Наверх','top','На передний план')+btn('Вниз','bottom','На задний план')+'</div>';
 if(t!=='image'&&t!=='group'){H+='<div class="dz-row"><label class="l">Заливка'+cp('pF',typeof o.fill==='string'&&o.fill?o.fill:'#000000','Заливка')+'</label><label class="l">Обводка'+cp('pS',typeof o.stroke==='string'&&o.stroke?o.stroke:'#000000','Обводка')+'</label></div><div class="dz-row"><label class="l">Толщина'+rg('pSw',0,60,o.strokeWidth||0,'Толщина обводки')+'</label><sl-select id="pDash" size="small" value="'+((o.strokeDashArray||[]).length?'d':'s')+'" style="width:140px" hoist><sl-option value="s">Сплошная</sl-option><sl-option value="d">Пунктир</sl-option></sl-select></div>'+
  '<div class="dz-row">'+btn('Градиент','grad','Линейный градиент от заливки к обводке')+btn('Без заливки','nofill','Убрать заливку')+(t==='rect'?'<label class="l">Радиус'+rg('pRx',0,200,o.rx||0,'Скругление')+'</label>':'')+'</div>'}
 H+='<div class="dz-row"><sl-switch id="pSh" '+(o.shadow?'checked':'')+'>Тень</sl-switch>'+(o.shadow?'<label class="l">Размытие'+rg('pShB',0,80,o.shadow.blur||0,'Размытие тени')+'</label>':'')+'</div><div class="dz-row"><sl-select id="pBlend" size="small" value="'+(o.globalCompositeOperation||'source-over')+'" style="width:190px" hoist label="Наложение">'+['source-over:Обычное','multiply:Умножение','screen:Экран','overlay:Перекрытие','darken:Темнее','lighten:Светлее','difference:Разница'].map(function(x){var p=x.split(':');return'<sl-option value="'+p[0]+'">'+p[1]+'</sl-option>'}).join('')+'</sl-select></div>';
 if(t==='textbox'||t==='text'||t==='i-text'){H+='<div class="dz-h">Текст</div><div class="dz-row"><sl-select id="pFont" size="small" value="'+esc(o.fontFamily)+'" style="width:180px" hoist>'+FONTS.map(function(f){return'<sl-option value="'+f+'">'+f+'</sl-option>'}).join('')+'</sl-select>'+nin('pFs','Размер',o.fontSize)+'</div><div class="dz-row">'+ib('type-bold','Жирный','bold')+ib('type-italic','Курсив','italic')+ib('type-underline','Подчёркнутый','underline')+ib('text-left','По левому','ta-left')+ib('text-center','По центру','ta-center')+ib('text-right','По правому','ta-right')+'</div><div class="dz-row"><label class="l">Межстр.'+rg('pLh',.6,3,o.lineHeight||1.16,'Межстрочный',.05)+'</label><label class="l">Межбукв.'+rg('pCs',-100,600,o.charSpacing||0,'Межбуквенный')+'</label></div>'}
 if(t==='image'){var fl=function(n){return(o.filters||[]).filter(function(f){return f.type===n})[0]};H+='<div class="dz-h">Изображение</div><div class="dz-row"><label class="l">Яркость'+rg('fBr',-100,100,Math.round(((fl('Brightness')||{}).brightness||0)*100),'Яркость')+'</label><label class="l">Контраст'+rg('fCo',-100,100,Math.round(((fl('Contrast')||{}).contrast||0)*100),'Контраст')+'</label><label class="l">Насыщ.'+rg('fSa',-100,100,Math.round(((fl('Saturation')||{}).saturation||0)*100),'Насыщенность')+'</label><label class="l">Размытие'+rg('fBl',0,100,Math.round(((fl('Blur')||{}).blur||0)*100),'Размытие')+'</label></div><div class="dz-row"><sl-switch id="fGr" '+(fl('Grayscale')?'checked':'')+'>Ч/Б</sl-switch><sl-switch id="fSe" '+(fl('Sepia')?'checked':'')+'>Сепия</sl-switch><sl-switch id="fIn" '+(fl('Invert')?'checked':'')+'>Инверсия</sl-switch></div><div class="dz-row">'+btn('Палитра','palette','Палитра цветов из изображения')+'</div>'}
 P.innerHTML=H;wireProps(o)}
function rg2(){}
function wireProps(o){
 var I=function(id,fn,ev){var e=$('#'+id);if(e)e.addEventListener(ev||'sl-change',function(){fn(e.value,e)})};
 var sc=function(){cv.requestRenderAll();o.setCoords();pushH('props')};
 I('pX',function(v){o.set('left',+v);sc()});I('pY',function(v){o.set('top',+v);sc()});I('pWd',function(v){if(+v>0){o.scaleX=+v/(o.width||1);sc()}});I('pHd',function(v){if(+v>0){o.scaleY=+v/(o.height||1);sc()}});I('pA',function(v){o.rotate(+v);sc()});
 I('pOp',function(v){o.set('opacity',v/100);sc()},'sl-input');I('pF',function(v){o.set('fill',v);sc()},'sl-input');I('pS',function(v){o.set('stroke',v);sc()},'sl-input');I('pSw',function(v){o.set('strokeWidth',+v);sc()},'sl-input');I('pRx',function(v){o.set({rx:+v,ry:+v});sc()},'sl-input');
 I('pDash',function(v){o.set('strokeDashArray',v==='d'?[Math.max(4,o.strokeWidth*3),Math.max(4,o.strokeWidth*2)]:null);sc()});
 I('pSh',function(v,e){o.set('shadow',e.checked?new F.Shadow({color:'rgba(0,0,0,.5)',blur:20,offsetX:6,offsetY:8}):null);sc();props()});I('pShB',function(v){if(o.shadow){o.shadow.blur=+v;sc()}},'sl-input');
 I('pBlend',function(v){o.set('globalCompositeOperation',v);sc()});
 I('pFont',function(v){o.set('fontFamily',v);sc()});I('pFs',function(v){o.set('fontSize',+v);sc()});I('pLh',function(v){o.set('lineHeight',+v);sc()},'sl-input');I('pCs',function(v){o.set('charSpacing',+v);sc()},'sl-input');
 var fa=function(){o.applyFilters();sc()};var setF=function(n,make,val,on){o.filters=(o.filters||[]).filter(function(f){return f.type!==n});if(on)o.filters.push(make(val));fa()};
 I('fBr',function(v){setF('Brightness',function(x){return new F.filters.Brightness({brightness:x/100})},+v,+v!==0)},'sl-input');I('fCo',function(v){setF('Contrast',function(x){return new F.filters.Contrast({contrast:x/100})},+v,+v!==0)},'sl-input');I('fSa',function(v){setF('Saturation',function(x){return new F.filters.Saturation({saturation:x/100})},+v,+v!==0)},'sl-input');I('fBl',function(v){setF('Blur',function(x){return new F.filters.Blur({blur:x/100})},+v,+v>0)},'sl-input');
 I('fGr',function(v,e){setF('Grayscale',function(){return new F.filters.Grayscale()},0,e.checked)});I('fSe',function(v,e){setF('Sepia',function(){return new F.filters.Sepia()},0,e.checked)});I('fIn',function(v,e){setF('Invert',function(){return new F.filters.Invert()},0,e.checked)})}
cv.on('object:moving',function(e){if(S.snap){var o=e.target,g=S.zoomPct>=400?10:20;o.set({left:Math.round(o.left/g)*g,top:Math.round(o.top/g)*g})}props()});
cv.on('object:scaling',function(){props()});cv.on('object:rotating',function(){props()});
function canvasSize(w,h){S.W=w;S.H=h;art.set({width:w,height:h});cv.requestRenderAll();fit();pushH('size');props()}

/* ---------- действия ---------- */
function act(o,fn){var a=cv.getActiveObjects().filter(vis);a.forEach(fn);cv.requestRenderAll();pushH('act');props()}
function align(k){var a=cv.getActiveObjects().filter(vis);if(!a.length){toast('Выберите объект');return}var box=a.length>1?cv.getActiveObject().getBoundingRect():{left:0,top:0,width:S.W,height:S.H};
 if(a.length>1){var bs=a.map(function(o){return o.getBoundingRect()}),x1=Math.min.apply(0,bs.map(function(b){return b.left})),y1=Math.min.apply(0,bs.map(function(b){return b.top})),x2=Math.max.apply(0,bs.map(function(b){return b.left+b.width})),y2=Math.max.apply(0,bs.map(function(b){return b.top+b.height})),z=cv.getZoom(),vt=cv.viewportTransform;box={left:(x1-vt[4])/z,top:(y1-vt[5])/z,width:(x2-x1)/z,height:(y2-y1)/z}}
 a.forEach(function(o){var w=o.getScaledWidth(),h=o.getScaledHeight();var oc=o.group?o.getCenterPoint():null;var L=o.left,T=o.top;
  if(k==='l')o.set('left',box.left);if(k==='r')o.set('left',box.left+box.width-w);if(k==='c')o.set('left',box.left+(box.width-w)/2);if(k==='t')o.set('top',box.top);if(k==='b')o.set('top',box.top+box.height-h);if(k==='m')o.set('top',box.top+(box.height-h)/2);o.setCoords()});cv.requestRenderAll();pushH('align');props()}
function dist(h){var a=cv.getActiveObjects().filter(vis);if(a.length<3){toast('Для распределения выберите 3+ объекта');return}var key=h?'left':'top',sz=h?'getScaledWidth':'getScaledHeight';a=a.slice().sort(function(p,q){return p[key]-q[key]});var f=a[0][key],l=a[a.length-1][key]+a[a.length-1][sz]();var tot=a.reduce(function(s,o){return s+o[sz]()},0),gap=(l-f-tot)/(a.length-1),pos=f;a.forEach(function(o){o.set(key,pos);pos+=o[sz]()+gap;o.setCoords()});cv.requestRenderAll();pushH('dist')}
function group(){var a=cv.getActiveObject();if(a&&a.type==='activeselection'){var g=a.toGroup();g.set('name','Группа');cv.setActiveObject(g);cv.requestRenderAll();pushH('group')}else toast('Выберите 2+ объекта')}
function ungroup(){var a=cv.getActiveObject();if(a&&a.type==='group'){var items=a.removeAll?a.removeAll():[];var g=a;var m=g.calcTransformMatrix();S.loading=true;cv.remove(g);items.forEach(function(it){F.util.addTransformToObject(it,m);it.setCoords();cv.add(it)});S.loading=false;pushH('ungroup');layers()}else toast('Выберите группу')}
function dup(){var a=cv.getActiveObject();if(!a||a.dzArt)return;a.clone(EXTRA).then(function(c){c.set({left:a.left+20,top:a.top+20,name:(a.name||nameOf(a))+' копия'});cv.discardActiveObject();if(c.type==='activeselection'){c.canvas=cv;c.forEachObject(function(o){cv.add(o)});c.setCoords()}else cv.add(c);cv.setActiveObject(c);cv.requestRenderAll()})}
function del(){var a=cv.getActiveObjects().filter(vis);if(!a.length){toast('Нечего удалять');return}cv.discardActiveObject();a.forEach(function(o){cv.remove(o)})}
function order(k){var o=cv.getActiveObject();if(!o||o.dzArt)return;if(k==='up')cv.bringObjectForward(o);if(k==='down'){var i=cv.getObjects().indexOf(o);if(i>1)cv.sendObjectBackwards(o)}if(k==='top')cv.bringObjectToFront(o);if(k==='bottom'){cv.sendObjectToBack(o);cv.sendObjectToBack(art)}pushH('order');layers()}
function fileIn(f){if(!f)return;if(/\.json$/i.test(f.name)){f.text().then(function(t){S.loading=true;loadSnap(t).then(function(){fit();pushH('open')})});return}var r=new FileReader();r.onload=function(){addImage(r.result,f.name.replace(/\.[^.]+$/,''))};r.readAsDataURL(f)}
function addImage(url,name,at){return IMG.fromURL(url,{crossOrigin:'anonymous'}).then(function(im){var m=Math.min(1,(S.W*.9)/im.width,(S.H*.9)/im.height);im.set({scaleX:m,scaleY:m,name:name||'Изображение'});if(at)im.set(at);else{im.set({left:(S.W-im.width*m)/2,top:(S.H-im.height*m)/2})}cv.add(im);cv.setActiveObject(im);cv.requestRenderAll();return im}).catch(function(e){toast('Не удалось открыть изображение: '+e)})}
function dl(url,name){var a=document.createElement('a');a.href=url;a.download=name;document.body.appendChild(a);a.click();a.remove()}
function hideEdit(fn){var h=[];cv.getObjects().forEach(function(o){if(o.dzMask&&o.visible!==false){o.visible=false;h.push(o)}});cv.discardActiveObject();try{return fn()}finally{h.forEach(function(o){o.visible=true});cv.requestRenderAll()}}
function expPNG(m,fmt,q){return hideEdit(function(){return cv.toDataURL({format:fmt||'png',quality:q||.92,left:0,top:0,width:S.W,height:S.H,multiplier:m||1,enableRetinaScaling:false})})}
function exportDlg(){var d=$('#dzExp');if(!d){d=document.createElement('sl-dialog');d.id='dzExp';d.label='Экспорт';d.innerHTML='<div class="dz-row"><sl-select id="eF" value="png" label="Формат" hoist><sl-option value="png">PNG</sl-option><sl-option value="jpeg">JPG</sl-option><sl-option value="webp">WebP</sl-option><sl-option value="svg">SVG (вектор)</sl-option></sl-select><sl-select id="eM" value="1" label="Масштаб" hoist><sl-option value="1">1x</sl-option><sl-option value="2">2x</sl-option><sl-option value="4">4x</sl-option></sl-select></div><div class="dz-row"><label class="l">Качество JPG/WebP<sl-range id="eQ" min="30" max="100" value="92"></sl-range></label></div><sl-button slot="footer" variant="primary" id="eGo">Скачать</sl-button><sl-button slot="footer" id="eSel">Только выделенное PNG</sl-button>';document.body.appendChild(d);
  $('#eGo',d).onclick=function(){var f=$('#eF',d).value,m=+$('#eM',d).value;if(f==='svg'){var s=hideEdit(function(){return cv.toSVG({viewBox:{x:0,y:0,width:S.W,height:S.H},width:S.W,height:S.H})});dl(URL.createObjectURL(new Blob([s],{type:'image/svg+xml'})),'nox-design.svg')}else dl(expPNG(m,f,$('#eQ',d).value/100),'nox-design.'+(f==='jpeg'?'jpg':f));d.hide()};
  $('#eSel',d).onclick=function(){var r=selRect();if(!r){toast('Нет выделения');return}dl(cropURL(r,+$('#eM',d).value),'nox-selection.png');d.hide()}}
 openD(d)}
function selRect(){var a=cv.getActiveObject();if(a&&!a.dzArt){var b=a.getBoundingRect(),z=cv.getZoom(),vt=cv.viewportTransform;return{l:(b.left-vt[4])/z,t:(b.top-vt[5])/z,w:b.width/z,h:b.height/z}}return null}
function cropURL(r,m,maxEdge,fmt){var k=m||1;if(maxEdge){k=Math.min(k,maxEdge/Math.max(r.w,r.h))}return hideEdit(function(){return cv.toDataURL({format:fmt||'png',quality:.88,left:r.l,top:r.t,width:r.w,height:r.h,multiplier:k,enableRetinaScaling:false})})}
function keysDlg(){var d=$('#dzKeys');if(!d){d=document.createElement('sl-dialog');d.id='dzKeys';d.label='Горячие клавиши';d.innerHTML='<div style="columns:2;font-size:13px;line-height:2">'+TOOLS.map(function(t){return'<b style="color:var(--ac,#e9b465)">'+t[3]+'</b> '+esc(t[2].replace(/ \(.*\)/,''))}).join('<br>')+'<br><b>Ctrl+Z / Ctrl+Shift+Z</b> отмена / повтор<br><b>Ctrl+C / V / D</b> копировать / вставить / дубль<br><b>Ctrl+G / Shift+G</b> группа / разгруппировать<br><b>Del</b> удалить<br><b>[ ]</b> порядок слоёв<br><b>Стрелки</b> сдвиг (Shift 10 px)<br><b>+ / -</b> зум<br><b>Ctrl+0 / Ctrl+1</b> вписать / 100%<br><b>Ctrl+S / Ctrl+E</b> сохранить / экспорт<br><b>Пробел</b> рука<br><b>Shift</b> пропорции фигуры; Shift+пипетка = обводка<br><b>Ctrl+Enter</b> запуск ИИ<br><b>?</b> эта справка</div>';document.body.appendChild(d)}openD(d)}
var ACT={undo:undo,redo:redo,'al-l':function(){align('l')},'al-c':function(){align('c')},'al-r':function(){align('r')},'al-t':function(){align('t')},'al-m':function(){align('m')},'al-b':function(){align('b')},'dist-h':function(){dist(true)},'dist-v':function(){dist(false)},group:group,ungroup:ungroup,dup:dup,del:del,open:function(){$('#dzFile').click()},savej:function(){dl(URL.createObjectURL(new Blob([snap()],{type:'application/json'})),'nox-project.json')},export:exportDlg,copypng:function(){try{var u=expPNG(1);fetch(u).then(function(r){return r.blob()}).then(function(b){return navigator.clipboard.write([new ClipboardItem({'image/png':b})])}).then(function(){toast('PNG в буфере')}).catch(function(e){toast('Буфер недоступен: '+e.message)})}catch(e){toast('Буфер недоступен')}},keys:keysDlg,
 zin:function(){setZoom(cv.getZoom()*1.5)},zout:function(){setZoom(cv.getZoom()/1.5)},fit:fit,z100:function(){setZoom(1)},up:function(){order('up')},down:function(){order('down')},top:function(){order('top')},bottom:function(){order('bottom')},
 newlay:function(){var g=new F.Group([],{name:'Слой '+(userObjs().length+1),left:0,top:0,width:10,height:10});cv.add(g);cv.setActiveObject(g)},
 rename:function(){var o=cv.getActiveObject();if(!o||o.dzArt){toast('Выберите слой');return}var d=document.createElement('sl-dialog');d.label='Имя слоя';d.innerHTML='<sl-input value="'+esc(o.name||'')+'" autofocus></sl-input><sl-button slot="footer" variant="primary">OK</sl-button>';document.body.appendChild(d);openD(d);var i=$('sl-input',d),go=function(){o.set('name',i.value||o.name);pushH('rename');layers();d.hide()};$('sl-button',d).onclick=go;i.addEventListener('keydown',function(e){if(e.key==='Enter')go()});d.addEventListener('sl-after-hide',function(){d.remove()})},
 lockSel:function(){act(0,function(o){var l=!o.lockMovementX;o.set({lockMovementX:l,lockMovementY:l,lockRotation:l,lockScalingX:l,lockScalingY:l})})},
 flipx:function(){act(0,function(o){o.set('flipX',!o.flipX)})},flipy:function(){act(0,function(o){o.set('flipY',!o.flipY)})},rot90:function(){act(0,function(o){o.rotate(((o.angle||0)+90)%360)})},
 grad:function(){act(0,function(o){var c1=typeof o.fill==='string'&&o.fill?o.fill:'#e9b465',c2=typeof o.stroke==='string'&&o.stroke?o.stroke:'#6b3cff';o.set('fill',new F.Gradient({type:'linear',coords:{x1:0,y1:0,x2:o.width,y2:o.height},colorStops:[{offset:0,color:c1},{offset:1,color:c2}]}))})},nofill:function(){act(0,function(o){o.set('fill','')})},
 bold:function(){act(0,function(o){o.set('fontWeight',o.fontWeight==='bold'?'normal':'bold')})},italic:function(){act(0,function(o){o.set('fontStyle',o.fontStyle==='italic'?'normal':'italic')})},underline:function(){act(0,function(o){o.set('underline',!o.underline)})},'ta-left':function(){act(0,function(o){o.set('textAlign','left')})},'ta-center':function(){act(0,function(o){o.set('textAlign','center')})},'ta-right':function(){act(0,function(o){o.set('textAlign','right')})},
 clrmask:function(){S.mask.forEach(function(m){cv.remove(m)});S.mask=[];maskInfo();pushH('mask')},
 maskinv:function(){S.maskInv=!S.maskInv;toast(S.maskInv?'Маска инвертирована: ИИ тронет всё, КРОМЕ закрашенного':'Маска обычная');maskInfo()},
 palette:function(){var a=cv.getActiveObject();var u=a&&a.type==='image'?a.toDataURL({format:'png',multiplier:.2}):expPNG(.25);showPalette(palette(u))},
 sheet:function(){$side.classList.toggle('open')}};
cs=null;
['1920x1080','1080x1080','1080x1920','512x512'].forEach(function(s){var p=s.split('x');ACT['cs-'+s]=function(){canvasSize(+p[0],+p[1])}});
function palette(url){return new Promise(function(res){var im=new Image();im.onload=function(){var c=document.createElement('canvas');c.width=c.height=48;var x=c.getContext('2d');x.drawImage(im,0,0,48,48);var d=x.getImageData(0,0,48,48).data,m={};for(var i=0;i<d.length;i+=4){if(d[i+3]<128)continue;var k=[d[i]>>5,d[i+1]>>5,d[i+2]>>5].join();(m[k]=m[k]||[0,0,0,0]);m[k][0]+=d[i];m[k][1]+=d[i+1];m[k][2]+=d[i+2];m[k][3]++}var arr=Object.keys(m).map(function(k){var v=m[k];return{n:v[3],c:[v[0]/v[3],v[1]/v[3],v[2]/v[3]].map(Math.round)}}).sort(function(a,b){return b.n-a.n});var out=[];arr.forEach(function(a){if(out.length<8&&out.every(function(o){return Math.abs(o[0]-a.c[0])+Math.abs(o[1]-a.c[1])+Math.abs(o[2]-a.c[2])>60}))out.push(a.c)});res(out.map(function(c){return'#'+c.map(function(v){return('0'+v.toString(16)).slice(-2)}).join('')}))};im.src=url})}
function showPalette(p){Promise.resolve(p).then(function(cols){aiOut('Палитра: '+cols.join(' '));cols.forEach(function(c){var r=new F.Rect({left:20+cols.indexOf(c)*70,top:S.H-90,width:60,height:60,fill:c,stroke:'#0003',strokeWidth:1,name:'Цвет '+c});cv.add(r)});toast('Палитра добавлена слоями')})}

/* делегирование кнопок */
root.addEventListener('click',function(e){var b=e.target.closest('[data-act]');if(b){var k=b.dataset.act;if(ACT[k])ACT[k]();else if(AIACT[k])AIACT[k]();else console.error('нет обработчика',k);return}
 b=e.target.closest('[data-tool]');if(b){setTool(b.dataset.tool);return}b=e.target.closest('[data-hi]');if(b){S.hi=+b.dataset.hi;loadSnap(S.hist[S.hi].s).then(renderHist)}});
$('#dzFile').addEventListener('change',function(e){fileIn(e.target.files[0]);e.target.value=''});
$stage.addEventListener('dragover',function(e){e.preventDefault()});$stage.addEventListener('drop',function(e){e.preventDefault();fileIn(e.dataTransfer.files[0])});
document.addEventListener('paste',function(e){var it=[].slice.call(e.clipboardData&&e.clipboardData.items||[]).filter(function(i){return/^image/.test(i.type)})[0];if(it&&!/INPUT|TEXTAREA/.test((document.activeElement||{}).tagName||'')){fileIn(it.getAsFile())}});
$('#dzZoom').addEventListener('sl-change',function(e){setZoom(+e.target.value/100)});
$('#dzSnap').addEventListener('sl-change',function(e){S.snap=e.target.checked});$('#dzGrid').addEventListener('sl-change',function(e){S.grid=e.target.checked;cv.requestRenderAll()});$('#dzPix').addEventListener('sl-change',function(e){S.pix=e.target.checked;setPix()});
var KEYS={};TOOLS.forEach(function(t){KEYS[t[3].toLowerCase()]=t[0]});
document.addEventListener('keydown',function(e){var tg=e.target,ed=/INPUT|TEXTAREA|SELECT/.test(tg.tagName||'')||/^SL-(INPUT|TEXTAREA|SELECT)/.test(tg.tagName||'')||tg.isContentEditable||(cv.getActiveObject()&&cv.getActiveObject().isEditing);
 if(!document.getElementById('dz'))return;
 if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){AIACT.run();e.preventDefault();return}
 if(ed)return;var k=e.key.toLowerCase(),c=e.ctrlKey||e.metaKey;
 if(c&&k==='z'){e.shiftKey?redo():undo();e.preventDefault();return}if(c&&k==='y'){redo();e.preventDefault();return}
 if(c&&k==='d'){dup();e.preventDefault();return}if(c&&k==='g'){e.shiftKey?ungroup():group();e.preventDefault();return}
 if(c&&k==='s'){ACT.savej();e.preventDefault();return}if(c&&k==='e'){exportDlg();e.preventDefault();return}
 if(c&&k==='c'){var a=cv.getActiveObject();if(a&&!a.dzArt)a.clone(EXTRA).then(function(x){S.clip=x});e.preventDefault();return}
 if(c&&k==='v'&&S.clip){S.clip.clone(EXTRA).then(function(x){x.set({left:x.left+20,top:x.top+20});cv.discardActiveObject();if(x.type==='activeselection'){x.forEachObject(function(o){cv.add(o)})}else cv.add(x);cv.setActiveObject(x);S.clip=x})}
 if(c&&k==='0'){fit();e.preventDefault();return}if(c&&k==='1'){setZoom(1);e.preventDefault();return}
 if(c)return;
 if(k==='delete'||k==='backspace'){del();e.preventDefault();return}if(k==='enter'&&S.tool==='pen'){finishPen();return}if(k==='escape'){if(S.tool==='pen'){penPts=null;if(penPrev){cv.remove(penPrev);penPrev=null}}cv.discardActiveObject();setTool('select');cv.requestRenderAll();return}
 if(k===' '){S._space=true;cv.defaultCursor='grab';e.preventDefault();return}
 if(k==='+'||k==='='){ACT.zin();return}if(k==='-'){ACT.zout();return}if(k==='['){order('down');return}if(k===']'){order('up');return}if(k==='?'){keysDlg();return}
 if(k.indexOf('arrow')===0){var o=cv.getActiveObjects().filter(vis),st=e.shiftKey?10:1;if(o.length){o.forEach(function(x){if(k==='arrowleft')x.left-=st;if(k==='arrowright')x.left+=st;if(k==='arrowup')x.top-=st;if(k==='arrowdown')x.top+=st;x.setCoords()});cv.requestRenderAll();pushH('nudge');props();e.preventDefault()}return}
 if(KEYS[k]){setTool(KEYS[k])}});
document.addEventListener('keyup',function(e){if(e.key===' '){S._space=false;setTool(S.tool)}});

/* ---------- ИИ ---------- */
var STYLES={'flat':'плоский вектор, чистые формы, ограниченная палитра','icon':'иконка, скруглённые формы, мягкий градиент','logo':'логотип, минимализм, сильный силуэт','water':'акварельный стиль с мягкими градиентами','blue':'чертёж, тонкие линии, технический стиль','comic':'комикс, жирный контур, яркие цвета','mini':'минимализм, много воздуха','neon':'неон, тёмный фон, светящиеся контуры'};
var PRESETS={none:'',photo:'Фотореалистичный стиль: естественный мягкий свет, реалистичные пропорции и фактуры, натуральный цвет без перенасыщения, лёгкое плёночное зерно, без пластикового вида. Избегать: лишних пальцев, искажённых рук, артефактов сжатия, водяных знаков, мультяшности.',portrait:'Портрет (только вымышленный взрослый персонаж): объектив 85 мм, f/1.8, мягкий боковой свет, естественная кожа с порами и микрорельефом, симметричные глаза, правильные руки. Избегать: пластиковой кожи, лишних пальцев, одинаковых зубов, искажённых пропорций.',nature:'Природа: естественное золотое освещение, глубина резкости, реалистичные текстуры листвы, камня и воды, широкий динамический диапазон, 35 мм. Избегать: перенасыщения, HDR-ореолов, повторяющихся узоров.',keep:'Сохранить оригинал: ничего вне указанной области не менять, не менять цвет, резкость и композицию исходного изображения; править только указанное.'};
var MODES={sel:'Перерисовать выделенное',keep:'Сохранить остальное (добавить поверх)',style:'Только стиль (форма и позиции те же)',bg:'Только фон (передний план не трогать)'};
var SKETCH=['sketch','улучши'];
var cs;
function aiUI(){var A=$('#dzAI');A.innerHTML='<div class="dz-row"><span class="dz-badge ok" id="bVis">Vision: готово (Qwen3.6)</span><span class="dz-badge off" id="bGen">Генератор: проверка</span></div>'+
 '<div class="dz-h">Режим</div><div class="dz-row"><sl-select id="aMode" value="sel" style="flex:1" hoist label="Что делать">'+Object.keys(MODES).map(function(k){return'<sl-option value="'+k+'">'+MODES[k]+'</sl-option>'}).join('')+'</sl-select></div>'+
 '<div class="dz-row"><sl-select id="aPre" value="none" style="width:48%" hoist label="Пресет"><sl-option value="none">Без пресета</sl-option><sl-option value="photo">Фото-реализм</sl-option><sl-option value="portrait">Портрет</sl-option><sl-option value="nature">Природа</sl-option><sl-option value="keep">Сохранить оригинал</sl-option></sl-select><sl-select id="aSty" value="flat" style="width:48%" hoist label="Стиль">'+Object.keys(STYLES).map(function(k){return'<sl-option value="'+k+'">'+STYLES[k].split(',')[0]+'</sl-option>'}).join('')+'</sl-select></div>'+
 '<div class="dz-row"><sl-select id="aSrc" value="auto" style="width:60%" hoist label="Что отправить"><sl-option value="auto">Авто: маска, выделение или весь холст</sl-option><sl-option value="sel">Выделение</sl-option><sl-option value="all">Весь холст</sl-option></sl-select><sl-select id="aLang" value="ru" style="width:36%" hoist label="Язык текста"><sl-option value="ru">Русский</sl-option><sl-option value="en">English</sl-option></sl-select></div>'+
 '<div class="dz-row"><sl-textarea id="aTxt" rows="3" resize="auto" style="width:100%" placeholder="Что сделать: например «перерисуй каракули как аккуратный дом с садом»" label="Команда ИИ"></sl-textarea></div>'+
 '<div class="dz-row"><sl-button variant="primary" data-act="run" style="flex:1">Выполнить (Ctrl+Enter)</sl-button><sl-button data-act="cancel">Отмена</sl-button></div><div id="dzProg"><sl-progress-bar indeterminate label="ИИ думает"></sl-progress-bar><div id="dzProgT" style="font-size:12px;color:var(--mu)"></div></div>'+
 '<div class="dz-h">Быстрые ИИ-функции (vision)</div><div class="dz-grid">'+[['sketch','Каракули в SVG-слои','Перерисовать рисунок как векторные слои'],['vec','Скетч в вектор','Чистый вектор по наброску'],['improve','Улучшить','Улучшить выбранное'],['restyle','В стиле','Перерисовать в выбранном стиле'],['variants','3 варианта','Три варианта подряд, скрытые слои'],['logo','Логотип','Логотип по описанию'],['describe','Описать выделение','Текстовое описание'],['alt','Альт-текст','Короткий альт-текст'],['critique','Критика дизайна','Что улучшить'],['font','Подбор шрифта','Подобрать шрифт к тексту'],['layout','Авто-layout','ИИ расставит объекты'],['rewrite','Переписать текст','Переписать текстовые слои'],['translate','Перевести текст','Перевод текстовых слоёв'],['html','UI в HTML','Сделать HTML-макет по наброску'],['palette2','Палитра (ИИ)','Палитра и подсказки по цвету'],['plan','Показать план','Только план без запуска']].map(function(x){return'<sl-tooltip content="'+x[2]+'"><sl-button class="sm" data-act="ai-'+x[0]+'" style="width:100%">'+x[1]+'</sl-button></sl-tooltip>'}).join('')+'</div>'+
 '<div class="dz-h">Генератор картинок</div><div id="dzGenNote" class="dz-row" style="font-size:12px;color:var(--mu)">Проверяется…</div><div class="dz-grid">'+[['sk2img','Скетч в изображение'],['rmbg','Удалить фон'],['outp','Расширить холст'],['gfill','Заливка по маске'],['upsc','Апскейл ×2'],['txt2img','Текст в картинку']].map(function(x){return'<sl-button class="sm gen" data-act="gen-'+x[0]+'" style="width:100%" disabled>'+x[1]+'</sl-button>'}).join('')+'</div>'+
 '<div class="dz-h">Результат</div><div id="dzAIOut" class="dz-out">Нарисуйте каракули (K), напишите команду и нажмите «Каракули в SVG-слои». ИИ вернёт редактируемые слои: фигуры, пути и текст отдельными объектами.</div>';
 $('#aMode').addEventListener('sl-change',function(e){S.mode=e.target.value});maskInfo()}
function aiOut(t){var o=$('#dzAIOut');if(o)o.textContent=t}
function maskInfo(){var n=S.mask.length;var b=$('#bMask');}
/* размер и регион */
function region(){var src=($('#aSrc')||{}).value||'auto',r=null,usedMask=false;
 if(src!=='all'){if(src==='auto'&&S.mask.length){var bs=S.mask.map(function(m){var b=m.getBoundingRect(true,true);return b}),x1=Math.min.apply(0,bs.map(function(b){return b.left})),y1=Math.min.apply(0,bs.map(function(b){return b.top})),x2=Math.max.apply(0,bs.map(function(b){return b.left+b.width})),y2=Math.max.apply(0,bs.map(function(b){return b.top+b.height}));r={l:Math.max(0,x1),t:Math.max(0,y1),w:Math.min(S.W,x2)-Math.max(0,x1),h:Math.min(S.H,y2)-Math.max(0,y1)};usedMask=true}else{var a=cv.getActiveObject();if(a&&!a.dzArt){var bb=a.getBoundingRect(true,true);r={l:bb.left,t:bb.top,w:bb.width,h:bb.height}}else if(src==='sel'){return null}}}
 if(!r)r={l:0,t:0,w:S.W,h:S.H};r.l=Math.max(0,r.l);r.t=Math.max(0,r.t);r.w=Math.max(8,Math.min(r.w,S.W-r.l));r.h=Math.max(8,Math.min(r.h,S.H-r.t));r.mask=usedMask;return r}
function cfg(){var g=function(i){return($('#'+i)||{}).value};return{mode:g('aMode')||'sel',pre:g('aPre')||'none',sty:g('aSty')||'flat',txt:(g('aTxt')||'').trim(),lang:g('aLang')||'ru'}}
function describeObjs(){return userObjs().filter(function(o){return o.visible!==false}).slice(0,40).map(function(o){return{id:o.name||o.type,type:o.type,x:Math.round(o.left),y:Math.round(o.top),w:Math.round(o.getScaledWidth()),h:Math.round(o.getScaledHeight()),text:o.type==='textbox'?o.text:undefined,fill:typeof o.fill==='string'?o.fill:undefined}})}
var SVGRULES='Верни ТОЛЬКО SVG (без пояснений и без ```), компактно: <svg viewBox="0 0 W H" xmlns="http://www.w3.org/2000/svg">. Структура: <g id="имя-группы"> с вложенными фигурами; КАЖДАЯ деталь отдельный элемент с понятным id латиницей (roof, wall, door, window-1, sun, leaf-1...). Каждый лист, ветка, деталь отдельно. Текст только элементом <text> (не контурами) с font-family и font-size. Без <image>, без фильтров, плоские цвета fill/stroke. Не больше 40 элементов.';
function buildPrompt(kind,c,r){var sk=Math.min(1,768/Math.max(r.w,r.h)),SW=Math.round(r.w*sk),SH=Math.round(r.h*sk);r.sw=SW;r.sh=SH;var base='Это изображение '+SW+'x'+SH+' пикселей (фрагмент холста дизайнера). ',pre=PRESETS[c.pre]?' Пресет: '+PRESETS[c.pre]:'',u=c.txt?' Команда пользователя: '+c.txt+'.':'',sty=' Стиль: '+STYLES[c.sty]+'.',mode={sel:' Перерисуй только то, что в кадре.',keep:' Добавь недостающее, существующее не меняй: верни только НОВЫЕ элементы поверх.',style:' Сохрани композицию и позиции элементов, поменяй только стиль: цвета, обводки, формы деталей.',bg:' Нарисуй только ФОН; передний план и главные объекты не рисуй.'}[c.mode];
 var vb=' viewBox должен быть ровно 0 0 '+SW+' '+SH+', координаты элементов совпадают с пикселями изображения: каждая фигура на том же месте и того же размера, что на наброске. ';
 var P={sketch:base+'Это нарисованный от руки набросок/каракули. Распознай, что нарисовано, и перерисуй как аккуратную векторную иллюстрацию в тех же местах и пропорциях.'+sty+mode+u+pre+vb+SVGRULES,
 vec:base+'Преврати набросок в чистый вектор с сохранением форм и позиций.'+sty+u+pre+vb+SVGRULES,
 improve:base+'Улучши этот дизайн: выровняй, исправь пропорции и цвет, повысь читаемость, сохрани смысл.'+sty+mode+u+pre+vb+SVGRULES,
 restyle:base+'Перерисуй в новом стиле, сохраняя композицию.'+sty+mode+u+pre+vb+SVGRULES,
 logo:base+'Нарисуй логотип'+(c.txt?' для: '+c.txt:' по наброску')+'. Минимализм, сильный силуэт, 2-3 цвета, название текстом <text>.'+vb+SVGRULES,
 describe:base+'Опиши, что на изображении (объекты, цвета, композиция, текст). 5-8 коротких предложений. Язык: '+(c.lang==='ru'?'русский':'English')+'.'+u,
 alt:base+'Напиши альт-текст в одно-два предложения. Язык: '+(c.lang==='ru'?'русский':'English')+'.',
 critique:base+'Ты арт-директор. Дай 6 конкретных пунктов критики и правок: композиция, иерархия, контраст, типографика, цвет, выравнивание. Кратко.'+u,
 font:base+'Определи тип шрифта на изображении и предложи 5 близких шрифтов из Google Fonts с кратким пояснением. Если текста нет, предложи шрифты под настроение.'+u,
 palette2:base+'Выдели палитру: 6 HEX-цветов с ролью (фон, основной, акцент, текст...) и 2 совета по сочетанию. Верни список "роль: #hex".',
 html:base+'Это набросок интерфейса. Верни полный самодостаточный HTML-документ (inline CSS, без внешних ресурсов), повторяющий макет. Только код, без пояснений.'+u,
 layout:'Дан список объектов на холсте '+S.W+'x'+S.H+' (JSON): '+JSON.stringify(describeObjs())+'. Предложи выровненную композицию: сетка, отступы, иерархия.'+u+' Верни ТОЛЬКО JSON-массив [{"id":"..","x":N,"y":N}] с новыми левыми верхними координатами; без пояснений. Координаты внутри холста.',
 rewrite:'Дай новые тексты для текстовых слоёв (JSON): '+JSON.stringify(userObjs().filter(function(o){return o.type==='textbox'}).map(function(o){return{id:o.name,text:o.text}}))+'.'+(c.txt?' Задание: '+c.txt:' Сделай короче и выразительнее.')+' Верни ТОЛЬКО JSON-массив [{"id":"..","text":".."}].',
 translate:'Переведи тексты слоёв (JSON): '+JSON.stringify(userObjs().filter(function(o){return o.type==='textbox'}).map(function(o){return{id:o.name,text:o.text}}))+' на '+(c.lang==='ru'?'английский':'русский')+'. Верни ТОЛЬКО JSON-массив [{"id":"..","text":".."}].'};
 return P[kind]}
var NEEDIMG={layout:0,rewrite:0,translate:0};
/* сетевой запрос с прогрессом, отменой, таймаутом */
function vision(prompt,imgURL){if(S.ctl)S.ctl.abort();var ctl=new AbortController();S.ctl=ctl;var t0=Date.now(),to=setTimeout(function(){ctl.abort('timeout')},240000);
 $('#dzProg').classList.add('on');var iv=setInterval(function(){$('#dzProgT').textContent='Прошло '+Math.round((Date.now()-t0)/1000)+' с (до 2-4 мин). Можно отменить.'},500);
 var done=function(){clearTimeout(to);clearInterval(iv);$('#dzProg').classList.remove('on');S.ctl=null;S.busy=false};
 S.busy=true;
 return fetch('/vision/describe',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({image:imgURL||blank(),prompt:prompt}),signal:ctl.signal}).then(function(r){return r.json().then(function(j){if(!r.ok||!j.text)throw new Error(j.error||('HTTP '+r.status));return j.text})}).then(function(t){done();return t},function(e){done();throw(ctl.signal.aborted?new Error(ctl.signal.reason==='timeout'?'Таймаут ожидания ответа модели':'Отменено'):e)})}
function blank(){var c=document.createElement('canvas');c.width=c.height=8;c.getContext('2d').fillStyle='#fff';c.getContext('2d').fillRect(0,0,8,8);return c.toDataURL('image/png')}
/* план и подтверждение */
function plan(kind,c,r){var n=userObjs().length,m=S.mask.length,txt=[];var chg={sketch:'нарисую SVG-слои по вашему наброску',vec:'векторизую набросок в слои',improve:'добавлю улучшенную версию слоями',restyle:'добавлю версию в стиле «'+STYLES[c.sty].split(',')[0]+'»',variants:'добавлю 3 варианта слоями (скрыты, кроме первого)',logo:'нарисую логотип слоями',describe:'только прочитаю и опишу (холст не меняется)',alt:'только напишу альт-текст',critique:'только дам критику (холст не меняется)',font:'только предложу шрифты',palette2:'только предложу палитру',html:'сделаю HTML-макет в окне предпросмотра (холст не меняется)',layout:'изменю X/Y объектов (размеры не трогаю)',rewrite:'изменю текст в текстовых слоях',translate:'изменю текст в текстовых слоях'}[kind];
 var readonly=['describe','alt','critique','font','palette2','html'].indexOf(kind)>=0;
 var where=r.mask?'область маски ('+m+' шт., вокруг '+Math.round(r.w)+'x'+Math.round(r.h)+')':(r.l||r.t||r.w<S.W||r.h<S.H?'выделение '+Math.round(r.w)+'x'+Math.round(r.h)+' в ('+Math.round(r.l)+','+Math.round(r.t)+')':'весь холст');
 return{change:chg+(readonly||kind==='layout'||kind==='rewrite'||kind==='translate'?'':'; область: '+where+'; режим: '+MODES[c.mode]),keep:(readonly?'всё на холсте остаётся как есть':'все '+n+' существующих объектов остаются; пиксели вне '+(r.mask?'маски':'области')+' берутся из оригинала, а не из ответа модели; результат добавляется НОВЫМИ слоями, откат Ctrl+Z')+(c.pre==='keep'?'; пресет «Сохранить оригинал»':''),cmd:c.txt||'(без текста)'}}
function confirmPlan(p){return new Promise(function(res){var d=document.createElement('sl-dialog');d.label='План: проверьте перед запуском';d.innerHTML='<div style="font-size:14px;line-height:1.6"><b style="color:#e9b465">Что меняю:</b><br>'+esc(p.change)+'<br><br><b style="color:#9ff0c8">Что не трогаю:</b><br>'+esc(p.keep)+'<br><br><b>Команда:</b> '+esc(p.cmd)+'</div><sl-button slot="footer" variant="primary" data-y>Подтвердить и выполнить</sl-button><sl-button slot="footer" data-n>Отмена</sl-button>';document.body.appendChild(d);var ok=false;$('[data-y]',d).onclick=function(){ok=true;d.hide()};$('[data-n]',d).onclick=function(){d.hide()};d.addEventListener('sl-after-hide',function(){d.remove();res(ok)});openD(d)})}
/* разбор SVG в слои */
function cleanSVG(t){t=String(t||'').replace(/```[a-z]*\n?/gi,'').replace(/```/g,'');var i=t.indexOf('<svg');if(i<0)return null;t=t.slice(i);if(t.indexOf('</svg>')<0){var cut=Math.max(t.lastIndexOf('/>'),t.lastIndexOf('</g>'),t.lastIndexOf('</text>'));if(cut<0)return null;t=t.slice(0,cut+(t.charAt(cut+1)==='>'?2:(t.slice(cut,cut+4)==='</g>'?4:(t.slice(cut,cut+7)==='</text>'?7:2))));var o=(t.match(/<g[\s>]/g)||[]).length-(t.match(/<\/g>/g)||[]).length;while(o-->0)t+='</g>';t+='</svg>'}else t=t.slice(0,t.indexOf('</svg>')+6);return t}
function svgToLayers(txt,r,tag){var s=cleanSVG(txt);if(!s)return Promise.reject(new Error('Модель не вернула SVG'));var doc=new DOMParser().parseFromString(s,'image/svg+xml');if(doc.querySelector('parsererror'))return Promise.reject(new Error('SVG не разобран'));var svg=doc.documentElement,vb=(svg.getAttribute('viewBox')||'0 0 '+r.w+' '+r.h).split(/[\s,]+/).map(Number),vw=vb[2]||r.w,vh=vb[3]||r.h,k=Math.min(r.w/vw,r.h/vh),leaves=[];
 var LEAF=/^(path|rect|circle|ellipse|line|polygon|polyline|text)$/i;
 (function walk(n,chain,pre){[].slice.call(n.children).forEach(function(c){var tn=c.tagName.toLowerCase();if(tn==='g'){walk(c,chain.concat([c]),(pre?pre+'/':'')+(c.getAttribute('id')||'группа'))}else if(LEAF.test(tn)){leaves.push({el:c,chain:chain,name:(pre?pre+'/':'')+(c.getAttribute('id')||tn)})}})})(svg,[],'');
 if(!leaves.length)return Promise.reject(new Error('В SVG нет элементов'));
 var out=[],ps=leaves.slice(0,60).map(function(L){
  if(L.el.tagName.toLowerCase()==='text'){var inh=function(a){var v=L.el.getAttribute(a);if(v!=null)return v;for(var i=L.chain.length-1;i>=0;i--){v=L.chain[i].getAttribute(a);if(v!=null)return v}return null};var fs=parseFloat(inh('font-size'))||24,x=parseFloat(L.el.getAttribute('x'))||0,y=parseFloat(L.el.getAttribute('y'))||0,anc=inh('text-anchor');var tb=new F.Textbox(L.el.textContent.trim(),{left:r.l+x*k,top:r.t+(y-fs)*k,fontSize:fs*k,fontFamily:(inh('font-family')||'Inter').split(',')[0].replace(/['"]/g,'').trim(),fill:inh('fill')||'#111111',fontWeight:inh('font-weight')||'normal',name:L.name,width:Math.max(60,L.el.textContent.length*fs*.6*k),textAlign:anc==='middle'?'center':anc==='end'?'right':'left'});if(anc==='middle')tb.left-=tb.width/2;if(anc==='end')tb.left-=tb.width;out.push(tb);return Promise.resolve()}
  var w=doc.createElementNS('http://www.w3.org/2000/svg','svg');w.setAttribute('xmlns','http://www.w3.org/2000/svg');w.setAttribute('viewBox','0 0 '+vw+' '+vh);w.setAttribute('width',vw);w.setAttribute('height',vh);var cur=w;L.chain.forEach(function(g){var c=g.cloneNode(false);cur.appendChild(c);cur=c});cur.appendChild(L.el.cloneNode(true));
  return F.loadSVGFromString(new XMLSerializer().serializeToString(w)).then(function(res){var os=(res.objects||[]).filter(Boolean);if(!os.length)return;var o=os[0];o.set({left:r.l+o.left*k,top:r.t+o.top*k,scaleX:(o.scaleX||1)*k,scaleY:(o.scaleY||1)*k,name:L.name});out.push(o)}).catch(function(){})});
 return Promise.all(ps).then(function(){if(!out.length)throw new Error('Слои не созданы');return out})}
function insertLayers(objs,r,c,hidden,group){
 var gname=group||'ИИ',useMask=r.mask&&S.mask.length;
 var pc=useMask?Promise.all(S.mask.map(function(m){return m.clone()})).then(function(cl){var g=new F.Group(cl,{absolutePositioned:true});if(S.maskInv)g.inverted=true;return g}):Promise.resolve(null);
 return pc.then(function(clip){S.loading=true;objs.forEach(function(o){o.set({name:(gname?gname+': ':'')+o.name,visible:!hidden,selectable:true,evented:true});if(clip)o.set('clipPath',clip);cv.add(o);if(c.mode==='bg'){cv.sendObjectToBack(o);cv.sendObjectToBack(art)}});S.loading=false;pushH('ИИ');layers();cv.requestRenderAll()})}
function runKind(kind){if(S.busy){toast('ИИ уже работает. Дождитесь или нажмите «Отмена»');return}var c=cfg(),r=region();if(!r){toast('Нет выделения: выделите объект или выберите «Весь холст»');return}
 var textOnly=NEEDIMG.hasOwnProperty(kind),readonly=['describe','alt','critique','font','palette2','html'].indexOf(kind)>=0;
 if(kind==='sketch'||kind==='vec'||kind==='improve'||kind==='restyle'||kind==='logo'){if(!userObjs().length){toast('Нарисуйте что-нибудь (каракули K) или вставьте картинку');return}}
 if(['layout','rewrite','translate'].indexOf(kind)>=0&&!userObjs().length){toast('На холсте нет объектов');return}
 var p=plan(kind,c,r);if(kind==='plan'){return}
 return confirmPlan(p).then(function(ok){if(!ok)return;aiOut('Отправляю в модель…');var url=textOnly?null:cropURL(r,1,768);
  if(url&&url.length>6e6)url=cropURL(r,1,512,'jpeg');
  var pr=buildPrompt(kind,c,r);
  var runner=function(){return vision(pr,url)};
  if(kind==='variants'){var res=[];var seq=function(i){if(i>=3)return Promise.resolve();var cc=Object.assign({},c);return vision(buildPrompt('sketch',cc,r)+' Вариант №'+(i+1)+', отличающийся от других.',url).then(function(t){return svgToLayers(t,r).then(function(o){insertLayers(o,r,c,i>0,'Вариант '+(i+1)).then(function(){aiOut('Готов вариант '+(i+1)+' из 3')})})}).then(function(){return seq(i+1)})};return seq(0).then(function(){aiOut('Три варианта добавлены (скрыты 2 и 3, включайте глазом в «Слоях»).')},fail)}
  return runner().then(function(t){
   if(['sketch','vec','improve','restyle','logo'].indexOf(kind)>=0){return svgToLayers(t,r).then(function(o){return insertLayers(o,r,c,false,kind==='logo'?'Лого':'ИИ').then(function(){aiOut('Готово: '+o.length+' слоёв ('+o.slice(0,6).map(function(x){return x.name}).join(', ')+(o.length>6?'…':'')+'). Всё редактируется; оригинал не изменён.')})})}
   if(kind==='layout'||kind==='rewrite'||kind==='translate'){var m=t.match(/\[[\s\S]*\]/);if(!m)throw new Error('Модель не вернула JSON');var arr=JSON.parse(m[0]);var cnt=0;arr.forEach(function(it){var o=userObjs().filter(function(x){return(x.name||x.type)===it.id})[0];if(!o)return;if(kind==='layout'&&isFinite(it.x)&&isFinite(it.y)){o.set({left:+it.x,top:+it.y});o.setCoords();cnt++}else if(it.text!=null&&o.type==='textbox'){o.set('text',String(it.text));cnt++}});cv.requestRenderAll();pushH(kind);aiOut('Изменено объектов: '+cnt+' (Ctrl+Z отменяет)');return}
   if(kind==='html'){var h=t.replace(/```html?\n?|```/g,'');var d=document.createElement('sl-dialog');d.label='HTML-макет';d.style.setProperty('--width','min(960px,96vw)');d.innerHTML='<iframe sandbox style="width:100%;height:60vh;border:0;background:#fff;border-radius:8px"></iframe><sl-button slot="footer" data-dl>Скачать .html</sl-button>';document.body.appendChild(d);$('iframe',d).srcdoc=h;$('[data-dl]',d).onclick=function(){dl(URL.createObjectURL(new Blob([h],{type:'text/html'})),'nox-mockup.html')};d.addEventListener('sl-after-hide',function(){d.remove()});openD(d);aiOut('HTML-макет открыт в окне');return}
   aiOut(t)},fail)})}
function fail(e){aiOut('Ошибка ИИ: '+(e&&e.message||e));toast('ИИ: '+(e&&e.message||e))}
var AIACT={run:function(){var t=(cfg().txt||'').length?'sketch':'sketch';runKind(t)},cancel:function(){if(S.ctl)S.ctl.abort();else toast('Нечего отменять')},
 'ai-plan':function(){var c=cfg(),r=region();if(!r){toast('Нет выделения');return}var p=plan('sketch',c,r);aiOut('ЧТО МЕНЯЮ: '+p.change+'\nЧТО НЕ ТРОГАЮ: '+p.keep+'\nКОМАНДА: '+p.cmd)}};
['sketch','vec','improve','restyle','variants','logo','describe','alt','critique','font','layout','rewrite','translate','html','palette2'].forEach(function(k){AIACT['ai-'+k]=function(){runKind(k)}});
/* генератор: честное состояние + автопроверка */
function genCheck(){return fetch('/img/generate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt:'probe',width:64,height:64,steps:1})}).then(function(r){return r.json().catch(function(){return{}}).then(function(j){return{code:r.status,j:j}})}).catch(function(){return{code:0,j:{}}})}
function genState(){genCheck().then(function(x){var off=!(x.code===200||x.code===202)||/disabled/.test(JSON.stringify(x.j));S.gen=!off;var b=$('#bGen');if(b){b.className='dz-badge '+(off?'off':'ok');b.textContent=off?'Генератор: недоступно':'Генератор: включён'}var n=$('#dzGenNote');if(n)n.textContent=off?'Недоступно, включится после обучения (проверка раз в минуту). Пока работают vision-функции выше.':'Генератор включён: функции активны.';$$('.gen').forEach(function(b){b.disabled=off})})}
function genRun(kind){var c=cfg();var pr=(c.txt||'фотореалистичное изображение')+'. '+(PRESETS[c.pre]||'');var r=region()||{l:0,t:0,w:S.W,h:S.H};if(kind==='rmbg'||kind==='upsc'||kind==='gfill'||kind==='outp'||kind==='sk2img'){toast('Эта функция использует img2img: подключится к генератору, когда он начнёт принимать изображения');}
 fetch('/api/creative/image',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt:pr.slice(0,1000),width:Math.min(1024,Math.round(r.w/8)*8)||512,height:Math.min(1024,Math.round(r.h/8)*8)||512})}).then(function(x){return x.json()}).then(function(j){if(!j.job_id){aiOut('Генератор: '+JSON.stringify(j).slice(0,200));return}aiOut('Задание '+j.job_id+' в очереди…');var n=0,iv=setInterval(function(){fetch('/api/creative/job/'+j.job_id).then(function(x){return x.json()}).then(function(s){if(s.status==='done'){clearInterval(iv);addImage('/api/creative/file/'+j.job_id+'.png','Генерация',{left:r.l,top:r.t});aiOut('Готово')}else if(['error','refused','busy','unavailable'].indexOf(s.status)>=0){clearInterval(iv);aiOut('Генератор: '+s.status+' '+(s.reason||''))}else if(++n>400){clearInterval(iv)}})},3000)}).catch(function(e){aiOut('Генератор недоступен: '+e)})}
['sk2img','rmbg','outp','gfill','upsc','txt2img'].forEach(function(k){AIACT['gen-'+k]=function(){if(!S.gen){toast('Генератор выключен на время обучения. Включится автоматически.');return}genRun(k)}});

/* ---------- запуск ---------- */
function boot(){mkArt();size();fit();setTool('select');opts();layers();props();aiUI();renderHist();
 var saved=null;try{saved=localStorage.getItem('nox_dz_proj')}catch(e){}
 var go=function(){S.hist=[];S.hi=-1;pushH('start');setTimeout(function(){pushH('start')},300)};
 if(saved&&saved.length<4e6){loadSnap(saved).then(function(){fit();go()}).catch(function(){go()})}else go();
 genState();S.genIv=setInterval(function(){if(S.gen){clearInterval(S.genIv)}else genState()},60000);
 var first=true,uz=false;cv.on('mouse:wheel',function(){uz=true});new ResizeObserver(function(){size();if(!uz&&(first||S.zoomPct<=100)){fit()}first=false}).observe($stage);window.addEventListener('resize',function(){size()});[300,900,2000].forEach(function(t){setTimeout(function(){size();if(!uz)fit()},t)});
 if(!window.Sortable){var s=document.createElement('script');s.src='./vendor/sortablejs/Sortable.min.js';s.onload=layers;document.head.appendChild(s)}
 window.NOXDZ={cv:cv,S:S,run:runKind,svgToLayers:svgToLayers,region:region,setTool:setTool,ACT:ACT,AIACT:AIACT}}
if(window.customElements&&customElements.whenDefined)Promise.all(['sl-button','sl-icon-button','sl-tab-group','sl-select'].map(function(n){return customElements.whenDefined(n)})).then(boot);else boot();
})();
