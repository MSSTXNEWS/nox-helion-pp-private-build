/** NOX R11 · Cinematic skin for the EIGHT ORIGINAL P01 menu tiles.
 * Rendering-only layer. The native P01 dispatcher exclusively owns clicks/ACK/ACL.
 * Preserves the ten logical submenu nodes, original media and five native controls.
 */
export const APPROVED_EIGHT=Object.freeze(['work','intelligence','knowledge','creative','people','development','world','system']);
export const APPROVED_TEN=Object.freeze(['work','intelligence','knowledge','learning','entertainment','people','creative','business','world','pc']);
const MODES=new Set(['MAX','BALANCED','ECO','REDUCED']);
const mounted=new WeakSet();

/** No new tile or route may be created. Fail closed on a stale source. */
export function validateCinematicMenu(root,tiles,worlds){
  if(!root||root.nodeType!==1||!root.ownerDocument||typeof root.contains!=='function'||
    root.dataset?.noxPage==='home'||root.closest?.('[data-nox-page="home"]'))
    throw Error('NOX_R11_CANONICAL_MENU_ROOT_REQUIRED');
  if(!Array.isArray(tiles)||tiles.length!==8||!Array.isArray(worlds)||worlds.length!==10)
    throw Error('NOX_R11_CANONICAL_EIGHT_TEN_REQUIRED');
  for(const [items,expected,label] of [[tiles,APPROVED_EIGHT,'TILE'],[worlds,APPROVED_TEN,'WORLD']]){
    const elements=new Set();
    items.forEach((item,i)=>{
      if(item?.id!==expected[i]||!item.element||item.element.nodeType!==1||
         !root.contains(item.element)||elements.has(item.element)||
         typeof item.routeId!=='string'||!/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(item.routeId))
        throw Error('NOX_R11_APPROVED_'+label+'_IDENTITY_HOLD');
      elements.add(item.element);
    });
  }
  return true;
}

