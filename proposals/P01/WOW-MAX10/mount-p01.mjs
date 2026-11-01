/* E01 P01 WOW MAX10: original lava/corona/gravity #30 + WOW51–200 #44.
 * T06 one visual scheduler, T07 click ACK route, T08 WebView2 host-only
 * shortcut, T09 ECO and Reduced Motion, T10 complete listener disposal.
 */
import {installNoxCinemaFX} from "../../NOX-CINEMA-FX/nox-cinema.mjs";
import {mountUnifiedCinema,reviewWowScopes} from "../../NOX-WOW-UNIFIED-1-150/gate.mjs";
import {createP01RouteDispatcher} from "./route-dispatch.mjs";
import {nativeVisualApproval} from "./p01-visual-approval.mjs";
import {createD02NativeVisualBus} from "./d02-native-events.mjs";
import {validateOwnerP01,shortcutRoute,validateMode} from "./scene-contract.mjs";
import {installP01Adaptive} from "./p01-responsive.mjs";
const mounted=new WeakSet();
// OS-level reduced motion always outranks the user-selected quality profile.
export function effectiveP01MotionMode(requested,reduced){
  return reduced===true?"REDUCED":requested;
}
export function shouldRunP01Visuals(homeIsActive,documentVisible){
  return homeIsActive===true && documentVisible===true;
}
export function nativeP01Feedback(result){
  // Browser clicks and pending promises are NEVER a completed native action.
  if(result?.ok===true && typeof result.receiptId==="string" &&
     /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(result.receiptId))
    return Object.freeze({state:"confirmed",receiptId:result.receiptId});
  const reason=typeof result?.reason==="string"&&/^[A-Z_]{1,80}$/.test(result.reason)
    ?result.reason:"ACK_MISSING";
  return Object.freeze({state:"hold",reason});
}
export function mountP01Owner(spec){
  const summary=validateOwnerP01(spec);
  const {root,orbs,menu,logicalMenu,buttons,hostPort,secondary=null,
    controls=[],panels=[],mode="BALANCED",shortcuts={},homeActive}=spec;
  if(mounted.has(root)||!validateMode(mode)||
     typeof homeActive!=="function"||
     !Array.isArray(controls)||!Array.isArray(panels)||
     [...controls,...panels].some(el=>!root.contains(el)))
    throw Error("P01_DUPLICATE_MOUNT_OR_UNTRUSTED_DECORATION");
  const dispatcher=createP01RouteDispatcher(hostPort);
  const cleanups=[];let fx=null,wow=null,nativeBus=null,disposed=false;
  let requestedMode=mode;
  const win=root.ownerDocument.defaultView;
  const motionQuery=typeof win?.matchMedia==="function"?
    win.matchMedia("(prefers-reduced-motion: reduce)"):null;
  const effectiveMode=()=>effectiveP01MotionMode(requestedMode,motionQuery?.matches===true);
  const saved=new Map([...menu,...logicalMenu,...buttons].map(x=>[x.element,{
    ack:x.element.dataset?.noxNativeAck, receipt:x.element.dataset?.noxNativeReceipt,
    state:x.element.dataset?.noxNativeState,reason:x.element.dataset?.noxNativeReason,
    hadAck:Object.hasOwn(x.element.dataset||{},"noxNativeAck"),
    hadReceipt:Object.hasOwn(x.element.dataset||{},"noxNativeReceipt"),
    hadState:Object.hasOwn(x.element.dataset||{},"noxNativeState"),
    hadReason:Object.hasOwn(x.element.dataset||{},"noxNativeReason")}]));
  const restore=()=>{for(const [el,s] of saved){
    if(s.hadAck)el.dataset.noxNativeAck=s.ack;else delete el.dataset.noxNativeAck;
    if(s.hadReceipt)el.dataset.noxNativeReceipt=s.receipt;else delete el.dataset.noxNativeReceipt;
    if(s.hadState)el.dataset.noxNativeState=s.state;else delete el.dataset.noxNativeState;
    if(s.hadReason)el.dataset.noxNativeReason=s.reason;else delete el.dataset.noxNativeReason;
  }};
  const watch=(element,type,handler)=>{
    element.addEventListener(type,handler);
    cleanups.push(()=>element.removeEventListener(type,handler));
  };
  try {
    // Existing approved renderer and original DOM; NO replacement assets.
    // Reuse the canonical scene, and attach the existing adaptive observer.
    // Both listeners and dataset flags are torn down with the ONE mount.
    const adaptive=installP01Adaptive(root);
    cleanups.push(()=>adaptive.destroy());
    fx=installNoxCinemaFX({root,orbs,controls,panels,profile:effectiveMode()});
    const doc=root.ownerDocument;
    const syncVisibility=()=>{
      if(disposed)return;
      let home=false;
      try{home=homeActive()===true;}catch{return;}
      const visible=doc.visibilityState!=="hidden" && doc.hidden!==true;
      fx.setVisible(shouldRunP01Visuals(home,visible));
    };
    watch(doc,"visibilitychange",syncVisibility);
    // Observe ONLY navigation state changes, never particle animation frames.
    const home=doc.getElementById?.("home");
    if(home&&typeof win?.MutationObserver==="function"){
      const navObserver=new win.MutationObserver(syncVisibility);
      navObserver.observe(home,{attributes:true,attributeFilter:["class"]});
      cleanups.push(()=>navObserver.disconnect());
    }
    syncVisibility();
    // One host-owned subscription: exact CoreIDs + the existing secondary WOW.
    nativeBus=createD02NativeVisualBus(hostPort,fx,orbs.slice(1).map(x=>x.id));
    if(secondary){
      reviewWowScopes();
      wow=mountUnifiedCinema(secondary,{
        mode:effectiveMode(),reducedMotion:motionQuery?.matches===true,
        trustedEventPort:{subscribe:handler=>nativeBus.subscribe(handler)},
        nativeAuthorizeShot:item=>nativeVisualApproval(hostPort,"shot",item),
        nativeAuthorizeComposition:item=>nativeVisualApproval(hostPort,"composition",item)
      });
    }
    for(const [items,kind] of [[menu,"MENU_TILE"],[logicalMenu,"MENU_SUBMENU"],[buttons,"BUTTON"]]){
      for(const item of items){
        const handler=async(event)=>{
          event?.preventDefault?.();
          if(disposed||dispatcher.isPending(item.routeId))return;
          item.element.dataset.noxNativeState="pending";
          delete item.element.dataset.noxNativeReason;
          const result=nativeP01Feedback(await dispatcher.invoke(item.routeId));
          if(disposed)return;
          item.element.dataset.noxNativeState=result.state;
          if(result.state==="confirmed"){
            item.element.dataset.noxNativeAck="true";
            item.element.dataset.noxNativeReceipt=result.receiptId;
            delete item.element.dataset.noxNativeReason;
          }else{
            // Do not make an unavailable route look like a successful button.
            delete item.element.dataset.noxNativeAck;
            delete item.element.dataset.noxNativeReceipt;
            item.element.dataset.noxNativeReason=result.reason;
          }
        };
        watch(item.element,"click",handler);
        // Native ACK and ACL remain the only authority for an asteroid route.
        // Semantic buttons/links already dispatch a browser-generated click on Enter.
        const target=item.element;
        if(!target.matches?.('button,input,select,textarea,summary,a[href]')){
          const attrs=['tabindex','role','aria-label'];
          const original=attrs.map(name=>[name,target.getAttribute(name)]);
          if(!target.hasAttribute('tabindex'))target.setAttribute('tabindex','0');
          if(!target.hasAttribute('role'))target.setAttribute('role','button');
          if(!target.hasAttribute('aria-label'))target.setAttribute('aria-label',String(item.label||item.id));
          cleanups.push(()=>{for(const [name,value] of original){
            if(value===null)target.removeAttribute(name);else target.setAttribute(name,value);
          }});
          watch(target,'keydown',e=>{
            if(e.target!==target||e.defaultPrevented||e.isComposing||e.repeat||
               e.altKey||e.ctrlKey||e.metaKey||e.shiftKey||
               !['Enter',' ','Spacebar'].includes(e.key))return;
            e.preventDefault?.();void handler(e);
          });
        }
      }
    }
    const onKey=async event=>{
      if(event.target?.nodeType===1&&!root.contains(event.target))return;
      let active=true;
      try{active=homeActive()===true;}catch{return;}
      const route=shortcutRoute(event,{...shortcuts,homeActive:active});
      if(!route)return;
      try{if(hostPort.isAvailable(route)!==true)return;}catch{return;}
      event.preventDefault?.();
      await dispatcher.invoke(route);
    };
    watch(root.ownerDocument,"keydown",onKey);
    if(motionQuery){
      const onMotion=()=>{
        if(disposed)return;
        const profile=effectiveMode();
        // Never leave the original D02 particle renderer in MAX when the OS
        // requests reduced motion, even if a secondary WOW layer errors.
        try{
          if(fx.setProfile(profile)!==true)return;
          wow?.setMode(profile);
        }catch{
          try{fx.setProfile("REDUCED");wow?.setMode("REDUCED");}catch{}
        }
      };
      if(typeof motionQuery.addEventListener==="function"){
        motionQuery.addEventListener("change",onMotion);
        cleanups.push(()=>motionQuery.removeEventListener("change",onMotion));
      }else if(typeof motionQuery.addListener==="function"){
        motionQuery.addListener(onMotion);
        cleanups.push(()=>motionQuery.removeListener(onMotion));
      }
    }
    mounted.add(root);
    return Object.freeze({
      summary,
      setMode(next){
        if(disposed||!validateMode(next))return false;
        const previous=requestedMode;
        const effective=effectiveP01MotionMode(next,motionQuery?.matches===true);
        if(!fx.setProfile(effective))return false;
        try{wow?.setMode(effective);
          requestedMode=next;return true;
        }catch{
          const restore=effectiveP01MotionMode(previous,motionQuery?.matches===true);
          fx.setProfile(restore);
          try{wow?.setMode(restore);}catch{}
          return false;
        }
      },
      status(){
        return Object.freeze({...summary,profile:fx.snapshot().profile,
          wowSourceMounted:!!wow,nativeCoreFeed:nativeBus.snapshot(),
          viewportLayout:root.dataset?.noxP01Layout||"unknown",
          viewportDpi:root.dataset?.noxP01Dpi||"unknown",
          hostIntegrationVerified:false,windowsExeAccepted:false});
      },
      destroy(){
        if(disposed)return;disposed=true;dispatcher.close();
        while(cleanups.length)cleanups.pop()();
        restore();
        try{wow?.destroy();}finally{
          try{nativeBus?.destroy();}finally{fx?.destroy();mounted.delete(root);}
        }
      }
    });
  }catch(err){
    dispatcher.close();
    while(cleanups.length)cleanups.pop()();
    restore();
    try{wow?.destroy();}finally{
      try{nativeBus?.destroy();}finally{fx?.destroy();}
    }
    throw err;
  }
}
