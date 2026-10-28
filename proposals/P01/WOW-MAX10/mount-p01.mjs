/* E01 P01 WOW MAX10: original lava/corona/gravity #30 + WOW51–200 #44.
 * T06 one visual scheduler, T07 click ACK route, T08 WebView2 host-only
 * shortcut, T09 ECO and Reduced Motion, T10 complete listener disposal.
 */
import {installNoxCinemaFX} from "../../NOX-CINEMA-FX/nox-cinema.mjs";
import {mountUnifiedCinema,reviewWowScopes} from "../../NOX-WOW-UNIFIED-1-150/gate.mjs";
import {createP01RouteDispatcher} from "./route-dispatch.mjs";
import {installP01Adaptive} from "./p01-responsive.mjs";
import {nativeVisualApproval} from "./p01-visual-approval.mjs";
import {validateOwnerP01,shortcutRoute,validateMode} from "./scene-contract.mjs";
const mounted=new WeakSet();
export function mountP01Owner(spec){
  const summary=validateOwnerP01(spec);
  const {root,orbs,menu,buttons,hostPort,secondary=null,
    controls=[],panels=[],mode="BALANCED",shortcuts={},homeActive}=spec;
  if(mounted.has(root)||!validateMode(mode)||
     typeof homeActive!=="function"||
     !Array.isArray(controls)||!Array.isArray(panels)||
     [...controls,...panels].some(el=>!root.contains(el)))
    throw Error("P01_DUPLICATE_MOUNT_OR_UNTRUSTED_DECORATION");
  const dispatcher=createP01RouteDispatcher(hostPort);
  const cleanups=[];let fx=null,wow=null,adaptive=null,disposed=false;
  const saved=new Map([...menu,...buttons].map(x=>[x.element,{
    ack:x.element.dataset?.noxNativeAck, receipt:x.element.dataset?.noxNativeReceipt,
    hadAck:Object.hasOwn(x.element.dataset||{},"noxNativeAck"),
    hadReceipt:Object.hasOwn(x.element.dataset||{},"noxNativeReceipt")}]));
  const restore=()=>{for(const [el,s] of saved){
    if(s.hadAck)el.dataset.noxNativeAck=s.ack;else delete el.dataset.noxNativeAck;
    if(s.hadReceipt)el.dataset.noxNativeReceipt=s.receipt;else delete el.dataset.noxNativeReceipt;
  }};
  const watch=(element,type,handler)=>{
    element.addEventListener(type,handler);
    cleanups.push(()=>element.removeEventListener(type,handler));
  };
  try {
    // Existing approved renderer and original DOM; NO replacement assets.
    adaptive=installP01Adaptive(root);
    fx=installNoxCinemaFX({root,orbs,controls,panels,profile:mode});
    if(secondary){
      reviewWowScopes();
      wow=mountUnifiedCinema(secondary,{
        mode,trustedEventPort:{subscribe:handler=>{
          const detach=hostPort.subscribeNative(handler);
          if(typeof detach!=="function")throw Error("NATIVE_UNSUBSCRIBE_REQUIRED");
          return detach;
        }},
        nativeAuthorizeShot:item=>nativeVisualApproval(hostPort,"shot",item),
        nativeAuthorizeComposition:item=>nativeVisualApproval(hostPort,"composition",item)
      });
    }
    for(const [items,kind] of [[menu,"MENU"],[buttons,"BUTTON"]]){
      for(const item of items){
        const handler=async()=>{
          if(disposed||dispatcher.isPending(item.routeId))return;
          const result=await dispatcher.invoke(item.routeId);
          // Click is not success. Only verified native receipt can mark ACK.
          if(disposed)return;
          if(result.ok===true){
            item.element.dataset.noxNativeAck="true";
            item.element.dataset.noxNativeReceipt=result.receiptId;
          }else{
            delete item.element.dataset.noxNativeAck;
            delete item.element.dataset.noxNativeReceipt;
          }
        };
        watch(item.element,"click",handler);
      }
    }
    const onKey=async event=>{
      let active=true;
      try{active=homeActive()===true;}catch{return;}
      const route=shortcutRoute(event,{...shortcuts,homeActive:active});
      if(!route)return;
      try{if(hostPort.isAvailable(route)!==true)return;}catch{return;}
      event.preventDefault?.();
      await dispatcher.invoke(route);
    };
    watch(root.ownerDocument,"keydown",onKey);
    mounted.add(root);
    return Object.freeze({
      summary,
      setMode(next){
        if(disposed||!validateMode(next))return false;
        if(!fx.setProfile(next))return false;
        wow?.setMode(next);
        return true;
      },
      status(){
        return Object.freeze({...summary,profile:fx.snapshot().profile,
          wowSourceMounted:!!wow,hostIntegrationVerified:false,
          windowsExeAccepted:false});
      },
      destroy(){
        if(disposed)return;disposed=true;dispatcher.close();
        while(cleanups.length)cleanups.pop()();
        restore();
        try{wow?.destroy();}finally{try{fx?.destroy();}finally{adaptive?.destroy();mounted.delete(root);}}
      }
    });
  }catch(err){
    dispatcher.close();
    while(cleanups.length)cleanups.pop()();
    restore();
    try{wow?.destroy();}finally{try{fx?.destroy();}finally{adaptive?.destroy();}}
    throw err;
  }
}
