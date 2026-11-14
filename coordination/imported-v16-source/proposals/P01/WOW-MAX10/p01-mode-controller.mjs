/* E01 C5: transactional user-selected cinema mode; no telemetry/progress writes. */
const MODES=new Set(["ECO","BALANCED","MAX","REDUCED"]);
export function createP01ModeController(fx,wow,initial="BALANCED"){
 if(typeof fx?.setProfile!=="function"||
    (wow&&typeof wow.setMode!=="function")||!MODES.has(initial))
   throw Error("P01_MODE_TARGET_REQUIRED");
 let current=initial,closed=false;
 return Object.freeze({
   set(next){
     if(closed||!MODES.has(next))return false;
     if(next===current)return true;
     const before=current;
     try{
       if(fx.setProfile(next)!==true)return false;
       wow?.setMode(next);
       current=next;return true;
     }catch{
       try{fx.setProfile(before);wow?.setMode(before);}catch{}
       return false;
     }
   },
   get(){return Object.freeze({mode:current,closed,telemetry:"UNMODIFIED"});},
   close(){closed=true;}
 });
}