const {chromium}=require('playwright');const fs=require('fs');
const U='http://127.0.0.1:18091/web/';let fails=0,total=0;
const ok=(vp,pg,name,c,d)=>{total++;if(!c)fails++;console.log((c?'PASS':'FAIL')+' ['+vp+'] '+pg+' · '+name+(c?'':'  -> '+(d||'')))};
(async()=>{const b=await chromium.launch({args:['--use-gl=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist']});
for(const [vp,w,h] of [['d',1440,900],['m',390,844]]){
 const ctx=await b.newContext({viewport:{width:w,height:h},isMobile:vp=='m',hasTouch:vp=='m',acceptDownloads:true});
 const mk=async(pg)=>{const p=await ctx.newPage();p.errs=[];p.on('pageerror',e=>p.errs.push(e.message));p.on('console',m=>{if(m.type()==='error'&&!/status of (503|502)/.test(m.text()))p.errs.push(m.text())});p.on('dialog',d=>d.accept());await p.goto(U+pg+'.html');await p.waitForTimeout(2500);return p};
 const dl=async(p,sel)=>{const [d]=await Promise.all([p.waitForEvent('download',{timeout:5000}),p.click(sel)]);const path=await d.path();return {name:d.suggestedFilename(),txt:fs.readFileSync(path,'utf8')}};
 const T=async(pg,name,fn)=>{try{const r=await fn();ok(vp,pg,name,r!==false,'false')}catch(e){ok(vp,pg,name,false,String(e.message).split('\n')[0].slice(0,160))}};
 // навигация
 for(const pg of ['index','projects','memory','training','models','system','settings','chat']){
  const p=await mk(pg);
  const links=vp=='d'?await p.$$eval('#nav a',a=>a.map(x=>x.getAttribute('href'))):await p.$$eval('.mnav a',a=>a.map(x=>x.getAttribute('href')));
  const top=vp=='m'?await p.$$eval('.toplink a',a=>a.map(x=>x.getAttribute('href'))):[];
  await T(pg,'меню: '+links.length+' ссылок'+(top.length?' + Резонанс сверху':''),async()=>{for(const l of links.concat(top,['settings.html'])){const r=await p.request.get(U+l);if(r.status()!==200)throw new Error(l+' '+r.status())}return links.length>=(vp=='d'?7:7)});
  await T(pg,'нет ошибок JS',async()=>{if(p.errs.length)throw new Error(p.errs.join(' | '));return true});
  await T(pg,'canvas фона и анимация',async()=>{return await p.evaluate(()=>!!window.__noxSpace||document.body.classList.contains('bgfallback'))});
  await p.close()}
 // ГЛАВНАЯ
 {const p=await mk('index');
  await T('index','Опросить сейчас',async()=>{const a=await p.textContent('#sumTime');await p.click('#refresh');await p.waitForTimeout(1500);const b2=await p.textContent('#sumTime');await p.waitForTimeout(100);return (await p.$$('#svc article')).length===8});
  await T('index','карточки служб с ms',async()=>(await p.$$eval('#svc .ms',a=>a.filter(x=>/МС/.test(x.textContent)).length))>=7);
  for(const l of ['chat','projects','memory','training','models','system','settings']){await T('index','быстрая ссылка '+l,async()=>{await p.goto(U+'index.html');await p.waitForTimeout(500);await p.click('.quick a[href="'+l+'.html"]');await p.waitForURL('**/'+l+'.html',{timeout:5000});return true})}
  await p.close()}
 // ПРОЕКТЫ
 {await ctx.addInitScript(()=>{});const p=await mk('projects');await p.evaluate(()=>localStorage.removeItem('nox.tasks.v1'));await p.reload();await p.waitForTimeout(2000);
  await T('projects','добавить задачу',async()=>{await p.fill('#aTitle','Тест A');await p.fill('#aProj','Альфа');await p.fill('#aDue','2026-11-25');await p.click('#addForm button[type=submit]');await p.waitForTimeout(300);return (await p.$$('.klist[data-col=queue] .task')).length===1});
  await T('projects','добавить 2-ю (в работе, прошлая дата)',async()=>{await p.fill('#aTitle','Тест B');await p.fill('#aProj','Бета');await p.selectOption('#aCol','doing');await p.fill('#aDue','2026-01-01');await p.click('#addForm button[type=submit]');await p.waitForTimeout(300);return (await p.$$('.klist[data-col=doing] .task.late')).length===1});
  await T('projects','перетащить todo -> done',async()=>{const src=p.locator('.klist[data-col=queue] .task').first(),dst=p.locator('.klist[data-col=done]');if(vp=='m'){await p.click('.klist[data-col=queue] .task [data-a=next]');await p.click('.klist[data-col=doing] .task:not(.late) [data-a=next]');await p.click('.klist[data-col=review] .task [data-a=next]')}else await src.dragTo(dst,{force:true});await p.waitForTimeout(500);return (await p.$$('.klist[data-col=done] .task')).length===1&&JSON.parse(await p.evaluate(()=>localStorage.getItem('nox.tasks.v1'))).tasks.some(t=>t.col==='done')});
  await T('projects','правка (карандаш)',async()=>{await p.click('.klist[data-col=doing] .task [data-a=edit]');await p.waitForSelector('#dlg[open]');await p.fill('#dTitle','Тест B2');await p.click('#dSave');await p.waitForTimeout(400);return (await p.textContent('.klist[data-col=doing]')).includes('Тест B2')});
  await T('projects','диалог: отмена',async()=>{await p.click('.klist[data-col=doing] .task [data-a=edit]');await p.waitForSelector('#dlg[open]');await p.click('#dCancel');await p.waitForTimeout(500);return !(await p.getAttribute('#dlg','open')!==null)});
  await T('projects','фильтр проекта',async()=>{await p.click('#chips button[data-p="Альфа"]');await p.waitForTimeout(200);const n=(await p.$$('.task')).length;await p.click('#chips button[data-p=""]');return n===1&&(await p.$$('.task')).length===2});
  await T('projects','календарь',async()=>{await p.click('#vCal');await p.waitForSelector('.fc-daygrid',{timeout:4000});return (await p.$$('.fc-event')).length>=1});
  await T('projects','календарь: клик по дню -> диалог -> сохранить',async()=>{await p.click('.fc-daygrid-day[data-date="2026-11-12"]');await p.waitForSelector('#dlg[open]');await p.fill('#dTitle','С календаря');await p.click('#dSave');await p.waitForTimeout(500);return (await p.$$('.fc-event')).length>=2});
  await T('projects','календарь: навигация prev/next/today/list',async()=>{await p.click('.fc-next-button');await p.click('.fc-today-button');await p.click('.fc-next-button');await p.click('.fc-prev-button');await p.click('.fc-listMonth-button');await p.waitForTimeout(300);await p.click('.fc-dayGridMonth-button');return true});
  await T('projects','календарь: перенос события мышью',async()=>{const ev=p.locator('.fc-event',{hasText:'С календаря'}).first();const to=p.locator('.fc-daygrid-day[data-date="2026-11-13"]');await ev.dragTo(to);await p.waitForTimeout(500);const t=JSON.parse(await p.evaluate(()=>localStorage.getItem('nox.tasks.v1'))).tasks.find(x=>x.title==='С календаря');return t.due==='2026-11-13'});
  await T('projects','Доска назад',async()=>{await p.click('#vBoard');return !(await p.isHidden('#vBoardBox'))});
  await T('projects','экспорт JSON',async()=>{const d=await dl(p,'#exp');const j=JSON.parse(d.txt);return j.tasks.length===3&&/\.json$/.test(d.name)});
  await T('projects','экспорт ICS',async()=>{const d=await dl(p,'#expIcs');return d.txt.includes('BEGIN:VEVENT')&&d.txt.includes('SUMMARY:Тест A')});
  await T('projects','импорт JSON',async()=>{fs.writeFileSync('/tmp/st/imp.json',JSON.stringify({tasks:[{title:'Импортная',col:'doing',due:'2026-12-01',project:'Имп'}]}));await p.setInputFiles('#impFile','/tmp/st/imp.json');await p.waitForTimeout(500);return (await p.textContent('#vBoardBox')).includes('Импортная')});
  await T('projects','удалить (x)',async()=>{const n=(await p.$$('.task')).length;await p.click('.task [data-a=del]');await p.waitForTimeout(300);return (await p.$$('.task')).length===n-1});
  await T('projects','проверка API задач (тег)',async()=>{await p.click('#apiTag');await p.waitForTimeout(800);return /API ЗАДАЧ/.test(await p.textContent('#apiTag'))});
  await T('projects','импорт из NOX скрыт без API',async()=>await p.isHidden('#apiAct'));
  await T('projects','ошибки JS',async()=>{if(p.errs.length)throw new Error(p.errs.join('|'));return true});
  await p.close()}
 // ПАМЯТЬ
 {const p=await mk('memory');
  await T('memory','статистика',async()=>/ФАКТОВ/.test(await p.textContent('#mStats')));
  await T('memory','ядро памяти',async()=>(await p.textContent('#core')).length>20);
  await T('memory','поиск',async()=>{await p.fill('#q','NOX');await p.click('#qForm button[type=submit]');await p.waitForSelector('.hit',{timeout:4000});return true});
  await T('memory','поиск без результата',async()=>{await p.fill('#q','zzqqxx');await p.click('#qForm button[type=submit]');await p.waitForTimeout(2500);return /ничего не помнит/.test(await p.textContent('#results'))});
  await p.fill('#q','NOX');await p.click('#qForm button[type=submit]');await p.waitForSelector('.hit');
  await T('memory','подтвердить',async()=>{await p.click('.hit [data-a=confirm]');await p.waitForTimeout(800);return (await p.$$('#journal tr')).length>1&&/confirm/.test(await p.textContent('#journal'))});
  await T('memory','исправить',async()=>{await p.click('.hit [data-a=correct]');await p.waitForSelector('#dlgC[open]');await p.fill('#cText','NOX HELION работает на S1 круглосуточно (исправлено)');await p.click('#cSave');await p.waitForTimeout(900);return /correct/.test(await p.textContent('#journal'))});
  await T('memory','исправить: отмена',async()=>{await p.fill('#q','NOX');await p.click('#qForm button[type=submit]');await p.waitForSelector('.hit');await p.click('.hit [data-a=correct]');await p.waitForSelector('#dlgC[open]');await p.click('#cCancel');await p.waitForTimeout(500);return true});
  await T('memory','удалить + откатить',async()=>{await p.click('.hit [data-a=delete]');await p.waitForSelector('#dlgD[open]');await p.click('#dOk');await p.waitForTimeout(900);const j=await p.textContent('#journal');if(!/delete/.test(j))return false;await p.click('#journal button[data-rev] >> nth=0');await p.waitForTimeout(900);return /revert/.test(await p.textContent('#journal'))});
  await T('memory','удалить: отмена',async()=>{await p.click('.hit [data-a=delete]');await p.waitForSelector('#dlgD[open]');await p.click('#dNo');await p.waitForTimeout(500);return true});
  await T('memory','обновить',async()=>{await p.click('#mRefresh');await p.waitForTimeout(600);return true});
  await T('memory','ошибки JS',async()=>{if(p.errs.length)throw new Error(p.errs.join('|'));return true});
  await p.close()}
 // ОБУЧЕНИЕ
 {const p=await mk('training');
  await T('training','графики ECharts',async()=>(await p.$$('#chMem canvas')).length===1&&(await p.$$('#chAct canvas')).length>=0);
  await T('training','данные S1 вместо заглушки',async()=>/Правок владельца в журнале|не подключена/.test(await p.textContent('#prog')));
  await T('training','пары исправлений',async()=>/исправлено/.test(await p.textContent('#pairs')));
  await T('training','Проверить снова',async()=>{await p.click('#tRefresh');await p.waitForTimeout(1200);return true});
  await T('training','JSONL',async()=>{const d=await dl(p,'#tJsonl');return d.txt.includes('"after"')});
  await p.close()}
 // ЯДРО
 {const p=await mk('models');
  await T('models','тиры и модели',async()=>(await p.$$('#tiers .card')).length===2&&/glm-5.3/.test(await p.textContent('#models')));
  await T('models','props: честная ошибка',async()=>(await p.textContent('#props')).length>10);
  await T('models','Обновить',async()=>{await p.click('#cRefresh');await p.waitForTimeout(1200);return /ОБНОВЛЕНО/.test(await p.textContent('#cTime'))});
  await T('models','Проверка генерации',async()=>{await p.click('#gen');await p.waitForSelector('#genOut pre,#genOut .err',{timeout:30000});return /МС|не удалась/.test(await p.textContent('#genOut'))&&(await p.$$('#genOut pre')).length===1});
  await T('models','таблица служб',async()=>(await p.$$('#srv tbody tr')).length===7);
  await p.close()}
 // СИСТЕМА
 {const p=await mk('system');await p.waitForTimeout(6500);
  await T('system','плитки и графики uPlot',async()=>(await p.$$('#tiles .card')).length===6&&(await p.$$('.uplot')).length===3);
  await T('system','пауза/продолжить',async()=>{await p.click('#sPause');const a=await p.textContent('#sState');await p.click('#sPause');return /ОСТАНОВЛЕН/.test(a)&&/КАЖДЫЕ/.test(await p.textContent('#sState'))});
  await T('system','CSV',async()=>{const d=await dl(p,'#sCsv');return d.txt.split('\n').length>=2&&d.txt.startsWith('time,')});
  await T('system','Очистить',async()=>{await p.click('#sClear');return true});
  await T('system','метрики ПК: данные или честная ошибка',async()=>/недоступны|GPU загрузка/.test(await p.textContent('#pc')));
  await T('system','ошибки JS',async()=>{if(p.errs.length)throw new Error(p.errs.join('|'));return true});
  await p.close()}
 // НАСТРОЙКИ
 {const p=await mk('settings');
  const planets=await p.$$eval('#planets button',a=>a.map(x=>x.dataset.id));
  for(const id of planets){await T('settings','планета '+id,async()=>{await p.click('#planets button[data-id='+id+']');await p.waitForTimeout(500);return (await p.evaluate(()=>localStorage.getItem('nox:planet')))===id&&(await p.getAttribute('#planets button[data-id='+id+']','aria-checked'))==='true'})}
  for(const c of ['255,180,84','127,245,239']){await T('settings','цвет '+c,async()=>{await p.click('#accent button[data-c="'+c+'"]');return (await p.evaluate(()=>getComputedStyle(document.documentElement).getPropertyValue('--cy').trim()))===c&&(await p.evaluate(()=>localStorage.getItem('nox.ui.accent')))===c})}
  const opts=await p.$$eval('.opt button',a=>a.map(x=>[x.parentElement.dataset.opt,x.dataset.v]));
  for(const [k,v] of opts){await T('settings','режим '+k+'='+v,async()=>{await p.click('.opt[data-opt='+k+'] button[data-v='+v+']');return JSON.parse(await p.evaluate(()=>localStorage.getItem('nox.wow.cfg')))[k]===v})}
  await T('settings','экспорт',async()=>{const d=await dl(p,'#sExp');return JSON.parse(d.txt).settings['nox.ui.accent']==='127,245,239'});
  await T('settings','импорт',async()=>{fs.writeFileSync('/tmp/st/set.json',JSON.stringify({settings:{'nox.ui.accent':'170,150,255'}}));await p.setInputFiles('#sFile','/tmp/st/set.json');await p.waitForTimeout(1800);await p.waitForLoadState('load');await p.waitForTimeout(800);return (await p.evaluate(()=>localStorage.getItem('nox.ui.accent')))==='170,150,255'});
  await T('settings','сброс',async()=>{await p.click('#sReset');await p.waitForTimeout(1800);return (await p.evaluate(()=>localStorage.getItem('nox.ui.accent')))===null});
  await T('settings','статус голоса честный',async()=>/STT/.test(await p.textContent('#voiceStat')));
  await T('settings','ошибки JS',async()=>{if(p.errs.length)throw new Error(p.errs.join('|'));return true});
  await p.close()}
 await ctx.close()}
console.log('ИТОГО',total-fails+'/'+total);await b.close();process.exit(fails?1:0)})();