export function mountCanonicalMenuCinematics({root,tiles,worlds,mode='BALANCED',
  documentRef=root?.ownerDocument,windowRef=documentRef?.defaultView}={}){
  validateCinematicMenu(root,tiles,worlds);
  if(mounted.has(root)||root.querySelector?.('[data-nox-r11-scene="true"]')||!MODES.has(mode)||
    !windowRef?.addEventListener||!documentRef?.addEventListener)
    throw Error('NOX_R11_SCENE_DUPLICATE_OR_HOST_HOLD');
  const doc=documentRef,win=windowRef;
  const motion=win.matchMedia?.('(prefers-reduced-motion: reduce)')||null;
  const supportsPointer=typeof win.PointerEvent!=='undefined';
  const clean=[];let dead=false,requested=mode;
  const remember=new Map();
  let before=null;
  // Pointer tilt is transient. Always restore owner-authored inline CSS rather
  // than deleting it on pointerleave, mode changes or reduced-motion signals.
  const restorePointer=el=>{
    const base=remember.get(el);
    if(!base)return;
    for(const [key,name] of [['x','--nox-r11-px'],['y','--nox-r11-py']]){
      if(base[key])el.style.setProperty(name,base[key]);
      else el.style.removeProperty(name);
    }
  };
  const clearPointerTilt=()=>{for(const el of remember.keys())restorePointer(el);};
  // Mount is a reversible transaction: exception paths also restore ORIGINAL
  // D02/MENU10 inline media/style and any preexisting status dataset values.
  const restoreOriginal=()=>{
    for(const [el,v] of remember){
      for(const [key,name] of [['x','--nox-r11-px'],['y','--nox-r11-py'],['ix','--nox-r11-index']]){
        if(v[key])el.style.setProperty(name,v[key]);else el.style.removeProperty(name);
      }
    }
    if(before){
      if(before.mode===null)delete root.dataset.noxR11CinematicMode;else root.dataset.noxR11CinematicMode=before.mode;
      if(before.hidden===null)delete root.dataset.noxR11CinematicHidden;else root.dataset.noxR11CinematicHidden=before.hidden;
    }
  };
  const attach=(target,type,handler,options)=>{
    target.addEventListener(type,handler,options);
    clean.push(()=>target.removeEventListener(type,handler,options));
  };
  const addClass=(el,cls)=>{
    // A class owned by the original D02/MENU10 must survive our teardown.
    if(el.classList.contains(cls))return;
    el.classList.add(cls);clean.push(()=>el.classList.remove(cls));
  };
  const scene=doc.createElement('div');scene.className='nox-r11-cinematic-atmosphere';
  scene.dataset.noxR11Scene='true';scene.setAttribute('aria-hidden','true');
  scene.style.pointerEvents='none';
  const glow=doc.createElement('div');glow.className='nox-r11-cinematic-beam';
  const dust=doc.createElement('div');dust.className='nox-r11-cinematic-dust';
  scene.append(glow,dust);
  // Source modifications are a reversible transaction. No original child replaced.
  try{
    addClass(root,'nox-r11-cinematic-root');
    for(const [i,item] of tiles.entries()){
      const el=item.element;
      addClass(el,'nox-r11-cinematic-tile');
      remember.set(el,{x:el.style.getPropertyValue('--nox-r11-px'),y:el.style.getPropertyValue('--nox-r11-py'),
        ix:el.style.getPropertyValue('--nox-r11-index')});
      el.style.setProperty('--nox-r11-index',String(i));
      if(supportsPointer){
        attach(el,'pointermove',e=>{
          if(dead||motion?.matches===true||root.dataset.noxR11CinematicMode!=='MAX'||doc.hidden)return;
          const rect=el.getBoundingClientRect?.();if(!rect?.width||!rect?.height)return;
          const nx=Math.max(-1,Math.min(1,(e.clientX-rect.left)/rect.width*2-1));
          const ny=Math.max(-1,Math.min(1,(e.clientY-rect.top)/rect.height*2-1));
          el.style.setProperty('--nox-r11-px',(nx*2.5).toFixed(1)+'px');
          el.style.setProperty('--nox-r11-py',(ny*2.5).toFixed(1)+'px');
        },{passive:true});
        attach(el,'pointerleave',()=>restorePointer(el));
      }
    }
    for(const world of worlds)addClass(world.element,'nox-r11-cinematic-subworld');
    // Never append a scene-wide atmosphere over the original HOME or other pages.
    // The eight approved tiles remain interactive even when no dedicated menu surface exists.
    const menuSurface=tiles[0].element.closest?.('[data-nox-page="menu"]');
    if(menuSurface && root.contains(menuSurface) && tiles.every(x=>menuSurface.contains(x.element))){
      addClass(menuSurface,'nox-r11-cinematic-surface');
      menuSurface.append(scene);
    }
    before={mode:Object.hasOwn(root.dataset,'noxR11CinematicMode')?root.dataset.noxR11CinematicMode:null,
      hidden:Object.hasOwn(root.dataset,'noxR11CinematicHidden')?root.dataset.noxR11CinematicHidden:null};
    const sync=()=>{
      if(dead)return;
      root.dataset.noxR11CinematicMode=motion?.matches===true?'REDUCED':requested;
      root.dataset.noxR11CinematicHidden=doc.hidden?'true':'false';
      if(root.dataset.noxR11CinematicMode!=='MAX'||doc.hidden)clearPointerTilt();
    };
    attach(doc,'visibilitychange',sync);
    if(motion?.addEventListener)attach(motion,'change',sync);
    else if(motion?.addListener){motion.addListener(sync);clean.push(()=>motion.removeListener(sync));}
    sync();mounted.add(root);
    return Object.freeze({
      status:()=>Object.freeze({originalMenuTiles:8,originalSubworlds:10,
        effectiveMode:root.dataset.noxR11CinematicMode,sourceOnly:true,nativeRoutesPreserved:true}),
      setMode(next){if(dead||!MODES.has(next))return false;requested=next;sync();return true;},
      destroy(){
        if(dead)return;dead=true;
        for(const f of clean.reverse())try{f()}catch{}
        restoreOriginal();
        scene.remove();mounted.delete(root);
      }
    });
  }catch(error){
    for(const f of clean.reverse())try{f()}catch{}
    restoreOriginal();
    scene.remove();mounted.delete(root);
    throw error;
  }
}
