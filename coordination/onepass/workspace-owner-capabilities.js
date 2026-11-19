(() => {
  'use strict';
  const native=window.NOX_NATIVE_OWNER===true;
  const visualOptions={mode:['BALANCED','MAX','ECO'],motion:['system','reduce','full'],theme:['amber','contrast','cosmic-blue','void-purple','graphite','arctic','ember'],language:['ru','es'],finish:['graphite','obsidian','titanium'],buttonStyle:['riveted','seamless','outline'],layout:['compact','balanced','focus'],musicStyle:['industrial','desert','orbital'],musicVolume:['quiet','normal','full']};
  const defaults={mode:'BALANCED',motion:'system',theme:'amber',language:'ru',voice:false,privacy:true,notifications:false,finish:'graphite',buttonStyle:'riveted',layout:'compact',musicEnabled:false,musicStyle:'industrial',musicVolume:'quiet',musicAdaptive:true};
  let session,values,capabilities=null,storageScope=native?'NATIVE_OWNER_PENDING':'EXISTING_WEB_WORKSPACE',browserVisual=false;
  let nativeSettingsSupport=null;
  function localVisual(){
    const result={...defaults};
    try{const saved=JSON.parse(localStorage.getItem('nox.native.visual.prefs')||'{}');for(const [key,allowed] of Object.entries(visualOptions))if(allowed.includes(saved[key]))result[key]=saved[key];}catch{}
    return result;
  }
  async function request(path, data) {
    let options = {cache:'no-store',credentials:'same-origin'};
    if (data !== undefined) {
      if (!native&&!session) {
        const token = await request('/api/nox/session');
        session = token.token;
      }
      options = {...options, method:'POST', headers:{'Content-Type':'application/json',...(!native?{'X-NOX-Session':session}:{})}, body:JSON.stringify(data)};
    }
    const response = await fetch(path,options);
    const value = await response.json();
    if (!response.ok) {
      if (response.status===403) session = null;
      const error=Error(value.reason || value.error || ('HTTP '+response.status));error.status=response.status;throw error;
    }
    return value;
  }
  function apply(settings) {
    settings={...settings};
    for(const key of Object.keys(visualOptions))settings[key]=visualOptions[key].includes(settings[key])?settings[key]:defaults[key];
    for(const key of ['voice','privacy','notifications','musicEnabled','musicAdaptive'])settings[key]=typeof settings[key]==='boolean'?settings[key]:defaults[key];
    values = {...settings};
    const html=document.documentElement;
    html.dataset.theme=settings.theme;
    html.dataset.metal=settings.finish;
    html.dataset.buttonStyle=settings.buttonStyle;
    html.dataset.layout=settings.layout;
    html.dataset.musicEnabled=String(settings.musicEnabled);
    html.dataset.musicStyle=settings.musicStyle;
    html.dataset.musicVolume=settings.musicVolume;
    html.dataset.musicAdaptive=String(settings.musicAdaptive);
    html.dataset.reducedMotion=settings.motion;
    html.dataset.voice=String(settings.voice);
    html.dataset.privacy=String(settings.privacy);
    try {
      localStorage.setItem('nox.fx',settings.mode);
      localStorage.setItem('nox.motion',settings.motion);
      localStorage.setItem('nox_visual_mode',settings.mode);
      localStorage.setItem('nox_reduced_motion',String(settings.motion==='reduce'||(settings.motion==='system'&&matchMedia('(prefers-reduced-motion:reduce)').matches)));
    } catch {}
    window.dispatchEvent(new CustomEvent('nox-settings',{detail:{...settings}}));
  }
  async function set(delta) {
    if(native&&nativeSettingsSupport===null)throw Error('NATIVE_CAPABILITIES_PENDING_OR_UNVERIFIED');
    if(native&&browserVisual){
      if(!delta||!Object.keys(delta).length||Object.entries(delta).some(([key,value])=>!visualOptions[key]?.includes(value)))throw Error('NATIVE_SETTINGS_NOT_MOUNTED');
      const settings={...localVisual(),...delta};localStorage.setItem('nox.native.visual.prefs',JSON.stringify(settings));apply(settings);return values;
    }
    const response = await request('/api/settings',delta);
    apply(response.settings);
    return values;
  }
  async function load(){
    let response;
    // Native owner settings are selected by the existing authenticated capability route.
    if(native){
      nativeSettingsSupport=null;browserVisual=false;
      const advertised=await request('/api/ui/capabilities');
      if(!advertised||typeof advertised!=='object'||Array.isArray(advertised)||
         advertised.schema!=='NOX_NATIVE_UI_WORKSPACE_V1'||typeof advertised.settings!=='boolean')
        throw Error('NATIVE_UI_CAPABILITIES_UNVERIFIED');
      capabilities=advertised;
      nativeSettingsSupport=advertised.settings;
      if(advertised.settings===false){
        browserVisual=true;storageScope='BROWSER_VISUAL_PREFS';apply(localVisual());return values;
      }
    }
    try{response=await request('/api/settings');}
    catch(error){
      if(!native||error.status!==404)throw error;
      browserVisual=true;storageScope='BROWSER_VISUAL_PREFS';capabilities={schema:'NATIVE_UI_NOT_MOUNTED',settings:false,projects:false,tools:[],installer_apply:false,push_delivery:false};apply(localVisual());return values;
    }
    capabilities=response.capabilities||null;storageScope=response.storage_scope||storageScope;
    if(native&&capabilities?.settings===false){browserVisual=true;storageScope='BROWSER_VISUAL_PREFS';apply(localVisual());return values;}
    if (!response.stored) {
      // Migrate valid visual preferences once. Do not infer browser permissions from storage.
      let mode, motion;
      try {
        mode=localStorage.getItem('nox.fx')||localStorage.getItem('nox_visual_mode');
        motion=localStorage.getItem('nox.motion')||(localStorage.getItem('nox_reduced_motion')==='true'?'reduce':null);
      }catch {}
      const delta={};
      if (['BALANCED','MAX','ECO'].includes(mode)) delta.mode=mode;
      if (['reduce','full'].includes(motion)) delta.motion=motion;
      if (Object.keys(delta).length) return set(delta);
    }
    apply(response.settings);
    return values;
  }
  let newestEvent=null, pending=false;
  async function checkJournal() {
    if (!values?.notifications || document.hidden || pending) return;
    pending=true;
    try{
      const data=await request('/api/notifications');
      const top=data.events[0];
      if(top && newestEvent!==null && top.id>newestEvent) {
        let toast=document.getElementById('workspaceToast');
        if(!toast){
          toast=document.createElement('div');
          toast.id='workspaceToast';toast.className='ws-toast';toast.setAttribute('role','status');
          document.body.append(toast);
        }
        toast.textContent=top.message;
        toast.hidden=false;
        clearTimeout(toast.noxTimer);toast.noxTimer=setTimeout(()=>{toast.hidden=true;},6500);
      }
      newestEvent=top?.id||0;
    }catch{}finally{pending=false;}
  }
  window.addEventListener('nox-settings',e=>{
    if(e.detail.notifications)void checkJournal();else newestEvent=null;
  });
  setInterval(checkJournal,15000);
  let ready;
  window.NoxWorkspace = {set,request,load,get native(){return native;},get capabilities(){return capabilities&&{...capabilities};},get storageScope(){return storageScope;},get ready(){return ready;},get settings(){return values&&{...values};}};
  ready = load();
  ready.catch(error=>{document.documentElement.dataset.settingsError=error.message;});
})();
