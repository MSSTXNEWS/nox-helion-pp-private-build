const {chromium}=require('playwright');const fs=require('fs');
const U='http://127.0.0.1:18091/web/';let fails=0,total=0;
const ok=(vp,pg,name,c,d)=>{total++;if(!c)fails++;console.log((c?'PASS':'FAIL')+' ['+vp+'] '+pg+' · '+name+(c?'':'  -> '+(d||'')))};
(async()=>{const b=await chromium.launch({channel:'chromium',args:['--use-gl=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist']});
for(const [vp,w,h] of [['d',1440,900],['m',390,844]]){
 const T=async(pg,name,fn)=>{try{const r=await fn();ok(vp,pg,name,r!==false,'false')}catch(e){ok(vp,pg,name,false,String(e.message).split('\n')[0].slice(0,200))}};
 const mkc=(perm)=>b.newContext({viewport:{width:w,height:h},isMobile:vp=='m',hasTouch:vp=='m',...(perm?{permissions:['notifications']}:{}),acceptDownloads:true});
 // --- Проекты (4 колонки, владелец, событие, Dexie)
 let ctx=await mkc(true);let p=await ctx.newPage();p.errs=[];p.on('pageerror',e=>p.errs.push(e.message));p.on('dialog',d=>d.accept());
 await p.goto(U+'projects.html');await p.evaluate(()=>{localStorage.removeItem('nox.tasks.v1');localStorage.removeItem('nox.notified')});await p.reload();await p.waitForTimeout(2500);
 await T('projects','4 колонки Очередь/В работе/Проверка/Готово',async()=>JSON.stringify(await p.$$eval('.kcol h2',a=>a.map(x=>x.firstChild.textContent.trim())))==='["Очередь","В работе","Проверка","Готово"]');
 await T('projects','карточка с владельцем и сроком',async()=>{await p.fill('#aTitle','Релиз');await p.fill('#aOwner','Иван');await p.fill('#aDue','2026-12-05');await p.click('#addForm button[type=submit]');await p.waitForTimeout(300);const t=await p.textContent('.klist[data-col=queue] .task');return t.includes('Иван')&&t.includes('2026-12-05')});
 await T('projects','стрелки: Очередь→В работе→Проверка',async()=>{await p.click('.task [data-a=next]');await p.click('.klist[data-col=doing] [data-a=next]');return (await p.$$('.klist[data-col=review] .task')).length===1});
 if(vp=='d')await T('projects','drag Проверка→Готово',async()=>{await p.locator('.klist[data-col=review] .task').dragTo(p.locator('.klist[data-col=done]'),{force:true});await p.waitForTimeout(400);return (await p.$$('.klist[data-col=done] .task')).length===1});
 await T('projects','календарь: событие с временем',async()=>{await p.click('#vCal');await p.waitForSelector('.fc-daygrid');await p.click('.fc-daygrid-day[data-date="2026-11-18"]');await p.waitForSelector('#dlg[open]');const k=await p.inputValue('#dKind');await p.fill('#dTitle','Созвон');await p.fill('#dOwner','Анна');await p.fill('#dTime','14:30');await p.click('#dSave');await p.waitForTimeout(500);return k==='event'&&(await p.$$('.fc-event.ev')).length===1&&(await p.textContent('.fc-event.ev')).includes('Созвон')});
 await T('projects','календарь: срок карточки виден',async()=>{await p.click('.fc-next-button');await p.waitForTimeout(200);return (await p.$$('.fc-event.dl')).length>=1});
 await T('projects','событие не попало на доску',async()=>!(await p.textContent('#vBoardBox')).includes('Созвон'));
 await T('projects','Dexie: зеркало в IndexedDB',async()=>{await p.waitForTimeout(600);const n=await p.evaluate(()=>new Promise(r=>{const q=indexedDB.open('nox-tasks');q.onsuccess=()=>{try{const g=q.result.transaction('tasks').objectStore('tasks').count();g.onsuccess=()=>r(g.result)}catch(e){r(-1)}};q.onerror=()=>r(-2)}));return n===2});
 await T('projects','Dexie: восстановление при пустом localStorage',async()=>{await p.evaluate(()=>localStorage.removeItem('nox.tasks.v1'));await p.reload();await p.waitForTimeout(2500);return (await p.$$('.task')).length>=1&&JSON.parse(await p.evaluate(()=>localStorage.getItem('nox.tasks.v1'))).tasks.length===2});
 await T('projects','уведомления: разрешено → тег ВКЛ, клик выключает/включает',async()=>{const a=await p.textContent('#ntag');await p.click('#ntag');const b2=await p.textContent('#ntag');await p.click('#ntag');return /ВКЛ/.test(a)&&/ВЫКЛ/.test(b2)&&/НАПОМИНАНИЯ: ВКЛ/.test(await p.textContent('#ntag'))});
 await p.evaluate(()=>window.NoxNotify.request());await p.waitForTimeout(1500);
 await T('projects','sw.js зарегистрирован',async()=>{return await p.evaluate(async()=>{const r=await navigator.serviceWorker.getRegistration();return !!r&&/sw\.js/.test((r.active||r.installing||r.waiting||{scriptURL:''}).scriptURL)})});
 await p.evaluate(()=>window.NoxNotify.show('NOX','тест','nox-test','projects.html'));await p.waitForTimeout(500);
 await T('projects','уведомление показано через SW',async()=>{const n=await p.evaluate(async()=>{const r=await navigator.serviceWorker.getRegistration();return (await r.getNotifications()).map(x=>x.title+'|'+x.body)});return n.some(s=>s.startsWith('NOX|'))});
 await T('projects','напоминание по сроку (событие в прошлом на сегодня)',async()=>{await p.evaluate(()=>{const d=new Date(),pad=n=>String(n).padStart(2,'0'),tm=new Date(d.getTime()-120000);const t=JSON.parse(localStorage.getItem('nox.tasks.v1'));t.tasks.push({id:'rm1',title:'Напомни-событие',kind:'event',col:'queue',due:d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate()),time:pad(tm.getHours())+':'+pad(tm.getMinutes()),owner:'Тест',project:'',note:'',created:1});localStorage.setItem('nox.tasks.v1',JSON.stringify(t))});const n=await p.evaluate(()=>window.NoxNotify.checkReminders());const list=await p.evaluate(async()=>{const r=await navigator.serviceWorker.getRegistration();return (await r.getNotifications()).map(x=>x.title)});return n>=1&&list.some(s=>/Напомни-событие/.test(s))});
 await T('projects','напоминание не дублируется',async()=>(await p.evaluate(()=>window.NoxNotify.checkReminders()))===0);
 await T('projects','ошибки JS',async()=>{if(p.errs.length)throw new Error(p.errs.join('|'));return true});
 await ctx.close();
 // --- уведомления: отказ
 ctx=await mkc(false);p=await ctx.newPage();p.on('dialog',d=>d.accept());await p.goto(U+'projects.html');await p.waitForTimeout(2000);
 await T('projects','отказ в разрешении: честная пометка',async()=>{await p.click('#ntag');await p.waitForTimeout(1200);const t=await p.textContent('#ntag');const st=await p.evaluate(()=>Notification.permission);return st==='granted'||/ЗАПРЕЩЕНЫ|ВКЛЮЧИТЬ/.test(t)});
 await ctx.close();
 // --- Настройки: уведомления
 ctx=await mkc(false);p=await ctx.newPage();p.on('dialog',d=>d.accept());await p.goto(U+'settings.html');await p.waitForTimeout(2500);
 await T('settings','уведомления: до запроса — «не запрошено», кнопки теста выключены',async()=>/НЕ ЗАПРОШЕНО/.test(await p.textContent('#nState'))&&await p.isDisabled('#nTest'));
 await ctx.grantPermissions(['notifications']);
 await T('settings','уведомления: разрешить',async()=>{await p.click('#nAsk');await p.waitForTimeout(1000);return /РАЗРЕШЕНО/.test(await p.textContent('#nState'))});
 await T('settings','уведомления: тест',async()=>{await p.click('#nTest');await p.waitForTimeout(800);return await p.evaluate(async()=>{const r=await navigator.serviceWorker.getRegistration();return (await r.getNotifications()).length>=1})});
 await T('settings','уведомления: переключатель напоминаний',async()=>{await p.click('#nToggle');const a=await p.textContent('#nToggle');await p.click('#nToggle');return /выкл/.test(a)});
 await ctx.close();
 // --- Резонанс: «NOX закончил ответ», вкладка скрыта
 ctx=await mkc(true);p=await ctx.newPage();await p.addInitScript(()=>{Object.defineProperty(document,'hidden',{get:()=>true});});await p.goto(U+'chat.html');await p.waitForTimeout(3000);
 await p.evaluate(()=>window.NoxNotify.request());
 await T('chat','«NOX закончил ответ» при скрытой вкладке (реальный ответ через шлюз)',async()=>{await p.evaluate(()=>{const c=JSON.parse(localStorage.getItem('nox.wow.cfg')||'{}');c.proto='glm';localStorage.setItem('nox.wow.cfg',JSON.stringify(c))});await p.reload();await p.waitForTimeout(2500);await p.fill('#input','привет');await p.press('#input','Enter');await p.waitForTimeout(9000);return await p.evaluate(async()=>{const r=await navigator.serviceWorker.getRegistration();return !!r&&(await r.getNotifications()).some(x=>x.title==='NOX закончил ответ')})});
 await ctx.close();
 // --- Память: Split, Fuse, вложения
 ctx=await mkc(false);p=await ctx.newPage();p.errs=[];p.on('pageerror',e=>p.errs.push(e.message));p.on('dialog',d=>d.accept());await p.goto(U+'memory.html');await p.waitForTimeout(2500);
 if(vp=='d')await T('memory','Split.js: граница перетаскивается',async()=>{const g=p.locator('.splitwrap>.gutter');const w0=(await p.locator('#paneL').boundingBox()).width;const bb=await g.boundingBox();await p.mouse.move(bb.x+3,bb.y+20);await p.mouse.down();await p.mouse.move(bb.x-150,bb.y+20,{steps:6});await p.mouse.up();const w1=(await p.locator('#paneL').boundingBox()).width;return Math.abs(w1-w0)>80});
 else await T('memory','Split.js выключен на телефоне (панели друг под другом)',async()=>(await p.$$('.splitwrap>.gutter')).length===0);
 await T('memory','Fuse: опечатка находит запись',async()=>{await p.fill('#q','Мадриде');await p.click('#qForm button[type=submit]');await p.waitForSelector('.hit');await p.fill('#q','Мдриде');await p.click('#qForm button[type=submit]');await p.waitForTimeout(900);const t=await p.textContent('#results');return /НЕЧЁТКО/.test(await p.textContent('#rInfo'))||/нечёткое/.test(t)});
 await T('memory','Fuse загружен',async()=>await p.evaluate(()=>typeof Fuse==='function'));
 await T('memory','вложения: PNG → галерея + PhotoSwipe',async()=>{await p.setInputFiles('#vFile','/tmp/st/fx1.png');await p.waitForSelector('#gallery a',{timeout:5000});await p.waitForTimeout(800);await p.click('#gallery a');await p.waitForSelector('.pswp--open',{timeout:5000});await p.waitForTimeout(1500);await p.keyboard.press('Escape');await p.waitForSelector('.pswp--open',{state:'detached',timeout:5000});return true});
 await T('memory','вложения: PDF → страницы PDF.js',async()=>{await p.setInputFiles('#vFile','/tmp/st/fx1.pdf');await p.waitForSelector('#pdfBox:not([hidden])',{timeout:8000});await p.waitForFunction(()=>/1 \/ 2/.test(document.getElementById('pInfo').textContent),null,{timeout:8000});await p.evaluate(()=>document.getElementById('pNext').scrollIntoView({block:'center'}));await p.click('#pNext');await p.waitForFunction(()=>/2 \/ 2/.test(document.getElementById('pInfo').textContent),null,{timeout:8000});const px=await p.evaluate(()=>{const c=document.getElementById('pdfCv'),d=c.getContext('2d').getImageData(0,0,c.width,c.height).data;let n=0;for(let i=0;i<d.length;i+=4)if(d[i]<100)n++;return n});await p.evaluate(()=>document.getElementById('pPrev').scrollIntoView({block:'center'}));await p.click('#pPrev');await p.waitForFunction(()=>/1 \/ 2/.test(document.getElementById('pInfo').textContent));await p.evaluate(()=>document.getElementById('pClose').scrollIntoView({block:'center'}));await p.click('#pClose');return px>50});
 await T('memory','вложения: неверный тип → честная ошибка',async()=>{fs.writeFileSync('/tmp/st/x.txt','a');await p.setInputFiles('#vFile','/tmp/st/x.txt');await p.waitForTimeout(500);return /не поддержан/.test(await p.textContent('#toasts'))});
 await T('memory','ошибки JS',async()=>{if(p.errs.length)throw new Error(p.errs.join('|'));return true});
 await ctx.close();
}
console.log('ИТОГО2',total-fails+'/'+total);await b.close();process.exit(fails?1:0)})();
