/* E01 C4: purely native-approved WOW interactions, never a capability flag alone. */
export function nativeVisualApproval(port,kind,item){
 const range=kind==="shot"?[101,150]:kind==="composition"?[151,200]:null;
 if(!range||!item||!Number.isSafeInteger(item.id)||
    item.id<range[0]||item.id>range[1])return false;
 if(typeof port?.isAvailable!=="function"||
    typeof port?.authorizeVisual!=="function")return false;
 try{
   const routeId="wow."+kind+"."+item.id;
   if(port.isAvailable(routeId)!==true)return false;
   const result=port.authorizeVisual(Object.freeze({routeId,kind,id:item.id,origin:"P01"}));
   return result===true; // promises and UI-made booleans aren't native ACK.
 }catch{return false;}
}
