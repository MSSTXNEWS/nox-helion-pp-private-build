const {chromium}=require('playwright');
const pages=(process.argv[2]||'index,projects,memory,training,models,system,settings,chat').split(',');
const tag=process.argv[3]||'pages';
(async()=>{const b=await chromium.launch({args:['--use-gl=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist']});
for(const [vn,vw,vh] of [['d',1440,900],['m',390,844]]){
 const ctx=await b.newContext({viewport:{width:vw,height:vh},isMobile:vn=='m',hasTouch:vn=='m',deviceScaleFactor:1});
 for(const pg of pages){const p=await ctx.newPage();const logs=[];
  p.on('console',m=>{if(m.type()==='error')logs.push('console.error: '+m.text().slice(0,200))});
  p.on('pageerror',e=>logs.push('PAGEERR '+e.message.slice(0,200)));
  p.on('response',r=>{if(r.status()>=400&&!/\/(api|stt|tts)\//.test(r.url()))logs.push('HTTP '+r.status()+' '+r.url().slice(0,120))});
  p.on('requestfailed',r=>logs.push('REQFAIL '+r.url().slice(0,100)));
  await p.goto('http://127.0.0.1:18091/web/'+pg+'.html',{waitUntil:'load'}).catch(e=>logs.push('GOTO '+e.message));
  await p.waitForTimeout(3500);
  const m=await p.evaluate(()=>{const de=document.documentElement;const pgEl=document.querySelector('.page');return {sw:de.scrollWidth,cw:de.clientWidth,bsw:document.body.scrollWidth,pageSW:pgEl?pgEl.scrollWidth:null,pageCW:pgEl?pgEl.clientWidth:null,title:document.title,canvas:!!document.getElementById('space')}});
  await p.screenshot({path:`/tmp/shots/${tag}-${pg}-${vn}.png`});
  console.log(vn,pg,JSON.stringify(m),(m.sw>m.cw||(m.pageSW>m.pageCW))?'  !!HSCROLL':'','\n   '+[...new Set(logs)].slice(0,8).join('\n   '));
  await p.close();}
 await ctx.close();}
await b.close()})();
