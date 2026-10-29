/* NOX-INTEGRATION-PACK-01: host-verified capability catalogue.
   Pure ES module. No network calls, no privileged operations, no implicit installs. */
export const CATEGORIES=Object.freeze(["chat","models","learning","voice","space"]);
export const RISKS=Object.freeze(["safe","sensitive","dangerous"]);
const ROUTE_RE=/^[a-z][a-z0-9]*(?:[._][a-z0-9]+)*$/;
// Fixed UI admission policy mirrors the existing native owner/risk route floor.
// Reject modified route/risk/owner metadata before rendering a capability.
const CANONICAL_ROUTE_POLICY=Object.freeze([["helion.chat",2,"safe"],["core.chat",2,"safe"],["persona.chat",2,"safe"],["chat.model",2,"safe"],["chat.history",2,"sensitive"],["chat.attach",2,"sensitive"],["chat.rag",2,"safe"],["chat.voice",2,"sensitive"],["chat.stop",2,"safe"],["chat.commands",2,"safe"],["models.catalog",3,"safe"],["models.installed",3,"safe"],["models.pull",3,"sensitive"],["models.gguf.import",3,"sensitive"],["models.queue",3,"safe"],["models.cancel",3,"safe"],["models.retry",3,"sensitive"],["models.digest",3,"safe"],["models.preflight",3,"safe"],["models.licenses",3,"safe"],["rag.import",4,"sensitive"],["rag.search",4,"safe"],["memory.manage",4,"sensitive"],["datasets.review",4,"safe"],["gpu.preflight",4,"safe"],["training.start",4,"dangerous"],["training.pause",4,"safe"],["training.resume",4,"sensitive"],["training.checkpoints",4,"sensitive"],["training.evaluate",4,"safe"],["translate.ru_es",2,"sensitive"],["maestro.spanish",2,"safe"],["voice.settings",2,"safe"],["calls.dial",2,"dangerous"],["calls.history",2,"sensitive"],["media.player",1,"sensitive"],["media.subtitles",1,"safe"],["browser.open",1,"sensitive"],["browser.bookmarks",1,"safe"],["images.generate",4,"sensitive"],["space.news",5,"safe"],["space.weather",5,"safe"],["space.fx",5,"safe"],["space.bitcoin",5,"safe"],["space.brent",5,"safe"],["system.telemetry",5,"safe"],["system.update",1,"dangerous"],["system.backup",1,"dangerous"],["system.pc_control",1,"dangerous"],["mobile.connect",6,"sensitive"]]);
const ALLOWED_STATES=new Set(["AVAILABLE","CONNECTED","VERIFIED"]);
const VERIFIED_ACTION_STATES=new Set(["CONNECTED","VERIFIED"]);
const OPT_RE=/^[A-Za-z0-9_.:/+\-]{1,128}$/;
export function verifyCatalog(catalog){
  if(!catalog||catalog.version!=="NOX-INTEGRATION-PACK-01"||!Array.isArray(catalog.actions))
    throw new Error("INVALID_PACK_SCHEMA");
  if(catalog.actions.length!==50)throw new Error("REQUIRE_EXACTLY_50");
  const ids=new Set(),tasks=new Set();
  const tally=Object.fromEntries(CATEGORIES.map(x=>[x,0]));
  for(const [index,x] of catalog.actions.entries()){
    const approved=CANONICAL_ROUTE_POLICY[index];
    if(x?.routeId!==approved[0] || x.owner!==approved[1] || x.risk!==approved[2] ||
       x.taskId!=="NIP01-"+String(index+1).padStart(2,"0"))
       throw new Error("CANONICAL_OWNER_RISK_MISMATCH");
  }
  for(const x of catalog.actions){
    if(!x||!ROUTE_RE.test(x.routeId)||ids.has(x.routeId))throw new Error("DUPLICATE_OR_INVALID_ROUTE");
    if(!/^NIP01-\d\d$/.test(x.taskId)||tasks.has(x.taskId))throw new Error("DUPLICATE_OR_INVALID_TASK_ID");
    if(!CATEGORIES.includes(x.category)||!RISKS.includes(x.risk)||![1,2,3,4,5,6].includes(x.owner))
      throw new Error("INVALID_ROUTE_METADATA");
    if(x.intent!=="nox.feature.request"||typeof x.title!=="string"||x.title.length<3||x.title.length>90)
      throw new Error("INVALID_ROUTE_ACTION");
    if(!Array.isArray(x.settings)||x.settings.length>4)throw new Error("INVALID_SETTINGS_SCHEMA");
    let keys=new Set();
    for(const f of x.settings){
      if(!f||!ROUTE_RE.test(f.key)||keys.has(f.key)||f.kind!=="select")throw new Error("INVALID_SETTING");
      if((f.source?1:0)+(f.options?1:0)!==1)throw new Error("UNBOUND_SETTING_OPTIONS");
      if(f.options && (!Array.isArray(f.options)||f.options.length<1||f.options.length>24||
        f.options.some(p=>!Array.isArray(p)||p.length!==2||!OPT_RE.test(p[0])||
          typeof p[1]!=="string"||p[1].length>80)))throw new Error("INVALID_SETTINGS_OPTIONS");
      keys.add(f.key);
    }
    ids.add(x.routeId);tasks.add(x.taskId);tally[x.category]++;
  }
  if(CATEGORIES.some(k=>tally[k]!==10))throw new Error("FIVE_GROUPS_OF_TEN_REQUIRED");
  return Object.freeze({...tally});
}
export function normalizeCapabilities(catalog,raw){
  verifyCatalog(catalog);
  const source=raw&&typeof raw==="object"&&!Array.isArray(raw)?raw:{};
  const output=Object.create(null);
  for(const x of catalog.actions){
    const item=Object.prototype.hasOwnProperty.call(source,x.routeId)?source[x.routeId]:null;
    const state=item&&typeof item.state==="string"&&ALLOWED_STATES.has(item.state)?item.state:"HOLD";
    const enabled=!!item && item.enabled===true && VERIFIED_ACTION_STATES.has(state) &&
      (x.risk!=="dangerous"||item.nativeConsent===true);
    output[x.routeId]=Object.freeze({state,enabled,sourceId:
      typeof item?.sourceId==="string"?item.sourceId.slice(0,128):null});
  }
  return Object.freeze(output);
}
export function filteredActions(catalog,needle="",category="all"){
  verifyCatalog(catalog);
  const term=String(needle||"").trim().toLocaleLowerCase("ru").slice(0,96);
  return catalog.actions.filter(x=>(category==="all"||x.category===category)&&
    (!term||(x.title+" "+x.routeId+" "+x.category).toLocaleLowerCase("ru").includes(term)));
}
export function optionsForField(field,hostChoices){
  if(Array.isArray(field.options))return field.options;
  const raw=hostChoices && typeof hostChoices==="object"?hostChoices[field.source]:null;
  if(!Array.isArray(raw))return [];
  const items=[],ids=new Set();
  for(const o of raw.slice(0,80)){
    if(!o||!OPT_RE.test(o.id)||typeof o.label!=="string"||!o.installed)continue;
    if(ids.has(o.id))continue;
    items.push([o.id,o.label.slice(0,80)]);ids.add(o.id);
  }
  return items;
}
export function makeRequest(action,form,choices){
  if(!action||!ROUTE_RE.test(action.routeId))throw new Error("INVALID_REQUEST_ROUTE");
  const inputs=form && typeof form==="object"?form:{};
  const settings=Object.create(null);
  for(const field of action.settings||[]){
    const opts=optionsForField(field,choices),picked=inputs[field.key];
    if(!Array.isArray(opts)||opts.length===0)throw new Error("SETTINGS_SOURCE_NOT_READY");
    if(typeof picked!=="string"||!opts.some(x=>x[0]===picked))throw new Error("UNSUPPORTED_SETTING");
    settings[field.key]=picked;
  }
  return {routeId:action.routeId,taskId:action.taskId,requestedOwner:action.owner,
    settings:Object.assign({},settings),intent:"nox.feature.request"};
}
