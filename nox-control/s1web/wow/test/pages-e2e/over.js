const {chromium}=require('playwright');
(async()=>{const b=await chromium.launch();const ctx=await b.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true});
for(const pg of process.argv[2].split(',')){const p=await ctx.newPage();await p.goto('http://127.0.0.1:18091/web/'+pg+'.html');await p.waitForTimeout(3000);
const r=await p.evaluate(()=>[...document.querySelectorAll(".page, .page *")].filter(e=>e.scrollWidth>e.clientWidth+1&&getComputedStyle(e).overflowX==="visible").slice(0,8).map(e=>e.tagName+"."+e.className+" sw"+e.scrollWidth+" cw"+e.clientWidth));console.log(pg,JSON.stringify(r));await p.close()}
await b.close()})();
