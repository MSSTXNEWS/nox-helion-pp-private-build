/* Pure fake DOM for source-only D02 tests (NO WebView2 release claim).
 * Models actual HTML button dispatch, new graphics controls and cleanup.
 */
export function makeFakeD02Dom({coreIds=[
 'CONSCIOUSNESS','PERSONA','ATLAS','VOICE','REFLECTION','CORE','NEXUS','FORGE'
],reduced=false,throwObserver=false}={}){
 const observers=[],elements=[],intervals=new Map(),frames=new Map(),stored=new Map();
 let tick=1000,nextHandle=0;
 function element(tag='div'){
   const callbacks=new Map(),attrs=new Map(),children=[];
   const node={tagName:tag.toUpperCase(),dataset:{},children,attributes:attrs,
     className:'',textContent:'',hidden:false,parentElement:null,ownerDocument:null,
     setAttribute(name,value){attrs.set(name,String(value));},
     getAttribute(name){return attrs.has(name)?attrs.get(name):null;},
     removeAttribute(name){attrs.delete(name);},
     addEventListener(name,fn){if(!callbacks.has(name))callbacks.set(name,new Set());callbacks.get(name).add(fn);},
     removeEventListener(name,fn){callbacks.get(name)?.delete(fn);},
     emit(name,props={}){for(const fn of callbacks.get(name)||[])fn({type:name,target:node,preventDefault(){},...props});},
     append(...items){for(const item of items){children.push(item);item.parentElement=node;}},
     appendChild(item){node.append(item);return item;},
     prepend(item){children.unshift(item);item.parentElement=node;},
     replaceChildren(...items){for(const child of children)child.parentElement=null;children.splice(0);node.append(...items);},
     remove(){const i=node.parentElement?.children.indexOf(node)??-1;if(i>=0)node.parentElement.children.splice(i,1);node.parentElement=null;},
     querySelector(selector){
       const test=x=>selector==='strong'?x.tagName==='STRONG':
         selector.startsWith('.')?x.classList.contains(selector.slice(1)):
         selector.startsWith('#')?x.id===selector.slice(1):x.tagName===selector.toUpperCase();
       const visit=n=>{for(const c of n.children){if(test(c))return c;const nested=visit(c);if(nested)return nested;}return null;};
       return visit(node);
     },
     querySelectorAll(selector){
       const out=[];const visit=n=>{for(const c of n.children){if(selector.startsWith('.')?
         c.classList.contains(selector.slice(1)):c.tagName===selector.toUpperCase())out.push(c);visit(c);}};
       visit(node);return out;
     },
     focus(){node.focused=true;},
     getContext(){return null;},
     getBoundingClientRect(){return {width:800,height:500,left:0,top:0};}
   };
   node.classList={
     contains(name){return node.className.split(/\s+/).includes(name);},
     add(...names){const all=new Set(node.className.split(/\s+/).filter(Boolean));for(const n of names)all.add(n);node.className=[...all].join(' ');},
     remove(...names){const all=new Set(node.className.split(/\s+/).filter(Boolean));for(const n of names)all.delete(n);node.className=[...all].join(' ');},
     toggle(name,force){const state=force===undefined?!node.classList.contains(name):Boolean(force);
       if(state)node.classList.add(name);else node.classList.remove(name);return state;}
   };
   elements.push(node);return node;
 }
 const central=element('button');const cores=coreIds.map(id=>{const c=element('button');c.dataset.coreId=id;return c;});
 const stage=element('div');stage.classList.add('nox-orbit-stage');
 stage.querySelector=s=>s==='.nox-eclipse'?central:null;
 stage.querySelectorAll=s=>s==='.nox-orbit-core'?cores:s==='.nox-eclipse'?[central]:[];
 const home=element('section');home.classList.add('screen','active');
 home.querySelector=s=>s==='.nox-orbit-stage'?stage:null;
 const body=element('body'),events=new Map();
 class Observer{
   constructor(fn){this.fn=fn;}
   observe(){observers.push(this);}
   disconnect(){this.disconnected=true;if(throwObserver)throw Error('OBS_FAIL');}
 }
 const motion={matches:reduced,addEventListener(){},removeEventListener(){}};
 const view={
   MutationObserver:Observer,
   matchMedia:query=>query.includes('reduced-motion')?motion:{matches:false},
   localStorage:{getItem:k=>stored.has(k)?stored.get(k):null,setItem:(k,v)=>stored.set(k,v)},
   performance:{now:()=>tick},devicePixelRatio:1,
   requestAnimationFrame(fn){const id=++nextHandle;frames.set(id,fn);return id;},
   cancelAnimationFrame(id){frames.delete(id);},
   setInterval(fn){const id=++nextHandle;intervals.set(id,fn);return id;},
   clearInterval(id){intervals.delete(id);},
   addEventListener(){},removeEventListener(){}
 };
 const doc={
   body,defaultView:view,hidden:false,
   createElement:tag=>element(tag),
   createElementNS:(_,tag)=>element(tag),
   getElementById:id=>id==='home'?home:null,
   addEventListener(k,fn){if(!events.has(k))events.set(k,new Set());events.get(k).add(fn);},
   removeEventListener(k,fn){events.get(k)?.delete(fn);},
   emit(k){for(const fn of events.get(k)||[])fn({type:k,key:k});}
 };
 for(const node of elements)node.ownerDocument=doc;
 return {
   doc,home,stage,central,cores,observers,stored,
   motion,view,
   advance(ms=16){tick+=ms;const queue=[...frames];frames.clear();for(const [,fn] of queue)fn(tick);},
   intervals,frames,
   findDock:()=>home.children.find(n=>n.dataset.noxGraphicsDock==='v2'),
   findButtons:()=>home.children.find(n=>n.dataset.noxGraphicsDock==='v2')?.children[1]?.children
 };
}
