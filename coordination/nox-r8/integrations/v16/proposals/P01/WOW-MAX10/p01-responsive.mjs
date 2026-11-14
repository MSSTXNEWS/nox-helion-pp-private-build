/* E01 C3: opt-in viewport metadata on existing D02, zero new nodes. */
export function viewportClass(w,h){
  if(!Number.isFinite(w)||!Number.isFinite(h)||w<=0||h<=0)return "unknown";
  if(h<=500)return "short";if(w<360)return "compact";
  if(w<720)return "phone";if(w<1120)return "tablet";
  if(w<1920)return "desktop";return "wide";
}
export function installP01Adaptive(root){
  const doc=root?.ownerDocument,win=doc?.defaultView;
  if(!root||root.nodeType!==1||!win||
    typeof win.addEventListener!=="function"||
    typeof win.removeEventListener!=="function")throw Error("RESPONSIVE_HOST_REQUIRED");
  const fields=["noxP01Layout","noxP01Motion","noxP01Dpi","noxP01Orientation"];
  const saved=fields.map(key=>({key,had:Object.hasOwn(root.dataset,key),value:root.dataset[key]}));
  const mq=win.matchMedia?.("(prefers-reduced-motion: reduce)")||null;
  let destroyed=false;
  function update(){
    if(destroyed)return;
    const width=Number(win.innerWidth),height=Number(win.innerHeight);
    root.dataset.noxP01Layout=viewportClass(width,height);
    root.dataset.noxP01Orientation=width>0&&height>0?(width>=height?"landscape":"portrait"):"unknown";
    root.dataset.noxP01Motion=mq?.matches?"reduced":"normal";
    const dpr=Number(win.devicePixelRatio);
    root.dataset.noxP01Dpi=Number.isFinite(dpr)&&dpr>=.5&&dpr<=6?String(Math.round(dpr*100)):"unknown";
  }
  win.addEventListener("resize",update,{passive:true});
  mq?.addEventListener?.("change",update);update();
  return Object.freeze({update,destroy(){
    if(destroyed)return;destroyed=true;
    win.removeEventListener("resize",update);
    mq?.removeEventListener?.("change",update);
    for(const s of saved){if(s.had)root.dataset[s.key]=s.value;else delete root.dataset[s.key];}
  }});
}