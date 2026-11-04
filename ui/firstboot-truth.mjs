// Native receipts are the sole source of first-boot status. Never infer GPU or training.
const obj=x=>x!==null&&typeof x==='object'&&!Array.isArray(x);
const held=x=>obj(x)&&(x.ok===false||x.ack===false||(x.errorCode!=null&&String(x.errorCode).trim()!=='')||['HOLD','FAILED','ERROR','DENIED','REJECTED','OFFLINE','UNAVAILABLE','STOPPED'].includes(String(x.status||'').toUpperCase()));
export function firstBootTruth(a1,capabilities,models){
 const a=obj(a1)&&a1.routeId==='chat.commands'&&a1.state==='COMPLETED'&&!held(a1)&&obj(a1.result)&&!held(a1.result)&&a1.result.schema==='NOX-A1-NATIVE-COMMAND-STATUS-v1'?a1.result:null;
 const c=obj(capabilities)&&capabilities.routeId==='chat.commands'&&capabilities.state==='COMPLETED'&&!held(capabilities)&&obj(capabilities.result)&&!held(capabilities.result)&&capabilities.result.status==='SOURCE_SERVICE'?capabilities.result:null;
 const m=obj(models)&&models.routeId==='chat.model'&&models.state==='COMPLETED'&&!held(models)&&obj(models.result)&&!held(models.result)&&Array.isArray(models.result.models)?models.result:null;
 const a1Ready=!!(a&&a.state==='ACTIVE_NATIVE_BOOT_RECEIPT'&&a.native_bound===true);
 const canPropose=!!(c&&obj(c.actions)&&obj(c.actions['selfbuilder.propose'])&&c.actions['selfbuilder.propose'].available===true&&c.actions['selfbuilder.propose'].status==='AVAILABLE');
 const count=m?m.models.length:null;
 return {
   summary:a1Ready?'A1 подтвердил запуск; остальные возможности проверяются отдельно.':'Я запущен. Проверяю подключение и разрешения OneHost; автономность пока не подтверждена.',
   items:[
     ['A1 / FirstBoot',a1Ready?'NATIVE READY':'HOLD · нет подтверждения'],
     ['Локальные модели',count===null?'HOLD · нет ответа OneHost':count>0?String(count)+' · обнаружены OneHost':'0 · требуется загрузка'],
     ['Самодоработка',canPropose?'Запрос доступен · требуется согласие':'HOLD · запрос не подтверждён'],
     ['S03 / RAG','Не проверено этим запросом'],
     ['GPU / LoRA','Обучение не подтверждено']
   ],
   verified:{a1:a1Ready,modelInventory:count!==null,selfbuildRequest:canPropose},
   training_started:false,weights_updated:false,code_merged:false
 };
}
